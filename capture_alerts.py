import argparse
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import requests


def normalize_payload(payload: Any, ignore_id: bool) -> Any:
    """
    Normalize JSON payload for comparison:
    - Optionally drop "id" field from top-level object.
    - Sort keys to make comparison stable.
    """
    if isinstance(payload, dict):
        data: Dict[str, Any] = dict(payload)
        if ignore_id and "id" in data:
            data = dict(data)
            data.pop("id", None)
        # Recursively normalize nested dicts/lists
        return {k: normalize_payload(v, ignore_id) for k, v in sorted(data.items())}
    if isinstance(payload, list):
        return [normalize_payload(v, ignore_id) for v in payload]
    return payload


def dump_payload(
    out_dir: Path,
    payload: Any,
    url: str,
    status: int,
    area_name: Optional[str],
) -> Path:
    """Write raw payload and metadata to a timestamped JSON file."""
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S.%fZ")
    suffix = "-alerts.json"
    filename = f"{ts}{suffix}"
    path = out_dir / filename

    record = {
        "meta": {
            "timestamp": ts,
            "url": url,
            "status": status,
            "areaName": area_name,
        },
        "payload": payload,
    }

    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def poll_once(
    session: requests.Session,
    url: str,
    area_name: Optional[str],
    ignore_id: bool,
    last_norm: Optional[Any],
    out_dir: Path,
) -> Optional[Any]:
    """Perform a single poll, optionally store changed payload, and return new normalized payload."""
    params: Dict[str, str] = {}
    if area_name:
        params["areaName"] = area_name

    try:
        resp = session.get(url, params=params, timeout=10)
        status = resp.status_code
        logging.info("GET %s -> %s", resp.url, status)
    except requests.RequestException as exc:
        logging.warning("Request failed: %s", exc)
        return last_norm

    try:
        # Decode as UTF-8 and strip BOM (oref.org.il may send one)
        raw = resp.content.decode("utf-8-sig").strip()
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as e:
        logging.warning("Response was not valid JSON (status %s): %s", resp.status_code, e)
        return last_norm

    # Skip idle [] responses entirely
    if payload == []:
        logging.info("Payload is empty array (idle); not saving")
        return normalize_payload(payload, ignore_id)

    norm = normalize_payload(payload, ignore_id)

    if last_norm is not None and norm == last_norm:
        logging.info("Payload unchanged; not saving")
        return norm

    saved_path = dump_payload(out_dir, payload, url, resp.status_code, area_name)
    logging.info("Payload changed; wrote %s", saved_path)
    return norm


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Poll Pikud Haoref alerts.json and capture changed responses over time."
    )
    parser.add_argument(
        "--url",
        required=True,
        help="Full URL to real alerts.json endpoint",
    )
    parser.add_argument(
        "--area-name",
        help="Optional areaName query parameter to send on each request",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=10.0,
        help="Polling interval in seconds (default: 10)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("captures"),
        help="Directory to store captured responses (default: ./captures)",
    )
    parser.add_argument(
        "--ignore-id",
        action="store_true",
        help='Ignore "id" field when deciding whether payload changed',
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    session = requests.Session()
    last_norm: Optional[Any] = None

    logging.info(
        "Starting poller: url=%s interval=%.1fs area=%s out_dir=%s ignore_id=%s",
        args.url,
        args.interval,
        args.area_name,
        args.out_dir,
        args.ignore_id,
    )

    try:
        while True:
            last_norm = poll_once(
                session=session,
                url=args.url,
                area_name=args.area_name,
                ignore_id=args.ignore_id,
                last_norm=last_norm,
                out_dir=args.out_dir,
            )
            time.sleep(args.interval)
    except KeyboardInterrupt:
        logging.info("Stopping poller on keyboard interrupt")


if __name__ == "__main__":
    main()

