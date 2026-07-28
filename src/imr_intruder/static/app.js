"use strict";

const token = document.querySelector('meta[name="request-token"]').content;
const form = document.getElementById("request-form");
const runButton = document.getElementById("run-button");
const cancelButton = document.getElementById("cancel-button");
const clearButton = document.getElementById("clear-button");
const exportButton = document.getElementById("export-button");
const tableHead = document.getElementById("results-head");
const tableBody = document.getElementById("results-body");
const searchInput = document.getElementById("table-search");
const statusFilter = document.getElementById("status-filter");
const anomalyFilter = document.getElementById("anomaly-filter");
const messageBox = document.getElementById("message-box");
const runStatus = document.getElementById("run-status");
const progressLabel = document.getElementById("progress-label");
const progressBar = document.getElementById("progress-bar");
const elapsedLabel = document.getElementById("elapsed-label");

let currentJobId = null;
let results = [];
let customColumns = [];
let expectedTotal = 0;
let startedAt = null;
let timerId = null;
let running = false;

const fixedColumns = [
  ["index", "#"],
  ["name", "name"],
  ["method", "method"],
  ["status", "status"],
  ["size_bytes", "size_bytes"],
  ["elapsed_ms", "elapsed_ms"],
  ["content_type", "content_type"],
];

function showMessage(message, type = "error") {
  messageBox.textContent = message;
  messageBox.className = `message-box ${type}`;
}

function hideMessage() {
  messageBox.textContent = "";
  messageBox.className = "message-box hidden";
}

function setRunState(isRunning, statusText = "Listo", statusClass = "idle") {
  running = isRunning;
  runButton.disabled = isRunning;
  cancelButton.disabled = !isRunning;
  runStatus.textContent = statusText;
  runStatus.className = `status-pill ${statusClass}`;
}

function formatElapsed(milliseconds) {
  const seconds = Math.max(0, Math.floor(milliseconds / 1000));
  const minutes = Math.floor(seconds / 60).toString().padStart(2, "0");
  const rest = (seconds % 60).toString().padStart(2, "0");
  return `${minutes}:${rest}`;
}

function startTimer() {
  startedAt = performance.now();
  clearInterval(timerId);
  timerId = setInterval(() => {
    elapsedLabel.textContent = formatElapsed(performance.now() - startedAt);
  }, 250);
}

function stopTimer() {
  clearInterval(timerId);
  timerId = null;
  if (startedAt !== null) {
    elapsedLabel.textContent = formatElapsed(performance.now() - startedAt);
  }
}

function collectPayload() {
  return {
    url: document.getElementById("url").value.trim(),
    method: document.getElementById("method").value,
    body_type: document.getElementById("body-type").value,
    body: document.getElementById("body").value,
    headers: document.getElementById("headers").value,
    params: document.getElementById("params").value,
    cookies: document.getElementById("cookies").value,
    values: document.getElementById("values").value,
    columns: document.getElementById("columns").value,
    workers: Number(document.getElementById("workers").value),
    timeout: Number(document.getElementById("timeout").value),
    delay_ms: Number(document.getElementById("delay-ms").value),
    verify_tls: document.getElementById("verify-tls").checked,
    follow_redirects: document.getElementById("follow-redirects").checked,
  };
}

function resetResults() {
  results = [];
  customColumns = [];
  expectedTotal = 0;
  currentJobId = null;
  progressLabel.textContent = "0 / 0";
  progressBar.style.width = "0%";
  elapsedLabel.textContent = "00:00";
  exportButton.disabled = true;
  updateStats();
  renderHeaders();
  renderRows();
}

function renderHeaders() {
  tableHead.replaceChildren();
  const columns = [
    ...fixedColumns.map(([, label]) => label),
    ...customColumns,
    "error",
  ];
  for (const label of columns) {
    const th = document.createElement("th");
    th.textContent = label;
    tableHead.appendChild(th);
  }
}

function mode(values) {
  const counts = new Map();
  let best = null;
  let bestCount = -1;
  for (const value of values) {
    const count = (counts.get(value) || 0) + 1;
    counts.set(value, count);
    if (count > bestCount) {
      best = value;
      bestCount = count;
    }
  }
  return best;
}

function rowSignature(item) {
  return `${item.status}|${item.size_bytes}`;
}

