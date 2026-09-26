/* =========================================================
   Music Lab — state
   ========================================================= */

const state = {
    // Separate tab
    separateFile: null,
    separateSource: null,
    separateResult: null, // { original, vocal, instrumental }

    // Mix tab
    mixInstrumentalSource: null,
    mixVocalSource: null,
    mixInstrumentalGenerated: false,
    mixVocalGenerated: false,
    suggestedOffset: null,
    lastMixResult: null,
};

const abortControllers = {
    separate: null,
    mix: null,
    suggestOffset: null,
};

function setOffsetBusy(busy) {
    const btn = el("suggestOffsetBtn");
    if (btn) btn.disabled = busy;
}

function setMixBusy(busy) {
    const btn = el("mixBtn");
    if (btn) btn.disabled = busy;
}

function toggleCancelButton(btnId, show) {
    const btn = el(btnId);
    if (btn) btn.style.display = show ? "inline-block" : "none";
}

/*
 * Each player is tracked independently: its own plot IDs,
 * its own animation frame handle. No shared "activePlayer".
 */
const PLAYER_PLOT_MAP = {
    separateOriginalPlayer: ["separateOriginalWaveform", "separateOriginalSpectrogram"],
    vocalPlayer: ["vocalWaveform", "vocalSpectrogram"],
    instrumentalPlayer: ["instrumentalWaveform", "instrumentalSpectrogram"],
    mixInstrumentalPlayer: ["mixInstrumentalWaveform", "mixInstrumentalSpectrogram"],
    mixVocalPlayer: ["mixVocalWaveform", "mixVocalSpectrogram"],
    mixedPlayer: ["mixedWaveform", "mixedSpectrogram"],
};

function drawCursorIfOwnerActive(plotId) {
    const ownerId = Object.keys(PLAYER_PLOT_MAP).find((pid) =>
        PLAYER_PLOT_MAP[pid].includes(plotId)
    );
    if (!ownerId) return;

    const player = el(ownerId);
    if (player && player.currentTime > 0) {
        updatePlotPlayback(plotId, player.currentTime, player.duration);
    }
}

/*
 * playbackState[playerId] = { animationFrame }
 * Populated lazily as players start playing/seeking.
 */
const playbackState = {};

function getPlaybackEntry(playerId) {
    if (!playbackState[playerId]) {
        playbackState[playerId] = { animationFrame: null };
    }
    return playbackState[playerId];
}

function el(id) { return document.getElementById(id); }

/* =========================================================
   status / busy helpers
   ========================================================= */

function setStatus(message, type = "info", tab = "separate") {
    const boxId = tab === "mix" ? "statusBoxMix" : "statusBoxSeparate";
    const box = el(boxId);
    if (!box) return;
    box.textContent = message;
    box.className = "status-msg" + (type === "error" ? " status-error" : type === "success" ? " status-success" : "");
    box.style.display = message ? "block" : "none";
}

function setBusy(busy) {
    document.querySelectorAll(".btn").forEach((b) => {
        if (b.id === "cancelSeparateBtn" || b.id === "cancelMixBtn" || b.id === "cancelSuggestOffsetBtn") return;
        b.disabled = busy;
    });
}

/*
 * Re-derives each button's enabled/disabled state from `state`.
 * Called after setBusy(false) so busy-disabling doesn't leave
 * buttons that should still be disabled (e.g. Mix before both
 * stems are loaded) incorrectly enabled.
 */
function refreshButtonStates() {
    el("separateBtn").disabled = !state.separateFile && !state.separateSource;

    const bothLoaded = !!(state.mixInstrumentalSource && state.mixVocalSource);

    el("mixBtn").disabled = !bothLoaded;
    el("suggestOffsetBtn").disabled = !bothLoaded;
}

/* =========================================================
   API helpers & Library loading
   ========================================================= */

async function apiPost_json(path, body, signal) {
    const res = await fetch(API_BASE + path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal,
    });
    if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail.detail || `Request to ${path} failed (${res.status})`);
    }
    return res.json();
}

