"""Manual projector controls and the common screen measurement rectangle."""

from image_lab.validation import Invalid, integer, object_value

UNITS_PER_WHITE = 100
PROJECTORS = ('a', 'b')


def defaults(width, height):
    return {'a': {'drive': 75, 'limit': 100, 'cast': 0},
            'b': {'drive': 72, 'limit': 100, 'cast': 30},
            'target': 64, 'area': [0, 0, width, height]}


def settings(value, size):
    value = object_value(value, '试放设置')
    width, height = size
    area = value.get('area')
    if not isinstance(area, list) or len(area) != 4:
        raise Invalid('测量范围需要左、上、右、下四个像素坐标。')
    left, top, right, bottom = [
        integer(item, name, 0, bound)
        for item, name, bound in zip(area, ('左', '上', '右', '下'), (width, height, width, height))
    ]
    if left >= right or top >= bottom:
        raise Invalid('选区右边须在左边右侧，下边须在上边下方。')
    result = {'area': [left, top, right, bottom],
              'target': integer(value.get('target'), '目标亮度', 1, 200)}
    for name in PROJECTORS:
        projector = object_value(value.get(name), f'{name.upper()} 机设置')
        limit = integer(projector.get('limit'), '驱动上限', 1, 100)
        result[name] = {'drive': integer(projector.get('drive'), '手动驱动', 0, limit),
                        'limit': limit, 'cast': integer(projector.get('cast'), '暖冷偏移', -100, 100)}
    return result


def rectangle(config):
    left, top, right, bottom = config['area']
    return slice(top, bottom), slice(left, right)
