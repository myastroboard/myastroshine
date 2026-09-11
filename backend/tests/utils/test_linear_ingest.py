"""Linear frame ingest for the stacking pipeline."""

from __future__ import annotations

import io

import cv2
import numpy as np
import pytest
import rawpy

from app.exceptions import UnsupportedImageError
from app.utils import linear_ingest
from app.utils.linear_ingest import (
    LinearFrame,
    debayer_rgb,
    ingest_frame,
    stretch_composite_bgr,
    summarize_capture,
    to_display_bgr,
)


def _fits_bytes(data: np.ndarray, **header: object) -> bytes:
    from astropy.io import fits

    hdu = fits.PrimaryHDU(data=data)
    for key, value in header.items():
        hdu.header[key] = value
    buffer = io.BytesIO()
    hdu.writeto(buffer)
    return buffer.getvalue()


def test_fits_mono_16bit_becomes_linear_unit_float() -> None:
    """A 16-bit mono FITS plane maps to float32 in [0, 1], staying linear (no stretch)."""
    data = np.full((20, 30), 12000, dtype=np.uint16)
    data[5, 5] = 60000

    frame = ingest_frame(_fits_bytes(data), "light.fit")

    assert frame.data.dtype == np.float32
    assert frame.data.shape == (20, 30)
    assert not frame.is_color
    assert not frame.is_cfa
    assert frame.source_bit_depth == 16
    assert not frame.already_stretched
    # linear: 12000/65535 ~= 0.183, not pushed toward a 0.25 background target
    assert frame.data[0, 0] == pytest.approx(12000 / 65535, abs=1e-4)
    assert frame.data[5, 5] == pytest.approx(60000 / 65535, abs=1e-4)


def test_fits_bayer_pattern_is_recorded_and_mosaic_kept() -> None:
    """A CFA FITS (BAYERPAT header) stays a 2D mosaic, flagged for downstream debayer."""
    data = np.full((16, 16), 8000, dtype=np.uint16)

    frame = ingest_frame(_fits_bytes(data, BAYERPAT="GRBG"), "light.fit")

    assert frame.is_cfa
    assert frame.bayer_pattern == "GRBG"
    assert frame.data.ndim == 2


def test_fits_bottom_up_cfa_swaps_the_bayer_rows() -> None:
    """Flipping a mosaic for ROWORDER = BOTTOM-UP (even height) also swaps its Bayer rows."""
    data = np.full((16, 16), 8000, dtype=np.uint16)

    frame = ingest_frame(_fits_bytes(data, BAYERPAT="GRBG", ROWORDER="BOTTOM-UP"), "b.fit")

    assert frame.is_cfa
    assert frame.bayer_pattern == "BGGR"  # GRBG rows swapped


def test_fits_rgb_cube_reads_as_rgb_channel_order() -> None:
    """A (3, H, W) FITS cube becomes (H, W, 3) in R, G, B order."""
    base = np.full((10, 10), 5000.0, dtype=np.float32)
    red, green, blue = base.copy(), base.copy(), base.copy()
    red[1, 1] = 50000
    green[5, 5] = 50000
    blue[8, 8] = 50000

    frame = ingest_frame(_fits_bytes(np.stack([red, green, blue])), "rgb.fit")

    assert frame.data.shape == (10, 10, 3)
    assert frame.data[1, 1, 0] > frame.data[1, 1, 2]  # red spot brightest in channel 0
    assert frame.data[5, 5, 1] > frame.data[5, 5, 0]  # green spot in channel 1
    assert frame.data[8, 8, 2] > frame.data[8, 8, 0]  # blue spot in channel 2


def test_fits_rgb_cube_trailing_axis_reads_as_rgb_channel_order() -> None:
    """A (H, W, 3) FITS cube (trailing colour axis) is also read as R, G, B."""
    base = np.full((10, 10), 5000.0, dtype=np.float32)
    red, green, blue = base.copy(), base.copy(), base.copy()
    red[1, 1] = 50000
    green[5, 5] = 50000
    blue[8, 8] = 50000

    frame = ingest_frame(_fits_bytes(np.stack([red, green, blue], axis=-1)), "rgb.fit")

    assert frame.data.shape == (10, 10, 3)
    assert frame.data[1, 1, 0] > frame.data[1, 1, 2]
    assert frame.data[5, 5, 1] > frame.data[5, 5, 0]
    assert frame.data[8, 8, 2] > frame.data[8, 8, 0]


