"""HSV-based color segmentation for poop crops.

`analyze` returns per-color pixel percentages.
`make_overlay` paints colored masks back onto the crop for visual review.

HSV ranges below are starting defaults — tune against real Pi captures.
OpenCV HSV: H 0-179, S 0-255, V 0-255.
"""

from dataclasses import dataclass
from typing import Dict

import cv2
import numpy as np

# (lower, upper) HSV ranges. Red wraps the hue circle, so it has two bands.
HSV_RANGES = {
    "red": [
        (np.array([0, 70, 50]),   np.array([10, 255, 255])),
        (np.array([170, 70, 50]), np.array([179, 255, 255])),
    ],
    "yellow": [
        # broadened hue and relaxed saturation/value to capture pale/yellow
        # tones under dim Pi lighting and after AWB adjustments.
        (np.array([10, 30, 30]),  np.array([60, 255, 255])),
    ],
    "green": [
        # widened to include muted greens that appear in some diets
        (np.array([20, 30, 20]),  np.array([100, 255, 255])),
    ],
    "brown": [
        # expanded brown/tan window; allow full V range so brighter browns
        # aren't excluded by a low V ceiling.
        (np.array([5, 20, 10]),   np.array([40, 255, 255])),
    ],
}

# BGR overlay tints (vivid so they pop against muted poop tones)
OVERLAY_TINTS = {
    "red":    (0, 0, 255),
    "yellow": (0, 200, 255),
    "green":  (0, 200, 0),
    "brown":  (40, 80, 140),
}


@dataclass
class ColorResult:
    percentages: Dict[str, float]   # name -> percent (0..100)
    masks: Dict[str, np.ndarray]    # name -> binary mask (uint8, 0/255)


def _build_mask(hsv: np.ndarray, ranges) -> np.ndarray:
    mask = None
    for lo, hi in ranges:
        m = cv2.inRange(hsv, lo, hi)
        mask = m if mask is None else cv2.bitwise_or(mask, m)
    # clean up specks (3x3 is less aggressive and preserves thin regions)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    return mask


def analyze(crop_bgr: np.ndarray) -> ColorResult:
    if crop_bgr is None or crop_bgr.size == 0:
        return ColorResult({k: 0.0 for k in HSV_RANGES}, {k: np.zeros((1, 1), np.uint8) for k in HSV_RANGES})
    # Apply a small blur to reduce sensor noise and speckling before HSV masking.
    blur = cv2.GaussianBlur(crop_bgr, (5, 5), 0)
    hsv = cv2.cvtColor(blur, cv2.COLOR_BGR2HSV)
    total = float(crop_bgr.shape[0] * crop_bgr.shape[1])
    percentages: Dict[str, float] = {}
    masks: Dict[str, np.ndarray] = {}
    for name, ranges in HSV_RANGES.items():
        m = _build_mask(hsv, ranges)
        masks[name] = m
        percentages[name] = round(100.0 * float(np.count_nonzero(m)) / total, 2)
    # LAB-distance fallback: sometimes AWB / lighting shifts push hues
    # away from our HSV windows. Compute LAB distance to reference colors
    # and add those pixels to the mask when within threshold.
    lab = cv2.cvtColor(blur, cv2.COLOR_BGR2LAB)

    # reference LAB colors (approximate) for red/yellow/green/brown
    LAB_REFS = {
        "red":    np.array([136, 208, 195]),
        "yellow": np.array([190, 128, 140]),
        "green":  np.array([150, 84, 150]),
        "brown":  np.array([120, 145, 140]),
    }
    # per-color distance thresholds (tuned conservatively)
    LAB_THRESH = {"red": 40, "yellow": 40, "green": 45, "brown": 45}

    for name, ref in LAB_REFS.items():
        ref_img = np.full(lab.shape, ref, dtype=np.uint8)
        dist = np.linalg.norm(lab.astype(np.int16) - ref_img.astype(np.int16), axis=2)
        lab_mask = (dist <= LAB_THRESH[name]).astype('uint8') * 255
        # combine HSV mask with LAB fallback
        combined = cv2.bitwise_or(masks[name], lab_mask)
        masks[name] = combined
        percentages[name] = round(100.0 * float(np.count_nonzero(combined)) / total, 2)

    return ColorResult(percentages, masks)


def make_overlay(crop_bgr: np.ndarray, masks: Dict[str, np.ndarray], opacity: float = 0.55) -> np.ndarray:
    out = crop_bgr.copy()
    tint_layer = np.zeros_like(out)
    any_mask = np.zeros(out.shape[:2], dtype=np.uint8)
    for name, mask in masks.items():
        tint = OVERLAY_TINTS.get(name, (255, 255, 255))
        tint_layer[mask > 0] = tint
        any_mask = cv2.bitwise_or(any_mask, mask)

    blended = cv2.addWeighted(out, 1.0 - opacity, tint_layer, opacity, 0)
    out[any_mask > 0] = blended[any_mask > 0]
    return out
