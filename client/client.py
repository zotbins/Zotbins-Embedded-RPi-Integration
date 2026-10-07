import logging
import threading

import requests

log = logging.getLogger("Upload")


class Uploader(threading.Thread):
    """Sends spooled records to the Front-End API (WasteRec) oldest first, in the background.

    Records are only deleted from the spool once the API accepts them. If the network
    or API is down, it retries every `retry_interval` seconds.
    """

    def __init__(self, spool, api_url, stop_event, retry_interval=10.0):
        super().__init__(name="uploader", daemon=True)
        self.spool = spool
        self.api_url = api_url.rstrip("/")
        self.stop_event = stop_event
        self.retry_interval = retry_interval
        self.session = requests.Session()  # reuses the connection between uploads
        self._wake = threading.Event()

    def wake(self):
        """Called when a new record is spooled (or on shutdown)."""
        self._wake.set()

    def run(self):
        if not self.api_url:
            log.warning("No API URL configured; records will stay in %s", self.spool.dir)
            return

        while not self.stop_event.is_set():
            self._wake.clear()
            if self._upload_pending():
                self._wake.wait()
            else:
                self._wake.wait(self.retry_interval)

    def _upload_pending(self) -> bool:
        """Upload everything waiting. Returns False if we should retry later."""
        for record_id in self.spool.pending():
            if self.stop_event.is_set():
                return True
            try:
                record, image_path = self.spool.load(record_id)
                with open(image_path, "rb") as image:
                    response = self.session.post(
                        f"{self.api_url}/record",
                        data=_form_fields(record),
                        files={"image": ("image.jpg", image, "image/jpeg")},
                        timeout=(5, 30),
                    )
            except FileNotFoundError:
                continue  # pruned from the spool while we were working on it
            except requests.RequestException as e:
                log.warning("Cannot reach %s (%s); %d record(s) waiting",
                            self.api_url, type(e).__name__, len(self.spool.pending()))
                return False

            if response.ok:
                self.spool.remove(record_id)
                log.info("Uploaded %s", record_id)
                _log_inference(response)
            elif response.status_code >= 500 or response.status_code in (408, 429):
                log.warning("API returned %d; will retry", response.status_code)
                return False
            else:
                # Retrying won't help a request the API refuses; set it aside instead of blocking the queue.
                log.error("API rejected %s (%d): %s", record_id, response.status_code, response.text[:200])
                self.spool.reject(record_id)
        return True


def _form_fields(record):
    return {key: record[key] for key in ("weight", "fullness") if record.get(key) is not None}


def _log_inference(response):
    try:
        result = response.json()
    except ValueError:
        return
    if result.get("inference_triggered"):
        log.info("Inference triggered: %s total", result.get("inference_count"))
