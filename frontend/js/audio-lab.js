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
    document.querySelectorAll(".btn").forEach((b) => (b.disabled = busy));
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

function renderSpectrogram(containerId, freqs, times, magnitude_db, options = {}) {
    const trace = {
        x: times, y: freqs, z: magnitude_db,
        type: "heatmap", colorscale: MAGNITUDE_COLORSCALE,
        zsmooth: "best",
        colorbar: { title: "dB", titleside: "right", tickfont: { size: 10 }, thickness: 12 },
    };
    const layout = baseLayout({
        xaxis: { title: "Time (s)" },
        yaxis: { title: "Frequency (Hz)", type: state.freqScale },
        height: 320,
        dragmode: options.selectable ? "select" : "zoom",
    });


    Plotly.newPlot(containerId, [trace], layout, {
        displayModeBar: true,
        responsive: true,
        modeBarButtonsToRemove: ["lasso2d"]
    }).then(() => {
        if (playbackState.activePlayer) {
            updatePlotPlayback(containerId, playbackState.activePlayer.currentTime || 0);
        }
    });

    if (options.onSelect) {
        document.getElementById(containerId).on("plotly_selected", (evt) => {
            if (!evt || !evt.range) return;
            options.onSelect(evt.range.x, evt.range.y);
        });
    }
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

    if (!player.paused && !player.ended) {
        playbackState.animationFrame = requestAnimationFrame(updatePlaybackCursor);
    } else {
        playbackState.animationFrame = null;
    }
}


function updatePlotPlayback(plotId, currentTime) {
    const plot = el(plotId);

    if (!plot || !plot.data || !plot.layout) return;

    const duration = playbackState.activePlayer?.duration;

    if (!duration || !Number.isFinite(duration) || duration <= 0) {
        return;
    }

    const xaxis = plot.layout.xaxis;

    if (!xaxis) return;

    const range = xaxis.range;

    if (!range || range.length < 2) return;

    const xMin = range[0];
    const xMax = range[1];

    // Keep the cursor inside the displayed time range.
    const x = Math.max(xMin, Math.min(currentTime, xMax));

    const shapes = plot.layout.shapes || [];

    // Preserve any existing shapes that are not playback shapes.
    const otherShapes = shapes.filter(
        (shape) => shape.name !== "playback-cursor" && shape.name !== "playback-progress"
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
            fillcolor: "rgba(120, 130, 145, 0.10)",
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
        shapes: [...otherShapes, ...playbackShapes],
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
        "phaseOnlyPlayer",

        "maskOriginalPlayer",
        "maskedPlayer",

        "retentionOriginalPlayer",
        "retainedPlayer",
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
        "maskOriginalPlayer",
        "retentionOriginalPlayer",
        "magOnlyPlayer",
        "phaseOnlyPlayer",
        "maskedPlayer",
        "retainedPlayer",
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

    // Reset mask selection values
    el("timeMin").value = "";
    el("timeMax").value = "";
    el("freqMin").value = "";
    el("freqMax").value = "";

    // Reset status message
    setStatus("");
}

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
        state.duration = data.duration;

        renderWaveform("waveformPlot", data.waveform);
        renderSpectrogram("overviewSpectrogram", data.freqs, data.times, data.magnitude_db, { selectable: false });
        renderSpectrogram("magSpectrogram", data.freqs, data.times, data.magnitude_db, { selectable: false });
        renderPhase("phasePlot", data.freqs, data.times, data.phase);
        renderSpectrogram("maskSpectrogram", data.freqs, data.times, data.magnitude_db, {
            selectable: true,
            onSelect: (xr, yr) => {
                el("timeMin").value = Math.max(0, xr[0]).toFixed(2);
                el("timeMax").value = Math.min(state.duration, xr[1]).toFixed(2);
                el("freqMin").value = Math.max(0, yr[0]).toFixed(0);
                el("freqMax").value = Math.min(data.sr / 2, yr[1]).toFixed(0);
            },
        });
        renderSpectrogram("retainSpectrogram", data.freqs, data.times, data.magnitude_db, { selectable: false });

        setAudioFromSource();

        el("timeMin").max = data.duration; el("timeMax").max = data.duration; el("timeMax").value = data.duration.toFixed(2);
        el("freqMax").max = data.sr / 2; el("freqMax").value = (data.sr / 2).toFixed(0);

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

async function setAudioFromSource() {
    const audioSrc = "/media/audio/" + state.source;

    // Overview
    el("originalPlayer").src = audioSrc;

    // Magnitude & Phase
    el("magPhaseOriginalPlayer").src = audioSrc;

    // Masking
    el("maskOriginalPlayer").src = audioSrc;

    // Retention
    el("retentionOriginalPlayer").src = audioSrc;
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
        setBusy(true);
        setStatus("Applying mask...");
        const mode = document.querySelector('input[name="maskMode"]:checked').value;
        const req = {
            source: state.source, sr: state.sr, n_fft: state.n_fft, hop_length: state.hop_length,
            freq_min: parseFloat(el("freqMin").value), freq_max: parseFloat(el("freqMax").value),
            time_min: parseFloat(el("timeMin").value), time_max: parseFloat(el("timeMax").value),
            mode,
        };
        const data = await apiPost_json("/audio/mask", req);
        state.lastMask = data;

        renderSpectrogram("maskResultSpectrogram", state.lastAnalyze.freqs, state.lastAnalyze.times, data.magnitude_db, { selectable: false });
        el("maskedPlayer").src = "data:audio/wav;base64," + data.audio_base64;

        el("maskReadouts").innerHTML = `
      <div class="readout"><div class="readout-label">SNR</div><div class="readout-value">${fmt(data.snr_db, 2, " dB")}</div></div>
      <div class="readout"><div class="readout-label">MSE</div><div class="readout-value">${data.mse.toFixed(6)}</div></div>
      <div class="readout"><div class="readout-label">Spectral Conv.</div><div class="readout-value">${data.spectral_convergence.toFixed(4)}</div></div>
    `;
        updateMetricsTab(data);
        setStatus("Mask applied", "success");
    } catch (err) {
        setStatus(err.message, "error");
    } finally {
        setBusy(false);
    }
}

async function saveMaskResult() {
    if (!state.lastMask) return;
    const data = await apiPost_json("/audio/save", { audio_base64: state.lastMask.audio_base64, label: "masked" });
    setStatus("Saved as " + data.filename, "success");
    refreshLibrary();
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
    const data = await apiPost_json("/audio/save", { audio_base64: state.lastRetain.audio_base64, label: "retained" });
    setStatus("Saved as " + data.filename, "success");
    refreshLibrary();
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
                    renderSpectrogram("overviewSpectrogram", d.freqs, d.times, d.magnitude_db, { selectable: false });
                    renderSpectrogram("magSpectrogram", d.freqs, d.times, d.magnitude_db, { selectable: false });
                    renderPhase("phasePlot", d.freqs, d.times, d.phase);
                }
            });
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