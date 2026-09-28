/**
 * FourierLab - Image Lab (MRI k-Space Module)
 * Client-side controller for k-space acquisition, decomposition,
 * frequency-domain masking, and progressive reconstruction.
 */

const state = {
    source: null,
    sourceLabel: "",
    resolution: 160,
    phaseStrength: 0.6,
    lastAnalyze: null,
    lastMask: null,
    lastRetain: null,
    lastSweep: null,
    activeTab: "tabOverview",

    // K-space lasso masking
    kspaceLasso: {
        canvas: null,
        ctx: null,
        pixelPath: [],
        vertices: [],
        isDrawing: false,
        mouseDown: false,
        enabled: false,
    },
};

function el(id) {
    return document.getElementById(id);
}

function setBusy(busy) {
    document.querySelectorAll(".btn").forEach((b) => (b.disabled = busy));
}

function setStatus(message, type = "info") {
    const sb = el("sidebarStatus");
    if (!sb) return;
    sb.textContent = message;
    sb.className = "sidebar-status" + (type === "loaded" ? " loaded" : "");
}

function fmt(value, digits = 2, suffix = "") {
    if (value === null || value === undefined) return "&infin;";
    return Number(value).toFixed(digits) + suffix;
}

function b64Src(b64) {
    if (!b64) return "";
    return b64.startsWith("data:") ? b64 : `data:image/png;base64,${b64}`;
}

/* =========================================================
   COLORBAR (scale legend under every heatmap)
   ========================================================= */

const CMAPS = {
    viridis: "linear-gradient(to right,#440154,#3b528b,#21918c,#5ec962,#fde725)",
    inferno: "linear-gradient(to right,#000004,#420a68,#932667,#dd513a,#fca50a,#fcffa4)",
    rdylgn: "linear-gradient(to right,#a50026,#f46d43,#fee08b,#a6d96a,#006837)",
    twilight: "linear-gradient(to right,#e2d9e2,#6a7fc0,#2f1437,#c47a68,#e2d9e2)",
};

function setColorbar(imgId, cmap, minTxt, maxTxt) {
    const img = el(imgId);
    if (!img) return;
    const id = imgId + "_cbar";
    let bar = el(id);
    if (!bar) {
        bar = document.createElement("div");
        bar.id = id;
        bar.style.marginTop = "6px";
        img.insertAdjacentElement("afterend", bar);
    }
    bar.innerHTML = `
        <div style="height:10px;border-radius:3px;background:${CMAPS[cmap]}"></div>
        <div style="display:flex;justify-content:space-between;font:0.65rem var(--mono);color:#8CA0BE">
            <span>${minTxt}</span><span>${maxTxt}</span>
        </div>`;
}

function readoutHtml(label, value) {
    return `
        <div class="readout">
            <div class="readout-label">${label}</div>
            <div class="readout-value">${value}</div>
        </div>
    `;
}

async function apiPost_json(path, body) {
    const res = await fetch(API_BASE + path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });
    if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail.detail || `Request to ${path} failed (${res.status})`);
    }
    return res.json();
}

/* =========================================================
   LIBRARY & SOURCE LOADING
   ========================================================= */

async function refreshLibrary() {
    try {
        const data = await apiGet("/image/library");
        const sampleSelect = el("sampleSelect");
        const savedSelect = el("savedSelect");

        if (sampleSelect) {
            sampleSelect.innerHTML = data.samples.length
                ? data.samples.map((f) => `<option value="${f}">${f}</option>`).join("")
                : `<option value="">(no samples found)</option>`;
        }

        if (savedSelect) {
            savedSelect.innerHTML = data.saved.length
                ? data.saved.map((f) => `<option value="${f}">${f}</option>`).join("")
                : `<option value="">(none saved yet)</option>`;
        }
    } catch (err) {
        console.warn("Could not load image library:", err);
    }
}

function currentSourceMode() {
    const checked = document.querySelector('input[name="sourceMode"]:checked');
    return checked ? checked.value : "upload";
}

function updateSourcePanelVisibility() {
    const mode = currentSourceMode();
    const panels = {
        upload: el("sourcePanel_upload"),
        sample: el("sourcePanel_sample"),
        phantom: el("sourcePanel_phantom"),
        saved: el("sourcePanel_saved"),
    };

    Object.keys(panels).forEach((k) => {
        if (panels[k]) {
            panels[k].style.display = (k === mode) ? "block" : "none";
        }
    });
}

