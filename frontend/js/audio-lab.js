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

    // ---------------------------------------------------------
    // Interactive masking state
    // ---------------------------------------------------------
    maskRegions: [],
    selectedMaskRegionId: null,
    maskInteractionMode: "edit",
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

function renderSpectrogram(
    containerId,
    freqs,
    times,
    magnitude_db,
    options = {}
) {
    const trace = {
        x: times,
        y: freqs,
        z: magnitude_db,

        type: "heatmap",

        colorscale:
            options.colorscale || MAGNITUDE_COLORSCALE,

        zsmooth: "best",

        colorbar: {
            title: options.colorbarTitle || "dB",
            titleside: "right",
            tickfont: {
                size: 10,
            },
            thickness: 12,
        },
    };


    const isMaskPlot =
        containerId === "maskSpectrogram";


    let dragmode = "zoom";

    if (isMaskPlot) {
        dragmode = "false";
    } else if (options.selectable) {
        dragmode = "select";
    }


    const layout = baseLayout({

        xaxis: {
            title: "Time (s)",
        },

        yaxis: {
            title: "Frequency (Hz)",
            type: state.freqScale,
        },

        height: 320,

        dragmode,

        /*
         * Allows clicks anywhere in the plotting area.
         * We do not rely on this for shape selection itself;
         * the masking system also listens directly to the
         * SVG shape layer.
         */
        clickmode: "event",

        clickanywhere: true,

        /*
         * Styling for Plotly-created rectangles.
         */
        newshape: {
            type: "rect",

            line: {
                color: "#F5A623",
                width: 2,
            },

            fillcolor: "rgba(245, 166, 35, 0.10)",

            opacity: 0.32,

            layer: "above",
        },

        /*
         * Avoid Plotly's default bright-magenta active shape.
         */
        activeshape: {
            fillcolor: "rgba(245, 166, 35, 0.12)",
            opacity: 0.55,
        },

        /*
         * Keep shape edits stable while the user interacts.
         */
        editrevision: "mask-regions",
    });


    const config = {
        displayModeBar: true,

        responsive: true,

        modeBarButtonsToRemove: [
            "lasso2d",
        ],

        /*
         * Only expose drawrect for the masking plot.
         * The actual interaction mode is controlled by our
         * Edit/Add buttons.
         */
        modeBarButtonsToAdd: [],
    };


    Plotly.newPlot(
        containerId,
        [trace],
        layout,
        config
    ).then(() => {

        if (
            playbackState.activePlayer
        ) {
            updatePlotPlayback(
                containerId,
                playbackState.activePlayer.currentTime || 0
            );
        }


        if (isMaskPlot) {

            attachMaskShapeClickHandler();

            const plot =
                el("maskSpectrogram");

            plot.on(
                "plotly_relayout",
                handleMaskRelayout
            );

            /*
             * Initial region state.
             */
            renderMaskRegionShapes();

            setMaskInteractionMode(
                state.maskInteractionMode
            );
        }


        if (options.onSelect) {

            const plot =
                document.getElementById(containerId);

            plot.on(
                "plotly_selected",
                (evt) => {

                    if (
                        !evt ||
                        !evt.range
                    ) {
                        return;
                    }

                    options.onSelect(
                        evt.range.x,
                        evt.range.y
                    );
                }
            );
        }
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
        "magOnlyPlayer",

        "phaseOriginalPlayer",
        "phaseOnlyPlayer",

        "maskOriginalPlayer",
        "maskedPlayer",

        "retentionOriginalPlayer",
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

    resetMaskRegions();

    // Reset status message
    setStatus("");
}




/* =========================================================
   INTERACTIVE MASKING
   ========================================================= */

let maskShapeEventAttached = false;


function createMaskRegion(x0, x1, y0, y1) {
    const timeMin = Math.min(Number(x0), Number(x1));
    const timeMax = Math.max(Number(x0), Number(x1));

    const freqMin = Math.min(Number(y0), Number(y1));
    const freqMax = Math.max(Number(y0), Number(y1));

    const nextId =
        state.maskRegions.length > 0
            ? Math.max(...state.maskRegions.map((r) => r.id)) + 1
            : 1;

    return clampMaskRegion({
        id: nextId,
        name: `Region ${nextId}`,

        freqMin,
        freqMax,
        timeMin,
        timeMax,

        mode: "remove",
        enabled: true,
    });
}


function getSelectedMaskRegion() {
    return state.maskRegions.find(
        (region) => region.id === state.selectedMaskRegionId
    ) || null;
}


function selectMaskRegion(regionId, refreshPlot = true) {
    const region = state.maskRegions.find(
        (item) => item.id === regionId
    );

    if (!region) {
        state.selectedMaskRegionId = null;
        updateMaskRegionEditor();
        if (refreshPlot) {
            renderMaskRegionShapes();
        }
        return;
    }

    state.selectedMaskRegionId = region.id;

    updateMaskRegionEditor();
    updateMaskRegionDropdown();

    if (refreshPlot) {
        renderMaskRegionShapes();
    }
}


function clearMaskRegionSelection() {
    state.selectedMaskRegionId = null;

    updateMaskRegionEditor();
    updateMaskRegionDropdown();
    renderMaskRegionShapes();
}


function updateMaskRegionEditor() {
    const region = getSelectedMaskRegion();

    const selectedLabel = el("maskSelectedRegion");
    const dropdownLabel = el("maskRegionDropdownLabel");

    const freqMin = el("freqMin");
    const freqMax = el("freqMax");
    const timeMin = el("timeMin");
    const timeMax = el("timeMax");

    const enabled = el("maskRegionEnabled");
    const editor = document.querySelector(".mask-editor-card");

    if (!region) {
        if (selectedLabel) {
            selectedLabel.textContent = "None";
        }

        if (dropdownLabel) {
            dropdownLabel.textContent = "No regions";
        }

        freqMin.value = "";
        freqMax.value = "";
        timeMin.value = "";
        timeMax.value = "";

        enabled.checked = false;

        if (editor) {
            editor.classList.add("region-empty");
        }

        document.querySelectorAll('input[name="maskMode"]').forEach((input) => {
            input.checked = input.value === "remove";
            input.disabled = true;
        });

        enabled.disabled = true;

        return;
    }

    if (editor) {
        editor.classList.remove("region-empty");
    }

    if (selectedLabel) {
        selectedLabel.textContent = region.name;
    }

    if (dropdownLabel) {
        dropdownLabel.textContent = region.name;
    }

    freqMin.value = Number(region.freqMin).toFixed(0);
    freqMax.value = Number(region.freqMax).toFixed(0);
    timeMin.value = Number(region.timeMin).toFixed(2);
    timeMax.value = Number(region.timeMax).toFixed(2);

    enabled.checked = region.enabled;
    enabled.disabled = false;

    document.querySelectorAll('input[name="maskMode"]').forEach((input) => {
        input.disabled = false;
        input.checked = input.value === region.mode;
    });
}


function updateMaskRegionDropdown() {
    const menu = el("maskRegionDropdownMenu");

    if (!menu) return;

    menu.innerHTML = "";

    if (state.maskRegions.length === 0) {
        menu.innerHTML = `
            <div class="mask-region-empty">
                No regions yet.
            </div>
        `;
        return;
    }

    state.maskRegions.forEach((region) => {
        const row = document.createElement("div");

        row.className =
            "mask-region-item" +
            (region.id === state.selectedMaskRegionId ? " selected" : "");

        row.dataset.regionId = region.id;

        row.innerHTML = `
            <span class="mask-region-item-label">
                ${region.name}
            </span>

            <label class="mask-region-item-checkbox">
                <input
                    type="checkbox"
                    ${region.enabled ? "checked" : ""}
                    data-region-enable="${region.id}">
                <span>Enabled</span>
            </label>
        `;

        row.addEventListener("click", (event) => {

            // Clicking the checkbox should only toggle enable/disable.
            if (event.target.matches('input[type="checkbox"]')) {
                return;
            }

            selectMaskRegion(region.id);
            closeMaskRegionDropdown();
        });

        const checkbox = row.querySelector(
            `[data-region-enable="${region.id}"]`
        );

        checkbox.addEventListener("change", (event) => {
            region.enabled = event.target.checked;

            updateMaskRegionEditor();
            renderMaskRegionShapes();
        });

        menu.appendChild(row);
    });
}


function openMaskRegionDropdown() {
    const dropdown = el("maskRegionDropdown");
    if (!dropdown) return;

    dropdown.classList.add("open");
}


function closeMaskRegionDropdown() {
    const dropdown = el("maskRegionDropdown");
    if (!dropdown) return;

    dropdown.classList.remove("open");
}


function toggleMaskRegionDropdown() {
    const dropdown = el("maskRegionDropdown");

    if (!dropdown) return;

    dropdown.classList.toggle("open");
}


function setMaskInteractionMode(mode) {

    if (
        mode !== "edit" &&
        mode !== "add"
    ) {
        return;
    }


    state.maskInteractionMode = mode;


    const editBtn =
        el("editRegionModeBtn");

    const addBtn =
        el("addRegionModeBtn");

    const hint =
        el("maskModeHint");

    const plot =
        el("maskSpectrogram");


    editBtn.classList.toggle(
        "active",
        mode === "edit"
    );

    addBtn.classList.toggle(
        "active",
        mode === "add"
    );


    if (mode === "edit") {

        hint.textContent =
            "Click a region to select it. Drag or resize the selected region.";


        if (
            plot &&
            plot.layout
        ) {

            Plotly.relayout(
                plot,
                {
                    dragmode: "false",
                }
            );
        }

    } else {

        hint.textContent =
            "Drag on empty space to create a new region.";


        if (
            plot &&
            plot.layout
        ) {

            Plotly.relayout(
                plot,
                {
                    dragmode: "drawrect",
                }
            );
        }
    }


    /*
     * Make only our region shapes editable while in Edit mode.
     */
    updateMaskShapeInteractivity();
}


function updateMaskShapeInteractivity() {
    const plot = el("maskSpectrogram");

    if (!plot || !plot.layout) return;

    const shapes = plot.layout.shapes || [];

    const updates = {};

    shapes.forEach((shape, index) => {

        if (!shape.name || !shape.name.startsWith("mask-region-")) {
            return;
        }

        updates[`shapes[${index}].editable`] =
            state.maskInteractionMode === "edit";
    });

    if (Object.keys(updates).length > 0) {
        Plotly.relayout(plot, updates);
    }
}


function getMaskRegionShapes() {
    return state.maskRegions.map((region) => {

        const selected =
            region.id === state.selectedMaskRegionId;

        const modeColor =
            region.mode === "remove"
                ? "#F5A623"
                : "#C792EA";

        return {
            type: "rect",

            xref: "x",
            yref: "y",

            x0: region.timeMin,
            x1: region.timeMax,

            y0: region.freqMin,
            y1: region.freqMax,

            name: `mask-region-${region.id}`,

            editable:
                state.maskInteractionMode === "edit",

            layer: "above",

            opacity: selected ? 0.55 : 0.32,

            fillcolor:
                region.enabled
                    ? `rgba(245, 166, 35, ${selected ? 0.16 : 0.08})`
                    : "rgba(120, 130, 145, 0.05)",

            line: {
                color: selected
                    ? modeColor
                    : region.enabled
                        ? modeColor
                        : "#7b8494",

                width: selected ? 3 : 1.5,

                dash:
                    region.enabled
                        ? "solid"
                        : "dash",
            },
        };
    });
}


function renderMaskRegionShapes() {
    const plot = el("maskSpectrogram");

    if (!plot || !plot.layout) return;

    const existingShapes = plot.layout.shapes || [];

    const playbackShapes = existingShapes.filter(
        (shape) =>
            shape.name &&
            shape.name !== "playback-cursor" &&
            shape.name !== "playback-progress" &&
            !shape.name.startsWith("mask-region-")
    );

    const regionShapes = getMaskRegionShapes();

    const currentPlaybackShapes = existingShapes.filter(
        (shape) =>
            shape.name === "playback-cursor" ||
            shape.name === "playback-progress"
    );

    Plotly.relayout(plot, {
        shapes: [
            ...playbackShapes,
            ...regionShapes,
            ...currentPlaybackShapes,
        ],
    });

    updateMaskRegionDropdown();
    updateMaskRegionEditor();
}


function syncSelectedMaskRegionFromShape(shapeIndex, shape) {
    if (!shape) return;

    if (
        !shape.name ||
        !shape.name.startsWith("mask-region-")
    ) {
        return;
    }

    const id = Number(
        shape.name.replace("mask-region-", "")
    );

    const region = state.maskRegions.find(
        (item) => item.id === id
    );

    if (!region) return;

    const x0 = Number(shape.x0);
    const x1 = Number(shape.x1);
    const y0 = Number(shape.y0);
    const y1 = Number(shape.y1);

    if (
        !Number.isFinite(x0) ||
        !Number.isFinite(x1) ||
        !Number.isFinite(y0) ||
        !Number.isFinite(y1)
    ) {
        return;
    }

    region.timeMin = Math.max(0, Math.min(x0, x1));
    region.timeMax = Math.min(
        state.duration,
        Math.max(x0, x1)
    );

    region.freqMin = Math.max(
        0,
        Math.min(y0, y1)
    );

    region.freqMax = Math.min(
        state.sr / 2,
        Math.max(y0, y1)
    );

    state.selectedMaskRegionId = region.id;

    updateMaskRegionEditor();
    updateMaskRegionDropdown();
    updateMaskRegionShapesOnly();
}


function updateMaskRegionShapesOnly() {
    const plot = el("maskSpectrogram");

    if (!plot || !plot.layout) return;

    const shapes = plot.layout.shapes || [];

    const updates = {};

    state.maskRegions.forEach((region) => {

        const shapeIndex = shapes.findIndex(
            (shape) =>
                shape.name === `mask-region-${region.id}`
        );

        if (shapeIndex === -1) return;

        updates[`shapes[${shapeIndex}].x0`] = region.timeMin;
        updates[`shapes[${shapeIndex}].x1`] = region.timeMax;
        updates[`shapes[${shapeIndex}].y0`] = region.freqMin;
        updates[`shapes[${shapeIndex}].y1`] = region.freqMax;
    });

    if (Object.keys(updates).length > 0) {
        Plotly.relayout(plot, updates);
    }
}

let maskNeedsRestyle = false;

function findTopMaskRegionAt(event) {
    const plot = el("maskSpectrogram");
    const fl = plot && plot._fullLayout;

    if (!fl || !fl.xaxis || !fl.yaxis) return null;

    const box = plot.getBoundingClientRect();

    const px = event.clientX - box.left - fl.xaxis._offset;
    const py = event.clientY - box.top - fl.yaxis._offset;

    // Ignore clicks outside the plotting area.
    if (px < 0 || px > fl.xaxis._length || py < 0 || py > fl.yaxis._length) {
        return null;
    }

    const x = fl.xaxis.p2d(px);
    const y = fl.yaxis.p2d(py);

    // Last region = drawn on top, so search from the end.
    for (let i = state.maskRegions.length - 1; i >= 0; i--) {
        const r = state.maskRegions[i];

        if (x >= r.timeMin && x <= r.timeMax && y >= r.freqMin && y <= r.freqMax) {
            return r;
        }
    }

    return null;
}


function attachMaskShapeClickHandler() {
    const plot = el("maskSpectrogram");

    if (!plot || maskShapeEventAttached) return;

    maskShapeEventAttached = true;

    plot.addEventListener("mousedown", (event) => {
        if (state.maskInteractionMode !== "edit" || event.button !== 0) return;
        if (event.target.closest && event.target.closest(".modebar")) return;

        const hit = findTopMaskRegionAt(event);

        if (!hit || hit.id === state.selectedMaskRegionId) return;

        state.selectedMaskRegionId = hit.id;

        updateMaskRegionEditor();
        updateMaskRegionDropdown();

        maskNeedsRestyle = true;
    });

    // Repaint the highlight only after the mouse is released,
    // so we never interrupt Plotly's drag/resize.
    plot.addEventListener("mouseup", () => {
        if (!maskNeedsRestyle) return;

        maskNeedsRestyle = false;
        setTimeout(renderMaskRegionShapes, 50);
    });
}


function clampMaskRegion(region) {
    const maxTime = state.duration > 0 ? state.duration : Infinity;
    const maxFreq = state.sr / 2;

    const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, Number(v) || 0));

    let tMin = clamp(region.timeMin, 0, maxTime);
    let tMax = clamp(region.timeMax, 0, maxTime);
    let fMin = clamp(region.freqMin, 0, maxFreq);
    let fMax = clamp(region.freqMax, 0, maxFreq);

    if (tMax < tMin) [tMin, tMax] = [tMax, tMin];
    if (fMax < fMin) [fMin, fMax] = [fMax, fMin];

    region.timeMin = tMin;
    region.timeMax = tMax;
    region.freqMin = fMin;
    region.freqMax = fMax;

    return region;
}



