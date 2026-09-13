"""
app.py

FourierLab -- MRI k-Space Module
Streamlit front-end tying together core/ (DSP logic) and utils/ (I/O +
plotting). Run with:

    streamlit run app.py
"""

from datetime import datetime
from pathlib import Path

import numpy as np
import streamlit as st

from mri_core.kspace_engine import (
    fft2_centered,
    ifft2_centered,
    magnitude_phase,
    combine_magnitude_phase,
    kspace_log_magnitude,
    create_complex_image,
)
from mri_core.masking import build_kspace_mask, apply_mask
from mri_core.reconstruction import (
    retain_center_fraction,
    retain_top_magnitude,
    retention_sweep,
)
from mri_core.metrics import mse_metric, psnr_metric, ssim_metric, error_heatmap

from mri_utils.image_io import (
    load_uploaded_image,
    create_phantom,
    normalize_image,
    image_to_png_bytes,
)
from mri_utils.plotting import (
    plot_kspace_magnitude,
    plot_phase_map,
    plot_error_heatmap,
    plot_ssim_map,
    plot_mask_overlay,
    plot_retention_curve,
)


# ============================================================
# PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="FourierLab - MRI k-Space Lab",
    page_icon="🧠",
    layout="wide",
)

st.title("FourierLab: MRI k-Space Reconstruction Lab")

st.markdown(
    """
    **Explore MRI image formation through k-space acquisition.**

    An MRI scanner doesn't photograph the body -- it measures **k-space**,
    the 2D Fourier transform of the image, one region at a time. This lab
    treats k-space as acquired measurement data: you choose what fraction
    of it to "acquire", and watch how that choice shapes the reconstructed
    image.
    """
)


# ============================================================
# SAMPLE / SAVED-RESULT GALLERY FOLDERS
# ============================================================

APP_ROOT = Path(__file__).resolve().parent.parent
IMAGE_SAMPLES_DIR = APP_ROOT / "assets" / "images" / "samples"
IMAGE_SAVED_DIR = APP_ROOT / "assets" / "images" / "saved"
IMAGE_SAVED_DIR.mkdir(parents=True, exist_ok=True)


def save_image_result(image_array: np.ndarray, label: str) -> Path:
    """Write a reconstructed image into the saved-results gallery folder."""
    filename = f"{label}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    path = IMAGE_SAVED_DIR / filename
    with open(path, "wb") as f:
        f.write(image_to_png_bytes(image_array))
    return path


# ============================================================
# SIDEBAR -- GLOBAL CONTROLS
# ============================================================

st.sidebar.header("Input & Acquisition Settings")

input_mode = st.sidebar.radio(
    "Input source",
    ["Synthetic MRI phantom", "Use a sample / saved result", "Upload an image"],
)

image_size = st.sidebar.select_slider(
    "Simulation resolution",
    options=[128, 160, 192, 256],
    value=160,
    help="Higher resolution looks sharper but makes every recomputation slower.",
)

uploaded_file = None
gallery_choice = None

if input_mode == "Upload an image":
    uploaded_file = st.sidebar.file_uploader("MRI-like image", type=["png", "jpg", "jpeg"])
elif input_mode == "Use a sample / saved result":
    # Samples and previously-saved reconstructions both show up here, so
    # users can chain experiments (e.g. re-mask something they saved earlier).
    gallery_files = sorted(IMAGE_SAMPLES_DIR.glob("*.png")) + sorted(IMAGE_SAVED_DIR.glob("*.png"))
    if not gallery_files:
        st.sidebar.warning("No sample/saved images found. Add .png files to assets/images/samples/.")
    else:
        gallery_choice = st.sidebar.selectbox(
            "Choose an image",
            gallery_files,
            format_func=lambda p: f"{p.stem}  ({'sample' if p.parent.name == 'samples' else 'saved'})",
        )

st.sidebar.subheader("Synthetic Phase")

phase_strength = st.sidebar.slider(
    "Phase strength",
    min_value=0.0,
    max_value=2.0,
    value=0.6,
    step=0.05,
    help=(
        "A real grayscale image has almost no interesting phase "
        "(it's either 0 or pi). This adds a smooth synthetic spatial "
        "phase so the Magnitude vs. Phase tab has something to show."
    ),
)


# ============================================================
# LOAD INPUT IMAGE
# ============================================================

if input_mode == "Upload an image":
    if uploaded_file is None:
        st.info("Upload an image from the sidebar, or switch source.")
        st.stop()
    magnitude_image = load_uploaded_image(uploaded_file, image_size)
elif input_mode == "Use a sample / saved result":
    if gallery_choice is None:
        st.info("No samples available yet -- add files to assets/images/samples/, or switch source.")
        st.stop()
    magnitude_image = load_uploaded_image(str(gallery_choice), image_size)