async function resolveSource() {
    const mode = currentSourceMode();

    if (mode === "upload") {
        const fileInput = el("uploadInput");
        if (!fileInput.files.length) {
            throw new Error("Please select an image file to upload first.");
        }
        const form = new FormData();
        form.append("file", fileInput.files[0]);

        setStatus("Uploading image...");

        // NOTE: no Content-Type header here, the browser sets the multipart boundary itself
        const r = await fetch(API_BASE + "/image/upload", { method: "POST", body: form });
        if (!r.ok) {
            const d = await r.json().catch(() => ({}));
            throw new Error(d.detail || `Upload failed (${r.status})`);
        }
        const up = await r.json();
        state.source = up.source;
        state.sourceLabel = fileInput.files[0].name;
        return;
    }

    if (mode === "sample") {
        const name = el("sampleSelect").value;
        if (!name) throw new Error("No sample selected.");
        state.source = "samples/" + name;
        state.sourceLabel = name;
        return;
    }

    if (mode === "phantom") {
        state.source = "synthetic_phantom";
        state.sourceLabel = "Synthetic Shepp-Logan Phantom";
        return;
    }

    if (mode === "saved") {
        const name = el("savedSelect").value;
        if (!name) throw new Error("No saved result selected.");
        state.source = "saved/" + name;
        state.sourceLabel = name;
        return;
    }
}

/* =========================================================
   CORE PIPELINE ACTIONS
   ========================================================= */

async function handleAnalyze() {
    setBusy(true);
    try {
        await resolveSource();

        clearKspaceLasso();

        const oldCanvas = el("kspaceLassoCanvas");
        if (oldCanvas) {
            oldCanvas.remove();
        }

        state.kspaceLasso.canvas = null;
        state.kspaceLasso.ctx = null;
        state.kspaceLasso.enabled = false;
        
        const resolution = parseInt(el("resolutionSelect").value, 10) || 160;
        const phaseStrength = parseFloat(el("phaseStrengthSlider").value) || 0.6;
        state.resolution = resolution;
        state.phaseStrength = phaseStrength;

        setStatus(`Analyzing ${state.sourceLabel}...`);

        const data = await apiPost_json("/image/analyze", {
            source: state.source,
            resolution: state.resolution,
            phase_strength: state.phaseStrength,
        });

        state.lastAnalyze = data;
        state.lastMask = null;

        // Display lab body and hide empty state
        el("emptyState").style.display = "none";
        el("labBody").style.display = "block";

        // Seed the masking comparison with the unmasked source images.
        el("maskOriginalKspaceImg").src = b64Src(data.kspace_mag_b64);
        el("maskOverlayImg").src = b64Src(data.kspace_mag_b64);
        el("maskReconImg").src = b64Src(data.original_b64);
        el("maskErrorImg").removeAttribute("src");
        el("maskErrorImg").hidden = true;
        el("maskErrorPlaceholder").hidden = false;
        el("maskRetainedBadge").textContent = "Not applied";
        el("maskReadouts").innerHTML = "";
        el("metricsReadouts").innerHTML = "";
        el("metricsErrorImg").removeAttribute("src");
        el("metricsSsimImg").removeAttribute("src");

        // Tab 1: Overview
        el("overviewOriginalImg").src = b64Src(data.original_b64);
        el("overviewKspaceImg").src = b64Src(data.kspace_mag_b64);
        el("overviewReconImg").src = b64Src(data.recon_b64);
        setColorbar("overviewKspaceImg", "viridis", "low", "high");

        el("overviewReadouts").innerHTML = [
            readoutHtml("Matrix Size", `${data.resolution} &times; ${data.resolution}`),
            readoutHtml("Center Energy", `${data.center_energy_pct}%`),
            readoutHtml("Phase Field", `${data.phase_strength.toFixed(2)} rad`),
            readoutHtml("Acquisition", "100.0%"),
        ].join("");

        // Tab 2: Magnitude & Phase maps
        el("magPhaseMagnitudeImg").src = b64Src(data.kspace_mag_b64);
        el("magPhasePhaseImg").src = b64Src(data.kspace_phase_b64);
        setColorbar("magPhaseMagnitudeImg", "viridis", "low", "high");
        setColorbar("magPhasePhaseImg", "twilight", "-π", "+π");

        // Sidebar status
        setStatus(`Loaded: ${state.sourceLabel} (${data.resolution} x ${data.resolution})`, "loaded");
        el("sidebarReadout").innerHTML = `
            <div style="font-family:var(--mono); font-size:0.75rem; color:var(--text); line-height:1.6;">
                <div><b>Source:</b> ${state.sourceLabel}</div>
                <div><b>Grid:</b> ${data.resolution}&times;${data.resolution} px</div>
                <div><b>Phase:</b> &times;${data.phase_strength.toFixed(2)}</div>
                <div><b>DC Core:</b> ${data.center_energy_pct}% energy</div>
            </div>
        `;

        // Compute the component and retention views; masking stays user-triggered.
        await handleGenComponents(true);
        await handleApplyRetention(true);

    } catch (err) {
        alert("Analysis error: " + err.message);
        setStatus("Error: " + err.message);
    } finally {
        setBusy(false);
    }
}

