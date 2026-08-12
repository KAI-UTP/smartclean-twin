/* SmartClean Twin operator console.
   Polls /api/state once per second and renders the twin. All requests go to
   this service, which proxies them to the other microservices. */

const POLL_MS = 1000;
const ROOM_M = 5.0;          // room is 5 m x 5 m
const CELL_M = 0.5;          // grid cell size

const $ = (id) => document.getElementById(id);
const fmt = (v, d = 1) => (typeof v === "number" && isFinite(v) ? v.toFixed(d) : "--");

/* ---------------------------------------------------------------- state */

async function poll() {
  try {
    const r = await fetch("/api/state");
    if (!r.ok) throw new Error("HTTP " + r.status);
    render(await r.json());
    setPill($("conn"), "live", "pill-ok");
  } catch (e) {
    setPill($("conn"), "disconnected", "pill-bad");
  }
}

function setPill(el, text, cls) {
  el.textContent = text;
  el.className = "pill " + cls;
}

function setTile(tile, valueEl, text, kind) {
  valueEl.textContent = text;
  tile.className = "tile" + (tile.classList.contains("wide") ? " wide" : "") +
                   (kind ? " " + kind : "");
}

function render(d) {
  const t = d.telemetry || {}, s = d.state || {}, p = d.prediction || {};

  /* status strip */
  const safety = s.safety_state || "--";
  setTile($("tileSafety"), $("safetyState"), safety,
    safety === "SAFE" ? "ok" : safety === "WARNING" ? "warn" :
    safety === "EMERGENCY" ? "bad" : "");

  setTile($("tileMission"), $("missionState"), s.mission_state || "--", "info");

  const health = p.health_state || "--";
  setTile($("tileHealth"), $("healthState"), health,
    health === "NORMAL" ? "ok" : health === "WARNING" ? "warn" :
    health === "CRITICAL" ? "bad" : "");

  const anom = p.is_anomaly;
  setTile($("tileAnomaly"), $("anomaly"),
    anom === undefined ? "--" : (anom >= 1 ? "DETECTED" : "none"),
    anom === undefined ? "" : (anom >= 1 ? "bad" : "ok"));

  const rec = p.recommendation || "--";
  setTile($("tileRec"), $("recommendation"), rec,
    rec.startsWith("Normal") ? "ok" :
    rec.startsWith("STOP") || rec.startsWith("Sensor") ? "bad" :
    rec === "--" ? "" : "warn");

  /* position */
  $("posX").textContent = fmt(t.x_m, 2);
  $("posY").textContent = fmt(t.y_m, 2);
  $("heading").textContent = fmt(t.heading_deg, 0);
  $("speed").textContent = fmt(t.speed_mps, 2);
  drawMap(t.x_m, t.y_m, t.heading_deg, safety);

  /* meters */
  meter("soc", t.battery_soc, "%");
  meter("cov", s.cleaning_coverage_pct, "%");
  meter("water", t.water_level_pct, "%");

  /* readouts */
  $("motorTemp").textContent = fmt(t.motor_temperature_c, 1);
  $("motorCurr").textContent = fmt(t.motor_current_a, 2);
  $("obstacle").textContent = fmt(t.obstacle_cm, 0);
  $("rul").textContent = fmt(p.predicted_rul_minutes, 0);
  $("toEmpty").textContent = p.minutes_to_empty === undefined
    ? "charging or idle" : fmt(p.minutes_to_empty, 0) + " min";
  $("toFinish").textContent = p.minutes_to_finish === undefined
    ? "not cleaning" : fmt(p.minutes_to_finish, 0) + " min";
}

function meter(prefix, value, unit) {
  const pct = typeof value === "number" ? Math.max(0, Math.min(100, value)) : 0;
  $(prefix + "Bar").style.width = pct + "%";
  $(prefix + "Txt").textContent = typeof value === "number"
    ? value.toFixed(1) + unit : "--";
  if (prefix === "soc") {
    $("socBar").style.background =
      pct > 40 ? "var(--gr)" : pct > 20 ? "var(--or)" : "var(--rd)";
  }
}

/* ---------------------------------------------------------------- map */

