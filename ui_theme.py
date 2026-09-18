"""
ui_theme.py

Unified visual theme, layout components, flowcharts, branding,
and Matplotlib styling for FourierLab.
"""

from pathlib import Path
import matplotlib.pyplot as plt
import streamlit as st

APP_ROOT = Path(__file__).resolve().parent
BRANDING_DIR = APP_ROOT / "assets" / "branding"
LOGO_PATH = BRANDING_DIR / "logo.png"


def setup_mpl_style():
    """
    Configures shared publication-quality Matplotlib styling for all labs.
    Clean typography, transparent backgrounds for seamless card integration,
    thin subtle grid lines, and high display DPI.
    """
    plt.rcParams.update({
        "figure.facecolor": "none",
        "axes.facecolor": "none",
        "savefig.facecolor": "none",
        "figure.dpi": 140,
        "savefig.dpi": 200,
        "font.family": "sans-serif",
        "font.sans-serif": ["Segoe UI", "DejaVu Sans", "Helvetica Neue", "Arial", "sans-serif"],
        "axes.edgecolor": "#cbd5e1",
        "axes.linewidth": 0.8,
        "axes.titlesize": 11,
        "axes.titleweight": "bold",
        "axes.titlepad": 8,
        "axes.labelsize": 10,
        "axes.labelweight": "normal",
        "axes.labelcolor": "#334155",
        "xtick.color": "#64748b",
        "ytick.color": "#64748b",
        "xtick.labelsize": 8.5,
        "ytick.labelsize": 8.5,
        "grid.color": "#e2e8f0",
        "grid.linestyle": "--",
        "grid.linewidth": 0.6,
        "grid.alpha": 0.7,
        "legend.fontsize": 8.5,
        "legend.framealpha": 0.85,
        "legend.edgecolor": "#e2e8f0",
    })