async function uploadAudioFile(file) {
    const form = new FormData();
    form.append("file", file);
    const res = await apiPost("/audio/upload", form);
    return res.source;
}

async function refreshMusicLibrary() {
    try {
        const data = await apiGet("/audio/library");
        const options = ['<option value="">-- Select from library --</option>']
            .concat(data.samples.map((f) => `<option value="${f}">${f}</option>`))
            .join("");

        ["separateLibrarySelect", "mixInstrumentalLibrarySelect", "mixVocalLibrarySelect"].forEach((id) => {
            const select = el(id);
            if (select) select.innerHTML = options;
        });
    } catch (err) {
        console.error("Failed to load music library:", err);
    }
}

async function handleLibrarySelect(slot, filename) {
    if (!filename) return;
    const source = "samples/" + filename;

    if (slot === "separate") {
        state.separateFile = null;
        state.separateSource = source;

        const label = el("separateSelectedFileName");
        if (label) {
            label.textContent = "Selected: " + filename;
            label.style.display = "block";
        }

        updateSidebarSeparate();
        refreshButtonStates();
    } else if (slot === "instrumental") {
        state.mixInstrumentalSource = source;
        state.mixInstrumentalGenerated = false;

        const player = el("mixInstrumentalPlayer");
        if (player) {
            player.src = "/media/audio/" + source;
            player.load();
        }

        const label = el("mixInstrumentalFileName");
        if (label) {
            label.textContent = "Selected: " + filename;
            label.style.display = "block";
        }

        updateSidebarMix();
        refreshButtonStates();
        await renderMixSlotVisuals("instrumental", source);
    } else if (slot === "vocal") {
        state.mixVocalSource = source;
        state.mixVocalGenerated = false;

        const player = el("mixVocalPlayer");
        if (player) {
            player.src = "/media/audio/" + source;
            player.load();
        }

        const label = el("mixVocalFileName");
        if (label) {
            label.textContent = "Selected: " + filename;
            label.style.display = "block";
        }

        updateSidebarMix();
        refreshButtonStates();
        await renderMixSlotVisuals("vocal", source);
    }
}

async function renderMixSlotVisuals(slot, source) {
    try {
        const data = await apiPost_json("/audio/analyze", {
            source, sr: 22050, n_fft: 2048, hop_length: 512,
        });
        const wfId = slot === "instrumental" ? "mixInstrumentalWaveform" : "mixVocalWaveform";
        const specId = slot === "instrumental" ? "mixInstrumentalSpectrogram" : "mixVocalSpectrogram";
        renderWaveform(wfId, data.waveform);
        renderSpectrogram(specId, data.freqs, data.times, data.magnitude_db);
    } catch (err) {
        console.error("Visualization failed:", err);
    }
}

/* =========================================================
   Playback cursor
   ========================================================= */

/*
 * Update the cursor (vertical line + progress shading) on a
 * single Plotly plot. Duration is now passed in explicitly by
 * the caller (read from that plot's OWN owning player), instead
 * of relying on a removed global `playbackState.activePlayer`.
 */
function updatePlotPlayback(plotId, currentTime, duration) {
    const plot = el(plotId);

    if (!plot || !plot.data || !plot.layout) {
        return;
    }

    if (!duration || !Number.isFinite(duration) || duration <= 0) {
        return;
    }

    const xaxis = plot.layout.xaxis;
    if (!xaxis) return;

    const range = xaxis.range;
    if (!range || range.length < 2) return;

    const xMin = range[0];
    const xMax = range[1];

    const x = Math.max(xMin, Math.min(currentTime, xMax));

    const shapes = plot.layout.shapes || [];

    const persistentShapes = shapes.filter(
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
            fillcolor: "rgba(120, 130, 145, 0.10)",
            line: { width: 0 },
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
            line: { color: "#F5F7FA", width: 2 },
            layer: "above",
        },
    ];

    Plotly.relayout(plot, {
        shapes: [...persistentShapes, ...playbackShapes],
    });
}

