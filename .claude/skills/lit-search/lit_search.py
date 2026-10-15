"""Search Semantic Scholar, arXiv, OpenAlex and DBLP. Standard library only.

python lit_search.py "query" --since 2023 --limit 25 --out state/collect/round_01/hits_q01.json
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

UA = {"User-Agent": "paper-pipeline-lit-search/1.0"}


def get(url, headers=None, tries=3):
    h = dict(UA, **(headers or {}))
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=30) as r:
                return r.read().decode("utf-8")
        except Exception as e:  # rate limit or network error
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))


def s2(q, since, limit):
    params = {"query": q, "limit": limit, "year": f"{since}-",
              "fields": "title,year,venue,authors,abstract,url,citationCount,externalIds,openAccessPdf"}
    key = os.environ.get("S2_API_KEY")
    data = json.loads(get("https://api.semanticscholar.org/graph/v1/paper/search?"
                          + urllib.parse.urlencode(params), {"x-api-key": key} if key else None))
    out = []
    for p in data.get("data", []):
        out.append({"title": p.get("title"), "year": p.get("year"), "venue": p.get("venue"),
                    "authors": [a["name"] for a in p.get("authors", [])][:8],
                    "abstract": p.get("abstract"), "url": p.get("url"),
                    "citations": p.get("citationCount"), "doi": (p.get("externalIds") or {}).get("DOI"),
                    "arxiv": (p.get("externalIds") or {}).get("ArXiv"), "s2_id": p.get("paperId"),
                    "pdf_url": (p.get("openAccessPdf") or {}).get("url"), "source": "semantic_scholar"})
    return out


def arxiv(q, since, limit):
    terms = " AND ".join(f"all:{w}" for w in q.split())
    params = {"search_query": terms, "start": 0, "max_results": limit,
              "sortBy": "relevance", "sortOrder": "descending"}
    root = ET.fromstring(get("https://export.arxiv.org/api/query?" + urllib.parse.urlencode(params)))
    ns = {"a": "http://www.w3.org/2005/Atom"}
    out = []
    for e in root.findall("a:entry", ns):
        year = int(e.find("a:published", ns).text[:4])
        if year < since:
            continue
        out.append({"title": " ".join(e.find("a:title", ns).text.split()), "year": year,
                    "venue": "arXiv", "authors": [a.find("a:name", ns).text for a in e.findall("a:author", ns)][:8],
                    "abstract": " ".join(e.find("a:summary", ns).text.split()),
                    "url": e.find("a:id", ns).text, "citations": None, "doi": None,
                    "arxiv": e.find("a:id", ns).text.rsplit("/", 1)[-1].split("v")[0],
                    "pdf_url": e.find("a:id", ns).text.replace("/abs/", "/pdf/"), "source": "arxiv"})
    return out


def openalex(q, since, limit):
    params = {"search": q, "per-page": limit, "filter": f"from_publication_date:{since}-01-01"}
    if os.environ.get("OPENALEX_EMAIL"):
        params["mailto"] = os.environ["OPENALEX_EMAIL"]
    data = json.loads(get("https://api.openalex.org/works?" + urllib.parse.urlencode(params)))
    out = []
    for w in data.get("results", []):
        inv = w.get("abstract_inverted_index") or {}
        words = sorted((pos, word) for word, ps in inv.items() for pos in ps)
        src = ((w.get("primary_location") or {}).get("source") or {})
        out.append({"title": w.get("title"), "year": w.get("publication_year"), "venue": src.get("display_name"),
                    "authors": [a["author"]["display_name"] for a in w.get("authorships", [])][:8],
                    "abstract": " ".join(x for _, x in words) or None,
                    "url": w.get("doi") or w.get("id"), "citations": w.get("cited_by_count"),
                    "doi": w.get("doi"), "source": "openalex"})
    return out


def dblp(q, since, limit):
    params = {"q": q, "format": "json", "h": limit}
    data = json.loads(get("https://dblp.org/search/publ/api?" + urllib.parse.urlencode(params)))
    out = []
    for h in ((data.get("result") or {}).get("hits") or {}).get("hit", []):
        i = h.get("info", {})
        year = int(i.get("year", 0) or 0)
        if year and year < since:
            continue
        au = (i.get("authors") or {}).get("author", [])
        au = au if isinstance(au, list) else [au]
        ee = i.get("ee")
        ee = ee[0] if isinstance(ee, list) else ee
        out.append({"title": (i.get("title") or "").rstrip("."), "year": year or None, "venue": i.get("venue"),
                    "authors": [a.get("text") if isinstance(a, dict) else a for a in au][:8],
                    "abstract": None, "url": ee or i.get("url"), "citations": None, "doi": i.get("doi"),
                    "source": "dblp"})
    return out


SOURCES = {"s2": s2, "arxiv": arxiv, "openalex": openalex, "dblp": dblp}


def norm(t):
    return re.sub(r"[^a-z0-9]", "", (t or "").lower())


def search(q, since, limit, sources):
    hits, errors = [], {}
    for name in sources:
        try:
            hits += SOURCES[name](q, since, limit)
        except Exception as e:
            errors[name] = str(e)[:200]
    merged = {}
    for h in hits:
        k = norm(h["title"])
        if not k:
            continue
        if k in merged:  # keep the richer record, remember all sources
            m = merged[k]
            m["sources"] = sorted(set(m["sources"] + [h["source"]]))
            for f in ("abstract", "venue", "doi", "citations", "arxiv", "s2_id", "pdf_url"):
                if not m.get(f) and h.get(f):
                    m[f] = h[f]
        else:
            h["sources"] = [h.pop("source")]
            merged[k] = h
    ranked = sorted(merged.values(), key=lambda h: (len(h["sources"]), h.get("citations") or 0), reverse=True)
    return {"query": q, "since": since, "errors": errors, "hits": ranked}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--since", type=int, default=2023)
    ap.add_argument("--limit", type=int, default=25)
    ap.add_argument("--sources", default="s2,arxiv,openalex,dblp")
    ap.add_argument("--out")
    a = ap.parse_args()
    res = search(a.query, a.since, a.limit, a.sources.split(","))
    if a.out:
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        with open(a.out, "w") as f:
            json.dump(res, f, indent=2)
    for i, h in enumerate(res["hits"][:25], 1):
        print(f"{i:2d}. [{h.get('year')}] {h.get('title')} | {h.get('venue')} | {h.get('url')}")
    if res["errors"]:
        print("Source errors:", res["errors"], file=sys.stderr)
