"""Run the survey pipeline. Run inside a survey PROJECT folder (not the template).

    python pipeline/orchestrator.py                  # normal run, resumes where it stopped
    python pipeline/orchestrator.py --auto           # no human checkpoints
    python pipeline/orchestrator.py --from-step taxonomy   # redo from a step

Steps: scope, collect, extract, taxonomy, analysis, bench, write, review
"""
import argparse
import glob
import shutil
import subprocess
import sys
import time
import zipfile

import corpus
from common import (HANDOFF, ROOT, STATE, chunks, git_pull, git_push, guard_not_template, load_config,
                    now, read_json, rel, require, run_agent, run_agents_parallel, write_json)

CFG = load_config()
STEPS = ["scope", "collect", "extract", "taxonomy", "analysis", "bench", "write", "review"]
PROGRESS = STATE / "progress.json"
SCHEMA = ROOT / ".claude" / "skills" / "extraction-schema" / "schema.json"
SKILLS = ROOT / ".claude" / "skills"
AUTO = False


def checkpoint(msg):
    if AUTO or not CFG.get("pause_at_checkpoints", True):
        return
    ans = input(f"\n[CHECKPOINT] {msg}\nPress Enter to continue, or type q to stop: ").strip().lower()
    if ans == "q":
        print("Stopped. Run again later; finished steps are kept in state/.")
        sys.exit(0)


def done(step):
    p = read_json(PROGRESS, {"done": []})
    if step not in p["done"]:
        p["done"].append(step)
    write_json(PROGRESS, p)
    git_push(["state", "paper"], f"survey: step {step} done")


def protocol():
    return read_json(STATE / "protocol.json", {})


def next_round():
    rounds = [int(r) for r in corpus.load()["rounds"]]
    return max(rounds, default=0) + 1


# ---------- 1. scope ----------

def step_scope():
    run_agent("scope-definer", (
        "Read inputs/topic.md, any seed list in inputs/seeds.md and the PDFs in inputs/papers/. "
        "Write state/protocol.md and state/protocol.json as your instructions say."), CFG)
    require(STATE / "protocol.json", "scope-definer")
    git_push(["state"], "survey: protocol")
    checkpoint("CP1. Read state/protocol.md and state/protocol.json (research questions, rules, queries). "
               "Edit them if needed.")


# ---------- 2. collect + screen ----------

def collect_round(rnd, mode, queries=None):
    """One collection round followed by screening. Returns number of newly included papers."""
    out = STATE / "collect" / f"round_{rnd:02d}"
    out.mkdir(parents=True, exist_ok=True)
    pr = protocol()
    if mode == "snowball":
        seeds = corpus.snowball_seeds(rnd, CFG["max_snowball_seeds"])
        if not seeds:
            print(f"Round {rnd}: no new seeds to snowball from.")
            return 0
        write_json(out / "seeds.json", {"seeds": seeds})
        task = (f"Round {rnd}. Mode: snowball. Seeds: {rel(out)}/seeds.json. "
                f"Limit per seed and direction: {CFG['snowball_limit']}. Save results in {rel(out)}/.")
    elif mode == "targeted":
        write_json(out / "queries.json", {"queries": queries or []})
        task = (f"Round {rnd}. Mode: targeted. Run the queries in {rel(out)}/queries.json "
                f"(each has a reason). Save results in {rel(out)}/.")
    else:
        task = (f"Round {rnd}. Mode: search. Run every query in state/protocol.json on every source. "
                f"Also find the seed papers listed in state/protocol.json. Save results in {rel(out)}/.")
    run_agent("paper-collector", task, CFG)
    files = [f for f in glob.glob(str(out / "hits_*.json"))]
    m = corpus.merge(files, rnd, pr.get("year_from"), pr.get("keywords_any"))
    print(f"Round {rnd} ({mode}): {m['hits']} hits, {m['new']} new, {m['duplicates']} duplicates, "
          f"{m['auto_excluded']} auto-excluded.")
    screen(rnd)
    _, new_inc, total = corpus.saturation(rnd)
    corpus.prisma()
    git_push(["state"], f"survey: collect round {rnd} ({mode})")
    print(f"Round {rnd}: {new_inc} newly included, {total} included in total.")
    return new_inc


