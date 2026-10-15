# Rules for every agent in this repo

This repo automates a systematic survey paper. Each agent does one step, reads and writes the files named
in its task (in `state/` or `paper/`), and then stops.

## Files
- Write only the output files named in your task. Follow the formats in the skills and in `schemas/`.
- Write valid JSON (no comments, no trailing commas). Check with `python -m json.tool <file>`.
- Never edit `state/corpus.json`, `state/prisma.json`, `state/progress.json`, `state/handoff/` or generated files
  (`paper/refs.bib`, `paper/generated/`, `paper/tables/`, `paper/figures/`). Python owns them.
- Paper ids (for example `kwon2023efficient`) are also BibTeX keys. Use them exactly.

## Honesty
- Never invent papers, authors, venues, numbers, quotes or URLs.
- Every fact about a paper comes from that paper (or its note). Every count about the corpus comes from Python output.
- Paraphrase papers; do not copy sentences.
- If you are unsure, write it down as an open question or a TODO. Do not guess silently.

## Style
- Simple, clear English. Canadian spelling (behaviour, modelling, centre).
- Avoid long (em) dashes. Use commas, colons or full stops instead.

## Useful commands
- `python pipeline/corpus.py stats` / `list --status included` / `show <id>`
- `python .claude/skills/lit-search/lit_search.py "<query>" --since <year> --out <file>`
- `python .claude/skills/extraction-schema/fetch_paper.py <id>` (full text into `work/papers/`)
- Skills: `.claude/skills/<name>/SKILL.md` (read it before using the skill)
