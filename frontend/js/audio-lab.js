const state = {
    source: null,
    sourceLabel: "",
    sr: 22050,
    n_fft: 2048,
    hop_length: 512,
    duration: 0,
    lastAnalyze: null,
    lastMask: null,
    lastRetain: null,
    freqScale: "linear",
    melFreqs: null,
    melMagnitudeDb: null,

    // Filter & EQ state
    filterBlocks: [],
    selectedFilterBlockId: null,
    lastFilter: null,

    // Lasso masking state
    maskRegions: [],
    selectedMaskRegionId: null,
    isDrawing: false,
    drawingVertices: [],   // [{t, f}, ...] in data coords during active draw
};


const playbackState = {
    activePlayer: null,
    animationFrame: null,
};


const MAGNITUDE_COLORSCALE = "Viridis";
const PHASE_COLORSCALE = [
    [0, "#C792EA"],
    [0.5, "#0A1120"],
    [1, "#59C9F5"],
];

function el(id) { return document.getElementById(id); }

function setStatus(message, type = "info") {
    const box = el("statusBox");
    if (!box) return;
    box.textContent = message;
    box.className = "status-msg" + (type === "error" ? " status-error" : type === "success" ? " status-success" : "");
    box.style.display = message ? "block" : "none";
}

function setBusy(busy) {
    document.querySelectorAll(".btn").forEach((b) => {
        if (b.id === "saveModalSaveBtn" || b.id === "saveModalSkipBtn") return;
        b.disabled = busy;
    });
}

function fmt(value, digits = 2, suffix = "") {
    if (value === null || value === undefined) return "&infin;";
    return value.toFixed(digits) + suffix;
}

/* ---------- library & source loading ---------- */

async function refreshLibrary() {
    const data = await apiGet("/audio/library");
    const sampleSelect = el("sampleSelect");
    const savedSelect = el("savedSelect");
    sampleSelect.innerHTML = data.samples.map((f) => `<option value="${f}">${f}</option>`).join("");
    savedSelect.innerHTML = data.saved.length
        ? data.saved.map((f) => `<option value="${f}">${f}</option>`).join("")
        : `<option value="">(none saved yet)</option>`;
}

function currentSourceMode() {
    return document.querySelector('input[name="sourceMode"]:checked').value;
}

async function resolveSource() {
    const mode = currentSourceMode();

    if (mode === "upload") {
        const fileInput = el("uploadInput");

        if (!fileInput.files.length) {
            throw new Error("Choose a file to upload first.");
        }

        const form = new FormData();
        form.append("file", fileInput.files[0]);

        setStatus("Uploading and decoding...");

        const res = await apiPost("/audio/upload", form);

        state.source = res.source;
        state.sourceLabel = fileInput.files[0].name;

        return;
    }

    if (mode === "sample") {
        const name = el("sampleSelect").value;

        if (!name) {
            throw new Error("No sample selected.");
        }

        state.source = "samples/" + name;
        state.sourceLabel = name;

        return;
    }

    const name = el("savedSelect").value;

    if (!name) {
        throw new Error("No saved result selected.");
    }

    state.source = "saved/" + name;
    state.sourceLabel = name;
}

/* ---------- plotting ---------- */

function baseLayout(extra = {}) {
    return Object.assign(
        {
            paper_bgcolor: "transparent",
            plot_bgcolor: "transparent",
            font: { family: "IBM Plex Mono, monospace", color: "#8CA0BE", size: 11 },
            margin: { l: 55, r: 20, t: 10, b: 40 },
            xaxis: { gridcolor: "#1C2A44", zerolinecolor: "#1C2A44" },
            yaxis: { gridcolor: "#1C2A44", zerolinecolor: "#1C2A44" },
        },
        extra
    );
}

function renderWaveform(containerId, waveform) {
    const traceMax = { x: waveform.time, y: waveform.max, mode: "lines", line: { width: 1, color: "#FFB454" }, name: "max" };
    const traceMin = {
        x: waveform.time, y: waveform.min, mode: "lines", line: { width: 1, color: "#FFB454" },
        fill: "tonexty", fillcolor: "rgba(255,180,84,0.25)", name: "min",
    };
    const layout = baseLayout({
        xaxis: { title: "Time (s)", gridcolor: "#1C2A44" },
        yaxis: { title: "Amplitude", gridcolor: "#1C2A44", range: [-1.05, 1.05] },
        showlegend: false,
        height: 200,
    });

    Plotly.newPlot(containerId, [traceMax, traceMin], layout, {
        displayModeBar: false,
        responsive: true
    }).then(() => {
        if (playbackState.activePlayer) {
            updatePlotPlayback(containerId, playbackState.activePlayer.currentTime || 0);
        }
    });
}

function renderSpectrogram(
    containerId,
    freqs,
    times,
    magnitude_db,
    options = {},
    mel_freqs = null,
    mel_magnitude_db = null,
) {
    // Always use linear STFT data — Mel y-axis causes distortion in Plotly heatmap
    const yData = freqs;
    const zData = magnitude_db;

    // Safe dB range computation — no spread operator
    let zMax = -Infinity;
    let zRawMin = Infinity;
    for (let i = 0; i < zData.length; i++) {
        for (let j = 0; j < zData[i].length; j++) {
            const v = zData[i][j];
            if (v > zMax) zMax = v;
            if (v < zRawMin) zRawMin = v;
        }
    }
    const zMin = Math.max(zRawMin, zMax - 80);

    const trace = {
        x: times,
        y: yData,
        z: zData,
        type: "heatmap",
        colorscale: "Inferno",
        zsmooth: "best",
        zmin: zMin,
        zmax: zMax,
        colorbar: {
            title: options.colorbarTitle || "dB",
            titleside: "right",
            tickfont: { size: 10 },
            thickness: 12,
            tickvals: [zMin, (zMin + zMax) / 2, zMax],
            ticktext: [
                `${Math.round(zMin)} dB`,
                `${Math.round((zMin + zMax) / 2)} dB`,
                `${Math.round(zMax)} dB`,
            ],
        },
    };

    const isMaskPlot = containerId === "maskSpectrogram";

    let dragmode = "zoom";
    if (isMaskPlot) dragmode = "false";
    else if (options.selectable) dragmode = "select";

    const layout = {
        paper_bgcolor: "transparent",
        plot_bgcolor: "transparent",
        font: { family: "IBM Plex Mono, monospace", color: "#8CA0BE", size: 11 },
        margin: { l: 55, r: 20, t: 10, b: 40 },
        xaxis: {
            title: "Time (s)",
            gridcolor: "#1C2A44",
            zerolinecolor: "#1C2A44",
        },
        yaxis: {
            title: "Frequency (Hz)",
            type: state.freqScale,      // respects linear/log toggle
            range: state.freqScale === "log"
                ? [Math.log10(Math.max(freqs[1] || 1, 20)), Math.log10(freqs[freqs.length - 1])]
                : [freqs[0], freqs[freqs.length - 1]],
            gridcolor: "#1C2A44",
            zerolinecolor: "#1C2A44",
        },
        height: 320,
        dragmode,
        clickmode: "event",
        clickanywhere: true,
        newshape: {
            type: "rect",
            line: { color: "#F5A623", width: 2 },
            fillcolor: "rgba(245, 166, 35, 0.10)",
            opacity: 0.32,
            layer: "above",
        },
        activeshape: {
            fillcolor: "rgba(245, 166, 35, 0.12)",
            opacity: 0.55,
        },
        editrevision: "mask-regions",
    };

    const config = {
        displayModeBar: true,
        responsive: true,
        modeBarButtonsToRemove: ["lasso2d"],
        modeBarButtonsToAdd: [],
    };

    Plotly.newPlot(containerId, [trace], layout, config).then(() => {
        if (playbackState.activePlayer) {
            updatePlotPlayback(containerId, playbackState.activePlayer.currentTime || 0);
        }

        if (isMaskPlot) {
            // Remove old Plotly shape machinery — lasso uses canvas overlay instead
            initLassoCanvas();
            wireLassoEvents();
            drawRegionsOnCanvas();
            // Disable Plotly's own drag so it doesn't fight the lasso canvas
            Plotly.relayout(el("maskSpectrogram"), { dragmode: false });
        }

        if (options.onSelect) {
            const plot = document.getElementById(containerId);
            plot.on("plotly_selected", (evt) => {
                if (!evt || !evt.range) return;
                options.onSelect(evt.range.x, evt.range.y);
            });
        }

        // if (containerId === "filterOriginalSpectrogram") {
        //     wireFilterSelection();
        // }
    });
}

