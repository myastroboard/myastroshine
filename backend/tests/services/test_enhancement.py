"""EnhancementService orchestration (sync mode)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from app.db.models import StackRecord
from app.exceptions import SessionNotFoundError, UnsupportedImageError
from app.models import ProcessingParameters, StackParameters
from app.services.enhancement import EnhancementService
from app.services.image_processing import ImageProcessingService
from app.services.job import JobService
from app.services.session import SessionService
from app.services.storage import StorageService


@pytest.fixture
def enhancement(db_session) -> EnhancementService:
    storage = StorageService()
    return EnhancementService(
        SessionService(db_session, storage),
        storage,
        ImageProcessingService(),
        JobService(db_session),
    )


def test_dispatch_runs_inline_and_completes(
    enhancement: EnhancementService, sample_image: np.ndarray
) -> None:
    """dispatch() writes processed.jpg and returns a completed job."""
    record = enhancement.sessions.create_session(image_path="")
    enhancement.storage.save_original(record.session_id, sample_image)

    response = enhancement.dispatch(record.session_id, ProcessingParameters(contrast=2.0))

    assert response.status == "completed"
    assert response.session_id == record.session_id
    assert response.ws_status_url == f"/ws/processing-status/{response.job_id}"
    processed = enhancement.storage.load_processed(record.session_id)
    assert not np.array_equal(processed, sample_image)


def test_run_tracks_progress_on_the_job(
    enhancement: EnhancementService, sample_image: np.ndarray
) -> None:
    """run() moves the job queued -> processing -> completed at 100%."""
    record = enhancement.sessions.create_session(image_path="")
    enhancement.storage.save_original(record.session_id, sample_image)
    job = enhancement.jobs.create(record.session_id)

    enhancement.run(record.session_id, ProcessingParameters(denoise=20), job.job_id)

    done = enhancement.jobs.get(job.job_id)
    assert done.status == "completed"
    assert done.progress_percent == 100
    assert done.current_step == "done"


def test_dispatch_unknown_session_raises(enhancement: EnhancementService) -> None:
    with pytest.raises(SessionNotFoundError):
        enhancement.dispatch("11111111-1111-1111-1111-111111111111", ProcessingParameters())


def _link_stack(enhancement: EnhancementService, session_id: str, composite: np.ndarray) -> str:
    """Register a StackRecord + composite.npy so the session reads as stack-backed."""
    stack_id = "stk00000-0000-0000-0000-000000000001"
    enhancement.sessions.db.add(
        StackRecord(
            stack_id=stack_id,
            frame_count=5,
            session_id=session_id,
            status="completed",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    enhancement.sessions.db.commit()
    enhancement.storage.save_stack_composite(stack_id, composite)
    return stack_id


def test_run_on_a_stacked_composite_uses_the_linear_pipeline(
    enhancement: EnhancementService, sample_image: np.ndarray
) -> None:
    """A stack-backed session runs apply_parameters on composite.npy, so the
    "Stack" step actually moves the result even with every other param default."""
    record = enhancement.sessions.create_session(image_path="")
    enhancement.storage.save_original(record.session_id, sample_image)
    rng = np.random.default_rng(0)
    composite = rng.random((64, 96, 3)).astype(np.float32) * 0.03 + 0.02
    _link_stack(enhancement, record.session_id, composite)

    subtle = ProcessingParameters(stack=StackParameters(stretch=0.0))
    strong = ProcessingParameters(stack=StackParameters(stretch=1.0))
    enhancement.run(record.session_id, subtle, enhancement.jobs.create(record.session_id).job_id)
    subtle_out = enhancement.storage.load_processed(record.session_id)
    enhancement.run(record.session_id, strong, enhancement.jobs.create(record.session_id).job_id)
    strong_out = enhancement.storage.load_processed(record.session_id)

    assert subtle_out.shape[:2] == composite.shape[:2]  # the composite, not sample_image
    assert float(strong_out.mean()) > float(subtle_out.mean())


def test_run_skips_a_superseded_job(
    enhancement: EnhancementService, sample_image: np.ndarray
) -> None:
    record = enhancement.sessions.create_session(image_path="")
    enhancement.storage.save_original(record.session_id, sample_image)
    job = enhancement.jobs.create(record.session_id)
    enhancement.jobs.update(job.job_id, status="superseded")

    enhancement.run(record.session_id, ProcessingParameters(contrast=2.0), job.job_id)

    assert enhancement.jobs.get(job.job_id).status == "superseded"


def test_run_aborts_when_the_job_is_superseded_mid_pipeline(
    enhancement: EnhancementService, sample_image: np.ndarray, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A newer edit that lands after the pipeline has started still stops this
    job at the next stage boundary - it does not run to completion."""
    record = enhancement.sessions.create_session(image_path="")
    enhancement.storage.save_original(record.session_id, sample_image)
    job = enhancement.jobs.create(record.session_id)

    def supersede_then_step(_image, _params, on_step=None, **_kwargs):  # type: ignore[no-untyped-def]
        enhancement.jobs.update(job.job_id, status="superseded")
        assert on_step is not None
        on_step("contrast", 30)  # must raise back out of run()
        raise AssertionError("pipeline continued past a superseded checkpoint")

    monkeypatch.setattr(enhancement.processing, "apply_parameters", supersede_then_step)

    enhancement.run(record.session_id, ProcessingParameters(contrast=2.0), job.job_id)

    assert enhancement.jobs.get(job.job_id).status == "superseded"  # not completed/failed


