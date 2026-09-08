"""Stacking routes: initiate -> upload -> process -> get."""

from __future__ import annotations

import io
import zipfile

import numpy as np

from tests.support import png_bytes, translate


def test_full_stack_workflow(client, star_field: np.ndarray) -> None:
    """initiate, upload 3 frames, process, then read the result back."""
    init = client.post(
        "/api/stack/initiate",
        json={"frame_count": 3, "combination_method": "median"},
    )
    assert init.status_code == 202
    stack_id = init.json()["stack_id"]

    status = ""
    for i in range(3):
        frame = png_bytes(translate(star_field, i, -i))
        up = client.post(
            f"/api/stack/{stack_id}/upload-frame",
            data={"frame_index": str(i)},
            files={"file": (f"f{i}.png", frame, "image/png")},
        )
        assert up.status_code == 202
        status = up.json()["status"]
    assert status == "ready"

    processed = client.post(f"/api/stack/{stack_id}/process")
    assert processed.status_code == 200
    body = processed.json()
    assert body["status"] == "completed"
    assert body["session_id"]
    assert body["statistics"]["frames_stacked"] == 3

    # the composite is a real session, enhanceable and previewable
    assert client.get(body["stacked_image_url"].replace("?full=true", "")).status_code == 200

    fetched = client.get(f"/api/stack/{stack_id}")
    assert fetched.json()["status"] == "completed"


def test_upload_frames_batch_indexes_from_start_index(client, star_field: np.ndarray) -> None:
    """A batch of frames goes in one request, indexed start_index upward."""
    init = client.post("/api/stack/initiate", json={"frame_count": 4})
    stack_id = init.json()["stack_id"]

    files = [
        ("files", (f"f{i}.png", png_bytes(translate(star_field, i, -i)), "image/png"))
        for i in range(4)
    ]
    r1 = client.post(
        f"/api/stack/{stack_id}/upload-frames", data={"start_index": "0"}, files=files[:2]
    )
    assert r1.status_code == 202
    assert r1.json()["received_frames"] == 2

    r2 = client.post(
        f"/api/stack/{stack_id}/upload-frames", data={"start_index": "2"}, files=files[2:]
    )
    assert r2.json()["received_frames"] == 4
    assert r2.json()["status"] == "ready"

    processed = client.post(f"/api/stack/{stack_id}/process").json()
    assert processed["statistics"]["frames_stacked"] == 4


def test_upload_archive_ingests_every_image_member(client, star_field: np.ndarray) -> None:
    """A .zip of frames is one request; members are assigned indices in filename order."""
    init = client.post("/api/stack/initiate", json={"frame_count": 3})
    stack_id = init.json()["stack_id"]

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("readme.txt", "ignored")
        for i in range(3):
            archive.writestr(f"frame_{i}.png", png_bytes(translate(star_field, i, -i)))

    response = client.post(
        f"/api/stack/{stack_id}/upload-archive",
        files={"file": ("frames.zip", buffer.getvalue(), "application/zip")},
    )

    assert response.status_code == 202
    assert response.json()["received_frames"] == 3
    assert response.json()["status"] == "ready"

    processed = client.post(f"/api/stack/{stack_id}/process").json()
    assert processed["statistics"]["frames_stacked"] == 3


def test_exclude_frame_drops_it_from_the_composite(client, star_field: np.ndarray) -> None:
    init = client.post("/api/stack/initiate", json={"frame_count": 3})
    stack_id = init.json()["stack_id"]
    for i in range(3):
        client.post(
            f"/api/stack/{stack_id}/upload-frame",
            data={"frame_index": str(i)},
            files={"file": (f"f{i}.png", png_bytes(translate(star_field, i, -i)), "image/png")},
        )

    excluded = client.post(f"/api/stack/{stack_id}/frame/1/exclude", json={"excluded": True})
    assert excluded.status_code == 200
    assert excluded.json() == {
        "index": 1,
        "thumb_url": f"/api/stack/{stack_id}/frame/1/thumb",
        "excluded": True,
    }

    listing = client.get(f"/api/stack/{stack_id}").json()
    assert [f["excluded"] for f in listing["frames"]] == [False, True, False]

    processed = client.post(f"/api/stack/{stack_id}/process").json()
    assert processed["statistics"]["frames_stacked"] == 2
    assert processed["statistics"]["frames_excluded"] == 1


