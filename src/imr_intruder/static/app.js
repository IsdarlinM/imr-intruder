"use strict";

const $ = (id) => document.getElementById(id);
let activeJob = null;
let paused = false;
let results = [];
let total = 0;
let terminalEventSeen = false;
let lastSequence = 0;
let previousFocus = null;

const elements = {
  run: $("runButton"), pause: $("pauseButton"), cancel: $("cancelButton"), csv: $("csvLink"),
  state: $("stateBadge"), message: $("message"), progress: $("progressBar"), body: $("resultsBody"),
  completed: $("completedMetric"), total: $("totalMetric"), interesting: $("interestingMetric"), errors: $("errorMetric"),
  search: $("search"), status: $("statusFilter"), differences: $("differenceOnly"),
  empty: $("emptyState"), table: $("tableWrap"), drawer: $("drawer"), backdrop: $("drawerBackdrop"),
  drawerContent: $("drawerContent"), drawerClose: $("drawerClose"), copy: $("copyButton")
};

function numberValue(id) {
  const raw = $(id).value.trim();
  return raw === "" ? null : Number(raw);
}

function buildPayload() {
  return {
    name: $("requestName").value.trim(), method: $("method").value, url: $("url").value.trim(),
    workers: numberValue("workers"), delay_ms: numberValue("delayMs"), rate: numberValue("rate"),
    timeout: numberValue("timeout"), retries: numberValue("retries"),
    body_limit: numberValue("bodyLimit") * 1024, cluster_threshold: numberValue("clusterThreshold"),
    verify_tls: $("verifyTls").checked, follow_redirects: $("followRedirects").checked,
    http2: $("http2").checked, backoff: $("backoff").checked,
    headers: $("headers").value, params: $("params").value, cookies: $("cookies").value,
    body_type: $("bodyType").value, body: $("body").value, payloads: $("payloads").value,
    mode: $("mode").value, max_requests: numberValue("maxRequests"), columns: $("columns").value,
    match: $("match").value, exclude: $("exclude").value, extract: $("extract").value
  };
}

function validatePayload(data) {
  let parsed;
  try { parsed = new URL(data.url); } catch (_) { throw new Error("Enter a valid absolute URL beginning with http:// or https://."); }
  if (!["http:", "https:"].includes(parsed.protocol) || !parsed.hostname) throw new Error("Only absolute http:// and https:// URLs are supported.");
  const integers = [
    ["Workers", data.workers, 1, 16], ["Delay ms", data.delay_ms, 0, 3600000],
    ["Retries", data.retries, 0, 5], ["Maximum requests", data.max_requests, 1, 10000],
    ["Preview KiB", data.body_limit / 1024, 1, 1024]
  ];
  for (const [name, value, minimum, maximum] of integers) {
    if (!Number.isInteger(value) || value < minimum || value > maximum) throw new Error(`${name} must be a whole number between ${minimum} and ${maximum}.`);
  }
  const numbers = [
    ["Timeout", data.timeout, 0.1, 300], ["Cluster threshold", data.cluster_threshold, 0, 100]
  ];
  if (data.rate !== null) numbers.push(["Rate", data.rate, 0.001, 10000]);
  for (const [name, value, minimum, maximum] of numbers) {
    if (!Number.isFinite(value) || value < minimum || value > maximum) throw new Error(`${name} must be between ${minimum} and ${maximum}.`);
  }
  if (data.body_type === "none" && data.body.trim()) throw new Error("A request body was entered, but Body type is None.");
  if (data.body_type === "json" && data.body.trim()) {
    try { JSON.parse(data.body); } catch (error) { throw new Error(`Invalid JSON body: ${error.message}`); }
  }
  const requestSurface = JSON.stringify({url: data.url, headers: data.headers, params: data.params, cookies: data.cookies, body: data.body});
  if (data.payloads.trim() && !/\{\{[A-Za-z_][A-Za-z0-9_]*\}\}/.test(requestSurface)) throw new Error("Payloads were provided, but the request has no placeholder.");
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
  if (options.body) headers.set("Content-Type", "application/json");
  let response;
  try { response = await fetch(path, {...options, headers, credentials: "same-origin"}); }
  catch (error) { throw new Error(`Unable to reach the web service: ${error.message}`); }
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
  elements.backdrop.hidden = true;
  if (previousFocus) previousFocus.focus();
}

function resetRun() {
  results = []; total = 0; activeJob = null; paused = false; terminalEventSeen = false; lastSequence = 0;
  elements.body.replaceChildren(); elements.progress.style.width = "0%";
  elements.progress.parentElement.setAttribute("aria-valuenow", "0");
  elements.completed.textContent = "0"; elements.total.textContent = "0";
  elements.interesting.textContent = "0"; elements.errors.textContent = "0"; elements.message.textContent = "";
  elements.pause.disabled = true; elements.cancel.disabled = true; elements.pause.textContent = "Pause";
  elements.csv.classList.add("disabled"); elements.csv.setAttribute("aria-disabled", "true"); elements.csv.removeAttribute("href");
  elements.empty.hidden = false; elements.table.hidden = true; closeDrawer();
}

