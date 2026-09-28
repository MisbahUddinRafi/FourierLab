# backend/music-lab/schemas.py

from __future__ import annotations

from typing import Optional, List
from pydantic import BaseModel, Field


# ---------------------------------------------------------------
# Shared building blocks
# ---------------------------------------------------------------

class WaveformData(BaseModel):
    """Downsampled amplitude envelope for a Plotly line/area trace."""
    time: List[float]
    min: List[float]
    max: List[float]
    duration: float
    sr: int


class SpectrogramData(BaseModel):
    """STFT magnitude-in-dB matrix for a Plotly heatmap trace.

    z is row-major: z[freq_index][time_index], matching Plotly's
    heatmap `z` convention when paired with `x=time`, `y=freq`.
    """
    time: List[float]
    freq: List[float]
    z: List[List[float]]
    zmin: float
    zmax: float


class AudioVisualization(BaseModel):
    """Everything the frontend needs to render one stem: player + plots."""
    url: str
    sr: int
    duration: float
    waveform: WaveformData
    spectrogram: SpectrogramData


# ---------------------------------------------------------------
# /music/separate
# ---------------------------------------------------------------

class SeparateResponse(BaseModel):
    job_id: str
    original: AudioVisualization
    vocal: AudioVisualization
    instrumental: AudioVisualization


# ---------------------------------------------------------------
# /music/suggest-offset
# ---------------------------------------------------------------

class SuggestOffsetResponse(BaseModel):
    suggested_offset_sec: float
    confidence: float = Field(
        ..., description="Normalized cross-correlation peak strength, 0-1."
    )


# ---------------------------------------------------------------
# /music/mix
# ---------------------------------------------------------------

class MixRequest(BaseModel):
    """
    Note: actual endpoint takes multipart/form-data (file uploads +
    form fields), not JSON. This model documents/validates the form
    fields once parsed, and is reused by any future JSON-based mix
    endpoint (e.g. mixing two already-uploaded job outputs by id).
    """
    instrumental_gain_db: float = 0.0
    vocal_gain_db: float = 0.0

    instrumental_start: float = 0.0
    instrumental_end: Optional[float] = None

    vocal_start: float = 0.0
    vocal_end: Optional[float] = None

    offset_sec: float = 0.0


class MixResponse(BaseModel):
    job_id: str
    mixed: AudioVisualization


# ---------------------------------------------------------------
# Generic error shape (optional, for consistent `detail` usage)
# ---------------------------------------------------------------

class ErrorResponse(BaseModel):
    detail: str