def test_frame_thumbnail_is_served(client, star_field: np.ndarray) -> None:
    init = client.post("/api/stack/initiate", json={"frame_count": 2})
    stack_id = init.json()["stack_id"]
    client.post(
        f"/api/stack/{stack_id}/upload-frame",
        data={"frame_index": "0"},
        files={"file": ("f0.png", png_bytes(star_field), "image/png")},
    )

    thumb = client.get(f"/api/stack/{stack_id}/frame/0/thumb")
    assert thumb.status_code == 200
    assert thumb.headers["content-type"] == "image/jpeg"
    assert client.get(f"/api/stack/{stack_id}/frame/9/thumb").status_code == 404


def test_process_can_re_stack_with_a_changed_setting(client, star_field: np.ndarray) -> None:
    """A body on /process re-stacks with a new combination method, no re-upload."""
    init = client.post(
        "/api/stack/initiate", json={"frame_count": 3, "combination_method": "average"}
    )
    stack_id = init.json()["stack_id"]
    for i in range(3):
        client.post(
            f"/api/stack/{stack_id}/upload-frame",
            data={"frame_index": str(i)},
            files={"file": (f"f{i}.png", png_bytes(translate(star_field, i, -i)), "image/png")},
        )

    first = client.post(f"/api/stack/{stack_id}/process").json()
    assert first["statistics"]["combination_method"] == "average"

    second = client.post(
        f"/api/stack/{stack_id}/process", json={"combination_method": "median"}
    ).json()
    assert second["status"] == "completed"
    assert second["statistics"]["combination_method"] == "median"


def test_calibration_frames_upload_clear_and_report(client, star_field: np.ndarray) -> None:
    """Dark/flat subs upload in a batch, show in the stack, and clear on request."""
    init = client.post("/api/stack/initiate", json={"frame_count": 3})
    stack_id = init.json()["stack_id"]

    upload = client.post(
        f"/api/stack/{stack_id}/calibration/dark/frames",
        files=[
            ("files", (f"d{i}.png", png_bytes(star_field), "image/png")) for i in range(3)
        ],
    )
    assert upload.status_code == 202
    assert upload.json()["frames"]["dark"] == 3

    listing = client.get(f"/api/stack/{stack_id}").json()
    assert listing["calibration"]["frames"] == {"dark": 3, "flat": 0, "bias": 0, "dark_flat": 0}
    assert listing["calibration"]["cosmetic_correction"] is True

    cleared = client.delete(f"/api/stack/{stack_id}/calibration/dark")
    assert cleared.status_code == 200
    assert cleared.json()["frames"]["dark"] == 0


def test_calibration_unknown_kind_is_rejected(client) -> None:
    init = client.post("/api/stack/initiate", json={"frame_count": 2})
    stack_id = init.json()["stack_id"]
    response = client.post(
        f"/api/stack/{stack_id}/calibration/sky/frames",
        files=[("files", ("s.png", b"x", "image/png"))],
    )
    assert response.status_code == 400


def test_process_with_calibration_marks_the_result_calibrated(
    client, star_field: np.ndarray
) -> None:
    init = client.post("/api/stack/initiate", json={"frame_count": 3})
    stack_id = init.json()["stack_id"]
    for i in range(3):
        client.post(
            f"/api/stack/{stack_id}/upload-frame",
            data={"frame_index": str(i)},
            files={"file": (f"f{i}.png", png_bytes(translate(star_field, i, -i)), "image/png")},
        )
    client.post(
        f"/api/stack/{stack_id}/calibration/bias/frames",
        files=[("files", (f"b{i}.png", png_bytes(star_field // 8), "image/png")) for i in range(3)],
    )

    processed = client.post(f"/api/stack/{stack_id}/process").json()
    assert processed["status"] == "completed"
    assert processed["statistics"]["calibrated"] is True


def test_initiate_rejects_too_few_frames(client) -> None:
    assert client.post("/api/stack/initiate", json={"frame_count": 1}).status_code == 400


def test_upload_frame_unknown_stack_is_404(client, star_field: np.ndarray) -> None:
    response = client.post(
        "/api/stack/nope/upload-frame",
        data={"frame_index": "0"},
        files={"file": ("f.png", png_bytes(star_field), "image/png")},
    )
    assert response.status_code == 404


def test_get_unknown_stack_is_404(client) -> None:
    assert client.get("/api/stack/nope").status_code == 404
