# Official Source Reconciliation

## Scope

This layer records evidence and reviewed semantic relations between current
KAIDA Products and official entities. It does not alter Product identity,
aliases, resolution rules, or the observation corpus.

## Recovered legacy BNS provenance

The legacy workbook
`reference/legacy/KAIDA.KZ_initial_product_catalog_v0.1.xlsx` uses `BNS` as a
source identifier for the Bureau of National Statistics of Kazakhstan.

The workbook establishes the following facts:

- its `Sources` sheet describes BNS as an official classification framework;
- the BNS URL is `https://stat.gov.kz/ru/classifiers/statistical/23/`;
- 748 of 787 legacy Product rows include `BNS` in `source_codes`;
- every one of those rows repeats the same landing-page URL;
- no row stores a BNS entity code or a direct entity URL.

Therefore, the workbook contains 748 legacy source references and zero
recoverable entity-level BNS mappings. A BNS tag is not treated as a current
verified relation.

The legacy URL currently opens the Bureau's general directories page, not a
specific classifier or entity. The exact classifier/version intended by the
legacy author cannot be recovered from the workbook alone.

## Current official source used for the first crosswalk

The first reproducible crosswalk uses the official national **Classifier of
Products by Economic Activity**, `KPVED GK RK 04-2008`:

- official agency: Bureau of National Statistics of Kazakhstan;
- introduced: 2009-01-01;
- official page states updated: 2024-04-01;
- official page: `https://stat.gov.kz/ru/classifiers/statistical/21/`;
- the downloaded XLS is stored unchanged under `reference/official/`;
- its SHA-256 is pinned in `kb/official/sources.json`.

This is a current authoritative product classifier selected for the first
crosswalk mechanism. It is not asserted to be the unnamed classifier used by
the legacy `BNS` tag.

## Workflow

```text
versioned legacy workbook + versioned official XLS + reviewed decisions
    -> deterministic extraction and validation
    -> official entities + crosswalk + unresolved/conflict reports
```

Run:

```powershell
.\.venv\Scripts\python.exe .\src\build_official_reconciliation.py
```

Generated outputs are written under `data/kb/official/` and are not edited by
hand. `kb/official/crosswalk_decisions.csv` is the only reviewed semantic input.

## Semantic safety

Allowed relations are `EXACT`, `BROADER`, `NARROWER`, `NO_MATCH`, and
`NOT_APPLICABLE`. Identical normalized names create review candidates only.
Fuzzy name similarity does not create either a candidate or a mapping.

The build rejects unknown Product/source IDs, missing official entities,
contradictory relations, multiple conflicting EXACT mappings, provenance loss,
malformed official codes, and source snapshot checksum changes.
