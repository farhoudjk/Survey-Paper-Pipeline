---
name: citation-check
description: Check that every citation in the LaTeX survey points to an included paper with a real DOI or URL, that numbers in the text come from extraction notes, and that every category in the taxonomy is discussed. Use after writing or revising a survey.
---
# Citation check

```bash
python .claude/skills/citation-check/check_citations.py --paper paper --state state --out state/citation_check.json
```

Exit code 0 means no errors (warnings may remain). It checks:

| Check | Level |
|---|---|
| Every `\cite{...}` key exists in `paper/refs.bib` | error |
| Every cited key is an included paper in `state/corpus.json` (background keys must be listed in `paper/background_refs.bib`) | error |
| Every bib entry of an included paper has a DOI or URL | warning |
| Every category of the primary taxonomy dimension is mentioned by name or label in the text | warning |
| Included papers never cited anywhere | warning (a survey should cite every surveyed paper at least once, often in a table) |
| Numbers with x, % or ms next to a citation that do not appear in that paper's note | warning |

## Background papers
Older or foundational papers that are not part of the surveyed corpus (for example the original Transformer paper)
go in `paper/background_refs.bib`, written by hand from a real lit-search result. `main.tex` loads both bib files.
