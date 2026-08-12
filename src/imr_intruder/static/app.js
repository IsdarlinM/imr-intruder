"use strict";

const $ = (id) => document.getElementById(id);
let activeJob = null;
let paused = false;
let results = [];
let total = 0;
let terminalEventSeen = false;
let lastSequence = 0;
let previousFocus = null;
let activeDrawerItem = null;
let sortKey = "index";
let sortDirection = 1;
let historyMode = false;
let currentRole = "viewer";
const MAX_RENDERED_ROWS = 500;

const elements = {
  run: $("runButton"), pause: $("pauseButton"), cancel: $("cancelButton"), csv: $("csvLink"), json: $("jsonLink"), jsonl: $("jsonlLink"), report: $("reportLink"),
  state: $("stateBadge"), message: $("message"), progress: $("progressBar"), body: $("resultsBody"),
  completed: $("completedMetric"), total: $("totalMetric"), interesting: $("interestingMetric"), errors: $("errorMetric"),
  search: $("search"), status: $("statusFilter"), differences: $("differenceOnly"),
  empty: $("emptyState"), table: $("tableWrap"), drawer: $("drawer"), backdrop: $("drawerBackdrop"),
  drawerContent: $("drawerContent"), drawerClose: $("drawerClose"), copy: $("copyButton"),
  stateLabel: document.querySelector("#stateBadge .state-label"), progressText: $("progressText"),
  live: document.querySelector(".live-indicator"), liveLabel: document.querySelector(".live-label"),
  sidebarToggle: $("sidebarToggle"), scope: $("scopeChip"), scopeLabel: $("scopeLabel"),
  breadcrumbTitle: document.querySelector(".breadcrumbs strong"), visibleCount: $("visibleCount"),
  importButton: $("importButton"), saveButton: $("saveButton"), copyCurl: $("copyCurlButton"),
  importDialog: $("importDialog"), importBackdrop: $("importBackdrop"), importMessage: $("importMessage"),
  savedRequests: $("savedRequestsList"), history: $("historyList")
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
    match: $("match").value, exclude: $("exclude").value, extract: $("extract").value,
    session: $("session").value, proxy: $("proxy").value.trim(), auth_type: $("authType").value,
    auth_username: $("authUsername").value, auth_password: $("authPassword").value,
    bearer_token: $("bearerToken").value
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
  elements.stateLabel.textContent = text;
  elements.state.dataset.kind = kind;
  elements.live.classList.toggle("running", kind === "running");
  elements.liveLabel.textContent = kind === "running" ? "Running" : kind === "paused" ? "Paused" : kind === "error" ? "Error" : text === "Completed" ? "Complete" : "Idle";
}

function closeDrawer() {
  if (!elements.drawer.classList.contains("open")) return;
  elements.drawer.classList.remove("open");
  elements.drawer.setAttribute("aria-hidden", "true");
  elements.drawer.setAttribute("inert", "");
  elements.backdrop.hidden = true;
  if (previousFocus) previousFocus.focus();
}

function resetRun() {
  results = []; total = 0; activeJob = null; paused = false; terminalEventSeen = false; lastSequence = 0;
  elements.body.replaceChildren(); elements.progress.style.width = "0%";
  elements.progress.parentElement.setAttribute("aria-valuenow", "0");
  elements.progressText.textContent = "0%";
  elements.completed.textContent = "0"; elements.total.textContent = "0";
  elements.interesting.textContent = "0"; elements.errors.textContent = "0"; elements.message.textContent = "";
  elements.pause.disabled = true; elements.cancel.disabled = true; elements.pause.textContent = "Pause";
  [elements.csv, elements.json, elements.jsonl, elements.report].forEach((link) => { link.classList.add("disabled"); link.setAttribute("aria-disabled", "true"); link.removeAttribute("href"); });
  historyMode = false;
  elements.empty.hidden = false; elements.table.hidden = true; closeDrawer();
}

