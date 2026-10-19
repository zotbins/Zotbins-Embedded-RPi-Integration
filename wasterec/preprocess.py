"""Image preprocessing shared by training, export calibration and Pi inference.

Only depends on numpy + OpenCV so it runs on the Raspberry Pi without torch.
Training and inference must use exactly the same steps, so keep them here.
"""
import cv2
import numpy as np


def resize(bgr, size):
    # INTER_AREA averages neighbouring pixels, which also suppresses sensor noise
    return cv2.resize(bgr, (size, size), interpolation=cv2.INTER_AREA)


def enhance(bgr, denoise_strength=5, clahe_clip=2.0):
    """Mild denoise + local contrast boost for dark, noisy frames (uint8 BGR in/out)."""
    if denoise_strength > 0:
        bgr = cv2.fastNlMeansDenoisingColored(bgr, None, denoise_strength, denoise_strength, 3, 9)
    if clahe_clip > 0:
        lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        l = cv2.createCLAHE(clipLimit=clahe_clip, tileGridSize=(4, 4)).apply(l)
        bgr = cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)
    return bgr


def to_tensor(bgr, mean, std):
    """uint8 BGR HxWx3 -> float32 RGB 3xHxW, normalised."""
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    rgb = (rgb - np.asarray(mean, np.float32)) / np.asarray(std, np.float32)
    return np.ascontiguousarray(rgb.transpose(2, 0, 1))


def preprocess(bgr, size, mean, std):
    """Full inference pipeline: resize -> enhance -> normalise."""
    return to_tensor(enhance(resize(bgr, size)), mean, std)


def load_camera_profile(path):
    """Profile written by calibrate_camera.py (stats + real noise residuals from Pi frames)."""
    with np.load(path) as d:
        return {k: d[k] for k in d.files}


def camera_profile_augment(bgr, rng, profile):
    """Make a training image look like a real Pi frame: its exposure, contrast,
    colour cast and actual sensor noise (uint8 BGR in/out)."""
    img = bgr.astype(np.float32)
    i = rng.integers(len(profile["l_mean"]))
    gray = img.mean(2)
    m, s = gray.mean(), gray.std() + 1e-3
    t = rng.uniform(0.5, 1.0)  # how far to move toward the sampled frame
    target_m = m + t * (profile["l_mean"][i] - m)
    target_s = s + t * (profile["l_std"][i] - s)
    img = (img - m) * (target_s / s) + target_m
    img = img * profile["gains"][i]  # per-channel colour cast (gray-world)

    noise = profile["noise"][rng.integers(len(profile["noise"]))].astype(np.float32)
    if rng.random() < 0.5:
        noise = noise[:, ::-1]
    if rng.random() < 0.5:
        noise = noise[::-1]
    h, w = img.shape[:2]
    if noise.shape[:2] != (h, w):  # tile/crop to fit; never resize, that would change the noise
        noise = np.pad(noise, ((0, max(0, h - noise.shape[0])), (0, max(0, w - noise.shape[1])), (0, 0)),
                       mode="wrap")[:h, :w]
    img = img + noise
    return np.clip(img, 0, 255).astype(np.uint8)


def low_light_augment(bgr, rng):
    """Simulate a dark, noisy, badly white-balanced camera (uint8 BGR in/out)."""
    img = bgr.astype(np.float32) / 255.0
    img = img * rng.uniform(0.75, 1.15) + rng.uniform(-0.08, 0.08)  # brightness
    img = (img - img.mean()) * rng.uniform(0.6, 1.2) + img.mean()   # contrast
    img = np.clip(img, 0, 1) ** rng.uniform(1.0, 2.2)               # darken via gamma
    img = img * rng.uniform(0.85, 1.15, size=3)                     # white balance drift
    sigma = rng.uniform(0.0, 0.08)
    img = img + rng.normal(0, sigma, img.shape)                     # sensor noise
    return (np.clip(img, 0, 1) * 255).astype(np.uint8)
