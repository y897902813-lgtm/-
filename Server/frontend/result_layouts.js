/* V2.16.9.1 - coordinate-layout UI and automatic draft persistence.
   The default distance layout is a reserved, non-deletable view derived from
   ProjectSpec.distance_pairs. No extra ProjectSpec field or API is introduced. */
function resultDistanceLayoutActive() {
  const layout = state.project?.result_layout;
  return (layout?.axes || []).some((axis, axisIndex) =>
    (axis.curves || []).some((curve, curveIndex) => {
      const source = typeof effectiveResultCurveSource === 'function'
        ? effectiveResultCurveSource(axis, curve, axisIndex, curveIndex)
        : String(curve?.source || '');
      return source.startsWith('pair:');
    }));
}

function resultLayoutHasWorkingChanges(layout = state.project?.result_layout) {
  if (!layout) return false;
  if (layout.active_preset_id === '__distance__') return false;
  const preset = (layout.presets || []).find(item => item.id === layout.active_preset_id);
  return preset
    ? JSON.stringify(layout.axes || []) !== JSON.stringify(preset.axes || [])
    : Boolean((layout.axes || []).length);
}

function nextResultLayoutName(presets, stem = '自定义布局') {
  const names = new Set(presets.map(item => item.name));
  for (let number = 1; number <= 51; number++) {
    const name = `${stem} ${number}`;
    if (!names.has(name)) return name;
  }
  return `${stem}（新）`;
}

function defaultDistanceAxes(previousAxes = []) {
  // Pair ID, not the display name, is the identity. Retain color/axis ID on
  // rename or reordering, but never retain deleted or duplicate pair sources.
  const oldAxes = new Map();
  (previousAxes || []).forEach(axis => {
    (axis.curves || []).forEach(curve => {
      if (String(curve.source || '').startsWith('pair:') && !oldAxes.has(curve.source))
        oldAxes.set(curve.source, {axis,curve});
    });
  });
  const seen = new Set();
  return (state.project?.distance_pairs || []).filter(pair => {
    const id = String(pair?.id || '');
    if (!id || seen.has(id)) return false;
    seen.add(id); return true;
  }).map((pair, index) => {
    const source = `pair:${pair.id}`, old = oldAxes.get(source);
    const name = String(pair.name || `测距对${index + 1}`);
    return {
      id:old?.axis.id || uid('axis'), name,
      combine:'none', keep_operands:false, add_to_gantt:false,
      curves:[{id:old?.curve.id || uid('curve'), source, label:name,
        operation:'raw', color:old?.curve.color || '#018c94'}],
    };
  });
}

function ensureDefaultDistancePreset(layout) {
  const presets = layout.presets ||= [];
  const existing = presets.find(item => item.id === '__distance__');
  if (existing) {
    if (canEditProject()) { existing.name = '测距对布局'; existing.kind = 'distance'; }
    return existing;
  }
  // Legacy 50-preset projects still have the permanent VIRTUAL default entry.
  // Do not evict a user's custom archive or exceed ResultLayout.presets <= 50.
  if (!canEditProject() || presets.length >= 50) return null;
  const preset = {id:'__distance__', name:'测距对布局', kind:'distance', axes:[]};
  presets.unshift(preset);
  return preset;
}

function reconcileActiveDistanceLayout({force = false} = {}) {
  const layout = state.project?.result_layout;
  if (!layout || layout.active_preset_id !== '__distance__') return false;
  const projectId = state.project.id;
  const signature = JSON.stringify((state.project.distance_pairs || []).map(pair => [pair.id, pair.name]));
  const last = state.resultDistanceLayoutVisit;
  if (!force && last?.projectId === projectId && last.projectObject === state.project &&
      last.signature === signature) return false;
  const hadPreset = (layout.presets || []).some(item => item.id === '__distance__');
  const preset = ensureDefaultDistancePreset(layout);
  const previous = !force && last?.projectId !== projectId && preset?.axes?.length
    ? preset.axes : layout.axes;
  const axes = defaultDistanceAxes(previous || []);
  const changed = JSON.stringify(layout.axes || []) !== JSON.stringify(axes);
  if (changed) layout.axes = axes;
  const presetChanged = Boolean(preset && canEditProject() &&
    JSON.stringify(preset.axes || []) !== JSON.stringify(axes));
  if (presetChanged) preset.axes = deepClone(axes);
  state.resultDistanceLayoutVisit = {projectId, projectObject:state.project, signature};
  if ((changed || presetChanged || (!hadPreset && preset)) && canEditProject()) {
    markDirty(); scheduleInteractionCommit();
  }
  return changed;
}

