const get = (id) => document.getElementById(id);
const state = { project: null, view: 'mix', point: null, busy: false };
const content = {
  mix: '按两台机当前输出预览相对亮度和暖冷变化。',
  difference: '从目标偏暗的地方显橙色，偏亮的地方显蓝色。',
  a: 'A 机满驱白场。零代表 A 机没有有效覆盖。',
  b: 'B 机满驱白场。零代表 B 机没有有效覆盖。',
  'drive-a': '送给 A 机的驱动图。白色对应满驱，匀亮后选区内为逐像素灰阶。',
  'drive-b': '送给 B 机的驱动图。白色对应满驱，匀亮后选区内为逐像素灰阶。',
};

async function request(url, method = 'GET', data) {
  const options = { method };
  if (data instanceof FormData) {
    options.body = data;
  } else if (data !== undefined) {
    options.headers = { 'Content-Type': 'application/json' };
    options.body = JSON.stringify(data);
  }
  const response = await fetch(url, options);
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.error || '校样请求失败。');
  }
  return response.json();
}

function notify(message, error = false) {
  const element = get('message');
  element.textContent = message;
  element.hidden = !message;
  element.classList.toggle('error', error);
}

async function busy(button, action) {
  if (state.busy) return;
  state.busy = true;
  button.disabled = true;
  notify('');
  try {
    await action();
  } catch (error) {
    notify(error.message, true);
  } finally {
    state.busy = false;
    button.disabled = false;
  }
}

function base(project = state.project) {
  return '/booth/projects/' + project.id;
}

function imagePath(view) {
  const tail = view.startsWith('drive-') ? 'drive/' + view.slice(6) : 'view/' + view;
  return base() + '/' + tail + '.png';
}

function linkFor(url) {
  return url + '?revision=' + state.project.revision + '&download=1';
}

function formFields(project) {
  const { config, size } = project;
  const form = get('setup').elements;
  for (const key of ['a', 'b']) {
    const fixture = config[key];
    form[key + 'Drive'].value = fixture.drive;
    form[key + 'Limit'].value = fixture.limit;
    form[key + 'Cast'].value = fixture.cast;
  }
  ['left', 'top', 'right', 'bottom'].forEach((name, index) => {
    form[name].value = config.area[index];
    form[name].max = size[index % 2];
  });
  form.target.value = config.target;
  get('probeX').max = size[0] - 1;
  get('probeY').max = size[1] - 1;
}

function readForm() {
  const fields = get('setup').elements;
  const number = (name) => fields[name].valueAsNumber;
  const projector = (key) => ({
    drive: number(key + 'Drive'),
    limit: number(key + 'Limit'),
    cast: number(key + 'Cast'),
  });
  return { a: projector('a'), b: projector('b'), target: number('target'),
    area: ['left', 'top', 'right', 'bottom'].map(number) };
}

function renderView() {
  const url = imagePath(state.view);
  const project = state.project;
  get('preview').src = url + '?revision=' + project.revision;
  get('downloadView').href = linkFor(url);
  get('downloadA').href = linkFor(imagePath('drive-a'));
  get('downloadB').href = linkFor(imagePath('drive-b'));
  get('viewHint').textContent = content[state.view];
  get('tabs').querySelectorAll('button').forEach((button) => {
    button.setAttribute('aria-pressed', button.dataset.view === state.view);
  });
  const [width, height] = project.size;
  const [left, top, right, bottom] = project.config.area;
  const roi = get('roi');
  roi.style.left = (100 * left / width) + '%';
  roi.style.top = (100 * top / height) + '%';
  roi.style.width = (100 * (right - left) / width) + '%';
  roi.style.height = (100 * (bottom - top) / height) + '%';
}

async function library() {
  const projects = await request('/booth/projects');
  const selector = get('projects');
  selector.replaceChildren(new Option('选择一组白场', ''));
  for (const item of projects) selector.add(new Option(item.name, item.id));
  selector.value = state.project ? state.project.id : '';
}

