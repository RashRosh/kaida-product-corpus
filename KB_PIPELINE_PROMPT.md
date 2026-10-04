# Prompt for Codex / Claude Code — KAIDA Product KB pipeline

Work in repository `RashRosh/kaida-product-corpus` on branch `kb-pipeline-prep` (or create a new feature branch from it). Do not touch production repository `KAIDA.KZ-2.0`.

## Goal

Turn the current ad-hoc product-corpus analysis into a deterministic, repeatable Product Knowledge Base build pipeline. Preserve raw 2GIS evidence unchanged. The pipeline must resolve seller-written names into canonical Product + attributes, produce an unresolved queue, and encode repeated human/AI decisions into versioned rules and regression tests.

## Before changing code

1. Read the whole repository: `README.md`, `.gitignore`, `requirements.txt`, `input/*`, `src/*`, `tests/*`.
2. Inspect local `data/extracted/observations.csv` and `data/extracted/products.csv` if present. Do not assume GitHub contains local generated corpus because `data/raw/*` and `data/extracted/*` are ignored.
3. Read `reference/KAIDA_Master_KB_Iteration_3.source.md`.
4. Ensure the binary workbook exists as `reference/KAIDA_Master_KB_Iteration_3.xlsx`. If it is missing, download the exact workbook from the Drive URL in the source file and verify SHA-256 `74cb60b07c970bd83151dd1cd226b06e11d2798c5d7bf6da53ae31807333213a` before using or committing it. Do not silently substitute another workbook.
5. Run the current scripts enough to understand behavior, but do not refetch the whole internet corpus unless necessary.

## Existing repository behavior that must be preserved

- `src/discover.py` discovers numeric 2GIS `branch_id` values from searches in `input/searches.csv`, deduplicates them, appends to `input/firms.csv`, then can launch `src/collect.py`.
- `src/collect.py` uses 2GIS `items_by_branch`, stores raw API pages under `data/raw`, maintains `data/extracted/products.csv`, and appends an observation only when `(raw_title, raw_description, categories, price, currency, source_code, product_type)` changes for `(branch_id, product_id)`.
- Therefore `observations.csv` is change history, not automatically the current catalog snapshot. Build both:
  - latest state per `(branch_id, product_id)` for current coverage/ranking/price statistics;
  - full historical evidence for audit and learning.
- `src/analyze_variants.py` normalizes by lowercase, `ё→е`, punctuation→spaces, whitespace collapse and then does all-pairs `SequenceMatcher >= 0.72`. Reuse the normalization semantics, but DO NOT use fuzzy similarity as an automatic canonical merge rule. The current O(n²) all-pairs step is only a candidate-generation probe and should not be on the critical build path.
- `src/extract_measurements.py` already extracts g/kg/ml/l/pcs, ranges, percentages and calibre like `16/20`. Refactor/reuse this logic rather than duplicating it.
- `src/fetch.py` is a debugging fetch of the first firm; do not make it part of the KB pipeline.

## Product model

Keep Product identity separate from Offer/SKU attributes.

Examples:
- `Молоко FoodMaster 3,2% 1 л` -> Product `Молоко коровье`; brand=FoodMaster; fat_percent=3.2; volume=1 l.
- `Креветка аргентинская красная L1 10/20 2 кг` -> Product `Креветка аргентинская`; variety/state/calibre/grade/weight become attributes.

Raw title is immutable evidence and must always be retained.

Entity class and Product identity are two different axes. For example a row can be `READY_DISH + NEW_PRODUCT` or `READY_DISH + ATTRIBUTES_ONLY`.

## Critical semantic guardrails already learned

Implement these as rules/tests, not comments:

