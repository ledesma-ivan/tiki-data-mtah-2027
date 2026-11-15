"""Continuity-aware velocities for open-data loaders only (ADR-015)."""
import os
import xml.etree.ElementTree as ET

import numpy as np

SPEED_VERSION = 1


def source_signature(paths):
    """Invalidate cached derivatives when a raw file or optional metadata changes."""
    return np.array([(os.stat(p).st_size, os.stat(p).st_mtime_ns) if os.path.exists(p) else (-1, -1)
                     for p in paths], dtype=np.int64)


def cache_matches(z, pitch, signature):
    return ("speed_version" in z and np.array_equal(z["speed_version"], SPEED_VERSION)
            and "pitch" in z and np.array_equal(z["pitch"], pitch)
            and "sources" in z and np.array_equal(z["sources"], signature))


def frame_numbers(values):
    """Require a strictly increasing, positive integer clock; gaps are allowed."""
    a = np.asarray(values, dtype=float)
    if (a.ndim != 1 or not len(a) or not np.isfinite(a).all() or (a < 1).any()
            or (a != np.floor(a)).any() or (np.diff(a) <= 0).any()):
        raise ValueError("tracking frames must be increasing positive integers")
    return a.astype(np.int64)


def derived_speed(xy, identities, periods, frames, *, scale=(1., 1.), fps=25):
    """Backward m/s difference, NaN unless player, period, clock and positions continue.

    identities is a string array [k] or [n,k]; periods is [n]. Empty strings denote
    missing metadata. There is deliberately no slot-identity fallback.
    """
    xy = np.asarray(xy)
    n, k, _ = xy.shape
    ids = np.broadcast_to(np.asarray(identities, dtype=str), (n, k))
    periods = np.asarray(periods, dtype=str)
    frames = np.asarray(frames)
    if periods.shape != (n,) or frames.shape != (n,):
        raise ValueError("periods and frames must match the tracking clock")
    speed = np.full((n, k), np.nan)
    valid = (np.isfinite(xy[1:]).all(axis=2) & np.isfinite(xy[:-1]).all(axis=2)
             & (ids[1:] != "") & (ids[1:] == ids[:-1])
             & ((periods[1:] != "") & (periods[1:] == periods[:-1])
                & (np.diff(frames) == 1))[:, None])
    with np.errstate(invalid="ignore"):
        step = (xy[1:] - xy[:-1]) * scale
        values = np.hypot(step[..., 0], step[..., 1]) * fps
    speed[1:] = np.where(valid, values, np.nan)
    return speed


def game3_continuity(path, frames, n_slots):
    """Resolve inclusive FIFA format intervals to player IDs and period IDs."""
    ids = np.full((len(frames), n_slots), "", dtype=object)
    periods = np.full(len(frames), "", dtype=object)
    if not os.path.exists(path):
        return ids, periods
    root = ET.parse(path).getroot()
    # Accept the same format with or without an XML default namespace.
    for elem in root.iter():
        elem.tag = elem.tag.rsplit("}", 1)[-1]
    channels = {c.get("id"): (c.get("playerId", ""), c.get("channelId"))
                for c in root.findall(".//PlayerChannel")}
    covered = np.zeros(len(frames), bool)
    for spec in root.findall(".//DataFormatSpecification"):
        try:
            start, end = int(spec.attrib["startFrame"]), int(spec.attrib["endFrame"])
        except (KeyError, ValueError) as exc:
            raise ValueError("tracking format requires integer startFrame/endFrame") from exc
        mask = (frames >= start) & (frames <= end)
        if end < start or (covered & mask).any():
            raise ValueError("invalid or overlapping tracking format intervals")
        covered |= mask
        refs = spec.findall(".//PlayerChannelRef")
        if len(refs) != 2 * n_slots:
            raise ValueError("tracking format must declare one x/y pair per slot")
        for slot in range(n_slots):
            x, y = [channels.get(r.get("playerChannelId"), ("", None))
                    for r in refs[2 * slot:2 * slot + 2]]
            if x[0] and x[0] == y[0] and x[1] == "x" and y[1] == "y":
                ids[mask, slot] = x[0]
    params = {p.findtext("Name"): p.findtext("Value")
              for p in root.findall(".//GlobalConfig/ProviderGlobalParameters/ProviderParameter")}
    for name in ("first_half", "second_half", "first_extra_half", "second_extra_half"):
        start, end = params.get(name + "_start"), params.get(name + "_end")
        if not start or not end:
            continue
        start, end = int(start), int(end)
        mask = (frames >= start) & (frames <= end)
        if end < start or (periods[mask] != "").any():
            raise ValueError("invalid or overlapping tracking periods")
        periods[mask] = name
    return ids, periods
