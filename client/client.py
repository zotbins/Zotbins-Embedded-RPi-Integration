import logging
import threading

import requests

log = logging.getLogger("Upload")


class Uploader(threading.Thread):
    """Sends stored events to the Front-End API (WasteRec) oldest first, in the background.

    An event is only marked uploaded once the API accepts it. If the network
    or API is down, it retries every `retry_interval` seconds.
    """

    def __init__(self, store, api_url, stop_event, retry_interval=10.0):
        super().__init__(name="uploader", daemon=True)
        self.store = store
        self.api_url = api_url.rstrip("/")
        self.stop_event = stop_event
        self.retry_interval = retry_interval
        self.session = requests.Session()  # reuses the connection between uploads
        self._wake = threading.Event()

    def wake(self):
        """Called when a new event is stored (or on shutdown)."""
        self._wake.set()

    def run(self):
        if not self.api_url:
            log.warning("No API URL configured; events are only stored locally (%s)", self.store.db_path)
            return

        while not self.stop_event.is_set():
            self._wake.clear()
            if self._upload_pending():
                self._wake.wait()
            else:
                self._wake.wait(self.retry_interval)

    def _upload_pending(self) -> bool:
        """Upload everything waiting. Returns False if we should retry later."""
        for record_id in self.store.pending():
            if self.stop_event.is_set():
                return True
            try:
                record, image_path = self.store.load(record_id)
                response = self._post(record, image_path)
            except FileNotFoundError:
                continue
            except requests.RequestException as e:
                log.warning("Cannot reach %s (%s); %d record(s) waiting",
                            self.api_url, type(e).__name__, len(self.store.pending()))
                return False

            if response.ok:
                self.store.mark_uploaded(record_id)
                log.info("Uploaded %s", record_id)
                _log_inference(response)
            elif response.status_code >= 500 or response.status_code in (408, 429):
                log.warning("API returned %d; will retry", response.status_code)
                return False
            else:
                # Retrying won't help a request the API refuses; mark it instead of blocking the queue.
                log.error("API rejected %s (%d): %s", record_id, response.status_code, response.text[:200])
                self.store.mark_rejected(record_id)
        return True

    def _post(self, record, image_path):
        url = f"{self.api_url}/record"
        fields = _form_fields(record)
        if image_path is None:  # camera disabled, or the picture was removed to free disk space
            return self.session.post(url, data=fields, timeout=(5, 30))
        with open(image_path, "rb") as image:
            return self.session.post(
                url,
                data=fields,
                files={"image": ("image.jpg", image, "image/jpeg")},
                timeout=(5, 30),
            )


def _form_fields(record):
    return {key: record[key] for key in ("weight", "fullness") if record.get(key) is not None}


def _log_inference(response):
    try:
        result = response.json()
    except ValueError:
        return
    if result.get("inference_triggered"):
        log.info("Inference triggered: %s total", result.get("inference_count"))