def test_fits_rgb_cube_bottom_up_is_flipped() -> None:
    top = np.full((10, 10), 5000.0, dtype=np.float32)
    top[0, :] = 40000.0  # bright first row, in file order
    cube = np.stack([top, top, top])  # same bright-top pattern on every channel

    frame = ingest_frame(_fits_bytes(cube, ROWORDER="BOTTOM-UP"), "rgb.fit")

    assert frame.data[-1, 0, 0] > frame.data[0, 0, 0]  # the bright row is now at the bottom


def test_fits_metadata_is_extracted() -> None:
    """Acquisition keywords are copied into LinearFrame.metadata under stable names."""
    data = np.zeros((8, 8), dtype=np.uint16)

    frame = ingest_frame(
        _fits_bytes(
            data,
            EXPTIME=10.0,
            GAIN=80,
            **{"CCD-TEMP": 25.3},
            **{"DATE-OBS": "2026-09-07T18:43:33"},
            OBJECT="C 11",
            FILTER="IRCUT",
            INSTRUME="Seestar S50",
        ),
        "light.fit",
    )

    assert frame.metadata["exposure_s"] == "10.0"
    assert frame.metadata["gain"] == "80"
    assert frame.metadata["sensor_temp_c"] == "25.3"
    assert frame.metadata["object"] == "C 11"
    assert frame.metadata["filter"] == "IRCUT"
    assert frame.metadata["instrument"] == "Seestar S50"


def test_summarize_capture_trusts_an_already_stacked_source_header() -> None:
    """A single already-stacked FITS (Seestar/ASIAIR) totals its own run in the
    header - STACKCNT/TOTALEXP are used as-is, not recomputed from one frame."""
    data = np.zeros((8, 8), dtype=np.uint16)
    frame = ingest_frame(
        _fits_bytes(
            data,
            OBJECT="M 31",
            TELESCOP="S50 Pro",
            FILTER="IRCUT",
            STACKCNT=1406,
            EXPOSURE=10.0,
            TOTALEXP=14060.0,
            **{"DATE-OBS": "2026-09-11T04:29:33"},
        ),
        "stack.fit",
    )

    info = summarize_capture([frame.metadata])

    assert info == {
        "object_name": "M 31",
        "telescope": "S50 Pro",
        "filter": "IRCUT",
        "date_obs": "2026-09-11T04:29:33",
        "frame_count": 1406,
        "exposure_s": 10.0,
        "total_exposure_s": 14060.0,
    }


def test_summarize_capture_sums_raw_subs_with_no_stack_total_in_the_header() -> None:
    """Many raw subs (the in-app multi-frame stacker) have no STACKCNT/TOTALEXP -
    the frame count and total exposure are derived from how many were passed."""
    acquisition = {"object": "NGC 7000", "exposure_s": "10.0"}

    info = summarize_capture([acquisition, acquisition, acquisition])

    assert info is not None
    assert info["frame_count"] == 3
    assert info["exposure_s"] == 10.0
    assert info["total_exposure_s"] == 30.0


def test_summarize_capture_handles_nothing_usable() -> None:
    assert summarize_capture([]) is None
    assert summarize_capture([{}]) is None


def test_summarize_capture_includes_gain_and_sensor_temp_when_present() -> None:
    info = summarize_capture([{"object": "M 42", "gain": "80", "sensor_temp_c": "-10.5"}])
    assert info is not None
    assert info["gain"] == 80.0
    assert info["sensor_temp_c"] == -10.5


def test_summarize_capture_ignores_an_unparseable_gain() -> None:
    """A malformed numeric field (corrupt header, non-numeric text) is dropped
    rather than raising - the rest of the capture info still comes through."""
    info = summarize_capture([{"object": "M 42", "gain": "not-a-number"}])
    assert info is not None
    assert "gain" not in info
    assert info["object_name"] == "M 42"


def test_summarize_capture_omits_date_obs_when_no_acquisition_has_one() -> None:
    info = summarize_capture([{"object": "M 42"}])
    assert info is not None
    assert "date_obs" not in info


def test_summarize_capture_omits_object_name_when_no_acquisition_has_one() -> None:
    info = summarize_capture([{"telescope": "S50 Pro"}])
    assert info is not None
    assert "object_name" not in info
    assert info["telescope"] == "S50 Pro"


def test_summarize_capture_omits_exposure_fields_when_none_is_known() -> None:
    """No acquisition carries exposure_s or total_exposure_s at all - neither
    key is set (nothing to sum, nothing trusted from a stack header)."""
    info = summarize_capture([{"object": "M 42"}])
    assert info is not None
    assert "exposure_s" not in info
    assert "total_exposure_s" not in info