function renderPhase(containerId, freqs, times, phase) {
    const trace = {
        x: times, y: freqs, z: phase,
        type: "heatmap", colorscale: PHASE_COLORSCALE, zmin: -Math.PI, zmax: Math.PI,
        colorbar: { title: "rad", titleside: "right", tickfont: { size: 10 }, thickness: 12 },
    };
    const layout = baseLayout({
        xaxis: { title: "Time (s)" },
        yaxis: { title: "Frequency (Hz)", type: state.freqScale },
        height: 320,
    });

    Plotly.newPlot(containerId, [trace], layout, {
        displayModeBar: false,
        responsive: true
    }).then(() => {
        if (playbackState.activePlayer) {
            updatePlotPlayback(containerId, playbackState.activePlayer.currentTime || 0);
        }
    });
}

function renderSweepChart(containerId, fractions, snrValues) {
    const finite = snrValues.filter((v) => v !== null);
    const cap = finite.length ? Math.max(...finite) * 1.15 : 100;
    const plotValues = snrValues.map((v) => (v === null ? cap : v));

    const trace = {
        x: fractions.map((f) => f * 100), y: plotValues,
        mode: "lines+markers", line: { color: "#FFB454", width: 2 }, marker: { size: 7, color: "#FFB454" },
        text: snrValues.map((v) => (v === null ? "perfect reconstruction (&infin; dB)" : v.toFixed(2) + " dB")),
        hovertemplate: "%{x:.0f}% retained<br>%{text}<extra></extra>",
    };
    const layout = baseLayout({
        xaxis: { title: "Data Retained (%)" },
        yaxis: { title: "SNR (dB)" },
        height: 280,
    });
    Plotly.newPlot(containerId, [trace], layout, { displayModeBar: false, responsive: true });
}


/* -------------- play-back cursor --------------- */

function updatePlaybackCursor() {
    const player = playbackState.activePlayer;

    if (!player) return;

    const currentTime = player.currentTime || 0;

    updatePlotPlayback("waveformPlot", currentTime);
    updatePlotPlayback("overviewSpectrogram", currentTime);

    updatePlotPlayback("magSpectrogram", currentTime);
    updatePlotPlayback("phasePlot", currentTime);

    updatePlotPlayback("maskSpectrogram", currentTime);
    updatePlotPlayback("maskResultSpectrogram", currentTime);

    updatePlotPlayback("retainSpectrogram", currentTime);
    updatePlotPlayback("retainResultSpectrogram", currentTime);

    updatePlotPlayback("filterOriginalSpectrogram", currentTime);
    updatePlotPlayback("filterResultSpectrogram", currentTime);
    updatePlotPlayback("filterOriginalWaveform", currentTime);
    updatePlotPlayback("filterResultWaveform", currentTime);

    if (!player.paused && !player.ended) {
        playbackState.animationFrame = requestAnimationFrame(updatePlaybackCursor);
    } else {
        playbackState.animationFrame = null;
    }
}


function updatePlotPlayback(plotId, currentTime) {

    const plot = el(plotId);

    if (
        !plot ||
        !plot.data ||
        !plot.layout
    ) {
        return;
    }


    const duration =
        playbackState.activePlayer?.duration;

    if (
        !duration ||
        !Number.isFinite(duration) ||
        duration <= 0
    ) {
        return;
    }


    const xaxis = plot.layout.xaxis;

    if (!xaxis) {
        return;
    }


    const range = xaxis.range;

    if (
        !range ||
        range.length < 2
    ) {
        return;
    }


    const xMin = range[0];
    const xMax = range[1];

    const x = Math.max(
        xMin,
        Math.min(currentTime, xMax)
    );


    const shapes =
        plot.layout.shapes || [];


    /*
     * Preserve:
     *
     * - mask region shapes
     * - any future non-playback shapes
     *
     * Remove only the previous playback shapes.
     */
    const persistentShapes =
        shapes.filter(
            (shape) =>
                shape.name !== "playback-cursor" &&
                shape.name !== "playback-progress"
        );


    const playbackShapes = [

        {
            name: "playback-progress",

            type: "rect",

            xref: "x",
            yref: "paper",

            x0: xMin,
            x1: x,

            y0: 0,
            y1: 1,

            fillcolor:
                "rgba(120, 130, 145, 0.10)",

            line: {
                width: 0,
            },

            layer: "below",
        },

        {
            name: "playback-cursor",

            type: "line",

            xref: "x",
            yref: "paper",

            x0: x,
            x1: x,

            y0: 0,
            y1: 1,

            line: {
                color: "#F5F7FA",
                width: 2,
            },

            layer: "above",
        },
    ];


    Plotly.relayout(plot, {
        shapes: [
            ...persistentShapes,
            ...playbackShapes,
        ],
    });
}


function setActivePlaybackPlayer(player) {
    if (!player) return;

    playbackState.activePlayer = player;

    if (playbackState.animationFrame) {
        cancelAnimationFrame(playbackState.animationFrame);
        playbackState.animationFrame = null;
    }

    updatePlaybackCursor();
}


function wirePlaybackPlayer(playerId) {
    const player = el(playerId);

    if (!player) return;

    // Clicking / interacting with a player makes it the active player.
    player.addEventListener("play", () => {
        setActivePlaybackPlayer(player);
    });

    player.addEventListener("timeupdate", () => {
        setActivePlaybackPlayer(player);
    });

    player.addEventListener("seeking", () => {
        setActivePlaybackPlayer(player);
    });

    player.addEventListener("seeked", () => {
        setActivePlaybackPlayer(player);
    });

    player.addEventListener("pause", () => {
        if (playbackState.activePlayer === player) {
            updatePlaybackCursor();
        }
    });

    player.addEventListener("ended", () => {
        if (playbackState.activePlayer === player) {
            updatePlaybackCursor();
        }
    });
}


function wirePlaybackTracking() {
    const playerIds = [
        "originalPlayer",

        "magPhaseOriginalPlayer",
        "magOnlyPlayer",

        "phaseOriginalPlayer",
        "phaseOnlyPlayer",

        "maskOriginalPlayer",
        "maskedPlayer",

        "retentionOriginalPlayer",
        "retainedPlayer",

        "filterOriginalPlayer",
        "filteredPlayer",
    ];

    playerIds.forEach(wirePlaybackPlayer);
}


/* ---------- tab switching ---------- */

