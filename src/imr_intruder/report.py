from __future__ import annotations

import html
import json
from collections import Counter
from pathlib import Path
from typing import Any

_SECRET_KEYS = {"authorization", "cookie", "set-cookie", "password", "token", "secret", "api_key", "apikey"}


def _redact(value: Any, key: str = "") -> Any:
    if key.lower() in _SECRET_KEYS:
        return "<REDACTED>"
    if isinstance(value, dict):
        return {item_key: _redact(item_value, str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def load_results(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".jsonl":
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("results"), list):
        return data["results"]
    raise ValueError("Results file must be JSONL, a JSON list, or an object with results.")


def build_html_report(results: list[dict[str, Any]], output: Path, title: str = "imr-intruder report") -> Path:
    safe_results = _redact(results)
    statuses = Counter(str(item.get("status") or "error") for item in safe_results)
    clusters = Counter(str(item.get("cluster") or "-") for item in safe_results)
    def anomaly_value(row: dict[str, Any]) -> float:
        value = row.get("anomaly_score")
        try:
            return float(value) if value is not None else -1.0
        except (TypeError, ValueError):
            return -1.0

    rows = []
    for item in sorted(safe_results, key=anomaly_value, reverse=True):
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(item.get('index', '')))}</td>"
            f"<td>{html.escape(str(item.get('name', '')))}</td>"
            f"<td>{html.escape(str(item.get('status', '')))}</td>"
            f"<td>{html.escape(str(item.get('size_bytes', '')))}</td>"
            f"<td>{html.escape(str(item.get('elapsed_ms', '')))}</td>"
            f"<td>{html.escape(str(item.get('similarity', '')))}</td>"
            f"<td>{html.escape(str(item.get('cluster', '')))}</td>"
            f"<td>{html.escape(str(item.get('anomaly_score', '')))}</td>"
            f"<td><details><summary>Evidence</summary><pre>{html.escape(json.dumps(item, ensure_ascii=False, indent=2))}</pre></details></td>"
            "</tr>"
        )
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><style>
:root{{color-scheme:dark}}body{{font-family:Inter,system-ui,sans-serif;margin:0;background:#0b1220;color:#e5e7eb}}
main{{max-width:1500px;margin:auto;padding:28px}}.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px}}
.card{{background:#111827;border:1px solid #243047;border-radius:12px;padding:16px}}table{{width:100%;border-collapse:collapse;margin-top:20px;background:#111827}}
th,td{{border-bottom:1px solid #263244;padding:10px;text-align:left;vertical-align:top}}th{{position:sticky;top:0;background:#172033}}
pre{{white-space:pre-wrap;max-width:900px;max-height:480px;overflow:auto}}code{{color:#93c5fd}}h1{{margin-top:0}}
</style></head><body><main><h1>{html.escape(title)}</h1>
<div class="cards"><div class="card"><strong>Total</strong><div>{len(safe_results)}</div></div>
<div class="card"><strong>Status</strong><pre>{html.escape(json.dumps(statuses, indent=2))}</pre></div>
<div class="card"><strong>Clusters</strong><pre>{html.escape(json.dumps(clusters, indent=2))}</pre></div></div>
<table><thead><tr><th>#</th><th>Name</th><th>Status</th><th>Bytes</th><th>ms</th><th>Similarity</th><th>Cluster</th><th>Anomaly</th><th>Details</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></main></body></html>"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8")
    return output
