"""Check citations, coverage and numbers in the LaTeX survey.

python check_citations.py --paper paper --state state --out state/citation_check.json
Exit 0 = no errors.
"""
import argparse
import json
import pathlib
import re
import sys


def bib_keys(path):
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    keys = {}
    for m in re.finditer(r"@\w+\s*\{\s*([^,\s]+)\s*,(.*?)(?=\n@|\Z)", text, re.S):
        keys[m.group(1)] = m.group(2)
    return keys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--paper", default="paper")
    ap.add_argument("--state", default="state")
    ap.add_argument("--out", default="state/citation_check.json")
    a = ap.parse_args()
    paper, state = pathlib.Path(a.paper), pathlib.Path(a.state)

    corpus = json.loads((state / "corpus.json").read_text(encoding="utf-8"))
    included = {pid for pid, p in corpus["papers"].items() if p["status"] == "included"}
    refs = bib_keys(paper / "refs.bib")
    background = bib_keys(paper / "background_refs.bib")
    errors, warnings = [], []

    cites = {}  # key -> list of (file, line)
    text_all = ""
    for f in sorted(paper.rglob("*.tex")):
        t = f.read_text(encoding="utf-8", errors="ignore")
        text_all += t + "\n"
        for i, line in enumerate(t.splitlines(), 1):
            if line.lstrip().startswith("%"):
                continue
            for m in re.finditer(r"\\cite[a-zA-Z]*\*?(?:\[[^\]]*\])*\{([^}]*)\}", line):
                for k in m.group(1).split(","):
                    k = k.strip()
                    if k:
                        cites.setdefault(k, []).append(f"{f.relative_to(paper)}:{i}")

    for k, where in sorted(cites.items()):
        if k not in refs and k not in background:
            errors.append({"type": "unknown_key", "key": k, "where": where[:5],
                           "fix": "Use a key from refs.bib (included papers) or add a real entry to background_refs.bib."})
        elif k in refs and k not in included:
            errors.append({"type": "not_included", "key": k, "where": where[:5],
                           "fix": "This paper is not in the included corpus. Remove the citation or move it to background_refs.bib."})

    for k in sorted(included):
        body = refs.get(k, "")
        if k in refs and "doi" not in body and "url" not in body:
            warnings.append({"type": "no_doi_or_url", "key": k})
    uncited = sorted(included - set(cites))
    if uncited:
        warnings.append({"type": "uncited_included_papers", "count": len(uncited), "keys": uncited[:50],
                         "fix": "Cite each surveyed paper at least once (text or comparison table)."})

    tax_path = state / "taxonomy.json"
    if tax_path.exists():
        tax = json.loads(tax_path.read_text(encoding="utf-8"))
        prim = tax.get("primary_dimension")
        low = text_all.lower()
        for d in tax.get("dimensions", []):
            if d["id"] != prim:
                continue
            for c in d.get("categories", []):
                if c.get("name", "").lower() not in low and f"sec:{c['id']}" not in low:
                    warnings.append({"type": "category_not_discussed", "category": c["id"], "name": c.get("name"),
                                     "fix": "Add a subsection or paragraph for this category (label sec:<id>)."})

    notes_dir = state / "notes"
    num = re.compile(r"(\d+(?:\.\d+)?)\s*(?:\\times|x|×|\\%|%|\s?ms)")
    sec_dir = paper / "sections"
    for f in (sorted(sec_dir.rglob("*.tex")) if sec_dir.exists() else []):
        for i, line in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if line.lstrip().startswith("%"):
                continue
            keys = [k.strip() for m in re.finditer(r"\\cite[a-zA-Z]*\{([^}]*)\}", line) for k in m.group(1).split(",")]
            nums = [m.group(1) for m in num.finditer(line)]
            if len(keys) != 1 or not nums:
                continue
            note = notes_dir / f"{keys[0]}.json"
            if not note.exists():
                continue
            nt = note.read_text(encoding="utf-8")
            for n in nums:
                if n not in nt:
                    warnings.append({"type": "number_not_in_note", "key": keys[0], "number": n,
                                     "where": f"{f.relative_to(paper)}:{i}",
                                     "fix": "Use the number recorded in the paper's note, or fix the note."})

    report = {"ok": not errors, "errors": errors, "warnings": warnings,
              "cited_keys": len(cites), "included": len(included), "uncited": len(uncited)}
    pathlib.Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(a.out).write_text(json.dumps(report, indent=2))
    print(f"Citation check: {len(errors)} errors, {len(warnings)} warnings, "
          f"{len(cites)} cited keys, {len(uncited)} of {len(included)} included papers not cited.")
    sys.exit(0 if not errors else 1)


if __name__ == "__main__":
    main()