function initTabs() {
    document.querySelectorAll(".lab-tab").forEach((tabBtn) => {
        tabBtn.addEventListener("click", () => {
            document.querySelectorAll(".lab-tab").forEach((b) => b.classList.remove("active"));
            document.querySelectorAll(".lab-panel").forEach((p) => p.classList.remove("active"));
            tabBtn.classList.add("active");
            el(tabBtn.dataset.target).classList.add("active");

            if (tabBtn.dataset.target === "tabFilter" && state.lastAnalyze) {
                const d = state.lastAnalyze;
                const plot = el("filterOriginalSpectrogram");
                if (plot && !plot.data) {
                    renderSpectrogram("filterOriginalSpectrogram", d.freqs, d.times, d.magnitude_db, { selectable: false });
                }
            }
        });
    });
}

/* reset before analyzing */
function resetResults() {
    // Reset analysis state
    state.lastAnalyze = null;
    state.lastMask = null;
    state.lastRetain = null;
    state.duration = 0;

    // Clear plots
    const plotIds = [
        "waveformPlot",
        "overviewSpectrogram",
        "magSpectrogram",
        "phasePlot",
        "maskSpectrogram",
        "maskResultSpectrogram",
        "retainSpectrogram",
        "retainResultSpectrogram",
        "sweepChart",
        "filterOriginalSpectrogram",
        "filterResultSpectrogram",
    ];

    plotIds.forEach((id) => {
        const plot = el(id);

        if (plot && plot.data) {
            Plotly.purge(plot);
        }

        if (plot) {
            plot.innerHTML = "";
        }
    });

    // Clear audio players
    const playerIds = [
        "originalPlayer",

        "magPhaseOriginalPlayer",
        "magOnlyPlayer",

        "phaseOriginalPlayer",
        "phaseOnlyPlayer",

        "maskOriginalPlayer",
        "maskedPlayer",

        "retentionOriginalPlayer",
        "retainedPlayer",

        "filterOriginalPlayer",
        "filteredPlayer",
    ];

    playerIds.forEach((id) => {
        const player = el(id);

        if (player) {
            player.pause();
            player.removeAttribute("src");
            player.load();
        }
    });

    // Clear result readouts
    el("maskReadouts").innerHTML = "";
    el("retainReadout").innerHTML = "";
    el("filterReadouts").innerHTML = "";
    el("filterResultSection").style.display = "none";
    resetFilterBlocks();
    el("metricsBody").innerHTML = "";

    // Reset sidebar
    el("sidebarStatus").textContent = "No audio analyzed yet.";
    el("sidebarStatus").classList.remove("loaded");
    el("sidebarReadout").innerHTML = "";

    // Disable tabs until the new analysis finishes
    document.querySelectorAll(".lab-tab").forEach((tab) => {
        tab.disabled = true;
    });

    // Show empty state
    el("emptyState").style.display = "block";
    el("labBody").style.display = "none";


    resetMaskRegions();

    // Reset status message
    setStatus("");
}




/* =========================================================
   INTERACTIVE MASKING
   ========================================================= */

/* =========================================================
   LASSO MASKING
   ========================================================= */

let lassoCanvas = null;
let lassoCtx = null;
let lassoPixelPath = [];   // [{x,y}] raw pixel coords during draw
let isLassoMouseDown = false;
let lassoDocumentWired = false;

function getLassoPlotAxes() {
    const plot = el("maskSpectrogram");
    if (!plot || !plot._fullLayout) return null;
    const fl = plot._fullLayout;
    if (!fl.xaxis || !fl.yaxis) return null;
    return { xaxis: fl.xaxis, yaxis: fl.yaxis, plot };
}

function pixelToData(px, py) {
    const axes = getLassoPlotAxes();
    if (!axes) return null;
    const { xaxis, yaxis } = axes;
    // px/py are relative to the plot div, subtract the axis offsets
    const t = xaxis.p2d(px - xaxis._offset);
    const f = yaxis.p2d(py - yaxis._offset);
    return { t, f };
}

function dataToPixel(t, f) {
    const axes = getLassoPlotAxes();
    if (!axes) return null;
    const { xaxis, yaxis } = axes;
    return {
        x: xaxis.d2p(t) + xaxis._offset,
        y: yaxis.d2p(f) + yaxis._offset,
    };
}

function initLassoCanvas() {
    const plot = el("maskSpectrogram");
    if (!plot) return;

    const old = document.getElementById("lassoCanvas");
    if (old) old.remove();

    // Use Plotly's own reported dimensions so the canvas maps 1:1
    // with the pixel coordinate system that dataToPixel() uses.
    const fl = plot._fullLayout;
    const canvasW = fl ? fl.width : plot.offsetWidth;
    const canvasH = fl ? fl.height : plot.offsetHeight;

    const canvas = document.createElement("canvas");
    canvas.id = "lassoCanvas";
    canvas.width = canvasW;
    canvas.height = canvasH;
    canvas.style.cssText = `
        position: absolute;
        top: 0; left: 0;
        width: ${canvasW}px;
        height: ${canvasH}px;
        pointer-events: auto;
        z-index: 10;
        border-radius: 4px;
        cursor: crosshair;
    `;

    plot.style.position = "relative";
    plot.appendChild(canvas);

    lassoCanvas = canvas;
    lassoCtx = canvas.getContext("2d");
}

function drawLassoPath() {
    if (!lassoCtx || !lassoCanvas) return;
    lassoCtx.clearRect(0, 0, lassoCanvas.width, lassoCanvas.height);

    if (lassoPixelPath.length < 2) return;

    lassoCtx.beginPath();
    lassoCtx.moveTo(lassoPixelPath[0].x, lassoPixelPath[0].y);
    for (let i = 1; i < lassoPixelPath.length; i++) {
        lassoCtx.lineTo(lassoPixelPath[i].x, lassoPixelPath[i].y);
    }

    // Draw closing line back to start
    lassoCtx.lineTo(lassoPixelPath[0].x, lassoPixelPath[0].y);

    lassoCtx.strokeStyle = "#F5A623";
    lassoCtx.lineWidth = 2;
    lassoCtx.setLineDash([5, 3]);
    lassoCtx.stroke();

    // Fill with semi-transparent amber
    lassoCtx.fillStyle = "rgba(245, 166, 35, 0.12)";
    lassoCtx.fill();

    // Draw start point circle so user knows where to close
    lassoCtx.beginPath();
    lassoCtx.arc(lassoPixelPath[0].x, lassoPixelPath[0].y, 5, 0, Math.PI * 2);
    lassoCtx.fillStyle = "#F5A623";
    lassoCtx.fill();
    lassoCtx.setLineDash([]);
}

