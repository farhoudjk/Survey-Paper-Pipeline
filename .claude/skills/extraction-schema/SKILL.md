---
name: extraction-schema
description: Fixed schema for per-paper survey notes, plus a script to download and convert a paper's full text. Use when extracting structured information from papers for a survey, or when checking or fixing notes.
---
# Extraction schema

Every included paper gets one note: `state/notes/<paper-id>.json`, following `schema.json`
(same folder). The `required` list in schema.json is checked by Python after extraction.

## Get the full text

```bash
python .claude/skills/extraction-schema/fetch_paper.py <paper-id>
```

It looks the paper up in `state/corpus.json`, tries (in order) a PDF in `inputs/papers/` whose name
contains the id or arXiv number, the arXiv PDF, then the open-access PDF URL. It saves
`work/papers/<id>.pdf` and `work/papers/<id>.txt` (needs `pdftotext`, from `poppler-utils`).
If no PDF is found it prints `ABSTRACT ONLY`; then set `"source_text": "abstract"` in the note and
fill only what the abstract supports.

Read the .txt with the Read tool. Long papers: read the abstract, introduction, design overview,
evaluation setup and results, and the limitations or discussion section.

## Rules
- Only write what the paper says. No guessing. Use `null` when the paper does not say.
- Every number in `main_results` must have a `where` (section, table or figure) so a reader can check it.
- Paraphrase. Do not copy sentences (short terms and names are fine).
- `technique_family` uses short reusable labels (the taxonomy builder groups them later). Reuse labels
  that already exist in other notes: run `grep -h technique_family -r state/notes | sort | uniq -c`.
- `confidence`: high (full text read), medium (parts read), low (abstract only).

## Modes
- `extract`: write the note from scratch.
- `add-fields`: open the existing note and add the fields listed under `new_fields` in
  `state/taxonomy.json`. Do not change other fields unless they are wrong.
- `fix`: fix the fact errors listed in the review file for these papers. Re-read the paper.