function visible(item) {
  const search = elements.search.value.toLowerCase();
  if (search && !JSON.stringify(item).toLowerCase().includes(search)) return false;
  const selected = elements.status.value;
  if (selected === "error" && !item.error) return false;
  if (/^[2-5]$/.test(selected) && !String(item.status || "").startsWith(selected)) return false;
  const baselineEquivalent = (item.cluster === null || item.cluster === undefined || item.cluster === "C1") && (item.similarity === null || item.similarity === undefined || Number(item.similarity) >= 99.99);
  return !(elements.differences.checked && baselineEquivalent && !item.error);
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
  const filtered = results.filter(visible).sort((left, right) => {
    const leftValue = left[sortKey] ?? ""; const rightValue = right[sortKey] ?? "";
    return (typeof leftValue === "number" && typeof rightValue === "number" ? leftValue - rightValue : String(leftValue).localeCompare(String(rightValue), undefined, {numeric: true})) * sortDirection;
  });
  const displayed = filtered.slice(0, MAX_RENDERED_ROWS);
  elements.visibleCount.textContent = filtered.length > MAX_RENDERED_ROWS ? `Showing ${MAX_RENDERED_ROWS} of ${filtered.length}. Refine the filters to see more.` : `${filtered.length} visible.`;
  for (const item of displayed) {
    const row = document.createElement("tr");
    row.tabIndex = 0; row.setAttribute("aria-label", `Open response ${item.index}`);
    const different = item.cluster && item.cluster !== "C1" || item.similarity !== null && item.similarity !== undefined && Number(item.similarity) < 99.99;
    if (different) row.classList.add("different");
    if (item.error) row.classList.add("error");
    const extracted = Object.entries(item.custom || {}).map(([key, value]) => `${key}=${value}`).join(" · ");
    const values = [item.index, item.name, item.method ?? "—", item.status ?? "—", item.size_bytes, displayMetric(item.elapsed_ms, " ms"), displayMetric(item.similarity, "%"), displayMetric(item.cluster), displayMetric(item.anomaly_score), item.location ?? "", extracted];
    const labels = ["#", "Request", "Method", "Status", "Bytes", "Latency", "Similarity", "Cluster", "Anomaly", "Location", "Extracted"];
    values.forEach((value, index) => {
      const cell = document.createElement("td"); cell.textContent = String(value ?? "");
      cell.dataset.label = labels[index];
      if (index === 3) cell.className = `status-cell ${statusClass(item.status)}`;
      if (index === 1 && (item.matched || item.excluded)) {
        const badge = document.createElement("span"); badge.className = `result-badge ${item.excluded ? "excluded" : "matched"}`; badge.textContent = item.excluded ? "Excluded" : "Matched"; cell.append(" ", badge);
      }
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
  const roundedPercent = Math.round(percent);
  elements.progressText.textContent = `${roundedPercent}%`;
  elements.progress.parentElement.setAttribute("aria-valuenow", String(roundedPercent));
}

function openDrawer(item) {
  previousFocus = document.activeElement;
  activeDrawerItem = item;
  activateDrawerTab("summary");
  elements.drawer.classList.add("open"); elements.drawer.setAttribute("aria-hidden", "false");
  elements.drawer.removeAttribute("inert");
  elements.backdrop.hidden = false; elements.drawerClose.focus();
}

function drawerData(section) {
  if (!activeDrawerItem) return {};
  const item = activeDrawerItem;
  if (section === "request") return {method: item.method, url: item.url, final_request_url: item.final_request_url, request_headers: item.request_headers, configured_request_headers: item.configured_request_headers, removed_request_headers: item.removed_request_headers, request_content_type: item.request_content_type, request_size_bytes: item.request_size_bytes, request_body_summary: item.request_body_summary, payload_variables: item.payload_variables};
  if (section === "response") return {status: item.status, outcome: item.outcome, response_received: item.response_received, response_headers: item.response_headers, content_type: item.content_type, http_version: item.http_version, location: item.location, size_bytes: item.size_bytes, elapsed_ms: item.elapsed_ms, body_truncated: item.body_truncated, body_preview: item.body_preview, error: item.error, error_type: item.error_type};
  if (section === "analysis") return {body_hash: item.body_hash, similarity: item.similarity, similarity_basis: item.similarity_basis, cluster: item.cluster, anomaly_score: item.anomaly_score, delta_bytes: item.delta_bytes, matched: item.matched, excluded: item.excluded, custom: item.custom};
  if (section === "raw") return item;
  return {name: item.name, method: item.method, status: item.status, size_bytes: item.size_bytes, elapsed_ms: item.elapsed_ms, similarity: item.similarity, cluster: item.cluster, anomaly_score: item.anomaly_score, outcome: item.outcome};
}

function activateDrawerTab(section) {
  document.querySelectorAll(".drawer-tab").forEach((button) => button.classList.toggle("active", button.dataset.drawerTab === section));
  elements.drawerContent.textContent = JSON.stringify(drawerData(section), null, 2);
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
  if (activeJob && !historyMode) {
    [[elements.csv, "csv"], [elements.json, "json"], [elements.jsonl, "jsonl"], [elements.report, "report"]].forEach(([link, format]) => { link.href = `/api/jobs/${activeJob}/${format}`; link.classList.remove("disabled"); link.setAttribute("aria-disabled", "false"); });
    if (terminalEventSeen) sessionStorage.removeItem("imr-intruder-active-job");
  }
}

async function run() {
  if (elements.run.disabled) return;
  setState("Validating"); elements.run.disabled = true;
  try {
    const requestPayload = validatePayload(buildPayload());
    resetRun(); elements.run.disabled = true; setState("Starting");
    const data = await (await api("/api/jobs", {method: "POST", body: JSON.stringify(requestPayload)})).json();
    activeJob = data.job_id; sessionStorage.setItem("imr-intruder-active-job", activeJob); total = Number(data.total || 0); updateMetrics();
    elements.pause.disabled = false; elements.cancel.disabled = false; setState("Running", "running");
    await stream(activeJob);
  } catch (error) { elements.message.textContent = error.message; setState("Error", "error"); }
  finally { finishRun(); loadHistory(); }
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

function multimapText(value, separator = "=") {
  if (!value || typeof value !== "object") return "";
  const lines = [];
  Object.entries(value).forEach(([key, raw]) => {
    (Array.isArray(raw) ? raw : [raw]).forEach((item) => lines.push(`${key}${separator}${item ?? ""}`));
  });
  return lines.join("\n");
}

function setMethod(value) {
  const method = String(value || "GET").toUpperCase();
  if (![...$("method").options].some((option) => option.value === method)) {
    const option = document.createElement("option"); option.value = method; option.textContent = method; $("method").appendChild(option);
  }
  $("method").value = method;
}

function applyRequest(data) {
  if (!data || typeof data !== "object") return;
  $("requestName").value = data.name || ""; setMethod(data.method); $("url").value = data.url || "";
  $("headers").value = multimapText(data.headers, ": "); $("params").value = multimapText(data.params); $("cookies").value = multimapText(data.cookies);
  $("proxy").value = data.proxy || ""; $("session").value = data.session || "";
  $("verifyTls").checked = data.verify_tls !== false; $("followRedirects").checked = Boolean(data.follow_redirects); $("http2").checked = Boolean(data.http2); $("backoff").checked = Boolean(data.backoff);
  if (data.body_type !== undefined) { $("bodyType").value = data.body_type; $("body").value = data.body || ""; }
  else if (data.json !== undefined) { $("bodyType").value = "json"; $("body").value = JSON.stringify(data.json, null, 2); }
  else if (data.data !== undefined) { $("bodyType").value = "form"; $("body").value = multimapText(data.data); }
  else if (data.multipart !== undefined) { $("bodyType").value = "multipart"; $("body").value = multimapText(data.multipart); }
  else if (data.body !== undefined) { $("bodyType").value = "raw"; $("body").value = String(data.body); }
  else { $("bodyType").value = data.body_type || "none"; $("body").value = data.body || ""; }
  if (data.auth) { $("authType").value = "basic"; $("authUsername").value = data.auth.username || ""; $("authPassword").value = data.auth.password || ""; }
  else { $("authType").value = data.auth_type || "none"; $("authUsername").value = data.auth_username || ""; $("authPassword").value = data.auth_password || ""; $("bearerToken").value = data.bearer_token || ""; }
  const mappings = {workers: "workers", delay_ms: "delayMs", rate: "rate", timeout: "timeout", retries: "retries", body_limit: "bodyLimit", cluster_threshold: "clusterThreshold", max_requests: "maxRequests", mode: "mode", payloads: "payloads", columns: "columns", match: "match", exclude: "exclude", extract: "extract"};
  Object.entries(mappings).forEach(([key, id]) => { if (data[key] !== undefined && data[key] !== null) $(id).value = key === "body_limit" ? Number(data[key]) / 1024 : data[key]; });
  updateAuthFields(); syncRequestMeta(); activateTab($("tab-headers")); window.scrollTo({top: 0, behavior: "smooth"});
}

function updateAuthFields() {
  const type = $("authType").value;
  $("basicAuthFields").hidden = type !== "basic"; $("bearerAuthField").hidden = type !== "bearer";
}

function openImport() {
  previousFocus = document.activeElement; elements.importDialog.classList.add("open"); elements.importDialog.setAttribute("aria-hidden", "false"); elements.importDialog.removeAttribute("inert"); elements.importBackdrop.hidden = false; elements.importMessage.textContent = ""; $("importContent").focus();
}

function closeImport() {
  if (!elements.importDialog.classList.contains("open")) return;
  elements.importDialog.classList.remove("open"); elements.importDialog.setAttribute("aria-hidden", "true"); elements.importDialog.setAttribute("inert", ""); elements.importBackdrop.hidden = true; if (previousFocus) previousFocus.focus();
}

async function importIntoBuilder() {
  elements.importMessage.textContent = ""; $("importApply").disabled = true;
  try {
    const response = await api("/api/import", {method: "POST", body: JSON.stringify({kind: $("importKind").value, content: $("importContent").value})});
    const imported = await response.json(); if (!imported.requests?.length) throw new Error("The import did not contain requests.");
    applyRequest(imported.requests[0]); closeImport(); elements.message.textContent = imported.requests.length > 1 ? `Imported the first of ${imported.requests.length} requests.` : "Request imported successfully.";
  } catch (error) { elements.importMessage.textContent = error.message; }
  finally { $("importApply").disabled = false; }
}

function safeSavedName() {
  return ($("requestName").value.trim() || "untitled-request").replace(/[^A-Za-z0-9_.-]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 80) || "untitled-request";
}

async function saveRequest() {
  try {
    const name = safeSavedName(); await api(`/api/requests/${encodeURIComponent(name)}`, {method: "PUT", body: JSON.stringify(buildPayload())});
    elements.message.textContent = `Saved request: ${name}`; await loadLibrary();
  } catch (error) { elements.message.textContent = error.message; }
}

function collectionButton(title, detail, status) {
  const button = document.createElement("button"); button.type = "button"; button.className = "collection-item";
  const copy = document.createElement("span"); const strong = document.createElement("strong"); strong.textContent = title; const small = document.createElement("small"); small.textContent = detail; copy.append(strong, small); button.append(copy);
  if (status) { const badge = document.createElement("em"); badge.textContent = status; button.append(badge); }
  return button;
}

async function loadLibrary() {
  try {
    const names = await (await api("/api/requests")).json(); elements.savedRequests.replaceChildren();
    if (!names.length) { const empty = document.createElement("p"); empty.className = "collection-empty"; empty.textContent = "No saved requests yet."; elements.savedRequests.append(empty); return; }
    names.forEach((name) => {
      const row = document.createElement("div"); row.className = "collection-row"; const open = collectionButton(name, "Open in request builder", "Saved");
      open.addEventListener("click", async () => { try { applyRequest(await (await api(`/api/requests/${encodeURIComponent(name)}`)).json()); } catch (error) { elements.message.textContent = error.message; } });
      const remove = document.createElement("button"); remove.type = "button"; remove.className = "icon-button danger"; remove.setAttribute("aria-label", `Delete ${name}`); remove.textContent = "×";
      remove.disabled = currentRole === "viewer"; remove.addEventListener("click", async () => { try { await api(`/api/requests/${encodeURIComponent(name)}`, {method: "DELETE"}); await loadLibrary(); } catch (error) { elements.message.textContent = error.message; } });
      row.append(open, remove); elements.savedRequests.append(row);
    });
  } catch (error) { elements.savedRequests.textContent = error.message; }
}

function enableHistoryDownloads(record) {
  [[elements.csv, "csv"], [elements.json, "json"], [elements.jsonl, "jsonl"], [elements.report, "report"]].forEach(([link, format]) => { link.href = `/api/history/${record.job_id}/${format}`; link.removeAttribute("download"); link.classList.remove("disabled"); link.setAttribute("aria-disabled", "false"); });
}

async function openHistory(jobId) {
  try {
    const record = await (await api(`/api/history/${encodeURIComponent(jobId)}`)).json(); resetRun(); historyMode = true; activeJob = record.job_id; results = record.results || []; total = Number(record.total || results.length); terminalEventSeen = true; updateMetrics(); renderRows(); setState(record.status === "done" ? "Completed" : record.status, record.status); enableHistoryDownloads(record); document.querySelector("#resultsWorkspace").scrollIntoView({behavior: "smooth"});
  } catch (error) { elements.message.textContent = error.message; }
}

async function loadHistory() {
  try {
    const rows = await (await api("/api/history")).json(); elements.history.replaceChildren();
    if (!rows.length) { const empty = document.createElement("p"); empty.className = "collection-empty"; empty.textContent = "No completed runs yet."; elements.history.append(empty); return; }
    rows.forEach((item) => { const target = (() => { try { return new URL(item.target).host; } catch (_) { return item.target || "Unknown target"; } })(); const row = document.createElement("div"); row.className = "collection-row"; const button = collectionButton(item.name || "Untitled request", `${target} · ${item.completed}/${item.total} responses`, item.status); button.addEventListener("click", () => openHistory(item.job_id)); const remove = document.createElement("button"); remove.type = "button"; remove.className = "icon-button danger"; remove.setAttribute("aria-label", `Delete history ${item.name || item.job_id}`); remove.textContent = "×"; remove.disabled = currentRole === "viewer"; remove.addEventListener("click", async () => { try { await api(`/api/history/${item.job_id}`, {method: "DELETE"}); await loadHistory(); } catch (error) { elements.message.textContent = error.message; } }); row.append(button, remove); elements.history.append(row); });
  } catch (error) { elements.history.textContent = error.message; }
}

async function loadSessions() {
  try {
    const names = await (await api("/api/sessions")).json(); const select = $("session"); select.replaceChildren(new Option("No session", "")); names.forEach((name) => select.add(new Option(name, name)));
  } catch (_) {}
}

async function loadIdentity() {
  try { const identity = await (await api("/api/me")).json(); currentRole = identity.role; $("sessionIdentity").textContent = `${identity.name} · ${identity.role}`; if (identity.role === "viewer") { [elements.run, elements.importButton, elements.saveButton, $("workspaceSelect"), $("newWorkspaceName"), $("createWorkspaceButton")].forEach((control) => { control.disabled = true; control.title = "Viewer access is read-only"; }); } }
  catch (_) { $("sessionIdentity").textContent = "Unauthorized"; }
}

async function loadWorkspaces() {
  try {
    const data = await (await api("/api/workspaces")).json(); const select = $("workspaceSelect"); select.replaceChildren(new Option("Global workspace", "")); data.items.forEach((name) => select.add(new Option(name, name))); select.value = data.current || ""; $("workspaceName").textContent = data.current || "Global";
  } catch (_) {}
}

async function selectWorkspace(name, create = false) {
  try { await api("/api/workspaces", {method: "POST", body: JSON.stringify({name, create})}); await loadWorkspaces(); await Promise.allSettled([loadLibrary(), loadHistory()]); elements.message.textContent = name ? `Workspace active: ${name}` : "Global workspace active."; }
  catch (error) { elements.message.textContent = error.message; await loadWorkspaces(); }
}

async function createWorkspaceFromInput() {
  const name = $("newWorkspaceName").value.trim(); if (!name) return; await selectWorkspace(name, true); $("newWorkspaceName").value = "";
}

function shellQuote(value) { return `'${String(value).replaceAll("'", `'\\''`)}'`; }
async function copyAsCurl() {
  try {
    const data = buildPayload(); let target = data.url;
    try { const parsed = new URL(target); new URLSearchParams(data.params.replace(/\r?\n/g, "&")).forEach((value, key) => parsed.searchParams.append(key, value)); target = parsed.toString(); } catch (_) {}
    const command = ["curl", "-X", data.method, shellQuote(target)];
    data.headers.split(/\r?\n/).filter(Boolean).forEach((line) => command.push("-H", shellQuote(line)));
    if (data.cookies.trim()) command.push("-b", shellQuote(data.cookies.split(/\r?\n/).join("; ")));
    if (data.auth_type === "basic") command.push("-u", shellQuote(`${data.auth_username}:${data.auth_password}`));
    if (data.auth_type === "bearer") command.push("-H", shellQuote(`Authorization: Bearer ${data.bearer_token}`));
    if (data.proxy) command.push("-x", shellQuote(data.proxy)); if (!data.verify_tls) command.push("-k"); if (data.follow_redirects) command.push("-L"); if (data.http2) command.push("--http2");
    if (data.body_type === "json") command.push("--json", shellQuote(data.body)); else if (data.body_type === "form" || data.body_type === "raw") command.push("--data-raw", shellQuote(data.body));
    await navigator.clipboard.writeText(command.join(" ")); elements.message.textContent = "cURL command copied.";
  } catch (error) { elements.message.textContent = `Unable to copy cURL: ${error.message}`; }
}

async function reconnectActiveJob() {
  const jobId = sessionStorage.getItem("imr-intruder-active-job"); if (!jobId) return;
  try {
    const status = await (await api(`/api/jobs/${jobId}`)).json(); resetRun(); activeJob = jobId; total = Number(status.total || 0);
    if (Array.isArray(status.results) && status.results.length) applySnapshot(status);
    if (["done", "cancelled", "error"].includes(status.status)) { terminalEventSeen = true; setState(status.status === "done" ? "Completed" : status.status, status.status); finishRun(); return; }
    elements.run.disabled = true; elements.pause.disabled = false; elements.cancel.disabled = false; setState(status.status === "paused" ? "Paused" : "Running", status.status === "paused" ? "paused" : "running"); await stream(jobId); finishRun();
  } catch (_) { sessionStorage.removeItem("imr-intruder-active-job"); }
}

function activateTab(button) {
  document.querySelectorAll(".tab").forEach((item) => {
    const selected = item === button; item.classList.toggle("active", selected); item.setAttribute("aria-selected", String(selected)); item.tabIndex = selected ? 0 : -1;
  });
  document.querySelectorAll(".tab-content").forEach((panel) => { const selected = panel.dataset.panel === button.dataset.tab; panel.classList.toggle("active", selected); panel.hidden = !selected; });
}

function syncRequestMeta() {
  elements.breadcrumbTitle.textContent = $("requestName").value.trim() || "Untitled request";
  let ready = false;
  try {
    const target = new URL($("url").value.trim());
    ready = ["http:", "https:"].includes(target.protocol) && Boolean(target.hostname);
  } catch (_) {}
  elements.scope.classList.toggle("ready", ready);
  elements.scopeLabel.textContent = ready ? "Target ready" : "Awaiting target";
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
$("requestName").addEventListener("input", syncRequestMeta);
$("url").addEventListener("input", syncRequestMeta);
elements.search.addEventListener("input", renderRows);
elements.status.addEventListener("change", renderRows);
elements.differences.addEventListener("change", renderRows);
elements.drawerClose.addEventListener("click", closeDrawer);
elements.backdrop.addEventListener("click", closeDrawer);
elements.copy.addEventListener("click", async () => { try { await navigator.clipboard.writeText(JSON.stringify(activeDrawerItem, null, 2)); elements.copy.textContent = "Copied"; setTimeout(() => { elements.copy.textContent = "Copy JSON"; }, 1200); } catch (error) { elements.message.textContent = `Unable to copy: ${error.message}`; } });
document.querySelectorAll(".drawer-tab").forEach((button) => button.addEventListener("click", () => activateDrawerTab(button.dataset.drawerTab)));
elements.importButton.addEventListener("click", openImport);
$("importClose").addEventListener("click", closeImport); $("importCancel").addEventListener("click", closeImport); elements.importBackdrop.addEventListener("click", closeImport); $("importApply").addEventListener("click", importIntoBuilder);
elements.saveButton.addEventListener("click", saveRequest); elements.copyCurl.addEventListener("click", copyAsCurl);
$("refreshLibraryButton").addEventListener("click", loadLibrary); $("refreshHistoryButton").addEventListener("click", loadHistory); $("authType").addEventListener("change", updateAuthFields);
$("workspaceSelect").addEventListener("change", () => selectWorkspace($("workspaceSelect").value)); $("createWorkspaceButton").addEventListener("click", createWorkspaceFromInput); $("newWorkspaceName").addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); createWorkspaceFromInput(); } });

const resultKeys = ["index", "name", "method", "status", "size_bytes", "elapsed_ms", "similarity", "cluster", "anomaly_score", "location", "custom"];
document.querySelectorAll("#tableWrap th").forEach((header, index) => { header.tabIndex = 0; header.setAttribute("aria-sort", "none"); const sort = () => { const nextKey = resultKeys[index]; sortDirection = sortKey === nextKey ? -sortDirection : 1; sortKey = nextKey; document.querySelectorAll("#tableWrap th").forEach((item) => item.setAttribute("aria-sort", "none")); header.setAttribute("aria-sort", sortDirection > 0 ? "ascending" : "descending"); renderRows(); }; header.addEventListener("click", sort); header.addEventListener("keydown", (event) => { if (["Enter", " "].includes(event.key)) { event.preventDefault(); sort(); } }); });

document.addEventListener("keydown", (event) => {
  if (event.key === "Tab") {
    const container = elements.importDialog.classList.contains("open") ? elements.importDialog : elements.drawer.classList.contains("open") ? elements.drawer : null;
    if (container) { const focusable = [...container.querySelectorAll('button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href], [tabindex="0"]')].filter((item) => !item.hidden); if (focusable.length) { const first = focusable[0]; const last = focusable[focusable.length - 1]; if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); } else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); } } }
  }
  if (event.key === "Escape") { closeDrawer(); closeImport(); document.documentElement.classList.remove("nav-open"); elements.sidebarToggle.setAttribute("aria-expanded", "false"); }
  if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) { event.preventDefault(); run(); }
  if (event.key === "/" && !["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName)) { event.preventDefault(); $("url").focus(); }
});

elements.sidebarToggle.addEventListener("click", () => {
  const open = document.documentElement.classList.toggle("nav-open");
  elements.sidebarToggle.setAttribute("aria-expanded", String(open));
});

document.querySelectorAll(".nav-item").forEach((item) => {
  item.addEventListener("click", () => {
    document.querySelectorAll(".nav-item").forEach((link) => link.classList.toggle("active", link === item));
    document.documentElement.classList.remove("nav-open");
    elements.sidebarToggle.setAttribute("aria-expanded", "false");
  });
});

document.addEventListener("click", (event) => {
  if (!document.documentElement.classList.contains("nav-open")) return;
  if ($("sidebar").contains(event.target) || elements.sidebarToggle.contains(event.target)) return;
  document.documentElement.classList.remove("nav-open");
  elements.sidebarToggle.setAttribute("aria-expanded", "false");
});

const savedTheme = localStorage.getItem("imr-intruder-theme");
if (savedTheme === "light") document.documentElement.classList.add("light");
function updateThemeButton() {
  const light = document.documentElement.classList.contains("light");
  $("themeLabel").textContent = light ? "Dark" : "Light";
  $("themeButton").setAttribute("aria-label", light ? "Switch to dark theme" : "Switch to light theme");
}
updateThemeButton();
syncRequestMeta();
$("themeButton").addEventListener("click", () => {
  document.documentElement.classList.toggle("light");
  localStorage.setItem("imr-intruder-theme", document.documentElement.classList.contains("light") ? "light" : "dark"); updateThemeButton();
});

updateAuthFields();
loadIdentity().then(() => Promise.allSettled([loadWorkspaces(), loadSessions(), loadLibrary(), loadHistory()])).then(() => reconnectActiveJob());
