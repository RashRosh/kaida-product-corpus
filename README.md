# KAIDA product corpus and Product KB

The repository has two deliberately separate workflows:

1. discover and collect immutable seller evidence from 2GIS;
2. build a deterministic, reviewable Product Knowledge Base from that evidence.

Local generated corpus files are intentionally ignored by Git. A GitHub checkout
alone does not contain the current `data/raw` pages or the full local
`data/extracted/observations.csv` history.

## Corpus discovery and collection

`input/searches.csv` contains city + search queries.

Run:

```powershell
.\.venv\Scripts\python.exe .\src\discover.py
```

`discover.py`:

- walks 2GIS search result pages;
- extracts only numeric `branch_id` values from `/firm/<id>` links;
- never needs company names; new sellers are stored as `UNKNOWN`;
- deduplicates by `branch_id`;
- appends new sellers to `input/firms.csv`;
- then launches the existing `src/collect.py` product collector.

Use `--discover-only` if only seller discovery is needed.

`src/collect.py` fetches 2GIS `items_by_branch` pages. It stores original API
responses in `data/raw`, maintains product/source metadata in
`data/extracted/products.csv`, and appends to `observations.csv` only when a
product state changes. Consequently, `observations.csv` is history rather than a
current catalog snapshot. The KB build derives latest state per
`(branch_id, product_id)` without changing the history.

## Seller metadata fallback

- `branch_id` is the stable seller/source identity.
- `seller_name` is optional metadata and is not required for corpus collection.
- New automatically discovered sellers use `UNKNOWN`.
- Never guess a seller name.
- Missing seller name must not block collection.
- Replacing `UNKNOWN` later may update seller metadata without creating a new observation if the product state itself has not changed.

`src/fetch.py` remains a debugging fetch for the first seller and is not part of
the KB pipeline. `src/analyze_variants.py` remains an offline candidate probe;
its O(n²) fuzzy scan is not used by the deterministic build.

## Product KB bootstrap

The reviewed workbook must exist at
`reference/KAIDA_Master_KB_Iteration_3.xlsx` with SHA-256
`74cb60b07c970bd83151dd1cd226b06e11d2798c5d7bf6da53ae31807333213a`.

Export its reviewed Products, aliases, attribute definitions, mappings, rules,
and decision log into repository-native sources:

```powershell
.\.venv\Scripts\python.exe .\src\bootstrap_kb_reference.py
```

The bootstrap verifies the hash and required sheets. It preserves workbook
statuses such as `PROVISIONAL_AI`; it does not promote them to approved
Products.

## Product KB build

Run the deterministic build against the local observation history:

```powershell
.\.venv\Scripts\python.exe .\src\build_kb.py
```

Optional paths and review limit:

```powershell
.\.venv\Scripts\python.exe .\src\build_kb.py --input data\extracted\observations.csv --out data\kb
.\.venv\Scripts\python.exe .\src\build_kb.py --top-unresolved 200
```

The build uses exact context-aware matches, versioned rules, reviewed mappings,
and manual decisions. It does not perform full-title fuzzy merging or call an
external LLM. Low-confidence and context-incompatible titles stay unresolved.
Current price statistics use only the latest state; historical price counts are
reported separately and `price_basis` remains `UNKNOWN` unless source evidence
states it. To include stable deltas without breaking repeat-build determinism,
place a retained report at `data/kb/previous_build_report.json`; the build reads
but does not overwrite that file.

## Unresolved review loop

1. Review `data/kb/unresolved.csv` from the highest `impact_score` downward.
2. Group by `family_key`; do not review thousands of duplicate offers one by one.
3. Keep one-off evidence in append-only `kb/manual_decisions.jsonl`.
4. Promote a repeated, context-safe pattern into `kb/rules.yaml`.
5. Add positive and negative fixtures under `tests/kb/fixtures/`.
6. Rerun tests and the full build.

Unknown seller titles never create approved global Products automatically.
Mappings to provisional Products are labeled `PROVISIONAL_MAPPING` and remain in
the unresolved review queue.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

The suite covers normalization, measurement extraction, history snapshots,
mandatory semantic guardrails, conservative resolution, workbook bootstrap,
output schemas, source immutability, and byte determinism.

## Version-controlled and generated files

Version-controlled:

- `reference/KAIDA_Master_KB_Iteration_3.xlsx` and its source note;
- `kb/seed/*.csv`, `kb/rules.yaml`, and `kb/manual_decisions.jsonl`;
- pipeline code and regression fixtures.

Generated and ignored:

- `data/raw/*` except `.gitkeep`;
- `data/extracted/*` except `.gitkeep`;
- `data/kb/*` except `.gitkeep`.

`data/kb/` contains `latest_observations.csv`, `observed_names.csv`,
`mappings.csv`, `unresolved.csv`, `prices.csv`, `products.csv`, `aliases.csv`,
`build_report.json`, and `regression_report.json`.