/*
 * rAF loop — runs while a player is active and playing.
 * Reads duration from THIS player only (fixes the bug where
 * updatePlotPlayback referenced a removed global player).
 */
function updatePlaybackCursor(playerId) {
    const player = el(playerId);
    if (!player) return;

    const entry = getPlaybackEntry(playerId);
    const plotIds = PLAYER_PLOT_MAP[playerId] || [];

    const currentTime = player.currentTime || 0;
    const duration = player.duration;

    plotIds.forEach((id) => updatePlotPlayback(id, currentTime, duration));

    if (!player.paused && !player.ended) {
        entry.animationFrame = requestAnimationFrame(() => updatePlaybackCursor(playerId));
    } else {
        entry.animationFrame = null;
    }
}

function startPlaybackTracking(playerId) {
    const entry = getPlaybackEntry(playerId);

    if (entry.animationFrame) {
        cancelAnimationFrame(entry.animationFrame);
        entry.animationFrame = null;
    }

    updatePlaybackCursor(playerId);
}

function wirePlaybackPlayer(playerId) {
    const player = el(playerId);
    if (!player) return;

    player.addEventListener("play", () => startPlaybackTracking(playerId));
    player.addEventListener("timeupdate", () => startPlaybackTracking(playerId));
    player.addEventListener("seeking", () => startPlaybackTracking(playerId));
    player.addEventListener("seeked", () => startPlaybackTracking(playerId));

    player.addEventListener("pause", () => updatePlaybackCursor(playerId));
    player.addEventListener("ended", () => updatePlaybackCursor(playerId));
}

function wireMusicPlaybackTracking() {
    [
        "separateOriginalPlayer",
        "vocalPlayer",
        "instrumentalPlayer",
        "mixInstrumentalPlayer",
        "mixVocalPlayer",
        "mixedPlayer",
    ].forEach(wirePlaybackPlayer);
}

/* =========================================================
   Plotting — waveform & spectrogram
   ========================================================= */

const MAGNITUDE_COLORSCALE = "Viridis";

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
    const traceMax = {
        x: waveform.time, y: waveform.max,
        mode: "lines", line: { width: 1, color: "#FFB454" }, name: "max",
    };
    const traceMin = {
        x: waveform.time, y: waveform.min,
        mode: "lines", line: { width: 1, color: "#FFB454" },
        fill: "tonexty", fillcolor: "rgba(255,180,84,0.25)", name: "min",
    };
    const layout = baseLayout({
        xaxis: { title: "Time (s)" },
        yaxis: { title: "Amplitude", range: [-1.05, 1.05] },
        showlegend: false,
        height: 160,
    });

    Plotly.newPlot(containerId, [traceMax, traceMin], layout, {
        displayModeBar: false,
        responsive: true,
    }).then(() => {
        drawCursorIfOwnerActive(containerId);
    });
}

function renderSpectrogram(containerId, freqs, times, magnitude_db) {
    const trace = {
        x: times,
        y: freqs,
        z: magnitude_db,
        type: "heatmap",
        colorscale: MAGNITUDE_COLORSCALE,
        zsmooth: "best",
        colorbar: { title: "dB", titleside: "right", tickfont: { size: 10 }, thickness: 12 },
    };
    const layout = baseLayout({
        xaxis: { title: "Time (s)" },
        yaxis: { title: "Frequency (Hz)" },
        height: 260,
    });

    Plotly.newPlot(containerId, [trace], layout, {
        displayModeBar: false,
        responsive: true,
    }).then(() => {
        drawCursorIfOwnerActive(containerId);
    });
}

/* =========================================================
   Sidebar summary helpers
   ========================================================= */

function shortName(source) {
    return source ? source.split("/").pop() : "—";
}

