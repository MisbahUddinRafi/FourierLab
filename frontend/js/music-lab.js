/* =========================================================
   Music Lab — state
   ========================================================= */

const state = {
    // Separate tab
    separateFile: null,
    separateResult: null, // { original, vocal, instrumental }

    // Mix tab
    mixInstrumentalSource: null,
    mixVocalSource: null,
    suggestedOffset: null,
    lastMixResult: null,
};

/*
 * Playback cursor state — mirrors audio-lab.js pattern exactly.
 * Each Music Lab plot that has a time axis gets a live cursor
 * drawn via Plotly shapes whenever a player is active.
 */
const playbackState = {
    activePlayer: null,
    animationFrame: null,
};

/*
 * All Plotly plot IDs in Music Lab that carry a time (x) axis
 * and should receive the playback cursor.
 */
const MUSIC_PLOT_IDS = [
    "separateOriginalWaveform",
    "separateOriginalSpectrogram",
    "vocalWaveform",
    "vocalSpectrogram",
    "instrumentalWaveform",
    "instrumentalSpectrogram",
    "mixedWaveform",
];

function el(id) { return document.getElementById(id); }

/* =========================================================
   status / busy helpers
   ========================================================= */

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

/*
 * Re-derives each button's enabled/disabled state from `state`.
 * Called after setBusy(false) so busy-disabling doesn't leave
 * buttons that should still be disabled (e.g. Mix before both
 * stems are loaded) incorrectly enabled.
 */
function refreshButtonStates() {
    el("separateBtn").disabled = !state.separateFile;

    const bothLoaded = !!(state.mixInstrumentalSource && state.mixVocalSource);

    el("mixBtn").disabled = !bothLoaded;
    el("suggestOffsetBtn").disabled = !bothLoaded;
}

/* =========================================================
   API helpers
   ========================================================= */

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

async function uploadAudioFile(file) {
    const form = new FormData();
    form.append("file", file);
    const res = await apiPost("/audio/upload", form);
    return res.source;
}

/* =========================================================
   Playback cursor — ported from audio-lab.js
   ========================================================= */

/*
 * Update the cursor (vertical line + progress shading) on a
 * single Plotly plot.  Identical logic to audio-lab.js
 * updatePlotPlayback(), but reads duration from the Music Lab
 * player's own .duration attribute so the two labs are fully
 * independent.
 */
function updatePlotPlayback(plotId, currentTime) {
    const plot = el(plotId);

    if (!plot || !plot.data || !plot.layout) {
        return;
    }

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

    const x = Math.max(xMin, Math.min(currentTime, xMax));

    const shapes = plot.layout.shapes || [];

    // Keep any non-playback shapes (none expected in Music Lab
    // plots, but safe to preserve them).
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
 */
function updatePlaybackCursor() {
    const player = playbackState.activePlayer;
    if (!player) return;

    const currentTime = player.currentTime || 0;

    MUSIC_PLOT_IDS.forEach((id) => updatePlotPlayback(id, currentTime));

    if (!player.paused && !player.ended) {
        playbackState.animationFrame = requestAnimationFrame(updatePlaybackCursor);
    } else {
        playbackState.animationFrame = null;
    }
}

/*
 * Make `player` the active player and kick the cursor loop.
 */
function setActivePlaybackPlayer(player) {
    if (!player) return;

    playbackState.activePlayer = player;

    if (playbackState.animationFrame) {
        cancelAnimationFrame(playbackState.animationFrame);
        playbackState.animationFrame = null;
    }

    updatePlaybackCursor();
}

/*
 * Wire all the standard HTML audio events on one player element
 * so that any interaction (play, seek, pause, …) kicks the cursor.
 */
function wirePlaybackPlayer(playerId) {
    const player = el(playerId);
    if (!player) return;

    player.addEventListener("play",       () => setActivePlaybackPlayer(player));
    player.addEventListener("timeupdate", () => setActivePlaybackPlayer(player));
    player.addEventListener("seeking",    () => setActivePlaybackPlayer(player));
    player.addEventListener("seeked",     () => setActivePlaybackPlayer(player));

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
   (Cursor is injected after each plot is created.)
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
        // Inject cursor immediately if a player is already active.
        if (playbackState.activePlayer) {
            updatePlotPlayback(containerId, playbackState.activePlayer.currentTime || 0);
        }
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
        if (playbackState.activePlayer) {
            updatePlotPlayback(containerId, playbackState.activePlayer.currentTime || 0);
        }
    });
}

