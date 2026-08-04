"use strict";

const $ = (id) => document.getElementById(id);
const token = document.body.dataset.token;
let activeJob = null;
let paused = false;
let results = [];
let total = 0;
let terminalEventSeen = false;

const elements = {
  run: $("runButton"), pause: $("pauseButton"), cancel: $("cancelButton"), csv: $("csvLink"),
  state: $("stateBadge"), message: $("message"), progress: $("progressBar"), body: $("resultsBody"),
  completed: $("completedMetric"), interesting: $("interestingMetric"), errors: $("errorMetric"),
  search: $("search"), status: $("statusFilter"), differences: $("differenceOnly"),
  drawer: $("drawer"), drawerContent: $("drawerContent"), drawerClose: $("drawerClose")
};

function buildPayload() {
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

function validatePayload(data) {
  let parsed;
  try { parsed = new URL(data.url); } catch (_) { throw new Error("Enter a valid URL beginning with http:// or https://."); }
  if (!["http:", "https:"].includes(parsed.protocol)) throw new Error("Only http:// and https:// URLs are supported.");
  const numeric = [
    ["Workers", data.workers, 1, 16],
    ["Delay ms", data.delay_ms, 0, 3600000],
    ["Timeout", data.timeout, 0.1, 300],
    ["Retries", data.retries, 0, 5],
    ["Maximum requests", data.max_requests, 1, 10000]
  ];
  for (const [name, value, minimum, maximum] of numeric) {
    if (!Number.isFinite(value) || value < minimum || value > maximum) throw new Error(`${name} must be between ${minimum} and ${maximum}.`);
  }
  if (data.body_type === "none" && data.body.trim()) {
    throw new Error("A request body was entered, but Body type is None. Select JSON, Form URL encoded, or Raw.");
  }
  if (data.body_type === "json" && data.body.trim()) {
    try { JSON.parse(data.body); } catch (error) { throw new Error(`Invalid JSON body: ${error.message}`); }
  }
  if (data.payloads.trim() && !/\{\{[A-Za-z_][A-Za-z0-9_]*\}\}/.test(JSON.stringify(data))) {
    throw new Error("Payloads were provided, but no {{VALUE}} or named placeholder exists in the request.");
  }
  return data;
}

function formatApiDetail(value, fallback) {
  if (!value) return fallback;
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.map((item) => formatApiDetail(item, "")).filter(Boolean).join("\n");
  if (typeof value === "object") {
    const location = Array.isArray(value.loc) ? value.loc.join(".") : "";
    const message = value.msg || value.message || JSON.stringify(value);
    return location ? `${location}: ${message}` : message;
  }
  return String(value);
}

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  headers.set("X-Request-Token", token);
  if (options.body) headers.set("Content-Type", "application/json");
  let response;
  try { response = await fetch(path, {...options, headers, credentials: "same-origin"}); }
  catch (error) { throw new Error(`Unable to reach the local web service: ${error.message}`); }
  if (!response.ok) {
    const fallback = `${response.status} ${response.statusText}`;
    let detail = fallback;
    try { detail = formatApiDetail((await response.json()).detail, fallback); } catch (_) {}
    throw new Error(detail);
  }
  return response;
}

function setState(text, kind = "") {
  elements.state.textContent = text;
  elements.state.dataset.kind = kind;
}

function closeDrawer() {
  elements.drawer.classList.remove("open");
  elements.drawer.setAttribute("aria-hidden", "true");
}