async function handleGenComponents(silent = false) {
    if (!state.lastAnalyze) return;
    try {
        if (!silent) setBusy(true);
        const data = await apiPost_json("/image/component", {
            source: state.source,
            resolution: state.resolution,
            phase_strength: state.phaseStrength,
            mode: "both",
        });

        el("magOnlyReconImg").src = b64Src(data.magnitude_only_b64);
        el("phaseOnlyReconImg").src = b64Src(data.phase_only_b64);
    } catch (err) {
        if (!silent) alert("Component reconstruction error: " + err.message);
    } finally {
        if (!silent) setBusy(false);
    }
}

async function handleApplyMask(silent = false) {
    if (!state.lastAnalyze) return;

    try {
        if (!silent) setBusy(true);

        const maskType = el("maskTypeSelect").value;
        const mode = document.querySelector(
            'input[name="maskModeRadio"]:checked'
        ).value;

        const radius = parseFloat(el("maskRadiusSlider").value);

        const req = {
            source: state.source,
            resolution: state.resolution,
            phase_strength: state.phaseStrength,
            mask_type: maskType,
            mode: mode,
            radius: radius,

            // Existing rectangular custom-mask values
            kx_min: parseFloat(el("kxMinSlider").value),
            kx_max: parseFloat(el("kxMaxSlider").value),
            ky_min: parseFloat(el("kyMinSlider").value),
            ky_max: parseFloat(el("kyMaxSlider").value),

            // New polygon/lasso mask
            lasso_vertices: null,
        };

        /*
         * When Custom Lasso is selected, send the polygon instead
         * of the rectangular slider coordinates.
         */
        if (maskType === "custom_lasso") {
            const vertices = state.kspaceLasso.vertices;

            if (!vertices || vertices.length < 3) {
                throw new Error("Draw a k-space region first.");
            }

            req.lasso_vertices = vertices.map((v) => ({
                kx: Number(v.kx),
                ky: Number(v.ky),
            }));
        }

        setStatus("Applying k-space mask...");

        const data = await apiPost_json("/image/mask", req);

        state.lastMask = data;

        el("maskOverlayImg").src = b64Src(data.mask_overlay_b64);
        if (maskType === "custom_lasso") {
            const img = el("maskOverlayImg");

            img.onload = () => {
                requestAnimationFrame(() => {
                    initKspaceLassoCanvas();
                    wireKspaceLassoEvents();
                    drawKspaceLassoRegions();
                });
            };
        }
        el("maskReconImg").src = b64Src(data.recon_b64);
        el("maskErrorImg").src = b64Src(data.error_heatmap_b64);
        el("maskErrorImg").hidden = false;
        el("maskErrorPlaceholder").hidden = true;

        setColorbar(
            "maskOverlayImg",
            "viridis",
            "low",
            "high"
        );

        setColorbar(
            "maskErrorImg",
            "inferno",
            "0",
            (data.error_max ?? 0).toFixed(3)
        );

        el("maskRetainedBadge").textContent =
            `${data.retained_pct.toFixed(1)}% kept`;

        el("maskReadouts").innerHTML = [
            readoutHtml(
                "k-Space Retained",
                `${data.retained_pct.toFixed(1)}%`
            ),
            readoutHtml(
                "PSNR",
                fmt(data.psnr, 2, " dB")
            ),
            readoutHtml(
                "SSIM",
                fmt(data.ssim, 4)
            ),
            readoutHtml(
                "MSE",
                fmt(data.mse, 6)
            ),
        ].join("");

        updateMetricsTab(data);

        updateMaskTip(maskType, mode);

    } catch (err) {
        if (!silent) {
            alert("Masking error: " + err.message);
        }
        setStatus("Masking error: " + err.message);
    } finally {
        if (!silent) setBusy(false);
    }
}

function handleResetMask() {
    const analysis = state.lastAnalyze;
    if (!analysis) return;

    state.lastMask = null;
    state.kspaceLasso.enabled = false;
    clearKspaceLasso();

    const lassoButton = el("kspaceLassoBtn");
    if (lassoButton) {
        lassoButton.textContent = "Draw Custom Region";
        lassoButton.classList.remove("active");
    }

    el("maskOverlayImg").src = b64Src(analysis.kspace_mag_b64);
    el("maskReconImg").src = b64Src(analysis.original_b64);
    el("maskErrorImg").removeAttribute("src");
    el("maskErrorImg").hidden = true;
    el("maskErrorPlaceholder").hidden = false;
    el("maskRetainedBadge").textContent = "Not applied";
    el("maskReadouts").innerHTML = "";
    el("metricsReadouts").innerHTML = "";
    el("metricsErrorImg").removeAttribute("src");
    el("metricsSsimImg").removeAttribute("src");

    setStatus("Mask reset to original k-space.", "loaded");
}


/* =========================================================
   K-SPACE LASSO MASKING
   ========================================================= */

function getKspaceLassoPlot() {
    const img = el("maskOverlayImg");
    if (!img) return null;

    const container = img.parentElement;
    if (!container) return null;

    return {
        img,
        container,
    };
}