/* =========================================================
   Sidebar summary helpers
   ========================================================= */

function shortName(source) {
    // source is like "audio/_music_lab/abc123_vocal.wav"
    // Just show the filename portion.
    return source ? source.split("/").pop() : "—";
}

function updateSidebarSeparate() {
    if (state.separateFile) {
        el("sbSeparateInput").textContent = state.separateFile.name;
    }
    if (state.separateResult) {
        el("sbSeparateVocal").textContent = shortName(state.separateResult.vocal.source);
        el("sbSeparateInst").textContent  = shortName(state.separateResult.instrumental.source);
        el("sbSeparateResults").style.display = "block";
    }
}

function updateSidebarMix() {
    el("sbMixInst").textContent   = state.mixInstrumentalSource ? shortName(state.mixInstrumentalSource) : "—";
    el("sbMixVocal").textContent  = state.mixVocalSource        ? shortName(state.mixVocalSource)        : "—";
    if (state.lastMixResult) {
        el("sbMixResult").textContent        = shortName(state.lastMixResult.mixed.source);
        el("sbMixResultRow").style.display   = "block";
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

        // Keep the underlying <input> in sync, mirroring Audio Lab's pattern.
        const dataTransfer = new DataTransfer();
        dataTransfer.items.add(file);
        input.files = dataTransfer.files;

        onFileSelected(file);
    });
}

/* =========================================================
   Tab 1 — Separate
   ========================================================= */

function handleSeparateFileSelected(file) {
    state.separateFile = file;

    const label = el("separateSelectedFileName");
    label.textContent = "Selected: " + file.name;
    label.style.display = "block";

    updateSidebarSeparate();
    refreshButtonStates();
}

async function runSeparate() {
    if (!state.separateFile) {
        setStatus("Choose an audio file first.", "error");
        return;
    }

    try {
        setBusy(true);
        setStatus("Uploading...");

        const source = await uploadAudioFile(state.separateFile);

        setStatus("Separating vocals and instrumental — this can take a while...");

        const data = await apiPost_json("/music/separate", { source });
        state.separateResult = data;

        // Original
        renderWaveform("separateOriginalWaveform", data.original.waveform);
        renderSpectrogram(
            "separateOriginalSpectrogram",
            data.original.spectrogram.freq,
            data.original.spectrogram.time,
            data.original.spectrogram.z
        );
        const originalPlayer = el("separateOriginalPlayer");
        originalPlayer.src = "/media/audio/" + data.original.source;
        originalPlayer.load();
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
        vocalPlayer.src = "/media/audio/" + data.vocal.source;
        vocalPlayer.load();
        el("vocalDownloadLink").href = "/media/audio/" + data.vocal.source;

        // Instrumental
        renderWaveform("instrumentalWaveform", data.instrumental.waveform);
        renderSpectrogram(
            "instrumentalSpectrogram",
            data.instrumental.spectrogram.freq,
            data.instrumental.spectrogram.time,
            data.instrumental.spectrogram.z
        );
        const instrumentalPlayer = el("instrumentalPlayer");
        instrumentalPlayer.src = "/media/audio/" + data.instrumental.source;
        instrumentalPlayer.load();
        el("instrumentalDownloadLink").href = "/media/audio/" + data.instrumental.source;

        // Show vertical stack (renamed from separateResultsGrid)
        el("separateResultsStack").style.display = "flex";

        updateSidebarSeparate();
        setStatus("Separation complete.", "success");
    } catch (err) {
        setStatus(err.message, "error");
    } finally {
        setBusy(false);
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

        const player = el("mixVocalPlayer");
        player.src = "/media/audio/" + stemData.source;
        player.load();

        const label = el("mixVocalFileName");
        label.textContent = "From Separate tab: " + stemData.source;
        label.style.display = "block";
    } else {
        state.mixInstrumentalSource = stemData.source;

        const player = el("mixInstrumentalPlayer");
        player.src = "/media/audio/" + stemData.source;
        player.load();

        const label = el("mixInstrumentalFileName");
        label.textContent = "From Separate tab: " + stemData.source;
        label.style.display = "block";
    }

    updateSidebarMix();
    switchToplevelTab("tabMix");
    refreshButtonStates();
    maybeSuggestOffset();
}

/* =========================================================
   Tab 2 — Mix
   ========================================================= */

