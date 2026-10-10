"""The root README's install steps name the files in ``integrations/urcap/dist/`` — exactly them,
for both pendants, with the same steps for each (Nick, 2026-10-10: "as identical as possible")."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("glob", "pattern"),
    [
        ("perceptronic-ps5-*.urcap", r"perceptronic-ps5-[0-9.]+\.urcap"),  # PolyScope 5
        ("perceptronic-[0-9]*.urcapx", r"perceptronic-[0-9.]+\.urcapx"),  # PolyScope X
    ],
)
def test_the_readme_names_the_committed_urcap(glob, pattern):
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    built = sorted(p.name for p in (ROOT / "integrations" / "urcap" / "dist").glob(glob))
    assert len(built) == 1, built
    named = set(re.findall(pattern, readme))
    assert named == set(built), f"README.md names {sorted(named)}, integrations/urcap/dist has {built}"
    for name in built:
        assert f"raw/main/integrations/urcap/dist/{name}" in readme, (
            f"README.md has no download link for {name}"
        )
    # the stick's auto-install file is gone (2026-10-08): nothing may send a user to it
    assert "urmagic" not in readme.lower()
    assert "magic file" not in readme.lower()


def test_both_pendants_get_the_same_install_steps():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    install = readme[readme.index("## Install it") : readme.index("## Developers")]
    # one download table and one on-the-pendant table, each with a row/column per pendant
    assert install.count("| **PolyScope 5**") == 1 and install.count("| **PolyScope X**") == 1
    assert "| | PolyScope 5 | PolyScope X |" in install
    for row in ("Open the URCaps screen", "Add the file", "Finish"):
        assert install.count(f"| {row} |") == 1, row
    # the same words for the node on both: Perceive to set up, Pounce in the program
    assert "**Installation** → **URCaps** → **Perceive**" in install
    assert "**Application** → **Perceive**" in install
    assert install.count("**Pounce**") == 1
