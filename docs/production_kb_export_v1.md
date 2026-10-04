# Production KB Export Package v1

This slice defines a small deterministic export package for the future
`KAIDA.KZ-2.0` importer. The package is a projection of the closed checkpoint
`v0.1.0-kb-foundation` at commit
`25a27637d3c131c6ab22f855e7d0d872745ea6e9`.

It does not approve Products, expand coverage, change ontology, import into
production, or carry raw/research evidence downstream.

## Build

```powershell
.\.venv\Scripts\python.exe .\src\build_official_reconciliation.py
.\.venv\Scripts\python.exe .\src\build_production_export.py
```

Default output:

```text
dist/kaida-kb-v1/
```

The generated directory is ignored by Git. The source of truth is the versioned
KB input plus the generator.

## Runtime Contract

`products.csv` contains only `LEGACY_APPROVED` Products. Stable `KAIDA-Pxxxx`
Product IDs are preserved.

`aliases.csv` contains only aliases where all of the following are true:

- `status = ACTIVE`
- `safe_for_auto_match = YES`
- `product_id` exists in `products.csv`

`categories.csv` contains only categories used by exported Products. A category
code with conflicting labels is a validation failure.

`official_mappings.csv` is optional provenance. It includes only
`CURRENT_VERIFIED` mappings for exported Products with relation `EXACT`,
`BROADER`, or `NARROWER`. Official mappings do not control Product eligibility.

`attribute_definitions.csv` is intentionally omitted from v1 runtime export.
The current definitions are `WORKING_I3` offer-attribute schema, not a required
contract for first Product identity import.

## Exclusions

The package excludes raw 2GIS evidence, full observation history, seller/company
data, unresolved queues, provisional Products, provisional mappings, conflict
queues, manual review queues, raw prices, price aggregates, source workbooks,
official XLS snapshots, and crawler tooling.

## Verification

`manifest.json` records source checkpoint identity, immutable corpus hashes,
counts, included/excluded datasets, source file hashes, official source snapshot
identity, and SHA-256 for each exported package file.

The generator validates:

- manifest file hashes
- unique Product and alias IDs
- stable `KAIDA-Pxxxx` Product IDs
- no dangling alias or parent Product references
- category label consistency
- no unknown Product categories
- no official mappings to missing Products
- no duplicate conflicting official mappings
- schema version
- required fields
- deterministic row ordering

