# Product KB sources

This directory contains version-controlled machine sources for the deterministic
Product KB build.

- `seed/` is exported from the verified Iteration 3 reference workbook.
- `rules.yaml` contains ordered, context-aware reusable rules. Rules may map only
  to an existing Product ID or explicitly defer/classify a row.
- `manual_decisions.jsonl` preserves workbook decisions as append-only evidence.

`PROVISIONAL_AI`, `PROVISIONAL_USER`, and `LEGACY_REVIEW` Products remain visible
but are never counted as approved mappings. A build labels them
`PROVISIONAL_MAPPING` and keeps them in the review queue.

Unknown titles do not create global Products. Add a reviewed decision or a
reusable rule, then add a regression fixture before expanding auto-resolution.