function snapshotActiveResultLayout() {
  const layout = state.project?.result_layout;
  if (!layout || !canEditProject()) return false;
  const preset = (layout.presets || []).find(item => item.id === layout.active_preset_id);
  if (!preset) return false;
  if (JSON.stringify(preset.axes || []) === JSON.stringify(layout.axes || [])) return false;
  preset.axes = deepClone(layout.axes || []);
  // The originating editor already marks the project dirty. This routine also
  // runs immediately before Enter to ensure the snapshot belongs to that commit.
  return true;
}

function archiveUnnamedResultLayout({reserveSlots = 0} = {}) {
  const layout = state.project?.result_layout;
  if (!layout || layout.active_preset_id || !(layout.axes || []).length || !canEditProject()) return true;
  const presets = layout.presets ||= [];
  if (presets.length + reserveSlots >= 50) {
    toast('布局最多 50 个，请删除旧布局后再切换，以免丢失当前坐标系', 'error');
    return false;
  }
  const preset = {id:uid('layout'), name:nextResultLayoutName(presets, '原有布局'),
    kind:'custom', axes:deepClone(layout.axes)};
  presets.push(preset);
  layout.active_preset_id = preset.id;
  return true;
}

function renderResultLayoutControls() {
  const select = $('#resultLayoutSelect'), layout = state.project?.result_layout;
  if (!select || !layout) return;
  const presets = layout.presets || [];
  const active = layout.active_preset_id;
  select.innerHTML = (!active ? '<option value="">当前布局</option>' : '') +
    '<option value="__distance__">测距对布局（自动同步）</option>' +
    presets.filter(item => item.id !== '__distance__').map(item =>
      `<option value="${esc(item.id)}">${esc(item.name)}</option>`).join('');
  select.value = active && (active === '__distance__' || presets.some(item => item.id === active)) ? active : '';
  const editable = canEditProject();
  const create = $('#newResultLayoutButton');
  if (create) create.disabled = !editable || presets.length >= 50;
  const remove = $('#deleteResultLayoutButton');
  if (remove) remove.disabled = !editable || !presets.some(item => item.id === active && item.id !== '__distance__');
  const rename = $('#renameResultLayoutButton');
  if (rename) {
    const unnamed = !active;
    rename.disabled = !editable || active === '__distance__' ||
      (!unnamed && !presets.some(item => item.id === active));
    rename.textContent = unnamed ? '自定义布局名称' : '✎ 名称';
    rename.title = unnamed ? '将当前坐标系保存为命名布局' : '重命名当前布局';
    rename.setAttribute?.('aria-label', rename.title);
  }
  const importer = $('#importResultLayoutButton');
  if (importer) importer.disabled = !editable || !state.project?.id;
}

function switchResultLayout(id) {
  const layout = state.project?.result_layout;
  if (!layout || !id) { renderResultLayoutControls(); return false; }
  const presets = layout.presets ||= [];
  let target = presets.find(item => item.id === id);
  if (id !== '__distance__' && !target) { renderResultLayoutControls(); return false; }
  if (id !== '__distance__' && id === layout.active_preset_id) {
    renderResultLayoutControls(); return true;
  }
  if (canEditProject()) {
    snapshotActiveResultLayout();
    if (!archiveUnnamedResultLayout()) {
      renderResultLayoutControls(); return false;
    }
  }
  if (id === '__distance__') {
    target = ensureDefaultDistancePreset(layout);
    // Force a fresh match EVERY entry, even when selecting the already-active
    // default: changed pair names, order and deletions all take effect.
    const oldAxes = layout.active_preset_id === '__distance__' ? layout.axes : (target?.axes || []);
    layout.axes = defaultDistanceAxes(oldAxes);
    state.resultDistanceLayoutVisit = {
      projectId:state.project.id, projectObject:state.project,
      signature:JSON.stringify((state.project.distance_pairs || []).map(pair => [pair.id,pair.name])),
    };
    if (target && canEditProject()) target.axes = deepClone(layout.axes);
  } else {
    layout.axes = deepClone(target.axes || []);
  }
  layout.active_preset_id = id;
  state.resultViewerCurveOverrides = {projectId:state.project.id, sources:{}};
  if (canEditProject()) { markDirty(); scheduleInteractionCommit(); }
  renderResultViewer(); refreshCombinedGanttSchedule();
  if (resultDistanceLayoutActive()) requestSelectedDistanceCurves();
  return true;
}

