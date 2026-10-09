# Apify Instagram seller-candidate imports

The offline importer supports JSON arrays from Instagram Profile Finder and
Instagram Profile Scraper. It never calls Apify/Instagram, publishes offers,
sends messages, or writes to the KAIDA production database.

From the project root, with the exported JSON files stored outside Git:

```powershell
.\.venv\Scripts\python.exe src\import_apify_instagram.py .\data\raw\dataset_*.json
```

Output: `data/extracted/instagram_seller_candidates.csv` (Git-ignored).
The importer deduplicates by lowercased Instagram username, extracts public
phone numbers and WhatsApp links from `bio_links`/`external_url`/bio,
preserves source filenames, and marks geography for review.

`ALMATY_CLAIMED` means the account *mentions* Almaty, not that it is
verified within the city. `OTHER_CITY_REVIEW` and `REVIEW_CONFLICT` require
manual checks. Every result is `PENDING`. Do not treat any as a registered
KAIDA seller. Public business contact data may still be personal data:
restrict access, review retention/consent and Kazakhstan data residency
before processing in production. Do not commit data exports to public GitHub.

Optional API integration should only be added after accepting the pilot's
cost/quality and defining a strict per-run spend limit. Keep Apify API tokens
out of Git and use environment secrets.