function statusClass(status) {
  const number = Number(status);
  if (!Number.isFinite(number)) return "status-error";
  if (number >= 200 && number < 300) return "status-2xx";
  if (number >= 300 && number < 400) return "status-3xx";
  if (number >= 400 && number < 500) return "status-4xx";
  if (number >= 500) return "status-5xx";
  return "status-error";
}

function itemMatchesStatus(item, filter) {
  if (filter === "all") return true;
  if (filter === "error") return Boolean(item.error);
  const status = Number(item.status);
  if (!Number.isFinite(status)) return false;
  const hundred = Math.floor(status / 100);
  return `${hundred}xx` === filter;
}

function getCellValue(item, key) {
  if (key in item) return item[key];
  return item.custom?.[key] ?? "";
}

function renderRows() {
  tableBody.replaceChildren();

  if (results.length === 0) {
    const row = document.createElement("tr");
    row.className = "empty-row";
    const cell = document.createElement("td");
    cell.colSpan = fixedColumns.length + customColumns.length + 1;
    cell.textContent = running
      ? "Esperando la primera respuesta…"
      : "Configura la solicitud y ejecuta para ver resultados en tiempo real.";
    row.appendChild(cell);
    tableBody.appendChild(row);
    return;
  }

  const query = searchInput.value.trim().toLowerCase();
  const selectedStatus = statusFilter.value;
  const baseline = mode(results.map(rowSignature));
  const onlyAnomalies = anomalyFilter.checked;

  const visible = [...results]
    .sort((a, b) => a.index - b.index)
    .filter((item) => {
      const searchable = JSON.stringify(item).toLowerCase();
      const anomaly = rowSignature(item) !== baseline || Boolean(item.error);
      return (
        (!query || searchable.includes(query)) &&
        itemMatchesStatus(item, selectedStatus) &&
        (!onlyAnomalies || anomaly)
      );
    });

  if (visible.length === 0) {
    const row = document.createElement("tr");
    row.className = "empty-row";
    const cell = document.createElement("td");
    cell.colSpan = fixedColumns.length + customColumns.length + 1;
    cell.textContent = "No hay resultados que coincidan con los filtros.";
    row.appendChild(cell);
    tableBody.appendChild(row);
    return;
  }

  for (const item of visible) {
    const row = document.createElement("tr");
    const anomaly = rowSignature(item) !== baseline;
    if (anomaly) row.classList.add("anomaly");
    if (item.error) row.classList.add("error-row");

    for (const [key] of fixedColumns) {
      const cell = document.createElement("td");
      const value = getCellValue(item, key);
      cell.title = String(value ?? "");
      if (key === "status") {
        const badge = document.createElement("span");
        badge.className = `status-badge ${statusClass(value)}`;
        badge.textContent = String(value);
        cell.appendChild(badge);
      } else {
        cell.textContent = String(value ?? "");
      }
      row.appendChild(cell);
    }

    for (const name of customColumns) {
      const cell = document.createElement("td");
      const value = item.custom?.[name] ?? "";
      cell.textContent = String(value);
      cell.title = String(value);
      row.appendChild(cell);
    }

    const errorCell = document.createElement("td");
    errorCell.textContent = item.error || "";
    errorCell.title = item.error || "";
    row.appendChild(errorCell);
    tableBody.appendChild(row);
  }
}

function updateStats() {
  document.getElementById("stat-completed").textContent = String(results.length);
  document.getElementById("stat-success").textContent = String(
    results.filter((item) => Number(item.status) >= 200 && Number(item.status) < 300).length
  );
  document.getElementById("stat-distinct").textContent = String(
    new Set(results.map(rowSignature)).size
  );
  const average = results.length
    ? results.reduce((sum, item) => sum + Number(item.elapsed_ms || 0), 0) / results.length
    : 0;
  document.getElementById("stat-average").textContent = `${average.toFixed(1)} ms`;
}

function updateProgress(completed, total) {
  expectedTotal = total || expectedTotal;
  progressLabel.textContent = `${completed} / ${expectedTotal}`;
  const percent = expectedTotal ? (completed / expectedTotal) * 100 : 0;
  progressBar.style.width = `${Math.min(100, percent)}%`;
}

async function parseError(response) {
  try {
    const data = await response.json();
    return data.detail || data.error || `Error HTTP ${response.status}`;
  } catch {
    return `Error HTTP ${response.status}`;
  }
}

