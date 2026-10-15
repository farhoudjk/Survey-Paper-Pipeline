---
name: lit-search
description: Keyword search over Semantic Scholar, arXiv, OpenAlex and DBLP with merged, de-duplicated results saved as a hits file the corpus tools can read. Use for survey collection, targeted gap searches and checking for missing papers.
---
# Literature search

Google Scholar has no official API and blocks scripts, so this skill uses four open sources.
Together they cover almost all CS venues and preprints.

## Command

```bash
python .claude/skills/lit-search/lit_search.py "speculative decoding mixture of experts" \
    --since 2022 --limit 25 --out state/collect/round_01/hits_q01.json
```

- `--since YEAR` only papers from this year on
- `--limit N` hits per source (default 25)
- `--sources s2,arxiv,openalex,dblp` pick sources
- `--out FILE` save JSON. **Name it `hits_<something>.json`** so the pipeline picks it up.

Optional environment variables (fewer rate limits):
- `S2_API_KEY` free Semantic Scholar key
- `OPENALEX_EMAIL` your email for the OpenAlex polite pool

## Output format

```json
{"query": "...", "since": 2022, "errors": {}, "hits": [
  {"title": "...", "year": 2024, "venue": "...", "authors": ["..."], "abstract": "...",
   "url": "...", "doi": "...", "arxiv": "2401.01234", "s2_id": "...", "pdf_url": "...",
   "citations": 12, "sources": ["semantic_scholar", "arxiv"]}]}
```

## Good queries
- 3 to 6 words. One concept pair per query: "expert offloading MoE inference".
- Use synonyms as separate queries: "mixture of experts", "MoE", "sparse experts".
- If a source returns an error (rate limit), wait 30 seconds and run that query again with `--sources` set to the failed one.
