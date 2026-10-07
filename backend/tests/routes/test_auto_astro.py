"""Auto Astro route."""

from __future__ import annotations

import io

import numpy as np


def _upload(client, sample_jpeg: bytes) -> str:
    resp = client.post("/api/upload", files={"file": ("m31.jpg", sample_jpeg, "image/jpeg")})
    return resp.json()["session_id"]


def test_apply_dispatches_processing_and_returns_parameters(client, sample_jpeg: bytes) -> None:
    session_id = _upload(client, sample_jpeg)

    response = client.post(f"/api/auto-astro/{session_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == session_id
    assert body["status"] == "completed"
    assert "job_id" in body
    assert "parameters" in body
    assert body["parameters"]["contrast"] == 1.0


def test_apply_preserves_the_session_geometry(client, sample_jpeg: bytes) -> None:
    """Auto Astro proposes tone / star settings only - it must not reset the
    user's crop back to the full frame."""
    session_id = _upload(client, sample_jpeg)
    client.post(
        f"/api/process/{session_id}",
        json={
            "parameters": {
                "geometry": {"crop_x": 0.25, "crop_y": 0.25, "crop_w": 0.5, "crop_h": 0.5}
            }
        },
    )

    response = client.post(f"/api/auto-astro/{session_id}")

    assert response.status_code == 200
    geometry = response.json()["parameters"]["geometry"]
    assert geometry["crop_w"] == 0.5
    assert geometry["crop_h"] == 0.5


def test_apply_unknown_session_is_404(client) -> None:
    response = client.post("/api/auto-astro/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


def test_apply_malformed_session_id_is_404(client) -> None:
    response = client.post("/api/auto-astro/not-a-valid-id")
    assert response.status_code == 404


def test_apply_preserves_the_session_look(client, sample_jpeg: bytes) -> None:
    """The "Style" look is a final choice - Auto Astro must not drop it."""
    session_id = _upload(client, sample_jpeg)
    client.post(
        f"/api/process/{session_id}",
        json={"parameters": {"look": {"look_id": "soft_glow", "amount": 40}}},
    )

    response = client.post(f"/api/auto-astro/{session_id}")

    assert response.status_code == 200
    assert response.json()["parameters"]["look"] == {"look_id": "soft_glow", "amount": 40}


def _upload_fits_composite(client) -> str:
    """A colour FITS stack: it opens as a composite session (the linear "Stack" step)."""
    from astropy.io import fits

    rng = np.random.default_rng(11)
    h, w = 120, 90
    cube = (10_000 + rng.normal(0, 40, (3, h, w))).astype(np.uint16)
    cube[:, h // 2 - 8 : h // 2 + 8, w // 2 - 8 : w // 2 + 8] += 3_000  # a faint object
    cube[:, 20, 20] = 60_000  # a star
    buffer = io.BytesIO()
    fits.PrimaryHDU(data=cube).writeto(buffer)
    response = client.post(
        "/api/upload",
        files={"file": ("Stacked_NGC.fits", buffer.getvalue(), "application/octet-stream")},
    )
    assert response.json()["is_stack"] is True
    return str(response.json()["session_id"])


def test_apply_keeps_the_stack_step_settings(client) -> None:
    """The "Stack" step is the user's: Auto Astro measures what it renders and
    proposes the edit on top, without resetting it."""
    session_id = _upload_fits_composite(client)
    client.post(
        f"/api/process/{session_id}",
        json={"parameters": {"stack": {"stretch": 0.2, "background_extraction": 40}}},
    )

    response = client.post(f"/api/auto-astro/{session_id}")

    assert response.status_code == 200
    stack = response.json()["parameters"]["stack"]
    assert stack["stretch"] == 0.2
    assert stack["background_extraction"] == 40


def test_apply_never_moves_the_tone_sliders(client, sample_jpeg: bytes) -> None:
    """Contrast / exposure / highlights / shadows stay at their defaults - the
    sky is deepened by a tone curve that cannot clip it."""
    session_id = _upload(client, sample_jpeg)

    parameters = client.post(f"/api/auto-astro/{session_id}").json()["parameters"]

    assert parameters["contrast"] == 1.0
    assert parameters["exposure"] == 0.0
    assert parameters["shadows"] == 0.0
