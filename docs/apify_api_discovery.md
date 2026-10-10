# Apify automated discovery (opt-in)

Already imported 49 unique candidate accounts from prior exports. No need to
repeat paid searches. Runs are **not automatic** and never message accounts.

The script uses the documented actor
`instagram-scraper/instagram-profile-finder` and sets Apify's
`maxTotalChargeUsd` cap on each invocation. It has no Instagram login.
Start with a dry run:

```powershell
git pull --ff-only
.\.venv\Scripts\python.exe src\run_apify_discovery.py
```

When ready for a paid test, obtain the Apify API token in Apify Console.
Set it locally, do not paste it into ChatGPT or commit it to GitHub:

```powershell
$env:APIFY_TOKEN = Read-Host "Apify API token"
.\.venv\Scripts\python.exe src\run_apify_discovery.py --run --limit 2 --max-usd 0.10
Remove-Item Env:APIFY_TOKEN
```

**Important:** if the request times out or fails, check Apify Console before
retrying: the remote run may still have incurred charges. Never set a blanket
retry loop. The local CSV importer runs separately against JSON exports,
and all candidates still require review for location, activity and suitability.
Avoid pushing exports or contacts to public GitHub. Production storage and
privacy decisions must be reviewed for KAIDA's Kazakhstan residency constraints.

Input terms live in `input/instagram_queries.txt`. Successful run JSON is
stored under `data/raw`, ignored by Git. To update candidates, import ALL
past exports together; the importer replaces its output from the supplied
files and does not merge automatically with the existing CSV.