1. Quantity, mass, volume and count alone do not create a new Product.
2. In dairy, brand/fat/packaging are Offer attributes once the base Product is known.
3. Category headers are not Products.
4. Exact/alias lexical equality is insufficient; category/context compatibility is required.
5. Prepared drink and dry/raw preparation product are different entities.
6. Multi-product garbage/list strings are `MALFORMED`, not one Product.
7. Bilingual `kk | ru` can be localized names of the same Offer only with language/context validation; `|` alone is insufficient.
8. Seller/branch catalog context may be used as evidence for omitted species/type, but only with `confidence` + `provenance`, and explicit title text wins on conflict.
9. Fish/meat process/state such as frozen/smoked/lightly salted is generally an attribute; buyer-relevant species/cut can form Product identity.
10. Tiger/king shrimp are buyer-relevant Product subtypes; calibre/shell/head/cleaning/weight are attributes.
11. Keep generic + species hierarchy for caviar and some fish where useful: e.g. `Красная икра` parent with `Икра кеты`, `Икра горбуши`; generic `Лосось` must not silently mean Pacific salmon.
12. Strong culinary transformation can create a Product: `Картофель фри`, `Картофельное пюре`, named soups, etc.
13. Filling/flavor usually remains an attribute for stable base forms like samosa/pie/croissant/macaron, while established recipe types such as `Наполеон`, `Медовик`, `Морковный торт`, `Испанский чизкейк` may be child Products.
14. Never map a ready dish to an ingredient only because the ingredient word appears in the title.
15. Never infer price or `price_basis` from historical/related offers if source does not state it.

Mandatory negative regression examples include at least:
- `Картошка` in dessert/pastry context MUST NOT auto-map to raw `Картофель`.
- `Какао 350 мл` / hot-drink context MUST NOT map to `Какао-порошок`.
- `Яблоко` in `Фреш/Фреши` MUST NOT map to fruit Product if context clearly means juice.
- `Рис` in garnish context MUST NOT be assumed dry grain without a prepared-food rule.
- `Тархун` in lemonade context MUST NOT map to herb `Эстрагон`.
- `Стейки кеты` MUST NOT fuzzy-map to `Стейк лакедры`.
- a long list of many salads in one title MUST NOT map to one ingredient Product.

## Repository structure to create

Keep collection and KB building separated.

Suggested structure (adjust only if you can justify a simpler equivalent):

```text
reference/
  KAIDA_Master_KB_Iteration_3.xlsx
  KAIDA_Master_KB_Iteration_3.source.md

kb/
  seed/
    products.csv
    aliases.csv
    attribute_definitions.csv
  rules.yaml
  manual_decisions.jsonl
  README.md

src/kb/
  __init__.py
  normalization.py
  measurements.py
  snapshot.py
  classifier.py
  resolver.py
  rules.py
  report.py
  io.py

src/build_kb.py
src/bootstrap_kb_reference.py

tests/kb/
  test_normalization.py
  test_measurements.py
  test_snapshot.py
  test_guardrails.py
  test_resolver.py
  fixtures/
    positive_cases.json
    negative_cases.json

data/kb/
  .gitkeep
  # generated outputs ignored by git
```

Do not commit the full generated corpus outputs. Version rules, seed canonical data, decisions, tests and the reference workbook. Add `data/kb/*` to `.gitignore` with `.gitkeep` exception.

## Bootstrap from the workbook

`reference/KAIDA_Master_KB_Iteration_3.xlsx` is the current human/audit snapshot, not the permanent machine source of truth.

Create `src/bootstrap_kb_reference.py` that validates required sheets and exports repository-native seed data. At minimum read:
- PRODUCTS
- ALIASES
- ATTRIBUTE_DEFINITIONS
- RULES
- DECISION_LOG

Preserve provisional/final statuses. Do not silently promote `PROVISIONAL_AI` / provisional Product IDs into approved production entities.

It is acceptable to add `openpyxl` for this one-time/bootstrap import. The deterministic main build should operate from repository-native CSV/YAML/JSONL, not require Excel as its authoritative store forever.

## Deterministic build command

Provide one main command, Windows-friendly:

```powershell
.\.venv\Scripts\python.exe .\src\build_kb.py
```

Optional useful flags:

```powershell
.\.venv\Scripts\python.exe .\src\build_kb.py --input data\extracted\observations.csv --out data\kb
.\.venv\Scripts\python.exe .\src\build_kb.py --top-unresolved 200
```

The build must be idempotent: same inputs/rules/decisions -> byte/logically equivalent outputs in deterministic order.

## Generated outputs

At minimum under `data/kb/`:

```text
latest_observations.csv
observed_names.csv
mappings.csv
unresolved.csv
prices.csv
products.csv
aliases.csv
build_report.json
regression_report.json
```