def screen(rnd, tries=2):
    sd = STATE / "screen" / f"round_{rnd:02d}"
    for attempt in range(tries):
        todo = corpus.todo_screen()
        if not todo:
            return
        jobs = []
        for k, batch in enumerate(chunks(todo, CFG["screen_batch"]), 1):
            tag = f"{attempt + 1}_{k:03d}"
            write_json(sd / f"todo_{tag}.json", {"papers": batch})
            jobs.append(("screener", (
                f"Round {rnd}. Screen the papers in {rel(sd)}/todo_{tag}.json against state/protocol.json. "
                f"Write {rel(sd)}/decisions_{tag}.json.")))
        print(f"Screening {len(todo)} candidates in {len(jobs)} batches...")
        run_agents_parallel(jobs, CFG)
        r = corpus.apply_screen(glob.glob(str(sd / f"decisions_{attempt + 1}_*.json")), rnd)
        print(f"   applied {r['applied']} decisions, {r['still_candidate']} still undecided.")
        if r["unknown_ids"]:
            print(f"   WARNING: unknown ids in decisions: {r['unknown_ids'][:10]}")


def step_collect():
    rnd = next_round()
    if rnd == 1:
        collect_round(1, "search")
        rnd = 2
    while rnd <= CFG["max_collect_rounds"]:
        collect_round(rnd, "snowball")
        share, new_inc, total = corpus.saturation(rnd)
        print(f"Saturation check: {share:.1%} of included papers are new this round "
              f"(threshold {CFG['saturation_threshold']:.0%}).")
        if share < CFG["saturation_threshold"]:
            print("Saturated. Collection stops.")
            break
        rnd += 1
    n = len(corpus.included())
    if n > CFG["max_papers_warning"]:
        print(f"WARNING: {n} included papers. Consider tighter rules in state/protocol.json.")
    p = corpus.prisma()
    checkpoint(f"CP2. {p['included']} papers included. Check them with "
               "'python pipeline/corpus.py list --status included'. To change a decision, edit the "
               "'status' field in state/corpus.json.")


# ---------- 3. extract ----------

def extract(ids, mode="extract", extra=""):
    if not ids:
        return
    jobs = []
    bd = STATE / "extract_batches"
    stamp = time.strftime("%Y%m%d%H%M%S")
    for k, batch in enumerate(chunks(ids, CFG["extract_batch"]), 1):
        f = bd / f"{mode}_{stamp}_{k:03d}.json"
        write_json(f, {"ids": batch})
        jobs.append(("extractor", f"Mode: {mode}. Papers: {rel(f)}. {extra}".strip()))
    print(f"Extractor ({mode}): {len(ids)} papers in {len(jobs)} batches...")
    run_agents_parallel(jobs, CFG)


def step_extract():
    extract(corpus.pending_notes())
    bad = corpus.validate_notes(SCHEMA)
    if bad:
        print(f"{len(bad)} notes are missing or incomplete. Retrying once...")
        extract(sorted(bad), "extract", "Some notes were missing or incomplete; redo them fully.")
        bad = corpus.validate_notes(SCHEMA)
        if bad:
            print(f"WARNING: still incomplete: {list(bad)[:10]}")
            if len(bad) > 0.1 * max(1, len(corpus.included())):
                git_push(["state"], "survey: extraction (partial)")
                raise SystemExit(f"Stopping: {len(bad)} notes are missing or incomplete (more than 10%). "
                                 "Read the newest extractor logs in logs/, fix the cause, then run "
                                 "'python pipeline/orchestrator.py' again (it continues with extraction).")
    git_push(["state"], "survey: extraction")


# ---------- 4. taxonomy ----------

def build_taxonomy(mode):
    run_agent("taxonomy-builder", (
        f"Mode: {mode}. Build or update state/taxonomy.json from the notes in state/notes/ "
        f"for every included paper. Minimum papers per category: {CFG['min_per_category']}."), CFG)
    require(STATE / "taxonomy.json", "taxonomy-builder")


def add_papers(queries, reason):
    """Targeted search -> screen -> extract new included papers."""
    rnd = next_round()
    before = {p["id"] for p in corpus.included()}
    collect_round(rnd, "targeted", queries)
    new_ids = [p["id"] for p in corpus.included() if p["id"] not in before]
    extract(new_ids)
    print(f"{reason}: {len(new_ids)} new papers added.")
    return new_ids