function handleMaskRelayout(eventData) {

    if (!eventData) {
        return;
    }

    const plot = el("maskSpectrogram");

    if (!plot) {
        return;
    }


    /*
     * =========================================================
     * 1. Detect newly drawn rectangle
     * =========================================================
     *
     * Plotly can report a newly created shape directly through
     * eventData:
     *
     *   shapes[0] = {...}
     *
     * or:
     *
     *   shapes[0].x0
     *   shapes[0].x1
     *   shapes[0].y0
     *   shapes[0].y1
     *
     * We inspect eventData directly instead of relying only on
     * plot.layout.shapes.
     */

    const hasShapeKey = Object.keys(eventData).some((k) => k.startsWith("shapes"));

    if (state.maskInteractionMode === "add" && hasShapeKey) {

        let newShape = null;

        const layoutShapes = plot.layout?.shapes || [];

        // Plotly's freshly drawn rectangle has no name.
        // Our own regions are named "mask-region-N", and playback shapes have names too.
        newShape = layoutShapes.find(
            (s) => s && s.type === "rect" && !s.name
        ) || null;

        console.log("[mask] relayout:", eventData, "newShape:", newShape);



        /*
         * If a new rectangle was actually created,
         * register it as one of our application regions.
         */
        if (newShape) {

            const x0 = Number(newShape.x0);
            const x1 = Number(newShape.x1);
            const y0 = Number(newShape.y0);
            const y1 = Number(newShape.y1);


            if (
                Number.isFinite(x0) &&
                Number.isFinite(x1) &&
                Number.isFinite(y0) &&
                Number.isFinite(y1)
            ) {

                /*
                 * Ignore tiny accidental drags.
                 */
                if (
                    Math.abs(x1 - x0) >= 0.01 &&
                    Math.abs(y1 - y0) >= 1
                ) {

                    const region =
                        createMaskRegion(
                            x0,
                            x1,
                            y0,
                            y1
                        );


                    /*
                     * Add it to application state.
                     */
                    state.maskRegions.push(
                        region
                    );

                    /*
                     * Automatically select it.
                     */
                    state.selectedMaskRegionId =
                        region.id;


                    /*
                     * Rebuild ALL region shapes from our
                     * application state.
                     *
                     * This removes Plotly's temporary unnamed
                     * drawing shape and replaces it with our
                     * properly named/editable region.
                     */
                    const regionShapes =
                        getMaskRegionShapes();


                    const currentShapes =
                        plot.layout?.shapes || [];


                    const persistentShapes =
                        currentShapes.filter(
                            (shape) =>
                                shape.name &&
                                shape.name !== "playback-cursor" &&
                                shape.name !== "playback-progress" &&
                                !shape.name.startsWith("mask-region-")
                        );

                    const playbackShapes =
                        currentShapes.filter(
                            (shape) =>
                                shape.name ===
                                "playback-cursor" ||
                                shape.name ===
                                "playback-progress"
                        );

                    state.maskInteractionMode = "edit";

                    Plotly.relayout(plot, {
                        shapes: [
                            ...persistentShapes,
                            ...regionShapes,
                            ...playbackShapes,
                        ],

                        /*
                         * Once the rectangle is registered,
                         * return to normal editing.
                         */
                        dragmode: "false",
                    });


                    /*
                     * Update our UI state.
                     */
                    state.maskInteractionMode =
                        "edit";


                    el(
                        "editRegionModeBtn"
                    ).classList.add("active");

                    el(
                        "addRegionModeBtn"
                    ).classList.remove("active");


                    el(
                        "maskModeHint"
                    ).textContent =
                        "Click a region to select it. Drag or resize the selected region.";


                    updateMaskRegionDropdown();

                    updateMaskRegionEditor();

                    return;
                }
            }
        }
    }


    /*
     * =========================================================
     * 2. Detect movement / resizing of existing regions
     * =========================================================
     */

    if (
        state.maskInteractionMode === "edit"
    ) {

        const shapes =
            plot.layout?.shapes || [];


        const changedRegionIds =
            new Set();


        Object.keys(eventData).forEach(
            (key) => {

                const match = key.match(
                    /^shapes\[(\d+)\]/
                );

                if (!match) {
                    return;
                }

                const index =
                    Number(match[1]);

                const shape =
                    shapes[index];

                if (
                    !shape ||
                    !shape.name ||
                    !shape.name.startsWith(
                        "mask-region-"
                    )
                ) {
                    return;
                }

                const id =
                    Number(
                        shape.name.replace(
                            "mask-region-",
                            ""
                        )
                    );

                if (
                    Number.isInteger(id)
                ) {
                    changedRegionIds.add(id);
                }
            }
        );


        /*
         * Synchronize every changed region.
         */
        changedRegionIds.forEach(
            (id) => {

                const region =
                    state.maskRegions.find(
                        (item) =>
                            item.id === id
                    );

                if (!region) {
                    return;
                }


                const shape =
                    shapes.find(
                        (item) =>
                            item.name ===
                            `mask-region-${id}`
                    );

                if (!shape) {
                    return;
                }


                const x0 =
                    Number(shape.x0);

                const x1 =
                    Number(shape.x1);

                const y0 =
                    Number(shape.y0);

                const y1 =
                    Number(shape.y1);


                if (
                    !Number.isFinite(x0) ||
                    !Number.isFinite(x1) ||
                    !Number.isFinite(y0) ||
                    !Number.isFinite(y1)
                ) {
                    return;
                }


                region.timeMin =
                    Math.max(
                        0,
                        Math.min(x0, x1)
                    );

                region.timeMax =
                    Math.min(
                        state.duration,
                        Math.max(x0, x1)
                    );


                region.freqMin =
                    Math.max(
                        0,
                        Math.min(y0, y1)
                    );

                region.freqMax =
                    Math.min(
                        state.sr / 2,
                        Math.max(y0, y1)
                    );


                /*
                 * The edited region becomes the selected region.
                 */
                state.selectedMaskRegionId =
                    region.id;
            }
        );


        if (
            changedRegionIds.size > 0
        ) {

            updateMaskRegionEditor();

            updateMaskRegionDropdown();
        }
    }
}

