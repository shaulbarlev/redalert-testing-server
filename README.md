# redalert-testing-server

Fake Pikud Haoref `alerts.json` HTTP server for testing the WLED RedAlert usermod without real alerts, plus a script to capture real API responses over time.

## Fake alerts server

### Install and run

```bash
pip install -r requirements.txt
python server.py --port 2500 --area-name "תל אביב - מזרח"
```

### Endpoints

- **Alerts (for WLED)**  
  `GET /WarningMessages/alert/alerts.json`  
  Returns JSON matching the real Pikud Haoref shape (Category 10 + title logic, as in redalert.cpp stateFromAlert):
  - **ok** → `[]`
  - **alert** → single object with `cat: "1"`, `title`, `data`, `desc`
  - **pre_alert** → single object with `cat: "10"`, `title: "בדקות הקרובות צפיות להתקבל התרעות באזורך"`
  - **end** → single object with `cat: "10"`, `title: "האירוע הסתיים"` (or any other cat-10 title → end)

  Optional query: `?areaName=...` to override the default area for that request.

- **State control**  
  `POST /set_state`  
  Body: `{ "state": "ok" | "alert" | "pre_alert" | "end" }`

- **Area control**  
  `POST /set_area`  
  Body: `{ "area": "<area name>" }` — sets the default area used when no `areaName` query is given.

- **Control UI**  
  `GET /` — HTML page with state buttons (OK / Alert / Pre-alert / End) and an area text field + “Set area” button.

### HTTPS

Provide PEM certificate and key to serve over HTTPS:

```bash
# One-time: create self-signed cert (e.g. for local testing)
openssl req -x509 -newkey rsa:2048 -nodes -keyout key.pem -out cert.pem -days 365 -subj "/CN=localhost"

# Run with HTTPS
python server.py --port 2500 --cert cert.pem --key key.pem
```

### CLI options

- `--host` — bind address (default: `0.0.0.0`)
- `--port` — port (default: `2500`)
- `--area-name` — default area name in alerts
- `--initial-state` — `ok` | `alert` | `pre_alert` | `end` (default: `ok`)
- `--cert` / `--key` — paths to PEM files for HTTPS

---

## API capture script

Polls the **real** Pikud Haoref `alerts.json` URL and saves a timestamped file whenever the response changes (skips idle `[]`).

### Usage

```bash
python capture_alerts.py \
  --url "https://www.oref.org.il/WarningMessages/alert/alerts.json" \
  --interval 0.5 \
  --out-dir ./captures \
  --ignore-id \
  --verbose
```

- **`--url`** — full URL to real `alerts.json` (required)
- **`--area-name`** — optional; send as `areaName` query param on each request
- **`--interval`** — seconds between polls (default: `10`)
- **`--out-dir`** — directory for captures (default: `./captures`)
- **`--ignore-id`** — when comparing, ignore the `id` field so only semantic changes trigger a save
- **`--verbose`** — debug logging

Each saved file contains `meta` (timestamp, URL, status, areaName) and `payload` (raw JSON from the API). Stop with Ctrl+C.