def step_taxonomy():
    build_taxonomy("build")
    for loop in range(CFG["max_coverage_loops"]):
        tax = read_json(STATE / "taxonomy.json", {})
        if tax.get("new_fields"):
            print(f"Taxonomy asks for new note fields: {[f['name'] for f in tax['new_fields']]}")
            extract([p["id"] for p in corpus.included()], "add-fields",
                    "Add the fields listed under new_fields in state/taxonomy.json.")
        cov = corpus.coverage(CFG["min_per_category"])
        if cov["unassigned"]:
            print(f"{len(cov['unassigned'])} included papers have no category.")
        queries = [q for q in tax.get("gap_queries", []) if q.get("query")]
        if not cov["thin"] and not tax.get("new_fields") and not cov["unassigned"]:
            break
        if cov["thin"]:
            print("Thin categories: " + ", ".join(f"{t['name']} ({t['papers']})" for t in cov["thin"]))
        if cov["thin"] and queries:
            add_papers(queries, "Coverage search")
        build_taxonomy("update")
    write_json(STATE / "coverage.json", corpus.coverage(CFG["min_per_category"]))
    git_push(["state"], "survey: taxonomy")
    checkpoint("CP3. Read state/taxonomy.json and state/coverage.json. The taxonomy shapes the whole "
               "survey. Edit it if needed.")


# ---------- 5. analysis ----------

def step_analysis():
    write_json(STATE / "analysis" / "stats.json", corpus.stats_for_analysis())
    run_agent("analyst", (
        "Analyze the included papers. Inputs: state/protocol.json, state/taxonomy.json, state/notes/, "
        "state/analysis/stats.json (exact counts, use these numbers). Write the files in state/analysis/ "
        "as your instructions say." + (" Also write state/analysis/bench_plan.json." if CFG["benchmark"] else "")),
        CFG)
    require(STATE / "analysis" / "challenges.md", "analyst")
    git_push(["state"], "survey: analysis")


# ---------- 6. optional GPU benchmark ----------

def step_bench():
    if not CFG.get("benchmark"):
        print("Benchmark is off (benchmark: false in config.yaml). Skipping.")
        return
    if not (STATE / "analysis" / "bench_plan.json").exists():
        print("No bench_plan.json. Skipping benchmark.")
        return
    job = {"job_id": f"bench-{int(time.time())}", "kind": "bench", "plan": "state/analysis/bench_plan.json",
           "created_at": now()}
    write_json(HANDOFF / "to_gpu.json", job)
    git_push(["state"], f"survey: GPU job {job['job_id']}")
    print(f"Sent benchmark job {job['job_id']}. Waiting for the GPU watcher...")
    deadline = time.time() + CFG["gpu_wait_hours"] * 3600
    while time.time() < deadline:
        time.sleep(CFG["poll_seconds"])
        git_pull()
        fr = read_json(HANDOFF / "from_gpu.json", {})
        if fr.get("job_id") == job["job_id"] and fr.get("status") in ("done", "failed"):
            print(f"Benchmark {fr['status']}.")
            return
    print("WARNING: benchmark timed out. Continuing without it.")


# ---------- 7. write ----------

def make_assets():
    corpus.prisma()
    n = corpus.bib(ROOT / "paper" / "refs.bib")
    subprocess.run([sys.executable, str(SKILLS / "survey-latex" / "make_survey_figures.py"),
                    "--state", str(STATE), "--out", str(ROOT / "paper")], check=True)
    print(f"refs.bib has {n} entries; figures and tables regenerated.")


def citation_check():
    out = STATE / "citation_check.json"
    r = subprocess.run([sys.executable, str(SKILLS / "citation-check" / "check_citations.py"),
                        "--paper", str(ROOT / "paper"), "--state", str(STATE), "--out", str(out)])
    return r.returncode == 0, out


def fix_citations():
    for i in range(CFG["max_citation_fixes"] + 1):
        ok, out = citation_check()
        if ok:
            print("Citation check passed.")
            return
        if i == CFG["max_citation_fixes"]:
            print(f"WARNING: citation check still failing. See {rel(out)}.")
            return
        run_agent("survey-writer", f"Mode: fix-citations. Fix every problem in {rel(out)}.", CFG)


