"""
Fourier_Lab.py

FourierLab -- homepage / entry point for the merged multipage app.
This file's name (with the underscore) is what makes Streamlit show
"Fourier Lab" as the first item in the sidebar navigation, with the
Audio Lab and Image Lab pages listed below it (see pages/).

Run the whole app with:

    streamlit run Fourier_Lab.py
"""

import streamlit as st

st.set_page_config(
    page_title="FourierLab",
    page_icon="🌊",
    layout="wide",
)

st.title("🌊 FourierLab")
st.subheader("Exploring Frequency-Domain Information Through MRI and Audio Signals")

st.markdown(
    """
    FourierLab studies one question using two different kinds of signals:
    **what does the frequency-domain representation of a signal actually
    contain, and what happens when we remove, isolate, or alter parts of it?**

    The same set of operations -- region masking, magnitude/phase
    separation, and progressive retention -- is applied to an **MRI image**
    through its **k-space** (2D spatial frequency) and to an **audio clip**
    through its **STFT** (time-frequency), so the two labs below demonstrate
    one consistent set of signal-processing concepts across image and audio,
    spatial and time domains.
    """
)

st.divider()

col1, col2 = st.columns(2)

with col1:
    st.markdown("### 🧠 Image Lab")
    st.write(
        "MRI k-space visualization, center/outer/custom frequency-domain "
        "masking, magnitude vs. phase analysis, progressive reconstruction, "
        "and MSE / PSNR / SSIM quality metrics."
    )
    try:
        st.page_link("pages/2_Image_Lab.py", label="Open Image Lab", icon="🧠")
    except Exception:
        st.info("Use the **Image Lab** link in the sidebar to open this module.")

with col2:
    st.markdown("### 🎧 Audio Lab")
    st.write(
        "STFT spectrogram visualization, time-frequency masking, "
        "magnitude vs. phase analysis, progressive reconstruction, and "
        "SNR-based quality metrics."
    )
    try:
        st.page_link("pages/1_Audio_Lab.py", label="Open Audio Lab", icon="🎧")
    except Exception:
        st.info("Use the **Audio Lab** link in the sidebar to open this module.")

st.divider()

st.markdown("### How the two labs mirror each other")

st.markdown(
    """
| | Image Lab (MRI k-space) | Audio Lab (STFT) |
|---|---|---|
| Frequency-domain data | 2D k-space | 2D spectrogram (freq x time) |
| "Low-frequency" region | k-space center | low-frequency band |
| Masking | center / outer / custom region | time-frequency rectangle |
| Progressive retention | center-radius or top-magnitude | low-frequency or top-magnitude |
| Magnitude carries | mostly contrast | mostly loudness |
| Phase carries | **mostly structure** (surprising!) | mostly timing (much less audible) |
| Quality metrics | MSE, PSNR, SSIM | SNR, MSE, spectral convergence |
    """
)

st.caption(
    "Tip: both labs let you pick a bundled sample or a previously saved "
    "result from the sidebar, in addition to uploading your own file."
)
