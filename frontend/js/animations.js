const REDUCED_MOTION = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function setupCanvas(canvas) {
  const ratio = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  canvas.width = rect.width * ratio;
  canvas.height = rect.height * ratio;
  const ctx = canvas.getContext("2d");
  ctx.scale(ratio, ratio);
  return { ctx, w: rect.width, h: rect.height };
}

function drawScope(canvasId) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const { ctx, w, h } = setupCanvas(canvas);
  let t = 0;

  function frame() {
    ctx.clearRect(0, 0, w, h);

    ctx.strokeStyle = "#1C2A44";
    ctx.lineWidth = 1;
    for (let x = 0; x < w; x += 30) {
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke();
    }
    for (let y = 0; y < h; y += 30) {
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
    }

    ctx.beginPath();
    ctx.strokeStyle = "#FFB454";
    ctx.lineWidth = 2;
    ctx.shadowColor = "rgba(255,180,84,0.5)";
    ctx.shadowBlur = 8;
    for (let x = 0; x <= w; x += 2) {
      const p = x / w;
      const y = h / 2
        + Math.sin(p * 14 + t) * (h * 0.16)
        + Math.sin(p * 34 + t * 1.7) * (h * 0.07);
      if (x === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.stroke();
    ctx.shadowBlur = 0;

    t += 0.03;
    if (!REDUCED_MOTION) requestAnimationFrame(frame);
  }
  frame();
}

function drawRadialSweep(canvasId) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const { ctx, w, h } = setupCanvas(canvas);
  const cx = w / 2, cy = h / 2;
  const maxR = Math.min(w, h) / 2 - 6;
  let angle = 0;

  function frame() {
    ctx.clearRect(0, 0, w, h);

    ctx.strokeStyle = "#26345c";
    ctx.lineWidth = 1;
    for (let r = maxR / 3; r <= maxR; r += maxR / 3) {
      ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.stroke();
    }

    const grad = ctx.createLinearGradient(cx, cy, cx + maxR * Math.cos(angle), cy + maxR * Math.sin(angle));
    grad.addColorStop(0, "rgba(199,146,234,0.9)");
    grad.addColorStop(1, "rgba(199,146,234,0)");
    ctx.strokeStyle = grad;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(cx + maxR * Math.cos(angle), cy + maxR * Math.sin(angle));
    ctx.stroke();

    ctx.fillStyle = "#C792EA";
    ctx.beginPath(); ctx.arc(cx, cy, 2.5, 0, Math.PI * 2); ctx.fill();

    angle += 0.025;
    if (!REDUCED_MOTION) requestAnimationFrame(frame);
  }
  frame();
}

function drawSpectrumBars(canvasId) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const { ctx, w, h } = setupCanvas(canvas);
  const barCount = 28;
  const barW = w / barCount;
  let t = 0;

  function frame() {
    ctx.clearRect(0, 0, w, h);
    for (let i = 0; i < barCount; i++) {
      const freq = i / barCount;
      const envelope = Math.exp(-freq * 2.2);
      const wobble = 0.5 + 0.5 * Math.sin(t * 2 + i * 0.7);
      const barH = Math.max(3, envelope * wobble * h * 0.9);
      ctx.fillStyle = i % 5 === 0 ? "#59C9F5" : "#2c4a68";
      ctx.fillRect(i * barW + 1, h - barH, barW - 2, barH);
    }
    t += 0.05;
    if (!REDUCED_MOTION) requestAnimationFrame(frame);
  }
  frame();
}