function drawRegionsOnCanvas() {
    if (!lassoCtx || !lassoCanvas) return;
    lassoCtx.clearRect(0, 0, lassoCanvas.width, lassoCanvas.height);

    state.maskRegions.forEach((region) => {
        if (!region.vertices || region.vertices.length < 3) return;

        const pixels = region.vertices.map(v => dataToPixel(v.t, v.f)).filter(Boolean);
        if (pixels.length < 3) return;

        const selected = region.id === state.selectedMaskRegionId;
        const color = region.mode === "isolate" ? "#C792EA" : "#F5A623";
        const fillAlpha = selected ? 0.20 : 0.08;
        const dash = region.enabled ? [] : [7, 5];

        const tracePath = () => {
            lassoCtx.beginPath();
            lassoCtx.moveTo(pixels[0].x, pixels[0].y);
            for (let i = 1; i < pixels.length; i++) {
                lassoCtx.lineTo(pixels[i].x, pixels[i].y);
            }
            lassoCtx.closePath();
        };

        // Fill
        tracePath();
        lassoCtx.fillStyle = `rgba(${hexToRgb(color)}, ${fillAlpha})`;
        lassoCtx.fill();

        // Dark halo underneath the colored line so the border reads clearly
        // against any part of the spectrogram — like a length of rope laid
        // on top of the heatmap.
        tracePath();
        lassoCtx.strokeStyle = "rgba(6, 10, 20, 0.85)";
        lassoCtx.lineWidth = selected ? 4.5 : 3.5;
        lassoCtx.setLineDash(dash);
        lassoCtx.stroke();

        // Selected regions get an extra glow behind the string
        if (selected) {
            lassoCtx.save();
            lassoCtx.shadowColor = color;
            lassoCtx.shadowBlur = 14;
            tracePath();
            lassoCtx.strokeStyle = `rgba(${hexToRgb(color)}, 0.9)`;
            lassoCtx.lineWidth = 2.5;
            lassoCtx.setLineDash(dash);
            lassoCtx.stroke();
            lassoCtx.restore();
        }

        // Bright colored line on top — this is the "string" itself
        tracePath();
        lassoCtx.strokeStyle = color;
        lassoCtx.lineWidth = selected ? 2.5 : 1.75;
        lassoCtx.setLineDash(dash);
        lassoCtx.stroke();
        lassoCtx.setLineDash([]);

        // Label with a small dark backing so it stays legible over any color
        const cx = pixels.reduce((s, p) => s + p.x, 0) / pixels.length;
        const cy = pixels.reduce((s, p) => s + p.y, 0) / pixels.length;
        lassoCtx.font = "11px IBM Plex Mono, monospace";
        const textWidth = lassoCtx.measureText(region.name).width;
        lassoCtx.fillStyle = "rgba(6, 10, 20, 0.75)";
        lassoCtx.fillRect(cx - textWidth / 2 - 5, cy - 9, textWidth + 10, 18);
        lassoCtx.fillStyle = color;
        lassoCtx.textAlign = "center";
        lassoCtx.textBaseline = "middle";
        lassoCtx.fillText(region.name, cx, cy);
    });
}

function hexToRgb(hex) {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return `${r}, ${g}, ${b}`;
}

function isNearStartPoint(px, py) {
    if (lassoPixelPath.length === 0) return false;
    const start = lassoPixelPath[0];
    const dx = px - start.x;
    const dy = py - start.y;
    return Math.sqrt(dx * dx + dy * dy) < 12;
}

function getPlotRelativeCoords(event) {
    const plot = el("maskSpectrogram");
    if (!plot) return null;
    const rect = plot.getBoundingClientRect();
    return {
        x: event.clientX - rect.left,
        y: event.clientY - rect.top,
    };
}

function pointInPolygon(t, f, vertices) {
    let inside = false;
    const n = vertices.length;
    let j = n - 1;
    for (let i = 0; i < n; i++) {
        const xi = vertices[i].t, yi = vertices[i].f;
        const xj = vertices[j].t, yj = vertices[j].f;
        const intersect = ((yi > f) !== (yj > f)) &&
            (t < (xj - xi) * (f - yi) / (yj - yi) + xi);
        if (intersect) inside = !inside;
        j = i;
    }
    return inside;
}

function findTopmostRegionAt(t, f) {
    // Search from end (last drawn = on top)
    for (let i = state.maskRegions.length - 1; i >= 0; i--) {
        const r = state.maskRegions[i];
        if (r.vertices && pointInPolygon(t, f, r.vertices)) {
            return r;
        }
    }
    return null;
}

function wireLassoEvents() {
    const canvas = lassoCanvas;
    if (!canvas) return;

    // mousedown always rebinds to the fresh canvas (a new one is created
    // on every render), so no "already wired" guard needed here.
    canvas.addEventListener("mousedown", (e) => {
        if (e.button !== 0) return;

        const pos = getPlotRelativeCoords(e);
        if (!pos) return;

        if (!state.isDrawing) {
            // Not in draw mode: clicking inside an existing region selects it
            const dataPos = pixelToData(pos.x, pos.y);
            if (dataPos) {
                const hit = findTopmostRegionAt(dataPos.t, dataPos.f);
                if (hit) selectMaskRegion(hit.id);
            }
            return;
        }

        // Draw mode is armed — this mousedown starts the actual path
        lassoPixelPath = [{ x: pos.x, y: pos.y }];
        state.drawingVertices = [];
        const dp = pixelToData(pos.x, pos.y);
        if (dp) state.drawingVertices.push(dp);
        isLassoMouseDown = true;
    });

    canvas.addEventListener("contextmenu", (e) => {
        e.preventDefault();
        cancelLassoDraw();
    });

    // Document-level listeners only need to be wired once — they don't
    // depend on which canvas instance is currently on screen, and the
    // canvas is recreated on every redraw.
    if (lassoDocumentWired) return;
    lassoDocumentWired = true;

    document.addEventListener("mousemove", (e) => {
        if (!state.isDrawing || !isLassoMouseDown) return;

        const pos = getPlotRelativeCoords(e);
        if (!pos) return;

        const last = lassoPixelPath[lassoPixelPath.length - 1];
        const dx = pos.x - last.x;
        const dy = pos.y - last.y;
        if (Math.sqrt(dx * dx + dy * dy) < 4) return;

        lassoPixelPath.push({ x: pos.x, y: pos.y });
        const dp = pixelToData(pos.x, pos.y);
        if (dp) state.drawingVertices.push(dp);

        drawLassoPath();
    });

    document.addEventListener("mouseup", () => {
        if (!state.isDrawing || !isLassoMouseDown) return;
        isLassoMouseDown = false;

        if (state.drawingVertices.length >= 3) {
            finalizeLassoRegion();
        } else {
            // Too few points, cancel
            state.isDrawing = false;
            lassoPixelPath = [];
            state.drawingVertices = [];
            if (lassoCtx && lassoCanvas) {
                lassoCtx.clearRect(0, 0, lassoCanvas.width, lassoCanvas.height);
            }
            drawRegionsOnCanvas();
            updateDrawModeUI();
        }
    });

    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && state.isDrawing) {
            cancelLassoDraw();
        }
        if ((e.key === "Delete" || e.key === "Backspace") && !state.isDrawing) {
            deleteSelectedMaskRegion();
        }
    });
}

function cancelLassoDraw() {
    state.isDrawing = false;
    lassoPixelPath = [];
    state.drawingVertices = [];
    if (lassoCtx && lassoCanvas) {
        lassoCtx.clearRect(0, 0, lassoCanvas.width, lassoCanvas.height);
    }
    drawRegionsOnCanvas();
    updateDrawModeUI();
}

function finalizeLassoRegion() {
    const vertices = state.drawingVertices;
    if (vertices.length < 3) return;

    const nextId = state.maskRegions.length > 0
        ? Math.max(...state.maskRegions.map(r => r.id)) + 1
        : 1;

    const region = {
        id: nextId,
        name: `Region ${nextId}`,
        vertices: vertices,
        mode: "remove",
        enabled: true,
    };

    state.maskRegions.push(region);
    state.selectedMaskRegionId = region.id;
    state.isDrawing = false;
    lassoPixelPath = [];
    state.drawingVertices = [];

    updateDrawModeUI();
    updateMaskRegionDropdown();
    updateMaskRegionEditor();
    drawRegionsOnCanvas();
}

function updateDrawModeUI() {
    const hint = el("maskModeHint");
    const drawBtn = el("drawRegionBtn");
    if (!hint || !drawBtn) return;

    if (state.isDrawing) {
        hint.textContent = "Hold and drag to draw. Release to close the region. Press Escape to cancel.";
        drawBtn.classList.add("active");
        drawBtn.textContent = "Cancel Draw";
    } else {
        hint.textContent = "Click Draw to start. Click inside a region to select it.";
        drawBtn.classList.remove("active");
        drawBtn.textContent = "Draw Region";
    }
}