function resetRun() {
  results = [];
  total = 0;
  activeJob = null;
  paused = false;
  terminalEventSeen = false;
  elements.body.replaceChildren();
  elements.progress.style.width = "0%";
  elements.completed.textContent = "0";
  elements.interesting.textContent = "0";
  elements.errors.textContent = "0";
  elements.message.textContent = "";
  elements.pause.disabled = true;
  elements.cancel.disabled = true;
  elements.pause.textContent = "Pause";
  elements.csv.classList.add("disabled");
  elements.csv.removeAttribute("href");
  closeDrawer();
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

function displayMetric(value, suffix = "") {
  return value === null || value === undefined || value === "" ? "-" : `${value}${suffix}`;
}

function renderRows() {
  const fragment = document.createDocumentFragment();
  for (const item of results.filter(visible)) {
    const row = document.createElement("tr");
    const different = item.similarity !== null && item.similarity !== undefined && (Number(item.similarity) < 99.99 || item.cluster !== "C1");
    if (different) row.classList.add("different");
    if (item.error) row.classList.add("error");
    const values = [
      item.index, item.name, item.method ?? "-", item.status ?? "-", item.size_bytes,
      displayMetric(item.elapsed_ms, " ms"), displayMetric(item.similarity, "%"),
      displayMetric(item.cluster), displayMetric(item.anomaly_score), item.location ?? ""
    ];
    for (const value of values) {
      const cell = document.createElement("td");
      cell.textContent = String(value ?? "");
      row.appendChild(cell);
    }
    row.addEventListener("click", () => openDrawer(item));
    fragment.appendChild(row);
  }
  elements.body.replaceChildren(fragment);
}

function updateMetrics() {
  elements.completed.textContent = String(results.length);
  elements.interesting.textContent = String(results.filter((item) => item.matched || (item.similarity !== null && Number(item.similarity) < 99.99) || Number(item.anomaly_score || 0) >= 4).length);
  elements.errors.textContent = String(results.filter((item) => item.error).length);
  elements.progress.style.width = total ? `${Math.min(100, results.length / total * 100)}%` : "0%";
}

function openDrawer(item) {
  elements.drawerContent.textContent = JSON.stringify(item, null, 2);
  elements.drawer.classList.add("open");
  elements.drawer.setAttribute("aria-hidden", "false");
}

function applySnapshot(event) {
  results = Array.isArray(event.results) ? event.results : [];
  total = Number(event.total || total || results.length);
  updateMetrics();
  renderRows();
}

async function stream(jobId) {
  const response = await api(`/api/jobs/${jobId}/events`);
  if (!response.body) throw new Error("The browser did not provide a readable response stream.");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const {value, done} = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, {stream: true});
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    for (const line of lines) {
      if (!line.trim()) continue;
      let event;
      try { event = JSON.parse(line); } catch (_) { throw new Error("The web service returned a malformed event stream."); }
      if (event.event === "meta") total = Number(event.total || 0);
      if (event.event === "result") {
        results.push(event.result);
        total = Number(event.total || total);
        updateMetrics();
        renderRows();
      }
      if (event.event === "snapshot") applySnapshot(event);
      if (event.event === "done") {
        terminalEventSeen = true;
        setState(event.status === "done" ? "Completed" : event.status === "cancelled" ? "Cancelled" : "Error");
      }
      if (event.event === "fatal") {
        terminalEventSeen = true;
        throw new Error(event.error || "The scan failed.");
      }
    }
  }
  if (!terminalEventSeen) {
    const statusResponse = await api(`/api/jobs/${jobId}`);
    const status = await statusResponse.json();
    if (Array.isArray(status.results) && status.results.length) applySnapshot(status);
    if (!["done", "cancelled"].includes(status.status)) throw new Error(`The event stream ended while the job was ${status.status}.`);
    setState(status.status === "done" ? "Completed" : "Cancelled");
  }
}

function finishRun() {
  elements.run.disabled = false;
  elements.pause.disabled = true;
  elements.cancel.disabled = true;
  if (activeJob) {
    elements.csv.href = `/api/jobs/${activeJob}/csv`;
    elements.csv.classList.remove("disabled");
  }
}

async function run() {
  if (elements.run.disabled) return;
  resetRun();
  setState("Validating");
  elements.run.disabled = true;
  try {
    const requestPayload = validatePayload(buildPayload());
    setState("Starting");
    const response = await api("/api/jobs", {method: "POST", body: JSON.stringify(requestPayload)});
    const data = await response.json();
    activeJob = data.job_id;
    total = Number(data.total || 0);
    elements.pause.disabled = false;
    elements.cancel.disabled = false;
    setState("Running");
    await stream(activeJob);
  } catch (error) {
    elements.message.textContent = error.message;
    setState("Error");
  } finally {
    finishRun();
  }
}

async function pauseResume() {
  if (!activeJob || elements.pause.disabled) return;
  elements.pause.disabled = true;
  try {
    const action = paused ? "resume" : "pause";
    await api(`/api/jobs/${activeJob}/${action}`, {method: "POST"});
    paused = !paused;
    elements.pause.textContent = paused ? "Resume" : "Pause";
    setState(paused ? "Paused" : "Running");
  } catch (error) {
    elements.message.textContent = error.message;
  } finally {
    if (!terminalEventSeen) elements.pause.disabled = false;
  }
}

async function cancel() {
  if (!activeJob || elements.cancel.disabled) return;
  elements.cancel.disabled = true;
  try {
    await api(`/api/jobs/${activeJob}/cancel`, {method: "POST"});
    elements.pause.disabled = true;
    setState("Cancelling");
  } catch (error) {
    elements.message.textContent = error.message;
    elements.cancel.disabled = false;
  }
}

document.querySelectorAll(".tab").forEach((button) => button.addEventListener("click", () => {
  document.querySelectorAll(".tab").forEach((item) => item.classList.toggle("active", item === button));
  document.querySelectorAll(".tab-content").forEach((panel) => panel.classList.toggle("active", panel.dataset.panel === button.dataset.tab));
}));

elements.run.addEventListener("click", run);
elements.pause.addEventListener("click", pauseResume);
elements.cancel.addEventListener("click", cancel);
elements.search.addEventListener("input", renderRows);
elements.status.addEventListener("change", renderRows);
elements.differences.addEventListener("change", renderRows);
elements.drawerClose.addEventListener("click", closeDrawer);

document.addEventListener("keydown", (event) => { if (event.key === "Escape") closeDrawer(); });

const savedTheme = localStorage.getItem("imr-intruder-theme");
if (savedTheme === "light") document.documentElement.classList.add("light");
$("themeButton").addEventListener("click", () => {
  document.documentElement.classList.toggle("light");
  localStorage.setItem("imr-intruder-theme", document.documentElement.classList.contains("light") ? "light" : "dark");
});
