"""Bin classifier: runs the exported ONNX model and turns material scores into a bin.

    from wasterec.classifier import BinClassifier
    clf = BinClassifier("models/wasterec_int8.onnx")
    result = clf.classify(bgr_image)      # {"bin": "recycle", "confidence": 0.94, ...}

Needs only numpy, OpenCV and onnxruntime, so it runs on the Pi.
"""
import json
from pathlib import Path

import numpy as np

from wasterec.preprocess import preprocess


class BinClassifier:
    def __init__(self, model="models/wasterec_int8.onnx", meta=None, threshold=0.6, fallback="trash",
                 threads=4):
        """threshold: minimum bin probability to trust the prediction.
        fallback: bin returned below the threshold ("when in doubt, throw it out")."""
        import onnxruntime as ort

        meta = Path(meta) if meta else Path(model).with_name("wasterec.json")
        self.meta = json.loads(meta.read_text())
        if not self.meta.get("bins"):
            raise ValueError(f"{meta} has no material->bin mapping; re-export a model trained on prepare_data.py data")
        self.classes = self.meta["classes"]
        self.bins = sorted(set(self.meta["bins"].values()))
        if fallback not in self.bins:
            raise ValueError(f"fallback {fallback!r} is not one of {self.bins}")
        self.threshold, self.fallback = threshold, fallback

        # material -> bin as a 0/1 matrix: bin probability = sum of its materials' probabilities
        self.to_bin = np.zeros((len(self.classes), len(self.bins)), np.float32)
        for i, c in enumerate(self.classes):
            self.to_bin[i, self.bins.index(self.meta["bins"][c])] = 1.0

        opts = ort.SessionOptions()
        opts.intra_op_num_threads = threads
        self.sess = ort.InferenceSession(str(model), opts, providers=["CPUExecutionProvider"])

    def material_probs(self, bgr, tta=False):
        x = preprocess(bgr, self.meta["img_size"], self.meta["mean"], self.meta["std"])[None]
        batch = [x, np.ascontiguousarray(x[..., ::-1])] if tta else [x]
        logits = np.concatenate([self.sess.run(None, {"input": b})[0] for b in batch])
        p = np.exp(logits - logits.max(1, keepdims=True))
        return (p / p.sum(1, keepdims=True)).mean(0)

    def classify(self, bgr, tta=False):
        """bgr: uint8 HxWx3 image as loaded by OpenCV."""
        mat = self.material_probs(bgr, tta)
        bin_p = mat @ self.to_bin
        best = int(bin_p.argmax())
        confident = bool(bin_p[best] >= self.threshold)
        return {
            "bin": self.bins[best] if confident else self.fallback,
            "confidence": float(bin_p[best]),
            "confident": confident,
            "bin_probs": {b: float(p) for b, p in zip(self.bins, bin_p)},
            "material": self.classes[int(mat.argmax())],
            "material_confidence": float(mat.max()),
        }
