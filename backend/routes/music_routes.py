# backend/routes/music_routes.py
"""
routes/music_routes.py

Endpoints (mounted under /api by main.py, so final paths are
/api/music/separate, /api/music/suggest-offset, /api/music/mix):

  POST /music/separate         -- {"source": "_uploads/xxx.wav"} ->
                                   vocal + instrumental + original,
                                   each with source/sr/duration/waveform/spectrogram
  POST /music/suggest-offset   -- {"instrumental_source": "...", "vocal_source": "..."} ->
                                   suggested alignment offset in seconds
  POST /music/mix              -- {"instrumental_source": "...", "vocal_source": "...",
                                    "instrumental_gain_db": ..., "vocal_gain_db": ...,
                                    "offset_sec": ..., ...} ->
                                   mixed result

"source" strings are paths relative to ASSETS_AUDIO_DIR, matching the
convention already used by /api/audio/upload (e.g. "_uploads/<uuid>.wav").
This lets the frontend reuse a file it already uploaded (via
/audio/upload) without re-uploading it here, and lets "Use in Mixer"
reference a separated stem's source the same way.
"""

from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from music_lab import config, schemas, audio_ops, separation, alignment, plotting, jobs


router = APIRouter(prefix="/music", tags=["music-lab"])


# ---------------------------------------------------------------
# Request bodies (JSON, source-based -- matches /audio/upload's
# {"source": "..."} convention rather than raw file uploads)
# ---------------------------------------------------------------

class SeparateRequest(BaseModel):
    source: str


class SuggestOffsetRequest(BaseModel):
    instrumental_source: str
    vocal_source: str


class MixRequestBody(BaseModel):
    instrumental_source: str
    vocal_source: str

    instrumental_gain_db: float = 0.0
    vocal_gain_db: float = 0.0

    instrumental_start: float = 0.0
    instrumental_end: Optional[float] = None

    vocal_start: float = 0.0
    vocal_end: Optional[float] = None

    offset_sec: float = 0.0


# ---------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------

def _resolve_source_path(source: str, field_name: str) -> str:
    """
    Resolve a "source" (relative to ASSETS_AUDIO_DIR, e.g.
    "_uploads/xxx.wav" or "_music_lab/jobs/xxx_vocal.wav") into an
    absolute path, guarding against path traversal outside
    ASSETS_AUDIO_DIR.
    """
    if not source:
        raise HTTPException(400, f"Missing '{field_name}'.")

    candidate = os.path.normpath(os.path.join(config.ASSETS_AUDIO_DIR, source))
    assets_root = os.path.normpath(config.ASSETS_AUDIO_DIR)

    if not (candidate == assets_root or candidate.startswith(assets_root + os.sep)):
        raise HTTPException(400, f"Invalid '{field_name}'.")

    if not os.path.exists(candidate):
        raise HTTPException(404, f"'{field_name}' not found: {source}")

    return candidate


def _source_for(path: str) -> str:
    """Inverse of _resolve_source_path: absolute path -> relative source string."""
    rel = os.path.relpath(path, config.ASSETS_AUDIO_DIR)
    return rel.replace(os.sep, "/")


def _build_visualization_dict(y, sr, source: str) -> dict:
    """
    Same as music_lab.plotting.build_audio_visualization, but keyed as
    "source" (relative path) instead of "url" (full URL), matching the
    existing app's convention. The frontend already does
    "/media/audio/" + data.X.source, so we hand back the relative path.
    """
    viz = plotting.build_audio_visualization(y, sr, url="")  # url unused here
    viz["source"] = source
    viz.pop("url", None)
    return viz


# ---------------------------------------------------------------
# POST /music/separate
# ---------------------------------------------------------------

@router.post("/separate")
async def separate(body: SeparateRequest):
    src_path = _resolve_source_path(body.source, "source")

    job_id = jobs.new_job_id()

    try:
        demucs_vocal_path, demucs_instrumental_path = separation.run_demucs_two_stems(
            src_path
        )

        final_vocal_path, final_instrumental_path = jobs.separated_output_paths(job_id)
        jobs.copy_into_jobs_dir(demucs_vocal_path, final_vocal_path)
        jobs.copy_into_jobs_dir(demucs_instrumental_path, final_instrumental_path)

        # Original is already on disk (uploaded via /audio/upload) --
        # no need to re-save it, just load it for visualization and
        # reuse its existing source path.
        y_original, sr_original = audio_ops.load_audio_stereo(src_path)
        y_vocal, sr_vocal = audio_ops.load_audio_stereo(final_vocal_path)
        y_instrumental, sr_instrumental = audio_ops.load_audio_stereo(final_instrumental_path)

        original_viz = _build_visualization_dict(y_original, sr_original, body.source)
        vocal_viz = _build_visualization_dict(
            y_vocal, sr_vocal, _source_for(final_vocal_path)
        )
        instrumental_viz = _build_visualization_dict(
            y_instrumental, sr_instrumental, _source_for(final_instrumental_path)
        )

        return {
            "job_id": job_id,
            "original": original_viz,
            "vocal": vocal_viz,
            "instrumental": instrumental_viz,
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, f"Separation failed: {exc}")


# ---------------------------------------------------------------
# POST /music/suggest-offset
# ---------------------------------------------------------------

@router.post("/suggest-offset", response_model=schemas.SuggestOffsetResponse)
async def suggest_offset(body: SuggestOffsetRequest):
    inst_path = _resolve_source_path(body.instrumental_source, "instrumental_source")
    voc_path = _resolve_source_path(body.vocal_source, "vocal_source")

    y_inst, sr_inst = audio_ops.load_audio_stereo(inst_path)
    y_voc, sr_voc = audio_ops.load_audio_stereo(voc_path)

    offset_sec, confidence = alignment.suggest_offset_sec(y_inst, sr_inst, y_voc, sr_voc)

    return schemas.SuggestOffsetResponse(
        suggested_offset_sec=offset_sec,
        confidence=confidence,
    )


# ---------------------------------------------------------------
# POST /music/mix
# ---------------------------------------------------------------

@router.post("/mix")
async def mix(body: MixRequestBody):
    audio_ops.validate_gain_db(body.instrumental_gain_db, "instrumental_gain_db")
    audio_ops.validate_gain_db(body.vocal_gain_db, "vocal_gain_db")

    inst_path = _resolve_source_path(body.instrumental_source, "instrumental_source")
    voc_path = _resolve_source_path(body.vocal_source, "vocal_source")

    y_inst, sr_inst = audio_ops.load_audio_stereo(inst_path)
    y_voc, sr_voc = audio_ops.load_audio_stereo(voc_path)

    target_sr = sr_inst
    y_voc = audio_ops.resample_stereo(y_voc, sr_voc, target_sr)

    y_inst = audio_ops.trim(y_inst, target_sr, body.instrumental_start, body.instrumental_end)
    y_voc = audio_ops.trim(y_voc, target_sr, body.vocal_start, body.vocal_end)

    mixed = audio_ops.mix_stereo(
        y_inst, y_voc, target_sr,
        instrumental_gain_db=body.instrumental_gain_db,
        vocal_gain_db=body.vocal_gain_db,
        offset_sec=body.offset_sec,
    )

    job_id = jobs.new_job_id()
    out_path = jobs.mixed_output_path(job_id)
    audio_ops.save_wav(mixed, target_sr, out_path)

    mixed_viz = _build_visualization_dict(mixed, target_sr, _source_for(out_path))

    return {"job_id": job_id, "mixed": mixed_viz}