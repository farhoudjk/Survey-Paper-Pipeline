"""Make survey figures and tables from the pipeline state (deterministic, no LLM).

python make_survey_figures.py --state state --out paper

Writes:
  paper/figures/papers_per_year.pdf      included papers per year, stacked by primary category
  paper/figures/categories_<dim>.pdf     papers per category, one chart per dimension
  paper/generated/prisma.tex             PRISMA flow diagram (TikZ)
  paper/generated/taxonomy_tree.tex      taxonomy tree with citations (forest)
  paper/tables/compare_<category>.tex    comparison table(s) per primary category (table* floats, 16 rows each)
  paper/tables/eval_landscape.tex        most used hardware, models, workloads, metrics
  paper/tables/prisma_counts.tex         numbers behind the PRISMA diagram
"""
import argparse
import collections
import json
import pathlib

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# Validated categorical palette (fixed order, never cycled). More than 8 categories fold into "Other".
PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
OTHER = "#8a8985"
ROWS_PER_TABLE = 16
RR = r">{\raggedright\arraybackslash}"  # ragged-right table column
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"
plt.rcParams.update({"font.size": 8, "axes.edgecolor": MUTED, "axes.labelcolor": INK, "xtick.color": MUTED,
                     "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False,
                     "pdf.fonttype": 42})


def tex(s):
    s = str(s or "")
    for a, b in [("\\", r"\textbackslash{}"), ("&", r"\&"), ("%", r"\%"), ("$", r"\$"), ("#", r"\#"),
                 ("_", r"\_"), ("{", r"\{"), ("}", r"\}"), ("~", r"\textasciitilde{}"), ("^", r"\^{}")]:
        s = s.replace(a, b)
    return s


def short(s, n=110):
    s = " ".join(str(s or "").split())
    first = s.split(". ")[0]
    s = first if len(first) <= n else s
    return s if len(s) <= n else s[: n - 3].rsplit(" ", 1)[0] + "..."


def as_list(x):
    return x if isinstance(x, list) else ([x] if x else [])


def load(state):
    c = json.loads((state / "corpus.json").read_text(encoding="utf-8"))
    inc = {pid: p for pid, p in c["papers"].items() if p["status"] == "included"}
    tax = json.loads((state / "taxonomy.json").read_text(encoding="utf-8")) if (state / "taxonomy.json").exists() else {}
    notes = {}
    for pid in inc:
        f = state / "notes" / f"{pid}.json"
        if f.exists():
            notes[pid] = json.loads(f.read_text(encoding="utf-8"))
    prisma = json.loads((state / "prisma.json").read_text(encoding="utf-8")) if (state / "prisma.json").exists() else {}
    return inc, tax, notes, prisma


def dim_cats(tax, dim_id):
    for d in tax.get("dimensions", []):
        if d["id"] == dim_id:
            return d, d.get("categories", [])
    return None, []


def members(tax, inc, dim_id, cat_id):
    out = []
    for pid, a in tax.get("assignments", {}).items():
        if pid in inc and cat_id in as_list(a.get(dim_id)):
            out.append(pid)
    return sorted(out, key=lambda k: (inc[k].get("year") or 0, k))


def fig_per_year(inc, tax, out):
    prim = tax.get("primary_dimension")
    _, cats = dim_cats(tax, prim)
    names = [c.get("name", c["id"]) for c in cats]
    keep = names[:8]
    years = sorted({p.get("year") for p in inc.values() if p.get("year")})
    if not years:
        return None
    counts = {n: collections.Counter() for n in keep + ["Other"]}
    for pid, p in inc.items():
        first = next(iter(as_list(tax.get("assignments", {}).get(pid, {}).get(prim))), None)
        name = next((c.get("name", c["id"]) for c in cats if c["id"] == first), None)
        counts[name if name in keep else "Other"][p.get("year")] += 1
    series = [n for n in keep + ["Other"] if sum(counts[n].values())]
    fig, ax = plt.subplots(figsize=(3.4, 2.3))
    bottom = [0] * len(years)
    for i, n in enumerate(series):
        vals = [counts[n][y] for y in years]
        ax.bar([str(y) for y in years], vals, bottom=bottom, width=0.7, label=n,
               color=PALETTE[i] if n != "Other" else OTHER, edgecolor="white", linewidth=1.0)
        bottom = [b + v for b, v in zip(bottom, vals)]
    ax.set_ylabel("Included papers")
    ax.grid(axis="y", color=GRID, linewidth=0.5)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, fontsize=6.5, ncol=2, loc="lower left", bbox_to_anchor=(0, 1.0),
              borderaxespad=0.3, handlelength=1.2)
    fig.tight_layout()
    path = out / "figures" / "papers_per_year.pdf"
    fig.savefig(path)
    plt.close(fig)
    return path


