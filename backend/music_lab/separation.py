import subprocess
import sys
import os
from fastapi import HTTPException

from . import config, jobs


def run_demucs_two_stems(input_path: str, job_id: str) -> tuple[str, str]:
    """
    Run Demucs on input_path, splitting into vocals / no_vocals.
    Returns (vocal_wav_path, instrumental_wav_path) inside Demucs'
    own output tree under config.SEPARATED_DIR.

    Registers the subprocess under job_id so it can be cancelled
    externally via jobs.cancel_job(job_id).
    """
    cmd = [
        sys.executable, "-m", "demucs",
        "--two-stems=vocals",
        "-n", config.DEMUCS_MODEL,
        "-o", config.SEPARATED_DIR,
        input_path,
    ]

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    jobs.register_process(job_id, proc)

    try:
        stdout, stderr = proc.communicate()
    finally:
        jobs.unregister_process(job_id)

    if proc.returncode is None:
        # Shouldn't normally happen after communicate(), but guard anyway.
        raise jobs.JobCancelledError(f"Job {job_id} did not complete cleanly.")

    if proc.returncode < 0:
        # Negative returncode means it was killed by a signal (our cancel path).
        raise jobs.JobCancelledError(f"Job {job_id} was cancelled.")

    if proc.returncode != 0:
        raise HTTPException(
            500,
            f"Demucs failed:\n{stderr[-2000:]}",
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