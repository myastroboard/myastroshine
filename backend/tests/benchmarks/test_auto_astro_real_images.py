"""Auto Astro on real captures: the sky deepened but never clipped, neutral, less noisy.

Synthetic tests guard the shape of each Auto Astro rule; only real captures show
whether the numbers hold up - the version this replaced passed its synthetic
tests and crushed real stacks' skies to black. This runs the whole path the app
runs (open the file as an upload would, Auto Astro on the picture the edit starts
from, the full render) on every image of a folder, one test per image:

    RUN_BENCHMARKS=1 AUTO_ASTRO_IMAGES=/path/to/captures pytest \\
        tests/benchmarks/test_auto_astro_real_images.py --no-cov -v

``AUTO_ASTRO_REPORT=/path/to/dir`` also writes a before | after JPEG per image, to
look at - a metric cannot say whether a picture got better. Opt-in, and the
captures are not in the repository: they are large and they are the photographers'.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.models import ProcessingParameters, StackParameters
from app.services.auto_astro import AutoAstroService, Measurements
from app.services.image_processing import ImageProcessingService
from app.services.linear_upload import PreparedComposite, is_linear_stack_upload, prepare_composite
from app.services.post_stack import render_stack_base
from app.services.star_detection import StarDetectionService
from app.utils import image_utils
from app.utils.sky_mask import fit_sky_mask

_EXTENSIONS = {".fit", ".fits", ".fts", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".dng"}
_FOLDER = os.environ.get("AUTO_ASTRO_IMAGES")
_REPORT = os.environ.get("AUTO_ASTRO_REPORT")
_FILES = (
    sorted(p for p in Path(_FOLDER).rglob("*") if p.suffix.lower() in _EXTENSIONS)
    if _FOLDER
    else []
)

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_BENCHMARKS") != "1" or not _FOLDER,
    reason="opt-in: set RUN_BENCHMARKS=1 and AUTO_ASTRO_IMAGES (see the module docstring)",
)

MAX_CLIPPED_SKY = 0.005  # fraction of the sky at 0-2 of 255
MIN_SKY_LEVEL = 8.0  # of 255: deep, not black
MAX_SKY_CAST = 4.0  # levels between the sky's brightest and darkest channel
#: Background noise under this sigma (of 255) is invisible: a phone's processed
#: night shot reads ~0.2, and a curve that deepens its sky may move that a little.
INVISIBLE_NOISE = 1.0
_BLACK = 2
_REPORT_HEIGHT = 900


@dataclass(frozen=True)
class _Capture:
    """A file opened the way an upload is: the picture an edit starts from."""

    before: np.ndarray  # BGR uint8
    composite: PreparedComposite | None  # set for linear data (FITS, 16-bit, ProRAW)

    @property
    def sky_mask(self) -> np.ndarray | None:
        return None if self.composite is None else self.composite.sky_mask

    def render(self, params: ProcessingParameters) -> np.ndarray:
        processing = ImageProcessingService()
        if self.composite is None:
            return processing.apply_parameters(self.before, params)
        return processing.apply_parameters(
            self.composite.composite,
            params,
            linear_composite=True,
            sky_mask=self.composite.sky_mask,
            render_hints=self.composite.hints,
        )


def _open(path: Path) -> _Capture:
    data = path.read_bytes()
    if not is_linear_stack_upload(data, path.name):
        return _Capture(image_utils.decode_image(data, path.name), None)
    prepared = prepare_composite(data, path.name)
    base = render_stack_base(
        prepared.composite, StackParameters(), prepared.sky_mask, prepared.hints
    )
    return _Capture(np.clip(base * 255.0, 0, 255).astype(np.uint8), prepared)


def _clipped_sky(image: np.ndarray, sky: np.ndarray | None) -> float:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    pixels = gray[sky] if sky is not None else gray
    return float((pixels <= _BLACK).mean())


def _summary(m: Measurements) -> str:
    blue, green, red = (round(v) for v in m.sky_bgr)
    return f"sky {m.sky:.0f} (B{blue} G{green} R{red}) noise {m.luma_noise:.1f}"


def _save_report(path: Path, before: np.ndarray, after: np.ndarray, notes: str) -> None:
    if not _REPORT:
        return
    out = Path(_REPORT)
    out.mkdir(parents=True, exist_ok=True)
    scale = min(1.0, _REPORT_HEIGHT / before.shape[0])
    size = (round(before.shape[1] * scale), round(before.shape[0] * scale))
    pair = np.hstack([cv2.resize(i, size, interpolation=cv2.INTER_AREA) for i in (before, after)])
    cv2.putText(pair, notes, (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 220, 255), 2)
    name = f"{path.stem}{path.suffix.replace('.', '_')}.jpg"  # a .fit and its .jpg export
    cv2.imwrite(str(out / name), pair, [cv2.IMWRITE_JPEG_QUALITY, 90])


@pytest.mark.parametrize("path", _FILES, ids=[p.name for p in _FILES])
def test_auto_astro_showcases_a_real_capture(path: Path) -> None:
    """The sky comes out deepened but not clipped, neutral, and no more visibly noisy."""
    service = AutoAstroService(StarDetectionService())
    capture = _open(path)
    wide_field = capture.composite is not None and capture.composite.hints.wide_field
    params = service.suggest_parameters(capture.before, capture.sky_mask, wide_field=wide_field)
    after = capture.render(params)

    sky = fit_sky_mask(capture.sky_mask, capture.before.shape)
    before_measured = service.measure(capture.before, sky)
    after_measured = service.measure(after, sky)
    _save_report(
        path, capture.before, after, f"{_summary(before_measured)} -> {_summary(after_measured)}"
    )

    if before_measured.sky < MIN_SKY_LEVEL:  # a Moon or a planet on black: nothing to deepen
        assert not params.curve_points
        return
    assert _clipped_sky(after, sky) < MAX_CLIPPED_SKY
    assert after_measured.sky >= MIN_SKY_LEVEL
    assert max(after_measured.sky_bgr) - min(after_measured.sky_bgr) <= MAX_SKY_CAST
    assert after_measured.luma_noise <= max(before_measured.luma_noise, INVISIBLE_NOISE)
