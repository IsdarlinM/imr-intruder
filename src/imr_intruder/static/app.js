"use strict";

const $ = (id) => document.getElementById(id);
const token = document.body.dataset.token;
let activeJob = null;
let paused = false;
let results = [];
let total = 0;

const elements = {
  run: $("runButton"), pause: $("pauseButton"), cancel: $("cancelButton"), csv: $("csvLink"),
  state: $("stateBadge"), message: $("message"), progress: $("progressBar"), body: $("resultsBody"),
  completed: $("completedMetric"), interesting: $("interestingMetric"), errors: $("errorMetric"),
  search: $("search"), status: $("statusFilter"), differences: $("differenceOnly"),
  drawer: $("drawer"), drawerContent: $("drawerContent"), drawerClose: $("drawerClose")
};

function payload() {
  return {
    method: $("method").value,
    url: $("url").value.trim(),
    workers: Number($("workers").value),
    delay_ms: Number($("delayMs").value),
    timeout: Number($("timeout").value),
    retries: Number($("retries").value),
    verify_tls: $("verifyTls").checked,
    follow_redirects: $("followRedirects").checked,
    http2: $("http2").checked,
    backoff: $("backoff").checked,
    headers: $("headers").value,
    params: $("params").value,
    cookies: $("cookies").value,
    body_type: $("bodyType").value,
    body: $("body").value,
    payloads: $("payloads").value,
    mode: $("mode").value,
    max_requests: Number($("maxRequests").value),
    columns: $("columns").value,
    match: $("match").value,
    exclude: $("exclude").value,
    extract: $("extract").value
  };
}

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  headers.set("X-Request-Token", token);
  if (options.body) headers.set("Content-Type", "application/json");
  const response = await fetch(path, {...options, headers});
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try { detail = (await response.json()).detail || detail; } catch (_) {}
    throw new Error(detail);
  }
  return response;
}

function setState(text, kind = "") {
  elements.state.textContent = text;
  elements.state.dataset.kind = kind;
}

function resetRun() {
  results = []; total = 0; activeJob = null; paused = false;
  elements.body.replaceChildren(); elements.progress.style.width = "0%";
  elements.completed.textContent = "0"; elements.interesting.textContent = "0"; elements.errors.textContent = "0";
  elements.message.textContent = ""; elements.pause.disabled = true; elements.cancel.disabled = true;
  elements.pause.textContent = "Pause"; elements.csv.classList.add("disabled"); elements.csv.href = "#";
}

function statusClass(status) {
  const code = Number(status);
  if (!status) return "error";
  if (code >= 200 && code < 300) return "ok";
  if (code >= 300 && code < 400) return "redirect";
  return "error";
}

function visible(item) {
  const search = elements.search.value.toLowerCase();
  if (search && !JSON.stringify(item).toLowerCase().includes(search)) return false;
  const selected = elements.status.value;
  if (selected === "error" && !item.error) return false;
  if (/^[2-5]$/.test(selected) && !String(item.status || "").startsWith(selected)) return false;
  if (elements.differences.checked && Number(item.similarity ?? 100) >= 99.99 && !item.error) return false;
  return true;
}

function renderRows() {
  const fragment = document.createDocumentFragment();
  for (const item of results.filter(visible)) {
    const row = document.createElement("tr");
    const different = Number(item.similarity ?? 100) < 99.99 || item.cluster !== "C1";
    if (different) row.classList.add("different");
    if (item.error) row.classList.add("error");
    const values = [item.index, item.name, item.status ?? "-", item.size_bytes, `${item.elapsed_ms} ms`, `${item.similarity ?? ""}%`, item.cluster ?? "", item.anomaly_score ?? "", item.location ?? ""];
    for (const value of values) { const cell = document.createElement("td"); cell.textContent = String(value ?? ""); row.appendChild(cell); }
    row.addEventListener("click", () => openDrawer(item));
    fragment.appendChild(row);
  }
  elements.body.replaceChildren(fragment);
}

function updateMetrics() {
  elements.completed.textContent = String(results.length);
  elements.interesting.textContent = String(results.filter((item) => item.matched || Number(item.similarity ?? 100) < 99.99 || Number(item.anomaly_score || 0) >= 4).length);
  elements.errors.textContent = String(results.filter((item) => item.error).length);
  elements.progress.style.width = total ? `${Math.min(100, results.length / total * 100)}%` : "0%";
}

function openDrawer(item) {
  elements.drawerContent.textContent = JSON.stringify(item, null, 2);
  elements.drawer.classList.add("open"); elements.drawer.setAttribute("aria-hidden", "false");
}

async function stream(jobId) {
  const response = await api(`/api/jobs/${jobId}/events`);
  const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = "";
  while (true) {
    const {value, done} = await reader.read(); if (done) break;
    buffer += decoder.decode(value, {stream: true});
    const lines = buffer.split("\n"); buffer = lines.pop() || "";
    for (const line of lines) {
      if (!line.trim()) continue;
      const event = JSON.parse(line);
      if (event.event === "meta") total = event.total;
      if (event.event === "result") { results.push(event.result); total = event.total; updateMetrics(); renderRows(); }
      if (event.event === "done") { setState(event.status === "done" ? "Completed" : "Cancelled"); finishRun(); }
      if (event.event === "fatal") { throw new Error(event.error); }
    }
  }
}

function finishRun() {
  elements.run.disabled = false; elements.pause.disabled = true; elements.cancel.disabled = true;
  if (activeJob) { elements.csv.href = `/api/jobs/${activeJob}/csv?token=${encodeURIComponent(token)}`; elements.csv.classList.remove("disabled"); }
}

async function run() {
  resetRun(); setState("Starting"); elements.run.disabled = true; elements.message.textContent = "";
  try {
    const response = await api("/api/jobs", {method: "POST", body: JSON.stringify(payload())});
    const data = await response.json(); activeJob = data.job_id; total = data.total;
    elements.pause.disabled = false; elements.cancel.disabled = false; setState("Running");
    await stream(activeJob);
  } catch (error) {
    elements.message.textContent = error.message; setState("Error"); finishRun();
  }
}

async function pauseResume() {
  if (!activeJob) return;
  try {
    const action = paused ? "resume" : "pause";
    await api(`/api/jobs/${activeJob}/${action}`, {method: "POST"});
    paused = !paused; elements.pause.textContent = paused ? "Resume" : "Pause"; setState(paused ? "Paused" : "Running");
  } catch (error) { elements.message.textContent = error.message; }
}

async function cancel() {
  if (!activeJob) return;
  try { await api(`/api/jobs/${activeJob}/cancel`, {method: "POST"}); setState("Cancelling"); }
  catch (error) { elements.message.textContent = error.message; }
}

document.querySelectorAll(".tab").forEach((button) => button.addEventListener("click", () => {
  document.querySelectorAll(".tab").forEach((item) => item.classList.toggle("active", item === button));
  document.querySelectorAll(".tab-content").forEach((panel) => panel.classList.toggle("active", panel.dataset.panel === button.dataset.tab));
}));

elements.run.addEventListener("click", run); elements.pause.addEventListener("click", pauseResume); elements.cancel.addEventListener("click", cancel);
elements.search.addEventListener("input", renderRows); elements.status.addEventListener("change", renderRows); elements.differences.addEventListener("change", renderRows);
elements.drawerClose.addEventListener("click", () => { elements.drawer.classList.remove("open"); elements.drawer.setAttribute("aria-hidden", "true"); });
$("themeButton").addEventListener("click", () => document.documentElement.classList.toggle("light"));