function updateSidebarSeparate() {
    if (state.separateFile) {
        el("sbSeparateInput").textContent = state.separateFile.name;
    } else if (state.separateSource) {
        el("sbSeparateInput").textContent = shortName(state.separateSource);
    }
    if (state.separateResult) {
        el("sbSeparateVocal").textContent = shortName(state.separateResult.vocal.source);
        el("sbSeparateInst").textContent = shortName(state.separateResult.instrumental.source);
        el("sbSeparateResults").style.display = "block";
    }
}

function updateSidebarMix() {
    el("sbMixInst").textContent = state.mixInstrumentalSource ? shortName(state.mixInstrumentalSource) : "—";
    el("sbMixVocal").textContent = state.mixVocalSource ? shortName(state.mixVocalSource) : "—";
    if (state.lastMixResult) {
        el("sbMixResult").textContent = shortName(state.lastMixResult.mixed.source);
        el("sbMixResultRow").style.display = "block";
    }
}

/* =========================================================
   top-level tabs (Separate / Mix)
   ========================================================= */

function initToplevelTabs() {
    document.querySelectorAll(".lab-tab").forEach((tabBtn) => {
        tabBtn.addEventListener("click", () => switchToplevelTab(tabBtn.dataset.target));
    });
}

function switchToplevelTab(targetId) {
    document.querySelectorAll(".lab-tab").forEach((b) => {
        b.classList.toggle("active", b.dataset.target === targetId);
    });
    document.querySelectorAll(".lab-panel").forEach((p) => {
        p.classList.toggle("active", p.id === targetId);
    });

    // Plotly sizes plots based on their container's dimensions at
    // render time. Plots rendered while their tab was inactive
    // (display:none) can end up with zero width/height. Force a
    // resize on every plot once its tab becomes visible again.
    if (targetId === "tabSeparate") {
        ["separateOriginalWaveform", "separateOriginalSpectrogram", "vocalWaveform", "vocalSpectrogram", "instrumentalWaveform", "instrumentalSpectrogram"]
            .forEach((id) => {
                const plot = el(id);
                if (plot && plot.data) Plotly.Plots.resize(plot);
            });
    } else if (targetId === "tabMix") {
        ["mixInstrumentalWaveform", "mixInstrumentalSpectrogram", "mixVocalWaveform", "mixVocalSpectrogram", "mixedWaveform", "mixedSpectrogram"]
            .forEach((id) => {
                const plot = el(id);
                if (plot && plot.data) Plotly.Plots.resize(plot);
            });
    }
}

/* =========================================================
   generic dropzone wiring
   ========================================================= */

function wireDropzone(inputId, dropzoneId, onFileSelected) {
    const input = el(inputId);
    const dropzone = el(dropzoneId);

    if (!input || !dropzone) return;

    dropzone.addEventListener("click", () => input.click());

    input.addEventListener("change", () => {
        const file = input.files[0];
        if (file) onFileSelected(file);
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

        const dataTransfer = new DataTransfer();
        dataTransfer.items.add(file);
        input.files = dataTransfer.files;

        onFileSelected(file);
    });
}

function cancelSeparate() {
    if (abortControllers.separate) {
        abortControllers.separate.abort();
    }
}

function cancelMix() {
    if (abortControllers.mix) {
        abortControllers.mix.abort();
    }
}

function cancelSuggestOffset() {
    if (abortControllers.suggestOffset) {
        abortControllers.suggestOffset.abort();
    }
}

/* =========================================================
   Tab 1 — Separate
   ========================================================= */

function handleSeparateFileSelected(file) {
    state.separateFile = file;
    state.separateSource = null;

    const label = el("separateSelectedFileName");
    if (label) {
        label.textContent = "Selected: " + file.name;
        label.style.display = "block";
    }

    updateSidebarSeparate();
    refreshButtonStates();
}

/*
 * Renders (or re-renders) the Separate tab's main-stage results
 * from state.separateResult. Pulled out into its own function so
 * it can run both right after a fresh /music/separate response,
 * AND whenever the user returns to a tab where results should
 * already be showing but the plots need to be (re)painted.
 */