def test_fits_bottom_up_row_order_is_flipped() -> None:
    """ROWORDER = BOTTOM-UP is flipped to top-down so frames align consistently."""
    data = np.zeros((20, 10), dtype=np.uint16)
    data[0, :] = 40000  # bright top row in file order

    top_down = ingest_frame(_fits_bytes(data), "a.fit")
    bottom_up = ingest_frame(_fits_bytes(data, ROWORDER="BOTTOM-UP"), "b.fit")

    assert top_down.data[0, 0] > top_down.data[-1, 0]
    assert bottom_up.data[-1, 0] > bottom_up.data[0, 0]  # flipped


def test_fits_float_already_normalized_is_left_as_is() -> None:
    """A 32-bit float FITS already in [0, 1] (a Siril stack export) is not rescaled."""
    data = np.full((10, 10), 0.4, dtype=np.float32)
    data[2, 2] = 0.95

    frame = ingest_frame(_fits_bytes(data), "stack.fits")

    assert frame.data[0, 0] == pytest.approx(0.4, abs=1e-5)
    assert frame.data[2, 2] == pytest.approx(0.95, abs=1e-5)
    assert frame.source_bit_depth == 32


def test_fits_float_adu_counts_are_normalized_by_peak() -> None:
    """A float FITS holding raw ADU counts (peak well above 1) is scaled to [0, 1]."""
    data = np.full((10, 10), 300.0, dtype=np.float32)
    data[2, 2] = 30000.0

    frame = ingest_frame(_fits_bytes(data), "raw.fits")

    assert frame.data.max() == pytest.approx(1.0, abs=1e-5)
    assert frame.data[0, 0] == pytest.approx(300.0 / 30000.0, abs=1e-4)


def test_fits_nan_pixels_do_not_poison_the_frame() -> None:
    """NaN/blank pixels map to 0, they don't blank the whole plane."""
    data = np.full((12, 12), 5000.0, dtype=np.float32)
    data[0:2, 0:2] = np.nan

    frame = ingest_frame(_fits_bytes(data), "blank.fits")

    assert frame.data[0, 0] == 0.0
    assert frame.data[6, 6] > 0.0


def test_fits_without_image_data_is_rejected() -> None:
    from astropy.io import fits

    buffer = io.BytesIO()
    fits.HDUList([fits.PrimaryHDU()]).writeto(buffer)

    with pytest.raises(UnsupportedImageError, match="no image data"):
        ingest_frame(buffer.getvalue(), "empty.fits")


def test_fits_garbage_is_rejected() -> None:
    with pytest.raises(UnsupportedImageError):
        ingest_frame(b"not a fits file", "broken.fit")


def test_fits_header_declared_oversized_shape_is_rejected_before_allocation() -> None:
    from astropy.io import fits

    header = fits.Header(
        [
            ("SIMPLE", True),
            ("BITPIX", -32),
            ("NAXIS", 2),
            ("NAXIS1", 50000),
            ("NAXIS2", 50000),
            ("EXTEND", True),
        ]
    )
    with pytest.raises(UnsupportedImageError, match="exceeding"):
        ingest_frame(header.tostring(padding=True).encode("ascii"), "huge.fits")


def test_fits_unsupported_cube_shape_is_rejected() -> None:
    data = np.zeros((2, 4, 5), dtype=np.float32)
    with pytest.raises(UnsupportedImageError, match="shape"):
        ingest_frame(_fits_bytes(data), "cube.fits")


def test_8bit_jpeg_is_flagged_stretched_and_linearised_in_rgb_order() -> None:
    """A Seestar-style 8-bit preview: already_stretched, sRGB-linearised, R-G-B order."""
    bgr = np.zeros((16, 24, 3), dtype=np.uint8)
    bgr[:, :, 2] = 200  # strong red in a BGR array
    ok, buffer = cv2.imencode(".jpg", bgr)
    assert ok

    frame = ingest_frame(buffer.tobytes(), "Light_C 11_10.0s.jpg")

    assert frame.already_stretched
    assert frame.source_bit_depth == 8
    assert frame.data.shape == (16, 24, 3)
    # red lives in channel 0 (RGB), and sRGB EOTF pulls 200/255 down below linear 0.784
    assert frame.data[0, 0, 0] > frame.data[0, 0, 2]
    assert frame.data[0, 0, 0] < 200 / 255


