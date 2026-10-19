"""Serves this bin's own records to the dashboard (zotbins-data-visualizer) running on the Pi.

It answers the same GET requests as the cloud API, from the files main.py writes
(data/spool, data/spool/rejected, data/history), so the dashboard works without the cloud.
There is no ML on the Pi, so /inferences is always empty.

Run: python -m data.local_api   (dashboard .env.local: NEXT_PUBLIC_API_URL=http://localhost:8000)
"""
import json
import logging
import re
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from config import CONFIG
from data.fullness import fullness_from_distance

log = logging.getLogger("LocalAPI")

RECORD_DIRS = [CONFIG["spool_dir"], CONFIG["spool_dir"] / "rejected", CONFIG["history_dir"]]
IMAGE_NAME = re.compile(r"^\d{8}T\d{6}_\d{3}\.jpg$")
# The dashboard's next.config.ts forwards this path to /images here, so image links work from any browser.
IMAGE_URL_PREFIX = "/zotbins-images/"

_items = {}  # record id -> dashboard item; records never change once written
_items_lock = threading.Lock()  # requests are handled on several threads


def raw_items():
    """Every record as the dashboard's RawInputItem, oldest first."""
    with _items_lock:
        return _refresh_items()


def _refresh_items():
    seen = set()
    for directory in RECORD_DIRS:
        for path in Path(directory).glob("*.json"):
            record_id = path.stem
            seen.add(record_id)
            if record_id not in _items:
                try:
                    _items[record_id] = _to_item(json.loads(path.read_text()))
                except (OSError, ValueError, KeyError) as e:
                    log.warning("Skipping %s: %s", path.name, e)
    for gone in set(_items) - seen:  # pruned since the last request
        del _items[gone]
    return sorted(_items.values(), key=lambda item: item["captured_at"])


def _to_item(record):
    captured = datetime.fromisoformat(record["ts"]).astimezone()  # stored as Pi local time
    fullness = record.get("fullness")
    if "distance_cm" not in record and fullness is not None:
        # Recorded before fullness was a fraction: the field held the distance in cm.
        fullness = fullness_from_distance(fullness, CONFIG["bin_empty_distance_cm"], CONFIG["bin_full_distance_cm"])
    return {
        "id": int(captured.timestamp() * 1000),
        "captured_at": captured.isoformat(),
        "image_url": IMAGE_URL_PREFIX + record["image"] if record.get("image") else "",
        "weight_after": record.get("weight"),
        "fullness_after": fullness,
        "inferred": False,
    }


def _date_range(query):
    def parse(name, default):
        value = query.get(name, [None])[0]
        return datetime.fromisoformat(value).astimezone(timezone.utc) if value else default

    end = parse("end_date", datetime.now(timezone.utc))
    start = parse("start_date", end - timedelta(days=365))
    return start, end


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlparse(self.path)
        query = parse_qs(url.query)
        try:
            if url.path in ("/", "/health"):
                self._json({"status": "ok", "services": {"database": "local files", "ml_model": "not on this Pi"}})
            elif url.path == "/waste-classes":
                self._json({})
            elif url.path == "/raw_data":
                start, end = _date_range(query)
                data = [item for item in raw_items()
                        if start <= datetime.fromisoformat(item["captured_at"]) <= end]
                self._json({"start_date": start.isoformat(), "end_date": end.isoformat(),
                            "count": len(data), "data": data})
            elif url.path == "/inferences":
                start, end = _date_range(query)
                self._json({"start_date": start.isoformat(), "end_date": end.isoformat(),
                            "count": 0, "data": [], "latest_inferred": end.isoformat()})
            elif url.path.startswith("/images/"):
                self._image(url.path.removeprefix("/images/"))
            else:
                self._json({"detail": "Not Found"}, 404)
        except ValueError as e:  # bad date in the query
            self._json({"detail": str(e)}, 422)

    def _image(self, name):
        if IMAGE_NAME.match(name):  # also blocks ../ paths
            for directory in RECORD_DIRS:
                path = Path(directory) / name
                if path.exists():
                    body = path.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "public, max-age=86400, immutable")
                    self.end_headers()
                    self.wfile.write(body)
                    return
        self._json({"detail": "Image not found"}, 404)

    def _json(self, payload, status=200):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        log.debug(fmt, *args)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
                        datefmt="%H:%M:%S")
    server = ThreadingHTTPServer((CONFIG["local_api_host"], CONFIG["local_api_port"]), Handler)
    log.info("Serving records on http://%s:%d", CONFIG["local_api_host"], CONFIG["local_api_port"])
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