function renderSeparateResults() {
    const data = state.separateResult;
    if (!data) return;

    // Original
    renderWaveform("separateOriginalWaveform", data.original.waveform);
    renderSpectrogram(
        "separateOriginalSpectrogram",
        data.original.spectrogram.freq,
        data.original.spectrogram.time,
        data.original.spectrogram.z
    );
    const originalPlayer = el("separateOriginalPlayer");
    if (originalPlayer) {
        originalPlayer.src = "/media/audio/" + data.original.source;
        originalPlayer.load();
    }
    el("separateOriginalBlock").style.display = "block";

    // Vocal
    renderWaveform("vocalWaveform", data.vocal.waveform);
    renderSpectrogram(
        "vocalSpectrogram",
        data.vocal.spectrogram.freq,
        data.vocal.spectrogram.time,
        data.vocal.spectrogram.z
    );
    const vocalPlayer = el("vocalPlayer");
    if (vocalPlayer) {
        vocalPlayer.src = "/media/audio/" + data.vocal.source;
        vocalPlayer.load();
    }
    const vocalDownload = el("vocalDownloadLink");
    if (vocalDownload) vocalDownload.href = "/media/audio/" + data.vocal.source;

    // Instrumental
    renderWaveform("instrumentalWaveform", data.instrumental.waveform);
    renderSpectrogram(
        "instrumentalSpectrogram",
        data.instrumental.spectrogram.freq,
        data.instrumental.spectrogram.time,
        data.instrumental.spectrogram.z
    );
    const instrumentalPlayer = el("instrumentalPlayer");
    if (instrumentalPlayer) {
        instrumentalPlayer.src = "/media/audio/" + data.instrumental.source;
        instrumentalPlayer.load();
    }
    const instrumentalDownload = el("instrumentalDownloadLink");
    if (instrumentalDownload) instrumentalDownload.href = "/media/audio/" + data.instrumental.source;

    // Show vertical stack
    el("separateResultsStack").style.display = "flex";
}

async function runSeparate() {
    if (!state.separateFile && !state.separateSource) {
        setStatus("Choose an audio file first.", "error");
        return;
    }

    const controller = new AbortController();
    abortControllers.separate = controller;

    try {
        setBusy(true);
        toggleCancelButton("cancelSeparateBtn", true);

        let source;
        if (state.separateFile) {
            setStatus("Uploading...");
            source = await uploadAudioFile(state.separateFile);
        } else {
            source = state.separateSource;
        }

        setStatus("Separating vocals and instrumental — this can take a while...");

        const data = await apiPost_json("/music/separate", { source }, controller.signal);
        state.separateResult = data;

        renderSeparateResults();

        updateSidebarSeparate();
        setStatus("Separation complete.", "success");
    } catch (err) {
        if (err.name === "AbortError") {
            setStatus("Separation cancelled.", "info");
        } else {
            setStatus(err.message, "error");
        }
    } finally {
        setBusy(false);
        toggleCancelButton("cancelSeparateBtn", false);
        abortControllers.separate = null;
        refreshButtonStates();
    }
}

/*
 * Hands a stem produced on Tab 1 off to Tab 2's mixer slots,
 * without requiring the user to re-upload it.
 */
function sendToMixer(stem) {
    const result = state.separateResult;
    if (!result) return;

    const stemData = result[stem]; // "vocal" | "instrumental"
    if (!stemData) return;

    if (stem === "vocal") {
        state.mixVocalSource = stemData.source;
        state.mixVocalGenerated = true;

        const player = el("mixVocalPlayer");
        if (player) {
            player.src = "/media/audio/" + stemData.source;
            player.load();
        }

        const label = el("mixVocalFileName");
        if (label) {
            label.textContent = "From Separate tab: " + shortName(stemData.source);
            label.style.display = "block";
        }
    } else {
        state.mixInstrumentalSource = stemData.source;
        state.mixInstrumentalGenerated = true;

        const player = el("mixInstrumentalPlayer");
        if (player) {
            player.src = "/media/audio/" + stemData.source;
            player.load();
        }

        const label = el("mixInstrumentalFileName");
        if (label) {
            label.textContent = "From Separate tab: " + shortName(stemData.source);
            label.style.display = "block";
        }
    }

    updateSidebarMix();
    switchToplevelTab("tabMix");
    refreshButtonStates();
    renderMixSlotVisuals(stem, stemData.source);
}

