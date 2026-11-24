"""Per-pixel even-brightness drive suggestions inside the evaluation rectangle.

Only pixels where both white fields carry light (grey level > 0) inside the
configured area are touched; every other pixel keeps the existing playback
raster. Drive levels are 8-bit grey values. The highest usable grey of a
projector is the largest integer not exceeding its drive limit, and a level of
0 means the projector is switched off.

A pixel is a shortfall pixel when no integer pair inside the two machines'
highest usable greys can bring the stacked brightness within ``TOLERANCE`` of
the target; both projectors are then pushed to their highest usable grey and
the missing brightness is reported. Every other overlap pixel receives an
integer pair whose stacked brightness is within ``TOLERANCE`` of the target,
preferring a small weighted warm/cool cast and a little upward headroom on
both machines.

Pixels sharing the same pair of white-field greys also share one solution, so
the integer search runs over the distinct grey pairs rather than every pixel.
"""

import numpy as np

from .setup import PROJECTORS, UNITS_PER_WHITE, rectangle

TOLERANCE = 0.5
# Preferred upward headroom, as a fraction of each machine's highest usable
# grey. Tried from most headroom to none, so each pixel is solved at the
# largest headroom that still has an integer solution.
MARGIN_STEPS = (0.05, 0.03, 0.015, 0.0)
EPSILON = 1e-9


def max_grey(limit):
    """Highest usable drive grey for a projector limit given in percent."""
    return int(np.floor(255 * limit / 100))


def flat_grey(drive):
    """Grey level used by the existing flat, manual playback image."""
    return int(round(255 * drive / 100))


def _solve_pairs(ka, kb, cap_a, cap_b, base_a, base_b, cast_a, cast_b, target):
    """Choose integer levels for distinct field-grey pairs.

    ``ka``/``kb`` hold the per-grey brightness contributions of the distinct
    pairs, ``cap_a``/``cap_b`` are the grey limits of the current headroom
    step and ``base_a``/``base_b`` are the highest usable greys against which
    relative headroom is measured. Each A level yields an integer B interval;
    the interval ends are ranked lexicographically by absolute weighted cast,
    minimum relative headroom and headroom balance. The search is vectorized
    over A levels, so no Python loop runs per screen pixel.
    """
    count = ka.shape[0]
    best_a = np.zeros(count, dtype=np.int64)
    best_b = np.zeros(count, dtype=np.int64)
    best_cast = np.full(count, np.inf)
    best_head = np.full(count, -np.inf)
    best_balance = np.full(count, np.inf)
    have = np.zeros(count, dtype=bool)

    for level_a in range(cap_a + 1):
        low = np.ceil((target - TOLERANCE - ka * level_a) / kb)
        high = np.floor((target + TOLERANCE - ka * level_a) / kb)
        low = np.maximum(low, 0)
        high = np.minimum(high, cap_b)
        feasible = low <= high
        if not np.any(feasible):
            continue
        for level_b in (low, high):
            valid = feasible & (level_b >= 0)
            if not np.any(valid):
                continue
            contribution_a = ka * level_a
            contribution_b = kb * level_b
            total = contribution_a + contribution_b
            valid &= np.abs(total - target) <= TOLERANCE + 1e-6
            if not np.any(valid):
                continue
            weighted_cast = ((cast_a * contribution_a + cast_b * contribution_b)
                             / np.maximum(total, EPSILON))
            headroom_a = (base_a - level_a) / max(base_a, 1)
            headroom_b = (base_b - level_b) / max(base_b, 1)
            min_headroom = np.minimum(headroom_a, headroom_b)
            imbalance = np.abs(headroom_a - headroom_b)
            cast_score = np.abs(weighted_cast)

            better = valid & (~have | (
                (cast_score < best_cast - 1e-12) |
                (np.abs(cast_score - best_cast) <= 1e-12) & (
                    (min_headroom > best_head + 1e-12) |
                    (np.abs(min_headroom - best_head) <= 1e-12) &
                    (imbalance < best_balance - 1e-12))))
            best_a = np.where(better, level_a, best_a)
            best_b = np.where(better, level_b, best_b)
            best_cast = np.where(better, cast_score, best_cast)
            best_head = np.where(better, min_headroom, best_head)
            best_balance = np.where(better, imbalance, best_balance)
            have |= valid
    return best_a, best_b, have