def fig_categories(inc, tax, out):
    made = []
    for d in tax.get("dimensions", []):
        cats = d.get("categories", [])
        rows = [(c.get("name", c["id"]), len(members(tax, inc, d["id"], c["id"]))) for c in cats]
        if not rows:
            continue
        fig, ax = plt.subplots(figsize=(3.4, 0.26 * len(rows) + 0.7))
        ax.barh(range(len(rows)), [r[1] for r in rows], color=PALETTE[0], height=0.62, edgecolor="white")
        ax.set_yticks(range(len(rows)), [r[0] for r in rows])
        ax.invert_yaxis()
        for i, (_, v) in enumerate(rows):
            ax.text(v + 0.2, i, str(v), va="center", fontsize=7, color=INK)
        ax.set_xlabel(f"Papers ({d.get('name', d['id'])})")
        ax.grid(axis="x", color=GRID, linewidth=0.5)
        ax.set_axisbelow(True)
        fig.tight_layout()
        path = out / "figures" / f"categories_{d['id']}.pdf"
        fig.savefig(path)
        plt.close(fig)
        made.append(path)
    return made


def prisma_tex(prisma, out):
    p = collections.defaultdict(int, prisma)
    reasons = "; ".join(f"{tex(k)}: {v}" for k, v in sorted(p.get("excluded_full_text_reasons", {}).items())) or "none"
    t = rf"""% Generated by make_survey_figures.py. Do not edit.
\begin{{tikzpicture}}[font=\footnotesize, node distance=0.45cm,
  box/.style={{draw, rounded corners=2pt, text width=4.6cm, align=center, inner sep=4pt}},
  side/.style={{draw, rounded corners=2pt, text width=3.6cm, align=left, inner sep=4pt}},
  arr/.style={{-latex}}]
\node[box] (id) {{Records identified (search and snowballing)\\ $n={p['identified']}$}};
\node[box, below=of id] (uq) {{Unique records after removing duplicates\\ $n={p['unique_records']}$}};
\node[box, below=of uq] (sc) {{Records screened (title and abstract)\\ $n={p['screened']}$}};
\node[box, below=of sc] (ft) {{Full texts assessed\\ $n={p['full_text_assessed']}$}};
\node[box, below=of ft] (in) {{Papers included in the survey\\ $n={p['included']}$}};
\node[side, right=0.6cm of id] (dup) {{Duplicates removed\\ $n={p['duplicates_removed']}$}};
\node[side, right=0.6cm of uq] (au) {{Excluded automatically (year, topic keywords)\\ $n={p['auto_excluded']}$}};
\node[side, right=0.6cm of sc] (ta) {{Excluded at title and abstract\\ $n={p['excluded_title_abstract']}$}};
\node[side, right=0.6cm of ft] (fx) {{Excluded at full text\\ $n={p['excluded_full_text']}$ ({reasons})}};
\draw[arr] (id) -- (uq); \draw[arr] (uq) -- (sc); \draw[arr] (sc) -- (ft); \draw[arr] (ft) -- (in);
\draw[arr] (id) -- (dup); \draw[arr] (uq) -- (au); \draw[arr] (sc) -- (ta); \draw[arr] (ft) -- (fx);
\end{{tikzpicture}}
"""
    (out / "generated" / "prisma.tex").write_text(t, encoding="utf-8")
    rows = [("Records identified", p["identified"]), ("Duplicates removed", p["duplicates_removed"]),
            ("Excluded automatically", p["auto_excluded"]), ("Screened", p["screened"]),
            ("Excluded at title and abstract", p["excluded_title_abstract"]),
            ("Full texts assessed", p["full_text_assessed"]), ("Excluded at full text", p["excluded_full_text"]),
            ("Included", p["included"])]
    body = "\n".join(f"{a} & {b} \\\\" for a, b in rows)
    (out / "tables" / "prisma_counts.tex").write_text(
        "% Generated. Do not edit.\n\\begin{tabular}{lr}\n\\toprule\nStage & Papers \\\\\n\\midrule\n"
        + body + "\n\\bottomrule\n\\end{tabular}\n", encoding="utf-8")


def taxonomy_tex(inc, tax, out):
    lines = ["% Generated by make_survey_figures.py. Do not edit.",
             r"\begin{forest}",
             r"for tree={grow'=east, parent anchor=east, child anchor=west, anchor=west, draw, rounded corners=2pt,",
             r"  font=\scriptsize, align=left, l sep=6mm, s sep=1.2mm, inner sep=2pt, edge={-}},",
             r"where level=2{text width=6.5cm}{},",
             "[Taxonomy, font=\\scriptsize\\bfseries"]
    for d in tax.get("dimensions", []):
        lines.append(f"  [{tex(d.get('name', d['id']))}, font=\\scriptsize\\bfseries")
        for c in d.get("categories", []):
            m = members(tax, inc, d["id"], c["id"])
            cites = ("\\\\ \\cite{" + ",".join(m) + "}") if m else ""
            lines.append(f"    [{{\\textbf{{{tex(c.get('name', c['id']))}}} ({len(m)}){cites}}}]")
        lines.append("  ]")
    lines += ["]", r"\end{forest}", ""]
    (out / "generated" / "taxonomy_tree.tex").write_text("\n".join(lines), encoding="utf-8")


