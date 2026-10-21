"""Starts the dashboard afresh, e.g. after test data, without deleting anything.

The dashboard then only shows events from the reset on (fullness history, total uses, composition, images);
every event stays in data/events.db. Takes effect at the dashboard's next refresh (10 s).

Run from the repo root:
    python3 -m data.dashboard_reset            # reset: show events from now on
    python3 -m data.dashboard_reset --status   # when it was last reset
    python3 -m data.dashboard_reset --undo     # show all events again
"""
import argparse
from datetime import datetime

from config import CONFIG
from data.store import RESET_KEY, EventStore


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--status", action="store_true", help="show when the dashboard was last reset")
    group.add_argument("--undo", action="store_true", help="show all events again")
    args = parser.parse_args()

    store = EventStore(CONFIG["data_dir"], CONFIG["min_free_disk_mb"])
    total = len(store.events())
    if args.undo:
        store.set_setting(RESET_KEY, None)
    elif not args.status:
        store.set_setting(RESET_KEY, datetime.now().astimezone().isoformat(timespec="milliseconds"))

    since = store.get_setting(RESET_KEY)
    if since:
        shown = len(store.events(int(datetime.fromisoformat(since).timestamp() * 1000)))
        print(f"Dashboard shows events since {since}: {shown} of {total} stored events")
    else:
        print(f"Dashboard shows all {total} stored events")


if __name__ == "__main__":
    main()