async function streamEvents(jobId) {
  const response = await fetch(`/api/jobs/${jobId}/events`, {
    headers: { "X-Request-Token": token },
    cache: "no-store",
  });
  if (!response.ok || !response.body) {
    throw new Error(await parseError(response));
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (!line.trim()) continue;
      const event = JSON.parse(line);
      handleEvent(event);
    }
    if (done) break;
  }
}

function handleEvent(event) {
  if (event.event === "heartbeat") return;

  if (event.event === "meta") {
    expectedTotal = event.total;
    customColumns = event.columns || [];
    renderHeaders();
    updateProgress(0, expectedTotal);
    return;
  }

  if (event.event === "result") {
    results.push(event.result);
    updateProgress(event.completed, event.total);
    updateStats();
    renderRows();
    exportButton.disabled = false;
    return;
  }

  if (event.event === "done") {
    stopTimer();
    const cancelled = event.status === "cancelled";
    setRunState(false, cancelled ? "Detenido" : "Completado", cancelled ? "error" : "done");
    updateProgress(event.completed, event.total);
    if (cancelled) showMessage("La ejecución fue detenida. Las solicitudes ya iniciadas pueden haber finalizado.", "info");
    return;
  }

  if (event.event === "fatal") {
    stopTimer();
    setRunState(false, "Error", "error");
    showMessage(event.error || "Error inesperado durante la ejecución.");
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (running) return;

  hideMessage();
  resetResults();
  setRunState(true, "Ejecutando", "running");
  startTimer();
  renderRows();

  try {
    const response = await fetch("/api/jobs", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Request-Token": token,
      },
      body: JSON.stringify(collectPayload()),
    });
    if (!response.ok) throw new Error(await parseError(response));

    const data = await response.json();
    currentJobId = data.job_id;
    expectedTotal = data.total;
    updateProgress(0, expectedTotal);
    await streamEvents(currentJobId);
  } catch (error) {
    stopTimer();
    setRunState(false, "Error", "error");
    showMessage(error instanceof Error ? error.message : String(error));
  }
});

cancelButton.addEventListener("click", async () => {
  if (!currentJobId || !running) return;
  cancelButton.disabled = true;
  try {
    const response = await fetch(`/api/jobs/${currentJobId}/cancel`, {
      method: "POST",
      headers: { "X-Request-Token": token },
    });
    if (!response.ok) throw new Error(await parseError(response));
    runStatus.textContent = "Deteniendo";
    runStatus.className = "status-pill running";
    cancelButton.disabled = true;
  } catch (error) {
    showMessage(error instanceof Error ? error.message : String(error));
    cancelButton.disabled = false;
  }
});

exportButton.addEventListener("click", async () => {
  if (!currentJobId || results.length === 0) return;
  try {
    const response = await fetch(`/api/jobs/${currentJobId}/csv`, {
      headers: { "X-Request-Token": token },
    });
    if (!response.ok) throw new Error(await parseError(response));
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `request-results-${currentJobId.slice(0, 8)}.csv`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  } catch (error) {
    showMessage(error instanceof Error ? error.message : String(error));
  }
});

clearButton.addEventListener("click", () => {
  if (running) {
    showMessage("Detén la ejecución antes de limpiar los resultados.", "info");
    return;
  }
  hideMessage();
  resetResults();
  setRunState(false, "Listo", "idle");
});

for (const element of [searchInput, statusFilter, anomalyFilter]) {
  element.addEventListener("input", renderRows);
  element.addEventListener("change", renderRows);
}

document.querySelectorAll(".tab").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((item) => item.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    document.getElementById(button.dataset.tab).classList.add("active");
  });
});

document.getElementById("body-type").addEventListener("change", (event) => {
  const body = document.getElementById("body");
  if (event.target.value === "json" && !body.value.trim().startsWith("{")) {
    body.value = '{\n  "username": "administrator",\n  "password": "{{VALUE}}"\n}';
  } else if (event.target.value === "form" && body.value.trim().startsWith("{")) {
    body.value = "username=administrator\npassword={{VALUE}}";
  } else if (event.target.value === "none") {
    body.placeholder = "Este método no enviará body.";
  }
});

document.getElementById("theme-toggle").addEventListener("click", () => {
  document.documentElement.classList.toggle("light");
  localStorage.setItem(
    "request-matrix-theme",
    document.documentElement.classList.contains("light") ? "light" : "dark"
  );
});

if (localStorage.getItem("request-matrix-theme") === "light") {
  document.documentElement.classList.add("light");
}

resetResults();
