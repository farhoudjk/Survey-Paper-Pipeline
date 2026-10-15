"""Corpus tools. The orchestrator calls these functions; agents may use the CLI to look at the corpus.

python pipeline/corpus.py stats                      # counts by status and round
python pipeline/corpus.py show <id>                  # one paper record
python pipeline/corpus.py list --status included     # ids and titles
python pipeline/corpus.py bib --out paper/refs.bib   # BibTeX of included papers

Paper ids are also the BibTeX keys, for example kwon2023efficient.
"""
import argparse
import json
import re
import sys
import unicodedata

from common import STATE, read_json, write_json

CORPUS = STATE / "corpus.json"
PRISMA = STATE / "prisma.json"
NOTES = STATE / "notes"
TAXONOMY = STATE / "taxonomy.json"
STOP = {"a", "an", "the", "on", "of", "for", "to", "in", "and", "with", "towards", "toward", "via", "is", "are", "at", "by"}


# ---------- basic helpers ----------

def ascii_letters(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]", "", s.lower())


def norm_title(t):
    return re.sub(r"[^a-z0-9]", "", ascii_letters_keep_digits(t))


def ascii_letters_keep_digits(s):
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()


def norm_doi(d):
    if not d:
        return None
    d = d.lower().strip()
    d = re.sub(r"^https?://(dx\.)?doi\.org/", "", d)
    return d or None


def arxiv_id(h):
    for f in ("arxiv", "url", "doi"):
        v = h.get(f) or ""
        m = re.search(r"(\d{4}\.\d{4,5})", v) if ("arxiv" in v.lower() or f == "arxiv") else None
        if m:
            return m.group(1)
    return None


def load():
    return read_json(CORPUS, {"papers": {}, "rounds": {}})


def save(c):
    write_json(CORPUS, c)


