---
name: taxonomy
description: How to build a survey taxonomy (2 to 3 dimensions, clear categories, every paper assigned), detect thin categories and propose gap searches, in the taxonomy.json format the pipeline checks. Use when organizing surveyed papers.
---
# Building a taxonomy

A taxonomy is the backbone of a survey. Readers use it to find their way, and the paper's sections follow it.

## Method
1. Read every note in `state/notes/` (use `technique_family`, `system_layer`, `problem`, `key_idea`).
2. List candidate dimensions. Good dimensions are **independent** of each other, for example:
   - What problem is solved (memory, latency, throughput, cost)
   - What technique is used (offloading, prefetching, scheduling, compression, speculation)
   - Where it acts (kernel, runtime, cluster)
3. Pick 2 to 3 dimensions. Mark one as `primary_dimension`: its categories become the main sections of the survey.
4. For each dimension, define 3 to 8 categories. Each has a one-sentence definition that decides membership.
   Categories in a dimension should not overlap. A paper may still belong to several categories when it truly combines techniques.
5. Assign **every** included paper in every dimension.
6. Check coverage: a category with fewer than the minimum number of papers is "thin". It may be a real research gap
   (that is a finding) or a search gap. For each thin category, propose 1 to 3 search queries in `gap_queries`.
7. If the notes lack information you need to assign papers (for example "is the method lossless?"), add it to `new_fields`.

## taxonomy.json

```json
{
  "dimensions": [
    {"id": "d1", "name": "Technique", "description": "...",
     "categories": [{"id": "offload", "name": "Expert offloading", "definition": "..."}]}
  ],
  "primary_dimension": "d1",
  "assignments": {"kwon2023efficient": {"d1": ["offload"], "d2": "runtime"}},
  "gaps": [{"dimension": "d1", "category": "offload", "kind": "research gap | search gap", "note": "..."}],
  "gap_queries": [{"query": "expert prefetching MoE inference", "reason": "thin category d1/prefetch"}],
  "new_fields": [{"name": "lossless", "question": "Does the method keep model outputs unchanged?", "type": "boolean"}],
  "changelog": ["what changed in this version and why"]
}
```

Rules:
- Category ids: short, lowercase, snake_case. Never rename an id in `update` mode (the text cites them); add new ones instead.
- Use `new_fields` only when needed: it re-runs extraction on all papers, which is slow.
- In `update` mode, keep existing assignments unless they are wrong; add the new papers; refresh gaps.
