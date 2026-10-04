from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from kb.resolver import Resolver
from kb.rules import load_rules


@pytest.fixture(scope="session")
def root() -> Path:
    return ROOT


@pytest.fixture(scope="session")
def resolver(root: Path) -> Resolver:
    kb_dir = root / "kb"
    return Resolver(kb_dir, load_rules(kb_dir / "rules.yaml"))