function wireMaskRegionControls() {

    el("maskRegionDropdownBtn").addEventListener(
        "click",
        (event) => {
            event.stopPropagation();
            toggleMaskRegionDropdown();
        }
    );


    document.addEventListener("click", (event) => {

        const dropdown = el("maskRegionDropdown");

        if (!dropdown) return;

        if (!dropdown.contains(event.target)) {
            closeMaskRegionDropdown();
        }
    });


    el("editRegionModeBtn").addEventListener(
        "click",
        () => {
            setMaskInteractionMode("edit");
        }
    );


    el("addRegionModeBtn").addEventListener(
        "click",
        () => {
            setMaskInteractionMode("add");
        }
    );


    const coordinateInputs = [
        ["freqMin", "freqMin"],
        ["freqMax", "freqMax"],
        ["timeMin", "timeMin"],
        ["timeMax", "timeMax"],
    ];


    coordinateInputs.forEach(([inputId, property]) => {

        el(inputId).addEventListener(
            "change",
            () => {

                const region = getSelectedMaskRegion();

                if (!region) return;

                const value = Number(
                    el(inputId).value
                );

                if (!Number.isFinite(value)) {
                    updateMaskRegionEditor();
                    return;
                }

                region[property] = value;

                /*
                 * Normalize the range.
                 */
                if (
                    property === "freqMin" ||
                    property === "freqMax"
                ) {
                    region.freqMin = Math.max(
                        0,
                        Math.min(region.freqMin, state.sr / 2)
                    );

                    region.freqMax = Math.max(
                        0,
                        Math.min(region.freqMax, state.sr / 2)
                    );
                }

                if (
                    region.freqMax < region.freqMin
                ) {
                    [
                        region.freqMin,
                        region.freqMax
                    ] = [
                            region.freqMax,
                            region.freqMin
                        ];
                }

                if (
                    region.timeMax < region.timeMin
                ) {
                    [
                        region.timeMin,
                        region.timeMax
                    ] = [
                            region.timeMax,
                            region.timeMin
                        ];
                }

                region.timeMin = Math.max(
                    0,
                    Math.min(region.timeMin, state.duration)
                );

                region.timeMax = Math.max(
                    0,
                    Math.min(region.timeMax, state.duration)
                );

                updateMaskRegionEditor();
                updateMaskRegionShapesOnly();
            }
        );
    });


    el("maskRegionEnabled").addEventListener(
        "change",
        (event) => {

            const region = getSelectedMaskRegion();

            if (!region) return;

            region.enabled = event.target.checked;

            updateMaskRegionDropdown();
            renderMaskRegionShapes();
        }
    );


    document
        .querySelectorAll('input[name="maskMode"]')
        .forEach((input) => {

            input.addEventListener(
                "change",
                (event) => {

                    const region = getSelectedMaskRegion();

                    if (!region) return;

                    region.mode = event.target.value;

                    renderMaskRegionShapes();
                    updateMaskRegionEditor();
                }
            );
        });


    el("deleteMaskRegionBtn").addEventListener(
        "click",
        deleteSelectedMaskRegion
    );
}


