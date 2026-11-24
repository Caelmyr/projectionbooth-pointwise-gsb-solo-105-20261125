"""Read linear 8-bit measurement rasters and encode views without rescaling."""

from io import BytesIO
from PIL import Image, UnidentifiedImageError
import numpy as np

from image_lab.validation import Invalid

MAX_BYTES = 20 * 1024 * 1024
MAX_PIXELS = 2_500_000


def decode(raw):
    if len(raw) > MAX_BYTES:
        raise Invalid('单张白场不得超过 20 MiB。')
    try:
        with Image.open(BytesIO(raw)) as image:
            width, height = image.size
            if not (8 <= width <= 2400 and 8 <= height <= 2400 and width * height <= MAX_PIXELS):
                raise Invalid('白场边长需为 8 至 2400 像素，总像素不超过 250 万。')
            if image.format != 'PNG' or image.mode != 'L' or getattr(image, 'n_frames', 1) != 1:
                raise Invalid('请上传单帧 8 位灰度 PNG 白场。')
            return np.asarray(image, dtype=np.uint8)
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise Invalid('白场文件无法读取。') from exc


def png(pixels):
    buffer = BytesIO()
    Image.fromarray(pixels).save(buffer, format='PNG', compress_level=3)
    return buffer.getvalue()


def read(path):
    with Image.open(path) as image:
        return np.asarray(image, dtype=np.uint8)