function selectMaskRegion(regionId) {
    state.selectedMaskRegionId = regionId;
    updateMaskRegionEditor();
    updateMaskRegionDropdown();
    drawRegionsOnCanvas();
}

function getSelectedMaskRegion() {
    return state.maskRegions.find(r => r.id === state.selectedMaskRegionId) || null;
}

function deleteSelectedMaskRegion() {
    const region = getSelectedMaskRegion();
    if (!region) return;

    const idx = state.maskRegions.findIndex(r => r.id === region.id);
    state.maskRegions.splice(idx, 1);

    if (state.maskRegions.length > 0) {
        const nextIdx = Math.min(idx, state.maskRegions.length - 1);
        state.selectedMaskRegionId = state.maskRegions[nextIdx].id;
    } else {
        state.selectedMaskRegionId = null;
    }

    updateMaskRegionEditor();
    updateMaskRegionDropdown();
    drawRegionsOnCanvas();
}

function updateMaskRegionEditor() {
    const region = getSelectedMaskRegion();
    const editor = document.querySelector(".mask-editor-card");
    const selectedLabel = el("maskSelectedRegion");
    const enabled = el("maskRegionEnabled");

    if (!region) {
        if (selectedLabel) selectedLabel.textContent = "None";
        if (editor) editor.classList.add("region-empty");
        if (enabled) { enabled.checked = false; enabled.disabled = true; }
        document.querySelectorAll('input[name="maskMode"]').forEach(i => {
            i.checked = i.value === "remove";
            i.disabled = true;
        });
        return;
    }

    if (editor) editor.classList.remove("region-empty");
    if (selectedLabel) selectedLabel.textContent = region.name;
    if (enabled) { enabled.checked = region.enabled; enabled.disabled = false; }

    document.querySelectorAll('input[name="maskMode"]').forEach(i => {
        i.disabled = false;
        i.checked = i.value === region.mode;
    });
}

function updateMaskRegionDropdown() {
    const menu = el("maskRegionDropdownMenu");
    const dropdownLabel = el("maskRegionDropdownLabel");
    if (!menu) return;

    const region = getSelectedMaskRegion();
    if (dropdownLabel) {
        dropdownLabel.textContent = region ? region.name : "No regions";
    }

    if (state.maskRegions.length === 0) {
        menu.innerHTML = `<div class="mask-region-empty">No regions yet. Click Draw to start.</div>`;
        return;
    }

    menu.innerHTML = "";
    state.maskRegions.forEach((r) => {
        const row = document.createElement("div");
        row.className = "mask-region-item" + (r.id === state.selectedMaskRegionId ? " selected" : "");
        row.innerHTML = `
            <span class="mask-region-item-label">${r.name}</span>
            <label class="mask-region-item-checkbox">
                <input type="checkbox" ${r.enabled ? "checked" : ""} data-region-enable="${r.id}">
                <span>Enabled</span>
            </label>
        `;
        row.addEventListener("click", (e) => {
            if (e.target.matches('input[type="checkbox"]')) return;
            selectMaskRegion(r.id);
            closeMaskRegionDropdown();
        });

        const cb = row.querySelector(`[data-region-enable="${r.id}"]`);
        cb.addEventListener("change", (e) => {
            r.enabled = e.target.checked;
            updateMaskRegionEditor();
            drawRegionsOnCanvas();
        });

        menu.appendChild(row);
    });
}

function openMaskRegionDropdown() {
    el("maskRegionDropdown")?.classList.add("open");
}

function closeMaskRegionDropdown() {
    el("maskRegionDropdown")?.classList.remove("open");
}

function toggleMaskRegionDropdown() {
    el("maskRegionDropdown")?.classList.toggle("open");
}

function resetMaskRegions() {
    state.maskRegions = [];
    state.selectedMaskRegionId = null;
    state.isDrawing = false;
    state.drawingVertices = [];
    lassoPixelPath = [];

    if (lassoCtx && lassoCanvas) {
        lassoCtx.clearRect(0, 0, lassoCanvas.width, lassoCanvas.height);
    }

    closeMaskRegionDropdown();
    updateDrawModeUI();

    if (el("maskRegionDropdownMenu")) updateMaskRegionDropdown();
    if (el("maskSelectedRegion")) updateMaskRegionEditor();
}

function wireMaskRegionControls() {
    el("maskRegionDropdownBtn")?.addEventListener("click", (e) => {
        e.stopPropagation();
        toggleMaskRegionDropdown();
    });

    document.addEventListener("click", (e) => {
        const dropdown = el("maskRegionDropdown");
        if (dropdown && !dropdown.contains(e.target)) {
            closeMaskRegionDropdown();
        }
    });

    el("drawRegionBtn")?.addEventListener("click", () => {
        if (state.isDrawing) {
            cancelLassoDraw();
        } else {
            state.isDrawing = true;
            lassoPixelPath = [];
            state.drawingVertices = [];
            updateDrawModeUI();
        }
    });

    el("maskRegionEnabled")?.addEventListener("change", (e) => {
        const region = getSelectedMaskRegion();
        if (!region) return;
        region.enabled = e.target.checked;
        updateMaskRegionDropdown();
        drawRegionsOnCanvas();
    });

    document.querySelectorAll('input[name="maskMode"]').forEach(input => {
        input.addEventListener("change", (e) => {
            const region = getSelectedMaskRegion();
            if (!region) return;
            region.mode = e.target.value;
            updateMaskRegionEditor();
            drawRegionsOnCanvas();
        });
    });

    el("deleteMaskRegionBtn")?.addEventListener("click", deleteSelectedMaskRegion);
}



/* =========================================================
   FILTER & EQ
   ========================================================= */

function getSelectedFilterBlock() {
    return state.filterBlocks.find(b => b.id === state.selectedFilterBlockId) || null;
}

function selectFilterBlock(id) {
    state.selectedFilterBlockId = id;
    updateFilterBlockEditor();
    updateFilterBlockDropdown();
}

function addFilterBlock() {
    const nextId = state.filterBlocks.length > 0
        ? Math.max(...state.filterBlocks.map(b => b.id)) + 1
        : 1;

    const block = {
        id: nextId,
        name: `Block ${nextId}`,
        filter_type: "lowpass",
        freq_min: 0,
        freq_max: state.lastAnalyze ? state.sr / 2 : 11025,
        time_min: 0,
        time_max: null,
        gain_db: 0,
        enabled: true,
    };

    state.filterBlocks.push(block);
    state.selectedFilterBlockId = block.id;
    updateFilterBlockDropdown();
    updateFilterBlockEditor();
    drawFilterResultSpectrogram();
}

function deleteSelectedFilterBlock() {
    const block = getSelectedFilterBlock();
    if (!block) return;

    const idx = state.filterBlocks.findIndex(b => b.id === block.id);
    state.filterBlocks.splice(idx, 1);

    if (state.filterBlocks.length > 0) {
        state.selectedFilterBlockId = state.filterBlocks[Math.min(idx, state.filterBlocks.length - 1)].id;
    } else {
        state.selectedFilterBlockId = null;
    }

    updateFilterBlockDropdown();
    updateFilterBlockEditor();
    drawFilterBlockShapes();
}

function resetFilterBlocks() {
    state.filterBlocks = [];
    state.selectedFilterBlockId = null;
    state.lastFilter = null;
    updateFilterBlockDropdown();
    updateFilterBlockEditor();
    drawFilterBlockShapes();
}

