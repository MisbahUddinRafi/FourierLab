# backend/music-lab/separation.py
"""
music-lab/separation.py

Demucs stem separation, run as a subprocess via its CLI (same approach
as the standalone demo). Two-stem split: vocals vs everything else.
"""

from __future__ import annotations

import os
import subprocess
import sys

from fastapi import HTTPException

from . import config


def run_demucs_two_stems(input_path: str) -> tuple[str, str]:
    """
    Run Demucs on input_path, splitting into vocals / no_vocals.
    Returns (vocal_wav_path, instrumental_wav_path) inside Demucs'
    own output tree under config.SEPARATED_DIR.
    """
    cmd = [
        sys.executable, "-m", "demucs",
        "--two-stems=vocals",
        "-n", config.DEMUCS_MODEL,
        "-o", config.SEPARATED_DIR,
        input_path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise HTTPException(
            500,
            f"Demucs failed:\n{result.stderr[-2000:]}",
        )

    stem_name = os.path.splitext(os.path.basename(input_path))[0]
    model_dir = os.path.join(config.SEPARATED_DIR, config.DEMUCS_MODEL, stem_name)

    vocal_path = os.path.join(model_dir, "vocals.wav")
    instrumental_path = os.path.join(model_dir, "no_vocals.wav")

    if not os.path.exists(vocal_path) or not os.path.exists(instrumental_path):
        raise HTTPException(
            500,
            "Demucs did not produce the expected output files.",
        )

    return vocal_path, instrumental_path