def compare_tables(inc, tax, notes, out):
    prim = tax.get("primary_dimension")
    _, cats = dim_cats(tax, prim)
    made = []
    for c in cats:
        m = members(tax, inc, prim, c["id"])
        if not m:
            continue
        rows = []
        for pid in m:
            n = notes.get(pid, {})
            ev = n.get("evaluation") or {}
            res = next(iter(n.get("main_results") or []), {})
            rows.append(" & ".join([
                f"\\cite{{{pid}}}", str(inc[pid].get("year") or ""),
                tex(short(n.get("key_idea"), 120)),
                tex(", ".join(as_list(n.get("system_layer")))[:40]),
                tex(short(", ".join(as_list(ev.get("hardware"))), 40)),
                tex(short(res.get("claim"), 70)),
            ]) + r" \\")
        parts = [rows[i:i + ROWS_PER_TABLE] for i in range(0, len(rows), ROWS_PER_TABLE)]
        t = "% Generated by make_survey_figures.py. Do not edit.\n"
        for k, part in enumerate(parts):
            cont = f" (part {k + 1} of {len(parts)})" if len(parts) > 1 else ""
            label = f"\\label{{tab:cmp_{c['id']}}}" if k == 0 else ""
            t += ("\\begin{table*}[tp]\n\\centering\\footnotesize\n"
                  f"\\caption{{Papers on {tex(c.get('name', c['id']))}{cont}. Results as reported by each paper "
                  f"(setups differ, so numbers are not directly comparable).}}{label}\n"
                  "\\begin{tabularx}{\\textwidth}{@{}" + RR + "p{1.3cm}p{0.6cm}" + RR + "X" + RR + "p{1.8cm}"
                  + RR + "p{2.4cm}" + RR + "p{3.6cm}@{}}\n\\toprule\n"
                  "Paper & Year & Key idea & Layer & Hardware & Main reported result \\\\\n\\midrule\n"
                  + "\n".join(part) + "\n\\bottomrule\n\\end{tabularx}\n\\end{table*}\n\n")
        path = out / "tables" / f"compare_{c['id']}.tex"
        path.write_text(t, encoding="utf-8")
        made.append(path)
    return made


def eval_landscape(notes, out, top=8):
    cols = {}
    for key in ("hardware", "models", "workloads", "metrics"):
        cnt = collections.Counter()
        for n in notes.values():
            for v in set(as_list((n.get("evaluation") or {}).get(key))):
                if v:
                    cnt[" ".join(str(v).split())] += 1
        cols[key] = cnt.most_common(top)
    rows = []
    for i in range(top):
        cells = []
        for key in ("hardware", "models", "workloads", "metrics"):
            if i < len(cols[key]):
                name, k = cols[key][i]
                cells.append(f"{tex(short(name, 28))} ({k})")
            else:
                cells.append("")
        if any(cells):
            rows.append(" & ".join(cells) + r" \\")
    t = ("% Generated. Do not edit. Numbers in brackets: how many surveyed papers use it.\n"
         "\\begin{tabularx}{\\linewidth}{@{}" + (RR + "X") * 4 + "@{}}\n\\toprule\nHardware & Models & Workloads & Metrics \\\\\n"
         "\\midrule\n" + "\n".join(rows) + "\n\\bottomrule\n\\end{tabularx}\n")
    (out / "tables" / "eval_landscape.tex").write_text(t, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default="state")
    ap.add_argument("--out", default="paper")
    a = ap.parse_args()
    state, out = pathlib.Path(a.state), pathlib.Path(a.out)
    for d in ("figures", "tables", "generated"):
        (out / d).mkdir(parents=True, exist_ok=True)
    inc, tax, notes, prisma = load(state)
    made = []
    if tax:
        made.append(fig_per_year(inc, tax, out))
        made += fig_categories(inc, tax, out)
        taxonomy_tex(inc, tax, out)
        made += compare_tables(inc, tax, notes, out)
    if prisma:
        prisma_tex(prisma, out)
    eval_landscape(notes, out)
    print(f"{len(inc)} included papers, {len(notes)} notes. Made: "
          + ", ".join(str(p.relative_to(out)) for p in made if p))


if __name__ == "__main__":
    main()