function updateFilterBlockDropdown() {
    const menu = el("filterBlockDropdownMenu");
    const label = el("filterBlockDropdownLabel");

    const block = getSelectedFilterBlock();
    if (label) label.textContent = block ? block.name : "No blocks";

    if (!menu) return;

    if (state.filterBlocks.length === 0) {
        menu.innerHTML = `<div class="mask-region-empty">No blocks yet. Click + Add block to start.</div>`;
        return;
    }

    menu.innerHTML = "";
    state.filterBlocks.forEach((b, idx) => {
        const row = document.createElement("div");
        row.className = "mask-region-item" + (b.id === state.selectedFilterBlockId ? " selected" : "");
        row.innerHTML = `
            <span class="mask-region-item-label">${idx + 1}. ${b.name}</span>
            <label class="mask-region-item-checkbox">
                <input type="checkbox" ${b.enabled ? "checked" : ""} data-filter-enable="${b.id}">
                <span>Enabled</span>
            </label>
        `;
        row.addEventListener("click", (e) => {
            if (e.target.matches('input[type="checkbox"]')) return;
            selectFilterBlock(b.id);
            closeFilterBlockDropdown();
        });

        const cb = row.querySelector(`[data-filter-enable="${b.id}"]`);
        cb.addEventListener("change", (e) => {
            b.enabled = e.target.checked;
            updateFilterBlockEditor();
        });

        menu.appendChild(row);
    });
}

function updateFilterBlockEditor() {
    const block = getSelectedFilterBlock();
    const editor = el("filterBlockEditor");
    if (!editor) return;

    if (!block) {
        editor.classList.add("region-empty");
        el("filterBlockName").value = "";
        el("filterTypeSelect").value = "lowpass";
        el("filterFreqMin").value = 0;
        el("filterFreqMax").value = 11025;
        el("filterTimeMin").value = 0;
        el("filterTimeMax").value = "";
        el("filterGainDb").value = 0;
        el("filterBlockEnabled").checked = true;
        el("filterBlockEnabled").disabled = true;
        el("filterGainRow").style.display = "none";
        return;
    }

    editor.classList.remove("region-empty");
    el("filterBlockName").value = block.name;
    el("filterTypeSelect").value = block.filter_type;
    el("filterFreqMin").value = block.freq_min;
    el("filterFreqMax").value = block.freq_max;
    el("filterTimeMin").value = block.time_min;
    el("filterTimeMax").value = block.time_max !== null ? block.time_max : "";
    el("filterGainDb").value = block.gain_db;
    el("filterBlockEnabled").checked = block.enabled;
    el("filterBlockEnabled").disabled = false;
    el("filterGainRow").style.display = block.filter_type === "custom_gain" ? "" : "none";
}

function openFilterBlockDropdown() {
    el("filterBlockDropdown")?.classList.add("open");
}

function closeFilterBlockDropdown() {
    el("filterBlockDropdown")?.classList.remove("open");
}

function wireFilterBlockControls() {
    el("addFilterBlockBtn")?.addEventListener("click", addFilterBlock);
    el("deleteFilterBlockBtn")?.addEventListener("click", deleteSelectedFilterBlock);

    el("filterBlockDropdownBtn")?.addEventListener("click", (e) => {
        e.stopPropagation();
        el("filterBlockDropdown")?.classList.toggle("open");
    });

    document.addEventListener("click", (e) => {
        const dd = el("filterBlockDropdown");
        if (dd && !dd.contains(e.target)) closeFilterBlockDropdown();
    });

    // Live-sync all editor inputs back to the active block
    const syncField = (inputId, prop, transform) => {
        el(inputId)?.addEventListener("input", () => {
            const block = getSelectedFilterBlock();
            if (!block) return;
            block[prop] = transform ? transform(el(inputId).value) : el(inputId).value;
            if (prop === "name") updateFilterBlockDropdown();
            drawFilterBlockShapes();
        });
    };

    syncField("filterBlockName", "name");
    syncField("filterFreqMin", "freq_min", parseFloat);
    syncField("filterFreqMax", "freq_max", parseFloat);
    syncField("filterTimeMin", "time_min", parseFloat);
    syncField("filterGainDb", "gain_db", parseFloat);

    // time_max: blank → null (full duration)
    el("filterTimeMax")?.addEventListener("input", () => {
        const block = getSelectedFilterBlock();
        if (!block) return;
        const v = el("filterTimeMax").value.trim();
        block.time_max = v === "" ? null : parseFloat(v);
    });

    // filter_type: also toggles the gain row
    el("filterTypeSelect")?.addEventListener("change", () => {
        const block = getSelectedFilterBlock();
        if (!block) return;
        block.filter_type = el("filterTypeSelect").value;
        el("filterGainRow").style.display = block.filter_type === "custom_gain" ? "" : "none";
    });

    el("filterBlockEnabled")?.addEventListener("change", (e) => {
        const block = getSelectedFilterBlock();
        if (!block) return;
        block.enabled = e.target.checked;
        updateFilterBlockDropdown();
    });
}


function drawFilterBlockShapes() {
    const plot = el("filterOriginalSpectrogram");
    if (!plot || !plot.data) return;

    const shapes = state.filterBlocks.map(b => {
        const color = b.enabled ? "#F5A623" : "#4A5568";
        return {
            type: "rect",
            xref: "x", yref: "y",
            x0: b.time_min,
            x1: b.time_max !== null ? b.time_max : state.duration,
            y0: b.freq_min,
            y1: b.freq_max,
            line: { color, width: 2 },
            fillcolor: b.enabled ? "rgba(245,166,35,0.10)" : "rgba(74,85,104,0.10)",
            layer: "above",
            name: b.name,
        };
    });

    Plotly.relayout(plot, { shapes });
}

async function applyFilterChain() {
    if (state.filterBlocks.length === 0) {
        setStatus("Add at least one filter block first.", "error");
        return;
    }

    const enabled = state.filterBlocks.filter(b => b.enabled);
    if (enabled.length === 0) {
        setStatus("Enable at least one filter block.", "error");
        return;
    }

    try {
        setBusy(true);
        setStatus("Applying filter chain...");

        const req = {
            source: state.source,
            sr: state.sr,
            n_fft: state.n_fft,
            hop_length: state.hop_length,
            blocks: enabled.map(b => ({
                id: b.id,
                name: b.name,
                filter_type: b.filter_type,
                freq_min: b.freq_min,
                freq_max: b.freq_max,
                time_min: b.time_min,
                time_max: b.time_max,
                gain_db: b.gain_db,
                enabled: true,
            })),
        };

        const data = await apiPost_json("/audio/filter", req);
        state.lastFilter = data;

        // Show result section
        el("filterResultSection").style.display = "block";

        // Render filtered spectrogram
        renderSpectrogram(
            "filterResultSpectrogram",
            data.freqs,
            data.times,
            data.magnitude_db_filtered,
            { selectable: false }
        );

        drawFilterBlockShapes();

        // Load filtered player
        const filteredPlayer = el("filteredPlayer");
        filteredPlayer.src = "data:audio/wav;base64," + data.audio_base64;
        filteredPlayer.load();

        // SNR + MSE readouts
        el("filterReadouts").innerHTML = `
            <div class="readout">
                <div class="readout-label">SNR</div>
                <div class="readout-value">${fmt(data.snr_db, 2, " dB")}</div>
            </div>
            <div class="readout">
                <div class="readout-label">MSE</div>
                <div class="readout-value">${data.mse.toFixed(6)}</div>
            </div>
        `;

        setStatus("Filter chain applied", "success");
    } catch (err) {
        setStatus(err.message, "error");
    } finally {
        setBusy(false);
    }
}

