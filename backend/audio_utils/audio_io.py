"""
utils/audio_io.py

Loading uploaded audio files and turning numpy waveforms back into
playable/downloadable audio bytes.
"""

import io

import numpy as np
import librosa
import soundfile as sf


def load_audio(file_like, target_sr: int | None = None, mono: bool = True):
    y, sr = librosa.load(file_like, sr=target_sr, mono=mono)
    return y.astype(np.float32), sr


def waveform_to_wav_bytes(y: np.ndarray, sr: int) -> bytes:
    peak = np.max(np.abs(y)) + 1e-12
    y_safe = y / peak if peak > 1.0 else y

    buffer = io.BytesIO()
    sf.write(buffer, y_safe, sr, format="WAV")
    buffer.seek(0)
    return buffer.read()