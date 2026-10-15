"""Backward and forward snowballing via the Semantic Scholar graph API. Standard library only.

python snowball.py --seeds seeds.json --direction both --limit 40 --since 2022 --out-dir state/collect/round_02/
"""
import argparse
import json
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.semanticscholar.org/graph/v1"
FIELDS = "title,year,venue,authors,abstract,url,citationCount,externalIds,openAccessPdf"


def get(url, tries=4):
    key = os.environ.get("S2_API_KEY")
    h = {"User-Agent": "survey-pipeline/1.0", **({"x-api-key": key} if key else {})}
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=40) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(3 * (i + 1) if key else 6 * (i + 1))
        except Exception:
            time.sleep(3 * (i + 1))
    return None


def resolve(seed):
    for ref in ([seed.get("s2_id")] if seed.get("s2_id") else []) + \
               ([f"DOI:{seed['doi']}"] if seed.get("doi") else []) + \
               ([f"ARXIV:{seed['arxiv']}"] if seed.get("arxiv") else []):
        d = get(f"{API}/paper/{urllib.parse.quote(ref, safe=':/')}?fields=paperId")
        if d and d.get("paperId"):
            return d["paperId"]
    if seed.get("title"):
        d = get(f"{API}/paper/search?" + urllib.parse.urlencode({"query": seed["title"], "limit": 1, "fields": "paperId,title"}))
        for p in (d or {}).get("data", []):
            if re.sub(r"\W", "", p["title"].lower()) == re.sub(r"\W", "", seed["title"].lower()):
                return p["paperId"]
    return None


def to_hit(p):
    ext = p.get("externalIds") or {}
    return {"title": p.get("title"), "year": p.get("year"), "venue": p.get("venue"),
            "authors": [a["name"] for a in p.get("authors") or []][:8], "abstract": p.get("abstract"),
            "url": p.get("url"), "doi": ext.get("DOI"), "arxiv": ext.get("ArXiv"), "s2_id": p.get("paperId"),
            "pdf_url": (p.get("openAccessPdf") or {}).get("url"), "citations": p.get("citationCount"),
            "sources": ["semantic_scholar"]}


def neighbours(pid, direction, limit):
    edge = "references" if direction == "backward" else "citations"
    key = "citedPaper" if direction == "backward" else "citingPaper"
    out, offset = [], 0
    while offset < 1000:
        d = get(f"{API}/paper/{pid}/{edge}?" + urllib.parse.urlencode({"fields": FIELDS, "limit": 100, "offset": offset}))
        if not d or not d.get("data"):
            break
        out += [x[key] for x in d["data"] if x.get(key) and x[key].get("title")]
        if not d.get("next"):
            break
        offset = d["next"]
        if not os.environ.get("S2_API_KEY"):
            time.sleep(1.5)
    out.sort(key=lambda p: p.get("citationCount") or 0, reverse=True)
    return out[:limit]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", required=True)
    ap.add_argument("--direction", choices=["backward", "forward", "both"], default="both")
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--since", type=int, default=0)
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args()
    seeds = json.loads(pathlib.Path(a.seeds).read_text())["seeds"]
    out = pathlib.Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    dirs = ["backward", "forward"] if a.direction == "both" else [a.direction]
    unresolved = []
    for s in seeds:
        pid = resolve(s)
        if not pid:
            unresolved.append(s["id"])
            continue
        for d in dirs:
            hits = [to_hit(p) for p in neighbours(pid, d, a.limit)]
            hits = [h for h in hits if not a.since or (h["year"] or 9999) >= a.since]
            data = {"seed": s["id"], "direction": d, "found_by": f"snowball:{d}:{s['id']}", "hits": hits}
            (out / f"hits_snow_{s['id']}_{d}.json").write_text(json.dumps(data, indent=2))
            print(f"{s['id']:30s} {d:8s} {len(hits)} papers")
        if not os.environ.get("S2_API_KEY"):
            time.sleep(1.5)
    if unresolved:
        print("Could not resolve seeds:", ", ".join(unresolved), file=sys.stderr)


if __name__ == "__main__":
    main()
