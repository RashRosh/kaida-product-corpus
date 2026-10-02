Собираем названия продуктов

## Automatic discovery

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

## Seller metadata fallback

- `branch_id` is the stable seller/source identity.
- `seller_name` is optional metadata and is not required for corpus collection.
- New automatically discovered sellers use `UNKNOWN`.
- Never guess a seller name.
- Missing seller name must not block collection.
- Replacing `UNKNOWN` later may update seller metadata without creating a new observation if the product state itself has not changed.
