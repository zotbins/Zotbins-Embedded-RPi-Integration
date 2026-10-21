"""Every event (an item going into the bin), kept permanently.

    data/events.db                        one row per event: time, fullness, weight, classification, upload status;
                                          plus fullness_readings, the fullness measured every minute between events
    data/images/2026-10-20/<id>.jpg       the picture of the item, one folder per day

Ids are the event's local time (20261020T181923_562), so sorting them gives oldest first.
The database is SQLite, so the pipeline (writing) and the local API (reading) can use it at the same time.
"""
import json
import logging
import os
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from data.fullness import fullness_from_distance

log = logging.getLogger("Store")

RESET_KEY = "dashboard_since"  # setting: the dashboard only shows events after this time (data.dashboard_reset)

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id             TEXT PRIMARY KEY,  -- local time, e.g. 20261020T181923_562
    ts             TEXT NOT NULL,     -- ISO 8601 with UTC offset
    unix_ms        INTEGER NOT NULL,  -- same instant, for time-range queries
    fullness       REAL,              -- 0.0 empty .. 1.0 full
    distance_cm    REAL,              -- raw ultrasonic reading
    weight_g       REAL,
    transit_s      REAL,              -- seconds the item was in view
    bin            TEXT,              -- classifier's bin: trash / recycle / compost
    bin_confidence REAL,
    classification TEXT,              -- classifier's full output (JSON)
    image          TEXT,              -- path under data/images, NULL if no picture
    upload         TEXT NOT NULL DEFAULT 'pending'  -- pending / uploaded / rejected (cloud API)
);
CREATE INDEX IF NOT EXISTS events_time ON events (unix_ms);
CREATE INDEX IF NOT EXISTS events_upload ON events (upload) WHERE upload = 'pending';

CREATE TABLE IF NOT EXISTS fullness_readings (
    unix_ms        INTEGER PRIMARY KEY,
    ts             TEXT NOT NULL,     -- ISO 8601 with UTC offset
    fullness       REAL,              -- 0.0 empty .. 1.0 full
    distance_cm    REAL               -- raw ultrasonic reading
);

