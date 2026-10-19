"""Decide which bin an item goes in: trash, recycle or compost.

    python -m wasterec.classify_bin --image photo.jpg
    python -m wasterec.classify_bin --camera                    # one capture
    python -m wasterec.classify_bin --camera --loop             # Enter = classify next item, Ctrl+C = quit
    python -m wasterec.classify_bin --camera --loop --save-dir captures   # also keep each frame for later labeling
"""
import argparse
import json
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from wasterec.classifier import BinClassifier


def report(result, dt_ms, as_json):
    if as_json:
        print(json.dumps({**result, "ms": round(dt_ms)}))
        return
    flag = "" if result["confident"] else f"  (low confidence -> {result['bin']})"
    probs = "  ".join(f"{b} {p:.2f}" for b, p in result["bin_probs"].items())
    print(f"BIN: {result['bin'].upper()}  {result['confidence']:.0%}{flag}   [{probs}]  "
          f"material: {result['material']}  ({dt_ms:.0f} ms)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="models/wasterec_int8.onnx")
    ap.add_argument("--meta", help="default: wasterec.json next to the model")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--image", nargs="+")
    src.add_argument("--camera", action="store_true")
    ap.add_argument("--loop", action="store_true", help="with --camera: keep running, classify on Enter")
    ap.add_argument("--threshold", type=float, default=0.6, help="minimum bin probability to trust")
    ap.add_argument("--fallback", default="trash", help="bin used below the threshold")
    ap.add_argument("--tta", action="store_true", help="also score the mirrored image (2x slower, a bit more accurate)")
    ap.add_argument("--save-dir", help="with --camera: save each frame named by its predicted bin")
    ap.add_argument("--json", action="store_true", help="one JSON line per result")
    ap.add_argument("--threads", type=int, default=4)
    args = ap.parse_args()

    clf = BinClassifier(args.model, args.meta, args.threshold, args.fallback, args.threads)

    def run(img):
        t0 = time.perf_counter()
        result = clf.classify(img, tta=args.tta)
        report(result, (time.perf_counter() - t0) * 1000, args.json)
        return result

    if args.image:
        for path in args.image:
            img = cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                print(f"could not read {path}")
                continue
            if len(args.image) > 1 and not args.json:
                print(f"{path}: ", end="")
            run(img)
        return

    from wasterec.camera import PiCamera

    save_dir = Path(args.save_dir) if args.save_dir else None
    if save_dir:
        save_dir.mkdir(parents=True, exist_ok=True)
    with PiCamera() as cam:
        while True:
            if args.loop:
                try:
                    input("Place item and press Enter (Ctrl+C to quit)... ")
                except (KeyboardInterrupt, EOFError):
                    print()
                    break
            frame = cam.capture()
            result = run(frame)
            if save_dir:
                name = f"{datetime.now():%Y%m%d_%H%M%S}_{result['bin']}_{result['material']}.jpg"
                cv2.imwrite(str(save_dir / name), frame)
            if not args.loop:
                break


if __name__ == "__main__":
    main()