async function saveFilterResult() {
    if (!state.lastFilter) return;
    downloadBase64Audio(state.lastFilter.audio_base64, "filtered.wav");
    setStatus("Download started", "success");
}


// function wireFilterSelection() {
//     const plot = el("filterOriginalSpectrogram");
//     if (!plot) return;

//     plot.on("plotly_selected", (evt) => {
//         if (!evt || !evt.range) return;
//         const tSpan = evt.range.x[1] - evt.range.x[0];
//         const fSpan = evt.range.y[1] - evt.range.y[0];
//         if (tSpan < 0.01 || fSpan < 1) return;   // ignore accidental clicks

//         const tMin = Math.max(0, evt.range.x[0]);
//         const tMax = Math.min(state.duration, evt.range.x[1]);
//         const fMin = Math.max(0, evt.range.y[0]);
//         const fMax = Math.min(state.sr / 2, evt.range.y[1]);

//         // Always add a new block for each rectangle drawn
//         addFilterBlock();

//         // Now update its freq/time fields from the selection
//         const block = getSelectedFilterBlock();
//         if (!block) return;

//         block.freq_min = Math.round(fMin);
//         block.freq_max = Math.round(fMax);
//         block.time_min = parseFloat(tMin.toFixed(3));
//         block.time_max = parseFloat(tMax.toFixed(3));

//         // Sync to DOM
//         el("filterFreqMin").value = block.freq_min;
//         el("filterFreqMax").value = block.freq_max;
//         el("filterTimeMin").value = block.time_min;
//         el("filterTimeMax").value = block.time_max;

//         updateFilterBlockDropdown();

//         // Clear Plotly's selection highlight so the canvas stays clean
//         Plotly.restyle(plot, { selectedpoints: [null] });
//     });
// }



/* ---------- main analyze flow ---------- */

async function runAnalyze() {
    // reset the previous results
    resetResults();

    try {
        await resolveSource();
        state.sr = parseInt(el("srSelect").value, 10);
        state.n_fft = parseInt(el("nfftSelect").value, 10);
        state.hop_length = parseInt(el("hopSelect").value, 10);

        setBusy(true);
        setStatus("Computing STFT...");

        const data = await apiPost_json("/audio/analyze", {
            source: state.source, sr: state.sr, n_fft: state.n_fft, hop_length: state.hop_length,
        });

        state.lastAnalyze = data;
        state.melFreqs = data.mel_freqs || null;
        state.melMagnitudeDb = data.mel_magnitude_db || null;
        state.duration = data.duration;

        renderWaveform("waveformPlot", data.waveform);
        renderSpectrogram("overviewSpectrogram", data.freqs, data.times, data.magnitude_db, { selectable: false }, data.mel_freqs, data.mel_magnitude_db);
        renderSpectrogram("magSpectrogram", data.freqs, data.times, data.magnitude_db, { selectable: false }, data.mel_freqs, data.mel_magnitude_db);
        renderPhase("phasePlot", data.freqs, data.times, data.phase);
        renderSpectrogram("maskSpectrogram", data.freqs, data.times, data.magnitude_db, { selectable: false }, data.mel_freqs, data.mel_magnitude_db);
        renderSpectrogram("retainSpectrogram", data.freqs, data.times, data.magnitude_db, { selectable: false }, state.melFreqs, state.melMagnitudeDb);
        setTimeout(() => {
            const p = el("retainSpectrogram");
            if (p && p.data) Plotly.Plots.resize(p);
        }, 100);

        setAudioFromSource();

        document.querySelectorAll(".lab-tab").forEach((b) => (b.disabled = false));
        document.getElementById("emptyState").style.display = "none";
        document.getElementById("labBody").style.display = "block";

        el("sidebarStatus").textContent =
            "Loaded " + state.sourceLabel;

        el("sidebarStatus").classList.add("loaded");

        el("sidebarReadout").innerHTML =
            `file: <b>${state.sourceLabel}</b><br>` +
            `sr: <b>${data.sr} Hz</b><br>` +
            `duration: <b>${data.duration}s</b><br>` +
            `bins: <b>${data.freqs.length} x ${data.times.length}</b>`;

        setStatus("Loaded " + state.sourceLabel, "success");
    } catch (err) {
        setStatus(err.message, "error");
    } finally {
        setBusy(false);
    }
}

function setAudioFromSource() {
    const audioSrc = "/media/audio/" + state.source;

    const playerIds = [
        "originalPlayer",
        "magPhaseOriginalPlayer",
        "phaseOriginalPlayer",
        "maskOriginalPlayer",
        "retentionOriginalPlayer",
        "filterOriginalPlayer",
    ];

    playerIds.forEach((id) => {
        const player = el(id);

        if (!player) return;

        player.pause();
        player.src = audioSrc;
        player.load();
    });
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

/* ---------- magnitude / phase only playback ---------- */

async function generateComponent(mode, playerId) {
    try {
        setBusy(true);
        setStatus("Reconstructing...");
        const data = await apiPost_json("/audio/component", {
            source: state.source, sr: state.sr, n_fft: state.n_fft, hop_length: state.hop_length, mode,
        });
        el(playerId).src = "data:audio/wav;base64," + data.audio_base64;
        setStatus("Done", "success");
    } catch (err) {
        setStatus(err.message, "error");
    } finally {
        setBusy(false);
    }
}

/* ---------- masking ---------- */

async function applyMask() {
    try {
        if (state.maskRegions.length === 0) {
            setStatus("Draw at least one masking region first.", "error");
            return;
        }

        const enabledRegions = state.maskRegions.filter(r => r.enabled);
        if (enabledRegions.length === 0) {
            setStatus("Enable at least one masking region.", "error");
            return;
        }

        setBusy(true);
        setStatus("Applying mask...");

        const req = {
            source: state.source,
            sr: state.sr,
            n_fft: state.n_fft,
            hop_length: state.hop_length,
            regions: enabledRegions.map(region => ({
                vertices: region.vertices.map(v => ({ t: v.t, f: v.f })),
                mode: region.mode,
                enabled: region.enabled,
            })),
        };

        const data = await apiPost_json("/audio/mask", req);
        state.lastMask = data;

        renderSpectrogram(
            "maskResultSpectrogram",
            state.lastAnalyze.freqs,
            state.lastAnalyze.times,
            data.magnitude_db,
            { selectable: false }
        );

        const maskedPlayer = el("maskedPlayer");
        maskedPlayer.src = "data:audio/wav;base64," + data.audio_base64;
        maskedPlayer.load();

        el("maskReadouts").innerHTML = `
            <div class="readout">
                <div class="readout-label">SNR</div>
                <div class="readout-value">${fmt(data.snr_db, 2, " dB")}</div>
            </div>
            <div class="readout">
                <div class="readout-label">MSE</div>
                <div class="readout-value">${data.mse.toFixed(6)}</div>
            </div>
            <div class="readout">
                <div class="readout-label">Spectral Conv.</div>
                <div class="readout-value">${data.spectral_convergence.toFixed(4)}</div>
            </div>
        `;

        updateMetricsTab(data);
        setStatus("Mask applied", "success");

    } catch (err) {
        setStatus(err.message, "error");
    } finally {
        setBusy(false);
    }
}



function downloadBase64Audio(base64, suggestedName) {
    const filename = suggestedName || "audio.wav";

    const byteChars = atob(base64);
    const byteNumbers = new Array(byteChars.length);
    for (let i = 0; i < byteChars.length; i++) {
        byteNumbers[i] = byteChars.charCodeAt(i);
    }
    const byteArray = new Uint8Array(byteNumbers);
    const blob = new Blob([byteArray], { type: "audio/wav" });

    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);

    setTimeout(() => URL.revokeObjectURL(url), 1000);
}