def test_16bit_png_is_linear_not_stretched() -> None:
    """A 16-bit PNG (a linear stack export) scales to [0, 1] and is not flagged stretched."""
    rng = np.random.default_rng(3)
    data = np.clip(rng.normal(3000, 200, size=(20, 20, 3)), 0, 65535).astype(np.uint16)
    ok, buffer = cv2.imencode(".png", data)
    assert ok

    frame = ingest_frame(buffer.tobytes(), "stack.png")

    assert not frame.already_stretched
    assert frame.source_bit_depth == 16
    assert float(np.median(frame.data)) == pytest.approx(3000 / 65535, abs=0.02)


def test_grayscale_png_stays_mono() -> None:
    gray = np.full((12, 18), 120, dtype=np.uint8)
    ok, buffer = cv2.imencode(".png", gray)
    assert ok

    frame = ingest_frame(buffer.tobytes(), "gray.png")

    assert frame.data.ndim == 2
    assert not frame.is_color


def test_rgba_png_drops_alpha() -> None:
    rgba = np.zeros((10, 10, 4), dtype=np.uint8)
    rgba[:, :, 3] = 255
    ok, buffer = cv2.imencode(".png", rgba)
    assert ok

    frame = ingest_frame(buffer.tobytes(), "rgba.png")

    assert frame.data.shape == (10, 10, 3)


def test_garbage_bytes_are_rejected() -> None:
    with pytest.raises(UnsupportedImageError):
        ingest_frame(b"not an image", "x.png")


def test_standard_ingest_handles_a_gray_plus_alpha_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 2-channel (gray + alpha) decode keeps the luminance plane and drops
    alpha, mirroring the BGRA-drop path for colour."""
    fake_decoded = np.zeros((10, 12, 2), dtype=np.uint8)
    fake_decoded[..., 0] = 100
    monkeypatch.setattr(linear_ingest.cv2, "imdecode", lambda *_a, **_k: fake_decoded)

    frame = ingest_frame(b"pretend png bytes", "gray_alpha.png")

    assert frame.data.ndim == 2
    assert not frame.is_color


def test_frame_over_the_pixel_cap_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    data = np.zeros((40, 40), dtype=np.uint16)
    monkeypatch.setattr(linear_ingest, "MAX_IMAGE_PIXELS", 100)
    with pytest.raises(UnsupportedImageError, match="exceeding"):
        ingest_frame(_fits_bytes(data), "big.fit")


def test_a_standard_format_frame_over_the_pixel_cap_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The generic post-decode size guard in ingest_frame (not any
    format-specific pre-check like FITS's header guard above)."""
    gray = np.full((40, 40), 100, dtype=np.uint8)
    ok, buffer = cv2.imencode(".png", gray)
    assert ok
    monkeypatch.setattr(linear_ingest, "MAX_IMAGE_PIXELS", 100)

    with pytest.raises(UnsupportedImageError, match="exceeding"):
        ingest_frame(buffer.tobytes(), "big.png")


