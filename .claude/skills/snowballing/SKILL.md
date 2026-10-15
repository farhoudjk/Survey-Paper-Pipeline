---
name: snowballing
description: Backward (references) and forward (citations) snowballing from seed papers using the Semantic Scholar graph API, saved as hits files the corpus tools can read. Use in survey collection rounds after the first keyword search.
---
# Snowballing

Snowballing finds papers that keyword search misses:
- **backward**: papers that a seed paper cites (its references)
- **forward**: newer papers that cite the seed paper

## Command

```bash
python .claude/skills/snowballing/snowball.py \
    --seeds state/collect/round_02/seeds.json \
    --direction both --limit 40 --since 2022 \
    --out-dir state/collect/round_02/
```

It writes one file per seed and direction: `hits_snow_<seed-id>_<direction>.json`.
Each hit carries `found_by: snowball:<direction>:<seed-id>`, so the PRISMA counts can show where papers came from.

Seeds file format (the orchestrator writes it):

```json
{"seeds": [{"id": "kwon2023efficient", "title": "...", "s2_id": "...", "doi": "...", "arxiv": "2309.06180"}]}
```

The script resolves each seed by `s2_id`, then DOI, then arXiv id, then title search.

## Tips
- Forward citations of famous papers can be huge. The `--limit` keeps the most cited ones first.
- Set `S2_API_KEY` for higher rate limits. Without a key the script waits between calls.
- Snowballing is mechanical. Relevance is decided later by the screener.