function newResultLayout() {
  if (!state.project || !canEditProject()) return false;
  const layout = state.project.result_layout, presets = layout.presets ||= [];
  const slots = presets.length + (!layout.active_preset_id && (layout.axes || []).length ? 1 : 0);
  if (slots >= 50) { toast('最多创建 50 个布局', 'error'); return false; }
  const suggestion = nextResultLayoutName(presets);
  const input = prompt('新布局名称（后续修改自动保存，按 Enter 同步当前模型）：', suggestion);
  if (input === null) { renderResultLayoutControls(); return false; }
  const name = input.trim();
  if (!name || name.length > 128) { toast('布局名称须为 1~128 个字符', 'error'); return false; }
  if (name === '测距对布局' || presets.some(item => item.name === name)) {
    toast('布局名称已存在，请换一个名称', 'error'); return false;
  }
  snapshotActiveResultLayout();
  if (!archiveUnnamedResultLayout({reserveSlots:1})) { renderResultLayoutControls(); return false; }
  const preset = {id:uid('layout'), name, kind:'custom', axes:[]};
  presets.push(preset);
  layout.axes = [];
  layout.active_preset_id = preset.id;
  state.resultViewerCurveOverrides = {projectId:state.project.id, sources:{}};
  markDirty(); scheduleInteractionCommit(); renderResultViewer(); refreshCombinedGanttSchedule();
  toast('新布局已创建。坐标系修改会自动保存到当前模型，按 Enter 同步', 'success');
  return true;
}

function renameResultLayout() {
  const layout = state.project?.result_layout;
  if (!layout || !canEditProject()) return false;
  const presets = layout.presets ||= [];
  const preset = presets.find(item => item.id === layout.active_preset_id && item.id !== '__distance__');
  if (!preset && layout.active_preset_id) return false; // Never rename the reserved default.
  if (!preset && presets.length >= 50) {
    toast('已达到 50 个命名布局上限，请先删除旧布局', 'error'); return false;
  }
  const input = prompt(preset ? '重命名当前布局：' : '保存当前布局，输入自定义布局名称：',
    preset?.name || nextResultLayoutName(presets));
  if (input === null) return false;
  const name = input.trim();
  if (!name || name.length > 128 || name === '测距对布局' ||
      presets.some(item => item !== preset && item.name === name)) {
    toast('请输入不重复且长度不超过 128 字符的布局名称', 'error'); return false;
  }
  if (preset) {
    preset.name = name;
  } else {
    // A user-facing save, not an empty layout: preserve every visible axis.
    const created = {id:uid('layout'), name, kind:'custom', axes:deepClone(layout.axes || [])};
    presets.push(created);
    layout.active_preset_id = created.id;
  }
  markDirty(); scheduleInteractionCommit(); renderResultLayoutControls();
  return true;
}

function deleteResultLayout() {
  if (!state.project || !canEditProject()) return false;
  const layout = state.project.result_layout;
  const preset = layout.presets?.find(item => item.id === layout.active_preset_id && item.id !== '__distance__');
  if (!preset || !confirm(`删除布局“${preset.name}”？此布局中的坐标系也会移除。`)) return false;
  layout.presets = layout.presets.filter(item => item !== preset);
  layout.active_preset_id = '';
  layout.axes = [];
  // The default distance entry is permanent; deleting another layout returns
  // to it instead of leaving an orphaned unsaved working copy.
  return switchResultLayout('__distance__');
}

function moveResultAxis(sourceId, targetId, before = true) {
  if (!canEditProject()) return false;
  const axes = state.project?.result_layout?.axes;
  const source = axes?.findIndex(axis => axis.id === sourceId);
  if (source == null || source < 0 || sourceId === targetId || !axes.some(axis => axis.id === targetId)) return false;
  const [axis] = axes.splice(source, 1);
  const target = axes.findIndex(item => item.id === targetId);
  axes.splice(target + (before ? 0 : 1), 0, axis);
  markDirty(); scheduleInteractionCommit(); renderResultViewer(); refreshCombinedGanttSchedule();
  return true;
}

