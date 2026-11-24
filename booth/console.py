"""Inspect the current drive at a screen point and produce separate playback images."""

import numpy as np

from image_lab.validation import integer

from .setup import PROJECTORS, UNITS_PER_WHITE


def drive_image(config, size, key):
    width, height = size
    drive = round(255 * config[key]['drive'] / 100)
    return np.full((height, width), drive, dtype=np.uint8)


def point(fields, config, size, x, y):
    width, height = size
    x = integer(x, '点测横坐标', 0, width - 1)
    y = integer(y, '点测纵坐标', 0, height - 1)
    readbacks = {}
    for key in PROJECTORS:
        white = int(fields[key][y, x]) * UNITS_PER_WHITE / 255
        limits = config[key]
        contribution = white * limits['drive'] / 100
        readbacks[key] = {'field': round(white, 3), 'drive': limits['drive'], 'limit': limits['limit'],
                          'contribution': round(contribution, 3), 'cast': limits['cast']}
    total = sum(item['contribution'] for item in readbacks.values())
    cast = sum(item['contribution'] * item['cast'] for item in readbacks.values()) / total if total else 0
    left, top, right, bottom = config['area']
    return {'x': x, 'y': y, 'selected': left <= x < right and top <= y < bottom, 'projectors': readbacks,
            'total': round(total, 3), 'cast': round(cast, 3), 'target': config['target']}
