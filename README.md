## redalert-testing-server

Fake Pikud Haoref `alerts.json` HTTP server for testing the WLED RedAlert usermod without real alerts.

### Run locally

1. **Install dependencies**

```bash
pip install -r requirements.txt
```

2. **Start the server**

```bash
python server.py --port 5000 --area-name "תל אביב - מזרח"
```

The server will:

- **Alerts endpoint**: `GET /WarningMessages/alert/alerts.json`
  - `ok` → `[]`
  - `alert` → one alert object with `category: 1`
  - `pre_alert` → one alert object with `category: 14`
  - `end` → one alert object with `category: 13`
- **Control API**: `POST /set_state` with JSON body:

```json
{ "state": "ok" | "alert" | "pre_alert" | "end" }
```

- **Control UI**: `GET /` – minimal HTML page with 4 buttons that call `/set_state`.

You can also pass an `areaName` query param to the alerts endpoint for flexible tests:

- `GET /WarningMessages/alert/alerts.json?areaName=תל אביב - מזרח`