function initKspaceLassoCanvas() {
    const target = getKspaceLassoPlot();
    if (!target) return;

    const { img, container } = target;

    const old = el("kspaceLassoCanvas");
    if (old) old.remove();

    /*
     * The overlay follows the actual displayed image.
     * This means the lasso stays aligned when the image
     * scales responsively.
     */
    const rect = img.getBoundingClientRect();

    if (rect.width <= 0 || rect.height <= 0) return;

    const canvas = document.createElement("canvas");
    canvas.id = "kspaceLassoCanvas";

    const dpr = window.devicePixelRatio || 1;

    canvas.width = Math.round(rect.width * dpr);
    canvas.height = Math.round(rect.height * dpr);

    canvas.style.cssText = `
        position: absolute;
        left: 0;
        top: 0;
        width: 100%;
        height: 100%;
        z-index: 20;
        pointer-events: auto;
        cursor: crosshair;
        border-radius: inherit;
    `;

    /*
     * The parent must be positioned so the canvas sits
     * exactly on top of the k-space image.
     */
    const computedPosition =
        window.getComputedStyle(container).position;

    if (computedPosition === "static") {
        container.style.position = "relative";
    }

    container.appendChild(canvas);

    const ctx = canvas.getContext("2d");

    /*
     * Draw using CSS-pixel coordinates rather than physical
     * canvas pixels.
     */
    ctx.scale(dpr, dpr);

    state.kspaceLasso.canvas = canvas;
    state.kspaceLasso.ctx = ctx;

    resizeKspaceLassoCanvas();

    drawKspaceLassoRegions();
}


function resizeKspaceLassoCanvas() {
    const canvas = state.kspaceLasso.canvas;

    if (!canvas) return;

    const target = getKspaceLassoPlot();
    if (!target) return;

    const rect = target.img.getBoundingClientRect();

    if (rect.width <= 0 || rect.height <= 0) return;

    const dpr = window.devicePixelRatio || 1;

    canvas.width = Math.round(rect.width * dpr);
    canvas.height = Math.round(rect.height * dpr);

    canvas.style.width = `${rect.width}px`;
    canvas.style.height = `${rect.height}px`;

    const ctx = canvas.getContext("2d");

    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    state.kspaceLasso.ctx = ctx;

    drawKspaceLassoRegions();
}


function kspacePixelToData(x, y) {
    const target = getKspaceLassoPlot();

    if (!target) return null;

    const rect = target.img.getBoundingClientRect();

    if (!rect.width || !rect.height) return null;

    /*
     * Convert image pixels to normalized k-space coordinates.
     *
     * Center = (0, 0)
     *
     * Left  = -0.5
     * Right = +0.5
     * Top   = -0.5
     * Bottom= +0.5
     */
    const kx = (x / rect.width) - 0.5;
    const ky = (y / rect.height) - 0.5;

    return {
        kx,
        ky,
    };
}


function kspaceDataToPixel(kx, ky) {
    const target = getKspaceLassoPlot();

    if (!target) return null;

    const rect = target.img.getBoundingClientRect();

    return {
        x: (kx + 0.5) * rect.width,
        y: (ky + 0.5) * rect.height,
    };
}


function getKspaceMousePosition(event) {
    const target = getKspaceLassoPlot();

    if (!target) return null;

    const rect = target.img.getBoundingClientRect();

    return {
        x: Math.max(
            0,
            Math.min(rect.width, event.clientX - rect.left)
        ),
        y: Math.max(
            0,
            Math.min(rect.height, event.clientY - rect.top)
        ),
    };
}


function drawCurrentKspaceLasso() {
    const ctx = state.kspaceLasso.ctx;
    const canvas = state.kspaceLasso.canvas;

    if (!ctx || !canvas) return;

    const rect = canvas.getBoundingClientRect();

    ctx.clearRect(0, 0, rect.width, rect.height);

    const path = state.kspaceLasso.pixelPath;

    if (path.length < 2) return;

    ctx.beginPath();

    ctx.moveTo(path[0].x, path[0].y);

    for (let i = 1; i < path.length; i++) {
        ctx.lineTo(path[i].x, path[i].y);
    }

    ctx.closePath();

    ctx.fillStyle = "rgba(245, 166, 35, 0.15)";
    ctx.fill();

    ctx.strokeStyle = "#F5A623";
    ctx.lineWidth = 2;
    ctx.setLineDash([6, 4]);
    ctx.stroke();

    ctx.setLineDash([]);

    /*
     * Start point
     */
    ctx.beginPath();
    ctx.arc(
        path[0].x,
        path[0].y,
        5,
        0,
        Math.PI * 2
    );

    ctx.fillStyle = "#F5A623";
    ctx.fill();
}


