"""Unit tests for the perceptronics package — no camera, no model weights, no deps.

Config, Frame, the PNG codec and the CLI on synthetic frames. The optional torch
backend is not imported here (it is behind the `sam` extra and the factory's lazy import).
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

import pytest

from perceptronics import (
    PerceptionConfig,
    synthetic_frame,
)
from perceptronics.frame import Frame, normalize
from perceptronics.pngio import load_png

# The real fixture: three apples (two red, one green) on a brushed-steel table —
# the PickAndStack pick target. Lives at <repo>/inputs/image.png.
IMAGE_PATH = Path(__file__).resolve().parent.parent / "inputs" / "image.png"

# ----- config ----------------------------------------------------------------


def test_config_defaults_and_env(monkeypatch):
    assert PerceptionConfig().segment_backend == "stub"
    monkeypatch.setenv("PERCEPTRONICS_WIDTH", "320")
    monkeypatch.setenv("PERCEPTRONICS_SEGMENT_BACKEND", "sam")
    cfg = PerceptionConfig.from_env()
    assert cfg.width == 320
    assert cfg.segment_backend == "sam"
    # explicit kwargs win over the environment
    assert PerceptionConfig.from_env(width=64).width == 64


def test_config_bad_env_is_clear(monkeypatch):
    monkeypatch.setenv("PERCEPTRONICS_FPS", "fast")
    with pytest.raises(ValueError, match="PERCEPTRONICS_FPS"):
        PerceptionConfig.from_env()


# ----- frame -----------------------------------------------------------------


def test_frame_validates_buffer_size():
    with pytest.raises(ValueError):
        Frame(width=2, height=2, data=b"\x00\x00\x00")  # too short


def test_synthetic_frame_paints_disks():
    f = synthetic_frame(64, 48)
    assert (f.width, f.height, f.channels) == (64, 48, 3)
    # center of the first (red) disk should be red, a corner should be background
    cx, cy, _, (r, g, b) = (
        64 // 4,
        48 // 2,
        4,
        (220, 40, 40),
    )
    assert f.pixel(cx, cy) == (r, g, b)
    assert f.pixel(0, 0) != (r, g, b)


def test_normalize_flat_is_zeros():
    assert normalize([5.0, 5.0, 5.0]) == [0.0, 0.0, 0.0]
    assert normalize([0.0, 5.0, 10.0]) == [0.0, 0.5, 1.0]


# ----- depth -----------------------------------------------------------------


# ----- blobs -----------------------------------------------------------------


# ----- factory + pipeline ----------------------------------------------------


# ----- tool registry ---------------------------------------------------------


# ----- CLI -------------------------------------------------------------------


# ----- PNG decoder (dependency-free) -----------------------------------------


def _encode_png(width: int, height: int, rgb: bytes) -> bytes:
    """Minimal filter-0 RGB PNG encoder — for round-tripping the decoder."""

    def chunk(tag: bytes, body: bytes) -> bytes:
        return (
            struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)  # 8-bit RGB
    raw = bytearray()
    stride = width * 3
    for y in range(height):
        raw.append(0)  # filter type None
        raw += rgb[y * stride : (y + 1) * stride]
    sig = b"\x89PNG\r\n\x1a\n"
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(bytes(raw))) + chunk(b"IEND", b"")


def test_png_decoder_roundtrip_exact(tmp_path):
    rgb = bytes([255, 0, 0, 0, 255, 0, 0, 0, 255, 255, 255, 0])  # 2x2: R G B Y
    p = tmp_path / "tiny.png"
    p.write_bytes(_encode_png(2, 2, rgb))
    w, h, c, buf = load_png(str(p))
    assert (w, h, c) == (2, 2, 3)
    assert buf == rgb
    # round-trips through Frame too
    f = Frame.from_png(str(p))
    assert f.pixel(0, 0) == (255, 0, 0)
    assert f.pixel(1, 1) == (255, 255, 0)


def test_png_decoder_rejects_non_png(tmp_path):
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not a png")
    with pytest.raises(ValueError, match="not a PNG"):
        load_png(str(bad))


# ----- Frame loading / scaling -----------------------------------------------


def test_frame_resize_and_to_rgb():
    f = synthetic_frame(64, 48)
    small = f.resized(16, 12)
    assert (small.width, small.height) == (16, 12)
    # to_rgb drops alpha
    rgba = Frame(width=1, height=1, data=bytes([10, 20, 30, 40]), channels=4)
    assert rgba.to_rgb().channels == 3
    assert rgba.to_rgb().pixel(0, 0) == (10, 20, 30)


# ----- the real apples-on-steel image ----------------------------------------


def test_real_image_loads_at_full_resolution():
    if not IMAGE_PATH.exists():
        pytest.skip(f"fixture image missing: {IMAGE_PATH}")
    f = Frame.from_png(str(IMAGE_PATH))
    assert (f.width, f.height, f.channels) == (1408, 768, 3)  # alpha dropped


def test_the_cli_survives_a_legacy_windows_codepage(tmp_path):
    """`perceptronics doctor` prints arrows; on a Windows console (cp1252, strict) that raised
    UnicodeEncodeError and the setup script died at its last step (CI, windows-latest,
    2026-09-30). The CLI must degrade the character, not crash."""
    import os
    import subprocess
    import sys
    from pathlib import Path

    env = {k: v for k, v in os.environ.items() if k != "UR_CELL" and not k.startswith("PERCEPTRONICS_")}
    env["PYTHONIOENCODING"] = "cp1252"  # strict errors, as on a legacy console
    out = subprocess.run(
        [sys.executable, "-m", "perceptronics", "--cell", "sim", "doctor"],
        cwd=Path(__file__).resolve().parent.parent,
        env=env,
        capture_output=True,
        timeout=120,
    )
    assert b"UnicodeEncodeError" not in out.stderr, out.stderr[-400:]
    # no robot or cockpit here, so the verdict is NOT READY (exit 1): what matters is that it got there
    assert out.returncode in (0, 1) and b"verdict:" in out.stdout