else:
    magnitude_image = create_phantom(image_size)


# ============================================================
# FORWARD MODEL: IMAGE -> COMPLEX IMAGE -> FULL K-SPACE
# ============================================================

complex_image, phase_map = create_complex_image(magnitude_image, phase_strength)
full_kspace = fft2_centered(complex_image)
full_kspace_log_mag = kspace_log_magnitude(full_kspace)


# ============================================================
# TABS
# ============================================================

tabs = st.tabs(
    [
        "Overview",
        "k-Space Analysis",
        "Frequency-Domain Masking",
        "Progressive Reconstruction",
        "Metrics",
    ]
)


# ------------------------------------------------------------
# TAB 1 -- OVERVIEW
# ------------------------------------------------------------

with tabs[0]:

    st.header("Image Formation Pipeline")

    st.markdown(
        "**Image -> Fourier Transform -> k-Space -> (partial) Acquisition -> Reconstruction -> Image**"
    )

    col1, col2, col3 = st.columns(3)

    with col1:
        st.image(magnitude_image, caption="Input Image", clamp=True, use_container_width=True)

    with col2:
        st.pyplot(plot_kspace_magnitude(full_kspace_log_mag, "Full k-Space (log magnitude)"), use_container_width=True)

    with col3:
        sanity_recon = normalize_image(np.abs(ifft2_centered(full_kspace)))
        st.image(sanity_recon, caption="Reconstruction from Full k-Space", clamp=True, use_container_width=True)

    st.info(
        """
        With **100% of k-space acquired**, reconstruction is essentially
        exact (up to floating-point rounding) -- this is the sanity check
        that every other tab's undersampling experiments are compared
        against. The center of k-space carries low spatial frequencies
        (overall contrast and shape); the outer region carries high
        spatial frequencies (edges and fine detail).
        """
    )


# ------------------------------------------------------------
# TAB 2 -- K-SPACE ANALYSIS (magnitude vs phase)
# ------------------------------------------------------------

with tabs[1]:

    st.header("Magnitude vs. Phase")

    st.markdown(
        r"""
        Every k-space sample is complex: $K(u,v) = |K(u,v)|\,e^{j\phi(u,v)}$.
        Try raising **Phase strength** in the sidebar to 0 and back up --
        watch how much the reconstruction changes even though the
        *magnitude* spectrum never does.
        """
    )

    col1, col2 = st.columns(2)
    with col1:
        st.pyplot(plot_kspace_magnitude(full_kspace_log_mag, "k-Space Magnitude"), use_container_width=True)
    with col2:
        kspace_phase = np.angle(full_kspace)
        st.pyplot(plot_phase_map(kspace_phase, "k-Space Phase"), use_container_width=True)

    st.subheader("Reconstruct from magnitude-only vs. phase-only")

    st.caption(
        "Magnitude-only sets every phase to zero. Phase-only flattens "
        "every magnitude to a constant. Neither is a physically real "
        "acquisition -- this isolates which component actually carries "
        "the image's structure."
    )

    magnitude, phase = magnitude_phase(full_kspace)
    magnitude_only_kspace = combine_magnitude_phase(magnitude, np.zeros_like(phase))
    phase_only_kspace = combine_magnitude_phase(np.ones_like(magnitude), phase)

    magnitude_only_img = normalize_image(np.abs(ifft2_centered(magnitude_only_kspace)))
    phase_only_img = normalize_image(np.abs(ifft2_centered(phase_only_kspace)))

    col1, col2 = st.columns(2)
    with col1:
        st.image(magnitude_only_img, caption="Magnitude-only reconstruction", clamp=True, use_container_width=True)
    with col2:
        st.image(phase_only_img, caption="Phase-only reconstruction", clamp=True, use_container_width=True)

    st.warning(
        """
        **Notice which one still looks like the original.** For natural
        images (unlike audio), *phase* carries most of the recognizable
        structure -- magnitude-only reconstructions tend to look like
        washed-out noise, while phase-only reconstructions, even with
        completely flattened magnitude, often still show recognizable
        edges and shapes. This is a well-known and counter-intuitive
        result in image processing, and the opposite of what holds for
        the audio module.
        """
    )


# ------------------------------------------------------------
# TAB 3 -- FREQUENCY-DOMAIN MASKING
# ------------------------------------------------------------

