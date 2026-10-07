import json
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path

log = logging.getLogger("Spool")


class Spool:
    """Records waiting to be uploaded, stored as <id>.jpg + <id>.json pairs.

    Every file is written under a temp name and then renamed, so a power cut can't
    leave a half-written file. The .json is written last, so its presence means the
    record is complete. Ids are timestamps, so sorting them gives oldest first.
    """

    def __init__(self, directory, max_records=1000):
        self.dir = Path(directory)
        self.rejected_dir = self.dir / "rejected"
        self.rejected_dir.mkdir(parents=True, exist_ok=True)
        self.max_records = max_records
        self._clean_partial_writes()

    def add(self, jpeg: bytes | None, record: dict) -> str:
        now = datetime.now()
        record_id = now.strftime("%Y%m%dT%H%M%S_") + f"{now.microsecond // 1000:03d}"
        record = {
            "id": record_id,
            "ts": now.isoformat(timespec="milliseconds"),
            **record,
            "image": f"{record_id}.jpg" if jpeg else None,
        }

        if jpeg:
            _atomic_write(self.dir / f"{record_id}.jpg", jpeg)
        _atomic_write(self.dir / f"{record_id}.json", json.dumps(record).encode())
        self._prune(self.dir)
        return record_id

    def pending(self) -> list[str]:
        return _record_ids(self.dir)

    def load(self, record_id) -> tuple[dict, Path | None]:
        record = json.loads((self.dir / f"{record_id}.json").read_text())
        return record, (self.dir / record["image"] if record["image"] else None)

    def remove(self, record_id):
        _remove_record(self.dir, record_id)

    def reject(self, record_id):
        """Keep a record the API refused for inspection, out of the upload queue."""
        for suffix in (".jpg", ".json"):
            src = self.dir / f"{record_id}{suffix}"
            if src.exists():
                shutil.move(str(src), str(self.rejected_dir / src.name))
        self._prune(self.rejected_dir)

    def _prune(self, directory):
        ids = _record_ids(directory)
        excess = len(ids) - self.max_records
        if excess <= 0:
            return
        for record_id in ids[:excess]:
            _remove_record(directory, record_id)
        log.warning("%s full, deleted %d oldest record(s)", directory, excess)

    def _clean_partial_writes(self):
        for tmp in self.dir.glob("*.tmp"):
            tmp.unlink()
        complete = set(self.pending())
        for image in self.dir.glob("*.jpg"):
            if image.stem not in complete:
                image.unlink()


def _record_ids(directory: Path) -> list[str]:
    return sorted(p.stem for p in directory.glob("*.json"))


def _remove_record(directory: Path, record_id):
    # json first, so a crash in between leaves an orphan image (cleaned at startup), never a record without one
    (directory / f"{record_id}.json").unlink(missing_ok=True)
    (directory / f"{record_id}.jpg").unlink(missing_ok=True)


def _atomic_write(path: Path, data: bytes):
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
