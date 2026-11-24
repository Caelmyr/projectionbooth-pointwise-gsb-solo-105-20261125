"""Inspect the current drive at a screen point and produce separate playback images."""

import numpy as np

from image_lab.validation import integer

from .setup import PROJECTORS, UNITS_PER_WHITE


def drive_image(config, size, key):
    width, height = size
    drive = round(255 * config[key]['drive'] / 100)
    return np.full((height, width), drive, dtype=np.uint8)


def point(fields, drives, config, size, x, y):
    width, height = size
    x = integer(x, '点测横坐标', 0, width - 1)
    y = integer(y, '点测纵坐标', 0, height - 1)
    readbacks = {}
    for key in PROJECTORS:
        white = int(fields[key][y, x]) * UNITS_PER_WHITE / 255
        grey = int(drives[key][y, x])
        limits = config[key]
        contribution = white * grey / 255
        readbacks[key] = {'field': round(white, 3), 'grey': grey,
                          'drive': round(100 * grey / 255, 2),
                          'limit': limits['limit'],
                          'max_grey': int(np.floor(255 * limits['limit'] / 100)),
                          'contribution': round(contribution, 3), 'cast': limits['cast']}
    total = sum(item['contribution'] for item in readbacks.values())
    cast = sum(item['contribution'] * item['cast'] for item in readbacks.values()) / total if total else 0
    left, top, right, bottom = config['area']
    selected = left <= x < right and top <= y < bottom
    both_cover = all(int(fields[key][y, x]) > 0 for key in PROJECTORS)
    at_limit = all(int(drives[key][y, x]) == int(readbacks[key]['max_grey'])
                   for key in PROJECTORS)
    shortfall = bool(selected and both_cover and at_limit and
                     abs(total - config['target']) > 0.5 + 1e-9)
    return {'x': x, 'y': y, 'selected': selected, 'shortfall': shortfall,
            'projectors': readbacks,
            'total': round(total, 3), 'cast': round(cast, 3), 'target': config['target']}