with tabs[2]:

    st.header("Frequency-Domain Masking")

    st.markdown(
        "Choose a region of k-space and either **isolate** it (keep only "
        "that region) or **remove** it (zero it out, keep everything else)."
    )

    mask_type = st.selectbox("Region type", ["center", "outer", "custom"], format_func=str.title)

    mask_mode = st.radio(
        "Mode",
        ["isolate", "remove"],
        horizontal=True,
        help="'isolate' keeps only the selected region; 'remove' zeroes out the selected region.",
    )

    radius, kx_range, ky_range = 0.2, (-1.0, 1.0), (-1.0, 1.0)

    if mask_type in ("center", "outer"):
        radius = st.slider(
            "Region radius (normalized, 0 = center only, ~1.4 = full k-space)",
            min_value=0.05,
            max_value=1.0,
            value=0.25,
            step=0.01,
        )
    else:
        col1, col2 = st.columns(2)
        with col1:
            kx_range = st.slider("kx range", -1.4, 1.4, (-0.4, 0.4), step=0.05)
        with col2:
            ky_range = st.slider("ky range", -1.4, 1.4, (-0.4, 0.4), step=0.05)

    keep_mask = build_kspace_mask(
        full_kspace.shape, mask_type, mask_mode,
        radius=radius, kx_range=kx_range, ky_range=ky_range,
    )

    masked_kspace = apply_mask(full_kspace, keep_mask)
    masked_recon = normalize_image(np.abs(ifft2_centered(masked_kspace)))
    retained_pct = 100 * keep_mask.mean()

    st.pyplot(
        plot_mask_overlay(full_kspace_log_mag, keep_mask, title=f"{mask_type.title()} region, {mask_mode} ({retained_pct:.1f}% retained)"),
        use_container_width=True,
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        st.image(magnitude_image, caption="Original", clamp=True, use_container_width=True)
    with col2:
        st.image(masked_recon, caption="Masked Reconstruction", clamp=True, use_container_width=True)
    with col3:
        err_map = error_heatmap(magnitude_image, masked_recon)
        st.pyplot(plot_error_heatmap(err_map, "Absolute Error"), use_container_width=True)

    m_psnr = psnr_metric(magnitude_image, masked_recon)
    m_ssim, _ = ssim_metric(magnitude_image, masked_recon)

    col1, col2, col3 = st.columns(3)
    col1.metric("k-Space Retained", f"{retained_pct:.1f}%")
    col2.metric("PSNR", f"{m_psnr:.2f} dB" if np.isfinite(m_psnr) else "∞")
    col3.metric("SSIM", f"{m_ssim:.4f}")

    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "⬇️ Download masked reconstruction (PNG)",
            data=image_to_png_bytes(masked_recon),
            file_name="mri_masked_reconstruction.png",
            mime="image/png",
        )
    with col2:
        if st.button("💾 Save to gallery", key="save_masked_image"):
            saved_path = save_image_result(masked_recon, f"masked_{mask_type}_{mask_mode}")
            st.success(f"Saved to assets/images/saved/{saved_path.name}")

    if mask_type == "center":
        st.info("Isolating the center: overall contrast/shape survives, fine detail is lost (blurry). Removing the center: contrast collapses even though fine detail remains.")
    elif mask_type == "outer":
        st.info("Isolating the outer region: only edges/fine detail remain, contrast is largely gone. Removing the outer region: this is the classic low-pass blur.")
    else:
        st.info("Custom rectangular regions let you probe anisotropic effects -- e.g. removing a horizontal band affects vertical edges differently than horizontal ones.")


# ------------------------------------------------------------
# TAB 4 -- PROGRESSIVE RECONSTRUCTION
# ------------------------------------------------------------

