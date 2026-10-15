# Survey pipeline (template)

This repo is a **template** for writing systematic survey papers with Claude Code agents.
Set it up once. For each new survey, `new_project.py` makes a fresh copy with its own GitHub repo.

| # | Agent | Job | Output |
|---|---|---|---|
| 1 | scope-definer | research questions, rules, queries, year range | `state/protocol.json`, `protocol.md` |
| 2 | paper-collector | keyword search, then snowballing rounds | `state/collect/round_NN/hits_*.json` |
| 3 | screener | include or exclude each candidate, with a reason | `state/screen/round_NN/decisions_*.json` |
| 4 | extractor | one structured note per included paper | `state/notes/<id>.json` |
| 5 | taxonomy-builder | dimensions, categories, assignments, gaps | `state/taxonomy.json`, `taxonomy.md` |
| 6 | analyst | answers to research questions, trends, challenges | `state/analysis/` |
| 7 | survey-writer | LaTeX survey with generated figures and tables | `paper/`, `paper/overleaf.zip` |
| 8 | survey-reviewer | coverage, accuracy, taxonomy, presentation | `state/review/review_NN.json` |
| - | bench-runner (optional, GPU) | small benchmark of open-source systems | `state/bench/` |

Python (`pipeline/`) does everything that must be exact: merging and de-duplicating papers, paper ids and BibTeX,
PRISMA counts, the saturation check, the coverage check, figures, tables and the citation check.

## Loops

| Check | If it fails |
|---|---|
| Saturation: a snowballing round adds fewer than 5% new included papers | not yet: another snowballing round (max 4 rounds) |
| Coverage: each taxonomy category has at least 3 papers | targeted search for thin categories, then taxonomy update (max 2 loops) |
| Citation check: every `\cite` is an included paper (or a background entry) | writer fixes it (max 2 tries) |
| Review (max 3) | missing papers go to collector, screener and extractor; wrong facts to extractor; writing issues to writer |

Checkpoints where you read and approve: **CP1** protocol, **CP2** included papers, **CP3** taxonomy, **CP4** each review.

---

# Part A. One-time setup (on your Linux machine)

You need Claude Code, `gh` (GitHub CLI, logged in), Python 3.10+ and these extra tools:

```bash
sudo apt install -y poppler-utils latexmk texlive-latex-extra texlive-fonts-recommended texlive-pictures
```
(`poppler-utils` gives `pdftotext` for reading papers. The LaTeX packages let the writer compile the survey.
If you only compile in Overleaf, you can skip the texlive packages.)

Copy `survey-pipeline.zip` to the machine, then:

```bash
source ~/pp-venv/bin/activate
cd ~/projects
python -m zipfile -e ~/survey-pipeline.zip .
cd survey-pipeline
pip install -r requirements.txt
git init -b main && git add -A && git commit -m "survey-pipeline template"
gh repo create survey-pipeline --private --source . --push
```

Optional, for fewer rate limits (add to `~/.bashrc`):
```bash
export S2_API_KEY=...            # free key from Semantic Scholar
export OPENALEX_EMAIL=you@example.com
```

---

# Part B. For each new survey

## B1. Create the project
```bash
source ~/pp-venv/bin/activate
cd ~/projects/survey-pipeline && git pull
python new_project.py moe-survey
cd ~/projects/moe-survey
claude        # say Yes to trust this folder, then /exit
```

## B2. Write the topic
```bash
nano inputs/topic.md      # topic, why now, scope, years
nano inputs/seeds.md      # optional: papers you know are central
```
Optional: copy key PDFs into `inputs/papers/`.

## B3. Run
```bash
tmux new -s survey
python pipeline/orchestrator.py
```
Detach with Ctrl+b then d; come back with `tmux attach -t survey`.

At each checkpoint, open another tmux window (Ctrl+b then c) to read or edit files, then press Enter.

| Checkpoint | What to check | Useful command |
|---|---|---|
| CP1 | research questions, rules, queries | `less state/protocol.md` |
| CP2 | the included papers | `python pipeline/corpus.py list --status included` |
| CP3 | the taxonomy (it shapes the whole survey) | `less state/taxonomy.md` |
| CP4 | each review | `less state/review/review_01.json` |

To change a screening decision at CP2, edit the paper's `"status"` in `state/corpus.json` (`included` or `excluded`).

## B4. Get the survey
When it prints `DONE`, copy `paper/overleaf.zip` to your laptop and upload it in Overleaf
(New project, Upload project). From Windows:
```
scp -i C:\path\to\key.pem ubuntu@<server>:~/projects/moe-survey/paper/overleaf.zip %USERPROFILE%\Downloads\
```

## Useful commands
```bash
python pipeline/orchestrator.py --auto                 # no checkpoints
python pipeline/orchestrator.py --from-step taxonomy   # redo from a step
python pipeline/orchestrator.py --only write           # run one step
python pipeline/corpus.py stats                        # counts by status and round
python pipeline/corpus.py prisma                       # PRISMA numbers
```
Steps: `scope, collect, extract, taxonomy, analysis, bench, write, review`. Finished steps are skipped on restart.

## Optional GPU benchmark
Set `benchmark: true` in `pipeline/config.yaml`. The analyst then writes `bench_plan.json`, and the pipeline sends a job
to `pipeline/gpu_watcher.py`. Run the watcher on the GPU machine in a second clone of the project repo
(same way as the paper pipeline: `git clone ... moe-survey-gpu`, then `python pipeline/gpu_watcher.py` in tmux).

## Cost and time
Extraction is the slowest step: about one agent call per 6 papers, 3 at a time (`extract_batch`, `parallel_agents`).
A 150-paper survey needs about 25 extractor calls. Lower `max_collect_rounds` or tighten the protocol to keep it smaller.

## Troubleshooting
- **"This is the TEMPLATE repo"**: `cd` into the project folder.
- **Search errors (429)**: rate limits. Set `S2_API_KEY`, or lower `snowball_limit` and `max_snowball_seeds`.
- **ABSTRACT ONLY** in extraction: no open PDF. Put the PDF in `inputs/papers/` with the paper id or arXiv id in its file name and run `--from-step extract`.
- **An agent did not write its file**: read the newest file in `logs/`.
- **Too many papers**: tighten `keywords_any` and the rules in `state/protocol.json`, then `--from-step collect`
  (delete `state/corpus.json`, `state/collect/` and `state/screen/` first for a clean restart).

## Folder map
```
new_project.py        (template only) makes a new survey project
.claude/agents/       9 agents
.claude/skills/       survey-protocol, lit-search, snowballing, extraction-schema, taxonomy, citation-check, survey-latex
CLAUDE.md             rules every agent follows
pipeline/             orchestrator.py, corpus.py, common.py, gpu_watcher.py (optional), config.yaml
schemas/              examples of protocol, decisions, note, taxonomy and review files
inputs/               topic.md, seeds.md, papers/
state/                everything the agents produce (committed)
paper/                the LaTeX survey and overleaf.zip
work/, logs/          local only (downloaded PDFs, agent logs)
```
