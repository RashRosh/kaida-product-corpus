# Official source crosswalk

This directory contains versioned inputs for the separate
`KAIDA Product ↔ Official Entity` reference layer.

- `sources.json` identifies official sources, versions, URLs, local snapshots,
  and SHA-256 checksums.
- `crosswalk_decisions.csv` contains explicit reviewed semantic decisions.

The build never promotes an identical or similar name to a mapping. Name-only
candidates remain in the generated review queue until a decision is added.
Legacy `BNS` evidence is retained separately because the original workbook
contains a source tag and landing-page URL but no official entity codes.