async function metrics(project) {
  const values = await request(base(project) + '/statistics');
  if (state.project !== project) return;
  const labels = ['双机覆盖 ' + values.overlap + ' px', '单机覆盖 ' + values.single + ' px', '无覆盖 ' + values.dark + ' px'];
  if (values.overlap > 0) {
    labels.push('双机平均亮度 ' + values.mean, '范围 ' + values.minimum + '–' + values.maximum,
      '低于目标 ' + values.below + ' px', '平均暖冷偏移 ' + values.mean_cast);
  }
  get('metrics').replaceChildren(...labels.map((label) => {
    const item = document.createElement('span');
    item.textContent = label;
    return item;
  }));
}

async function runs(project) {
  const values = await request(base(project) + '/runs');
  if (state.project !== project) return;
  get('runs').replaceChildren(...values.map((run) => {
    const item = document.createElement('li');
    const link = document.createElement('a');
    link.textContent = '下载校样 ZIP · 第 ' + run.revision + ' 版 · ' + run.id.slice(0, 6);
    link.href = base(project) + '/runs/' + run.id + '/proof.zip';
    link.download = '';
    item.append(link);
    return item;
  }));
}

function resetPoint() {
  state.point = null;
  get('marker').hidden = true;
  get('pointInfo').textContent = '点击幕面，或输入原像素坐标。';
}

function renderBalance(project) {
  const box = get('balanceSummary');
  const summary = project.balance;
  if (project.playback !== 'balanced' || !summary) {
    box.hidden = true;
    box.replaceChildren();
    return;
  }
  const lines = [
    '匀亮版本 · 目标 ' + summary.target,
    '双机覆盖 ' + summary.overlap + ' px · 已重算 ' + summary.adjusted + ' px',
  ];
  if (summary.shortfall > 0) {
    lines.push('达不到目标 ' + summary.shortfall + ' px（能力不足 ' +
      (summary.capacity_shortfall || 0) + ' · 整数灰阶够不着 ' +
      (summary.quantization_shortfall || 0) + '）· 容差 ±' + summary.tolerance);
    if ((summary.capacity_shortfall || 0) > 0) {
      lines.push('最大能力缺口 ' + summary.max_deficit + '（两台均已开到本机最高灰阶）');
    }
  } else {
    lines.push('全部落在目标 ±' + summary.tolerance + ' 内');
  }
  box.replaceChildren(...lines.map((line) => {
    const item = document.createElement('span');
    item.textContent = line;
    return item;
  }));
  box.hidden = false;
}

async function show(project, switched) {
  state.project = project;
  if (switched) {
    state.view = 'mix';
    resetPoint();
  }
  get('workbench').hidden = false;
  get('empty').hidden = true;
  get('library').open = false;
  get('projectName').textContent = project.name;
  const mode = project.playback === 'balanced' ? '逐像素匀亮' : '平面手动';
  get('screenSize').textContent = project.size.join(' × ') + ' px · 第 ' + project.revision +
    ' 版 · ' + mode;
  formFields(project);
  renderBalance(project);
  renderView();
  const url = new URL(window.location.href);
  url.searchParams.set('project', project.id);
  history.replaceState({}, '', url);
  await Promise.all([metrics(project), runs(project)]);
  if (state.point) await inspect(state.point[0], state.point[1]);
}