/* =========================================================
   Tab 2 — Mix
   ========================================================= */

async function handleMixFileSelected(slot, file) {
    try {
        setBusy(true);
        setStatus("Uploading " + slot + "...", "mix");

        const source = await uploadAudioFile(file);

        if (slot === "instrumental") {
            state.mixInstrumentalSource = source;
            state.mixInstrumentalGenerated = false;

            const player = el("mixInstrumentalPlayer");
            if (player) {
                player.src = "/media/audio/" + source;
                player.load();
            }

            const label = el("mixInstrumentalFileName");
            if (label) {
                label.textContent = "Selected: " + file.name;
                label.style.display = "block";
            }
        } else {
            state.mixVocalSource = source;
            state.mixVocalGenerated = false;

            const player = el("mixVocalPlayer");
            if (player) {
                player.src = "/media/audio/" + source;
                player.load();
            }

            const label = el("mixVocalFileName");
            if (label) {
                label.textContent = "Selected: " + file.name;
                label.style.display = "block";
            }
        }

        updateSidebarMix();
        setStatus("", "info", "mix");
        await renderMixSlotVisuals(slot, source);
    } catch (err) {
        setStatus(err.message, "error", "mix");
    } finally {
        setBusy(false);
        refreshButtonStates();
    }
}

async function runSuggestOffset() {
    if (!state.mixInstrumentalSource || !state.mixVocalSource) {
        setStatus("Load both an instrumental and a vocal first.", "error", "mix");
        return;
    }

    const controller = new AbortController();
    abortControllers.suggestOffset = controller;

    try {
        setOffsetBusy(true);
        toggleCancelButton("cancelSuggestOffsetBtn", true);
        setStatus("Computing suggested offset...", "", "mix");

        const data = await apiPost_json(
            "/music/suggest-offset",
            {
                instrumental_source: state.mixInstrumentalSource,
                vocal_source: state.mixVocalSource,
            },
            controller.signal
        );

        state.suggestedOffset = data.suggested_offset_sec;

        el("suggestedOffsetReadout").textContent = data.suggested_offset_sec.toFixed(3) + " s";
        el("offsetInput").value = data.suggested_offset_sec.toFixed(3);

        setStatus("Suggested offset computed.", "success", "mix");
    } catch (err) {
        if (err.name === "AbortError") {
            setStatus("Offset suggestion cancelled.", "info", "mix");
        } else {
            setStatus(err.message, "error", "mix");
        }
    } finally {
        setOffsetBusy(false);
        toggleCancelButton("cancelSuggestOffsetBtn", false);
        abortControllers.suggestOffset = null;
    }
}