def test_run_marks_job_failed_on_missing_image(
    enhancement: EnhancementService,
) -> None:
    """If the original image is gone, the job ends 'failed' and the error raises."""
    record = enhancement.sessions.create_session(image_path="")
    job = enhancement.jobs.create(record.session_id)

    with pytest.raises(UnsupportedImageError):
        enhancement.run(record.session_id, ProcessingParameters(), job.job_id)

    assert enhancement.jobs.get(job.job_id).status == "failed"


def _all_engines_found():
    from app.models.engines import EngineStatus

    ok = EngineStatus(configured=True, found=True, version="9.9.9", known_good=True, detail="ok")
    return {"starnet2": ok, "deepsnr": ok}


def test_starnet2_engine_invokes_the_binary_and_caches_it(
    enhancement: EnhancementService, sample_image: np.ndarray, monkeypatch: pytest.MonkeyPatch
) -> None:
    """star_removal_engine='starnet2' routes the split through the operator binary
    when one is available, streams its progress onto the job, and the second edit
    reuses the cached estimate."""
    from app.services import enhancement as enh_module
    from app.services import external_engine
    from app.utils.app_settings import save_app_settings
    from tests.support import fake_engine_popen

    save_app_settings({"starnet2_path": "/opt/starnet2"})
    monkeypatch.setattr(enh_module, "get_engine_statuses", _all_engines_found)

    invocations: list[list[str]] = []
    monkeypatch.setattr(
        external_engine.subprocess,
        "Popen",
        fake_engine_popen(lines=['{"percent": 50}\n', '{"percent": 100}\n'], record=invocations),
    )

    seen_progress: list[tuple[str, int]] = []
    original_emit = enhancement._emit

    def spy_emit(job_id: str) -> None:
        job = enhancement.jobs.get(job_id)
        seen_progress.append((job.current_step, job.progress_percent))
        original_emit(job_id)

    monkeypatch.setattr(enhancement, "_emit", spy_emit)

    record = enhancement.sessions.create_session(image_path="")
    enhancement.storage.save_original(record.session_id, sample_image)

    params = ProcessingParameters(star_removal=100, star_removal_engine="starnet2")
    enhancement.run(record.session_id, params, enhancement.jobs.create(record.session_id).job_id)
    assert len(invocations) == 1
    assert "--machine-progress" in invocations[0]
    # StarNet2's 0.5 fraction lands mid-band (_STARNET2_PROGRESS_BAND = 20..80).
    assert ("star_removal", 50) in seen_progress
    # The bar never went backwards afterwards.
    assert [p for _, p in seen_progress] == sorted(p for _, p in seen_progress)

    # Same detection inputs, a creative-only change -> cache hit, no new pass.
    enhancement.run(
        record.session_id,
        params.model_copy(update={"contrast": 1.6}),
        enhancement.jobs.create(record.session_id).job_id,
    )
    assert len(invocations) == 1