async function inspect(x, y) {
  const project = state.project;
  const point = await request(base(project) + '/point?x=' + x + '&y=' + y);
  if (state.project !== project) return;
  const [width, height] = project.size;
  state.point = [x, y];
  get('probeX').value = point.x;
  get('probeY').value = point.y;
  get('marker').style.left = (100 * (x + .5) / width) + '%';
  get('marker').style.top = (100 * (y + .5) / height) + '%';
  get('marker').hidden = false;
  const heading = document.createElement('b');
  heading.textContent = '(' + point.x + ', ' + point.y + ') · ' + (point.selected ? '选区内' : '选区外') +
    (point.shortfall ? ' · 达不到目标（已开双机上限）' : '');
  const gap = point.total - point.target;
  const gapText = Math.abs(gap) <= 0.5 ? '达标' :
    (gap < 0 ? '偏暗 ' : '偏亮 ') + Math.abs(gap).toFixed(3);
  const values = ['实测叠加 ' + point.total + ' / 目标 ' + point.target +
    ' · ' + gapText + ' · 暖冷偏移 ' + point.cast];
  for (const key of ['a', 'b']) {
    const sample = point.projectors[key];
    values.push(key.toUpperCase() + ' 机 · 白场 ' + sample.field + ' · 灰阶 ' + sample.grey +
      '（驱动 ' + sample.drive + '% / 上限 ' + sample.limit + '%，最高灰阶 ' +
      sample.max_grey + '）· 亮度贡献 ' + sample.contribution);
  }
  const rows = values.map((line) => {
    const item = document.createElement('div');
    item.textContent = line;
    return item;
  });
  get('pointInfo').replaceChildren(heading, ...rows);
}

get('demo').addEventListener('click', () => busy(get('demo'), async () => {
  await show(await request('/booth/demo', 'POST'), true);
  await library();
}));

get('upload').addEventListener('submit', (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  busy(form.querySelector('button'), async () => {
    await show(await request('/booth/projects', 'POST', new FormData(form)), true);
    form.reset();
    await library();
  });
});

get('projects').addEventListener('change', (event) => {
  const select = event.currentTarget;
  if (select.value) busy(select, async () => {
    await show(await request('/booth/projects/' + select.value), true);
  });
});

get('setup').addEventListener('submit', (event) => {
  event.preventDefault();
  busy(get('apply'), async () => {
    const project = await request(base(), 'PATCH', {
      revision: state.project.revision,
      config: readForm(),
    });
    await show(project, false);
    notify('试放设置已应用，驱动图回到平面手动灰阶。');
  });
});

get('balance').addEventListener('click', () => busy(get('balance'), async () => {
  const project = await request(base() + '/balance', 'POST', {
    revision: state.project.revision,
  });
  await show(project, false);
  const summary = project.balance;
  notify(summary.shortfall > 0
    ? '匀亮建议已采用：' + summary.shortfall + ' 个双机像素开到上限仍达不到目标，点测可查看缺口与各自贡献。'
    : '匀亮建议已采用，选区内双机像素叠加亮度均落在目标 ±' + summary.tolerance + ' 内。');
}));

get('tabs').addEventListener('click', (event) => {
  const button = event.target.closest('[data-view]');
  if (!button || !state.project) return;
  state.view = button.dataset.view;
  renderView();
});

get('preview').addEventListener('click', (event) => {
  const box = get('preview').getBoundingClientRect();
  if (!(box.width && box.height)) return;
  const [width, height] = state.project.size;
  const x = Math.min(width - 1, Math.floor((event.clientX - box.left) / box.width * width));
  const y = Math.min(height - 1, Math.floor((event.clientY - box.top) / box.height * height));
  inspect(x, y).catch((error) => notify(error.message, true));
});

get('probeForm').addEventListener('submit', (event) => {
  event.preventDefault();
  inspect(get('probeX').valueAsNumber, get('probeY').valueAsNumber).catch((error) => notify(error.message, true));
});

get('save').addEventListener('click', () => busy(get('save'), async () => {
  await request(base() + '/runs', 'POST', { revision: state.project.revision });
  await runs(state.project);
  notify('校样已保存，可下载 ZIP。');
}));

get('prepare').addEventListener('click', () => busy(get('prepare'), async () => {
  const result = await request(base() + '/prepare', 'POST');
  window.location.assign(result.url);
}));

(async () => {
  await library();
  const key = new URL(window.location.href).searchParams.get('project');
  if (!key) return;
  await show(await request('/booth/projects/' + key), true);
  get('projects').value = key;
})().catch((error) => notify(error.message, true));