async function runMix() {
    if (!state.mixInstrumentalSource || !state.mixVocalSource) {
        setStatus("Load both an instrumental and a vocal first.", "error", "mix");
        return;
    }

    const controller = new AbortController();
    abortControllers.mix = controller;

    try {
        setMixBusy(true);
        toggleCancelButton("cancelMixBtn", true);
        setStatus("Mixing...", "", "mix");

        const req = {
            instrumental_source: state.mixInstrumentalSource,
            vocal_source: state.mixVocalSource,
            instrumental_gain_db: parseFloat(el("instrumentalGainSlider").value),
            vocal_gain_db: parseFloat(el("vocalGainSlider").value),
            offset_sec: parseFloat(el("offsetInput").value) || 0,
        };

        const data = await apiPost_json("/music/mix", req, controller.signal);
        state.lastMixResult = data;

        renderWaveform("mixedWaveform", data.mixed.waveform);
        renderSpectrogram(
            "mixedSpectrogram",
            data.mixed.spectrogram.freq,
            data.mixed.spectrogram.time,
            data.mixed.spectrogram.z
        );

        const mixedPlayer = el("mixedPlayer");
        if (mixedPlayer) {
            mixedPlayer.src = "/media/audio/" + data.mixed.source;
            mixedPlayer.load();
        }

        const downloadLink = el("mixedDownloadLink");
        if (downloadLink) {
            downloadLink.href = "/media/audio/" + data.mixed.source;
        }

        const mixResultBlock = el("mixResultBlock");
        if (mixResultBlock) {
            mixResultBlock.style.display = "block";
        }

        updateSidebarMix();
        setStatus("Mix complete.", "success", "mix");
    } catch (err) {
        if (err.name === "AbortError") {
            setStatus("Mix cancelled.", "info", "mix");
        } else {
            setStatus(err.message, "error", "mix");
        }
    } finally {
        setMixBusy(false);
        toggleCancelButton("cancelMixBtn", false);
        abortControllers.mix = null;
    }
}

/* =========================================================
   gain sliders
   ========================================================= */

function wireGainSlider(sliderId, labelId) {
    const slider = el(sliderId);
    const label = el(labelId);
    if (!slider || !label) return;

    const update = () => {
        const value = parseFloat(slider.value);
        label.textContent = (value > 0 ? "+" : "") + value.toFixed(1) + " dB";
    };

    slider.addEventListener("input", update);
    update();
}

/* =========================================================
   Apply Masking — save unsaved files, then hand off to Audio Lab
   ========================================================= */

function showSaveModal(defaultLabel) {
    return new Promise((resolve) => {
        const overlay = el("saveModalOverlay");
        const card = overlay.querySelector(".save-modal-card");
        const input = el("saveModalLabelInput");
        const fileLabel = el("saveModalFileLabel");
        const saveBtn = el("saveModalSaveBtn");
        const skipBtn = el("saveModalSkipBtn");
        const closeBtn = el("saveModalCloseBtn");

        fileLabel.textContent = defaultLabel;
        input.value = defaultLabel;
        overlay.style.display = "flex";
        input.focus();

        function cleanup(result) {
            overlay.style.display = "none";
            saveBtn.removeEventListener("click", onSave);
            skipBtn.removeEventListener("click", onSkip);
            closeBtn.removeEventListener("click", onSkip);
            overlay.removeEventListener("click", onOverlayClick);
            resolve(result);
        }

        function onSave() {
            const label = input.value.trim() || defaultLabel;
            cleanup({ save: true, label });
        }

        function onSkip() {
            cleanup({ save: false });
        }

        function onOverlayClick(event) {
            if (!card.contains(event.target)) {
                onSkip();
            }
        }

        saveBtn.addEventListener("click", onSave);
        skipBtn.addEventListener("click", onSkip);
        closeBtn.addEventListener("click", onSkip);
        overlay.addEventListener("click", onOverlayClick);
    });
}

async function saveGeneratedFile(source, defaultLabel) {
    const choice = await showSaveModal(defaultLabel);
    if (!choice.save) {
        return source;
    }

    const audioRes = await fetch("/media/audio/" + source);
    const blob = await audioRes.blob();
    const audio_base64 = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result.split(",")[1]);
        reader.onerror = reject;
        reader.readAsDataURL(blob);
    });

    const data = await apiPost_json("/audio/save", { audio_base64, label: choice.label });
    return "saved/" + data.filename;
}

function goToAudioLab(source) {
    sessionStorage.setItem("pendingSource", source);
    window.location.href = "audio-lab.html";
}

