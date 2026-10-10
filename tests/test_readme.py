"""The root README's install steps name the files in ``integrations/urcap/dist/`` — exactly them."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_the_readme_names_the_committed_polyscope_5_urcap():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    built = sorted(
        p.name for p in (ROOT / "integrations" / "urcap" / "dist").glob("perceptronic-ps5-*.urcap")
    )
    assert len(built) == 1, built
    named = set(re.findall(r"perceptronic-ps5-[0-9.]+\.urcap", readme))
    assert named == set(built), f"README.md names {sorted(named)}, integrations/urcap/dist has {built}"
    for name in built:
        assert f"raw/main/integrations/urcap/dist/{name}" in readme, (
            f"README.md has no download link for {name}"
        )
    # the stick's auto-install file is gone (2026-10-08): nothing may send a user to it
    assert "urmagic" not in readme.lower()
    assert "magic file" not in readme.lower()