function drawKspaceLassoRegions() {
    const ctx = state.kspaceLasso.ctx;
    const canvas = state.kspaceLasso.canvas;

    if (!ctx || !canvas) return;

    const rect = canvas.getBoundingClientRect();

    ctx.clearRect(0, 0, rect.width, rect.height);

    /*
     * Only one custom lasso region is used for Image Lab.
     * This intentionally keeps the feature simple.
     */
    const vertices = state.kspaceLasso.vertices;

    if (!vertices || vertices.length < 3) return;

    const pixels = vertices
        .map(v => kspaceDataToPixel(v.kx, v.ky))
        .filter(Boolean);

    if (pixels.length < 3) return;

    ctx.beginPath();

    ctx.moveTo(
        pixels[0].x,
        pixels[0].y
    );

    for (let i = 1; i < pixels.length; i++) {
        ctx.lineTo(
            pixels[i].x,
            pixels[i].y
        );
    }

    ctx.closePath();

    /*
     * Fill
     */
    ctx.fillStyle = "rgba(199, 146, 234, 0.18)";
    ctx.fill();

    /*
     * Dark halo
     */
    ctx.strokeStyle = "rgba(6, 10, 20, 0.9)";
    ctx.lineWidth = 5;
    ctx.stroke();

    /*
     * Main border
     */
    ctx.strokeStyle = "#C792EA";
    ctx.lineWidth = 2.5;
    ctx.stroke();
}


function clearKspaceLasso() {
    state.kspaceLasso.pixelPath = [];
    state.kspaceLasso.vertices = [];
    state.kspaceLasso.isDrawing = false;
    state.kspaceLasso.mouseDown = false;

    const ctx = state.kspaceLasso.ctx;
    const canvas = state.kspaceLasso.canvas;

    if (ctx && canvas) {
        const rect = canvas.getBoundingClientRect();
        ctx.clearRect(0, 0, rect.width, rect.height);
    }
}


function finalizeKspaceLasso() {
    const vertices = state.kspaceLasso.vertices;

    if (!vertices || vertices.length < 3) {
        clearKspaceLasso();
        return;
    }

    state.kspaceLasso.isDrawing = false;
    state.kspaceLasso.mouseDown = false;
    state.kspaceLasso.pixelPath = [];

    drawKspaceLassoRegions();

    setStatus(
        `Custom k-space region selected (${vertices.length} points).`,
        "loaded"
    );
}


function cancelKspaceLasso() {
    state.kspaceLasso.isDrawing = false;
    state.kspaceLasso.mouseDown = false;
    state.kspaceLasso.pixelPath = [];

    /*
     * Do NOT delete an already completed region.
     * Escape only cancels the currently-being-drawn region.
     */
    drawKspaceLassoRegions();
}


function wireKspaceLassoEvents() {
    const canvas = state.kspaceLasso.canvas;

    if (!canvas) return;

    /*
     * Prevent browser image dragging.
     */
    canvas.addEventListener("dragstart", (e) => {
        e.preventDefault();
    });

    canvas.addEventListener("contextmenu", (e) => {
        e.preventDefault();
        cancelKspaceLasso();
    });

    canvas.addEventListener("mousedown", (e) => {
        if (e.button !== 0) return;

        if (!state.kspaceLasso.enabled) return;

        const pos = getKspaceMousePosition(e);

        if (!pos) return;

        state.kspaceLasso.isDrawing = true;
        state.kspaceLasso.mouseDown = true;
        state.kspaceLasso.pixelPath = [
            {
                x: pos.x,
                y: pos.y,
            },
        ];

        state.kspaceLasso.vertices = [];

        const data = kspacePixelToData(
            pos.x,
            pos.y
        );

        if (data) {
            state.kspaceLasso.vertices.push(data);
        }

        drawCurrentKspaceLasso();

        e.preventDefault();
    });

    canvas.addEventListener("mousemove", (e) => {
        if (!state.kspaceLasso.isDrawing) return;
        if (!state.kspaceLasso.mouseDown) return;

        const pos = getKspaceMousePosition(e);

        if (!pos) return;

        const path =
            state.kspaceLasso.pixelPath;

        const last =
            path[path.length - 1];

        const dx = pos.x - last.x;
        const dy = pos.y - last.y;

        /*
         * Don't store hundreds/thousands of almost-identical
         * points. This keeps the polygon lightweight.
         */
        if (Math.sqrt(dx * dx + dy * dy) < 3) {
            return;
        }

        path.push({
            x: pos.x,
            y: pos.y,
        });

        const data =
            kspacePixelToData(
                pos.x,
                pos.y
            );

        if (data) {
            state.kspaceLasso.vertices.push(data);
        }

        drawCurrentKspaceLasso();

        e.preventDefault();
    });

    const finish = () => {
        if (!state.kspaceLasso.mouseDown) return;

        state.kspaceLasso.mouseDown = false;

        if (
            state.kspaceLasso.vertices.length >= 3
        ) {
            finalizeKspaceLasso();
        } else {
            cancelKspaceLasso();
        }
    };

    canvas.addEventListener("mouseup", finish);
    canvas.addEventListener("mouseleave", finish);
}


