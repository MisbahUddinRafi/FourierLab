# backend/music-lab/jobs.py
"""
music-lab/jobs.py

Tracks per-request working files on disk under predictable, job_id-based
names so:
  - Demucs' nested output tree gets normalized into flat, servable files
  - the "Use in Mixer" button can reference a Separate-tab result by
    URL/job_id without re-uploading
  - route handlers stay thin (no manual path-building inline)

Nothing here is a database -- it's just consistent file naming/copying
on top of the directories defined in config.py. Good enough for a
single-user lab tool; swap for real persistence later if needed.
"""

from __future__ import annotations

import os
import shutil
import uuid
import threading

from . import config


def new_job_id() -> str:
    return uuid.uuid4().hex


def upload_path_for(job_id: str, tag: str, original_filename: str) -> str:
    """e.g. UPLOAD_DIR/<job_id>_<tag>_<original_filename>"""
    safe_name = os.path.basename(original_filename)
    return os.path.join(config.UPLOAD_DIR, f"{job_id}_{tag}_{safe_name}")


def separated_output_paths(job_id: str) -> tuple[str, str]:
    """Final, flat, servable paths for a separation job's stems."""
    vocal_path = os.path.join(config.JOBS_DIR, f"{job_id}_vocal.wav")
    instrumental_path = os.path.join(config.JOBS_DIR, f"{job_id}_instrumental.wav")
    return vocal_path, instrumental_path


def original_copy_path(job_id: str, ext: str = ".wav") -> str:
    """Where the (re-encoded) original upload is kept for the
    Separate tab's 'Original' waveform/spectrogram/player block."""
    return os.path.join(config.JOBS_DIR, f"{job_id}_original{ext}")


def mixed_output_path(job_id: str) -> str:
    return os.path.join(config.JOBS_DIR, f"{job_id}_mixed.wav")


def url_for(path: str) -> str:
    """
    Build the public URL for a file living under config.ASSETS_AUDIO_DIR,
    matching the StaticFiles mount at config.FILES_URL_PREFIX.
    """
    rel = os.path.relpath(path, config.ASSETS_AUDIO_DIR)
    rel = rel.replace(os.sep, "/")
    return f"{config.FILES_URL_PREFIX}/{rel}"


def cleanup_paths(*paths: str) -> None:
    for p in paths:
        try:
            if p and os.path.exists(p):
                os.remove(p)
        except OSError:
            pass


def copy_into_jobs_dir(src_path: str, dest_path: str) -> None:
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    shutil.copy(src_path, dest_path)






# job_id -> subprocess.Popen handle for any currently-running Demucs job
_running_processes: dict[str, subprocess.Popen] = {}
_processes_lock = threading.Lock()


def register_process(job_id: str, proc: subprocess.Popen) -> None:
    with _processes_lock:
        _running_processes[job_id] = proc


def unregister_process(job_id: str) -> None:
    with _processes_lock:
        _running_processes.pop(job_id, None)


def cancel_job(job_id: str) -> bool:
    """Returns True if a running process was found and terminated."""
    with _processes_lock:
        proc = _running_processes.get(job_id)

    if proc is None:
        return False

    if proc.poll() is None:  # still running
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()

    unregister_process(job_id)
    return True


class JobCancelledError(Exception):
    pass