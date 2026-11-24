"""Expose the projector console and its photo preparation workspace."""

from io import BytesIO
from pathlib import Path

from flask import Blueprint, jsonify, render_template, request, send_file

from image_lab import create_app as preparation_app
from image_lab.validation import Invalid, object_value

from . import console, demo, photometry, raster
from .setup import PROJECTORS
from .storage import Booths

VIEWS = {'a', 'b', 'mix', 'difference'}


def body():
    return object_value(request.get_json(silent=True), '校样操作')


def image_response(pixels, filename=None):
    return send_file(BytesIO(raster.png(pixels)), mimetype='image/png', max_age=0,
                     download_name=filename, as_attachment=filename is not None)


def create_app(root):
    app = preparation_app(root / 'prepare')
    library = Booths(root)
    api = Blueprint('booth', __name__, url_prefix='/booth')

    @app.get('/')
    def home():
        return render_template('booth.html')

    @api.get('/health')
    def health():
        return jsonify(status='ready', service='projection-booth')

    @api.route('/projects', methods=['GET', 'POST'])
    def projects():
        if request.method == 'GET':
            return jsonify(library.list())
        fields, names = {}, {}
        for key in PROJECTORS:
            item = request.files.get(key)
            if item is None or not item.filename:
                raise Invalid('请选择 A、B 两张已经对齐的灰度白场。')
            names[key] = Path(item.filename).name[:120]
            fields[key] = raster.decode(item.stream.read(raster.MAX_BYTES + 1))
        return jsonify(library.add(request.form.get('name') or '双机白场校样', fields, names)), 201

    @api.post('/demo')
    def practice():
        fields, config = demo.example()
        names = {key: f'synthetic-field-{key}.png' for key in PROJECTORS}
        return jsonify(library.add('展厅中央幕 · 合成练习', fields, names, config)), 201

    @api.route('/projects/<key>', methods=['GET', 'PATCH'])
    def item(key):
        if request.method == 'PATCH':
            return jsonify(library.apply(key, body()))
        return jsonify(library.record(key))

    @api.get('/projects/<key>/view/<kind>.png')
    def image(key, kind):
        if kind not in VIEWS:
            raise Invalid('没有这个图像视图。')
        record = library.record(key)
        pixels = photometry.view(library.fields(key), record['config'], kind)
        return image_response(pixels, f'{kind}.png' if request.args.get('download') else None)

    @api.get('/projects/<key>/drive/<projector>.png')
    def drive(key, projector):
        if projector not in PROJECTORS:
            raise Invalid('请选择 A 机或 B 机。')
        record = library.record(key)
        pixels = console.drive_image(record['config'], record['size'], projector)
        return image_response(pixels, f'drive-{projector}.png' if request.args.get('download') else None)

    @api.get('/projects/<key>/statistics')
    def statistics(key):
        record = library.record(key)
        return jsonify(photometry.statistics(library.fields(key), record['config']))

    @api.get('/projects/<key>/point')
    def point(key):
        record = library.record(key)
        return jsonify(console.point(library.fields(key), record['config'], record['size'],
                                     request.args.get('x', type=int), request.args.get('y', type=int)))

    @api.route('/projects/<key>/runs', methods=['GET', 'POST'])
    def runs(key):
        if request.method == 'GET':
            return jsonify(library.runs(key))
        return jsonify(library.save(key, body().get('revision'))), 201

    @api.get('/projects/<key>/runs/<run>/proof.zip')
    def proof(key, run):
        path, record = library.package(key, run)
        return send_file(path, mimetype='application/zip', as_attachment=True, max_age=0,
                         download_name=f"projector-proof-{record['revision']}-{run[:8]}.zip")

    @api.post('/projects/<key>/prepare')
    def prepare(key):
        record = library.record(key)
        pixels = photometry.view(library.fields(key), record['config'], 'mix')
        name = record['name'] + ' · 合光'
        tags = dict(booth_source_sha256=record['source_sha256'], booth_revision=record['revision'])
        asset = app.extensions['assets'].put(pixels.astype('float32') / 255, name, tags)
        project = app.extensions['store'].create(name)
        result = app.extensions['frames'].add(project['id'], project['revision'], [asset['id']])
        return jsonify(url=f"/prepare?project={result['project']['id']}"), 201

    app.register_blueprint(api)
    return app