async function saveMaskResult() {
    if (!state.lastMask) return;
    downloadBase64Audio(state.lastMask.audio_base64, "masked.wav");
    setStatus("Download started", "success");
}

/* ---------- progressive reconstruction ---------- */

function wireFractionSlider() {
    const slider = el("fractionSlider");
    slider.addEventListener("input", () => {
        el("fractionLabel").textContent = Math.round(slider.value * 100) + "%";
    });
}

async function applyRetention() {
    try {
        setBusy(true);
        setStatus("Reconstructing...");
        const req = {
            source: state.source, sr: state.sr, n_fft: state.n_fft, hop_length: state.hop_length,
            strategy: el("strategySelect").value, fraction: parseFloat(el("fractionSlider").value),
        };
        const data = await apiPost_json("/audio/retain", req);
        state.lastRetain = data;

        renderSpectrogram("retainResultSpectrogram", state.lastAnalyze.freqs, state.lastAnalyze.times, data.magnitude_db, { selectable: false });
        setTimeout(() => {
            const p = el("retainResultSpectrogram");
            if (p && p.data) Plotly.Plots.resize(p);
        }, 100);
        requestAnimationFrame(() => {
            const p2 = el("retainResultSpectrogram");
            if (p2 && p2.data) Plotly.Plots.resize(p2);
        });
        el("retainedPlayer").src = "data:audio/wav;base64," + data.audio_base64;
        el("retainReadout").innerHTML = `<div class="readout"><div class="readout-label">SNR</div><div class="readout-value">${fmt(data.snr_db, 2, " dB")}</div></div>`;

        setStatus("Reconstructed", "success");
    } catch (err) {
        setStatus(err.message, "error");
    } finally {
        setBusy(false);
    }
}


async function saveRetainResult() {
    if (!state.lastRetain) return;
    downloadBase64Audio(state.lastRetain.audio_base64, "retained.wav");
    setStatus("Download started", "success");
}

async function runSweep() {
    try {
        setBusy(true);
        setStatus("Running sweep across retention levels...");
        const req = {
            source: state.source, sr: state.sr, n_fft: state.n_fft, hop_length: state.hop_length,
            strategy: el("strategySelect").value,
        };
        const data = await apiPost_json("/audio/sweep", req);
        renderSweepChart("sweepChart", data.fractions, data.snr_db);
        setStatus("Sweep complete", "success");
    } catch (err) {
        setStatus(err.message, "error");
    } finally {
        setBusy(false);
    }
}

/* ---------- metrics tab ---------- */

function updateMetricsTab(data) {
    el("metricsBody").innerHTML = `
    <div class="readout-row">
      <div class="readout"><div class="readout-label">SNR</div><div class="readout-value">${fmt(data.snr_db, 2, " dB")}</div></div>
      <div class="readout"><div class="readout-label">MSE</div><div class="readout-value">${data.mse.toFixed(6)}</div></div>
      <div class="readout"><div class="readout-label">Spectral Convergence</div><div class="readout-value">${data.spectral_convergence.toFixed(4)}</div></div>
    </div>
  `;
}

/* ---------- freq scale toggle ---------- */

function wireFreqToggle() {
    document.querySelectorAll(".freq-scale-toggle").forEach((group) => {
        group.querySelectorAll(".plot-toggle").forEach((btn) => {
            btn.addEventListener("click", () => {
                group.querySelectorAll(".plot-toggle").forEach((b) => b.classList.remove("active"));
                btn.classList.add("active");
                state.freqScale = btn.dataset.scale;
                if (state.lastAnalyze) {
                    const d = state.lastAnalyze;
                    renderSpectrogram("overviewSpectrogram", d.freqs, d.times, d.magnitude_db, { selectable: false }, state.melFreqs, state.melMagnitudeDb);
                    renderSpectrogram("magSpectrogram", d.freqs, d.times, d.magnitude_db, { selectable: false }, state.melFreqs, state.melMagnitudeDb);
                    renderPhase("phasePlot", d.freqs, d.times, d.phase);  // phase stays linear, no change
                }
            });
        });
    });
}


function wireRetentionResize() {
    window.addEventListener("resize", () => {
        ["retainSpectrogram", "retainResultSpectrogram"].forEach((id) => {
            const p = el(id);
            if (p && p.data) Plotly.Plots.resize(p);
        });
    });
}


/* ---------- source mode toggle ---------- */

/* ---------- upload drag & drop ---------- */

function wireUploadDropzone() {
    const input = el("uploadInput");
    const dropzone = el("uploadDropzone");
    const fileName = el("selectedFileName");

    if (!input || !dropzone) return;

    function showSelectedFile(file) {
        if (!file) {
            fileName.textContent = "";
            fileName.style.display = "none";
            return;
        }

        fileName.textContent = "Selected: " + file.name;
        fileName.style.display = "block";
    }

    dropzone.addEventListener("click", () => {
        input.click();
    });

    input.addEventListener("change", () => {
        const file = input.files[0];

        if (file) {
            showSelectedFile(file);
        }
    });

    dropzone.addEventListener("dragenter", (event) => {
        event.preventDefault();
        event.stopPropagation();
        dropzone.classList.add("dragover");
    });

    dropzone.addEventListener("dragover", (event) => {
        event.preventDefault();
        event.stopPropagation();
        dropzone.classList.add("dragover");
    });

    dropzone.addEventListener("dragleave", (event) => {
        event.preventDefault();
        event.stopPropagation();

        if (!dropzone.contains(event.relatedTarget)) {
            dropzone.classList.remove("dragover");
        }
    });

    dropzone.addEventListener("drop", (event) => {
        event.preventDefault();
        event.stopPropagation();

        dropzone.classList.remove("dragover");

        const files = event.dataTransfer.files;

        if (!files || !files.length) return;

        const file = files[0];

        /*
         * Put the dropped file into the same file input used by
         * the existing upload flow.
         */
        const dataTransfer = new DataTransfer();
        dataTransfer.items.add(file);
        input.files = dataTransfer.files;

        showSelectedFile(file);
    });
}


function wireSourceMode() {
    document.querySelectorAll('input[name="sourceMode"]').forEach((radio) => {
        radio.addEventListener("change", () => {
            document.querySelectorAll(".source-panel").forEach((panel) => {
                panel.style.display = "none";
            });

            const activePanel = el("sourcePanel_" + radio.value);

            if (activePanel) {
                activePanel.style.display = "block";
            }
        });
    });
}

/* ---------- init ---------- */

window.addEventListener("DOMContentLoaded", () => {
    initTabs();
    wireSourceMode();
    wireUploadDropzone();
    wireFractionSlider();
    wireFreqToggle();
    wirePlaybackTracking();
    wireMaskRegionControls();
    wireFilterBlockControls();
    el("applyFilterBtn").addEventListener("click", applyFilterChain);
    el("saveFilterBtn").addEventListener("click", saveFilterResult);
    wireRetentionResize();
    refreshLibrary();

    el("analyzeBtn").addEventListener("click", runAnalyze);
    el("magOnlyBtn").addEventListener("click", () => generateComponent("magnitude_only", "magOnlyPlayer"));
    el("phaseOnlyBtn").addEventListener("click", () => generateComponent("phase_only", "phaseOnlyPlayer"));
    el("applyMaskBtn").addEventListener("click", applyMask);
    el("saveMaskBtn").addEventListener("click", saveMaskResult);
    el("applyRetentionBtn").addEventListener("click", applyRetention);
    el("saveRetainBtn").addEventListener("click", saveRetainResult);
    el("sweepBtn").addEventListener("click", runSweep);
});