"""Build the deterministic Production KB Export Package v1."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from kb.export_package import PACKAGE_NAME, build_package  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path, default=ROOT / "dist" / PACKAGE_NAME)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = build_package(args.root, args.out)
    counts = manifest["counts"]
    print("Production KB export package complete")
    print(f"Package schema version: {manifest['package_schema_version']}")
    print(f"Source checkpoint: {manifest['source_checkpoint_tag']}")
    print(f"Source SHA: {manifest['source_commit_sha']}")
    print(f"Products: {counts['exported_products']} / {counts['source_products_total']}")
    print(f"Aliases: {counts['exported_aliases']} / {counts['source_aliases']}")
    print(f"Categories: {counts['categories']}")
    print(f"Outputs: {args.out}")


if __name__ == "__main__":
    main()
