"""Show material + bin scores for a single image (debugging view; see classify_bin.py for bins).

    python -m wasterec.predict --image photo.jpg
    python -m wasterec.predict --camera            # grab one frame from the Pi camera
"""
import argparse
import time

import cv2
import numpy as np

from wasterec.classifier import BinClassifier


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="models/wasterec_int8.onnx")
    ap.add_argument("--meta", help="default: wasterec.json next to the model")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--image")
    src.add_argument("--camera", action="store_true")
    ap.add_argument("--threshold", type=float, default=0.6, help="below this confidence report 'unsure'")
    ap.add_argument("--tta", action="store_true", help="average with horizontally flipped image")
    ap.add_argument("--threads", type=int, default=4)
    args = ap.parse_args()

    clf = BinClassifier(args.model, args.meta, args.threshold, threads=args.threads)

    if args.camera:
        from wasterec.camera import PiCamera
        with PiCamera() as cam:
            img = cam.capture()
    else:
        img = cv2.imdecode(np.fromfile(args.image, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            raise SystemExit(f"could not read {args.image}")

    t0 = time.perf_counter()
    probs = clf.material_probs(img, tta=args.tta)
    bin_probs = probs @ clf.to_bin
    dt = (time.perf_counter() - t0) * 1000

    top = np.argsort(probs)[::-1][:3]
    label = clf.classes[top[0]] if probs[top[0]] >= args.threshold else "unsure"
    print(f"prediction: {label}  ({dt:.0f} ms)")
    for i in top:
        print(f"  {clf.classes[i]:<20} {probs[i]:.3f}")
    best = int(bin_probs.argmax())
    bin_label = clf.bins[best] if bin_probs[best] >= args.threshold else "unsure"
    print(f"bin: {bin_label}  " + "  ".join(f"{b} {p:.3f}" for b, p in zip(clf.bins, bin_probs)))


if __name__ == "__main__":
    main()