function visible(item) {
  const search = elements.search.value.toLowerCase();
  if (search && !JSON.stringify(item).toLowerCase().includes(search)) return false;
  const selected = elements.status.value;
  if (selected === "error" && !item.error) return false;
  if (/^[2-5]$/.test(selected) && !String(item.status || "").startsWith(selected)) return false;
  return !(elements.differences.checked && Number(item.similarity ?? 100) >= 99.99 && !item.error);
}

function displayMetric(value, suffix = "") {
  return value === null || value === undefined || value === "" ? "—" : `${value}${suffix}`;
}

function statusClass(status) {
  const first = String(status || "")[0];
  return first === "2" ? "success" : first === "3" ? "redirect" : first === "4" || first === "5" ? "failure" : "neutral";
}

function renderRows() {
  const fragment = document.createDocumentFragment();
  for (const item of results.filter(visible)) {
    const row = document.createElement("tr");
    row.tabIndex = 0; row.setAttribute("aria-label", `Open response ${item.index}`);
    const different = item.similarity !== null && item.similarity !== undefined && (Number(item.similarity) < 99.99 || item.cluster !== "C1");
    if (different) row.classList.add("different");
    if (item.error) row.classList.add("error");
    const values = [item.index, item.name, item.method ?? "—", item.status ?? "—", item.size_bytes, displayMetric(item.elapsed_ms, " ms"), displayMetric(item.similarity, "%"), displayMetric(item.cluster), displayMetric(item.anomaly_score), item.location ?? ""];
    values.forEach((value, index) => {
      const cell = document.createElement("td"); cell.textContent = String(value ?? "");
      if (index === 3) cell.className = `status-cell ${statusClass(item.status)}`;
      row.appendChild(cell);
    });
    const open = () => openDrawer(item);
    row.addEventListener("click", open);
    row.addEventListener("keydown", (event) => { if (["Enter", " "].includes(event.key)) { event.preventDefault(); open(); } });
    fragment.appendChild(row);
  }
  elements.body.replaceChildren(fragment);
  elements.empty.hidden = results.length > 0;
  elements.table.hidden = results.length === 0;
}

function updateMetrics() {
  elements.total.textContent = String(total);
  elements.completed.textContent = String(results.length);
  elements.interesting.textContent = String(results.filter((item) => item.matched || (item.similarity !== null && Number(item.similarity) < 99.99) || Number(item.anomaly_score || 0) >= 4).length);
  elements.errors.textContent = String(results.filter((item) => item.error).length);
  const percent = total ? Math.min(100, results.length / total * 100) : 0;
  elements.progress.style.width = `${percent}%`;
  elements.progress.parentElement.setAttribute("aria-valuenow", String(Math.round(percent)));
}

function openDrawer(item) {
  previousFocus = document.activeElement;
  elements.drawerContent.textContent = JSON.stringify(item, null, 2);
  elements.drawer.classList.add("open"); elements.drawer.setAttribute("aria-hidden", "false");
  elements.backdrop.hidden = false; elements.drawerClose.focus();
}

function upsertResult(item) {
  const existing = results.findIndex((row) => row.index === item.index);
  if (existing >= 0) results[existing] = item; else results.push(item);
  results.sort((left, right) => left.index - right.index);
}

function applySnapshot(event) {
  results = Array.isArray(event.results) ? event.results : [];
  total = Number(event.total || total || results.length); updateMetrics(); renderRows();
}

function handleEvent(event) {
  if (Number.isInteger(event.sequence)) lastSequence = Math.max(lastSequence, event.sequence);
  if (event.event === "meta") { total = Number(event.total || 0); updateMetrics(); }
  if (event.event === "result") { upsertResult(event.result); total = Number(event.total || total); updateMetrics(); renderRows(); }
  if (event.event === "snapshot") applySnapshot(event);
  if (event.event === "done") { terminalEventSeen = true; setState(event.status === "done" ? "Completed" : event.status === "cancelled" ? "Cancelled" : "Error", event.status); }
  if (event.event === "fatal") { terminalEventSeen = true; throw new Error(event.error || "The scan failed."); }
}

async function readStream(response) {
  if (!response.body) throw new Error("The browser did not provide a readable response stream.");
  const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = "";
  while (true) {
    const {value, done} = await reader.read(); if (done) break;
    buffer += decoder.decode(value, {stream: true}); const lines = buffer.split("\n"); buffer = lines.pop() || "";
    for (const line of lines) { if (line.trim()) handleEvent(JSON.parse(line)); }
  }
}