def test_starnet2_engine_falls_back_to_classical_when_unavailable(
    enhancement: EnhancementService, sample_image: np.ndarray, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services import external_engine

    def must_not_run(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("the external binary must not be called when unavailable")

    monkeypatch.setattr(external_engine.subprocess, "run", must_not_run)
    monkeypatch.setattr(external_engine.subprocess, "Popen", must_not_run)

    record = enhancement.sessions.create_session(image_path="")
    enhancement.storage.save_original(record.session_id, sample_image)
    job = enhancement.jobs.create(record.session_id)

    enhancement.run(
        record.session_id,
        ProcessingParameters(star_removal=80, star_removal_engine="starnet2"),
        job.job_id,
    )

    assert enhancement.jobs.get(job.job_id).status == "completed"


def test_deepsnr_engine_denoises_early_and_drops_the_classical_stage(
    enhancement: EnhancementService, sample_image: np.ndarray, monkeypatch: pytest.MonkeyPatch
) -> None:
    """denoise_engine='deepsnr' runs the binary once (before the tone work), the
    classical bilateral filter does not run, and its progress lands on the bar."""
    from app.services import enhancement as enh_module
    from app.services import external_engine, image_processing
    from app.utils.app_settings import save_app_settings
    from tests.support import fake_engine_popen

    save_app_settings({"deepsnr_path": "/opt/deepsnr"})
    monkeypatch.setattr(enh_module, "get_engine_statuses", _all_engines_found)

    invocations: list[list[str]] = []
    monkeypatch.setattr(
        external_engine.subprocess,
        "Popen",
        fake_engine_popen(lines=['{"percent": 100}\n'], record=invocations),
    )

    def _boom(*_a: object, **_k: object) -> object:
        raise AssertionError("classical apply_denoise must not run when DeepSNR is active")

    monkeypatch.setattr(image_processing.ImageProcessingService, "apply_denoise", _boom)

    steps: list[str] = []
    original_emit = enhancement._emit

    def spy_emit(job_id: str) -> None:
        steps.append(enhancement.jobs.get(job_id).current_step)
        original_emit(job_id)

    monkeypatch.setattr(enhancement, "_emit", spy_emit)

    record = enhancement.sessions.create_session(image_path="")
    enhancement.storage.save_original(record.session_id, sample_image)
    job = enhancement.jobs.create(record.session_id)

    enhancement.run(
        record.session_id,
        ProcessingParameters(denoise=60, denoise_engine="deepsnr"),
        job.job_id,
    )

    assert enhancement.jobs.get(job.job_id).status == "completed"
    assert len(invocations) == 1
    assert "--machine-progress" in invocations[0]
    assert "denoise" in steps  # progress reported it


def test_deepsnr_engine_falls_back_to_classical_when_unavailable(
    enhancement: EnhancementService, sample_image: np.ndarray, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services import external_engine

    def must_not_run(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("the external binary must not be called when unavailable")

    monkeypatch.setattr(external_engine.subprocess, "run", must_not_run)
    monkeypatch.setattr(external_engine.subprocess, "Popen", must_not_run)

    record = enhancement.sessions.create_session(image_path="")
    enhancement.storage.save_original(record.session_id, sample_image)
    job = enhancement.jobs.create(record.session_id)

    enhancement.run(
        record.session_id,
        ProcessingParameters(denoise=50, denoise_engine="deepsnr"),
        job.job_id,
    )

    assert enhancement.jobs.get(job.job_id).status == "completed"
