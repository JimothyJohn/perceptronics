"""perceptronics — the RGB-D cockpit, the volume detector and the pick server, parallel to ``urctl``.

Env-driven config, Protocol-based pluggable backends and a plain-data tool surface,
mirroring the control library's shape. The core is dependency-free; the RealSense
binding, the cockpit (:mod:`perceptronics.webapp`) and the pick node's server
(:mod:`perceptronics.picknode`) are the product path.
"""

from __future__ import annotations

from .config import PerceptionConfig
from .frame import Frame, synthetic_frame
from .rgbd import DepthImage, Intrinsics, RgbdFrame, synthetic_rgbd
from .segment import Mask, ObjectFeatures, Segmenter, StubSegmenter, extract_features

__all__ = [
    "PerceptionConfig",
    "Frame",
    "synthetic_frame",
    "DepthImage",
    "Intrinsics",
    "RgbdFrame",
    "synthetic_rgbd",
    "Mask",
    "ObjectFeatures",
    "Segmenter",
    "StubSegmenter",
    "extract_features",
]