async function applyMasking(kind) {
    const tab = kind === "mixed" ? "mix" : "separate";

    try {
        setBusy(true);

        if (kind === "vocal" || kind === "instrumental") {
            const result = state.separateResult;
            if (!result) throw new Error("No separation result yet.");

            let vocalSource = result.vocal.source;
            let instrumentalSource = result.instrumental.source;

            if (kind === "vocal") {
                instrumentalSource = await saveGeneratedFile(instrumentalSource, "instrumental");
                vocalSource = await saveGeneratedFile(vocalSource, "vocal");
                goToAudioLab(vocalSource);
            } else {
                vocalSource = await saveGeneratedFile(vocalSource, "vocal");
                instrumentalSource = await saveGeneratedFile(instrumentalSource, "instrumental");
                goToAudioLab(instrumentalSource);
            }
            return;
        }

        if (!state.lastMixResult) throw new Error("No mix result yet.");

        if (state.mixInstrumentalGenerated) {
            state.mixInstrumentalSource = await saveGeneratedFile(state.mixInstrumentalSource, "instrumental");
            state.mixInstrumentalGenerated = false;
        }
        if (state.mixVocalGenerated) {
            state.mixVocalSource = await saveGeneratedFile(state.mixVocalSource, "vocal");
            state.mixVocalGenerated = false;
        }

        const mixedSaved = await saveGeneratedFile(state.lastMixResult.mixed.source, "mixed");
        goToAudioLab(mixedSaved);

    } catch (err) {
        setStatus(err.message, "error", tab);
    } finally {
        setBusy(false);
    }
}

/* =========================================================
   init
   ========================================================= */
window.addEventListener("DOMContentLoaded", () => {
    initToplevelTabs();

    wireMusicPlaybackTracking();

    refreshMusicLibrary();

    wireDropzone("separateUploadInput", "separateDropzone", handleSeparateFileSelected);
    wireDropzone("mixInstrumentalInput", "mixInstrumentalDropzone", (file) => handleMixFileSelected("instrumental", file));
    wireDropzone("mixVocalInput", "mixVocalDropzone", (file) => handleMixFileSelected("vocal", file));

    const sepLibSelect = el("separateLibrarySelect");
    if (sepLibSelect) sepLibSelect.addEventListener("change", (e) => handleLibrarySelect("separate", e.target.value));

    const mixInstLibSelect = el("mixInstrumentalLibrarySelect");
    if (mixInstLibSelect) mixInstLibSelect.addEventListener("change", (e) => handleLibrarySelect("instrumental", e.target.value));

    const mixVocLibSelect = el("mixVocalLibrarySelect");
    if (mixVocLibSelect) mixVocLibSelect.addEventListener("change", (e) => handleLibrarySelect("vocal", e.target.value));

    wireGainSlider("instrumentalGainSlider", "instrumentalGainLabel");
    wireGainSlider("vocalGainSlider", "vocalGainLabel");

    el("separateBtn").addEventListener("click", runSeparate);
    el("useVocalInMixerBtn").addEventListener("click", () => sendToMixer("vocal"));
    el("useInstrumentalInMixerBtn").addEventListener("click", () => sendToMixer("instrumental"));
    el("suggestOffsetBtn").addEventListener("click", runSuggestOffset);
    el("mixBtn").addEventListener("click", runMix);

    const applyVocBtn = el("applyMaskingVocalBtn");
    if (applyVocBtn) applyVocBtn.addEventListener("click", () => applyMasking("vocal"));

    const applyInstBtn = el("applyMaskingInstrumentalBtn");
    if (applyInstBtn) applyInstBtn.addEventListener("click", () => applyMasking("instrumental"));

    const applyMixBtn = el("applyMaskingMixedBtn");
    if (applyMixBtn) applyMixBtn.addEventListener("click", () => applyMasking("mixed"));

    const cancelSepBtn = el("cancelSeparateBtn");
    if (cancelSepBtn) cancelSepBtn.addEventListener("click", cancelSeparate);

    const cancelSuggestBtn = el("cancelSuggestOffsetBtn");
    if (cancelSuggestBtn) cancelSuggestBtn.addEventListener("click", cancelSuggestOffset);

    const cancelMixBtn = el("cancelMixBtn");
    if (cancelMixBtn) cancelMixBtn.addEventListener("click", cancelMix);

    refreshButtonStates();
});