def make_id(h, used):
    authors = h.get("authors") or []
    first = authors[0] if authors else "anon"
    surname = ascii_letters(first.split()[-1] if first.split() else "anon") or "anon"
    word = next((ascii_letters(w) for w in (h.get("title") or "").split()
                 if ascii_letters(w) and ascii_letters(w) not in STOP), "paper")
    base = f"{surname}{h.get('year') or 'nd'}{word}"
    pid, k = base, 0
    while pid in used:
        k += 1
        pid = base + "abcdefghijklmnopqrstuvwxyz"[(k - 1) % 26] * (1 + (k - 1) // 26)
    return pid


def index(c):
    idx = {}
    for pid, p in c["papers"].items():
        for key in (("t", norm_title(p["title"])), ("d", norm_doi(p.get("doi"))), ("a", p.get("arxiv"))):
            if key[1]:
                idx[key] = pid
    return idx


# ---------- merge search / snowball hits ----------

def read_hit_files(files):
    hits = []
    for f in files:
        data = read_json(f, {})
        src = data.get("query") or data.get("seed") or f
        for h in data.get("hits", []):
            h = dict(h)
            h.setdefault("_found_by", data.get("found_by") or f"query:{src}")
            hits.append(h)
    return hits


def merge(files, rnd, year_from=None, keywords_any=None):
    """Add hits to the corpus. Returns dict with counts."""
    c = load()
    idx = index(c)
    used = set(c["papers"])
    hits = read_hit_files(files)
    new, dup, auto_ex = 0, 0, 0
    kws = [k.lower() for k in (keywords_any or []) if k.strip()]
    for h in hits:
        if not h.get("title"):
            continue
        h["doi"] = norm_doi(h.get("doi"))
        h["arxiv"] = arxiv_id(h)
        keys = [("t", norm_title(h["title"])), ("d", h["doi"]), ("a", h["arxiv"])]
        pid = next((idx[k] for k in keys if k[1] and k in idx), None)
        if pid:
            dup += 1
            p = c["papers"][pid]
            if h["_found_by"] not in p["found_by"]:
                p["found_by"].append(h["_found_by"])
            for f in ("abstract", "venue", "doi", "arxiv", "url", "s2_id", "citations", "year", "pdf_url"):
                if not p.get(f) and h.get(f):
                    p[f] = h[f]
            continue
        pid = make_id(h, used)
        used.add(pid)
        p = {"id": pid, "title": " ".join(h["title"].split()), "year": h.get("year"),
             "venue": h.get("venue"), "authors": h.get("authors") or [], "abstract": h.get("abstract"),
             "url": h.get("url"), "doi": h["doi"], "arxiv": h["arxiv"], "s2_id": h.get("s2_id"),
             "pdf_url": h.get("pdf_url"), "citations": h.get("citations"),
             "found_round": rnd, "found_by": [h["_found_by"]],
             "status": "candidate", "stage": None, "reason": None}
        text = f"{p['title']} {p.get('abstract') or ''}".lower()
        if year_from and p["year"] and int(p["year"]) < int(year_from):
            p.update(status="excluded", stage="auto", reason=f"published before {year_from}")
            auto_ex += 1
        elif kws and not any(k in text for k in kws):
            p.update(status="excluded", stage="auto", reason="no topic keyword in title or abstract")
            auto_ex += 1
        c["papers"][pid] = p
        for k in [("t", norm_title(p["title"])), ("d", p["doi"]), ("a", p["arxiv"])]:
            if k[1]:
                idx[k] = pid
        new += 1
    r = c["rounds"].setdefault(str(rnd), {"hits": 0, "new": 0, "duplicates": 0, "auto_excluded": 0})
    r["hits"] += len(hits)
    r["new"] += new
    r["duplicates"] += dup
    r["auto_excluded"] += auto_ex
    save(c)
    return {"hits": len(hits), "new": new, "duplicates": dup, "auto_excluded": auto_ex}


# ---------- screening ----------

def todo_screen():
    c = load()
    return [{k: p.get(k) for k in ("id", "title", "year", "venue", "authors", "abstract", "url", "found_by")}
            for p in c["papers"].values() if p["status"] == "candidate"]


def apply_screen(files, rnd):
    c = load()
    applied, unknown = 0, []
    for f in files:
        for d in read_json(f, {}).get("decisions", []):
            p = c["papers"].get(d.get("id"))
            if not p:
                unknown.append(d.get("id"))
                continue
            dec = d.get("decision")
            if dec not in ("include", "exclude"):
                continue
            p.update(status="included" if dec == "include" else "excluded",
                     stage=d.get("stage", "title_abstract"), reason=d.get("reason"),
                     criterion=d.get("criterion"), screened_round=rnd)
            if dec == "include":
                p.setdefault("included_round", rnd)
            applied += 1
    save(c)
    left = sum(1 for p in c["papers"].values() if p["status"] == "candidate")
    return {"applied": applied, "unknown_ids": unknown, "still_candidate": left}


def included(c=None):
    c = c or load()
    return [p for p in c["papers"].values() if p["status"] == "included"]


def saturation(rnd):
    """Share of included papers that were first included in this round."""
    inc = included()
    if not inc:
        return 1.0, 0, 0
    new = sum(1 for p in inc if p.get("included_round") == rnd)
    return new / len(inc), new, len(inc)


def snowball_seeds(rnd, max_seeds):
    """Papers included in the previous round, most cited first."""
    inc = [p for p in included() if p.get("included_round") == rnd - 1]
    inc.sort(key=lambda p: p.get("citations") or 0, reverse=True)
    return [{"id": p["id"], "title": p["title"], "s2_id": p.get("s2_id"), "doi": p.get("doi"),
             "arxiv": p.get("arxiv")} for p in inc[:max_seeds]]


# ---------- PRISMA ----------

def prisma():
    c = load()
    ps = list(c["papers"].values())
    identified = sum(r["hits"] for r in c["rounds"].values())
    unique = len(ps)
    auto = [p for p in ps if p["status"] == "excluded" and p.get("stage") == "auto"]
    ta = [p for p in ps if p["status"] == "excluded" and p.get("stage") == "title_abstract"]
    ft = [p for p in ps if p["status"] == "excluded" and p.get("stage") == "full_text"]
    inc = [p for p in ps if p["status"] == "included"]
    reasons = {}
    for p in ft:
        r = p.get("criterion") or (p.get("reason") or "other")[:60]
        reasons[r] = reasons.get(r, 0) + 1
    out = {"identified": identified, "duplicates_removed": identified - unique, "unique_records": unique,
           "auto_excluded": len(auto), "screened": unique - len(auto),
           "excluded_title_abstract": len(ta), "full_text_assessed": len(ft) + len(inc),
           "excluded_full_text": len(ft), "excluded_full_text_reasons": reasons,
           "included": len(inc), "rounds": c["rounds"],
           "candidates_left": sum(1 for p in ps if p["status"] == "candidate")}
    write_json(PRISMA, out)
    return out


# ---------- notes ----------

def pending_notes():
    return [p["id"] for p in included() if not (NOTES / f"{p['id']}.json").exists()]


def validate_notes(schema_path):
    req = read_json(schema_path, {}).get("required", [])
    bad = {}
    for p in included():
        n = read_json(NOTES / f"{p['id']}.json")
        if n is None:
            bad[p["id"]] = ["missing file"]
            continue
        miss = [k for k in req if k not in n or n[k] in (None, "", [])]
        if n.get("id") != p["id"]:
            miss.append("id does not match file name")
        if miss:
            bad[p["id"]] = miss
    return bad


# ---------- taxonomy coverage ----------

def coverage(min_per_category):
    tax = read_json(TAXONOMY)
    if not tax:
        return {"thin": [], "unassigned": [], "counts": {}}
    inc_ids = {p["id"] for p in included()}
    counts = {}
    for d in tax.get("dimensions", []):
        for cat in d.get("categories", []):
            counts[(d["id"], cat["id"])] = 0
    assigned = set()
    for pid, a in tax.get("assignments", {}).items():
        if pid not in inc_ids:
            continue
        assigned.add(pid)
        for dim, cats in a.items():
            for cat in cats if isinstance(cats, list) else [cats]:
                if (dim, cat) in counts:
                    counts[(dim, cat)] += 1
    names = {(d["id"], cat["id"]): f"{d.get('name', d['id'])} / {cat.get('name', cat['id'])}"
             for d in tax.get("dimensions", []) for cat in d.get("categories", [])}
    thin = [{"dimension": k[0], "category": k[1], "name": names[k], "papers": v}
            for k, v in counts.items() if v < min_per_category]
    return {"thin": thin, "unassigned": sorted(inc_ids - assigned),
            "counts": {names[k]: v for k, v in counts.items()}}


def stats_for_analysis():
    """Counts the analyst can rely on (computed, not estimated)."""
    c = load()
    inc = included(c)
    tax = read_json(TAXONOMY, {})
    by_year, by_venue, by_cat_year = {}, {}, {}
    prim = tax.get("primary_dimension")
    cat_names = {cat["id"]: cat.get("name", cat["id"]) for d in tax.get("dimensions", [])
                 if d["id"] == prim for cat in d.get("categories", [])}
    for p in inc:
        y = str(p.get("year") or "unknown")
        by_year[y] = by_year.get(y, 0) + 1
        v = p.get("venue") or "unknown"
        by_venue[v] = by_venue.get(v, 0) + 1
        a = tax.get("assignments", {}).get(p["id"], {}).get(prim)
        for cat in (a if isinstance(a, list) else [a] if a else []):
            key = cat_names.get(cat, cat)
            by_cat_year.setdefault(key, {})
            by_cat_year[key][y] = by_cat_year[key].get(y, 0) + 1
    return {"included": len(inc), "by_year": dict(sorted(by_year.items())),
            "by_venue": dict(sorted(by_venue.items(), key=lambda kv: -kv[1])),
            "by_primary_category_and_year": by_cat_year, "prisma": prisma()}


# ---------- BibTeX ----------

def tex_escape(s):
    s = s or ""
    for a, b in [("\\", r"\textbackslash{}"), ("&", r"\&"), ("%", r"\%"), ("$", r"\$"),
                 ("#", r"\#"), ("_", r"\_"), ("{", r"\{"), ("}", r"\}")]:
        s = s.replace(a, b)
    return s


def bib(out):
    lines = []
    for p in sorted(included(), key=lambda p: p["id"]):
        venue = p.get("venue") or ""
        is_arxiv = (not venue) or "arxiv" in venue.lower()
        f = {"title": "{" + tex_escape(p["title"]) + "}",
             "author": " and ".join(tex_escape(a) for a in p.get("authors") or []) or "Unknown",
             "year": str(p.get("year") or "")}
        if is_arxiv:
            kind = "misc"
            f["howpublished"] = f"arXiv:{p['arxiv']}" if p.get("arxiv") else "Preprint"
            if p.get("arxiv"):
                f["eprint"], f["archiveprefix"] = p["arxiv"], "arXiv"
        else:
            kind = "inproceedings"
            f["booktitle"] = tex_escape(venue)
        if p.get("doi"):
            f["doi"] = p["doi"]
        if p.get("url"):
            f["url"] = p["url"]
        body = ",\n".join(f"  {k} = {{{v}}}" for k, v in f.items() if v)
        lines.append(f"@{kind}{{{p['id']},\n{body}\n}}\n")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("% Generated by pipeline/corpus.py from state/corpus.json. Do not edit by hand.\n\n")
        fh.write("\n".join(lines))
    return len(lines)


# ---------- CLI ----------

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("stats")
    s = sub.add_parser("show")
    s.add_argument("id")
    s = sub.add_parser("list")
    s.add_argument("--status", default="included")
    s = sub.add_parser("bib")
    s.add_argument("--out", default="paper/refs.bib")
    sub.add_parser("prisma")
    a = ap.parse_args()
    c = load()
    if a.cmd == "stats":
        st = {}
        for p in c["papers"].values():
            st[p["status"]] = st.get(p["status"], 0) + 1
        print(json.dumps({"by_status": st, "rounds": c["rounds"]}, indent=2))
    elif a.cmd == "show":
        print(json.dumps(c["papers"].get(a.id) or {"error": "not found"}, indent=2, ensure_ascii=False))
    elif a.cmd == "list":
        for p in sorted(c["papers"].values(), key=lambda p: p["id"]):
            if p["status"] == a.status:
                print(f"{p['id']}\t{p.get('year')}\t{p['title']}")
    elif a.cmd == "bib":
        print(f"Wrote {bib(a.out)} entries to {a.out}")
    elif a.cmd == "prisma":
        print(json.dumps(prisma(), indent=2))


if __name__ == "__main__":
    sys.exit(main())