def suggest(fields, config, size, current=None):
    """Return balanced drive maps and a summary of the suggestion.

    ``current`` holds the two existing playback rasters. When omitted, flat
    manual drives are used. Only dual-coverage pixels inside the configured
    rectangle are rewritten; every other pixel keeps its existing grey.
    """
    width, height = size
    maps = {}
    for key in PROJECTORS:
        if current is not None and current[key] is not None:
            maps[key] = current[key].copy()
        else:
            maps[key] = np.full((height, width), flat_grey(config[key]['drive']), dtype=np.uint8)

    window = rectangle(config)
    field_a = fields['a'][window]
    field_b = fields['b'][window]
    scale = UNITS_PER_WHITE / 255.0
    top = {key: max_grey(config[key]['limit']) for key in PROJECTORS}
    cast = {key: float(config[key]['cast']) for key in PROJECTORS}
    target = config['target']

    overlap = (field_a > 0) & (field_b > 0)
    overlap_count = int(np.count_nonzero(overlap))

    # Group overlap pixels by their (A grey, B grey) pair; each distinct pair
    # needs only one integer search, and its answer fans back to all pixels.
    pair_id = field_a.astype(np.int32) * 256 + field_b.astype(np.int32)
    pair_id[~overlap] = -1
    unique_pairs, inverse = np.unique(pair_id[overlap], return_inverse=True)
    grey_a = (unique_pairs // 256).astype(np.float64)
    grey_b = (unique_pairs % 256).astype(np.float64)
    ka = scale * grey_a
    kb = scale * grey_b

    _, _, reachable = _solve_pairs(ka, kb, top['a'], top['b'],
                                   top['a'], top['b'], cast['a'], cast['b'], target)
    shortfall_pairs = ~reachable
    shortfall_flat = shortfall_pairs[inverse]
    shortfall = np.zeros_like(overlap)
    shortfall[overlap] = shortfall_flat
    for key in ('a', 'b'):
        maps[key][window][shortfall] = top[key]

    unsolved_pairs = reachable.copy()
    shortfall_count = int(np.count_nonzero(shortfall_flat))
    adjusted = shortfall_count

    layer_a = maps['a'][window]
    layer_b = maps['b'][window]
    flat_a = layer_a[overlap]
    flat_b = layer_b[overlap]

    for margin_step in MARGIN_STEPS:
        if not np.any(unsolved_pairs):
            break
        cap_a = max(top['a'] - int(round(margin_step * top['a'])), 0)
        cap_b = max(top['b'] - int(round(margin_step * top['b'])), 0)
        level_a, level_b, feasible_pairs = _solve_pairs(
            ka, kb, cap_a, cap_b, cap_a, cap_b,
            cast['a'], cast['b'], target)
        feasible_pairs &= unsolved_pairs
        if not np.any(feasible_pairs):
            continue
        chosen = feasible_pairs[inverse]
        flat_a[chosen] = level_a[inverse][chosen].astype(np.uint8)
        flat_b[chosen] = level_b[inverse][chosen].astype(np.uint8)
        adjusted += int(np.count_nonzero(chosen))
        unsolved_pairs &= ~feasible_pairs

    # Reachable pairs that no positive-headroom pass solved use the full-cap
    # answer established by the first pass.
    if np.any(unsolved_pairs):
        level_a, level_b, feasible_pairs = _solve_pairs(
            ka, kb, top['a'], top['b'], top['a'], top['b'],
            cast['a'], cast['b'], target)
        chosen = (feasible_pairs & unsolved_pairs)[inverse]
        flat_a[chosen] = level_a[inverse][chosen].astype(np.uint8)
        flat_b[chosen] = level_b[inverse][chosen].astype(np.uint8)
        adjusted += int(np.count_nonzero(chosen))

    layer_a[overlap] = flat_a
    layer_b[overlap] = flat_b

    max_total = ka * top['a'] + kb * top['b']
    # Capacity shortfalls have a positive missing amount. Quantization
    # shortfalls already exceed the target at full drive, so they carry no
    # capacity deficit; report how many pixels fall in each category.
    capacity_pairs = shortfall_pairs & (max_total < target - TOLERANCE)
    pair_deficit = np.where(capacity_pairs, target - max_total, 0.0)
    capacity_count = int(np.count_nonzero(capacity_pairs[inverse]))
    quantization_count = shortfall_count - capacity_count
    summary = {
        'mode': 'balanced',
        'target': target,
        'area': list(config['area']),
        'overlap': overlap_count,
        'pairs': int(unique_pairs.size),
        'adjusted': adjusted,
        'shortfall': shortfall_count,
        'capacity_shortfall': capacity_count,
        'quantization_shortfall': quantization_count,
        'max_deficit': round(float(pair_deficit.max()), 3) if capacity_count else 0.0,
        'tolerance': TOLERANCE,
    }
    return maps, summary
