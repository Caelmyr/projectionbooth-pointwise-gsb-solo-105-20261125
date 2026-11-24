"""Persist aligned white fields, playback rasters and frozen proof packages."""

from hashlib import sha256
import json
from shutil import rmtree
from threading import RLock
from uuid import uuid4

from werkzeug.exceptions import NotFound

from image_lab.validation import Conflict, Invalid, identifier, integer, text, timestamp

from . import balance, delivery, raster, setup
from .console import drive_image


def read_json(path):
    try:
        return json.loads(path.read_bytes())
    except FileNotFoundError:
        raise NotFound('找不到这组校样或它的保存记录。') from None


def write_json(path, value):
    temporary = path.with_name('.' + uuid4().hex)
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False), encoding='utf-8')
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


class Booths:
    def __init__(self, root):
        self.root = root / 'booths'
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()

    def directory(self, key):
        return self.root / identifier(key)

    def record(self, key):
        return read_json(self.directory(key) / 'booth.json')

    def list(self):
        records = [read_json(path) for path in self.root.glob('[a-f0-9]*/booth.json')]
        return sorted(records, key=lambda record: (record['created'], record['id']), reverse=True)

    def add(self, name, fields, names, config=None):
        clean_name = text(name, '校样名称', 84, False)
        height, width = fields['a'].shape
        if fields['b'].shape != fields['a'].shape:
            raise Invalid('两张已对齐白场的宽高必须一致。')
        size = [width, height]
        source = {key: raster.png(fields[key]) for key in setup.PROJECTORS}
        key = uuid4().hex
        clean_config = setup.settings(config or setup.defaults(width, height), size)
        drives = {name: raster.png(drive_image(clean_config, size, name))
                  for name in setup.PROJECTORS}
        record = {'id': key, 'name': clean_name, 'size': size, 'revision': 1,
                  'created': timestamp(), 'source_names': names, 'synthetic': config is not None,
                  'playback': 'flat', 'balance': None,
                  'source_sha256': {name: sha256(data).hexdigest() for name, data in source.items()},
                  'drive_sha256': {name: sha256(data).hexdigest() for name, data in drives.items()},
                  'config': clean_config}
        staging = self.root / ('.' + key)
        try:
            (staging / 'runs').mkdir(parents=True)
            for name, data in source.items():
                (staging / f'field-{name}.png').write_bytes(data)
            for name, data in drives.items():
                (staging / f'drive-{name}.png').write_bytes(data)
            write_json(staging / 'booth.json', record)
            staging.rename(self.directory(key))
        finally:
            if staging.exists():
                rmtree(staging)
        return record

    def fields(self, key):
        folder = self.directory(key)
        self.record(key)
        return {name: raster.read(folder / f'field-{name}.png') for name in setup.PROJECTORS}

    def drives(self, key):
        folder = self.directory(key)
        self.record(key)
        return {name: raster.read(folder / f'drive-{name}.png') for name in setup.PROJECTORS}

    def current(self, key, revision):
        record = self.record(key)
        if integer(revision, '版次', 1) != record['revision']:
            raise Conflict('校样设置已变化，请重新打开该项目。')
        return record

    def _write_drives(self, folder, record, drives):
        encoded = {name: raster.png(drives[name]) for name in setup.PROJECTORS}
        for name, data in encoded.items():
            (folder / f'drive-{name}.png').write_bytes(data)
        record['drive_sha256'] = {name: sha256(data).hexdigest()
                                  for name, data in encoded.items()}

    def apply(self, key, value):
        with self.lock:
            record = self.current(key, value.get('revision'))
            config = setup.settings(value.get('config'), record['size'])
            record['config'] = config
            # Manual settings describe flat playback; any prior per-pixel
            # suggestion is superseded by the new flat manual drives.
            drives = {name: drive_image(config, record['size'], name)
                      for name in setup.PROJECTORS}
            self._write_drives(self.directory(key), record, drives)
            record['playback'] = 'flat'
            record['balance'] = None
            record['revision'] += 1
            write_json(self.directory(key) / 'booth.json', record)
            return record

    def balance(self, key, value):
        with self.lock:
            record = self.current(key, value.get('revision'))
            config = record['config']
            current = self.drives(key)
            fields = self.fields(key)
            drives, summary = balance.suggest(fields, config, record['size'], current=current)
            self._write_drives(self.directory(key), record, drives)
            record['playback'] = 'balanced'
            record['balance'] = summary
            record['revision'] += 1
            write_json(self.directory(key) / 'booth.json', record)
            return record

    def runs(self, key):
        self.record(key)
        records = [read_json(path) for path in (self.directory(key) / 'runs').glob('[a-f0-9]*/run.json')]
        return sorted(records, key=lambda run: (run['created'], run['id']), reverse=True)

    def save(self, key, revision):
        with self.lock:
            record = self.current(key, revision)
            run = {'id': uuid4().hex, 'revision': record['revision'], 'created': timestamp(), 'name': record['name']}
            folder = self.directory(key)
            staging = folder / 'runs' / ('.' + run['id'])
            staging.mkdir()
            try:
                contents = delivery.archive(self.fields(key), self.drives(key), record, run)
                run['sha256'] = sha256(contents).hexdigest()
                (staging / 'proof.zip').write_bytes(contents)
                write_json(staging / 'run.json', run)
                staging.rename(folder / 'runs' / run['id'])
            finally:
                if staging.exists():
                    rmtree(staging)
            return run

    def package(self, key, run):
        folder = self.directory(key) / 'runs' / identifier(run)
        return folder / 'proof.zip', read_json(folder / 'run.json')