function setupKspaceLassoControls() {
    const maskTypeSelect = el("maskTypeSelect");
    const lassoField = el("maskLassoField");
    const button = el("kspaceLassoBtn");

    if (!maskTypeSelect || !lassoField || !button) return;

    lassoField.hidden = maskTypeSelect.value !== "custom_lasso";

    button.addEventListener("click", () => {
        const isCurrentlyDrawing =
            state.kspaceLasso.enabled;

        state.kspaceLasso.enabled =
            !isCurrentlyDrawing;

        if (state.kspaceLasso.enabled) {
            button.textContent = "Cancel Drawing";
            button.classList.add("active");

            setStatus(
                "Drag on the k-space image to draw a custom region."
            );
        } else {
            button.textContent = "Draw Custom Region";
            button.classList.remove("active");

            cancelKspaceLasso();
        }
    });

    /*
     * When Custom Lasso is selected, automatically prepare
     * the interactive k-space image.
     */
    maskTypeSelect.addEventListener("change", (e) => {
        const lassoSelected = e.target.value === "custom_lasso";
        lassoField.hidden = !lassoSelected;

        if (e.target.value === "custom_lasso") {
            initKspaceLassoCanvas();
            wireKspaceLassoEvents();
            state.kspaceLasso.enabled = false;
            button.textContent = "Draw Custom Region";
            button.classList.remove("active");
        } else {
            state.kspaceLasso.enabled = false;

            button.textContent = "Draw Custom Region";
            button.classList.remove("active");

            cancelKspaceLasso();
        }
    });
}


function updateMaskTip(type, mode) {
    const tip = el("maskTipText");

    if (!tip) return;

    if (type === "center") {
        if (mode === "isolate") {
            tip.innerHTML =
                "<b>Center Isolated:</b> Low spatial frequencies preserved &rarr; Overall contrast and coarse geometry survive, but edges and fine details are blurred out.";
        } else {
            tip.innerHTML =
                "<b>Center Removed:</b> Low spatial frequencies blocked &rarr; Global contrast collapses while fine boundary information remains.";
        }

    } else if (type === "outer") {
        if (mode === "isolate") {
            tip.innerHTML =
                "<b>Outer Isolated:</b> Only peripheral high spatial frequencies kept &rarr; Edge information dominates while bulk contrast is reduced.";
        } else {
            tip.innerHTML =
                "<b>Outer Removed:</b> Classical circular low-pass behavior &rarr; High-frequency edge information is suppressed.";

        }

    } else if (type === "custom_lasso") {
        tip.innerHTML =
            "<b>Custom Lasso Mask:</b> Draw any free-form region directly on k-space &rarr; isolate or remove exactly the spatial-frequency region you select.";

    } else {
        tip.innerHTML =
            "<b>Custom Rectangular Mask:</b> Allows anisotropic exploration &rarr; Select horizontal or vertical frequency bands independently.";
    }
}

async function handleSaveMask() {
    if (!state.lastMask || !state.lastMask.recon_b64) {
        alert("Apply a mask first before saving.");
        return;
    }
    setBusy(true);
    try {
        const maskType = el("maskTypeSelect").value;
        const mode = document.querySelector('input[name="maskModeRadio"]:checked').value;
        const label = `masked_${maskType}_${mode}`;

        const res = await apiPost_json("/image/save", {
            image_base64: state.lastMask.recon_b64,
            label: label,
        });
        alert(`Reconstruction saved as ${res.filename} to assets/images/saved/`);
        await refreshLibrary();
    } catch (err) {
        alert("Save failed: " + err.message);
    } finally {
        setBusy(false);
    }
}

async function handleApplyRetention(silent = false) {
    if (!state.lastAnalyze) return;
    try {
        if (!silent) setBusy(true);

        const strategy = el("strategySelect").value;
        const fraction = parseFloat(el("fractionSlider").value);

        const req = {
            source: state.source,
            resolution: state.resolution,
            phase_strength: state.phaseStrength,
            strategy: strategy,
            fraction: fraction,
        };

        const data = await apiPost_json("/image/retain", req);
        state.lastRetain = data;

        el("retainKspaceImg").src = b64Src(data.retained_kspace_b64);
        el("retainReconImg").src = b64Src(data.recon_b64);
        el("retainErrorImg").src = b64Src(data.error_heatmap_b64);
        setColorbar("retainKspaceImg", "viridis", "low", "high");
        setColorbar("retainErrorImg", "inferno", "0", (data.error_max ?? 0).toFixed(3));

        el("actualRetainedBadge").textContent = `${data.actual_pct.toFixed(1)}%`;

        el("retainReadouts").innerHTML = [
            readoutHtml("Actual Retained", `${data.actual_pct.toFixed(1)}%`),
            readoutHtml("PSNR", fmt(data.psnr, 2, " dB")),
            readoutHtml("SSIM", fmt(data.ssim, 4)),
            readoutHtml("MSE", fmt(data.mse, 6)),
        ].join("");

    } catch (err) {
        if (!silent) alert("Retention reconstruction error: " + err.message);
    } finally {
        if (!silent) setBusy(false);
    }
}

