"""Measure bin accuracy (trash / recycle / compost) on a labeled image folder.

Sub-folders may be named by material (data/val/metal/...) or by bin (pi_test/recycle/...).

    python -m wasterec.evaluate_bins --data data/val
    python -m wasterec.evaluate_bins --data pi_test --save-errors errors
"""
import argparse
import shutil
from pathlib import Path

import cv2
import numpy as np

from wasterec.classifier import BinClassifier

IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="models/wasterec_int8.onnx")
    ap.add_argument("--meta")
    ap.add_argument("--data", default="data/val")
    ap.add_argument("--threshold", type=float, default=0.6)
    ap.add_argument("--fallback", default="trash")
    ap.add_argument("--tta", action="store_true")
    ap.add_argument("--save-errors", help="copy wrongly binned images here, named true_as_predicted")
    args = ap.parse_args()

    clf = BinClassifier(args.model, args.meta, args.threshold, args.fallback)
    bins = clf.bins
    folder_to_bin = {**clf.meta["bins"], **{b: b for b in bins}}

    conf = np.zeros((len(bins), len(bins)), int)  # rows: true bin, cols: predicted (after fallback)
    raw_correct = confident = confident_correct = 0
    skipped = set()
    for d in sorted(p for p in Path(args.data).iterdir() if p.is_dir()):
        if d.name not in folder_to_bin:
            skipped.add(d.name)
            continue
        true_bin = folder_to_bin[d.name]
        for f in sorted(p for p in d.rglob("*") if p.suffix.lower() in IMG_EXTS):
            img = cv2.imdecode(np.fromfile(str(f), np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                continue
            r = clf.classify(img, tta=args.tta)
            top_bin = max(r["bin_probs"], key=r["bin_probs"].get)
            conf[bins.index(true_bin), bins.index(r["bin"])] += 1
            raw_correct += top_bin == true_bin
            if r["confident"]:
                confident += 1
                confident_correct += top_bin == true_bin
            if args.save_errors and r["bin"] != true_bin:
                out = Path(args.save_errors)
                out.mkdir(parents=True, exist_ok=True)
                shutil.copy(f, out / f"{true_bin}_as_{r['bin']}_{r['material']}_{f.name}")

    n = conf.sum()
    assert n, f"no labeled images found in {args.data} (folders must be materials or bins)"
    if skipped:
        print(f"skipped unknown folders: {sorted(skipped)}")
    print(f"{n} images from {args.data}\n")
    print(f"bin accuracy (with '{args.fallback}' fallback): {np.trace(conf) / n:.1%}")
    print(f"bin accuracy (top bin, no threshold):        {raw_correct / n:.1%}")
    print(f"confident predictions: {confident / n:.1%} of images, {confident_correct / max(confident, 1):.1%} correct\n")

    width = max(map(len, bins)) + 2
    print("true \\ predicted".ljust(width + 4) + "".join(b.rjust(width) for b in bins) + "   recall")
    for i, b in enumerate(bins):
        recall = conf[i, i] / max(conf[i].sum(), 1)
        print(b.ljust(width + 4) + "".join(str(v).rjust(width) for v in conf[i]) + f"   {recall:6.1%}")
    precision = [conf[j, j] / max(conf[:, j].sum(), 1) for j in range(len(bins))]
    print("precision".ljust(width + 4) + "".join(f"{p:.1%}".rjust(width) for p in precision))


if __name__ == "__main__":
    main()
