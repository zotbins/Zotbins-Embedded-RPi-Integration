"""Run from the repo root: python -m unittest discover tests"""
import tempfile
import threading
import unittest
from datetime import datetime
from unittest import mock

import requests

from client.client import Uploader
from data.store import EventStore


def response(status):
    r = requests.Response()
    r.status_code = status
    r._content = b"{}"
    return r


class UploaderTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = EventStore(tmp.name)
        self.uploader = Uploader(self.store, "http://api", threading.Event(), upload_timeout=123.0)
        self.uploader.session = mock.Mock()

    def post_kwargs(self):
        return self.uploader.session.post.call_args.kwargs

    def test_sends_the_capture_time_with_utc_offset(self):
        self.store.add(b"jpeg", 0.5, 10.0, 200.0, 1.0, None)
        self.uploader.session.post.return_value = response(200)

        self.uploader._upload_pending()

        sent = datetime.fromisoformat(self.post_kwargs()["data"]["captured_at"])
        self.assertIsNotNone(sent.tzinfo)
        self.assertEqual(self.store.pending(), [])
        self.assertIn("image", self.post_kwargs()["files"])

    def test_leaves_out_readings_it_does_not_have(self):
        self.store.add(b"jpeg", None, None, None, 1.0, None)
        self.uploader.session.post.return_value = response(200)

        self.uploader._upload_pending()

        self.assertEqual(set(self.post_kwargs()["data"]), {"captured_at"})

    def test_waits_long_enough_for_batch_inference(self):
        self.store.add(b"jpeg", 0.5, 10.0, 200.0, 1.0, None)
        self.uploader.session.post.return_value = response(200)

        self.uploader._upload_pending()

        self.assertEqual(self.post_kwargs()["timeout"], (5, 123.0))

    def test_timeout_keeps_the_event_pending(self):
        event_id = self.store.add(b"jpeg", 0.5, 10.0, 200.0, 1.0, None)
        self.uploader.session.post.side_effect = requests.ReadTimeout()

        self.assertFalse(self.uploader._upload_pending())
        self.assertEqual(self.store.pending(), [event_id])


if __name__ == "__main__":
    unittest.main()
