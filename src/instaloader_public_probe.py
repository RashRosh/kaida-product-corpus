"""Opt-in, no-login Instaloader probe for known PUBLIC profiles only."""
import argparse
import csv
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "extracted" / "instaloader_public_probe.csv"
USER_RE = re.compile(r"^[A-Za-z0-9._]{1,30}$")
FIELDS = ("username", "profile_url", "full_name", "biography", "followers", "posts", "status", "error")


def normalize_username(value: str) -> str:
    value = value.strip().rstrip("/")
    value = re.sub(r"^https?://(?:www\\.)?instagram\\.com/", "", value, flags=re.I)
    value = value.lstrip("@").split("?", 1)[0]
    if "/" in value or not USER_RE.fullmatch(value):
        raise ValueError("Provide a profile username or instagram.com/username URL")
    return value.lower()


def probe(names: list[str], output: Path) -> None:
    import instaloader
    loader = instaloader.Instaloader(
        download_pictures=False,
        download_videos=False,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
        quiet=True,
    )
    results = []
    for index, name in enumerate(names):
        row = dict.fromkeys(FIELDS, "")
        row.update(username=name, profile_url=f"https://www.instagram.com/{name}/")
        try:
            profile = instaloader.Profile.from_username(loader.context, name)
            if profile.is_private:
                row["status"] = "PRIVATE_SKIP"
            else:
                row.update(
                    full_name=profile.full_name or "",
                    biography=profile.biography or "",
                    followers=profile.followers,
                    posts=profile.mediacount,
                    status="PUBLIC_OK",
                )
        except Exception as exc:
            row.update(status="FAILED", error=type(exc).__name__)
            results.append(row)
            print(f"{name}: {type(exc).__name__}; stopping after first failure")
            break
        results.append(row)
        print(f"{name}: {row['status']}")
        if index + 1 < len(names):
            time.sleep(5)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(results)
    print(f"Saved {len(results)} rows: {output}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profiles", nargs="*", help="1-3 public profile usernames/URLs")
    parser.add_argument("--run", action="store_true", help="Actually fetch profiles without login")
    args = parser.parse_args()
    if not 1 <= len(args.profiles) <= 3:
        parser.error("Supply between 1 and 3 public usernames")
    try:
        names = list(dict.fromkeys(normalize_username(name) for name in args.profiles))
    except ValueError as exc:
        parser.error(str(exc))
    print("Profiles:", ", ".join(names))
    if not args.run:
        print("DRY RUN: no Instagram requests. Add --run to fetch public metadata.")
        return
    probe(names, OUT)


if __name__ == "__main__":
    main()