async function handleSaveRetain() {
    if (!state.lastRetain || !state.lastRetain.recon_b64) {
        alert("Reconstruct first before saving.");
        return;
    }
    setBusy(true);
    try {
        const strategy = el("strategySelect").value;
        const pct = Math.round(state.lastRetain.actual_pct || 25);
        const label = `retained_${strategy}_${pct}pct`;

        const res = await apiPost_json("/image/save", {
            image_base64: state.lastRetain.recon_b64,
            label: label,
        });
        alert(`Reconstruction saved as ${res.filename} to assets/images/saved/`);
        await refreshLibrary();
    } catch (err) {
        alert("Save failed: " + err.message);
    } finally {
        setBusy(false);
    }
}

async function handleRunSweep() {
    if (!state.lastAnalyze) return;
    setBusy(true);
    try {
        const strategy = el("strategySelect").value;
        const req = {
            source: state.source,
            resolution: state.resolution,
            phase_strength: state.phaseStrength,
            strategy: strategy,
        };

        setStatus("Running retention sweep...");
        const data = await apiPost_json("/image/sweep", req);
        state.lastSweep = data;

        renderSweepChart("sweepChart", data.actual_fractions, data.psnr, data.ssim, strategy);
        setStatus(`Sweep completed for ${strategy}`, "loaded");
    } catch (err) {
        alert("Sweep error: " + err.message);
    } finally {
        setBusy(false);
    }
}

function renderSweepChart(containerId, fractions, psnrValues, ssimValues, strategy) {
    const xPct = fractions.map((f) => Number((f * 100).toFixed(1)));

    const tracePsnr = {
        x: xPct,
        y: psnrValues,
        name: "PSNR (dB)",
        type: "scatter",
        mode: "lines+markers",
        line: { color: "#FFB454", width: 2.5 },
        marker: { color: "#FFB454", size: 6 },
        yaxis: "y1",
    };

    const traceSsim = {
        x: xPct,
        y: ssimValues,
        name: "SSIM",
        type: "scatter",
        mode: "lines+markers",
        line: { color: "#59C9F5", width: 2.5, dash: "dot" },
        marker: { color: "#59C9F5", size: 6 },
        yaxis: "y2",
    };

    const layout = {
        paper_bgcolor: "transparent",
        plot_bgcolor: "transparent",
        font: { family: "IBM Plex Mono, monospace", color: "#8CA0BE", size: 11 },
        margin: { l: 55, r: 55, t: 25, b: 45 },
        xaxis: {
            title: "k-Space Retained (%)",
            gridcolor: "#1C2A44",
            zerolinecolor: "#1C2A44",
        },
        yaxis: {
            title: "PSNR (dB)",
            titlefont: { color: "#FFB454" },
            tickfont: { color: "#FFB454" },
            gridcolor: "#1C2A44",
            zerolinecolor: "#1C2A44",
        },
        yaxis2: {
            title: "SSIM",
            titlefont: { color: "#59C9F5" },
            tickfont: { color: "#59C9F5" },
            overlaying: "y",
            side: "right",
            range: [0, 1.05],
            gridcolor: "transparent",
        },
        legend: {
            orientation: "h",
            x: 0.1,
            y: 1.15,
            font: { color: "#E7ECF3" },
        },
        height: 320,
    };

    Plotly.newPlot(containerId, [tracePsnr, traceSsim], layout, {
        displayModeBar: false,
        responsive: true,
    });
}

function updateMetricsTab(data) {
    if (!data) return;

    el("metricsReadouts").innerHTML = [
        readoutHtml("MSE", fmt(data.mse, 6)),
        readoutHtml("PSNR", fmt(data.psnr, 2, " dB")),
        readoutHtml("SSIM", fmt(data.ssim, 4)),
        readoutHtml("Retained", `${data.retained_pct || 100}%`),
    ].join("");

    if (data.error_heatmap_b64) {
        el("metricsErrorImg").src = b64Src(data.error_heatmap_b64);
        setColorbar("metricsErrorImg", "inferno", "0", (data.error_max ?? 0).toFixed(3));
    }
    if (data.ssim_map_b64) {
        el("metricsSsimImg").src = b64Src(data.ssim_map_b64);
        setColorbar("metricsSsimImg", "rdylgn", "0 (bad)", "1 (good)");
    }
}

/* =========================================================
   EVENT LISTENERS & INITIALIZATION
   ========================================================= */

