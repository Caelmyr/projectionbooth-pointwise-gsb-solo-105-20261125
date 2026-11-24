"""Render playback rasters against measured projector white fields."""

import numpy as np

from .setup import PROJECTORS, UNITS_PER_WHITE, rectangle

WHITE = np.array([238.0, 242.0, 239.0], dtype=np.float32)
COOL = np.array([128.0, 185.0, 255.0], dtype=np.float32)
WARM = np.array([255.0, 179.0, 111.0], dtype=np.float32)
UNDER = np.array([241.0, 124.0, 68.0], dtype=np.float32)
OVER = np.array([82.0, 178.0, 242.0], dtype=np.float32)


def measurement(field):
    return field.astype(np.float32) * (UNITS_PER_WHITE / 255)


def emit(fields, drives):
    """Per-pixel relative brightness of each projector from its drive raster."""
    return {key: measurement(fields[key]) * (drives[key].astype(np.float32) / 255.0)
            for key in PROJECTORS}


def cast_field(light, config):
    total = light['a'] + light['b']
    chroma = sum(light[key] * config[key]['cast'] for key in PROJECTORS)
    return np.divide(chroma, total, out=np.zeros_like(total), where=total > 0)


def read_mix(fields, drives, config):
    light = emit(fields, drives)
    total = light['a'] + light['b']
    return light, total, cast_field(light, config)


def composite(total, cast):
    color = np.where(cast[..., None] >= 0, COOL, WARM)
    tone = WHITE + np.abs(cast[..., None] / 100) * (color - WHITE)
    return np.rint(np.clip(total[..., None] / UNITS_PER_WHITE, 0, 1) * tone).astype('uint8')


def difference(total, target):
    error = total - target
    shading = np.minimum(np.abs(error) / max(target, 12), 1)[..., None]
    tone = np.where(error[..., None] < 0, UNDER, OVER)
    neutral = np.array([31.0, 41.0, 49.0], dtype=np.float32)
    return np.rint(neutral + shading * (tone - neutral)).astype('uint8')


def view(fields, drives, config, kind):
    if kind in PROJECTORS:
        return fields[kind]
    _, total, cast = read_mix(fields, drives, config)
    return composite(total, cast) if kind == 'mix' else difference(total, config['target'])


def statistics(fields, drives, config):
    window = rectangle(config)
    local_fields = {key: fields[key][window] for key in PROJECTORS}
    local_drives = {key: drives[key][window] for key in PROJECTORS}
    active = {key: local_fields[key] > 0 for key in PROJECTORS}
    light, total, cast = read_mix(local_fields, local_drives, config)
    overlap = active['a'] & active['b']
    values = total[overlap]
    metrics = {'overlap': int(values.size), 'single': int(np.count_nonzero(active['a'] ^ active['b'])),
               'dark': int(np.count_nonzero(~(active['a'] | active['b'])))}
    if values.size:
        metrics.update(minimum=round(float(values.min()), 2),
                       mean=round(float(values.mean()), 2), maximum=round(float(values.max()), 2),
                       below=int(np.count_nonzero(values < config['target'])),
                       mean_cast=round(float(cast[overlap].mean()), 2))
    return metrics