async function stream(jobId) {
  let failure = null;
  for (let attempt = 0; attempt < 4 && !terminalEventSeen; attempt += 1) {
    try { await readStream(await api(`/api/jobs/${jobId}/events?after=${lastSequence}`)); failure = null; }
    catch (error) { failure = error; }
    if (!terminalEventSeen) {
      const status = await (await api(`/api/jobs/${jobId}`)).json();
      if (Array.isArray(status.results) && status.results.length) applySnapshot(status);
      if (["done", "cancelled", "error"].includes(status.status)) { terminalEventSeen = true; setState(status.status === "done" ? "Completed" : status.status === "cancelled" ? "Cancelled" : "Error", status.status); break; }
      await new Promise((resolve) => setTimeout(resolve, 250 * (attempt + 1)));
    }
  }
  if (!terminalEventSeen) throw failure || new Error("The event stream ended before the job completed.");
}

function finishRun() {
  elements.run.disabled = false; elements.pause.disabled = true; elements.cancel.disabled = true;
  if (activeJob) { elements.csv.href = `/api/jobs/${activeJob}/csv`; elements.csv.classList.remove("disabled"); elements.csv.setAttribute("aria-disabled", "false"); }
}

async function run() {
  if (elements.run.disabled) return;
  resetRun(); setState("Validating"); elements.run.disabled = true;
  try {
    const requestPayload = validatePayload(buildPayload()); setState("Starting");
    const data = await (await api("/api/jobs", {method: "POST", body: JSON.stringify(requestPayload)})).json();
    activeJob = data.job_id; total = Number(data.total || 0); updateMetrics();
    elements.pause.disabled = false; elements.cancel.disabled = false; setState("Running", "running");
    await stream(activeJob);
  } catch (error) { elements.message.textContent = error.message; setState("Error", "error"); }
  finally { finishRun(); }
}

async function pauseResume() {
  if (!activeJob || elements.pause.disabled) return;
  elements.pause.disabled = true;
  try {
    const action = paused ? "resume" : "pause";
    await api(`/api/jobs/${activeJob}/${action}`, {method: "POST"}); paused = !paused;
    elements.pause.textContent = paused ? "Resume" : "Pause"; setState(paused ? "Paused" : "Running", paused ? "paused" : "running");
  } catch (error) { elements.message.textContent = error.message; }
  finally { if (!terminalEventSeen) elements.pause.disabled = false; }
}

async function cancel() {
  if (!activeJob || elements.cancel.disabled) return;
  elements.cancel.disabled = true;
  try { await api(`/api/jobs/${activeJob}/cancel`, {method: "POST"}); elements.pause.disabled = true; setState("Cancelling", "paused"); }
  catch (error) { elements.message.textContent = error.message; elements.cancel.disabled = false; }
}

function activateTab(button) {
  document.querySelectorAll(".tab").forEach((item) => {
    const selected = item === button; item.classList.toggle("active", selected); item.setAttribute("aria-selected", String(selected)); item.tabIndex = selected ? 0 : -1;
  });
  document.querySelectorAll(".tab-content").forEach((panel) => { const selected = panel.dataset.panel === button.dataset.tab; panel.classList.toggle("active", selected); panel.hidden = !selected; });
}

document.querySelectorAll(".tab").forEach((button) => {
  button.addEventListener("click", () => activateTab(button));
  button.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault(); const tabs = [...document.querySelectorAll(".tab")]; const current = tabs.indexOf(button);
    const next = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : (current + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
    activateTab(tabs[next]); tabs[next].focus();
  });
});

elements.run.addEventListener("click", run);
elements.pause.addEventListener("click", pauseResume);
elements.cancel.addEventListener("click", cancel);
elements.search.addEventListener("input", renderRows);
elements.status.addEventListener("change", renderRows);
elements.differences.addEventListener("change", renderRows);
elements.drawerClose.addEventListener("click", closeDrawer);
elements.backdrop.addEventListener("click", closeDrawer);
elements.copy.addEventListener("click", async () => { await navigator.clipboard.writeText(elements.drawerContent.textContent); elements.copy.textContent = "Copied"; setTimeout(() => { elements.copy.textContent = "Copy JSON"; }, 1200); });

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeDrawer();
  if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) { event.preventDefault(); run(); }
});

const savedTheme = localStorage.getItem("imr-intruder-theme");
if (savedTheme === "light") document.documentElement.classList.add("light");
function updateThemeButton() { $("themeButton").textContent = document.documentElement.classList.contains("light") ? "Dark mode" : "Light mode"; }
updateThemeButton();
$("themeButton").addEventListener("click", () => {
  document.documentElement.classList.toggle("light");
  localStorage.setItem("imr-intruder-theme", document.documentElement.classList.contains("light") ? "light" : "dark"); updateThemeButton();
});
