---
name: survey-latex
description: Write a systematic survey in LaTeX for Overleaf, using generated figures (papers per year, category counts, PRISMA flow, taxonomy tree) and comparison tables built from extraction notes. Use when drafting or revising a survey paper.
---
# Survey in LaTeX

## Generated assets (made by Python, never edit by hand)
The pipeline runs `make_survey_figures.py` before each writing step:

| File | Use it in |
|---|---|
| `generated/prisma.tex` | Methodology: `\begin{figure}...\resizebox{\columnwidth}{!}{\input{generated/prisma}}...` |
| `tables/prisma_counts.tex` | Methodology (optional, small table) |
| `generated/taxonomy_tree.tex` | Taxonomy: put it in a `figure*` with `\resizebox{\textwidth}{!}{\input{generated/taxonomy_tree}}` |
| `figures/papers_per_year.pdf` | Introduction or analysis (growth of the field) |
| `figures/categories_<dim>.pdf` | Taxonomy or analysis |
| `tables/compare_<category>.tex` | End of each category section: `\input{tables/compare_<id>}` (full-width `table*` floats, split into parts of 16 rows) |
| `tables/eval_landscape.tex` | Analysis of evaluation practice (RQ about how work is evaluated) |
| `refs.bib` | All included papers. Key = paper id. |

## Structure
1. **Abstract**: topic, scope, number of papers, taxonomy, main findings, open challenges.
2. **Introduction**: why the topic matters now, what earlier surveys miss (cite them if found), research questions,
   contributions (taxonomy, comparison, challenges), paper organization.
3. **Background**: only what a reader needs (for example how MoE layers and routing work).
4. **Methodology**: protocol (sources, queries, year range, rules), snowballing, saturation, PRISMA figure.
5. **Taxonomy**: dimensions, category definitions, the tree figure.
6. **One section per primary category** (`sections/cat_<id>.tex`, label `sec:<id>`): the problem the group solves,
   the main ideas, how papers differ, a comparison table. Group papers by idea; do not write one paragraph per paper in a list.
7. **Cross-cutting analysis**: answers to each RQ, trends, evaluation practice, comparability of results.
8. **Open challenges and future directions**: from the analyst's `challenges.md`, each backed by evidence.
9. **Conclusion**.

## Writing rules
- Cite every included paper at least once. Use only keys from `refs.bib` (and `background_refs.bib`).
- Every number about a paper comes from its note (`state/notes/<id>.json`). Write "reports" or "claims":
  results come from different setups and are not directly comparable. Say so.
- Every count about the corpus (how many papers, per year, per category) comes from `state/analysis/stats.json`
  or `state/prisma.json`.
- Synthesize: compare and contrast, name trade-offs, show which ideas build on which.
- Use `\todo{...}` for anything you cannot support from the evidence.

## Build and zip
```bash
cd paper && latexmk -pdf -interaction=nonstopmode main.tex
```
The pipeline zips `paper/` into `paper/overleaf.zip` after each writing step.
