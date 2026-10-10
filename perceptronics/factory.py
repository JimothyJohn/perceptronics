"""Backend factory — turn the configured segmenter name into an instance.

Maps ``config.segment_backend`` to a concrete :class:`~perceptronics.segment.Segmenter`,
importing the optional heavy backend lazily so selecting ``"stub"`` never touches torch.
"""

from __future__ import annotations

from .config import PerceptionConfig
from .segment import Segmenter, StubSegmenter

SEGMENT_BACKENDS = ("stub", "sam")


def make_segmenter(config: PerceptionConfig) -> Segmenter:
    name = config.segment_backend
    if name == "stub":
        return StubSegmenter(link_tolerance=float(config.blob_link_tolerance))
    if name == "sam":
        from .backends.sam import SamSegmenter

        return SamSegmenter(model_id=config.sam_model) if config.sam_model else SamSegmenter()
    raise ValueError(f"unknown segment backend {name!r}; choose from {SEGMENT_BACKENDS}")