def apply_theme():
    """
    Injects custom CSS to modernize Streamlit's default UI into a refined,
    precision scientific laboratory interface.
    """
    setup_mpl_style()
    st.markdown(
        """
        <style>
        /* Import clean modern font */
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

        html, body, [class*="css"] {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        }

        code, pre, .stCodeBlock {
            font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, Consolas, monospace !important;
        }

        /* App background smoothing */
        .stApp {
            background-color: #f8fafc;
        }

        /* Sidebar console styling */
        section[data-testid="stSidebar"] {
            background-color: #0f172a;
            border-right: 1px solid #1e293b;
        }

        section[data-testid="stSidebar"] h1,
        section[data-testid="stSidebar"] h2,
        section[data-testid="stSidebar"] h3,
        section[data-testid="stSidebar"] span,
        section[data-testid="stSidebar"] label,
        section[data-testid="stSidebar"] p {
            color: #f1f5f9 !important;
        }

        section[data-testid="stSidebar"] .stSelectbox label,
        section[data-testid="stSidebar"] .stSlider label,
        section[data-testid="stSidebar"] .stRadio label {
            color: #94a3b8 !important;
            font-size: 0.85rem !important;
            font-weight: 500 !important;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        /* Modern styled cards */
        .lab-card {
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 12px;
            padding: 1.25rem 1.5rem;
            margin-bottom: 1.25rem;
            box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05), 0 1px 2px -1px rgba(0, 0, 0, 0.05);
            transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
        }

        .lab-card:hover {
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.08), 0 2px 4px -2px rgba(0, 0, 0, 0.05);
            border-color: #cbd5e1;
        }

        .lab-card-audio {
            border-top: 4px solid #6366f1;
        }

        .lab-card-image {
            border-top: 4px solid #0d9488;
        }

        .lab-card-neutral {
            border-top: 4px solid #3b82f6;
        }

        /* Metric cards */
        div[data-testid="stMetric"] {
            background-color: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 10px;
            padding: 0.8rem 1rem;
            box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03);
        }

        div[data-testid="stMetric"] label {
            color: #64748b !important;
            font-size: 0.8rem !important;
            font-weight: 600 !important;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }

        div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
            color: #0f172a !important;
            font-weight: 700 !important;
            font-size: 1.6rem !important;
        }

        /* Tabs styling */
        .stTabs [data-baseweb="tab-list"] {
            gap: 8px;
            background-color: #f1f5f9;
            padding: 6px;
            border-radius: 10px;
            border: 1px solid #e2e8f0;
        }

        .stTabs [data-baseweb="tab"] {
            height: 38px;
            border-radius: 6px;
            font-weight: 500;
            font-size: 0.9rem;
            color: #475569;
            padding: 0 16px;
            border: none !important;
            background-color: transparent;
            transition: all 0.2s ease;
        }

        .stTabs [aria-selected="true"] {
            background-color: #ffffff !important;
            color: #1e40af !important;
            font-weight: 600 !important;
            box-shadow: 0 1px 3px rgba(0,0,0,0.08) !important;
        }

        /* Button styling */
        .stButton > button {
            border-radius: 8px;
            font-weight: 500;
            transition: all 0.15s ease;
            border: 1px solid #cbd5e1;
        }

        .stButton > button:hover {
            border-color: #2563eb;
            color: #2563eb;
            box-shadow: 0 2px 4px rgba(37, 99, 235, 0.1);
        }

        /* Download button styling */
        .stDownloadButton > button {
            border-radius: 8px;
            font-weight: 500;
            background-color: #f8fafc;
            border: 1px solid #cbd5e1;
        }

        /* Plot wrapper card */
        .plot-container {
            background-color: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 10px;
            padding: 8px;
            box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
            margin-bottom: 0.75rem;
        }

        /* Section divider accent */
        .section-header {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-top: 1rem;
            margin-bottom: 0.5rem;
            color: #0f172a;
            font-weight: 700;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_logo(location: str = "sidebar", subtitle: str = ""):
    """
    Renders brand identity. If 'assets/branding/logo.png' exists, it is displayed.
    Otherwise, an elegant fallback SVG wordmark + icon is rendered.
    """
    has_logo = LOGO_PATH.exists()

    if location == "sidebar":
        if has_logo:
            st.sidebar.image(str(LOGO_PATH), use_container_width=True)
        else:
            st.sidebar.markdown(
                """
                <div style="padding: 10px 0 16px 0; border-bottom: 1px solid #334155; margin-bottom: 16px;">
                    <div style="display: flex; align-items: center; gap: 10px;">
                        <div style="background: linear-gradient(135deg, #2563eb, #06b6d4); width: 36px; height: 36px; border-radius: 8px; display: flex; align-items: center; justify-content: center; box-shadow: 0 2px 8px rgba(37,99,235,0.4);">
                            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
                                <path d="M2 12h3l3-8 4 16 3-8h7"></path>
                            </svg>
                        </div>
                        <div>
                            <div style="color: #ffffff; font-size: 1.15rem; font-weight: 700; letter-spacing: -0.02em; line-height: 1.1;">FourierLab</div>
                            <div style="color: #94a3b8; font-size: 0.7rem; font-weight: 500; letter-spacing: 0.04em; text-transform: uppercase;">Signal Workbench</div>
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    elif location == "header":
        if has_logo:
            col_l, col_r = st.columns([1, 6])
            with col_l:
                st.image(str(LOGO_PATH), use_container_width=True)
            with col_r:
                st.markdown(
                    f"""
                    <div style="margin-top: 4px;">
                        <h1 style="margin: 0; font-size: 2rem; font-weight: 700; color: #0f172a; letter-spacing: -0.02em;">FourierLab</h1>
                        <p style="margin: 0; color: #64748b; font-size: 0.95rem; font-weight: 500;">{subtitle or 'Academic Signal Processing Exploration Environment'}</p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.markdown(
                f"""
                <div style="display: flex; align-items: center; gap: 14px; margin-bottom: 0.75rem; padding-bottom: 0.75rem; border-bottom: 1px solid #e2e8f0;">
                    <div style="background: linear-gradient(135deg, #1e40af, #0d9488); width: 44px; height: 44px; border-radius: 10px; display: flex; align-items: center; justify-content: center; box-shadow: 0 4px 12px rgba(30,64,175,0.25);">
                        <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M2 12h3l3-8 4 16 3-8h7"></path>
                        </svg>
                    </div>
                    <div>
                        <div style="font-size: 1.85rem; font-weight: 800; color: #0f172a; letter-spacing: -0.03em; line-height: 1.1;">FourierLab</div>
                        <div style="font-size: 0.88rem; color: #64748b; font-weight: 500;">{subtitle or 'Academic Signal Processing Exploration Environment'}</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def render_pipeline_flowchart(mode: str = "home"):
    """
    Renders styled SVG/HTML flow diagrams showing the mathematical signal pipeline.
    """
    if mode == "home":
        st.markdown(
            """
            <div class="lab-card lab-card-neutral" style="margin-top: 1rem; margin-bottom: 1.5rem;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem;">
                    <span style="font-size: 0.85rem; font-weight: 700; color: #1e40af; text-transform: uppercase; letter-spacing: 0.05em;">
                        Unified Mathematical Pipeline
                    </span>
                    <span style="font-size: 0.75rem; background: #eff6ff; color: #1d4ed8; padding: 2px 8px; border-radius: 4px; font-weight: 600;">
                        Dual-Domain Symmetry
                    </span>
                </div>
                <div style="display: grid; grid-template-columns: 1fr; gap: 14px;">
                    <!-- Audio Pipeline -->
                    <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px;">
                        <div style="font-size: 0.8rem; font-weight: 700; color: #6366f1; margin-bottom: 6px; display: flex; align-items: center; gap: 6px;">
                            <span>🎧 AUDIO (1D Time ➔ 2D Time-Frequency)</span>
                        </div>
                        <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 6px; font-size: 0.82rem; font-weight: 500;">
                            <span style="background: #ffffff; padding: 4px 10px; border-radius: 6px; border: 1px solid #cbd5e1; color: #0f172a;">Waveform <i>x(t)</i></span>
                            <span style="color: #94a3b8; font-weight: 700;">➔ <small style="color:#6366f1; font-weight: 600;">STFT</small> ➔</span>
                            <span style="background: #eef2ff; padding: 4px 10px; border-radius: 6px; border: 1px solid #c7d2fe; color: #3730a3;">Complex STFT <i>|D| e<sup>jφ</sup></i></span>
                            <span style="color: #94a3b8; font-weight: 700;">➔ <small style="color:#6366f1; font-weight: 600;">Mask / Truncate</small> ➔</span>
                            <span style="background: #fdf2f8; padding: 4px 10px; border-radius: 6px; border: 1px solid #fbcfe8; color: #831843;">Modified Spectrum <i>D'</i></span>
                            <span style="color: #94a3b8; font-weight: 700;">➔ <small style="color:#6366f1; font-weight: 600;">iSTFT</small> ➔</span>
                            <span style="background: #f0fdf4; padding: 4px 10px; border-radius: 6px; border: 1px solid #bbf7d0; color: #166534;">Reconstructed <i>x'(t)</i></span>
                        </div>
                    </div>
                    <!-- MRI Pipeline -->
                    <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px;">
                        <div style="font-size: 0.8rem; font-weight: 700; color: #0d9488; margin-bottom: 6px; display: flex; align-items: center; gap: 6px;">
                            <span>🧠 MRI IMAGE (2D Spatial ➔ 2D Spatial-Frequency)</span>
                        </div>
                        <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 6px; font-size: 0.82rem; font-weight: 500;">
                            <span style="background: #ffffff; padding: 4px 10px; border-radius: 6px; border: 1px solid #cbd5e1; color: #0f172a;">Image <i>I(x,y)</i></span>
                            <span style="color: #94a3b8; font-weight: 700;">➔ <small style="color:#0d9488; font-weight: 600;">2D FFT</small> ➔</span>
                            <span style="background: #f0fdfa; padding: 4px 10px; border-radius: 6px; border: 1px solid #99f6e4; color: #115e59;">k-Space <i>K(u,v)</i></span>
                            <span style="color: #94a3b8; font-weight: 700;">➔ <small style="color:#0d9488; font-weight: 600;">Acquisition Mask</small> ➔</span>
                            <span style="background: #fdf2f8; padding: 4px 10px; border-radius: 6px; border: 1px solid #fbcfe8; color: #831843;">Sampled k-Space <i>K'</i></span>
                            <span style="color: #94a3b8; font-weight: 700;">➔ <small style="color:#0d9488; font-weight: 600;">iFFT2</small> ➔</span>
                            <span style="background: #f0fdf4; padding: 4px 10px; border-radius: 6px; border: 1px solid #bbf7d0; color: #166534;">Reconstructed <i>I'(x,y)</i></span>
                        </div>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    elif mode == "audio":
        st.markdown(
            """
            <div style="background: #ffffff; border: 1px solid #e2e8f0; border-left: 4px solid #6366f1; border-radius: 8px; padding: 10px 14px; margin-bottom: 1.25rem;">
                <div style="font-size: 0.72rem; font-weight: 700; color: #6366f1; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 4px;">
                    Audio Processing Ribbon
                </div>
                <div style="display: flex; align-items: center; gap: 8px; font-size: 0.8rem; font-weight: 500; color: #334155; overflow-x: auto; white-space: nowrap;">
                    <span style="background: #f1f5f9; padding: 3px 8px; border-radius: 4px;">Waveform</span> ➔
                    <span style="background: #eef2ff; color: #3730a3; padding: 3px 8px; border-radius: 4px; font-weight: 600;">STFT Windowing</span> ➔
                    <span style="background: #f1f5f9; padding: 3px 8px; border-radius: 4px;">Complex Spectrogram</span> ➔
                    <span style="background: #fef2f2; color: #991b1b; padding: 3px 8px; border-radius: 4px;">Masking / Retention</span> ➔
                    <span style="background: #eef2ff; color: #3730a3; padding: 3px 8px; border-radius: 4px; font-weight: 600;">Inverse STFT</span> ➔
                    <span style="background: #f0fdf4; color: #166534; padding: 3px 8px; border-radius: 4px; font-weight: 600;">Reconstructed Audio</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    elif mode == "image":
        st.markdown(
            """
            <div style="background: #ffffff; border: 1px solid #e2e8f0; border-left: 4px solid #0d9488; border-radius: 8px; padding: 10px 14px; margin-bottom: 1.25rem;">
                <div style="font-size: 0.72rem; font-weight: 700; color: #0d9488; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 4px;">
                    MRI Reconstruction Ribbon
                </div>
                <div style="display: flex; align-items: center; gap: 8px; font-size: 0.8rem; font-weight: 500; color: #334155; overflow-x: auto; white-space: nowrap;">
                    <span style="background: #f1f5f9; padding: 3px 8px; border-radius: 4px;">Input Image</span> ➔
                    <span style="background: #f0fdfa; color: #115e59; padding: 3px 8px; border-radius: 4px; font-weight: 600;">2D FFT</span> ➔
                    <span style="background: #f1f5f9; padding: 3px 8px; border-radius: 4px;">Centered k-Space</span> ➔
                    <span style="background: #fef2f2; color: #991b1b; padding: 3px 8px; border-radius: 4px;">Acquisition / Subsampling</span> ➔
                    <span style="background: #f0fdfa; color: #115e59; padding: 3px 8px; border-radius: 4px; font-weight: 600;">2D Inverse FFT</span> ➔
                    <span style="background: #f0fdf4; color: #166534; padding: 3px 8px; border-radius: 4px; font-weight: 600;">Reconstructed MRI</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_quick_start(step1: str, step2: str, step3: str):
    """
    Renders a compact, numbered quick-start guide at the top of a lab page.
    """
    st.markdown(
        f"""
        <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px 14px; margin-bottom: 1.25rem; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px;">
            <div style="display: flex; align-items: center; gap: 6px;">
                <span style="background: #2563eb; color: #ffffff; border-radius: 50%; width: 20px; height: 20px; display: inline-flex; align-items: center; justify-content: center; font-size: 0.75rem; font-weight: 700;">1</span>
                <span style="font-size: 0.84rem; color: #334155; font-weight: 500;">{step1}</span>
            </div>
            <div style="color: #cbd5e1; font-weight: bold;">➔</div>
            <div style="display: flex; align-items: center; gap: 6px;">
                <span style="background: #2563eb; color: #ffffff; border-radius: 50%; width: 20px; height: 20px; display: inline-flex; align-items: center; justify-content: center; font-size: 0.75rem; font-weight: 700;">2</span>
                <span style="font-size: 0.84rem; color: #334155; font-weight: 500;">{step2}</span>
            </div>
            <div style="color: #cbd5e1; font-weight: bold;">➔</div>
            <div style="display: flex; align-items: center; gap: 6px;">
                <span style="background: #2563eb; color: #ffffff; border-radius: 50%; width: 20px; height: 20px; display: inline-flex; align-items: center; justify-content: center; font-size: 0.75rem; font-weight: 700;">3</span>
                <span style="font-size: 0.84rem; color: #334155; font-weight: 500;">{step3}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