function setupEventListeners() {
    // Source radio change
    document.querySelectorAll('input[name="sourceMode"]').forEach((radio) => {
        radio.addEventListener("change", updateSourcePanelVisibility);
    });

    // Upload dropzone interactions
    const dropzone = el("uploadDropzone");
    const fileInput = el("uploadInput");
    const fileNameDisplay = el("selectedFileName");

    if (dropzone && fileInput) {
        dropzone.addEventListener("click", () => fileInput.click());

        fileInput.addEventListener("change", () => {
            if (fileInput.files.length > 0) {
                fileNameDisplay.textContent = fileInput.files[0].name;
            } else {
                fileNameDisplay.textContent = "";
            }
        });

        dropzone.addEventListener("dragover", (e) => {
            e.preventDefault();
            dropzone.style.borderColor = "var(--amber)";
        });

        dropzone.addEventListener("dragleave", () => {
            dropzone.style.borderColor = "var(--border)";
        });

        dropzone.addEventListener("drop", (e) => {
            e.preventDefault();
            dropzone.style.borderColor = "var(--border)";
            if (e.dataTransfer.files.length > 0) {
                fileInput.files = e.dataTransfer.files;
                fileNameDisplay.textContent = fileInput.files[0].name;
            }
        });
    }

    // Phase strength slider live label
    const phaseSlider = el("phaseStrengthSlider");
    const phaseLabel = el("phaseStrengthLabel");
    if (phaseSlider && phaseLabel) {
        phaseSlider.addEventListener("input", (e) => {
            phaseLabel.textContent = Number(e.target.value).toFixed(2);
        });
    }

    // Mask radius slider live label
    const radiusSlider = el("maskRadiusSlider");
    const radiusLabel = el("maskRadiusLabel");
    if (radiusSlider && radiusLabel) {
        radiusSlider.addEventListener("input", (e) => {
            radiusLabel.textContent = Number(e.target.value).toFixed(2);
        });
    }

    // Mask type selector (switch between radial and custom rectangular inputs)
    const maskTypeSelect = el("maskTypeSelect");
    const maskRadiusField = el("maskRadiusField");
    const maskCustomGrid = el("maskCustomGrid");

    if (maskTypeSelect) {
        maskTypeSelect.addEventListener("change", (e) => {
            const val = e.target.value;

            if (val === "custom") {
                if (maskRadiusField) {
                    maskRadiusField.style.display = "none";
                }

                if (maskCustomGrid) {
                    maskCustomGrid.style.display = "grid";
                }

                state.kspaceLasso.enabled = false;
            }

            else if (val === "custom_lasso") {
                if (maskRadiusField) {
                    maskRadiusField.style.display = "none";
                }

                if (maskCustomGrid) {
                    maskCustomGrid.style.display = "none";
                }
            }

            else {
                if (maskRadiusField) {
                    maskRadiusField.style.display = "block";
                }

                if (maskCustomGrid) {
                    maskCustomGrid.style.display = "none";
                }

                state.kspaceLasso.enabled = false;

                const button = el("kspaceLassoBtn");

                if (button) {
                    button.textContent = "Draw Custom Region";
                    button.classList.remove("active");
                }

                cancelKspaceLasso();
            }
        });
    }

    // Custom rectangular sliders
    ["kxMin", "kxMax", "kyMin", "kyMax"].forEach((name) => {
        const slider = el(name + "Slider");
        const label = el(name + "Label");
        if (slider && label) {
            slider.addEventListener("input", (e) => {
                label.textContent = Number(e.target.value).toFixed(2);
            });
        }
    });

    // Retention fraction slider live label
    const fractionSlider = el("fractionSlider");
    const fractionLabel = el("fractionLabel");
    if (fractionSlider && fractionLabel) {
        fractionSlider.addEventListener("input", (e) => {
            fractionLabel.textContent = `${Math.round(e.target.value * 100)}%`;
        });
    }

    // Tab buttons
    document.querySelectorAll(".lab-tab").forEach((tabBtn) => {
        tabBtn.addEventListener("click", () => {
            document.querySelectorAll(".lab-tab").forEach((b) => b.classList.remove("active"));
            document.querySelectorAll(".lab-panel").forEach((p) => p.classList.remove("active"));

            tabBtn.classList.add("active");
            const targetId = tabBtn.getAttribute("data-target");
            const panel = el(targetId);
            if (panel) {
                panel.classList.add("active");
                state.activeTab = targetId;

                // Resize Plotly charts if switching to Retention tab
                if (targetId === "tabRetention" && state.lastSweep) {
                    Plotly.Plots.resize(el("sweepChart"));
                }
            }
        });
    });

    // Buttons
    // Buttons
    el("analyzeBtn")?.addEventListener("click", handleAnalyze);
    el("genComponentsBtn")?.addEventListener(
        "click",
        () => handleGenComponents(false)
    );
    el("applyMaskBtn")?.addEventListener(
        "click",
        () => handleApplyMask(false)
    );
    el("resetMaskBtn")?.addEventListener(
        "click",
        handleResetMask
    );
    el("saveMaskBtn")?.addEventListener(
        "click",
        handleSaveMask
    );
    el("applyRetentionBtn")?.addEventListener(
        "click",
        () => handleApplyRetention(false)
    );
    el("saveRetainBtn")?.addEventListener(
        "click",
        handleSaveRetain
    );
    el("sweepBtn")?.addEventListener(
        "click",
        handleRunSweep
    );


    setupKspaceLassoControls();
}

document.addEventListener("DOMContentLoaded", () => {
    setupEventListeners();
    refreshLibrary();
    updateSourcePanelVisibility();
});