with tabs[3]:

    st.header("Progressive Reconstruction")

    st.markdown(
        "Simulate acquiring only a fraction of k-space and reconstructing "
        "from it -- the central undersampled-MRI experiment."
    )

    strategy = st.selectbox(
        "Retention strategy",
        ["center_radius", "top_magnitude"],
        format_func=lambda s: {
            "center_radius": "Center-radius retention (undersampled acquisition)",
            "top_magnitude": "Top-magnitude retention (data-driven / compressive)",
        }[s],
    )

    keep_fraction = st.slider("Fraction of k-space retained", 0.01, 1.0, 0.25, step=0.01)

    if strategy == "center_radius":
        kspace_retained, actual_fraction = retain_center_fraction(full_kspace, keep_fraction)
    else:
        kspace_retained, actual_fraction = retain_top_magnitude(full_kspace, keep_fraction)

    retained_recon = normalize_image(np.abs(ifft2_centered(kspace_retained)))
    retained_log_mag = kspace_log_magnitude(kspace_retained)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.pyplot(plot_kspace_magnitude(retained_log_mag, f"Retained k-Space ({actual_fraction*100:.1f}%)"), use_container_width=True)
    with col2:
        st.image(retained_recon, caption="Reconstruction", clamp=True, use_container_width=True)
    with col3:
        err_map = error_heatmap(magnitude_image, retained_recon)
        st.pyplot(plot_error_heatmap(err_map, "Absolute Error"), use_container_width=True)

    p_psnr = psnr_metric(magnitude_image, retained_recon)
    p_ssim, _ = ssim_metric(magnitude_image, retained_recon)

    col1, col2, col3 = st.columns(3)
    col1.metric("Actual k-Space Retained", f"{actual_fraction*100:.1f}%")
    col2.metric("PSNR", f"{p_psnr:.2f} dB" if np.isfinite(p_psnr) else "∞")
    col3.metric("SSIM", f"{p_ssim:.4f}")

    if st.button("💾 Save reconstruction to gallery", key="save_retained_image"):
        saved_path = save_image_result(retained_recon, f"retained_{strategy}_{int(actual_fraction*100)}pct")
        st.success(f"Saved to assets/images/saved/{saved_path.name}")

    st.divider()
    st.subheader("Quality vs. Retention Curve")

    if st.button("Run retention sweep (may take a few seconds)"):

        fractions = [0.02, 0.05, 0.1, 0.2, 0.3, 0.5, 0.7, 1.0]
        sweep_results = retention_sweep(full_kspace, strategy, fractions)

        actual_fracs, psnr_values, ssim_values = [], [], []
        for _, actual_frac, kspace_variant in sweep_results:
            recon_variant = normalize_image(np.abs(ifft2_centered(kspace_variant)))
            p = psnr_metric(magnitude_image, recon_variant)
            s, _ = ssim_metric(magnitude_image, recon_variant)
            actual_fracs.append(actual_frac)
            psnr_values.append(min(p, 60) if np.isfinite(p) else 60)  # cap for readable plotting
            ssim_values.append(s)

        col1, col2 = st.columns(2)
        with col1:
            st.pyplot(
                plot_retention_curve(actual_fracs, {"PSNR (dB)": psnr_values}, title=f"PSNR vs. Retention ({strategy})"),
                use_container_width=True,
            )
        with col2:
            st.pyplot(
                plot_retention_curve(actual_fracs, {"SSIM": ssim_values}, title=f"SSIM vs. Retention ({strategy})"),
                use_container_width=True,
            )

        st.caption(
            "Compare the two retention strategies by re-running this sweep "
            "after switching the strategy dropdown above -- center-radius "
            "retention typically reaches usable image quality at a much "
            "lower percentage than top-magnitude retention, because MRI "
            "contrast is concentrated at the k-space center."
        )


# ------------------------------------------------------------
# TAB 5 -- METRICS
# ------------------------------------------------------------

with tabs[4]:

    st.header("Quantitative Reconstruction Analysis")

    st.markdown("Metrics computed for the **current Masking tab result** above.")

    m_mse = mse_metric(magnitude_image, masked_recon)
    m_psnr = psnr_metric(magnitude_image, masked_recon)
    m_ssim, m_ssim_map = ssim_metric(magnitude_image, masked_recon)

    col1, col2, col3 = st.columns(3)
    col1.metric("MSE", f"{m_mse:.6f}")
    col2.metric("PSNR", f"{m_psnr:.2f} dB" if np.isfinite(m_psnr) else "∞")
    col3.metric("SSIM", f"{m_ssim:.4f}")

    col1, col2 = st.columns(2)
    with col1:
        st.pyplot(plot_error_heatmap(error_heatmap(magnitude_image, masked_recon), "Absolute Error Heatmap"), use_container_width=True)
    with col2:
        st.pyplot(plot_ssim_map(m_ssim_map, "Local SSIM Map"), use_container_width=True)

    st.markdown(
        """
        **MSE** -- average squared pixel-by-pixel difference. Lower is better.
        Treats every pixel independently; doesn't know or care about spatial structure.

        **PSNR** -- a logarithmic (decibel) transform of MSE. Higher is better.
        Easier to compare across images of different overall contrast than raw MSE.

        **SSIM** -- compares local luminance, contrast, and structure in a
        sliding window, rather than pixels independently. Ranges roughly
        [-1, 1], where 1.0 is a perfect match. SSIM often drops sharply
        even when MSE/PSNR look only mildly worse, because blurring
        (the classic undersampling artifact) barely changes average
        pixel error but destroys local structure -- exactly the gap the
        local SSIM map above is visualizing.
        """
    )


# ============================================================
# FOOTER
# ============================================================

st.divider()
st.caption(
    "FourierLab MRI Module -- educational k-space signal-processing demo. "
    "Reconstruction methods are simplified and not intended for clinical use."
)
