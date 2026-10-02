Собираем названия продуктов

## Seller metadata fallback

- `branch_id` is the stable seller/source identity.
- If the seller name cannot be determined quickly, use `UNKNOWN` in `input/firms.csv`.
- Never guess a seller name.
- Missing seller name must not block collection.
- Replacing `UNKNOWN` later may update seller metadata without creating a new observation if the product state itself has not changed.
