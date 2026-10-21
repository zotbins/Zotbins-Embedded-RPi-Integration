"""Serves this bin's own events to the dashboard (zotbins-data-visualizer) running on the Pi.

It answers the same GET requests as the cloud API, from the event store main.py writes
(data/events.db + data/images), so the dashboard works without the cloud and shows the bin's whole history.
/inferences and /waste-classes come from the on-device classifier (wasterec) that main.py runs.

Run: python -m data.local_api   (dashboard .env.local: NEXT_PUBLIC_API_URL=http://localhost:8000)
"""
import json
import logging
import re
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from config import CONFIG
from data.store import EventStore

log = logging.getLogger("LocalAPI")

store = EventStore(CONFIG["data_dir"], CONFIG["min_free_disk_mb"])
# The dashboard only shows the bin: landfill / recycle / compost. The classifier calls landfill "trash".
DASHBOARD_BIN = {"trash": "landfill"}
DASHBOARD_BINS = ("landfill", "recycle", "compost")
IMAGE_NAME = re.compile(r"^(\d{8}T\d{6}_\d{3})\.jpg$")
# The dashboard's next.config.ts forwards this path to /images here, so image links work from any browser.
IMAGE_URL_PREFIX = "/zotbins-images/"


def items(query):
    """Events in the request's date range as (RawInputItem, InferenceItem or None), oldest first."""
    start, end = _date_range(query)
    events = store.events(int(start.timestamp() * 1000), int(end.timestamp() * 1000))
    return start, end, [_to_items(event) for event in events]


def _to_items(event):
    captured = datetime.fromisoformat(event["ts"]).astimezone()  # shown in Pi local time
    raw = {
        "id": event["unix_ms"],
        "captured_at": captured.isoformat(),
        "image_url": f"{IMAGE_URL_PREFIX}{event['id']}.jpg" if event["image"] else "",
        "weight_after": event["weight_g"],
        "fullness_after": event["fullness"],
        "inferred": event["bin"] is not None,
    }
    inference = None
    if event["bin"]:
        inference = {
            "id": raw["id"],
            "raw_id": raw["id"],
            "bounding_box": (event["classification"] or {}).get("box") or [],
            "class_name": DASHBOARD_BIN.get(event["bin"], event["bin"]),
            "captured_at": raw["captured_at"],
        }
    return raw, inference


def _date_range(query):
    """Without start_date / end_date: everything, from the first event up to now."""
    def parse(name, default):
        value = query.get(name, [None])[0]
        return datetime.fromisoformat(value).astimezone(timezone.utc) if value else default

    end = parse("end_date", datetime.now(timezone.utc))
    start = parse("start_date", datetime.fromtimestamp(0, timezone.utc))
    return start, end


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlparse(self.path)
        query = parse_qs(url.query)
        try:
            if url.path in ("/", "/health"):
                model = "wasterec (on device)" if Path(CONFIG["classifier_model"]).exists() else "none"
                self._json({"status": "ok", "services": {"database": "SQLite (data/events.db)", "ml_model": model}})
            elif url.path == "/waste-classes":
                self._json({b: b for b in DASHBOARD_BINS})  # class names are already bins
            elif url.path == "/raw_data":
                start, end, pairs = items(query)
                data = [raw for raw, _ in pairs]
                self._json({"start_date": start.isoformat(), "end_date": end.isoformat(),
                            "count": len(data), "data": data})
            elif url.path == "/inferences":
                start, end, pairs = items(query)
                data = [inf for _, inf in pairs if inf]
                latest = data[-1]["captured_at"] if data else end.isoformat()
                self._json({"start_date": start.isoformat(), "end_date": end.isoformat(),
                            "count": len(data), "data": data, "latest_inferred": latest})
            elif url.path.startswith("/images/"):
                self._image(url.path.removeprefix("/images/"))
            else:
                self._json({"detail": "Not Found"}, 404)
        except ValueError as e:  # bad date in the query
            self._json({"detail": str(e)}, 422)

    def _image(self, name):
        match = IMAGE_NAME.match(name)  # also blocks ../ paths
        path = store.image_path(match.group(1)) if match else None
        if path and path.exists():
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
