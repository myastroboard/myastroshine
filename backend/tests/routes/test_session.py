"""GET /api/session/{session_id}/capture-info."""

from __future__ import annotations

import io

import numpy as np


def test_capture_info_for_a_stacked_fits_upload(client) -> None:
    """A FITS upload's header (object, telescope, filter, frame count, exposure)
    surfaces through the capture info endpoint - the editor's info panel."""
    from astropy.io import fits

    rng = np.random.default_rng(3)
    data = rng.normal(500, 20, size=(40, 60)).astype(np.float32)
    hdu = fits.PrimaryHDU(data=data)
    hdu.header["OBJECT"] = "M 31"
    hdu.header["TELESCOP"] = "S50 Pro"
    hdu.header["FILTER"] = "IRCUT"
    hdu.header["STACKCNT"] = 1406
    hdu.header["EXPOSURE"] = 10.0
    hdu.header["TOTALEXP"] = 14060.0
    buffer = io.BytesIO()
    hdu.writeto(buffer)

    session_id = client.post(
        "/api/upload",
        files={"file": ("stack.fit", buffer.getvalue(), "application/octet-stream")},
    ).json()["session_id"]

    response = client.get(f"/api/session/{session_id}/capture-info")

    assert response.status_code == 200
    assert response.json() == {
        "object_name": "M 31",
        "telescope": "S50 Pro",
        "filter": "IRCUT",
        "frame_count": 1406,
        "exposure_s": 10.0,
        "total_exposure_s": 14060.0,
        "date_obs": None,
        "gain": None,
        "sensor_temp_c": None,
    }


def test_capture_info_is_null_for_an_ordinary_photo(client, sample_jpeg: bytes) -> None:
    """A plain image has no linked stack, so there is nothing to show."""
    session_id = client.post(
        "/api/upload", files={"file": ("photo.jpg", sample_jpeg, "image/jpeg")}
    ).json()["session_id"]

    response = client.get(f"/api/session/{session_id}/capture-info")

    assert response.status_code == 200
    assert response.json() is None


def test_capture_info_for_an_unknown_session_is_404(client) -> None:
    response = client.get("/api/session/00000000-0000-0000-0000-000000000000/capture-info")

    assert response.status_code == 404


def test_capture_info_for_a_malformed_session_id_is_404(client) -> None:
    response = client.get("/api/session/not-a-valid-id/capture-info")

    assert response.status_code == 404
