---
name: survey-protocol
description: How to write a systematic survey protocol (research questions, inclusion and exclusion criteria, search strings, sources, year range) in a PRISMA-style way, and how to apply it when screening papers. Use when defining a survey scope or screening candidate papers.
---
# Survey protocol (PRISMA-style)

A protocol makes the survey repeatable: another person following it should find and keep
the same papers. It is written once (Agent 1), approved by the human, then used by every agent.

## protocol.json fields

```json
{
  "title": "Working title of the survey",
  "scope": "One paragraph: what is in and what is out.",
  "research_questions": [{"id": "RQ1", "question": "...", "why": "..."}],
  "inclusion": [{"id": "I1", "rule": "Proposes or evaluates a system technique for X"}],
  "exclusion": [{"id": "E1", "rule": "Only about model training"}],
  "year_from": 2020,
  "venues_focus": ["OSDI", "SOSP", "EuroSys", "ASPLOS", "MLSys", "NSDI", "ATC", "SC", "ISCA", "MICRO", "NeurIPS", "ICML", "ICLR"],
  "keywords_any": ["mixture of experts", "moe", "expert"],
  "queries": [{"id": "Q01", "query": "mixture of experts inference serving", "concept": "core"}],
  "seed_papers": [{"title": "...", "doi": null, "arxiv": "2401.00000"}],
  "extraction_focus": ["what to extract beyond the standard schema, if anything"],
  "notes": "Assumptions and open questions for the human."
}
```

- `keywords_any`: lowercase words or phrases. A candidate with **none** of them in its title or
  abstract is excluded automatically. Keep it broad (synonyms, abbreviations), or it will drop good papers.
- `queries`: 10 to 30 short queries. Cover the core concept, each sub-topic and the synonyms.
  Combine the core concept with each sub-topic: "MoE expert offloading", "MoE expert parallelism".
- `year_from`: older papers are excluded automatically. Foundational older papers can still be cited
  as background in the text, but they are not part of the surveyed corpus.

## Writing good rules
- Each rule is testable from the title, abstract or full text. Avoid "high quality".
- Inclusion rules all must hold. Any exclusion rule is enough to drop a paper.
- Typical exclusions: not in English, no technical contribution (opinion, tutorial), patent, thesis
  duplicate of a paper, workshop version when the full version is included, out of scope topic.
- Decide what to do with preprints: usually include arXiv papers, prefer the published version when both exist.

## Screening rules (for the screener)
1. Title and abstract stage: exclude only when clearly out of scope. When unsure, read the full text.
2. Full-text stage: apply every rule. Record which rule decided it (`criterion`: I2 or E3).
3. Every decision has a one-sentence reason.
4. Duplicates of the same work (preprint and conference version): include the published one, exclude the
   other with criterion `E-dup` and name the kept id in the reason.

## Research questions
Good survey RQs are answerable from extracted data, for example:
- RQ1: What problems in X do systems target, and how has this changed over time?
- RQ2: What technique families are used, and at which system layer?
- RQ3: How are they evaluated (hardware, models, workloads, metrics), and how comparable are results?
- RQ4: What open problems and research gaps remain?