CREATE TABLE IF NOT EXISTS settings (
    key            TEXT PRIMARY KEY,  -- e.g. dashboard_since: the dashboard only shows events after this
    value          TEXT
);
"""
COLUMNS = ("id", "ts", "unix_ms", "fullness", "distance_cm", "weight_g", "transit_s",
           "bin", "bin_confidence", "classification", "image", "upload")


class EventStore:
    def __init__(self, data_dir, min_free_disk_mb=1000):
        self.dir = Path(data_dir)
        self.db_path = self.dir / "events.db"
        self.images_dir = self.dir / "images"
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.min_free_bytes = min_free_disk_mb * 1_000_000
        with self._connect() as db:
            db.execute("PRAGMA journal_mode=WAL")  # readers don't block the writer
            db.executescript(SCHEMA)

    @contextmanager
    def _connect(self):
        # A connection per call: the pipeline, the uploader thread and the API's request threads each get their own.
        db = sqlite3.connect(self.db_path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:  # commits, or rolls back on an exception
                yield db
        finally:
            db.close()

    def add(self, jpeg: bytes | None, fullness, distance_cm, weight_g, transit_s, classification) -> str:
        now = datetime.now().astimezone()  # ts keeps its UTC offset, so a timezone change can't shift it
        event_id = now.strftime("%Y%m%dT%H%M%S_") + f"{now.microsecond // 1000:03d}"
        image = None
        if jpeg:
            self._make_room()
            image = f"{now:%Y-%m-%d}/{event_id}.jpg"
            _atomic_write(self.images_dir / image, jpeg)  # before the row, so a row never points at a missing file
        self._insert({
            "id": event_id,
            "ts": now.isoformat(timespec="milliseconds"),
            "unix_ms": int(now.timestamp() * 1000),
            "fullness": fullness,
            "distance_cm": distance_cm,
            "weight_g": weight_g,
            "transit_s": transit_s,
            "bin": classification["bin"] if classification else None,
            "bin_confidence": classification["confidence"] if classification else None,
            "classification": json.dumps(classification) if classification else None,
            "image": image,
            "upload": "pending",
        })
        return event_id

    def _insert(self, row):
        with self._connect() as db:
            db.execute(f"INSERT OR IGNORE INTO events ({', '.join(COLUMNS)}) VALUES "
                       f"({', '.join(':' + c for c in COLUMNS)})", row)

    def events(self, start_ms=None, end_ms=None) -> list[dict]:
        """Events in a time range (both ends optional), oldest first."""
        with self._connect() as db:
            rows = db.execute("SELECT * FROM events WHERE unix_ms BETWEEN ? AND ? ORDER BY unix_ms",
                              (start_ms or 0, end_ms or 2**62)).fetchall()
        return [_as_event(row) for row in rows]

    def add_reading(self, fullness, distance_cm):
        """A fullness measurement taken between events (so emptying the bin shows up without an event)."""
        now = datetime.now().astimezone()
        with self._connect() as db:
            db.execute("INSERT OR REPLACE INTO fullness_readings VALUES (?, ?, ?, ?)",
                       (int(now.timestamp() * 1000), now.isoformat(timespec="milliseconds"), fullness, distance_cm))

    def current_fullness(self) -> dict | None:
        """The newest fullness measurement, from an event or a reading between events."""
        with self._connect() as db:
            row = db.execute("""
                SELECT ts, unix_ms, fullness, distance_cm FROM (
                    SELECT ts, unix_ms, fullness, distance_cm FROM events WHERE distance_cm IS NOT NULL
                    UNION ALL
                    SELECT ts, unix_ms, fullness, distance_cm FROM fullness_readings WHERE distance_cm IS NOT NULL
                ) ORDER BY unix_ms DESC LIMIT 1""").fetchone()
        return dict(row) if row else None

    def get_setting(self, key):
        with self._connect() as db:
            row = db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def set_setting(self, key, value):
        """None removes it."""
        with self._connect() as db:
            if value is None:
                db.execute("DELETE FROM settings WHERE key = ?", (key,))
            else:
                db.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (key, value))

    def image_path(self, event_id) -> Path | None:
        with self._connect() as db:
            row = db.execute("SELECT image FROM events WHERE id = ?", (event_id,)).fetchone()
        return self.images_dir / row["image"] if row and row["image"] else None

    # ---- upload queue (client.Uploader) ----

    def pending(self) -> list[str]:
        with self._connect() as db:
            return [r["id"] for r in db.execute("SELECT id FROM events WHERE upload = 'pending' ORDER BY id")]

    def load(self, event_id) -> tuple[dict, Path | None]:
        with self._connect() as db:
            row = db.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
        if row is None:
            raise FileNotFoundError(event_id)
        image = self.images_dir / row["image"] if row["image"] else None
        return {"weight": row["weight_g"], "fullness": row["fullness"]}, image if image and image.exists() else None

    def mark_uploaded(self, event_id):
        self._set_upload(event_id, "uploaded")

    def mark_rejected(self, event_id):
        """The API refused it; keep it, but stop retrying."""
        self._set_upload(event_id, "rejected")

    def _set_upload(self, event_id, status):
        with self._connect() as db:
            db.execute("UPDATE events SET upload = ? WHERE id = ?", (status, event_id))

    # ---- housekeeping ----

    def _make_room(self):
        """Events are never deleted, but if the SD card is nearly full the oldest pictures go, so the Pi keeps working."""
        if shutil.disk_usage(self.images_dir).free >= self.min_free_bytes:
            return
        with self._connect() as db:
            oldest = db.execute("SELECT id, image FROM events WHERE image IS NOT NULL ORDER BY id LIMIT 50").fetchall()
            for row in oldest:
                (self.images_dir / row["image"]).unlink(missing_ok=True)
                db.execute("UPDATE events SET image = NULL WHERE id = ?", (row["id"],))
        if oldest:
            log.warning("Disk nearly full: deleted the %d oldest pictures (their events are kept)", len(oldest))

    def import_legacy(self, spool_dir, empty_cm, full_cm):
        """Move records from the old <id>.json + <id>.jpg folders (data/spool, its rejected/, data/history) in here."""
        spool_dir = Path(spool_dir)
        folders = {spool_dir: "pending", spool_dir / "rejected": "rejected", self.dir / "history": "uploaded"}
        moved = 0
        for folder, upload in folders.items():
            for path in sorted(folder.glob("*.json")) if folder.is_dir() else []:
                record = json.loads(path.read_text())
                fullness = record.get("fullness")
                if "distance_cm" not in record and fullness is not None:
                    # Recorded before fullness was a fraction: the field held the distance in cm.
                    record["distance_cm"], fullness = fullness, fullness_from_distance(fullness, empty_cm, full_cm)
                when = datetime.fromisoformat(record["ts"])
                image = None
                if record.get("image") and (folder / record["image"]).exists():
                    image = f"{when:%Y-%m-%d}/{record['id']}.jpg"
                    (self.images_dir / image).parent.mkdir(exist_ok=True)
                    shutil.move(str(folder / record["image"]), str(self.images_dir / image))
                classification = record.get("classification")
                self._insert({
                    "id": record["id"],
                    "ts": record["ts"],
                    "unix_ms": int(when.timestamp() * 1000),
                    "fullness": fullness,
                    "distance_cm": record.get("distance_cm"),
                    "weight_g": record.get("weight"),
                    "transit_s": record.get("transit_duration"),
                    "bin": classification["bin"] if classification else None,
                    "bin_confidence": classification["confidence"] if classification else None,
                    "classification": json.dumps(classification) if classification else None,
                    "image": image,
                    "upload": upload,
                })
                path.unlink()  # only after the row is committed
                moved += 1
        for folder in folders:
            for leftover in folder.glob("*.tmp") if folder.is_dir() else []:
                leftover.unlink()
        for folder in sorted(folders, key=lambda f: len(f.parts), reverse=True):  # rejected/ before spool/
            if folder.is_dir() and not any(folder.iterdir()):
                folder.rmdir()
        if moved:
            log.info("Moved %d record(s) from the old spool/history folders into %s", moved, self.db_path)


def _as_event(row) -> dict:
    event = dict(row)
    event["classification"] = json.loads(event["classification"]) if event["classification"] else None
    return event


def _atomic_write(path: Path, data: bytes):
    path.parent.mkdir(exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
