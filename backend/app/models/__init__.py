"""Pydantic request/response models for the MyAstroShine API."""

from app.models.astrodex import (
    HandoffResumeRequest,
    HandoffResumeResponse,
    HandoffReturnRequest,
    HandoffReturnResponse,
)
from app.models.auth import (
    AdminSessionListResponse,
    AdminSessionOut,
    AuthStatusResponse,
    ChangePasswordRequest,
    LoginRequest,
    SetupRequest,
)
from app.models.auto_astro import AutoAstroResponse
from app.models.config_export import (
    ConfigExportPreset,
    ConfigExportResponse,
    ConfigImportRequest,
    ConfigImportResponse,
)
from app.models.depth_shift import (
    DepthLayerInfo,
    DepthMetadataResponse,
    DepthShiftRequest,
    DepthShiftResponse,
    DepthStatistics,
    FocusPoint,
)
from app.models.engines import (
    EngineStatus,
    EngineStatusResponse,
    InstalledEngineOut,
    InstallEngineRequest,
    StagedEngineResponse,
)
from app.models.image import Dimensions, HistogramData, UploadResponse
from app.models.job import DiskUsageResponse, JobListResponse, JobSummary
from app.models.logs import LogLevels, LogLevelUpdate, LogTailResponse
from app.models.preset import (
    PresetListResponse,
    PresetOut,
    SavePresetRequest,
    SavePresetResponse,
)
from app.models.processing import (
    CurvePoint,
    GeometryParameters,
    LookCatalog,
    LookId,
    LookParameters,
    ProcessingParameters,
    ProcessRequest,
    ProcessResponse,
    StackParameters,
)
from app.models.session import SessionInfo
from app.models.settings import AppSettingsResponse, AppSettingsUpdate
from app.models.stack import (
    CalibrationFrameCounts,
    CalibrationSummary,
    CaptureInfo,
    ExcludeFrameRequest,
    FrameQualityInfo,
    InitiateStackRequest,
    ProcessStackRequest,
    StackFrameInfo,
    StackResultResponse,
    StackSessionResponse,
    StackStatistics,
    UploadFrameResponse,
)
from app.models.star_mask import StarMaskRequest, StarMaskResponse, StarSourceInfo
from app.models.token import (
    CreatedTokenResponse,
    CreateTokenRequest,
    TokenListResponse,
    TokenOut,
)

__all__ = [
    "AdminSessionListResponse",
    "AdminSessionOut",
    "AppSettingsResponse",
    "AppSettingsUpdate",
    "AuthStatusResponse",
    "AutoAstroResponse",
    "CalibrationFrameCounts",
    "CalibrationSummary",
    "CaptureInfo",
    "ChangePasswordRequest",
    "ConfigExportPreset",
    "ConfigExportResponse",
    "ConfigImportRequest",
    "ConfigImportResponse",
    "CreateTokenRequest",
    "CreatedTokenResponse",
    "CurvePoint",
    "DepthLayerInfo",
    "DepthMetadataResponse",
    "DepthShiftRequest",
    "DepthShiftResponse",
    "DepthStatistics",
    "Dimensions",
    "DiskUsageResponse",
    "EngineStatus",
    "EngineStatusResponse",
    "ExcludeFrameRequest",
    "FocusPoint",
    "FrameQualityInfo",
    "GeometryParameters",
    "HandoffResumeRequest",
    "HandoffResumeResponse",
    "HandoffReturnRequest",
    "HandoffReturnResponse",
    "HistogramData",
    "InitiateStackRequest",
    "InstallEngineRequest",
    "InstalledEngineOut",
    "JobListResponse",
    "JobSummary",
    "LogLevelUpdate",
    "LogLevels",
    "LogTailResponse",
    "LoginRequest",
    "LookCatalog",
    "LookId",
    "LookParameters",
    "PresetListResponse",
    "PresetOut",
    "ProcessRequest",
    "ProcessResponse",
    "ProcessStackRequest",
    "ProcessingParameters",
    "SavePresetRequest",
    "SavePresetResponse",
    "SessionInfo",
    "SetupRequest",
    "StackFrameInfo",
    "StackParameters",
    "StackResultResponse",
    "StackSessionResponse",
    "StackStatistics",
    "StagedEngineResponse",
    "StarMaskRequest",
    "StarMaskResponse",
    "StarSourceInfo",
    "TokenListResponse",
    "TokenOut",
    "UploadFrameResponse",
    "UploadResponse",
]
