"""Archive the exact calibrated sources, views and playback PNGs for a saved run."""

from io import BytesIO
import json
from zipfile import ZIP_DEFLATED, ZipFile

from . import photometry, raster
from .setup import PROJECTORS


def archive(fields, drives, record, run):
    config = record['config']
    metrics = photometry.statistics(fields, drives, config)
    report = {'run': run, 'screen': record['size'], 'config': config,
              'playback': record.get('playback', 'flat'),
              'balance': record.get('balance'),
              'statistics': metrics,
              'source_names': record['source_names'], 'source_sha256': record['source_sha256'],
              'drive_sha256': record.get('drive_sha256'),
              'brightness_units': 'relative: white-field PNG level 255 = 100 at full drive',
              'playback_encoding': '8-bit linear drive, 255 = 100 percent'}
    buffer = BytesIO()
    with ZipFile(buffer, 'w', ZIP_DEFLATED) as package:
        for key in PROJECTORS:
            package.writestr(f'field-{key}.png', raster.png(fields[key]))
            package.writestr(f'drive-{key}.png', raster.png(drives[key]))
        for kind in ('mix', 'difference'):
            package.writestr(f'{kind}.png', raster.png(photometry.view(fields, drives, config, kind)))
        package.writestr('report.json', json.dumps(report, ensure_ascii=False, indent=2))
    return buffer.getvalue()