Useful mapping fields:
- raw_title
- normalized_title
- entity_class
- canonical_product_id
- canonical_name
- mapping_status
- mapping_method
- confidence
- provenance
- matched_rule_id
- attributes_json
- categories
- branch_count/current_branch_count
- observation_count/history_count

Do not hide ambiguity. Low confidence stays unresolved.

## Decision loop

`kb/manual_decisions.jsonl` is append-only/reviewable decision evidence, not an untraceable Python `if/elif` dump.

Each decision should have stable fields such as:
- decision_id
- scope / normalized pattern or explicit raw title
- category/context condition
- action (`MAP_EXISTING`, `CREATE_PRODUCT_CANDIDATE`, `ALIAS`, `ATTRIBUTES_ONLY`, `OUT_OF_SCOPE`, `MALFORMED`, `DEFER`)
- product_id/name if applicable
- attributes
- confidence
- provenance
- rationale
- created_at / version

Repeated patterns should be promoted into `kb/rules.yaml`; one-off exceptions can remain manual decisions.

Never let a new unknown seller title directly create a global canonical Product without explicit/provisional status and evidence.

## Ranking of unresolved work

Create a deterministic impact score so the agent works on high-value ambiguity first. Prefer signals such as:
- number of current branches
- number of observations
- price availability
- repeated normalized family
- whether there is a plausible legacy candidate
- semantic risk / false-match risk

Do not ask a human to review 18k rows. Group semantically and surface top unresolved families.

## Tests and quality gate

Add `pytest` and real tests; current `tests/` is empty.

The build must fail if mandatory guardrails regress.

Minimum gate:
1. unit tests for normalization and measurement extraction;
2. latest-snapshot tests from observation history;
3. positive mapping fixtures;
4. negative context-aware fixtures above;
5. determinism test;
6. schema validation for outputs;
7. no mutation of `data/extracted/observations.csv` or `data/raw`;
8. no `#`/silent fallback behavior that creates a Product on uncertainty.

## Performance

Do not keep an O(n²) full-title `SequenceMatcher` scan in normal build. If fuzzy candidate generation is retained, use blocking/indexing and make it optional/offline. Exact/rule/context paths should be the normal pipeline.

## Build report

`build_report.json` and console summary must include at least:
- raw history rows
- current latest rows
- unique current raw names
- mapped unique/current rows
- unresolved unique/current rows
- out-of-scope rows
- mapping coverage by unique name and by current observations
- price coverage using current state
- counts by mapping method/confidence/entity class
- new Product candidates
- rules applied
- regression pass/fail
- comparison with previous report if present

Prices: calculate current price statistics from latest current observations; historical price evidence may be reported separately and must not be mixed silently into current price stats.

## Documentation

Expand root `README.md` with separate sections:
- corpus discovery/collection (existing behavior)
- Product KB bootstrap
- Product KB build
- unresolved review loop
- tests
- what files are generated vs version-controlled

Document that local generated corpus is intentionally ignored by Git and that the GitHub repo alone does not contain the full current 2GIS observations.

## Scope exclusions for this task

- Do NOT modify `KAIDA.KZ-2.0`.
- Do NOT implement production DB migrations.
- Do NOT implement Search ranking or Issue #76 distance sensitivity; only preserve the field/backlog concept if already present in the reference workbook.
- Do NOT introduce an external LLM API into the build pipeline.
- Do NOT auto-publish provisional Product decisions.
- Do NOT refetch the entire 2GIS corpus merely to run tests.

## Execution protocol

1. Inspect and report repo state first.
2. Create/verify the reference workbook at the required path and SHA.
3. Implement bootstrap + deterministic pipeline in small commits.
4. Add tests before enabling broad auto-resolution rules.
5. Run bootstrap, full local build and pytest.
6. Review the highest-impact unresolved families yourself; add only high-confidence reusable rules/decisions.
7. Rerun until no new high-confidence rule is discovered in the first review batch.
8. Stop and report rather than guessing on architectural ambiguity.

Final report must show:
- changed files;
- commands run;
- test results;
- build metrics before/after;
- new rules/decisions added;
- regression results;
- top remaining architectural questions (maximum 10);
- exact commit SHA / branch.

Do not claim success if the actual local `observations.csv` was not processed or the regression suite did not pass.
