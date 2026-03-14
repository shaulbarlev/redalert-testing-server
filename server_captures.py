"""
Capture-based Pikud Haoref alerts server.
Serves only from pre-captured JSON files; no synthetic state.
"""

import argparse
import json
import logging
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request, render_template_string
from flask_cors import CORS

# Category 10 title strings (redalert.cpp stateFromAlert) — string search for type
TITLE_END = "האירוע הסתיים"
TITLE_PRE_ALERT = "בדקות הקרובות צפויות להתקבל התרעות באזורך"


def get_alert_type(payload: dict[str, Any]) -> str:
    """
    Derive display type from payload: cat 10 + title search → End (safe) or Pre alert;
    any other cat → Alert.
    """
    cat = str(payload.get("cat", "")).strip()
    title = (payload.get("title") or "").strip()
    if cat == "10":
        if TITLE_END in title:
            return "End (safe)"
        if TITLE_PRE_ALERT in title:
            return "Pre alert"
        # cat 10 but unknown title → treat as end
        return "End (safe)"
    return "Alert"


def get_capture_list(
    captures_dir: Path,
    city_filter: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Scan captures_dir for *-alerts.json files. Return list of
    {filename, time, size, num_cities, type}, sorted by time descending.
    If city_filter is set, only include captures whose payload.data contains
    at least one city that has any of the filter strings as a substring.
    """
    if not captures_dir.is_dir():
        return []
    entries: list[dict[str, Any]] = []
    for path in captures_dir.glob("*-alerts.json"):
        try:
            raw = path.read_text(encoding="utf-8")
            size = path.stat().st_size
            data = json.loads(raw)
            meta = data.get("meta") or {}
            payload = data.get("payload")
            if not isinstance(payload, dict):
                logging.warning("Skipping %s: payload is not a dict", path.name)
                continue
            data_list = payload.get("data")
            if not isinstance(data_list, list):
                data_list = []
            if city_filter:
                city_strings = [str(c) for c in data_list]
                terms = [q.strip() for q in city_filter if q.strip()]
                if terms and not any(
                    term in city
                    for city in city_strings
                    for term in terms
                ):
                    continue
            time_str = meta.get("timestamp") or path.stem.replace("-alerts", "")
            num_cities = len(data_list)
            alert_type = get_alert_type(payload)
            entries.append({
                "filename": path.name,
                "time": time_str,
                "size": size,
                "num_cities": num_cities,
                "type": alert_type,
            })
        except (json.JSONDecodeError, OSError) as exc:
            logging.warning("Skipping %s: %s", path.name, exc)
    entries.sort(key=lambda e: e["time"], reverse=True)
    return entries


def create_app(captures_dir: str | Path) -> Flask:
    captures_path = Path(captures_dir)
    app = Flask(__name__)
    CORS(app)

    app.config["CAPTURES_DIR"] = captures_path
    app.config["SELECTED_FILENAME"] = None  # type: ignore[assignment]

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    logger = logging.getLogger("redalert-captures")

    def log_request(path: str) -> None:
        logger.info("Request: path=%s", path)

    @app.route("/WarningMessages/alert/alerts.json", methods=["GET"])
    def alerts() -> tuple[Any, int]:
        log_request(request.path)
        selected = app.config.get("SELECTED_FILENAME")
        if not selected:
            return jsonify([]), 200
        path = captures_path / selected
        if not path.is_file():
            app.config["SELECTED_FILENAME"] = None
            return jsonify([]), 200
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            payload = data.get("payload")
            if isinstance(payload, dict):
                return jsonify(payload), 200
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read selected capture %s: %s", selected, exc)
            app.config["SELECTED_FILENAME"] = None
        return jsonify([]), 200

    @app.route("/captures", methods=["GET"])
    def list_captures() -> Any:
        log_request(request.path)
        city_param = request.args.get("city", "").strip()
        city_filter = [s.strip() for s in city_param.split(",") if s.strip()]
        entries = get_capture_list(captures_path, city_filter=city_filter or None)
        selected = app.config.get("SELECTED_FILENAME")
        return jsonify({"captures": entries, "selected": selected})

    @app.route("/select_capture", methods=["POST"])
    def select_capture() -> Any:
        log_request(request.path)
        body = request.get_json(silent=True) or {}
        filename = body.get("filename")
        if filename is None:
            app.config["SELECTED_FILENAME"] = None
            logger.info("Selection cleared")
            return jsonify({"selected": None})
        if not isinstance(filename, str) or not filename.strip():
            return jsonify({"error": "filename must be a non-empty string or null"}), 400
        filename = filename.strip()
        path = captures_path / filename
        if not path.is_file():
            return jsonify({"error": "file not found", "filename": filename}), 404
        # Optionally validate it's in the list (same dir, *-alerts.json)
        if not filename.endswith("-alerts.json"):
            return jsonify({"error": "invalid filename"}), 400
        app.config["SELECTED_FILENAME"] = filename
        logger.info("Selected capture: %s", filename)
        return jsonify({"selected": filename})

    CONTROL_HTML = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Fake Pikud Haoref – Capture mode</title>
    <style>
      body { font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; padding: 2rem; background: #0b1020; color: #f7fafc; }
      h1 { margin-bottom: 1rem; }
      .endpoint { font-family: monospace; background: #1a202c; padding: 0.5rem; border-radius: 4px; margin-top: 0.5rem; }
      table { border-collapse: collapse; margin-top: 1rem; width: 100%; max-width: 720px; }
      th, td { text-align: left; padding: 0.5rem 0.75rem; border: 1px solid #4a5568; }
      th { background: #1a202c; }
      tr:hover { background: #1a202c; }
      tr.selected { background: #2c5282; }
      tr.clickable { cursor: pointer; }
      .serving { margin: 1rem 0; font-weight: 600; }
      .log { margin-top: 1rem; font-size: 0.85rem; color: #a0aec0; }
    </style>
  </head>
  <body>
    <h1>Fake Pikud Haoref – Capture mode</h1>
    <div class="serving">Serving: <span id="serving-label">None</span></div>
    <p>Select a capture to serve, or "None" to return empty array.</p>
    <div style="margin-bottom: 1rem;">
      <label for="city-search">Filter by city (substring):</label>
      <input id="city-search" type="text" placeholder="e.g. תל אביב or ירושלים" style="margin-left: 0.5rem; min-width: 200px; padding: 0.35rem 0.5rem; border-radius: 4px; border: 1px solid #4a5568; background: #1a202c; color: #e2e8f0;" />
      <span id="search-hint" style="margin-left: 0.5rem; color: #718096; font-size: 0.9rem;"></span>
    </div>
    <table id="captures-table">
      <thead>
        <tr>
          <th></th>
          <th>Time</th>
          <th>Size</th>
          <th>Num cities</th>
          <th>Type</th>
        </tr>
      </thead>
      <tbody id="captures-body"></tbody>
    </table>
    <div style="margin-top: 1.5rem;">
      <div>Alerts endpoint:</div>
      <div class="endpoint">GET /WarningMessages/alert/alerts.json</div>
    </div>
    <div class="log" id="log"></div>
    <script>
      const logEl = document.getElementById('log');
      const bodyEl = document.getElementById('captures-body');
      const servingEl = document.getElementById('serving-label');

      function esc(s) {
        if (s == null) return '';
        return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
      }
      function setServing(name) {
        servingEl.textContent = name == null ? 'None' : name;
      }

      let searchDebounce = null;
      function getCityParam() {
        const raw = document.getElementById('city-search').value.trim();
        return raw ? raw : '';
      }
      async function loadCaptures() {
        const city = getCityParam();
        const url = city ? '/captures?city=' + encodeURIComponent(city) : '/captures';
        const hintEl = document.getElementById('search-hint');
        if (city) hintEl.textContent = 'Filtering by: \"' + city + '\"';
        else hintEl.textContent = '';
        try {
          const res = await fetch(url);
          const data = await res.json();
          if (!res.ok) {
            logEl.textContent = 'Error: ' + JSON.stringify(data);
            return;
          }
          const { captures, selected } = data;
          setServing(selected);

          bodyEl.innerHTML = '';
          const noneRow = document.createElement('tr');
          noneRow.className = 'clickable' + (selected == null ? ' selected' : '');
          noneRow.dataset.filename = '';
          noneRow.innerHTML = '<td><input type="radio" name="capture" value=""> None</td><td colspan="4">—</td>';
          noneRow.onclick = () => selectCapture(null);
          bodyEl.appendChild(noneRow);

          captures.forEach(c => {
            const tr = document.createElement('tr');
            tr.className = 'clickable' + (selected === c.filename ? ' selected' : '');
            tr.dataset.filename = c.filename;
            tr.innerHTML = '<td><input type="radio" name="capture" value="' + esc(c.filename) + '"> </td><td>' + esc(c.time) + '</td><td>' + esc(c.size) + '</td><td>' + esc(c.num_cities) + '</td><td>' + esc(c.type) + '</td>';
            tr.onclick = () => selectCapture(c.filename);
            bodyEl.appendChild(tr);
          });
        } catch (err) {
          logEl.textContent = 'Request failed: ' + err;
        }
      }
      function onCitySearchInput() {
        if (searchDebounce) clearTimeout(searchDebounce);
        searchDebounce = setTimeout(loadCaptures, 300);
      }

      async function selectCapture(filename) {
        logEl.textContent = '';
        try {
          const res = await fetch('/select_capture', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filename: filename || null })
          });
          const data = await res.json();
          if (!res.ok) {
            logEl.textContent = 'Error: ' + JSON.stringify(data);
            return;
          }
          setServing(data.selected);
          document.querySelectorAll('#captures-body tr').forEach(tr => {
            tr.classList.toggle('selected', tr.dataset.filename === (filename || ''));
          });
          document.querySelectorAll('input[name=capture]').forEach(inp => {
            inp.checked = (inp.value === (filename || ''));
          });
        } catch (err) {
          logEl.textContent = 'Request failed: ' + err;
        }
      }

      document.getElementById('city-search').addEventListener('input', onCitySearchInput);
      document.getElementById('city-search').addEventListener('keydown', function(e) {
        if (e.key === 'Enter') {
          if (searchDebounce) clearTimeout(searchDebounce);
          loadCaptures();
        }
      });
      loadCaptures();
    </script>
  </body>
</html>
"""

    @app.route("/", methods=["GET"])
    def control_page() -> Any:
        log_request(request.path)
        return render_template_string(CONTROL_HTML)

    return app


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Serve Pikud Haoref alerts from captured JSON files only"
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=2501,
        help="Port to listen on (default: 2501, to avoid clashing with synthetic server)",
    )
    parser.add_argument(
        "--captures-dir",
        type=Path,
        default=Path("captures"),
        help="Directory containing *-alerts.json capture files (default: ./captures)",
    )
    parser.add_argument(
        "--cert",
        help="Path to SSL certificate file (PEM) for HTTPS",
    )
    parser.add_argument(
        "--key",
        help="Path to SSL private key file (PEM) for HTTPS",
    )
    args = parser.parse_args()
    if not args.captures_dir.is_dir():
        parser.error(f"Captures dir is not a directory: {args.captures_dir}")
    app = create_app(args.captures_dir)
    ssl_context = None
    if args.cert and args.key:
        ssl_context = (args.cert, args.key)
    app.run(host=args.host, port=args.port, ssl_context=ssl_context)


if __name__ == "__main__":
    main()
