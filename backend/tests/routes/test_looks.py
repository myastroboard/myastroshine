"""GET /api/looks/{id}/thumbnail - the "Style" gallery thumbnails."""

from __future__ import annotations

import cv2
import numpy as np

#: The groups every session gets, in order (a night landscape adds its own first).
_DEEP_SKY_GROUPS = [
    {"scene": "general", "looks": ["vivid", "soft_glow", "cinematic"]},
    {"scene": "nebula", "looks": ["luminous", "structure"]},
    {"scene": "galaxy", "looks": ["deep_field", "warm_core"]},
    {"scene": "cluster", "looks": ["sparkle", "night_velvet"]},
]


def _upload(client, sample_jpeg: bytes) -> str:
    resp = client.post("/api/upload", files={"file": ("m31.jpg", sample_jpeg, "image/jpeg")})
    return resp.json()["session_id"]


def _decode(data: bytes) -> np.ndarray:
    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    assert image is not None
    return image


def test_thumbnail_before_any_render_uses_the_preview(client, sample_jpeg: bytes) -> None:
    """A fresh upload has no pre-look render yet: the thumbnail comes from its preview."""
    session_id = _upload(client, sample_jpeg)

    plain = client.get(f"/api/looks/{session_id}/thumbnail")
    styled = client.get(f"/api/looks/{session_id}/thumbnail", params={"look": "soft_glow"})

    assert plain.status_code == 200
    assert plain.headers["content-type"] == "image/jpeg"
    assert styled.status_code == 200
    assert not np.array_equal(_decode(plain.content), _decode(styled.content))


def test_thumbnail_uses_the_pre_look_render(client, sample_jpeg: bytes) -> None:
    """After a render with a look, the no-look thumbnail shows the edit without it."""
    session_id = _upload(client, sample_jpeg)
    client.post(f"/api/process/{session_id}", json={"parameters": {"contrast": 1.5}})
    before = _decode(client.get(f"/api/looks/{session_id}/thumbnail").content)

    client.post(
        f"/api/process/{session_id}",
        json={"parameters": {"contrast": 1.5, "look": {"look_id": "vivid", "amount": 90}}},
    )
    after = _decode(client.get(f"/api/looks/{session_id}/thumbnail").content)

    assert np.array_equal(before, after)


def test_thumbnail_amount_zero_is_the_plain_thumbnail(client, sample_jpeg: bytes) -> None:
    session_id = _upload(client, sample_jpeg)
    plain = client.get(f"/api/looks/{session_id}/thumbnail")
    zero = client.get(
        f"/api/looks/{session_id}/thumbnail", params={"look": "cinematic", "amount": 0}
    )
    assert plain.content == zero.content


def test_thumbnail_rejects_an_unknown_look_or_amount(client, sample_jpeg: bytes) -> None:
    session_id = _upload(client, sample_jpeg)
    bad_look = client.get(f"/api/looks/{session_id}/thumbnail", params={"look": "spikes"})
    bad_amount = client.get(
        f"/api/looks/{session_id}/thumbnail", params={"look": "vivid", "amount": 101}
    )
    assert bad_look.status_code == 400
    assert bad_amount.status_code == 400


def test_thumbnail_unknown_session_is_404(client) -> None:
    response = client.get("/api/looks/00000000-0000-0000-0000-000000000000/thumbnail")
    assert response.status_code == 404


def test_thumbnail_invalid_session_id_is_404(client) -> None:
    response = client.get("/api/looks/not-a-session/thumbnail")
    assert response.status_code == 404


def _make_night_landscape(client, db_session, sample_jpeg: bytes) -> str:
    """Upload, then back the session with a composite that has a sky mask (top half)."""
    from datetime import UTC, datetime, timedelta

    from app.db.models import StackRecord
    from app.services.storage import StorageService

    session_id = _upload(client, sample_jpeg)
    storage = StorageService()
    original = storage.load_original(session_id)
    height, width = original.shape[:2]
    stack_id = "night-stack-1"
    db_session.add(
        StackRecord(
            stack_id=stack_id,
            status="completed",
            frame_count=1,
            session_id=session_id,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    db_session.commit()
    storage.save_stack_composite(stack_id, original.astype(np.float32) / 255.0)
    mask = np.zeros((height, width), dtype=np.uint8)
    mask[: height // 2] = 255
    storage.save_stack_sky_mask(stack_id, mask)
    return session_id


def test_catalogue_offers_the_general_looks_for_an_ordinary_image(
    client, sample_jpeg: bytes
) -> None:
    session_id = _upload(client, sample_jpeg)

    response = client.get(f"/api/looks/{session_id}")

    assert response.status_code == 200
    assert response.json() == {"scene": "general", "groups": _DEEP_SKY_GROUPS}


def test_catalogue_puts_the_night_looks_first_for_a_night_landscape(
    client, db_session, sample_jpeg: bytes
) -> None:
    session_id = _make_night_landscape(client, db_session, sample_jpeg)

    response = client.get(f"/api/looks/{session_id}")

    assert response.json() == {
        "scene": "nightscape",
        "groups": [
            {"scene": "nightscape", "looks": ["galactic_core", "blue_hour"]},
            *_DEEP_SKY_GROUPS,
        ],
    }


def test_catalogue_unknown_session_is_404(client) -> None:
    assert client.get("/api/looks/00000000-0000-0000-0000-000000000000").status_code == 404
    assert client.get("/api/looks/not-a-session").status_code == 404


def test_night_landscape_thumbnail_uses_the_sky_mask(
    client, db_session, sample_jpeg: bytes
) -> None:
    """A night-landscape look's thumbnail renders with the session's sky mask."""
    session_id = _make_night_landscape(client, db_session, sample_jpeg)

    plain = client.get(f"/api/looks/{session_id}/thumbnail")
    styled = client.get(
        f"/api/looks/{session_id}/thumbnail", params={"look": "galactic_core", "amount": 100}
    )

    assert styled.status_code == 200
    assert not np.array_equal(_decode(plain.content), _decode(styled.content))