def zip_paper():
    """Zip paper/ for Overleaf, without build files."""
    p = ROOT / "paper"
    z = p / "overleaf.zip"
    skip = {".aux", ".log", ".fls", ".fdb_latexmk", ".out", ".blg", ".bbl", ".synctex.gz", ".toc", ".zip"}
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(p.rglob("*")):
            if f.is_file() and not any(str(f).endswith(e) for e in skip):
                zf.write(f, f.relative_to(p))
    print(f"Overleaf zip: {rel(z)}")


def step_write():
    tpl = SKILLS / "survey-latex" / "template"
    if not (ROOT / "paper" / "main.tex").exists():
        shutil.copytree(tpl, ROOT / "paper", dirs_exist_ok=True)
    make_assets()
    run_agent("survey-writer", (
        "Mode: draft. Write the survey in paper/ from state/protocol.json, state/taxonomy.json, "
        "state/notes/, state/analysis/, state/prisma.json"
        + (", state/bench/" if (STATE / "bench").exists() else "") + "."), CFG)
    fix_citations()
    zip_paper()
    git_push(["paper", "state"], "survey: draft")


# ---------- 8. review ----------

def step_review():
    for i in range(1, CFG["max_review_loops"] + 1):
        out = STATE / "review" / f"review_{i:02d}.json"
        citation_check()
        run_agent("survey-reviewer", (
            f"Review {i}. Review paper/ against the evidence in state/. Earlier reviews: state/review/. "
            f"Citation check report: state/citation_check.json. Output: {rel(out)}."), CFG)
        require(out, "survey-reviewer")
        rev = read_json(out)
        git_push(["state"], f"survey: review {i}")
        mp, fe, pi = (rev.get("missing_papers", []), rev.get("fact_errors", []),
                      rev.get("presentation_issues", []))
        print(f"Review {i}: {rev['decision']} ({len(mp)} missing papers, {len(fe)} fact errors, "
              f"{len(pi)} presentation issues)")
        if rev["decision"] == "accept":
            zip_paper()
            git_push(["paper", "state"], "survey: accepted")
            print("\nDONE. Upload paper/overleaf.zip to Overleaf (New project > Upload project).")
            return
        checkpoint(f"CP4. Review {i} asks for changes. Read {rel(out)}.")
        if mp:
            queries = [{"query": m.get("query") or m.get("title"), "reason": m.get("why", "reviewer")} for m in mp]
            new_ids = add_papers(queries, "Reviewer missing papers")
            if new_ids:
                build_taxonomy("update")
        if fe:
            ids = sorted({f["paper_id"] for f in fe if f.get("paper_id")})
            extract(ids, "fix", f"Fix the fact_errors listed in {rel(out)} for these papers.")
        make_assets()
        run_agent("survey-writer", (
            f"Mode: revise. Fix every issue in {rel(out)}. Notes, taxonomy, figures and tables may have "
            "changed; use the current versions. Log your changes in paper/CHANGES.md."), CFG)
        fix_citations()
        zip_paper()
        git_push(["paper", "state"], f"survey: revision {i}")
    print("\nReached max review loops. The latest survey is in paper/. Read the last review.")


RUN = {"scope": step_scope, "collect": step_collect, "extract": step_extract, "taxonomy": step_taxonomy,
       "analysis": step_analysis, "bench": step_bench, "write": step_write, "review": step_review}


def main():
    global AUTO
    ap = argparse.ArgumentParser()
    ap.add_argument("--auto", action="store_true", help="skip human checkpoints")
    ap.add_argument("--from-step", choices=STEPS, help="redo from this step on")
    ap.add_argument("--only", choices=STEPS, help="run just this one step")
    a = ap.parse_args()
    guard_not_template(CFG)
    AUTO = a.auto
    git_pull()
    prog = read_json(PROGRESS, {"done": []})
    if a.from_step:
        prog["done"] = [s for s in prog["done"] if STEPS.index(s) < STEPS.index(a.from_step)]
        write_json(PROGRESS, prog)
    steps = [a.only] if a.only else STEPS
    for s in steps:
        if s in prog["done"] and not a.only:
            print(f"Step {s}: already done (use --from-step {s} to redo).")
            continue
        print(f"\n========== STEP: {s} ==========")
        RUN[s]()
        done(s)


if __name__ == "__main__":
    main()