async function handleMixFileSelected(slot, file) {
    try {
        setBusy(true);
        setStatus("Uploading " + slot + "...");

        const source = await uploadAudioFile(file);

        if (slot === "instrumental") {
            state.mixInstrumentalSource = source;

            const player = el("mixInstrumentalPlayer");
            player.src = "/media/audio/" + source;
            player.load();

            const label = el("mixInstrumentalFileName");
            label.textContent = "Selected: " + file.name;
            label.style.display = "block";
        } else {
            state.mixVocalSource = source;

            const player = el("mixVocalPlayer");
            player.src = "/media/audio/" + source;
            player.load();

            const label = el("mixVocalFileName");
            label.textContent = "Selected: " + file.name;
            label.style.display = "block";
        }

        updateSidebarMix();
        setStatus("");
        maybeSuggestOffset();
    } catch (err) {
        setStatus(err.message, "error");
    } finally {
        setBusy(false);
        refreshButtonStates();
    }
}

function maybeSuggestOffset() {
    if (!state.mixInstrumentalSource || !state.mixVocalSource) return;
    runSuggestOffset();
}

async function runSuggestOffset() {
    if (!state.mixInstrumentalSource || !state.mixVocalSource) {
        setStatus("Load both an instrumental and a vocal first.", "error");
        return;
    }

    try {
        setBusy(true);
        setStatus("Computing suggested offset...");

        const data = await apiPost_json("/music/suggest-offset", {
            instrumental_source: state.mixInstrumentalSource,
            vocal_source: state.mixVocalSource,
        });

        state.suggestedOffset = data.suggested_offset_sec;

        el("suggestedOffsetReadout").textContent = data.suggested_offset_sec.toFixed(3) + " s";
        el("offsetInput").value = data.suggested_offset_sec.toFixed(3);

        setStatus("Suggested offset computed.", "success");
    } catch (err) {
        setStatus(err.message, "error");
    } finally {
        setBusy(false);
        refreshButtonStates();
    }
}

async function runMix() {
    if (!state.mixInstrumentalSource || !state.mixVocalSource) {
        setStatus("Load both an instrumental and a vocal first.", "error");
        return;
    }

    try {
        setBusy(true);
        setStatus("Mixing...");

        const req = {
            instrumental_source: state.mixInstrumentalSource,
            vocal_source: state.mixVocalSource,
            instrumental_gain_db: parseFloat(el("instrumentalGainSlider").value),
            vocal_gain_db: parseFloat(el("vocalGainSlider").value),
            offset_sec: parseFloat(el("offsetInput").value) || 0,
        };

        const data = await apiPost_json("/music/mix", req);
        state.lastMixResult = data;

        renderWaveform("mixedWaveform", data.mixed.waveform);

        const mixedPlayer = el("mixedPlayer");
        mixedPlayer.src = "/media/audio/" + data.mixed.source;
        mixedPlayer.load();

        el("mixedDownloadLink").href = "/media/audio/" + data.mixed.source;
        el("mixResultBlock").style.display = "block";

        updateSidebarMix();
        setStatus("Mix complete.", "success");
    } catch (err) {
        setStatus(err.message, "error");
    } finally {
        setBusy(false);
        refreshButtonStates();
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
   init
   ========================================================= */

window.addEventListener("DOMContentLoaded", () => {
    initToplevelTabs();

    // Wire all players for playback cursor tracking.
    wireMusicPlaybackTracking();

    wireDropzone("separateUploadInput", "separateDropzone", handleSeparateFileSelected);
    wireDropzone("mixInstrumentalInput", "mixInstrumentalDropzone", (file) => handleMixFileSelected("instrumental", file));
    wireDropzone("mixVocalInput", "mixVocalDropzone", (file) => handleMixFileSelected("vocal", file));

    wireGainSlider("instrumentalGainSlider", "instrumentalGainLabel");
    wireGainSlider("vocalGainSlider", "vocalGainLabel");

    el("separateBtn").addEventListener("click", runSeparate);
    el("useVocalInMixerBtn").addEventListener("click", () => sendToMixer("vocal"));
    el("useInstrumentalInMixerBtn").addEventListener("click", () => sendToMixer("instrumental"));
    el("suggestOffsetBtn").addEventListener("click", runSuggestOffset);
    el("mixBtn").addEventListener("click", runMix);

    refreshButtonStates();
});
