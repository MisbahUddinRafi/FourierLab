# backend/music-lab/config.py

import os

# backend/music-lab/
MUSIC_LAB_DIR = os.path.dirname(os.path.abspath(__file__))

# backend/
BACKEND_DIR = os.path.dirname(MUSIC_LAB_DIR)

# Reuse the shared assets/audio tree that already exists in the project,
# rather than inventing a new uploads/outputs layout.
ASSETS_AUDIO_DIR = os.path.join(BACKEND_DIR, "assets", "audio")

UPLOAD_DIR = os.path.join(ASSETS_AUDIO_DIR, "_uploads")
SAVED_DIR = os.path.join(ASSETS_AUDIO_DIR, "saved")
SAMPLES_DIR = os.path.join(ASSETS_AUDIO_DIR, "samples")

# Music-lab-specific working directories, kept separate from _uploads/saved
# so separated stems / mixes don't collide with audio-lab's files.
MUSIC_LAB_ASSETS_DIR = os.path.join(ASSETS_AUDIO_DIR, "_music_lab")
SEPARATED_DIR = os.path.join(MUSIC_LAB_ASSETS_DIR, "separated")
MIXED_DIR = os.path.join(MUSIC_LAB_ASSETS_DIR, "mixed")
JOBS_DIR = os.path.join(MUSIC_LAB_ASSETS_DIR, "jobs")

for _d in (UPLOAD_DIR, SAVED_DIR, SAMPLES_DIR, SEPARATED_DIR, MIXED_DIR, JOBS_DIR):
    os.makedirs(_d, exist_ok=True)

# Public URL prefix these files are served under. Must match wherever
# main.py mounts StaticFiles for ASSETS_AUDIO_DIR, e.g.:
#   app.mount("/files/audio", StaticFiles(directory=ASSETS_AUDIO_DIR), name="audio_files")
FILES_URL_PREFIX = "/files/audio"

ALLOWED_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".mp4"}
MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # 200 MB safety cap

DEMUCS_MODEL = "htdemucs"

# Stereo throughout. Everything gets coerced to this many channels.
TARGET_CHANNELS = 2

# STFT params for spectrogram JSON generation (matches stft_engine.py defaults)
SPECTROGRAM_N_FFT = 2048
SPECTROGRAM_HOP_LENGTH = 512
SPECTROGRAM_WIN_LENGTH = 2048
SPECTROGRAM_TOP_DB = 80.0

# How many points to send to the frontend for waveform plots. Plotly gets
# slow/unresponsive with raw sample-rate data on long tracks, so we downsample
# using min/max envelope per bucket (keeps transients visible).
WAVEFORM_DOWNSAMPLE_POINTS = 4000

# Cap on spectrogram time-frames sent to the frontend (downsampled similarly
# if exceeded) to keep the JSON payload and Plotly heatmap responsive.
SPECTROGRAM_MAX_FRAMES = 1500

# Gain slider range on the frontend (dB), used for server-side validation
GAIN_DB_MIN = -24.0
GAIN_DB_MAX = 12.0