function drawMap(x, y, heading, safety) {
  const c = $("map"), g = c.getContext("2d");
  const W = c.width, H = c.height, pad = 18;
  const span = W - pad * 2;
  const sx = (m) => pad + (m / ROOM_M) * span;
  const sy = (m) => H - pad - (m / ROOM_M) * span;   // y up

  g.clearRect(0, 0, W, H);

  /* floor and grid */
  g.fillStyle = "#111b25";
  g.fillRect(pad, pad, span, span);
  g.strokeStyle = "#22303d";
  g.lineWidth = 1;
  for (let m = 0; m <= ROOM_M + 0.001; m += CELL_M) {
    g.beginPath(); g.moveTo(sx(m), sy(0)); g.lineTo(sx(m), sy(ROOM_M)); g.stroke();
    g.beginPath(); g.moveTo(sx(0), sy(m)); g.lineTo(sx(ROOM_M), sy(m)); g.stroke();
  }
  g.strokeStyle = "#3a4a5c"; g.lineWidth = 2;
  g.strokeRect(pad, pad, span, span);

  /* desk obstacles, matching grid_map blocked cells */
  g.fillStyle = "rgba(140,100,60,.55)";
  [[2.0, 1.25, 0.4, 1.1], [3.0, 2.25, 0.4, 1.1], [1.5, 3.5, 0.4, 0.4]]
    .forEach(([cx, cy, w, h]) => {
      g.fillRect(sx(cx - w / 2), sy(cy + h / 2), (w / ROOM_M) * span, (h / ROOM_M) * span);
    });

  /* dock */
  g.fillStyle = "rgba(34,211,238,.35)";
  g.fillRect(sx(0.25) - 7, sy(0.25) - 7, 14, 14);

  if (typeof x !== "number" || typeof y !== "number") return;

  /* robot */
  const col = safety === "EMERGENCY" ? "#f87171"
            : safety === "WARNING" ? "#fbbf24" : "#34d399";
  const rx = sx(x), ry = sy(y);
  g.beginPath(); g.arc(rx, ry, 11, 0, Math.PI * 2);
  g.fillStyle = col; g.fill();
  g.strokeStyle = "rgba(255,255,255,.65)"; g.lineWidth = 2; g.stroke();

  /* heading arrow */
  if (typeof heading === "number") {
    const rad = (heading * Math.PI) / 180;
    g.beginPath();
    g.moveTo(rx, ry);
    g.lineTo(rx + Math.cos(rad) * 22, ry - Math.sin(rad) * 22);
    g.strokeStyle = col; g.lineWidth = 3; g.stroke();
  }
}

/* ---------------------------------------------------------------- actions */

async function post(url, body, box, label) {
  box.className = "ack";
  box.textContent = label + " ...";
  try {
    const r = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || "HTTP " + r.status);
    return data;
  } catch (e) {
    box.className = "ack bad";
    box.textContent = "Failed: " + e.message;
    return null;
  }
}

document.querySelectorAll("[data-cmd]").forEach((b) => {
  b.addEventListener("click", async () => {
    const box = $("ackBox");
    document.querySelectorAll("[data-cmd]").forEach((x) => (x.disabled = true));
    const d = await post("/api/command", { command: b.dataset.cmd }, box,
                         "Sending " + b.dataset.cmd);
    document.querySelectorAll("[data-cmd]").forEach((x) => (x.disabled = false));
    if (!d) return;
    const ok = d.ack_received && d.ack_accepted;
    box.className = "ack " + (ok ? "ok" : "bad");
    box.textContent =
      `command   : ${d.command}\n` +
      `command_id: ${d.command_id}\n` +
      `status    : ${d.status}\n` +
      `ACK       : ${d.ack_received ? "received" : "not received"}` +
      (d.ack_accepted !== null && d.ack_accepted !== undefined
        ? ` , accepted=${d.ack_accepted}` : "") +
      (d.ack_timestamp ? `\nACK time  : ${d.ack_timestamp}` : "");
    loadHistory();
  });
});

document.querySelectorAll("[data-fault]").forEach((b) => {
  b.addEventListener("click", async () => {
    const box = $("faultBox");
    const d = await post("/api/fault", { fault: b.dataset.fault }, box,
                         "Injecting " + b.dataset.fault);
    if (!d) return;
    box.className = "ack " + (b.dataset.fault === "clear" ? "ok" : "bad");
    box.textContent = b.dataset.fault === "clear"
      ? "All faults cleared. The twin returns to SAFE within a few seconds."
      : `Fault '${d.injected || b.dataset.fault}' injected.\n` +
        "Watch the status strip above, the Grafana dashboard and the 3D scene.";
  });
});

["Temp", "Curr", "Soc", "Water"].forEach((k) => {
  const inp = $("w" + k), out = $("o" + k);
  inp.addEventListener("input", () => (out.textContent = inp.value));
});

$("runWhatIf").addEventListener("click", async () => {
  const box = $("whatifBox");
  const d = await post("/api/whatif", {
    motor_temperature_c: parseFloat($("wTemp").value),
    motor_current_a: parseFloat($("wCurr").value),
    battery_soc: parseFloat($("wSoc").value),
    water_level_pct: parseFloat($("wWater").value),
  }, box, "Running scenario");
  if (!d) return;
  const p = d.prediction || {};
  box.className = "ack " + (p.health_state_prediction === "NORMAL" ? "ok" : "bad");
  box.textContent =
    `motor health  : ${p.motor_health_prediction} (confidence ${p.motor_health_confidence})\n` +
    `health state  : ${p.health_state_prediction} (confidence ${p.health_state_confidence})\n` +
    `predicted RUL : ${p.predicted_rul_minutes} minutes\n` +
    `anomaly       : ${p.is_anomaly} (score ${p.anomaly_score})\n` +
    `recommendation: ${p.recommendation}`;
});

/* ---------------------------------------------------------------- history */

async function loadHistory() {
  try {
    const r = await fetch("/api/history");
    const rows = await r.json();
    const body = $("histBody");
    if (!rows.length) {
      body.innerHTML = '<tr><td colspan="3" class="muted">No commands yet.</td></tr>';
      return;
    }
    body.innerHTML = rows.map((c) => {
      const ok = c.ack_received && c.ack_accepted;
      return `<tr><td>${c.command}</td><td class="muted">${c.status}</td>` +
             `<td class="${ok ? "ok-txt" : "bad-txt"}">${ok ? "accepted" : "no ACK"}</td></tr>`;
    }).join("");
  } catch (e) { /* leave the previous table in place */ }
}

poll();
loadHistory();
setInterval(poll, POLL_MS);
setInterval(loadHistory, 5000);