def test_raw_dispatches_through_rawpy_to_linear_rgb(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeRaw:
        def __enter__(self) -> _FakeRaw:
            return self

        def __exit__(self, *exc_info: object) -> None:
            return None

        def postprocess(self, **kwargs: object) -> np.ndarray:
            assert kwargs["gamma"] == (1, 1)
            assert kwargs["no_auto_bright"] is True
            assert kwargs["output_bps"] == 16
            return np.full((4, 6, 3), 32768, dtype=np.uint16)

    monkeypatch.setattr(rawpy, "imread", lambda _file: _FakeRaw())

    frame = ingest_frame(b"fake raw", "photo.CR2")

    assert frame.data.shape == (4, 6, 3)
    assert frame.data[0, 0, 0] == pytest.approx(0.5, abs=1e-3)
    assert not frame.is_cfa


def test_raw_garbage_is_rejected() -> None:
    with pytest.raises(UnsupportedImageError):
        ingest_frame(b"not a raw file", "photo.nef")


def test_to_display_bgr_stretches_a_mono_frame_to_a_visible_thumbnail() -> None:
    """A dark linear mono frame becomes a stretched, non-black BGR thumbnail."""
    rng = np.random.default_rng(11)
    data = np.clip(rng.normal(0.03, 0.006, size=(200, 300)), 0, 1).astype(np.float32)
    data[50:60, 50:60] = 0.8  # a bright star

    thumb = to_display_bgr(LinearFrame(data=data, source_bit_depth=16), max_size=128)

    assert thumb.shape == (85, 128, 3)  # aspect kept, longest edge capped
    assert thumb.dtype == np.uint8
    assert int(np.median(thumb)) > 5  # background lifted off pure black by the stretch


def test_to_display_bgr_superpixel_debayers_a_cfa_frame_to_half_resolution() -> None:
    """A CFA frame is 2x2-superpixel de-mosaiced (half-res, 3-channel) for the thumbnail.

    Channels are stretched independently (same accepted tradeoff as the FITS
    single-image ingest), so this asserts structure survives, not colour balance.
    """
    rng = np.random.default_rng(5)
    cfa = np.clip(rng.normal(0.1, 0.01, size=(160, 160)), 0, 1).astype(np.float32)
    cfa[:80, :] += 0.5  # a bright band across the top half - a "trail" proxy

    thumb = to_display_bgr(LinearFrame(data=cfa, is_cfa=True, bayer_pattern="GRBG"), max_size=64)

    assert thumb.ndim == 3
    assert thumb.shape[2] == 3
    top, bottom = thumb[: thumb.shape[0] // 2], thumb[thumb.shape[0] // 2 :]
    assert int(top.mean()) > int(bottom.mean())  # the bright band is visible


def test_debayer_rgb_keeps_full_resolution_and_recovers_colour() -> None:
    """The edge-aware debayer is full-res and maps each Bayer site to its channel."""
    red, green, blue = 0.30, 0.50, 0.70
    mosaic = np.zeros((32, 40), dtype=np.float32)
    for i, channel in enumerate("GRBG"):
        row, col = i // 2, i % 2
        mosaic[row::2, col::2] = {"R": red, "G": green, "B": blue}[channel]

    out = debayer_rgb(LinearFrame(data=mosaic, is_cfa=True, bayer_pattern="GRBG"))

    assert out.data.shape == (32, 40, 3)  # full resolution, not halved
    centre = out.data[8:24, 8:32].reshape(-1, 3).mean(axis=0)
    assert centre == pytest.approx([red, green, blue], abs=0.02)


def test_debayer_rgb_preserves_a_negative_calibration_pedestal() -> None:
    """Calibration can push pixels below zero; the 16-bit round-trip must keep them."""
    mosaic = np.full((16, 16), 0.2, dtype=np.float32) - 0.1  # uniform -0.1 ... 0.1 after phases
    mosaic[0::2, 0::2] = -0.05

    out = debayer_rgb(LinearFrame(data=mosaic, is_cfa=True, bayer_pattern="RGGB"))

    assert float(out.data.min()) < 0.0


def test_debayer_rgb_passes_non_cfa_frames_through() -> None:
    rgb = np.zeros((8, 8, 3), dtype=np.float32)
    frame = LinearFrame(data=rgb)
    assert debayer_rgb(frame) is frame


def test_debayer_rgb_leaves_an_unrecognised_pattern_alone() -> None:
    mosaic = np.full((16, 16), 0.2, dtype=np.float32)
    frame = LinearFrame(data=mosaic, is_cfa=True, bayer_pattern="XYZW")
    assert debayer_rgb(frame) is frame


def test_stretch_composite_bgr_lifts_faint_signal_and_keeps_colour() -> None:
    """A linear composite (signal ~1% of the range) becomes a visible, neutral
    BGR frame - one shared stretch, not a per-channel one."""
    rng = np.random.default_rng(4)
    h, w = 200, 160
    sky = 0.008 + rng.normal(0, 0.0004, (h, w, 3)).astype(np.float32)
    sky[80:120, 60:100] += 0.01  # a faint "nebula" patch
    sky[:, :, 0] += 0.002  # a red cast the neutralisation should remove

    bgr = stretch_composite_bgr(sky, max_size=4096)

    assert bgr.shape == (h, w, 3)
    assert bgr.dtype == np.uint8
    assert int(np.median(bgr)) < 90  # background stays dark, not lifted to mid-grey
    patch = bgr[80:120, 60:100].mean()
    background = bgr[:40, :40].mean()
    assert patch > background + 15  # the faint patch is now clearly brighter
    # background neutral: channel means within a tight spread despite the red cast
    ch = bgr[:40, :40].reshape(-1, 3).mean(axis=0)
    assert float(ch.max() - ch.min()) < 12


def test_stretch_composite_bgr_handles_a_nan_rotation_wedge() -> None:
    data = np.full((60, 60, 3), 0.01, dtype=np.float32)
    data[:, :20] = np.nan  # unregistered edge
    out = stretch_composite_bgr(data)
    assert out.shape == (60, 60, 3)
    assert np.isfinite(out).all()
