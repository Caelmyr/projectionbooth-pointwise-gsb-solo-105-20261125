"""Make synthetic projector measurements for training on the normal console."""

import numpy as np

from .setup import defaults

WIDTH, HEIGHT = 512, 300


def example():
    yy, xx = np.mgrid[:HEIGHT, :WIDTH]
    a = 232 - 0.57 * np.maximum(xx - 200, 0) + 4 * np.cos(yy / 27)
    b = 251 - 0.6 * np.maximum(336 - xx, 0) + 5 * np.sin(yy / 31)
    a[xx >= 417] = 0
    b[xx < 135] = 0
    shading = np.exp(-((xx - 303) ** 2 / 780 + (yy - 221) ** 2 / 320))
    a -= 151 * shading
    b -= 169 * shading
    fields = {'a': np.rint(a).clip(0, 255).astype('uint8'),
              'b': np.rint(b).clip(0, 255).astype('uint8')}
    config = defaults(WIDTH, HEIGHT)
    config.update(area=[105, 50, 453, 265], target=65)
    config['a'].update(drive=66, limit=85, cast=0)
    config['b'].update(drive=57, limit=82, cast=46)
    return fields, config