function deleteSelectedMaskRegion() {

    const region = getSelectedMaskRegion();

    if (!region) return;

    const deletedIndex =
        state.maskRegions.findIndex(
            (item) => item.id === region.id
        );

    if (deletedIndex === -1) return;

    state.maskRegions.splice(
        deletedIndex,
        1
    );


    /*
     * Select the nearest remaining region.
     */
    if (state.maskRegions.length > 0) {

        const nextIndex = Math.min(
            deletedIndex,
            state.maskRegions.length - 1
        );

        state.selectedMaskRegionId =
            state.maskRegions[nextIndex].id;

    } else {

        state.selectedMaskRegionId = null;
    }


    renderMaskRegionShapes();
}


function resetMaskRegions() {

    state.maskRegions = [];
    state.selectedMaskRegionId = null;
    state.maskInteractionMode = "edit";

    closeMaskRegionDropdown();

    const editBtn =
        el("editRegionModeBtn");

    const addBtn =
        el("addRegionModeBtn");

    const hint =
        el("maskModeHint");

    if (editBtn) {
        editBtn.classList.add("active");
    }

    if (addBtn) {
        addBtn.classList.remove("active");
    }

    if (hint) {
        hint.textContent =
            "Click a region to select it. Drag or resize the selected region.";
    }

    if (el("maskRegionDropdownMenu")) {
        updateMaskRegionDropdown();
    }

    if (el("freqMin")) {
        updateMaskRegionEditor();
    }
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
        renderSpectrogram(
            "maskSpectrogram",
            data.freqs,
            data.times,
            data.magnitude_db,
            {
                selectable: false,
            }
        );
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

function setAudioFromSource() {
    const audioSrc = "/media/audio/" + state.source;

    const playerIds = [
        "originalPlayer",
        "magPhaseOriginalPlayer",
        "phaseOriginalPlayer",
        "maskOriginalPlayer",
        "retentionOriginalPlayer",
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
            setStatus(
                "Create at least one masking region first.",
                "error"
            );
            return;
        }


        const enabledRegions =
            state.maskRegions.filter(
                (region) => region.enabled
            );


        if (enabledRegions.length === 0) {
            setStatus(
                "Enable at least one masking region.",
                "error"
            );
            return;
        }


        setBusy(true);
        setStatus("Applying mask...");


        const req = {

            source: state.source,

            sr: state.sr,

            n_fft: state.n_fft,

            hop_length: state.hop_length,

            regions: enabledRegions
                .map((region) => clampMaskRegion({ ...region }))
                .filter((r) => r.timeMax > r.timeMin && r.freqMax > r.freqMin)
                .map((region) => ({
                    freq_min: region.freqMin,
                    freq_max: region.freqMax,

                    time_min: region.timeMin,
                    time_max: region.timeMax,

                    mode: region.mode,

                    enabled: region.enabled,
                })),
        };

        if (req.regions.length === 0) {
            setStatus("Enabled regions have no valid area inside the audio.", "error");
            setBusy(false);
            return;
        }


        const data =
            await apiPost_json(
                "/audio/mask",
                req
            );


        state.lastMask = data;


        renderSpectrogram(
            "maskResultSpectrogram",

            state.lastAnalyze.freqs,

            state.lastAnalyze.times,

            data.magnitude_db,

            {
                selectable: false,
            }
        );


        const maskedPlayer =
            el("maskedPlayer");


        maskedPlayer.src =
            "data:audio/wav;base64," +
            data.audio_base64;

        maskedPlayer.load();


        el("maskReadouts").innerHTML = `

            <div class="readout">

                <div class="readout-label">
                    SNR
                </div>

                <div class="readout-value">
                    ${fmt(data.snr_db, 2, " dB")}
                </div>

            </div>


            <div class="readout">

                <div class="readout-label">
                    MSE
                </div>

                <div class="readout-value">
                    ${data.mse.toFixed(6)}
                </div>

            </div>


            <div class="readout">

                <div class="readout-label">
                    Spectral Conv.
                </div>

                <div class="readout-value">
                    ${data.spectral_convergence.toFixed(4)}
                </div>

            </div>

        `;


        updateMetricsTab(data);

        setStatus(
            "Mask applied",
            "success"
        );

    } catch (err) {

        setStatus(
            err.message,
            "error"
        );

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
    wireMaskRegionControls();
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