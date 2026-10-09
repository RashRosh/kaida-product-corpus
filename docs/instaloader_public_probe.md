# No-login Instaloader pilot

This tests whether anonymous access can read basic metadata from 1-3 **known,
public** Instagram profiles. It does not search Instagram, download posts, use
cookies, or log in. Instagram may still rate-limit or block the connection.
Stop on the first error; do not bypass protection or repeatedly retry.

From PowerShell in the repository:

```powershell
git pull --ff-only
.\.venv\Scripts\python.exe -m pip install instaloader
.\.venv\Scripts\python.exe .\src\instaloader_public_probe.py instagram
.\.venv\Scripts\python.exe .\src\instaloader_public_probe.py instagram --run
```

The first script invocation is a dry run. The second performs one anonymous
request for a known public profile. Replace `instagram` with 1-3 known public
business usernames (not your own working accounts) once the pilot functions.

CSV output: `data/extracted/instaloader_public_probe.csv`, ignored by Git.
Profiles with status PUBLIC_OK only confirm metadata access, **not** seller
identity, food relevance, Almaty location or permission to publish.

Do not use the optional logged-in mode of Instaloader. This experiment has no
session file, password option, proxies, CAPTCHA bypass or automatic retries.
