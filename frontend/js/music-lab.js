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
   plotting (lightweight, non-interactive — view only)
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
    const traceMax = { x: waveform.time, y: waveform.max, mode: "lines", line: { width: 1, color: "#FFB454" }, name: "max" };
    const traceMin = {
        x: waveform.time, y: waveform.min, mode: "lines", line: { width: 1, color: "#FFB454" },
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
    });
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

        el("separateResultsGrid").style.display = "grid";

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
