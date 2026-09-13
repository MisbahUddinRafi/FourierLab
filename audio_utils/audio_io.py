"""
utils/audio_io.py

Loading uploaded audio files and turning numpy waveforms back into
playable/downloadable audio bytes for Streamlit.
"""

import io

import numpy as np
import librosa
import soundfile as sf


def load_audio(file_like, target_sr: int | None = None, mono: bool = True):
    """
    Load an uploaded audio file into a numpy waveform.

    Parameters
    ----------
    file_like : a file path or file-like object (Streamlit's
                UploadedFile works directly here).
    target_sr : resample to this rate if given; None keeps native rate.
    mono : downmix to a single channel if True.

    Returns
    -------
    y  : 1D float32 array, waveform samples in roughly [-1, 1]
    sr : int, sample rate actually used
    """
    y, sr = librosa.load(file_like, sr=target_sr, mono=mono)
    return y.astype(np.float32), sr


def waveform_to_wav_bytes(y: np.ndarray, sr: int) -> bytes:
    """
    Encode a numpy waveform as in-memory WAV bytes, suitable for
    st.audio(...) playback or a st.download_button(...).
    """
    # Guard against clipping when writing to file: rescale only if needed.
    peak = np.max(np.abs(y)) + 1e-12
    y_safe = y / peak if peak > 1.0 else y

    buffer = io.BytesIO()
    sf.write(buffer, y_safe, sr, format="WAV")
    buffer.seek(0)
    return buffer.read()
