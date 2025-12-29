"""Shared fixtures for RAC format tests."""

import os
from pathlib import Path


def get_statute_dir():
    """Get statute directory from env or default."""
    default = Path.home() / "CosilicoAI" / "cosilico-us" / "statute"
    return Path(os.environ.get("STATUTE_DIR", default))


def get_all_rac_files():
    """Get all .rac files for parametrized testing."""
    statute_dir = get_statute_dir()
    if not statute_dir.exists():
        return []
    return list(statute_dir.rglob("*.rac"))
