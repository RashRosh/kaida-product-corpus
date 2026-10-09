# Instagrapi: small optional technical check

Instagrapi is an **unofficial Instagram API client**, not a Meta-approved
data collection method. Instagram may challenge, suspend, or block the account.
Use only if you are authorized and accept those risks. Do not evade challenges,
use proxies to avoid limits, or repeatedly retry. The official Meta API or
licensed data sources are preferable for production.

This experiment is isolated from the 2GIS workflow and never writes seller
records or offers into KAIDA. It runs a maximum of three user searches with
five results each by default. Profiles/city/business status remain unverified.
No direct messages, no followers, no posts, no media downloads.

PowerShell from project root:

```powershell
git pull --ff-only
.\.venv\Scripts\python.exe -m pip install instagrapi
.\.venv\Scripts\python.exe src\instagrapi_probe.py
```

The first invocation of the script is a dry run and does not log in.
For an explicit authorized test, supply credentials through local environment
variables, run the test and then clear them:

```powershell
$env:IG_USERNAME = Read-Host "Instagram username"
$secure = Read-Host "Instagram password" -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try { $env:IG_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
.\.venv\Scripts\python.exe src\instagrapi_probe.py --run
Remove-Item Env:IG_USERNAME, Env:IG_PASSWORD
```

Warning: environment variables are plaintext during execution; avoid
shared computers, terminal recording, and screenshots of credentials.
Never put passwords in command-line arguments or Git files.

Output (ignored by Git): `data/extracted/instagrapi_candidates.csv`.
No results are assumed. Evaluate login success, search availability, share of
real Almaty food sellers, and data completeness before scaling.
