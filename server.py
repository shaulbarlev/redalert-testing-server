import argparse
import logging
from datetime import datetime
from typing import Literal

from flask import Flask, jsonify, request, render_template_string
from flask_cors import CORS

State = Literal["ok", "alert", "pre_alert", "end"]


def create_app(initial_state: State = "ok", area_name: str = "תל אביב - מזרח") -> Flask:
    app = Flask(__name__)
    CORS(app)  # Allow all origins for easy testing

    # In-memory state
    app.config["CURRENT_STATE"] = initial_state
    app.config["AREA_NAME"] = area_name

    # Basic logging configuration
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    logger = logging.getLogger("redalert-testing-server")

    def log_request(path: str) -> None:
        state = app.config.get("CURRENT_STATE", "ok")
        logger.info("Request: path=%s state=%s", path, state)

    @app.route("/WarningMessages/alert/alerts.json", methods=["GET"])
    def alerts():
        log_request(request.path)

        state: State = app.config.get("CURRENT_STATE", "ok")
        area = request.args.get("areaName", app.config.get("AREA_NAME"))

        if state == "ok":
            # Match real API behaviour when there are no alerts
            return jsonify([])

        # Map state to Pikud Haoref-style "cat" codes:
        # - "14" → pre_alert
        # - "13" → end
        # - anything else (here: "1") → alert
        if state == "pre_alert":
            cat = "14"
        elif state == "end":
            cat = "13"
        else:
            cat = "1"

        alert_obj = {
            "id": datetime.utcnow().strftime("%Y%m%d%H%M%S000000"),  # unique-ish
            "cat": cat,
            "title": "ירי רקטות וטילים",
            "data": [area],
            "desc": "היכנסו מייד למרחב המוגן ",
        }

        # Real endpoint returns a single object (not an array) when there is an alert
        return jsonify(alert_obj)

    @app.route("/set_state", methods=["POST"])
    def set_state():
        log_request(request.path)

        body = request.get_json(silent=True) or {}
        new_state = body.get("state")

        valid_states: set[State] = {"ok", "alert", "pre_alert", "end"}
        if new_state not in valid_states:
            return (
                jsonify(
                    {
                        "error": "Invalid state",
                        "allowed": sorted(valid_states),
                    }
                ),
                400,
            )

        old_state: State = app.config.get("CURRENT_STATE", "ok")
        app.config["CURRENT_STATE"] = new_state  # type: ignore[assignment]
        logger.info("State change: %s -> %s", old_state, new_state)

        return jsonify({"old_state": old_state, "new_state": new_state})

    @app.route("/set_area", methods=["POST"])
    def set_area():
        log_request(request.path)

        body = request.get_json(silent=True) or {}
        raw_area = body.get("area", "")
        if not isinstance(raw_area, str):
            return jsonify({"error": "area must be a string"}), 400

        new_area = raw_area.strip()
        if not new_area:
            return jsonify({"error": "area is required"}), 400

        old_area = app.config.get("AREA_NAME")
        app.config["AREA_NAME"] = new_area
        logger.info("Area change: %s -> %s", old_area, new_area)

        return jsonify({"old_area": old_area, "new_area": new_area})

    CONTROL_HTML = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Fake Pikud Haoref Alerts</title>
    <style>
      body { font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; padding: 2rem; background: #0b1020; color: #f7fafc; }
      h1 { margin-bottom: 1rem; }
      .state { margin-bottom: 1.5rem; }
      button { margin: 0.25rem; padding: 0.6rem 1.2rem; border-radius: 6px; border: none; cursor: pointer; font-size: 0.95rem; font-weight: 600; }
      button.ok { background: #2f855a; color: white; }
      button.alert { background: #e53e3e; color: white; }
      button.pre_alert { background: #d69e2e; color: #1a202c; }
      button.end { background: #3182ce; color: white; }
      button:disabled { opacity: 0.6; cursor: default; }
      .log { margin-top: 1.5rem; font-size: 0.85rem; color: #a0aec0; white-space: pre-wrap; }
      .endpoint { font-family: monospace; background: #1a202c; padding: 0.5rem; border-radius: 4px; margin-top: 0.5rem; }
      a { color: #90cdf4; }
    </style>
  </head>
  <body>
    <h1>Fake Pikud Haoref Alerts</h1>
    <div class="state">
      <div>Current state: <strong id="current-state">loading…</strong></div>
      <div style="margin-top: 0.75rem;">
        <button class="ok" onclick="setState('ok')">OK</button>
        <button class="alert" onclick="setState('alert')">Alert</button>
        <button class="pre_alert" onclick="setState('pre_alert')">Pre-alert</button>
        <button class="end" onclick="setState('end')">End</button>
      </div>
    </div>

    <div>
      <div>Alerts endpoint your WLED should poll:</div>
      <div class="endpoint">GET /WarningMessages/alert/alerts.json</div>
      <div class="endpoint" style="margin-top: 0.4rem;">GET /WarningMessages/alert/alerts.json?areaName={{ area_name|e }}</div>
    </div>

    <div style="margin-top: 1.5rem;">
      <div>Current default area (used when no <code>areaName</code> query param is given):</div>
      <div style="margin-top: 0.5rem;">
        <input id="area-input" type="text" value="{{ area_name|e }}" style="min-width: 260px; padding: 0.35rem 0.5rem; border-radius: 4px; border: 1px solid #4a5568; background: #1a202c; color: #e2e8f0;" />
        <button class="end" style="margin-left: 0.5rem;" onclick="setArea()">Set area</button>
      </div>
    </div>

    <div class="log" id="log"></div>

    <script>
      async function setState(state) {
        const logEl = document.getElementById('log');
        logEl.textContent = '';
        try {
          const res = await fetch('/set_state', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ state })
          });
          const data = await res.json();
          if (!res.ok) {
            logEl.textContent = 'Error: ' + JSON.stringify(data);
          } else {
            document.getElementById('current-state').textContent = data.new_state;
            logEl.textContent = 'State changed: ' + data.old_state + ' → ' + data.new_state;
          }
        } catch (err) {
          logEl.textContent = 'Request failed: ' + err;
        }
      }

      async function setArea() {
        const logEl = document.getElementById('log');
        const input = document.getElementById('area-input');
        logEl.textContent = '';
        const area = input.value.trim();

        if (!area) {
          logEl.textContent = 'Error: area is required';
          return;
        }

        try {
          const res = await fetch('/set_area', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ area })
          });
          const data = await res.json();
          if (!res.ok) {
            logEl.textContent = 'Error: ' + JSON.stringify(data);
          } else {
            logEl.textContent = 'Area changed: ' + data.old_area + ' → ' + data.new_area;
          }
        } catch (err) {
          logEl.textContent = 'Request failed: ' + err;
        }
      }

      // Initialize current state by hitting alerts endpoint once
      async function initState() {
        try {
          const res = await fetch('/WarningMessages/alert/alerts.json');
          const payload = res.ok ? (await res.json()) : [];
          let state = 'ok';
          let alertObj = null;

          if (Array.isArray(payload)) {
            if (payload.length > 0) {
              alertObj = payload[0];
            }
          } else if (payload && typeof payload === 'object') {
            alertObj = payload;
          }

          if (alertObj && alertObj.cat !== undefined) {
            const cat = String(alertObj.cat);
            if (cat === '14') state = 'pre_alert';
            else if (cat === '13') state = 'end';
            else state = 'alert';
          }

          document.getElementById('current-state').textContent = state;
        } catch {
          document.getElementById('current-state').textContent = 'unknown';
        }
      }

      initState();
    </script>
  </body>
  </html>
    """

    @app.route("/", methods=["GET"])
    def control_page():
        log_request(request.path)
        return render_template_string(
            CONTROL_HTML,
            area_name=app.config.get("AREA_NAME"),
        )

    return app


def main():
    parser = argparse.ArgumentParser(
        description="Fake Pikud Haoref alerts.json server for WLED RedAlert testing"
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=2500,
        help="Port to listen on (default: 5000)",
    )
    parser.add_argument(
        "--cert",
        help="Path to SSL certificate file (PEM) for HTTPS",
    )
    parser.add_argument(
        "--key",
        help="Path to SSL private key file (PEM) for HTTPS",
    )
    parser.add_argument(
        "--area-name",
        default="תל אביב - מזרח",
        help="Default area name to embed in alerts (default: תל אביב - מזרח)",
    )
    parser.add_argument(
        "--initial-state",
        choices=["ok", "alert", "pre_alert", "end"],
        default="ok",
        help='Initial state at startup (default: "ok")',
    )

    args = parser.parse_args()
    app = create_app(initial_state=args.initial_state, area_name=args.area_name)
    ssl_context = None
    if args.cert and args.key:
        ssl_context = (args.cert, args.key)

    app.run(host=args.host, port=args.port, ssl_context=ssl_context)


if __name__ == "__main__":
    main()