// V2.16.11.3: import a named layout from another model in the same Hub
// project root. Catalog scope + source GET ACL; source remains read-only.
let resultLayoutImportRevision = 0;
let resultLayoutImportSource = null;
let resultLayoutImportPeerIds = new Set();
function layoutProjectFolder(project) { return String(project?.category || 'None'); }
function layoutCurveCatalog(project) {
  const result = new Map();
  const register = (group, id, name) => {
    if (id) result.set(`${group}:${id}`, String(name || id));
  };
  (project?.drives || []).forEach(item => register('drive',item.id,item.name));
  (project?.distance_pairs || []).forEach(item => register('pair',item.id,item.name));
  (project?.layers || []).forEach(layer => (layer.joints || []).forEach(item =>
    register('joint',item.id,`${layer.name || ''} / ${item.name || ''}`)));
  return result;
}
function mapImportedLayoutAxes(sourceProject, sourceAxes, targetProject) {
  const oldCatalog = layoutCurveCatalog(sourceProject);
  const newCatalog = layoutCurveCatalog(targetProject);
  const uniqueByName = new Map();
  for (const [key, name] of newCatalog) {
    const kind = key.split(':')[0], identity = `${kind}:${name}`;
    if (!uniqueByName.has(identity)) uniqueByName.set(identity, []);
    uniqueByName.get(identity).push(key);
  }
  let unmatched = 0, matched = 0;
  const axes = (sourceAxes || []).map(axis => ({
    id:uid('axis'), name:String(axis.name || '坐标系'),
    combine:['sum','difference'].includes(axis.combine) ? axis.combine : 'none',
    keep_operands:Boolean(axis.keep_operands), add_to_gantt:Boolean(axis.add_to_gantt),
    curves:(axis.curves || []).map(curve => {
      const key = canonicalResultCurveSource(curve.source);
      let mapped = '';
      if (key && oldCatalog.has(key)) {
        const sourceName = oldCatalog.get(key);
        // Matching raw IDs are safe only when the human-readable identity also
        // matches. A unique matching name is the cross-model fallback.
        if (newCatalog.get(key) === sourceName) mapped = key;
        else {
          const candidates = uniqueByName.get(`${key.split(':')[0]}:${sourceName}`) || [];
          if (candidates.length === 1) mapped = candidates[0];
        }
        if (mapped) matched++; else unmatched++;
      } else if (key) {
        unmatched++;
      }
      return {id:uid('curve'), source:mapped, label:String(curve.label || ''),
        operation:['raw','integral','d1','d2','d3','sum'].includes(curve.operation) ? curve.operation : 'raw',
        color:/^#[\da-fA-F]{6}$/.test(curve.color || '') ? curve.color : '#2563eb'};
    }),
  }));
  return {axes, matched, unmatched};
}
function layoutImportPresets(project) {
  const layout = project?.result_layout || {};
  const presets = (layout.presets || []).filter(item => item && Array.isArray(item.axes));
  const items = presets.map(item => ({id:item.id, name:item.name, axes:item.id === layout.active_preset_id
    ? (layout.axes || item.axes) : item.axes}));
  if (!layout.active_preset_id && (layout.axes || []).length)
    items.unshift({id:'__current__', name:'当前布局（未命名）', axes:layout.axes});
  if (layout.active_preset_id === '__distance__' && !items.some(item => item.id === '__distance__'))
    items.unshift({id:'__distance__', name:'测距对布局', axes:layout.axes || []});
  return items;
}
async function loadImportLayoutSource(sourceId) {
  const dialog = $('#resultLayoutImportDialog'), select = $('#resultLayoutImportPreset');
  const info = $('#resultLayoutImportInfo');
  if (!dialog?.open || !select || !info || !sourceId) return;
  const revision = ++resultLayoutImportRevision, targetId = state.project?.id;
  resultLayoutImportSource = null;
  select.innerHTML = '<option value="">正在读取布局…</option>';
  info.textContent = '读取授权模型的布局快照中…';
  try {
    const project = await api(`/api/projects/${encodeURIComponent(sourceId)}`);
    if (revision !== resultLayoutImportRevision || !dialog.open || state.project?.id !== targetId ||
        $('#resultLayoutImportProject')?.value !== sourceId) return;
    if (project?.id === targetId || !resultLayoutImportPeerIds.has(project.id))
      throw new Error('布局来源不在当前项目目录的已授权模型清单中');
    const items = layoutImportPresets(project);
    resultLayoutImportSource = {project, items};
    select.innerHTML = '<option value="">请选择布局</option>' + items.map((item,index) =>
      `<option value="${index}">${esc(item.name || '未命名布局')} · ${item.axes.length} 个坐标系</option>`).join('');
    info.textContent = items.length ? '只复制布局及颜色；跨模型曲线来源会按名称唯一匹配，无法匹配的曲线保持未选择。' : '此模型还没有可导入的布局。';
  } catch (error) {
    if (revision === resultLayoutImportRevision) {
      select.innerHTML = '<option value="">无法加载</option>';
      info.textContent = `读取失败：${error.message}`;
    }
  }
}
async function openResultLayoutImportDialog() {
  if (!state.project || !canEditProject()) return toast('请先签出目标模型再导入布局', 'error');
  const dialog = $('#resultLayoutImportDialog'), selector = $('#resultLayoutImportProject');
  if (!dialog || !selector) return;
  const targetId = state.project.id, folder = layoutProjectFolder(state.project);
  resultLayoutImportSource = null;
  resultLayoutImportPeerIds = new Set();
  dialog.showModal();
  selector.innerHTML = '<option value="">正在读取项目模型…</option>';
  $('#resultLayoutImportPreset').innerHTML = '<option value="">先选择模型</option>';
  $('#resultLayoutImportInfo').textContent = '选择同一 Hub 项目根目录下的其他模型，可跨模型类型文件夹。';
  const revision = ++resultLayoutImportRevision;
  try {
    const summaries = await api('/api/projects?detail=summary', {timeout:12000});
    if (!dialog.open || revision !== resultLayoutImportRevision || state.project?.id !== targetId) return;
    const peers = (Array.isArray(summaries) ? summaries : []).filter(item => item.id && item.id !== targetId);
    peers.sort((a,b) => layoutProjectFolder(a).localeCompare(layoutProjectFolder(b),'zh-CN') ||
      String(a.name || '').localeCompare(String(b.name || ''),'zh-CN'));
    resultLayoutImportPeerIds = new Set(peers.map(item => item.id));
    selector.innerHTML = '<option value="">请选择来源模型</option>' + peers.map(item =>
      `<option value="${esc(item.id)}">${esc(layoutProjectFolder(item))} / ${esc(item.name || item.id)}</option>`).join('');
    if (!peers.length) $('#resultLayoutImportInfo').textContent = '项目目录中没有其他可读取的模型。';
  } catch (error) {
    if (revision === resultLayoutImportRevision)
      $('#resultLayoutImportInfo').textContent = `模型目录读取失败：${error.message}`;
  }
}
function confirmImportResultLayout() {
  const source = resultLayoutImportSource, selector = $('#resultLayoutImportPreset');
  const index = selector?.value === '' ? -1 : Number(selector?.value);
  const chosen = source?.items?.[index], layout = state.project?.result_layout;
  if (!chosen || !layout || !canEditProject() || !$('#resultLayoutImportDialog')?.open) return false;
  if (source.project.id !== $('#resultLayoutImportProject')?.value ||
      !resultLayoutImportPeerIds.has(source.project.id)) return false;
  const presets = layout.presets ||= [];
  const reserve = !layout.active_preset_id && (layout.axes || []).length ? 1 : 0;
  if (presets.length + reserve >= 50) { toast('布局最多 50 个，请先删除旧布局', 'error'); return false; }
  const imported = mapImportedLayoutAxes(source.project, chosen.axes, state.project);
  const sourceName = `${source.project.name || '模型'} · ${chosen.name || '布局'}`;
  const input = prompt('导入为新的自定义布局名称：', sourceName.slice(0,128));
  if (input === null) return false;
  const name = input.trim();
  if (!name || name.length > 128 || name === '测距对布局' || presets.some(item => item.name === name)) {
    toast('布局名称重复或长度不合法（1~128 字符）', 'error'); return false;
  }
  if (imported.unmatched && !confirm(`有 ${imported.unmatched} 条曲线无法与当前模型唯一匹配，导入后将保持“未选择”。\n已匹配 ${imported.matched} 条。继续吗？`)) return false;
  snapshotActiveResultLayout();
  if (!archiveUnnamedResultLayout({reserveSlots:1})) return false;
  const preset = {id:uid('layout'), name, kind:'custom', axes:deepClone(imported.axes)};
  presets.push(preset);
  layout.active_preset_id = preset.id;
  layout.axes = deepClone(imported.axes);
  state.resultViewerCurveOverrides = {projectId:state.project.id,sources:{}};
  markDirty(); scheduleInteractionCommit();
  $('#resultLayoutImportDialog')?.close();
  renderResultViewer(); refreshCombinedGanttSchedule();
  if (resultDistanceLayoutActive()) requestSelectedDistanceCurves();
  toast(`已导入 ${imported.axes.length} 个坐标系，匹配 ${imported.matched} 条曲线；按 Enter 可同步`, 'success');
  return true;
}

function bindResultLayoutControls() {
  $$('[data-axis-columns]').forEach(button => button.addEventListener('click', () => setResultAxisColumns(button.dataset.axisColumns)));
  $('#axisColumnToggle')?.addEventListener('click', () => setResultAxisColumns(resultAxisColumnCount() === 2 ? 1 : 2));
  $('#resultLayoutSelect')?.addEventListener('change', event => switchResultLayout(event.target.value));
  $('#renameResultLayoutButton')?.addEventListener('click', renameResultLayout);
  $('#importResultLayoutButton')?.addEventListener('click', openResultLayoutImportDialog);
  $('#resultLayoutImportProject')?.addEventListener('change', event => loadImportLayoutSource(event.target.value));
  $('#resultLayoutImportPreset')?.addEventListener('change', event => {
    const item = resultLayoutImportSource?.items?.[Number(event.target.value)];
    $('#resultLayoutImportInfo').textContent = item && event.target.value !== ''
      ? `将导入 ${item.axes.length} 个坐标系、${item.axes.reduce((n,axis) => n+(axis.curves||[]).length,0)} 条曲线；失效来源会留空。`
      : '请选择要导入的命名布局。';
  });
  $('#confirmResultLayoutImportButton')?.addEventListener('click', confirmImportResultLayout);
  $('#resultLayoutImportDialog')?.addEventListener('close', () => {
    ++resultLayoutImportRevision; resultLayoutImportSource = null;
    resultLayoutImportPeerIds = new Set();
  });
  $('#newResultLayoutButton')?.addEventListener('click', newResultLayout);
  $('#deleteResultLayoutButton')?.addEventListener('click', deleteResultLayout);
  const root = $('#resultAxes');
  if (root && typeof ResizeObserver === 'function') {
    let queued = false;
    new ResizeObserver(() => {
      if (queued || document.querySelector('[data-result-pane="axes"]')?.classList.contains('hidden')) return;
      queued = true;
      requestAnimationFrame(() => { queued = false; if (state.project) drawResultAxes(); });
    }).observe(root);
  }
  let dragId = '';
  const clear = () => root?.querySelectorAll('.axis-drop-before,.axis-drop-after').forEach(card => card.classList.remove('axis-drop-before','axis-drop-after'));
  root?.addEventListener('dragstart', event => {
    const handle = event.target.closest?.('[data-axis-drag]');
    if (!handle) return;
    if (!canEditProject()) { event.preventDefault(); return; }
    dragId = handle.dataset.axisDrag;
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('application/x-result-axis', dragId);
  });
  root?.addEventListener('dragover', event => {
    if (!dragId) return;
    const card = event.target.closest?.('[data-axis-card]');
    if (!card) return;
    event.preventDefault(); clear();
    if (card.dataset.axisCard === dragId) return;
    const rect = card.getBoundingClientRect();
    card.classList.add(event.clientY < rect.top + rect.height / 2 ? 'axis-drop-before' : 'axis-drop-after');
  });
  root?.addEventListener('drop', event => {
    const card = event.target.closest?.('[data-axis-card]');
    if (!dragId || !card) return;
    event.preventDefault(); clear();
    const rect = card.getBoundingClientRect();
    moveResultAxis(dragId, card.dataset.axisCard, event.clientY < rect.top + rect.height / 2);
    dragId = '';
  });
  root?.addEventListener('dragend', () => { dragId = ''; clear(); });
  root?.addEventListener('keydown', event => {
    const handle = event.target.closest?.('[data-axis-drag]');
    if (!handle || !['ArrowUp','ArrowDown'].includes(event.key)) return;
    event.preventDefault();
    const axes = state.project.result_layout.axes;
    const index = axes.findIndex(axis => axis.id === handle.dataset.axisDrag);
    const target = axes[index + (event.key === 'ArrowUp' ? -1 : 1)];
    if (target && moveResultAxis(handle.dataset.axisDrag, target.id, event.key === 'ArrowUp'))
      root.querySelector(`[data-axis-drag="${CSS.escape(handle.dataset.axisDrag)}"]`)?.focus();
  });
}
