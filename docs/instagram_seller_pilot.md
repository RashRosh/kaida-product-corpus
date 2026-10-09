# Instagram seller discovery: exploratory pilot

This isolated experiment finds **candidate public Instagram profile URLs** in publicly
accessible search-engine result pages. It does **not** scrape Instagram, log in,
bypass access controls, use private data or message accounts.

## Usage (PowerShell)

```powershell
.\.venv\Scripts\python.exe src\instagram_discover.py
.\.venv\Scripts\python.exe src\instagram_discover.py --run --limit 3
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_instagram_discover.py"
```

The first command only prints search URLs. The second makes at most three
sequential search-page requests with a minimum 3-second interval. It stops at
HTTP 401/403/429 or a detected challenge, and does not attempt to evade restrictions.

Output: `data/extracted/instagram_candidates.csv` (ignored by Git).
Deduplication uses normalized Instagram username. Existing review columns are
preserved on later runs. Query attribution is the first query that found the account.

## Limitations / decisions

- Search-result HTML is unstable and may expose zero usable profile links.
- Search engines may refuse automation. If so, stop and evaluate permitted APIs,
  licensed providers or manual discovery rather than implementing bypasses.
- City, product category, seller activity, contacts and prices are **not verified**.
- An Instagram account is **not** a KAIDA seller or offer.
- Review results manually; never auto-publish these candidates to the buyer catalog.
- Do not commit personal contact information or downloaded profile content.
- Do not transfer this dataset into KAIDA production without consent, provenance,
  data-protection review and compliance with Kazakhstan data-residency requirements.
- No automated messaging and no scraping of private/age-restricted content.

## Acceptance criteria for the pilot

Measure requests succeeded, profiles per query, duplicate rate, proportion of
candidates actually selling food in Almaty, and proportion with public product
prices. Manually review the first 30 candidates before deciding to scale.
