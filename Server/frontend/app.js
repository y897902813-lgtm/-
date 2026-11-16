const state = {
  auth: null,
  project: null,
  ui: {},
  projects: [],
  recycleBin: [],
  hubSelectedTrashIds: new Set(),
  hubBaselineSortDescending: false,
  hubArchiveDragActive: false,
  trashRetentionDays: 7,
  categories: [],
  modelTypes: [],
  hubCollapsedModelTypes: new Set(),
  hubCollapseInitialized: false,
  editorLayout: {meshTwoColumns:true, driveTwoColumns:true, driveColumnPercent:50},
  projectRootName: '项目',
  skills: [],
  jobs: [],
  artifacts: [],
  meshFiles: [],
  selectedLayerId: null,
  expandedLayerAdvanced: new Set(),
  hubSelectedProjectId: null,
  hubCategory: 'None',
  hubPreview: null,
  hubFiles: null,
  modelAssetManager: {category:'', folders:[], selected:'', files:[], root:''},
  modelAssetManagerContext: {mode:'manage', projectId:'', current:'', editable:false, frozen:false},
  hubPreviewVersionId: null,
  hubVersions: [],
  hubCompareIds: new Set(),
  hubSelectedVariables: new Set(),
  hubTypeSummary: null,
  editSessionMode: null,
  editorWindowId: null,
  editorRegistryTimer: null,
  lastUserActivityAt: Date.now(),
  dirty: false,
  unarchivedChanges: false,
  activeJobId: null,
  activeJobKind: null,
  animationExportWindow: null,
  animationBlobUrl: null,
  animationLoading: false,
  animationExportHandle: null,
  animationExportProjectId: null,
  animationExportJobId: null,
  pollTimer: null,
  eventCursor: 0,
  latestSimulation: null,
  baseSimulationSchedule: [],
  simulationSchedule: [],
  simulationScheduleError: '',
  resultAutoSimulationPending: false,
  refreshAnimationAfterSimulation: false, // legacy flag remains false after refresh split
  simulationJobId: null,
  simulationRefreshSubmitting: false,
  enterCommitRunning: false,
  enterRefreshQueuedProjectId: null,
  animationRefreshSubmitting: false,
  resultViewerCurveOverrides: {projectId:null, sources:{}},
  resultAxisControlView: {projectId:null, expandedAxisIds:new Set()}, // V2.16.6.1: transient per-axis toolbar folds
  distanceCurveSession: null, // derivative cache; never part of ProjectSpec
  driveResolvedVariables: {},
  mappingTables: {},
  companionTravels: new Map(),
  expandedSegments: new Set(),
  editRevision: 0,
  saveChain: Promise.resolve(),
  uiCommitChain: Promise.resolve(),
  uiRevision: 0,
  uiPersistedRevision: 0,
  suppressUiEvents: false,
  cursorDrag: null,
  ganttCursorDrag: false,
  activeCursorIndex: 0,
  llmConfig: null,
  agentConversation: [],
  massProperties: null,
  assistantAbort: null,
  assistantStreaming: false,
  webViewerWindow: null,
  quickOptimizationRunning: false,
  projectLoadRevision: 0,
  interactionCommitTimer: null,
  interactionCommitNeedsMassRefresh: false,
  localDraftTimer: null,
  localDraftHistory: [],
  localDraftHistoryIndex: -1,
  localDraftBaseServerProject: null,
  localDraftUiChanges: new Map(),
  localDraftWriteErrorShown: false,
  localDraftRestored: false,
  leaseHeartbeatFailures: 0,
  leaseHeartbeatInFlight: false,
  viewerLaunchPending: false,
  viewerLaunchJobId: null,
  interactionCommitDebounceMs: 400,
  capabilities: {desktop_enabled:false, native_viewer:false, server_file_dialogs:false, direct_downloads:false},
  leaseTtlSeconds: 180,
  leaseHeartbeatTimer: null,
  leaseHeartbeatFailed: false,
  leaseLost: false,
  leaseLostReason: null,
  leaseRecoveryInFlight: false,
  idleDeadlines: {},
  idleCountdownTimer: null,
  localClientUrl: 'http://127.0.0.1:8766',
  networkPorts: {hub: Number(location.port) || (location.protocol === 'https:' ? 443 : 80), client: 8766, vz: 8877},
  localMeshVersions: [],
  selectedLocalMeshVersionId: null,
  adminMeshPath: '',
  localClientStatus: {online:false, mesh_path_ready:false, synchronized:false, extra_files:[]},
  hubProjectClickTimer: null,
  hubPreviewRevision: 0,
  hubPreviewLoading: false,
  hubPreviewRequest: null,
  hubPreviewLoadedAt: new Map(),
  hubPreviewCache: new Map(),
  hubRefreshTimer: null,
  hubVzStatusTimer: null,
  archiveLimit: 20,
  hubInspectorSection: 'model_assets',
  hubInspectorAssetSplitRatio: 0.42,
  hubInspectorAssetDrag: null,
  hubInspectorAssetLoading: false,
  hubProjectListWidth: 242,
  editorFocusRevision: 0,
  hubDeliverySuffixByProject: new Map(),
  expandedClosureId: '',
  hierarchyDiagramSelection: null,
  hierarchyDiagramMultiSelection: new Set(),
  hierarchyDiagramSuppressPaneClick: false,
  hierarchyDiagramInteraction: null,
  hierarchyDiagramViewportGesture: null,
  hierarchyDiagramViewportCommitTimer: null,
  hierarchyDiagramLayoutGesture: null,
  hierarchyDiagramLinkKind: 'parent',
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const randomId = () => globalThis.crypto && typeof globalThis.crypto.randomUUID === 'function'
  ? globalThis.crypto.randomUUID().replace(/-/g, '')
  : `${Date.now().toString(36)}${Math.random().toString(36).slice(2)}`;
const uid = (prefix) => `${prefix}_${randomId().slice(0, 10)}`;
const encodeArtifactPath = value => String(value ?? '').replace(/\\/g, '/').split('/').filter(Boolean).map(encodeURIComponent).join('/');
const esc = (value) => String(value ?? '').replace(/[&<>'"]/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
const roleLabel = role => ({guest:'游客',engineer:'工程师',admin:'管理员'})[role] || String(role || '');
const HUB_ENTRY_STORAGE_KEY = 'mujocoStudioHubEntry';
const hubEntryIsZoomed = document.documentElement.classList.contains('hub-entry-zoomed');
const HUB_ENTRY_MIN_VISIBLE_MS = hubEntryIsZoomed ? 0 : (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? 100 : 260);
const hubEntryStartedAt = document.documentElement.classList.contains('hub-entry-pending') ? Date.now() : 0;
let loginMetalPointerCleanup = null;
let hubEntryFinishScheduled = false;

function stopLoginMetalPointerMotion() {
  if (loginMetalPointerCleanup) loginMetalPointerCleanup();
  loginMetalPointerCleanup = null;
}

function startLoginMetalPointerMotion() {
  stopLoginMetalPointerMotion();
  const screen = $('#loginScreen');
  if (!screen) return;
  const move = event => {
    screen.style.setProperty('--login-pointer-x', `${event.clientX}px`);
    screen.style.setProperty('--login-pointer-y', `${event.clientY}px`);
  };
  window.addEventListener('pointermove', move, {passive:true});
  loginMetalPointerCleanup = () => {
    window.removeEventListener('pointermove', move);
  };
}

function playLoginHubTransition() {
  const screen = $('#loginScreen');
  if (!screen) return Promise.resolve();
  stopLoginMetalPointerMotion();
  screen.classList.add('is-authenticated');
  window.__LoginGlbViewer__?.enterHub?.();
  const duration = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? 120 : 780;
  return new Promise(resolve => window.setTimeout(resolve, duration));
}

if (hubEntryStartedAt) $('#hubEntryTransition')?.setAttribute('aria-hidden', 'false');

function clearHubEntryTransition() {
  try { sessionStorage.removeItem(HUB_ENTRY_STORAGE_KEY); } catch (_) {}
  document.documentElement.classList.remove('hub-entry-pending', 'hub-entry-revealing', 'hub-entry-zoomed');
  const overlay = $('#hubEntryTransition');
  if (overlay) {
    overlay.setAttribute('aria-hidden', 'true');
    overlay.classList.remove('is-ready');
  }
}

function finishHubEntryTransition() {
  if (!document.documentElement.classList.contains('hub-entry-pending') || hubEntryFinishScheduled) return;
  hubEntryFinishScheduled = true;
  const elapsed = hubEntryStartedAt ? Date.now() - hubEntryStartedAt : HUB_ENTRY_MIN_VISIBLE_MS;
  const delay = Math.max(0, HUB_ENTRY_MIN_VISIBLE_MS - elapsed);
  window.setTimeout(() => {
    const overlay = $('#hubEntryTransition');
    document.documentElement.classList.add('hub-entry-revealing');
    overlay?.classList.add('is-ready');
    try { sessionStorage.removeItem(HUB_ENTRY_STORAGE_KEY); } catch (_) {}
    window.setTimeout(() => {
      document.documentElement.classList.remove('hub-entry-pending', 'hub-entry-revealing', 'hub-entry-zoomed');
      overlay?.setAttribute('aria-hidden', 'true');
    }, 680);
  }, delay);
}
const rgbaToHex = (rgba) => {
  const values = String(rgba || '').split(/[ ,]+/).slice(0, 3).map(value => Math.max(0, Math.min(255, Math.round(Number(value) * 255))));
  return `#${values.map(value => (Number.isFinite(value) ? value : 184).toString(16).padStart(2, '0')).join('')}`;
};
const hexToRgba = (hex, alpha = 1) => {
  const raw = String(hex).replace('#', '').padEnd(6, '0');
  return [0, 2, 4].map(index => (parseInt(raw.slice(index, index + 2), 16) / 255).toFixed(3)).join(' ') + ` ${alpha}`;
};


function editBaselineLog(defaultLog = '', defaultName = '') {
  const dialog = $('#baselineLogDialog');
  const textarea = $('#baselineLogText');
  const nameInput = $('#baselineNameText');
  if (!dialog || !textarea || !nameInput) {
    const name = prompt('请输入基线模型名称：', defaultName);
    if (name === null) return Promise.resolve(null);
    const log = prompt('请输入本次基线更新日志：', defaultLog);
    return Promise.resolve(log === null ? null : {name:String(name || '').trim(), log:String(log || '')});
  }
  nameInput.value = String(defaultName || '');
  textarea.value = String(defaultLog || '');
  return new Promise(resolve => {
    const finish = () => {
      const confirmed = dialog.returnValue === 'confirm';
      dialog.removeEventListener('close', finish);
      resolve(confirmed ? {name:nameInput.value.trim(), log:textarea.value} : null);
    };
    dialog.addEventListener('close', finish);
    dialog.showModal();
    requestAnimationFrame(() => {
      nameInput.focus();
      nameInput.select();
    });
  });
}

const CAMERA_CONFIG = {
  front_view: {pos:[0.8,-1,0.6], direction:[0,1,0], posId:'cameraFrontPos', directionId:'cameraFrontDirection'},
  side_view: {pos:[1.5,-0.405,0.8], direction:[-1,0,0], posId:'cameraSidePos', directionId:'cameraSideDirection'},
  pov_view: {pos:[1.4,-0.405,0.97], direction:[-0.898,0,-0.439], posId:'cameraPovPos', directionId:'cameraPovDirection'},
  initial_free_view: {pos:[0.8,-1.5,0.6], direction:[0,1,0], posId:'cameraFreePos', directionId:'cameraFreeDirection'},
};

function cameraSettingsFromProject() {
  const result = Object.fromEntries(Object.entries(CAMERA_CONFIG).map(([name,item])=>[name,{pos:[...item.pos],direction:[...item.direction]}]));
  const raw = String(state.project?.viewer_control?.camera_initial_pose || '').trim();
  if (!raw) return result;
  try {
    const decoded = JSON.parse(raw), cameras = decoded.cameras || decoded;
    Object.keys(result).forEach(name=>{
      const item=cameras?.[name];
      if(Array.isArray(item?.pos)&&item.pos.length===3&&Array.isArray(item?.direction)&&item.direction.length===3){
        result[name]={pos:item.pos.map(Number),direction:item.direction.map(Number)};
      }
    });
  } catch (_) {
    const values=raw.replaceAll('；',',').replaceAll(';',',').split(',').map(Number);
    if(values.length===6&&values.every(Number.isFinite))result.initial_free_view={pos:values.slice(0,3).map(v=>v*.001),direction:values.slice(3)};
  }
  return result;
}

function renderCameraSettings() {
  const cameras=cameraSettingsFromProject();
  Object.entries(CAMERA_CONFIG).forEach(([name,meta])=>{
    $(`#${meta.posId}`).value=cameras[name].pos.join(' ');
    $(`#${meta.directionId}`).value=cameras[name].direction.join(' ');
  });
}

function cameraVector(inputId, label, allowZero=false) {
  const values=String($(`#${inputId}`).value||'').trim().split(/[\s,]+/).map(Number);
  if(values.length!==3||values.some(value=>!Number.isFinite(value)))throw new Error(`${label}必须包含 3 个有效数值`);
  if(!allowZero&&Math.hypot(...values)<=1e-12)throw new Error(`${label}不能是零向量`);
  return values;
}

function collectCameraSettings() {
  const cameras={};
  Object.entries(CAMERA_CONFIG).forEach(([name,meta])=>{
    cameras[name]={pos:cameraVector(meta.posId,`${name} 坐标`,true),direction:cameraVector(meta.directionId,`${name} 朝向`)};
  });
  state.project.viewer_control ||= {};
  state.project.viewer_control.camera_initial_pose=JSON.stringify({version:1,cameras});
}

const pageMeta = {
  overview: ['WORKSPACE', '工程总览'], model: ['MODEL GRAPH', '层级建模'], drives: ['MOTION SYSTEM', '驱动设置'],
  distance: ['DISTANCE ENGINE', '测距配置'], simulation: ['RESULT VIEWER', '仿真结果查看'], optimization: ['SEARCH', '批量优化'],
  agent: ['AUTOMATION', '智能体工作台'],
};

const EDITOR_PAGES = new Set(['model','drives','distance','simulation','optimization','agent']);
const HUB_PATH = '/hub';
const EDITOR_REGISTRY_PREFIX = 'mujocoStudio.editor.';
const EDITOR_REGISTRY_STALE_MS = 45000;

function editorWindowName(projectId) {
  return `mujoco-model-${String(projectId || '').replace(/[^A-Za-z0-9_-]/g, '_')}`;
}

function editorUrl(projectId, page = 'model', search = '') {
  const safePage = EDITOR_PAGES.has(page) ? page : 'model';
  const suffix = search ? (String(search).startsWith('?') ? String(search) : `?${search}`) : '';
  return `/models/${encodeURIComponent(projectId)}/editor/${safePage}${suffix}`;
}

function routeContextFromLocation() {
  const match = location.pathname.match(/^\/models\/([^/]+)\/editor(?:\/([^/]+))?\/?$/);
  if (match) {
    const page = EDITOR_PAGES.has(match[2]) ? match[2] : 'model';
    return {kind:'editor', projectId:decodeURIComponent(match[1]), page};
  }
  const legacy = location.hash.replace('#','');
  if (EDITOR_PAGES.has(legacy) && state.project?.id && state.editSessionMode) {
    return {kind:'editor', projectId:state.project.id, page:legacy, legacy:true};
  }
  return {kind:'hub', projectId:null, page:'overview', legacy:location.pathname !== HUB_PATH};
}

function currentPage() {
  const context = routeContextFromLocation();
  return context.kind === 'editor' ? context.page : 'overview';
}

function navigateToPage(page, {replace = false} = {}) {
  if (page === 'overview') {
    if (routeContextFromLocation().kind === 'editor') { openHubWindow(); return; }
    const method = replace ? 'replaceState' : 'pushState';
    history[method](null, '', HUB_PATH);
    window.name = 'mujoco-studio-hub';
    route();
    return;
  }
  if (!state.project?.id) return toast('请先打开一个模型编辑器', 'error');
  if (state.auth?.role === 'guest' && page !== 'simulation') {
    toast('游客只能进入仿真结果页面查看', 'error');
    page = 'simulation';
    replace = true;
  }
  const method = replace ? 'replaceState' : 'pushState';
  history[method](null, '', editorUrl(state.project.id, page));
  route();
}

function editorRegistryKey(projectId) { return `${EDITOR_REGISTRY_PREFIX}${state.auth?.username || 'anonymous'}.${projectId}`; }

function readEditorRegistry(projectId) {
  try {
    const raw = localStorage.getItem(editorRegistryKey(projectId));
    if (!raw) return null;
    const record = JSON.parse(raw);
    if (!record || Date.now() - Number(record.updatedAt || 0) > EDITOR_REGISTRY_STALE_MS) {
      localStorage.removeItem(editorRegistryKey(projectId));
      return null;
    }
    return record;
  } catch (_) { return null; }
}

function isEditorWindowOpen(projectId) { return Boolean(readEditorRegistry(projectId)); }

function markEditorWindowLaunching(projectId) {
  try { localStorage.setItem(editorRegistryKey(projectId), JSON.stringify({windowId:'launching', updatedAt:Date.now()})); } catch (_) {}
}

function registerEditorWindow(projectId) {
  if (!projectId) return;
  state.editorWindowId ||= uid('editor_window');
  window.name = editorWindowName(projectId);
  const writeRecord = () => {
    try { localStorage.setItem(editorRegistryKey(projectId), JSON.stringify({windowId:state.editorWindowId, updatedAt:Date.now()})); } catch (_) {}
  };
  writeRecord();
  clearInterval(state.editorRegistryTimer);
  state.editorRegistryTimer = setInterval(writeRecord, 10000);
}

function unregisterEditorWindow(projectId) {
  clearInterval(state.editorRegistryTimer); state.editorRegistryTimer = null;
  try {
    const record = readEditorRegistry(projectId);
    if (record?.windowId === state.editorWindowId || record?.windowId === 'launching') localStorage.removeItem(editorRegistryKey(projectId));
  } catch (_) {}
}

function openModelEditorWindow(projectId, page = 'model', {view = ''} = {}) {
  if (!projectId) return null;
  const query = view ? `view=${encodeURIComponent(view)}` : '';
  const targetUrl = editorUrl(projectId, page, query);
  const name = editorWindowName(projectId);
  if (isEditorWindowOpen(projectId)) {
    const existing = window.open('', name);
    if (existing) {
      try {
        const expectedPrefix = `/models/${encodeURIComponent(projectId)}/editor/`;
        if (existing.location.href === 'about:blank' || !existing.location.pathname.startsWith(expectedPrefix)) {
          existing.location.replace(targetUrl);
        } else {
          existing.postMessage({type:'mujoco-studio-editor-navigate', projectId, page, view}, location.origin);
        }
        existing.focus();
      } catch (_) {
        try { existing.location.href = targetUrl; existing.focus(); } catch (_) {}
      }
      return existing;
    }
  }
  markEditorWindowLaunching(projectId);
  const opened = window.open(targetUrl, name);
  if (opened) { try { opened.focus(); } catch (_) {} return opened; }
  try { localStorage.removeItem(editorRegistryKey(projectId)); } catch (_) {}
  location.assign(targetUrl);
  return null;
}

function openHubLab(projectId = state.hubSelectedProjectId) {
  const url = projectId ? `/lab?project_id=${encodeURIComponent(projectId)}` : '/lab';
  const opened = window.open(url, 'mujoco-lab');
  if (opened) { try { opened.focus(); } catch (_) {} }
  else location.assign(url);
}

function openHubWindow() {
  const opened = window.open(HUB_PATH, 'mujoco-studio-hub');
  try { opened?.focus(); } catch (_) {}
  return opened;
}

const PROJECT_LIFECYCLE_SYNC_KEY = 'mujocoStudioProjectLifecycleSync';
function invalidateHubProjectState(projectId) {
  if (!projectId) return;
  state.hubPreviewCache.delete(projectId);
  state.hubPreviewLoadedAt.delete(projectId);
  if (state.hubPreview?.id === projectId) {
    state.hubPreview = null;
    state.hubVersions = [];
    state.hubFiles = null;
  }
}
async function refreshHubProjectLifecycle(projectId, updatedProject = null) {
  if (!projectId) return;
  if (updatedProject?.id === projectId) {
    updateProjectSummary(updatedProject);
    if (state.project?.id === projectId && !state.dirty) state.project = updatedProject;
  }
  invalidateHubProjectState(projectId);
  if (routeContextFromLocation().kind === 'hub') renderHub();
  try {
    // Let any pre-sign-in catalog request settle first, then issue a fresh read
    // so an older response cannot land after the lifecycle synchronization.
    if (hubProjectsRequest?.promise) { try { await hubProjectsRequest.promise; } catch (_) {} }
    await loadProjects(projectId);
  } catch (error) {
    console.warn('[lifecycle-sync] Hub refresh failed:', error);
  }
}
function publishProjectLifecycleUpdate(updatedProject) {
  const projectId = updatedProject?.id;
  if (!projectId) return;
  const message = {type:'mujoco-studio-project-lifecycle-updated', projectId, project:updatedProject};
  try {
    if (window.opener && !window.opener.closed) window.opener.postMessage(message, location.origin);
  } catch (_) {}
  // Fallback for an existing Hub tab whose opener relationship was lost.
  // The key is transient and removed immediately; project state remains server-authoritative.
  try {
    localStorage.setItem(PROJECT_LIFECYCLE_SYNC_KEY, JSON.stringify({projectId, updatedAt:Date.now()}));
    localStorage.removeItem(PROJECT_LIFECYCLE_SYNC_KEY);
  } catch (_) {}
}

window.addEventListener('message', event => {
  if (event.origin !== location.origin) return;
  const message = event.data || {};
  if (message.type === 'mujoco-studio-editor-check-in' && message.projectId === state.project?.id) {
    void checkInCurrentEditor({confirmed:true, archive:message.archive !== false, log:message.log ?? '',
      archive_name:message.archive_name ?? '', overwrite_version_id:message.overwrite_version_id ?? ''});
    return;
  }
  if (message.type === 'mujoco-studio-project-lifecycle-updated' && message.projectId) {
    void refreshHubProjectLifecycle(message.projectId, message.project || null);
  }
});
window.addEventListener('storage', event => {
  if (event.key !== PROJECT_LIFECYCLE_SYNC_KEY || !event.newValue) return;
  try {
    const payload = JSON.parse(event.newValue);
    if (payload?.projectId) void refreshHubProjectLifecycle(payload.projectId);
  } catch (_) {}
});

function integratedVzUrl(path='/engineer') {
  const protocol = location.protocol === 'https:' ? 'http:' : location.protocol;
  return `${protocol}//${location.hostname}:${state.networkPorts.vz}${path}`;
}

async function api(path, options = {}) {
  const isFormData = options.body instanceof FormData;
  const {timeout, signal: userSignal, returnResponse = false, ...restOptions} = options;
  // 超时：options.timeout 传毫秒；默认 20s（比页面"永远挂着"强）；可传 null 关闭
  const t = timeout == null ? 20000 : (timeout === 0 || timeout === false ? 0 : Number(timeout) || 0);
  const ctrl = t > 0 ? new AbortController() : null;
  let timer = null;
  if (ctrl) {
    timer = setTimeout(() => ctrl.abort(new Error(`timeout ${t}ms`)), t);
  }
  // 信号合并：用户自定义 signal + 我们的超时信号
  const combinedSignals = [ctrl && ctrl.signal, userSignal].filter(Boolean);
  const signal = combinedSignals.length > 1
    ? (typeof AbortSignal.any === 'function' ? AbortSignal.any(combinedSignals) : (ctrl && ctrl.signal || userSignal))
    : (combinedSignals[0] || undefined);
  const headers = isFormData ? {...(restOptions.headers || {})} : {'Content-Type': 'application/json', ...(restOptions.headers || {})};
  try {
    const response = await fetch(path, {
      credentials:'same-origin', // Session cookie shared by /events and /state
      headers,
      signal,
      ...restOptions,
    });
    if (response.status === 401 && path !== '/api/auth/login') {
      if (state.auth) {
        showLogin('登录会话已过期；后台轮询已暂停，请重新登录后继续。模型不会因网络断开自动签入。');
        if (state.pollTimer) { clearInterval(state.pollTimer); state.pollTimer=null; }
        if (state.leaseHeartbeatTimer) { clearInterval(state.leaseHeartbeatTimer); state.leaseHeartbeatTimer=null; }
      }
      const error=new Error('登录会话已过期，请重新登录；已停止重复请求');
      error.status=401;
      throw error;
    }
    if (!response.ok) {
      let message = `${response.status} ${response.statusText}`;
      let retryAfter = 5;
      try {
        const body = await response.json();
        const detail = body.detail ?? body;
        if (typeof detail === 'string') message = detail;
        else if (Array.isArray(detail)) message = detail.map(item => item.message || item.msg || JSON.stringify(item)).join('\n');
        else {
          message = (detail.message || detail.error?.message || JSON.stringify(detail, null, 2)) + (detail.retry_after ? `（${detail.retry_after} 秒后重试）` : '');
          if (Number.isFinite(Number(detail.retry_after))) retryAfter = Math.max(1, Number(detail.retry_after));
        }
      } catch (_) {}
      const error = new Error(message);
      error.status = response.status;
      error.retryAfter = retryAfter;
      throw error;
    }
    if (response.status === 204) return returnResponse ? {data:null, response} : null;
    // 非 JSON 响应（如跨域拦截返回 HTML）也要给出人类可读错误
    const contentType = response.headers.get('content-type') || '';
    const looksJson = contentType.includes('application/json') || contentType.includes('+json');
    if (!looksJson) {
      const text = await response.text();
      if (/<html/i.test(text) || /<head/i.test(text)) {
        const snippet = text.slice(0, 200).replace(/\s+/g, ' ');
        throw new Error(`后端没有返回 JSON，却返回了 HTML（很可能是代理/网关/Nginx 拦截或路由错误）。前 200 字符：${snippet}`);
      }
      try {
        const data = JSON.parse(text);
        return returnResponse ? {data, response} : data;
      } catch (parseErr) {
        throw new Error(`接口 ${path} 返回的不是 JSON：${parseErr.message}。原文前 200 字符：${String(text).slice(0, 200)}`);
      }
    }
    const data = await response.json();
    return returnResponse ? {data, response} : data;
  } catch (err) {
    const name = err && err.name ? String(err.name) : '';
    const msg = err && err.message ? String(err.message) : `${err}`;
    if (name === 'AbortError' || msg.includes('timeout') || msg.includes('abort')) {
      const friendly = t > 0 ? `请求超时（${t}ms 未响应）。请确认后端已启动并在运行。` : '请求已取消。';
      throw new Error(friendly + ` [${options.method || 'GET'} ${path}]`);
    }
    if (/Failed to fetch|NetworkError|network request failed/i.test(msg)) {
      throw new Error(`无法连接后端 [${options.method || 'GET'} ${path}]：网络不通 / 端口未监听 / 浏览器 CORS 被阻止。请确认后端服务已启动，或查看浏览器 Network 面板里的 Preflight/Response。`);
    }
    throw err;
  } finally {
    if (timer) clearTimeout(timer);
  }
}

function applyDrivePreview(projectId, preview, {render = false} = {}) {
  if (!preview || state.project?.id !== projectId) return false;
  state.driveResolvedVariables = preview.variables || {};
  state.baseSimulationSchedule = preview.gantt || [];
  state.mappingTables = preview.mapping_tables || {};
  state.simulationScheduleError = preview.schedule_error || '';
  if (render && currentPage() === 'drives') renderDrives();
  if (render && currentPage() === 'simulation') { refreshCombinedGanttSchedule({render:false}); renderSimulationGantt(); }
  return true;
}

async function refreshDriveProjection(projectId, revision = state.editRevision, {render = true, draft = false} = {}) {
  // A Gantt projection never needs the latest MuJoCo result or the expensive
  // mesh/result fingerprint. POST accepts an unsynced browser draft, but DOES
  // NOT persist it; only Enter/check-in can publish the authoritative model.
  const preview = draft
    ? await api(`/api/projects/${projectId}/preview`, {method:'POST', body:JSON.stringify(deepClone(state.project)), timeout:12000})
    : await api(`/api/projects/${projectId}/preview?include_latest_result=false`);
  if (state.project?.id !== projectId || state.editRevision !== revision) return null;
  applyDrivePreview(projectId, preview, {render});
  return preview;
}

// No MuJoCo request from a Gantt/drive field edit. Keep only the most recent
// unsaved projection per browser. Lightweight local numeric edits render at
// once; the server resolves references, mapping curves and expressions exactly.
let draftGanttTimer = null;
let draftGanttBusy = false;
let draftGanttPending = false;
function renderImmediateDraftGantt() {
  if (!state.project) return;
  const old = new Map((state.baseSimulationSchedule || []).map(item => [String(item.mapping_segment_id||item.id),item]));
  const result = [];
  for (const drive of state.project.drives || []) {
    if (drive.enabled === false) continue;
    let position = 0;
    for (const segment of drive.segments || []) {
      const oldEntry = old.get(String(segment.id));
      const start = Number(segment.start), travel = Number(segment.travel);
      const speed = Math.abs(Number(segment.speed));
      const rise = segment.ease_in ? Number(segment.ease_in_time ?? segment.acceleration_time) : 0;
      const fall = segment.ease_out ? Number(segment.ease_out_time ?? segment.acceleration_time) : 0;
      const riseTime = segment.easing_mode === 'acceleration' && segment.ease_in
        ? speed / Math.abs(Number(segment.ease_in_acceleration)) : rise;
      const fallTime = segment.easing_mode === 'acceleration' && segment.ease_out
        ? speed / Math.abs(Number(segment.ease_out_acceleration)) : fall;
      const duration = segment.mode === 'duration' ? Number(segment.duration)
        : Math.abs(travel) / speed + .5 * (riseTime + fallTime);
      // Acceleration-based duration mode is quadratic (the MuJoCo Studio
      // schedule resolver solves a discriminant); use server projection instead
      // of displaying a numerically plausible but incorrect local estimate.
      const numeric = segment.start_mode !== 'reference' && ['s_curve','smoothstep'].includes(segment.profile || 's_curve') &&
        !(segment.mode === 'duration' && segment.easing_mode === 'acceleration' && (segment.ease_in || segment.ease_out)) &&
        Number.isFinite(start) && Number.isFinite(travel) && Number.isFinite(duration) &&
        duration >= 0 && (segment.mode === 'duration' || speed > 0);
      // Avoid inventing results for expressions, mapping and dependent segments;
      // the asynchronous authoritative schedule preview will handle them.
      if (numeric) {
        const unit = oldEntry?.travel_unit || '';
        result.push({...(oldEntry || {}), id:segment.id, drive_id:drive.id, drive_name:drive.name,
          joint_id:drive.joint_id, name:segment.name, start, end:start+duration,
          duration, travel, travel_start:position, travel_end:position+travel, travel_unit:unit});
        position += travel;
      } else if (oldEntry) {
        result.push(oldEntry);
        position = Number(oldEntry.travel_end) || position;
      }
    }
  }
  state.baseSimulationSchedule = result;
  if (currentPage() === 'simulation') refreshCombinedGanttSchedule();
}
function scheduleDraftGanttProjection() {
  if (!state.project || !canEditProject()) return;
  renderImmediateDraftGantt();
  if (draftGanttTimer) clearTimeout(draftGanttTimer);
  draftGanttPending = true;
  draftGanttTimer = setTimeout(async () => {
    draftGanttTimer = null;
    if (draftGanttBusy) return; // in-flight result triggers one latest follow-up
    draftGanttBusy = true;
    try {
      while (draftGanttPending && state.project && canEditProject()) {
        draftGanttPending = false;
        const id = state.project.id, revision = state.editRevision;
        try {
          await refreshDriveProjection(id, revision, {render:true, draft:true});
        } catch (error) {
          // 429 is intentional low-priority shedding. Never block the editor.
          if (!String(error.message).includes('429'))
            console.warn('[gantt] unsaved schedule preview:',error);
        }
      }
    } finally { draftGanttBusy = false; }
  }, 170);
}

// V2.16.2: prevent duplicate transient messages (especially concurrent HTTP
// failures) from stacking over the editor. Navigation and background progress
// are intentionally not announced through this channel.
const toastRecentMessages = new Map();
function toast(message, kind = 'info', durationMs = null) {
  const key = `${kind}\u0000${String(message)}`;
  const now = Date.now();
  if (now - (toastRecentMessages.get(key) || 0) < 2200) return;
  toastRecentMessages.set(key, now);
  if (toastRecentMessages.size > 80) {
    for (const [oldKey, when] of toastRecentMessages) {
      if (now - when > 15000) toastRecentMessages.delete(oldKey);
    }
  }
  const region = $('#toastRegion');
  if (!region) return;
  // Existing toast API is retained for user-triggered server operations and
  // actionable errors. A single operation should not obscure all controls.
  const active = [...region.querySelectorAll('.toast')];
  while (active.length >= (kind === 'error' ? 3 : 2)) active.shift()?.remove();
  const item = document.createElement('div');
  item.className = `toast ${kind}`;
  item.innerHTML = `<div><strong>${kind === 'error' ? '操作失败' : '提示'}</strong><pre>${esc(message)}</pre></div><button aria-label="关闭">×</button>`;
  item.querySelector('button').addEventListener('click', () => item.remove());
  region.append(item);
  const lifespan = Number.isFinite(durationMs) ? Math.max(250, durationMs) : (kind === 'error' ? 12000 : 4800);
  setTimeout(() => item.remove(), lifespan);
}


const blockingLoadingState = {
  stack: [], timer: null, progress: 8, startedAt: 0, sequence: 0,
};

function blockingLoadingActive() {
  return blockingLoadingState.stack.length > 0;
}

function renderBlockingLoading() {
  const overlay = $('#blockingLoadingOverlay');
  if (!overlay) return;
  const current = blockingLoadingState.stack.at(-1);
  if (!current) return;
  $('#blockingLoadingTitle').textContent = current.title || '正在处理';
  $('#blockingLoadingDetail').textContent = current.detail || '请等待当前操作完成。';
  const seconds=Math.max(0,Math.floor((Date.now()-blockingLoadingState.startedAt)/1000));
  const timeLabel=$('#blockingLoadingElapsed');
  if(timeLabel)timeLabel.textContent=`已等待 ${seconds} 秒 · ${seconds>=15?'服务端仍可能在处理，请勿重复提交相同操作':'正在处理'}${seconds>=45?' · 若网络掉线，请查看后台任务/项目状态':''}`;
  const bar = $('#blockingLoadingBar');
  if (bar) bar.style.width = `${blockingLoadingState.progress.toFixed(1)}%`;
}

function beginBlockingLoading({title = '正在处理', detail = '请等待当前操作完成。'} = {}) {
  const token = {id: ++blockingLoadingState.sequence, title, detail};
  const first = !blockingLoadingActive();
  blockingLoadingState.stack.push(token);
  if (first) {
    blockingLoadingState.startedAt = Date.now();
    blockingLoadingState.progress = 8;
    const overlay = $('#blockingLoadingOverlay');
    if (overlay) {
      overlay.classList.remove('hidden');
      overlay.setAttribute('aria-hidden', 'false');
      document.body.classList.add('blocking-loading-active');
      document.body.setAttribute('aria-busy', 'true');
      document.activeElement?.blur?.();
      try { overlay.focus({preventScroll:true}); } catch (_) { overlay.focus?.(); }
    }
    blockingLoadingState.timer = setInterval(() => {
      // We do not have authoritative backend percentage.  The bar therefore
      // approaches 92% while work is pending and reaches 100% only on success/failure completion.
      const remaining = 92 - blockingLoadingState.progress;
      blockingLoadingState.progress = Math.min(92, blockingLoadingState.progress + Math.max(.25, remaining * .035));
      renderBlockingLoading();
    }, 160);
  }
  renderBlockingLoading();
  return token;
}

function updateBlockingLoading(token, {title, detail} = {}) {
  const item = blockingLoadingState.stack.find(candidate => candidate.id === token?.id);
  if (!item) return;
  if (title) item.title = title;
  if (detail) item.detail = detail;
  renderBlockingLoading();
}

async function endBlockingLoading(token) {
  const index = blockingLoadingState.stack.findIndex(candidate => candidate.id === token?.id);
  if (index >= 0) blockingLoadingState.stack.splice(index, 1);
  if (blockingLoadingActive()) {
    renderBlockingLoading();
    return;
  }
  if (blockingLoadingState.timer) clearInterval(blockingLoadingState.timer);
  blockingLoadingState.timer = null;
  blockingLoadingState.progress = 100;
  const bar = $('#blockingLoadingBar');
  if (bar) bar.style.width = '100%';
  const elapsed = Date.now() - blockingLoadingState.startedAt;
  await new Promise(resolve => setTimeout(resolve, Math.max(140, 320 - elapsed)));
  const overlay = $('#blockingLoadingOverlay');
  overlay?.classList.add('hidden');
  overlay?.setAttribute('aria-hidden', 'true');
  document.body.classList.remove('blocking-loading-active');
  document.body.removeAttribute('aria-busy');
  blockingLoadingState.progress = 8;
}

async function withBlockingLoading(options, operation) {
  const token = beginBlockingLoading(options);
  try {
    return await operation(token);
  } finally {
    await endBlockingLoading(token);
  }
}

function blockInteractionDuringLoading(event) {
  if (!blockingLoadingActive() || !event.isTrusted || event.target?.closest?.('#cancelViewerLaunchButton')) return;
  event.preventDefault();
  event.stopImmediatePropagation();
}

for (const eventName of ['keydown','keyup','keypress','beforeinput','pointerdown','click','dblclick','contextmenu','wheel','touchstart','touchmove','dragstart','drop']) {
  document.addEventListener(eventName, blockInteractionDuringLoading, {capture:true, passive:false});
}
document.addEventListener('focusin', event => {
  if (event.target?.matches?.('input,textarea,select,[contenteditable="true"]')) state.editorFocusRevision += 1;
  if (!blockingLoadingActive() || event.target?.closest?.('#blockingLoadingOverlay')) return;
  event.stopImmediatePropagation();
  $('#blockingLoadingOverlay')?.focus?.({preventScroll:true});
}, true);
window.addEventListener('beforeunload', event => {
  if (!blockingLoadingActive()) return;
  event.preventDefault();
  event.returnValue = '';
});

function markDirty() {
  if (!canEditProject()) return;
  state.dirty = true;
  state.unarchivedChanges = true;
  state.editRevision += 1;
  $('#dirtyBadge').textContent = '正在保存…';
  $('#dirtyBadge').title = '更改正保存在当前设备；按 Enter 会更新云端当前版本和坐标系';
  $('#dirtyBadge').classList.remove('hidden');
  if ($('#syncDraftButton')) $('#syncDraftButton').disabled = false;
  pushLocalHistory();
  scheduleLocalDraftWrite();
}

// Local-first editable ProjectSpec: drafts survive navigation and failed sync,
// but never grant permission and never replace another user's server revision.
function localDraftEligible() {
  return Boolean(state.project?.id && state.auth?.username && state.editSessionMode === 'persistent' &&
    projectStatus(state.project) === 'checked_out' && canEditProject());
}
function projectServerSignature(project) {
  return JSON.stringify(project || null);
}
function pushLocalHistory() {
  if (!localDraftEligible() || !state.project) return;
  const history = state.localDraftHistory;
  const snapshot = deepClone(state.project);
  if (state.localDraftHistoryIndex >= 0 &&
      JSON.stringify(history[state.localDraftHistoryIndex]) === JSON.stringify(snapshot)) return;
  history.splice(state.localDraftHistoryIndex + 1);
  history.push(snapshot);
  if (history.length > 32) history.shift();
  state.localDraftHistoryIndex = history.length - 1;
}
function scheduleLocalDraftWrite() {
  if (!localDraftEligible()) return;
  if (state.localDraftTimer) clearTimeout(state.localDraftTimer);
  state.localDraftTimer = setTimeout(() => {
    state.localDraftTimer = null;
    void persistLocalDraft();
  }, 250);
}
async function persistLocalDraft() {
  if (!localDraftEligible() || !window.MuJoCoLocalDrafts) return;
  const owner = state.auth.username;
  const projectId = state.project.id;
  const pendingUi = [...state.localDraftUiChanges.entries()];
  if (!state.dirty && !pendingUi.length) return;
  const payload = {
    project:deepClone(state.project), ui:deepClone(state.ui),
    projectDirty:Boolean(state.dirty), uiChanges:pendingUi,
    leaseId:String(state.project.lifecycle?.lease_id || ''),
    baseSignature:projectServerSignature(state.localDraftBaseServerProject),
    savedAt:Date.now(),
  };
  // Preserve an IndexedDB undo/redo window across editor reloads, not just
  // the latest draft. Keep server baseline (index 0) plus up to seven nearby
  // snapshots. Drop optional history first when a large CAD ProjectSpec risks
  // exhausting the 8 MiB per-draft budget; never sacrifice the current draft.
  const allHistory = state.localDraftHistory;
  if (allHistory.length) {
    const cursor = Math.max(0, Math.min(state.localDraftHistoryIndex, allHistory.length-1));
    const start = Math.max(1, Math.min(cursor - 3, Math.max(1, allHistory.length - 7)));
    const indexes = [0];
    for (let index=start; index<Math.min(allHistory.length, start+7); index++) indexes.push(index);
    let active = indexes.indexOf(cursor);
    if (active < 0) { indexes.push(cursor); active=indexes.length-1; }
    let windowHistory = indexes.map(index => deepClone(allHistory[index]));
    const withinBudget = () => JSON.stringify({...payload, localHistory:windowHistory}).length * 2 <= 7 * 1024 * 1024;
    while (windowHistory.length > 2 && !withinBudget()) {
      const removeAt = active > 1 ? 1 : windowHistory.length - 1;
      windowHistory.splice(removeAt,1);
      if (removeAt < active) active -= 1;
    }
    if (!withinBudget()) { windowHistory=[]; active=-1; }
    payload.localHistory=windowHistory;
    payload.localHistoryIndex=active;
  }
  try {
    await MuJoCoLocalDrafts.save(owner, projectId, payload);
    state.localDraftWriteErrorShown = false;
    if (state.project?.id === projectId && (state.dirty || state.localDraftUiChanges.size)) {
      $('#dirtyBadge').textContent = '已保存';
      $('#dirtyBadge').title = '本机工作草稿已安全保存；按 Enter 更新云端和仿真坐标系';
    }
  } catch (error) {
    if (!state.localDraftWriteErrorShown && state.project?.id === projectId) {
      state.localDraftWriteErrorShown = true;
      toast(`本机草稿保存失败：${error.message}。可按 Enter 提交至服务端，或先保留编辑器并检查浏览器空间。`, 'error');
    }
  }
}
async function removeLocalDraft(projectId, username = state.auth?.username) {
  if (!projectId || !username) return;
  try { await window.MuJoCoLocalDrafts?.remove(username, projectId); }
  catch (error) { console.warn('[local-draft] remove failed', error); }
}
async function recoverLocalDraftForProject(projectId) {
  if (!window.MuJoCoLocalDrafts || !localDraftEligible()) return false;
  const entry = await MuJoCoLocalDrafts.read(state.auth.username, projectId).catch(error => {
    console.warn('[local-draft] read failed', error); return null;
  });
  const draft = entry?.payload;
  if (!draft?.project || draft.project.id !== projectId || !draft.projectDirty && !draft.uiChanges?.length) return false;
  const validLease = Boolean(draft.leaseId) && draft.leaseId === String(state.project.lifecycle?.lease_id || '');
  const matchingServer = draft.baseSignature === projectServerSignature(state.localDraftBaseServerProject);
  if (!validLease || !matchingServer) {
    // This is an actionable data conflict, not a normal editor-entry notice.
    toast('本机草稿与服务端模型或编辑租约不匹配；已保留草稿但没有覆盖服务端，请核对版本后再恢复。', 'error', 9000);
    return false;
  }
  // Same user, exact server baseline AND lease: safe to restore on-device work
  // without another startup confirmation. No network write occurs here.
  if (draft.projectDirty) state.project = deepClone(draft.project);
  if (draft.ui && typeof draft.ui === 'object') state.ui = deepClone(draft.ui);
  state.localDraftUiChanges = new Map(Array.isArray(draft.uiChanges) ? draft.uiChanges : []);
  state.dirty = Boolean(draft.projectDirty);
  // Restore the optional on-device undo window only after the same-account,
  // same-lease and exact server-baseline checks have succeeded above.
  const history = Array.isArray(draft.localHistory) ? draft.localHistory : [];
  const cursor = Number(draft.localHistoryIndex);
  if (history.length && history.length <= 32 && Number.isInteger(cursor) && cursor >= 0 && cursor < history.length &&
      projectServerSignature(history[0]) === projectServerSignature(state.localDraftBaseServerProject) &&
      projectServerSignature(history[cursor]) === projectServerSignature(state.project)) {
    state.localDraftHistory = deepClone(history);
    state.localDraftHistoryIndex = cursor;
  }
  state.localDraftRestored = true;
  state.editRevision += 1;
  if (state.dirty || state.localDraftUiChanges.size) {
    $('#dirtyBadge').textContent = '已保存';
    $('#dirtyBadge').classList.remove('hidden');
    if ($('#syncDraftButton')) $('#syncDraftButton').disabled = false;
  }
  return true;
}

function projectStatus(project = state.project) {
  return project?.lifecycle?.status || project?.lifecycle_status || 'checked_in';
}

function canEditProject(project = state.project) {
  if (!['engineer','admin'].includes(state.auth?.role)) return false;
  const owner = project?.lifecycle?.checked_out_by || project?.checked_out_by || '';
  if (['checked_in','baseline'].includes(projectStatus(project))) return project?.id === state.project?.id && state.editSessionMode === 'temporary';
  return projectStatus(project) === 'checked_out' && (!owner || owner.toLowerCase() === state.auth.username.toLowerCase());
}

function canGenerateAnimationHtml(project = state.project) {
  return projectStatus(project) === 'checked_out' && canEditProject(project);
}

function lifecycleLabel(status) {
  return ({checked_in:'签入', checked_out:'签出', baseline:'基线'})[status] || status;
}

function projectNameMarker(status) {
  return ({checked_in:'🔒', checked_out:'📩🧑‍💻', baseline:'⚑'})[status] || '•';
}

function editorDisplayName(project = state.project) {
  const name = project?.name || '模型';
  return `${projectNameMarker(projectStatus(project))} ${name}`;
}

const GANTT_SEGMENT_COLORS = ['#F9B665','#ED8A49','#EE4D30','#F8D385','#EDE2A0','#B3CEA5','#71BDB9','#366C9A'];

function ganttSegmentColor(display, segmentIndex = 0) {
  const fallback = GANTT_SEGMENT_COLORS[Math.max(0, segmentIndex) % GANTT_SEGMENT_COLORS.length];
  const custom = display?.custom_color === true ? String(display.color || '') : '';
  return /^#[0-9a-f]{6}$/i.test(custom) ? custom : fallback;
}

function clearDirty() {
  state.dirty = false;
  if ($('#syncDraftButton')) $('#syncDraftButton').disabled = !state.localDraftUiChanges.size;
  $('#dirtyBadge').textContent = '已保存';
  $('#dirtyBadge').title = '当前工作版本已保存；需要历史恢复点时可保存到版本历史';
}

function markArchiveDirty() {
  state.unarchivedChanges = true;
  $('#dirtyBadge').classList.remove('hidden');
}

function clearArchiveDirty() {
  state.unarchivedChanges = false;
  $('#dirtyBadge').classList.add('hidden');
}

function valueAtPath(object, path) {
  return path.split('.').reduce((value, key) => value?.[Number.isNaN(Number(key)) ? key : Number(key)], object);
}

function setAtPath(object, path, value) {
  const keys = path.split('.');
  const final = keys.pop();
  const parent = keys.reduce((current, key) => current[Number.isNaN(Number(key)) ? key : Number(key)], object);
  parent[Number.isNaN(Number(final)) ? final : Number(final)] = value;
}

/* 确保 path 对应的父级对象已存在（类似 mkdir -p）；最后一级值是 undefined 则不写入，仅准备父节点 */
function ensurePath(object, path) {
  const keys = path.split('.');
  for (let i = 0; i < keys.length - 1; i++) {
    const key = keys[i];
    const isNumeric = /^\d+$/.test(key);
    const k = isNumeric ? Number(key) : key;
    const nextKey = keys[i + 1];
    const nextIsNumeric = /^\d+$/.test(nextKey);
    if (!object[k] || typeof object[k] !== 'object') {
      object[k] = nextIsNumeric ? [] : {};
    }
    object = object[k];
  }
}

/** 生成一个短随机 id。优先用 crypto.randomUUID，否则回落到伪随机（非安全上下文时 crypto.randomUUID 可能不存在） */
function makeShortId(len = 8) {
  if (globalThis.crypto && typeof crypto.randomUUID === 'function') {
    try { return crypto.randomUUID().replace(/-/g, '').slice(0, Math.max(6, len)); }
    catch (_) { /* fallback below */ }
  }
  const alphabet = '0123456789abcdefghijklmnopqrstuvwxyz';
  let out = '';
  let entropy = Date.now() ^ (Math.random() * 0x7fffffff);
  for (let i = 0; i < len; i++) {
    entropy = (entropy * 9301 + 49297) % 233280;
    const idx = Math.floor((entropy / 233280) * alphabet.length);
    out += alphabet[idx % alphabet.length];
  }
  return out;
}

function deepClone(value) {
  if (value == null || typeof value !== 'object') return value;
  if (value instanceof Date) return new Date(value.getTime());
  if (Array.isArray(value)) return value.map(v => deepClone(v));
  if (value instanceof Map || value instanceof Set) return value; // 不克隆内部集合
  const out = {}; for (const k in value) if (Object.prototype.hasOwnProperty.call(value, k)) out[k] = deepClone(value[k]); return out;
}

/* =========================================================
 * 语义化 UI 状态修改入口（架构文档 §4.3 的最小落地版）
 * - 所有修改 state.ui.* 的代码必须走 uiSet / uiBatch
 * - 负责：写本地镜像 + 写 localStorage 语义日志 + 调用 commitUiState 落库
 * - semantic 必须是人类可读一句话（供未来撤销栈 / 操作日志 / LLM 轨迹使用）
 * ========================================================= */
const UI_LOG_KEY = 'mujoco_studio_ui_log_v1';
const UI_LOG_MAX = 500;

function _pushUiLog(entry) {
  try {
    const raw = localStorage.getItem(UI_LOG_KEY);
    const list = raw ? JSON.parse(raw) : [];
    list.push(entry);
    if (list.length > UI_LOG_MAX) list.splice(0, list.length - UI_LOG_MAX);
    localStorage.setItem(UI_LOG_KEY, JSON.stringify(list));
  } catch (_) { /* 忽略 quota/解析错误 */ }
}

/** 修改 ui 子树的单个路径值。
 * @param {string} path 以 "ui." 开头或省略前缀都行（例如 ui.results.gantt_scale_x / results.gantt_scale_x）
 * @param {*} value 新值
 * @param {string} semantic 人类可读一句话（必填）
 * @param {{silent?:boolean, persist?:boolean, debug?:boolean, transient?:boolean, client?:'human_ui'|'automation'|'llm_agent'}} opts
 *   transient=true 表示实时调试变量（如拖动滑块中间值）：不写日志 + 不持久化；只有最终 change 才落盘
 *   client: human_ui=人类实时调试（默认 transient=true） / automation=自动化流程（会记录且持久化）
 */
function uiSet(path, value, semantic, opts = {}) {
  if (!semantic || typeof semantic !== 'string') throw new Error('uiSet 必须传入 semantic（人类可读操作描述）');
  const normalized = path.startsWith('ui.') ? path : `ui.${path}`;
  const client = opts.client || (typeof window.__llm_client_tag === 'string' ? 'llm_agent' : 'human_ui');
  // 只有调用方明确标记 transient 的中间值才不落盘。最终 change/pointerup
  // 必须正常记录，否则缩放、游标和倒放等设置会看似生效、刷新后却丢失。
  const isTransient = Boolean(opts.transient);
  // 确保父对象存在：根节点是 state，path 第一级是 ui
  ensurePath(state, normalized);
  const before = deepClone(valueAtPath(state, normalized));
  const after = deepClone(value);
  setAtPath(state, normalized, value);
  if (opts.debug) debugger;
  if (!opts.silent) {
    console.debug(`${isTransient ? '[uiSet·实时]' : '[uiSet]'} ${semantic}`, {path: normalized, before, after, client});
  }
  if (!isTransient) {
    _pushUiLog({
      ts: new Date().toISOString(),
      kind: 'set',
      path: normalized,
      before, after,
      semantic,
      client,
    });
  }
  // 只有非实时调试（=语义动作完成）才落库
  if (!isTransient && opts.persist !== false && state.project?.id) {
    // UI-only mutations do not mark the project dirty, so they need their own
    // revision fence.  It prevents a background /state mirror that started
    // before this ui.set reached the server from repainting an older view.
    const uiRevision = ++state.uiRevision;
    state.uiPersistedRevision = uiRevision; // local fence; authoritative echo must not overwrite a draft
    if (localDraftEligible()) {
      state.localDraftUiChanges.set(normalized, deepClone(value));
      scheduleLocalDraftWrite();
      if ($('#syncDraftButton')) $('#syncDraftButton').disabled = false;
    } else {
      commitUiState(normalized, value, uiRevision).catch(() => {});
    }
  }
  return after;
}

/** 批量改多个 ui 路径。
 * @param {Array<{path:string, value:any, semantic?:string, transient?:boolean, client?:string}>} ops
 * @param {{semantic:string, persist?:boolean, client?:'human_ui'|'automation'|'llm_agent'}} batchMeta
 */
function uiBatch(ops, batchMeta) {
  if (!batchMeta?.semantic || typeof batchMeta.semantic !== 'string') throw new Error('uiBatch 必须传入 batchMeta.semantic');
  const batchId = `batch_${Date.now().toString(36)}_${makeShortId(6)}`;
  const client = batchMeta.client || (typeof window.__llm_client_tag === 'string' ? 'llm_agent' : 'human_ui');
  const opResults = [];
  let anyPersist = false;
  for (const op of ops) {
    if (!op || typeof op.path !== 'string') continue;
    const normalized = op.path.startsWith('ui.') ? op.path : `ui.${op.path}`;
    const opClient = op.client || client;
    const isTransient = Boolean(op.transient);
    ensurePath(state, normalized);
    const before = deepClone(valueAtPath(state, normalized));
    const after = deepClone(op.value);
    setAtPath(state, normalized, op.value);
    opResults.push({path:normalized, before, after, semantic: op.semantic || batchMeta.semantic, client:opClient, transient: isTransient});
    if (!isTransient) anyPersist = true;
    console.debug(`${isTransient ? '[uiBatch·实时·' : '[uiBatch·'}${batchId}] ${op.semantic || batchMeta.semantic}`, {path:normalized, before, after, client:opClient});
  }
  const batchTransient = !anyPersist && opResults.every(it => it.transient);
  if (!batchTransient) {
    _pushUiLog({
      ts: new Date().toISOString(),
      kind: 'batch',
      batch_id: batchId,
      semantic: batchMeta.semantic,
      client,
      ops: opResults.map(({path, before, after, semantic, client:opClient, transient}) => ({path, before, after, semantic, client:opClient, transient})),
    });
  }
  // 批量落库（串行，保证后端顺序；失败不影响前端镜像一致性）。
  // Reserve all revisions up front: although every batch value is already in
  // the optimistic local mirror, an authoritative poll must stay fenced until
  // the final persisted op in this batch reaches the server.
  if (anyPersist && batchMeta.persist !== false && state.project?.id) {
    const persistedOps = opResults.filter(item => !item.transient);
    const firstRevision = state.uiRevision + 1;
    state.uiRevision += persistedOps.length;
    if (localDraftEligible()) {
      for (const {path, after} of persistedOps) state.localDraftUiChanges.set(path, deepClone(after));
      state.uiPersistedRevision = state.uiRevision;
      scheduleLocalDraftWrite();
      if ($('#syncDraftButton')) $('#syncDraftButton').disabled = false;
    } else {
      (async () => {
        for (let index = 0; index < persistedOps.length; index += 1) {
          const {path, after} = persistedOps[index];
          try { await commitUiState(path, after, firstRevision + index); } catch (_) {}
        }
      })();
    }
  }
  return opResults;
}

/** 注册「右键 → 设为默认值」能力：
 *  目标元素需设置 data-ui-default-bind='{"path":"ui.results.xxx","valueFrom":"value|checked|dataset|textContent","label":"横向缩放"}'
 *  选到的默认值会写入 localStorage 的 UI_DEFAULTS_KEY，下次 boot 时统一 apply 到 state.ui（以及对应控件的初始值）
 */
const UI_DEFAULTS_KEY = 'mujoco_studio_ui_defaults_v1';
function registerUiDefaultsContextMenu() {
  const getLabel = (el) => {
    try { return JSON.parse(el.dataset.uiDefaultBind || '{}').label || '该控件'; } catch { return '该控件'; }
  };
  window.addEventListener('contextmenu', (ev) => {
    const el = ev.target.closest?.('[data-ui-default-bind]');
    if (!el) return;
    ev.preventDefault();
    const label = getLabel(el);
    const cfg = JSON.parse(el.dataset.uiDefaultBind || '{}');
    let value;
    switch (cfg.valueFrom || 'value') {
      case 'checked': value = el.checked; break;
      case 'textContent': value = el.textContent.trim(); break;
      case 'dataset': value = el.dataset[cfg.datasetKey || 'value']; break;
      default: value = el.value;
    }
    if (confirm(`将【${label}】设为默认值？\n值 = ${typeof value === 'string' ? value : JSON.stringify(value)}\n（全局所有项目新建/打开时都会覆盖 UI 初始值）`)) {
      const path = cfg.path.startsWith('ui.') ? cfg.path : `ui.${cfg.path}`;
      try {
        const raw = localStorage.getItem(UI_DEFAULTS_KEY);
        const dict = raw ? JSON.parse(raw) : {};
        dict[path] = value;
        localStorage.setItem(UI_DEFAULTS_KEY, JSON.stringify(dict));
        // 立刻把最新默认值回填到当前 state.ui（不写事件流，不重跑渲染——渲染会用到 state 新值）
        ensurePath(state, path); setAtPath(state, path, value);
        toast(`已设默认：${label}=${String(value)}`);
      } catch (err) {
        toast('设置默认值失败：' + err.message, 'error');
      }
    }
  });
}

/** boot 时应用用户已保存的 UI 默认值（仅补默认值，不打日志，不写持久化） */
function applyUiDefaults() {
  try {
    const raw = localStorage.getItem(UI_DEFAULTS_KEY);
    if (!raw) return;
    const dict = JSON.parse(raw) || {};
    for (const [path, value] of Object.entries(dict)) {
      if (typeof path !== 'string' || !path.startsWith('ui.')) continue;
      ensurePath(state, path);
      setAtPath(state, path, value);
    }
  } catch (_) { /* ignore */ }
}

/** 调试钩子：返回最近 N 条 UI 操作日志（console 或 DevTools 里用） */
function uiLogTail(limit = 30) {
  try {
    const raw = localStorage.getItem(UI_LOG_KEY);
    const list = raw ? JSON.parse(raw) : [];
    return list.slice(-Math.max(1, limit));
  } catch (_) { return []; }
}
window.__uiSet = uiSet;
window.__uiBatch = uiBatch;
window.__uiLogTail = uiLogTail;

function negateVectorText(value) {
  const raw = String(value ?? '').trim();
  const parts = raw.split(/[\s,，]+/).filter(Boolean);
  if (parts.length !== 3) return raw;
  const numbers = parts.map(Number);
  if (!numbers.every(Number.isFinite)) return raw;
  return numbers.map(value => {
    const negated = -value;
    return String(Object.is(negated, -0) ? 0 : negated);
  }).join(', ');
}

function displayJointVector(value, reverse) {
  return reverse ? negateVectorText(value) : String(value ?? '');
}

function inputValue(element) {
  if (element.type === 'checkbox') return element.checked;
  if (element.multiple) return [...element.selectedOptions].map(option => option.value);
  if (element.dataset.type === 'number') return element.value === '' ? 0 : Number(element.value);
  if (element.dataset.type === 'nullable-number') return element.value === '' ? null : Number(element.value);
  if (element.dataset.type === 'lines') return element.value.split(/[,\n]/).map(item => item.trim()).filter(Boolean);
  if (element.dataset.reverseVector === 'true') return negateVectorText(element.value);
  return element.value;
}

function firstInvalidActiveJointRange(project = state.project) {
  for (const layer of project?.layers || []) {
    for (const joint of layer.joints || []) {
      if (!joint?.limited) continue;
      const values = Array.isArray(joint.range) ? joint.range.map(Number) : [];
      if (values.length !== 2 || !values.every(Number.isFinite) || !(values[0] < values[1])) {
        return {joint, layer};
      }
    }
  }
  return null;
}

function activeJointRangeErrorMessage(issue) {
  return issue ? `运动副“${issue.joint?.name || '未命名'}”已启用范围限制，下限必须小于上限；请修正两个范围值后再保存或生成 Viewer。` : '';
}

/* 启动链路诊断：把关键节点写入数组，最后挂到 window.__bootDiagnose 方便排查 */
const __BOOT_DIAGNOSE__ = [];
function bootMark(step, payload = {}) {
  const entry = Object.assign({ts: Date.now(), step}, payload);
  __BOOT_DIAGNOSE__.push(entry);
  if (window.__enableBootVerbose__) console.debug('[boot]', step, payload);
}

function showLogin(message = '') {
  clearHubEntryTransition();
  state.auth = null;
  const loginScreen = $('#loginScreen');
  loginScreen?.classList.remove('hidden', 'is-authenticated');
  $('.shell')?.setAttribute('aria-hidden', 'true');
  try {
    const raw = sessionStorage.getItem('mujocoStudioLogoutStatus');
    if (raw) {
      const result = JSON.parse(raw);
      sessionStorage.removeItem('mujocoStudioLogoutStatus');
      if (result?.status === 'deferred') message = '已退出账号；后台任务仍在运行，任务结束后模型会自动签入。';
      else if (result?.status === 'complete') message = '已安全退出，当前会话持有的模型已完成签入。';
    }
  } catch (_) {}
  if ($('#loginError')) $('#loginError').textContent = message;
  startLoginMetalPointerMotion();
  setTimeout(() => $('#loginUsername')?.focus(), 0);
}

function hideLogin() {
  stopLoginMetalPointerMotion();
  $('#loginScreen')?.classList.add('hidden');
  $('.shell')?.removeAttribute('aria-hidden');
}

function applyCapabilityProjection() {
  const desktop = Boolean(state.capabilities?.desktop_enabled);
  const direct = true;
  const importButton = $('#hubImportProjectButton');
  if (importButton) importButton.title = desktop ? '从服务器桌面或浏览器 JSON 导入完整项目；默认导入当前文件夹' : '从浏览器 JSON 文件导入完整项目；默认导入当前文件夹';
  const bundleImportButton = $('#hubImportBundleButton');
  if (bundleImportButton) bundleImportButton.title = '导入模型完整压缩包到当前文件夹，并恢复数模、交付数据与可用存档';
  const csvButton = $('#exportAllAxesButton');
  if (csvButton) csvButton.title = direct ? '选择“分别导出 / 合并导出”，文件直接下载到浏览器默认下载目录' : (desktop ? '选择 CSV 导出模式与保存位置' : '选择 CSV 导出模式');
}

function setIdleDeadline(projectId, deadline) {
  const value=Number(deadline);
  if(projectId && Number.isFinite(value) && value>0) state.idleDeadlines[projectId]=value;
  renderIdleCountdown();
}

function renderIdleCountdown() {
  // V2.6.3 removes the automatic-check-in countdown from the Editor UI.
  // The authoritative idle deadline remains server-side and is still tracked
  // transiently so lease recovery can preserve the original lifecycle clock.
}

function showLeaseBanner(message) {
  const banner=$('#leaseLostBanner'), label=$('#leaseLostMessage');
  if(label)label.textContent=message;
  banner?.classList.remove('hidden');
}

function hideLeaseBanner() { $('#leaseLostBanner')?.classList.add('hidden'); }

async function reacquireEditLease(projectIds=[]) {
  if(state.leaseRecoveryInFlight)return null;
  state.leaseRecoveryInFlight=true;
  try {
    const requested=[...new Set((projectIds||[]).filter(Boolean))];
    const result=await api('/api/auth/lease/reacquire',{method:'POST',body:JSON.stringify({project_ids:requested}),timeout:10000});
    (result.reacquired||[]).forEach(item=>setIdleDeadline(item.project_id,item.idle_check_in_deadline));
    if((result.failures||[]).length){
      const failure=result.failures[0];
      showLeaseBanner(`编辑租约已恢复，但模型状态发生变化：${failure.error||'无法恢复该模型编辑'}`);
      if(state.project?.id && (result.failures||[]).some(item=>item.project_id===state.project.id)){
        await loadProject(state.project.id,{force:true});
        state.editSessionMode='readonly';
        applyProjectAccess(); renderIdleCountdown();
      }
      toast(`模型编辑恢复失败：${failure.error||'状态已变化'}`,'error');
      return result;
    }
    state.leaseLost=false; state.leaseLostReason=null; hideLeaseBanner();
    // The lease banner closes below; no non-actionable success toast.
    return result;
  } catch(error) {
    showLeaseBanner(`编辑租约仍未恢复：${error.message||String(error)}。模型签出状态不会因 Lease 到期而自动改变。`);
    return null;
  } finally { state.leaseRecoveryInFlight=false; }
}

async function handleLeaseLost(payload={}) {
  state.leaseLost=true;
  state.leaseLostReason=payload.lease_lost_reason||'revoked';
  const reasonLabel={expired:'已到期',revoked:'已被收回',no_session:'会话不存在'}[state.leaseLostReason]||'已失效';
  showLeaseBanner(`编辑租约${reasonLabel}，模型仍保持原签出状态。正在尝试恢复编辑；也可点击“恢复编辑”重试。`);
  return reacquireEditLease(payload.checked_out_project_ids||[]);
}

async function runLeaseHeartbeat() {
  if(!state.auth || !['engineer','admin'].includes(state.auth.role) || state.leaseHeartbeatInFlight)return;
  state.leaseHeartbeatInFlight = true;
  try {
    const payload=await api('/api/auth/heartbeat',{method:'POST',body:'{}',timeout:5000});
    state.leaseTtlSeconds=Number(payload.lease_ttl_seconds)||state.leaseTtlSeconds;
    const networkWasDown=state.leaseHeartbeatFailures >= 3;
    state.leaseHeartbeatFailed=false;
    state.leaseHeartbeatFailures=0;
    if(payload.lease_active===false){
      const owned=(payload.checked_out_project_ids||[]).filter(Boolean);
      if(!owned.length && state.editSessionMode!=='persistent'){
        state.leaseLost=false; state.leaseLostReason=null; hideLeaseBanner();
        return;
      }
      await handleLeaseLost({...payload,checked_out_project_ids:owned});
      return;
    }
    if(networkWasDown && !state.leaseLost) hideLeaseBanner();
    if(state.leaseLost){state.leaseLost=false;state.leaseLostReason=null;hideLeaseBanner();}
  } catch(error) {
    console.warn('[lease-heartbeat] network failed:',error);
    state.leaseHeartbeatFailures=Math.min(8, state.leaseHeartbeatFailures+1);
    if(state.leaseHeartbeatFailures===3 && state.editSessionMode==='persistent' && !state.leaseLost) {
      showLeaseBanner('编辑连接连续三次未响应，正在后台重试。浏览器草稿继续保留；确认租约失效前不会主动签入。');
    }
    state.leaseHeartbeatFailed=true;
  } finally { state.leaseHeartbeatInFlight = false; }
}

function configureLeaseHeartbeat() {
  if(state.leaseHeartbeatTimer)clearInterval(state.leaseHeartbeatTimer);
  if(state.idleCountdownTimer)clearInterval(state.idleCountdownTimer);
  state.idleCountdownTimer=null;
  const periodMs=Math.max(30000,Math.min(60000,Math.floor(Number(state.leaseTtlSeconds||180)*1000/3)));
  state.leaseHeartbeatTimer=setInterval(()=>{void runLeaseHeartbeat();},periodMs);
  void runLeaseHeartbeat();
}

function bindLeaseRecoveryUi() {
  $('#leaseReacquireButton')?.addEventListener('click',()=>{
    const ids=state.project?.lifecycle?.status==='checked_out'?[state.project.id]:[];
    void reacquireEditLease(ids);
  });
  $('#editorCheckinButton')?.addEventListener('click',()=>{ void checkInCurrentEditor(); });
}

function applyRoleProjection() {
  const auth = state.auth || {};
  const isGuest = auth.role === 'guest';
  const canManageTypes = auth.role === 'admin' || Boolean(auth.admin_mode);
  const canManageAssets = ['engineer', 'admin'].includes(auth.role);
  document.body.classList.toggle('guest-role', isGuest);
  $('#authIdentity').textContent = `${auth.username} · ${roleLabel(auth.role)}${auth.admin_mode ? ' · 管理员模式' : ''}`;
  $('#authIdentity').classList.remove('hidden');
  $('#logoutButton').classList.toggle('hidden', Boolean(auth.single_user));
  $('#accountButton').classList.toggle('hidden', Boolean(auth.single_user) || !canManageAssets);
  const guestBlocked = [
    '#hubNewProjectButton','#hubImportProjectButton','#hubExportProjectButton','#hubImportBundleButton','#hubExportBundleButton',
    '#quickRunButton',
    '#undoButton','#redoButton','#validateButton','#saveButton',
  ];
  guestBlocked.forEach(selector => $(selector)?.classList.toggle('role-hidden', isGuest));
  ['#hubAddCategoryButton','#hubDeleteCategoryButton'].forEach(selector => $(selector)?.classList.toggle('role-hidden', !canManageTypes));
}

function renderStorageLocation(payload) {
  const status = $('#storageLocationStatus');
  if (!payload) return;
  $('#storageServerPath').value = payload.server_path || '';
  const defaultLevels = Number(payload.default_ancestor_levels || 2);
  const levelsInput = $('#storageAncestorLevels');
  levelsInput.dataset.defaultLevels = String(defaultLevels);
  levelsInput.value = Number(payload.ancestor_levels ?? defaultLevels);
  const helper = $('#storageLocationHelper');
  if (helper) helper.innerHTML = `当前部署：<b>${esc(payload.platform || 'Unknown')}</b>；系统默认向上 <b>${defaultLevels}</b> 级寻找 <code>V2_projec</code>。显式保存的设置优先。`;
  if (document.activeElement !== $('#storageBasePath')) $('#storageBasePath').value = payload.manual_base_path || '';
  $('#storageActiveRoot').value = payload.active_data_root || '';
  $('#storageCandidatePath').value = payload.candidate_path || '';
  const locked = Boolean(payload.environment_override);
  $('#storageSaveButton').disabled = locked || !payload.ok;
  $('#storageAncestorLevels').disabled = locked;
  $('#storageBasePath').disabled = locked;
  $('#storageProbeButton').disabled = locked;
  $('#storageBrowseButton').disabled = locked;
  status.classList.toggle('success', Boolean(payload.ok));
  status.classList.toggle('error', !payload.ok);
  status.textContent = locked
    ? `环境变量 MUJOCO_STUDIO_DATA 已锁定为：${payload.environment_override}`
    : (payload.ok
      ? `${payload.message || '查找成功'}${payload.candidate_path ? ` · ${payload.candidate_path}` : ''}`
      : (payload.message || '尚未识别到 V2_projec'));
}

async function loadStorageLocation() {
  const payload = await api('/api/admin/storage-location');
  renderStorageLocation(payload);
  return payload;
}

async function probeStorageLocation() {
  const payload = await api('/api/admin/storage-location/probe', {method:'POST', body:JSON.stringify({
    ancestor_levels:Number($('#storageAncestorLevels').value || $('#storageAncestorLevels').dataset.defaultLevels || 2),
    base_path:$('#storageBasePath').value.trim(),
  })});
  payload.active_data_root = $('#storageActiveRoot').value;
  renderStorageLocation(payload);
  return payload;
}

async function browseStorageLocation() {
  if (!state.capabilities?.server_file_dialogs) {
    toast('当前服务器未启用本机目录选择器；请直接填写服务器上的父目录或 V2_projec 路径。');
    return;
  }
  const initial = $('#storageBasePath').value.trim() || $('#storageCandidatePath').value.trim() || $('#storageServerPath').value.trim();
  const selected = await api(`/api/dialogs/select-directory?initial=${encodeURIComponent(initial)}&title=${encodeURIComponent('选择 V2_projec 或其父目录')}`, {method:'POST'});
  if (!selected.path) return;
  $('#storageBasePath').value = selected.path;
  await probeStorageLocation();
}

async function saveStorageLocation() {
  const probe = await probeStorageLocation();
  if (!probe.ok) throw new Error(probe.message || '未识别到可写的 V2_projec');
  const saved = await api('/api/admin/storage-location', {method:'PUT', body:JSON.stringify({
    ancestor_levels:Number($('#storageAncestorLevels').value || $('#storageAncestorLevels').dataset.defaultLevels || 2),
    base_path:$('#storageBasePath').value.trim(),
  })});
  renderStorageLocation(saved);
  $('#storageActiveRoot').value = saved.active_data_root || '';
  toast(`数据地址已保存：${saved.candidate_path}。重启 Server 后生效。`);
}

async function manageAccounts() {
  if (state.auth.role === 'engineer' && !state.auth.admin_mode) {
    const password = prompt('输入管理员模式密码（临时获得新增账号权限）');
    if (password == null) return;
    state.auth = await api('/api/auth/admin-mode', {method:'POST', body:JSON.stringify({password})});
    applyRoleProjection();
  }
  await refreshAccountList();
  $('#accountModeHint').textContent = state.auth.role === 'admin' ? '管理员：可新增和删除账号，并设置管理员模式密码。' : '工程师管理员模式：可新增和删除其他账号，不能修改管理员模式密码。';
  $('#adminModePasswordSection').classList.toggle('hidden', state.auth.role !== 'admin');
  $('#storageLocationSection').classList.toggle('hidden', state.auth.role !== 'admin');
  if (state.auth.role === 'admin') await loadStorageLocation();
  $('#accountDialog').showModal();
}

async function refreshAccountList() {
  const payload = await api('/api/auth/users');
  $('#accountList').innerHTML = payload.users.map(item => `<div><span><strong>${esc(item.username)}</strong><small>${esc(roleLabel(item.role))}${item.built_in ? ' · 唯一管理员账号' : ''}</small></span>${(state.auth.role === 'admin' || state.auth.admin_mode) && !item.built_in && item.username.toLowerCase() !== state.auth.username.toLowerCase() ? `<button class="button tiny danger" type="button" data-delete-account="${esc(item.username)}">删除</button>` : ''}</div>`).join('');
  $$('[data-delete-account]', $('#accountList')).forEach(button => button.addEventListener('click', async () => {
    const username = button.dataset.deleteAccount;
    if (!confirm(`确认删除账号 ${username}？该账号现有会话会立即失效。`)) return;
    try { await api(`/api/auth/users/${encodeURIComponent(username)}`, {method:'DELETE'}); await refreshAccountList(); }
    catch (error) { toast(error.message, 'error'); }
  }));
}

function bindAuthenticationUi() {
  $('#loginForm')?.addEventListener('keydown', event => {
    if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      event.currentTarget.requestSubmit();
    }
  });
  $('#loginForm')?.addEventListener('submit', async event => {
    event.preventDefault();
    $('#loginError').textContent = '';
    const submitButton = event.currentTarget.querySelector('button[type="submit"]');
    if (submitButton) {
      submitButton.disabled = true;
      submitButton.textContent = '正在验证…';
    }
    try {
      const loginResult=await api('/api/auth/login', {method:'POST', body:JSON.stringify({
        username:$('#loginUsername').value, password:$('#loginPassword').value,
      })});
      sessionStorage.setItem('mujocoStudioPendingLifecycleFailures',JSON.stringify(loginResult.pending_lifecycle_failures||[]));
      sessionStorage.setItem(HUB_ENTRY_STORAGE_KEY, 'zoomed');
      if (submitButton) submitButton.textContent = '验证通过 · 正在进入';
      await playLoginHubTransition();
      location.reload();
    } catch (error) {
      $('#loginError').textContent = error.message;
      if (submitButton) {
        submitButton.disabled = false;
        submitButton.textContent = '登录';
      }
      startLoginMetalPointerMotion();
    }
  });
  $('#logoutButton')?.addEventListener('click', async () => {
    try {
      const result = await api('/api/auth/logout', {method:'POST'});
      sessionStorage.setItem('mujocoStudioLogoutStatus', JSON.stringify(result));
      if (result.status === 'failed') {
        toast(`退出失败：${result.failures?.[0]?.error || '模型签入失败，请重试'}`, 'error');
        return;
      }
      location.reload();
    } catch (error) {
      toast(error.message || String(error), 'error');
    }
  });
  $('#accountButton')?.addEventListener('click', () => manageAccounts().catch(error => toast(error.message, 'error')));
  $('#accountCreateButton')?.addEventListener('click', async () => {
    const username=$('#accountUsername').value.trim(), password=$('#accountPassword').value, role=$('#accountRole').value;
    if (!username || !password) { toast('用户名和初始密码不可为空', 'error'); return; }
    try {
      await api('/api/auth/users', {method:'POST',body:JSON.stringify({username,password,role})});
      $('#accountUsername').value=''; $('#accountPassword').value=''; await refreshAccountList(); toast(`账号 ${username} 已新增`);
    } catch (error) { toast(error.message, 'error'); }
  });
  $('#adminModePasswordButton')?.addEventListener('click', async () => {
    const password=$('#adminModeNewPassword').value; if (!password) { toast('新密码不可为空','error'); return; }
    try { await api('/api/auth/admin-mode-password',{method:'PUT',body:JSON.stringify({password})}); $('#adminModeNewPassword').value=''; toast('管理员模式密码已更新，已有提权会话已降级'); }
    catch (error) { toast(error.message,'error'); }
  });
  $('#storageBrowseButton')?.addEventListener('click', () => browseStorageLocation().catch(error => toast(error.message, 'error')));
  $('#storageProbeButton')?.addEventListener('click', () => probeStorageLocation().catch(error => toast(error.message, 'error')));
  $('#storageSaveButton')?.addEventListener('click', () => saveStorageLocation().catch(error => toast(error.message, 'error')));
  $('#storageAncestorLevels')?.addEventListener('change', () => probeStorageLocation().catch(error => toast(error.message, 'error')));
  $('#storageBasePath')?.addEventListener('change', () => probeStorageLocation().catch(error => toast(error.message, 'error')));
}

function bindEditSessionUnload() {
  window.addEventListener('pagehide', () => {
    if (state.dirty || state.localDraftUiChanges.size) void persistLocalDraft();
    const context = routeContextFromLocation();
    if (context.kind !== 'editor' || !state.project?.id || !state.editSessionMode) return;
    const projectId = state.project.id;
    if (state.auth?.role === 'guest' || state.editSessionMode === 'readonly') {
      unregisterEditorWindow(projectId);
      return;
    }
    const url = `/api/projects/${encodeURIComponent(projectId)}/edit-session/leave`;
    const finalState = state.editSessionMode === 'persistent' && state.dirty
      ? {project:state.project}
      : {};
    const body = JSON.stringify(finalState);
    let queued = false;
    try {
      const payload = new Blob([body], {type:'application/json'});
      queued = Boolean(navigator.sendBeacon?.(url, payload));
    } catch (_) { /* fall through to keepalive */ }
    if (!queued) {
      try { fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body, keepalive:true, credentials:'same-origin'}); } catch (_) {}
    }
    unregisterEditorWindow(projectId);
  });
}

/** 带超时的 fetch：默认 5000ms；AbortController 兼容到老浏览器
 * 注意：api() 仍返回非 json 的报错；超时错误文案要明确
 */
function withTimeout(promise, ms, label = '请求') {
  if (ms == null || ms <= 0) return promise;
  let timer = null;
  const timeoutPromise = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error(`${label} 超时（${ms}ms 未响应）。请确认后端已启动且端口可达，或刷新重试。`)), ms);
  });
  return Promise.race([promise, timeoutPromise]).finally(() => { if (timer) clearTimeout(timer); });
}

/** 读取并应用 localStorage 中用户存的 UI 默认值。
 * 这是启动第一步，失败绝对不能打断 boot，否则前端看起来就会一直"正在连接/正在读取"。
 */
function safeApplyUiDefaults() {
  try {
    applyUiDefaults();
    bootMark('ui-defaults-applied');
  } catch (err) {
    bootMark('ui-defaults-failed', {error: String(err && err.message || err)});
    console.warn('[ui.defaults] 应用 UI 默认值失败，跳过：', err);
  }
}

let hubCatalogRecoveryTimer = null;
let hubCatalogRecoveryAttempts = 0;
function scheduleHubCatalogRecovery() {
  if (hubCatalogRecoveryTimer || routeContextFromLocation().kind !== 'hub' || !state.auth) return;
  const delay = Math.min(12000, 2000 * Math.pow(2, Math.min(hubCatalogRecoveryAttempts, 3)));
  hubCatalogRecoveryTimer = setTimeout(async () => {
    hubCatalogRecoveryTimer = null;
    if (routeContextFromLocation().kind !== 'hub' || !state.auth) return;
    try {
      await loadProjects(null);
      hubCatalogRecoveryAttempts = 0;
      renderHub();
    } catch (error) {
      if (error?.status === 401) return;
      hubCatalogRecoveryAttempts += 1;
      console.warn('[hub] catalog recovery retry failed:', error);
      scheduleHubCatalogRecovery();
    }
  }, delay);
}

async function boot() {
  bindAuthenticationUi();
  bindLeaseRecoveryUi();
  bindEditSessionUnload();
  bootMark('enter');
  window.__bootDiagnose = __BOOT_DIAGNOSE__;
  try {
    safeApplyUiDefaults();
  } catch (err) {
    // 兜底绝对不抛，否则 UI 状态永远挂在 loading
    bootMark('apply-defaults-crashed', {error: String(err && err.message || err)});
  }
  try {
    bindStaticEvents();
    registerUiDefaultsContextMenu();
    route();
    window.addEventListener('popstate', route);
    window.addEventListener('hashchange', () => { const legacy=location.hash.replace('#',''); if(legacy==='overview') navigateToPage('overview',{replace:true}); else if(EDITOR_PAGES.has(legacy)&&state.project?.id) navigateToPage(legacy,{replace:true}); });
  } catch (err) {
    bootMark('pre-http-setup-crashed', {error: String(err && err.message || err)});
    try { toast('启动初始化失败：' + (err.message || String(err)), 'error'); } catch (_) {}
    $('#apiDot').classList.add('error');
    $('#apiStatus').textContent = '初始化失败（打开控制台查看详情）';
    finishHubEntryTransition();
    return;
  }
  bootMark('pre-http-ready');

  // 协议探测：
  // Studio 后端：GET /api/health，返回 {version, mujoco_available, data_root}
  // Kernel 后端（mujoco_v3.main:app）：GET /health，返回 {status, service, version}
  // Studio 后端还会有 /api/projects，Kernel 只有 /api/state + /api/commands
  // 先试 /api/health（Studio），如果 4xx/明确 "后端没有返回 JSON 却返回了 HTML/非 JSON" 这类仍会在 api() 里被 throw，
  // 但如果是 404 且 path 不存在，我们再试 /health；成功则提示用户后端和前端协议不匹配。
  let health = null;
  let backendKind = 'unknown';
  let kernelHealth = null;
  try {
    health = await withTimeout(api('/api/health'), 4500, '/api/health');
    backendKind = 'studio';
  } catch (studioErr) {
    const msg = String((studioErr && studioErr.message) || studioErr || '');
    bootMark('health-studio-failed', {error: msg});
    const looksLikePathMissing = /404|Not Found|接口 .* 返回的不是 JSON|后端没有返回 JSON/i.test(msg) || /\/api\/health/.test(msg);
    if (looksLikePathMissing) {
      try {
        kernelHealth = await withTimeout(api('/health'), 3500, '/health');
        backendKind = 'kernel';
        bootMark('health-kernel-ok', {version: kernelHealth && kernelHealth.version, service: kernelHealth && kernelHealth.service});
      } catch (kernelErr) {
        bootMark('health-kernel-failed', {error: String((kernelErr && kernelErr.message) || kernelErr || '')});
      }
    }
    if (!kernelHealth) {
      // 不是 kernel 也不是 studio：走原来的通用错误
      $('#apiDot').classList.add('error');
      $('#apiStatus').textContent = 'API 连接失败（超时/端口不通）';
      toast(`无法连接 API：${msg}。请确认后端服务已启动（MuJoCo Studio 推荐命令：python mujoco_studio/run.py）。`, 'error');
      try {
        if (!state.projects || !state.projects.length) renderHubProjects([]);
      } catch (_) {}
      finishHubEntryTransition();
      return;
    }
  }

  if (backendKind === 'kernel') {
    // Kernel 后端不匹配：明确告诉用户问题在哪 + 解决方法，而不是一直"正在读取项目"
    $('#apiDot').classList.add('error');
    const v = (kernelHealth && kernelHealth.version) ? ` ${kernelHealth.version}` : '';
    $('#apiStatus').textContent = `检测到 MuJoCo V3 Kernel 后端${v}（与 Studio 前端协议不匹配）`;
    const line1 = `当前后端是 V3 kernel（接口为 /health、/api/state、/api/commands），但这套前端需要 MuJoCo Studio REST 后端（接口为 /api/health、/api/projects 等）。`;
    const line2 = `解决方法：请关掉现有的 8000 端口后端，改从工作目录执行：`;
    const line3 = `  cd MuJoCo_Studio_V2.16.11.6_Integrated/Server ; python run.py`;
    const port = Number(location.port) || state.networkPorts.hub;
    const line4 = `它会在端口 ${port} 同时提供 API 和 frontend 静态页面，浏览器打开 http://127.0.0.1:${port} 即可。`;
    toast(`${line1}\n${line2}\n${line3}\n${line4}`, 'error');
    $('#hubProjectList').textContent = '前后端协议不匹配（Kernel vs Studio REST）。请启动 MuJoCo Studio 后端：python mujoco_studio/run.py';
    $('#hubProjectList').classList.add('empty-state');
    finishHubEntryTransition();
    return;
  }

  // 下面是 Studio 后端的正常路径
  try {
    bootMark('health-ok', {version: health && health.version, mujoco_available: health && health.mujoco_available});
    $('#apiDot').classList.add('ok');
    $('#apiStatus').textContent = `API ${health.version}${health.mujoco_available ? ' · MuJoCo ready' : ''}`;
    $('#hubProjectRoot').textContent = '项目目录 · 服务端托管';
    $('#hubProjectRoot').title = '项目文件由认证 Web 文件通道管理，不向浏览器暴露服务器绝对路径';
    // The existing /api/health response is the only browser-facing port source.
    // Do not tie local Client/VZ addresses to the Hub HTTP listener's port.
    const suppliedPorts = health.network_ports || {};
    const validPort = (value, fallback) => Number.isInteger(value) && value >= 1 && value <= 65535 ? value : fallback;
    state.networkPorts = {
      hub: validPort(suppliedPorts.hub, state.networkPorts.hub),
      client: validPort(suppliedPorts.client, state.networkPorts.client),
      vz: validPort(suppliedPorts.vz, state.networkPorts.vz),
    };
    state.localClientUrl = `http://127.0.0.1:${state.networkPorts.client}`;
    state.capabilities = {...state.capabilities, ...(health.capabilities || {})};
    state.leaseTtlSeconds = Number(health.lease_ttl_seconds) || 180;
    state.interactionCommitDebounceMs = Number(health.interaction_commit_debounce_ms) || 400;
    applyCapabilityProjection();
    const archiveLimit = Number(health.max_archive_versions) || 20;
    state.archiveLimit = archiveLimit;
    state.trashRetentionDays = Number(health.trash_retention_days) || 7;
    $('#saveButton').title = `手动保存历史版本（与基线记录合计最多保留最近 ${archiveLimit} 个），当前模型工作版本仍自动保存`;
  } catch (error) {
    bootMark('health-render-failed', {error: String(error && error.message || error)});
  }

  try {
    state.auth = await api('/api/auth/me');
    hideLogin();
    applyRoleProjection();
    applyCapabilityProjection();
    configureLeaseHeartbeat();
    finishHubEntryTransition();
    try {
      const pendingFailures=JSON.parse(sessionStorage.getItem('mujocoStudioPendingLifecycleFailures')||'[]');
      sessionStorage.removeItem('mujocoStudioPendingLifecycleFailures');
      if(Array.isArray(pendingFailures)&&pendingFailures.length){
        const label=$('#lifecycleFailureMessage');
        if(label) {
          const ids=pendingFailures.map(item=>String(item.project_id||'')).filter(Boolean);
          label.textContent=`有 ${ids.length} 个历史自动签入任务未能完成。模型仍保持原签出状态，请管理员核对租约与具体失败原因后逐个处理（不要直接批量强制签入）。示例：${ids.slice(0,3).join('、')}${ids.length>3?'…':''}`;
          label.title=ids.join('、');
        }
        $('#lifecycleFailureBanner')?.classList.remove('hidden');
      }
    } catch(error) { console.warn('[lifecycle-failures] restore failed:',error); }
  } catch (error) {
    showLogin(error.message);
    return;
  }

  // 启动阶段：把 loadProjects / loadSkills / startJobPolling 拆开，各自 try/catch 独立写 bootMark，
  // 确保任何一步失败都不会让整个 boot 看起来"自动结束"。
  window.__booting = true;
  try {
    const bootRoute = routeContextFromLocation();
    if (bootRoute.kind === 'editor') {
      await activateEditorRoute(bootRoute);
    } else {
      await withTimeout(loadProjects(null), 20000, '加载项目列表');
      window.name = 'mujoco-studio-hub';
      if (location.pathname !== HUB_PATH || location.hash) history.replaceState(null, '', HUB_PATH);
      route();
    }
    bootMark('load-projects-ok', {projectsLen: state.projects.length, hubSelectedProjectId: state.hubSelectedProjectId});
  } catch (error) {
    const msg = String(error && error.message || error || '');
    bootMark('load-projects-failed', {error: msg});
    console.error('[boot] loadProjects failed:', error);
    toast(`加载项目失败：${msg}。请查看后端日志中 /api/projects 相关报错。`, 'error');
    if (routeContextFromLocation().kind === 'hub') {
      const list = $('#hubProjectList');
      if (list && !state.projects.length) {
        list.classList.add('empty-state');
        list.textContent = '项目列表暂时不可用（服务器可能正在复制基线文件），将自动重试。已保存的项目不会被清空。';
      }
      scheduleHubCatalogRecovery();
    }
  }
  try {
    if (state.auth?.role !== 'guest') await withTimeout(loadSkills(), 12000, '加载技能列表');
    bootMark('load-skills-ok', {skillsLen: state.skills.length});
  } catch (error) {
    const msg = String(error && error.message || error || '');
    bootMark('load-skills-failed', {error: msg});
    console.warn('[boot] loadSkills failed:', error);
    toast(`加载技能失败：${msg}（不影响项目使用）`, 'error');
  }
  try {
    if (state.auth?.role !== 'guest') startJobPolling();
    bootMark('job-polling-started');
  } catch (error) {
    const msg = String(error && error.message || error || '');
    bootMark('job-polling-failed', {error: msg});
    console.warn('[boot] startJobPolling failed:', error);
  } finally {
    // 无论是否有步骤失败，都清掉 booting 标志，避免后续用户切项目时被误判为"首次启动"
    setTimeout(() => { try { delete window.__booting; } catch (_) { window.__booting = false; } }, 0);
  }
  bootMark('finished');
  finishHubEntryTransition();
}

let hubFocusRefreshAt = 0;
let hubLastFullRefreshAt = 0;
let hubSummaryRequest = null;
const HUB_REFRESH_TTL_MS = 10 * 60 * 1000;
const HUB_CATALOG_REFRESH_MS = 25 * 1000;

function mergeHubCatalogCritical(incoming, existing = []) {
  // A cold/temporarily unavailable summary is not evidence that a previously
  // verified frozen badge disappeared.  Never copy values across identities.
  const previous = new Map((existing || []).map(item => [String(item.id), item]));
  return (incoming || []).map(item => {
    const old = previous.get(String(item.id));
    if (!old || !['pending', 'unavailable'].includes(String(item.critical_source || ''))) return item;
    if (!Array.isArray(old.critical_data) || !old.critical_data.length ||
        !['baseline', 'archive', 'current'].includes(String(old.critical_source || ''))) return item;
    const tokenMatch = Boolean(item.critical_token && old.critical_token &&
      item.critical_token === old.critical_token);
    // Pre-V2.16.11.5 per-account caches do not carry critical_token.  For a
    // baseline only, frozen created_at plus id is sufficient to recover it.
    const legacyFrozenMatch = !old.critical_token && !item.critical_token?.startsWith('archive:') &&
      item.lifecycle_status === 'baseline' && old.lifecycle_status === 'baseline' &&
      old.critical_source === 'baseline' && Boolean(item.baseline_created_at) &&
      String(item.baseline_created_at) === String(old.baseline_created_at || '');
    if (!tokenMatch && !legacyFrozenMatch) return item;
    if (String(item.lifecycle_status) !== String(old.lifecycle_status)) return item;
    return {...item, critical_data:old.critical_data, critical_source:old.critical_source};
  });
}

const HUB_BASELINE_BADGE_RETRY_DELAYS_MS = [1500, 3000, 6000, 12000];
let hubBaselineBadgeRetryTimer = null;
let hubBaselineBadgeRetryCount = 0;
function scheduleHubBaselineBadgeRetry() {
  const hasPendingBaseline = (state.projects || []).some(item =>
    item.lifecycle_status === 'baseline' && item.critical_source === 'pending');
  if (!hasPendingBaseline) {
    if (hubBaselineBadgeRetryTimer !== null) clearTimeout(hubBaselineBadgeRetryTimer);
    hubBaselineBadgeRetryTimer = null;
    hubBaselineBadgeRetryCount = 0;
    return;
  }
  if (!state.auth || routeContextFromLocation().kind !== 'hub' || document.hidden ||
      hubBaselineBadgeRetryTimer !== null ||
      hubBaselineBadgeRetryCount >= HUB_BASELINE_BADGE_RETRY_DELAYS_MS.length) return;
  const delay = HUB_BASELINE_BADGE_RETRY_DELAYS_MS[hubBaselineBadgeRetryCount++];
  hubBaselineBadgeRetryTimer = setTimeout(() => {
    hubBaselineBadgeRetryTimer = null;
    if (!state.auth || routeContextFromLocation().kind !== 'hub' || document.hidden) return;
    // This is still only the cheap summary; never hydrate all project previews.
    refreshHubCatalogSummary().catch(error => console.warn('[hub-baseline-badge] retry failed:', error));
  }, delay);
}

async function refreshHubCatalogSummary() {
  // Unlike loadProjects this never requests all project previews, model types
  // or recycle-bin contents. It only replaces badges after a valid response.
  if (hubSummaryRequest) return hubSummaryRequest;
  const task = (async () => {
    const latest = await api('/api/projects?detail=summary', {timeout:10000});
    if (!Array.isArray(latest) || !state.auth || routeContextFromLocation().kind !== 'hub') return;
    const previous = new Map((state.projects || []).map(item => [String(item.id), item]));
    const merged = mergeHubCatalogCritical(latest, state.projects);
    const changed = merged.length !== previous.size || merged.some(item => {
      const old = previous.get(String(item.id));
      return !old || old.updated_at !== item.updated_at || old.name !== item.name ||
        old.category !== item.category || old.lifecycle_status !== item.lifecycle_status ||
        old.critical_source !== item.critical_source || old.critical_token !== item.critical_token ||
        JSON.stringify(old.critical_data || []) !== JSON.stringify(item.critical_data || []);
    });
    if (!changed) { scheduleHubBaselineBadgeRetry(); return; }
    const selectedId = state.hubSelectedProjectId;
    const oldSelected = previous.get(String(selectedId));
    const newSelected = merged.find(item => item.id === selectedId);
    state.projects = merged;
    scheduleHubBaselineBadgeRetry();
    if (newSelected && state.hubPreview?._summary_only && state.hubPreview?.id === selectedId) {
      primeHubPreviewFromCatalog(selectedId);
    }
    if (!state.hubArchiveDragActive) renderHub();
    if (newSelected && oldSelected && newSelected.updated_at !== oldSelected.updated_at &&
        !state.dirty && !state.hubPreview?._summary_only && state.hubPreview?.id === selectedId) {
      // Only the already-selected model may load its full preview, never all rows.
      void loadHubPreview(selectedId, {force:true, waitForMetadata:false});
    }
  })();
  hubSummaryRequest = task;
  try { await task; } finally { if (hubSummaryRequest === task) hubSummaryRequest = null; }
}
window.addEventListener('focus', () => {
  if (!state.auth || routeContextFromLocation().kind !== 'hub') return;
  const now = Date.now(); if (now - hubFocusRefreshAt < HUB_CATALOG_REFRESH_MS) return;
  hubFocusRefreshAt = now;
  const refresh = now - hubLastFullRefreshAt >= HUB_REFRESH_TTL_MS
    ? loadProjects(state.hubSelectedProjectId)
    : refreshHubCatalogSummary();
  refresh.catch(error => console.warn('[hub-focus-refresh] failed', error));
});
function startHubRefreshTimer() {
  if (state.hubRefreshTimer) return;
  state.hubRefreshTimer = setInterval(() => {
    if (!state.auth || routeContextFromLocation().kind !== 'hub' || document.hidden) return;
    hubFocusRefreshAt = Date.now();
    const refresh = Date.now() - hubLastFullRefreshAt >= HUB_REFRESH_TTL_MS
      ? loadProjects(state.hubSelectedProjectId)
      : refreshHubCatalogSummary();
    refresh.catch(error => console.warn('[hub-periodic-refresh] failed', error));
  }, HUB_CATALOG_REFRESH_MS);
}

async function refreshHubVzPushStatuses() {
  if (!state.auth || state.auth.role === 'guest' || routeContextFromLocation().kind !== 'hub' || document.hidden) return;
  try {
    const payload = await api('/api/vz-push-status', {timeout:3500});
    const items = Array.isArray(payload?.projects) ? payload.projects : [];
    const byId = new Map(items.map(item => [String(item.id || ''), item.vz_push || {enabled:false}]));
    let changed = false;
    state.projects = state.projects.map(project => {
      const next = byId.get(String(project.id || ''));
      if (!next) return project;
      const before = project.vz_push || {enabled:false};
      if (Boolean(before.enabled) !== Boolean(next.enabled) || String(before.model_id || '') !== String(next.model_id || '') || String(before.updated_at || '') !== String(next.updated_at || '')) changed = true;
      return {...project, vz_push:next};
    });
    if (state.hubPreview?.id) {
      const next = byId.get(String(state.hubPreview.id));
      if (next) {
        const before = state.hubPreview.vz_push || {enabled:false};
        if (Boolean(before.enabled) !== Boolean(next.enabled) || String(before.model_id || '') !== String(next.model_id || '') || String(before.updated_at || '') !== String(next.updated_at || '')) changed = true;
        state.hubPreview.vz_push = next;
      }
    }
    if (changed && !state.hubArchiveDragActive) renderHub();
  } catch (error) {
    console.warn('[hub-vz-status] refresh failed', error);
  }
}

function startHubVzStatusTimer() {
  if (state.hubVzStatusTimer) return;
  state.hubVzStatusTimer = setInterval(() => { void refreshHubVzPushStatuses(); }, 30000);
}
startHubRefreshTimer();
startHubVzStatusTimer();

function flattenModelTypes(nodes, depth = 0) {
  return (nodes || []).flatMap(node => [{...node, depth}, ...flattenModelTypes(node.children || [], depth + 1)]);
}
function flattenVisibleModelTypes(nodes, depth = 0) {
  return (nodes || []).flatMap(node => {
    const current = {...node, depth};
    return state.hubCollapsedModelTypes.has(node.path) ? [current] : [current, ...flattenVisibleModelTypes(node.children || [], depth + 1)];
  });
}
function collapsibleModelTypePaths() {
  return flattenModelTypes(state.modelTypes).filter(node => node.path !== 'None' && Boolean(node.children?.length)).map(node => node.path);
}
const HUB_FOLD_STATE_KEY = 'mujoco_studio.hub_folder_folds.v1';
function persistHubCollapseState() {
  try { localStorage.setItem(HUB_FOLD_STATE_KEY, JSON.stringify([...state.hubCollapsedModelTypes])); }
  catch (error) { console.warn('Hub 折叠状态保存失败', error); }
}
function syncHubCollapseState() {
  const validPaths = new Set(flattenModelTypes(state.modelTypes).map(node => node.path));
  if (!state.hubCollapseInitialized) {
    let restored = null;
    try { const raw = JSON.parse(localStorage.getItem(HUB_FOLD_STATE_KEY)); if (Array.isArray(raw)) restored = raw; } catch (_) {}
    const valid = new Set(flattenModelTypes(state.modelTypes).map(node => node.path));
    state.hubCollapsedModelTypes = new Set(restored ? restored.filter(path => typeof path === 'string' && valid.has(path)) : collapsibleModelTypePaths());
    state.hubCollapseInitialized = true;
    return;
  }
  state.hubCollapsedModelTypes = new Set([...state.hubCollapsedModelTypes].filter(path => validPaths.has(path)));
}
function resetEditorLayoutDefaults() {
  state.editorLayout.meshTwoColumns = true;
  state.editorLayout.driveTwoColumns = true;
  state.editorLayout.driveColumnPercent = 50; // visual session state; never ProjectSpec
}
function currentHubImportCategory() {
  return state.hubCategory && state.hubCategory !== '__recycle_bin__' ? state.hubCategory : 'None';
}

function hubBaselineFrozenAt(project) {
  return String(project?.baseline_created_at || project?.updated_at || '');
}

function hubCategoryProjects(category = state.hubCategory) {
  const selected = String(category || 'None');
  const direct = state.projects.filter(project => String(project?.category || 'None') === selected);
  const descendantPrefix = selected === 'None' ? '' : `${selected}/`;
  const latestBaselineByFolder = new Map();
  (state.projects || []).forEach(project => {
    if (projectStatus(project) !== 'baseline') return;
    const projectCategory = String(project?.category || 'None');
    const isDescendant = selected === 'None'
      ? projectCategory !== 'None'
      : projectCategory.startsWith(descendantPrefix);
    if (!isDescendant) return;
    const current = latestBaselineByFolder.get(projectCategory);
    const projectKey = `${hubBaselineFrozenAt(project)}|${String(project?.updated_at || '')}|${String(project?.id || '')}`;
    const currentKey = current
      ? `${hubBaselineFrozenAt(current)}|${String(current?.updated_at || '')}|${String(current?.id || '')}`
      : '';
    if (!current || projectKey > currentKey) latestBaselineByFolder.set(projectCategory, project);
  });
  return [...direct, ...latestBaselineByFolder.values()];
}
let activeModelTypeDrag = '';
let activeDistancePairDragId = '';
function modelTypeSiblingPaths(parentPath = '') {
  if (!parentPath) return (state.modelTypes || []).map(node => node.path).filter(path => path !== 'None');
  const parent = flattenModelTypes(state.modelTypes).find(node => node.path === parentPath);
  return (parent?.children || []).map(node => node.path);
}
function clearModelTypeDropHints() {
  $$('.hub-category.drag-over,.hub-category.drag-before,.hub-category.drag-inside,.hub-category.drag-after').forEach(row => {
    row.classList.remove('drag-over','drag-before','drag-inside','drag-after');
  });
}
function clearDistancePairDropHints() {
  $$('.pair-card-v2134.pair-drop-before,.pair-card-v2134.pair-drop-after').forEach(card => {
    card.classList.remove('pair-drop-before','pair-drop-after');
  });
}
function reorderDistancePairList(list, draggedPairId, targetPairId, before) {
  if (!Array.isArray(list) || !draggedPairId || !targetPairId || draggedPairId === targetPairId) return false;
  const fromIndex = list.findIndex(item => item.id === draggedPairId);
  const targetIndex = list.findIndex(item => item.id === targetPairId);
  if (fromIndex < 0 || targetIndex < 0) return false;
  const [item] = list.splice(fromIndex, 1);
  const targetAfterRemoval = list.findIndex(pair => pair.id === targetPairId);
  list.splice(targetAfterRemoval + (before ? 0 : 1), 0, item);
  return true;
}
function modelTypeDropPlan(row, event, draggedType) {
  if (!row || !draggedType) return null;
  if (row.dataset.modelRoot === 'true') {
    return {targetParent:'', before:'', mode:'inside', targetLabel:state.projectRootName || '项目'};
  }
  const target = row.dataset.modelType;
  if (!target || target === draggedType) return null;
  const rect = row.getBoundingClientRect();
  const ratio = Math.max(0, Math.min(1, (event.clientY - rect.top) / Math.max(1, rect.height)));
  const targetParent = target.split('/').slice(0,-1).join('/');
  const siblings = modelTypeSiblingPaths(targetParent).filter(path => path !== draggedType);
  const targetIndex = siblings.indexOf(target);
  if (ratio < .28) return {targetParent, before:target, mode:'before', targetLabel:target};
  if (ratio > .72) return {targetParent, before:targetIndex >= 0 ? (siblings[targetIndex + 1] || '') : '', mode:'after', targetLabel:target};
  return {targetParent:target, before:'', mode:'inside', targetLabel:target};
}
const encodePath = value => String(value || '').split('/').map(encodeURIComponent).join('/');

function clearHubProjectSelection({clearTypeSummary = true} = {}) {
  state.hubSelectedProjectId = null;
  state.hubPreview = null;
  state.hubFiles = null;
  state.hubVersions = [];
  state.hubPreviewVersionId = null;
  state.hubPreviewLoading = false;
  state.hubInspectorAssetLoading = false;
  state.modelAssetManager = {category:'', folders:[], selected:'', files:[], root:''};
  state.modelAssetManagerContext = {mode:'manage', projectId:'', category:'', current:'', editable:false, frozen:false};
  if (clearTypeSummary) state.hubTypeSummary = null;
  document.querySelector('.hub-gantt-preview-floating')?.remove();
  const gantt = $('#hubGanttQuick');
  if (gantt) gantt.hidden = true;
}

async function _loadProjects(preferredId = null, {editorOnly = false} = {}) {
  const cachedProjects = window.MuJoCoLocalDrafts?.readCatalog(state.auth?.username);
  if (!editorOnly && cachedProjects?.length && !state.projects.length) {
    state.projects = cachedProjects;
    try { renderHub(); } catch (error) { console.warn('[hub-cache] early render failed', error); }
  }
  const projectRequest = api('/api/projects?detail=summary', {timeout: 8000}).catch(error => {
    if (cachedProjects?.length && !editorOnly && error?.status !== 401) {
      toast('服务器目录暂不可达，已显示本账号的最近 Hub 缓存；在线后自动刷新。', 'info', 6000);
      return cachedProjects;
    }
    throw error;
  });
  const categoryRequest = (editorOnly || state.auth?.role === 'guest') ? Promise.resolve(null) : api('/api/model-types', {timeout: 8000}).catch(error => {
    if (error?.status === 401) throw error;
    console.warn('[hub] 模型类型目录暂不可用，项目卡片继续显示:', error);
    return null;
  });
  const recycleRequest = (!editorOnly && ['engineer','admin'].includes(state.auth?.role))
    ? api('/api/recycle-bin', {timeout:8000}).catch(error => { console.warn('[recycle-bin] load failed:', error); return []; })
    : Promise.resolve([]);
  // The model catalog is the first paint.  Never hold it behind model-type
  // metadata, trash enumeration, badge calculation or a slow baseline fork.
  const projects = await projectRequest;
  const previousCatalog = state.projects.length ? state.projects : (cachedProjects || []);
  state.projects = Array.isArray(projects) ? mergeHubCatalogCritical(projects, previousCatalog) : [];
  if (!editorOnly) scheduleHubBaselineBadgeRetry();
  if (!editorOnly && routeContextFromLocation().kind === 'hub') {
    try { renderHub(); } catch (error) { console.warn('[hub] first catalog paint failed:', error); }
  }
  const [categoryPayload, recycleBin] = await Promise.all([categoryRequest, recycleRequest]);
  if (Array.isArray(projects) && projects !== cachedProjects)
    window.MuJoCoLocalDrafts?.saveCatalog(state.auth?.username, state.projects);
  hubLastFullRefreshAt = Date.now();
  state.recycleBin = Array.isArray(recycleBin) ? recycleBin : [];
  const availableTrashIds = new Set(state.recycleBin.map(item => String(item.trash_id || '')).filter(Boolean));
  state.hubSelectedTrashIds = new Set([...state.hubSelectedTrashIds].filter(id => availableTrashIds.has(id)));
  if (categoryPayload) {
    state.modelTypes = Array.isArray(categoryPayload?.tree) ? categoryPayload.tree : [];
    state.categories = flattenModelTypes(state.modelTypes).map(item => item.path);
    syncHubCollapseState();
    state.projectRootName=categoryPayload?.project_name||'项目';
    if($('#hubProjectRoot')){$('#hubProjectRoot').textContent=state.projectRootName;$('#hubProjectRoot').title=`项目：${state.projectRootName}；${categoryPayload?.root||''}`;}
  }
  if (!state.projects.length && !editorOnly && state.auth?.role !== 'guest') {
    try {
      const created = await api('/api/projects', {method: 'POST', body: JSON.stringify({name: 'My first mechanism', demo: true}), timeout: 15000});
      if (created && created.id) {
        const refreshed = await Promise.all([api('/api/projects?detail=summary'), api('/api/model-types')]);
        state.projects = refreshed[0] || [];
        state.modelTypes = Array.isArray(refreshed[1]?.tree) ? refreshed[1].tree : [];
        state.categories = flattenModelTypes(state.modelTypes).map(item => item.path);
        syncHubCollapseState();
      }
    } catch (createErr) {
      console.warn('[boot] 无项目且创建默认项目失败，跳过：', createErr);
      state.projects = [];
      state.categories = state.categories || [];
    }
    if (!state.projects.length) {
      try { if (typeof renderHub === 'function') renderHub(); } catch (_) {}
      return;
    }
  }
  const selectedStillExists = state.projects.some(item => item.id === state.hubSelectedProjectId);
  const requested = preferredId && state.projects.some(item => item.id === preferredId) ? preferredId : null;
  const editorTarget = requested || state.project?.id || (selectedStillExists ? state.hubSelectedProjectId : null) || state.projects[0]?.id || null;
  const target = editorOnly ? editorTarget : (requested || (selectedStillExists ? state.hubSelectedProjectId : null));
  if (editorOnly) return target;
  if (target) {
    state.hubSelectedProjectId = target;
    primeHubPreviewFromCatalog(target, {preserveExisting:true});
  } else {
    // Hub refresh starts from an explicit empty selection. Do not silently reuse
    // the first catalog row or stale inspector state from the previous page life.
    clearHubProjectSelection();
  }

  // Render the catalog immediately. Model body/preview hydration continues below
  // and must not gate the user seeing the Hub list.
  try { renderHub(); } catch (_) {}
  if (!target) {
    return null;
  }
  try {
    await loadHubPreview(target, {waitForMetadata:false});
  } catch (previewErr) {
    console.warn('[boot] loadHubPreview failed:', previewErr);
  }
}

let hubProjectsRequest = null;
async function loadProjects(preferredId = null, options = {}) {
  const key = `${preferredId || ''}:${options.editorOnly ? 'editor' : 'full'}`;
  if (hubProjectsRequest?.key === key) return hubProjectsRequest.promise;
  const promise = _loadProjects(preferredId, options);
  hubProjectsRequest = {key, promise};
  try { return await promise; } finally { if (hubProjectsRequest?.promise === promise) hubProjectsRequest = null; }
}

async function loadProject(projectId, {force = false, initialProject = null} = {}) {
  // 首次启动（__booting）或强制加载时跳过 confirm，避免"页面看起来什么都没做就结束了"
  if (!force && !window.__booting && state.dirty) {
    if (!confirm('当前项目有尚未自动提交的修改，确定切换吗？')) return;
  }
  if (state.localDraftTimer) { clearTimeout(state.localDraftTimer); state.localDraftTimer = null; }
  if (state.dirty || state.localDraftUiChanges.size) await persistLocalDraft();
  cancelInteractionCommit();
  // Finish any optimistic UI-only writes before loading an authoritative mirror.
  // This also keeps project switches from abandoning the tail of uiCommitChain.
  await state.uiCommitChain.catch(() => null);
  if(state.animationBlobUrl){URL.revokeObjectURL(state.animationBlobUrl);state.animationBlobUrl=null;$('#embeddedAnimationFrame')?.removeAttribute('src');}
  $('#embeddedAnimationFrame')?.classList.add('hidden'); if($('#fullscreenEmbeddedAnimation'))$('#fullscreenEmbeddedAnimation').disabled=true;
  const loadRevision = ++state.projectLoadRevision;
  let project = null; let mirror = null;
  try {
    [project, mirror] = await Promise.all([
      initialProject ? Promise.resolve(initialProject) : api(`/api/projects/${projectId}`, {timeout: 12000}),
      state.auth?.role === 'guest' ? Promise.resolve({state:{ui:{}}}) :
        api(`/api/projects/${projectId}/state?detail=ui`, {timeout:2500}).catch(error => {
          if (error?.status===401) throw error; // Do not bypass authentication.
          console.warn('[editor-entry] optional layout state unavailable; opening with defaults:',error);
          return {state:{ui:{}}};
        }),
    ]);
  } catch (err) {
    // 即使某个子请求失败，也尽量把已经拿到的先填进去（或者明确抛错交给上层兜底）
    throw err;
  }
  state.project = project;
  state.localDraftBaseServerProject = deepClone(project);
  state.localDraftRestored = false;
  state.localDraftUiChanges = new Map();
  state.localDraftHistory = [];
  state.localDraftHistoryIndex = -1;
  state.project.solver_mode = state.project.solver_mode || 'kinematic';
  state.project.kinematic_closures = state.project.kinematic_closures || [];
  state.project.simulation = state.project.simulation || {};
  Object.assign(state.project.simulation, {
    engine: 'mujoco',
    gravity_m_s2: state.project.simulation.gravity_m_s2 ?? 9.81,
    ground_enabled: state.project.simulation.ground_enabled ?? true,
    ground_friction: state.project.simulation.ground_friction ?? .8,
    ground_collision_margin_mm: state.project.simulation.ground_collision_margin_mm ?? 0,
    contact_response_time_s: state.project.simulation.contact_response_time_s ?? .025,
    contact_damping_ratio: state.project.simulation.contact_damping_ratio ?? 2,
    contact_impedance_min: state.project.simulation.contact_impedance_min ?? .95,
    contact_impedance_max: state.project.simulation.contact_impedance_max ?? .99,
    contact_impedance_width_m: state.project.simulation.contact_impedance_width_m ?? .001,
  });
  state.llmConfig = null; state.agentConversation = [];
  state.companionTravels = new Map();
  state.expandedLayerAdvanced = new Set();
  state.activeCursorIndex = 0;
  state.ui = (mirror && mirror.state && mirror.state.ui) || {};
  state.uiRevision = 0;
  state.uiPersistedRevision = 0;
  // 项目 UI 状态载入后再覆盖用户默认值；boot 早期应用会被上面一行替换掉。
  safeApplyUiDefaults();
  state.expandedSegments = new Set(
    Object.entries((state.ui.drives && state.ui.drives.expanded_segments) || {})
      .filter(([, open]) => open).map(([key]) => key)
  );
  state.project.result_layout = state.project.result_layout || {axes:[], cursor_times:[], height:80};
  state.project.result_layout.axes = state.project.result_layout.axes || [];
  state.project.quick_optimization ||= {version:1,enabled:false,name:'快速寻优工作流',steps:[],last_run:{}};
  state.latestSimulation = null;
  state.baseSimulationSchedule = [];
  state.simulationSchedule = [];
  // Schedule/preview may be computationally expensive; open the editor first.
  // A guarded idle task fills in schedule-derived panels without blocking entry.
  state.resultAutoSimulationPending = false;
  state.resultViewerCurveOverrides = {projectId:projectId, sources:{}};
  state.distanceCurveSession = null;
  state.distanceLayoutConsentProjectId = null;
  activeLibraryTimeSeries = null;
  state.eventCursor = 0;
  state.selectedLayerId = (state.project.layers || []).some(layer => layer.id === state.selectedLayerId)
    ? state.selectedLayerId
    : (state.project.layers && state.project.layers[0] && state.project.layers[0].id) || null;
  clearDirty();
  clearArchiveDirty();
  await recoverLocalDraftForProject(projectId);
  if (!state.localDraftRestored || !state.localDraftHistory.length) {
    state.localDraftHistory = [deepClone(state.localDraftRestored ? project : state.project)];
    if (state.localDraftRestored && state.dirty) state.localDraftHistory.push(deepClone(state.project));
    state.localDraftHistoryIndex = state.localDraftHistory.length - 1;
  }
  markJsonEditorStale();
  try { renderAll(); } catch (e) { console.error('[loadProject] renderAll failed', e); try { toast('渲染失败：' + (e.message || String(e)), 'error'); } catch(_){} }
  try { setAssistantOpen(Boolean(state.ui.assistant && state.ui.assistant.open), false); } catch (e) { console.warn('[loadProject] setAssistantOpen failed', e); }
  state.suppressUiEvents = true;
  try { const panel = $('#variablesPanel'); if (panel) panel.open = Boolean(state.ui.drives && state.ui.drives.variables_open); } catch (_) {}
  setTimeout(() => { state.suppressUiEvents = false; }, 0);
  if (state.auth?.role === 'guest') return;
  const previewRevision=state.editRevision;
  scheduleProjectIdleTasks(projectId, loadRevision, [
    ['refreshDrivePreview', async () => {
      const preview=await api(`/api/projects/${projectId}/preview?include_latest_result=false`, {timeout:10000});
      if (state.project?.id===projectId && state.editRevision===previewRevision && state.projectLoadRevision===loadRevision)
        applyDrivePreview(projectId, preview, {render:true});
    }],
    ['refreshMeshLibrary', refreshMeshLibrary],
    ['refreshServerScenes', refreshServerScenes],
    ['refreshMassProperties', async () => { await refreshMassProperties(); renderLayerDetails(); }],
    ['refreshJobs', refreshJobs],
    ['refreshArtifacts', refreshArtifacts],
    ['refreshEventStatus', () => refreshEventStatus(false)],
    ['loadGlobalAssistantConversation', loadGlobalAssistantConversation],
  ]);
}

function scheduleProjectIdleTasks(projectId, revision, tasks) {
  const schedule = globalThis.requestIdleCallback || (callback => setTimeout(() => callback({didTimeout:false,timeRemaining:()=>0}), 0));
  tasks.forEach(([name, task]) => schedule(() => {
    if (state.project?.id !== projectId || state.projectLoadRevision !== revision) return;
    Promise.resolve().then(task).catch(error => console.warn(`[loadProject] ${name} failed`, error));
  }, {timeout: 1000}));
}

function reconcileEditorAfterAuthoritativeRefresh(project) {
  if (!project?.id || routeContextFromLocation().kind !== 'editor' || project.id !== state.project?.id) return false;
  const status = projectStatus(project);
  const expectedMode = status === 'checked_out' ? 'persistent' : (status === 'baseline' ? 'readonly' : 'temporary');
  if (state.editSessionMode === expectedMode) return false;
  state.editSessionMode = 'readonly';
  clearDirty();
  showLeaseBanner('模型生命周期或编辑会话已在其他位置发生变化；当前 Editor 已切换为只读。请返回 Hub 后重新进入以建立新的编辑会话。');
  applyProjectAccess(); renderIdleCountdown();
  return true;
}

function captureAuthoritativeProjectFence(projectId = state.project?.id) {
  return {
    projectId: projectId || '',
    editRevision: state.editRevision,
    uiRevision: state.uiRevision,
    projectLoadRevision: state.projectLoadRevision,
    editorFocusRevision: state.editorFocusRevision,
  };
}

function canApplyAuthoritativeProject(fence, {requireClean = true} = {}) {
  if (!fence?.projectId || state.project?.id !== fence.projectId) return false;
  if (state.projectLoadRevision !== fence.projectLoadRevision) return false;
  if (state.editRevision !== fence.editRevision) return false;
  if (state.uiRevision !== fence.uiRevision) return false;
  if (state.editorFocusRevision !== fence.editorFocusRevision) return false;
  // A local ui.set is visible immediately but may still be queued for the
  // server. Never let polling apply an authoritative mirror until all UI
  // writes represented by this fence have been acknowledged (or failed).
  if (state.uiPersistedRevision < fence.uiRevision) return false;
  // Local-only UI edits are just as authoritative as unsynced ProjectSpec.
  // A polling mirror may never replace them before the user explicitly syncs.
  if (requireClean && (state.dirty || state.localDraftUiChanges.size > 0)) return false;
  return true;
}

async function refreshEventStatus(syncMirror = false) {
  if (!state.project) return;
  const fence = captureAuthoritativeProjectFence();
  const previous = state.eventCursor;
  const payload = await api(`/api/projects/${fence.projectId}/events?since=${state.eventCursor}`);
  // A project switch can complete while the polling request is in flight.  Do
  // not let the old request move the new project's event cursor or state.
  if (state.project?.id !== fence.projectId || state.projectLoadRevision !== fence.projectLoadRevision) return;
  state.eventCursor = payload.cursor;
  if ($('#eventBadge')) $('#eventBadge').textContent = `${payload.cursor} EVENTS`;
  if (syncMirror && previous > 0 && payload.events.length && canApplyAuthoritativeProject(fence)) {
    const mirrorFence = captureAuthoritativeProjectFence(fence.projectId);
    const mirror = await api(`/api/projects/${fence.projectId}/state`);
    // Critical race fence: the user may have edited B/C/D while the authoritative
    // mirror request was travelling.  A late server snapshot must never replace
    // newer local edits, even if the request started while the editor was clean.
    if (!canApplyAuthoritativeProject(mirrorFence)) return;
    state.project = mirror.state.project;
    state.ui = mirror.state.ui || {};
    state.expandedSegments = new Set(Object.entries(state.ui.drives?.expanded_segments || {}).filter(([,open]) => open).map(([key]) => key));
    const modeChanged = reconcileEditorAfterAuthoritativeRefresh(state.project);
    updateProjectSummary(state.project);
    await refreshMassProperties();
    // Mass refresh is another await boundary.  Re-check before rendering an
    // authoritative projection so a just-entered local edit keeps its DOM too.
    if (!canApplyAuthoritativeProject(mirrorFence)) return;
    renderAll();
    if (modeChanged) route();
    state.suppressUiEvents = true; $('#variablesPanel').open = Boolean(state.ui.drives?.variables_open); setTimeout(() => { state.suppressUiEvents = false; }, 0);
  }
}

async function undoOrRedo(action) {
  if (!state.project) return;
  const offset = action === 'undo' ? -1 : 1;
  const target = state.localDraftHistoryIndex + offset;
  if (localDraftEligible() && target >= 0 && target < state.localDraftHistory.length) {
    state.localDraftHistoryIndex = target;
    state.project = deepClone(state.localDraftHistory[target]);
    state.editRevision += 1;
    state.dirty = state.localDraftHistoryIndex !== 0;
    state.unarchivedChanges ||= state.dirty;
    $('#dirtyBadge').textContent = '已保存';
    $('#dirtyBadge').classList.toggle('hidden', !state.unarchivedChanges && !state.dirty);
    if ($('#syncDraftButton')) $('#syncDraftButton').disabled = !state.dirty && !state.localDraftUiChanges.size;
    markJsonEditorStale(); renderAll();
    if (!state.dirty && !state.localDraftUiChanges.size) void removeLocalDraft(state.project.id);
    else scheduleLocalDraftWrite();
    toast(action === 'undo' ? '已撤销本地草稿修改' : '已前进本地草稿修改', 'info');
    return;
  }
  if (state.dirty) { toast('本地修改尚未同步，不能越过草稿边界执行服务端撤销；请先同步或继续本地编辑', 'info'); return; }
  cancelInteractionCommit();
  clearDirty();
  await state.uiCommitChain.catch(() => null);
  try {
    const result = await api(`/api/projects/${state.project.id}/${action}`, {
      method: 'POST', body: JSON.stringify({confirmed: true, client: 'human_ui'}),
    });
    const mirror = await api(`/api/projects/${state.project.id}/state`);
    state.project = mirror.state.project;
    state.ui = mirror.state.ui || {};
    state.expandedSegments = new Set(Object.entries(state.ui.drives?.expanded_segments || {}).filter(([,open]) => open).map(([key]) => key));
    const modeChanged = reconcileEditorAfterAuthoritativeRefresh(state.project);
    state.eventCursor = mirror.cursor ?? (result.event?.seq + 1 || state.eventCursor);
    if ($('#eventBadge')) $('#eventBadge').textContent = `${state.eventCursor} EVENTS`;
    updateProjectSummary(state.project);
    await refreshMassProperties();
    renderAll();
    if (modeChanged) route();
    if (currentPage() === 'overview' && state.hubSelectedProjectId === state.project.id) await loadHubPreview(state.project.id, {force:true});
    markArchiveDirty();
    state.suppressUiEvents = true; $('#variablesPanel').open = Boolean(state.ui.drives?.variables_open); setTimeout(() => { state.suppressUiEvents = false; }, 0);
    toast(result.event?.semantic || (action === 'undo' ? '已撤销' : '已前进'), 'info', action === 'undo' ? 3600 : null);
  } catch (error) { toast(error.message, 'error'); }
}

async function commitEdits({message = '编辑已自动提交', quiet = true} = {}) {
  if (!state.project) return null;
  if (!canEditProject()) throw new Error('项目只读，请先签出再修改配置');
  if (!state.dirty) return state.project;
  const updated = await commitCurrentStep(message, quiet);
  if (updated) { updateProjectSummary(updated); renderHub(); markJsonEditorStale(); }
  if (currentPage() === 'simulation') await loadSimulationWorkspace();
  return updated;
}

async function archiveVersion() {
  if (!state.project) return null;
  if (state.editSessionMode === 'temporary') throw new Error('签入/基线临时编辑不能保存历史版本');
  if (!canEditProject()) throw new Error('模型只读，请先签出再保存历史版本');
  const projectId = state.project.id;
  const choice = await chooseArchiveVersionDetails(projectId);
  if (!choice) return null;
  return withBlockingLoading({title:'正在保存历史版本', detail:'先保存当前工作版本，再创建可恢复的历史快照。'}, async token => {
    updateBlockingLoading(token, {detail:'正在同步当前工作版本…'});
    await flushInteractionCommit({finalize:true});
    await syncLocalDraft({quiet:true});
    updateBlockingLoading(token, {detail:'正在写入历史版本和备注…'});
    const archived = await api(`/api/projects/${projectId}/archive`, {method:'POST', body:JSON.stringify(choice)});
    clearArchiveDirty();
    updateProjectSummary(state.project);
    state.hubSelectedProjectId ||= projectId;
    if (state.hubSelectedProjectId === projectId) await loadHubPreview(projectId, {force:true});
    toast(`${choice.overwrite_version_id ? '已覆盖' : '已保存'}历史版本「${choice.archive_name}」；当前工作版本不变`, 'success');
    return archived;
  });
}

async function saveEditableDraft() {
  if (canEditProject()) await syncLocalDraft({quiet:true});
}

function cancelInteractionCommit() {
  if (state.interactionCommitTimer) clearTimeout(state.interactionCommitTimer);
  state.interactionCommitTimer = null;
  state.interactionCommitNeedsMassRefresh = false;
}

function scheduleInteractionCommit({refreshMass = false} = {}) {
  if (!state.project || !canEditProject()) return;
  state.interactionCommitNeedsMassRefresh ||= refreshMass;
  if (state.interactionCommitTimer) clearTimeout(state.interactionCommitTimer);
  state.interactionCommitTimer = null;
  // A limited joint must have an ordered two-value range, but editing the two
  // inputs is inherently non-atomic.  Keep the transient invalid state local
  // instead of persisting it during the debounce window; the next valid edit
  // will schedule the normal project.replace commit.
  if (firstInvalidActiveJointRange()) return;
  if (currentPage() === 'drives') scheduleDraftGanttProjection();
  state.interactionCommitTimer = setTimeout(() => {
    state.interactionCommitTimer = null;
    const shouldRefreshMass = state.interactionCommitNeedsMassRefresh;
    state.interactionCommitNeedsMassRefresh = false;
    if (!state.dirty) return;
    scheduleLocalDraftWrite();
    if (shouldRefreshMass) state.massProperties = null; // derived preview refreshes on explicit server sync

  }, state.interactionCommitDebounceMs);
}

async function flushInteractionCommit({finalize = false} = {}) {
  const shouldRefreshMass = state.interactionCommitNeedsMassRefresh;
  cancelInteractionCommit();
  // UI-only writes share the same server event stream as project saves. Drain
  // their invocation-ordered queue before a finalize/check-in transition so a
  // late hierarchy/diagram toggle can never repaint an older server UI state.
  await state.uiCommitChain.catch(() => null);
  // A debounce save may already be in flight. Waiting for it first prevents a
  // check-in click from queueing the same snapshot a second time.
  await state.saveChain.catch(() => null);
  if (!state.dirty) {
    await flushLocalUiChanges();
    return state.project;
  }
  const updated = await commitCurrentStep('字段变更已自动提交', true, {skipPostSave:finalize});
  await flushLocalUiChanges();
  if (!state.dirty && !state.localDraftUiChanges.size) await removeLocalDraft(updated?.id);
  if (shouldRefreshMass && !finalize) { await refreshMassProperties(); renderLayerDetails(); }
  return updated;
}

function commitCurrentStep(message = '当前步骤已保存', quiet = false, {skipPostSave = false} = {}) {
  if (!state.project) return Promise.resolve(null);
  if (!canEditProject()) return Promise.reject(new Error('项目只读，请先签出再修改配置'));
  const rangeIssue = firstInvalidActiveJointRange();
  if (rangeIssue) return Promise.reject(new Error(activeJointRangeErrorMessage(rangeIssue)));
  collectStaticFields();
  const revision = state.editRevision;
  const snapshot = deepClone(state.project);
  const task = state.saveChain.catch(() => null).then(async () => {
    if (state.editSessionMode === 'persistent' && state.localDraftBaseServerProject?.id === snapshot.id) {
      const remote = await api(`/api/projects/${snapshot.id}`, {timeout:10000});
      if (projectServerSignature(remote) !== projectServerSignature(state.localDraftBaseServerProject)) {
        throw new Error('服务端模型已发生变化，已保留本地草稿。请核对其他标签页/用户的更新后再同步，避免覆盖他人数据。');
      }
    }
    const updated = await api(`/api/projects/${snapshot.id}`, {method:'PUT', body:JSON.stringify(snapshot)});
    if (state.project?.id === snapshot.id) state.localDraftBaseServerProject = deepClone(updated);
    if (state.editRevision === revision) {
      state.project = updated; clearDirty();
      if (state.localDraftTimer) { clearTimeout(state.localDraftTimer); state.localDraftTimer = null; }
      if (!state.localDraftUiChanges.size) void removeLocalDraft(snapshot.id);
      else scheduleLocalDraftWrite();
      state.localDraftHistory = [deepClone(updated)];
      state.localDraftHistoryIndex = 0;
      // Gantt and drive folded variables are one projection of resolve_schedule().
      // Keep the editRevision guard so an older save can never overwrite newer input.
      if (!skipPostSave) {
        try {
          await refreshDriveProjection(snapshot.id, revision, {render:true});
        } catch (error) {
          if (state.project?.id === snapshot.id && state.editRevision === revision) {
            state.simulationScheduleError = error.message || String(error);
            if(currentPage()==='drives')renderDrives();
            if(currentPage()==='simulation')renderSimulationGantt();
          }
        }
      }
    }
    if (!skipPostSave) await refreshEventStatus(false);
    if (!quiet) toast(message);
    return updated;
  });
  state.saveChain = task.catch(error => { toast(error.message, 'error'); return null; });
  return task;
}

async function commitUiState(path, value, uiRevision = state.uiRevision) {
  const projectId = state.project?.id;
  if (!projectId) return null;
  const payload = deepClone(value);
  const revision = Number(uiRevision) || 0;
  // V2.10.3: ui.set previously fired concurrently. At a medium click cadence an
  // older hierarchy-view request could arrive after the newer request and make
  // the server-authoritative UI state appear to roll back. Serialize UI writes
  // in invocation order while keeping the local mirror immediate.
  const task = state.uiCommitChain.catch(() => null).then(async () => {
    try {
      const result = await api(`/api/projects/${projectId}/commands?confirmed=true`, {method:'POST', body:JSON.stringify({command:{tool_id:'ui.set',params:{path,value:payload},client:'human_ui'},confirmed:true})});
      if (state.project?.id === projectId) {
        state.uiPersistedRevision = Math.max(state.uiPersistedRevision, revision);
        await refreshEventStatus(false);
      }
      return result;
    } catch (error) {
      // Release the mirror fence for this failed write; the next authoritative
      // poll may then restore the real server value instead of leaving a local
      // optimistic state stuck forever. Newer queued revisions remain fenced.
      if (state.project?.id === projectId) state.uiPersistedRevision = Math.max(state.uiPersistedRevision, revision);
      throw error;
    }
  });
  state.uiCommitChain = task.catch(error => { toast(error.message, 'error'); return null; });
  return task;
}

async function flushLocalUiChanges() {
  if (!state.project || !state.localDraftUiChanges.size) return;
  const projectId = state.project.id;
  const edits = [...state.localDraftUiChanges.entries()];
  for (const [path, value] of edits) {
    if (state.project?.id !== projectId) throw new Error('模型已切换，停止 UI 草稿同步');
    await commitUiState(path, value, state.uiRevision);
    if (JSON.stringify(state.localDraftUiChanges.get(path)) === JSON.stringify(value))
      state.localDraftUiChanges.delete(path);
  }
}
async function syncLocalDraft({quiet = false} = {}) {
  if (!state.project || !canEditProject()) throw new Error('模型只读，不能同步草稿');
  if (state.localDraftTimer) { clearTimeout(state.localDraftTimer); state.localDraftTimer = null; }
  if (state.dirty) await commitCurrentStep('模型草稿已同步', quiet);
  await flushLocalUiChanges();
  if (!state.dirty && !state.localDraftUiChanges.size) {
    await removeLocalDraft(state.project.id);
    state.localDraftHistory = [deepClone(state.project)];
    state.localDraftHistoryIndex = 0;
    if ($('#syncDraftButton')) $('#syncDraftButton').disabled = true;
    if (!quiet) toast('浏览器草稿已同步至服务端', 'success');
  } else {
    await persistLocalDraft();
  }
  return state.project;
}

async function chooseManualCheckInArchive(projectId) {
  const dialog = $('#checkInArchiveChoiceDialog');
  if (!dialog) throw new Error('签入确认弹窗未加载');
  const anchor = $('#checkInCreateAnchor');
  const fields = $('#checkInAnchorFields');
  const name = $('#checkInAnchorName');
  const log = $('#checkInAnchorLog');
  const newRadio = $('#checkInVersionNew');
  const overwriteRadio = $('#checkInVersionOverwrite');
  const targetRow = $('#checkInOverwriteTargetRow');
  const target = $('#checkInOverwriteTarget');
  const versionList = $('#checkInVersionList');
  const versionCount = $('#checkInVersionCount');
  const refreshButton = $('#checkInVersionRefresh');
  const form = $('#checkInFinishForm');
  const projectSummary = state.project?.id === projectId ? state.project
    : (state.projects || []).find(item => item.id === projectId)
      || (state.hubPreview?.id === projectId ? state.hubPreview : null);
  const defaultName = `${projectSummary?.name || '模型'} · 阶段版本`;
  let freshName = defaultName, freshLog = '', lastMode = 'new';
  let versions = [], selectedVersionId = '', historyRequestId = 0, closed = false;
  const listeners = [];
  const listen = (node, event, callback) => {
    if (!node) return;
    node.addEventListener(event, callback);
    listeners.push([node, event, callback]);
  };
  const overwritable = item => item && item.version_kind !== 'baseline'
    && item.reason !== 'baseline' && !item.locked;
  const findSelected = () => versions.find(item => String(item.id) === selectedVersionId && overwritable(item));
  const versionTitle = item => String(item.archive_name ||
    (item.version_kind === 'baseline' ? item.baseline_name : '') || item.name || '未命名历史版本');
  const updateMode = (forceSelected = false) => {
    const savingHistory = Boolean(anchor.checked);
    const overwriting = savingHistory && Boolean(overwriteRadio?.checked);
    fields.classList.toggle('hidden', !savingHistory);
    name.required = savingHistory;
    targetRow?.classList.toggle('hidden', !overwriting);
    if (target) target.required = overwriting;
    if (overwriting) {
      if (lastMode !== 'overwrite') { freshName = name.value || defaultName; freshLog = log.value; }
      const selected = findSelected();
      if (selected && (forceSelected || lastMode !== 'overwrite')) {
        name.value = String(selected.archive_name || selected.name || defaultName);
        log.value = String(selected.log || '');
      }
    } else if (lastMode === 'overwrite') {
      name.value = freshName;
      log.value = freshLog;
    }
    if (savingHistory && !name.value.trim()) name.value = defaultName;
    lastMode = overwriting ? 'overwrite' : 'new';
  };
  const renderHistory = () => {
    if (versionCount) {
      const available = versions.filter(overwritable).length;
      versionCount.textContent = `${versions.length} 个版本 · ${available} 个可覆盖`;
    }
    if (target) {
      const available = versions.filter(overwritable);
      target.innerHTML = '<option value="">请从右侧历史列表选择</option>' + available.map(item =>
        `<option value="${esc(String(item.id))}">${esc(versionTitle(item))} · ${esc(formatDate(item.archived_at || item.saved_at))}</option>`
      ).join('');
      target.value = findSelected() ? selectedVersionId : '';
    }
    if (overwriteRadio) overwriteRadio.disabled = !versions.some(overwritable);
    if (!versionList) return;
    if (!versions.length) {
      versionList.innerHTML = '<p class="empty-state">当前模型暂无历史版本。可以选择“新建历史版本”。</p>';
      return;
    }
    versionList.innerHTML = versions.map(item => {
      const locked = !overwritable(item);
      const selected = !locked && String(item.id) === selectedVersionId && Boolean(anchor.checked && overwriteRadio?.checked);
      const type = locked ? (item.version_kind === 'baseline' ? '基线 · 不可覆盖' : '锁定 · 不可覆盖') : '普通版本';
      const actor = String(item.actor || '未知用户');
      const stamp = formatDate(item.archived_at || item.saved_at);
      const excerpt = String(item.log || '').trim().slice(0, 140);
      return `<div role="listitem"><button type="button" class="check-in-version-row ${selected ? 'selected' : ''}" ` +
        `data-checkin-version-id="${esc(String(item.id))}" ${locked ? 'disabled aria-disabled="true"' : ''} ` +
        `aria-label="${esc(locked ? `${versionTitle(item)}，${type}` : `选择覆盖 ${versionTitle(item)}`)}" ` +
        `aria-pressed="${selected}">` +
        `<span class="check-in-version-row-top"><strong>${esc(versionTitle(item))}</strong><span class="check-in-version-kind ${locked ? 'locked' : ''}">${esc(type)}</span></span>` +
        `<span class="check-in-version-meta">${esc(stamp)} · ${esc(actor)}</span>` +
        (excerpt ? `<span class="check-in-version-note">${esc(excerpt)}</span>` : '') +
        `</button></div>`;
    }).join('');
  };
  const chooseTarget = id => {
    const item = versions.find(entry => String(entry.id) === String(id) && overwritable(entry));
    if (!item) return; // Baseline/locked versions are visible but not selectable.
    selectedVersionId = String(item.id);
    anchor.checked = true;
    if (overwriteRadio) overwriteRadio.checked = true;
    if (newRadio) newRadio.checked = false;
    updateMode(true);
    renderHistory();
  };
  const onToggle = () => {
    if (!anchor.checked && newRadio && overwriteRadio) {
      newRadio.checked = true;
      overwriteRadio.checked = false;
    }
    updateMode();
    renderHistory();
  };
  const onModeChange = () => { updateMode(true); renderHistory(); };
  const onTargetChange = () => { chooseTarget(target.value); };
  const onHistoryClick = event => {
    const button = event.target.closest?.('[data-checkin-version-id]');
    if (button && !button.disabled) chooseTarget(button.dataset.checkinVersionId);
  };
  const onSubmit = event => {
    if (event.submitter?.value !== 'confirm') return;
    if (anchor.checked && !name.value.trim()) {
      event.preventDefault(); toast('请填写历史版本名称', 'error'); name.focus?.(); return;
    }
    if (anchor.checked && overwriteRadio?.checked) {
      const selected = findSelected();
      if (!selected) {
        event.preventDefault();
        toast('请选择右侧一个未锁定的普通历史版本；基线版本不可覆盖。', 'error');
        return;
      }
      if (!confirm(`确定覆盖历史版本「${versionTitle(selected)}」？\n\n将使用本次签入模型替换该版本原有快照，原快照无法恢复。当前最新版本仍会正常保存。`)) {
        event.preventDefault();
      }
    }
  };
  const loadVersions = async () => {
    const requestId = ++historyRequestId;
    if (versionCount) versionCount.textContent = '正在读取…';
    if (versionList) versionList.innerHTML = '<p class="empty-state">正在读取当前模型的存档日志…</p>';
    try {
      const response = await api(`/api/projects/${encodeURIComponent(projectId)}/versions?detail=metadata`, {timeout:12000});
      if (closed || historyRequestId !== requestId) return;
      versions = Array.isArray(response) ? response : [];
      // A version may have been deleted or locked while this dialog was open.
      // Never silently substitute another overwrite destination.
      if (selectedVersionId && !findSelected()) selectedVersionId = '';
      renderHistory();
      updateMode();
    } catch (error) {
      if (closed || historyRequestId !== requestId) return;
      versions = [];
      renderHistory();
      if (versionCount) versionCount.textContent = '读取失败 · 可重试';
      if (versionList) versionList.innerHTML = '<p class="empty-state">历史版本读取失败。可以点击“刷新”，或不勾选历史版本直接签入。</p>';
      toast(`读取历史版本失败：${error.message || String(error)}`, 'error');
    }
  };
  anchor.checked = false;
  fields.classList.add('hidden');
  name.value = '';
  name.required = false;
  log.value = '';
  if (newRadio) newRadio.checked = true;
  if (overwriteRadio) { overwriteRadio.checked = false; overwriteRadio.disabled = true; }
  if (target) { target.value = ''; target.required = false; }
  targetRow?.classList.add('hidden');
  if (versionCount) versionCount.textContent = '正在读取…';
  if (versionList) versionList.innerHTML = '<p class="empty-state">正在读取历史版本…</p>';
  listen(anchor, 'change', onToggle);
  listen(newRadio, 'change', onModeChange);
  listen(overwriteRadio, 'change', onModeChange);
  listen(target, 'change', onTargetChange);
  listen(versionList, 'click', onHistoryClick);
  listen(refreshButton, 'click', () => { void loadVersions(); });
  listen(form, 'submit', onSubmit);
  dialog.returnValue = '';
  const decision = await new Promise(resolve => {
    dialog.addEventListener('close', () => resolve(dialog.returnValue), {once:true});
    dialog.showModal();
    // The right-hand history fetch is deliberately nonblocking. A user who
    // only wants to sign in should not have to wait for metadata hydration.
    if (typeof api === 'function') void loadVersions();
  });
  closed = true;
  historyRequestId++;
  for (const [node, event, callback] of listeners) node.removeEventListener(event, callback);
  if (decision !== 'confirm') return null;
  if (anchor.checked && !name.value.trim()) { toast('请填写历史版本名称', 'error'); return null; }
  const overwriting = anchor.checked && Boolean(overwriteRadio?.checked);
  if (overwriting && !findSelected()) {
    toast('历史版本已变化或未选择覆盖目标，请重新打开签入弹窗选择。', 'error');
    return null;
  }
  return {
    archive: Boolean(anchor.checked),
    log: anchor.checked ? log.value : '',
    archive_name: anchor.checked ? name.value.trim() : '',
    overwrite_version_id: overwriting ? selectedVersionId : '',
  };
}

async function chooseArchiveVersionDetails(projectId) {
  const editorDialog = $('#checkInArchiveEditorDialog');
  if (!editorDialog) throw new Error('历史版本弹窗未加载');
  let versions = [];
  try {
    const entries = await api(`/api/projects/${encodeURIComponent(projectId)}/versions`);
    versions = (Array.isArray(entries) ? entries : []).filter(item =>
      item.version_kind !== 'baseline' && !item.locked);
  } catch (error) { toast(`读取历史版本失败：${error.message}`, 'error'); return null; }
  const radios = $$('input[name="checkInArchiveMode"]', editorDialog);
  const targetRow = $('#checkInArchiveTargetRow');
  const target = $('#checkInArchiveTarget');
  const name = $('#checkInArchiveName');
  const log = $('#checkInArchiveLog');
  target.innerHTML = '<option value="">请选择要覆盖的历史版本</option>' + versions.map(item =>
    `<option value="${esc(item.id)}">${esc(item.archive_name || item.name || '历史版本')} · ${esc(formatDate(item.archived_at || item.saved_at))}</option>`
  ).join('');
  const overwriteRadio = radios.find(item => item.value === 'overwrite');
  if (overwriteRadio) overwriteRadio.disabled = versions.length === 0;
  radios.forEach(radio => { radio.checked = radio.value === 'new'; });
  name.value = `${state.project?.name || '模型'} · 新版本`;
  log.value = '';
  const updateMode = () => {
    const overwrite = radios.some(radio => radio.checked && radio.value === 'overwrite');
    targetRow.classList.toggle('hidden', !overwrite);
    target.required = overwrite;
    if (overwrite && target.value) {
      const selected = versions.find(item => item.id === target.value);
      if (selected) { name.value = selected.archive_name || selected.name || name.value; log.value = String(selected.log || ''); }
    }
  };
  radios.forEach(radio => radio.addEventListener('change', updateMode));
  target.addEventListener('change', updateMode);
  updateMode();
  editorDialog.returnValue = '';
  const result = await new Promise(resolve => {
    editorDialog.addEventListener('close', () => {
      const overwrite = radios.some(radio => radio.checked && radio.value === 'overwrite');
      const payload = editorDialog.returnValue === 'confirm' ? {
        log:log.value, archive_name:name.value.trim(), overwrite_version_id:overwrite ? target.value : '',
      } : null;
      resolve(payload && payload.archive_name && (!overwrite || payload.overwrite_version_id) ? payload : null);
    }, {once:true});
    editorDialog.showModal();
    requestAnimationFrame(() => { name.focus(); name.select(); });
  });
  radios.forEach(radio => radio.removeEventListener('change', updateMode));
  target.removeEventListener('change', updateMode);
  return result;
}

async function checkInCurrentEditor({confirmed = false, archive = true, log = null,
                                     archive_name = '', overwrite_version_id = ''} = {}) {
  const context = routeContextFromLocation();
  const projectId = state.project?.id;
  if (context.kind !== 'editor' || !projectId || state.editSessionMode !== 'persistent' || projectStatus(state.project) !== 'checked_out') {
    toast('当前模型不是可签入的签出编辑状态', 'error');
    return false;
  }
  // The single finish-editing dialog already communicates closing this editor.
  if (log === null) {
    const choice = await chooseManualCheckInArchive(projectId);
    if (choice === null) return false;
    archive = choice.archive;
    log = choice.log;
    archive_name = choice.archive_name;
    overwrite_version_id = choice.overwrite_version_id;
  }
  archive = Boolean(archive);
  log = archive ? String(log || '') : '';
  return withBlockingLoading({
    title:'正在签入模型',
    detail:archive ? (overwrite_version_id ? '正在提交编辑、更新指定历史版本并签入；成功后关闭当前模型分页。' : '正在提交编辑、新建历史版本并签入；成功后关闭当前模型分页。') : '正在保存最新工作版本并签入；无需额外历史版本。',
  }, async token => {
    try {
      updateBlockingLoading(token,{detail:'正在提交当前编辑修改…'});
      await flushInteractionCommit({finalize:true});
      updateBlockingLoading(token,{detail:archive ? (overwrite_version_id ? '正在覆盖指定历史版本、执行签入并释放编辑会话…' : '正在新建历史版本、执行签入并释放编辑会话…') : '正在保存最新版本、释放编辑占用…'});
      const updated = await api(`/api/projects/${projectId}/lifecycle`, {
        method:'POST',
        body:JSON.stringify({action:'check_in', archive, log, archive_name, overwrite_version_id}),
        timeout:120000, // bounded wait; on timeout reconcile authoritative lifecycle before any retry
      });
      state.project = updated;
      updateProjectSummary(updated);
      invalidateHubProjectState(projectId);
      publishProjectLifecycleUpdate(updated);
      clearDirty(); clearArchiveDirty();
      unregisterEditorWindow(projectId);
      state.editSessionMode = null;
      state.editorWindowId = null;
      toast(archive ? (overwrite_version_id ? '模型已签入并更新指定历史版本，当前 Editor 将关闭' : '模型已签入并新建历史版本，当前 Editor 将关闭') : '模型最新版本已保存并签入，当前 Editor 将关闭');
      // window.close() works for windows opened by Hub. Directly opened tabs
      // fall back to Hub instead of leaving a dead editor URL behind.
      setTimeout(() => {
        try { window.close(); } catch (_) {}
        setTimeout(() => {
          if (!window.closed) {
            window.name = 'mujoco-studio-hub';
            location.replace(HUB_PATH);
          }
        }, 80);
      }, 80);
      return true;
    } catch (error) {
      let confirmedCheckedIn=false;
      try {
        const live=await api(`/api/projects/${projectId}`, {timeout:6000});
        confirmedCheckedIn=projectStatus(live)==='checked_in';
        if(confirmedCheckedIn){
          state.project=live; updateProjectSummary(live); invalidateHubProjectState(projectId);
          publishProjectLifecycleUpdate(live);
          clearDirty(); clearArchiveDirty(); unregisterEditorWindow(projectId);
          state.editSessionMode=null; state.editorWindowId=null;
          toast('服务器已确认模型签入成功；原响应可能在网络中断时丢失。','success');
          setTimeout(()=>{try{window.close();}catch(_){} if(!window.closed)location.replace(HUB_PATH);},100);
          return true;
        }
      } catch(checkError){console.warn('[check-in] reconciliation unavailable',checkError);}
      toast(`签入未确认：${error.message || String(error)}。${confirmedCheckedIn?'':'请先在 Hub 查看实际签出状态，不要连续重试。'}`, 'error',12000);
      return false;
    }
  });
}

function returnCurrentWindowToHub(projectId = state.project?.id) {
  if (projectId) unregisterEditorWindow(projectId);
  state.editSessionMode = null;
  state.editorWindowId = null;
  window.name = 'mujoco-studio-hub';
  history.replaceState(null, '', HUB_PATH);
  route();
}

async function activateEditorRoute(context = routeContextFromLocation()) {
  if (context.kind !== 'editor') return false;
  resetEditorLayoutDefaults();
  let selected = state.projects.find(item => item.id === context.projectId);
  if (!selected) {
    try { selected = await api(`/api/projects/${context.projectId}`, {timeout:10000}); }
    catch (error) { console.warn('[editor-entry] targeted project lookup failed', error); }
  }
  if (!selected) {
    toast('模型不存在或当前账号无权访问', 'error');
    returnCurrentWindowToHub(context.projectId);
    return false;
  }
  const status = projectStatus(selected);
  if (state.auth?.role === 'guest' && status !== 'baseline') {
    toast('游客只能进入基线模型查看', 'error');
    returnCurrentWindowToHub(context.projectId);
    return false;
  }
  if (state.auth?.role === 'guest') {
    return withBlockingLoading({title:'正在打开基线结果', detail:'正在载入只读仿真结果，请等待。'}, async () => {
      try {
        state.editSessionMode = 'readonly';
        await loadProject(context.projectId, {force:true});
        registerEditorWindow(context.projectId);
        const view = new URLSearchParams(location.search).get('view');
        if (view) { state.ui.results ||= {}; state.ui.results.active_view = view; }
        history.replaceState(null, '', editorUrl(context.projectId, 'simulation', view ? `view=${encodeURIComponent(view)}` : ''));
        route();
        return true;
      } catch (error) {
        toast(error.message, 'error');
        returnCurrentWindowToHub(context.projectId);
        return false;
      }
    });
  }
  // Explicit navigation is sufficient intent: no confirm + "opening" +
  // "opened" toast sequence. Read-only/temporary status is already indicated
  // by the editor access controls. Keep genuine request failures visible.
  return (async () => {
    try {
      const result = await api(`/api/projects/${context.projectId}/edit-session`, {method:'POST', body:'{}', timeout:12000});
      state.editSessionMode = result.mode;
      setIdleDeadline(context.projectId, result.idle_check_in_deadline);
      await loadProject(context.projectId, {force:true, initialProject:result.project});
      registerEditorWindow(context.projectId);
      const view = new URLSearchParams(location.search).get('view');
      if (context.page === 'simulation' && view) { state.ui.results ||= {}; state.ui.results.active_view = view; }
      history.replaceState(null, '', editorUrl(context.projectId, context.page));
      route();
      return true;
    } catch (error) {
      toast(error.message, 'error');
      returnCurrentWindowToHub(context.projectId);
      return false;
    }
  })();
}

function route() {
  let context = routeContextFromLocation();
  if (state.auth?.role === 'guest' && context.kind === 'editor' && context.page !== 'simulation') {
    const view = new URLSearchParams(location.search).get('view');
    history.replaceState(null, '', editorUrl(context.projectId, 'simulation', view ? `view=${encodeURIComponent(view)}` : ''));
    context = routeContextFromLocation();
  }
  if (context.kind === 'editor' && context.legacy && state.project?.id) {
    history.replaceState(null, '', editorUrl(state.project.id, context.page));
  }
  const editorRoute = context.kind === 'editor';
  const editorReady = editorRoute && Boolean(state.editSessionMode) && state.project?.id === context.projectId;
  const page = editorRoute ? context.page : 'overview';
  const editing = editorRoute;
  document.body.classList.toggle('hub-mode', !editing);
  document.body.classList.toggle('model-edit-mode', editing);
  document.body.classList.toggle('editor-route-pending', editorRoute && !editorReady);
  document.body.classList.toggle('checked-in-edit-mode', Boolean(editorReady && state.editSessionMode === 'temporary' && projectStatus(state.project) === 'checked_in'));
  $$('[data-page-content]').forEach(item => item.classList.toggle('hidden', item.dataset.pageContent !== page));
  $$('#navigation a').forEach(item => item.classList.toggle('active', item.dataset.page === page));
  $('#pageEyebrow').textContent = pageMeta[page][0];
  $('#pageTitle').textContent = pageMeta[page][1];
  const brandTitle = $('#brandTitle');
  const brandSubtitle = $('#brandSubtitle');
  const editorName = editorReady ? editorDisplayName(state.project) : '模型';
  if (brandTitle) brandTitle.textContent = editing ? editorName : 'MuJoCoHub';
  if (brandSubtitle) brandSubtitle.textContent = editing ? 'MODEL EDITING' : 'MODEL HUB';
  const editorLabel = $('#editorProjectLabel');
  if (editorLabel) { editorLabel.textContent = editing ? editorName : ''; editorLabel.classList.toggle('hidden', !editing); }
  document.title = editing ? `${editorName} — MuJoCo Studio` : 'MuJoCoHub — MuJoCo Studio';
  const editorCheckinButton = $('#editorCheckinButton');
  if (editorCheckinButton) editorCheckinButton.classList.toggle('hidden', !(editorReady && state.editSessionMode === 'persistent' && projectStatus(state.project) === 'checked_out'));
  if (!editing && context.kind === 'hub' && state.project) requestAnimationFrame(() => {
    renderHub();
    loadHubPreview(state.hubSelectedProjectId || state.project.id);
  });
  if (page === 'simulation' && state.project) loadSimulationWorkspace();
  if (page === 'agent' && state.project) loadAgentWorkspace();
  syncJsonEditorIfVisible();
}

function renderAll() {
  if (!state.project) return;
  const tasks = [
    ['renderMetrics', () => renderMetrics()],
    ['renderHub', () => renderHub()],
    ['renderLayers', () => renderLayers()],
    ['renderVariables', () => renderVariables()],
    ['renderDrives', () => renderDrives()],
    ['renderQuickOptimization', () => renderQuickOptimization()],
    ['renderPairs', () => renderPairs()],
    ['renderSettings', () => renderSettings()],
    ['renderRanges', () => renderRanges()],
    ['renderResultViewer', () => renderResultViewer()],
    ['renderSimulationGantt', () => renderSimulationGantt()],
  ];
  const failed = [];
  for (const [name, fn] of tasks) {
    try { fn(); } catch (e) {
      console.error(`[renderAll] ${name} failed:`, e);
      failed.push(`${name}: ${e && e.message ? e.message : String(e)}`);
    }
  }
  markJsonEditorStale();
  syncJsonEditorIfVisible();
  try { applyProjectAccess(); } catch (e) { console.error('[renderAll] applyProjectAccess failed:', e); }
  if (failed.length) toast(`部分模块渲染失败：${failed.length} 项（控制台查看详情）`, 'error');
}

function markJsonEditorStale() {
  const editor = $('#jsonEditor');
  if (editor) editor.dataset.stale = 'true';
}

function syncJsonEditorIfVisible() {
  const editor = $('#jsonEditor');
  if (!editor || editor.dataset.stale !== 'true' || editor.offsetParent === null || editor.closest('.hidden')) return;
  try { editor.value = JSON.stringify(state.project, null, 2); editor.dataset.stale = 'false'; }
  catch (error) { console.error('[jsonEditor] serialization failed', error); }
}

function updateProjectSummary(project) {
  if (!project?.id) return;
  const index = state.projects.findIndex(item => item.id === project.id);
  const previous = index >= 0 ? state.projects[index] : {};
  const summary = {...previous, id:project.id, name:project.name, description:project.description || '',
    category:project.category || 'None', tags:project.tags || [], mesh_root:project.mesh_root || '',
    updated_at:project.metadata?.updated_at || previous.updated_at || '',
    version_index:project.metadata?.version_index, version_date:project.metadata?.version_date || '',
    lifecycle_status:project.lifecycle?.status || previous.lifecycle_status || 'checked_in',
    checked_out_by:project.lifecycle?.checked_out_by || previous.checked_out_by || ''};
  if (index >= 0) state.projects.splice(index, 1, summary); else state.projects.unshift(summary);
}

function applyProjectAccess() {
  if (!state.project) return;
  const editable = canEditProject();
  document.body.classList.toggle('project-readonly', !editable);
  const context = routeContextFromLocation();
  document.body.classList.toggle('checked-in-edit-mode', Boolean(context.kind === 'editor' && context.projectId === state.project.id && state.editSessionMode === 'temporary' && projectStatus(state.project) === 'checked_in'));
  $('#saveButton').disabled = !editable || state.editSessionMode === 'temporary';
  if ($('#syncDraftButton')) $('#syncDraftButton').disabled = !editable || (!state.dirty && !state.localDraftUiChanges.size);
  $$('[data-bind],[data-color-bind],[data-variable-name],[data-variable-value],[data-quick-bind],[data-quick-relink]').forEach(control => {
    const resultViewerSelection = control.matches('[data-result-curve-source]');
    const guestViewerControl = state.auth?.role === 'guest' && control.matches('#axisHeightRange');
    control.disabled = !editable && !resultViewerSelection && !guestViewerControl;
  });
  const projectControls = [
    '#newResultLayoutButton','#renameResultLayoutButton','#deleteResultLayoutButton','#solverModeToggle','#adaptiveAddDriveButton','#addDriveButton','#addPairButton','#addVariableButton','#addRangeButton',
    '#scanMeshPathButton','#repairMeshesButton',
    '#generateButton','#optimizeButton','#runAgentButton','#quickRunButton','#adaptiveAddResultAxesButton','#addResultAxisButton','#addCursorButton','#removeCursorButton',
    '#simStart','#simEnd','#simStep','#simEngine','#simGroundEnabled','#simGravity','#simGroundFriction','#simGroundMargin','#simContactResponse','#simContactDamping','#distanceSampleLimit','#quickOptimizationToggle','#quickWorkflowName','#quickWorkflowInput',
  ];
  $$(projectControls.join(',')).forEach(control => {
    const guestViewerControl = state.auth?.role === 'guest' && ['addCursorButton','removeCursorButton'].includes(control.id);
    control.disabled = !editable && !guestViewerControl;
  });

  const animationHtmlWritable = canGenerateAnimationHtml();
  const regenerateAnimationButton = $('#regenerateEmbeddedAnimation');
  const reloadAnimationButton = $('#reloadEmbeddedAnimation');

  if (regenerateAnimationButton) {
    regenerateAnimationButton.disabled = !animationHtmlWritable;
    regenerateAnimationButton.title = animationHtmlWritable
      ? '重新生成最新动画 HTML 并覆盖交付数据；不会自动下载'
      : '签入/基线模型禁止重新生成动画 HTML；可使用“重新加载”读取交付数据中的 HTML';
  }
  if (reloadAnimationButton) {
    reloadAnimationButton.disabled = false;
    reloadAnimationButton.title = '重新加载交付数据中的最新动画 HTML';
  }

  const mutatingActions = [
    'add-closure','remove-closure','add-joint','remove-joint','remove-mesh','adaptive-all-meshes','adaptive-all-project-meshes','remove-layer','duplicate-layer',
    'promote-layer','demote-layer','remove-drive','add-segment','remove-segment','remove-pair','remove-range','remove-variable',
    'choose-mapping-csv','source-to-companion','companion-to-source','add-result-curve','adaptive-result-axis-name','remove-result-axis','remove-result-curve','layer-mass-toggle',
    'quick-run-all','quick-run-step','quick-load-all','quick-load-step','quick-remove-step','quick-save','quick-import',
  ];
  mutatingActions.forEach(action => $$(`[data-action="${action}"]`).forEach(control => { control.disabled = !editable; }));
  $('#dirtyBadge').title = state.editSessionMode === 'temporary' ? '临时编辑：退出后修改与事件会被删除' : (editable ? '工作版本会自动保留；需要历史恢复点可另存历史版本' : '当前项目只读');
  const owner = state.project.lifecycle?.checked_out_by || '';
  if (!editable && owner) $('#dirtyBadge').title = `项目由 ${owner} 签出，当前仅可只读访问`;
}

function setAssistantOpen(open, persist = true) {
  $('#globalAssistant').classList.toggle('collapsed', !open);
  $('#assistantToggle').setAttribute('aria-expanded', String(open));
  document.body.classList.toggle('assistant-open', open);
  uiSet('assistant.open', open, open ? '打开右侧智能体面板' : '折叠右侧智能体面板', {persist: persist && !!state.project?.id});
}

function renderMetrics() {
  const joints = state.project.layers.flatMap(layer => layer.joints || []);
  const segments = state.project.drives.flatMap(drive => drive.segments || []);
  $('#metricLayers').textContent = state.project.layers.length;
  $('#metricJoints').textContent = joints.length;
  $('#metricSegments').textContent = segments.length;
  $('#metricPairs').textContent = state.project.distance_pairs.length;
}

function hubCatalogProject(projectId) {
  return state.projects.find(item => String(item?.id || '') === String(projectId || '')) || null;
}

function primeHubPreviewFromCatalog(projectId, {preserveExisting = false} = {}) {
  if (!projectId) return null;
  if (preserveExisting && state.hubPreview?.id === projectId && !state.hubPreview?._summary_only) return state.hubPreview;
  const item = hubCatalogProject(projectId);
  if (!item) return null;
  const archiveFields = Array.isArray(item.critical_data) ? item.critical_data : [];
  state.hubPreview = {
    id:item.id, name:item.name, description:item.description || '', category:item.category || 'None', tags:item.tags || [],
    mesh_root:item.mesh_root || '', updated_at:item.updated_at || '', baseline_created_at:item.baseline_created_at || '',
    lifecycle_status:item.lifecycle_status || 'checked_in',
    lifecycle:{status:item.lifecycle_status || 'checked_in', checked_out_by:item.checked_out_by || '', baseline_created_at:item.baseline_created_at || ''},
    vz_push:item.vz_push || {enabled:false}, archive_fields:archiveFields,
    archive_order:archiveFields.map(field => field?.key).filter(Boolean), _summary_only:true,
  };
  state.hubPreviewLoading = true;
  return state.hubPreview;
}

function syncHubCatalogFromPreview(preview) {
  if (!preview?.id) return;
  state.projects = state.projects.map(item => item.id === preview.id ? {
    ...item,
    name:preview.name ?? item.name,
    description:preview.description ?? item.description,
    category:preview.category ?? item.category,
    tags:Array.isArray(preview.tags) ? preview.tags : item.tags,
    mesh_root:preview.mesh_root ?? item.mesh_root,
    updated_at:preview.updated_at ?? item.updated_at,
    baseline_created_at:preview.lifecycle?.baseline_created_at || preview.baseline_created_at || item.baseline_created_at,
    lifecycle_status:preview.lifecycle_status || preview.lifecycle?.status || item.lifecycle_status,
    checked_out_by:preview.lifecycle?.checked_out_by ?? item.checked_out_by,
    vz_push:preview.vz_push || item.vz_push,
    // Baseline previews are authoritative projections of the frozen ProjectSpec;
    // restore their ◆ source flag together with the numeric fields.  An ordinary
    // model's newest archive still wins over its mutable live preview.
    critical_source:(preview.lifecycle_status || preview.lifecycle?.status) === 'baseline'
      ? 'baseline' : item.critical_source,
    critical_data:item.critical_source === 'archive' && (preview.lifecycle_status || preview.lifecycle?.status) !== 'baseline'
      ? item.critical_data : (Array.isArray(preview.archive_fields) ? preview.archive_fields : item.critical_data),
  } : item);
}

function reorderHubArchiveFields(fields, order) {
  const byKey = new Map((fields || []).map(item => [String(item?.key || ''), item]));
  const result = [];
  const seen = new Set();
  (order || []).forEach(key => {
    const normalized = String(key || '');
    const item = byKey.get(normalized);
    if (item && !seen.has(normalized)) { result.push(item); seen.add(normalized); }
  });
  (fields || []).forEach(item => {
    const key = String(item?.key || '');
    if (key && !seen.has(key)) { result.push(item); seen.add(key); }
  });
  return result;
}

function applyHubPropertyUpdate(result, {archiveFields = null} = {}) {
  if (!result?.id) return;
  const projectId = result.id;
  const canonicalOrder = Array.isArray(result.archive_order) ? result.archive_order : null;
  state.projects = state.projects.map(item => item.id === projectId ? {
    ...item,
    name:result.name ?? item.name,
    updated_at:result.updated_at ?? item.updated_at,
    lifecycle_status:result.lifecycle_status || item.lifecycle_status,
    checked_out_by:result.lifecycle?.checked_out_by ?? item.checked_out_by,
    critical_data:archiveFields || (canonicalOrder ? reorderHubArchiveFields(item.critical_data || [], canonicalOrder) : item.critical_data),
  } : item);
  if (state.hubPreview?.id === projectId) {
    const nextFields = archiveFields || (canonicalOrder ? reorderHubArchiveFields(state.hubPreview.archive_fields || [], canonicalOrder) : state.hubPreview.archive_fields);
    state.hubPreview = {
      ...state.hubPreview,
      name:result.name ?? state.hubPreview.name,
      updated_at:result.updated_at ?? state.hubPreview.updated_at,
      lifecycle_status:result.lifecycle_status || state.hubPreview.lifecycle_status,
      lifecycle:result.lifecycle || state.hubPreview.lifecycle,
      archive_order:canonicalOrder || state.hubPreview.archive_order,
      archive_fields:nextFields,
      _summary_only:false,
    };
    const cached = state.hubPreviewCache.get(projectId);
    if (cached?.preview) state.hubPreviewCache.set(projectId, {...cached, preview:{...cached.preview, ...state.hubPreview}});
    state.hubPreviewLoadedAt.set(projectId, Date.now());
  }
  if (state.project?.id === projectId) {
    if (result.name != null) state.project.name = result.name;
    if (canonicalOrder) state.project.archive_order = [...canonicalOrder];
    if (result.updated_at != null) state.project.metadata.updated_at = result.updated_at;
    if (result.delivery_name_suffix != null) state.project.metadata.delivery_name_suffix = result.delivery_name_suffix;
  }
  renderHub();
}

function hubPreviewCacheEntry(projectId) {
  if (!projectId) return null;
  const loadedAt = state.hubPreviewLoadedAt.get(projectId) || 0;
  const cached = state.hubPreviewCache.get(projectId) || null;
  if (!cached?.preview || !loadedAt || Date.now() - loadedAt >= HUB_REFRESH_TTL_MS) return null;
  return cached;
}

function applyHubPreviewCache(projectId, cached) {
  if (!cached?.preview || state.hubSelectedProjectId !== projectId) return false;
  state.hubPreview = cached.preview;
  syncHubCatalogFromPreview(cached.preview);
  state.hubVersions = Array.isArray(cached.versions) ? cached.versions : [];
  state.hubFiles = cached.files || null;
  state.hubTypeSummary = null;
  state.hubPreviewLoading = false;
  if (state.project?.id === projectId && !state.dirty) {
    applyDrivePreview(projectId, cached.preview, {render:true});
  }
  renderHub();
  return true;
}

async function _loadHubPreview(projectId, {waitForMetadata = true} = {}) {
  if (!projectId) return;
  const selectedAtStart = projectId;
  const revision = ++state.hubPreviewRevision;

  // Reserve this project's cache revision before IO so late responses cannot
  // overwrite a newer forced reload of the same model.
  state.hubPreviewCache.set(projectId, {preview:null, versions:null, files:null, revision});
  state.hubPreviewLoadedAt.delete(projectId);
  state.hubPreviewLoading = true;

  const projectChanged = !state.hubPreview || state.hubPreview.id !== projectId;
  if (projectChanged) {
    state.hubPreviewVersionId = null;
    state.hubVersions = [];
    state.hubFiles = null;
  }
  renderHub();

  let preview = null;
  try {
    preview = await api(`/api/projects/${projectId}/preview?include_latest_result=false`, {timeout:10000});
    const reserved = state.hubPreviewCache.get(projectId);
    if (reserved?.revision !== revision) return;

    state.hubPreviewCache.set(projectId, {preview, versions:null, files:null, revision});
    state.hubPreviewLoadedAt.set(projectId, Date.now());

    if (state.hubSelectedProjectId === selectedAtStart) {
      state.hubPreview = {...preview, _summary_only:false};
      syncHubCatalogFromPreview(preview);
      state.hubTypeSummary = null;
      state.hubPreviewLoading = false;
      if (state.project?.id === projectId && !state.dirty) {
        applyDrivePreview(projectId, preview, {render:true});
      }
      renderHub();
    }
  } catch (error) {
    const reserved = state.hubPreviewCache.get(projectId);
    if (reserved?.revision === revision) {
      state.hubPreviewCache.delete(projectId);
      state.hubPreviewLoadedAt.delete(projectId);
    }
    if (state.hubSelectedProjectId === selectedAtStart) {
      state.hubPreviewLoading = false;
      renderHub();
      toast(`项目属性读取失败：${error.message}`, 'error');
    }
    return;
  }

  // Versions/files are secondary metadata and share the same 10-minute
  // per-project page-memory cache. A full browser refresh clears this Map.
  const metadataTask = Promise.allSettled([
    state.auth?.role === 'guest'
      ? Promise.resolve([])
      : api(`/api/projects/${projectId}/versions`, {timeout:12000}),
    api(`/api/projects/${projectId}/files`, {timeout:12000}),
  ]).then(([versionsResult, filesResult]) => {
    const cached = state.hubPreviewCache.get(projectId);
    if (!cached || cached.revision !== revision) return;

    const updated = {
      ...cached,
      versions: versionsResult.status === 'fulfilled' ? versionsResult.value : [],
      files: filesResult.status === 'fulfilled' ? filesResult.value : null,
    };
    state.hubPreviewCache.set(projectId, updated);

    if (versionsResult.status !== 'fulfilled') {
      console.warn('[hub-preview] versions failed:', versionsResult.reason);
    }
    if (filesResult.status !== 'fulfilled') {
      console.warn('[hub-preview] files failed:', filesResult.reason);
    }

    if (state.hubSelectedProjectId === selectedAtStart) {
      state.hubVersions = updated.versions;
      state.hubFiles = updated.files;
      renderHub();
    }
  });

  if (waitForMetadata) await metadataTask;
  else void metadataTask.catch(error => console.warn('[hub-preview] metadata render failed:', error));
}

async function loadHubPreview(projectId, options = {}) {
  if (!projectId) return;

  if (!options.force) {
    const cached = hubPreviewCacheEntry(projectId);
    if (cached) {
      applyHubPreviewCache(projectId, cached);
      return cached.preview;
    }
  }

  const active = state.hubPreviewRequest;
  if (active?.projectId === projectId) return active.promise;

  const promise = _loadHubPreview(projectId, options);
  state.hubPreviewRequest = {projectId, promise};
  try {
    return await promise;
  } finally {
    if (state.hubPreviewRequest?.promise === promise) state.hubPreviewRequest = null;
  }
}

async function renameProjectRoot() {
  if(!(state.auth?.role==='admin'||state.auth?.admin_mode)) return toast('修改项目名称需要管理员权限/管理模式','error');
  const name=prompt('项目名称',state.projectRootName||'项目'); if(!name?.trim())return;
  try{const result=await api('/api/project-root/name',{method:'PUT',body:JSON.stringify({name:name.trim()})});state.projectRootName=result.name;renderHub();if($('#hubProjectRoot'))$('#hubProjectRoot').textContent=result.name;toast('项目名称已更新');}catch(error){toast(error.message,'error');}
}

async function loadHubTypeSummary(category) {
  clearHubProjectSelection({clearTypeSummary:false});
  if (!category || category === 'None' || category === '全部项目') {
    state.hubTypeSummary = {
      category:'None', name:state.projectRootName||'项目',
      can_manage:Boolean(state.auth?.role === 'admin' || state.auth?.admin_mode),
    };
    renderHub();
    return;
  }
  const node = flattenModelTypes(state.modelTypes).find(item => item.path === category);
  if (!node) {
    state.hubTypeSummary = null;
    renderHub();
    toast('项目文件夹不存在或已被刷新，请重新选择', 'error');
    return;
  }
  state.hubTypeSummary = {
    category:node.path, name:node.name || node.path.split('/').pop(),
    owner:node.owner || '', can_manage:Boolean(node.can_manage),
  };
  renderHub();
}

function renderHub() {
  if (!$('#hubProjectList')) return;
  $('#vzEngineerButton')?.classList.toggle('hidden', !['engineer','admin'].includes(state.auth?.role));
  const recycleMode = state.hubCategory === '__recycle_bin__';
  $('#hubProjectCount').textContent = recycleMode ? state.recycleBin.length : state.projects.length;
  const deleteCategoryButton = $('#hubDeleteCategoryButton');
  const toggleAllButton = $('#hubToggleAllCategoriesButton');
  const collapsiblePaths = collapsibleModelTypePaths();
  const allCollapsed = collapsiblePaths.length > 0 && collapsiblePaths.every(path => state.hubCollapsedModelTypes.has(path));
  if (toggleAllButton) {
    toggleAllButton.disabled = !collapsiblePaths.length;
    toggleAllButton.classList.toggle('is-expand', allCollapsed);
    toggleAllButton.title = allCollapsed ? '展开全部文件夹' : '折叠全部文件夹';
    toggleAllButton.setAttribute('aria-label', toggleAllButton.title);
    toggleAllButton.setAttribute('aria-pressed', String(!allCollapsed));
  }
  const selectedType = flattenModelTypes(state.modelTypes).find(node => node.path === state.hubCategory);
  if (deleteCategoryButton) deleteCategoryButton.disabled = recycleMode || state.hubCategory === 'None' || !selectedType?.can_manage;
  const typeRows = flattenVisibleModelTypes(state.modelTypes).filter(node => node.path !== 'None').map(node => { const hasChildren=Boolean(node.children?.length), collapsed=state.hubCollapsedModelTypes.has(node.path), canMove=node.can_manage; return `<div class="hub-category child ${state.hubCategory === node.path ? 'active' : ''}" style="--tree-depth:${node.depth}" data-category="${esc(node.path)}" data-model-type="${esc(node.path)}" title="${esc(node.can_manage ? `创建者：${node.owner || '系统'}；可拖拽调整层级和顺序` : `创建者：${node.owner || '旧版目录'}；进入管理模式后可移动或删除`)}"><span class="hub-category-drag-handle ${canMove ? '' : 'disabled'}" ${canMove ? `draggable="true" data-model-type-drag="${esc(node.path)}" title="拖拽移动文件夹：上/下边缘调整同级顺序，中部移入目标文件夹"` : 'aria-hidden="true"'}>⠿</span><button type="button" class="hub-category-fold ${hasChildren ? '' : 'empty'}" data-action="hub-toggle-category" data-category="${esc(node.path)}" aria-expanded="${hasChildren ? String(!collapsed) : 'false'}" ${hasChildren ? `title="${collapsed ? '展开文件夹' : '折叠文件夹'}"` : 'disabled title="没有子文件夹"'}>${hasChildren ? (collapsed ? '▸' : '▾') : '·'}</button><button type="button" class="hub-category-main" data-action="hub-category" data-category="${esc(node.path)}"><span><i>📁</i>${esc(node.name)}</span></button><b>${node.count || 0}</b></div>`; });
  const rootProjectCount = state.projects.length;
  $('#hubCategoryTree').innerHTML = [
    `<button class="hub-category ${state.hubCategory === 'None' ? 'active' : ''}" data-action="hub-category" data-category="None" data-model-root="true" title="根项目文件夹：显示根层模型，并穿透显示各后代文件夹最新基线；可将模型拖到这里取消分类"><span class="hub-category-root-label"><i>🗂️</i>${esc(state.projectRootName||'项目')}</span><b>${rootProjectCount}</b></button>`,
    ...typeRows,
  ].join('');
  const recycleSlot = $('#hubRecycleBinSlot');
  if (recycleSlot) recycleSlot.innerHTML = ['engineer','admin'].includes(state.auth?.role)
    ? `<button class="hub-category recycle-bin ${recycleMode ? 'active' : ''}" data-action="hub-category" data-category="__recycle_bin__" title="删除的模型保留 ${state.trashRetentionDays} 天，可在此恢复"><span class="hub-category-root-label"><i>🗑️</i>回收站</span><b>${state.recycleBin.length}</b></button>`
    : '';
  const query = ($('#hubProjectSearch').value || '').trim().toLowerCase();
  const baselineSortDescending = Boolean(state.hubBaselineSortDescending);
  const baselineSortToggle = $('#hubBaselineSortToggle');
  if (baselineSortToggle) {
    baselineSortToggle.textContent = baselineSortDescending ? '基线：晚 → 早' : '基线：早 → 晚';
    baselineSortToggle.setAttribute('aria-pressed', String(baselineSortDescending));
    baselineSortToggle.disabled = recycleMode;
  }
  if (recycleMode) {
    const items = state.recycleBin.filter(item => !query || [item.name,item.category,item.project_id].join(' ').toLowerCase().includes(query))
      .sort((a,b) => String(b.deleted_at||'').localeCompare(String(a.deleted_at||'')));
    const visibleTrashIds = new Set(items.map(item => String(item.trash_id || '')).filter(Boolean));
    // Search filtering must never leave hidden selections queued for permanent deletion.
    state.hubSelectedTrashIds = new Set([...state.hubSelectedTrashIds].filter(id => visibleTrashIds.has(id)));
    const selectedCount = state.hubSelectedTrashIds.size;
    const allVisibleSelected = items.length > 0 && items.every(item => state.hubSelectedTrashIds.has(item.trash_id));
    $('#hubProjectList').classList.toggle('empty-state', !items.length);
    $('#hubProjectList').innerHTML = items.length ? `
      <div class="hub-trash-toolbar">
        <label class="hub-trash-select-all"><input id="hubTrashSelectAll" type="checkbox" data-action="hub-trash-select-all" ${allVisibleSelected ? 'checked' : ''}><span>全选当前列表</span></label>
        <span>已选 ${selectedCount} / ${items.length}</span>
        <button class="button tiny danger" data-action="hub-delete-selected-trash" ${selectedCount ? '' : 'disabled'}>永久删除已选${selectedCount ? ` (${selectedCount})` : ''}</button>
      </div>
      ${items.map(item => `<article class="hub-project-card recycle-card">
        <label class="hub-trash-select" title="选择该模型"><input type="checkbox" data-action="hub-trash-toggle" data-trash-id="${esc(item.trash_id)}" ${state.hubSelectedTrashIds.has(item.trash_id) ? 'checked' : ''}><span>选择</span></label>
        <div class="hub-project-main"><strong><span class="hub-model-name">${esc(item.name || item.project_id)}</span><span class="project-name-marker">🗑️</span><span class="project-name-status">原类型：${esc(item.category || 'None')}</span></strong><small>删除 ${formatDate(item.deleted_at)} · 保留至 ${formatDate(item.expires_at)}</small></div>
        <button class="button tiny primary" data-action="hub-restore-trash" data-trash-id="${esc(item.trash_id)}">恢复模型</button>
      </article>`).join('')}` : `回收站为空；删除的模型会保留 ${state.trashRetentionDays} 天。`;
    renderHubPreview();
    return;
  }
  const catalogProjects = query ? state.projects : hubCategoryProjects(state.hubCategory);
  const projects = catalogProjects.filter(project => {
    return !query || [project.name, project.description, project.mesh_root, project.category || 'None', ...(project.tags || [])].join(' ').toLowerCase().includes(query);
  }).sort((a, b) => {
    // V2.16.11.3: a signed-out editing model belongs above the historical
    // baseline/checked-in catalog. The currently selected checkout is first.
    const activeCheckout = item => projectStatus(item) === 'checked_out';
    const selectedCheckout = item => activeCheckout(item) && item.id === state.hubSelectedProjectId;
    if (selectedCheckout(a) !== selectedCheckout(b)) return selectedCheckout(a) ? -1 : 1;
    if (activeCheckout(a) !== activeCheckout(b)) return activeCheckout(a) ? -1 : 1;
    const baselineOrder=(projectStatus(a)==='baseline')-(projectStatus(b)==='baseline');
    if(baselineOrder)return baselineOrder;
    if(projectStatus(a)==='baseline'&&projectStatus(b)==='baseline') {
      const direction = baselineSortDescending ? -1 : 1;
      return direction * (hubBaselineFrozenAt(a).localeCompare(hubBaselineFrozenAt(b)) || Number(a.version_index || 0)-Number(b.version_index || 0));
    }
    return String(b.updated_at || '').localeCompare(String(a.updated_at || '')) || a.name.localeCompare(b.name, 'zh-CN');
  });
  $('#hubProjectList').classList.toggle('empty-state', !projects.length);
  $('#hubProjectList').innerHTML = projects.length ? projects.map(project => {
    const selected = project.id === state.hubSelectedProjectId;
    const status = projectStatus(project);
    const critical = (project.critical_data || []).map(formatCriticalData).filter(Boolean).join('，');
    const source = project.critical_source || 'current';
    const badgeTitle = source === 'baseline' ? '基线冻结关键数据 · 固定锚点'
      : source === 'archive' ? '最近存档版本的关键数据 · 点击模型不会改变这份历史快照'
      : source === 'unavailable' ? '关键数据读取失败，下次自动重试'
      : source === 'pending' ? '项目列表已就绪，关键数据将在查看模型时读取' : '当前模型的关键数据';
    const archiveMarkup = critical
      ? `<span class="hub-archive-chip version ${source === 'baseline' ? 'baseline-anchor' : ''}" title="${esc(badgeTitle)}">${source === 'baseline' ? '◆ ' : ''}${esc(critical)}</span>`
      : `<span class="hub-archive-empty" title="${esc(badgeTitle)}">${source === 'unavailable' ? '关键数据暂不可用' : source === 'pending' ? '关键数据按需加载' : '暂无关键数据'}</span>`;
    const pushedLabel = project.vz_push?.enabled ? '<span class="hub-pushed-label" title="该模型当前已同步到 VZ 推送库">【已推送】</span>' : '';
    return `<article class="hub-project-card ${selected ? 'active' : ''}" draggable="${status !== 'baseline'}" data-action="hub-select-project" data-project-id="${esc(project.id)}" title="${status === 'baseline' ? '基线不可重新分类' : '按住并拖到左侧项目列表文件夹可重新分类并自动重命名'}">
      <div class="hub-project-main"><strong><span class="hub-model-name">${esc(project.name)}</span><span class="project-name-marker ${esc(status)}" title="${esc(lifecycleLabel(status))}">${esc(projectNameMarker(status))}</span><span class="project-name-status ${esc(status)}">${esc(lifecycleLabel(status))}${project.checked_out_by ? ` · ${esc(project.checked_out_by)}` : ''}</span><span class="hub-card-archive-data">${archiveMarkup}</span>${pushedLabel}</strong><small class="${status === 'baseline' ? 'hub-baseline-frozen-time' : ''}">${query ? `文件夹：${esc(project.category || state.projectRootName || '项目')} · ` : ''}${status === 'baseline' ? `<b>冻结时间</b> ${formatDate(hubBaselineFrozenAt(project))}` : `上次修改 ${formatDate(project.updated_at)}`}</small></div>
    </article>`;
  }).join('') : '没有匹配模型';
  renderHubPreview();
}

function renderHubPreview() {
  const selectedPreviewReady = Boolean(state.hubPreview?.id && state.hubPreview.id === state.hubSelectedProjectId);
  $('#hubPreviewLoading')?.classList.toggle('hidden', !state.hubPreviewLoading || selectedPreviewReady);
  const folderPropertiesMode = Boolean(state.hubTypeSummary) && state.hubCategory !== '__recycle_bin__';
  const inspectorPanel = $('#hubInspector')?.closest('.hub-inspector');
  // Keep the inspector in the rightmost grid cell when selecting folders.
  // V2.11.7 used to hide it and collapse four columns to three, which also
  // detached the V2.13.6 project-list width splitter from its saved width.
  if (inspectorPanel) inspectorPanel.hidden = false;
  $('.hub-workspace')?.classList.toggle('hub-folder-properties-mode', folderPropertiesMode);
  $('#hubReloadGanttPreview')?.classList.toggle('hidden', folderPropertiesMode);
  if (state.hubCategory === '__recycle_bin__') {
    $('#hubPreviewTitle').textContent='回收站';
    $('#hubPreviewSubtitle').textContent=`模型保留 ${state.trashRetentionDays} 天后自动清理`;
    $('#hubPreview').innerHTML=`<section class="hub-type-summary recycle-summary"><div class="hub-preview-head"><div><h3>🗑️ 模型回收站</h3><small>管理员和工程师可见 · ${state.recycleBin.length} 个待清理模型</small></div></div><p>删除操作不会立即物理销毁模型；在保留期内可恢复到原模型类型与原目录，也可多选后执行“永久删除已选”。永久删除不可恢复；恢复遇到同 ID 或原交付目录冲突时会拒绝覆盖。</p></section>`;
    $('#hubGanttQuick').hidden=true;
    $('#hubInspectorTitle').textContent='回收站说明';
    $('#hubInspectorSubtitle').textContent='恢复不会覆盖现有模型';
    $('#hubInspector').className='hub-inspector-body empty-state';
    $('#hubInspector').textContent=`超过 ${state.trashRetentionDays} 天的条目会由服务端自动清理。`;
    return;
  }
  if (state.hubTypeSummary) {
    const summary = state.hubTypeSummary;
    const rename = Boolean(summary.can_manage);
    $('#hubPreviewTitle').textContent = '项目文件夹属性';
    $('#hubPreviewSubtitle').textContent = '';
    document.querySelector('.hub-gantt-preview-floating')?.remove();
    $('#hubGanttQuick').hidden = true;
    $('#hubPreview').innerHTML = `<section class="hub-folder-properties">
      <label class="compact-label">文件夹名称<input id="hubTypeNameInput" value="${esc(summary.name || '')}" maxlength="80" ${rename ? '' : 'disabled'}></label>
      ${rename ? '<button class="button tiny primary" data-action="hub-rename-folder">保存名称</button>' : ''}
    </section>`;
    renderHubInspectorDetail();
    return;
  }
  $('#hubPreviewTitle').textContent = '模型属性';
  $('#hubGanttQuick')?.classList.remove('type-summary-preview');
  $('#hubPreviewSubtitle').textContent = '';
  const preview = state.hubPreview;
  if (!preview || preview.id !== state.hubSelectedProjectId) {
    document.querySelector('.hub-gantt-preview-floating')?.remove();
    $('#hubGanttQuick').hidden = true;
    const waiting = Boolean(state.hubSelectedProjectId && state.hubPreviewLoading);
    $('#hubPreview').innerHTML = `<div class="empty-state">${waiting ? '正在读取模型属性…' : '请选择模型查看属性'}</div>`;
    renderHubInspectorDetail();
    return;
  }
  const status = preview.lifecycle_status || preview.lifecycle?.status || 'checked_in';
  const editable = status === 'checked_out' && !state.hubPreviewVersionId;
  const nameEditable = !state.hubPreviewVersionId && (editable || (status === 'baseline' && ['engineer','admin'].includes(state.auth?.role)));
  const hasCategory = preview.category && preview.category !== 'None';
  const lifecycleActions = state.auth?.role === 'guest' ? '' : status === 'checked_in'
    ? `<button class="button tiny primary" data-action="hub-check-out">签出</button><button class="button tiny ghost" data-action="hub-copy-version" title="复制当前模型">复制</button><button class="button tiny ghost" data-action="hub-create-baseline" ${hasCategory ? '' : 'disabled title="请先拖入一个分类"'}>打基线</button>`
    : status === 'checked_out'
      ? '<button class="button tiny primary" data-action="hub-check-in">签入</button>'
      : status === 'baseline'
        ? '<button class="button tiny primary" data-action="hub-fork-project">使用版本</button>'
        : '';
  const deleteAction = state.auth?.role === 'guest' ? '' : '<button class="button tiny danger" data-action="hub-delete-project" title="删除当前模型">删除</button>';
  const files = state.hubFiles || {};
  const assets = files.model_assets || [];
  const delivery = files.delivery_outputs || [];
  const timeSeries = files.time_series_library || [];
  const tableAssets = files.table_assets || [];
  const archiveFields = preview.archive_fields || [];
  const section = state.auth?.role === 'guest' ? 'delivery_outputs' : (state.hubInspectorSection || 'model_assets');
  if (state.auth?.role === 'guest') state.hubInspectorSection = 'delivery_outputs';
  const propertyRows = state.auth?.role === 'guest'
    ? [{key:'delivery_outputs', icon:'↗', label:'交付数据', meta:`${delivery.length} 个文件`}]
    : [
      {key:'model_assets', icon:'◫', label:'数模资产', meta:`${assets.length} 个文件`},
      {key:'table_assets', icon:'▤', label:'表格资产', meta:`${tableAssets.length} 张表格`},
      {key:'time_series_library', icon:'▦', label:'时序库', meta:`${timeSeries.length} 个 TSJSON`},
      {key:'delivery_outputs', icon:'↗', label:'交付数据', meta:`${delivery.length} 个文件`},
      {key:'archive_log', icon:'◷', label:'存档日志', meta:status === 'baseline' ? '冻结基线' : `${Math.min(state.hubVersions.length, state.archiveLimit)} 条`},
    ];
  const propertyMarkup = `<section class="hub-property-nav" aria-label="模型属性对象">${propertyRows.map(item => `<button type="button" class="hub-property-row ${section === item.key ? 'active' : ''}" data-action="hub-inspector-section" data-inspector-section="${item.key}" aria-current="${section === item.key ? 'true' : 'false'}"><span><i>${item.icon}</i><b>${item.label}</b></span><small>${esc(item.meta)}</small><em>›</em></button>`).join('')}</section>`;
  const vzPush = preview.vz_push || {};
  const vzPushControl = state.auth?.role === 'guest' || state.hubPreviewVersionId ? '' : `<label class="hub-vz-push-control" title="开启后，该模型会出现在 VZ 用户网址的模型库中"><span>推送模型</span><span class="hub-vz-push-switch"><input type="checkbox" role="switch" data-action="hub-vz-push" ${vzPush.enabled ? 'checked' : ''}><i aria-hidden="true"></i></span></label>`;
  $('#hubPreview').innerHTML = `<label class="compact-label hub-model-name-row"><span>模型名称 ${projectNameMarker(status)}</span><input id="hubProjectNameInput" value="${esc(preview.name)}" maxlength="160" ${nameEditable ? '' : 'disabled'}></label>
    <div class="hub-vz-status-row"><span class="project-status ${esc(status)}">${esc(lifecycleLabel(status))}${preview.lifecycle?.checked_out_by ? ` · 由 ${esc(preview.lifecycle.checked_out_by)} 签出` : ''}</span>${vzPushControl}</div>
    <small class="hub-model-directory">服务端目录：${esc(files.model_directory || preview.category || 'None')}</small>
    ${propertyMarkup}
    <div class="hub-preview-actions">${lifecycleActions}${deleteAction}</div>
    <section class="hub-name-fields hub-critical-data-bottom"><div class="compact-heading"><strong>关键数据</strong></div><div id="hubArchiveOrder">${preview._summary_only && !archiveFields.length ? '<div class="hub-critical-loading">详细关键数据读取中…</div>' : archiveFields.map(item => `<div draggable="${editable}" data-archive-key="${esc(item.key)}"><span>⠿</span><b>${esc(item.label)}：</b><strong>${esc(formatCriticalData(item))}</strong></div>`).join('')}</div></section>`;
  const projectId = preview.id || state.hubSelectedProjectId;
  if (projectId && state.auth?.role !== 'guest' && typeof window.__refreshHubGanttPreview === 'function') queueMicrotask(() => window.__refreshHubGanttPreview(projectId));
  queueMicrotask(bindArchiveDragOrder);
  renderHubInspectorDetail();
}



function hubInspectorDefaultSection() {
  return state.auth?.role === 'guest' ? 'delivery_outputs' : 'model_assets';
}

function modelAssetCanMaintain() {
  const manager = state.modelAssetManager || {};
  const context = state.modelAssetManagerContext || {};
  return ['engineer','admin'].includes(state.auth?.role) && Boolean(manager.writable) && !Boolean(context.frozen || manager.frozen);
}

function modelAssetCanBindSelected() {
  const manager = state.modelAssetManager || {};
  const context = state.modelAssetManagerContext || {};
  const folder = manager.folders?.find(item => item.name === manager.selected);
  const projectCategory = String(context.category || state.hubPreview?.category || '').toLowerCase();
  const managerCategory = String(manager.category || '').toLowerCase();
  return context.mode === 'bind' && context.editable && !context.frozen && Boolean(folder?.reference)
    && projectCategory === managerCategory && folder.reference !== context.current;
}

function renderHubAssetInspector() {
  const manager = state.modelAssetManager || {category:'',folders:[],selected:'',files:[]};
  const context = state.modelAssetManagerContext || {};
  if (!state.hubSelectedProjectId || context.mode !== 'bind' || context.projectId !== state.hubSelectedProjectId) return '<div class="empty-state">请选择模型后查看数模资产。</div>';
  if (state.hubInspectorAssetLoading) return '<div class="hub-inspector-loading"><span class="hub-preview-spinner"></span><strong>正在读取数模资产库…</strong></div>';
  const frozen = Boolean(context.frozen || manager.frozen);
  const canMaintain = modelAssetCanMaintain();
  const selectedFolder = manager.folders?.find(item => item.name === manager.selected);
  const folderRows = (manager.folders || []).map(folder => {
    const uploader = folder.uploaded_by ? folder.uploaded_by : '未记录';
    const secondLine = `上传用户：${uploader} · ${modelAssetUsageText(folder)} · ${folder.file_count || 0} 文件 · ${formatBytes(folder.size_bytes || 0)}`;
    return `<button type="button" class="hub-asset-folder ${folder.name === manager.selected ? 'active' : ''} ${folder.frozen ? 'frozen' : ''}" data-action="hub-asset-select-folder" data-asset-folder="${esc(folder.name)}" ${frozen ? 'disabled' : ''}><span><strong>📁 ${esc(folder.name)}</strong><small>${esc(secondLine)}</small></span></button>`;
  }).join('') || '<p class="empty-state">当前模型类型还没有数模版本。</p>';
  const fileRows = !selectedFolder ? '<p class="empty-state">请选择上方数模版本。</p>' : (manager.files || []).map(item => item.kind === 'folder'
    ? `<div class="hub-asset-file folder"><span>📁 ${esc(item.path)}</span></div>`
    : `<div class="hub-asset-file"><span><b>${esc(item.path)}</b><small>${formatBytes(item.size || 0)}</small></span><div class="hub-asset-file-actions">${item.url ? `<a class="hub-asset-icon-action" href="${esc(item.url)}" download title="下载" aria-label="下载">⇩</a>` : ''}${canMaintain ? `<button class="hub-asset-icon-action danger" type="button" data-action="hub-asset-delete-file" data-asset-path="${esc(item.path)}" title="删除" aria-label="删除">×</button>` : ''}</div></div>`).join('') || '<p class="empty-state">当前版本为空，可上传 STL/OBJ 文件或包含贴图的文件夹。</p>';
  const bindingHint = frozen
    ? `基线冻结资产：${context.current || '冻结目录'}。只能查看和下载。`
    : context.mode === 'bind' && !context.editable
      ? `当前绑定：${context.current || '未绑定'}。模型需先签出才可重新绑定；资产库维护不受签出状态影响。`
      : context.mode === 'bind' && String(manager.category || '').toLowerCase() !== String(state.hubPreview?.category || '').toLowerCase()
        ? `正在浏览其他模型类型的公共资产库；只能维护，不能绑定到当前“${state.hubPreview?.category || 'None'}”模型。`
        : `当前绑定：${context.current || '未绑定'}。选择版本后显式“绑定到当前模型”才会修改模型。`;
  return `<section class="hub-inspector-section hub-asset-inspector">
    <div class="hub-inspector-toolbar hub-asset-toolbar-inline">
      <div class="hub-inspector-toolbar-actions hub-asset-primary-actions">
        <button class="button tiny ghost" data-action="hub-asset-new-version" ${canMaintain ? '' : 'disabled'}>＋ 新建文件夹</button>
        <button class="button tiny ghost" data-action="hub-asset-copy-version" ${canMaintain && selectedFolder ? '' : 'disabled'}>复制文件夹</button>
        <button class="button tiny ghost" data-action="hub-asset-rename-version" ${canMaintain && selectedFolder ? '' : 'disabled'}>修改名称</button>
        <button class="button tiny danger" data-action="hub-asset-delete-version" ${canMaintain && selectedFolder && !selectedFolder.usage_count ? '' : 'disabled'}>删除文件夹</button>
      </div>
    </div>
    <div class="hub-asset-split" style="--hub-asset-top:${Math.round(state.hubInspectorAssetSplitRatio*100)}%">
      <section class="hub-asset-folder-pane">
        <div class="hub-inspector-subhead hub-asset-pane-title"><span class="hub-asset-version-heading"><strong>数模版本</strong><small>${manager.root || '公共数模资产库'}</small></span><span class="badge">${manager.folders?.length || 0}</span></div>
        <div class="hub-asset-folder-list">${folderRows}</div>
      </section>
      <div class="hub-asset-splitter" data-hub-asset-splitter role="separator" aria-orientation="horizontal" aria-label="调整数模版本与文件列表高度" tabindex="0"><span></span></div>
      <section class="hub-asset-file-pane">
        <div class="hub-inspector-subhead hub-asset-file-title"><span><strong>${esc(selectedFolder?.name || '数模文件')}</strong><small>${selectedFolder ? `${selectedFolder.file_count || 0} 文件 · ${formatBytes(selectedFolder.size_bytes || 0)}` : '选择数模版本查看文件'}</small></span>
          <div class="hub-inspector-toolbar-actions">
            <button class="button tiny ghost hub-asset-file-action-large" data-action="hub-asset-upload-files" ${canMaintain && selectedFolder ? '' : 'disabled'}>上传文件</button>
            <button class="button tiny ghost hub-asset-file-action-large" data-action="hub-asset-download-folder" ${selectedFolder && (selectedFolder.file_count || 0) ? '' : 'disabled'}>批量下载</button>
            <button class="button tiny danger hub-asset-file-action-large" data-action="hub-asset-clear-folder" ${canMaintain && selectedFolder && (selectedFolder.file_count || 0) ? '' : 'disabled'}>清空</button>
          </div>
        </div>
        <div class="hub-asset-file-grid">${fileRows}</div>
      </section>
    </div>
    <footer class="hub-inspector-footer"><small>${esc(bindingHint)}</small>${context.mode === 'bind' && !frozen ? `<button class="button tiny primary" data-action="hub-asset-bind" ${modelAssetCanBindSelected() ? '' : 'disabled'}>绑定到当前模型</button>` : ''}</footer>
  </section>`;
}

function safeDeliverySuffix(value) {
  return String(value || '').trim().replace(/[<>:"/\\|?*\x00-\x1f]+/g, '_').replace(/[\s._-]+$/g, '').replace(/^[\s._-]+/g, '').slice(0, 96);
}

function deliverySuggestedName(item, suffix='') {
  const original = String(item?.relative_path || item?.path || item?.name || 'delivery-file').replace(/\\/g,'/').split('/').pop() || 'delivery-file';
  const safeSuffix = safeDeliverySuffix(suffix);
  if (!safeSuffix) return original;
  const dot = original.lastIndexOf('.');
  if (dot <= 0) return `${original}_${safeSuffix}`;
  return `${original.slice(0,dot)}_${safeSuffix}${original.slice(dot)}`;
}

function renderHubDeliveryInspector() {
  const preview = state.hubPreview || {};
  const files = state.hubFiles || {};
  const projectId = preview.id || state.hubSelectedProjectId || '';
  const items = files.delivery_outputs || [];
  const status = preview.lifecycle_status || preview.lifecycle?.status || 'checked_in';
  const canMutate = ['engineer','admin'].includes(state.auth?.role) && status !== 'baseline';
  const suffix = state.hubDeliverySuffixByProject.get(projectId) || '';
  return `<section class="hub-inspector-section hub-delivery-inspector">
    <div class="hub-inspector-toolbar hub-delivery-compact-toolbar">
      <label class="hub-delivery-suffix-inline"><span>文件名后缀</span><input data-hub-delivery-suffix value="${esc(suffix)}" placeholder="例如：A版_100mm"></label>
      <div class="hub-delivery-action-row">
        <button class="button tiny ghost" data-action="hub-delivery-auto-suffix" ${preview.archive_fields?.length ? '' : 'disabled'}>自动填入</button>
        <button class="button tiny ghost" data-action="hub-delivery-download-all" ${items.length ? '' : 'disabled'}>全部批量下载</button>
        ${state.auth?.role === 'guest' ? '' : `<button class="button tiny danger" data-action="hub-delivery-clear" ${canMutate && items.length ? '' : 'disabled'}>清空交付数据</button>`}
      </div>
    </div>
    <small class="hub-inspector-note">仅影响本次下载的建议文件名，不修改服务器上的交付文件；“自动填入”按关键数据当前排序生成。</small>
    <div class="hub-delivery-directory-head"><strong>交付目录</strong><small>${items.length} 项${status === 'baseline' ? ' · 基线冻结' : ''}</small></div>
    <div class="hub-delivery-file-list">${items.length ? items.map(item => { const relative=item.relative_path||String(item.path||'').replace(/^delivery\//,''); const folder=item.node_type==='directory'; return `<div class="hub-delivery-file-row"><button type="button" data-action="hub-delivery-download" data-delivery-path="${esc(item.path)}" data-delivery-kind="${esc(item.kind||'')}"><span><b>${folder?'▣ ':''}${esc(deliverySuggestedName(item,suffix))}</b><small>${folder?`${Number(item.file_count)||0} 个 CSV · `:''}${esc(formatSavedTime(item.modified))}</small></span></button>${canMutate ? `<button class="button tiny danger" data-action="hub-delivery-delete" data-delivery-relative="${esc(relative)}">删除</button>` : ''}</div>`; }).join('') : '<p class="empty-state">当前交付目录为空。</p>'}</div>
  </section>`;
}

function renderHubTableAssetsInspector() {
  const files = state.hubFiles || {};
  const items = files.table_assets || [];
  return `<section class="hub-inspector-section hub-table-assets-inspector">
    <div class="hub-inspector-note">模型专属目录：<b>模型 / assets / tables</b>。映射表与外部运动表在导入时先备份，导出时从模型 JSON 的内嵌点表更新资产；同一驱动/运动段/表格类型永远只保留一份。这里不替代“交付数据 / 表格文件夹”。</div>
    <div class="hub-delivery-directory-head"><strong>表格资产</strong><small>${items.length} 张表格</small></div>
    <div class="hub-delivery-file-list">${items.length ? items.map(item => `<div class="hub-delivery-file-row"><a class="hub-time-series-download" href="${esc(item.url || '')}" download><span><b>▤ ${esc(item.label || item.name)}</b><small>${esc(item.kind)} · ${formatBytes(item.size || 0)} · ${esc(formatSavedTime(item.modified))}</small></span></a></div>`).join('') : '<p class="empty-state">暂无表格资产。导入映射电机/外部运动 CSV，或导出模型使用的表格后，会在此自动备份。</p>'}</div>
  </section>`;
}

function renderHubTimeSeriesInspector() {
  const preview = state.hubPreview || {};
  const files = state.hubFiles || {};
  const items = files.time_series_library || [];
  const status = preview.lifecycle_status || preview.lifecycle?.status || 'checked_in';
  const canMutate = ['engineer','admin'].includes(state.auth?.role) && status !== 'baseline';
  const mainCount = items.filter(item=>item.kind==='combined').length;
  const mappingCount = items.filter(item=>item.kind==='mapping').length;
  return `<section class="hub-inspector-section hub-time-series-inspector">
    <div class="hub-inspector-note">物理目录：<b>模型 / 时序库</b>。此处仅存放含完整驱动参数、运动段与曲线数据的 TSJSON。合并结果 CSV、旧版时序 CSV 和时序交换附表保存到<b>交付数据 / 表格文件夹</b>；模型使用的映射/外部运动表另归档在<b>表格资产</b>。向旧版 VZ 推送时临时转换 CSV，不落在这里。</div>
    <div class="hub-delivery-directory-head"><strong>时序库</strong><small>${items.length} 个 TSJSON</small></div>
    <div class="hub-delivery-file-list">${items.length ? items.map(item=>`<div class="hub-delivery-file-row"><a class="hub-time-series-download" href="${esc(item.url||'')}" download><span><b>▦ ${esc(item.name)}</b><small>TSJSON 时序交换文件 · ${formatBytes(item.size||0)} · ${esc(formatSavedTime(item.modified))}</small></span></a>${canMutate?`<button class="button tiny danger" data-action="hub-time-series-delete" data-time-series-name="${esc(item.name)}">删除</button>`:''}</div>`).join('') : '<p class="empty-state">暂无 TSJSON。请在模型签出后从仿真结果批量导出，或在 Lab 中编辑时序。</p>'}</div>
  </section>`;
}

async function deleteTimeSeriesFile(name) {
  const projectId = state.hubFiles?.project_id || state.hubSelectedProjectId;
  if (!projectId || !name || !confirm(`删除时序库文件“${name}”？${state.hubPreview?.vz_push?.enabled?'\n已推送 VZ 的模型会同步刷新。':''}`)) return;
  try {
    const response = await api(`/api/projects/${encodeURIComponent(projectId)}/time-series/${encodeURIComponent(name)}`, {method:'DELETE'});
    state.hubFiles = response.files;
    renderHubPreview();
    if (response.vz_sync?.error) toast(`时序库已删除，但 VZ 同步失败：${response.vz_sync.error}`, 'error');
    else toast(response.vz_sync?.synced ? '时序库已删除，VZ 已同步刷新' : '时序库文件已删除', 'success');
  } catch (error) { toast(error.message, 'error'); }
}

function renderHubArchiveInspector() {
  const preview = state.hubPreview || {};
  const status = preview.lifecycle_status || preview.lifecycle?.status || 'checked_in';
  if (status === 'baseline') {
    const log = String(preview.baseline_log || '').trim();
    return `<section class="hub-inspector-section hub-archive-inspector"><article class="hub-archive-card baseline"><header><div><strong>⚑ 基线版本</strong></div><time>${formatDate(preview.lifecycle?.baseline_created_at || preview.updated_at)}</time></header><p class="hub-archive-log-text">${log ? esc(log) : '未填写基线说明'}</p><small>这是冻结的基线模型本体；其来源模型的存档日志中另有一条“基线版本”记录。</small></article></section>`;
  }
  const versions = (state.hubVersions || []).slice(0, state.archiveLimit);
  const canManage = ['engineer','admin'].includes(state.auth?.role);
  return `<section class="hub-inspector-section hub-archive-inspector"><div class="hub-inspector-note">最多保留最近 ${state.archiveLimit} 个版本；日志统一只有“存档版本 / 基线版本”。最新工作版本始终保存；手动签入默认不另建历史版本，可按需勾选；系统自动签入仍会创建安全存档，打基线只新增一条基线版本记录，不改原模型当前状态。</div><div class="hub-archive-card-list">${versions.length ? versions.map(version => {
    const critical = version.critical_data_text || (version.critical_data || []).map(formatCriticalData).filter(Boolean).join('，') || '暂无关键数据';
    const isBaseline = version.version_kind === 'baseline';
    const versionLabel = isBaseline && version.baseline_name ? `基线版本 · ${version.baseline_name}` : (isBaseline ? '基线版本' : `存档版本 · ${version.archive_name || '未命名版本'}`);
    const title = version.actor ? `${isBaseline ? '基线创建人' : '存档人'}：${version.actor}` : versionLabel;
    return `<article class="hub-archive-card ${isBaseline ? 'baseline-entry' : 'archive-entry'}"><div class="hub-archive-critical-value">${esc(critical)}</div><div class="hub-archive-meta-row"><span class="hub-archive-version-meta" title="${esc(title)}">${esc(versionLabel)}</span><div class="hub-archive-head-actions"><time>${formatDate(version.archived_at || version.saved_at)}</time>${canManage ? `${status === 'checked_out' && !isBaseline ? `<button class="button tiny primary" data-action="hub-archive-restore" data-version-id="${esc(version.id)}" title="先保护当前状态，再恢复这一历史版本">回档</button>` : ''}<button class="button tiny danger" data-action="hub-archive-delete" data-version-id="${esc(version.id)}">删除存档</button><button class="button tiny ghost" data-action="hub-archive-cutout" data-version-id="${esc(version.id)}">切出为独立模型</button>` : ''}</div></div><p class="hub-archive-log-text">${esc(String(version.log || '').trim() || (isBaseline ? '未填写基线说明' : '未填写存档日志'))}</p></article>`;
  }).join('') : '<p class="empty-state">当前模型还没有存档版本或基线版本。</p>'}</div></section>`;
}

function renderHubInspectorDetail() {
  const root = $('#hubInspector');
  const title = $('#hubInspectorTitle');
  const subtitle = $('#hubInspectorSubtitle');
  const headActions = $('#hubInspectorHeadActions');
  if (!root || !title || !subtitle || !headActions) return;
  headActions.innerHTML = '';
  if (state.hubTypeSummary) {
    title.textContent = '属性检视器'; subtitle.textContent = '模型类型没有二级属性配置';
    root.className = 'hub-inspector-body empty-state'; root.innerHTML = '选择中间的模型对象后，这里会显示所选模型属性的配置项。'; return;
  }
  const preview = state.hubPreview;
  if (!preview || preview.id !== state.hubSelectedProjectId) {
    title.textContent = '属性检视器'; subtitle.textContent = '等待模型选择';
    root.className = 'hub-inspector-body empty-state'; root.innerHTML = '选择模型后，从“模型属性”中选择数模资产、表格资产、交付数据或存档日志。'; return;
  }
  const allowed = state.auth?.role === 'guest' ? ['delivery_outputs'] : ['model_assets','table_assets','time_series_library','delivery_outputs','archive_log'];
  if (!allowed.includes(state.hubInspectorSection)) state.hubInspectorSection = hubInspectorDefaultSection();
  const labels = {model_assets:['数模资产','公共资产库 / 当前模型绑定'],table_assets:['表格资产','当前模型 / CSV 与 TSV 资产 / 唯一覆盖'],time_series_library:['时序库','TSJSON / 统一时序交换 / VZ 同步'],delivery_outputs:['交付数据','下载命名 / 文件管理'],archive_log:['存档日志',`最近 ${state.archiveLimit} 个版本`]};
  const [label, hint] = labels[state.hubInspectorSection] || ['属性检视器',''];
  title.textContent = label; subtitle.textContent = hint;
  if (state.hubInspectorSection === 'delivery_outputs') {
    const status = preview.lifecycle_status || preview.lifecycle?.status || 'checked_in';
    const writable = ['engineer','admin'].includes(state.auth?.role) && status !== 'baseline' && !state.hubPreviewVersionId;
    const refreshing = hubDeliveryRefreshPending.has(preview.id);
    headActions.innerHTML = `<button class="button tiny ghost hub-delivery-refresh-button" type="button" data-action="hub-delivery-refresh" ${!writable || refreshing ? 'disabled' : ''} title="更新 NX 脚本、甘特图 PNG、模型 JSON 和仿真 XML；保留动画 HTML 与表格">↻ ${refreshing ? '刷新中…' : '刷新'}</button>`;
  }
  if (state.hubInspectorSection === 'model_assets') {
    const manager = state.modelAssetManager || {category:'',folders:[],selected:'',files:[]};
    const context = state.modelAssetManagerContext || {};
    const frozen = Boolean(context.frozen || manager.frozen);
    const categories = modelAssetCategories();
    const options = frozen
      ? `<option value="${esc(manager.category || '')}">${esc(manager.category || '基线冻结资产')}</option>`
      : (categories.length ? categories.map(item => `<option value="${esc(item.path)}" ${item.path === manager.category ? 'selected' : ''}>${esc(item.path)}</option>`).join('') : '<option value="">暂无模型类型</option>');
    headActions.innerHTML = `<select data-hub-asset-category ${frozen ? 'disabled' : ''} aria-label="模型类型">${options}</select>`;
  }
  root.className = 'hub-inspector-body';
  if (state.hubInspectorSection === 'model_assets') root.innerHTML = renderHubAssetInspector();
  else if (state.hubInspectorSection === 'table_assets') root.innerHTML = renderHubTableAssetsInspector();
  else if (state.hubInspectorSection === 'time_series_library') root.innerHTML = renderHubTimeSeriesInspector();
  else if (state.hubInspectorSection === 'delivery_outputs') root.innerHTML = renderHubDeliveryInspector();
  else root.innerHTML = renderHubArchiveInspector();
}

async function activateHubInspectorSection(section, options = {}) {
  const allowed = state.auth?.role === 'guest' ? ['delivery_outputs'] : ['model_assets','table_assets','time_series_library','delivery_outputs','archive_log'];
  const next = allowed.includes(section) ? section : hubInspectorDefaultSection();
  state.hubInspectorSection = next;
  renderHubPreview();
  if (next !== 'model_assets') return;
  const projectId = state.hubSelectedProjectId || state.hubPreview?.id;
  if (!projectId) return;
  if (!options.force && state.modelAssetManagerContext?.projectId === projectId && state.modelAssetManager?.category) return;
  state.hubInspectorAssetLoading = true; renderHubInspectorDetail();
  try { await prepareModelAssetManager({mode:'bind', projectId}); }
  catch (error) { toast(`数模资产库读取失败：${error.message}`, 'error'); }
  finally { state.hubInspectorAssetLoading = false; renderHubInspectorDetail(); }
}

async function deleteModelAssetFile(path) {
  const manager = state.modelAssetManager;
  if (!path || !manager?.selected || !modelAssetCanMaintain()) return;
  if (!confirm(`确认从“${manager.selected}”删除文件：\n${path}？`)) return;
  try {
    const query = new URLSearchParams({category:manager.category, folder:manager.selected, path});
    state.modelAssetManager = await api(`/api/model-asset-library/file?${query}`, {method:'DELETE'});
    renderModelAssetManager();
    toast(`已删除数模文件 ${path}`);
  } catch (error) { toast(error.message, 'error'); }
}

async function downloadWholeModelAssetFolder() {
  const manager = state.modelAssetManager || {};
  if (!manager.selected) return toast('请先选择数模版本', 'error');
  let count=0;
  try {
    for(const item of (manager.files||[])){
      if(item.kind==='folder'||!item.url)continue;
      const filename=String(item.path||'').replace(/\\/g,'/').split('/').filter(Boolean).pop()||'mesh-file';
      const response=await fetch(item.url);
      if(!response.ok)throw new Error(`数模文件读取失败：${item.path} (${response.status})`);
      await writeBlobToChosenHandle({kind:'browser-download',suggestedName:filename},await response.blob(),filename,true);
      count+=1;
    }
    toast(`已开始直接下载 ${count} 个数模文件`);
  }catch(error){toast(error.message||String(error),'error');}
}

async function downloadHubDeliveryFile(path) {
  const projectId = state.hubSelectedProjectId || state.hubPreview?.id;
  if (!projectId || !path) return;
  const item=(state.hubFiles?.delivery_outputs||[]).find(candidate=>candidate.path===path) || {path};
  const suffix=state.hubDeliverySuffixByProject.get(projectId)||'';
  const folder=item.node_type==='directory'||item.kind==='tables_folder'||item.kind==='axes_csv_folder';
  const baseName=deliverySuggestedName(item,suffix);
  const name=folder?`${baseName}.zip`:baseName;
  const mime=folder?'application/zip':({'.html':'text/html','.py':'text/x-python','.json':'application/json','.png':'image/png'}[(name.match(/\.[^.]+$/)||[''])[0].toLowerCase()]||'application/octet-stream');
  const handle=await chooseLocalSaveHandle(name,mime); if(!handle)return;
  try {
    const relative=item.relative_path||String(path).replace(/^delivery\//,'');
    const url=folder
      ? `/api/projects/${encodeURIComponent(projectId)}/delivery-folder.zip?subdir=${encodeURIComponent(relative)}`
      : `/api/projects/${encodeURIComponent(projectId)}/artifacts/${encodeArtifactPath(path)}`;
    const response=await fetch(url);
    if(!response.ok)throw new Error(`${folder?'文件夹':'文件'}读取失败 (${response.status})`);
    await writeBlobToChosenHandle(handle,await response.blob(),name);
  } catch(error) { toast(error.message||String(error),'error'); }
}

function autoFillHubDeliverySuffix() {
  const preview=state.hubPreview; if(!preview)return;
  const suffix=(preview.archive_fields||[]).map(formatCriticalData).filter(Boolean).join('_');
  state.hubDeliverySuffixByProject.set(preview.id,safeDeliverySuffix(suffix));
  renderHubInspectorDetail();
}

async function deleteHubArchiveVersion(versionId) {
  const projectId = state.hubSelectedProjectId;
  const version = (state.hubVersions || []).find(item => item.id === versionId);
  if (!projectId || !versionId || !version) return;
  const isBaseline = version.version_kind === 'baseline';
  const extra = isBaseline && version.baseline_name
    ? `\n\n这只会删除原模型存档日志中的“${version.baseline_name}”基线记录，不会删除实际基线模型。`
    : '';
  if (!confirm(`确认删除这条${isBaseline ? '基线版本记录' : '存档版本'}？删除后无法从存档日志恢复。${extra}`)) return;
  return withBlockingLoading({title:'正在删除存档', detail:'正在删除指定版本快照与元数据；当前模型不会被修改。'}, async () => {
    try {
      await api(`/api/projects/${projectId}/versions/${encodeURIComponent(versionId)}`, {method:'DELETE'});
      state.hubPreviewCache.delete(projectId);
      state.hubPreviewLoadedAt.delete(projectId);
      await loadHubPreview(projectId, {force:true});
      renderHubInspectorDetail();
      toast(isBaseline ? '基线版本记录已从原模型存档日志删除；实际基线模型未删除' : '存档版本已删除');
    } catch (error) { toast(error.message || String(error), 'error'); }
  });
}

async function cutOutHubArchiveVersion(versionId) {
  const projectId=state.hubSelectedProjectId;
  const version=(state.hubVersions||[]).find(item=>item.id===versionId);
  if(!projectId||!versionId||!version)return;
  const versionLabel = version.version_kind === 'baseline' ? '基线版本' : '存档版本';
  if(!confirm(`从“${versionLabel}”切出一个独立模型？\n当前模型不会被回退或修改。`))return;
  return withBlockingLoading({title:'正在切出版本',detail:'正在复制该版本快照，并复用其公共数模资产文件夹创建独立模型…'},async()=>{
    try{
      const copied=await api(`/api/projects/${projectId}/copy-version`,{method:'POST',body:JSON.stringify({version_id:versionId})});
      state.hubPreviewCache.delete(projectId); state.hubPreviewLoadedAt.delete(projectId);
      await loadProjects(projectId);
      await loadHubPreview(projectId,{force:true});
      toast(`已从存档切出独立模型“${copied.name}”`);
    }catch(error){toast(error.message||String(error),'error');}
  });
}

async function renameHubFolder() {
  const summary = state.hubTypeSummary;
  const name = $('#hubTypeNameInput')?.value.trim();
  if (!summary || !name || summary.category === '全部项目') return;
  try {
    if (summary.category === 'None') {
      const result = await api('/api/project-root/name', {method:'PUT', body:JSON.stringify({name})});
      state.projectRootName = result.name;
      state.hubTypeSummary = {...summary, name:result.name};
      if ($('#hubProjectRoot')) $('#hubProjectRoot').textContent = result.name;
      renderHub();
      toast(`项目文件夹已重命名为「${result.name}」`);
      return;
    }
    const result = await api(`/api/model-types/${encodePath(summary.category)}/name`, {method:'PUT', body:JSON.stringify({name})});
    state.hubCategory = result.target;
    await loadProjects();
    await loadHubTypeSummary(result.target);
    toast(`项目文件夹已重命名为「${result.target}」`);
  } catch (error) { toast(error.message, 'error'); }
}

async function restoreHubVersion() {
  const projectId = state.hubSelectedProjectId, versionId = state.hubPreviewVersionId;
  if (!projectId || !versionId) return;
  if (!confirm('确认回退到这个版本吗？当前配置会先自动保存为“回退前保护版本”。')) return;
  return withBlockingLoading({title:'正在回退版本', detail:'正在创建回退前保护版本并恢复目标数据，请勿进行其他操作。'}, async token => {
    try {
      const updated = await api(`/api/projects/${projectId}/versions/${encodeURIComponent(versionId)}/restore`, {method:'POST', body:'{}'});
      state.project = updated; state.hubPreviewVersionId = null; updateProjectSummary(updated);
      updateBlockingLoading(token,{detail:'版本已恢复，正在刷新项目预览与文件状态…'});
      await loadHubPreview(projectId, {force:true}); renderAll(); toast('版本回退完成；回退前状态已保护存档');
    } catch (error) { toast(error.message, 'error'); }
  });
}

function enterModelEdit(projectId) {
  const selected = state.projects.find(item => item.id === projectId);
  if (!selected) return;
  if (state.auth?.role === 'guest' && projectStatus(selected) !== 'baseline') return toast('游客只能进入基线模型查看', 'error');
  openModelEditorWindow(projectId, state.auth?.role === 'guest' ? 'simulation' : 'model');
}

async function exitModelEdit() {
  if (state.dirty) {
    try { await flushInteractionCommit(); } catch (error) { return toast(error.message, 'error'); }
  }
  openHubWindow();
}

function modelFileRows(group) {
  const files = state.hubFiles || {};
  if (group === 'project_json') {
    const item = files.project_json;
    return item ? `<a class="model-file-row" href="${esc(item.url)}" download><span>⌘ ${esc(item.name)}</span><small>${formatBytes(item.size)}</small></a>` : '<p>project.json 不存在</p>';
  }
  const items = files[group] || [];
  return items.length ? items.map(item => {
    if (group === 'table_assets') return `<a class="model-file-row" href="${esc(item.url || '')}" download><span>▤ ${esc(item.label || item.name)}</span><small>${formatBytes(item.size)}</small></a>`;
    if(group==='delivery_outputs'){
      const frozen=(state.hubPreview?.lifecycle_status||'')==='baseline';
      const deleteButton = state.auth?.role === 'guest' ? '' : `<button class="button tiny danger" type="button" data-delivery-file-delete="${esc(item.relative_path||String(item.path||'').replace(/^delivery\//,''))}" ${frozen?'disabled title="基线交付数据已冻结"':''}>删除</button>`;
      return `<div class="model-file-row delivery-file-row"><button class="delivery-file-open" type="button" data-delivery-file-save="${esc(item.path)}"><span>${esc(item.path)}</span><small>${formatBytes(item.size)}</small></button>${deleteButton}</div>`;
    }
    const url = `/api/projects/${files.project_id}/artifacts/${encodeArtifactPath(item.path)}`;
    return `<a class="model-file-row" href="${esc(url)}" download><span>${esc(item.path)}</span><small>${formatBytes(item.size)}</small></a>`;
  }).join('') : '<p>这个文件夹目前为空</p>';
}

async function downloadWholeDeliveryFolder() {
  const files=state.hubFiles||{};
  const projectId=files.project_id||state.hubSelectedProjectId;
  if(!projectId)return toast('未选择模型','error');
  const anchor=document.createElement('a');
  anchor.href=`/api/projects/${encodeURIComponent(projectId)}/delivery-folder.zip`;
  anchor.download='';
  anchor.style.display='none';
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  toast('交付数据 ZIP 已开始下载到浏览器默认下载目录');
}

async function refreshDeliveryManager(projectId){
  await loadHubPreview(projectId, {force:true});
  if(state.hubSelectedProjectId!==projectId)return;
  const dialog=$('#modelFilesDialog');
  if(dialog?.open && dialog.dataset.group==='delivery_outputs') openModelFiles('delivery_outputs');
  if(state.hubInspectorSection==='delivery_outputs') renderHubInspectorDetail();
}


// V2.16.11.1: use the existing heavy background job pool, not a blocking Hub request.
const hubDeliveryRefreshPending = new Set();
async function refreshHubDeliveryOutputs() {
  const projectId = state.hubSelectedProjectId;
  const preview = state.hubPreview;
  if (!projectId || preview?.id !== projectId) return;
  if (hubDeliveryRefreshPending.has(projectId)) return toast('交付数据正在刷新，请勿重复提交', 'info');
  if (!['engineer','admin'].includes(state.auth?.role) || (preview.lifecycle_status || preview.lifecycle?.status) === 'baseline' || state.hubPreviewVersionId) {
    return toast('冻结基线、历史预览或只读角色不能更新交付数据', 'error');
  }
  if (!confirm('更新当前模型交付数据中的 NX AFU 脚本、甘特图 PNG、模型 JSON 和仿真 XML？动画 HTML、表格文件夹中的 CSV/TSV 均保持不变。任务将在后台运行，Hub 可继续使用。')) return;
  hubDeliveryRefreshPending.add(projectId);
  renderHubInspectorDetail();
  try {
    const accepted = await api(`/api/projects/${encodeURIComponent(projectId)}/delivery-files/refresh`, {method:'POST',timeout:15000});
    toast('交付数据刷新已提交后台任务；动画 HTML 不会重新生成', 'info');
    const job = await waitForBackgroundJob(accepted.job_id, '交付数据刷新');
    await refreshDeliveryManager(projectId);
    toast(`交付数据刷新完成：${(job.result?.refreshed||[]).length} 类文件已更新，动画 HTML 未改变`, 'success');
  } catch (error) {
    toast(`刷新交付数据失败：${error.message}`, 'error');
  } finally {
    hubDeliveryRefreshPending.delete(projectId);
    if (state.hubSelectedProjectId === projectId && state.hubInspectorSection === 'delivery_outputs') renderHubInspectorDetail();
  }
}

async function deleteDeliveryFile(relativePath){
  const projectId=state.hubFiles?.project_id||state.hubSelectedProjectId;if(!projectId||!relativePath)return;
  if(!confirm(`确定删除交付文件“${relativePath}”？此操作不可撤销。`))return;
  try{await api(`/api/projects/${encodeURIComponent(projectId)}/delivery-files/${encodeArtifactPath(relativePath)}`,{method:'DELETE'});await refreshDeliveryManager(projectId);toast('交付文件已删除');}
  catch(error){toast(error.message||String(error),'error');}
}

async function clearDeliveryFiles(){
  const projectId=state.hubFiles?.project_id||state.hubSelectedProjectId;if(!projectId)return;
  if(!confirm('确定清空该模型的全部交付数据？此操作不可撤销。'))return;
  try{const result=await api(`/api/projects/${encodeURIComponent(projectId)}/delivery-files`,{method:'DELETE'});await refreshDeliveryManager(projectId);toast(`已清空 ${result.deleted||0} 个交付文件`);}
  catch(error){toast(error.message||String(error),'error');}
}

function openModelFiles(group = 'project_json') {
  if (group === 'model_assets') { void openModelAssetManager({mode:'bind', projectId:state.hubSelectedProjectId || state.project?.id}); return; }
  const dialog = $('#modelFilesDialog'), files = state.hubFiles;
  if (!dialog || !files) return;
  const labels = {project_json:'project.json', table_assets:'表格资产', delivery_outputs:'交付数据', derived_outputs:'其他派生产物'};
  dialog.dataset.group = group;
  $('#modelFilesTitle').textContent = labels[group] || '模型文件';
  $('#modelFilesPath').textContent = `${files.model_directory || ''} / ${labels[group] || ''}`;
  $('#modelFilesBody').innerHTML = modelFileRows(group);
  if(group==='delivery_outputs'){
    $$('[data-delivery-file-save]',$('#modelFilesBody')).forEach(button=>button.addEventListener('click',async()=>{
      const path=button.dataset.deliveryFileSave;
      if(!path)return;
      await downloadHubDeliveryFile(path);
    }));
    $$('[data-delivery-file-delete]',$('#modelFilesBody')).forEach(button=>button.addEventListener('click',()=>deleteDeliveryFile(button.dataset.deliveryFileDelete)));
  }
  $('#modelLocalActions').classList.add('hidden');
  const editable = (state.hubPreview?.lifecycle_status || '') === 'checked_out';
  const frozenDelivery=(state.hubPreview?.lifecycle_status||'')==='baseline';
  $('#modelDeliveryDownloadFolderButton').hidden = group !== 'delivery_outputs';
  $('#modelDeliveryClearButton').hidden = group !== 'delivery_outputs' || state.auth?.role === 'guest';
  $('#modelDeliveryClearButton').disabled = frozenDelivery;
  $('#modelDeliveryClearButton').title = frozenDelivery ? '基线交付数据已冻结，只能随基线模型一起删除' : '';
  $('#modelJsonUploadButton').hidden = group !== 'project_json';
  $('#modelJsonUploadButton').disabled = !editable;
  if (!dialog.open) dialog.showModal();
}

function requireLocalClientRole() {
  if (!['engineer','admin'].includes(state.auth?.role)) {
    toast('无权限，请联系管理员开通权限', 'error');
    return false;
  }
  return true;
}

function isAdminDirectMesh() {
  return state.auth?.role === 'admin';
}

async function localClientRequest(path, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), options.timeout || 2500);
  try {
    const response = await fetch(`${state.localClientUrl}${path}`, {
      method: options.method || 'GET',
      headers: options.body ? {'Content-Type':'application/json'} : {},
      body: options.body ? JSON.stringify(options.body) : undefined,
      signal: controller.signal,
      cache: 'no-store',
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const missing=Array.isArray(payload.details?.missing)?payload.details.missing:[];
      const suffix=missing.length?`；缺少：${missing.join('、')}`:'';
      throw new Error((payload.message || payload.detail || `本地客户端返回 ${response.status}`)+suffix);
    }
    return payload;
  } finally {
    clearTimeout(timer);
  }
}

async function localClientHealth({quiet=false} = {}) {
  try {
    const health = await localClientRequest('/v1/health', {timeout:1200});
    if (health.status === 'config_invalid') {
      if (!quiet) toast(`本地客户端配置无效：${health.config_error || '请检查 client_config.json'}`, 'error');
      return null;
    }
    return health;
  } catch (_error) {
    if (!quiet) toast('本地客户端未启动', 'error');
    return null;
  }
}

function meshNameSet(items) {
  return new Set((items || []).map(item => String(item?.path || item?.filename || item).replace(/\\/g,'/').split('/').at(-1).toLocaleLowerCase()));
}

async function refreshLocalMeshStatus({quiet=false, render=false} = {}) {
  if (isAdminDirectMesh()) {
    state.localClientStatus = {
      project_id:state.hubSelectedProjectId || state.project?.id || '',
      online:true, mesh_path_ready:Boolean(state.adminMeshPath), synchronized:true,
      extra_files:[], missing_local:[], admin_direct:true,
    };
    if (render) {
      const lamp=$('#modelClientStatus'), apiLamp=$('#modelClientApiStatus');
      if (lamp) { lamp.className='client-status-light online'; lamp.textContent='● 管理员直连（无需客户端）'; }
      if (apiLamp) { apiLamp.className='client-status-light online'; apiLamp.textContent='● API 2.16.11.6 · 服务端直连'; }
      renderHub();
    }
    return state.localClientStatus;
  }
  const health = await localClientHealth({quiet:true});
  const server = meshNameSet(state.hubFiles?.model_assets || []);
  const local = meshNameSet(health?.mesh_files || []);
  const extra = [...local].filter(name => !server.has(name));
  const missing = [...server].filter(name => !local.has(name));
  state.localClientStatus = {
    project_id:state.hubSelectedProjectId || state.project?.id || '',
    online:Boolean(health), mesh_path_ready:Boolean(health?.mesh_path_ready),
    synchronized:Boolean(health?.mesh_path_ready && !extra.length && !missing.length),
    extra_files:extra, missing_local:missing, health,
  };
  if (!health && !quiet) toast('本地客户端未启动', 'error');
  if (render) {
    const lamp=$('#modelClientStatus'), apiLamp=$('#modelClientApiStatus');
    if (lamp) { lamp.className=`client-status-light ${health?'online':'offline'}`; lamp.textContent=`● ${health?'已开启客户端':'未开启客户端'}`; }
    if (apiLamp) { apiLamp.className=`client-status-light ${health?.dependencies_ready?'online':health?'warning':'offline'}`; apiLamp.textContent=`● API 2.16.11.6 · MuJoCo ${health?.dependencies_ready?'ready':health?'missing':'unknown'}`; }
    renderHub();
  }
  return state.localClientStatus;
}

async function selectLocalMeshPath() {
  if (!requireLocalClientRole()) return;
  if (isAdminDirectMesh()) {
    if (!state.capabilities?.server_file_dialogs) {
      await openModelAssetManager({mode:'bind', projectId:state.hubSelectedProjectId || state.project?.id});
      toast('当前服务未启用本机目录选择器；请在统一数模资产窗口选择版本后使用“上传文件夹”');
      return '';
    }
    try {
      const selected = await api(`/api/dialogs/select-directory?initial=${encodeURIComponent(state.adminMeshPath)}&title=${encodeURIComponent('选择管理员本机 STL / OBJ 文件夹')}`, {method:'POST'});
      state.adminMeshPath = selected.path || '';
      if (state.adminMeshPath) {
        toast('管理员本机数模路径已选择');
      }
      await refreshLocalMeshStatus({quiet:true, render:true});
      return state.adminMeshPath;
    } catch (error) { toast(error.message, 'error'); return ''; }
  }
  if (!await localClientHealth()) return;
  try {
    const projectId = state.hubSelectedProjectId || state.project?.id;
    if (!projectId) return toast('请先选择一个模型', 'error');
    const issued = await api(`/api/projects/${projectId}/client-ticket`, {
      method:'POST', body:JSON.stringify({purpose:'select_mesh_path'}),
    });
    const result = await localClientRequest('/v1/select-mesh-path', {
      method:'POST', body:{server_url:location.origin,ticket:issued.ticket}, timeout:120000,
    });
    if (result.path) {
      toast('本地数模路径已保存');
    }
  } catch (error) { toast(error.message, 'error'); }
}

async function syncLocalMeshes() {
  if (!requireLocalClientRole()) return;
  if (isAdminDirectMesh()) {
    const projectId = state.hubSelectedProjectId;
    if (!projectId) return toast('请先选择一个模型', 'error');
    const selectedPath = state.adminMeshPath || await selectLocalMeshPath();
    if (!selectedPath) return;
    return withBlockingLoading({title:'正在同步数模', detail:'正在读取本机数模并写入当前公共数模资产文件夹，请等待。'}, async token => {
      try {
        await api(`/api/projects/${projectId}/admin-local-mesh-sync`, {
          method:'POST', body:JSON.stringify({path:selectedPath}),
        });
        updateBlockingLoading(token,{detail:'数模已上传，正在刷新公共数模资产文件夹状态…'});
        await loadProjects(projectId);
        await loadHubPreview(projectId, {force:true});
        openModelFiles('model_assets');
        await refreshLocalMeshStatus({quiet:true, render:true});
        toast('管理员本机数模已同步到当前数模资产文件夹，预览将重新渲染');
      } catch (error) { toast(error.message, 'error'); }
    });
  }
  const health = await localClientHealth();
  if (!health) return;
  if (!health.mesh_path_ready) {
    toast('请先选择本地数模路径', 'error');
    return;
  }
  const projectId = state.hubSelectedProjectId;
  return withBlockingLoading({title:'正在同步数模', detail:'正在通过本地客户端上传资产，文件较多时请耐心等待。'}, async token => {
    try {
      const issued = await api(`/api/projects/${projectId}/client-ticket`, {
        method:'POST', body:JSON.stringify({purpose:'mesh_sync'}),
      });
      await localClientRequest('/v1/sync', {
        method:'POST',
        body:{server_url:location.origin,ticket:issued.ticket},
        timeout:600000,
      });
      updateBlockingLoading(token,{detail:'数模上传完成，正在刷新项目预览与版本信息…'});
      await loadProjects(projectId);
      await loadHubPreview(projectId, {force:true});
      openModelFiles('model_assets');
      await refreshLocalMeshStatus({quiet:true, render:true});
      toast('本地数模已上传到当前数模资产文件夹，预览将重新渲染');
    } catch (error) { toast(error.message, 'error'); }
  });
}



async function replaceModelProjectJson(file) {
  const projectId = state.hubSelectedProjectId;
  if (!projectId || !file) return;
  const form = new FormData(); form.append('file', file, 'project.json');
  return withBlockingLoading({title:'正在上传 project.json', detail:'正在校验配置并写入项目，请等待完成后再继续操作。'}, async () => {
    try {
      const result = await api(`/api/projects/${projectId}/files/project-json`, {method:'PUT', body:form});
      if (state.project?.id === projectId) state.project = result.project;
      await loadProjects(projectId); await loadHubPreview(projectId, {force:true}); openModelFiles('project_json');
      toast('project.json 已验证并上传到服务端');
    } catch (error) { toast(error.message, 'error'); }
  });
}

function formatArchiveValue(value) { const n=Number(value); return Number.isFinite(n) ? n.toFixed(6).replace(/\.?0+$/,'') : '—'; }
function formatGanttMetric(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return '—';
  return Math.abs(n) < 1e-10 ? '0' : n.toFixed(2).replace(/\.00$/,'');
}
function formatCriticalData(item) {
  const text = formatGanttMetric(item?.value);
  return text === '—' ? text : `${text}${item?.unit || ''}`;
}

function managedReclassifiedProjectName(sourceName, sourceCategory, targetCategory) {
  let baseName=String(sourceName || '').trim();
  const source=String(sourceCategory || 'None');
  const target=String(targetCategory || 'None');
  if(target===source)return baseName;
  if(source!=='None'){
    const sourceLeaf=source.split('/').pop() || '';
    const prefix=`${sourceLeaf}_`;
    if(baseName.startsWith(prefix)&&baseName.length>prefix.length)baseName=baseName.slice(prefix.length);
  }
  if(target==='None')return baseName;
  return `${target.split('/').pop()}_${baseName}`;
}

function refreshHubModelTypeCountsFromProjects() {
  const counts=new Map(flattenModelTypes(state.modelTypes).map(node=>[String(node.path || ''),0]));
  (state.projects || []).forEach(item=>{
    const category=String(item?.category || 'None');
    if(category==='None')return;
    const parts=category.split('/');
    for(let index=1;index<=parts.length;index+=1){
      const ancestor=parts.slice(0,index).join('/');
      if(counts.has(ancestor))counts.set(ancestor,(counts.get(ancestor) || 0)+1);
    }
  });
  const visit=nodes=>(nodes || []).forEach(node=>{
    node.count=counts.get(String(node.path || '')) || 0;
    visit(node.children);
  });
  visit(state.modelTypes);
}

function applyHubProjectAuthoritative(project, {render=true}={}) {
  if(!project?.id)return;
  const projectId=project.id;
  const lifecycleStatus=project.lifecycle?.status || 'checked_in';
  const updatedAt=project.metadata?.updated_at || '';
  state.projects=state.projects.map(item=>item.id===projectId?{
    ...item, name:project.name, category:project.category, mesh_root:project.mesh_root,
    updated_at:updatedAt || item.updated_at, lifecycle_status:lifecycleStatus,
    checked_out_by:project.lifecycle?.checked_out_by || '', lease_id:project.lifecycle?.lease_id || '',
  }:item);
  const previewPatch={
    name:project.name, category:project.category, mesh_root:project.mesh_root,
    updated_at:updatedAt, lifecycle_status:lifecycleStatus, lifecycle:project.lifecycle || {},
  };
  if(state.hubPreview?.id===projectId)state.hubPreview={...state.hubPreview,...previewPatch};
  const cached=state.hubPreviewCache.get(projectId);
  if(cached?.preview)state.hubPreviewCache.set(projectId,{...cached,preview:{...cached.preview,...previewPatch}});
  if(state.hubFiles&&state.hubSelectedProjectId===projectId){
    state.hubFiles={...state.hubFiles,model_directory:`${project.category || 'None'}/${projectId}`};
  }
  if(state.modelAssetManagerContext?.projectId===projectId){
    state.modelAssetManagerContext={...state.modelAssetManagerContext,category:project.category};
  }
  if(state.project?.id===projectId&&!state.dirty)state.project=project;
  refreshHubModelTypeCountsFromProjects();
  if(render)renderHub();
}

function bindArchiveDragOrder(){
  const root=$('#hubArchiveOrder');if(!root)return;let dragged=null;let startOrder=[];
  root.querySelectorAll('[data-archive-key]').forEach(row=>{
    row.addEventListener('dragstart',()=>{state.hubArchiveDragActive=true;dragged=row;startOrder=[...root.querySelectorAll('[data-archive-key]')].map(item=>item.dataset.archiveKey);row.classList.add('dragging')});
    row.addEventListener('dragend',()=>{row.classList.remove('dragging');const order=[...root.querySelectorAll('[data-archive-key]')].map(item=>item.dataset.archiveKey);dragged=null;state.hubArchiveDragActive=false;if(order.join('\u001f')!==startOrder.join('\u001f'))void saveHubArchiveOrder(order);else renderHub();startOrder=[]});
    row.addEventListener('dragover',event=>{if(!dragged||dragged===row)return;event.preventDefault();const box=row.getBoundingClientRect();root.insertBefore(dragged,event.clientY<box.top+box.height/2?row:row.nextSibling)});
    row.addEventListener('drop',event=>{event.preventDefault()});
  });
}

async function saveHubArchiveOrder(order){
  const projectId=state.hubSelectedProjectId;if(!projectId||!Array.isArray(order)||!order.length)return;
  const previousFields=state.hubPreview?.id===projectId?[...(state.hubPreview.archive_fields||[])]:[];
  const optimisticFields=reorderHubArchiveFields(previousFields,order);
  applyHubPropertyUpdate({id:projectId,archive_order:order,updated_at:state.hubPreview?.updated_at||''},{archiveFields:optimisticFields});
  try{
    const result=await api(`/api/projects/${encodeURIComponent(projectId)}/hub-properties`,{method:'PATCH',body:JSON.stringify({archive_order:order})});
    const canonicalFields=reorderHubArchiveFields(optimisticFields,result.archive_order||order);
    applyHubPropertyUpdate(result,{archiveFields:canonicalFields});
    toast('关键数据顺序已保存');
  }catch(error){
    toast(`关键数据顺序保存失败：${error.message}`,'error');
    if(state.hubSelectedProjectId===projectId){
      state.hubPreviewCache.delete(projectId);state.hubPreviewLoadedAt.delete(projectId);
      await loadHubPreview(projectId,{force:true,waitForMetadata:false}).catch(()=>{});
    }
  }
}

async function saveHubProperties() {
  const projectId = state.hubSelectedProjectId;
  if (!projectId || state.hubPreviewVersionId) return;
  try {
    if (state.project?.id === projectId && state.dirty) await commitEdits();
    const requestedName=$('#hubProjectNameInput').value.trim();
    if(!requestedName)return toast('模型名称不能为空','error');
    const updated = await api(`/api/projects/${encodeURIComponent(projectId)}/hub-properties`, {method:'PATCH', body:JSON.stringify({name:requestedName})});
    state.hubSelectedProjectId = projectId;
    applyHubPropertyUpdate(updated);
    toast(updated.name !== requestedName ? `名称已存在，已自动保存为「${updated.name}」` : '模型名称已保存');
  } catch (error) { toast(error.message, 'error'); }
}

async function browseHubMeshRoot() {
  if (!state.capabilities?.server_file_dialogs) {
    toast('服务器模式通过统一数模资产窗口上传；不会读取客户端或服务器绝对路径');
    await openModelAssetManager({mode:'bind', projectId:state.hubSelectedProjectId || state.project?.id});
    return;
  }
  try {
    const initial = $('#hubMeshRootInput').value.trim();
    const selected = await api(`/api/dialogs/select-directory?initial=${encodeURIComponent(initial)}`, {method:'POST'});
    if (!selected.path) return;
    toast('桌面扫描仅允许重扫当前项目已托管资产；新增资产仍请使用 Web 上传');
  } catch (error) { toast(error.message, 'error'); }
}

async function bindProjectDeliveryFolder(){
  const projectId=state.hubSelectedProjectId;if(!projectId)return;
  if (!state.capabilities?.server_file_dialogs) {
    openModelFiles('delivery_outputs');
    toast('服务器模式的交付文件由项目托管目录管理，可在文件面板下载');
    return;
  }
  try{
    const initial=state.hubPreview?.delivery_root||'';
    const selected=await api(`/api/dialogs/select-directory?initial=${encodeURIComponent(initial)}&title=${encodeURIComponent('绑定类别交付文件夹')}`,{method:'POST'});
    if(!selected.path)return;
    await api(`/api/projects/${projectId}/bind-delivery-folder`,{method:'POST',body:JSON.stringify({path:selected.path})});
    await loadHubPreview(projectId, {force:true});toast('类别交付文件夹已绑定');
  }catch(error){toast(error.message,'error')}
}

async function openAnimationResult(projectId){
  if(!projectId)return;
  if(routeContextFromLocation().kind === 'editor' && state.project?.id === projectId){
    state.ui.results ||= {}; state.ui.results.active_view='animation'; navigateToPage('simulation'); return;
  }
  openModelEditorWindow(projectId, 'simulation', {view:'animation'});
}

function switchResultTab(tab){
  $$('[data-result-tab]').forEach(item=>item.classList.toggle('active',item.dataset.resultTab===tab));
  $$('[data-result-pane]').forEach(item=>item.classList.toggle('hidden',item.dataset.resultPane!==tab));
  if(tab==='axes')requestAnimationFrame(drawResultAxes);
  if(tab==='animation'&&$('#embeddedAnimationFrame')?.classList.contains('hidden'))$('#animationLoadStatus').textContent='点击“重新加载”载入已生成动画';
}

async function fullscreenEmbeddedAnimation(){
  const frame=$('#embeddedAnimationFrame');
  if(!frame||frame.classList.contains('hidden')||!frame.src)return toast('请先重新加载动画 HTML','error');
  const request=frame.requestFullscreen||frame.webkitRequestFullscreen;
  if(!request)return toast('当前浏览器不支持全屏展示','error');
  try{await request.call(frame)}catch(error){toast(`全屏展示失败：${error.message||error}`,'error')}
}

async function loadEmbeddedAnimation(force=false){
  if(!state.project||state.animationLoading)return;
  const frame=$('#embeddedAnimationFrame'),empty=$('#animationEmpty'),progress=$('#animationLoadProgress'),bar=$('#animationLoadBar'),percent=$('#animationLoadPercent'),status=$('#animationLoadStatus'),fullscreen=$('#fullscreenEmbeddedAnimation');
  if(!force&&!frame.classList.contains('hidden')&&frame.src)return;

  state.animationLoading=true;
  if(fullscreen)fullscreen.disabled=true;
  frame.classList.add('hidden');
  empty.classList.add('hidden');
  progress.classList.remove('hidden');
  bar.style.width='0%';
  percent.textContent='0%';

  status.textContent='正在查找交付数据中的最新动画 HTML…';

  try{
    const files=await api(`/api/projects/${state.project.id}/files`);
    const deliveryHtml=[...(files.delivery_outputs||[])]
      .filter(item=>item.kind==='animation_html'||/\.html?$/i.test(String(item.path||item.name||'')))
      .sort((a,b)=>Number(b.modified||0)-Number(a.modified||0));
    const artifact=deliveryHtml[0]||null;

    if(!artifact){
      const message='交付数据中没有动画 HTML';
      empty.textContent=message;
      empty.classList.remove('hidden');
      progress.classList.add('hidden');
      status.textContent=message;
      return;
    }

    const response=await fetch(
      `/api/projects/${state.project.id}/artifacts/${encodeArtifactPath(artifact.path)}`,
      {cache:'reload'}
    );
    if(!response.ok)throw new Error(`动画读取失败 (${response.status})`);

    const total=Number(response.headers.get('Content-Length'))||Number(artifact.size)||0;
    const reader=response.body?.getReader();
    let loaded=0,chunks=[];

    if(reader){
      while(true){
        const {done,value}=await reader.read();
        if(done)break;
        chunks.push(value);
        loaded+=value.length;
        const pct=total
          ?Math.min(99,Math.round(loaded/total*100))
          :Math.min(95,Math.round(loaded/1048576*10));
        bar.style.width=`${pct}%`;
        percent.textContent=`${pct}%`;
        status.textContent=`正在加载动画… ${formatBytes(loaded)} / ${total?formatBytes(total):'未知大小'}`;
      }
    }else{
      chunks=[new Uint8Array(await response.arrayBuffer())];
    }

    if(state.animationBlobUrl)URL.revokeObjectURL(state.animationBlobUrl);
    state.animationBlobUrl=URL.createObjectURL(new Blob(chunks,{type:'text/html'}));
    await new Promise(resolve=>{frame.onload=resolve;frame.src=state.animationBlobUrl});

    bar.style.width='100%';
    percent.textContent='100%';
    status.textContent='已从交付数据加载动画';
    frame.classList.remove('hidden');
    if(fullscreen)fullscreen.disabled=false;
    setTimeout(()=>progress.classList.add('hidden'),350);
  }catch(error){
    empty.textContent=error.message;
    empty.classList.remove('hidden');
    progress.classList.add('hidden');
    status.textContent='动画加载失败';
    toast(error.message,'error');
  }finally{
    state.animationLoading=false;
  }
}

async function compareHubProjects() {
  const projectIds = [...state.hubCompareIds];
  if (projectIds.length < 2) return toast('请先勾选至少两个项目', 'error');
  try {
    const result = await api('/api/project-comparisons', {method:'POST', body:JSON.stringify({project_ids:projectIds, variables:[...state.hubSelectedVariables], skill_id:'compare-variable-sets'})});
    const changed = result.differences.filter(item => item.changed);
    $('#hubComparison').classList.remove('hidden');
    $('#hubComparison').innerHTML = `<div class="compact-heading"><strong>Skill 对比结果 · ${result.projects.length} 个项目</strong><button class="compact-delete" data-action="hub-close-comparison">×</button></div>
      <div class="comparison-table"><div class="comparison-row header"><b>变量</b>${result.projects.map(project => `<b>${esc(project.name)}</b>`).join('')}<b>跨度</b></div>${(changed.length ? changed : result.differences).map(item => `<div class="comparison-row"><code>${esc(item.variable)}</code>${item.values.map(value => `<span>${esc(value ?? '—')}</span>`).join('')}<strong>${item.spread == null ? '—' : Number(item.spread).toPrecision(5)}</strong></div>`).join('')}</div>`;
    $('#hubComparison').scrollIntoView({behavior:'smooth', block:'nearest'});
  } catch (error) { toast(error.message, 'error'); }
}

function formatDate(value) {
  if (!value) return '尚未保存';
  const date = new Date(value); return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString('zh-CN', {month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit'});
}

function formatSavedTime(value) {
  if (value === undefined || value === null || value === '') return '尚未保存';
  const numeric = Number(value);
  const normalized = Number.isFinite(numeric) && numeric > 0 && numeric < 1e12 ? numeric * 1000 : value;
  const date = new Date(normalized);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString('zh-CN', {month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit'});
}

function modelAssetCategories() {
  return flattenModelTypes(state.modelTypes).filter(item => item.path && item.path !== 'None');
}

function modelAssetUsageText(folder) {
  const names = (folder?.usage || []).map(item => item.name || item.id).filter(Boolean);
  return names.length ? `使用模型：${names.join('、')}` : '当前没有模型使用';
}

function renderModelAssetManager() {
  const manager = state.modelAssetManager || {category:'', folders:[], selected:'', files:[], root:''};
  const context = state.modelAssetManagerContext || {mode:'manage', projectId:'', current:'', editable:false, frozen:false};
  const categories = modelAssetCategories();
  const select = $('#modelAssetCategorySelect');
  if (!select) return;
  const frozen = Boolean(context.frozen || manager.frozen);
  const bindMode = context.mode === 'bind';
  const canMaintain = Boolean(manager.writable) && !frozen;
  select.innerHTML = frozen
    ? `<option value="${esc(manager.category || '')}">${esc(manager.category || '基线冻结资产')}</option>`
    : categories.map(item => `<option value="${esc(item.path)}" ${item.path === manager.category ? 'selected' : ''}>${esc(item.path)}</option>`).join('');
  select.disabled = frozen || bindMode;
  $('#modelAssetDialogTitle').textContent = frozen ? '冻结数模资产' : bindMode ? '选择模型数模资产' : '数模资产管理';
  $('#modelAssetRootPath').textContent = manager.root || (manager.category ? `model_asset_libraries/${manager.category}` : '暂无可用模型类型');
  $('#modelAssetManagerDialog').classList.toggle('baseline-frozen', frozen);
  $('#modelAssetVersionCount').textContent = manager.folders.length;
  const list = $('#modelAssetVersionList');
  list.innerHTML = manager.folders.map(folder => {
    const active = folder.name === manager.selected;
    const uploader = folder.uploaded_by ? `上传用户：${folder.uploaded_by}` : '上传用户：历史数据未记录';
    const usage = modelAssetUsageText(folder);
    return `<button type="button" class="model-asset-version-row ${active ? 'active' : ''} ${folder.frozen ? 'frozen' : ''}" data-model-asset-version="${esc(folder.name)}" ${frozen ? 'disabled' : ''}><span><strong>📁 ${esc(folder.name)}</strong><small>${folder.file_count || 0} 文件 · ${formatBytes(folder.size_bytes || 0)}</small><small>${esc(uploader)}</small><small>${esc(usage)}</small></span><code>${folder.mesh_count || 0} mesh</code></button>`;
  }).join('') || '<p class="empty-state">当前模型类型还没有数模版本。点击“新建版本”创建第一个文件夹。</p>';
  if (!frozen) $$('[data-model-asset-version]', list).forEach(button => button.addEventListener('click', () => void loadModelAssetLibrary(manager.category, button.dataset.modelAssetVersion)));

  const selectedFolder = manager.folders.find(item => item.name === manager.selected);
  $('#modelAssetVersionTitle').textContent = selectedFolder ? manager.selected : '请选择数模版本';
  $('#modelAssetVersionMeta').textContent = selectedFolder
    ? `${selectedFolder.file_count || 0} 个文件 · ${selectedFolder.mesh_count || 0} 个 STL/OBJ · ${formatBytes(selectedFolder.size_bytes || 0)} · ${selectedFolder.uploaded_by ? `上传用户 ${selectedFolder.uploaded_by}` : '上传用户未记录'} · ${modelAssetUsageText(selectedFolder)}`
    : '一个版本对应服务器上的一个文件夹';
  $('#modelAssetNewVersionButton').hidden = frozen;
  $('#modelAssetCopyVersionButton').hidden = frozen;
  $('#modelAssetDeleteVersionButton').hidden = frozen;
  $('#modelAssetUploadFilesButton').hidden = frozen;
  $('#modelAssetUploadFolderButton').hidden = frozen;
  $('#modelAssetNewVersionButton').disabled = !canMaintain;
  $('#modelAssetCopyVersionButton').disabled = !canMaintain || !selectedFolder;
  $('#modelAssetDeleteVersionButton').disabled = !canMaintain || !selectedFolder || Boolean(selectedFolder?.usage_count);
  $('#modelAssetUploadFilesButton').disabled = !canMaintain || !selectedFolder;
  $('#modelAssetUploadFolderButton').disabled = !canMaintain || !selectedFolder;
  const clearButton = $('#modelAssetClearFolderButton');
  clearButton.hidden = frozen;
  clearButton.disabled = !canMaintain || !selectedFolder || !(selectedFolder.file_count || 0);
  clearButton.title = selectedFolder && selectedFolder.usage_count ? `当前有 ${selectedFolder.usage_count} 个模型使用该文件夹；清空会删除其资产文件` : '';
  const fileList = $('#modelAssetFileList');
  fileList.innerHTML = !selectedFolder
    ? '<p class="empty-state">请选择左侧数模版本查看文件。</p>'
    : manager.files.map(item => item.kind === 'folder'
      ? `<div class="model-asset-file-row folder"><span>📁 ${esc(item.path)}</span></div>`
      : `<div class="model-asset-file-row"><span><b>${esc(item.path)}</b><small>${formatBytes(item.size || 0)}</small></span><div class="model-asset-file-actions">${item.url ? `<a class="button tiny ghost" href="${esc(item.url)}" download>下载</a>` : ''}${canMaintain ? `<button class="button tiny danger" type="button" data-model-asset-file-delete="${esc(item.path)}">删除</button>` : ''}</div></div>`
    ).join('') || '<p class="empty-state">当前版本为空，可上传 STL/OBJ 文件或包含贴图的文件夹。</p>';
  $$('[data-model-asset-file-delete]', fileList).forEach(button => button.addEventListener('click', async () => {
    const path = button.dataset.modelAssetFileDelete;
    if (!confirm(`确认从“${manager.selected}”删除文件：\n${path}？`)) return;
    try {
      const query = new URLSearchParams({category:manager.category, folder:manager.selected, path});
      state.modelAssetManager = await api(`/api/model-asset-library/file?${query}`, {method:'DELETE'});
      renderModelAssetManager();
      toast(`已删除数模文件 ${path}`);
    } catch (error) { toast(error.message, 'error'); }
  }));
  const confirmButton = $('#modelAssetConfirmBindingButton');
  confirmButton.hidden = !bindMode || frozen;
  confirmButton.disabled = !modelAssetCanBindSelected();
  const summary = $('#modelAssetBindingSummary');
  if (frozen) summary.textContent = `基线冻结资产：${context.current || '冻结目录'}。该数模只能下载，不可编辑或重新绑定。`;
  else if (bindMode && manager.selection_state === 'missing') summary.textContent = `当前绑定：${context.current || '未绑定'}。该引用来自另一环境、已重新分类或对应文件夹已不存在；资产库已正常打开，请选择左侧现有版本并点击“确认绑定”。`;
  else if (bindMode && manager.selection_state === 'casefold_repaired') summary.textContent = `当前绑定：${context.current || '未绑定'}。检测到 Windows/Linux 大小写差异，已定位到“${manager.selected}”；点击“确认绑定”可把引用修正为服务器真实目录名。`;
  else if (bindMode) summary.textContent = `当前绑定：${context.current || '未绑定'}。选择左侧文件夹后点击“确认绑定”才会修改模型。`;
  else summary.innerHTML = '模型项目只保存 <code>@model_assets/模型类型/数模版本</code> 引用；左侧直接显示上传用户和正在使用该资产的模型名称。';
  if (state.hubInspectorSection === 'model_assets') renderHubInspectorDetail();
}

async function clearModelAssetVersionFiles() {
  const manager = state.modelAssetManager;
  const context = state.modelAssetManagerContext || {};
  const folder = manager?.folders?.find(item => item.name === manager.selected);
  const canMaintain = Boolean(manager?.writable) && !context.frozen;
  if (!canMaintain || !manager?.category || !folder) return;
  const usage = folder.usage_count ? `\n当前有 ${folder.usage_count} 个模型使用该文件夹；清空后这些模型的数模文件会暂时缺失。` : '';
  if (!confirm(`确认清空数模文件夹“${folder.name}”中的全部文件？\n文件夹本身会保留，此操作不可撤销。${usage}`)) return;
  try {
    const query = new URLSearchParams({category:manager.category, name:folder.name});
    state.modelAssetManager = await api(`/api/model-asset-library/folders/contents?${query}`, {method:'DELETE'});
    renderModelAssetManager();
    toast(`已清空“${folder.name}”，删除 ${state.modelAssetManager.deleted_files || 0} 个文件`);
  } catch (error) { toast(error.message, 'error'); }
}

async function loadModelAssetLibrary(category, folder = '') {
  const categories = modelAssetCategories();
  const fallback = categories[0]?.path || '';
  const requested = category && category !== '全部项目' && category !== 'None' ? category : fallback;
  if (!requested) {
    state.modelAssetManager = {category:'', folders:[], selected:'', files:[], root:''};
    renderModelAssetManager();
    return;
  }
  const query = new URLSearchParams({category:requested});
  if (folder) query.set('folder', folder);
  state.modelAssetManager = await api(`/api/model-asset-library?${query}`);
  renderModelAssetManager();
}

async function prepareModelAssetManager(options = {}) {
  const requested = options && typeof options === 'object' && !('type' in options) ? options : {};
  const mode = requested.mode === 'bind' ? 'bind' : 'manage';
  if (mode === 'manage' && !['engineer','admin'].includes(state.auth?.role)) throw new Error('只有工程师或管理员可以维护数模资产');
  if (mode === 'bind') {
    const projectId = requested.projectId || state.hubSelectedProjectId || state.project?.id;
    if (!projectId) throw new Error('请先选择模型');
    const project = await api(`/api/projects/${encodeURIComponent(projectId)}`);
    const status = project.lifecycle?.status || 'checked_in';
    const editable = status === 'checked_out' && ['engineer','admin'].includes(state.auth?.role);
    state.modelAssetManagerContext = {mode:'bind', projectId, category:project.category || '', current:project.mesh_root || '', editable, frozen:status === 'baseline'};
    if (status === 'baseline') {
      const files = await api(`/api/projects/${encodeURIComponent(projectId)}/files`);
      const assetFiles = files.model_assets || [];
      const sizeBytes = assetFiles.reduce((sum, item) => sum + Number(item.size || 0), 0);
      state.modelAssetManager = {
        category:project.category || '', root:`${files.model_directory || projectId}/assets/baseline_mesh_snapshot`, writable:false, frozen:true,
        selected:'基线冻结数模',
        folders:[{name:'基线冻结数模', reference:project.mesh_root || '', file_count:assetFiles.length, mesh_count:assetFiles.filter(item=>['.stl','.obj'].includes(String(item.extension||'').toLowerCase())).length, size_bytes:sizeBytes, uploaded_by:project.metadata?.baseline_model_asset_uploaded_by || '', usage:[{id:project.id,name:project.name,status:'baseline'}], usage_count:1, frozen:true}],
        files:assetFiles.map(item=>({...item, kind:'file'})),
      };
      renderModelAssetManager();
    } else {
      const folder = String(project.mesh_root || '').startsWith('@model_assets/') ? String(project.mesh_root).split('/').at(-1) : '';
      await loadModelAssetLibrary(project.category, folder);
      if (state.modelAssetManager?.selection_state === 'missing') {
        toast(`当前模型引用的数模版本“${folder}”在本服务器“${state.modelAssetManager.category}”资产库中不存在，请选择现有版本并确认绑定。`);
      } else if (state.modelAssetManager?.selection_state === 'casefold_repaired') {
        toast(`已兼容 Linux 大小写差异并定位数模版本“${state.modelAssetManager.selected}”；如需永久修正引用，请点击“确认绑定”。`);
      }
    }
  } else {
    state.modelAssetManagerContext = {mode:'manage', projectId:'', category:'', current:'', editable:true, frozen:false};
    await loadModelAssetLibrary(state.hubCategory);
  }
  return state.modelAssetManager;
}

async function openModelAssetManager(options = {}) {
  try {
    await prepareModelAssetManager(options);
    $('#modelAssetManagerDialog')?.showModal();
  } catch (error) { toast(`数模资产库读取失败：${error.message}`, 'error'); }
}


async function confirmModelAssetBinding() {
  const context = state.modelAssetManagerContext;
  const manager = state.modelAssetManager;
  const folder = manager?.folders?.find(item => item.name === manager.selected);
  if (context?.mode !== 'bind' || context.frozen || !context.editable || !context.projectId || !folder?.reference) return;
  if (String(context.category || '').toLowerCase() !== String(manager.category || '').toLowerCase()) return toast('只能把当前模型类型中的数模版本绑定到该模型', 'error');
  return withBlockingLoading({title:'正在绑定数模资产', detail:'正在更新模型的公共数模资产路径并修复失效引用…'}, async () => {
    try {
      const result = await api(`/api/projects/${encodeURIComponent(context.projectId)}/mesh-folders/select`, {method:'POST', body:JSON.stringify({reference:folder.reference})});
      context.current = result.current || folder.reference;
      if (state.project?.id === context.projectId) state.project = result.project;
      await loadProjects(context.projectId);
      if (state.hubSelectedProjectId === context.projectId) await loadHubPreview(context.projectId, {force:true});
      renderModelAssetManager();
      toast(`已绑定数模资产“${folder.name}”`);
    } catch (error) { toast(error.message, 'error'); }
  });
}

async function createModelAssetVersion() {
  const category = state.modelAssetManager?.category;
  if (!category) return toast('请先创建并选择模型类型', 'error');
  const name = prompt(`在“${category}”下新建数模版本文件夹`, '版本_001');
  if (!name?.trim()) return;
  try {
    state.modelAssetManager = await api('/api/model-asset-library/folders', {method:'POST', body:JSON.stringify({category, name:name.trim()})});
    renderModelAssetManager();
    toast(`已创建数模版本“${name.trim()}”`);
  } catch (error) { toast(error.message, 'error'); }
}

async function copyModelAssetVersion() {
  const manager = state.modelAssetManager;
  if (!manager?.category || !manager.selected) return toast('请先选择要复制的数模版本', 'error');
  const name = prompt(`复制“${manager.selected}”为新版本`, `${manager.selected}_copy`);
  if (!name?.trim() || name.trim() === manager.selected) return;
  try {
    state.modelAssetManager = await api('/api/model-asset-library/folders/copy', {method:'POST', body:JSON.stringify({category:manager.category, source:manager.selected, name:name.trim()})});
    renderModelAssetManager();
    toast(`已复制数模版本为“${name.trim()}”`);
  } catch (error) { toast(error.message, 'error'); }
}

async function renameModelAssetVersion() {
  const manager = state.modelAssetManager;
  const folder = manager?.folders?.find(item => item.name === manager.selected);
  if (!manager?.category || !folder) return toast('请先选择要重命名的数模版本', 'error');
  const name = prompt(`修改数模文件夹“${folder.name}”的名称`, folder.name);
  if (!name?.trim() || name.trim() === folder.name) return;
  if (!confirm(`将“${folder.name}”重命名为“${name.trim()}”。\n\n当前引用该公共数模文件夹的 ${folder.usage_count || 0} 个模型会同步迁移引用名称。是否继续？`)) return;
  try {
    state.modelAssetManager = await api('/api/model-asset-library/folders', {method:'PUT', body:JSON.stringify({category:manager.category, source:folder.name, name:name.trim()})});
    const renamed = state.modelAssetManager.rename || {};
    const affected = renamed.affected_project_ids?.length || folder.usage_count || 0;
    if (state.modelAssetManagerContext?.current === folder.reference) {
      state.modelAssetManagerContext.current = renamed.target || state.modelAssetManager.folders?.find(item => item.name === state.modelAssetManager.selected)?.reference || '';
    }
    if (state.hubPreview?.id && renamed.affected_project_ids?.includes(state.hubPreview.id)) {
      await loadProjects(state.hubPreview.id);
      await loadHubPreview(state.hubPreview.id, {force:true});
    }
    renderModelAssetManager();
    renderHubInspectorDetail();
    toast(`已重命名为“${name.trim()}”，同步更新 ${affected} 个模型引用`);
  } catch (error) { toast(error.message, 'error'); }
}

async function deleteModelAssetVersion() {
  const manager = state.modelAssetManager;
  const folder = manager?.folders?.find(item => item.name === manager.selected);
  if (!manager?.category || !folder) return toast('请先选择要删除的数模版本', 'error');
  if (folder.usage_count) return toast(`该版本仍被以下模型使用：${(folder.usage || []).map(item=>item.name || item.id).join('、')}`, 'error');
  if (!confirm(`确认永久删除数模版本文件夹“${folder.name}”及其中全部文件？`)) return;
  try {
    const query = new URLSearchParams({category:manager.category, name:folder.name});
    state.modelAssetManager = await api(`/api/model-asset-library/folders?${query}`, {method:'DELETE'});
    renderModelAssetManager();
    toast(`已删除数模版本“${folder.name}”`);
  } catch (error) { toast(error.message, 'error'); }
}

async function uploadModelAssetVersionFiles(input) {
  const manager = state.modelAssetManager;
  if (!manager?.category || !manager.selected || !input?.files?.length) return;
  const files = [...input.files];
  return withBlockingLoading({title:'正在上传数模资产', detail:`正在上传 ${files.length} 个文件到“${manager.selected}”，请等待。`}, async token => {
    const form = new FormData();
    files.forEach(file => form.append('files', file, file.name));
    form.append('category', manager.category);
    form.append('folder', manager.selected);
    form.append('relative_paths', JSON.stringify(files.map(file => file.webkitRelativePath || file.name)));
    try {
      updateBlockingLoading(token,{detail:'文件已提交，正在刷新数模资产目录…'});
      state.modelAssetManager = await api('/api/model-asset-library/upload', {method:'POST', body:form, timeout:0});
      renderModelAssetManager();
      toast(`已上传 ${state.modelAssetManager.uploaded?.length || files.length} 个数模资产文件`);
    } catch (error) { toast(error.message, 'error'); }
    finally { input.value = ''; }
  });
}

async function createProjectFromPrompt() {
  const category = state.hubCategory && state.hubCategory !== '全部项目' ? state.hubCategory : 'None';
  try {
    const payload = category === 'None' ? {name:'新模型', demo:true} : {name:'新模型', category, demo:true};
    const project = await api('/api/projects', {method:'POST', body:JSON.stringify(payload)});
    state.hubSelectedProjectId = project.id;
    await loadProjects(project.id);
    await loadHubPreview(project.id);
    state.hubInspectorSection = hubInspectorDefaultSection();
    await activateHubInspectorSection(state.hubInspectorSection, {force:true});
    toast(`已在“${category === 'None' ? (state.projectRootName || '项目') : category}”中创建模型 ${project.name}`);
  } catch (error) { toast(error.message, 'error'); }
}

async function addProjectCategory() {
  if (!(state.auth?.role === 'admin' || state.auth?.admin_mode)) return toast('新增模型类型需要管理员权限/管理模式', 'error');
  const parent = state.hubCategory === '全部项目' || state.hubCategory === 'None' ? '' : state.hubCategory;
  const name = prompt(parent ? `在“${parent}”下创建子文件夹` : '新建模型类型文件夹', '新类型');
  if (!name?.trim()) return;
  try {
    const result = await api('/api/project-categories', {method:'POST', body:JSON.stringify({name:name.trim(), parent})});
    state.categories = result.categories || state.categories;
    state.modelTypes = result.tree || state.modelTypes;
    state.hubCategory = result.created;
    renderHub();
    toast(`已添加分类“${result.created}”`);
  } catch (error) { toast(error.message, 'error'); }
}

async function deleteProjectCategory() {
  const category = state.hubCategory;
  if (!category || category === '全部项目' || category === 'None') {
    toast('请先选择一个可删除的项目分类', 'error');
    return;
  }
  if (!(state.auth?.role === 'admin' || state.auth?.admin_mode)) return toast('删除模型分类需要管理员权限/管理模式', 'error');
  const count = state.projects.filter(item => (item.category || 'None') === category || (item.category || '').startsWith(`${category}/`)).length;
  const deleteProjects = confirm(`删除分类“${category}”后，是否同时删除其中的 ${count} 个模型？\n\n选择“取消”会保留模型并将它们移到根“${state.projectRootName || '项目'}”文件夹。`);
  if (deleteProjects && !confirm(`再次确认：将永久删除分类“${category}”及其中全部 ${count} 个模型。此操作不可撤销。`)) return;
  try {
    const result = await api(`/api/project-categories/${encodePath(category)}?delete_projects=${deleteProjects ? 'true' : 'false'}`, {method:'DELETE'});
    state.categories = result.categories || [];
    state.modelTypes = result.tree || state.modelTypes;
    state.hubCategory = 'None';
    state.hubSelectedProjectId = null; state.hubPreview = null;
    if (deleteProjects && result.affected_project_ids?.includes(state.project?.id)) { state.project = null; clearDirty(); }
    await loadProjects();
    toast(deleteProjects ? `已删除分类“${category}”及其中模型` : `已删除分类“${category}”，其中模型已移到根“${state.projectRootName || '项目'}”文件夹`);
  } catch (error) { toast(error.message, 'error'); }
}

async function transitionHubProject(action) {
  const projectId = state.hubSelectedProjectId;
  if (!projectId) return;
  const editorOpen = isEditorWindowOpen(projectId);
  if (editorOpen && action !== 'check_in') {
    toast('该模型已有独立 Editor 页面，当前无需重复签出。', 'error');
    return;
  }
  let checkInChoice = {archive:false, log:'', archive_name:'', overwrite_version_id:''};
  if (action === 'check_in') {
    const choice = await chooseManualCheckInArchive(projectId);
    if (choice === null) return;
    checkInChoice = choice;
  }
  if (editorOpen && action === 'check_in') {
    const existing = window.open('', editorWindowName(projectId));
    if (existing) {
      try {
        existing.postMessage({
          type:'mujoco-studio-editor-check-in',
          projectId,
          archive:checkInChoice.archive,
          log:checkInChoice.log,
          archive_name:checkInChoice.archive_name,
          overwrite_version_id:checkInChoice.overwrite_version_id,
        }, location.origin);
        existing.focus();
      } catch (_) {}
      toast(checkInChoice.archive ? (checkInChoice.overwrite_version_id ? '已在模型 Editor 中发起“覆盖历史版本并签入”。' : '已在模型 Editor 中发起“新建历史版本并签入”。') : '已在模型 Editor 中发起“保存最新版本并签入”。');
      return;
    }
    try { localStorage.removeItem(editorRegistryKey(projectId)); } catch (_) {}
  }
  const checkingIn = action === 'check_in';
  return withBlockingLoading({
    title: checkingIn ? '正在签入模型' : '正在签出模型',
    detail: checkingIn
      ? (checkInChoice.archive ? (checkInChoice.overwrite_version_id ? '正在保存修改、覆盖指定历史版本并锁定项目。' : '正在保存修改、新建历史版本并锁定项目。') : '正在保存最新模型并结束编辑占用。')
      : '正在建立可编辑状态并刷新项目权限，请等待。',
  }, async token => {
    try {
      if (checkingIn && state.project?.id === projectId) {
        updateBlockingLoading(token,{detail:'正在提交尚未落盘的编辑修改…'});
        await flushInteractionCommit({finalize:true});
      }
      updateBlockingLoading(token,{
        detail:checkingIn
          ? (checkInChoice.archive ? (checkInChoice.overwrite_version_id ? '正在覆盖指定历史版本并完成签入…' : '正在新建历史版本并完成签入…') : '正在保存最新版本并释放编辑占用…')
          : '正在执行签出与编辑权限切换…',
      });
      const updated = await api(`/api/projects/${projectId}/lifecycle`, {
        method:'POST',
        body:JSON.stringify({
          action,
          ...(checkingIn ? {archive:checkInChoice.archive, log:checkInChoice.log,
            archive_name:checkInChoice.archive_name, overwrite_version_id:checkInChoice.overwrite_version_id} : {}),
        }),
      });
      if (state.project?.id === projectId) {
        state.project = updated; clearDirty();
        if (checkingIn) clearArchiveDirty();
        applyProjectAccess(); markJsonEditorStale();
      }
      updateProjectSummary(updated);
      state.hubSelectedProjectId = projectId;
      renderHub();
      if (action === 'check_out') {
        const catalog = $('#hubProjectList');
        if (catalog) catalog.scrollTop = 0;
      }
      updateBlockingLoading(token,{detail:'生命周期切换已完成，正在同步预览、版本和文件状态…'});
      await loadHubPreview(projectId, {waitForMetadata:false, force:true});
      toast(checkingIn
        ? (checkInChoice.archive ? (checkInChoice.overwrite_version_id ? '项目已签入并更新指定历史版本；配置已锁定' : '项目已签入并新建历史版本；配置已锁定') : '最新版本已保存并签入；编辑占用已释放')
        : '项目已签出，现在可以修改配置并生成动画 HTML');
    } catch (error) { toast(error.message, 'error'); }
  });
}

async function waitForBackgroundJob(jobId, purpose='后台任务', onProgress=null) {
  if(!jobId) throw new Error(`${purpose}没有返回 Job ID`);
  let transientErrors = 0;
  while(true) {
    let job;
    try {
      job=await api(`/api/jobs/${encodeURIComponent(jobId)}`, {timeout:9000});
      transientErrors = 0;
    } catch (error) {
      if (error?.status === 401 || error?.status === 403 || error?.status === 404 || ++transientErrors > 5) throw error;
      // An interrupted network poll is not proof that the copy has failed;
      // keep its job identity and retry instead of submitting a second fork.
      await new Promise(resolve=>setTimeout(resolve,2000));
      continue;
    }
    if (typeof onProgress === 'function') onProgress(job);
    if(job.status==='completed') return job;
    if(['failed','cancelled','timed_out'].includes(job.status)) {
      const message=job.error?.message||job.message||`${purpose}失败`;
      throw new Error(message);
    }
    await new Promise(resolve=>setTimeout(resolve,1500));
  }
}

async function ensureBaselineAnimationHtml(projectId) {
  const inventory=await api(`/api/projects/${encodeURIComponent(projectId)}/files`);
  const exists=(inventory.delivery_outputs||[]).some(item=>item.kind==='animation_html');
  if(exists)return false;
  alert('当前交付数据中没有动画 HTML。系统将自动在后台生成动画 HTML；生成完成后再继续创建基线。');
  toast('未找到动画 HTML，正在后台自动生成…');
  const result=await api(`/api/projects/${encodeURIComponent(projectId)}/export-animation-html?baseline_prepare=true`,{method:'POST'});
  await waitForBackgroundJob(result.job_id,'动画 HTML 自动生成');
  toast('动画 HTML 已自动生成并推送到交付数据，继续创建基线','success');
  return true;
}

async function refreshBaselineGantt(projectId) {
  if(typeof window.__GanttPopup__?.refreshCache!=='function') return null;
  try {
    const result=await window.__GanttPopup__.refreshCache(projectId);
    return Number(result?.saved_at)||null;
  } catch(error) {
    console.warn('[baseline] browser gantt refresh failed; server fallback will regenerate:',error);
    toast(`浏览器甘特图重新生成失败，将改用服务端兼容渲染继续打基线：${error.message}`,'error');
    return null;
  }
}

async function latestArchiveLogForProject(projectId) {
  let versions = [];
  try {
    const fresh = await api(`/api/projects/${encodeURIComponent(projectId)}/versions`, {timeout:12000});
    versions = Array.isArray(fresh) ? fresh : [];
    if (state.hubSelectedProjectId === projectId) state.hubVersions = versions;
  } catch (error) {
    console.warn('[baseline] latest archive log refresh failed; using loaded Hub history:', error);
    versions = state.hubSelectedProjectId === projectId && Array.isArray(state.hubVersions) ? state.hubVersions : [];
  }
  const latestArchive = versions.find(version => String(version?.version_kind || 'archive') === 'archive');
  return String(latestArchive?.log || '');
}

async function createHubBaseline() {
  const projectId = state.hubSelectedProjectId;
  if (!projectId) return;
  if(!confirm('创建基线将自动重新生成并覆盖 3 类交付数据：NX AFU 脚本、甘特图 PNG、模型 JSON；动画 HTML 复用交付数据中的最新文件。所有 CSV 保存在交付数据的“表格文件夹”中，时序库仅保存 TSJSON。若动画 HTML 不存在，系统会先弹窗提示并自动后台生成。随后冻结这 4 类交付数据与当前数模资产。是否继续？'))return;
  const existingLog = await latestArchiveLogForProject(projectId);
  const sourceName = state.hubPreview?.name || state.projects.find(item => item.id === projectId)?.name || '基线模型';
  const baselineEdit = await editBaselineLog(existingLog, sourceName);
  if (baselineEdit === null) return;
  const name = String(baselineEdit.name || '').trim();
  const log = String(baselineEdit.log || '');
  if (!name) return toast('基线模型名称不能为空', 'error');
  return withBlockingLoading({title:'正在创建基线', detail:'正在准备动画 HTML，随后生成交付文件与冻结快照。请勿重复提交。'}, async token => {
    try {
      updateBlockingLoading(token,{detail:'阶段 1/3 · 校验或生成交付动画 HTML…'});
      await ensureBaselineAnimationHtml(projectId);
      updateBlockingLoading(token,{detail:'阶段 2/3 · 更新甘特图缓存…'});
      const gantt_saved_at=await refreshBaselineGantt(projectId);
      updateBlockingLoading(token,{detail:'阶段 3/3 · 服务端校验仿真、冻结基线资产；大模型可能需要较长时间…'});
      const baseline = await api(
        `/api/projects/${projectId}/baseline`,
        {method:'POST', body:JSON.stringify({name, log, gantt_saved_at}), timeout:0},
      );
      await loadProjects(baseline.id);
      state.hubSelectedProjectId = baseline.id;
      await loadHubPreview(baseline.id);
      toast(`已创建基线 ${baseline.name}；XML 与其余交付数据已冻结`);
    } catch (error) { toast(error.message, 'error'); }
  });
}

// V2.16.11.1: default binding is a read-only choice from the existing public
// library. The server validates category + every required mesh file again.
async function chooseBaselineForkMeshPolicy(projectId) {
  const preview = state.hubPreview;
  if (!preview || preview.id !== projectId) throw new Error('请重新选择基线模型');
  const category = String(preview.category || '');
  const library = await api(`/api/model-asset-library?category=${encodeURIComponent(category)}`, {timeout:15000});
  const dialog = $('#hubForkMeshDialog');
  const form = $('#hubForkMeshForm');
  const select = $('#hubForkMeshFolder');
  const copyName = $('#hubForkCopyFolderName');
  const hint = $('#hubForkMeshHint');
  const folders = Array.isArray(library.folders) ? library.folders : [];
  const reference = String(preview.baseline_mesh_source_reference || '');
  select.innerHTML = '<option value="">请选择现有数模资产文件夹</option>' + folders.map(folder =>
    `<option value="${esc(folder.reference)}">${esc(folder.name)} · ${Number(folder.mesh_count)||0} 个数模</option>`).join('');
  if (folders.some(folder => folder.reference === reference)) select.value = reference;
  copyName.value = `${preview.name || '模型'}_数模副本`;
  form.querySelector('[value="bind_existing"]').checked = true;
  hint.textContent = folders.length
    ? '默认不复制数模。请确认现有资产文件夹与基线引用的 STL/OBJ 文件对应。'
    : '当前模型类型没有可绑定的现有资产文件夹；如需继续，请主动选择“复制冻结数模”。';
  function updateFields() {
    const mode = form.querySelector('[name="hubForkMeshStrategy"]:checked')?.value;
    $('#hubForkBindFields').hidden = mode !== 'bind_existing';
    $('#hubForkCopyFields').hidden = mode !== 'copy_frozen';
    select.disabled = mode !== 'bind_existing';
    copyName.disabled = mode !== 'copy_frozen';
  }
  updateFields();
  return await new Promise(resolve => {
    // Native <dialog> emits its close event asynchronously. Resolve only after
    // that event to avoid a stale close from dismissing the next quick fork.
    let closing = false;
    let selected = null;
    const cleanup = () => {
      form.removeEventListener('submit', onSubmit);
      form.removeEventListener('change', updateFields);
      $('#hubForkMeshCancel').removeEventListener('click', onCancel);
      dialog.removeEventListener('close', onClose);
      resolve(selected);
    };
    const finish = value => {
      if (closing) return;
      closing = true;
      selected = value;
      if (dialog.open) dialog.close();
      else cleanup();
    };
    const onCancel = () => finish(null);
    const onClose = () => cleanup();
    const onSubmit = event => {
      event.preventDefault();
      const strategy = form.querySelector('[name="hubForkMeshStrategy"]:checked')?.value;
      if (strategy === 'bind_existing') {
        if (!select.value) { hint.textContent = '请选择一个现有数模文件夹，或切换到复制冻结数模。'; select.focus(); return; }
        finish({mesh_asset_strategy:'bind_existing',mesh_asset_reference:select.value});
      } else {
        if (!copyName.value.trim()) { hint.textContent = '请输入新数模资产文件夹名称。'; copyName.focus(); return; }
        finish({mesh_asset_strategy:'copy_frozen',mesh_folder_name:copyName.value.trim()});
      }
    };
    form.addEventListener('submit', onSubmit);
    form.addEventListener('change', updateFields);
    $('#hubForkMeshCancel').addEventListener('click', onCancel);
    dialog.addEventListener('close', onClose);
    dialog.showModal();
  });
}

let hubForkInProgress = null;
async function forkHubProject() {
  const projectId = state.hubSelectedProjectId;
  if (!projectId) return;
  if (hubForkInProgress === projectId) {
    toast('该基线已经在后台复制，可在任务列表查看进度，无需重复提交。', 'info');
    return;
  }
  // Lock the Hub action before opening the dialog so rapid double-clicks do
  // not create multiple modals or concurrent model copies.
  hubForkInProgress = projectId;
  try {
    const selection = await chooseBaselineForkMeshPolicy(projectId);
    if (!selection) return;
    // Existing JobManager heavy lane; no synchronous mesh copying in HTTP.
    const accepted = await api(`/api/projects/${encodeURIComponent(projectId)}/fork?background=true`, {
      method:'POST', body:JSON.stringify(selection), timeout:15000,
    });
    toast('已受理基线复制任务，Hub 可继续使用。完成后将自动刷新项目列表。', 'info');
    const job = await waitForBackgroundJob(accepted.job_id, '基线版本复制');
    const result = job.result || {};
    if (!result.project_id) throw new Error('复制任务完成但没有返回新模型 ID，请刷新 Hub 核对任务状态');
    const stillSelected = state.hubSelectedProjectId === projectId && routeContextFromLocation().kind === 'hub';
    await loadProjects(stillSelected ? result.project_id : null);
    toast(`已创建可编辑项目「${result.name || result.project_id}」，后台复制完整结束`, 'success');
  } catch (error) {
    toast(`使用基线失败：${error.message}`, 'error');
  } finally {
    if (hubForkInProgress === projectId) hubForkInProgress = null;
  }
}


async function copyHubProjectVersion() {
  const projectId = state.hubSelectedProjectId;
  if (!projectId) return;
  const defaultModelName=`${state.hubPreview?.name||'模型'}_副本`;
  const modelName=prompt('请输入复制后的模型名称：',defaultModelName);
  if(modelName===null)return;if(!modelName.trim())return toast('模型名称不能为空','error');
  return withBlockingLoading({title:'正在复制模型版本', detail:'正在复制模型数据，并继续复用原公共数模资产文件夹…'}, async () => {
    try {
      const copied = await api(`/api/projects/${projectId}/copy-version`, {method:'POST', body:JSON.stringify({model_name:modelName.trim()})});
      state.hubCategory = copied.category || state.hubPreview?.category || 'None';
      state.hubSelectedProjectId = copied.id;
      await loadProjects(copied.id);
      await loadHubPreview(copied.id);
      toast(`已在原模型类型中复制模型“${copied.name}”，并继续使用原公共数模资产文件夹`);
    } catch (error) { toast(error.message, 'error'); }
  });
}

async function deleteHubProject() {
  const projectId = state.hubSelectedProjectId;
  const preview = state.hubPreview;
  if (!projectId || !preview || !confirm(`确定删除“${preview.name}”？模型将移入回收站并保留 ${state.trashRetentionDays} 天，可在回收站恢复。`)) return;
  return withBlockingLoading({title:'正在移入回收站', detail:'正在移动模型与其交付数据并刷新模型列表，请勿进行其他操作。'}, async () => {
    try {
      await api(`/api/projects/${projectId}`, {method:'DELETE'});
      if (state.project?.id === projectId) { state.project = null; clearDirty(); }
      state.hubPreview = null; state.hubSelectedProjectId = null;
      await loadProjects();
      toast(`模型已移入回收站，将保留 ${state.trashRetentionDays} 天`);
    } catch (error) { toast(error.message, 'error'); }
  });
}


async function restoreHubTrashProject(trashId) {
  if (!trashId || !['engineer','admin'].includes(state.auth?.role)) return;
  const item=state.recycleBin.find(entry=>entry.trash_id===trashId);
  if (!item) return toast('回收站条目不存在或已过期','error');
  if (!confirm(`恢复“${item.name || item.project_id}”到原模型类型“${item.category || 'None'}”？`)) return;
  return withBlockingLoading({title:'正在恢复模型', detail:'正在恢复模型目录与交付数据；如原位置存在冲突将拒绝覆盖。'}, async()=>{
    try {
      const restored=await api(`/api/recycle-bin/${encodeURIComponent(trashId)}/restore`,{method:'POST',body:'{}'});
      state.hubCategory=restored.category||'None';
      state.hubSelectedProjectId=restored.id;
      state.hubTypeSummary=null;
      await loadProjects(restored.id);
      await loadHubPreview(restored.id,{force:true});
      toast(`已恢复模型“${restored.name}”`);
    } catch(error) { toast(error.message||String(error),'error'); }
  });
}

async function deleteSelectedHubTrashProjects() {
  if (!['engineer','admin'].includes(state.auth?.role)) return;
  const selectedItems = state.recycleBin.filter(item => state.hubSelectedTrashIds.has(item.trash_id));
  if (!selectedItems.length) return toast('请先选择要永久删除的模型', 'error');
  const previewNames = selectedItems.slice(0, 4).map(item => `“${item.name || item.project_id}”`).join('、');
  const more = selectedItems.length > 4 ? ` 等 ${selectedItems.length} 个模型` : '';
  if (!confirm(`确定永久删除 ${previewNames}${more}？\n\n此操作会物理删除回收站中的模型及其随附交付数据，无法恢复。`)) return;
  return withBlockingLoading({title:'正在永久删除', detail:`准备删除 ${selectedItems.length} 个回收站模型；该操作不可恢复。`}, async token => {
    const failures = [];
    let deleted = 0;
    for (let index = 0; index < selectedItems.length; index += 1) {
      const item = selectedItems[index];
      updateBlockingLoading(token, {detail:`正在永久删除 ${index + 1}/${selectedItems.length}：${item.name || item.project_id}`});
      try {
        await api(`/api/recycle-bin/${encodeURIComponent(item.trash_id)}`, {method:'DELETE'});
        state.hubSelectedTrashIds.delete(item.trash_id);
        deleted += 1;
      } catch (error) {
        failures.push({item, error});
      }
    }
    await loadProjects();
    state.hubCategory = '__recycle_bin__';
    renderHub();
    if (failures.length) {
      const first = failures[0];
      toast(`已永久删除 ${deleted} 个；${failures.length} 个失败：${first.item.name || first.item.project_id} · ${first.error.message || first.error}`, 'error');
    } else {
      toast(`已永久删除 ${deleted} 个回收站模型`);
    }
  });
}

async function reclassifyHubProject(projectId, category) {
  const row=state.projects.find(item=>item.id===projectId);
  const previousProjects=state.projects;
  const previousPreview=state.hubPreview;
  const previousCache=state.hubPreviewCache.get(projectId);
  const previousFiles=state.hubFiles;
  const previousAssetContext=state.modelAssetManagerContext;
  const previousSelectedProjectId=state.hubSelectedProjectId;
  const sourceCategory=row?.category || (state.hubPreview?.id===projectId?state.hubPreview.category:'None');
  const sourceName=row?.name || (state.hubPreview?.id===projectId?state.hubPreview.name:projectId);
  const optimisticName=managedReclassifiedProjectName(sourceName,sourceCategory,category);
  state.projects=state.projects.map(item=>item.id===projectId?{...item,category,name:optimisticName}:item);
  if(state.hubPreview?.id===projectId)state.hubPreview={...state.hubPreview,category,name:optimisticName};
  if(previousCache?.preview)state.hubPreviewCache.set(projectId,{...previousCache,preview:{...previousCache.preview,category,name:optimisticName}});
  if(state.hubFiles&&(state.hubFiles.project_id===projectId||previousSelectedProjectId===projectId)){
    state.hubFiles={...state.hubFiles,model_directory:`${category || 'None'}/${projectId}`};
  }
  if(state.modelAssetManagerContext?.projectId===projectId){
    state.modelAssetManagerContext={...state.modelAssetManagerContext,category};
  }
  refreshHubModelTypeCountsFromProjects();
  renderHub();
  try {
    const updated = await api(`/api/projects/${projectId}/reclassify`, {method:'POST', body:JSON.stringify({category})});
    if(previousSelectedProjectId!==projectId){
      state.hubSelectedProjectId=projectId;
      state.hubPreview=null;
      state.hubVersions=[];
      state.hubFiles=null;
      state.hubTypeSummary=null;
    }
    applyHubProjectAuthoritative(updated);
    if(previousSelectedProjectId!==projectId){
      void loadHubPreview(projectId,{force:true}).catch(error=>console.warn('[hub] async reclassify preview refresh failed:',error));
    }
    const targetLabel = updated.category === 'None' ? (state.projectRootName || '项目') : updated.category;
    toast(`已归入“${targetLabel}”并重命名为 ${updated.name}`);
  } catch (error) {
    state.projects=previousProjects;
    state.hubPreview=previousPreview;
    state.hubFiles=previousFiles;
    state.modelAssetManagerContext=previousAssetContext;
    state.hubSelectedProjectId=previousSelectedProjectId;
    if(previousCache)state.hubPreviewCache.set(projectId,previousCache);else state.hubPreviewCache.delete(projectId);
    refreshHubModelTypeCountsFromProjects();
    renderHub();
    toast(error.message, 'error');
  }
}

async function moveModelType(source, targetParent = '', before = '') {
  if (!source) return;
  const sourceParent = source.split('/').slice(0,-1).join('/');
  if (targetParent === source || targetParent.startsWith(`${source}/`)) return toast('文件夹不能移动到自身或其子文件夹下', 'error');
  const hierarchyChanged = sourceParent !== targetParent;
  const parentLabel = targetParent ? `“${targetParent}”下` : `根“${state.projectRootName || '项目'}”下`;
  const positionLabel = before ? `，位于“${before.split('/').pop()}”之前` : '，位于该层级末尾';
  const actionLabel = hierarchyChanged ? `改变层级并移动到${parentLabel}${positionLabel}` : `调整同层顺序到${parentLabel}${positionLabel}`;
  if (!confirm(`即将${actionLabel}：\n\n“${source}”\n\n该操作会连同其全部子文件夹和其中模型一起移动。确认后执行并自动刷新页面。`)) return;
  try {
    const result = await api(`/api/model-types/${encodePath(source)}/move`, {method:'POST', body:JSON.stringify({target_parent:targetParent, before})});
    state.modelTypes = result.tree || state.modelTypes;
    state.categories = flattenModelTypes(state.modelTypes).map(item => item.path);
    syncHubCollapseState();
    location.reload();
  } catch (error) { toast(error.message, 'error'); }
}

async function exportSelectedProject() {
  const projectId = state.hubSelectedProjectId || state.project?.id;
  if (!projectId) return toast('请先选择一个项目', 'error');
  const selected = state.projects.find(item => item.id === projectId);
  if (projectStatus(selected) === 'checked_out') return toast('签出状态的项目不能导出，请先签入', 'error');
  if (state.project?.id === projectId && state.dirty) await commitEdits();
  const modelName=String(selected?.name || state.project?.name || projectId).replace(/[\/:*?"<>|]+/g,'_').replace(/[ ._]+$/g,'') || '模型';
  const filename=`${modelName}.json`;
  const handle=await chooseLocalSaveHandle(filename,'application/json');if(!handle)return;
  const response=await fetch(`/api/projects/${encodeURIComponent(projectId)}/export-json`);
  if(!response.ok)return toast(`项目 JSON 导出失败 (${response.status})`,'error');
  await writeBlobToChosenHandle(handle,await response.blob(),'项目 JSON');
}

async function importProjectJson(file) {
  if (!file) return;
  try {
    const data = JSON.parse(await file.text());
    await importProjectData(data);
  } catch (error) { toast(error.message, 'error'); }
}

async function importProjectData(data) {
  return withBlockingLoading({title:'正在导入项目', detail:'正在校验、迁移并写入项目数据，请等待。'}, async token => {
    try {
      const result = await api('/api/projects/import-json', {
        method:'POST', body:JSON.stringify({data, target_category:currentHubImportCategory()}),
      });
      const repair = result.repair || {removed_drives:[], cleared_mappings:[]};
      updateBlockingLoading(token,{detail:'项目数据已写入，正在刷新模型列表与预览…'});
      state.hubCategory = result.project.category || currentHubImportCategory();
      await loadProjects(result.project.id);
      state.hubSelectedProjectId = result.project.id;
      await loadHubPreview(result.project.id);
      const warnings=result.migration?.warnings || [];
      toast(`${result.baseline_project ? '基线及其签入工作副本已导入' : result.migration?.legacy ? '一代 V21.5 模型 JSON 已兼容导入' : '项目已导入'}${repair.removed_drives.length ? `；清理 ${repair.removed_drives.length} 个失效驱动` : ''}${warnings.length ? `；忽略 ${warnings.length} 个不兼容运动段` : ''}`);
      if(warnings.length){
        const shown=warnings.slice(0,12).join('\n');
        const more=warnings.length>12?`\n……另有 ${warnings.length-12} 项已省略。`:'';
        window.alert(`模型 JSON 已完成兼容导入。以下运动段的 motion profile 不属于二代互通范围，已提醒并忽略：\n\n${shown}${more}`);
      }
    } catch (error) { toast(error.message, 'error'); }
  });
}

async function importProjectFromDefaultFolder() {
  if (!state.capabilities?.server_file_dialogs) {
    $('#projectJsonInput').click();
    return;
  }
  try {
    const selected = await api('/api/dialogs/select-project-json', {method:'POST'});
    if (selected.data) await importProjectData(selected.data);
  } catch (error) {
    toast(`${error.message}；已切换到浏览器文件选择`, 'error');
    $('#projectJsonInput').click();
  }
}

async function exportSelectedBundle() {
  const projectId = state.hubSelectedProjectId || state.project?.id;
  if (!projectId) return toast('请先选择一个项目', 'error');
  const selected = state.projects.find(item => item.id === projectId);
  if (projectStatus(selected) === 'checked_out') return toast('签出状态的项目不能导出完整包，请先签入', 'error');
  const modelName=String(selected?.name || state.project?.name || projectId).replace(/[\/:*?"<>|]+/g,'_').replace(/[ ._]+$/g,'') || '模型';
  const filename=`${modelName}.mujoco-project.zip`;
  const handle=await chooseLocalSaveHandle(filename,'application/zip'); if(!handle)return;
  return withBlockingLoading({title:'正在导出完整压缩包', detail:'正在隔离复制数模、交付数据与存档并生成压缩包，请等待。'}, async token => {
    const response=await fetch(`/api/projects/${encodeURIComponent(projectId)}/export-bundle`);
    if(!response.ok){
      let detail=''; try{detail=(await response.json())?.detail||'';}catch(_){}
      throw new Error(detail || `完整压缩包导出失败 (${response.status})`);
    }
    updateBlockingLoading(token,{detail:'压缩包已生成，正在写入所选位置…'});
    await writeBlobToChosenHandle(handle,await response.blob(),'项目完整压缩包');
  });
}

async function importProjectBundle(file) {
  if (!file) return;
  return withBlockingLoading({title:'正在导入完整压缩包', detail:'正在安全解包、校验并恢复数模、交付数据与存档，请等待。'}, async token => {
    try {
      const form=new FormData(); form.append('file',file); form.append('target_category',currentHubImportCategory());
      const result=await api('/api/projects/import-bundle',{method:'POST',body:form,timeout:0});
      updateBlockingLoading(token,{detail:'完整包已恢复，正在刷新当前文件夹与模型预览…'});
      state.hubCategory=result.project.category || currentHubImportCategory();
      await loadProjects(result.project.id);
      state.hubSelectedProjectId=result.project.id;
      await loadHubPreview(result.project.id);
      const bundle=result.bundle||{};
      toast(`完整压缩包已导入${bundle.asset_folder_name ? `；数模注入 ${bundle.asset_folder_name}` : ''}${Number(bundle.archive_versions_imported)>0 ? `；恢复 ${bundle.archive_versions_imported} 条存档` : ''}`);
    } catch(error) { toast(error.message,'error'); }
  });
}

async function loadHubVersionPreview(versionId) {
  const projectId = state.hubSelectedProjectId;
  try {
    const preview = await api(`/api/projects/${projectId}/versions/${versionId}/preview`);
    if (state.hubSelectedProjectId !== projectId) return;
    state.hubPreview = preview;
    state.hubPreviewVersionId = versionId;
    renderHubPreview();
  } catch (error) { toast(error.message, 'error'); }
}

async function saveHubCategory() {
  const projectId = state.hubSelectedProjectId;
  const category = $('#hubCategoryInput')?.value.trim() || 'None';
  try {
    if (state.project?.id === projectId && state.dirty) await commitEdits();
    const project = state.project?.id === projectId ? state.project : await api(`/api/projects/${projectId}`);
    project.category = category;
    await api(`/api/projects/${projectId}`, {method:'PUT', body:JSON.stringify(project)});
    state.hubCategory = category;
    await loadProjects(state.project.id);
    toast('项目分类已保存');
  } catch (error) { toast(error.message, 'error'); }
}

function hierarchyViewMode() {
  return state.ui?.model?.hierarchy_view === 'diagram' ? 'diagram' : 'tree';
}

function hierarchyDiagramUi() {
  return state.ui?.model?.diagram || {};
}


const HIERARCHY_DIAGRAM_NODE_LIMITS = {minW:96, maxW:720, minH:72, maxH:520};

function hierarchyDiagramClampNodeSize(value, axis) {
  const min = axis === 'w' ? HIERARCHY_DIAGRAM_NODE_LIMITS.minW : HIERARCHY_DIAGRAM_NODE_LIMITS.minH;
  const max = axis === 'w' ? HIERARCHY_DIAGRAM_NODE_LIMITS.maxW : HIERARCHY_DIAGRAM_NODE_LIMITS.maxH;
  return Math.max(min, Math.min(max, Number(value) || min));
}

function hierarchyDiagramLayoutState() {
  const saved = hierarchyDiagramUi().layout || {};
  return {
    property_height:Math.max(86, Math.min(360, Number(saved.property_height) || 150)),
    library_width:Math.max(108, Math.min(320, Number(saved.library_width) || 140)),
  };
}

function hierarchyDiagramApplyLayout() {
  const studio = $('.model-studio');
  if (!studio || hierarchyViewMode() !== 'diagram') return;
  const layout = hierarchyDiagramLayoutState();
  studio.style.setProperty('--diagram-property-height', `${layout.property_height}px`);
  studio.style.setProperty('--diagram-library-width', `${layout.library_width}px`);
}

function hierarchyDiagramSetLayout(next, semantic, opts = {}) {
  const current = hierarchyDiagramLayoutState();
  const layout = {
    property_height:Math.max(86, Math.min(360, Number(next?.property_height) || current.property_height)),
    library_width:Math.max(108, Math.min(320, Number(next?.library_width) || current.library_width)),
  };
  uiSet('model.diagram.layout', layout, semantic, opts);
  hierarchyDiagramApplyLayout();
  return layout;
}

function hierarchyDiagramNodeDefaults(layer, layout = null) {
  const saved = hierarchyDiagramUi().nodes?.[layer.id] || {};
  const firstMesh = (layer.meshes || [])[0] || null;
  const selectedMeshId = (layer.meshes || []).some(mesh => mesh.id === saved.body_mesh_id) ? saved.body_mesh_id : (firstMesh?.id || '');
  const fallback = layout?.[layer.id] || {x:80, y:70, w:196, h:158};
  return {
    x: Number.isFinite(Number(saved.x)) ? Number(saved.x) : fallback.x,
    y: Number.isFinite(Number(saved.y)) ? Number(saved.y) : fallback.y,
    w: hierarchyDiagramClampNodeSize(Number.isFinite(Number(saved.w)) ? Number(saved.w) : fallback.w, 'w'),
    h: hierarchyDiagramClampNodeSize(Number.isFinite(Number(saved.h)) ? Number(saved.h) : fallback.h, 'h'),
    body_mesh_id: selectedMeshId,
  };
}

function hierarchyDiagramAutoLayoutValues() {
  const layers = state.project?.layers || [];
  const byId = new Map(layers.map(layer => [layer.id, layer]));
  const savedNodes = hierarchyDiagramUi().nodes || {};
  const order = new Map(layers.map((layer, index) => [layer.id, index]));
  const dimensions = new Map(layers.map(layer => {
    const saved = savedNodes[layer.id] || {};
    return [layer.id, {
      w:hierarchyDiagramClampNodeSize(Number(saved.w) || 196, 'w'),
      h:hierarchyDiagramClampNodeSize(Number(saved.h) || 158, 'h'),
      body_mesh_id:(layer.meshes || []).some(mesh => mesh.id === saved.body_mesh_id) ? saved.body_mesh_id : (layer.meshes?.[0]?.id || ''),
    }];
  }));
  const children = new Map();
  const addChild = (parentId, layer) => {
    if (!children.has(parentId)) children.set(parentId, []);
    children.get(parentId).push(layer);
  };
  layers.forEach(layer => {
    const parentId = layer.parent_id !== layer.id && byId.has(layer.parent_id) ? layer.parent_id : 'root';
    addChild(parentId, layer);
  });
  children.forEach(items => items.sort((a, b) => {
    const ay = Number(savedNodes[a.id]?.y), by = Number(savedNodes[b.id]?.y);
    if (Number.isFinite(ay) && Number.isFinite(by) && Math.abs(ay - by) > 0.5) return ay - by;
    return (order.get(a.id) || 0) - (order.get(b.id) || 0);
  }));

  const roots = [...(children.get('root') || [])];
  const depthById = new Map();
  const depthVisited = new Set();
  const assignDepth = (layer, depth, stack = new Set()) => {
    if (!layer || stack.has(layer.id) || depthVisited.has(layer.id)) return;
    depthVisited.add(layer.id); depthById.set(layer.id, depth);
    const nextStack = new Set(stack); nextStack.add(layer.id);
    (children.get(layer.id) || []).forEach(child => assignDepth(child, depth + 1, nextStack));
  };
  roots.forEach(layer => assignDepth(layer, 0));
  layers.filter(layer => !depthVisited.has(layer.id)).forEach(layer => {
    roots.push(layer);
    assignDepth(layer, 0);
  });

  const depthWidths = [];
  layers.forEach(layer => {
    const depth = depthById.get(layer.id) || 0;
    depthWidths[depth] = Math.max(depthWidths[depth] || 0, dimensions.get(layer.id)?.w || 196);
  });
  const columnGap = 112;
  const columnX = [80];
  for (let depth = 1; depth < depthWidths.length; depth += 1) {
    columnX[depth] = columnX[depth - 1] + (depthWidths[depth - 1] || 196) + columnGap;
  }

  const siblingGap = 46;
  const forestGap = 72;
  const subtreeMemo = new Map();
  const subtreeHeight = (layer, stack = new Set()) => {
    if (!layer || stack.has(layer.id)) return 0;
    if (subtreeMemo.has(layer.id)) return subtreeMemo.get(layer.id);
    const nextStack = new Set(stack); nextStack.add(layer.id);
    const childHeights = (children.get(layer.id) || [])
      .filter(child => !nextStack.has(child.id))
      .map(child => subtreeHeight(child, nextStack));
    const childBlock = childHeights.length ? childHeights.reduce((sum, value) => sum + value, 0) + siblingGap * (childHeights.length - 1) : 0;
    const span = Math.max(dimensions.get(layer.id)?.h || 158, childBlock);
    subtreeMemo.set(layer.id, span);
    return span;
  };

  const result = {};
  const placed = new Set();
  const place = (layer, top, stack = new Set()) => {
    if (!layer || stack.has(layer.id) || placed.has(layer.id)) return 0;
    const span = subtreeHeight(layer, stack);
    const dim = dimensions.get(layer.id) || {w:196,h:158,body_mesh_id:''};
    const depth = depthById.get(layer.id) || 0;
    result[layer.id] = {
      x:columnX[depth] || 80,
      y:top + Math.max(0, (span - dim.h) / 2),
      w:dim.w,
      h:dim.h,
      body_mesh_id:dim.body_mesh_id,
    };
    placed.add(layer.id);
    const nextStack = new Set(stack); nextStack.add(layer.id);
    const childLayers = (children.get(layer.id) || []).filter(child => !nextStack.has(child.id) && !placed.has(child.id));
    const childHeights = childLayers.map(child => subtreeHeight(child, nextStack));
    const childBlock = childHeights.length ? childHeights.reduce((sum, value) => sum + value, 0) + siblingGap * (childHeights.length - 1) : 0;
    let childTop = top + Math.max(0, (span - childBlock) / 2);
    childLayers.forEach((child, index) => {
      place(child, childTop, nextStack);
      childTop += childHeights[index] + siblingGap;
    });
    return span;
  };

  let forestTop = 70;
  roots.forEach(layer => {
    if (placed.has(layer.id)) return;
    const span = place(layer, forestTop);
    forestTop += span + forestGap;
  });
  layers.filter(layer => !placed.has(layer.id)).forEach(layer => {
    const span = place(layer, forestTop);
    forestTop += span + forestGap;
  });
  return result;
}

function hierarchyDiagramFallbackLayoutValues() {
  const layers = state.project?.layers || [];
  const savedNodes = hierarchyDiagramUi().nodes || {};
  const columns = Math.max(1, Math.min(4, Math.ceil(Math.sqrt(Math.max(1, layers.length)))));
  return Object.fromEntries(layers.map((layer, index) => {
    const saved = savedNodes[layer.id] || {};
    const w = hierarchyDiagramClampNodeSize(Number(saved.w) || 196, 'w');
    const h = hierarchyDiagramClampNodeSize(Number(saved.h) || 158, 'h');
    return [layer.id, {
      x:80 + (index % columns) * 292,
      y:70 + Math.floor(index / columns) * 228,
      w,
      h,
      body_mesh_id:(layer.meshes || []).some(mesh => mesh.id === saved.body_mesh_id) ? saved.body_mesh_id : (layer.meshes?.[0]?.id || ''),
    }];
  }));
}

function hierarchyDiagramResolvedNodes() {
  const fallback = hierarchyDiagramFallbackLayoutValues();
  return Object.fromEntries((state.project?.layers || []).map(layer => [layer.id, hierarchyDiagramNodeDefaults(layer, fallback)]));
}

function hierarchyDiagramPersistAutoLayout() {
  const nodes = hierarchyDiagramAutoLayoutValues();
  uiSet('model.diagram.nodes', nodes, '框图建模：按节点实际尺寸与父子子树占用空间自动排布全部框图');
  renderLayers();
}

function hierarchyDiagramWorldPoint(clientX, clientY) {
  const viewport = $('#hierarchyDiagramViewport');
  if (!viewport) return {x:0, y:0};
  const rect = viewport.getBoundingClientRect();
  const view = hierarchyDiagramViewportState();
  return {
    x:(clientX - rect.left - view.pan_x) / view.zoom,
    y:(clientY - rect.top - view.pan_y) / view.zoom,
  };
}

function hierarchyDiagramViewportState() {
  const saved = hierarchyDiagramUi().viewport || {};
  return {
    pan_x:Number.isFinite(Number(saved.pan_x)) ? Number(saved.pan_x) : 0,
    pan_y:Number.isFinite(Number(saved.pan_y)) ? Number(saved.pan_y) : 0,
    zoom:Math.max(.35, Math.min(2.4, Number.isFinite(Number(saved.zoom)) ? Number(saved.zoom) : 1)),
  };
}

function hierarchyDiagramApplyViewport() {
  const viewport = $('#hierarchyDiagramViewport'), world = $('#hierarchyDiagramWorld');
  if (!viewport || !world || hierarchyViewMode() !== 'diagram') return;
  const view = hierarchyDiagramViewportState();
  world.style.transformOrigin = '0 0';
  world.style.transform = `translate(${view.pan_x}px, ${view.pan_y}px) scale(${view.zoom})`;
  viewport.style.setProperty('--diagram-grid-size', `${22 * view.zoom}px`);
  viewport.style.setProperty('--diagram-grid-x', `${view.pan_x}px`);
  viewport.style.setProperty('--diagram-grid-y', `${view.pan_y}px`);
  const zoomLabel = $('#hierarchyDiagramZoom');
  if (zoomLabel) zoomLabel.textContent = `${Math.round(view.zoom * 100)}%`;
}

function hierarchyDiagramSetViewport(next, semantic, opts = {}) {
  const current = hierarchyDiagramViewportState();
  const config = {
    pan_x:Number.isFinite(Number(next?.pan_x)) ? Number(next.pan_x) : current.pan_x,
    pan_y:Number.isFinite(Number(next?.pan_y)) ? Number(next.pan_y) : current.pan_y,
    zoom:Math.max(.35, Math.min(2.4, Number.isFinite(Number(next?.zoom)) ? Number(next.zoom) : current.zoom)),
  };
  uiSet('model.diagram.viewport', config, semantic, opts);
  hierarchyDiagramApplyViewport();
  return config;
}

function hierarchyDiagramPersistViewportSoon() {
  clearTimeout(state.hierarchyDiagramViewportCommitTimer);
  state.hierarchyDiagramViewportCommitTimer = setTimeout(() => {
    state.hierarchyDiagramViewportCommitTimer = null;
    hierarchyDiagramSetViewport(hierarchyDiagramViewportState(), '框图建模：保存画布缩放与平移视图');
  }, 180);
}

function hierarchyDiagramWorldSize(nodes = hierarchyDiagramResolvedNodes()) {
  const values = Object.values(nodes || {});
  return {
    width:Math.max(1100, ...values.map(node => node.x + node.w + 180)),
    height:Math.max(680, ...values.map(node => node.y + node.h + 180)),
  };
}

function hierarchyDiagramRenderEdgesOnly(nodes = hierarchyDiagramResolvedNodes()) {
  const size = hierarchyDiagramWorldSize(nodes);
  const world = $('#hierarchyDiagramWorld');
  if (world) { world.style.width = `${size.width}px`; world.style.height = `${size.height}px`; }
  renderHierarchyDiagramEdges(nodes, size.width, size.height);
}

function hierarchyDiagramSetNodeUi(layerId, config, semantic, opts = {}) {
  uiSet(`model.diagram.nodes.${layerId}`, config, semantic, opts);
}

function hierarchyDiagramSetEdgeUi(kind, edgeId, config, semantic, opts = {}) {
  const bucket = kind === 'closure' ? 'closure_edges' : 'tree_edges';
  uiSet(`model.diagram.${bucket}.${edgeId}`, config, semantic, opts);
}

function hierarchyDiagramCreateClosure(sourceId, targetId) {
  const source = state.project?.layers?.find(layer => layer.id === sourceId);
  const target = state.project?.layers?.find(layer => layer.id === targetId);
  if (!source || !target || source.id === target.id) return null;
  const existing = hierarchyDiagramMatchingClosure(source.id, target.id);
  if (existing) return existing;
  state.project.kinematic_closures ||= [];
  const closure = {
    id:uid('closure'),
    name:uniqueName('闭链', state.project.kinematic_closures.map(item => item.name || ''), true),
    enabled:true,
    kind:'point',
    endpoint_a:{layer_id:source.id, point_mm:[0,0,0]},
    endpoint_b:{layer_id:target.id, point_mm:[0,0,0]},
    solve_joint_ids:[],
    tolerance_mm:0.05,
    max_iterations:40,
    damping:0.0001,
    max_angle_step_deg:8,
    max_slide_step_mm:5,
  };
  state.project.kinematic_closures.push(closure);
  hierarchyDiagramSyncClosurePassiveJoints(closure);
  return closure;
}

function hierarchyDiagramDescendants(layerId) {
  const descendants = [];
  const queue = [layerId];
  const visited = new Set(queue);
  while (queue.length) {
    const parentId = queue.shift();
    (state.project?.layers || []).forEach(layer => {
      if (layer.parent_id !== parentId || visited.has(layer.id)) return;
      visited.add(layer.id); descendants.push(layer); queue.push(layer.id);
    });
  }
  return descendants;
}

function hierarchyDiagramMatchingClosure(parentId, childId) {
  return (state.project?.kinematic_closures || []).find(closure => {
    const a = closure.endpoint_a?.layer_id, b = closure.endpoint_b?.layer_id;
    return (a === parentId && b === childId) || (a === childId && b === parentId);
  }) || null;
}

function hierarchyDiagramLayerIsActive(layerId) {
  const layer = (state.project?.layers || []).find(item => item.id === layerId);
  return Boolean(layer) && layer.active !== false;
}

function hierarchyDiagramClosureLocked(closure) {
  if (!closure) return true;
  return !hierarchyDiagramLayerIsActive(closure.endpoint_a?.layer_id) || !hierarchyDiagramLayerIsActive(closure.endpoint_b?.layer_id);
}

function hierarchyDiagramEdgeLocked(edgeKind, edgeId) {
  if (edgeKind === 'closure') {
    const closure = (state.project?.kinematic_closures || []).find(item => item.id === edgeId);
    return hierarchyDiagramClosureLocked(closure);
  }
  const child = (state.project?.layers || []).find(item => item.id === edgeId);
  const parent = child ? (state.project?.layers || []).find(item => item.id === child.parent_id) : null;
  return !child || child.active === false || !parent || parent.active === false;
}

function removeLayerAtIndex(li, {diagramSelection = false} = {}) {
  const removed = state.project?.layers?.[li];
  if (!removed) return null;
  removeJointReferences((removed.joints || []).map(joint => joint.id));
  (state.project.layers || []).forEach(layer => { if (layer.parent_id === removed.id) layer.parent_id = removed.parent_id; });
  const removedClosureIds = new Set((state.project.kinematic_closures || [])
    .filter(closure => closure.endpoint_a?.layer_id === removed.id || closure.endpoint_b?.layer_id === removed.id)
    .map(closure => closure.id));
  state.project.kinematic_closures = (state.project.kinematic_closures || [])
    .filter(closure => !removedClosureIds.has(closure.id));
  state.project.layers.splice(li, 1);
  hierarchyDiagramSyncAllClosurePassiveJoints();
  state.hierarchyDiagramMultiSelection?.delete(removed.id);
  if (state.hierarchyDiagramInteraction?.kind === 'closure-joint-pick' && removedClosureIds.has(state.hierarchyDiagramInteraction.closureId)) {
    state.hierarchyDiagramInteraction = null;
  }
  if (diagramSelection || hierarchyViewMode() === 'diagram') {
    state.selectedLayerId = null;
    state.hierarchyDiagramSelection = null;
    state.hierarchyDiagramMultiSelection = new Set();
  } else {
    state.selectedLayerId = state.project.layers[0]?.id || null;
  }
  return removed;
}

function deleteHierarchyDiagramSelection() {
  if (hierarchyViewMode() !== 'diagram' || !state.project || !state.hierarchyDiagramSelection) return false;
  if (!canEditProject()) { toast('当前模型不可编辑，不能删除框图或连线', 'error'); return true; }
  const selection = state.hierarchyDiagramSelection;
  if (selection.type === 'node') {
    const li = state.project.layers.findIndex(layer => layer.id === selection.layerId);
    if (li < 0) return false;
    const removed = removeLayerAtIndex(li, {diagramSelection:true});
    if (!removed) return false;
    markDirty(); renderAll(); scheduleInteractionCommit(); toast(`已删除层级“${removed.name}”`);
    return true;
  }
  if (selection.type === 'tree_edge') {
    const child = state.project.layers.find(layer => layer.id === selection.childId);
    const parent = child ? state.project.layers.find(layer => layer.id === child.parent_id) : null;
    if (!child || !parent) return false;
    if (hierarchyDiagramEdgeLocked('tree', child.id)) { toast('未激活层级相关连线已锁定，不能删除父子连线', 'error'); return true; }
    child.parent_id = 'root';
    hierarchyDiagramSyncAllClosurePassiveJoints();
    state.hierarchyDiagramSelection = {type:'node', layerId:child.id};
    state.selectedLayerId = child.id;
    state.hierarchyDiagramMultiSelection = new Set();
    markDirty(); renderAll(); scheduleInteractionCommit(); toast(`已删除父子连线：${parent.name} → ${child.name}`);
    return true;
  }
  if (selection.type === 'closure_edge') {
    const ci = (state.project.kinematic_closures || []).findIndex(closure => closure.id === selection.closureId);
    if (ci < 0) return false;
    const closure = state.project.kinematic_closures[ci];
    if (hierarchyDiagramClosureLocked(closure)) { toast('未激活层级相关闭链已锁定，不能删除闭链连线', 'error'); return true; }
    state.project.kinematic_closures.splice(ci, 1);
    if (state.hierarchyDiagramInteraction?.kind === 'closure-joint-pick' && state.hierarchyDiagramInteraction.closureId === closure.id) state.hierarchyDiagramInteraction = null;
    state.hierarchyDiagramSelection = null;
    state.hierarchyDiagramMultiSelection = new Set();
    markDirty(); renderAll(); scheduleInteractionCommit(); toast(`已删除闭链连线“${closure.name || `闭链${ci + 1}`}”`);
    return true;
  }
  return false;
}

function hierarchyDiagramEndpointOptions(selectedId) {
  const layers = state.project?.layers || [];
  const active = layers.filter(layer => layer.active !== false);
  const selected = layers.find(layer => layer.id === selectedId);
  const rows = selected && selected.active === false ? [selected, ...active] : active;
  return [`<option value="">请选择</option>`, ...rows.map(layer => `<option value="${esc(layer.id)}" ${layer.id===selectedId?'selected':''} ${layer.active===false?'disabled':''}>${esc(layer.name)}${layer.active===false?'（未激活）':''}</option>`)].join('');
}

function hierarchyDiagramEdgePath(a, b, bend = {}) {
  const direction = side => ({left:{x:-1,y:0},right:{x:1,y:0},top:{x:0,y:-1},bottom:{x:0,y:1}}[side] || {x:1,y:0});
  const distance = Math.hypot(b.x - a.x, b.y - a.y);
  const handle = Math.max(34, Math.min(170, distance * .42));
  const startVector = direction(a.side), endVector = direction(b.side);
  // 4/3 makes the cubic midpoint move by exactly bend_x/bend_y while the endpoints remain fixed.
  const bx = (Number(bend.bend_x) || 0) * 4 / 3;
  const by = (Number(bend.bend_y) || 0) * 4 / 3;
  const c1 = {x:a.x + startVector.x * handle + bx, y:a.y + startVector.y * handle + by};
  const c2 = {x:b.x + endVector.x * handle + bx, y:b.y + endVector.y * handle + by};
  const cubicPoint = t => {
    const u = 1 - t;
    return {
      x:u*u*u*a.x + 3*u*u*t*c1.x + 3*u*t*t*c2.x + t*t*t*b.x,
      y:u*u*u*a.y + 3*u*u*t*c1.y + 3*u*t*t*c2.y + t*t*t*b.y,
    };
  };
  const midpoint = cubicPoint(.5), drivePoint = cubicPoint(.68);
  return {
    d:`M ${a.x.toFixed(1)} ${a.y.toFixed(1)} C ${c1.x.toFixed(1)} ${c1.y.toFixed(1)} ${c2.x.toFixed(1)} ${c2.y.toFixed(1)} ${b.x.toFixed(1)} ${b.y.toFixed(1)}`,
    mx:midpoint.x, my:midpoint.y, driveX:drivePoint.x, driveY:drivePoint.y,
  };
}

function hierarchyDiagramPortPoint(node, side) {
  if (side === 'left') return {x:node.x, y:node.y + node.h / 2, side};
  if (side === 'right') return {x:node.x + node.w, y:node.y + node.h / 2, side};
  if (side === 'top') return {x:node.x + node.w / 2, y:node.y, side};
  return {x:node.x + node.w / 2, y:node.y + node.h, side:'bottom'};
}

function hierarchyDiagramPreferredSide(node, point) {
  const cx = node.x + node.w / 2, cy = node.y + node.h / 2;
  const dx = point.x - cx, dy = point.y - cy;
  return Math.abs(dx) >= Math.abs(dy) ? (dx >= 0 ? 'right' : 'left') : (dy >= 0 ? 'bottom' : 'top');
}

function hierarchyDiagramEdgeEndpoints(aNode, bNode) {
  const ac = {x:aNode.x + aNode.w/2, y:aNode.y + aNode.h/2};
  const bc = {x:bNode.x + bNode.w/2, y:bNode.y + bNode.h/2};
  return {
    start:hierarchyDiagramPortPoint(aNode, hierarchyDiagramPreferredSide(aNode, bc)),
    end:hierarchyDiagramPortPoint(bNode, hierarchyDiagramPreferredSide(bNode, ac)),
  };
}

function hierarchyDiagramOppositeSide(side) {
  return ({left:'right',right:'left',top:'bottom',bottom:'top'})[side] || 'left';
}

const HIERARCHY_CLOSURE_COLORS = ['#19e65c','#1489ff','#8a36ff','#ff8a00','#00c853','#005cff','#bd25ff','#ffb000'];

function hierarchyDiagramClosureColor(index) {
  const n = Math.max(0, Number(index) || 0);
  if (n < HIERARCHY_CLOSURE_COLORS.length) return HIERARCHY_CLOSURE_COLORS[n];
  // Additional loops stay in the requested green / blue / purple / orange families; red is intentionally excluded.
  const families = [138, 211, 274, 31];
  const hue = (families[n % families.length] + Math.floor(n / families.length) * 9) % 360;
  return `hsl(${hue.toFixed(1)} 96% 52%)`;
}

function hierarchyDiagramTreePathEdgeIds(aId, bId) {
  const byId = new Map((state.project?.layers || []).map(layer => [layer.id, layer]));
  if (!byId.has(aId) || !byId.has(bId) || aId === bId) return [];
  const ancestors = new Set(['root']);
  let cursor = aId, guard = 0;
  while (byId.has(cursor) && guard++ < byId.size + 2) {
    ancestors.add(cursor);
    cursor = byId.get(cursor).parent_id;
  }
  const fromB = [];
  cursor = bId; guard = 0;
  while (!ancestors.has(cursor) && byId.has(cursor) && guard++ < byId.size + 2) {
    fromB.push(cursor); // tree edge is keyed by its child layer id.
    cursor = byId.get(cursor).parent_id;
  }
  const lca = cursor;
  if (!ancestors.has(lca)) return [];
  const fromA = [];
  cursor = aId; guard = 0;
  while (cursor !== lca && byId.has(cursor) && guard++ < byId.size + 2) {
    fromA.push(cursor);
    cursor = byId.get(cursor).parent_id;
  }
  return [...fromA, ...fromB].filter(childId => byId.has(byId.get(childId)?.parent_id));
}

function hierarchyDiagramClosureCycles() {
  return (state.project?.kinematic_closures || []).map((closure, index) => ({
    closure,
    color:hierarchyDiagramClosureColor(index),
    treeEdgeIds:new Set(hierarchyDiagramTreePathEdgeIds(closure.endpoint_a?.layer_id, closure.endpoint_b?.layer_id)),
  }));
}

function hierarchyDiagramEdgeDrives(layer) {
  const jointIds = new Set((layer?.joints || []).map(joint => joint.id));
  return (state.project?.drives || []).filter(drive => jointIds.has(drive.joint_id));
}

function hierarchyDiagramEdgePassiveJointIds(childId, closure = null) {
  const child = (state.project?.layers || []).find(layer => layer.id === childId);
  if (!child || child.active === false) return [];
  if (closure) {
    const path = new Set(hierarchyDiagramTreePathEdgeIds(closure.endpoint_a?.layer_id, closure.endpoint_b?.layer_id));
    if (!path.has(childId)) return [];
  }
  // V2.10.5 treats the diagram line as the driven/passive unit. Once any drive
  // is bound to a joint on this child edge, the whole line is the driving side
  // of the loop and none of its joints are auto-selected as passive.
  if (hierarchyDiagramEdgeDrives(child).length) return [];
  return (child.joints || []).filter(joint => joint.type !== 'crank').map(joint => joint.id);
}

function hierarchyDiagramClosureAutoPassiveJointIds(closure) {
  if (!closure) return [];
  return hierarchyDiagramTreePathEdgeIds(closure.endpoint_a?.layer_id, closure.endpoint_b?.layer_id)
    .flatMap(childId => hierarchyDiagramEdgePassiveJointIds(childId, closure));
}

function hierarchyDiagramSyncClosurePassiveJoints(closure) {
  if (!closure) return [];
  closure.solve_joint_ids = [...new Set(hierarchyDiagramClosureAutoPassiveJointIds(closure))];
  return closure.solve_joint_ids;
}

function hierarchyDiagramSyncAllClosurePassiveJoints() {
  (state.project?.kinematic_closures || []).forEach(hierarchyDiagramSyncClosurePassiveJoints);
}

function hierarchyDiagramJointSymbolMarkup(type) {
  if (type === 'crank') return '<span aria-hidden="true">⟳</span>';
  // Translation explicitly uses Figure 2; rotation retains its dedicated asset.
  return `<img src="/assets/diagram_joint_${type === 'translation' ? 'translation' : 'rotation'}.png" alt="">`;
}

function hierarchyDiagramJointIconMarkup(layer, path, inactive = false) {
  const joint = (layer?.joints || [])[0];
  if (!joint) return '';
  const type = joint.type === 'rotation' ? 'rotation' : joint.type === 'translation' ? 'translation' : 'crank';
  const typeLabel = type === 'rotation' ? '旋转副' : type === 'translation' ? '滑动副' : '曲柄旋转特殊副';
  return `<button type="button" class="hierarchy-edge-joint-icon ${type} ${inactive?'inactive':''}" data-action="diagram-select-tree-edge" data-child-id="${esc(layer.id)}" style="left:${path.mx}px;top:${path.my}px" title="${esc(joint.name || typeLabel)} · ${typeLabel}">${hierarchyDiagramJointSymbolMarkup(type)}</button>`;
}

function hierarchyDiagramDriveIconMarkup(layer, path, inactive = false) {
  const drives = hierarchyDiagramEdgeDrives(layer);
  if (!drives.length) return '';
  const allDisabled = drives.every(drive => drive.enabled === false);
  const title = drives.map(drive => drive.name || '驱动').join('、');
  // Figure 1 is rendered at exactly 2x the 18px joint marker and follows the same Bezier edge.
  return `<span class="hierarchy-edge-drive-icon ${(inactive || allDisabled)?'inactive':''}" style="left:${path.driveX}px;top:${path.driveY}px" title="驱动：${esc(title)}"><img src="/assets/diagram_joint_drive.png" alt="驱动"></span>`;
}


function hierarchyDiagramJointLabel(layer) {
  const joint = (layer?.joints || [])[0];
  if (!joint) return '父子层级';
  return joint.type === 'rotation' ? '旋转副' : joint.type === 'translation' ? '滑动副' : '曲柄副';
}

function renderHierarchyModeControls() {
  const mode = hierarchyViewMode();
  const studio = $('.model-studio');
  studio?.classList.toggle('diagram-mode', mode === 'diagram');
  $('#hierarchyDiagramPanel')?.classList.toggle('hidden', mode !== 'diagram');
  const label = $('#hierarchyViewLabel'); if (label) label.textContent = mode === 'diagram' ? '框图建模' : '层级建模';
  const toggle = $('#hierarchyViewToggle'); if (toggle) toggle.classList.toggle('active', mode === 'diagram');
}

function renderHierarchyDiagramEdges(nodes, worldWidth, worldHeight) {
  const svg = $('#hierarchyDiagramEdges'), labels = $('#hierarchyDiagramEdgeLabels');
  if (!svg || !labels) return;
  svg.setAttribute('viewBox', `0 0 ${worldWidth} ${worldHeight}`);
  svg.setAttribute('width', worldWidth); svg.setAttribute('height', worldHeight);
  const treeEdges = hierarchyDiagramUi().tree_edges || {};
  const closureEdges = hierarchyDiagramUi().closure_edges || {};
  const byId = new Map((state.project?.layers || []).map(layer => [layer.id, layer]));
  const selected = state.hierarchyDiagramSelection || null;
  const cycles = hierarchyDiagramClosureCycles();
  const pickClosureId = state.hierarchyDiagramInteraction?.kind === 'closure-joint-pick' ? state.hierarchyDiagramInteraction.closureId : '';
  const pickClosure = (state.project.kinematic_closures || []).find(closure => closure.id === pickClosureId) || null;
  const pickPath = new Set(pickClosure ? hierarchyDiagramTreePathEdgeIds(pickClosure.endpoint_a?.layer_id, pickClosure.endpoint_b?.layer_id) : []);
  const pickedPassive = new Set(pickClosure?.solve_joint_ids || []);
  const edgeSvg = [];
  const labelHtml = [];
  edgeSvg.push(`<defs><marker id="hierarchyArrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="context-stroke"></path></marker><marker id="hierarchyClosureArrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="context-stroke"></path></marker></defs>`);

  (state.project?.layers || []).forEach(child => {
    const parent = byId.get(child.parent_id); if (!parent) return;
    const pn = nodes[parent.id], cn = nodes[child.id]; if (!pn || !cn) return;
    const {start, end} = hierarchyDiagramEdgeEndpoints(pn, cn);
    const config = treeEdges[child.id] || {}, path = hierarchyDiagramEdgePath(start, end, config);
    const cycle = cycles.find(item => item.closure.enabled !== false && item.treeEdgeIds.has(child.id));
    const inactive = parent.active === false || child.active === false;
    const active = selected?.type === 'tree_edge' && selected.childId === child.id;
    const passiveIds = pickClosure && pickPath.has(child.id) ? hierarchyDiagramEdgePassiveJointIds(child.id, pickClosure) : [];
    const passivePick = Boolean(pickClosure && pickPath.has(child.id) && !inactive);
    const passiveSelected = passiveIds.length > 0 && passiveIds.every(id => pickedPassive.has(id));
    const style = cycle ? ` style="--closure-color:${cycle.color}"` : '';
    // Closure path tree edges inherit the loop color but stay solid. The explicit
    // site closure is the only dashed edge; manual passive correction selects lines.
    edgeSvg.push(`<path class="hierarchy-edge-hit ${inactive?'locked':''} ${passivePick?'passive-pick-hit':''}" d="${path.d}" data-action="diagram-select-tree-edge" data-child-id="${esc(child.id)}" data-diagram-edge-bend="tree:${esc(child.id)}"></path><path class="hierarchy-edge tree-edge ${cycle?'loop-edge':''} ${inactive?'inactive':''} ${active?'selected':''} ${passivePick?'passive-pick':''} ${passiveSelected?'passive-selected':''}" d="${path.d}" marker-end="url(#hierarchyArrow)"${style}></path>`);
    labelHtml.push(hierarchyDiagramJointIconMarkup(child, path, inactive));
    labelHtml.push(hierarchyDiagramDriveIconMarkup(child, path, inactive));
  });

  (state.project?.kinematic_closures || []).forEach((closure, index) => {
    const aLayer = byId.get(closure.endpoint_a?.layer_id), bLayer = byId.get(closure.endpoint_b?.layer_id); if (!aLayer || !bLayer || aLayer.id === bLayer.id) return;
    // Render the closure/site edge independently even for adjacent layers so the
    // dashed site line never changes a normal parent-child edge into a dashed edge.
    const an = nodes[aLayer.id], bn = nodes[bLayer.id]; if (!an || !bn) return;
    const {start, end} = hierarchyDiagramEdgeEndpoints(an, bn);
    const config = closureEdges[closure.id] || {bend_y:-36 - (index % 3) * 18};
    const path = hierarchyDiagramEdgePath(start, end, config);
    const inactive = closure.enabled === false || aLayer.active === false || bLayer.active === false;
    const active = selected?.type === 'closure_edge' && selected.closureId === closure.id;
    const cycle = cycles[index];
    edgeSvg.push(`<path class="hierarchy-edge-hit ${inactive?'locked':''}" d="${path.d}" data-action="diagram-select-closure-edge" data-closure-id="${esc(closure.id)}" data-diagram-edge-bend="closure:${esc(closure.id)}"></path><path class="hierarchy-edge closure-edge loop-edge loop-site-edge ${inactive?'inactive':''} ${active?'selected':''}" d="${path.d}" marker-end="url(#hierarchyClosureArrow)" style="--closure-color:${cycle?.color || hierarchyDiagramClosureColor(index)}"></path>`);
  });

  const interaction = state.hierarchyDiagramInteraction;
  if (interaction?.kind === 'connect' && nodes[interaction.sourceId] && Number.isFinite(interaction.x) && Number.isFinite(interaction.y)) {
    const source = nodes[interaction.sourceId];
    const sourceSide = interaction.sourceSide || hierarchyDiagramPreferredSide(source, {x:interaction.x,y:interaction.y});
    const start = hierarchyDiagramPortPoint(source, sourceSide);
    const end = {x:interaction.x, y:interaction.y, side:hierarchyDiagramOppositeSide(sourceSide)};
    const path = hierarchyDiagramEdgePath(start, end, {bend_x:0,bend_y:0});
    edgeSvg.push(`<path class="hierarchy-edge temporary ${interaction.linkKind==='closure'?'closure-edge':''}" d="${path.d}" marker-end="url(#${interaction.linkKind==='closure'?'hierarchyClosureArrow':'hierarchyArrow'})"></path>`);
  }
  svg.innerHTML = edgeSvg.join(''); labels.innerHTML = labelHtml.join('');
}

function renderHierarchyDiagram() {
  const panel = $('#hierarchyDiagramPanel'), world = $('#hierarchyDiagramWorld'), nodesRoot = $('#hierarchyDiagramNodes');
  if (!panel || !world || !nodesRoot || hierarchyViewMode() !== 'diagram') return;
  const nodes = hierarchyDiagramResolvedNodes();
  const size = hierarchyDiagramWorldSize(nodes);
  world.style.width = `${size.width}px`; world.style.height = `${size.height}px`;
  const selected = state.hierarchyDiagramSelection || null;
  nodesRoot.innerHTML = (state.project.layers || []).map(layer => {
    const node=nodes[layer.id], meshes=layer.meshes || [], body=meshes.find(mesh=>mesh.id===node.body_mesh_id) || meshes[0] || null;
    const bodyFile=body?.filename || '', file=state.meshFiles.find(item=>item.filename===bodyFile);
    const fingerprint=bodyFile ? `${file ? meshThumbnailFingerprint(file) : `${state.project?.mesh_root||''}|${bodyFile}|0|0`}|front` : '';
    const isSelected = selected?.type === 'node' && selected.layerId === layer.id || state.selectedLayerId === layer.id && !selected;
    const isMultiSelected = state.hierarchyDiagramMultiSelection?.has(layer.id);
    const portTitle = layer.active===false ? '未激活层级已锁定连线' : `拖动任一接口到目标框图建立${state.hierarchyDiagramLinkKind==='closure'?'闭链':'父子'}连线`;
    const ports = ['left','right','top','bottom'].map(side => `<button class="hierarchy-node-port side-${side}" type="button" data-diagram-connect-source="${esc(layer.id)}" data-diagram-connect-target="${esc(layer.id)}" data-diagram-port-side="${side}" title="${portTitle}" ${layer.active===false?'disabled':''}></button>`).join('');
    return `<article class="hierarchy-diagram-node ${isSelected?'selected':''} ${isMultiSelected?'multi-selected':''} ${layer.active===false?'inactive':''}" data-diagram-layer-node="${esc(layer.id)}" style="left:${node.x}px;top:${node.y}px;width:${node.w}px;height:${node.h}px;--layer-color:${rgbaToHex(layer.color)}">
      <div class="hierarchy-node-title" data-diagram-node-drag-handle="${esc(layer.id)}"><span data-diagram-node-title="${esc(layer.id)}" title="双击重命名层级">${esc(layer.name)}</span></div>
      <div class="hierarchy-node-preview" data-diagram-node-drag-handle="${esc(layer.id)}">${bodyFile?`<canvas width="224" height="152" data-mesh-thumbnail="${esc(bodyFile)}" data-thumbnail-key="${esc(fingerprint)}" data-thumbnail-view="front" aria-label="${esc(layer.name)} 本体数模正视图"></canvas>`:'<div class="hierarchy-node-empty-preview">拖入数模以建立层级本体</div>'}</div>
      ${ports}
      <i class="hierarchy-node-resize axis-x" data-diagram-node-resize="${esc(layer.id)}" data-diagram-node-resize-axis="x" title="横向拖动调整缩略图宽度"></i>
      <i class="hierarchy-node-resize axis-y" data-diagram-node-resize="${esc(layer.id)}" data-diagram-node-resize-axis="y" title="纵向拖动调整缩略图高度"></i>
      <i class="hierarchy-node-resize axis-xy" data-diagram-node-resize="${esc(layer.id)}" data-diagram-node-resize-axis="xy" title="任意比例调整缩略图宽高"></i>
    </article>`;
  }).join('') || '<div class="hierarchy-diagram-empty">从右侧数模库拖入画布即可建立第一个层级框图</div>';
  renderHierarchyDiagramEdges(nodes, size.width, size.height);
  hierarchyDiagramApplyViewport();
  hierarchyDiagramApplyLayout();
  $$('[data-thumbnail-view="front"]', nodesRoot).forEach(canvas => ensureMeshThumbnail(canvas));
  $$('[data-action="diagram-link-kind"]', panel).forEach(button => button.classList.toggle('active', button.dataset.kind === state.hierarchyDiagramLinkKind));
}

function byLayerName(layerId) {
  return state.project?.layers?.find(layer => layer.id === layerId)?.name || layerId || 'root';
}

function renderDiagramClosureDetails(closure) {
  const index = (state.project.kinematic_closures || []).findIndex(item => item.id === closure.id);
  if (index < 0) return false;
  const options = selectedId => hierarchyDiagramEndpointOptions(selectedId);
  const pickActive = state.hierarchyDiagramInteraction?.kind === 'closure-joint-pick' && state.hierarchyDiagramInteraction.closureId === closure.id;
  const color = hierarchyDiagramClosureCycles()[index]?.color || hierarchyDiagramClosureColor(index);
  const root = $('#layerDetails');
  delete root.dataset.diagramMeshDropTarget;
  root.className = 'diagram-property-root diagram-compact-properties diagram-edge-properties';
  root.innerHTML = `<div class="diagram-property-head"><span class="diagram-loop-swatch" style="--closure-color:${color}"></span><b>${esc(closure.name || `闭链${index+1}`)}</b><small>${esc(byLayerName(closure.endpoint_a?.layer_id))} ⇢ ${esc(byLayerName(closure.endpoint_b?.layer_id))}</small><label class="inline-check"><input type="checkbox" data-bind="kinematic_closures.${index}.enabled" ${closure.enabled!==false?'checked':''}>激活</label><button class="compact-delete" data-action="remove-closure" data-closure="${index}" title="删除闭链">×</button></div>
    <div class="diagram-closure-compact-grid">
      <label>名称<input data-bind="kinematic_closures.${index}.name" value="${esc(closure.name || `闭链${index+1}`)}"></label>
      <label>端点 A<select data-bind="kinematic_closures.${index}.endpoint_a.layer_id">${options(closure.endpoint_a?.layer_id||'')}</select></label>
      <label>端点 B<select data-bind="kinematic_closures.${index}.endpoint_b.layer_id">${options(closure.endpoint_b?.layer_id||'')}</select></label>
      <label>闭链坐标<input data-closure-point="${index}:shared" value="${esc(closurePointText(closure.endpoint_b?.point_mm))}" title="单位 mm；修改后同时写入闭链两端数模的 site 坐标，两个 site 保持一致"></label>
      <div class="diagram-closure-actions"><button type="button" class="button tiny ${pickActive?'primary':'ghost'}" data-action="diagram-pick-closure-joints" data-closure-id="${esc(closure.id)}">${pickActive?'完成线段修正':'线段修正从动副'}</button><button type="button" class="button tiny ghost" data-action="adaptive-closure-joints" data-closure="${index}">重新自动识别</button><small title="${esc(closureSelectedJointText(closure))}">自动从动副：${esc(closureSelectedJointText(closure))}</small></div>
    </div>`;
  return true;
}

function renderLayers() {
  renderHierarchyModeControls();
  renderLayerTree();
  renderLayerDetails();
  renderMeshLibrary();
  renderHierarchyDiagram();
}

function renderLayerTree() {
  const children = new Map();
  state.project.layers.forEach(layer => {
    const parent = state.project.layers.some(item => item.id === layer.parent_id) ? layer.parent_id : 'root';
    if (!children.has(parent)) children.set(parent, []);
    children.get(parent).push(layer);
  });
  const byId = new Map(state.project.layers.map(layer => [layer.id, layer]));
  $('#layerTreeTabs').innerHTML = `<button type="button" class="button tiny ghost layer-tree-adaptive-all" data-action="adaptive-all-project-meshes" title="对当前模型全部层级的数模执行同族自适应">全部数模自适应</button>`;
  const depthOf = layer => { let depth=0,current=layer,visited=new Set(); while(current&&current.parent_id!=='root'&&!visited.has(current.id)){visited.add(current.id);current=byId.get(current.parent_id);depth+=1;} return depth; };
  const treeWidth = Math.min(420, Math.max(180, ...state.project.layers.map(layer => 88 + depthOf(layer) * 14 + [...String(layer.name || '')].length * 10)));
  $('.model-studio')?.style.setProperty('--layer-tree-width', `${treeWidth}px`);
  const closureSuffixes = new Map();
  (state.project.kinematic_closures || []).forEach(closure => {
    [closure.endpoint_a?.layer_id, closure.endpoint_b?.layer_id].filter(Boolean).forEach(layerId => {
      if (!closureSuffixes.has(layerId)) closureSuffixes.set(layerId, new Set());
      closureSuffixes.get(layerId).add(closure.name || '闭链');
    });
  });
  const branch = (parentId, visited = new Set()) => (children.get(parentId) || []).map(layer => {
    if (visited.has(layer.id)) return '';
    const nextVisited = new Set(visited); nextVisited.add(layer.id);
    const nested = branch(layer.id, nextVisited);
    const closureSuffix = [...(closureSuffixes.get(layer.id) || [])].map(name => `——>${name}`).join(' ');
    return `<div><button class="tree-item ${layer.id === state.selectedLayerId ? 'active' : ''} ${layer.active ? '' : 'disabled'}" data-action="select-layer" data-layer-id="${esc(layer.id)}">${nested ? '▾' : '•'} <i class="tree-color" style="background:${rgbaToHex(layer.color)}"></i>${esc(layer.name)}${closureSuffix ? ` <span class="closure-tree-suffix">${esc(closureSuffix)}</span>` : ''} <small>${layer.meshes.length}/${layer.joints.length}</small></button>${nested ? `<div class="tree-children">${nested}</div>` : ''}</div>`;
  }).join('');
  $('#layerTree').innerHTML = branch('root') || '<div class="empty-inline">暂无层级</div>';
  document.querySelector('.tree-root')?.classList.toggle('active', state.selectedLayerId == null);
}

function meshOptions(selected) {
  const names = state.meshFiles.map(item => item.filename);
  if (selected && !names.some(name => name.toLowerCase() === selected.toLowerCase())) names.unshift(selected);
  return names.map(name => `<option value="${esc(name)}" ${name === selected ? 'selected' : ''}>${esc(name)}</option>`).join('');
}

async function refreshServerScenes() {
  const select=document.getElementById('serverSceneSelect'); if(!select||!state.project)return;
  const payload=await api('/api/scenes');
  const selected=String(state.project.template_scene||'').split(/[\\/]/).pop();
  select.innerHTML=`<option value="">内置默认场景</option>${(payload.scenes||[]).map(item=>`<option value="${esc(item.name)}" ${item.name===selected?'selected':''}>${esc(item.name)}</option>`).join('')}`;
  select.disabled=!canEditProject();
  document.getElementById('uploadSceneButton').disabled=!canEditProject();
}

async function selectServerScene(name) {
  if(!state.project)return;
  const updated=await api(`/api/projects/${state.project.id}/scene`,{method:'PUT',body:JSON.stringify({scene:name||''})});
  state.project=updated;updateProjectSummary(updated);markArchiveDirty();
  toast(name?`已选择服务端场景：${name}`:'已恢复内置默认场景');
}

async function uploadServerScene(file) {
  if(!file)return;
  const form=new FormData();form.append('file',file,file.name);
  return withBlockingLoading({title:'正在上传场景', detail:'正在上传并绑定 MuJoCo 场景 XML，请等待。'}, async () => {
    const uploaded=await api('/api/scenes/upload',{method:'POST',body:form,timeout:30000});
    await refreshServerScenes();
    document.getElementById('serverSceneSelect').value=uploaded.name;
    await selectServerScene(uploaded.name);
  });
}

function closurePointText(point) { const p=Array.isArray(point)?point:[0,0,0]; return `Point(${p.map(v=>Number(v)||0).join(', ')})`; }
function parseClosurePoint(text) { const normalized=String(text||'').replaceAll('（','(').replaceAll('）',')').replaceAll('，',',').replace(/^\s*Point\s*/i,'').replace(/[()]/g,' '); const values=normalized.split(/[\s,]+/).filter(Boolean).map(Number); return values.length===3&&values.every(Number.isFinite)?values:null; }
function setClosurePointMm(closure, side, point) {
  if (!closure || !Array.isArray(point) || point.length !== 3) return false;
  const normalized = point.map(Number);
  if (!normalized.every(Number.isFinite)) return false;
  if (side === 'shared') {
    closure.endpoint_a.point_mm = [...normalized];
    closure.endpoint_b.point_mm = [...normalized];
    return true;
  }
  (side === 'a' ? closure.endpoint_a : closure.endpoint_b).point_mm = [...normalized];
  return true;
}

function closureJointRows() {
  return state.project.layers.filter(item => item.active!==false).flatMap(
    item => (item.joints || []).filter(joint => joint.type !== 'crank').map(joint => ({layer:item,joint}))
  );
}

function closureSelectedJointText(closure) {
  const selected = new Set(closure.solve_joint_ids || []);
  const labels = closureJointRows().filter(({joint}) => selected.has(joint.id)).map(({layer,joint}) => `${layer.name} / ${joint.name}`);
  return labels.length ? labels.join('；') : '未选择从动运动副';
}

function closureJointTreeMarkup(closure, closureIndex) {
  const selected = new Set(closure.solve_joint_ids || []);
  const children = new Map();
  state.project.layers.filter(layer => layer.active !== false).forEach(layer => {
    const parent = state.project.layers.some(item => item.id === layer.parent_id && item.active !== false) ? layer.parent_id : 'root';
    if (!children.has(parent)) children.set(parent, []);
    children.get(parent).push(layer);
  });
  const branch = (parentId, visited = new Set()) => (children.get(parentId) || []).map(layer => {
    if (visited.has(layer.id)) return '';
    const nextVisited = new Set(visited); nextVisited.add(layer.id);
    const jointRows = (layer.joints || []).filter(joint => joint.type !== 'crank').map(joint => `
      <label class="closure-joint-option ${selected.has(joint.id) ? 'selected' : ''}">
        <input type="checkbox" data-closure-joint-option="${closureIndex}" data-joint-id="${esc(joint.id)}" ${selected.has(joint.id) ? 'checked' : ''}>
        <span><b>${esc(joint.name)}</b><small>${esc(joint.type === 'rotation' ? '旋转副' : '滑动副')}</small></span>
      </label>`).join('');
    const nested = branch(layer.id, nextVisited);
    return `<div class="closure-layer-node"><div class="closure-layer-title">${nested ? '▾' : '•'} ${esc(layer.name)}</div>${jointRows ? `<div class="closure-layer-joints">${jointRows}</div>` : '<div class="closure-layer-empty">无可选运动副</div>'}${nested ? `<div class="closure-layer-children">${nested}</div>` : ''}</div>`;
  }).join('');
  return branch('root') || '<div class="empty-state">当前没有可选运动副</div>';
}

function renderClosureSettings() {
  const closures = state.project.kinematic_closures || [];
  const endpointOptions = selectedId => hierarchyDiagramEndpointOptions(selectedId);
  return closures.map((closure,ci)=>{
    const expanded = state.expandedClosureId === closure.id;
    return `<div class="closure-card">
      <div class="closure-row closure-row-head"><label>名称<input data-bind="kinematic_closures.${ci}.name" value="${esc(closure.name||`闭链${ci+1}`)}"></label><label class="inline-check"><input type="checkbox" data-bind="kinematic_closures.${ci}.enabled" ${closure.enabled!==false?'checked':''}>启用</label><button class="compact-delete" data-action="remove-closure" data-closure="${ci}">×</button></div>
      <div class="closure-row closure-joint-picker-row"><button type="button" class="button tiny ghost closure-joint-expand" data-action="toggle-closure-joints" data-closure-id="${esc(closure.id)}">查看从动运动副</button><button type="button" class="button tiny ghost" data-action="adaptive-closure-joints" data-closure="${ci}">重新自动识别</button></div>
      <div class="closure-selected-summary" title="${esc(closureSelectedJointText(closure))}"><b>已选：</b>${esc(closureSelectedJointText(closure))}</div>
      <div class="closure-row closure-endpoints"><label>端点 A 层级<select data-bind="kinematic_closures.${ci}.endpoint_a.layer_id">${endpointOptions(closure.endpoint_a?.layer_id||'')}</select></label><label>端点 A<input data-closure-point="${ci}:a" value="${esc(closurePointText(closure.endpoint_a?.point_mm))}"></label><label>端点 B 层级<select data-bind="kinematic_closures.${ci}.endpoint_b.layer_id">${endpointOptions(closure.endpoint_b?.layer_id||'')}</select></label><label>端点 B<input data-closure-point="${ci}:b" value="${esc(closurePointText(closure.endpoint_b?.point_mm))}"></label></div>
      <details class="closure-advanced"><summary>高级参数</summary><div class="closure-advanced-grid"><label>容差 mm<input type="number" step="0.01" data-type="number" data-bind="kinematic_closures.${ci}.tolerance_mm" value="${closure.tolerance_mm??.05}"></label><label>最大迭代<input type="number" step="1" data-type="number" data-bind="kinematic_closures.${ci}.max_iterations" value="${closure.max_iterations??40}"></label><label>阻尼<input type="number" step="0.0001" data-type="number" data-bind="kinematic_closures.${ci}.damping" value="${closure.damping??.0001}"></label></div></details>
      ${expanded ? `<div class="closure-joint-overlay"><div class="closure-joint-dialog"><header><div><strong>${esc(closure.name || `闭链${ci+1}`)} · 从动运动副</strong><small>按层级树多选；勾选即有反馈，关闭后保留选择结果</small></div><button class="compact-delete" data-action="toggle-closure-joints" data-closure-id="${esc(closure.id)}">×</button></header><div class="closure-joint-tree"><div class="closure-layer-title root">▾ root</div>${closureJointTreeMarkup(closure,ci)}</div><footer><span>${(closure.solve_joint_ids||[]).length} 个已选</span><button class="button tiny primary" data-action="toggle-closure-joints" data-closure-id="${esc(closure.id)}">完成</button></footer></div></div>` : ''}
    </div>`;
  }).join('');
}

function renderRootDetails() {
  const root = $('#layerDetails');
  delete root.dataset.diagramMeshDropTarget;
  const closureMarkup = renderClosureSettings();
  root.classList.remove('inactive-layer');
  root.innerHTML = `<div class="property-header"><div><p class="eyebrow">ROOT PROPERTIES</p><h2>root</h2></div></div><div class="property-section closure-property-section"><div class="property-section-title"><span>${state.project.solver_mode==='dynamic'?'动力学闭链':'运动学闭链'}</span><button class="button tiny ghost" data-action="add-closure">＋ 添加点闭链</button></div>${closureMarkup||'<div class="empty-inline">可添加端点 A/B 点约束；运动学模式用 DLS，动力学模式转为 MuJoCo equality connect。</div>'}</div>`;
}

function adaptiveClosureJointIds(closure) {
  return hierarchyDiagramClosureAutoPassiveJointIds(closure);
}

function renderDiagramEmptyDetails() {
  const root = $('#layerDetails');
  delete root.dataset.diagramMeshDropTarget;
  root.className = 'diagram-property-root diagram-property-empty';
  root.innerHTML = '';
}

function renderDiagramNodeDetails(layer, li) {
  const root = $('#layerDetails');
  const meshes = layer.meshes || [];
  const node = hierarchyDiagramNodeDefaults(layer, hierarchyDiagramFallbackLayoutValues());
  const body = meshes.find(mesh => mesh.id === node.body_mesh_id) || meshes[0] || null;
  const locked = layer.active === false;
  root.dataset.diagramMeshDropTarget = String(li);
  root.className = `diagram-property-root diagram-compact-properties ${locked?'inactive-layer':''}`;
  const meshPickerBody = `<label>本体缩略图<select data-diagram-body-mesh="${esc(layer.id)}" ${meshes.length&&!locked?'':'disabled'}>${meshes.length?meshes.map(mesh=>`<option value="${esc(mesh.id)}" ${mesh.id===(body?.id||'')?'selected':''}>${esc(mesh.filename.split('/').at(-1))}</option>`).join(''):'<option value="">无数模</option>'}</select></label><div class="diagram-mesh-chip-list">${meshes.length?meshes.map(mesh=>`<span title="${esc(mesh.filename)}">${esc(mesh.filename.split('/').at(-1))}</span>`).join(''):'<i>把右侧数模拖到这里，可给当前层级继续增加数模</i>'}</div><small>默认第一个数模为本体；本体选择只改变框图缩略图。拖入此区域会复用当前层级 mesh 列表，不新建层级。</small>`;
  const meshPicker = meshes.length > 1
    ? `<div class="diagram-body-mesh-picker diagram-body-mesh-picker-static"><div class="diagram-body-mesh-title">数模 / 本体 <b>${esc(body?.filename?.split('/').at(-1) || '无数模')}</b><em>${meshes.length} 个</em></div>${meshPickerBody}</div>`
    : `<details class="diagram-body-mesh-picker"><summary>数模 / 本体 <b>${esc(body?.filename?.split('/').at(-1) || '无数模')}</b><em>${meshes.length} 个</em></summary>${meshPickerBody}</details>`;
  root.innerHTML = `<div class="diagram-node-property-actions"><strong>层级属性 · ${esc(layer.name)}</strong><button type="button" class="button tiny primary" data-action="add-child-layer" data-layer="${li}" ${locked?'disabled title="未激活层级不能创建子级"':''}>＋ 添加子层级</button></div><div class="diagram-node-property-row">
    <label class="diagram-node-name-field"><span>名称</span><input data-bind="layers.${li}.name" data-param-path="layers.${li}.name" value="${esc(layer.name)}" ${locked?'disabled':''}></label>
    <label class="color-field diagram-node-color-field"><span>层级颜色</span><input type="color" data-color-bind="layers.${li}.color" data-param-path="layers.${li}.color" value="${rgbaToHex(layer.color)}" ${locked?'disabled':''}><code>${esc(layer.color)}</code></label>
    <label class="inline-check diagram-node-active-field"><input type="checkbox" data-bind="layers.${li}.active" data-param-path="layers.${li}.active" ${layer.active?'checked':''}>激活</label>
    ${meshPicker}
  </div>`;
}

function renderDiagramTreeEdgeDetails(layer, li) {
  const root = $('#layerDetails');
  const parent = state.project.layers.find(item => item.id === layer.parent_id);
  if (!parent) { renderDiagramEmptyDetails(); return; }
  const closure = hierarchyDiagramMatchingClosure(parent.id, layer.id);
  const locked = parent.active === false || layer.active === false;
  delete root.dataset.diagramMeshDropTarget;
  root.className = `diagram-property-root diagram-compact-properties diagram-edge-properties ${locked?'inactive-layer':''}`;
  const joints = (layer.joints || []).map((joint, ji) => `<div class="diagram-joint-row ${joint.type==='crank'?'crank':''}">
    <span class="diagram-joint-type-icon ${joint.type}" title="${esc(hierarchyDiagramJointLabel({joints:[joint]}))}">${hierarchyDiagramJointSymbolMarkup(joint.type)}</span>
    <label>名称<input data-bind="layers.${li}.joints.${ji}.name" data-param-path="layers.${li}.joints.${ji}.name" value="${esc(joint.name)}" ${locked?'disabled':''}></label>
    <label>类型<select data-bind="layers.${li}.joints.${ji}.type" data-param-path="layers.${li}.joints.${ji}.type" ${locked?'disabled':''}>${[['rotation','旋转副'],['translation','滑动副'],['crank','曲柄旋转特殊副']].map(([type,label])=>`<option value="${type}" ${type===joint.type?'selected':''}>${label}</option>`).join('')}</select></label>
    ${joint.type==='crank'?`<label>运动副矢量<input data-bind="layers.${li}.joints.${ji}.slide_axis" data-param-path="layers.${li}.joints.${ji}.slide_axis" data-reverse-vector="${joint.reverse?'true':'false'}" value="${esc(displayJointVector(joint.slide_axis || '1, 0, 0', joint.reverse))}" ${locked?'disabled':''}></label>`:`<label>轴矢量<input data-bind="layers.${li}.joints.${ji}.axis" data-param-path="layers.${li}.joints.${ji}.axis" data-reverse-vector="${joint.reverse?'true':'false'}" value="${esc(displayJointVector(joint.axis, joint.reverse))}" ${locked?'disabled':''}></label>`}
    ${joint.type==='rotation'?`<label>世界坐标点<input data-bind="layers.${li}.joints.${ji}.point" data-param-path="layers.${li}.joints.${ji}.point" value="${esc(joint.point)}" ${locked?'disabled':''}></label>`:''}
    <label class="inline-check"><input type="checkbox" data-bind="layers.${li}.joints.${ji}.reverse" data-param-path="layers.${li}.joints.${ji}.reverse" ${joint.reverse?'checked':''} ${locked?'disabled':''}>反向</label>
    <label class="inline-check"><input type="checkbox" data-bind="layers.${li}.joints.${ji}.limited" data-param-path="layers.${li}.joints.${ji}.limited" ${joint.limited?'checked':''} ${locked?'disabled':''}>范围</label>
    ${joint.limited?`<label class="diagram-joint-range">范围<input type="number" data-type="number" data-bind="layers.${li}.joints.${ji}.range.0" value="${joint.range?.[0] ?? -180}" ${locked?'disabled':''}><input type="number" data-type="number" data-bind="layers.${li}.joints.${ji}.range.1" value="${joint.range?.[1] ?? 180}" ${locked?'disabled':''}></label>`:''}
    <button class="compact-delete" data-action="remove-joint" data-layer="${li}" data-joint="${ji}" ${locked?'disabled':''}>×</button>
  </div>`).join('') || '<span class="empty-inline">当前连线没有运动副</span>';
  root.innerHTML = `<div class="diagram-property-head"><b>运动副</b><small>${esc(parent.name)} → ${esc(layer.name)} · 作用于 child Layer 整个刚体${layer.meshes.length > 1 ? `（${layer.meshes.length} 个数模）` : ''}</small><label class="inline-check diagram-closure-toggle" title="闭链开关只在属性视窗中显示"><input type="checkbox" data-diagram-tree-closure-toggle data-parent-id="${esc(parent.id)}" data-child-id="${esc(layer.id)}" ${closure?'checked':''} ${locked?'disabled':''}>闭链</label><button class="button tiny ghost" data-action="add-joint" data-layer="${li}" ${locked?'disabled':''}>＋运动副</button></div><div class="diagram-joint-list">${joints}</div>`;
}

function renderLayerDetails() {
  const diagramSelection = hierarchyViewMode() === 'diagram' ? state.hierarchyDiagramSelection : null;
  if (hierarchyViewMode() === 'diagram') {
    if (!diagramSelection) { renderDiagramEmptyDetails(); return; }
    if (diagramSelection.type === 'closure_edge') {
      const closure = (state.project.kinematic_closures || []).find(item => item.id === diagramSelection.closureId);
      if (closure && renderDiagramClosureDetails(closure)) return;
      state.hierarchyDiagramSelection = null; renderDiagramEmptyDetails(); return;
    }
    const selectedLayerId = diagramSelection.type === 'tree_edge' ? diagramSelection.childId : diagramSelection.layerId;
    const diagramIndex = state.project.layers.findIndex(layer => layer.id === selectedLayerId);
    if (diagramIndex < 0) { renderDiagramEmptyDetails(); return; }
    state.selectedLayerId = selectedLayerId;
    const diagramLayer = state.project.layers[diagramIndex];
    if (diagramSelection.type === 'tree_edge') renderDiagramTreeEdgeDetails(diagramLayer, diagramIndex);
    else renderDiagramNodeDetails(diagramLayer, diagramIndex);
    return;
  }
  const li = state.project.layers.findIndex(layer => layer.id === state.selectedLayerId);
  if (li < 0) {
    renderRootDetails();
    return;
  }
  const layer = state.project.layers[li];
  $('#layerDetails').classList.toggle('inactive-layer', !layer.active);
  const advancedOpen = state.expandedLayerAdvanced.has(layer.id);
  const massEnabled = Boolean(state.ui.model?.mass_enabled_layers?.[layer.id]);
  const parentOptions = [`<option value="root" ${layer.parent_id === 'root' ? 'selected' : ''}>root</option>`, ...state.project.layers.filter(item => item.id !== layer.id).map(item => `<option value="${esc(item.id)}" ${layer.parent_id === item.id ? 'selected' : ''}>${esc(item.name)}</option>`)].join('');
  const layerMass = (state.massProperties?.layers || []).find(item => item.layer_id === layer.id);
  // V2.9.7.1: 每次重新进入编辑模式都从双列开始；仅当前编辑会话内切换，不写 ProjectSpec/UI 持久状态。
  const meshTwoColumns = state.editorLayout.meshTwoColumns !== false;
  $('#layerDetails').innerHTML = `    <div class="property-header"><div><p class="eyebrow">LAYER PROPERTIES</p><h2>${esc(layer.name)}</h2></div><div class="row-actions"><button class="button tiny primary" data-action="add-child-layer" data-layer="${li}" ${layer.active===false?'disabled':''}>＋ 添加子层级</button><button class="button tiny ghost" data-action="promote-layer" data-layer="${li}" title="移到当前父层级的上一级">升级</button><button class="button tiny ghost" data-action="demote-layer" data-layer="${li}" title="降为前一个同级层级的子层级">降级</button><button class="button tiny ghost" data-action="duplicate-layer" data-layer="${li}">复制</button><button class="button tiny danger" data-action="remove-layer" data-layer="${li}">删除</button></div></div>
    <div class="layer-primary-row">
      <label class="layer-name-field"><span>名称</span><input data-bind="layers.${li}.name" data-param-path="layers.${li}.name" value="${esc(layer.name)}"></label>
      <label class="color-field">颜色<input type="color" data-color-bind="layers.${li}.color" data-param-path="layers.${li}.color" value="${rgbaToHex(layer.color)}"><code>${esc(layer.color)}</code></label>
      <label class="inline-check"><input type="checkbox" data-bind="layers.${li}.active" data-param-path="layers.${li}.active" ${layer.active ? 'checked' : ''}>激活</label>
      <button class="fold-button ${advancedOpen ? 'open' : ''}" data-action="toggle-layer-advanced" data-layer-id="${esc(layer.id)}" title="展开位置和父层级">⌄</button>
    </div>
    ${advancedOpen ? `<div class="layer-advanced"><div class="form-grid four"><label>父层级<select data-bind="layers.${li}.parent_id" data-param-path="layers.${li}.parent_id">${parentOptions}</select></label>${[0,1,2].map(axis => `<label>位置 ${['X','Y','Z'][axis]} mm<input type="number" data-type="number" data-bind="layers.${li}.position_mm.${axis}" data-param-path="layers.${li}.position_mm.${axis}" value="${layer.position_mm?.[axis] || 0}"></label>`).join('')}</div><label class="inline-check mass-enable-check"><input type="checkbox" data-action="layer-mass-toggle" data-layer-id="${esc(layer.id)}" ${massEnabled ? 'checked' : ''}>显示 / 编辑质量</label>${massEnabled ? `<div class="mass-summary-row"><label>层级目标总质量 kg<input type="number" min="0" step="any" data-type="nullable-number" data-bind="layers.${li}.mass_kg" data-param-path="layers.${li}.mass_kg" value="${layer.mass_kg ?? ''}" placeholder="留空按数模设置 / 默认密度"></label><span>解析总质量 <b>${formatMass(layerMass?.resolved_mass_kg)}</b></span><small>层级质量会先扣除数模显式质量，再向其余数模分配；分配后的 kg 作为最终目标质量直接写入 MJCF。</small></div>` : ''}</div>` : ''}
    <div class="property-section joint-property-section"><div class="property-section-title"><span>运动副</span><small class="joint-body-scope ${layer.meshes.length > 1 ? 'warning' : ''}" title="一个 Layer 对应一个 MuJoCo 刚体；本层所有数模共用这些运动副">作用于整个层级刚体 · ${layer.meshes.length} 个数模${layer.meshes.length > 1 ? '（不是单个数模）' : ''}</small><button class="button tiny ghost" data-action="add-joint" data-layer="${li}">＋ 添加运动副</button></div>
      ${(layer.joints || []).map((joint, ji) => `<div class="sub-card joint-card ${joint.type === 'crank' ? 'joint-card-crank' : ''}"><div class="joint-compact-row">
        <label class="joint-name-field">名称<input data-bind="layers.${li}.joints.${ji}.name" data-param-path="layers.${li}.joints.${ji}.name" value="${esc(joint.name)}"></label>
        <label class="joint-type-field">类型<select data-bind="layers.${li}.joints.${ji}.type" data-param-path="layers.${li}.joints.${ji}.type">${[['rotation','旋转副'],['translation','滑动副'],['crank','曲柄旋转特殊副']].map(([type,label]) => `<option value="${type}" ${type === joint.type ? 'selected' : ''}>${label}</option>`).join('')}</select></label>
        ${joint.type === 'crank' ? `
          <label class="joint-axis-field joint-crank-axis-field">运动副矢量<input data-bind="layers.${li}.joints.${ji}.slide_axis" data-param-path="layers.${li}.joints.${ji}.slide_axis" data-reverse-vector="${joint.reverse ? 'true' : 'false'}" value="${esc(displayJointVector(joint.slide_axis || '1, 0, 0', joint.reverse))}"></label>
          <label class="joint-crank-field">曲柄旋转中心<input data-bind="layers.${li}.joints.${ji}.crank_center" data-param-path="layers.${li}.joints.${ji}.crank_center" value="${esc(joint.crank_center || '0, 0, 0')}"></label>
          <label class="joint-crank-field">曲柄末端<input data-bind="layers.${li}.joints.${ji}.crank_end" data-param-path="layers.${li}.joints.${ji}.crank_end" value="${esc(joint.crank_end || '0, 10, 0')}"></label>
          <label class="joint-crank-field">连杆末端<input data-bind="layers.${li}.joints.${ji}.rod_end" data-param-path="layers.${li}.joints.${ji}.rod_end" value="${esc(joint.rod_end || '30, 0, 0')}"></label>
        ` : `<label class="joint-axis-field">轴矢量<input data-bind="layers.${li}.joints.${ji}.axis" data-param-path="layers.${li}.joints.${ji}.axis" data-reverse-vector="${joint.reverse ? 'true' : 'false'}" value="${esc(displayJointVector(joint.axis, joint.reverse))}"></label>${joint.type === 'rotation' ? `<label class="joint-point-field">世界坐标点<input data-bind="layers.${li}.joints.${ji}.point" data-param-path="layers.${li}.joints.${ji}.point" value="${esc(joint.point)}"></label>` : ''}`}
        <span class="joint-flag-fields"><label class="inline-check joint-direction-check" title="切换运动副正向/反向"><input type="checkbox" data-bind="layers.${li}.joints.${ji}.reverse" data-param-path="layers.${li}.joints.${ji}.reverse" ${joint.reverse ? 'checked' : ''}><span aria-hidden="true"></span><b>反向</b></label><label class="inline-check"><input type="checkbox" data-bind="layers.${li}.joints.${ji}.limited" data-param-path="layers.${li}.joints.${ji}.limited" ${joint.limited ? 'checked' : ''}>范围</label></span>
        ${joint.limited ? `<label class="range-pair" title="已启用范围限位">范围值<span><input data-bind="layers.${li}.joints.${ji}.range.0" data-param-path="layers.${li}.joints.${ji}.range.0" data-type="number" type="number" value="${joint.range?.[0] ?? -180}"><input data-bind="layers.${li}.joints.${ji}.range.1" data-param-path="layers.${li}.joints.${ji}.range.1" data-type="number" type="number" value="${joint.range?.[1] ?? 180}"></span></label>` : ''}
        <button class="compact-delete" data-action="remove-joint" data-layer="${li}" data-joint="${ji}">×</button>
      </div>${state.project.solver_mode==='dynamic'?`<div class="joint-dynamics-row"><span>动力学</span><b class="joint-drive-state ${state.project.drives.some(drive=>drive.enabled&&drive.joint_id===joint.id)?'driven':'passive'}">${state.project.drives.some(drive=>drive.enabled&&drive.joint_id===joint.id)?'已驱动':'被动自由度'}</b><label>阻尼<input type="number" min="0" step="0.01" data-type="number" data-bind="layers.${li}.joints.${ji}.damping" value="${joint.damping??.1}"></label><label>干摩擦<input type="number" min="0" step="0.01" data-type="number" data-bind="layers.${li}.joints.${ji}.frictionloss" value="${joint.frictionloss??0}"></label><label>刚度<input type="number" min="0" step="0.1" data-type="number" data-bind="layers.${li}.joints.${ji}.stiffness" value="${joint.stiffness??0}"></label><label>自然位置 ${joint.type==='rotation'?'°':'mm'}<input type="number" step="0.1" data-type="number" data-bind="layers.${li}.joints.${ji}.spring_reference" value="${joint.spring_reference??0}"></label>${state.project.drives.some(drive=>drive.enabled&&drive.joint_id===joint.id)?'':`<small class="passive-joint-help">无 enabled 驱动：该自由度会受重力/惯性/约束反力运动。若要刚性固定请删除运动副；若要保持位置请绑定驱动或显式设置刚度/干摩擦。</small>`}</div>`:''}</div>`).join('') || '<div class="empty-inline">当前层级没有运动副</div>'}
    </div>
    <div class="property-section mesh-property-section" data-mesh-drop-target="${li}"><div class="property-section-title"><span>STL / OBJ 数模</span><small class="mesh-drop-hint" title="拖到本区域会并入同一个刚体；若要相对运动，应在框图把数模拖到本层级节点上创建 child Layer">拖到这里＝同一刚体；相对运动请建 child Layer</small><label class="inline-check mesh-column-toggle"><input type="checkbox" data-action="mesh-two-columns" ${meshTwoColumns ? 'checked' : ''}>双列</label><button class="button tiny ghost" data-action="adaptive-all-meshes" data-layer="${li}" title="对当前层级全部数模执行同族适配">自适应</button></div>
      <div class="layer-mesh-list ${meshTwoColumns ? 'mesh-grid-two' : ''}">${(layer.meshes || []).map((mesh, mi) => { const props = state.massProperties?.meshes?.[mesh.id]; return `<div class="sub-card mesh-select-row">
        <label class="mesh-file-field">文件<select data-bind="layers.${li}.meshes.${mi}.filename" data-param-path="layers.${li}.meshes.${mi}.filename">${meshOptions(mesh.filename)}</select></label>
        <div class="color-field mesh-color ${String(mesh.rgba || '').trim() ? '' : 'mesh-color-unset'}" title="${String(mesh.rgba || '').trim() ? '数模单独颜色（优先于层级颜色）' : '当前跟随层级颜色'}" aria-label="数模颜色"><span class="mesh-color-swatch"><input type="color" data-color-bind="layers.${li}.meshes.${mi}.rgba" data-param-path="layers.${li}.meshes.${mi}.rgba" value="${rgbaToHex(mesh.rgba || layer.color)}" ${String(mesh.rgba || '').trim() ? '' : 'disabled'}><button type="button" class="mesh-color-clear" data-action="set-mesh-color" data-layer="${li}" data-mesh="${mi}" title="启用数模单独调色" aria-label="启用数模单独调色">×</button></span><button type="button" class="mesh-follow-layer" data-action="follow-layer-color" data-layer="${li}" data-mesh="${mi}" ${String(mesh.rgba || '').trim() ? '' : 'disabled'}>跟随层级</button></div>
        <label class="mesh-opacity-field" title="数模透明度" aria-label="数模透明度"><input type="number" min="0" max="1" step=".05" data-type="number" data-bind="layers.${li}.meshes.${mi}.opacity" data-param-path="layers.${li}.meshes.${mi}.opacity" value="${mesh.opacity}"></label>
        ${massEnabled ? `<label class="mesh-mass-field" title="填写的 kg 是最终目标质量；生成 MJCF 时直接写 mass，不会因数模体积再次放大">目标质量 kg<input type="number" min="0" step="any" data-type="nullable-number" data-bind="layers.${li}.meshes.${mi}.mass_kg" data-param-path="layers.${li}.meshes.${mi}.mass_kg" value="${mesh.mass_kg ?? ''}" placeholder="继承层级"></label><label class="mass-derived">最终解析质量<output>${formatMass(props?.resolved_mass_kg)}</output><small>${massApplicationLabel(props?.mass_application)} · ${massSourceLabel(props?.source)}</small></label><label class="mass-derived mass-reference-density">参考密度<output>${formatDensity(props?.density_kg_m3)}</output><small>${formatVolume(props?.volume_m3)} · 仅用于分配/诊断</small></label>` : ''}
        <label class="inline-check mesh-collision-field"><input type="checkbox" data-bind="layers.${li}.meshes.${mi}.collision" data-param-path="layers.${li}.meshes.${mi}.collision" ${mesh.collision ? 'checked' : ''}>碰撞</label>
        ${state.project.solver_mode==='dynamic'&&mesh.collision?`<label class="mesh-dynamic-field">摩擦<input type="number" min="0" step="0.05" data-type="nullable-number" data-bind="layers.${li}.meshes.${mi}.friction" value="${mesh.friction??''}" placeholder="0.8"></label><label class="mesh-dynamic-field">膨胀 mm<input type="number" min="0" step="0.5" data-type="number" data-bind="layers.${li}.meshes.${mi}.collision_margin_mm" value="${mesh.collision_margin_mm??0}"></label>`:''}
        <button class="compact-delete" data-action="remove-mesh" data-layer="${li}" data-mesh="${mi}">×</button>
      </div>`; }).join('') || '<div class="empty-inline mesh-drop-empty">将右侧 STL/OBJ 数模拖拽到这里</div>'}</div>
    </div>`;
}

function formatMass(value) { return Number.isFinite(Number(value)) ? `${Number(value).toPrecision(6)} kg` : '—'; }
function formatDensity(value) { return Number.isFinite(Number(value)) ? `${Number(value).toPrecision(6)} kg/m³` : 'MuJoCo 内部逆求'; }
function formatVolume(value) { return Number.isFinite(Number(value)) ? `${(Number(value) * 1e9).toPrecision(6)} mm³` : '体积待读取'; }
function massSourceLabel(value) { return ({mesh:'数模目标质量',layer_volume:'层级按体积分配',layer_equal_fallback:'层级等分回退',default:'默认密度'})[value] || '待计算'; }
function massApplicationLabel(value) { return value === 'direct_mass' ? 'MJCF 直接质量' : '默认密度'; }

async function refreshMassProperties() {
  if (!state.project) return;
  try {
    const response = await api(`/api/projects/${state.project.id}/commands`, {
      method:'POST', body:JSON.stringify({command:{tool_id:'model.mass_properties',params:{},client:'human_ui'}}),
    });
    state.massProperties = response.output || null;
  } catch (_) { state.massProperties = null; }
}

function renderMeshLibrary() {
  const query = ($('#meshSearch')?.value || '').trim().toLowerCase();
  const files = state.meshFiles.filter(item => item.filename.toLowerCase().includes(query));
  $('#meshFileCount').textContent = `${state.meshFiles.length} FILES`;
  $('#meshRootLabel').textContent = state.project.mesh_root || '尚未选择模型目录';
  $('#localMeshPath').value = state.project.mesh_root || '';
  $('#meshFileList').classList.toggle('empty-state', !files.length);
  const force = meshThumbnailForceNextRender;
  meshThumbnailForceNextRender = false;
  $('#meshFileList').innerHTML = files.length ? files.map(item => {
    const parent = String(item.filename || '').includes('/') ? String(item.filename).split('/').slice(0,-1).join('/') : '';
    const fingerprint = meshThumbnailFingerprint(item);
    return `<article class="mesh-file" draggable="true" data-mesh-drag-filename="${esc(item.filename)}" title="双击或拖拽到当前层级添加；悬停 0.2 秒放大"><canvas class="mesh-thumbnail" width="224" height="152" data-mesh-thumbnail="${esc(item.filename)}" data-thumbnail-key="${esc(fingerprint)}"></canvas><span class="mesh-file-info"><strong>${esc(item.basename)}</strong>${parent ? `<small>${esc(parent)}</small>` : ''}</span><span class="mesh-file-size">${formatBytes(item.size)}</span></article>`;
  }).join('') : '没有匹配的 STL/OBJ 文件';
  $$('[data-mesh-thumbnail]').forEach(canvas => ensureMeshThumbnail(canvas, force));
  $$('.mesh-file', $('#meshFileList')).forEach(card => bindMeshCardHover(card));
}

let sharedMeshThumbnailRenderer = null;
const MESH_THUMBNAIL_CACHE_LIMIT = 256;
const meshThumbnailCache = new Map();
const meshThumbnailPending = new Map();
let meshThumbnailForceNextRender = false;

function meshThumbnailFingerprint(item) {
  return `${state.project?.mesh_root||''}|${item.filename}|${Number(item.size)||0}|${Number(item.modified)||0}`;
}

function rememberMeshThumbnail(key, surface) {
  meshThumbnailCache.delete(key);
  meshThumbnailCache.set(key, surface);
  while (meshThumbnailCache.size > MESH_THUMBNAIL_CACHE_LIMIT) meshThumbnailCache.delete(meshThumbnailCache.keys().next().value);
}

function paintCachedMeshThumbnail(canvas, surface) {
  const context=canvas.getContext('2d');context.clearRect(0,0,canvas.width,canvas.height);context.drawImage(surface,0,0,canvas.width,canvas.height);
}

async function ensureMeshThumbnail(canvas, force = false) {
  const key = canvas.dataset.thumbnailKey, filename = canvas.dataset.meshThumbnail, view = canvas.dataset.thumbnailView || 'iso';
  if (!key || !filename) return;
  if (force) { meshThumbnailCache.delete(key); meshThumbnailPending.delete(key); }
  const cached = meshThumbnailCache.get(key);
  if (cached) { paintCachedMeshThumbnail(canvas, cached); return; }
  let pending = !force && meshThumbnailPending.get(key);
  if (!pending) {
    pending = (async () => {
      const scratch = document.createElement('canvas'); scratch.width=224; scratch.height=152;
      await drawMeshThumbnail(scratch, filename, '', view);
      rememberMeshThumbnail(key, scratch); return scratch;
    })().finally(() => { if (meshThumbnailPending.get(key) === pending) meshThumbnailPending.delete(key); });
    meshThumbnailPending.set(key, pending);
  }
  paintCachedMeshThumbnail(canvas, await pending);
}

function bindMeshCardHover(card) {
  let timer = null;
  card.addEventListener('pointerenter', () => { timer=setTimeout(()=>card.classList.add('hover-expanded'),600); });
  card.addEventListener('pointerleave', () => { if(timer)clearTimeout(timer);timer=null;card.classList.remove('hover-expanded'); });
}
// Blender coordinates: Z is up. Positive rotation around +Y turns +Z toward
// +X, which appears clockwise when viewed from +Y toward the origin.
const MESH_THUMBNAIL_YAW = Math.PI / 4;
// Raw CAD mesh previews arrived rolled +90° around X compared with the
// animation scene's Z-up convention. Undo that roll before applying the
// familiar slightly elevated thumbnail view.
const MESH_THUMBNAIL_PITCH = .46 - Math.PI / 2;

function meshThumbnailRenderer(width, height) {
  if (sharedMeshThumbnailRenderer) {
    sharedMeshThumbnailRenderer.canvas.width = width;
    sharedMeshThumbnailRenderer.canvas.height = height;
    return sharedMeshThumbnailRenderer;
  }
  const surface = document.createElement('canvas');
  const gl = surface.getContext('webgl2', {alpha:true, antialias:true, premultipliedAlpha:false, preserveDrawingBuffer:true});
  if (!gl) return null;
  const compile = (type, source) => {
    const shader=gl.createShader(type);gl.shaderSource(shader,source);gl.compileShader(shader);
    if(!gl.getShaderParameter(shader,gl.COMPILE_STATUS))throw new Error(gl.getShaderInfoLog(shader)||'thumbnail shader failed');
    return shader;
  };
  const vertex = compile(gl.VERTEX_SHADER, `#version 300 es
    layout(location=0) in vec3 aPosition; layout(location=1) in vec3 aNormal;
    uniform mat3 uRotation; uniform float uAspect;
    out vec3 vNormal;
    void main(){
      vec3 p=uRotation*aPosition; vNormal=uRotation*aNormal;
      float camera=3.4-p.z*.34;
      gl_Position=vec4(p.x*2.72/uAspect/camera,p.y*2.72/camera,-p.z*.24,1.0);
    }`);
  const fragment = compile(gl.FRAGMENT_SHADER, `#version 300 es
    precision highp float; in vec3 vNormal; out vec4 outColor;
    void main(){
      vec3 n=normalize(vNormal);vec3 l=normalize(vec3(.45,-.55,.8));
      float d=max(dot(n,l),0.0);float light=.30+.70*d;
      outColor=vec4(vec3(.72,.75,.80)*light,1.0);
    }`);
  const program=gl.createProgram();gl.attachShader(program,vertex);gl.attachShader(program,fragment);gl.linkProgram(program);
  if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw new Error(gl.getProgramInfoLog(program)||'thumbnail program failed');
  sharedMeshThumbnailRenderer={canvas:surface,gl,program,position:gl.getAttribLocation(program,'aPosition'),normal:gl.getAttribLocation(program,'aNormal'),rotation:gl.getUniformLocation(program,'uRotation'),aspect:gl.getUniformLocation(program,'uAspect')};
  surface.width=width;surface.height=height;
  return sharedMeshThumbnailRenderer;
}

function paintMeshThumbnailBackdrop(context, canvas) {
  const width=canvas.width,height=canvas.height;
  const background=context.createRadialGradient(width*.5,height*.35,0,width*.5,height*.35,width*.76);
  background.addColorStop(0,'#ffffff');background.addColorStop(1,'#edf1f4');
  context.fillStyle=background;context.fillRect(0,0,width,height);
}

function parseMeshThumbnailTriangles(buffer, filename, maximumFaces=32000) {
  const triangles=[];
  if (/\.obj$/i.test(filename)) {
    const lines=new TextDecoder().decode(buffer).split(/\r?\n/),vertices=[];
    let triangleCount=0;
    lines.forEach(line=>{const parts=line.trim().split(/\s+/);if(parts[0]==='v'&&parts.length>=4)vertices.push(parts.slice(1,4).map(Number));else if(parts[0]==='f'&&parts.length>=4)triangleCount+=parts.length-3;});
    const step=Math.max(1,Math.ceil(triangleCount/maximumFaces));let triangleIndex=0;
    lines.forEach(line=>{const parts=line.trim().split(/\s+/);if(parts[0]!=='f'||parts.length<4)return;const ids=parts.slice(1).map(value=>Number(value.split('/')[0])).map(value=>value<0?vertices.length+value:value-1);for(let i=1;i+1<ids.length;i++,triangleIndex++){if(triangleIndex%step)continue;const face=[vertices[ids[0]],vertices[ids[i]],vertices[ids[i+1]]];if(face.every(Boolean))triangles.push(face);}});
    return triangles;
  }
  const view=new DataView(buffer),binaryCount=buffer.byteLength>=84?view.getUint32(80,true):0;
  if(binaryCount&&84+binaryCount*50<=buffer.byteLength){
    const step=Math.max(1,Math.ceil(binaryCount/maximumFaces));
    for(let face=0;face<binaryCount;face+=step){const offset=84+face*50+12;triangles.push([0,1,2].map(vertex=>[0,1,2].map(axis=>view.getFloat32(offset+vertex*12+axis*4,true))));}
    return triangles;
  }
  const text=new TextDecoder().decode(buffer),pattern=/vertex\s+([-+\deE.]+)\s+([-+\deE.]+)\s+([-+\deE.]+)/gi;
  let match,vertexCount=0;while((match=pattern.exec(text)))vertexCount++;
  const step=Math.max(1,Math.ceil(vertexCount/3/maximumFaces));pattern.lastIndex=0;let faceIndex=0,face=[];
  while((match=pattern.exec(text))){face.push([Number(match[1]),Number(match[2]),Number(match[3])]);if(face.length===3){if(faceIndex%step===0)triangles.push(face);face=[];faceIndex++;}}
  return triangles;
}

function renderMeshThumbnailWebGL(target, triangles, view = 'iso') {
  const renderer=meshThumbnailRenderer(target.width,target.height);if(!renderer)return false;
  const {canvas,gl,program}=renderer;
  const all=triangles.flat(),minimum=[0,1,2].map(axis=>Math.min(...all.map(point=>point[axis]))),maximum=[0,1,2].map(axis=>Math.max(...all.map(point=>point[axis]))),center=[0,1,2].map(axis=>(minimum[axis]+maximum[axis])/2),extent=Math.max(...[0,1,2].map(axis=>maximum[axis]-minimum[axis]),1e-9);
  const normalized=triangles.map(face=>face.map(point=>point.map((value,axis)=>(value-center[axis])*2/extent)));
  const normalSums=new Map(),faceNormals=[];
  const keyOf=point=>point.map(value=>value.toFixed(5)).join(',');
  normalized.forEach(face=>{const u=face[1].map((value,index)=>value-face[0][index]),v=face[2].map((value,index)=>value-face[0][index]),normal=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]],length=Math.hypot(...normal)||1,unit=normal.map(value=>value/length);faceNormals.push(unit);face.forEach(point=>{const key=keyOf(point),sum=normalSums.get(key)||[0,0,0];normalSums.set(key,sum.map((value,index)=>value+normal[index]));});});
  const positions=[],normals=[];
  normalized.forEach((face,faceIndex)=>face.forEach(point=>{positions.push(...point);const sum=normalSums.get(keyOf(point))||faceNormals[faceIndex],length=Math.hypot(...sum)||1;normals.push(...sum.map(value=>value/length));}));
  const upload=(location,data)=>{const buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(data),gl.STREAM_DRAW);gl.enableVertexAttribArray(location);gl.vertexAttribPointer(location,3,gl.FLOAT,false,0,0);return buffer;};
  canvas.width=target.width;canvas.height=target.height;gl.viewport(0,0,canvas.width,canvas.height);gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);gl.enable(gl.DEPTH_TEST);gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);gl.useProgram(program);
  const positionBuffer=upload(renderer.position,positions),normalBuffer=upload(renderer.normal,normals),ay=view==='front'?0:MESH_THUMBNAIL_YAW,ax=view==='front'?-Math.PI/2:MESH_THUMBNAIL_PITCH,cy=Math.cos(ay),sy=Math.sin(ay),cx=Math.cos(ax),sx=Math.sin(ax);
  // Column-major R_y(+45°) * R_x(pitch): first make the raw mesh upright,
  // then turn it around Blender's world +Y axis.
  gl.uniformMatrix3fv(renderer.rotation,false,new Float32Array([cy,0,-sy,sy*sx,cx,cy*sx,sy*cx,-sx,cy*cx]));gl.uniform1f(renderer.aspect,canvas.width/canvas.height);gl.drawArrays(gl.TRIANGLES,0,positions.length/3);gl.finish();
  const context=target.getContext('2d');paintMeshThumbnailBackdrop(context,target);context.drawImage(canvas,0,0,target.width,target.height);gl.deleteBuffer(positionBuffer);gl.deleteBuffer(normalBuffer);return true;
}

async function drawMeshThumbnail(canvas, filename, sourceUrl = '', view = 'iso') {
  const context = canvas.getContext('2d');
  context.clearRect(0, 0, canvas.width, canvas.height);
  try {
    const safePath = filename.split('/').map(encodeURIComponent).join('/');
    const response = await fetch(sourceUrl || `/api/projects/${state.project.id}/meshes/file/${safePath}`);
    if (!response.ok) throw new Error('thumbnail unavailable');
    const buffer = await response.arrayBuffer();
    const triangles=parseMeshThumbnailTriangles(buffer,filename);
    const finite=triangles.filter(face=>face.length===3&&face.every(point=>point?.every(Number.isFinite)));
    if (!finite.length) throw new Error('empty mesh');
    if(renderMeshThumbnailWebGL(canvas,finite,view))return;
    const all=finite.flat(),center=[0,1,2].map(axis=>(Math.min(...all.map(point=>point[axis]))+Math.max(...all.map(point=>point[axis])))/2);
    const rotate=([x,y,z])=>{x-=center[0];y-=center[1];z-=center[2];const ay=view==='front'?0:MESH_THUMBNAIL_YAW,ax=view==='front'?-Math.PI/2:MESH_THUMBNAIL_PITCH,y1=y*Math.cos(ax)-z*Math.sin(ax),z1=y*Math.sin(ax)+z*Math.cos(ax),x2=x*Math.cos(ay)+z1*Math.sin(ay),z2=-x*Math.sin(ay)+z1*Math.cos(ay);return[x2,y1,z2];};
    const faces=finite.map(face=>face.map(rotate));
    const projected=faces.flat();
    const xs = projected.map(point => point[0]), ys = projected.map(point => point[1]);
    const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
    const scale = Math.min((canvas.width - 12) / Math.max(maxX - minX, 1e-9), (canvas.height - 12) / Math.max(maxY - minY, 1e-9));
    const map = ([x,y]) => [6 + (x - minX) * scale, canvas.height - 6 - (y - minY) * scale];
    paintMeshThumbnailBackdrop(context,canvas);context.lineJoin='round';
    faces.sort((a,b)=>a.reduce((sum,point)=>sum+point[2],0)-b.reduce((sum,point)=>sum+point[2],0)).forEach(face=>{
      const u=face[1].map((value,index)=>value-face[0][index]),v=face[2].map((value,index)=>value-face[0][index]),normal=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]],length=Math.hypot(...normal)||1,light=Math.max(.18,Math.min(1,.38+.62*Math.abs((normal[0]*.25+normal[1]*-.45+normal[2]*.86)/length))),shade=Math.round(78+light*112),points=face.map(map);
      context.beginPath();context.moveTo(...points[0]);context.lineTo(...points[1]);context.lineTo(...points[2]);context.closePath();context.fillStyle=`rgb(${shade},${shade+3},${shade+7})`;context.fill();
    });
  } catch (_) {
    paintMeshThumbnailBackdrop(context,canvas);context.strokeStyle = '#9aa6b2'; context.strokeRect(18, 16, canvas.width - 36, canvas.height - 32);
    context.beginPath(); context.moveTo(18, canvas.height - 16); context.lineTo(canvas.width / 2, 30); context.lineTo(canvas.width - 18, canvas.height - 16); context.stroke();
  }
}

function renderVariables() {
  const entries = Object.entries(state.project.variables || {});
  $('#variableList').innerHTML = entries.length ? entries.map(([name, value], index) => `<div class="variable-row"><label>变量名称<input data-variable-name="${index}" value="${esc(name)}" aria-label="变量名称"></label><label>变量值 / 表达式<input data-variable-value="${index}" value="${esc(value)}" aria-label="变量值或表达式"></label><button class="compact-delete" data-action="remove-variable" data-variable="${index}">×</button></div>`).join('') : '<span class="empty-inline">暂无自定义变量</span>';
}

function allJoints() {
  return state.project.layers.flatMap(layer => (layer.joints || []).map(joint => ({...joint, layerName: layer.name})));
}

function segmentVariableRows(drive, segment, segmentIndex) {
  const number = segmentIndex + 1;
  const variableName = suffix => `${drive.name}/${suffix}${number}`;
  const startExpression = segment.start_mode === 'reference'
    ? `${segment.reference || '未设置参考段'}/${segment.reference_boundary === 'start' ? 'start' : 'end'} + ${segment.start}`
    : String(segment.start);
  const durationExpression = segment.mode === 'duration' ? String(segment.duration) : `abs(${variableName('stroke')}) / ${variableName('speed')}`;
  const scheduled = [...(state.baseSimulationSchedule || []), ...(state.simulationSchedule || [])]
    .find(item => item.drive_id === drive.id && (item.mapping_segment_id || item.id) === segment.id);
  const fallbackValues = scheduled ? {
    [variableName('starttime')]: Number(scheduled.start),
    [variableName('endtime')]: Number(scheduled.end),
    [variableName('duration')]: Number(scheduled.duration),
    [variableName('speed')]: Number(scheduled.speed),
    [variableName('stroke')]: Number(scheduled.travel),
  } : {};
  const rows = [
    [variableName('starttime'), startExpression],
    [variableName('endtime'), `${startExpression} + ${variableName('duration')}`],
    [variableName('duration'), durationExpression],
    [variableName('speed'), String(segment.speed)],
    [variableName('stroke'), String(segment.travel)],
  ];
  return rows.map(([name, expression]) => {
    const cached = state.driveResolvedVariables?.[name];
    const fallback = fallbackValues[name];
    return {name, expression, value:Number.isFinite(Number(cached)) ? Number(cached) : (Number.isFinite(fallback) ? fallback : null)};
  });
}

function segmentVariableText(drive, segment, segmentIndex) {
  return segmentVariableRows(drive, segment, segmentIndex).map(item => `${item.name}\n表达式: ${item.expression}\n当前值: ${item.value ?? '—'}`).join('\n');
}

const profileLabel = value => ({s_curve:'缓起缓停',smoothstep:'Smoothstep',points:'自定义点',external_csv:'外部 CSV',mapping:'映射电机'})[value] || value;

function mappingRows(segment) {
  return MappingMath.normalizeRows(state.mappingTables?.[segment.id] || segment.points || []);
}

const mappingNumber=value=>MappingMath.mappingNumber(value);
const mapPosition=(rows,source)=>MappingMath.mapPosition(rows,source);
const inverseMapPosition=(rows,target,preferred)=>MappingMath.inverseMapPosition(rows,target,preferred);
const mappedTravelExpression=(rows,start,expression,inverse=false)=>MappingMath.mappedTravelExpression(
  rows, start, expression, inverse, {...(state.project?.variables||{}), ...(state.driveResolvedVariables||{})}
);
function sourceSegmentStart(drive, segment, segmentIndex, relation=null) {
  return MappingMath.sourceSegmentStart({
    schedule: state.baseSimulationSchedule?.length ? state.baseSimulationSchedule : state.simulationSchedule,
    drive, segment, segmentIndex, relation,
    variables: state.driveResolvedVariables || {},
  });
}
function mappingFollowers(drive) {
  return state.project.drives.flatMap((follower,di)=>(follower.segments||[]).map((segment,si)=>({follower,segment,di,si}))).filter(item=>item.segment.profile==='mapping'&&((drive.joint_id&&item.segment.mapping_source_joint_id===drive.joint_id)||item.segment.mapping_source_joint_id===`drive:${drive.id}`));
}
function companionTravelControl(drive, segment, driveIndex, segmentIndex) {
  const relation=mappingFollowers(drive)[0];if(!relation)return'';
  const key=`${segment.id}:${relation.segment.id}`,rows=mappingRows(relation.segment),start=sourceSegmentStart(drive,segment,segmentIndex,relation);
  if(!state.companionTravels.has(key)){try{state.companionTravels.set(key,mappedTravelExpression(rows,start,segment.travel));}catch{state.companionTravels.set(key,'');}}
  return `<div class="companion-travel"><button class="button tiny ghost" data-action="companion-to-source" data-drive="${driveIndex}" data-segment="${segmentIndex}" data-mapping-drive="${relation.di}" data-mapping-segment="${relation.si}" title="由伴生行程反查源头行程">←</button><small>映射</small><button class="button tiny ghost" data-action="source-to-companion" data-drive="${driveIndex}" data-segment="${segmentIndex}" data-mapping-drive="${relation.di}" data-mapping-segment="${relation.si}" title="由源头行程映射伴生行程">→</button><label>伴生行程（${esc(relation.follower.name)}）<input data-companion-travel="${esc(key)}" value="${esc(state.companionTravels.get(key)||'')}" aria-label="伴生行程表达式"></label></div>`;
}

function quickOptimization() {
  state.project.quick_optimization ||= {version:1,enabled:false,name:'快速寻优工作流',steps:[],last_run:{}};
  state.project.quick_optimization.steps ||= [];
  return state.project.quick_optimization;
}

function quickModeForField(field) {
  return field === 'speed' ? 'speed' : field === 'travel' ? 'travel' : 'time';
}

function quickVariableMeta(drive, segment, segmentIndex, field) {
  const number = segmentIndex + 1;
  const suffix = ({start:`starttime${number}`,duration:`duration${number}`,speed:`speed${number}`,travel:`stroke${number}`})[field];
  const labels = {start:'开始时间 / 参考偏移',duration:'运动时长',speed:'运动速度',travel:'运动行程'};
  const legacyCamel = ({start:`startTime${number}`,duration:`Duration${number}`,speed:`Speed${number}`,travel:`Stroke${number}`})[field];
  const resolved = state.driveResolvedVariables[`${drive.name}/${suffix}`] ?? state.driveResolvedVariables[`${drive.name}.${suffix}`] ?? state.driveResolvedVariables[`${drive.name}/${legacyCamel}`];
  const raw = Number(segment[field]);
  return {
    variable_name:`${drive.name}/${suffix}`,
    description:`${drive.name} · ${segment.name} · ${labels[field]}`,
    initial_value:Number.isFinite(raw) ? raw : Number(resolved),
    mode:quickModeForField(field),
  };
}

function quickTargetCatalog() {
  return state.project.drives.flatMap((drive,di) => (drive.segments || []).flatMap((segment,si) => {
    if (segment.profile === 'mapping') return [];
    const fields=segment.profile === 'external_csv' ? ['start'] : ['start',segment.mode==='speed'?'speed':'duration','travel'];
    return fields.map(field=>({
      key:`${drive.id}|${segment.id}|${field}`, drive_id:drive.id, segment_id:segment.id, field,
      ...quickVariableMeta(drive,segment,si,field),
    }));
  }));
}

function quickStepSelected(driveId, segmentId, field) {
  return quickOptimization().steps.some(step => step.drive_id === driveId && step.segment_id === segmentId && step.field === field);
}

function renderQuickOptimization() {
  const workflow = quickOptimization();
  const targetCatalog=quickTargetCatalog();
  const open = Boolean(workflow.enabled);
  $('#quickOptimizationToggle').checked = open;
  $('#quickOptimizationPanel').classList.toggle('hidden', !open);
  $('#driveOptimizationLayout').classList.toggle('quick-open', open);
  $('#quickWorkflowName').value = workflow.name || '快速寻优工作流';
  const modeOptions = selected => [['time','时间寻优'],['speed','速度寻优'],['travel','行程寻优']].map(([value,label]) => `<option value="${value}" ${value===selected?'selected':''}>${label}</option>`).join('');
  const constraints = step => (step.last_constraints || []).map(item => `<span class="${item.passed?'pass':'fail'}">${esc(item.name)} ${item.minimum_mm == null ? '—' : Number(item.minimum_mm).toFixed(3)} &gt; ${Number(item.boundary_mm).toFixed(3)} mm</span>`).join('');
  const targetOptions = step => {
    const selected=`${step.drive_id}|${step.segment_id}|${step.field}`;
    return `<option value="">按中文说明重新选择</option>`+targetCatalog.map(item=>`<option value="${esc(item.key)}" ${item.key===selected?'selected':''}>${esc(item.description)} · ${esc(item.variable_name)}</option>`).join('');
  };
  $('#quickOptimizationSteps').innerHTML = workflow.steps.length ? workflow.steps.map((step,index) => {
    const result = step.result_value == null ? '' : Number(step.result_value).toFixed(6).replace(/0+$/,'').replace(/\.$/,'');
    const statusClass = ['completed','limit_reached'].includes(step.status) ? 'completed' : ['no_feasible_value','failed'].includes(step.status) ? 'failed' : '';
    return `<article class="quick-step ${statusClass}" data-quick-step-id="${esc(step.id)}">
      <div class="quick-step-main">
        <div><small>寻优对象 ${index+1}</small><div class="quick-variable-name" title="${esc(step.variable_name)}">${esc(step.variable_name)}</div></div>
        <label>初始值<input type="number" step="any" data-quick-bind="initial_value" value="${Number(step.initial_value)}"></label>
        <label>寻优结果<input readonly value="${esc(result)}" placeholder="—"></label>
        <label>寻优方式<select data-quick-bind="mode">${modeOptions(step.mode)}</select></label>
        <button class="quick-step-fold ${step.collapsed?'':'open'}" data-action="quick-toggle-step" data-step-id="${esc(step.id)}" title="展开 / 折叠">⌄</button>
        <button class="button tiny primary" data-action="quick-run-step" data-step-id="${esc(step.id)}" ${state.quickOptimizationRunning?'disabled':''}>开始</button>
        <button class="quick-step-remove" data-action="quick-remove-step" data-step-id="${esc(step.id)}" title="移除">×</button>
      </div>
      ${step.collapsed ? '' : `<div class="quick-step-details">
        <label>中文说明<input data-quick-bind="description" value="${esc(step.description||'')}"></label>
        <label>对象关联<select data-quick-relink>${targetOptions(step)}</select></label>
        ${step.mode === 'speed' ? `<label class="switch-label speed-direction"><input type="checkbox" data-quick-bind="speed_direction" ${step.speed_direction==='increase'?'checked':''}><span></span>${step.speed_direction==='increase'?'加速寻优':'减速寻优'}</label>` : '<span></span>'}
        <label>间隔<input type="number" min="0.000001" step="any" data-quick-bind="step_size" value="${step.step_size ?? ''}" placeholder="默认"></label>
        <div class="quick-step-constraints">${constraints(step)}</div>
        <div class="quick-result-actions"><button class="button tiny ghost" data-action="quick-load-step" data-step-id="${esc(step.id)}" ${step.result_value==null?'disabled':''}>载入寻优结果</button></div>
      </div>`}
    </article>`;
  }).join('') : '<div class="quick-empty">尚未添加寻优对象。<br>请双击左侧运动段的参数标题。</div>';
  $$('[data-action="quick-run-all"]').forEach(button => { button.disabled = state.quickOptimizationRunning || !workflow.steps.length; });
  $$('[data-action="quick-preview"],[data-action="quick-load-all"]').forEach(button => { button.disabled = !workflow.steps.some(step => step.result_value != null); });
}

function addQuickOptimizationTarget(label) {
  const workflow = quickOptimization();
  if (!workflow.enabled) return toast('请先开启“快速寻优”', 'error');
  const di = Number(label.dataset.quickDrive), si = Number(label.dataset.quickSegment), field = label.dataset.quickTarget;
  const drive = state.project.drives[di], segment = drive?.segments?.[si];
  if (!drive || !segment || !['start','duration','speed','travel'].includes(field)) return;
  if (segment.profile === 'external_csv' && field !== 'start') return toast('外部 CSV 的时长/行程由内嵌曲线决定，仅开始时间可加入快速寻优', 'error');
  if (quickStepSelected(drive.id, segment.id, field)) return toast('该变量已经在寻优工作流中');
  const meta = quickVariableMeta(drive, segment, si, field);
  if (!Number.isFinite(meta.initial_value)) return toast(`变量 ${meta.variable_name} 当前值无法解析为数值`, 'error');
  workflow.steps.push({
    id:uid('quickopt'), drive_id:drive.id, segment_id:segment.id, field,
    variable_name:meta.variable_name, description:meta.description,
    initial_value:meta.initial_value, result_value:null, mode:meta.mode,
    speed_direction:'decrease', step_size:null, max_attempts:200,
    collapsed:true, status:'pending', last_constraints:[],
  });
  markDirty(); renderDrives(); renderQuickOptimization(); scheduleInteractionCommit();
}

function quickResultValues(stepIds = null) {
  const selected = stepIds ? new Set(stepIds) : null;
  return Object.fromEntries(quickOptimization().steps
    .filter(step => step.result_value != null && (!selected || selected.has(step.id)))
    .map(step => [step.id, Number(step.result_value)]));
}

function loadQuickOptimizationResults(stepIds = null) {
  const values = quickResultValues(stepIds);
  if (!Object.keys(values).length) return toast('尚无可载入的寻优结果', 'error');
  for (const step of quickOptimization().steps) {
    if (!(step.id in values)) continue;
    const drive = state.project.drives.find(item => item.id === step.drive_id);
    const segment = drive?.segments?.find(item => item.id === step.segment_id);
    if (!segment) return toast(`无法载入“${step.description}”：当前项目中找不到对应运动段，请展开步骤重新关联`, 'error');
    segment[step.field] = values[step.id];
  }
  markDirty(); renderAll(); scheduleInteractionCommit();
}

async function runQuickOptimization(stepIds = []) {
  if (!quickOptimization().steps.length) return toast('请先双击运动参数添加寻优对象', 'error');
  return withBlockingLoading({title:'正在提交快速寻优',detail:'正在保存工作流并创建后台寻优任务；任务受理后即可继续操作。'}, async () => {
    try {
      state.quickOptimizationRunning = true; renderQuickOptimization();
      await saveEditableDraft();
      const result = await api(`/api/projects/${state.project.id}/optimize?quick=true`, {
        method:'POST', body:JSON.stringify({step_ids:stepIds}),
      });
      watchJob(result.job_id, 'quick_optimization');
      toast(stepIds.length ? '单步快速寻优已提交' : '自动化寻优工作流已提交');
    } catch (error) {
      state.quickOptimizationRunning = false; renderQuickOptimization(); toast(error.message, 'error');
    }
  });
}

function acceptQuickOptimizationResult(result) {
  const workflow = quickOptimization();
  for (const item of result?.steps || []) {
    const step = workflow.steps.find(candidate => candidate.id === item.step_id);
    if (!step) continue;
    step.result_value = item.result_value;
    step.status = item.status;
    step.last_constraints = item.constraints || [];
  }
  workflow.last_run = {...result, artifacts:undefined};
  state.quickOptimizationRunning = false;
  markDirty(); renderAll(); scheduleInteractionCommit();
}

async function previewQuickOptimization() {
  const values = quickResultValues();
  if (!Object.keys(values).length) return toast('尚无可预览的寻优结果', 'error');
  try {
    await saveEditableDraft();
    state.webViewerWindow = window.open('about:blank', '_blank');
    const result = await api(`/api/projects/${state.project.id}/web-viewer`, {method:'POST', body:JSON.stringify({quick_results:values})});
    watchJob(result.job_id, 'web_viewer_export');
    toast('正在准备寻优结果 Web 预览；当前项目值不会被改写');
  } catch (error) { toast(error.message, 'error'); }
}

async function exportQuickWorkflow() {
  const workflow = deepClone(quickOptimization());
  workflow.last_run = {};
  workflow.steps.forEach(step => { step.result_value=null; step.status='pending'; step.last_constraints=[]; });
  const payload = {format:'mujoco_studio_quick_optimization',format_version:1,application_version:'2.16.11.6',workflow};
  const filename=`${(workflow.name||'quick_optimization').replace(/[\\/:*?"<>|]+/g,'_')}.quick-opt.json`;
  await saveBlobToChosenPath(filename,new Blob([JSON.stringify(payload,null,2)],{type:'application/json'}),'application/json');
}

async function importQuickWorkflow(file) {
  if (!file) return;
  try {
    const payload=JSON.parse(await file.text());
    if (payload.format!=='mujoco_studio_quick_optimization' || !Array.isArray(payload.workflow?.steps)) throw new Error('不是有效的快速寻优工作流 JSON');
    state.project.quick_optimization={
      version:1, enabled:true, name:String(payload.workflow.name||'导入的快速寻优工作流'),
      steps:payload.workflow.steps.map(step=>({...step,id:String(step.id||uid('quickopt')),result_value:null,status:'pending',last_constraints:[],collapsed:false})),
      last_run:{},
    };
    markDirty(); renderAll(); await commitCurrentStep('已导入快速寻优工作流');
  } catch(error){toast(`工作流导入失败：${error.message}`,'error');}
}

// V2.16.10.2 — Session-only, bounded two-column drive width. Keep the original
// drive card DOM, order and ProjectSpec untouched when moving this separator.
function driveColumnBounds(width) {
  const minimum = Math.min(50, Math.max(30, Math.ceil(35500 / Math.max(1, width))));
  return {minimum, maximum:100-minimum};
}
function applyDriveColumnSplit(percent) {
  const shell = $('#driveListShell'), splitter = $('#driveColumnSplitter');
  if (!shell || !splitter) return;
  const width = shell.getBoundingClientRect().width;
  // The editor may be hidden when renderAll runs; do not corrupt its ratio.
  const {minimum, maximum} = driveColumnBounds(width || 1200);
  const requested = Number(percent);
  const next = Math.max(minimum, Math.min(maximum, Number.isFinite(requested) ? requested : 50));
  state.editorLayout.driveColumnPercent = next;
  shell.style.setProperty('--drive-left-width', `${next}%`);
  splitter.setAttribute('aria-valuemin', String(minimum));
  splitter.setAttribute('aria-valuemax', String(maximum));
  splitter.setAttribute('aria-valuenow', String(Math.round(next)));
  splitter.setAttribute('aria-valuetext', `左侧 ${Math.round(next)}%，右侧 ${Math.round(100-next)}%`);
  splitter.title = `拖动调整驱动栏：左 ${Math.round(next)}% / 右 ${Math.round(100-next)}%；方向键微调，双击均分`;
}
function initDriveColumnResizer() {
  const shell = $('#driveListShell'), splitter = $('#driveColumnSplitter');
  if (!shell || !splitter) return;
  let active = null;
  const available = () => shell.classList.contains('drive-split-active') && getComputedStyle(splitter).display !== 'none';
  const fromPointer = event => {
    const rect = shell.getBoundingClientRect();
    return rect.width > 0 ? (event.clientX - rect.left) * 100 / rect.width : 50;
  };
  splitter.addEventListener('pointerdown', event => {
    if (event.button !== 0 || !available() || active) return;
    active = {id:event.pointerId, initial:state.editorLayout.driveColumnPercent};
    splitter.setPointerCapture(event.pointerId);
    splitter.classList.add('dragging');
    event.preventDefault(); event.stopPropagation();
  });
  splitter.addEventListener('pointermove', event => {
    if (!active || event.pointerId !== active.id) return;
    applyDriveColumnSplit(fromPointer(event));
    event.preventDefault(); event.stopPropagation();
  });
  const finish = event => {
    if (!active || event.pointerId !== active.id) return;
    const initial = active.initial;
    active = null;
    splitter.classList.remove('dragging');
    if (event.type === 'pointercancel') applyDriveColumnSplit(initial);
    if (splitter.hasPointerCapture?.(event.pointerId)) splitter.releasePointerCapture(event.pointerId);
    event.preventDefault(); event.stopPropagation();
  };
  splitter.addEventListener('pointerup', finish);
  splitter.addEventListener('pointercancel', finish);
  splitter.addEventListener('lostpointercapture', () => {active=null; splitter.classList.remove('dragging');});
  splitter.addEventListener('keydown', event => {
    if (!available()) return;
    const {minimum,maximum} = driveColumnBounds(shell.getBoundingClientRect().width);
    let next;
    if (event.key === 'ArrowLeft') next = state.editorLayout.driveColumnPercent - (event.shiftKey ? 10 : 2);
    else if (event.key === 'ArrowRight') next = state.editorLayout.driveColumnPercent + (event.shiftKey ? 10 : 2);
    else if (event.key === 'Home') next = minimum;
    else if (event.key === 'End') next = maximum;
    else return;
    applyDriveColumnSplit(next); event.preventDefault(); event.stopPropagation();
  });
  splitter.addEventListener('dblclick', event => {
    if (!available()) return;
    applyDriveColumnSplit(50); event.preventDefault(); event.stopPropagation();
  });
  if (typeof ResizeObserver !== 'undefined') {
    new ResizeObserver(() => {
      if (shell.getBoundingClientRect().width > 0 && shell.classList.contains('drive-split-active')) {
        applyDriveColumnSplit(state.editorLayout.driveColumnPercent);
      }
    }).observe(shell);
  }
  applyDriveColumnSplit(state.editorLayout.driveColumnPercent);
}

function renderDrives() {
  const joints = allJoints();
  const twoColumns = state.editorLayout.driveTwoColumns !== false;
  $('#driveTwoColumn').checked = twoColumns;
  $('#driveList').style.setProperty('--drive-font', '"Microsoft YaHei",sans-serif');
  $('#driveList').classList.toggle('drive-grid-two', twoColumns);
  $('#driveListShell')?.classList.toggle('drive-split-active', twoColumns && state.project.drives.length > 1);
  applyDriveColumnSplit(state.editorLayout.driveColumnPercent);
  const jointOptions = selected => `<option value="" ${!selected ? 'selected' : ''}>无运动副（原点透明 Geom）</option>` + joints.map(joint => `<option value="${esc(joint.id)}" ${joint.id === selected ? 'selected' : ''}>${esc(joint.layerName)} / ${esc(joint.name)}</option>`).join('');
  const mappingSourceOptions = (selected, targetDriveId) => {
    const driveOptions = state.project.drives.filter(item => item.id !== targetDriveId).map(item => {
      const joint = joints.find(candidate => candidate.id === item.joint_id);
      const detail = joint ? `${joint.layerName} / ${joint.name}` : '无运动副 · 原点透明 Geom';
      const value = `drive:${item.id}`;
      return `<option value="${esc(value)}" ${value === selected ? 'selected' : ''}>驱动：${esc(item.name)} · ${esc(detail)}</option>`;
    }).join('');
    const jointRows = joints.map(joint => `<option value="${esc(joint.id)}" ${joint.id === selected ? 'selected' : ''}>运动副：${esc(joint.layerName)} / ${esc(joint.name)}</option>`).join('');
    return `<option value="">请选择</option><optgroup label="源驱动">${driveOptions}</optgroup><optgroup label="兼容旧项目 · 源运动副">${jointRows}</optgroup>`;
  };
  $('#driveList').innerHTML = state.project.drives.length ? state.project.drives.map((drive, di) => `
    <article class="entity-card drive-card" data-drive-card="${di}"><div class="entity-head drive-head">
      <span class="drive-drag-handle" draggable="true" title="按住并拖拽驱动排序">⠿</span><span class="drive-identity"><b class="drive-index">${esc(drive.name)}</b><small class="drive-function" title="当前驱动的运动函数">${esc([...new Set(drive.segments.map(seg => profileLabel(seg.profile)))].join(' / ') || '无运动段')}</small></span>
      <label class="drive-inline-field"><span>名称</span><input data-bind="drives.${di}.name" value="${esc(drive.name)}"></label>
      <label class="drive-inline-field drive-joint-field"><span>运动副</span><select data-bind="drives.${di}.joint_id">${jointOptions(drive.joint_id)}</select></label>
      <label class="inline-check"><input type="checkbox" data-bind="drives.${di}.enabled" ${drive.enabled ? 'checked' : ''}>启用</label>
      ${state.project.solver_mode === 'dynamic' ? `<details class="drive-dynamics-tuning"><summary>自锁 / 动力学参数</summary><div><label>自锁力 <small>静止目标接合 · ${joints.find(item => item.id === drive.joint_id)?.type === 'rotation' ? 'N·m' : 'N'} · 0=关闭</small><input type="number" min="0" step="10" data-type="number" data-bind="drives.${di}.dynamic_lock_force" value="${esc(drive.dynamic_lock_force ?? 2000)}"></label><label>Kp <small>位置保持刚度</small><input type="number" min="0" step="1" data-type="number" data-bind="drives.${di}.dynamic_kp" value="${esc(drive.dynamic_kp ?? 100)}"></label><label>Kv <small>速度阻尼；不能单独提供静态承载</small><input type="number" min="0" step="1" data-type="number" data-bind="drives.${di}.dynamic_kv" value="${esc(drive.dynamic_kv ?? 20)}"></label></div><small class="drive-lock-help">自锁只在当前目标与下一物理步目标相同时接合；驱动目标开始变化前自动释放。</small></details>` : ''}
      <span class="badge">${drive.segments.length} 段</span>
      <button class="button tiny ghost" data-action="add-segment" data-drive="${di}">＋ 运动段</button>
      <button class="compact-delete" data-action="remove-drive" data-drive="${di}">×</button>
    </div><div class="entity-body drive-segments">
      ${drive.segments.map((seg, si) => {
        const key = `${drive.id}:${seg.id}`;
        const expanded = state.expandedSegments.has(key);
        const refDriveName = String(seg.reference || '').split('/')[0];
        const refDrive = state.project.drives.find(item => item.name === refDriveName) || drive;
        const refSegments = (refDrive?.segments || []).filter(item => refDrive.id !== drive.id || item.id !== seg.id);
        return `<div class="motion-segment-row ${expanded ? 'expanded' : ''} ${seg.profile === 'mapping' ? 'mapping-segment' : ''}" data-drive-index="${di}" data-segment-index="${si}"><div class="motion-segment-main">
          <span class="segment-drag-handle" draggable="true" title="按住并拖拽运动段排序">⠿</span>
          ${seg.profile === 'mapping' ? `<label>运动函数<select data-bind="drives.${di}.segments.${si}.profile">${['s_curve','smoothstep','points','external_csv','mapping'].map(profile => `<option value="${profile}" ${profile === seg.profile ? 'selected' : ''}>${profileLabel(profile)}</option>`).join('')}</select></label><label class="mapping-source-inline">映射源<select data-bind="drives.${di}.segments.${si}.mapping_source_joint_id">${mappingSourceOptions(seg.mapping_source_joint_id, drive.id)}</select></label><div class="mapping-csv mapping-csv-inline"><strong>${esc(seg.mapping_csv_name || (seg.csv_path ? seg.csv_path.split(/[\\/]/).pop() : ((seg.points||[]).length ? '旧项目内嵌映射' : '尚未导入 CSV')))}</strong><small>${seg.mapping_point_count || (seg.points||[]).length || 0} 点 · JSON内嵌</small><input class="hidden" type="file" accept=".csv,text/csv" data-mapping-csv="${di}:${si}"><button class="button tiny ghost" data-action="choose-mapping-csv" data-drive="${di}" data-segment="${si}">导入 CSV</button><button class="button tiny ghost" data-action="export-mapping-csv" data-drive="${di}" data-segment="${si}" ${(seg.points||[]).length>=2?'':'disabled title="映射表尚无两个数值点"'}>导出 CSV</button></div><button class="compact-delete" data-action="remove-segment" data-drive="${di}" data-segment="${si}">×</button>` : `
          <label class="start-mode-field">开始模式<select data-bind="drives.${di}.segments.${si}.start_mode"><option value="direct" ${seg.start_mode === 'direct' ? 'selected' : ''}>绝对时间</option><option value="reference" ${seg.start_mode === 'reference' ? 'selected' : ''}>相对时间</option></select></label>
          <label class="key-motion-field start-field ${quickStepSelected(drive.id,seg.id,'start')?'quick-selected':''}" data-quick-target="start" data-quick-drive="${di}" data-quick-segment="${si}" title="双击添加到快速寻优">开始 / 偏移<input data-bind="drives.${di}.segments.${si}.start" value="${esc(seg.start)}"></label>
          <label class="parameter-mode-field">参数模式<select data-bind="drives.${di}.segments.${si}.mode" ${seg.profile === 'external_csv' ? 'disabled' : ''}><option value="duration" ${seg.mode === 'duration' ? 'selected' : ''}>时长</option><option value="speed" ${seg.mode === 'speed' ? 'selected' : ''}>速度</option></select></label>
          ${seg.mode === 'speed' && seg.profile !== 'external_csv'
            ? `<label class="key-motion-field speed-field ${quickStepSelected(drive.id,seg.id,'speed')?'quick-selected':''}" data-quick-target="speed" data-quick-drive="${di}" data-quick-segment="${si}" title="双击添加到快速寻优">速度<input data-bind="drives.${di}.segments.${si}.speed" value="${esc(seg.speed)}"></label>`
            : `<label class="key-motion-field duration-field ${quickStepSelected(drive.id,seg.id,'duration')?'quick-selected':''}" data-quick-target="duration" data-quick-drive="${di}" data-quick-segment="${si}" title="${seg.profile === 'external_csv' ? '由外部 CSV 时间轴决定' : '双击添加到快速寻优'}">时长<input data-bind="drives.${di}.segments.${si}.duration" value="${esc(seg.duration)}" ${seg.profile === 'external_csv' ? 'readonly' : ''}></label>`}
          <label class="key-motion-field travel-field ${quickStepSelected(drive.id,seg.id,'travel')?'quick-selected':''}" data-quick-target="travel" data-quick-drive="${di}" data-quick-segment="${si}" title="${seg.profile === 'external_csv' ? '由外部 CSV 位置曲线决定' : '双击添加到快速寻优'}">行程<input data-bind="drives.${di}.segments.${si}.travel" value="${esc(seg.travel)}" ${seg.profile === 'external_csv' ? 'readonly' : ''}></label>
          ${seg.profile === 'external_csv' ? `<div class="mapping-csv mapping-csv-inline external-motion-csv"><strong>${esc(seg.external_csv_name || ((seg.points||[]).length ? '模型 JSON 内嵌外部曲线' : '尚未导入 CSV'))}</strong><small>${(seg.points||[]).length || 0} 点 · ${esc(seg.external_csv_source_metric || '位置')} · ${esc(seg.external_csv_header || 'time/value')}</small><input class="hidden" type="file" accept=".csv,text/csv" data-external-motion-csv="${di}:${si}"><button class="button tiny ghost" data-action="choose-external-motion-csv" data-drive="${di}" data-segment="${si}">导入 CSV</button><button class="button tiny ghost" data-action="export-external-motion-csv" data-drive="${di}" data-segment="${si}" ${(seg.points||[]).length>=2?'':'disabled title="外部运动表尚无两个数值点"'}>导出 CSV</button></div>` : ''}
          ${seg.start_mode === 'reference' ? `<label class="reference-drive-field">参考驱动<select data-ref-drive="${di}:${si}">${state.project.drives.map(item => `<option value="${esc(item.name)}" ${item.name === refDriveName ? 'selected' : ''}>${esc(item.name)}</option>`).join('')}</select></label><label class="reference-boundary-field">参考边界<select data-ref-boundary="${di}:${si}"><option value="">请选择</option>${refSegments.flatMap(item => [['start','开始'],['end','结束']].map(([boundary,label]) => `<option value="${esc(refDrive.name + '/' + item.name + '|' + boundary)}" ${seg.reference === `${refDrive.name}/${item.name}` && seg.reference_boundary === boundary ? 'selected' : ''}>${esc(item.name)} · ${label}</option>`)).join('')}</select></label>` : ''}
          ${companionTravelControl(drive, seg, di, si)}
          <button class="segment-fold ${expanded ? 'open' : ''}" data-action="toggle-segment-advanced" data-segment-key="${esc(key)}" title="运动函数、加速时间和缓起缓停">⌄</button>
          <button class="compact-delete" data-action="remove-segment" data-drive="${di}" data-segment="${si}">×</button>
          `}
          </div>
          ${expanded && seg.profile !== 'mapping' ? `<div class="segment-advanced">
            <div class="segment-advanced-fields">
              <label>运动函数<select data-bind="drives.${di}.segments.${si}.profile">${['s_curve','smoothstep','points','external_csv','mapping'].map(profile => `<option value="${profile}" ${profile === seg.profile ? 'selected' : ''}>${profileLabel(profile)}</option>`).join('')}</select></label>
              ${seg.profile === 'external_csv'
                ? `<span class="hint">外部 CSV 曲线按采样时间线性插值；速度/加速度列会在导入时按一代 V21.5 规则积分为位置曲线。</span>`
                : `<label>设置方式<select data-bind="drives.${di}.segments.${si}.easing_mode"><option value="time" ${(seg.easing_mode||'time')==='time'?'selected':''}>时间模式</option><option value="acceleration" ${seg.easing_mode==='acceleration'?'selected':''}>加速度模式</option></select></label>
              <label class="inline-check"><input type="checkbox" data-bind="drives.${di}.segments.${si}.ease_in" ${seg.ease_in ? 'checked' : ''}>缓起</label>
              <label class="inline-check"><input type="checkbox" data-bind="drives.${di}.segments.${si}.ease_out" ${seg.ease_out ? 'checked' : ''}>缓停</label>
              ${(seg.easing_mode||'time')==='time'
                ? `<label>缓起时间<input data-bind="drives.${di}.segments.${si}.ease_in_time" value="${esc(seg.ease_in_time ?? seg.acceleration_time ?? .2)}"></label><label>缓停时间<input data-bind="drives.${di}.segments.${si}.ease_out_time" value="${esc(seg.ease_out_time ?? seg.acceleration_time ?? .2)}"></label>`
                : `<label>缓起加速度<input data-bind="drives.${di}.segments.${si}.ease_in_acceleration" value="${esc(seg.ease_in_acceleration ?? 150)}"></label><label>缓停加速度<input data-bind="drives.${di}.segments.${si}.ease_out_acceleration" value="${esc(seg.ease_out_acceleration ?? 150)}"></label>`}`}
            </div><div class="segment-variable-panel"><div><strong>当前变量信息</strong><button class="button tiny ghost" data-action="copy-segment-variables" data-drive="${di}" data-segment="${si}">复制</button></div><pre tabindex="0">${esc(segmentVariableText(drive, seg, si))}</pre></div>
          </div>` : ''}
        </div>`;
      }).join('') || '<div class="empty-inline">尚未添加运动段</div>'}
    </div></article>`).join('') : '<div class="empty-state panel">先创建运动副，然后添加驱动</div>';
}

function renderPairs() {
  const objectOptions = selected => {
    const available = state.meshFiles.map(item => item.filename);
    const names = [...available, ...(selected || []).filter(name => !available.includes(name))];
    return names.map(name => `<option value="${esc(name)}" ${(selected || []).includes(name) ? 'selected' : ''}>${esc(name)}${available.includes(name) ? '' : ' [缺失]'}</option>`).join('');
  };
  const expandedId = state.ui.distance?.expanded_pair || '';
  const summary = values => values?.length ? values.map(value => `<span title="${esc(value)}">${esc(value.split(/[\\/]/).pop())}</span>`).join('') : '<i>尚未选择</i>';
  const summaryText = values => values?.length ? values.map(value => value.split(/[\\/]/).pop()).join('、') : '点击选择对象';
  $('#pairList').innerHTML = state.project.distance_pairs.map((pair, pi) => {
    const expanded = expandedId === pair.id;
    const pairDragEnabled = canEditProject();
    return `<article class="pair-card pair-card-v2134 ${expanded ? 'objects-expanded' : ''}" data-pair-card data-pair-id="${esc(pair.id)}">
      <span class="pair-v21341-drag-handle ${pairDragEnabled ? '' : 'disabled'}" data-pair-drag-handle="${esc(pair.id)}" ${pairDragEnabled ? 'draggable="true"' : 'aria-disabled="true"'} title="${pairDragEnabled ? '按住并拖拽调整测距对顺序' : '当前模型只读，不能调整测距对顺序'}" aria-label="拖拽调整测距对顺序">⠿</span>
      <div class="pair-v2134-main">
        <div class="pair-v2134-identity"><h3 title="${esc(pair.name)}">${esc(pair.name)}</h3><input aria-label="测距对名称" data-bind="distance_pairs.${pi}.name" value="${esc(pair.name)}"></div>
        <div class="pair-v2134-objects">
          <button type="button" data-action="toggle-pair-objects" data-pair-id="${esc(pair.id)}" data-pair-focus="a" title="选择对象 A"><b>对象A</b><span>${esc(summaryText(pair.objects_a))}</span></button>
          <button type="button" data-action="toggle-pair-objects" data-pair-id="${esc(pair.id)}" data-pair-focus="b" title="选择对象 B"><b>对象B</b><span>${esc(summaryText(pair.objects_b))}</span></button>
        </div>
        <details class="pair-v2134-advanced"><summary>高级设置</summary><div><label>精确撒点间隙<input type="number" min="0.1" step="0.1" data-type="number" data-bind="distance_pairs.${pi}.precise_spacing_mm" value="${pair.precise_spacing_mm ?? 2}"><span>mm</span></label><label>寻优边界<input type="number" min="0" step="0.1" data-type="number" data-bind="distance_pairs.${pi}.boundary_mm" value="${pair.boundary_mm ?? 8}"><span>mm</span></label></div></details>
        <button class="compact-delete pair-v2134-delete" data-action="remove-pair" data-pair="${pi}" title="删除测距对">×</button>
      </div>
      ${expanded ? `<div class="pair-object-overlay"><div class="pair-object-dialog"><header><div><strong>${esc(pair.name)} · 对象选择</strong><small>默认多选：单击切换选中/取消，已选对象高亮显示</small></div><button class="compact-delete" data-action="toggle-pair-objects" data-pair-id="${esc(pair.id)}">×</button></header><div class="pair-object-lists"><label data-pair-list="a">对象 A<select multiple size="18" data-bind="distance_pairs.${pi}.objects_a">${objectOptions(pair.objects_a)}</select></label><label data-pair-list="b">对象 B<select multiple size="18" data-bind="distance_pairs.${pi}.objects_b">${objectOptions(pair.objects_b)}</select></label></div><footer><button class="button tiny primary" data-action="toggle-pair-objects" data-pair-id="${esc(pair.id)}">完成</button></footer></div></div>` : ''}
    </article>`;
  }).join('') || '<div class="empty-state panel">尚未配置测距对</div>';
}

function renderSettings() {
  $('#simStart').value = state.project.simulation.start_time;
  $('#simEnd').value = state.project.simulation.end_time;
  $('#simStep').value = state.project.simulation.timestep;
  $('#simEngine').value = 'mujoco';
  if($('#simGroundEnabled')) $('#simGroundEnabled').checked = state.project.simulation.ground_enabled ?? true;
  if($('#simGroundMargin')) $('#simGroundMargin').value = state.project.simulation.ground_collision_margin_mm ?? 0;
  if($('#simGravity')) $('#simGravity').value = state.project.simulation.gravity_m_s2 ?? 9.81;
  if($('#simGroundFriction')) $('#simGroundFriction').value = state.project.simulation.ground_friction ?? .8;
  if($('#simContactResponse')) $('#simContactResponse').value = state.project.simulation.contact_response_time_s ?? .025;
  if($('#simContactDamping')) $('#simContactDamping').value = state.project.simulation.contact_damping_ratio ?? 2;
  document.body.classList.toggle('solver-dynamic', state.project.solver_mode === 'dynamic');
  document.body.classList.toggle('solver-kinematic', state.project.solver_mode !== 'dynamic');
  if($('#solverModeToggle')) $('#solverModeToggle').checked = state.project.solver_mode === 'dynamic';
  renderCameraSettings();
  $('#axisHeightRange').value = state.project.result_layout?.height || 80;
  $('#axisHeightValue').textContent = `${state.project.result_layout?.height || 80} px`;
  $('#distanceSampleLimit').value = state.project.distance_sampling?.max_points_per_object || 400;
  state.project.animation_html ||= {fps:30,max_faces_per_mesh:120000,distance_follow_damping:0.35,adaptive_threshold_mm:25,watermark_text:'C项目-时序仿真组',watermark_position_mm:'0, 0, 0',watermark_size_mm:150,watermark_thickness_mm:10,watermark_color:'#B3B3B3'};
  $$('[data-bind^="animation_html."]').forEach(control => {
    const key=control.dataset.bind.split('.').at(-1),value=state.project.animation_html[key];
    control.value=value ?? (key==='adaptive_threshold_mm' ? 25 : '');
  });
  const opt = state.project.optimization;
  $('#optMode').value = opt.mode; $('#optTrials').value = opt.trials; $('#optObjective').value = opt.objective; $('#optDirection').value = opt.direction;
}

function renderRanges() {
  $('#rangeList').innerHTML = state.project.optimization.variables.map((item, index) => `<div class="range-row"><input data-bind="optimization.variables.${index}.name" value="${esc(item.name)}" placeholder="变量名"><input type="number" data-type="number" data-bind="optimization.variables.${index}.minimum" value="${item.minimum}" placeholder="最小"><input type="number" data-type="number" data-bind="optimization.variables.${index}.maximum" value="${item.maximum}" placeholder="最大"><input type="number" data-type="number" data-bind="optimization.variables.${index}.step" value="${item.step}" placeholder="间隔"><button class="compact-delete" data-action="remove-range" data-range="${index}">×</button></div>`).join('') || '<div class="empty-inline">添加自变参数后即可遍历或随机采样</div>';
}

function resultSourceCatalog() {
  const result = state.latestSimulation;
  if (!result) return [];
  const sources = [];
  Object.entries(result.drive_curves || {}).forEach(([id, curve]) => {
    if (Array.isArray(curve.position)) sources.push({group:'drive', key:`drive:${id}`, label:curve.name || id, unit:curve.unit || '', values:curve.position});
  });
  Object.entries(result.curves || {}).forEach(([id, curve]) => {
    const layer = state.project.layers.find(item => (item.joints || []).some(joint => joint.id === id));
    const label = `${layer?.name || '未分层'} / ${curve.name || id}`;
    // Result-object catalog exposes one canonical entry per joint.
    // Velocity/acceleration remain available through the existing operation selector (d1/d2).
    if (Array.isArray(curve.position)) sources.push({group:'joint', key:`joint:${id}`, label, unit:curve.unit || '', values:curve.position});
  });
  Object.entries(result.distance_curves || {}).forEach(([id, curve]) => {
    const session = state.distanceCurveSession;
    const overlay = session?.projectId === state.project?.id && session?.simulationId === result.simulation_id
      ? session.loaded[id] : null;
    const actual = overlay?.method === 'viewer_sampled_surface_v1' ? overlay : curve;
    // Legacy native convex-hull curves are never silently offered as a Viewer
    // sampled-surface result. Missing data stay missing; never coerce to zero.
    const values = actual?.method === 'viewer_sampled_surface_v1' && actual.viewer_query_mode === 'exact_all_samples' && Array.isArray(actual.values) ? actual.values : [];
    sources.push({group:'pair', key:`pair:${id}`, label:curve.name || id, unit:'mm', values});
  });
  return sources;
}

// V2.15.10: user-selected measurements are lazy, isolated per trajectory and
// cached outside the model JSON / immutable baseline simulation results.
function currentDistanceCurveSession() {
  const projectId = state.project?.id;
  const simulationId = state.latestSimulation?.simulation_id;
  if (!projectId || !simulationId) return null;
  const previous = state.distanceCurveSession;
  if (previous?.projectId !== projectId || previous?.simulationId !== simulationId) {
    state.distanceCurveSession = {projectId, simulationId, loaded:{}, requested:new Set(), jobs:{}, errors:{},
      inflightPairIds:new Set(), pendingPairIds:new Set(), consentGranted:false};
  }
  return state.distanceCurveSession;
}

function selectedResultDistancePairs() {
  const ids = new Set();
  (state.project?.result_layout?.axes || []).forEach((axis, axisIndex) => {
    (axis.curves || []).forEach((curve, curveIndex) => {
      const source = effectiveResultCurveSource(axis, curve, axisIndex, curveIndex);
      if (source.startsWith('pair:')) ids.add(source.slice(5));
    });
  });
  return [...ids].filter(id => Object.hasOwn(state.latestSimulation?.distance_curves || {}, id));
}

function currentDistanceCurveStatus(pairId) {
  const session = currentDistanceCurveSession();
  if (!resultDistanceLayoutActive()) return ''; 
  if (!session) return '';
  if (session.errors[pairId]) return `测距失败：${session.errors[pairId]}`;
  const curve = session.loaded[pairId];
  if (curve?.status === 'ready') return '';
  if (curve?.status === 'partial') return `测距中 ${curve.completed_frames || 0}/${curve.total_frames || 0} 帧`;
  if (session.waitingForSlot) return '测距任务排队中（用户并发任务上限，自动重试）…';
  if (session.batchJobId || session.batchRequest || session.jobs[pairId] || session.requested.has(pairId)) return 'Viewer 表面测距后台计算中…';
  return '';
}

function updateDistanceCurveStatus({render=true}={}) {
  $$('[data-axis-distance-status]').forEach(element => {
    const axis = state.project?.result_layout?.axes?.[Number(element.dataset.axisDistanceStatus)];
    const ids = (axis?.curves || []).map((curve, curveIndex) =>
      effectiveResultCurveSource(axis, curve, Number(element.dataset.axisDistanceStatus), curveIndex))
      .filter(key => key.startsWith('pair:')).map(key => key.slice(5));
    const message = ids.map(id => currentDistanceCurveStatus(id)).filter(Boolean).join('；');
    element.textContent = message;
    element.title = message;
  });
  if (render) drawResultAxes();
}

function scheduleDistanceAxisRenderOnce(session) {
  if (state.distanceCurveSession !== session || session.visibleAxisRefreshScheduled) return;
  session.visibleAxisRefreshScheduled = true;
  const repaint = () => {
    session.visibleAxisRefreshScheduled = false;
    if (state.distanceCurveSession !== session || state.project?.id !== session.projectId ||
        state.latestSimulation?.simulation_id !== session.simulationId) return;
    drawResultAxes();
  };
  if (typeof requestAnimationFrame === 'function') requestAnimationFrame(repaint);
  else repaint();
}

function applyDistanceCurveDataOnly(response, session) {
  if (!session || state.distanceCurveSession !== session ||
      response?.simulation_id !== session.simulationId || response.pair_id == null) return false;
  const curve = response.curve;
  if (!curve || curve.method !== 'viewer_sampled_surface_v1' ||
      curve.viewer_query_mode !== 'exact_all_samples' || !Array.isArray(curve.values)) return false;
  const previous = session.loaded[response.pair_id];
  if (previous?.status === 'ready' && response.status !== 'ready') return false;
  if (previous?.status === response.status && previous.values.length >= curve.values.length) return false;
  session.loaded[response.pair_id] = {...curve, status:response.status};
  if (response.status === 'ready') session.inflightPairIds?.delete(response.pair_id);
  delete session.errors[response.pair_id];
  return true;
}

function applyDistanceCurveResponse(response, session) {
  const changed = applyDistanceCurveDataOnly(response, session);
  if (changed) {
    updateDistanceCurveStatus({render:false});
    refreshCombinedGanttSchedule({render:false});
    scheduleDistanceAxisRenderOnce(session);
  }
  return changed;
}

function applyDistanceBatchResponse(response, session) {
  if (state.distanceCurveSession !== session || response?.simulation_id !== session.simulationId) return false;
  const changed = Object.values(response.pairs || {}).map(row => applyDistanceCurveDataOnly(row, session)).some(Boolean);
  if (changed) {
    updateDistanceCurveStatus({render:false});
    refreshCombinedGanttSchedule({render:false});
    scheduleDistanceAxisRenderOnce(session); // one Canvas render for N rows
  }
  return true;
}

function distancePairSubsetUrl(projectId, ids) {
  const base = `/api/projects/${encodeURIComponent(projectId)}/distance-curves`;
  return ids.length ? `${base}?${ids.map(id => `pair_id=${encodeURIComponent(id)}`).join('&')}` : base;
}

async function requestSelectedDistanceCurve(pairId, {retry=false}={}) {
  return requestSelectedDistanceCurves({pairIds:[pairId],retry});
}

async function requestSelectedDistanceCurves({retry=false,pairIds=null}={}) {
  if (!resultDistanceLayoutActive() && pairIds === null) return;
  const session = currentDistanceCurveSession();
  if (!session) return;
  const available = state.latestSimulation?.distance_curves || {};
  // Single-pair actions MUST honor the explicit ID. Layout requests use only
  // the effective pair: sources currently visible, not every frozen pair.
  const requested = [...new Set(pairIds === null ? selectedResultDistancePairs() : pairIds)]
    .filter(id => Object.hasOwn(available, id));
  const ids = [...new Set([...session.pendingPairIds, ...requested])]
    .filter(id => session.loaded[id]?.status !== 'ready' && !session.inflightPairIds.has(id));
  if (!ids.length) return;
  if (retry) {
    ids.forEach(id => delete session.errors[id]);
    session.declined = false;
  }
  if (session.declined || ids.every(id => session.errors[id])) return;
  if (session.batchRequest) {
    ids.forEach(id => session.pendingPairIds.add(id));
    return;
  }
  if (session.waitingForSlot && Date.now() < (session.retryAt || 0)) {
    ids.forEach(id => session.pendingPairIds.add(id));
    return;
  }
  session.batchRequest = true;
  session.waitingForSlot = false;
  ids.forEach(id => {session.requested.add(id); session.pendingPairIds.delete(id);});
  updateDistanceCurveStatus({render:false});
  const base = `/api/projects/${encodeURIComponent(session.projectId)}/distance-curves`;
  try {
    const cached = await api(distancePairSubsetUrl(session.projectId, ids), {timeout:12000});
    if (!applyDistanceBatchResponse(cached, session)) return;
    const missing = ids.filter(id => session.loaded[id]?.status !== 'ready');
    if (!missing.length) return; // Cache hits do not require a costly-job prompt.
    if (!session.consentGranted) {
      if (!confirm(`将计算当前坐标系所选的 ${missing.length} 个测距对（所有真实轨迹帧、完整精确采样）。大型模型可能较慢，是否继续？`)) {
        session.declined = true; return;
      }
      session.consentGranted = true;
      state.distanceLayoutConsentProjectId = session.projectId;
    }
    const started = await api(base, {method:'POST',body:JSON.stringify({pair_ids:missing}),timeout:25000});
    if (!applyDistanceBatchResponse(started, session)) return;
    if (started.job_id) {
      session.batchJobId = started.job_id;
      missing.forEach(id => session.inflightPairIds.add(id));
      session.lastPoll = Date.now();
      session.completionNotified = false;
    } else if (started.status === 'ready') {
      missing.forEach(id => session.inflightPairIds.delete(id));
    }
  } catch (error) {
    if (state.distanceCurveSession === session) {
      if (error.status === 429) {
        ids.forEach(id => session.pendingPairIds.add(id));
        session.waitingForSlot = true;
        session.retryAt = Date.now() + Math.max(3, error.retryAfter || 5) * 1000;
      } else {
        ids.forEach(id => { session.errors[id] = error.message || String(error); });
        toast(`测距对计算失败：${error.message}`, 'error');
      }
    }
  } finally {
    session.batchRequest = false;
    ids.forEach(id => session.requested.delete(id));
    if (state.distanceCurveSession === session) {
      updateDistanceCurveStatus({render:false});
      if (session.pendingPairIds.size && !session.waitingForSlot && !session.declined) {
        // Selection changed during GET/POST; append another wave to the same
        // server Job, never submit a second independent distance Job.
        queueMicrotask(() => { void requestSelectedDistanceCurves(); });
      }
    }
  }
}

async function pollSelectedDistanceCurves() {
  const session = currentDistanceCurveSession();
  if (!session || session.polling || currentPage() !== 'simulation') return;
  if (session.waitingForSlot) {
    if (Date.now() >= (session.retryAt || 0) && !session.batchRequest) {
      await requestSelectedDistanceCurves();
    }
    return;
  }
  // Newly visible pair IDs can join an already running Job. The server owns
  // the single-flight pending queue and returns its existing job_id.
  if (!session.batchRequest && session.batchJobId &&
      selectedResultDistancePairs().some(id => session.loaded[id]?.status !== 'ready' &&
        !session.inflightPairIds.has(id))) {
    await requestSelectedDistanceCurves();
  }
  if (!session.batchJobId || Date.now() - (session.lastPoll || 0) < 5000) return;
  session.polling = true;
  session.lastPoll = Date.now();
  const ids = [...new Set([...session.inflightPairIds, ...selectedResultDistancePairs()])];
  const path = distancePairSubsetUrl(session.projectId, ids);
  const jobId = session.batchJobId;
  try {
    const [record, job] = await Promise.all([
      api(path, {timeout:12000}),
      Promise.resolve(state.jobs.find(item => item.id === jobId)).then(item => item || api(`/api/jobs/${jobId}`)),
    ]);
    if (!applyDistanceBatchResponse(record, session)) return;
    if (['completed','failed','cancelled','timed_out'].includes(job.status)) {
      session.batchJobId = null;
      if (job.status === 'completed') {
        const finalRecord = record.status === 'ready' ? record : await api(path, {timeout:12000});
        if (!applyDistanceBatchResponse(finalRecord, session)) return;
        if (ids.some(id => session.loaded[id]?.status !== 'ready'))
          throw new Error('任务已结束，但当前轨迹缺少完整的完全精确测距结果，请重试');
        session.inflightPairIds.clear();
        if (!session.completionNotified) {
          session.completionNotified = true;
          toast('当前所选测距对曲线计算完成', 'success');
        }
      } else {
        session.inflightPairIds.forEach(id => {
          session.errors[id] = job.error?.message || job.message || '计算中断';
        });
        session.inflightPairIds.clear();
        toast(`测距对计算失败：${job.error?.message || job.message || '计算中断'}`, 'error');
      }
      updateDistanceCurveStatus({render:false});
    }
  } finally { session.polling = false; }
}

function canonicalResultCurveSource(source) {
  const value = String(source || '');
  return value.replace(/^(joint:[^:]+):(position|velocity|acceleration)$/, '$1');
}

function resultViewerCurveOverrideKey(axis, curve, axisIndex, curveIndex) {
  return curve?.id || `${axis?.id || axisIndex}:${curveIndex}`;
}

function effectiveResultCurveSource(axis, curve, axisIndex, curveIndex) {
  const overrides = state.resultViewerCurveOverrides;
  if (overrides?.projectId === state.project?.id) {
    const key = resultViewerCurveOverrideKey(axis, curve, axisIndex, curveIndex);
    if (Object.prototype.hasOwnProperty.call(overrides.sources || {}, key)) return canonicalResultCurveSource(overrides.sources[key]);
  }
  return canonicalResultCurveSource(curve?.source || '');
}

function setResultViewerCurveSource(axisIndex, curveIndex, source) {
  const axis = state.project?.result_layout?.axes?.[axisIndex];
  const curve = axis?.curves?.[curveIndex];
  if (!axis || !curve) return false;
  if (canEditProject()) {
    curve.source = source;
    const overrides = state.resultViewerCurveOverrides;
    if (overrides?.projectId === state.project?.id) {
      delete overrides.sources[resultViewerCurveOverrideKey(axis, curve, axisIndex, curveIndex)];
    }
    return true;
  }
  if (state.resultViewerCurveOverrides?.projectId !== state.project.id) {
    state.resultViewerCurveOverrides = {projectId:state.project.id, sources:{}};
  }
  state.resultViewerCurveOverrides.sources[resultViewerCurveOverrideKey(axis, curve, axisIndex, curveIndex)] = source;
  return true;
}

function resultAxisControlView() {
  // V2.16.6.1: presentation-only state; never persist a fold bit into ProjectSpec
  // or an archived named coordinate layout. Keep each axis's setting through DOM
  // repaints and drag reorder, but reset when switching to another project.
  const projectId = String(state.project?.id || '');
  let view = state.resultAxisControlView;
  if (!view || view.projectId !== projectId) {
    view = {projectId, expandedAxisIds:new Set()};
    state.resultAxisControlView = view;
  }
  const existing = new Set((state.project?.result_layout?.axes || [])
    .map((axis, index) => String(axis.id || `__axis_index_${index}`)));
  for (const key of view.expandedAxisIds) {
    if (!existing.has(key)) view.expandedAxisIds.delete(key);
  }
  return view;
}

function resultAxisColumnCount() {
  return Number(state.ui.results?.axis_columns) === 2 ? 2 : 1;
}

function applyResultAxisColumns() {
  const columns = resultAxisColumnCount();
  const root = $('#resultAxes');
  if (root) root.classList.toggle('result-axes-two', columns === 2);
  $$('[data-axis-columns]').forEach(button => {
    const selected = Number(button.dataset.axisColumns) === columns;
    button.setAttribute('aria-pressed', String(selected));
    button.classList.toggle('active', selected);
  });
  const toggle = $('#axisColumnToggle');
  if (toggle) {
    toggle.setAttribute('aria-checked', String(columns === 2));
    const label = toggle.querySelector('.axis-column-current');
    if (label) label.textContent = columns === 2 ? '双列' : '单列';
  }
}

function setResultAxisColumns(columns) {
  const next = Number(columns) === 2 ? 2 : 1;
  if (resultAxisColumnCount() !== next) {
    uiSet('results.axis_columns', next,
      `仿真结果坐标系改为${next === 2 ? '双列' : '单列'}排列`,
      {persist:canEditProject()});
  }
  applyResultAxisColumns();
  if (!document.querySelector('[data-result-pane="axes"]')?.classList.contains('hidden')) {
    requestAnimationFrame(drawResultAxes);
  }
}

function toggleResultAxisControls(button) {
  const card = button?.closest?.('[data-axis-card]');
  const panel = card?.querySelector('[data-axis-tools-panel]');
  if (!card || !panel) return false;
  const axisKey = card.dataset.axisCard;
  const expanded = resultAxisControlView().expandedAxisIds;
  const willOpen = !expanded.has(axisKey);
  if (willOpen) expanded.add(axisKey); else expanded.delete(axisKey);
  panel.hidden = !willOpen;
  panel.classList.toggle('hidden', !willOpen);
  button.setAttribute('aria-expanded', String(willOpen));
  button.title = willOpen ? '收起此坐标系的曲线与运算设置' : '展开此坐标系的曲线与运算设置';
  const text = button.querySelector('.axis-tools-toggle-label');
  if (text) text.textContent = '设置';
  return true;
}

function renderResultViewer() {
  const root = $('#resultAxes');
  if (!root || !state.project) return;
  if (typeof reconcileActiveDistanceLayout === 'function') reconcileActiveDistanceLayout();
  if (typeof snapshotActiveResultLayout === 'function') snapshotActiveResultLayout();
  renderResultLayoutControls();
  const axes = state.project.result_layout?.axes || [];
  const expanded = resultAxisControlView().expandedAxisIds;
  const sources = resultSourceCatalog();
  const sourceOptions = selected => {
    const groups = [['joint','关节类'], ['drive','驱动类'], ['pair','测距类']];
    const prompt = sources.length ? '选择曲线对象' : (state.resultAutoSimulationPending ? '后台仿真中…' : '暂无曲线数据');
    // Newly configured pairs can exist in ProjectSpec before a fresh frozen
    // simulation is available. Show the chosen pair without claiming that its
    // measurements are ready or offering stale trajectory data as a valid hit.
    const pendingPair = String(selected || '').startsWith('pair:')
      ? (state.project?.distance_pairs || []).find(pair => `pair:${pair.id}` === selected) : null;
    const missingSelected = selected && !sources.some(item => item.key === selected)
      ? `<option value="${esc(selected)}" selected>${esc(pendingPair ? `${pendingPair.name || pendingPair.id}（按 Enter 更新结果）` : '数据源暂不可用')}</option>`
      : '';
    return `<option value="">${prompt}</option>${missingSelected}${groups.map(([key,label]) => `<optgroup label="${label}">${sources.filter(item => item.group === key).map(item => `<option value="${esc(item.key)}" ${item.key === selected ? 'selected' : ''}>${esc(item.label)}</option>`).join('')}</optgroup>`).join('')}`;
  };
  root.classList.toggle('empty-state', !axes.length);
  applyResultAxisColumns();
  root.innerHTML = axes.length ? axes.map((axis, ai) => {
    const axisKey = String(axis.id || `__axis_index_${ai}`);
    const isOpen = expanded.has(axisKey);
    const legacySum = (axis.curves || []).some(curve => curve.operation === 'sum');
    const combine = axis.combine || (legacySum ? 'sum' : 'none');
    const operands = (axis.curves || []).map((curve, ci) => ({curve,ci})).filter(item => item.curve.operation !== 'sum');
    const chosenLabel = (curve, ci) => sources.find(item => item.key === effectiveResultCurveSource(axis, curve, ai, ci))?.label || curve.label || '未选择';
    return `<article class="result-axis-card" data-axis-card="${esc(axisKey)}">
      <div class="result-axis-head">
        <button type="button" class="axis-drag-handle button tiny ghost" data-axis-drag="${esc(axis.id)}" draggable="${canEditProject()}" aria-label="拖拽或用上下方向键调整坐标系顺序" title="拖拽排序；聚焦后上下方向键排序">⠿</button>
        <label class="axis-name-field"><input data-bind="result_layout.axes.${ai}.name" value="${esc(axis.name)}" aria-label="坐标系名称" title="编辑坐标系名称"><span class="axis-name-readonly" title="${esc(axis.name)}">${esc(axis.name)}</span></label>
        <div class="axis-head-curves" role="group" aria-label="${esc(axis.name)}的曲线对象">
          ${operands.length ? operands.map(({curve,ci}) => `<select class="axis-source-select" title="曲线 ${ci + 1}：${esc(chosenLabel(curve,ci))}" aria-label="曲线对象 ${ci + 1}" data-result-curve-source data-axis="${ai}" data-curve="${ci}" data-bind="result_layout.axes.${ai}.curves.${ci}.source">${sourceOptions(effectiveResultCurveSource(axis, curve, ai, ci))}</select>`).join('') : '<span class="axis-no-curves">未添加曲线</span>'}
          <small class="distance-curve-status" data-axis-distance-status="${ai}" aria-live="polite"></small>
        </div>
        <button type="button" class="axis-tools-toggle button tiny ghost" data-action="toggle-result-axis-tools" data-axis="${ai}" aria-controls="result-axis-tools-${ai}" aria-expanded="${isOpen}" title="${isOpen ? '收起' : '展开'}曲线配置与添加曲线"><span class="axis-tools-toggle-label">设置</span><span class="axis-tools-chevron" aria-hidden="true">⌄</span></button>
        <button type="button" class="compact-delete axis-remove-button" data-action="remove-result-axis" data-axis="${ai}" aria-label="删除坐标系 ${esc(axis.name)}" title="删除此坐标系（仅此按钮）">×</button>
      </div>
      <div class="axis-tools-panel ${isOpen ? '' : 'hidden'}" id="result-axis-tools-${ai}" data-axis-tools-panel ${isOpen ? '' : 'hidden'}>
        <div class="axis-tools-row axis-tools-curves-row">
          <span class="axis-tools-row-caption">曲线设置</span>
          <div class="axis-curve-settings">${operands.map(({curve,ci}) => `<span class="axis-curve-settings-item">
            <input class="curve-color" type="color" data-bind="result_layout.axes.${ai}.curves.${ci}.color" value="${esc(curve.color || '#2563eb')}" title="曲线 ${ci+1} 颜色" aria-label="曲线 ${ci+1} 颜色">
            <span class="axis-curve-settings-name" title="${esc(chosenLabel(curve,ci))}">${esc(chosenLabel(curve,ci))}</span>
            <select title="曲线 ${ci+1} 原值 / 运算" aria-label="曲线 ${ci+1} 运算" data-bind="result_layout.axes.${ai}.curves.${ci}.operation"><option value="raw" ${curve.operation === 'raw' ? 'selected' : ''}>原值</option><option value="integral" ${curve.operation === 'integral' ? 'selected' : ''}>积分</option><option value="d1" ${curve.operation === 'd1' ? 'selected' : ''}>速度</option><option value="d2" ${curve.operation === 'd2' ? 'selected' : ''}>加速度</option><option value="d3" ${curve.operation === 'd3' ? 'selected' : ''}>三阶导</option></select>
            <button type="button" class="button tiny ghost axis-curve-delete" data-action="remove-result-curve" data-axis="${ai}" data-curve="${ci}" aria-label="删除曲线 ${ci + 1}" title="删除此曲线">删曲线</button>
          </span>`).join('') || '<span class="axis-no-curves">尚无曲线</span>'}</div>
          <button type="button" class="button tiny ghost axis-add-curve" data-action="add-result-curve" data-axis="${ai}">＋ 添加曲线</button>
        </div>
        <div class="axis-tools-row axis-tools-options-row">
          <button type="button" class="button tiny ghost" data-action="adaptive-result-axis-name" data-axis="${ai}" title="用当前所选曲线名称填充坐标系名称">自适应名称</button>
          <label class="axis-combine axis-combine-inline">运算<select data-bind="result_layout.axes.${ai}.combine"><option value="none" ${combine === 'none' ? 'selected' : ''}>无</option><option value="sum" ${combine === 'sum' ? 'selected' : ''}>求和</option><option value="difference" ${combine === 'difference' ? 'selected' : ''}>求差</option></select></label>
          <label class="inline-check result-keep-check"><input type="checkbox" data-bind="result_layout.axes.${ai}.keep_operands" ${axis.keep_operands ? 'checked' : ''}>保留</label>
          <label class="inline-check axis-add-gantt" title="将此坐标系内的曲线按位移变化区间加入甘特图"><input type="checkbox" data-bind="result_layout.axes.${ai}.add_to_gantt" ${axis.add_to_gantt ? 'checked' : ''}>加入甘特图</label>
          <span class="result-axis-actions"><button type="button" class="button tiny ghost" data-action="export-result-axis" data-axis="${ai}">CSV</button></span>
        </div>
      </div>
      <canvas class="result-axis-canvas" data-result-axis="${ai}" tabindex="0" aria-label="${esc(axis.name)}；可拖动游标，左右方向键逐点移动" height="${state.project.result_layout.height || 80}"></canvas>
    </article>`;
  }).join('') : '尚未配置坐标系；点击右上角“＋ 坐标系”开始。';
  requestAnimationFrame(updateDistanceCurveStatus);
  if (!document.querySelector('[data-result-pane="axes"]')?.classList.contains('hidden')) {
    requestAnimationFrame(drawResultAxes);
  }
}

function validResultNumber(value) {
  if (value === null || value === undefined || value === '') return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function derivative(values, times) {
  return values.map((value, index) => {
    if (values.length < 2) return null;
    const left = Math.max(0, index - 1), right = Math.min(values.length - 1, index + 1);
    const a = validResultNumber(values[left]), b = validResultNumber(values[right]);
    const dt = Number(times[right]) - Number(times[left]);
    return a !== null && b !== null && Number.isFinite(dt) && dt > 0 ? (b - a) / dt : null;
  });
}

function transformResultValues(values, times, operation) {
  let result = values.map(validResultNumber);
  if (operation === 'integral') {
    if (!result.length) return [];
    const integrated = [result[0] === null ? null : 0];
    let total = 0;
    for (let index = 1; index < result.length; index++) {
      const dt = Number(times[index]) - Number(times[index - 1]);
      if (result[index - 1] === null || result[index] === null || !Number.isFinite(dt) || dt <= 0) {
        integrated.push(null); // A missing measurement is never treated as 0 mm.
      } else {
        total += .5 * (result[index - 1] + result[index]) * dt;
        integrated.push(total);
      }
    }
    return integrated;
  }
  const order = {d1:1, d2:2, d3:3}[operation] || 0;
  for (let count = 0; count < order; count++) result = derivative(result, times);
  return result;
}

function transformedUnit(unit, operation) {
  const displayUnit = value => String(value || '').replace(/deg/gi, '°');
  if (operation === 'integral') return displayUnit(unit ? `${unit}·s` : 's');
  const order = {d1:1, d2:2, d3:3}[operation] || 0;
  return displayUnit(order && unit ? `${unit}/s${order > 1 ? `^${order}` : ''}` : unit);
}

function resolvedAxisCurves(axis, axisIndex = null) {
  const catalog = new Map(resultSourceCatalog().map(item => [item.key, item]));
  const times = (state.latestSimulation?.times || []).map(Number);
  const ordinary = (axis.curves || []).map((curve, curveIndex) => ({curve, curveIndex})).filter(item => item.curve.operation !== 'sum').map(({curve, curveIndex}) => {
    const source = catalog.get(effectiveResultCurveSource(axis, curve, axisIndex, curveIndex));
    return {show_minimum:source?.group === 'pair' && curve.operation === 'raw', label:source?.label || '曲线', color:curve.color || '#2563eb', unit:transformedUnit(source?.unit || '', curve.operation), values:source ? transformResultValues(source.values || [], times, curve.operation) : []};
  });
  const legacySum = (axis.curves || []).some(curve => curve.operation === 'sum');
  const combine = axis.combine || (legacySum ? 'sum' : 'none');
  if (combine === 'none' || !ordinary.length) return {times, curves:ordinary};
  const length = Math.max(0, ...ordinary.map(item => item.values.length));
  const values = Array.from({length}, (_, index) => {
    const operands = ordinary.map(item => validResultNumber(item.values[index]));
    if (operands.some(value => value === null)) return null;
    return combine === 'sum' ? operands.reduce((sum, value) => sum + value, 0)
      : operands.slice(1).reduce((value, item) => value - item, operands[0]);
  });
  const combined = {label:`${axis.name || '坐标系'}${combine === 'sum' ? ' · 求和' : ' · 求差'}`, color:'#253247', unit:ordinary.every(item => item.unit === ordinary[0].unit) ? ordinary[0].unit : '', values};
  return {times, curves:axis.keep_operands ? [...ordinary, combined] : [combined]};
}

function curveMotionIntervals(times, values) {
  const intervals = [];
  let active = null;
  for (let index = 1; index < times.length; index++) {
    const previousTime = Number(times[index-1]), currentTime = Number(times[index]);
    const previousValue = validResultNumber(values[index-1]), currentValue = validResultNumber(values[index]);
    if (!Number.isFinite(previousTime) || !Number.isFinite(currentTime) || currentTime <= previousTime ||
        previousValue === null || currentValue === null) {
      if (active) intervals.push(active);
      active = null;
      continue;
    }
    if (Math.abs(currentValue - previousValue) > 0) {
      if (!active) active = {start:previousTime, end:currentTime, travel_start:previousValue, travel_end:currentValue};
      else if (Math.abs(active.end - previousTime) <= 1e-8) {
        active.end = currentTime; active.travel_end = currentValue;
      } else {
        intervals.push(active);
        active = {start:previousTime, end:currentTime, travel_start:previousValue, travel_end:currentValue};
      }
    } else if (active) { intervals.push(active); active = null; }
  }
  if (active) intervals.push(active);
  return intervals;
}

function resultCurveGanttSegments() {
  const segments = [];
  (state.project?.result_layout?.axes || []).forEach((axis, axisIndex) => {
    if (!axis.add_to_gantt) return;
    const {times, curves} = resolvedAxisCurves(axis, axisIndex);
    curves.forEach((curve, curveIndex) => {
      const rowId = `result-curve:${axis.id || axisIndex}:${curveIndex}`;
      curveMotionIntervals(times, curve.values).forEach((interval, intervalIndex) => segments.push({
        id:`${rowId}:motion:${intervalIndex + 1}`,
        drive_id:rowId,
        drive_name:`${axis.name || `坐标系${axisIndex + 1}`} · ${curve.label || `曲线${curveIndex + 1}`}`,
        name:`运动段${intervalIndex + 1}`,
        start:interval.start,
        end:interval.end,
        duration:interval.end - interval.start,
        travel:interval.travel_end - interval.travel_start,
        travel_start:interval.travel_start,
        travel_end:interval.travel_end,
        travel_unit:curve.unit || '',
      }));
    });
  });
  return segments;
}

function refreshCombinedGanttSchedule({render=true}={}) {
  state.simulationSchedule = [...(state.baseSimulationSchedule || []), ...resultCurveGanttSegments()];
  if (render) renderSimulationGantt();
}

function drawResultAxes() {
  $$('[data-result-axis]').forEach(canvas => {
    const axis = state.project.result_layout.axes[Number(canvas.dataset.resultAxis)];
    const {times, curves} = resolvedAxisCurves(axis, Number(canvas.dataset.resultAxis));
    // Canvas width/height attributes change intrinsic size; measure the parent
    // rather than feeding the old intrinsic canvas width back into the grid.
    const ratio = devicePixelRatio || 1;
    const width = Math.max(1, Math.floor(canvas.parentElement?.clientWidth || canvas.clientWidth || 700));
    const height = Number(state.project.result_layout.height || 80);
    canvas.style.width = '100%';
    canvas.style.height = `${height}px`;
    canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio);
    const context = canvas.getContext('2d'); context.setTransform(ratio,0,0,ratio,0,0); context.fillStyle='#ffffff'; context.fillRect(0,0,width,height);
    const plotLeft = 48, plotRight = width - 12, plotTop = 28, plotBottom = height - 28;
    const plotWidth = Math.max(1, plotRight - plotLeft), plotHeight = Math.max(1, plotBottom - plotTop);
    context.strokeStyle = '#e1e6eb'; context.lineWidth = 1;
    for (let row = 0; row <= 4; row++) { const y = plotTop + plotHeight * row / 4; context.beginPath(); context.moveTo(plotLeft,y); context.lineTo(plotRight,y); context.stroke(); }
    for (let column = 0; column <= 4; column++) { const x = plotLeft + plotWidth * column / 4; context.beginPath(); context.moveTo(x,plotTop); context.lineTo(x,plotBottom); context.stroke(); }
    context.strokeStyle = '#35414a'; context.lineWidth = 1.4; context.beginPath(); context.moveTo(plotLeft,plotTop); context.lineTo(plotLeft,plotBottom); context.lineTo(plotRight,plotBottom); context.stroke();
    context.fillStyle='#35414a'; context.font='10px "Microsoft YaHei",sans-serif'; context.textAlign='center'; context.fillText('时间 (s)',plotLeft + plotWidth / 2,height - 5);
    context.save(); context.translate(11,plotTop + plotHeight / 2); context.rotate(-Math.PI/2); context.font='700 11px "Microsoft YaHei",sans-serif'; context.fillText(String(axis.name || '坐标系'),0,0); context.restore(); context.textAlign='left';
    const values = curves.flatMap(item => item.values).filter(value => validResultNumber(value) !== null);
    if (!values.length) { context.fillStyle='#607086'; context.fillText('暂无有效曲线值；所选测距对可能正在后台计算', plotLeft + 8, height / 2); return; }
    const low = values.reduce((min, value) => Math.min(min, value), Infinity);
    const high = values.reduce((max, value) => Math.max(max, value), -Infinity);
    const span = Math.max(high - low, 1e-12);
    const firstTime = Number(times[0] ?? 0), lastTime = Number(times.at(-1) ?? firstTime), timeSpan = Math.max(lastTime - firstTime, 1e-12);
    context.fillStyle='#5d6974'; context.font='9px ui-monospace,monospace'; context.textAlign='right';
    [high,(high+low)/2,low].forEach((value,index) => context.fillText(Number(value).toPrecision(4),plotLeft-5,plotTop+plotHeight*index/2+3));
    context.textAlign='center'; [firstTime,(firstTime+lastTime)/2,lastTime].forEach((value,index) => context.fillText(Number(value).toFixed(2),plotLeft+plotWidth*index/2,plotBottom+12)); context.textAlign='left';
    curves.forEach((curve, curveIndex) => {
      context.strokeStyle = curve.color; context.lineWidth = 1.6; context.beginPath();
      let connected = false;
      curve.values.forEach((raw,index) => {
        const value = validResultNumber(raw);
        if (value === null || !Number.isFinite(Number(times[index]))) { connected = false; return; }
        const x = plotLeft + plotWidth * (Number(times[index]) - firstTime) / timeSpan;
        const y = plotBottom-plotHeight*(value-low)/span;
        if (connected) context.lineTo(x,y); else context.moveTo(x,y);
        connected = true;
      }); context.stroke();
      context.fillStyle=curve.color; context.font='10px "Microsoft YaHei",sans-serif'; context.fillText(`${curve.label}${curve.unit ? ` · ${curve.unit}` : ''}`, plotLeft + 6, 13 + curveIndex * 13);
    });
    curves.forEach(curve => {
      if (!curve.show_minimum) return;
      let minimum = null, minimumIndex = -1;
      curve.values.forEach((raw, index) => {
        const value = validResultNumber(raw);
        if (value !== null && Number.isFinite(Number(times[index])) && (minimum === null || value < minimum)) {
          minimum = value; minimumIndex = index;
        }
      });
      if (minimumIndex < 0) return;
      const time = Number(times[minimumIndex]);
      const x = plotLeft + plotWidth * (time - firstTime) / timeSpan;
      const y = plotBottom - plotHeight * (minimum - low) / span;
      const label = `min (${time.toFixed(3)} s, ${minimum.toFixed(3)} ${curve.unit || ''})`;
      context.fillStyle = curve.color; context.beginPath(); context.arc(x,y,3.5,0,Math.PI*2); context.fill();
      context.font = '10px ui-monospace,monospace'; context.textAlign = 'left';
      const labelWidth = context.measureText(label).width;
      const labelX = Math.max(plotLeft + 3, Math.min(x + 6, plotRight - labelWidth - 3));
      const labelY = Math.max(plotTop + 11, Math.min(y - 6, plotBottom - 3));
      context.fillStyle = 'rgba(255,255,255,.92)'; context.fillRect(labelX - 2,labelY - 10,labelWidth + 4,13);
      context.fillStyle = curve.color; context.fillText(label,labelX,labelY);
    });
    (state.project.result_layout.cursor_times || []).forEach((time,index) => {
      const x = plotLeft + plotWidth * (Number(time)-firstTime) / timeSpan;
      context.strokeStyle=['#ff4d4f','#1677ff','#52c41a','#722ed1','#fa8c16'][index % 5]; context.lineWidth=1.2;
      context.beginPath(); context.moveTo(x,plotTop); context.lineTo(x,plotBottom); context.stroke();
      context.fillStyle=context.strokeStyle; context.font='700 11px "Microsoft YaHei",sans-serif';
      const sampleIndex = times.length ? times.reduce((best,value,candidate) => Math.abs(Number(value)-Number(time)) < Math.abs(Number(times[best])-Number(time)) ? candidate : best, 0) : 0;
      context.fillText(`${Number(time).toFixed(3)}s`,Math.min(x+3,width-58),height-5);
      curves.forEach((curve,labelIndex) => {
        const value = validResultNumber(curve.values[sampleIndex]); if (value === null) return;
        const y = plotBottom - plotHeight * (value - low) / span;
        const label = `${value.toFixed(3)}${curve.unit || ''}`;
        context.font='700 12px "Microsoft YaHei",sans-serif';
        const labelWidth=context.measureText(label).width;
        const labelX=Math.max(plotLeft+3,Math.min(x+7,plotRight-labelWidth-3));
        const labelY=Math.max(plotTop+13,Math.min(y+(labelIndex%2 ? 15 : -7),plotBottom-3));
        context.fillStyle='rgba(255,255,255,.88)'; context.fillRect(labelX-2,labelY-11,labelWidth+4,14);
        context.fillStyle=curve.color; context.beginPath(); context.arc(x,y,3,0,Math.PI*2); context.fill();
        context.fillText(label,labelX,labelY);
      });
    });
  });
}

async function requestResultSimulationIfEmpty() {
  if (resultSourceCatalog().length || state.resultAutoSimulationPending || !state.project) return;
  state.resultAutoSimulationPending = true;
  renderResultViewer();
  alert('当前没有可选曲线，已自动提交后台仿真。仿真完成后曲线下拉菜单会自动更新。');
  try {
    await saveEditableDraft();
    const result = await api(`/api/projects/${state.project.id}/simulate`, {method:'POST'});
    watchJob(result.job_id, 'simulation');
    toast('结果曲线后台仿真已提交');
  } catch (error) {
    state.resultAutoSimulationPending = false;
    renderResultViewer();
    toast(error.message, 'error');
  }
}

function addResultAxis() {
  const axes = state.project.result_layout.axes;
  const source = resultSourceCatalog().find(item => item.group === 'drive');
  axes.push({id:uid('axis'), name:`坐标系${axes.length + 1}`, combine:'none', keep_operands:false, add_to_gantt:false, curves:source ? [{id:uid('curve'), source:source.key, label:source.label, operation:'raw', color:'#2563eb'}] : []});
  markDirty(); renderResultViewer(); scheduleInteractionCommit();
  if (!source) void requestResultSimulationIfEmpty();
}

function adaptiveAddResultAxes() {
  if (!state.project) return;
  const axes = state.project.result_layout.axes ||= [];
  const drives = state.project.drives || [];
  if (!drives.length) return toast('当前模型没有驱动，无法自适应添加坐标系', 'error');
  const existingDriveSources = new Set();
  axes.forEach((axis, axisIndex) => (axis.curves || []).forEach((curve, curveIndex) => {
    const source = effectiveResultCurveSource(axis, curve, axisIndex, curveIndex);
    if (source.startsWith('drive:')) existingDriveSources.add(source);
  }));
  let added = 0;
  drives.forEach((drive, index) => {
    const source = `drive:${drive.id}`;
    if (existingDriveSources.has(source)) return;
    axes.push({
      id:uid('axis'), name:String(drive.name || `驱动${index + 1}`), combine:'none', keep_operands:false, add_to_gantt:false,
      curves:[{id:uid('curve'), source, label:String(drive.name || drive.id), operation:'raw', color:'#2563eb'}],
    });
    existingDriveSources.add(source);
    added += 1;
  });
  if (!added) return toast('当前所有驱动都已经有对应坐标系');
  markDirty(); renderResultViewer(); refreshCombinedGanttSchedule(); scheduleInteractionCommit();
  toast(`已按驱动自适应添加 ${added} 个同名坐标系`, 'success');
  if (!state.latestSimulation) void requestResultSimulationIfEmpty();
}

function adaptiveResultAxisName(axisIndex) {
  const axis = state.project?.result_layout?.axes?.[axisIndex];
  if (!axis) return;
  const curveIndex = (axis.curves || []).findIndex((curve, curveIndex) => curve.operation !== 'sum' && effectiveResultCurveSource(axis, curve, axisIndex, curveIndex));
  const index = curveIndex >= 0 ? curveIndex : 0;
  const curve = axis.curves?.[index];
  if (!curve) return toast('请先给该坐标系选择一条曲线', 'error');
  const sourceKey = effectiveResultCurveSource(axis, curve, axisIndex, index);
  const catalog = resultSourceCatalog();
  let name = catalog.find(item => item.key === sourceKey)?.label || '';
  if (!name && sourceKey.startsWith('drive:')) name = state.project.drives.find(item => `drive:${item.id}` === sourceKey)?.name || '';
  if (!name && sourceKey.startsWith('pair:')) name = (state.project.distance_pairs || []).find(item => `pair:${item.id}` === sourceKey)?.name || '';
  if (!name && sourceKey.startsWith('joint:')) {
    const jointId = sourceKey.slice(6);
    const layer = state.project.layers.find(item => (item.joints || []).some(joint => joint.id === jointId));
    const joint = layer?.joints?.find(item => item.id === jointId);
    name = joint ? `${layer?.name || '未分层'} / ${joint.name || joint.id}` : '';
  }
  name = String(name || curve.label || '').trim();
  if (!name) return toast('当前所选曲线没有可识别名称', 'error');
  axis.name = name;
  markDirty(); renderResultViewer(); refreshCombinedGanttSchedule(); scheduleInteractionCommit();
}

function addResultCursor() {
  const times = state.latestSimulation?.times || [];
  if (!times.length) return toast('请先运行仿真再添加游标', 'error');
  const cursors = state.project.result_layout.cursor_times ||= [];
  if (cursors.length >= 5) return toast('最多显示 5 个游标', 'error');
  const start = Number(times[0]), end = Number(times.at(-1));
  cursors.push(start + (end - start) * (cursors.length + 1) / (cursors.length + 2));
  if (canEditProject()) { markDirty(); scheduleInteractionCommit(); }
  drawResultAxes();
}

function removeResultCursor() {
  const cursors = state.project.result_layout.cursor_times ||= [];
  if (!cursors.length) return;
  cursors.pop(); if (canEditProject()) { markDirty(); scheduleInteractionCommit(); }
  drawResultAxes();
}

function cursorTimeFromPointer(canvas, event) {
  const times = state.latestSimulation?.times || [];
  const rect = canvas.getBoundingClientRect(), plotLeft = 48, plotRight = 12;
  const ratio = Math.max(0, Math.min(1, (event.clientX - rect.left - plotLeft) / Math.max(rect.width - plotLeft - plotRight, 1)));
  return Number(times[0] || 0) + ratio * (Number(times.at(-1) || 0) - Number(times[0] || 0));
}

function axisCsv(axis) {
  const axisIndex = state.project?.result_layout?.axes?.indexOf(axis) ?? -1;
  const {times, curves} = resolvedAxisCurves(axis, axisIndex);
  const escapeCsv = value => `"${String(value ?? '').replaceAll('"','""')}"`;
  const rows = [["time_s", ...curves.map(item => item.label)], ...times.map((time,index) => [time, ...curves.map(item => item.values[index] ?? '')])];
  return '\ufeff' + rows.map(row => row.map(escapeCsv).join(',')).join('\r\n');
}

async function downloadCsv(filename, content) {
  return saveBlobToChosenPath(filename,new Blob([content],{type:'text/csv;charset=utf-8'}),'text/csv');
}

async function publishResultAxisTables(files) {
  if (!state.project?.id || state.editSessionMode !== 'persistent' || projectStatus(state.project) === 'baseline') return false;
  await api(`/api/projects/${encodeURIComponent(state.project.id)}/export-axes-csv`, {
    method:'POST', body:JSON.stringify({delivery:true, tables_only:true, files}),
  });
  return true;
}

async function exportResultAxis(index) {
  const axis = state.project.result_layout.axes[index];
  if (!axis) return;
  if (pendingDistancePairSources(axis, index).length) return toast('测距对曲线尚未计算完成，请等待 Viewer 表面测距结束再导出 CSV', 'error');
  if (!resolvedAxisCurves(axis, index).curves.some(item => item.values.length)) return toast('当前坐标系没有可导出的曲线', 'error');
  const filename = `${String(axis.name || `axis_${index+1}`).replace(/[\\/:*?"<>|]+/g,'_')}.csv`;
  const content = axisCsv(axis);
  try {
    const persisted = await publishResultAxisTables([{filename,content,asset_key:String(axis.id || `axis_${index+1}`)}]);
    await downloadCsv(filename,content);
    toast(persisted ? '坐标系 CSV 已保存至交付数据 / 表格文件夹' : '已下载 CSV；只读/临时结果不写回交付数据');
  } catch (error) { toast(`坐标系 CSV 导出失败：${error.message}`, 'error'); }
}

// V2.16.6.2: Only explicit selection-dialog timeline replacement may ask to snapshot
// the current drives. Normal Enter always syncs the active ProjectSpec directly.
let activeLibraryTimeSeries = null;
function serializedDrives() { return JSON.stringify(state.project?.drives || []); }
async function confirmTimeSeriesSwitch({reason='切换时序前', intent=''} = {}) {
  // Never ask during Enter, ordinary edits or an unrelated UI flow.
  // The modal and an explicit replacement intent are both required.
  if (!['new', 'import'].includes(intent) || !$('#timeSeriesImportDialog')?.open) return false;
  if (!state.project?.drives?.length) return true;
  const current = serializedDrives();
  if (activeLibraryTimeSeries?.projectId === state.project.id && current === activeLibraryTimeSeries.snapshot) return true;
  const action = prompt(`${reason}，是否保存当前编辑内容？\n输入 1：保存为新时序\n输入 2：覆盖已有时序\n输入 3：不单独保存时序，继续\n点击取消：继续编辑`, '1');
  if (action === null) return false;
  if (action.trim() === '3') return true;
  if (action.trim() !== '1' && action.trim() !== '2') { toast('请输入 1、2 或 3', 'error'); return false; }
  let overwriteFilename = '', suggestedName = '';
  if (action.trim() === '2') {
    const files = await api(`/api/projects/${encodeURIComponent(state.project.id)}/files`);
    const items = (files.time_series_library || []).filter(item => item.kind === 'tsjson');
    if (!items.length) { toast('时序库为空，请选择保存为新时序', 'error'); return false; }
    const selection = prompt('输入要覆盖的时序序号：\n' + items.map((item, idx) => `${idx+1}. ${item.name}`).join('\n'), '1');
    if (selection === null) return false;
    const target = items[Number(selection)-1];
    if (!target) { toast('所选时序不存在', 'error'); return false; }
    if (!confirm(`确认覆盖“${target.name}”？原有内容将被替换，无法撤销。`)) return false;
    overwriteFilename = target.name;
    suggestedName = target.name.replace(/--\d{8}_\d{6}_\d{6}_[a-f0-9]{6}\.tsjson$/i,'').replace(/\.tsjson$/i,'');
  } else {
    const value = prompt('请输入新时序名称', `${state.project.name || '模型'} · 新时序`);
    if (value === null) return false;
    suggestedName = value.trim();
  }
  if (!suggestedName) return false;
  return await saveCurrentTimeSeriesToLibrary({overwriteFilename,suggestedName});
}
async function applyTimeSeriesImport(requestPayload) {
  if (!state.project || !canEditProject() || state.editSessionMode !== 'persistent')
    return toast('项目只读，请先签出再导入时序文件', 'error');
  if (!$('#timeSeriesImportDialog')?.open) return false;
  if (state.enterCommitRunning) return toast('正在同步当前时序，请完成后再切换', 'error');
  const projectId = state.project.id;
  const parseUrl = `/api/projects/${encodeURIComponent(projectId)}/time-series/parse`;
  const fetchParse = payload => api(parseUrl, {method:'POST', body:JSON.stringify(payload)});
  let parsed = await fetchParse(requestPayload);
  if (parsed.unresolved?.length) {
    const mapping = {...(requestPayload.joint_mapping || {})};
    for (const missing of parsed.unresolved) {
      const options = missing.joint_candidates || [];
      const choice = prompt(`历史驱动“${missing.name}”无法唯一定位运动副。\n请选择编号（取消则停止整个导入）：\n` +
        options.map((j, i) => `${i+1}. ${j.name} [${j.id}]`).join('\n'), '');
      if (choice === null) return;
      const target = options[Number(choice)-1];
      if (!target) { toast('运动副映射编号无效，已取消导入', 'error'); return; }
      mapping[missing.name] = target.id;
    }
    parsed = await fetchParse({...requestPayload, joint_mapping:mapping});
    if (parsed.unresolved?.length) throw new Error('仍有运动副无法映射，已取消导入以免丢失时序');
  }
  const drives = Array.isArray(parsed.drives) ? parsed.drives : [];
  if (!drives.length) throw new Error('所选时序文件没有可导入驱动');
  const warningText = (parsed.warnings || []).slice(0,8).join('\n');
  const message = `将用“${parsed.filename || '时序文件'}”中的 ${drives.length} 个驱动替换当前驱动配置。${warningText ? `\n\n注意：\n${warningText}` : ''}\n\n是否继续？`;
  if (state.project?.id !== projectId || !canEditProject()) return false;
  if (parsed.lossy && !confirm('这是从旧数据重建的时序，可能不包含原始缓起缓停、映射曲线。导入后请逐段检查，再保存为 TSJSON。\n\n是否接受这些限制？')) return false;
  if (!confirm(message)) return false;
  // Parse and approve the replacement before asking whether to archive the old
  // timeline. An invalid file or a cancelled preview never triggers a save.
  if (!await confirmTimeSeriesSwitch({reason:'导入其他时序前', intent:'import'})) return false;
  if (state.project?.id !== projectId || !canEditProject() || !$('#timeSeriesImportDialog')?.open) return false;
  state.project.drives = drives;
  activeLibraryTimeSeries = {projectId:state.project.id, filename:requestPayload.server_filename || requestPayload.filename || '', snapshot:serializedDrives()};
  state.mappingTables = {};
  state.companionTravels.clear();
  state.expandedSegments.clear();
  hierarchyDiagramSyncAllClosurePassiveJoints();
  markDirty();
  renderDrives();
  await commitCurrentStep('已从时序文件生成驱动配置', true);
  $('#timeSeriesImportDialog')?.close();
  toast(`已导入 ${drives.length} 个驱动；运动段与伴生映射已恢复`, 'success');
}


async function createBlankTimeSeries() {
  if (!state.project || !canEditProject() || state.editSessionMode !== 'persistent')
    return toast('项目只读，请先签出再新建时序', 'error');
  if (!$('#timeSeriesImportDialog')?.open) return false;
  if (state.enterCommitRunning) return toast('正在同步当前时序，请完成后再新建', 'error');
  const projectId = state.project.id;
  if (!await confirmTimeSeriesSwitch({reason:'新建空白时序前', intent:'new'})) return false;
  if (state.project?.id !== projectId || !canEditProject() || !$('#timeSeriesImportDialog')?.open) return false;
  if (!state.project.drives?.length) {
    $('#timeSeriesImportDialog')?.close();
    toast('当前已是空白时序，可以直接添加驱动', 'success');
    return true;
  }
  // ProjectSpec.drives is the one active timeline; the old named TSJSON
  // remains in the library only if the user elected to save it.
  state.project.drives = [];
  activeLibraryTimeSeries = null;
  state.mappingTables = {};
  state.companionTravels.clear();
  state.expandedSegments.clear();
  hierarchyDiagramSyncAllClosurePassiveJoints();
  markDirty();
  renderDrives();
  await commitCurrentStep('已新建空白时序', true);
  $('#timeSeriesImportDialog')?.close();
  toast('已新建空白时序；后续编辑仍在当前模型同步', 'success');
  return true;
}

async function saveCurrentTimeSeriesToLibrary({overwriteFilename = "", suggestedName = ""} = {}) {
  if (!state.project?.id || !canEditProject() || state.editSessionMode !== 'persistent')
    return toast('请先签出模型，再保存正式时序', 'error');
  const input = $('#timeSeriesSaveName');
  const name = String(suggestedName || input?.value || '').trim();
  if (!name) { input?.focus(); return toast('请填写要保存的时序名称', 'error'); }
  const button = $('#timeSeriesSaveCurrentButton');
  if (button?.disabled) return;
  if (button) button.disabled = true;
  const projectId = state.project.id;
  try {
    await syncLocalDraft({quiet:true});
    if (state.project?.id !== projectId) throw new Error('模型已切换，取消保存');
    const saved = await api(`/api/projects/${encodeURIComponent(projectId)}/time-series/save`, {
      method:'POST',body:JSON.stringify({name, overwrite_filename:overwriteFilename}),
    });
    activeLibraryTimeSeries = {projectId, filename:saved.filename || overwriteFilename, snapshot:serializedDrives()};
    if (input) input.value = '';
    toast(`时序“${name}”已保存为 TSJSON（${saved.drive_count} 个驱动）`, 'success');
    await loadTimeSeriesLibraryChoices(projectId);
    if (saved.vz_sync?.error) toast(`TSJSON 已保存，VZ 同步失败：${saved.vz_sync.error}`, 'error');
  } catch (error) { toast(`保存时序失败：${error.message}`, 'error'); return false; }
  finally { if (button) button.disabled = false; }
  return true;
}

// Every asynchronous inventory response is scoped to this modal visit; a slow
// source request cannot repaint a newer model's time-series list.
let timeSeriesLibraryLoadRevision = 0;
async function loadTimeSeriesLibraryChoices(sourceId = state.project?.id) {
  const targetId = state.project?.id;
  const selector = $('#timeSeriesSourceProject');
  const list = $('#timeSeriesServerList');
  if (!sourceId || !targetId || !list || !selector) return;
  const revision = ++timeSeriesLibraryLoadRevision;
  list.innerHTML = '<p class="empty-state">正在读取时序库…</p>';
  try {
    const files = await api(`/api/projects/${encodeURIComponent(sourceId)}/files`);
    if (revision !== timeSeriesLibraryLoadRevision || state.project?.id !== targetId ||
        !$('#timeSeriesImportDialog')?.open || selector.value !== sourceId) return;
    const items = (files.time_series_library || []).filter(item => item.kind === 'tsjson');
    list.innerHTML = items.length ? items.map(item => {
      const title = String(item.name || '').replace(/--\d{8}_\d{6}_\d{6}_[a-f0-9]{6}\.tsjson$/i, '').replace(/\.tsjson$/i, '');
      return `<button type="button" class="time-series-server-item" data-time-series-server="${esc(item.name)}"><span><b title="${esc(item.name)}">${esc(title)}</b><small>${formatBytes(item.size || 0)} · ${esc(formatSavedTime(item.modified))}</small></span><em>替换</em></button>`;
    }).join('') : '<p class="empty-state">所选模型暂无 TSJSON 时序。请切换模型或导入本地文件。</p>';
    $$('[data-time-series-server]', list).forEach(button => button.onclick = async () => {
      if (selector.value !== sourceId || revision !== timeSeriesLibraryLoadRevision) return;
      try { await applyTimeSeriesImport({server_filename:button.dataset.timeSeriesServer,
        ...(sourceId !== targetId ? {source_project_id:sourceId} : {})}); }
      catch (error) { toast(error.message, 'error'); }
    });
  } catch (error) {
    if (revision === timeSeriesLibraryLoadRevision && selector.value === sourceId)
      list.innerHTML = `<p class="empty-state">读取失败：${esc(error.message)}</p>`;
  }
}

async function openTimeSeriesImportDialog() {
  if (!state.project) return;
  if (!canEditProject()) return toast('项目只读，请先签出再导入时序文件', 'error');
  const dialog = $('#timeSeriesImportDialog');
  const selector = $('#timeSeriesSourceProject');
  if (!dialog || !selector) return;
  const targetId = state.project.id;
  dialog.showModal();
  selector.innerHTML = `<option value="${esc(targetId)}">当前模型 · ${esc(state.project.name)}</option>`;
  selector.value = targetId;
  selector.onchange = () => loadTimeSeriesLibraryChoices(selector.value);
  await loadTimeSeriesLibraryChoices(targetId);
  try {
    const projects = await api('/api/projects?detail=summary', {timeout:12000});
    if (!dialog.open || state.project?.id !== targetId) return;
    const previous = selector.value;
    const others = (Array.isArray(projects) ? projects : []).filter(item => item.id && item.id !== targetId);
    others.sort((a,b) => String(a.name || '').localeCompare(String(b.name || ''),'zh-CN'));
    selector.innerHTML = `<option value="${esc(targetId)}">当前模型 · ${esc(state.project.name)}</option>` +
      others.map(item => `<option value="${esc(item.id)}">${esc(item.category || '根目录')} / ${esc(item.name || item.id)}</option>`).join('');
    selector.value = previous;
    if (!selector.value) selector.value = targetId;
  } catch (error) {
    if (dialog.open && state.project?.id === targetId)
      toast(`其他模型列表暂不可用：${error.message}`, 'info');
  }
}

async function importTimeSeriesSingleFile(files) {
  const file = [...(files || [])][0];
  if (!file) return;
  if (!/\.(tsjson|csv|html|py)$/i.test(file.name)) return toast('请选择 TSJSON、CSV、HTML 或 Python 文件', 'error');
  await applyTimeSeriesImport({filename:file.name, content:await file.text()});
}

async function importTimeSeriesLocalFolder(files) {
  const candidates = [...(files || [])].filter(file => /\.(tsjson|csv|html|py)$/i.test(file.name) && !file.name.endsWith('映射表格.csv'));
  if (!candidates.length) return toast('所选文件夹中没有 TSJSON、CSV、HTML 或 Python 时序文件', 'error');
  const inspected = await Promise.all(candidates.map(async file => {
    const header = (await file.slice(0, /\.html$/i.test(file.name) ? 1048576 : 4096).text()).replace(/^\uFEFF/, '').trimStart();
    return /\.tsjson$/i.test(file.name) ? (header.startsWith('{') && header.includes('mujoco_studio_time_series') ? file : null)
      : /\.html$/i.test(file.name) ? (header.includes('const DATA=') && header.includes('ganttRows') ? file : null)
      : /\.py$/i.test(file.name) ? (header.includes('MUJOCO_TIMING_JSON') ? file : null)
      : (header.startsWith('VZ_TIME_SERIES,1.0') ? file : null);
  }));
  const supported = inspected.filter(Boolean);
  if (!supported.length) return toast('未找到可识别的时序文件（Python 需 MUJOCO_TIMING_JSON 标记）', 'error');
  supported.sort((a,b)=>Number(/\.tsjson$/i.test(b.name))-Number(/\.tsjson$/i.test(a.name)) ||
    (Number(b.lastModified)||0)-(Number(a.lastModified)||0)||a.name.localeCompare(b.name,'zh-CN'));
  const selected = supported[0];
  if (supported.length > 1 && !confirm(`检测到 ${supported.length} 个可导入文件，将优先导入：\n${selected.name}\n\n是否继续？`)) return;
  const content = await selected.text();
  await applyTimeSeriesImport({filename:selected.name,content});
}

function pendingDistancePairSources(axis, axisIndex) {
  const session = currentDistanceCurveSession();
  return (axis?.curves || []).map((curve, curveIndex) =>
    effectiveResultCurveSource(axis, curve, axisIndex, curveIndex))
    .filter(key => key.startsWith('pair:'))
    .filter(key => session?.loaded[key.slice(5)]?.status !== 'ready');
}

function exportableResultAxes() {
  return state.project.result_layout.axes
    .map((axis,index)=>({axis,index,resolved:resolvedAxisCurves(axis,index)}))
    .filter(item=>item.resolved.curves.some(curve=>curve.values.length));
}

function openCsvExportModeDialog() {
  const items=exportableResultAxes();
  if(!items.length)return toast('当前界面没有可导出的坐标系','error');
  const dialog=$('#csvExportModeDialog');
  if(!dialog)return exportAllResultAxes('separate');
  $('#csvExportModeCount').textContent=`当前可导出 ${items.length} 个坐标系`;
  dialog.showModal();
}

function mergedResultAxesCsv(items) {
  const names = new Map();
  const sources = items.map(({axis, resolved}) => {
    const basicName = String(axis.name || '坐标系');
    const count = (names.get(basicName) || 0) + 1;
    names.set(basicName, count);
    const name = count === 1 ? basicName : `${basicName} (${count})`;
    const curves = resolved.curves || [];
    const chosen = (axis.combine === 'sum' || axis.combine === 'difference')
      ? curves.at(-1) : curves.find(curve => (curve.values || []).length);
    const series = new Map();
    (resolved.times || []).forEach((time,index) => {
      const numeric = Number(time);
      if (!Number.isFinite(numeric)) return;
      const raw = chosen?.values?.[index];
      const value = raw === null || raw === undefined || raw === '' ? '' : Number(raw);
      series.set(numeric, value === '' || Number.isFinite(value) ? value : '');
    });
    return {name, series};
  });
  const times = [...new Set(sources.flatMap(source => [...source.series.keys()]))].sort((a,b) => a-b);
  const escapeCsv = value => `"${String(value ?? '').replaceAll('"','""')}"`;
  return '\ufeff' + [['time', ...sources.map(source => source.name)],
    ...times.map(time => [time, ...sources.map(source => source.series.get(time) ?? '')])]
      .map(row => row.map(escapeCsv).join(',')).join('\r\n') + '\r\n';
}

async function exportResultAxesTable() {
  const items = exportableResultAxes();
  if (!items.length) return toast('当前界面没有可导出的坐标系', 'error');
  if (items.some(({axis,index}) => pendingDistancePairSources(axis,index).length))
    return toast('测距对尚未全部计算完成，请等待结果就绪再导出表格', 'error');
  // Use the same time/value selection as the existing combined CSV. TSV is
  // directly readable by Excel and does not rely on third-party XLSX packages.
  const csv = mergedResultAxesCsv(items).replace(/^\ufeff/, '');
  const rows = [];
  let fields = [], value = '', inQuotes = false;
  for (let i = 0; i < csv.length; i++) {
    const char = csv[i];
    if (char === '"') {
      if (inQuotes && csv[i + 1] === '"') { value += '"'; i++; }
      else inQuotes = !inQuotes;
    } else if (!inQuotes && char === ',') { fields.push(value); value = ''; }
    else if (!inQuotes && (char === '\r' || char === '\n')) {
      if (char === '\r' && csv[i + 1] === '\n') i++;
      fields.push(value); rows.push(fields); fields = []; value = '';
    } else value += char;
  }
  if (fields.length || value) { fields.push(value); rows.push(fields); }
  const safeCell = entry => {
    const text = String(entry ?? '').replace(/[\t\r\n]+/g, ' ');
    // Prevent spreadsheet formula injection when the export is opened in Excel.
    return /^[=+@-]/.test(text.trimStart()) && !/^-?\d+(?:\.\d+)?(?:e[+-]?\d+)?$/i.test(text.trim())
      ? "'" + text : text;
  };
  const content = '\ufeff' + rows.map(row => row.map(safeCell).join('\t')).join('\r\n') + '\r\n';
  const stem = String(state.project?.name || '坐标系结果').replace(/[\\/:*?"<>|]+/g, '_').slice(0, 90) || '坐标系结果';
  const filename = `${stem}_坐标系表格.tsv`;
  try {
    if (state.editSessionMode === 'persistent' && projectStatus(state.project) !== 'baseline') {
      await api(`/api/projects/${encodeURIComponent(state.project.id)}/export-axes-csv`, {
        method:'POST', body:JSON.stringify({delivery:true, tables_only:true,
          files:[{filename,content,asset_key:'all'}]}),
      });
    }
    await writeBlobToChosenHandle({kind:'browser-download', suggestedName:filename,
      mimeType:'text/tab-separated-values'},
      new Blob([content],{type:'text/tab-separated-values;charset=utf-8'}),filename,true);
    toast(`已导出 ${items.length} 个坐标系的合并表格（TSV，可直接用 Excel 打开）`, 'success');
  } catch (error) { toast(`导出表格失败：${error.message}`, 'error'); }
}

async function publishResultAxesTimeSeries(mergedContent) {
  if(!state.project?.id || state.editSessionMode!=='persistent' || projectStatus(state.project)==='baseline') {
    return {published:false,error:'当前为临时/基线只读上下文，不能更新正式时序库',timeSeries:null};
  }
  try {
    const response = await api(`/api/projects/${encodeURIComponent(state.project.id)}/export-axes-csv`,{
      method:'POST',body:JSON.stringify({delivery:true,
        files:[{filename:'合并结果.csv',content:mergedContent}]}),
    });
    return {published:true,error:'',timeSeries:response.time_series||null};
  } catch(error) {
    return {published:false,error:error.message||String(error),timeSeries:null};
  }
}

async function exportAllResultAxes(mode='separate') {
  const items=exportableResultAxes();
  if(!items.length)return toast('当前界面没有可导出的坐标系','error');
  if (items.some(({axis,index}) => pendingDistancePairSources(axis,index).length))
    return toast('所选坐标系含有未完成的测距对，请等待后台测距完成再批量导出', 'error');
  const files=items.map(({axis,index})=>({
    filename:`${String(axis.name||`axis_${index+1}`).replace(/[\/:*?"<>|]+/g,'_')}.csv`,
    content:axisCsv(axis),
    asset_key:String(axis.id || `axis_${index+1}`),
  }));
  if(mode==='combined') {
    const content=mergedResultAxesCsv(items);
    const readonly = state.editSessionMode !== 'persistent' || projectStatus(state.project) === 'baseline';
    const result=readonly ? {published:false, error:'readonly', timeSeries:null} : await publishResultAxesTimeSeries(content);
    if(!result.published && !readonly) return toast(`合并导出失败：${result.error}`,'error');
    const filename=result.timeSeries?.merged_filename || '合并结果.csv';
    try {
      await writeBlobToChosenHandle({kind:'browser-download',suggestedName:filename,mimeType:'text/csv'},
        new Blob([content],{type:'text/csv;charset=utf-8'}),filename,true);
    } catch(error) {
      return toast(`CSV 已保存交付数据，但本地下载失败：${error.message}`,'error');
    }
    const vz=result.timeSeries?.vz_sync;
    toast(readonly ? '已下载合并 CSV；只读/临时模型不修改冻结交付数据' :
      `合并 CSV 已保存到交付数据 / 表格文件夹，TSJSON 已写入时序库${vz?.error?`；VZ 同步失败：${vz.error}`:vz?.synced?'；VZ 已同步':''}`,'success');
    return;
  }
  let persisted = false;
  try {
    persisted = await publishResultAxisTables(files);
  } catch(error) {
    toast(`表格无法保存交付数据：${error.message}`,'error');
    return;
  }
  for(const item of files) {
    await writeBlobToChosenHandle(
      {kind:'browser-download',suggestedName:item.filename,mimeType:'text/csv'},
      new Blob([item.content],{type:'text/csv;charset=utf-8'}),item.filename,true,
    );
  }
  toast(persisted ? `已导出 ${files.length} 个坐标系 CSV；文件保存在交付数据 / 表格文件夹` :
    `已下载 ${files.length} 个坐标系 CSV；只读/临时模型不修改交付数据`,'success');
}

async function loadSimulationWorkspace() {
  if (!state.project) return;
  try {
    await refreshDriveProjection(state.project.id, state.editRevision, {render:false});
  } catch (error) { state.baseSimulationSchedule = []; state.simulationScheduleError = error.message; }
  try {
    const response = await api(`/api/projects/${state.project.id}/latest-simulation`);
    state.latestSimulation = response.result;
    $('#latestResultLabel').textContent = `最新结果 · ${response.result.engine || 'unknown'} · ${response.result.times?.length || 0} 点`;
  } catch (_) {
    // A completed simulation job already provides a valid current result.
    // A transient latest-simulation convergence/read failure must not erase it.
    // This preserves the V2.5.3 checked-in result-view contract.
    if (!state.latestSimulation) $('#latestResultLabel').textContent = '运行仿真后编辑曲线';
  }
  refreshCombinedGanttSchedule({render:false}); renderSimulationGantt(); renderResultViewer();
  requestSelectedDistanceCurves();
}

function renderTechnicalGantt(root, source, {error='', includeReverse=false, fontFamily='Microsoft YaHei', fontSize=11, compact=false, interactive=false}={}) {
  const simulationEnd = Math.max(0, Number(state.project?.simulation?.end_time) || 0);
  const motionEnd = Math.max(simulationEnd, ...source.map(item => Number(item.end) || 0));
  const rowsByDrive = new Map();
  source.forEach(item => {
    if (!rowsByDrive.has(item.drive_id)) rowsByDrive.set(item.drive_id, {id:item.drive_id,name:item.drive_name, segments:[]});
    rowsByDrive.get(item.drive_id).segments.push({...item});
  });
  let rows = [...rowsByDrive.values()];
  const settings = state.ui.results || {};
  const autoSort = settings.gantt_auto_sort !== false;
  const sortDirection = settings.gantt_sort_desc ? -1 : 1;
  if (interactive) {
    const hidden = new Set(settings.gantt_hidden || []);
    rows = rows.filter(row => !hidden.has(row.id));
    rows.forEach(row => row.name = settings.gantt_display_names?.[row.id] || row.name);
    // 当用户自定义顺序存在时，按该顺序重排；未设置顺序的放到最后
    const order = settings.gantt_drive_order || [];
    if (order.length && !autoSort) {
      const pos = new Map(order.map((id, i) => [id, i]));
      rows.sort((a, b) => {
        const pa = pos.has(a.id) ? pos.get(a.id) : Number.MAX_SAFE_INTEGER;
        const pb = pos.has(b.id) ? pos.get(b.id) : Number.MAX_SAFE_INTEGER;
        if (pa !== pb) return pa - pb;
        return String(a.name).localeCompare(String(b.name), 'zh-CN');
      });
    } else if (autoSort) {
      rows.sort((a,b) => sortDirection * (Math.min(...a.segments.map(item=>Number(item.start)||0))-Math.min(...b.segments.map(item=>Number(item.start)||0))) || String(a.name).localeCompare(String(b.name),'zh-CN'));
    }
  } else {
    rows.sort((a,b) => Math.min(...a.segments.map(item=>Number(item.start)||0))-Math.min(...b.segments.map(item=>Number(item.start)||0)) || String(a.name).localeCompare(String(b.name),'zh-CN'));
  }
  if (includeReverse) rows.push(...rows.map(row => ({
    name:`${row.name} [倒放]`, reverse:true,
    segments:row.segments.map(item => ({...item, start:Math.max(0,motionEnd-Number(item.end)), end:Math.max(0,motionEnd-Number(item.start)), travel_start:item.travel_end, travel_end:item.travel_start})).sort((a,b) => a.start-b.start),
  })));
  rows.forEach(row => row.segments.sort((a,b) => Number(a.start)-Number(b.start) || Number(a.end)-Number(b.end)));
  const end = Math.max(simulationEnd, ...rows.flatMap(row => row.segments.map(item => Number(item.end) || 0)));
  root.classList.toggle('empty-state', !rows.length);
  root.style.setProperty('--gantt-font', `"${fontFamily}",sans-serif`); root.style.setProperty('--gantt-font-size', `${fontSize}px`);
  const scaleX = Number(state.ui.results?.gantt_scale_x || 100) / 100;
  const scaleY = Number(state.ui.results?.gantt_scale_y || 100) / 100;
  root.style.setProperty('--gantt-scale-x', String(Math.max(.3, scaleX)));
  root.style.setProperty('--gantt-row-height', `${Math.round(62 * scaleY)}px`);
  // 横缩同步：左侧驱动名列宽也跟 scaleX 走（140px * scaleX，最小 120）
  const nameWidth = Math.max(96, Math.round(140 * scaleX));
  root.style.setProperty('--gantt-name-width', `${nameWidth}px`);
  // 横缩同步：结果页左侧 UI 栏的基础宽度也随 scaleX 稍放大（保证视觉一致）
  const sideUi = document.querySelector('.gantt-side-ui');
  if (sideUi) {
    const sideBase = 260;
    sideUi.style.setProperty('--side-scale-x', String(scaleX));
    sideUi.style.width = `calc(${sideBase}px + ${Math.max(0, (nameWidth - 140))}px)`;
  }
  root.classList.toggle('compact', compact);
  if(compact) root.style.setProperty('--gantt-row-height', `${Math.max(20,Math.min(40,150/Math.max(rows.length,1)))}px`);
  const fmt = formatGanttMetric;
  const cursorRatio = Number(state.ui.results?.gantt_cursor || 0) / 1000, cursor = cursorRatio * 100, cursorTime = cursorRatio * end;
  const cursorVisible = Boolean(state.ui.results?.gantt_cursor_visible);
  root.innerHTML = rows.length ? `<div class="technical-gantt-axis"><span></span><b>0 s</b><b>${(end/2).toFixed(2)} s</b><b>${end.toFixed(2)} s</b></div>${rows.map((row,rowIndex) => { const crossed=row.segments.find(item=>Number(item.start)<=cursorTime&&cursorTime<=Number(item.end)); const position=crossed ? Number(crossed.travel_start)+(Number(crossed.travel_end)-Number(crossed.travel_start))*(cursorTime-Number(crossed.start))/Math.max(Number(crossed.end)-Number(crossed.start),1e-12) : null; return `<div class="technical-gantt-row"><strong data-gantt-drive-name="${esc(row.id || '')}" title="双击可重命名或从甘特图隐藏">${esc(row.name)}</strong><div class="technical-gantt-track">${interactive && cursorVisible ? `<u class="gantt-cursor-line" style="left:${cursor}%"><b>${cursorTime.toFixed(3)}s${position==null?'':` · ${fmt(position)}${esc(crossed.travel_unit||'')}`}</b></u>` : ''}${row.segments.map((item,segmentIndex) => {
    const left = end ? Math.max(0, Number(item.start) / end * 100) : 0;
    const width = end ? Math.max(0.8, (Number(item.end)-Number(item.start)) / end * 100) : 100;
    const unit = item.travel_unit || '';
    const displays = state.ui.results?.gantt_segments || {};
    const display = displays[item.mapping_segment_id] || displays[item.source_segment_id] || displays[item.id] || {};
    const segColor = ganttSegmentColor(display, segmentIndex);
    const primary = `${Number(item.start).toFixed(2)}s → ${Number(item.end).toFixed(2)}s`;
    const sourceLabel = item.source_drive_name ? `${item.source_drive_name}/${item.source_segment_name || '运动段'} · ` : '';
    const editId = item.mapping_segment_id || item.id;
    return `<i data-gantt-segment="${esc(editId)}" data-gantt-drive="${esc(item.drive_id)}" title="${esc(item.name || '')}；${esc(primary)}；${fmt(item.travel_start)}${esc(unit)} → ${fmt(item.travel_end)}${esc(unit)}；双击编辑" style="left:${left}%;width:${Math.min(width,100-left)}%;--segment-color:${esc(segColor)}"><span>${esc(sourceLabel)}${esc(primary)}</span><span>${fmt(item.travel_start)}${esc(unit)} → ${fmt(item.travel_end)}${esc(unit)}</span></i>`;
  }).join('')}</div></div>`; }).join('')}` : esc(error || '当前项目没有驱动段');
  return end;
}

/* 渲染结果页左侧：驱动列表（可拖拽重排 / 重命名 / 隐藏） */
function renderGanttDriveSideList(source) {
  const box = document.getElementById('ganttDriveList');
  if (!box) return;
  if (!source || !source.length) { box.classList.add('empty-state'); box.innerHTML = '运行仿真后显示驱动顺序'; return; }
  state.ui.results ||= {};
  const settings = state.ui.results;
  const rowsById = new Map();
  source.forEach(item => { if (!rowsById.has(item.drive_id)) rowsById.set(item.drive_id, { id: item.drive_id, name: item.drive_name }); });
  // 按用户顺序或默认顺序输出
  const order = settings.gantt_drive_order || [];
  const pos = new Map(order.map((id, i) => [id, i]));
  const all = [...rowsById.values()];
  all.sort((a, b) => {
    const pa = pos.has(a.id) ? pos.get(a.id) : Number.MAX_SAFE_INTEGER;
    const pb = pos.has(b.id) ? pos.get(b.id) : Number.MAX_SAFE_INTEGER;
    if (pa !== pb) return pa - pb;
    return String(a.name).localeCompare(String(b.name), 'zh-CN');
  });
  // 保存规范化顺序（包含所有 id）
  settings.gantt_drive_order = all.map(r => r.id);
  const hiddenSet = new Set(settings.gantt_hidden || []);
  const displayNames = settings.gantt_display_names || {};
  box.classList.remove('empty-state');
  box.innerHTML = all.map((row, idx) => {
    const shown = !hiddenSet.has(row.id);
    const shownName = displayNames[row.id] || row.name;
    return `<div class="gantt-drive-row" draggable="true" data-drive-id="${esc(row.id)}" data-drive-index="${idx}">
      <span class="gantt-drive-handle" title="按住拖动调整顺序" aria-label="拖动排序">⠿</span>
      <label class="inline-check" title="取消勾选：从甘特图隐藏该驱动"><input type="checkbox" data-gantt-visible="${esc(row.id)}" ${shown ? 'checked' : ''}></label>
      <div class="gantt-drive-name" data-gantt-name="${esc(row.id)}" title="双击重命名">${esc(shownName)}</div>
      <button type="button" class="gantt-drive-edit" data-gantt-edit="${esc(row.id)}" title="重命名该驱动（甘特图显示名称）">▣</button>
    </div>`;
  }).join('');
}

function renderSimulationGantt() {
  const root = $('#simulationGantt'); if (!root) return;
  const fontFamily = state.ui.results?.gantt_font_family || 'Microsoft YaHei';
  const requestedSize = Number(state.ui.results?.gantt_font_size ?? 11);
  const fontSize = Number.isFinite(requestedSize) ? Math.max(6, Math.min(36, Math.round(requestedSize))) : 11;
  const fontInput = $('#ganttFontSize');
  if (fontInput && document.activeElement !== fontInput) fontInput.value = String(fontSize);
  const includeReverse = Boolean(state.ui.results?.gantt_reverse);
  const autoSort = state.ui.results?.gantt_auto_sort !== false;
  const sortDescending = Boolean(state.ui.results?.gantt_sort_desc);
  const r1 = $('#ganttReverse'), r2 = $('#ganttReverse2');
  if (r1) r1.checked = includeReverse;
  if (r2) r2.checked = includeReverse;
  $('#ganttScaleX').value=String(state.ui.results?.gantt_scale_x||100); $('#ganttScaleY').value=String(state.ui.results?.gantt_scale_y||100);
  $('#ganttScaleXReadout').textContent=`${state.ui.results?.gantt_scale_x||100}%`; $('#ganttScaleYReadout').textContent=`${state.ui.results?.gantt_scale_y||100}%`;
  $('#ganttAutoSort').checked=autoSort; $('#ganttAutoSort').disabled=false;
  $('#ganttSortDescending').checked=sortDescending;
  $('#ganttSortDescending').disabled=!autoSort;
  $('#ganttSortDirectionText').textContent=sortDescending?'晚到早':'早到晚';
  $('#ganttCursorVisible').checked=Boolean(state.ui.results?.gantt_cursor_visible);
  const active=state.ui.results?.active_view||'gantt'; switchResultTab(active);
  const end = renderTechnicalGantt(root, state.simulationSchedule || [], {
    error:state.simulationScheduleError, includeReverse, fontFamily, fontSize, interactive:true,
  });
  $('#simulationGanttEnd').textContent = `${end.toFixed(2)} s`;
  // 左侧驱动栏
  renderGanttDriveSideList(state.simulationSchedule || []);
}

function updateGanttCursorFromPointer(event) {
  const track=$('#simulationGantt .technical-gantt-track'); if(!track)return;
  const rect=track.getBoundingClientRect(), ratio=Math.max(0,Math.min(1,(event.clientX-rect.left)/Math.max(rect.width,1)));
  const next = Math.round(ratio*1000);
  const prev = Number(state.ui.results?.gantt_cursor ?? null);
  if (prev === next) return;
  // 拖动中只做实时镜像更新（不写日志/不落库），避免高频请求卡顿
  uiSet('results.gantt_cursor', next, `实时甘特图游标位置：${prev} → ${next}（0~1000）`, {transient: true, silent: true});
  renderSimulationGantt();
}

function editGanttSegment(driveId, segmentId) {
  const drive=state.project.drives.find(item=>item.id===driveId), segment=drive?.segments?.find(item=>item.id===segmentId);if(!segment)return;
  const display=state.ui.results?.gantt_segments?.[segment.id]||{};
  const scheduled=[...state.simulationSchedule,...state.baseSimulationSchedule].find(item=>(item.mapping_segment_id||item.id)===segment.id)||{};
  const segmentIndex=Math.max(0,drive.segments.indexOf(segment));
  const configEditable=canEditProject();
  state.ganttDialogTarget={driveId,segmentId,travelStart:Number(scheduled.travel_start)||0};
  $('#ganttDialogSegmentName').textContent=`${drive.name} / ${segment.name}`;
  $('#ganttDialogStart').value=segment.start;
  $('#ganttDialogTravelMode').value=segment.gantt_travel_input_mode||'travel';
  const numericTravel=Number(segment.travel), travelStart=Number(scheduled.travel_start)||0;
  $('#ganttDialogTravel').value=$('#ganttDialogTravelMode').value==='end_position'&&Number.isFinite(numericTravel)?travelStart+numericTravel:segment.travel;
  $('#ganttDialogRateMode').value=segment.mode||'speed';
  $('#ganttDialogRate').value=segment.mode==='duration'?segment.duration:segment.speed;
  $('#ganttDialogColor').value=ganttSegmentColor(display,segmentIndex);
  $('#ganttDialogColorButton span').style.background=$('#ganttDialogColor').value;
  $('#ganttDialogArchiveStart').checked=Boolean(segment.archive_start); $('#ganttDialogArchiveEnd').checked=Boolean(segment.archive_end);
  $('#ganttDialogArchiveStartTime').checked=Boolean(segment.archive_start_time); $('#ganttDialogArchiveTravel').checked=Boolean(segment.archive_motion_value); $('#ganttDialogArchiveRate').checked=Boolean(segment.archive_rate_value);
  ['ganttDialogArchiveStart','ganttDialogArchiveEnd','ganttDialogArchiveStartTime','ganttDialogArchiveTravel','ganttDialogArchiveRate','ganttDialogStart','ganttDialogTravel','ganttDialogTravelMode','ganttDialogRate','ganttDialogRateMode'].forEach(id=>{$(`#${id}`).disabled=!configEditable;});
  $('#ganttDialogReadonly').classList.toggle('hidden',configEditable);
  $('#ganttSegmentDialog').showModal();
}

async function saveGanttSegmentDialog(event) {
  event.preventDefault();
  if(event.submitter?.value==='cancel'){state.ganttDialogTarget=null;$('#ganttSegmentDialog').close();return;}
  const target=state.ganttDialogTarget;if(!target)return $('#ganttSegmentDialog').close();
  const drive=state.project.drives.find(item=>item.id===target.driveId),segment=drive?.segments?.find(item=>item.id===target.segmentId);if(!segment)return $('#ganttSegmentDialog').close();
  const display={color:$('#ganttDialogColor').value,custom_color:true};
  uiSet(`results.gantt_segments.${segment.id}`, display, `修改甘特图运动段显示：${drive.name}/${segment.name} → color=${display.color}`);
  if(canEditProject()){
    const travelMode=$('#ganttDialogTravelMode').value, rawTravel=$('#ganttDialogTravel').value.trim();
    if(travelMode==='end_position'){
      const endPosition=Number(rawTravel);
      if(!Number.isFinite(endPosition)){toast('结束位置模式需要输入有效数值','error');return;}
      segment.travel=String(endPosition-(Number(target.travelStart)||0));
    }else segment.travel=rawTravel;
    segment.gantt_travel_input_mode=travelMode;
    segment.start=$('#ganttDialogStart').value.trim();segment.mode=$('#ganttDialogRateMode').value;
    if(segment.mode==='duration')segment.duration=$('#ganttDialogRate').value.trim();else segment.speed=$('#ganttDialogRate').value.trim();
    segment.archive_start=$('#ganttDialogArchiveStart').checked;segment.archive_end=$('#ganttDialogArchiveEnd').checked;
    segment.archive_start_time=$('#ganttDialogArchiveStartTime').checked;segment.archive_motion_value=$('#ganttDialogArchiveTravel').checked;segment.archive_rate_value=$('#ganttDialogArchiveRate').checked;
    markDirty();renderDrives();
    scheduleInteractionCommit();
    scheduleDraftGanttProjection(); // web Gantt refreshes without Enter / MuJoCo
  } else renderSimulationGantt();
  state.ganttDialogTarget=null;
  $('#ganttSegmentDialog').close();
}

function collectStaticFields() {
  if (!state.project) return;
  state.project.simulation = {...state.project.simulation, start_time: Number($('#simStart').value), end_time: Number($('#simEnd').value), timestep: Number($('#simStep').value), engine: 'mujoco', gravity_m_s2: Number($('#simGravity')?.value ?? state.project.simulation.gravity_m_s2 ?? 9.81), ground_enabled: Boolean($('#simGroundEnabled')?.checked ?? state.project.simulation.ground_enabled ?? true), ground_friction: Number($('#simGroundFriction')?.value ?? state.project.simulation.ground_friction ?? .8), ground_collision_margin_mm: Number($('#simGroundMargin')?.value ?? state.project.simulation.ground_collision_margin_mm ?? 0), contact_response_time_s: Number($('#simContactResponse')?.value ?? state.project.simulation.contact_response_time_s ?? .025), contact_damping_ratio: Number($('#simContactDamping')?.value ?? state.project.simulation.contact_damping_ratio ?? 2)};
  collectCameraSettings();
  Object.assign(state.project.optimization, {mode: $('#optMode').value, trials: Number($('#optTrials').value), objective: $('#optObjective').value, direction: $('#optDirection').value});
}

async function refreshMeshLibrary() {
  if (!state.project) return;
  try {
    const result = await api(`/api/projects/${state.project.id}/meshes`, {timeout: 10000});
    state.meshFiles = (result && Array.isArray(result.files)) ? result.files : [];
    state.project.mesh_root = (result && typeof result.mesh_root === 'string') ? result.mesh_root : (state.project.mesh_root || '');
    if ($('#meshFileList')) renderMeshLibrary();
  } catch (e) {
    console.warn('[refreshMeshLibrary] failed:', e);
    state.meshFiles = [];
    if ($('#meshFileList')) renderMeshLibrary();
  }
}

async function scanMeshPath() {
  return withBlockingLoading({title:'正在扫描数模资产', detail:'正在遍历项目资产并重建数模索引，请等待。'}, async token => {
    try {
      if (state.dirty){updateBlockingLoading(token,{detail:'正在保存当前模型修改…'});await commitEdits();}
      updateBlockingLoading(token,{detail:'正在扫描 STL/OBJ 资产并修复引用…'});
      const result = await api(`/api/projects/${state.project.id}/meshes/rescan`, {method:'POST', body:'{}'});
      state.meshFiles = result.files;
      state.project = result.project;
      meshThumbnailForceNextRender = true;
      clearDirty(); renderAll();
      const repair = result.repair || {removed:[], normalized:[]};
      toast(`已重新扫描服务端项目资产 ${result.files.length} 个模型，并强制重建缩略图；自动移除 ${repair.removed.length} 个失效引用，校正 ${repair.normalized.length} 项`);
    } catch (error) { toast(error.message, 'error'); }
  });
}

function addMeshFromLibrary(filename, layerIndex) {
  if (!canEditProject()) return toast('当前模型不可编辑，不能添加数模', 'error');
  const layer = state.project.layers[layerIndex];
  if (!layer) return toast('请选择目标层级', 'error');
  if (layer.active === false) return toast('未激活层级已锁定，不能添加数模', 'error');
  if (!state.meshFiles.some(item => item.filename === filename)) return toast('数模库中已找不到这个数模，请刷新数模库', 'error');
  if (layer.meshes.some(mesh => mesh.filename === filename)) return toast('当前层级已添加这个数模');
  layer.meshes.push({id:uid('mesh'), filename, collision:false, rgba:'', opacity:1, mass_kg:/\.stl$/i.test(filename) ? 0.01 : null});
  state.selectedLayerId = layer.id;
  if (hierarchyViewMode() === 'diagram') state.hierarchyDiagramSelection = {type:'node', layerId:layer.id};
  markDirty(); renderAll(); scheduleInteractionCommit();
  toast(`已拖入数模：${filename}`);
}

function meshBaseName(filename) {
  const leaf = String(filename || '').split(/[\/]/).pop() || 'layer';
  return leaf.replace(/\.(?:stl|obj)$/i, '').trim() || 'layer';
}

function addDiagramLayerFromMesh(filename, parentId, worldX, worldY) {
  if (!canEditProject()) return toast('当前模型不可编辑，不能新增层级', 'error');
  if (!state.meshFiles.some(item => item.filename === filename)) return toast('数模库中已找不到这个数模，请刷新数模库', 'error');
  const parent = (state.project.layers || []).find(layer => layer.id === parentId) || null;
  if (parent?.active === false) return toast('未激活层级已锁定，不能通过拖入数模新增其子层级', 'error');
  const previousSelection = state.selectedLayerId;
  state.selectedLayerId = parent?.id || null;
  const layer = newLayer();
  state.selectedLayerId = previousSelection;
  layer.name = uniqueName(meshBaseName(filename), (state.project.layers || []).map(item => item.name));
  layer.parent_id = parent?.id || 'root';
  const mesh = {id:uid('mesh'), filename, collision:false, rgba:'', opacity:1, mass_kg:/\.stl$/i.test(filename) ? 0.01 : null};
  layer.meshes.push(mesh);
  state.project.layers.push(layer);
  state.selectedLayerId = layer.id;
  state.hierarchyDiagramSelection = {type:'node', layerId:layer.id};
  const config = {
    x:Number(worldX) - 98,
    y:Number(worldY) - 79,
    w:196,
    h:158,
    body_mesh_id:mesh.id,
  };
  hierarchyDiagramSetNodeUi(layer.id, config, `框图建模：拖入数模创建${parent ? `“${parent.name}”的子` : '顶'}层级“${layer.name}”`);
  markDirty();
  renderAll();
  scheduleInteractionCommit();
  toast(parent ? `已创建“${parent.name}”的子层级：${layer.name}` : `已创建顶层层级：${layer.name}`);
}

function layerMeshFamilySeeds(layer) {
  const familySeeds = new Map();
  (layer?.meshes || []).forEach(mesh => {
    const match = String(mesh.filename || '').match(/^(.*?)(?:\.\d+)?(\.[^.]+)$/);
    const key = match ? `${match[1]}${match[2]}`.toLowerCase() : String(mesh.filename || '').toLowerCase();
    if (mesh.filename && !familySeeds.has(key)) familySeeds.set(key, mesh.filename);
  });
  return [...familySeeds.values()];
}

async function adaptiveMeshFamiliesForLayer(layerId) {
  const layer = state.project.layers.find(item => item.id === layerId);
  const changes = {added:0, removed:0, normalized:0};
  for (const seedFilename of layerMeshFamilySeeds(layer)) {
    const result = await api(`/api/projects/${state.project.id}/meshes/adaptive`, {method:'POST', body:JSON.stringify({layer_id:layerId, seed_filename:seedFilename})});
    state.project = result.project;
    changes.added += result.added?.length || 0;
    changes.removed += result.removed?.length || 0;
    changes.normalized += result.normalized?.length || 0;
  }
  return changes;
}

async function adaptiveAllMeshFamilies(layerIndex) {
  return withBlockingLoading({title:'正在自适应数模', detail:'正在逐组分析当前层级同族资产并更新模型，请等待。'}, async () => {
    try {
      if (state.dirty) await commitEdits();
      layerIndex = state.project.layers.findIndex(layer => layer.id === state.selectedLayerId);
      const layer = state.project.layers[layerIndex];
      if (!layer?.meshes?.length) return toast('当前层级没有可适配的数模', 'error');
      const changes = await adaptiveMeshFamiliesForLayer(layer.id);
      clearDirty(); renderAll();
      const detail = [`新增 ${changes.added}`, `删除失效 ${changes.removed}`, `校正 ${changes.normalized}`].join(' · ');
      toast(`自适应完成：${detail}`);
    } catch (error) { toast(error.message, 'error'); }
  });
}

async function adaptiveAllProjectMeshFamilies() {
  return withBlockingLoading({title:'正在全部数模自适应', detail:'正在按层级逐组执行现有同族适配逻辑，请等待。'}, async () => {
    try {
      if (state.dirty) await commitEdits();
      const layerIds = state.project.layers.filter(layer => layer.meshes?.length).map(layer => layer.id);
      if (!layerIds.length) return toast('当前模型没有可适配的数模', 'error');
      const changes = {added:0, removed:0, normalized:0};
      for (const layerId of layerIds) {
        const layerChanges = await adaptiveMeshFamiliesForLayer(layerId);
        changes.added += layerChanges.added; changes.removed += layerChanges.removed; changes.normalized += layerChanges.normalized;
      }
      clearDirty(); renderAll();
      toast(`全部数模自适应完成：新增 ${changes.added} · 删除失效 ${changes.removed} · 校正 ${changes.normalized}`);
    } catch (error) { toast(error.message, 'error'); }
  });
}

async function repairMeshes() {
  if (!confirm('将删除失效的层级/测距引用，并校正文件名大小写。继续吗？')) return;
  return withBlockingLoading({title:'正在修复数模引用', detail:'正在扫描资产并校正失效引用，请等待。'}, async () => {
    try {
      if (state.dirty) await commitEdits();
      const result = await api(`/api/projects/${state.project.id}/meshes/repair`, {method:'POST'});
      state.project = result.project; clearDirty(); renderAll();
      toast(`已删除 ${result.removed.length} 个失效引用，校正 ${result.normalized.length} 项`);
    } catch (error) { toast(error.message, 'error'); }
  });
}

function assistantSetStreaming(active) {
  state.assistantStreaming = active;
  $('#assistantSend').disabled = active;
  $('#assistantInput').disabled = active;
  $('#assistantStop').disabled = !active;
}

function assistantMessage(role, content = '') {
  const root = $('#assistantMessages'); root.querySelector('.assistant-empty')?.remove();
  const item = document.createElement('div'); item.className = `assistant-message ${role}`; item.textContent = content;
  root.append(item); root.scrollTop = root.scrollHeight; return item;
}

async function loadGlobalAssistantConversation() {
  if (!state.project || !$('#assistantMessages')) return;
  try {
    const result = await api(`/api/projects/${state.project.id}/agent-conversation`);
    const messages = (result.messages || []).filter(item => ['user','assistant'].includes(item.role)).slice(-30);
    const root = $('#assistantMessages'); root.innerHTML = '';
    if (!messages.length) root.innerHTML = '<div class="assistant-empty">可以询问当前项目，或让我检索变量并生成可审阅的操作建议。</div>';
    else messages.forEach(item => assistantMessage(item.role, item.content));
  } catch (_) {}
}

function renderAssistantProposal(payload) {
  const root = $('#assistantMessages'), changeset = payload.changeset, dryRun = payload.dry_run || {};
  const card = document.createElement('section'); card.className = 'assistant-proposal';
  const title = document.createElement('strong'); title.textContent = changeset.title || '操作建议';
  const status = document.createElement('small'); status.textContent = dryRun.ok ? `待审批 · ${changeset.commands.length} 项变更` : '预检未通过，不可执行';
  const detail = document.createElement('pre'); detail.textContent = changeset.commands.map(command => `${command.tool_id}  ${command.params.path} = ${JSON.stringify(command.params.value)}`).join('\n');
  const actions = document.createElement('div'); actions.className = 'proposal-actions';
  const reject = document.createElement('button'); reject.className = 'button tiny ghost'; reject.textContent = '不执行';
  const execute = document.createElement('button'); execute.className = 'button tiny primary'; execute.textContent = '审阅后执行'; execute.disabled = !dryRun.ok;
  reject.addEventListener('click', () => { execute.disabled = true; reject.disabled = true; status.textContent = '已拒绝，未修改任何状态'; });
  execute.addEventListener('click', async () => {
    try {
      execute.disabled = true; reject.disabled = true;
      await api(`/api/projects/${state.project.id}/changesets/${changeset.id}/commit`, {method:'POST', body:JSON.stringify({confirmed:true})});
      const mirror = await api(`/api/projects/${state.project.id}/state`);
      state.project = mirror.state.project; state.ui = mirror.state.ui || {}; clearDirty(); renderAll();
      card.classList.add('applied'); status.textContent = '已执行 · 可通过全局撤销回退'; toast(`已执行：${changeset.title}`);
    } catch (error) { execute.disabled = false; reject.disabled = false; toast(error.message, 'error'); }
  });
  actions.append(reject, execute); card.append(title, status, detail, actions); root.append(card); root.scrollTop = root.scrollHeight;
}

async function sendGlobalAssistant() {
  const message = $('#assistantInput').value.trim();
  if (!message || state.assistantStreaming || !state.project) return;
  if (state.dirty) { try { await commitEdits(); } catch (_) { return; } }
  $('#globalAssistant').classList.remove('collapsed'); $('#assistantToggle').setAttribute('aria-expanded','true');
  assistantMessage('user', message); $('#assistantInput').value = '';
  const reply = assistantMessage('assistant', ''), controller = new AbortController(); state.assistantAbort = controller; assistantSetStreaming(true);
  try {
    const response = await fetch(`/api/projects/${state.project.id}/assistant/stream`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({message}), signal:controller.signal});
    if (!response.ok) { let detail = `${response.status} ${response.statusText}`; try { const body=await response.json(); detail=body.detail||detail; } catch (_) {} throw new Error(detail); }
    const reader = response.body.getReader(), decoder = new TextDecoder(); let buffer = '';
    while (true) {
      const {value, done} = await reader.read(); buffer += decoder.decode(value || new Uint8Array(), {stream:!done});
      const packets = buffer.split('\n\n'); buffer = packets.pop() || '';
      for (const packet of packets) {
        const line = packet.split('\n').find(item => item.startsWith('data:')); if (!line) continue;
        const event = JSON.parse(line.slice(5).trim());
        if (event.type === 'token') { reply.textContent += event.text; $('#assistantMessages').scrollTop = $('#assistantMessages').scrollHeight; }
        else if (event.type === 'proposal') renderAssistantProposal(event);
        else if (event.type === 'proposal_error') assistantMessage('error', event.message);
        else if (event.type === 'error') throw new Error(event.message);
      }
      if (done) break;
    }
    if (!reply.textContent.trim()) reply.remove();
  } catch (error) {
    if (!reply.textContent.trim()) reply.remove();
    assistantMessage('error', error.name === 'AbortError' ? '已终止本轮回答。' : error.message);
  } finally { state.assistantAbort = null; assistantSetStreaming(false); $('#assistantInput').focus(); }
}

// V2.16.11.4: preserve one copy of every existing layout control. When the
// chart pane is extremely narrow, move the controls into the native menu,
// rather than overlapping the always-visible NX export action.
function initCompactResultAxisToolbar() {
  const toolbar = document.querySelector('.result-viewer-panel .result-axis-main-toolbar');
  const layout = toolbar?.querySelector('.axis-toolbar-layout');
  const menu = layout?.querySelector('.axis-layout-more');
  const panel = menu?.querySelector('.axis-toolbar-more-content');
  if (!toolbar || !layout || !menu || !panel) return;
  const nodes = [
    layout.querySelector('#axisColumnToggle'),
    layout.querySelector('.result-layout-picker'),
    layout.querySelector('#renameResultLayoutButton'),
    layout.querySelector('#addResultAxisButton'),
  ];
  if (nodes.some(node => !node)) return;
  let compact = null;
  const refresh = () => {
    // The result tab may be hidden during initialization. ResizeObserver
    // will re-evaluate the real width as soon as the tab becomes visible.
    const width = toolbar.getBoundingClientRect().width;
    if (!width) return;
    const next = width < 400;
    if (next === compact) return;
    compact = next;
    menu.open = false;
    if (compact) panel.prepend(...nodes);
    else nodes.forEach(node => layout.insertBefore(node, menu));
    toolbar.classList.toggle('axis-toolbar-compact', compact);
  };
  refresh();
  if (typeof ResizeObserver !== 'undefined') {
    new ResizeObserver(refresh).observe(toolbar);
  } else window.addEventListener('resize', refresh);
}

function bindStaticEvents() {
  initDriveColumnResizer();
  const hubWidthSplitter=$('#hubProjectWidthSplitter');
  const applyHubProjectWidth=value=>{
    const width=Math.max(160,Math.min(520,Math.round(Number(value)||242)));
    state.hubProjectListWidth=width; document.documentElement.style.setProperty('--hub-project-list-width',`${width}px`);
    try{localStorage.setItem('mujoco_studio.hub_project_list_width.v1',String(width));}catch(_){}
  };
  try{applyHubProjectWidth(Number(localStorage.getItem('mujoco_studio.hub_project_list_width.v1'))||242);}catch(_){applyHubProjectWidth(242);}
  hubWidthSplitter?.addEventListener('pointerdown',event=>{
    if(event.button!==0)return; const startX=event.clientX,startWidth=state.hubProjectListWidth; hubWidthSplitter.setPointerCapture?.(event.pointerId);
    const move=e=>applyHubProjectWidth(startWidth+(e.clientX-startX));
    const stop=e=>{hubWidthSplitter.removeEventListener('pointermove',move);hubWidthSplitter.removeEventListener('pointerup',stop);hubWidthSplitter.removeEventListener('pointercancel',stop);};
    hubWidthSplitter.addEventListener('pointermove',move);hubWidthSplitter.addEventListener('pointerup',stop);hubWidthSplitter.addEventListener('pointercancel',stop);event.preventDefault();
  });
  hubWidthSplitter?.addEventListener('keydown',event=>{if(['ArrowLeft','ArrowRight'].includes(event.key)){applyHubProjectWidth(state.hubProjectListWidth+(event.key==='ArrowRight'?20:-20));event.preventDefault();}});

  $('#navigation')?.addEventListener('click', event => {
    const link = event.target.closest('a[data-page]'); if (!link) return;
    event.preventDefault(); navigateToPage(link.dataset.page);
  });
  window.addEventListener('message', event => {
    if (event.origin !== location.origin || event.data?.type !== 'mujoco-studio-editor-navigate') return;
    if (event.data.projectId !== state.project?.id) return;
    if (event.data.view && event.data.page === 'simulation') { state.ui.results ||= {}; state.ui.results.active_view = event.data.view; }
    navigateToPage(event.data.page || 'model');
    try { window.focus(); } catch (_) {}
  });
  $('#assistantToggle').addEventListener('click', () => setAssistantOpen($('#globalAssistant').classList.contains('collapsed')));
  $('#serverSceneSelect')?.addEventListener('change', event => selectServerScene(event.target.value).catch(error=>toast(error.message,'error')));
  $('#uploadSceneButton')?.addEventListener('click', () => $('#sceneXmlInput')?.click());
  $('#sceneXmlInput')?.addEventListener('change', event => {
    const file=event.target.files?.[0]; event.target.value='';
    uploadServerScene(file).catch(error=>toast(`上传场景失败：${error.message}`,'error'));
  });
  $('#assistantClose').addEventListener('click', () => setAssistantOpen(false));
  $('#assistantSend').addEventListener('click', sendGlobalAssistant);
  $('#assistantStop').addEventListener('click', () => state.assistantAbort?.abort());
  $('#assistantInput').addEventListener('keydown', event => { if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) { event.preventDefault(); sendGlobalAssistant(); } });
  // The only submit button is Save.  Cancel/close must not become the
  // implicit default when Enter is pressed in a Gantt segment text field.
  const ganttSegmentDialog = $('#ganttSegmentDialog');
  const ganttSegmentForm = $('#ganttSegmentForm');
  ganttSegmentForm.addEventListener('submit', saveGanttSegmentDialog);
  ganttSegmentForm.querySelectorAll('[data-gantt-dialog-cancel]').forEach(button => {
    button.addEventListener('click', () => {
      state.ganttDialogTarget = null;
      ganttSegmentDialog.close();
    });
  });
  // Escape fires cancel synchronously, including when the dialog has not closed yet.
  ganttSegmentDialog.addEventListener('cancel', () => { state.ganttDialogTarget = null; });
  // Use the same submit event (and its validation/permissions) as clicking Save.
  // Native select menus, color pickers and other buttons keep their own Enter behavior.
  ganttSegmentForm.addEventListener('keydown', event => {
    if (event.key !== 'Enter' || event.isComposing || event.repeat || event.ctrlKey || event.altKey || event.metaKey || event.shiftKey) return;
    const input = event.target;
    if (input?.tagName !== 'INPUT' || !['text','number','search'].includes(input.type)) return;
    event.preventDefault();
    ganttSegmentForm.requestSubmit($('#ganttDialogSave'));
  });
  $('#ganttDialogColorButton')?.addEventListener('click',()=>$('#ganttDialogColor')?.click());
  $('#ganttDialogColor')?.addEventListener('input',event=>{$('#ganttDialogColorButton span').style.background=event.target.value;});
  $('#ganttDialogTravelMode')?.addEventListener('change',event=>{
    const target=state.ganttDialogTarget, input=$('#ganttDialogTravel');if(!target||!input)return;
    const value=Number(input.value);if(!Number.isFinite(value))return;
    input.value=event.target.value==='end_position'?value+(Number(target.travelStart)||0):value-(Number(target.travelStart)||0);
  });
  document.addEventListener('input', event => {
    const target = event.target;
    if (target.matches('[data-hub-delivery-suffix]')) {
      const projectId=state.hubSelectedProjectId||state.hubPreview?.id;if(projectId)state.hubDeliverySuffixByProject.set(projectId,target.value);
      $$('.hub-delivery-file-row [data-delivery-path]').forEach(button=>{const item=(state.hubFiles?.delivery_outputs||[]).find(candidate=>candidate.path===button.dataset.deliveryPath);const label=button.querySelector('b');if(item&&label)label.textContent=deliverySuggestedName(item,target.value);});
      return;
    }
    if (target.matches('[data-companion-travel]')) { state.companionTravels.set(target.dataset.companionTravel, target.value); return; }
    const projectField = target.matches('[data-bind],[data-color-bind],#simStart,#simEnd,#simStep,#simEngine,#simGroundEnabled,#simGravity,#simGroundFriction,#simGroundMargin,#simContactResponse,#simContactDamping,#optMode,#optTrials,#optObjective,#optDirection,.camera-config-grid input');
    if (projectField && !canEditProject()) return;
    const layerActiveDeferred = /^layers\.\d+\.active$/.test(target.dataset.bind || '');
    if (target.matches('[data-bind]') && state.project && !layerActiveDeferred) {
      setAtPath(state.project, target.dataset.bind, inputValue(target));
      const travelMatch=target.dataset.bind.match(/^drives\.(\d+)\.segments\.(\d+)\.travel$/);
      if(travelMatch){const segment=state.project.drives[Number(travelMatch[1])]?.segments?.[Number(travelMatch[2])];if(segment)for(const key of state.companionTravels.keys())if(key.startsWith(`${segment.id}:`))state.companionTravels.delete(key);}
      markDirty(); renderMetrics();
      if (target.dataset.bind?.startsWith('kinematic_closures.')) { renderLayerTree(); renderHierarchyDiagram(); }
    }
    if (target.matches('[data-color-bind]') && state.project) {
      const current = String(valueAtPath(state.project, target.dataset.colorBind) || '').trim().split(/[ ,]+/);
      setAtPath(state.project, target.dataset.colorBind, hexToRgba(target.value, Number(current[3] ?? 1)));
      markDirty();
      const code = target.closest('.color-field')?.querySelector('code');
      if (code) code.textContent = valueAtPath(state.project, target.dataset.colorBind);
    }
    if (target.matches('#simStart,#simEnd,#simStep,#simEngine,#simGroundEnabled,#simGravity,#simGroundFriction,#simGroundMargin,#simContactResponse,#simContactDamping,#optMode,#optTrials,#optObjective,#optDirection,.camera-config-grid input')) markDirty();
  });
  document.addEventListener('keydown', event => {
    const input=event.target.closest?.('[data-companion-travel]');if(!input||event.key!=='Enter')return;
    const action=input.closest('.companion-travel')?.querySelector('[data-action="companion-to-source"]');if(action){event.preventDefault();handleEntityAction(action);}
  });
  document.addEventListener('change', event => {
    const target = event.target;
    if (target.matches('[data-diagram-tree-closure-toggle]')) {
      const parentId = target.dataset.parentId, childId = target.dataset.childId;
      const existing = hierarchyDiagramMatchingClosure(parentId, childId);
      if (!canEditProject()) { target.checked = Boolean(existing); return toast('当前模型不可编辑，不能修改闭链', 'error'); }
      if (!hierarchyDiagramLayerIsActive(parentId) || !hierarchyDiagramLayerIsActive(childId)) { target.checked = Boolean(existing); return toast('未激活层级相关连线已锁定，不能修改闭链', 'error'); }
      if (target.checked) {
        const closure = existing || hierarchyDiagramCreateClosure(parentId, childId);
        if (closure) state.hierarchyDiagramSelection = {type:'closure_edge', closureId:closure.id};
      } else if (existing) {
        state.project.kinematic_closures = (state.project.kinematic_closures || []).filter(item => item.id !== existing.id);
        if (state.hierarchyDiagramSelection?.type === 'closure_edge' && state.hierarchyDiagramSelection.closureId === existing.id) state.hierarchyDiagramSelection = {type:'tree_edge', childId};
        if (state.hierarchyDiagramInteraction?.kind === 'closure-joint-pick' && state.hierarchyDiagramInteraction.closureId === existing.id) state.hierarchyDiagramInteraction = null;
      }
      markDirty(); renderAll(); scheduleInteractionCommit(); return;
    }
    if (target.matches('[data-diagram-body-mesh]')) {
      const layer = (state.project?.layers || []).find(item => item.id === target.dataset.diagramBodyMesh); if (!layer) return;
      if (!canEditProject() || layer.active === false) { renderHierarchyDiagram(); return toast(layer.active === false ? '未激活层级已锁定框图编辑' : '当前模型不可编辑，不能修改本体数模预览', 'error'); }
      const current = hierarchyDiagramNodeDefaults(layer, hierarchyDiagramFallbackLayoutValues());
      current.body_mesh_id = target.value;
      hierarchyDiagramSetNodeUi(layer.id, current, `框图建模：设置“${layer.name}”的本体数模预览`);
      renderHierarchyDiagram(); renderLayerDetails(); return;
    }
    const layerActiveMatch = String(target.dataset.bind || '').match(/^layers\.(\d+)\.active$/);
    if (layerActiveMatch && state.project) {
      if (!canEditProject()) { renderLayerDetails(); return; }
      const layer = state.project.layers[Number(layerActiveMatch[1])]; if (!layer) return;
      const next = Boolean(target.checked);
      if (!next) {
        const descendants = hierarchyDiagramDescendants(layer.id).filter(item => item.active !== false);
        if (descendants.length) {
          const disableChildren = confirm(`层级“${layer.name}”存在向子层级发出的连线。是否同时禁用其 ${descendants.length} 个子层级？\n确定：同时禁用子层级；取消：只禁用当前层级。`);
          if (disableChildren) descendants.forEach(item => { item.active = false; });
        }
      }
      layer.active = next;
      pruneInvalidClosureSolveJointRefs();
      hierarchyDiagramSyncAllClosurePassiveJoints();
      if (state.hierarchyDiagramInteraction?.kind === 'closure-joint-pick') {
        const pickingClosure = (state.project.kinematic_closures || []).find(item => item.id === state.hierarchyDiagramInteraction.closureId);
        if (hierarchyDiagramClosureLocked(pickingClosure)) state.hierarchyDiagramInteraction = null;
      }
      markDirty(); renderAll(); scheduleInteractionCommit(); return;
    }
    if (target.matches('[data-hub-asset-category]')) { void loadModelAssetLibrary(target.value); return; }
    if (target.matches('[data-result-curve-source]') && state.project) {
      const axisIndex = Number(target.dataset.axis);
      const curveIndex = Number(target.dataset.curve);
      if (!setResultViewerCurveSource(axisIndex, curveIndex, inputValue(target))) return;
      if (canEditProject()) {
        markDirty();
        scheduleInteractionCommit();
      }
      renderResultViewer();
      refreshCombinedGanttSchedule();
      if (String(target.value || '').startsWith('pair:')) {
        void requestSelectedDistanceCurve(String(target.value).slice(5), {retry:true});
      }
      return;
    }
    const projectField = target.matches('[data-bind],[data-color-bind],[data-quick-bind],[data-quick-relink],#quickWorkflowName,#simStart,#simEnd,#simStep,#simEngine,#simGroundEnabled,#simGravity,#simGroundFriction,#simGroundMargin,#simContactResponse,#simContactDamping,#optMode,#optTrials,#optObjective,#optDirection,.camera-config-grid input');
    if (projectField && !canEditProject()) return;
    if (target.matches('[data-quick-relink]')) {
      const root=target.closest('[data-quick-step-id]'), step=quickOptimization().steps.find(item=>item.id===root?.dataset.quickStepId);
      const item=quickTargetCatalog().find(candidate=>candidate.key===target.value); if(!step||!item)return;
      Object.assign(step,{drive_id:item.drive_id,segment_id:item.segment_id,field:item.field,variable_name:item.variable_name,initial_value:item.initial_value,mode:item.mode,result_value:null,status:'pending',last_constraints:[]});
      if(!step.description)step.description=item.description;
      markDirty(); renderAll(); scheduleInteractionCommit(); return;
    }
    if (target.matches('[data-quick-bind]')) {
      const root=target.closest('[data-quick-step-id]'), step=quickOptimization().steps.find(item=>item.id===root?.dataset.quickStepId);
      if (!step) return;
      const key=target.dataset.quickBind;
      if (key==='speed_direction') step[key]=target.checked?'increase':'decrease';
      else if (key==='initial_value') step[key]=Number(target.value);
      else if (key==='step_size') step[key]=target.value===''?null:Number(target.value);
      else step[key]=target.value;
      step.result_value=null; step.status='pending'; step.last_constraints=[];
      markDirty(); renderDrives(); renderQuickOptimization(); scheduleInteractionCommit(); return;
    }
    if (target.matches('#quickWorkflowName')) {
      quickOptimization().name=target.value.trim()||'快速寻优工作流'; markDirty(); scheduleInteractionCommit(); return;
    }
    if (target.matches('#hubProjectNameInput,#hubMeshRootInput')) { saveHubProperties(); return; }
    if (target.matches('[data-mapping-csv]') && target.files?.[0]) {
      const [di,si]=target.dataset.mappingCsv.split(':').map(Number); uploadMappingCsv(di,si,target.files[0]); return;
    }
    if (target.matches('[data-external-motion-csv]') && target.files?.[0]) {
      const [di,si]=target.dataset.externalMotionCsv.split(':').map(Number); uploadExternalMotionCsv(di,si,target.files[0]); return;
    }
    if (target.matches('[data-gantt-visible]')) {
      state.ui.results ||= {}; const hidden=new Set(state.ui.results.gantt_hidden||[]);
      const id = target.dataset.ganttVisible;
      target.checked ? hidden.delete(id) : hidden.add(id);
      const next = [...hidden];
      uiSet('results.gantt_hidden', next, target.checked ? `甘特图显示驱动：${id}` : `甘特图隐藏驱动：${id}`);
      renderSimulationGantt(); return;
    }
    if (target.matches('[data-gantt-name]')) {
      const id = target.dataset.ganttName; const v = target.value.trim();
      uiSet(`results.gantt_display_names.${id}`, v, `甘特图驱动显示名修改：${id} → ${v || '(空，回退原始名)'}`);
      renderSimulationGantt(); return;
    }
    if (target.matches('[data-ref-drive]')) {
      const [di,si] = target.dataset.refDrive.split(':').map(Number), segment = state.project.drives[di].segments[si];
      const ref = state.project.drives.find(item => item.name === target.value);
      segment.reference = ref?.segments?.length ? `${ref.name}/${ref.segments[0].name}` : '';
      segment.reference_boundary = 'end'; markDirty(); renderDrives(); scheduleInteractionCommit(); return;
    }
    if (target.matches('[data-ref-boundary]')) {
      const [di,si] = target.dataset.refBoundary.split(':').map(Number), [reference,boundary] = target.value.split('|');
      state.project.drives[di].segments[si].reference = reference; state.project.drives[di].segments[si].reference_boundary = boundary;
      markDirty(); scheduleInteractionCommit(); return;
    }
    if (target.matches('[data-closure-joint-option]')) {
      const closure = state.project.kinematic_closures?.[Number(target.dataset.closureJointOption)];
      if (!closure) return;
      const jointId = target.dataset.jointId;
      const selected = new Set(closure.solve_joint_ids || []);
      target.checked ? selected.add(jointId) : selected.delete(jointId);
      closure.solve_joint_ids = [...selected];
      target.closest('.closure-joint-option')?.classList.toggle('selected', target.checked);
      const dialog = target.closest('.closure-joint-dialog');
      const count = dialog?.querySelector('footer span');
      if (count) count.textContent = `${closure.solve_joint_ids.length} 个已选`;
      markDirty(); scheduleInteractionCommit(); return;
    }
    if (target.matches('[data-closure-point]')) {
      const [indexText, side] = String(target.dataset.closurePoint || '').split(':');
      const closure = state.project.kinematic_closures?.[Number(indexText)];
      if (!closure) return;
      const point = parseClosurePoint(target.value);
      if (!point) { toast(side === 'shared' ? '闭链坐标请输入 Point(x, y, z)，支持中文全角括号与逗号' : '闭链端点请输入 Point(x, y, z)，支持中文全角括号与逗号', 'error'); renderLayerDetails(); return; }
      if (!setClosurePointMm(closure, side, point)) { toast('闭链坐标无效', 'error'); renderLayerDetails(); return; }
      markDirty(); scheduleInteractionCommit(); return;
    }
    if (target.matches('[data-bind]') && state.project) {
      setAtPath(state.project, target.dataset.bind, inputValue(target)); markDirty();
      if (target.dataset.bind.endsWith('.type') && target.dataset.bind.includes('.joints.')) {
        const [, layerIndex, , jointIndex] = target.dataset.bind.split('.');
        const joint = state.project.layers[Number(layerIndex)].joints[Number(jointIndex)];
        joint.axis = joint.type === 'translation' ? '1, 0, 0' : '0, 1, 0';
        if (joint.type === 'crank') {
          joint.crank_center ||= '0, 0, 0'; joint.crank_end ||= '0, 10, 0';
          joint.rod_end ||= '30, 0, 0'; joint.slide_axis ||= '1, 0, 0';
        }
        pruneInvalidClosureSolveJointRefs();
        hierarchyDiagramSyncAllClosurePassiveJoints();
        renderLayerDetails();
      }
      if (target.dataset.bind.startsWith('kinematic_closures.')) {
        if (target.dataset.bind.endsWith('.endpoint_a.layer_id') || target.dataset.bind.endsWith('.endpoint_b.layer_id')) {
          const closureIndex = Number(target.dataset.bind.split('.')[1]);
          hierarchyDiagramSyncClosurePassiveJoints(state.project.kinematic_closures?.[closureIndex]);
        }
        renderLayerTree(); renderHierarchyDiagram();
      }
      if (target.dataset.bind.startsWith('drives.')) {
        if (target.dataset.bind.endsWith('.joint_id') || target.dataset.bind.endsWith('.enabled')) hierarchyDiagramSyncAllClosurePassiveJoints();
        renderHierarchyDiagram();
        if (hierarchyViewMode() === 'diagram') renderLayerDetails();
      }
      if (target.dataset.bind.startsWith('layers.')) {
        renderLayerTree(); renderPairs(); renderHierarchyDiagram();
        if (target.dataset.bind.endsWith('.active')) { pruneInvalidClosureSolveJointRefs(); hierarchyDiagramSyncAllClosurePassiveJoints(); renderLayerDetails(); }
        if (target.dataset.bind.endsWith('.parent_id')) hierarchyDiagramSyncAllClosurePassiveJoints();
        if (target.dataset.bind.endsWith('.limited') || target.dataset.bind.endsWith('.reverse')) renderLayerDetails();
      }
      if (target.dataset.bind.includes('.segments.') && (target.dataset.bind.endsWith('.mode') || target.dataset.bind.endsWith('.start_mode') || target.dataset.bind.endsWith('.profile') || target.dataset.bind.endsWith('.easing_mode'))) renderDrives();
      if (target.dataset.bind.startsWith('result_layout.')) { renderResultViewer(); refreshCombinedGanttSchedule(); }
    }
    if (target.matches('[data-bind],[data-color-bind],#simStart,#simEnd,#simStep,#simEngine,#simGroundEnabled,#simGravity,#simGroundFriction,#simGroundMargin,#simContactResponse,#simContactDamping,#optMode,#optTrials,#optObjective,#optDirection,.camera-config-grid input')) {
      scheduleInteractionCommit({refreshMass: target.dataset.bind?.endsWith('.mass_kg')});
    }
    if (target.matches('[data-color-bind]')) { renderLayerTree(); renderLayerDetails(); renderHierarchyDiagram(); }
  });
  document.addEventListener('click', event => {
    queueMicrotask(syncJsonEditorIfVisible);
    const diagramNode = event.target.closest?.('[data-diagram-layer-node]');
    if (diagramNode && hierarchyViewMode() === 'diagram' && !event.target.closest('button,input,select,textarea,[data-action]')) {
      const layerId = diagramNode.dataset.diagramLayerNode;
      if ((state.project?.layers || []).some(layer => layer.id === layerId)) {
        state.selectedLayerId = layerId;
        state.hierarchyDiagramSelection = {type:'node', layerId};
        if (!state.hierarchyDiagramMultiSelection?.has(layerId)) state.hierarchyDiagramMultiSelection = new Set();
        renderLayers();
        return;
      }
    }
    const diagramViewportClick = event.target.closest?.('[data-hierarchy-diagram-viewport]');
    if (diagramViewportClick && hierarchyViewMode() === 'diagram' && !diagramNode && !event.target.closest('[data-action],button,input,select,textarea')) {
      if (state.hierarchyDiagramSuppressPaneClick) { state.hierarchyDiagramSuppressPaneClick = false; return; }
      state.selectedLayerId = null;
      state.hierarchyDiagramSelection = null;
      state.hierarchyDiagramMultiSelection = new Set();
      renderLayers();
      return;
    }
    const projectCard = event.target.closest('[data-action="hub-select-project"]');
    if (projectCard && !event.target.closest('.hub-compare-check')) {
      const now = performance.now(), projectId = projectCard.dataset.projectId;
      const secondClick = state.hubLastProjectClick?.projectId === projectId && now - state.hubLastProjectClick.at <= 450;
      state.hubLastProjectClick = {projectId, at:now};
      if (secondClick) {
        clearTimeout(state.hubProjectClickTimer); state.hubProjectClickTimer = null;
        event.preventDefault(); event.stopPropagation();
        enterModelEdit(projectId);
        return;
      }
      clearTimeout(state.hubProjectClickTimer);
      state.hubProjectClickTimer = setTimeout(() => handleEntityAction(projectCard), 260);
      return;
    }
    const go = event.target.closest('[data-go]'); if (go) navigateToPage(go.dataset.go);
    const action = event.target.closest('[data-action]'); if (action) { handleEntityAction(action); if (state.dirty) queueMicrotask(() => scheduleInteractionCommit()); }
  });
  document.addEventListener('pointerdown', event => {
    if (hierarchyViewMode() !== 'diagram' || !state.project) return;
    const diagramViewport = event.target.closest?.('[data-hierarchy-diagram-viewport]');
    if (event.button === 1 && diagramViewport) {
      const view = hierarchyDiagramViewportState();
      state.hierarchyDiagramViewportGesture = {kind:'pan', startClientX:event.clientX, startClientY:event.clientY, startPanX:view.pan_x, startPanY:view.pan_y, moved:false};
      diagramViewport.classList.add('panning');
      event.preventDefault(); event.stopPropagation(); return;
    }
    if (event.button !== 0) return;
    const bendHandle = event.target.closest?.('[data-diagram-edge-bend]');
    if (bendHandle) {
      // During passive-joint correction a tree line is a selection target, not a bend handle.
      // Let the normal click action toggle that line instead of swallowing it as a curve drag.
      if (state.hierarchyDiagramInteraction?.kind === 'closure-joint-pick' && String(bendHandle.dataset.diagramEdgeBend || '').startsWith('tree:')) return;
      if (!canEditProject()) return;
      const [edgeKind, edgeId] = String(bendHandle.dataset.diagramEdgeBend || '').split(':');
      if (!edgeId) return;
      if (hierarchyDiagramEdgeLocked(edgeKind === 'closure' ? 'closure' : 'tree', edgeId)) return toast('未激活层级相关连线已锁定，不能调整线段', 'error');
      const bucket = edgeKind === 'closure' ? hierarchyDiagramUi().closure_edges : hierarchyDiagramUi().tree_edges;
      const saved = deepClone(bucket?.[edgeId] || {});
      state.hierarchyDiagramInteraction = {kind:'bend', edgeKind:edgeKind === 'closure' ? 'closure' : 'tree', edgeId, startClientX:event.clientX, startClientY:event.clientY, startBendX:Number(saved.bend_x)||0, startBendY:Number(saved.bend_y)||0, moved:false};
      state.hierarchyDiagramSelection = edgeKind === 'closure' ? {type:'closure_edge', closureId:edgeId} : {type:'tree_edge', childId:edgeId};
      renderLayerDetails();
      event.preventDefault(); event.stopPropagation(); return;
    }
    const resizeHandle = event.target.closest?.('[data-diagram-node-resize]');
    if (resizeHandle) {
      if (!canEditProject()) return;
      const layer = state.project.layers.find(item => item.id === resizeHandle.dataset.diagramNodeResize); if (!layer || layer.active === false) return;
      const node = hierarchyDiagramNodeDefaults(layer, hierarchyDiagramFallbackLayoutValues());
      state.selectedLayerId = layer.id; state.hierarchyDiagramSelection = {type:'node', layerId:layer.id};
      state.hierarchyDiagramInteraction = {kind:'resize', layerId:layer.id, axis:resizeHandle.dataset.diagramNodeResizeAxis || 'xy', startClientX:event.clientX, startClientY:event.clientY, startW:node.w, startH:node.h, base:node, moved:false};
      event.preventDefault(); event.stopPropagation(); return;
    }
    const sourcePort = event.target.closest?.('[data-diagram-connect-source]');
    if (sourcePort) {
      if (!canEditProject()) return;
      const layer = state.project.layers.find(item => item.id === sourcePort.dataset.diagramConnectSource); if (!layer || layer.active === false) return toast('未激活的层级已锁定连线', 'error');
      const point = hierarchyDiagramWorldPoint(event.clientX, event.clientY);
      state.selectedLayerId = layer.id; state.hierarchyDiagramSelection = {type:'node', layerId:layer.id};
      state.hierarchyDiagramInteraction = {kind:'connect', sourceId:layer.id, sourceSide:sourcePort.dataset.diagramPortSide || 'right', linkKind:state.hierarchyDiagramLinkKind === 'closure' ? 'closure' : 'parent', x:point.x, y:point.y};
      hierarchyDiagramRenderEdgesOnly();
      event.preventDefault(); event.stopPropagation(); return;
    }
    const dragHandle = event.target.closest?.('[data-diagram-node-drag-handle]');
    if (dragHandle && !event.target.closest('button,input,select,textarea')) {
      if (!canEditProject()) return;
      const layer = state.project.layers.find(item => item.id === dragHandle.dataset.diagramNodeDragHandle); if (!layer || layer.active === false) return;
      const node = hierarchyDiagramNodeDefaults(layer, hierarchyDiagramFallbackLayoutValues());
      const selectedIds = state.hierarchyDiagramMultiSelection?.has(layer.id)
        ? [...state.hierarchyDiagramMultiSelection].filter(id => hierarchyDiagramLayerIsActive(id))
        : [layer.id];
      const nodes = hierarchyDiagramResolvedNodes();
      const groupBase = Object.fromEntries(selectedIds.map(id => [id, deepClone(nodes[id])]).filter(([,value]) => value));
      state.selectedLayerId = layer.id; state.hierarchyDiagramSelection = {type:'node', layerId:layer.id};
      state.hierarchyDiagramInteraction = {kind:'node-drag', layerId:layer.id, layerIds:selectedIds, startClientX:event.clientX, startClientY:event.clientY, base:node, groupBase, moved:false};
      const card = dragHandle.closest('[data-diagram-layer-node]');
      $$('.hierarchy-diagram-node.selected').forEach(item => item.classList.remove('selected'));
      card?.classList.add('selected');
      renderLayerDetails();
      return;
    }
    const blankPane = diagramViewport && !event.target.closest?.('[data-diagram-layer-node],[data-diagram-edge-bend],[data-action],button,input,select,textarea,[contenteditable="true"]');
    if (blankPane) {
      const start = hierarchyDiagramWorldPoint(event.clientX, event.clientY);
      state.hierarchyDiagramInteraction = {kind:'lasso', startX:start.x, startY:start.y, x:start.x, y:start.y, moved:false};
      diagramViewport.classList.add('selecting');
      event.preventDefault(); event.stopPropagation();
    }
  });

  window.addEventListener('pointermove', event => {
    if (hierarchyViewMode() !== 'diagram') return;
    const viewportGesture = state.hierarchyDiagramViewportGesture;
    if (viewportGesture?.kind === 'pan') {
      const dx = event.clientX - viewportGesture.startClientX, dy = event.clientY - viewportGesture.startClientY;
      if (!viewportGesture.moved && Math.hypot(dx,dy) < 2) return;
      viewportGesture.moved = true;
      hierarchyDiagramSetViewport({pan_x:viewportGesture.startPanX + dx, pan_y:viewportGesture.startPanY + dy, zoom:hierarchyDiagramViewportState().zoom}, '框图建模：中键平移画布', {transient:true, silent:true});
      event.preventDefault(); return;
    }
    const interaction = state.hierarchyDiagramInteraction;
    if (!interaction) return;
    if (interaction.kind === 'lasso') {
      const point = hierarchyDiagramWorldPoint(event.clientX, event.clientY);
      interaction.x = point.x; interaction.y = point.y;
      if (!interaction.moved && Math.hypot(interaction.x - interaction.startX, interaction.y - interaction.startY) < 3) return;
      interaction.moved = true;
      const box = $('#hierarchyDiagramSelectionBox');
      if (box) {
        const left=Math.min(interaction.startX,interaction.x), top=Math.min(interaction.startY,interaction.y);
        box.style.display='block'; box.style.left=`${left}px`; box.style.top=`${top}px`; box.style.width=`${Math.abs(interaction.x-interaction.startX)}px`; box.style.height=`${Math.abs(interaction.y-interaction.startY)}px`;
      }
      event.preventDefault(); return;
    }
    if (interaction.kind === 'node-drag') {
      const zoom = hierarchyDiagramViewportState().zoom;
      const dx = (event.clientX - interaction.startClientX) / zoom, dy = (event.clientY - interaction.startClientY) / zoom;
      if (!interaction.moved && Math.hypot(dx,dy) < 2) return;
      interaction.moved = true;
      (interaction.layerIds || [interaction.layerId]).forEach(id => {
        const base = interaction.groupBase?.[id] || (id === interaction.layerId ? interaction.base : null); if (!base) return;
        const config = {...base, x:base.x + dx, y:base.y + dy};
        hierarchyDiagramSetNodeUi(id, config, `框图建模：移动${(interaction.layerIds || []).length > 1 ? '多选' : ''}框图 ${id}`, {transient:true, silent:true});
        const nodeEl = document.querySelector(`[data-diagram-layer-node="${CSS.escape(id)}"]`);
        if (nodeEl) { nodeEl.style.left=`${config.x}px`; nodeEl.style.top=`${config.y}px`; }
      });
      hierarchyDiagramRenderEdgesOnly();
      event.preventDefault(); return;
    }
    if (interaction.kind === 'resize') {
      const zoom = hierarchyDiagramViewportState().zoom;
      const dx = (event.clientX - interaction.startClientX) / zoom, dy = (event.clientY - interaction.startClientY) / zoom;
      if (!interaction.moved && Math.hypot(dx,dy) < 2) return;
      interaction.moved = true;
      const config = {...interaction.base,
        w:interaction.axis === 'y' ? interaction.startW : hierarchyDiagramClampNodeSize(interaction.startW + dx, 'w'),
        h:interaction.axis === 'x' ? interaction.startH : hierarchyDiagramClampNodeSize(interaction.startH + dy, 'h'),
      };
      hierarchyDiagramSetNodeUi(interaction.layerId, config, `框图建模：调整框图大小 ${interaction.layerId}`, {transient:true, silent:true});
      const nodeEl = document.querySelector(`[data-diagram-layer-node="${CSS.escape(interaction.layerId)}"]`);
      if (nodeEl) { nodeEl.style.width=`${config.w}px`; nodeEl.style.height=`${config.h}px`; }
      hierarchyDiagramRenderEdgesOnly();
      event.preventDefault(); return;
    }
    if (interaction.kind === 'bend') {
      const zoom = hierarchyDiagramViewportState().zoom;
      const dx = (event.clientX - interaction.startClientX) / zoom, dy = (event.clientY - interaction.startClientY) / zoom;
      if (!interaction.moved && Math.hypot(dx,dy) < 2) return;
      interaction.moved = true;
      const config = {bend_x:interaction.startBendX + dx, bend_y:interaction.startBendY + dy};
      hierarchyDiagramSetEdgeUi(interaction.edgeKind, interaction.edgeId, config, `框图建模：微调${interaction.edgeKind === 'closure' ? '闭链' : '父子'}连线`, {transient:true, silent:true});
      hierarchyDiagramRenderEdgesOnly();
      event.preventDefault(); return;
    }
    if (interaction.kind === 'connect') {
      const point = hierarchyDiagramWorldPoint(event.clientX, event.clientY);
      interaction.x = point.x; interaction.y = point.y;
      hierarchyDiagramRenderEdgesOnly();
      event.preventDefault();
    }
  }, {passive:false});

  const finishHierarchyDiagramPointer = (event, cancelled=false) => {
    const viewportGesture = state.hierarchyDiagramViewportGesture;
    if (viewportGesture?.kind === 'pan') {
      state.hierarchyDiagramViewportGesture = null;
      $('#hierarchyDiagramViewport')?.classList.remove('panning');
      if (cancelled && viewportGesture.moved) hierarchyDiagramSetViewport({pan_x:viewportGesture.startPanX, pan_y:viewportGesture.startPanY, zoom:hierarchyDiagramViewportState().zoom}, '框图建模：取消画布平移', {transient:true, silent:true});
      else if (viewportGesture.moved) hierarchyDiagramSetViewport(hierarchyDiagramViewportState(), '框图建模：完成中键平移画布');
      return;
    }
    const interaction = state.hierarchyDiagramInteraction;
    if (!interaction || !['lasso','node-drag','resize','bend','connect'].includes(interaction.kind)) return;
    if (interaction.kind === 'lasso') {
      state.hierarchyDiagramInteraction = null;
      $('#hierarchyDiagramViewport')?.classList.remove('selecting');
      const box = $('#hierarchyDiagramSelectionBox'); if (box) box.style.display='none';
      if (cancelled || !interaction.moved) return;
      const left=Math.min(interaction.startX,interaction.x), right=Math.max(interaction.startX,interaction.x), top=Math.min(interaction.startY,interaction.y), bottom=Math.max(interaction.startY,interaction.y);
      const nodes=hierarchyDiagramResolvedNodes();
      const ids=(state.project?.layers||[]).filter(layer => { const n=nodes[layer.id]; return layer.active !== false && n && n.x < right && n.x+n.w > left && n.y < bottom && n.y+n.h > top; }).map(layer=>layer.id);
      state.hierarchyDiagramMultiSelection = new Set(ids);
      state.hierarchyDiagramSuppressPaneClick = true;
      setTimeout(() => { state.hierarchyDiagramSuppressPaneClick = false; }, 80);
      if (ids.length) { state.selectedLayerId=ids[0]; state.hierarchyDiagramSelection={type:'node',layerId:ids[0]}; } else { state.selectedLayerId=null; state.hierarchyDiagramSelection=null; }
      renderLayers(); return;
    }
    if (interaction.kind === 'node-drag' || interaction.kind === 'resize') {
      const layer = state.project?.layers?.find(item => item.id === interaction.layerId);
      state.hierarchyDiagramInteraction = null;
      if (interaction.kind === 'node-drag' && interaction.moved) {
        const ids = interaction.layerIds || [interaction.layerId];
        ids.forEach(id => {
          const targetLayer=state.project?.layers?.find(item=>item.id===id); if(!targetLayer)return;
          const config=hierarchyDiagramNodeDefaults(targetLayer,hierarchyDiagramFallbackLayoutValues());
          if (cancelled) hierarchyDiagramSetNodeUi(id, interaction.groupBase?.[id] || config, '框图建模：取消多选框图移动', {transient:true,silent:true});
          else hierarchyDiagramSetNodeUi(id, config, `框图建模：完成${ids.length>1?'多选':''}框图移动“${targetLayer.name}”`);
        });
      } else if (interaction.kind === 'resize' && interaction.moved && layer) {
        const config=hierarchyDiagramNodeDefaults(layer,hierarchyDiagramFallbackLayoutValues());
        if (cancelled) hierarchyDiagramSetNodeUi(layer.id, interaction.base, '框图建模：取消框图缩放', {transient:true,silent:true});
        else hierarchyDiagramSetNodeUi(layer.id, config, `框图建模：调整框图大小“${layer.name}”`);
      }
      renderHierarchyDiagram();
      return;
    }
    if (interaction.kind === 'bend') {
      const bucket = interaction.edgeKind === 'closure' ? hierarchyDiagramUi().closure_edges : hierarchyDiagramUi().tree_edges;
      const config = deepClone(bucket?.[interaction.edgeId] || {bend_x:interaction.startBendX, bend_y:interaction.startBendY});
      state.hierarchyDiagramInteraction = null;
      if (cancelled && interaction.moved) hierarchyDiagramSetEdgeUi(interaction.edgeKind, interaction.edgeId, {bend_x:interaction.startBendX,bend_y:interaction.startBendY}, `框图建模：取消${interaction.edgeKind === 'closure' ? '闭链' : '父子'}连线微调`, {transient:true, silent:true});
      else if (interaction.moved) hierarchyDiagramSetEdgeUi(interaction.edgeKind, interaction.edgeId, config, `框图建模：完成${interaction.edgeKind === 'closure' ? '闭链' : '父子'}连线微调`);
      renderHierarchyDiagram();
      return;
    }
    if (interaction.kind === 'connect') {
      state.hierarchyDiagramInteraction = null;
      if (cancelled) { renderHierarchyDiagram(); return; }
      const hit = document.elementFromPoint(event.clientX, event.clientY)?.closest?.('[data-diagram-layer-node]');
      const targetId = hit?.dataset.diagramLayerNode || '';
      const source = state.project?.layers?.find(item => item.id === interaction.sourceId);
      const target = state.project?.layers?.find(item => item.id === targetId);
      if (!source || !target || source.id === target.id) { renderHierarchyDiagram(); return; }
      if (source.active === false || target.active === false) { toast('未激活的层级已锁定连线', 'error'); renderHierarchyDiagram(); return; }
      if (interaction.linkKind === 'parent') {
        if (isLayerInBranch(source.id, target.id)) {
          const before = (state.project.kinematic_closures || []).length;
          const closure = hierarchyDiagramCreateClosure(source.id, target.id);
          if (!closure) { renderHierarchyDiagram(); return; }
          state.hierarchyDiagramSelection = {type:'closure_edge', closureId:closure.id};
          state.selectedLayerId = target.id;
          if ((state.project.kinematic_closures || []).length !== before) {
            markDirty(); scheduleInteractionCommit();
            toast(`父子连线会形成层级循环，已自动转换为闭链虚线：${source.name} ⇢ ${target.name}`);
          } else toast('该循环关系已存在闭链虚线');
          renderAll(); return;
        }
        if (target.parent_id === source.id) {
          state.selectedLayerId = target.id; state.hierarchyDiagramSelection = {type:'tree_edge', childId:target.id};
          renderLayers(); return;
        }
        target.parent_id = source.id;
        hierarchyDiagramSyncAllClosurePassiveJoints();
        state.selectedLayerId = target.id; state.hierarchyDiagramSelection = {type:'tree_edge', childId:target.id};
        markDirty(); renderAll(); scheduleInteractionCommit(); toast(`已建立父子层级：${source.name} → ${target.name}`); return;
      }
      const before = (state.project.kinematic_closures || []).length;
      const closure = hierarchyDiagramCreateClosure(source.id, target.id);
      if (!closure) { renderHierarchyDiagram(); return; }
      state.hierarchyDiagramSelection = {type:'closure_edge', closureId:closure.id};
      state.selectedLayerId = target.id;
      if ((state.project.kinematic_closures || []).length !== before) { markDirty(); scheduleInteractionCommit(); toast(`已建立闭链：${source.name} ⇢ ${target.name}`); }
      else toast('这两个层级之间已经存在闭链');
      renderAll();
    }
  };
  window.addEventListener('pointerup', event => finishHierarchyDiagramPointer(event, false));
  window.addEventListener('pointercancel', event => finishHierarchyDiagramPointer(event, true));
  document.addEventListener('wheel', event => {
    const viewport = event.target.closest?.('[data-hierarchy-diagram-viewport]');
    if (!viewport || hierarchyViewMode() !== 'diagram' || !event.ctrlKey) return;
    const rect = viewport.getBoundingClientRect();
    const before = hierarchyDiagramViewportState();
    const worldX = (event.clientX - rect.left - before.pan_x) / before.zoom;
    const worldY = (event.clientY - rect.top - before.pan_y) / before.zoom;
    const factor = Math.exp(-event.deltaY * .0015);
    const zoom = Math.max(.35, Math.min(2.4, before.zoom * factor));
    const next = {
      zoom,
      pan_x:event.clientX - rect.left - worldX * zoom,
      pan_y:event.clientY - rect.top - worldY * zoom,
    };
    hierarchyDiagramSetViewport(next, '框图建模：Ctrl+滚轮缩放画布', {transient:true, silent:true});
    hierarchyDiagramPersistViewportSoon();
    event.preventDefault();
  }, {passive:false});

  document.addEventListener('dragstart', event => {
    const meshCard = event.target.closest('[data-mesh-drag-filename]');
    if (meshCard) { event.dataTransfer.effectAllowed='copy'; event.dataTransfer.setData('application/x-mesh-filename', meshCard.dataset.meshDragFilename); meshCard.classList.add('dragging'); return; }
    const project = event.target.closest('.hub-project-card');
    if (project) { event.dataTransfer.setData('application/x-project-id', project.dataset.projectId); project.classList.add('dragging'); return; }
    const modelTypeHandle = event.target.closest('[data-model-type-drag]');
    if (modelTypeHandle) { const modelType=modelTypeHandle.closest('[data-model-type]'); activeModelTypeDrag=modelTypeHandle.dataset.modelTypeDrag || ''; event.dataTransfer.effectAllowed='move'; event.dataTransfer.setData('application/x-model-type', activeModelTypeDrag); modelType?.classList.add('dragging'); return; }
    const pairHandle = event.target.closest?.('[data-pair-drag-handle]');
    const pairCard = pairHandle?.closest?.('[data-pair-card]');
    if (pairHandle && pairCard) {
      if (!canEditProject()) { event.preventDefault(); return; }
      event.dataTransfer.effectAllowed='move';
      activeDistancePairDragId = pairCard.dataset.pairId || '';
      event.dataTransfer.setData('application/x-distance-pair', activeDistancePairDragId);
      pairCard.classList.add('dragging');
      return;
    }
    const driveCard = event.target.closest('[data-drive-card]');
    if (driveCard && event.target.closest('.drive-drag-handle')) { event.dataTransfer.effectAllowed='move'; event.dataTransfer.setData('application/x-drive-card', driveCard.dataset.driveCard); driveCard.classList.add('dragging'); return; }
    const segment = event.target.closest('.motion-segment-row');
    if (segment && event.target.closest('.segment-drag-handle')) { event.dataTransfer.effectAllowed='move'; event.dataTransfer.setData('application/x-drive-segment', `${segment.dataset.driveIndex}:${segment.dataset.segmentIndex}`); }
    else if (segment) event.preventDefault();
  });
  document.addEventListener('dragend', event => { event.target.closest('.dragging')?.classList.remove('dragging'); activeModelTypeDrag=''; activeDistancePairDragId=''; clearModelTypeDropHints(); clearDistancePairDropHints(); });
  document.addEventListener('dragover', event => {
    const pairCard = event.target.closest?.('[data-pair-card]');
    if (pairCard && event.dataTransfer.types.includes('application/x-distance-pair')) {
      event.preventDefault();
      event.dataTransfer.dropEffect='move';
      clearDistancePairDropHints();
      const draggedPairId = activeDistancePairDragId || event.dataTransfer.getData('application/x-distance-pair');
      if (pairCard.dataset.pairId !== draggedPairId) {
        const rect = pairCard.getBoundingClientRect();
        pairCard.classList.add(event.clientY < rect.top + rect.height / 2 ? 'pair-drop-before' : 'pair-drop-after');
      }
      return;
    }
    const diagramViewport = event.target.closest?.('[data-hierarchy-diagram-viewport]');
    if (diagramViewport && hierarchyViewMode() === 'diagram' && event.dataTransfer.types.includes('application/x-mesh-filename')) {
      event.preventDefault(); event.dataTransfer.dropEffect='copy';
      diagramViewport.classList.add('mesh-drag-over');
      event.target.closest?.('[data-diagram-layer-node]')?.classList.add('mesh-drag-over');
      return;
    }
    const diagramMeshDrop = event.target.closest?.('[data-diagram-mesh-drop-target]');
    if (diagramMeshDrop && event.dataTransfer.types.includes('application/x-mesh-filename')) { event.preventDefault(); event.dataTransfer.dropEffect='copy'; diagramMeshDrop.classList.add('mesh-drag-over'); return; }
    const meshDrop = event.target.closest('[data-mesh-drop-target]');
    if (meshDrop && event.dataTransfer.types.includes('application/x-mesh-filename')) { event.preventDefault(); event.dataTransfer.dropEffect='copy'; meshDrop.classList.add('mesh-drag-over'); return; }
    const category=event.target.closest('.hub-category');
    if(category){
      event.preventDefault();
      if(event.dataTransfer.types.includes('application/x-model-type')){
        event.dataTransfer.dropEffect='move';
        const draggedType=activeModelTypeDrag || event.dataTransfer.getData('application/x-model-type');
        const plan=modelTypeDropPlan(category,event,draggedType);
        clearModelTypeDropHints();
        if(plan)category.classList.add('drag-over',`drag-${plan.mode}`);
      }
      return;
    }
    if (event.target.closest('.drive-card,.motion-segment-row')) event.preventDefault();
  });
  document.addEventListener('dragleave', event => {
    event.target.closest('[data-mesh-drop-target]')?.classList.remove('mesh-drag-over');
    event.target.closest?.('[data-diagram-mesh-drop-target]')?.classList.remove('mesh-drag-over');
    const diagramNode = event.target.closest?.('[data-diagram-layer-node].mesh-drag-over');
    if (diagramNode && !diagramNode.contains(event.relatedTarget)) diagramNode.classList.remove('mesh-drag-over');
    const diagramViewport = event.target.closest?.('[data-hierarchy-diagram-viewport].mesh-drag-over');
    if (diagramViewport && !diagramViewport.contains(event.relatedTarget)) diagramViewport.classList.remove('mesh-drag-over');
    const category=event.target.closest('.hub-category.drag-over'); if(category&&!category.contains(event.relatedTarget))clearModelTypeDropHints();
    const pairCard=event.target.closest?.('.pair-card-v2134.pair-drop-before,.pair-card-v2134.pair-drop-after');
    if(pairCard&&!pairCard.contains(event.relatedTarget))pairCard.classList.remove('pair-drop-before','pair-drop-after');
  });
  document.addEventListener('drop', event => {
    const targetPairCard = event.target.closest?.('[data-pair-card]');
    const draggedPairId = activeDistancePairDragId || event.dataTransfer.getData('application/x-distance-pair');
    if (targetPairCard && draggedPairId) {
      event.preventDefault();
      clearDistancePairDropHints();
      if (!canEditProject()) return;
      const targetPairId = targetPairCard.dataset.pairId || '';
      if (!targetPairId || targetPairId === draggedPairId) return;
      const list = state.project.distance_pairs || [];
      const rect = targetPairCard.getBoundingClientRect();
      const before = event.clientY < rect.top + rect.height / 2;
      if (!reorderDistancePairList(list, draggedPairId, targetPairId, before)) return;
      markDirty();
      renderPairs();
      scheduleInteractionCommit();
      return;
    }
    const meshFilename = event.dataTransfer.getData('application/x-mesh-filename');
    const diagramViewport = event.target.closest?.('[data-hierarchy-diagram-viewport]');
    if (diagramViewport && hierarchyViewMode() === 'diagram' && meshFilename) {
      event.preventDefault();
      const targetNode = event.target.closest?.('[data-diagram-layer-node]');
      const point = hierarchyDiagramWorldPoint(event.clientX, event.clientY);
      diagramViewport.classList.remove('mesh-drag-over');
      targetNode?.classList.remove('mesh-drag-over');
      addDiagramLayerFromMesh(meshFilename, targetNode?.dataset.diagramLayerNode || state.selectedLayerId || 'root', point.x, point.y);
      return;
    }
    const diagramMeshDrop = event.target.closest?.('[data-diagram-mesh-drop-target]');
    if (diagramMeshDrop && meshFilename) { event.preventDefault(); diagramMeshDrop.classList.remove('mesh-drag-over'); addMeshFromLibrary(meshFilename, Number(diagramMeshDrop.dataset.diagramMeshDropTarget)); return; }
    const meshDrop = event.target.closest('[data-mesh-drop-target]');
    if (meshDrop && meshFilename) { event.preventDefault(); meshDrop.classList.remove('mesh-drag-over'); addMeshFromLibrary(meshFilename, Number(meshDrop.dataset.meshDropTarget)); return; }
    const category = event.target.closest('.hub-category');
    const projectId = event.dataTransfer.getData('application/x-project-id');
    const draggedType = event.dataTransfer.getData('application/x-model-type') || activeModelTypeDrag;
    if (category && draggedType) {
      event.preventDefault();
      const plan=modelTypeDropPlan(category,event,draggedType);
      activeModelTypeDrag='';
      clearModelTypeDropHints();
      if(!plan)return;
      moveModelType(draggedType,plan.targetParent,plan.before); return;
    }
    if (category && projectId) {
      const targetCategory = category.dataset.modelRoot === 'true' ? 'None' : category.dataset.modelType;
      if (targetCategory) { event.preventDefault(); reclassifyHubProject(projectId, targetCategory); return; }
    }
    const targetDrive = event.target.closest('[data-drive-card]'); const drivePayload = event.dataTransfer.getData('application/x-drive-card');
    if (targetDrive && drivePayload !== '') {
      event.preventDefault(); const fromIndex=Number(drivePayload), toIndex=Number(targetDrive.dataset.driveCard);
      if (fromIndex !== toIndex) { const [item]=state.project.drives.splice(fromIndex,1); state.project.drives.splice(toIndex,0,item); markDirty(); renderDrives(); scheduleInteractionCommit(); }
      return;
    }
    const target = event.target.closest('.motion-segment-row'); const payload = event.dataTransfer.getData('application/x-drive-segment');
    if (target && payload) {
      event.preventDefault(); const [fromDrive,fromIndex] = payload.split(':').map(Number), toDrive = Number(target.dataset.driveIndex), toIndex = Number(target.dataset.segmentIndex);
      if (fromDrive === toDrive && fromIndex !== toIndex) { const drive=state.project.drives[toDrive],list=drive.segments; const [item]=list.splice(fromIndex,1); list.splice(toIndex,0,item); renumberSegments(drive); markDirty(); renderDrives(); scheduleInteractionCommit(); }
    }
  });
  document.addEventListener('dblclick', event => {
    const diagramTitle = event.target.closest?.('[data-diagram-node-title]');
    if (diagramTitle && hierarchyViewMode() === 'diagram') {
      event.preventDefault();
      if (!canEditProject()) return toast('当前模型不可编辑，不能重命名层级', 'error');
      const layer = (state.project?.layers || []).find(item => item.id === diagramTitle.dataset.diagramNodeTitle); if (!layer) return;
      if (layer.active === false) return toast('未激活层级已锁定框图编辑，不能重命名', 'error');
      const next = prompt('重命名层级', layer.name);
      if (next === null) return;
      const name = next.trim();
      if (!name) return toast('层级名称不能为空', 'error');
      if ((state.project.layers || []).some(item => item.id !== layer.id && item.name === name)) return toast('层级名称不能重复', 'error');
      layer.name = name;
      markDirty(); renderAll(); scheduleInteractionCommit(); return;
    }
    const meshCard=event.target.closest('[data-mesh-drag-filename]');
    if(meshCard){
      event.preventDefault();
      const layerIndex=(state.project?.layers||[]).findIndex(layer=>layer.id===state.selectedLayerId);
      if(layerIndex<0)return toast('请先在左侧选择要添加数模的层级','error');
      addMeshFromLibrary(meshCard.dataset.meshDragFilename,layerIndex);return;
    }
    const hubModel = event.target.closest('.hub-project-card');
    if (hubModel) { event.preventDefault(); return; }
    const quickTarget=event.target.closest('[data-quick-target]');
    if(quickTarget && !event.target.matches('input,select,button')){event.preventDefault();addQuickOptimizationTarget(quickTarget);return;}
    const block=event.target.closest('[data-gantt-segment]'); if(block){editGanttSegment(block.dataset.ganttDrive,block.dataset.ganttSegment);event.preventDefault();return;}
    const label=event.target.closest('[data-gantt-drive-name]'); if(!label)return; const id=label.dataset.ganttDriveName,current=label.textContent;
    const name=prompt('输入甘特图显示名称；输入“删除”可仅从甘特图隐藏该驱动',current); if(name===null)return;
    const trimmed = name.trim();
    if(['删除','delete'].includes(trimmed.toLowerCase())){
      const hidden=new Set(state.ui.results?.gantt_hidden||[]); hidden.add(id);
      uiSet('results.gantt_hidden', [...hidden], `通过甘特图驱动名对话框操作：隐藏驱动 ${id}`);
    } else {
      uiSet(`results.gantt_display_names.${id}`, trimmed || current, `通过甘特图驱动名对话框重命名：${id} → ${trimmed || current}`);
    }
    renderSimulationGantt();
  });
  $('#saveButton').addEventListener('click', () => archiveVersion().catch(error => toast(error.message, 'error')));
  $('#syncDraftButton')?.addEventListener('click', () => syncLocalDraft().catch(error => toast(error.message, 'error')));
  $('#undoButton').addEventListener('click', () => undoOrRedo('undo'));
  $('#redoButton').addEventListener('click', () => undoOrRedo('redo'));
  $('#validateButton')?.addEventListener('click', validateCurrent);
  $('#globalViewerButton').addEventListener('click', openMuJoCoViewer);
  $('#hubProjectRoot')?.addEventListener('click', renameProjectRoot);
  $('#cancelViewerLaunchButton')?.addEventListener('click', cancelViewerLaunch);
  $('#refreshHealthButton')?.addEventListener('click', validateCurrent);
  $('#solverModeToggle')?.addEventListener('change', event => { if(!canEditProject()){event.target.checked=state.project.solver_mode==='dynamic';return;} state.project.solver_mode = event.target.checked ? 'dynamic' : 'kinematic'; state.project.simulation.engine='mujoco'; markDirty(); renderAll(); scheduleInteractionCommit(); toast(state.project.solver_mode==='dynamic' ? '已切换为纯动力学：后台 mj_step 求解，Viewer 只回放轨迹' : '已切换为纯运动学：直接位置求解，不考虑重力/摩擦/接触力'); });
  $('#adaptiveAddDriveButton').addEventListener('click', adaptiveAddDrives);
  $('#importTimeSeriesButton')?.addEventListener('click', () => openTimeSeriesImportDialog().catch(error => toast(error.message, 'error')));
  $('#timeSeriesSaveCurrentButton')?.addEventListener('click', () => void saveCurrentTimeSeriesToLibrary());
  $('#timeSeriesNewBlankButton')?.addEventListener('click', () => void createBlankTimeSeries().catch(error => toast(error.message, 'error')));
  $('#timeSeriesChooseFileButton')?.addEventListener('click', () => { const input=$('#timeSeriesLocalFileInput'); if(input){input.value='';input.click();} });
  $('#timeSeriesLocalFileInput')?.addEventListener('change', event => importTimeSeriesSingleFile(event.target.files).catch(error => toast(error.message, 'error')));
  $('#timeSeriesChooseLocalButton')?.addEventListener('click', () => { const input=$('#timeSeriesLocalFolderInput'); if(input){ input.value=''; input.click(); } });
  $('#timeSeriesLocalFolderInput')?.addEventListener('change', event => importTimeSeriesLocalFolder(event.target.files).catch(error => toast(error.message, 'error')));
  $('#addDriveButton').addEventListener('click', () => { const joint = allJoints()[0]; state.project.drives.push(newDrive(joint?.id || '')); hierarchyDiagramSyncAllClosurePassiveJoints(); markDirty(); renderAll(); scheduleInteractionCommit(); if (!joint) toast('已创建无运动副驱动；将自动使用原点透明 Geom 作为作用对象'); });
  $('#addPairButton').addEventListener('click', () => { state.project.distance_pairs.push(newPair()); markDirty(); renderAll(); scheduleInteractionCommit(); });
  $('#addVariableButton').addEventListener('click', event => { event.preventDefault(); event.stopPropagation(); const name = uniqueName('variable', Object.keys(state.project.variables)); state.project.variables[name] = 0; markDirty(); renderVariables(); scheduleInteractionCommit(); });
  $('#quickOptimizationToggle').addEventListener('change', event => {
    quickOptimization().enabled=event.target.checked; markDirty(); renderAll(); scheduleInteractionCommit();
  });
  $('#quickWorkflowInput').addEventListener('change', event => importQuickWorkflow(event.target.files?.[0]).finally(()=>{event.target.value='';}));
  $('#driveTwoColumn').addEventListener('change', event => {
    state.editorLayout.driveTwoColumns = event.target.checked;
    $('#driveList').classList.toggle('drive-grid-two', event.target.checked);
    $('#driveListShell')?.classList.toggle('drive-split-active', event.target.checked && state.project?.drives?.length > 1);
    applyDriveColumnSplit(state.editorLayout.driveColumnPercent);
  });
  $('#addRangeButton').addEventListener('click', () => { state.project.optimization.variables.push({name:Object.keys(state.project.variables)[0] || 'speed_scale', minimum:0.5, maximum:1.5, step:0.1}); markDirty(); renderRanges(); scheduleInteractionCommit(); });
  $('#generateButton').addEventListener('click', generateCurrent);
  $('#mujocoCheckButton').addEventListener('click', mujocoCheck);
  $('#openViewerModelButton').addEventListener('click', openMuJoCoViewer);
  $('#simulateButton').addEventListener('click', runSimulation);
  $('#refreshAnimationButton')?.addEventListener('click', () => regenerateEmbeddedAnimation({source:'refresh-animation'}));
  $('#adaptiveAddResultAxesButton').addEventListener('click', adaptiveAddResultAxes);
  $('#addResultAxisButton').addEventListener('click', addResultAxis);
  bindResultLayoutControls();
  initCompactResultAxisToolbar();
  $('#exportAllAxesButton').addEventListener('click', openCsvExportModeDialog);
  $('#exportResultTableButton')?.addEventListener('click', () => { void exportResultAxesTable(); });
  $('#exportNxAfuButton').addEventListener('click',exportNxAfuScript);
  $$('.result-axis-main-toolbar .axis-toolbar-more').forEach(menu => {
    menu.addEventListener('click', event => {
      if (event.target.closest('.axis-toolbar-more-content button')) menu.open = false;
    });
  });
  document.addEventListener('pointerdown', event => {
    $$('.result-axis-main-toolbar .axis-toolbar-more[open]').forEach(menu => {
      if (!menu.contains(event.target)) menu.open = false;
    });
  });
  $$('[data-csv-export-mode]').forEach(button=>button.addEventListener('click',()=>{ $('#csvExportModeDialog')?.close(); void exportAllResultAxes(button.dataset.csvExportMode); }));
  $('#addCursorButton').addEventListener('click', addResultCursor);
  $('#removeCursorButton').addEventListener('click', removeResultCursor);
  $('#axisHeightRange').addEventListener('input', event => {
    $('#axisHeightValue').textContent = `${event.target.value} px`;
    $$('[data-result-axis]').forEach(canvas => canvas.setAttribute('height', event.target.value));
    drawResultAxes();
  });
  const updateGanttUi = (path, value, semantic, opts = {}) => {
    const fullPath = `results.${path}`;
    uiSet(fullPath, value, semantic || `修改甘特图参数：${path}=${typeof value === 'object' ? '[object]' : String(value)}`, opts);
    renderSimulationGantt();
  };
  $('#ganttFontFamily').addEventListener('change', event => updateGanttUi('gantt_font_family', event.target.value, `将甘特图字体改为 ${event.target.value}`));
  $('#ganttFontSize').addEventListener('change', event => {
    const requested = Number(event.target.value);
    const size = Number.isFinite(requested) ? Math.max(6, Math.min(36, Math.round(requested))) : 11;
    event.target.value = String(size);
    updateGanttUi('gantt_font_size', size, `将甘特图字号调整为 ${size}px`);
  });
  $('#ganttColor').addEventListener('change', event => updateGanttUi('gantt_color', event.target.value, `将甘特图默认色改为 ${event.target.value}`));
  $('#ganttReverse2').addEventListener('change', event => updateGanttUi('gantt_reverse', event.target.checked, event.target.checked ? '开启甘特图倒放视图' : '关闭甘特图倒放视图'));
  $('#ganttCursorVisible').addEventListener('change', event => updateGanttUi('gantt_cursor_visible', event.target.checked, event.target.checked ? '显示甘特图游标' : '隐藏甘特图游标'));
  $$('[data-result-tab]').forEach(button => button.addEventListener('click', () => {
    switchResultTab(button.dataset.resultTab);
    uiSet('results.active_view', button.dataset.resultTab, `切换结果查看视图：${button.dataset.resultTab}`);
  }));
  $('#reloadEmbeddedAnimation')?.addEventListener('click',()=>loadEmbeddedAnimation(true));
  $('#fullscreenEmbeddedAnimation')?.addEventListener('click',fullscreenEmbeddedAnimation);
  // 缩放滑块：input 实时仅刷新 UI（transient=true，不写日志/不落库）；change/pointerup 才语义化提交
  const onScaleXInput = (ev) => {
    const v = Number(ev.target.value) || 100;
    const r = document.getElementById('ganttScaleXReadout'); if (r) r.textContent = `${v}%`;
    updateGanttUi('gantt_scale_x', v, `将甘特图横向缩放改为 ${v}%`, {transient: true, silent: true});
  };
  const onScaleYInput = (ev) => {
    const v = Number(ev.target.value) || 100;
    const r = document.getElementById('ganttScaleYReadout'); if (r) r.textContent = `${v}%`;
    updateGanttUi('gantt_scale_y', v, `将甘特图纵向缩放改为 ${v}%`, {transient: true, silent: true});
  };
  const onScaleXChange = (ev) => {
    const v = Number(ev.target.value) || 100;
    updateGanttUi('gantt_scale_x', v, `甘特图横向缩放最终值：${v}%`);
  };
  const onScaleYChange = (ev) => {
    const v = Number(ev.target.value) || 100;
    updateGanttUi('gantt_scale_y', v, `甘特图纵向缩放最终值：${v}%`);
  };
  $('#ganttScaleX').addEventListener('input', onScaleXInput);
  $('#ganttScaleY').addEventListener('input', onScaleYInput);
  $('#ganttScaleX').addEventListener('change', onScaleXChange);
  $('#ganttScaleY').addEventListener('change', onScaleYChange);
  $('#ganttAutoSort').addEventListener('change',event=>updateGanttUi('gantt_auto_sort',event.target.checked,event.target.checked?'甘特图启用按时间排序':'甘特图改为按左侧栏自定义顺序'));
  $('#ganttSortDescending').addEventListener('change',event=>updateGanttUi('gantt_sort_desc',event.target.checked,event.target.checked?'甘特图时间排序改为从晚到早':'甘特图时间排序改为从早到晚'));
  $('#ganttFullscreen').addEventListener('click',()=>$('.simulation-gantt-panel').classList.toggle('gantt-expanded'));
  $('#openGanttPopup')?.addEventListener('click', openGanttPopup);
  // 左侧驱动栏：拖拽排序
  const bindDriveRowDrag = (() => {
    let dragId = null; let overRow = null;
    document.addEventListener('dragstart', ev => {
      const row = ev.target.closest?.('.gantt-drive-row'); if (!row) return;
      dragId = row.dataset.driveId; row.classList.add('dragging');
      try { ev.dataTransfer.effectAllowed = 'move'; ev.dataTransfer.setData('text/plain', dragId); } catch {}
    });
    document.addEventListener('dragend', ev => {
      const row = ev.target.closest?.('.gantt-drive-row'); if (row) row.classList.remove('dragging');
      dragId = null; overRow && (overRow.classList.remove('over-top','over-bottom'), overRow = null);
    });
    document.addEventListener('dragover', ev => {
      if (!dragId) return;
      const row = ev.target.closest?.('.gantt-drive-row');
      if (overRow && overRow !== row) overRow.classList.remove('over-top','over-bottom');
      overRow = row;
      if (!row || row.dataset.driveId === dragId) return;
      ev.preventDefault();
      const rect = row.getBoundingClientRect();
      const isTop = ev.clientY < rect.top + rect.height / 2;
      row.classList.toggle('over-top', isTop); row.classList.toggle('over-bottom', !isTop);
    });
    document.addEventListener('drop', ev => {
      if (!dragId) return;
      const row = ev.target.closest?.('.gantt-drive-row');
      if (!row || row.dataset.driveId === dragId) return;
      ev.preventDefault();
      const toId = row.dataset.driveId;
      const rect = row.getBoundingClientRect();
      const before = ev.clientY < rect.top + rect.height / 2;
      const order = [...(state.ui.results?.gantt_drive_order || [])];
      const from = order.indexOf(dragId); if (from >= 0) order.splice(from, 1);
      const to = order.indexOf(toId);
      if (to < 0) order[before ? 'unshift' : 'push'](dragId);
      else order.splice(to + (before ? 0 : 1), 0, dragId);
      const wasAutoSort = state.ui.results?.gantt_auto_sort !== false;
      uiBatch(
        [
          {path:'results.gantt_drive_order', value: order, semantic: `拖拽调整甘特图驱动顺序：将 ${dragId} 拖到 ${toId} ${before?'前':'后'}`},
          ...(wasAutoSort ? [{path:'results.gantt_auto_sort', value:false, semantic:'手动拖动顺序后，取消「按时间排序」'}] : []),
        ],
        {semantic:`调整甘特图驱动顺序（拖拽：${dragId} → ${toId} ${before?'前':'后'}）`}
      );
      if (wasAutoSort) document.getElementById('ganttAutoSort').checked = false;
      renderSimulationGantt();
    });
  });
  bindDriveRowDrag();
  // 左侧驱动栏：▣ 按钮 / 双击重命名
  document.addEventListener('click', ev => {
    const editBtn = ev.target.closest?.('[data-gantt-edit]');
    if (editBtn) {
      ev.preventDefault(); ev.stopPropagation();
      const id = editBtn.dataset.ganttEdit;
      const list = document.getElementById('ganttDriveList');
      const nameEl = list?.querySelector(`[data-gantt-name="${CSS.escape(id)}"]`);
      if (nameEl) startGanttDriveRename(nameEl, id);
    }
  });
  document.addEventListener('dblclick', ev => {
    const nameEl = ev.target.closest?.('.gantt-drive-name');
    if (!nameEl) return;
    const id = nameEl.dataset.ganttName; startGanttDriveRename(nameEl, id);
  });
  function startGanttDriveRename(nameEl, id) {
    if (nameEl.isContentEditable) return;
    const oldText = nameEl.textContent.trim();
    nameEl.contentEditable = 'true';
    nameEl.setAttribute('tabindex', '0');
    nameEl.focus();
    // 全选
    const range = document.createRange(); range.selectNodeContents(nameEl);
    const sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(range);
    const finish = (save) => {
      nameEl.contentEditable = 'false'; nameEl.removeAttribute('tabindex');
      nameEl.removeEventListener('blur', onBlur); nameEl.removeEventListener('keydown', onKey);
      if (!save) { nameEl.textContent = oldText; return; }
      const v = nameEl.textContent.trim() || oldText;
      nameEl.textContent = v;
      uiSet(`results.gantt_display_names.${id}`, v, `重命名甘特图驱动显示名：${id} → ${v}`);
      renderSimulationGantt();
    };
    const onBlur = () => finish(true);
    const onKey = (e) => { if (e.key === 'Enter') { e.preventDefault(); finish(true); } else if (e.key === 'Escape') { e.preventDefault(); finish(false); } };
    nameEl.addEventListener('blur', onBlur); nameEl.addEventListener('keydown', onKey);
  }
  // 总览右侧：甘特图缓存快速预览
  async function refreshHubGanttPreview(projectId) {
    const block = document.getElementById('hubGanttQuick');
    const img = document.getElementById('hubGanttQuickImg');
    const wrap = document.getElementById('hubGanttQuickThumbWrap');
    const meta = document.getElementById('hubGanttQuickMeta');
    const isCurrentModel = () => Boolean(projectId && state.hubSelectedProjectId === projectId && !state.hubTypeSummary);
    if (!block || !img || !isCurrentModel()) { block?.setAttribute('hidden', ''); return; }
    block.classList.add('empty-state'); block.removeAttribute('hidden');
    meta.textContent = '正在读取甘特图缓存…'; img.removeAttribute('src');
    try {
      const res = await api(`/api/projects/${projectId}/gantt-cache`);
      if (!isCurrentModel()) { block.setAttribute('hidden', ''); img.removeAttribute('src'); return; }
      if (!res || !res.png) {
        block.classList.add('empty-state'); meta.textContent = '尚未生成缓存（请先在甘特图弹窗点击「保存到缓存」）';
        wrap.removeAttribute('href'); img.removeAttribute('src'); return;
      }
      block.classList.remove('empty-state');
      img.src = `${res.png}?_ts=${(res.saved_at || Date.now())}`;
      wrap.removeAttribute('href'); wrap.removeAttribute('target'); wrap.removeAttribute('rel');
      const parts = [];
      if (res.saved_at) parts.push(new Date(res.saved_at * 1000).toLocaleString('zh-CN'));
      if (res.size) { const kb = res.size / 1024; parts.push(kb >= 1024 ? `${(kb/1024).toFixed(2)} MB` : `${kb.toFixed(1)} KB`); }
      if (res.json) {
        if (res.json.segment_count != null) parts.push(`${res.json.segment_count} 段`);
        if (res.json.drive_count != null) parts.push(`${res.json.drive_count} 驱动`);
        if (res.json.scene_width && res.json.scene_height) parts.push(`${res.json.scene_width}×${res.json.scene_height}`);
      }
      meta.textContent = parts.join(' · ') || '已生成缓存';
    } catch (err) {
      if (!isCurrentModel()) { block.setAttribute('hidden', ''); return; }
      block.classList.add('empty-state'); meta.textContent = `读取失败：${err.message}`;
    }
  }
  window.__refreshHubGanttPreview = refreshHubGanttPreview;
  document.getElementById('hubReloadGanttPreview')?.addEventListener('click', async event => {
    const button=event.currentTarget, projectId=state.hubTypeSummary?.entries?.at(-1)?.project_id || state.hubSelectedProjectId || state.project?.id;
    if(!projectId)return;
    button.disabled=true;
    try {
      await window.__GanttPopup__?.refreshCache?.(projectId);
      await Promise.all([refreshHubGanttPreview(projectId), refreshLocalMeshStatus({quiet:true,render:true})]);
      toast('甘特图缓存与本地客户端同步状态已刷新');
    } catch(error) { toast(`刷新失败：${error.message}`,'error'); }
    finally { button.disabled=false; }
  });
  const hubGanttQuick = document.getElementById('hubGanttQuick');
  let hubGanttHoverTimer = null;
  let hubGanttFloatingPreview = null;
  function closeHubGanttFloatingPreview() {
    hubGanttFloatingPreview?.remove();
    hubGanttFloatingPreview = null;
  }
  function openHubGanttFloatingPreview() {
    if (state.hubTypeSummary || !hubGanttQuick || hubGanttQuick.hidden || !document.getElementById('hubGanttQuickImg')?.getAttribute('src')) return;
    closeHubGanttFloatingPreview();
    const rect = hubGanttQuick.getBoundingClientRect();
    const floating = hubGanttQuick.cloneNode(true);
    floating.removeAttribute('id'); floating.removeAttribute('hidden'); floating.setAttribute('aria-hidden', 'true');
    floating.classList.add('hub-gantt-preview-floating');
    floating.querySelector('#hubGanttQuickThumb')?.classList.add('hub-gantt-preview-thumb');
    floating.querySelector('#hubGanttQuickThumbWrap')?.classList.add('hub-gantt-preview-wrap');
    floating.querySelector('#hubGanttQuickImg')?.classList.add('hub-gantt-preview-image');
    floating.querySelectorAll('[id]').forEach(item => item.removeAttribute('id'));
    Object.assign(floating.style, {left:`${rect.left}px`,top:`${rect.top}px`,width:`${rect.width}px`,height:`${rect.height}px`,transform:'none'});
    document.body.append(floating); hubGanttFloatingPreview = floating;
    const targetWidth = Math.min(1100, window.innerWidth - 48);
    const sourceImage=document.getElementById('hubGanttQuickImg');
    const ratio=sourceImage?.naturalWidth&&sourceImage?.naturalHeight?sourceImage.naturalHeight/sourceImage.naturalWidth:9/16;
    const targetHeight = Math.min(window.innerHeight - 48, targetWidth * ratio + 82);
    requestAnimationFrame(() => Object.assign(floating.style, {
      left:'50%', top:'50%', width:`${targetWidth}px`, height:`${targetHeight}px`, transform:'translate(-50%,-50%)',
    }));
  }
  hubGanttQuick?.addEventListener('pointerenter', () => {
    clearTimeout(hubGanttHoverTimer);
    hubGanttHoverTimer = setTimeout(openHubGanttFloatingPreview, 200);
  });
  hubGanttQuick?.addEventListener('pointerleave', () => {
    clearTimeout(hubGanttHoverTimer); closeHubGanttFloatingPreview();
  });
  hubGanttQuick?.addEventListener('click', event => {
    event.preventDefault();
    if (event.target.closest('#hubReloadGanttPreview')) return;
    if (state.hubTypeSummary) return;
    const pid = state.hubSelectedProjectId || state.project?.id;
    if (!pid) return;
    // 若不是当前项目，先载入项目，再使用当前路由器支持的 #simulation。
    if (!state.project || state.project.id !== pid) {
      openModelEditorWindow(pid, 'simulation');
    } else {
      openModelEditorWindow(pid, 'simulation');
    }
  });
  $('#simulationGantt').addEventListener('pointerdown',event=>{
    if(event.button!==0||event.detail>1||!event.target.closest('.technical-gantt-track')||event.target.closest('[data-gantt-segment]'))return;
    if(state.ui.results?.gantt_cursor_visible){state.ganttCursorDrag=true;updateGanttCursorFromPointer(event);}
    else {const root=$('#simulationGantt');state.ganttPan={x:event.clientX,left:root.scrollLeft};root.classList.add('panning');root.setPointerCapture?.(event.pointerId);}
    event.preventDefault();
  });
  $('#resultAxes').addEventListener('pointerdown', event => {
    const canvas = event.target.closest('[data-result-axis]'); if (!canvas || !state.latestSimulation?.times?.length) return;
    if (event.button !== 0) return;
    const cursors = state.project.result_layout.cursor_times ||= [];
    const time = cursorTimeFromPointer(canvas, event);
    const added = !cursors.length;
    if (added) cursors.push(time);
    let index = 0, distance = Infinity;
    cursors.forEach((value,cursorIndex) => { const next=Math.abs(Number(value)-time); if(next<distance){distance=next;index=cursorIndex;} });
    state.activeCursorIndex = index;
    state.cursorDrag = {index, original:added ? null : Number(cursors[index]), canvas};
    cursors[index] = time; canvas.focus({preventScroll:true}); canvas.setPointerCapture?.(event.pointerId); drawResultAxes(); event.preventDefault(); event.stopPropagation();
  });
  $('#resultAxes').addEventListener('keydown', event => {
    if (!['ArrowLeft','ArrowRight'].includes(event.key) || !event.target.matches('[data-result-axis]')) return;
    const times = (state.latestSimulation?.times || []).map(Number); const cursors = state.project.result_layout.cursor_times ||= [];
    if (!times.length || !cursors.length) return;
    const cursorIndex = Math.max(0, Math.min(Number(state.activeCursorIndex || 0), cursors.length - 1));
    const currentTime = Number(cursors[cursorIndex]);
    const sampleIndex = times.reduce((best,value,index) => Math.abs(value-currentTime) < Math.abs(times[best]-currentTime) ? index : best, 0);
    const nextIndex = Math.max(0, Math.min(times.length - 1, sampleIndex + (event.key === 'ArrowRight' ? 1 : -1)));
    if (nextIndex === sampleIndex && Number(cursors[cursorIndex]) === times[nextIndex]) return;
    cursors[cursorIndex] = times[nextIndex]; markDirty(); drawResultAxes();
    scheduleInteractionCommit();
    event.preventDefault(); event.stopPropagation();
  });
  window.addEventListener('pointermove', event => {
    if(state.ganttCursorDrag){updateGanttCursorFromPointer(event);event.preventDefault();return;}
    if (!state.cursorDrag) return;
    if (!(event.buttons & 1)) return;
    state.project.result_layout.cursor_times[state.cursorDrag.index] = cursorTimeFromPointer(state.cursorDrag.canvas, event);
    drawResultAxes(); event.preventDefault(); event.stopPropagation();
  });
  window.addEventListener('pointerup', () => {
    if(state.ganttPan){state.ganttPan=null;$('#simulationGantt')?.classList.remove('panning');return;}
    if(state.ganttCursorDrag){
      state.ganttCursorDrag=false;
      const value = Number(state.ui.results?.gantt_cursor||0);
      // 拖拽时已做 persist=false 的快速更新；松手后真正持久化
      uiSet('results.gantt_cursor', value, `甘特图游标拖动结束，位置=${value}`, {silent: true});
      return;
    }
    if (!state.cursorDrag) return;
    const changed = state.cursorDrag.original === null || Number(state.project.result_layout.cursor_times[state.cursorDrag.index]) !== state.cursorDrag.original;
    state.cursorDrag = null;
    if (changed) { markDirty(); scheduleInteractionCommit(); }
  });
  window.addEventListener('pointermove', event => {if(state.ganttPan){const root=$('#simulationGantt');root.scrollLeft=state.ganttPan.left-(event.clientX-state.ganttPan.x);}});
  window.addEventListener('pointercancel', () => { state.ganttCursorDrag=false;state.ganttPan=null;$('#simulationGantt')?.classList.remove('panning');state.cursorDrag = null; drawResultAxes(); });
  $('#optimizeButton').addEventListener('click', runOptimization);
  $('#refreshResultsButton').addEventListener('click', event => { event.preventDefault(); event.stopPropagation(); Promise.all([refreshJobs(), refreshArtifacts()]); });
  $('#cancelActiveJob').addEventListener('click', cancelActiveJob);
  $('#runAgentButton').addEventListener('click', runAgent);
  $('#skillSelect').addEventListener('change', renderSkillOverview);
  $('#saveLlmConfigButton').addEventListener('click', () => saveLlmConfig().catch(error => toast(error.message, 'error')));
  $('#testLlmButton').addEventListener('click', testLlmConnection);
  $('#quickRunButton').addEventListener('click', () => runAgent('simulate-report'));
  $('#hubLabButton').addEventListener('click', () => openHubLab());
  $('#hubNewProjectButton').addEventListener('click', createProjectFromPrompt);
  $('#hubAddCategoryButton').addEventListener('click', addProjectCategory);
  $('#hubDeleteCategoryButton').addEventListener('click', deleteProjectCategory);
  $('#modelAssetCategorySelect').addEventListener('change', event => { if (state.modelAssetManagerContext?.mode === 'manage') void loadModelAssetLibrary(event.target.value); });
  $('#modelAssetNewVersionButton').addEventListener('click', createModelAssetVersion);
  $('#modelAssetCopyVersionButton').addEventListener('click', copyModelAssetVersion);
  $('#modelAssetDeleteVersionButton').addEventListener('click', deleteModelAssetVersion);
  $('#modelAssetUploadFilesButton').addEventListener('click', () => $('#modelAssetFilesInput').click());
  $('#modelAssetUploadFolderButton').addEventListener('click', () => $('#modelAssetFolderInput').click());
  $('#modelAssetFilesInput').addEventListener('change', event => { void uploadModelAssetVersionFiles(event.target); });
  $('#modelAssetFolderInput').addEventListener('change', event => { void uploadModelAssetVersionFiles(event.target); });
  $('#modelAssetConfirmBindingButton').addEventListener('click', () => void confirmModelAssetBinding());
  $('#modelAssetClearFolderButton').addEventListener('click', () => void clearModelAssetVersionFiles());
  $('#hubImportProjectButton').addEventListener('click', importProjectFromDefaultFolder);
  $('#hubExportProjectButton').addEventListener('click', () => exportSelectedProject().catch(error => toast(error.message, 'error')));
  $('#hubImportBundleButton').addEventListener('click', () => $('#projectBundleInput').click());
  $('#hubExportBundleButton').addEventListener('click', () => exportSelectedBundle().catch(error => toast(error.message, 'error')));
  $('#projectJsonInput').addEventListener('change', event => importProjectJson(event.target.files[0]).finally(() => { event.target.value = ''; }));
  $('#projectBundleInput').addEventListener('change', event => importProjectBundle(event.target.files[0]).finally(() => { event.target.value = ''; }));
  $('#hubProjectSearch').addEventListener('input', renderHub);
  $('#hubBaselineSortToggle').addEventListener('click', () => { state.hubBaselineSortDescending = !state.hubBaselineSortDescending; renderHub(); });
  $('#saveSkillButton').addEventListener('click', saveSkill);
  $('#scanMeshPathButton').addEventListener('click', scanMeshPath);
  $('#modelJsonUploadButton').addEventListener('click', () => $('#modelJsonFileInput').click());
  $('#modelDeliveryDownloadFolderButton')?.addEventListener('click',downloadWholeDeliveryFolder);
  $('#modelDeliveryClearButton')?.addEventListener('click',clearDeliveryFiles);
  $('#modelJsonFileInput').addEventListener('change', event => replaceModelProjectJson(event.target.files?.[0]).finally(() => { event.target.value=''; }));
  $('#localMeshSyncButton')?.addEventListener('click', syncLocalMeshes);
  $('#localMeshPathButton')?.addEventListener('click', selectLocalMeshPath);
  $('#repairMeshesButton').addEventListener('click', repairMeshes);
  $('#meshSearch').addEventListener('input', renderMeshLibrary);
  $('#variablesPanel').addEventListener('toggle', event => { if (!state.suppressUiEvents) uiSet('drives.variables_open', event.currentTarget.open, event.currentTarget.open ? '展开驱动变量面板' : '收起驱动变量面板'); });
  document.addEventListener('mousedown', event => {
    const select = event.target.closest?.('select[multiple][data-bind^="distance_pairs."]');
    if (!select || event.target.tagName !== 'OPTION' || !canEditProject()) return;
    // Native multiple-select focus may scroll back to the first selected option.
    // Preserve the viewport, not merely the selection, for every subsequent click.
    const scrollTop = select.scrollTop, scrollLeft = select.scrollLeft;
    event.preventDefault();
    event.target.selected = !event.target.selected;
    select.dispatchEvent(new Event('change', {bubbles:true}));
    select.focus({preventScroll:true});
    select.scrollTop = scrollTop;
    select.scrollLeft = scrollLeft;
    requestAnimationFrame(() => {
      if (!select.isConnected) return;
      select.scrollTop = scrollTop;
      select.scrollLeft = scrollLeft;
    });
  });
  document.addEventListener('pointerdown', event => {
    const splitter=event.target.closest?.('[data-hub-asset-splitter]');if(!splitter)return;
    const split=splitter.closest('.hub-asset-split');if(!split)return;
    state.hubInspectorAssetDrag={split,rect:split.getBoundingClientRect()};splitter.setPointerCapture?.(event.pointerId);event.preventDefault();
  });
  window.addEventListener('pointermove', event => {
    const drag=state.hubInspectorAssetDrag;if(!drag)return;
    const ratio=Math.max(.22,Math.min(.72,(event.clientY-drag.rect.top)/Math.max(1,drag.rect.height)));
    state.hubInspectorAssetSplitRatio=ratio;drag.split.style.setProperty('--hub-asset-top',`${Math.round(ratio*100)}%`);event.preventDefault();
  });
  window.addEventListener('pointerup', () => { state.hubInspectorAssetDrag=null; });
  document.addEventListener('pointerdown', event => {
    const splitter=event.target.closest?.('[data-diagram-layout-splitter]'); if(!splitter || hierarchyViewMode()!=='diagram')return;
    const studio=splitter.closest('.model-studio'); if(!studio)return;
    state.hierarchyDiagramLayoutGesture={kind:splitter.dataset.diagramLayoutSplitter,rect:studio.getBoundingClientRect(),start:hierarchyDiagramLayoutState()};
    splitter.setPointerCapture?.(event.pointerId); event.preventDefault();
  });
  window.addEventListener('pointermove', event => {
    const drag=state.hierarchyDiagramLayoutGesture; if(!drag)return;
    if(drag.kind==='property') hierarchyDiagramSetLayout({property_height:drag.rect.bottom-event.clientY,library_width:drag.start.library_width},'框图建模：调整属性视窗高度',{transient:true,silent:true});
    else if(drag.kind==='library') hierarchyDiagramSetLayout({property_height:drag.start.property_height,library_width:drag.rect.right-event.clientX},'框图建模：调整数模库宽度',{transient:true,silent:true});
    event.preventDefault();
  });
  window.addEventListener('pointerup', () => {
    const drag=state.hierarchyDiagramLayoutGesture; if(!drag)return;
    state.hierarchyDiagramLayoutGesture=null;
    hierarchyDiagramSetLayout(hierarchyDiagramLayoutState(), drag.kind==='property'?'框图建模：保存属性视窗高度':'框图建模：保存数模库宽度');
  });
  document.addEventListener('keydown', event => {
    const splitter=event.target.closest?.('[data-hub-asset-splitter]');if(!splitter||!['ArrowUp','ArrowDown'].includes(event.key))return;
    const delta=event.key==='ArrowUp'?-.04:.04;state.hubInspectorAssetSplitRatio=Math.max(.22,Math.min(.72,state.hubInspectorAssetSplitRatio+delta));
    splitter.closest('.hub-asset-split')?.style.setProperty('--hub-asset-top',`${Math.round(state.hubInspectorAssetSplitRatio*100)}%`);event.preventDefault();
  });
  window.addEventListener('beforeunload', event => {
    if (state.dirty) {
      event.preventDefault();
      event.returnValue = '当前模型仍有尚未完成持久化的修改。';
    }
  });
  window.addEventListener('keydown', event => {
    const editingTarget = event.target.closest?.('input,textarea,select,[contenteditable="true"]');
    if (event.key === 'Delete' && !editingTarget && hierarchyViewMode() === 'diagram' && state.hierarchyDiagramSelection) {
      if (deleteHierarchyDiagramSelection()) event.preventDefault();
      return;
    }
    if ((event.ctrlKey || event.metaKey) && !event.altKey) {
      if (event.key.toLowerCase() === 'z' && !event.shiftKey) { event.preventDefault(); undoOrRedo('undo'); }
      if (event.key.toLowerCase() === 'y' || (event.key.toLowerCase() === 'z' && event.shiftKey)) { event.preventDefault(); undoOrRedo('redo'); }
      return;
    }
    const nativeEnterAction = event.target?.closest?.('dialog,[role="dialog"],textarea,[contenteditable="true"],button,a,summary,[role="button"],[role="link"]');
    const nativeInputAction = event.target?.matches?.('input[type="checkbox"],input[type="radio"],input[type="file"],input[type="color"],input[type="range"],input[type="button"],input[type="submit"],input[type="reset"]');
    if (event.key === 'Enter' && !event.isComposing && !event.repeat && !event.ctrlKey && !event.altKey && !event.metaKey &&
        !nativeEnterAction && !nativeInputAction) {
      if (event.target.closest('dialog,[role="dialog"]')) return; // Enter confirms dialogs, not simulations.
      if (event.target.matches('#hubProjectNameInput,#hubMeshRootInput,#hubCategoryInput')) {
        event.preventDefault(); saveHubProperties(); return;
      }
      const route = routeContextFromLocation();
      if (route.kind !== 'editor' || !canEditProject() || state.editSessionMode !== 'persistent') return;
      event.preventDefault();
      event.target.dispatchEvent(new Event('change', {bubbles:true}));
      if (state.enterCommitRunning) return;
      state.enterCommitRunning = true;
      void (async () => {
        try {
          // A server error must prevent the subsequent calculation; never claim
          // that stale coordinates correspond to an unsynced local draft.
          const changedDriveInputs = Boolean(state.dirty);
          if (typeof snapshotActiveResultLayout === 'function') snapshotActiveResultLayout();
          // V2.16.6.2: Enter commits the active timeline directly. Only an
          // explicit switch in the time-series picker may request a snapshot.
          await flushInteractionCommit({finalize:true});
          await syncLocalDraft({quiet:true});
          renderAll();
          // PNG refresh is a separate light path: it cannot hold up coordinate
          // submission and a failed PNG write cannot invalidate saved edits.
          if (changedDriveInputs) void window.__GanttPopup__?.refreshCache?.(state.project.id)
            .catch(error => console.warn('[enter] PNG cache refresh:', error));
          await runSimulation({skipSave:true, fromEnter:true});
        } catch (error) {
          $('#dirtyBadge').textContent = '保存受阻';
          $('#dirtyBadge').title = '本次修改未能同步；本机草稿仍保留';
          toast(`当前修改未能完成保存和坐标系刷新：${error.message}`, 'error');
        } finally { state.enterCommitRunning = false; }
      })();
    }
  });
}

$('#vzEngineerButton')?.addEventListener('click', () => {
  window.open(integratedVzUrl('/engineer'), '_blank', 'noopener');
});

async function setHubVzPush(enabled, control = null) {
  const projectId = state.hubSelectedProjectId || state.hubPreview?.id;
  if (!projectId) return;
  if (control) control.disabled = true;
  try {
    const result = await api(`/api/projects/${encodeURIComponent(projectId)}/vz-push`, {method:'PUT', body:JSON.stringify({enabled:Boolean(enabled)})});
    const next = result.vz_push || {enabled:Boolean(enabled)};
    if (state.hubPreview?.id === projectId) state.hubPreview.vz_push = next;
    state.projects = state.projects.map(project => project.id === projectId ? {...project, vz_push:next} : project);
    renderHub();
    toast(enabled ? '模型已推送到 VZ 模型库' : '已关闭推送并同步移出 VZ 模型库', 'success');
  } catch (error) {
    if (control) control.checked = !enabled;
    toast(`VZ 模型推送失败：${error.message}`, 'error');
  } finally {
    if (control?.isConnected) control.disabled = false;
  }
}

function handleEntityAction(element) {
  // V2.16.6.1: fold is purely visual and must work in read-only mode.
  if (element.dataset.action === 'toggle-result-axis-tools') { toggleResultAxisControls(element); return; }
  const action = element.dataset.action;
  const li = Number(element.dataset.layer), ji = Number(element.dataset.joint), mi = Number(element.dataset.mesh), di = Number(element.dataset.drive), si = Number(element.dataset.segment), pi = Number(element.dataset.pair);
  if (action === 'source-to-companion' || action === 'companion-to-source') {
    const mdi=Number(element.dataset.mappingDrive),msi=Number(element.dataset.mappingSegment);
    const drive=state.project.drives[di],segment=drive?.segments?.[si],mapping=state.project.drives[mdi]?.segments?.[msi];if(!drive||!segment||!mapping)return;
    const relation={segment:mapping},key=`${segment.id}:${mapping.id}`,rows=mappingRows(mapping),start=sourceSegmentStart(drive,segment,si,relation);
    try {
      if(action==='source-to-companion'){state.companionTravels.set(key,mappedTravelExpression(rows,start,segment.travel));renderDrives();toast('已由源头行程映射伴生行程');}
      else {segment.travel=mappedTravelExpression(rows,start,state.companionTravels.get(key)||'',true);state.companionTravels.delete(key);markDirty();renderDrives();scheduleInteractionCommit();toast('已由伴生行程反查源头行程');}
    } catch(error){toast(`行程映射失败：${error.message}`,'error');}
    return;
  }
  if (action === 'toggle-hierarchy-view') {
    const next = hierarchyViewMode() === 'diagram' ? 'tree' : 'diagram';
    state.hierarchyDiagramSelection = null;
    state.hierarchyDiagramMultiSelection = new Set();
    state.hierarchyDiagramSuppressPaneClick = false;
    state.hierarchyDiagramInteraction = null;
    state.hierarchyDiagramViewportGesture = null;
    clearTimeout(state.hierarchyDiagramViewportCommitTimer); state.hierarchyDiagramViewportCommitTimer = null;
    uiSet('model.hierarchy_view', next, `层级建模视图切换为${next === 'diagram' ? '框图建模' : '层级建模'}`);
    // V2.10.5: entering diagram mode never writes auto-layout. Saved manual geometry
    // is authoritative; legacy nodes without geometry use a non-persisted stable grid.
    renderLayers(); return;
  }
  if (action === 'diagram-auto-arrange') { hierarchyDiagramPersistAutoLayout(); return; }
  if (action === 'diagram-link-kind') {
    state.hierarchyDiagramLinkKind = element.dataset.kind === 'closure' ? 'closure' : 'parent';
    renderHierarchyDiagram(); return;
  }
  if (action === 'diagram-select-tree-edge') {
    const childId = element.dataset.childId; if (!childId) return;
    const pick = state.hierarchyDiagramInteraction?.kind === 'closure-joint-pick' ? state.hierarchyDiagramInteraction : null;
    if (pick) {
      const closure = (state.project.kinematic_closures || []).find(item => item.id === pick.closureId);
      if (!closure) { state.hierarchyDiagramInteraction = null; renderLayers(); return; }
      const path = new Set(hierarchyDiagramTreePathEdgeIds(closure.endpoint_a?.layer_id, closure.endpoint_b?.layer_id));
      if (!path.has(childId)) return toast('该线段不属于当前闭链闭环，请选择闭环中的线段', 'error');
      const passiveIds = hierarchyDiagramEdgePassiveJointIds(childId, closure);
      if (!passiveIds.length) return toast('该线段没有可选从动运动副：可能已添加驱动、属于曲柄副或当前未激活', 'error');
      const selected = new Set(closure.solve_joint_ids || []);
      const allSelected = passiveIds.every(id => selected.has(id));
      passiveIds.forEach(id => allSelected ? selected.delete(id) : selected.add(id));
      closure.solve_joint_ids = [...selected];
      markDirty(); scheduleInteractionCommit(); renderLayers();
      toast(`${allSelected ? '取消' : '加入'}从动运动副线段：${byLayerName(state.project.layers.find(layer => layer.id === childId)?.parent_id)} → ${byLayerName(childId)}`);
      return;
    }
    state.hierarchyDiagramSelection = {type:'tree_edge', childId};
    state.selectedLayerId = childId;
    renderLayers(); return;
  }
  if (action === 'diagram-select-closure-edge') {
    const closureId = element.dataset.closureId;
    const closure = (state.project?.kinematic_closures || []).find(item => item.id === closureId); if (!closure) return;
    state.hierarchyDiagramSelection = {type:'closure_edge', closureId};
    state.selectedLayerId = closure.endpoint_b?.layer_id || closure.endpoint_a?.layer_id || state.selectedLayerId;
    renderLayers(); return;
  }
  if (action === 'diagram-close-selection') {
    state.hierarchyDiagramSelection = null;
    if (state.hierarchyDiagramInteraction?.kind === 'closure-joint-pick') state.hierarchyDiagramInteraction = null;
    renderLayers(); return;
  }
  if (action === 'diagram-pick-closure-joints') {
    const closureId = element.dataset.closureId;
    const closure = (state.project?.kinematic_closures || []).find(item => item.id === closureId); if (!closure) return;
    if (!canEditProject()) return toast('当前模型不可编辑，不能从画布选择闭链从动运动副', 'error');
    if (hierarchyDiagramClosureLocked(closure)) return toast('闭链连接到未激活层级，画布选择已锁定', 'error');
    const active = state.hierarchyDiagramInteraction?.kind === 'closure-joint-pick' && state.hierarchyDiagramInteraction.closureId === closureId;
    state.hierarchyDiagramInteraction = active ? null : {kind:'closure-joint-pick', closureId};
    renderLayers(); return;
  }
  if (action === 'hub-vz-push') { void setHubVzPush(Boolean(element.checked), element); return; }
  if (action === 'hub-toggle-category') { const category=element.dataset.category; if(state.hubCollapsedModelTypes.has(category))state.hubCollapsedModelTypes.delete(category);else state.hubCollapsedModelTypes.add(category); persistHubCollapseState(); renderHub(); return; }
  if (action === 'hub-toggle-all-categories') {
    const paths=collapsibleModelTypePaths();
    const allCollapsed=paths.length>0 && paths.every(path=>state.hubCollapsedModelTypes.has(path));
    state.hubCollapsedModelTypes=allCollapsed ? new Set() : new Set(paths);
    persistHubCollapseState();
    renderHub(); return;
  }
  if (action === 'hub-category') { const category=element.dataset.category;state.hubCategory=category;clearHubProjectSelection();if(category!=='__recycle_bin__')state.hubSelectedTrashIds.clear();renderHub();if(category!=='__recycle_bin__')loadHubTypeSummary(category);return; }
  if (action === 'hub-trash-toggle') { const trashId=element.dataset.trashId;if(!trashId)return;if(element.checked)state.hubSelectedTrashIds.add(trashId);else state.hubSelectedTrashIds.delete(trashId);renderHub();return; }
  if (action === 'hub-trash-select-all') { const query=($('#hubProjectSearch').value||'').trim().toLowerCase();const visible=state.recycleBin.filter(item=>!query||[item.name,item.category,item.project_id].join(' ').toLowerCase().includes(query));state.hubSelectedTrashIds=element.checked?new Set(visible.map(item=>item.trash_id).filter(Boolean)):new Set();renderHub();return; }
  if (action === 'hub-delete-selected-trash') { void deleteSelectedHubTrashProjects(); return; }
  if (action === 'hub-restore-trash') { void restoreHubTrashProject(element.dataset.trashId); return; }
  if (action === 'hub-select-project') { const projectId=element.dataset.projectId; state.hubSelectedProjectId = projectId; state.hubTypeSummary = null; state.hubPreviewVersionId = null; state.hubInspectorSection = hubInspectorDefaultSection(); primeHubPreviewFromCatalog(projectId); renderHub(); void loadHubPreview(projectId,{waitForMetadata:false}).then(()=>activateHubInspectorSection(state.hubInspectorSection,{force:true})).catch(error=>toast(error.message||String(error),'error')); return; }
  if (action === 'hub-inspector-section') { void activateHubInspectorSection(element.dataset.inspectorSection); return; }
  if (action === 'hub-asset-select-folder') { void loadModelAssetLibrary(state.modelAssetManager?.category, element.dataset.assetFolder); return; }
  if (action === 'hub-asset-new-version') { void createModelAssetVersion(); return; }
  if (action === 'hub-asset-copy-version') { void copyModelAssetVersion(); return; }
  if (action === 'hub-asset-rename-version') { void renameModelAssetVersion(); return; }
  if (action === 'hub-asset-delete-version') { void deleteModelAssetVersion(); return; }
  if (action === 'hub-asset-upload-files') { $('#modelAssetFilesInput')?.click(); return; }
  if (action === 'hub-asset-upload-folder') { $('#modelAssetFolderInput')?.click(); return; }
  if (action === 'hub-asset-download-folder') { void downloadWholeModelAssetFolder(); return; }
  if (action === 'hub-asset-clear-folder') { void clearModelAssetVersionFiles(); return; }
  if (action === 'hub-asset-delete-file') { void deleteModelAssetFile(element.dataset.assetPath); return; }
  if (action === 'hub-asset-bind') { void confirmModelAssetBinding(); return; }
  if (action === 'hub-delivery-auto-suffix') { autoFillHubDeliverySuffix(); return; }
  if (action === 'hub-delivery-download') { void downloadHubDeliveryFile(element.dataset.deliveryPath); return; }
  if (action === 'hub-delivery-download-all') { void downloadWholeDeliveryFolder(); return; }
  if (action === 'hub-delivery-refresh') { void refreshHubDeliveryOutputs(); return; }
  if (action === 'hub-time-series-delete') { void deleteTimeSeriesFile(element.dataset.timeSeriesName); return; }
  if (action === 'hub-delivery-delete') { void deleteDeliveryFile(element.dataset.deliveryRelative); return; }
  if (action === 'hub-delivery-clear') { void clearDeliveryFiles(); return; }
  if (action === 'hub-archive-restore') { state.hubPreviewVersionId = element.dataset.versionId; void restoreHubVersion(); return; }
  if (action === 'hub-archive-delete') { void deleteHubArchiveVersion(element.dataset.versionId); return; }
  if (action === 'hub-archive-cutout') { void cutOutHubArchiveVersion(element.dataset.versionId); return; }
  if (action === 'hub-rename-folder') { renameHubFolder(); return; }
  if (action === 'hub-toggle-compare') { element.checked ? state.hubCompareIds.add(element.dataset.projectId) : state.hubCompareIds.delete(element.dataset.projectId); return; }
  if (action === 'hub-check-out') { transitionHubProject('check_out'); return; }
  if (action === 'hub-check-in') { transitionHubProject('check_in'); return; }
  if (action === 'hub-create-baseline') { createHubBaseline(); return; }
  if (action === 'hub-copy-version') { copyHubProjectVersion(); return; }
  if (action === 'hub-fork-project') { forkHubProject(); return; }
  if (action === 'hub-delete-project') { deleteHubProject(); return; }
  if (action === 'hub-open-files') { openModelFiles(element.dataset.fileGroup); return; }
  if (action === 'hub-save-category' || action === 'hub-save-properties') { saveHubProperties(); return; }
  if (action === 'hub-browse-mesh-root') { browseHubMeshRoot(); return; }
  if (action === 'hub-open-project-folder') { openProjectFolder(); return; }
  if (action === 'hub-bind-project-folder') { bindProjectDeliveryFolder(); return; }
  if (action === 'hub-open-lab') { openHubLab(element.dataset.projectId || state.hubSelectedProjectId); return; }
  if (action === 'hub-open-animation') { openAnimationResult(element.dataset.projectId); return; }
  if (action === 'quick-run-all') { runQuickOptimization(); return; }
  if (action === 'quick-run-step') { runQuickOptimization([element.dataset.stepId]); return; }
  if (action === 'quick-load-all') { loadQuickOptimizationResults(); return; }
  if (action === 'quick-load-step') { loadQuickOptimizationResults([element.dataset.stepId]); return; }
  if (action === 'quick-preview') { previewQuickOptimization(); return; }
  if (action === 'quick-export') { exportQuickWorkflow(); return; }
  if (action === 'quick-import') { $('#quickWorkflowInput').click(); return; }
  if (action === 'quick-save') { commitEdits().catch(error=>toast(error.message,'error')); return; }
  if (action === 'quick-toggle-step') {
    const step=quickOptimization().steps.find(item=>item.id===element.dataset.stepId); if(!step)return;
    step.collapsed=!step.collapsed; markDirty(); renderQuickOptimization(); return;
  }
  if (action === 'quick-remove-step') {
    const index=quickOptimization().steps.findIndex(item=>item.id===element.dataset.stepId); if(index<0)return;
    quickOptimization().steps.splice(index,1); markDirty(); renderDrives(); renderQuickOptimization(); return;
  }
  if (action === 'toggle-segment-advanced') { const key=element.dataset.segmentKey; const open=!state.expandedSegments.has(key); open ? state.expandedSegments.add(key) : state.expandedSegments.delete(key); renderDrives(); uiSet(`drives.expanded_segments.${key}`, open, open ? `展开运动段高级配置：${key}` : `折叠运动段高级配置：${key}`); return; }
  if (action === 'toggle-closure-joints') {
    state.expandedClosureId = state.expandedClosureId === element.dataset.closureId ? '' : element.dataset.closureId;
    renderLayers(); applyProjectAccess(); return;
  }
  if (action === 'adaptive-closure-joints') {
    const closure = state.project.kinematic_closures?.[Number(element.dataset.closure)];
    if (!closure) return;
    closure.solve_joint_ids = adaptiveClosureJointIds(closure);
    markDirty(); scheduleInteractionCommit(); renderLayers();
    toast(closure.solve_joint_ids.length ? `已自适应选择 ${closure.solve_joint_ids.length} 个从动运动副` : '当前没有可用从动运动副', closure.solve_joint_ids.length ? 'success' : 'error');
    return;
  }
  if (action === 'toggle-pair-objects') {
    const next = state.ui.distance?.expanded_pair === element.dataset.pairId ? '' : element.dataset.pairId;
    uiSet('distance.expanded_pair', next, next ? `展开测距对象面板：${next}` : `折叠测距对象面板`);
    renderPairs(); applyProjectAccess();
    if (next && element.dataset.pairFocus) requestAnimationFrame(() => $(`[data-pair-list="${element.dataset.pairFocus}"] select`)?.focus({preventScroll:true}));
    return;
  }
  if (action === 'copy-segment-variables') {
    const text = segmentVariableText(state.project.drives[di], state.project.drives[di].segments[si], si);
    if (navigator.clipboard?.writeText) navigator.clipboard.writeText(text).then(() => toast('变量信息已复制')).catch(() => prompt('复制变量信息', text));
    else prompt('复制变量信息', text);
    return;
  }
  if (action === 'choose-mapping-csv') { element.closest('.motion-segment-row')?.querySelector('[data-mapping-csv]')?.click(); return; }
  if (action === 'export-mapping-csv') { void exportMotorTableCsv(di,si,'mapping'); return; }
  if (action === 'export-external-motion-csv') { void exportMotorTableCsv(di,si,'external_motion'); return; }
  if (action === 'choose-external-motion-csv') { element.closest('.motion-segment-row')?.querySelector('[data-external-motion-csv]')?.click(); return; }
  if (action === 'adaptive-result-axis-name') { adaptiveResultAxisName(Number(element.dataset.axis)); return; }
  if (action === 'add-result-curve') {
    const axis = state.project.result_layout.axes[Number(element.dataset.axis)]; const source = resultSourceCatalog().find(item => item.group === 'drive');
    axis.curves.push({id:uid('curve'), source:source?.key || '', label:source?.label || `曲线${axis.curves.length+1}`, operation:'raw', color:['#2563eb','#263f5f','#314f3f','#4a354f'][axis.curves.length % 4]}); markDirty(); renderResultViewer();
    if (!source) void requestResultSimulationIfEmpty();
    return;
  }
  if (action === 'remove-result-axis') { state.project.result_layout.axes.splice(Number(element.dataset.axis), 1); markDirty(); renderResultViewer(); refreshCombinedGanttSchedule(); return; }
  if (action === 'remove-result-curve') { state.project.result_layout.axes[Number(element.dataset.axis)].curves.splice(Number(element.dataset.curve), 1); markDirty(); renderResultViewer(); refreshCombinedGanttSchedule(); return; }
  if (action === 'export-result-axis') { exportResultAxis(Number(element.dataset.axis)); return; }
  if (action === 'hub-preview-version') { loadHubVersionPreview(element.dataset.versionId); return; }
  if (action === 'hub-restore-version') { restoreHubVersion(); return; }
  if (action === 'hub-close-comparison') { $('#hubComparison').classList.add('hidden'); return; }
  if (action === 'toggle-layer-advanced') { state.expandedLayerAdvanced.has(element.dataset.layerId) ? state.expandedLayerAdvanced.delete(element.dataset.layerId) : state.expandedLayerAdvanced.add(element.dataset.layerId); renderLayerDetails(); return; }
  if (action === 'mesh-two-columns') {
    state.editorLayout.meshTwoColumns = element.checked;
    renderLayerDetails(); return;
  }
  if (action === 'layer-mass-toggle') {
    uiSet(`model.mass_enabled_layers.${element.dataset.layerId}`, element.checked, element.checked ? `显示层级质量编辑：${element.dataset.layerId}` : `隐藏层级质量编辑：${element.dataset.layerId}`);
    renderLayerDetails(); return;
  }
  if (action === 'select-layer') { state.selectedLayerId = element.dataset.layerId; renderLayers(); return; }
  if (action === 'select-root') { state.selectedLayerId = null; renderLayers(); return; }
  if (action === 'adaptive-all-meshes') { adaptiveAllMeshFamilies(li); return; }
  if (action === 'adaptive-all-project-meshes') { adaptiveAllProjectMeshFamilies(); return; }
  if (action === 'add-child-layer') { addChildLayer(li); return; }
  if (action === 'remove-layer') removeLayerAtIndex(li);
  if (action === 'duplicate-layer') {
    duplicateLayerBranch(li, confirm('是否同时复制该层级的全部子层级及层级关系？'));
  }
  if (action === 'promote-layer') promoteLayer(li);
  if (action === 'demote-layer') demoteLayer(li);
  if (action === 'add-closure') {
    const layerId = state.project.layers[0]?.id || '';
    if (!layerId) { toast('请先创建至少一个层级，再添加闭链', 'error'); return; }
    state.project.kinematic_closures ||= [];
    state.project.kinematic_closures.push({
      id:uid('closure'), name:`闭链${state.project.kinematic_closures.length + 1}`, enabled:true, kind:'point',
      endpoint_a:{layer_id:layerId, point_mm:[0,0,0]}, endpoint_b:{layer_id:layerId, point_mm:[0,0,0]},
      solve_joint_ids:[], tolerance_mm:0.05, max_iterations:40, damping:0.0001, max_angle_step_deg:8, max_slide_step_mm:5,
    });
  }
  if (action === 'remove-closure') state.project.kinematic_closures?.splice(Number(element.dataset.closure), 1);
  if (action === 'add-joint') {
    const layer = state.project.layers[li];
    if ((layer.meshes || []).length > 1 && !confirm(`当前层级“${layer.name}”包含 ${layer.meshes.length} 个数模。\n\n运动副会作用于整个层级刚体，不会只绑定某一个数模。\n如果你希望新增物体相对当前物体旋转，应把新增物体建立为当前层级的 child Layer，再把旋转副加在 child Layer 上。\n\n仍要给整个层级添加运动副吗？`)) return;
    const joint = newJoint(layer.joints.length);
    if (hierarchyViewMode() === 'diagram' && state.hierarchyDiagramSelection?.type === 'tree_edge' && state.hierarchyDiagramSelection.childId === layer.id) {
      const parent = state.project.layers.find(item => item.id === layer.parent_id);
      if (parent) joint.name = uniqueName(`${parent.name}——>${layer.name}`, state.project.layers.flatMap(item => (item.joints || []).map(existing => existing.name)));
    }
    layer.joints.push(joint);
    hierarchyDiagramSyncAllClosurePassiveJoints();
  }
  if (action === 'remove-joint') {
    const joint = state.project.layers[li].joints[ji];
    const removedDrives = removeJointReferences([joint.id]);
    state.project.layers[li].joints.splice(ji, 1);
    hierarchyDiagramSyncAllClosurePassiveJoints();
    if (removedDrives) toast(`运动副已删除，并同步移除 ${removedDrives} 个关联驱动`);
  }
  if (action === 'remove-mesh') state.project.layers[li].meshes.splice(mi, 1);
  if (action === 'set-mesh-color') { const input=element.closest('.mesh-color')?.querySelector('input[type="color"]'); if(input){input.disabled=false;input.click();} return; }
  if (action === 'follow-layer-color') state.project.layers[li].meshes[mi].rgba = '';
  if (action === 'clear-mesh-color') state.project.layers[li].meshes[mi].rgba = '';
  if (action === 'remove-drive') { state.project.drives.splice(di, 1); hierarchyDiagramSyncAllClosurePassiveJoints(); }
  if (action === 'add-segment') { const drive=state.project.drives[di]; drive.segments.push(newSegment(drive.segments.length)); renumberSegments(drive); }
  if (action === 'remove-segment') { const drive=state.project.drives[di]; drive.segments.splice(si, 1); renumberSegments(drive); }
  if (action === 'remove-pair') state.project.distance_pairs.splice(pi, 1);
  if (action === 'remove-range') state.project.optimization.variables.splice(Number(element.dataset.range), 1);
  if (action === 'remove-variable') { const key = Object.keys(state.project.variables)[Number(element.dataset.variable)]; delete state.project.variables[key]; }
  markDirty(); renderAll();
}

function addChildLayer(parentIndex) {
  if (!canEditProject()) return toast('当前模型只读，请先签出再添加子层级', 'error');
  const parent = state.project?.layers?.[parentIndex];
  if (!parent) return toast('未找到要添加子层级的父层级', 'error');
  if (parent.active === false) return toast('未激活层级已锁定，不能添加子层级', 'error');
  state.selectedLayerId = parent.id;
  const child = newLayer();
  child.parent_id = parent.id;
  child.name = uniqueName(`${parent.name}_child`, state.project.layers.map(layer => layer.name));
  state.project.layers.push(child);
  state.selectedLayerId = child.id;
  if (hierarchyViewMode() === 'diagram') state.hierarchyDiagramSelection = {type:'node', layerId:child.id};
  markDirty(); renderAll(); scheduleInteractionCommit();
  toast(`已在“${parent.name}”下添加子层级“${child.name}”`, 'success');
}

function newLayer() { return {id:uid('layer'), name:uniqueName('layer', state.project.layers.map(item=>item.name)), parent_id:state.selectedLayerId || 'root', active:true, color:'0.72 0.75 0.80 1', position_mm:[0,0,0], mass_kg:null, meshes:[], joints:[]}; }
function isLayerInBranch(layerId, rootId) {
  if (!layerId) return false;
  const byId = new Map(state.project.layers.map(layer => [layer.id, layer]));
  let current = byId.get(layerId), guard = new Set();
  while (current && !guard.has(current.id)) {
    if (current.id === rootId) return true;
    guard.add(current.id); current = byId.get(current.parent_id);
  }
  return false;
}
function newJoint(index=0) { return {id:uid('joint'), name:index ? `joint1_${index}` : 'joint1', type:'rotation', point:'0, 0, 0', axis:'0, 1, 0', crank_center:'0, 0, 0', crank_end:'0, 10, 0', rod_end:'30, 0, 0', slide_axis:'1, 0, 0', reverse:false, limited:false, range:[-180,180], damping:.1, armature:.01, frictionloss:0, stiffness:0, spring_reference:0, parameters:{}}; }
function newSegment(index=0) { return {id:uid('seg'), name:`seg${index+1}`, start_mode:'direct', start:0, reference:'', reference_boundary:'end', mode:'duration', duration:1, speed:30, travel:30, profile:'s_curve', ease_in:true, ease_out:true, easing_mode:'time', ease_in_time:.2, ease_out_time:.2, ease_in_acceleration:150, ease_out_acceleration:150, acceleration_time:.2, points:[], csv_path:'', external_csv_name:'', external_csv_header:'', external_csv_source_metric:'', mapping_source_joint_id:'', mapping_csv_name:'', mapping_point_count:0}; }
function newDrive(jointId) { return {id:uid('drive'), name:uniqueName('act', state.project.drives.map(item=>item.name), true), joint_id:jointId, role:'', enabled:true, dynamic_kp:100, dynamic_kv:20, dynamic_lock_force:2000, segments:[newSegment()]}; }
function adaptiveAddDrives() {
  const bound=new Set(state.project.drives.map(item=>item.joint_id));
  const pending=state.project.layers.flatMap(layer=>(layer.joints||[]).filter(joint=>!bound.has(joint.id)));
  if(!pending.length)return toast('所有运动副均已绑定驱动');
  const desired=pending.map(joint=>String(joint.name||'').trim());
  if(desired.some(name=>!name))return toast('存在未命名运动副，无法创建同名驱动','error');
  const duplicates=desired.filter((name,index)=>desired.indexOf(name)!==index);
  if(duplicates.length)return toast(`存在同名运动副“${duplicates[0]}”，无法保证驱动同名唯一绑定`,'error');
  const occupied=new Map(state.project.drives.map(drive=>[String(drive.name||''),drive]));
  const conflict=pending.find(joint=>occupied.has(String(joint.name||'').trim())&&occupied.get(String(joint.name||'').trim())?.joint_id!==joint.id);
  if(conflict)return toast(`驱动名称“${conflict.name}”已被其他运动副占用，请先处理名称冲突`,'error');
  pending.forEach(joint=>{const drive=newDrive(joint.id);drive.name=String(joint.name).trim();state.project.drives.push(drive);});
  hierarchyDiagramSyncAllClosurePassiveJoints();
  markDirty(); renderAll(); scheduleInteractionCommit(); toast(`已按当前层级运动副名称自适应添加并绑定 ${pending.length} 个驱动`);
}
function newPair() { /* V2.5.2: creating a distance pair must not mutate project.variables. */ return {id:uid('pair'), name:uniqueName('distance', state.project.distance_pairs.map(item=>item.name), true), objects_a:[], objects_b:[], strategy_spacing_mm:12, precise_spacing_mm:2, animation_spacing_mm:2, boundary_mm:8, distmax_m:.1}; }
function uniqueName(prefix, names, numeric=false) { let index=1, name=numeric ? `${prefix}${index}` : prefix; while(names.includes(name)) { index++; name=numeric ? `${prefix}${index}` : `${prefix}_${index}`; } return name; }
function renumberSegments(drive) {
  const changes = new Map();
  drive.segments.forEach((segment,index) => { const next=`seg${index+1}`; changes.set(String(segment.name||''),next); segment.name=next; });
  state.project.drives.forEach(item => item.segments.forEach(segment => {
    const [driveName,segmentName] = String(segment.reference||'').split('/');
    if (driveName===drive.name && changes.has(segmentName)) segment.reference=`${driveName}/${changes.get(segmentName)}`;
  }));
}

async function exportMotorTableCsv(driveIndex, segmentIndex, kind) {
  try {
    if (state.dirty) await commitEdits();
    const projectId = state.project?.id;
    const drive = state.project?.drives?.[driveIndex];
    const segment = drive?.segments?.[segmentIndex];
    if (!projectId || !drive || !segment) return toast('运动段已变化，请刷新页面重试', 'error');
    const route = kind === 'mapping' ? 'mapping-csv' : 'external-motion-csv';
    const result = await api(`/api/projects/${encodeURIComponent(projectId)}/${route}/export`, {
      method:'POST', body:JSON.stringify({drive_id:drive.id, segment_id:segment.id}),
    });
    await downloadCsv(result.filename, result.content);
    toast(result.backed_up ? '表格已覆盖备份至 Hub / 表格资产，并完成 CSV 导出' : '已从当前模型内嵌点表导出 CSV；只读/临时模型未改动资产', 'success');
  } catch (error) { toast(`表格导出失败：${error.message}`, 'error'); }
}

async function uploadMappingCsv(driveIndex, segmentIndex, file) {
  try {
    if (state.dirty) await commitEdits();
    const drive=state.project.drives[driveIndex], segment=drive?.segments?.[segmentIndex]; if(!segment)return;
    const form=new FormData(); form.append('drive_id',drive.id);form.append('segment_id',segment.id);form.append('file',file,file.name);
    const result=await api(`/api/projects/${state.project.id}/mapping-csv`,{method:'POST',body:form});
    state.project=result.project;clearDirty();await loadSimulationWorkspace();renderAll();toast(`已自动备份至 Hub / 表格资产，并导入 ${result.count} 个映射点`);
  } catch(error){toast(error.message,'error');}
}

async function uploadExternalMotionCsv(driveIndex, segmentIndex, file) {
  try {
    if (state.dirty) await commitEdits();
    const drive=state.project.drives[driveIndex], segment=drive?.segments?.[segmentIndex]; if(!segment)return;
    const form=new FormData(); form.append('drive_id',drive.id);form.append('segment_id',segment.id);form.append('file',file,file.name);
    const result=await api(`/api/projects/${state.project.id}/external-motion-csv`,{method:'POST',body:form});
    state.project=result.project;clearDirty();await loadSimulationWorkspace();renderAll();
    toast(`已备份至 Hub / 表格资产，并导入 ${result.count} 个外部运动点 · ${result.source_metric || '位置'}`);
  } catch(error){toast(error.message,'error');}
}

function pruneInvalidClosureSolveJointRefs() {
  if (!state.project) return 0;
  const valid = new Set(
    state.project.layers
      .filter(layer => layer.active !== false)
      .flatMap(layer => (layer.joints || []).filter(joint => joint.type !== 'crank').map(joint => joint.id))
  );
  let removed = 0;
  (state.project.kinematic_closures || []).forEach(closure => {
    const before = closure.solve_joint_ids || [];
    const after = before.filter(id => valid.has(id));
    removed += before.length - after.length;
    closure.solve_joint_ids = after;
  });
  return removed;
}

function removeJointReferences(jointIds) {
  const removed = new Set(jointIds);
  const before = state.project.drives.length;
  state.project.drives = state.project.drives.filter(drive => !removed.has(drive.joint_id));
  state.project.drives.forEach(drive => drive.segments.forEach(segment => {
    if (removed.has(segment.mapping_source_joint_id)) segment.mapping_source_joint_id = '';
  }));
  (state.project.kinematic_closures || []).forEach(closure => { closure.solve_joint_ids = (closure.solve_joint_ids || []).filter(id => !removed.has(id)); });
  return before - state.project.drives.length;
}

function promoteLayer(index) {
  const layer = state.project.layers[index];
  if (!layer || layer.parent_id === 'root') return toast('当前层级已经位于顶层');
  const parent = state.project.layers.find(item => item.id === layer.parent_id);
  layer.parent_id = parent?.parent_id || 'root';
  hierarchyDiagramSyncAllClosurePassiveJoints();
}

function demoteLayer(index) {
  const layer = state.project.layers[index];
  const siblings = state.project.layers.filter(item => item.parent_id === layer.parent_id && item.id !== layer.id);
  const previous = [...siblings].reverse().find(item => state.project.layers.indexOf(item) < index);
  if (!previous) return toast('没有可作为新父级的同级层级', 'error');
  layer.parent_id = previous.id;
  hierarchyDiagramSyncAllClosurePassiveJoints();
}

function duplicateLayerBranch(index, includeChildren) {
  const source = state.project.layers[index];
  const sourceIds = new Set([source.id]);
  if (includeChildren) {
    let changed = true;
    while (changed) { changed = false; state.project.layers.forEach(item => { if (sourceIds.has(item.parent_id) && !sourceIds.has(item.id)) { sourceIds.add(item.id); changed = true; } }); }
  }
  const originals = state.project.layers.filter(item => sourceIds.has(item.id));
  const layerIds = new Map(originals.map(item => [item.id, uid('layer')]));
  const jointIds = new Map();
  const copies = originals.map(item => {
    const copy = deepClone(item); copy.id = layerIds.get(item.id);
    copy.name = uniqueName(`${item.name}_copy`, state.project.layers.map(entry => entry.name));
    copy.parent_id = item.id === source.id ? item.parent_id : (layerIds.get(item.parent_id) || item.parent_id);
    copy.meshes = copy.meshes.map(mesh => ({...mesh, id:uid('mesh')}));
    copy.joints = copy.joints.map(joint => { const id=uid('joint'); jointIds.set(joint.id,id); return {...joint,id}; });
    return copy;
  });
  state.project.layers.push(...copies); state.selectedLayerId = layerIds.get(source.id);
}

async function validateCurrent() {
  return withBlockingLoading({title:'正在检查项目', detail:'正在保存修改并检查配置、文件和模型引用，请等待。'}, async () => {
    try { await saveEditableDraft(); const issues = await api(`/api/projects/${state.project.id}/validate?check_files=true`, {method:'POST'}); renderIssues(issues); const errors = issues.filter(item=>item.severity==='error').length; toast(errors ? `发现 ${errors} 个错误` : '项目检查通过', errors ? 'error' : 'info'); } catch(error) { toast(error.message,'error'); }
  });
}
function renderIssues(issues) { const root=$('#healthList'); if(!root)return; root.classList.remove('empty-state'); root.innerHTML = issues.map(item=>`<div class="issue ${item.severity}"><span class="severity"></span><div><strong>${esc(item.message)}</strong><small>${esc(item.path || item.code)}</small></div></div>`).join(''); }

async function generateCurrent() { return withBlockingLoading({title:'正在生成 MuJoCo 模型',detail:'正在保存项目并生成 XML/派生文件，请等待。'},async()=>{try { await saveEditableDraft(); const result = await api(`/api/projects/${state.project.id}/generate`,{method:'POST'}); toast(`已生成 ${Object.keys(result).length-1} 个文件`); await refreshArtifacts(); } catch(error){toast(error.message,'error');}}); }
async function mujocoCheck() { return withBlockingLoading({title:'正在执行 MuJoCo 检查',detail:'正在生成并加载模型进行接触/间隙验证，请等待。'},async()=>{try { await saveEditableDraft(); const result = await api(`/api/projects/${state.project.id}/mujoco-check`,{method:'POST'}); toast(`MuJoCo 模型有效：${result.nbody} bodies / ${result.njnt} joints`); } catch(error){toast(error.message,'error');}}); }
const waitFor = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));
async function verifyLocalAdminViewer(projectId, pid, token) {
  if (!Number.isInteger(Number(pid)) || Number(pid) <= 0) throw new Error('服务端未返回有效的 MuJoCo Viewer 进程编号');
  let failures = 0;
  for (let attempt=0; attempt<60; attempt+=1) {
    await waitFor(1000);
    let status;
    try { status = await api(`/api/projects/${projectId}/local-viewer/${pid}/status`, {timeout:3000}); failures = 0; }
    catch (error) { if (++failures < 4) continue; throw new Error(`Viewer 状态连续查询失败：${error.message}`); }
    if(token) updateViewerProgress(token,status);
    if (!status.tracked) throw new Error(status.reason || '服务端未保留 MuJoCo Viewer 启动记录');
    if (!status.running) {
      if (status.exit_code === 0 && viewerSamplingStatus(status).ready) return status;
      throw new Error([status.reason,status.log_tail].filter(Boolean).join('\n') || 'MuJoCo Viewer 启动后异常退出');
    }
    if (viewerSamplingStatus(status).ready) return status;
  }
  throw new Error('MuJoCo Viewer 启动超时');
}
async function verifyLocalClientViewer(pid, token) {
  if (!Number.isInteger(Number(pid)) || Number(pid) <= 0) throw new Error('本地客户端未返回有效的 MuJoCo Viewer 进程编号');
  let failures = 0;
  for (let attempt = 0; attempt < 60; attempt += 1) {
    await waitFor(1000);
    let status;
    try { status = await localClientRequest(`/v1/viewer/${pid}`, {timeout:1500}); failures = 0; }
    catch (_error) { if (++failures < 4) continue; throw new Error('本机客户端连续多次无法确认 Viewer 启动状态'); }
    if(token) updateViewerProgress(token,status);
    if (!status.tracked) throw new Error(status.reason || '本地客户端未保留 Viewer 启动记录');
    if (!status.running) {
      if (status.exit_code === 0 && viewerSamplingStatus(status).ready) return status;
      throw new Error([status.reason, status.log_tail].filter(Boolean).join('\n') || 'MuJoCo Viewer 启动后异常退出');
    }
    if (viewerSamplingStatus(status).ready) return status;
  }
  throw new Error('MuJoCo Viewer 启动超时');
}
function viewerSamplingStatus(status) {
  const tail=String(status?.log_tail||'');
  const matches=[...tail.matchAll(/MUJOCO_STUDIO_SAMPLING_PROGRESS\s+(\d+)\/(\d+)\s+(\d+)/g)];
  const last=matches.at(-1);
  const sampling=status?.sampling||{};
  const done=Number.isFinite(Number(sampling.done))?Number(sampling.done):(last?Number(last[1]):0);
  const total=Math.max(1,Number.isFinite(Number(sampling.total))?Number(sampling.total):(last?Number(last[2]):1));
  const points=Number.isFinite(Number(sampling.points))?Number(sampling.points):(last?Number(last[3]):0);
  const ready=Boolean(status?.ready)||tail.includes('MUJOCO_STUDIO_VIEWER_READY');
  return {done,total,points,ready};
}
function updateViewerProgress(token,status){
  const p=viewerSamplingStatus(status);
  const pct=Math.min(99,Math.max(1,(p.done/p.total)*95));
  blockingLoadingState.progress=pct;
  const percent=Math.round((p.done/p.total)*100); const detail=p.ready?`MuJoCo Viewer 已显示；撒点共 ${p.points} 点`:(p.done>=p.total&&p.points>0?`撒点完成 100%，共 ${p.points} 点，正在创建 MuJoCo Viewer 窗口…`:`正在撒点：${p.done}/${p.total} 个数模对象（${percent}%），已撒 ${p.points} 点`);
  updateBlockingLoading(token,{detail});
}
// This fingerprint is a cache invalidation hint, NOT an authentication or
// ModelSpec freshness token. Include the schedule inputs but not presentation
// colors, so users may keep a manually styled PNG until drives really change.
function viewerGanttDriveSignature(project = state.project) {
  if (!project) return '';
  const representation = JSON.stringify([
    project.drives || [], project.variables || {},
    (project.layers || []).map(layer => (layer.joints || []).map(j =>
      [j.id,j.type,j.drive_id,j.limit_lower,j.limit_upper])),
    project.simulation?.start_time, project.simulation?.end_time,
  ]);
  let checksum = 2166136261;
  for (let index = 0; index < representation.length; index++) {
    checksum = Math.imul((checksum ^ representation.charCodeAt(index)), 16777619);
  }
  return `fnv1a32:${representation.length}:${(checksum >>> 0).toString(16).padStart(8,'0')}`;
}
async function ensureViewerGanttCache(projectId, {force = false} = {}) {
  if (!projectId) throw new Error('缺少模型 ID');
  if (typeof window.__GanttPopup__?.awaitCacheIdle === 'function')
    await window.__GanttPopup__.awaitCacheIdle();
  // The cache may be from a previous signed-in revision or a second browser.
  // Preserving a PNG requires both a PNG+JSON pair AND an exact drive hint.
  const existing = await api(`/api/projects/${projectId}/gantt-cache`, {timeout:5000});
  const currentSignature = state.project?.id === projectId ? viewerGanttDriveSignature() : '';
  if (!force && existing?.png && existing?.json &&
      (!currentSignature || existing.json.drive_signature === currentSignature)) return existing;
  if (typeof window.__GanttPopup__?.refreshCache !== 'function')
    throw new Error('浏览器甘特图缓存渲染器尚未加载');
  return window.__GanttPopup__.refreshCache(projectId);
}

async function openMuJoCoViewer(event) {
  const button = event?.currentTarget || $('#openViewerButton');
  if (!requireLocalClientRole()) return;
  if (state.activeViewerLaunch?.kind === 'admin-job') {
    if (confirm('服务端 Viewer 启动任务仍在运行。是否取消该任务？')) await cancelViewerLaunch();
    return;
  }
  if (state.viewerLaunchPending) return toast('Viewer 启动请求正在提交，请勿重复点击', 'info');
  const projectId = state.project?.id || state.hubSelectedProjectId;
  if (!projectId) return toast('请先选择一个模型', 'error');
  state.viewerLaunchPending = true;
  if (button) button.disabled = true;
  try {
    const editedSinceCache = Boolean(state.project?.id === projectId && state.dirty);
    if (state.project?.id === projectId && canEditProject()) await saveEditableDraft();
    // V2.16.2: the native Viewer consumes an actual PNG+JSON snapshot, never a
    // live Web Gantt widget. Preserve an existing manually styled PNG unless
    // this editor has unsynced changes; otherwise build the missing/stale pair
    // BEFORE freezing a Client Bundle or opening the admin native Viewer.
    try {
      await ensureViewerGanttCache(projectId, {force:editedSinceCache});
    } catch (ganttError) {
      // Presentation caching must not re-introduce the old hard Viewer gate.
      console.warn('[viewer] PNG cache preparation failed:', ganttError);
      toast(`Viewer 甘特图 PNG 缓存未准备成功：${ganttError.message}；Viewer 将继续启动`, 'error');
    }
    if (state.auth?.role === 'admin') {
      // The server responds with a Job ID, not a PID. A native Viewer process
      // must never keep the HTTP/UI blocking overlay open while it launches.
      const queued = await api(`/api/projects/${projectId}/local-viewer`, {
        method:'POST', body:'{}', timeout:12000,
      });
      if (!queued.job_id) throw new Error('服务端未返回 Viewer 启动 Job 编号');
      state.viewerLaunchJobId = queued.job_id;
      state.activeViewerLaunch = {kind:'admin-job', projectId, jobId:queued.job_id};
      watchJob(queued.job_id, 'native_viewer_launch');
      toast('MuJoCo Viewer 已加入独立后台队列，页面可以继续编辑；状态见后台任务。再次点击可取消启动。', 'success', 8000);
      return;
    }
    // Engineer Client 0.3.9 owns native Viewer on its own machine. Keep the
    // current trajectory explicit, but never block the entire browser page.
    // Client Bundle reuses a fingerprint-matched trajectory, and computes an
    // isolated fallback when none exists. Do not force a redundant /simulate
    // Job + polling loop before each Engineer Viewer launch.
    toast('正在准备本机 Viewer：优先复用当前轨迹，缺失时由独立仿真进程补算；页面仍可操作。', 'info', 6000);
    const health = await localClientHealth();
    if (!health) return;
    if (health.dependencies_ready === false)
      throw new Error(`本地客户端缺少依赖：${(health.missing_dependencies || []).join(', ')}`);
    const issued = await api(`/api/projects/${projectId}/client-ticket`, {
      method:'POST', body:JSON.stringify({purpose:'viewer_launch'}), timeout:12000,
    });
    const launched = await localClientRequest('/v1/launch', {
      method:'POST', body:{server_url:location.origin,ticket:issued.ticket}, timeout:180000,
    });
    state.activeViewerLaunch = {kind:'client', projectId, pid:launched.pid};
    toast('本机 MuJoCo Viewer 进程已启动；窗口状态将在后台确认。', 'success');
    void verifyLocalClientViewer(launched.pid, null).then(() => {
      toast('本机 MuJoCo Viewer 窗口已就绪', 'success');
    }).catch(error => toast(`本机 Viewer 状态：${error.message}`, 'error'))
      .finally(() => { if (state.activeViewerLaunch?.pid === launched.pid) state.activeViewerLaunch = null; });
  } catch (error) {
    toast(`MuJoCo Viewer 启动失败：${error.message}`, 'error');
  } finally {
    state.viewerLaunchPending = false;
    if (button) button.disabled = false;
  }
}
async function cancelViewerLaunch() {
  const active = state.activeViewerLaunch;
  if (!active) return;
  try {
    if (active.kind === 'admin-job') {
      await api(`/api/jobs/${active.jobId}/cancel`, {method:'POST', body:'{}'});
      toast('已请求取消 Viewer 启动 Job');
      return;
    }
    if (active.kind === 'admin')
      await api(`/api/projects/${active.projectId}/local-viewer/${active.pid}/terminate`, {method:'POST',body:'{}'});
    else
      await localClientRequest(`/v1/viewer/${active.pid}/terminate`, {method:'POST',body:{}});
    state.activeViewerLaunch = null;
    toast('已终止 Viewer 进程');
  } catch (error) { toast(error.message, 'error'); }
}

async function runSimulation({skipSave = false, fromEnter = false} = {}) {
  if(state.simulationJobId||state.simulationRefreshSubmitting) {
    if (fromEnter && state.project?.id) {
      // Latest-wins: at most one pending revision, never start a second solve.
      state.enterRefreshQueuedProjectId = state.project.id;
      return toast('坐标系正在计算；完成后将验证最新物理输入并按需刷新', 'info');
    }
    return toast('坐标系刷新任务正在进行，请看后台任务进度','info');
  }
  if(!state.project?.id) return;
  state.simulationRefreshSubmitting=true;
  const button=$('#simulateButton');if(button)button.disabled=true;
  return withBlockingLoading({title:'正在提交坐标系刷新',detail:'先保存模型，再提交轨迹求解；不会自动生成动画 HTML。'},async token=>{
    try {
      state.refreshAnimationAfterSimulation=false;
      if (!skipSave) await saveEditableDraft();
      if (fromEnter) {
        // Server provenance validates the exact current assets as well as all
        // solver inputs. Only explicitly proven display-only edits may reuse.
        // Old 2.16.8 provenance without this hint safely re-solves when stale.
        const projectId = state.project.id;
        const latest = await api(`/api/projects/${encodeURIComponent(projectId)}/latest-simulation`,
          {timeout:30000}).catch(() => null);
        if (state.project?.id !== projectId) return;
        if (latest?.physical_input_current && latest.result?.simulation_id) {
          state.latestSimulation = latest.result;
          $('#latestResultLabel').textContent=`最新结果 · ${latest.result.engine || 'unknown'} · ${latest.result.times?.length || 0} 点`;
          refreshCombinedGanttSchedule({render:false});
          renderResultViewer();
          requestSelectedDistanceCurves();
          toast('物理输入未变，已复用当前精确轨迹；坐标系显示已更新', 'success');
          return;
        }
      }
      updateBlockingLoading(token,{detail:'正在向后端提交坐标系/轨迹求解任务…'});
      const result=await api(`/api/projects/${state.project.id}/simulate`,{method:'POST',timeout:30000});
      state.simulationJobId=result.job_id;
      watchJob(result.job_id,'simulation');
      toast(fromEnter ? '更改已保存，坐标系正在后台刷新' : `坐标系刷新已提交 · Job ${result.job_id}，后台求解中；动画不会自动刷新`,'success');
      $('#activeJobMessage').textContent='坐标系正在求解；请关注后台任务进度…';
    } catch(error){
      state.simulationJobId=null;
      toast(`坐标系刷新未能提交：${error.message}`,'error');
    } finally {
      state.simulationRefreshSubmitting=false;
      if(button)button.disabled=Boolean(state.simulationJobId);
    }
  });
}
function preferDirectBrowserDownload(){ return true; }
async function chooseLocalSaveHandle(suggestedName, mimeType='application/octet-stream') {
  const name=String(suggestedName||'download.bin');
  return {kind:'browser-download', suggestedName:name, mimeType};
}

async function writeBlobToChosenHandle(handle, blob, label='文件', quiet=false) {
  if(!handle)return false;
  try {
    if(handle.kind==='browser-download'){
      const url=URL.createObjectURL(blob);
      const anchor=document.createElement('a');
      anchor.href=url;anchor.download=String(handle.suggestedName||label||'download.bin');
      anchor.style.display='none';document.body.appendChild(anchor);anchor.click();anchor.remove();
      setTimeout(()=>URL.revokeObjectURL(url),1000);
      if(!quiet)toast(`${label}已开始下载到浏览器默认下载目录`);
      return true;
    }
    const writable=await handle.createWritable();await writable.write(blob);await writable.close();
    if(!quiet)toast(`${label}已保存到所选路径`);
    return true;
  } catch(error) {
    toast(`保存失败：${error.message||error}`,'error');
    return false;
  }
}
async function saveBlobToChosenPath(suggestedName, blob, mimeType=blob?.type||'application/octet-stream') {
  const handle=await chooseLocalSaveHandle(suggestedName,mimeType);
  return handle?writeBlobToChosenHandle(handle,blob,suggestedName):false;
}
async function saveProjectArtifactToChosenHandle(projectId, path, handle) {
  if (!projectId || !path || !handle) return false;
  try {
    const response=await fetch(`/api/projects/${encodeURIComponent(projectId)}/artifacts/${encodeArtifactPath(path)}`);
    if(!response.ok)throw new Error(`文件读取失败 (${response.status})`);
    return writeBlobToChosenHandle(handle,await response.blob(),String(path).split('/').pop()||'文件');
  } catch(error) {
    toast(error.message||String(error),'error');return false;
  }
}
async function saveArtifactToChosenHandle(path,handle){return state.project?saveProjectArtifactToChosenHandle(state.project.id,path,handle):false;}
async function saveArtifactToChosenPath(path, suggestedName=null) {
  if (!state.project || !path) return false;
  const name=suggestedName || String(path).split('/').pop() || 'download.bin';
  const handle=await chooseLocalSaveHandle(name);
  return handle?saveArtifactToChosenHandle(path,handle):false;
}
function animationHtmlThresholdValid() {
  const threshold=Number(state.project?.animation_html?.adaptive_threshold_mm ?? 25);
  if(Number.isFinite(threshold) && threshold>0)return true;
  toast('自适应测距显示阈值必须是大于 0 的有效毫米数，请先修改后再生成动画 HTML','error');
  return false;
}
async function regenerateEmbeddedAnimation({skipSave=false, source='manual'}={}) {
  if(!animationHtmlThresholdValid())return;
  if(state.animationExportJobId||state.animationRefreshSubmitting)return toast('动画 HTML 正在生成，请查看后台任务进度','info');
  if(state.simulationJobId||state.simulationRefreshSubmitting)return toast('坐标系求解尚未完成，请先等待求解成功，再刷新动画。','info');
  state.animationRefreshSubmitting=true;
  const button=$('#regenerateEmbeddedAnimation');
  const refreshButton=$('#refreshAnimationButton');
  if(refreshButton)refreshButton.disabled=true;
  if(!canGenerateAnimationHtml()){
    state.animationRefreshSubmitting=false;
    if(refreshButton)refreshButton.disabled=false;
    return toast('签入/基线模型禁止重新生成动画 HTML；请点击“重新加载”读取交付数据中的 HTML','error');
  }
  return withBlockingLoading({title:'正在重新生成动画 HTML',detail:'正在保存模型；生成完成后覆盖交付数据中的上一版，不会自动下载。'}, async token=>{
    try {
      if(button)button.disabled=true;
      $('#animationClosureError')?.classList.add('hidden');
      $('#animationLoadStatus').textContent='正在重新生成动画 HTML…';
      if(!skipSave)await saveEditableDraft();
      const projectId=state.project.id;
      state.animationExportHandle=null;
      state.animationExportProjectId=projectId;
      state.animationExportJobId=null;
      if(typeof window.__GanttPopup__?.refreshCache==='function'){
        updateBlockingLoading(token,{detail:'正在后台刷新甘特图弹窗并预载 PNG…'});
        try{await window.__GanttPopup__.refreshCache(projectId);}catch(ganttError){console.warn('[animation-regenerate] gantt popup cache refresh failed:',ganttError);toast('甘特图缓存刷新失败；动画仍会继续生成，并使用隔离兜底图或兼容时序图','error');}
      }
      updateBlockingLoading(token,{detail:'甘特图准备完成，正在提交动画重新生成任务…'});
      const result=await api(`/api/projects/${projectId}/export-animation-html`,{method:'POST'});
      state.animationExportJobId=result.job_id;
      watchJob(result.job_id,'animation_html_export');
      toast('动画 HTML 已提交独立后台任务，不会重复求解坐标系；完成后覆盖交付数据','success');
    } catch(error) {
      state.animationExportHandle=null;state.animationExportProjectId=null;state.animationExportJobId=null;
      if(button)button.disabled=!canGenerateAnimationHtml();
      $('#animationLoadStatus').textContent=`动画重新生成失败：${error.message}`;
      toast(error.message,'error');
    } finally {
      state.animationRefreshSubmitting=false;
      if(refreshButton)refreshButton.disabled=Boolean(state.animationExportJobId);
    }
  });
}

async function exportAnimationHtml() {
  const button=$('#exportAnimationHtmlButton');
  if(!canGenerateAnimationHtml())return toast('签入/基线模型禁止生成动画 HTML；请在动画页点击“重新加载”读取交付数据中的 HTML','error');
  if(!animationHtmlThresholdValid())return;
  return withBlockingLoading({title:'正在导出动画 HTML',detail:'正在保存模型；生成完成后会覆盖交付数据中的上一版并自动下载。'}, async token=>{
    try {
      if(button)button.disabled=true;
      $('#animationClosureError')?.classList.add('hidden');
      $('#animationLoadStatus').textContent='正在生成动画 HTML…';
      await saveEditableDraft();
      const projectId=state.project.id;
      const stem=(await api(`/api/projects/${projectId}/delivery-stem`)).stem || state.project.name || '模型';
      const handle=await chooseLocalSaveHandle(`${stem}_anim.html`,'text/html');
      if(!handle){if(button)button.disabled=false;return;}
      state.animationExportHandle=handle;state.animationExportProjectId=projectId;state.animationExportJobId=null;
      if(typeof window.__GanttPopup__?.refreshCache==='function'){
        updateBlockingLoading(token,{detail:'正在后台刷新甘特图弹窗并预载 PNG…'});
        try{await window.__GanttPopup__.refreshCache(projectId);}catch(ganttError){console.warn('[animation-export] gantt popup cache refresh failed:',ganttError);toast('甘特图缓存刷新失败；动画仍会继续生成，并使用隔离兜底图或兼容时序图','error');}
      }
      updateBlockingLoading(token,{detail:'甘特图准备完成，正在提交动画导出任务…'});
      const result=await api(`/api/projects/${projectId}/export-animation-html`,{method:'POST'});
      state.animationExportJobId=result.job_id;watchJob(result.job_id,'animation_html_export');
      toast('动画 HTML 导出任务已提交；完成后将自动交付并下载');
    } catch(error) {
      state.animationExportHandle=null;state.animationExportProjectId=null;state.animationExportJobId=null;
      if(button)button.disabled=!canGenerateAnimationHtml();$('#animationLoadStatus').textContent=`动画导出失败：${error.message}`;toast(error.message,'error');
    }
  });
}

async function exportNxAfuScript() {
  const button=$('#exportNxAfuButton');
  if(!state.project)return;
  let localHandle=null;
  try {
    const stem=(await api(`/api/projects/${state.project.id}/delivery-stem`)).stem || state.project.name || '模型';
    localHandle=await chooseLocalSaveHandle(`${stem}_NX script.py`,'text/x-python');
  } catch(_) {
    const base=String(state.project?.name||'模型').replace(/[\\/:*?"<>|]+/g,'_').replace(/[ ._]+$/g,'')||'模型';
    localHandle=await chooseLocalSaveHandle(`${base}_NX script.py`,'text/x-python');
  }
  if(!localHandle)return;
  return withBlockingLoading({title:'正在导出 NX AFU 脚本',detail:'正在生成脚本、覆盖交付数据中的上一版，并下载到本地。'}, async()=>{
    try {
      if(button)button.disabled=true;
      await saveEditableDraft();
      const result=await api(`/api/projects/${state.project.id}/export-nx-afu-script`,{method:'POST'});
      const path=result.artifact_relative;
      await saveArtifactToChosenHandle(path,localHandle);
      await refreshArtifacts();
      if(state.hubSelectedProjectId===state.project.id)await loadHubPreview(state.project.id,{force:true});
    } catch(error){toast(error.message,'error');}
    finally{if(button)button.disabled=false;}
  });
}
async function openProjectFolder() {
  const projectId=state.hubSelectedProjectId || state.project?.id;
  if(!projectId)return;
  if (!state.capabilities?.desktop_enabled) {
    openModelFiles('delivery_outputs');
    toast('服务器模式已打开 Web 文件视图；不会启动服务器资源管理器');
    return;
  }
  try { const result=await api(`/api/projects/${projectId}/open-folder`,{method:'POST'});toast(`已打开项目文件夹：${result.path}`); }
  catch(error){toast(error.message,'error');}
}
async function runOptimization() { return withBlockingLoading({title:'正在提交优化任务',detail:'正在保存参数并创建后台优化任务；任务受理后即可继续操作。'},async()=>{try { if(canEditProject()) collectStaticFields(); await saveEditableDraft(); const result = await api(`/api/projects/${state.project.id}/optimize`,{method:'POST'}); watchJob(result.job_id); toast('优化任务已提交'); } catch(error){toast(error.message,'error');}}); }

const agentToolNames = {
  validate_project:'检查项目', generate_project:'生成 MuJoCo 模型', run_simulation:'运行仿真',
  run_optimization:'运行时序优化', save_project:'保存项目',
};

async function loadSkills() {
  state.skills = await api('/api/skills');
  $('#skillSelect').innerHTML = state.skills.map(skill=>`<option value="${esc(skill.id)}">${esc(skill.name)}</option>`).join('');
  renderSkillOverview();
}

function renderSkillOverview() {
  const skill = state.skills.find(item => item.id === $('#skillSelect')?.value) || state.skills[0];
  const root = $('#skillOverview'); if (!root) return;
  root.innerHTML = skill ? `<strong>${esc(skill.name)}</strong><div>${esc(skill.description)}</div><div class="skill-step-list">${skill.steps.map((step,index)=>`<span>${index+1}. ${esc(agentToolNames[step.tool] || step.tool)}</span>`).join('')}</div>` : '尚无可用 Skill';
}

async function loadAgentWorkspace() {
  if (!state.project) return;
  try {
    const [config, conversation] = await Promise.all([
      api(`/api/projects/${state.project.id}/llm-config`),
      api(`/api/projects/${state.project.id}/agent-conversation`),
      refreshJobs(), refreshArtifacts(),
    ]);
    state.llmConfig = config; state.agentConversation = conversation.messages || [];
    $('#llmBaseUrl').value = config.base_url;
    $('#llmModel').value = config.model;
    $('#llmContextRounds').value = config.context_rounds;
    $('#llmIncludeVariables').checked = config.include_variables;
    $('#llmIncludeEvents').checked = config.include_operation_log;
    $('#llmIncludeArtifacts').checked = config.include_artifacts;
    $('#llmConfigStatus').textContent = config.credential?.configured ? `已配置 ${config.credential.masked}` : '未配置密钥';
    $('#conversationWindowBadge').textContent = `${config.context_rounds} 轮`;
    renderAgentConversation(); renderSkillOverview();
  } catch (error) { toast(`智能体工作区读取失败：${error.message}`, 'error'); }
}

function renderAgentConversation() {
  const root = $('#agentConversation'); if (!root) return;
  root.classList.toggle('empty-state', !state.agentConversation.length);
  root.innerHTML = state.agentConversation.length ? state.agentConversation.map(item => `<div class="agent-message ${esc(item.role)}"><div>${esc(item.content)}</div><small>${item.role === 'user' ? '用户' : '智能体'} · ${formatDate(item.created_at)}</small></div>`).join('') : '尚无智能体对话；每次执行目标与结果会进入上下文。';
  root.scrollTop = root.scrollHeight;
}

async function saveLlmConfig({quiet=false}={}) {
  const key = $('#llmApiKey').value.trim();
  const body = {
    base_url:$('#llmBaseUrl').value.trim(), model:$('#llmModel').value.trim(),
    context_rounds:Number($('#llmContextRounds').value || 20),
    include_variables:$('#llmIncludeVariables').checked,
    include_operation_log:$('#llmIncludeEvents').checked,
    include_artifacts:$('#llmIncludeArtifacts').checked,
  };
  if (key) body.api_key = key;
  const projectId = state.project.id;
  const config = await api(`/api/projects/${projectId}/llm-config`, {method:'PUT', body:JSON.stringify(body)});
  state.llmConfig = config; $('#llmApiKey').value = '';
  $('#llmConfigStatus').textContent = config.credential?.configured ? `已配置 ${config.credential.masked}` : '未配置密钥';
  $('#conversationWindowBadge').textContent = `${config.context_rounds} 轮`;
  const mirrorFence = captureAuthoritativeProjectFence(projectId);
  const mirror = await api(`/api/projects/${projectId}/state`);
  if (canApplyAuthoritativeProject(mirrorFence)) state.project = mirror.state.project;
  await refreshEventStatus(false);
  if (!quiet) toast('大模型配置已保存');
  return config;
}

async function testLlmConnection() {
  const button = $('#testLlmButton'); button.disabled = true;
  try {
    await saveLlmConfig({quiet:true});
    const result = await api(`/api/projects/${state.project.id}/llm-test`, {method:'POST'});
    toast(`${result.model}：${result.response}`);
  } catch (error) { toast(error.message, 'error'); }
  finally { button.disabled = false; }
}
async function saveSkill() { try { const skill={id:$('#skillId').value.trim(),name:$('#skillName').value.trim(),description:$('#skillDescription').value.trim(),steps:JSON.parse($('#skillSteps').value),max_steps:20}; await api('/api/skills',{method:'POST',body:JSON.stringify(skill)}); await loadSkills(); $('#skillSelect').value=skill.id; toast('自定义 Skill 已保存'); } catch(error){toast(error.message,'error');} }
async function runAgent(forcedSkill=null) { const button=$('#runAgentButton');button.disabled=true;try { if (state.llmConfig) await saveLlmConfig({quiet:true}); await commitEdits(); const request={skill_id:forcedSkill || $('#skillSelect').value,goal:$('#agentGoal').value}; const result=await api(`/api/projects/${state.project.id}/agent-runs`,{method:'POST',body:JSON.stringify(request)}); watchJob(result.job_id,'agent'); navigateToPage('agent'); toast('智能体开始工作；回答完成前可使用“停止”终止'); } catch(error){button.disabled=false;toast(error.message,'error');} }

function watchJob(jobId, kind=null) {
  state.activeJobId=jobId;state.activeJobKind=kind;
  const overlay = $('#activeJob');
  // A fixed element inside the sticky simulator panel is still trapped by
  // ancestor stacking contexts. Move it to body to make z-index meaningful.
  if (overlay && overlay.parentElement !== document.body) document.body.appendChild(overlay);
  overlay?.classList.remove('hidden');
  $('#activeJobBar').style.width='0%';
}
async function cancelActiveJob(){if(!state.activeJobId)return;try{await api(`/api/jobs/${state.activeJobId}/cancel`,{method:'POST'});toast('已请求停止任务');}catch(error){toast(error.message,'error')}}
let jobPollInFlight=false;
let jobPollBackoffUntil=0;
let jobPollFailures=0;
let jobPollLastIdleAt=0;
function startJobPolling(){
  if(state.pollTimer)clearInterval(state.pollTimer);
  state.pollTimer=setInterval(()=>{void poll();},2500);
  void poll();
}
async function poll(){
  if(jobPollInFlight||!state.auth||document.hidden||Date.now()<jobPollBackoffUntil)return;
  const busy = Boolean(state.activeJobId || state.simulationJobId || state.animationExportJobId || state.viewerLaunchJobId || state.distanceCurveSession?.batchJobId || state.distanceCurveSession?.batchRequest || state.distanceCurveSession?.waitingForSlot);
  if (!busy && Date.now()-jobPollLastIdleAt < 7500) return;
  if (!busy) jobPollLastIdleAt = Date.now();
  jobPollInFlight=true;
  try{
    await Promise.all([refreshJobs(), state.project?refreshEventStatus(true):Promise.resolve()]);
    await pollSelectedDistanceCurves();
    jobPollFailures=0;jobPollBackoffUntil=0;
    if (state.viewerLaunchJobId && state.viewerLaunchJobId !== state.activeJobId) {
      const viewerJob = state.jobs.find(item => item.id === state.viewerLaunchJobId) ||
        await api(`/api/jobs/${state.viewerLaunchJobId}`, {timeout:5000});
      if (['completed','failed','cancelled','timed_out'].includes(viewerJob.status)) {
        state.viewerLaunchJobId = null;
        handleCompletedJob(viewerJob);
      }
    }
    if(state.simulationJobId&&state.simulationJobId!==state.activeJobId){
      const simJob=state.jobs.find(item=>item.id===state.simulationJobId) || await api(`/api/jobs/${state.simulationJobId}`);
      if(['completed','failed','cancelled','timed_out'].includes(simJob.status)){
        state.simulationJobId=null;handleCompletedJob(simJob);await refreshArtifacts();
      }
    }
    // Animation export owns a browser download handle. Track that job separately
    // so starting another background task cannot steal the completion callback.
    if(state.animationExportJobId && state.animationExportJobId!==state.activeJobId){
      const animationJob=state.jobs.find(item=>item.id===state.animationExportJobId) || await api(`/api/jobs/${state.animationExportJobId}`);
      if(['completed','failed','cancelled','timed_out'].includes(animationJob.status)){
        state.animationExportJobId=null;
        handleCompletedJob(animationJob);
        await refreshArtifacts();
      }
    }
    if(state.activeJobId){
      const job=await api(`/api/jobs/${state.activeJobId}`);
      $('#activeJobBar').style.width=`${job.progress*100}%`;
      $('#activeJobMessage').textContent=job.message;
      if(['completed','failed','cancelled','timed_out'].includes(job.status)){
        if(state.activeJobKind==='agent')$('#runAgentButton').disabled=false;
        if(state.activeJobKind==='quick_optimization'){state.quickOptimizationRunning=false;renderQuickOptimization();}
        if(job.id===state.animationExportJobId)state.animationExportJobId=null;
        state.activeJobId=null;state.activeJobKind=null;$('#activeJob').classList.add('hidden');
        handleCompletedJob(job);await refreshArtifacts();
      }
    }
  }catch(error){
    if(error?.status===401||!state.auth)return;
    jobPollFailures=Math.min(jobPollFailures+1,8);
    jobPollBackoffUntil=Date.now()+Math.min(30000,1000*2**jobPollFailures);
    if(jobPollFailures===1)console.warn('[job-poll] retrying after transient error',error);
  }finally{jobPollInFlight=false;}
}
async function refreshJobs(){state.jobs=await api('/api/jobs?limit=50',{timeout:8000});renderJobs();}
function renderJobs(){const html=state.jobs.map(job=>`<div class="job-item ${job.status}" data-job-id="${job.id}"><span class="job-state"></span><div><strong>${esc(job.kind)}</strong><small>${esc(job.message)} · ${Math.round(job.progress*100)}%</small></div><small>${new Date(job.created_at).toLocaleTimeString()}</small></div>`).join('')||'<div class="empty-state">还没有后台任务</div>';const recent=$('#recentJobs');if(recent)recent.innerHTML=state.jobs.slice(0,5).length?state.jobs.slice(0,5).map(job=>`<div class="job-item ${job.status}" data-job-id="${job.id}"><span class="job-state"></span><div><strong>${esc(job.kind)}</strong><small>${esc(job.message)}</small></div><small>${Math.round(job.progress*100)}%</small></div>`).join(''):'<div class="empty-state">还没有后台任务</div>';$('#allJobs').innerHTML=html;$$('[data-job-id]').forEach(item=>item.addEventListener('click',()=>inspectJob(item.dataset.jobId)));}
async function inspectJob(id){try{const job=await api(`/api/jobs/${id}`);$('#resultInspector').textContent=JSON.stringify(job.result||job.error||job,null,2);if(job.status==='completed')handleCompletedJob(job);}catch(error){toast(error.message,'error')}}
function renderAnimationExportError(error) {
  const panel=$('#animationClosureError'); if(!panel)return;
  if(error?.code!=='kinematic_closure_nonconvergence'){panel.classList.add('hidden');panel.innerHTML='';return;}
  const ids=(error.closure_ids||[]).map(esc).join('、')||'未提供';
  const time=Number.isFinite(Number(error.time_s))?`${Number(error.time_s).toFixed(4)} s`:'未提供';
  const residual=Number.isFinite(Number(error.residual_mm))?`${Number(error.residual_mm).toFixed(4)} mm`:'未提供';
  panel.innerHTML=`<strong>${esc(error.message||'闭链求解未收敛')}</strong><div>闭链 ID：<code>${ids}</code></div><div>发散时刻：${esc(time)} · 残差：${esc(residual)}${error.iterations!=null?` · 迭代：${esc(error.iterations)}`:''}</div><div>${esc(error.hint||'请检查闭链约束和机构可达性后重试。')}</div>`;
  panel.classList.remove('hidden');
}
function handleCompletedJob(job) {
  if (job.kind === 'native_viewer_launch') {
    if (state.viewerLaunchJobId === job.id) state.viewerLaunchJobId = null;
    const context = state.activeViewerLaunch;
    if (context?.kind === 'admin-job' && context.jobId === job.id) {
      state.activeViewerLaunch = null;
      if (job.status === 'completed' && Number(job.result?.pid) > 0) {
        const pid = Number(job.result.pid);
        state.activeViewerLaunch = {kind:'admin',projectId:context.projectId,pid};
        toast('服务端 Viewer 子进程已启动，后台确认窗口就绪情况；无需停留在等待页面。', 'success');
        void verifyLocalAdminViewer(context.projectId, pid, null).then(() => {
          toast('服务端 MuJoCo Viewer 窗口已就绪', 'success');
        }).catch(error => toast(`服务端 Viewer 状态：${error.message}`, 'error'))
          .finally(() => { if (state.activeViewerLaunch?.pid === pid) state.activeViewerLaunch = null; });
      }
    }
  }
  if (job.kind === 'animation_html_export') {
    if($('#regenerateEmbeddedAnimation'))$('#regenerateEmbeddedAnimation').disabled = !canGenerateAnimationHtml();
    if($('#refreshAnimationButton'))$('#refreshAnimationButton').disabled=false;
  }
  if (job.kind === 'simulation') {
    state.resultAutoSimulationPending=false;state.simulationJobId=null;
    if($('#simulateButton'))$('#simulateButton').disabled=false;
    // The latest Enter while a previous trajectory was still solving must not
    // be silently discarded; the next run uses the already-synced latest model.
    const pending = state.enterRefreshQueuedProjectId;
    state.enterRefreshQueuedProjectId = null;
    if (pending && state.project?.id === pending && canEditProject())
      queueMicrotask(() => { void runSimulation({skipSave:true, fromEnter:true}); });
    // A previous trajectory may complete after a newer edit was queued; do
    // not present that superseded result as corresponding to current inputs.
    state.simulationSupersededJobId = pending ? job.id : null;
  }
  if (['failed','timed_out'].includes(job.status)) {
    if (job.kind === 'animation_html_export') { state.animationExportHandle=null;state.animationExportProjectId=null;state.animationExportJobId=null;$('#animationLoadStatus').textContent=`动画导出失败：${job.error?.message||job.message}`; renderAnimationExportError(job.error); }
    if (job.kind === 'web_viewer_export') { state.webViewerWindow?.close(); state.webViewerWindow=null; }
    if (job.kind === 'quick_optimization') { state.quickOptimizationRunning=false; renderQuickOptimization(); }
    if (job.kind === 'simulation') { state.refreshAnimationAfterSimulation=false; renderResultViewer(); }
    const prefix=job.status==='timed_out'?'任务超时：':'';
    return toast(prefix+(job.error?.message||job.message),'error');
  }
  if (job.status !== 'completed') {
    if (job.kind === 'animation_html_export') {state.animationExportHandle=null;state.animationExportProjectId=null;state.animationExportJobId=null;$('#animationLoadStatus').textContent='动画导出已取消';}
    if (job.kind === 'web_viewer_export') { state.webViewerWindow?.close(); state.webViewerWindow=null; }
    if (job.kind === 'simulation') { state.refreshAnimationAfterSimulation=false; renderResultViewer(); }
    return toast('任务已取消');
  }
  if (job.kind === 'simulation') {
    if (state.simulationSupersededJobId === job.id) {
      state.simulationSupersededJobId = null;
      return;
    }
    state.latestSimulation=job.result;
    $('#latestResultLabel').textContent=`最新结果 · ${job.result.engine||'unknown'} · ${job.result.times?.length||0} 点`;
    refreshCombinedGanttSchedule(); renderResultViewer(); void loadSimulationWorkspace();
    requestSelectedDistanceCurves();
    // V2.15.10: animation refresh is a separate explicit user action.
    state.refreshAnimationAfterSimulation=false;
    toast('坐标系已刷新。需要更新动画时，请单独点击「刷新动画」。','success');
  }
  if (job.kind === 'optimization') renderBest(job.result?.best);
  if (job.kind === 'quick_optimization') acceptQuickOptimizationResult(job.result);
  if (job.kind === 'animation_html_export') {
    renderAnimationExportError(null);
    const path=job.result?.artifact_relative;
    const warnings=job.result?.warnings||[];
    const notes=[];
    if(warnings.includes('trajectory_reused_stale_parameters'))notes.push('使用了上一次仿真轨迹，当前参数改动未重新求解');
    if(warnings.includes('gantt_snapshot_unavailable'))notes.push('甘特图快照不可用，HTML 使用兼容时序图');
    if(job.result?.gantt_source==='fallback_render')notes.push('甘特图来自本次隔离兜底渲染');
    if (path) {
      const projectId=state.animationExportProjectId||state.project?.id;
      const handle=state.animationExportHandle;
      state.animationExportHandle=null;state.animationExportProjectId=null;state.animationExportJobId=null;
      const autoDownload=Boolean(handle);
      $('#animationLoadStatus').textContent=autoDownload
        ? `动画已生成并写入交付数据${notes.length?` · ${notes.join('；')}`:''}；正在自动下载`
        : `动画已重新生成并写入交付数据${notes.length?` · ${notes.join('；')}`:''}`;
      void (async()=>{
        if(projectId&&handle)await saveProjectArtifactToChosenHandle(projectId,path,handle);
        if(state.project?.id===projectId)await loadEmbeddedAnimation(true);
        if(state.hubSelectedProjectId===projectId)await loadHubPreview(projectId,{force:true});
      })();
      toast(`${autoDownload?'动画 HTML 已生成并覆盖最新交付':'动画 HTML 已重新生成并覆盖最新交付（未自动下载）'}：${path}${notes.length?`；${notes.join('；')}`:''}`);
    } else { state.animationExportHandle=null;state.animationExportProjectId=null;state.animationExportJobId=null;$('#animationLoadStatus').textContent=`动画 HTML 已生成${notes.length?` · ${notes.join('；')}`:''}`; toast('动画 HTML 已生成'); }
  }
  if(job.kind==='web_viewer_export'){
    const url=job.result?.viewer_url||`/api/projects/${state.project.id}/web-viewer`;
    if(state.webViewerWindow&&!state.webViewerWindow.closed)state.webViewerWindow.location.replace(url);else window.open(url,'_blank','noopener');
    state.webViewerWindow=null;toast('MuJoCo 结果回放已就绪');
  }
  if(job.kind==='agent')renderAgentTrace(job.result);
  if(job.kind==='agent')loadAgentWorkspace();
  $('#resultInspector').textContent=JSON.stringify(job.result,null,2);
}

async function refreshArtifacts(){if(!state.project)return;state.artifacts=await api(`/api/projects/${state.project.id}/artifacts`);const root=$('#artifactList');root.innerHTML=state.artifacts.map(item=>{const status=item.freshness?.status;const label=status==='current'?'当前':status==='stale'?'已过期':status==='unknown'?'来源未知':'';const action=['animation_html_preview','animation_html'].includes(item.kind)?'<span class="artifact-preview-note">HTML 请在首页模型属性中下载</span>':`<button class="button tiny ghost" data-artifact-save="${esc(item.path)}">下载</button>`;return `<div class="artifact-item"><div><strong>${esc(item.path)}</strong><small>${formatBytes(item.size)}${label?` · ${label}`:''}</small></div>${action}</div>`}).join('')||'<div class="empty-state">尚未生成产物</div>';$$('[data-artifact-save]',root).forEach(button=>button.addEventListener('click',()=>saveArtifactToChosenPath(button.dataset.artifactSave)));}
function formatBytes(value){if(value<1024)return `${value} B`;if(value<1048576)return `${(value/1024).toFixed(1)} KB`;return `${(value/1048576).toFixed(1)} MB`;}
function renderBest(best){const root=$('#optimizationBest');if(!best){root.innerHTML='<div class="empty-state">没有结果通过筛选</div>';return;}root.innerHTML=`<div class="best-value">${esc(best[state.project.optimization.objective] ?? '—')}</div><small>${esc(state.project.optimization.objective)} · ${state.project.optimization.direction}</small><div class="best-grid">${Object.entries(best).map(([key,value])=>`<span>${esc(key)} = ${esc(value)}</span>`).join('')}</div>`;}
function renderAgentTrace(result){const root=$('#agentTrace');const steps=result?.steps||[];root.classList.remove('empty-state');root.innerHTML=`<div class="issue info"><span class="severity"></span><div><strong>${esc(result.planning_mode)}</strong><small>${esc(result.goal||'Skill workflow')}</small></div></div>`+steps.map(item=>`<div class="trace-step ${item.status}"><span class="number">${item.step}</span><div><strong>${esc(item.tool)}</strong><small>${esc(item.error||item.status)}</small></div><span class="badge">${esc(item.status)}</span></div>`).join('');}

function drawCurves(result){const canvas=$('#curveCanvas'),root=$('#curvePreview');root.querySelector('.empty-overlay')?.remove();const rect=root.getBoundingClientRect();const scale=devicePixelRatio||1;canvas.width=rect.width*scale;canvas.height=rect.height*scale;const ctx=canvas.getContext('2d');ctx.scale(scale,scale);const w=rect.width,h=rect.height,pad=46;ctx.clearRect(0,0,w,h);ctx.strokeStyle='#263143';ctx.lineWidth=1;for(let i=0;i<=8;i++){const x=pad+(w-pad*2)*i/8;ctx.beginPath();ctx.moveTo(x,pad);ctx.lineTo(x,h-pad);ctx.stroke()}for(let i=0;i<=5;i++){const y=pad+(h-pad*2)*i/5;ctx.beginPath();ctx.moveTo(pad,y);ctx.lineTo(w-pad,y);ctx.stroke()}const curves=Object.values(result?.curves||{});const times=result?.times||[];const colors=['#55d8e7','#b9e76b','#ffb35c','#b18cff'];curves.forEach((curve,index)=>{const values=curve.position||[];if(!values.length)return;const min=Math.min(...values),max=Math.max(...values),span=max-min||1;ctx.strokeStyle=colors[index%colors.length];ctx.lineWidth=2;ctx.beginPath();values.forEach((value,i)=>{const x=pad+(w-pad*2)*i/Math.max(values.length-1,1),y=h-pad-(h-pad*2)*(value-min)/span;i?ctx.lineTo(x,y):ctx.moveTo(x,y)});ctx.stroke();ctx.fillStyle=colors[index%colors.length];ctx.font='11px sans-serif';ctx.fillText(`${curve.name} · ${curve.unit}`,pad+10,pad+16+index*18)});ctx.fillStyle='#8f9bad';ctx.font='10px sans-serif';ctx.fillText(`${times[0]??0}s`,pad,h-15);ctx.fillText(`${times.at(-1)??0}s`,w-pad-28,h-15);}

document.addEventListener('change', event=>{if(event.target.matches('[data-variable-name],[data-variable-value]')){if(!canEditProject())return;const index=Number(event.target.dataset.variableName??event.target.dataset.variableValue);const entries=Object.entries(state.project.variables);const [oldName,oldValue]=entries[index];const newName=$(`[data-variable-name="${index}"]`).value.trim();const newValue=$(`[data-variable-value="${index}"]`).value;if(newName!==oldName){delete state.project.variables[oldName];state.project.variables[newName]=newValue}else state.project.variables[oldName]=newValue;markDirty();scheduleInteractionCommit();}});

/* ================================================================
 *  Qt 甘特图弹窗（Web 复刻版）
 *  参照：mujoco_xml_tool_v21_5_3/ui/qt_gantt_popup.py
 * ================================================================ */
(function () {
  const DEFAULT_COLORS = GANTT_SEGMENT_COLORS;
  const DEFAULT_FONT_FAMILY = '"Microsoft YaHei", "Noto Sans SC", system-ui, sans-serif';
  const DEFAULT_PRESET_KEY = 'mujoco_studio.gantt_text_default.v1';
  const G = {
    popup: null, canvas: null, ctx: null, labelLayer: null, viewport: null, status: null,
    badge: null,
    segments: [], segmentByUid: {}, rows: [],
    selectedUid: null, selectedLabel: null,
    labelState: new Map(), // key -> {visible,pos:[x,y],color,customColor,text}
    options: {
      hZoom: 1.0, vZoom: 2.5,
      labelFontSize: 16, labelBold: true,
      driverFontSize: 20, driverBold: true,
      showTime: true, showTravel: true,
    },
    lastRenderMeta: {},
    uidCounter: 0,
    labelDialogTarget: null,
    tempLabelColor: null,
    savedDefaultPreset: null,
    updatingDefaultCheckbox: false,
  };

  function asFloat(v, d=0) { const n = Number(v); return Number.isFinite(n) ? n : d; }
  function fmtTime(v) {
    if (v == null) return '—';
    const n = Number(v);
    if (!Number.isFinite(n)) return '—';
    return Math.abs(n) < 0.05 ? '0' : n.toFixed(1);
  }
  function fmtTravel(v) { return fmtTime(v); }
  function fmtUnit(u) { return String(u||'').replace('deg','°'); }
  function fmtAxisTick(v, step) {
    step = Math.abs(asFloat(step, 0));
    if (step <= 0) return fmtTime(v);
    const digits = step >= 1 ? 1 : Math.min(6, Math.max(1, Math.ceil(-Math.log10(step)) + 1));
    const text = asFloat(v, 0).toFixed(digits).replace(/0+$/,'').replace(/\.$/,'');
    return text === '' || text === '-0' ? '0' : text;
  }
  function luminanceOf(hex) {
    const c = String(hex||'').replace('#','');
    if (c.length === 3) { const [r,g,b]=c; return 0.299*parseInt(r+r,16)+0.587*parseInt(g+g,16)+0.114*parseInt(b+b,16); }
    if (c.length >= 6) { return 0.299*parseInt(c.slice(0,2),16)+0.587*parseInt(c.slice(2,4),16)+0.114*parseInt(c.slice(4,6),16); }
    return 128;
  }
  function pickColorOnBackground(barColor) { return luminanceOf(barColor) < 150 ? '#FFFFFF' : '#111827'; }
  function uid() { return 's_' + (++G.uidCounter) + '_' + Math.random().toString(36).slice(2, 7); }
  function labelKey(segUid, kind) { return segUid + '::' + kind; }
  function stableLabelKey(seg, kind) { return seg.stableKey + '::' + kind; }

  function readDefaultPreset() {
    try {
      const value = JSON.parse(localStorage.getItem(DEFAULT_PRESET_KEY) || 'null');
      return value && value.formatVersion === 1 && value.options && value.labels ? value : null;
    } catch (_) { return null; }
  }

  function currentDefaultPreset() {
    const labels = {};
    G.segments.forEach(seg => {
      ['time','travel'].forEach(kind => {
        const state = G.labelState.get(labelKey(seg.uid, kind)) || {visible:true,color:'#000000',customColor:true};
        labels[stableLabelKey(seg, kind)] = {
          visible: state.visible !== false,
          ...(typeof state.text === 'string' ? {text:state.text} : {}),
          ...(Array.isArray(state.pos) ? {pos:[Number(state.pos[0]), Number(state.pos[1])]} : {}),
          color: state.color || '#000000',
          customColor: state.customColor !== false,
        };
      });
    });
    return {
      formatVersion: 1,
      options: {
        labelFontSize:G.options.labelFontSize, labelBold:G.options.labelBold,
        driverFontSize:G.options.driverFontSize, driverBold:G.options.driverBold,
        showTime:G.options.showTime, showTravel:G.options.showTravel,
      },
      labels,
    };
  }

  function setDefaultCheckbox(checked) {
    const checkbox = document.getElementById('ganttPSetDefault'); if (!checkbox) return;
    G.updatingDefaultCheckbox = true;
    checkbox.checked = Boolean(checked);
    G.updatingDefaultCheckbox = false;
  }

  function initializeTextDefaults() {
    const preset = G.savedDefaultPreset;
    if (preset?.options) Object.assign(G.options, preset.options);
    G.labelState = new Map();
    G.segments.forEach(seg => {
      ['time','travel'].forEach(kind => {
        const saved = preset?.labels?.[stableLabelKey(seg, kind)];
        G.labelState.set(labelKey(seg.uid, kind), saved ? deepClone(saved) : {
          visible:true, color:'#000000', customColor:true,
        });
      });
    });
    setDefaultCheckbox(Boolean(preset));
  }

  function syncTextControls() {
    const setValue = (id, value) => { const el=document.getElementById(id); if (el) el.value=String(value); };
    setValue('ganttPFontSize', G.options.labelFontSize);
    setValue('ganttPDriverSize', G.options.driverFontSize);
    const showTime=document.getElementById('ganttPShowTime'), showTravel=document.getElementById('ganttPShowTravel');
    if (showTime) showTime.checked=Boolean(G.options.showTime);
    if (showTravel) showTravel.checked=Boolean(G.options.showTravel);
    [['ganttPBoldLabel','labelBold'],['ganttPBoldAxis','driverBold']].forEach(([id,key]) => {
      const button=document.getElementById(id); if (!button) return;
      button.classList.toggle('active', Boolean(G.options[key]));
      button.setAttribute('aria-pressed', String(Boolean(G.options[key])));
    });
  }

  function textConfigurationChanged() {
    if (!G.savedDefaultPreset) return;
    if (JSON.stringify(currentDefaultPreset()) === JSON.stringify(G.savedDefaultPreset)) return;
    localStorage.removeItem(DEFAULT_PRESET_KEY);
    G.savedDefaultPreset = null;
    setDefaultCheckbox(false);
  }

  /* ---------- 数据构造：从仿真 schedule 构造 rows/segments ---------- */
  function buildSegmentsFromSchedule() {
    const schedule = state.simulationSchedule || [];
    const includeReverse = Boolean(state.ui.results?.gantt_reverse);
    const displayNames = state.ui.results?.gantt_display_names || {};
    const segmentsDisplay = state.ui.results?.gantt_segments || {};
    const motionEnd = Math.max(
      asFloat(state.project?.simulation?.end_time, 0),
      schedule.reduce((m, s) => Math.max(m, asFloat(s.end)), 0),
    );

    const rowsByDrive = new Map();
    schedule.forEach(item => {
      if (!rowsByDrive.has(item.drive_id)) rowsByDrive.set(item.drive_id, {id: item.drive_id, name: item.drive_name, segments: []});
      rowsByDrive.get(item.drive_id).segments.push({...item});
    });
    let rows = [...rowsByDrive.values()];
    const hidden = new Set(state.ui.results?.gantt_hidden || []);
    rows = rows.filter(r => !hidden.has(r.id));
    rows.forEach(row => row.name = displayNames[row.id] || row.name);
    rows.forEach(row => row.segments.sort((a,b)=>asFloat(a.start)-asFloat(b.start)));
    if (state.ui.results?.gantt_auto_sort !== false) {
      const direction = state.ui.results?.gantt_sort_desc ? -1 : 1;
      rows.sort((a,b) => direction * (Math.min(...a.segments.map(s=>asFloat(s.start)||0))-Math.min(...b.segments.map(s=>asFloat(s.start)||0))) || String(a.name).localeCompare(String(b.name),'zh-CN'));
    } else {
      const order = state.ui.results?.gantt_drive_order || [];
      const position = new Map(order.map((id,index)=>[id,index]));
      rows.sort((a,b)=>(position.get(a.id)??Number.MAX_SAFE_INTEGER)-(position.get(b.id)??Number.MAX_SAFE_INTEGER));
    }

    if (includeReverse) rows.push(...rows.map(row => ({
      id: row.id + '_reverse', name: `${row.name} [倒放]`, reverse: true,
      segments: row.segments.map(item => ({...item,
        start: Math.max(0, motionEnd - asFloat(item.end)),
        end:   Math.max(0, motionEnd - asFloat(item.start)),
        travel_start: item.travel_end, travel_end: item.travel_start,
      })).sort((a,b) => asFloat(a.start)-asFloat(b.start)),
    })));

    const segments = [];
    rows.forEach(row => {
      (row.segments || []).forEach((seg, i) => {
        let start = asFloat(seg.start, 0), end = asFloat(seg.end, start + asFloat(seg.duration, 0));
        if (end < start) [start, end] = [end, start];
        const index = i + 1;
        let color = ganttSegmentColor(segmentsDisplay[seg.id], index - 1);
        if (!/^#?[0-9a-f]{3,8}$/i.test(String(color).replace('#',''))) color = DEFAULT_COLORS[0];
        if (!color.startsWith('#')) color = '#' + color;
        let ts = seg.travel_start ?? null, te = seg.travel_end ?? seg.travel ?? null;
        if (ts != null) ts = asFloat(ts, 0); if (te != null) te = asFloat(te, 0);
        segments.push({
          uid: uid(), rowName: row.name, name: segmentsDisplay[seg.id]?.label || seg.name || `Segment ${index}`,
          stableKey: String(seg.id || `${seg.drive_id || row.id}:${index}:${start}:${end}`),
          start, end, segmentIndex: index,
          sourceDrive: seg.drive_id || row.id, sourceDisplayName: row.name,
          travelStart: ts, travelEnd: te, travelUnit: seg.travel_unit || '',
          color,
        });
      });
    });
    G.rows = rows.map(r => ({name: r.name, id: r.id}));
    G.segments = segments;
    G.segmentByUid = Object.fromEntries(segments.map(s => [s.uid, s]));
    initializeTextDefaults();
  }

  /* ---------- 渲染主循环 ---------- */
  function measureText(ctx, text, font, bold, size) {
    ctx.font = `${bold ? 'bold ' : ''}${size}px ${font}`;
    return ctx.measureText(text).width;
  }

  function draw() {
    if (!G.ctx) return;
    const o = G.options;
    const canvas = G.canvas, ctx = G.ctx;
    const ratio = window.devicePixelRatio || 1;
    const viewportWidth = Math.max(900, G.viewport.clientWidth - 0);
    const viewportHeight = Math.max(600, G.viewport.clientHeight - 0);
    // 预估 canvas 尺寸（先依据段数和缩放），实际宽度 = chartWidth + 左右边距
    const labelFont = DEFAULT_FONT_FAMILY;
    const driverFont = DEFAULT_FONT_FAMILY;

    // 计算行布局（先估算 leftMargin）
    ctx.save();
    ctx.scale(ratio, ratio);
    ctx.font = `${o.driverBold ? 'bold ' : ''}${o.driverFontSize}px ${driverFont}`;
    const leftMargin = Math.ceil(Math.max(0, ...G.rows.map(r => ctx.measureText(r.name).width))) + 10;
    const rightMargin = 12;

    const minT = Math.min(0, ...G.segments.map(s => s.start));
    const maxT = Math.max(0, ...G.segments.map(s => s.end));
    const totalTime = Math.max(
      asFloat(state.project?.simulation?.end_time, 0),
      asFloat(state.simulationSchedule && state.simulationSchedule.reduce ? state.simulationSchedule.reduce((m,s)=>Math.max(m,asFloat(s.end)),0) : 0, 0),
    );
    const axisMax = Math.max(maxT, totalTime, 0.01);
    const axisMin = minT < 0 ? minT : 0;
    const timeSpan = Math.max(1e-9, axisMax - axisMin);

    const baseChartWidth = Math.max(760, viewportWidth - leftMargin - rightMargin);
    const chartWidth = baseChartWidth * o.hZoom;
    const pixelsPerTime = chartWidth / timeSpan;

    const barHeight = Math.max(16, 19 * o.vZoom / 2.5);
    const laneGap = Math.max(3, 4 * o.vZoom / 2.5);
    const laneHeight = barHeight + laneGap;
    const rowGap = Math.max(3, 5 * o.vZoom / 2.5);
    // 每行1个lane（简单版）；如果未来有同驱动重叠，可拆分（此处保持1lane）
    const rowHeights = new Map();
    G.rows.forEach(r => rowHeights.set(r.name, laneHeight + rowGap));
    const contentHeight = G.rows.reduce((acc, r) => acc + (rowHeights.get(r.name) || laneHeight + rowGap), 0);

    // 顶部/底部边距
    ctx.font = `${o.driverBold ? 'bold ' : ''}${o.driverFontSize}px ${driverFont}`;
    const tickH = ctx.measureText('M').width; // 近似
    const topMargin = Math.max(78, tickH + o.driverFontSize + 26);
    const bottomMargin = 38;

    const sceneWidth = leftMargin + chartWidth + rightMargin;
    const sceneHeight = topMargin + contentHeight + bottomMargin;

    // 设定 canvas 尺寸
    canvas.width = Math.ceil(sceneWidth * ratio);
    canvas.height = Math.ceil(sceneHeight * ratio);
    canvas.style.width = sceneWidth + 'px';
    canvas.style.height = sceneHeight + 'px';
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);

    // 背景
    ctx.fillStyle = '#FBFCFD';
    ctx.fillRect(0, 0, sceneWidth, sceneHeight);

    if (G.segments.length === 0) {
      ctx.fillStyle = '#5d6974';
      ctx.font = `12px ${labelFont}`;
      ctx.fillText('暂无时序图数据，运行仿真后刷新可显示。', 20, 40);
      ctx.restore();
      renderLabelLayer();
      return;
    }

    // 坐标轴
    const axisY = topMargin - 26;
    ctx.strokeStyle = '#94A2AC'; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(leftMargin, axisY); ctx.lineTo(leftMargin + chartWidth, axisY); ctx.stroke();
    const tickStep = timeSpan <= 10 ? 0.5 : 1;
    const tickMin = Math.floor(axisMin / tickStep) * tickStep;
    const tickMax = Math.ceil(axisMax / tickStep) * tickStep;
    const span = Math.max(tickStep, tickMax - tickMin);
    const ppt = chartWidth / span;
    const tickCount = Math.max(1, Math.round(span / tickStep));
    ctx.fillStyle = '#000000';
    ctx.font = `${o.driverBold ? 'bold ' : ''}${o.driverFontSize}px ${driverFont}`;
    for (let i = 0; i <= tickCount; i++) {
      const t = tickMin + tickStep * i;
      const x = leftMargin + (t - tickMin) * ppt;
      ctx.beginPath(); ctx.moveTo(x, axisY - 4); ctx.lineTo(x, axisY + 4); ctx.stroke();
      // 虚线网格
      ctx.save();
      ctx.strokeStyle = '#E7ECF1'; ctx.setLineDash([5, 4]);
      ctx.beginPath(); ctx.moveTo(x, topMargin - 4); ctx.lineTo(x, topMargin + contentHeight); ctx.stroke();
      ctx.restore();
      const text = fmtAxisTick(t, tickStep);
      const w = ctx.measureText(text).width;
      ctx.fillText(text, x - w / 2, axisY - 10);
    }

    // 行名称 + 轨道
    let currentY = topMargin;
    const rowTops = new Map(); const rowCenters = new Map();
    G.rows.forEach(row => {
      const h = rowHeights.get(row.name) || laneHeight + rowGap;
      const center = currentY + (h - rowGap) / 2;
      rowTops.set(row.name, currentY);
      rowCenters.set(row.name, center);

      // 行名称（左侧，可双击重命名）
      ctx.save();
      ctx.fillStyle = '#000000';
      ctx.font = `${o.driverBold ? 'bold ' : ''}${o.driverFontSize}px ${driverFont}`;
      const w = ctx.measureText(row.name).width;
      const nameX = leftMargin - w - 10;
      const nameY = center - o.driverFontSize / 2 + ctx.measureText('M').width; // 垂直居中（近似）
      // 用 textBaseline 精确居中
      ctx.textBaseline = 'middle';
      ctx.fillText(row.name, nameX, center);
      ctx.restore();

      // 行分隔线
      ctx.strokeStyle = '#EAEEF2';
      ctx.beginPath(); ctx.moveTo(leftMargin, currentY + h - rowGap/2); ctx.lineTo(leftMargin + chartWidth, currentY + h - rowGap/2); ctx.stroke();

      // 轨道背景条
      const trackY = currentY + (laneHeight - laneGap - barHeight) / 2;
      const r = Math.min(5, barHeight / 3);
      roundRect(ctx, leftMargin, trackY, chartWidth, barHeight, r);
      ctx.fillStyle = '#F3F6F9'; ctx.fill();
      ctx.strokeStyle = '#E4E9EE'; ctx.lineWidth = 1; ctx.stroke();

      currentY += h;
    });

    // 画色块
    const barRects = {};
    const sortedByRow = new Map();
    G.segments.forEach(seg => {
      if (!sortedByRow.has(seg.rowName)) sortedByRow.set(seg.rowName, []);
      sortedByRow.get(seg.rowName).push(seg);
    });

    G.rows.forEach(row => {
      const y0 = rowTops.get(row.name) || topMargin;
      const segs = sortedByRow.get(row.name) || [];
      segs.forEach(seg => {
        const laneY = y0 + (laneHeight - laneGap - barHeight) / 2;
        const x = leftMargin + (seg.start - tickMin) * ppt;
        const dur = Math.max(0, seg.end - seg.start);
        const width = Math.max(3, dur * ppt);
        const rect = {x, y: laneY, width, height: barHeight};
        barRects[seg.uid] = rect;
        const r = Math.min(5, barHeight / 3);
        roundRect(ctx, x, laneY, width, barHeight, r);
        ctx.fillStyle = seg.color; ctx.fill();
        if (seg.uid === G.selectedUid) {
          ctx.strokeStyle = '#111827'; ctx.lineWidth = 1.5;
          roundRect(ctx, x, laneY, width, barHeight, r); ctx.stroke();
        }
      });
    });

    ctx.restore();

    G.lastRenderMeta = {
      leftMargin, rightMargin, topMargin, bottomMargin,
      chartWidth, sceneWidth, sceneHeight,
      axisMin: tickMin, axisMax: tickMax, ppt,
      barHeight, laneHeight, laneGap, rowGap,
      barRects, rowHeights, rowCenters, rowTops,
      labelFont, driverFont, labelSize: o.labelFontSize, labelBold: o.labelBold,
    };
    renderLabelLayer();
  }

  function roundRect(ctx, x, y, w, h, r) {
    const rr = Math.min(r, w/2, h/2);
    ctx.beginPath();
    ctx.moveTo(x+rr, y);
    ctx.arcTo(x+w, y, x+w, y+h, rr);
    ctx.arcTo(x+w, y+h, x, y+h, rr);
    ctx.arcTo(x, y+h, x, y, rr);
    ctx.arcTo(x, y, x+w, y, rr);
    ctx.closePath();
  }

  /* ---------- Label（时间/行程）HTML 层渲染 ---------- */
  function renderLabelLayer() {
    const layer = G.labelLayer; if (!layer) return;
    const meta = G.lastRenderMeta; if (!meta.barRects) { layer.innerHTML = ''; return; }
    const o = G.options;
    const rowsLabelNeeded = [];
    G.segments.forEach(seg => {
      const rect = meta.barRects[seg.uid]; if (!rect) return;
      const labels = [];
      if (o.showTime) {
        labels.push({kind:'time', text:`${fmtTime(seg.start)}s → ${fmtTime(seg.end)}s`});
      }
      if (o.showTravel && (seg.travelStart != null || seg.travelEnd != null)) {
        const t = `${fmtTravel(seg.travelStart)}${fmtUnit(seg.travelUnit)} → ${fmtTravel(seg.travelEnd)}${fmtUnit(seg.travelUnit)}`;
        labels.push({kind:'travel', text: t});
      }
      labels.forEach(label => rowsLabelNeeded.push({seg, rect, ...label}));
    });

    const fontSize = meta.labelSize;
    const bold = meta.labelBold;
    const lineGap = Math.max(2, fontSize * 0.1);
    // 预测量
    const tmpC = G.ctx;
    tmpC.save();
    tmpC.font = `${bold ? 'bold ' : ''}${fontSize}px ${meta.labelFont}`;
    const textHeight = fontSize * 1.25;

    // 渲染 HTML 标签
    const existing = new Map();
    layer.querySelectorAll('.gantt-label').forEach(el => {
      existing.set(el.dataset.key, el); el.classList.remove('keep');
    });

    const nowVisible = new Set();
    rowsLabelNeeded.forEach(({seg, rect, kind, text}) => {
      const key = labelKey(seg.uid, kind);
      const lstate = G.labelState.get(key) || {visible: true};
      if (lstate.visible === false) return;
      nowVisible.add(key);

      let customText = lstate.text;
      const displayText = typeof customText === 'string' ? customText : text;

      let el = existing.get(key);
      if (!el) {
        el = document.createElement('div');
        el.className = 'gantt-label';
        el.dataset.key = key;
        el.dataset.uid = seg.uid;
        el.dataset.kind = kind;
        attachLabelInteractions(el);
        layer.appendChild(el);
      }
      el.classList.add('keep');
      el.classList.toggle('selected', G.selectedLabel === key);
      el.textContent = displayText;
      el.style.fontSize = fontSize + 'px';
      el.style.fontWeight = bold ? '700' : '400';
      el.style.lineHeight = '1.2';
      tmpC.font = el.style.fontWeight === '700' ? `bold ${fontSize}px ${meta.labelFont}` : `${fontSize}px ${meta.labelFont}`;
      const w = Math.ceil(tmpC.measureText(displayText).width);
      // 定位：按段中心+kind偏移；如果 lstate.pos 则用自定义
      const count = (o.showTime && o.showTravel && (seg.travelStart != null || seg.travelEnd != null)) ? 2 : 1;
      const totalTextH = count * textHeight + (count - 1) * lineGap;
      const baseY = rect.y + rect.height / 2 - totalTextH / 2;
      const idx = kind === 'time' ? 0 : 1;
      const xDefault = rect.x + rect.width / 2 - w / 2;
      const yDefault = baseY + idx * (textHeight + lineGap);
      const hasCustomPos = Array.isArray(lstate.pos) && lstate.pos.length >= 2;
      const x = hasCustomPos ? lstate.pos[0] : xDefault;
      const y = hasCustomPos ? lstate.pos[1] : yDefault;
      el.style.left = x + 'px';
      el.style.top = y + 'px';
      el.style.width = 'auto';

      // 颜色：如果自定义颜色优先；否则自适应（色块内：黑/白；色块外：黑）
      let color;
      if (lstate.customColor && lstate.color) {
        color = lstate.color;
      } else {
        // 逐字自适应：简化为按标签中心
        const barRect = rect;
        const labelW = w;
        const cx = x + labelW / 2, cy = y + textHeight / 2;
        const inside = cx >= barRect.x && cx <= barRect.x + barRect.width && cy >= barRect.y && cy <= barRect.y + barRect.height;
        color = inside ? pickColorOnBackground(seg.color) : '#111827';
      }
      el.style.color = color;

      // tooltip
      el.title = '单击选中；拖动可移动；双击可改色和编辑文本；选中后按 Delete 可删除。';
    });

    // 清理不再存在的标签
    existing.forEach((el, key) => {
      if (!el.classList.contains('keep')) el.remove();
    });

    tmpC.restore();

    // 更新 badge
    const segCount = G.segments.length, rowCount = G.rows.length;
    G.badge.textContent = `${rowCount} 行 / ${segCount} 段`;
  }

  function attachLabelInteractions(el) {
    el.addEventListener('pointerdown', ev => {
      ev.stopPropagation();
      const key = el.dataset.key, uid = el.dataset.uid, kind = el.dataset.kind;
      G.selectedUid = null; G.selectedLabel = key;
      renderLabelLayer();
      setStatus(`已选择${kind==='time'?'时间':'行程'}文本：${G.segmentByUid[uid]?.rowName || ''} / 第 ${G.segmentByUid[uid]?.segmentIndex} 段。可拖动位置，双击编辑，按 Delete 删除。`);
      // 开始拖拽
      const startX = ev.clientX, startY = ev.clientY;
      const sx = parseFloat(el.style.left), sy = parseFloat(el.style.top);
      el.classList.add('dragging');
      el.setPointerCapture && el.setPointerCapture(ev.pointerId);
      const move = e => {
        el.style.left = Math.max(0, sx + (e.clientX - startX)) + 'px';
        el.style.top  = Math.max(0, sy + (e.clientY - startY)) + 'px';
      };
      const up = e => {
        el.classList.remove('dragging');
        el.releasePointerCapture && el.releasePointerCapture(ev.pointerId);
        window.removeEventListener('pointermove', move);
        window.removeEventListener('pointerup', up);
        // 保存位置
        const state = G.labelState.get(key) || {};
        state.visible = true;
        state.pos = [parseFloat(el.style.left), parseFloat(el.style.top)];
        G.labelState.set(key, state);
        textConfigurationChanged();
      };
      window.addEventListener('pointermove', move);
      window.addEventListener('pointerup', up);
    });
    el.addEventListener('dblclick', ev => {
      ev.stopPropagation();
      const key = el.dataset.key;
      G.selectedLabel = key;
      openLabelDialog(key);
    });
    el.addEventListener('contextmenu', ev => {
      ev.preventDefault();
      ev.stopPropagation();
      const key = el.dataset.key;
      G.selectedLabel = key;
      if (confirm('对该文本执行：确定 = 删除；取消 = 编辑颜色/内容。')) {
        deleteSelectedLabel();
      } else {
        openLabelDialog(key);
      }
    });
  }

  function deleteCurrentSelection() {
    if (G.selectedLabel) { deleteSelectedLabel(); return; }
    if (G.selectedUid) { deleteSelectedSegment(G.selectedUid); return; }
    setStatus('请先单击选择一个文本或色块，再按 Delete 删除。');
  }

  function deleteSelectedLabel() {
    const key = G.selectedLabel; if (!key) return;
    const st = G.labelState.get(key) || {}; st.visible = false; G.labelState.set(key, st);
    G.selectedLabel = null;
    renderLabelLayer();
    textConfigurationChanged();
    setStatus('已删除所选文本。点击「复位并自适应文本」可恢复。');
  }

  function deleteSelectedSegment(uid) {
    const seg = G.segmentByUid[uid]; if (!seg) return;
    const removed = `${seg.rowName} / 第 ${seg.segmentIndex} 段 / ${seg.name}`;
    G.segments = G.segments.filter(s => s.uid !== uid);
    delete G.segmentByUid[uid];
    for (const k of [...G.labelState.keys()]) if (k.startsWith(uid + '::')) G.labelState.delete(k);
    G.selectedUid = null; G.selectedLabel = null;
    setStatus(`已删除色块：${removed}`);
    draw();
    textConfigurationChanged();
  }

  function setStatus(text, isError=false) {
    if (!G.status) return;
    G.status.classList.toggle('error', Boolean(isError));
    G.status.textContent = text;
  }

  /* ---------- 色块颜色 ---------- */
  function updateSegmentColorButton() {
    const btn = document.getElementById('ganttPSegmentColor'); if (!btn) return;
    const seg = G.segmentByUid[G.selectedUid || ''];
    const color = seg?.color || DEFAULT_COLORS[0];
    btn.style.setProperty('--btn-color', color);
    btn.style.borderLeft = `14px solid ${color}`;
  }

  function chooseSingleSegmentColor(uid) {
    const seg = G.segmentByUid[uid || G.selectedUid || '']; if (!seg) {
      setStatus('请先在甘特图中单击一个色块。', true); return;
    }
    G.selectedUid = seg.uid; G.selectedLabel = null;
    const tmp = document.createElement('input');
    tmp.type = 'color'; tmp.value = seg.color;
    tmp.addEventListener('change', () => {
      seg.color = tmp.value; updateSegmentColorButton(); draw();
      setStatus(`已单独更新色块颜色：${seg.rowName} / 第 ${seg.segmentIndex} 段 / ${seg.color}`);
    });
    tmp.click();
  }

  function chooseMotionSegmentColor() {
    const selected = G.segmentByUid[G.selectedUid || '']; if (!selected) {
      setStatus('请先在甘特图中单击一个色块。', true); return;
    }
    const tmp = document.createElement('input');
    tmp.type = 'color'; tmp.value = selected.color;
    tmp.addEventListener('change', () => {
      const motionKey = String(selected.name || '').trim();
      let changed = 0;
      G.segments.forEach(seg => {
        const same = motionKey ? (String(seg.name || '').trim() === motionKey) : (seg.segmentIndex === selected.segmentIndex);
        if (same) { seg.color = tmp.value; changed++; }
      });
      draw();
      setStatus(`已更新运动段「${selected.name}」颜色：${tmp.value}（共 ${changed} 个色块）；双击色块仍可单独覆盖。`);
    });
    tmp.click();
  }

  /* ---------- 标签编辑对话框 ---------- */
  function openLabelDialog(key) {
    const dlg = document.getElementById('ganttLabelDialog'); if (!dlg) return;
    const [uid, kind] = (key || G.selectedLabel || '').split('::');
    if (!uid) return;
    G.labelDialogTarget = key;
    const st = G.labelState.get(key) || {};
    const el = G.labelLayer.querySelector(`[data-key="${CSS.escape(key)}"]`);
    const currentColor = st.color || (el ? el.style.color : '#2B353C') || '#2B353C';
    // RGB 近似转 hex
    const color = rgbToHex(String(currentColor)) || '#2B353C';
    G.tempLabelColor = color;
    document.getElementById('ganttLabelDialogText').value = st.text ?? el?.textContent ?? '';
    document.getElementById('ganttLabelDialogColor').value = color;
    updateLabelDialogPreview(color);
    if (typeof dlg.showModal === 'function') dlg.showModal();
  }
  function rgbToHex(input) {
    const s = String(input).trim();
    if (/^#([0-9a-f]{3,8})$/i.test(s)) return s;
    const m = s.match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const parts = m[1].split(',').map(x => Number(x.trim()));
    const [r,g,b] = parts;
    return '#' + [r,g,b].map(v => Math.max(0,Math.min(255,Math.round(v||0))).toString(16).padStart(2,'0')).join('');
  }
  function updateLabelDialogPreview(color) {
    const p = document.getElementById('ganttLabelDialogPreview'); if (!p) return;
    color = color || '#2B353C';
    p.textContent = color; p.style.background = color;
    const lum = luminanceOf(color);
    p.style.color = lum > 170 ? '#111827' : '#FFFFFF';
  }

  function confirmLabelDialog() {
    const key = G.labelDialogTarget; if (!key) return;
    const text = document.getElementById('ganttLabelDialogText').value;
    const color = document.getElementById('ganttLabelDialogColor').value || '#2B353C';
    const st = G.labelState.get(key) || {};
    st.text = text; st.color = color; st.customColor = true; st.visible = true;
    G.labelState.set(key, st);
    renderLabelLayer();
    textConfigurationChanged();
    setStatus(`已更新文本内容和颜色：${text || '空文本'} / ${color}`);
  }

  /* ---------- 复位 / 全黑 / 双击驱动名重命名 ---------- */
  function resetAllLabelState() {
    const preserved = new Map();
    G.labelState.forEach((st, key) => {
      const next = {visible: true};
      if (typeof st.text === 'string') next.text = st.text;
      if (st.customColor && st.color) { next.color = st.color; next.customColor = true; }
      preserved.set(key, next);
    });
    G.labelState = preserved; G.selectedLabel = null;
    draw();
    textConfigurationChanged();
    setStatus('已将全部时间/行程文本复位到色块中心；默认黑色及用户自定义颜色保持优先。');
  }
  function makeAllFontsBlack() {
    G.segments.forEach(seg => {
      ['time','travel'].forEach(kind => {
        const st = G.labelState.get(labelKey(seg.uid, kind)) || {};
        st.color = '#000000'; st.customColor = true; st.visible = true;
        G.labelState.set(labelKey(seg.uid, kind), st);
      });
    });
    renderLabelLayer();
    textConfigurationChanged();
    setStatus('已将甘特图字体统一设置为黑色；点击「复位并自适应文本」可恢复自适应。');
  }
  function renameDriverRow(oldName) {
    const newName = prompt('自定义驱动名称：', oldName);
    if (newName == null) return;
    const nm = String(newName).trim();
    if (!nm || nm === oldName) return;
    if (G.rows.some(r => r.name === nm)) { alert('驱动名称已存在。'); return; }
    G.rows.forEach(r => { if (r.name === oldName) r.name = nm; });
    G.segments.forEach(s => {
      if (s.rowName === oldName) { s.rowName = nm; if (!s.sourceDisplayName || s.sourceDisplayName === oldName) s.sourceDisplayName = nm; }
    });
    setStatus(`已将驱动名称从「${oldName}」修改为「${nm}」。`);
    draw();
  }

  /* ---------- 画布交互（平移/单击色块选中等） ---------- */
  function attachViewportInteractions() {
    const vp = G.viewport; const canvas = G.canvas;
    // 滚轮横向缩放（可选）：这里做平移（用 grab cursor 做 scroll）
    let panning = null;
    vp.addEventListener('pointerdown', ev => {
      const inLabel = ev.target.closest && ev.target.closest('.gantt-label');
      if (inLabel) return;
      // 判断是否点击了色块（通过坐标命中）
      const rect = canvas.getBoundingClientRect();
      const x = ev.clientX - rect.left, y = ev.clientY - rect.top;
      const meta = G.lastRenderMeta;
      let hitUid = null;
      for (const uid in (meta.barRects || {})) {
        const b = meta.barRects[uid];
        if (x >= b.x && x <= b.x + b.width && y >= b.y && y <= b.y + b.height) { hitUid = uid; break; }
      }
      // 判断是否点击了左侧行名称（双击重命名）
      if (hitUid) {
        G.selectedUid = hitUid; G.selectedLabel = null;
        const seg = G.segmentByUid[hitUid];
        const travel = (seg.travelStart!=null||seg.travelEnd!=null) ? `，行程 ${fmtTravel(seg.travelStart)}${fmtUnit(seg.travelUnit)} → ${fmtTravel(seg.travelEnd)}${fmtUnit(seg.travelUnit)}` : '';
        setStatus(`已选择色块：${seg.rowName} / 第 ${seg.segmentIndex} 段 / ${seg.name}，时间 ${fmtTime(seg.start)}s → ${fmtTime(seg.end)}s，时长 ${fmtTime(seg.duration)}s${travel}。双击可单独改色，按 Delete 可删除该色块。`);
        updateSegmentColorButton();
        draw();
        return;
      }
      // 双击行名称
      if (meta && ev.detail === 2) {
        for (const row of G.rows) {
          const cy = meta.rowCenters.get(row.name);
          const nameW = measureText(G.ctx, row.name, meta.driverFont, G.options.driverBold, G.options.driverFontSize);
          const xL = meta.leftMargin - nameW - 10, xR = meta.leftMargin - 10;
          const half = Math.max(meta.driverFontSize * 1.1, 22) / 2;
          if (x >= xL && x <= xR && y >= cy - half && y <= cy + half) {
            renameDriverRow(row.name); return;
          }
        }
      }
      // 双击空白处：单段颜色
      if (ev.detail === 2 && G.selectedUid) {
        chooseSingleSegmentColor(G.selectedUid);
        return;
      }
      // 空白处开始 panning
      panning = {sx: ev.clientX, sy: ev.clientY, sl: vp.scrollLeft, st: vp.scrollTop};
      vp.classList.add('panning');
      ev.preventDefault();
    });
    window.addEventListener('pointermove', ev => {
      if (!panning) return;
      vp.scrollTop = panning.st - (ev.clientY - panning.sy);
      vp.scrollLeft = panning.sl - (ev.clientX - panning.sx);
    });
    window.addEventListener('pointerup', () => {
      if (!panning) return;
      panning = null; vp.classList.remove('panning');
    });
    // 右键菜单（画布）
    canvas.addEventListener('contextmenu', ev => {
      ev.preventDefault();
      const rect = canvas.getBoundingClientRect();
      const x = ev.clientX - rect.left, y = ev.clientY - rect.top;
      const meta = G.lastRenderMeta;
      for (const uid in (meta.barRects || {})) {
        const b = meta.barRects[uid];
        if (x >= b.x && x <= b.x + b.width && y >= b.y && y <= b.y + b.height) {
          G.selectedUid = uid; draw();
          const choice = prompt('对该色块操作：\n输入 1 = 更改颜色\n输入 2 = 删除该色块\n输入 3 = 显示详情', '1');
          if (choice === '1') chooseSingleSegmentColor(uid);
          else if (choice === '2') deleteSelectedSegment(uid);
          else if (choice === '3') showSegmentDetail(uid);
          return;
        }
      }
    });
  }

  function showSegmentDetail(uid) {
    const seg = G.segmentByUid[uid]; if (!seg) return;
    alert([
      `驱动行：${seg.rowName}`,
      `来源驱动：${seg.sourceDrive}`,
      `展示名称：${seg.sourceDisplayName || seg.rowName}`,
      `段号：第 ${seg.segmentIndex} 段`,
      `段名称：${seg.name}`,
      `起始时间：${fmtTime(seg.start)} s`,
      `结束时间：${fmtTime(seg.end)} s`,
      `运动时长：${fmtTime(seg.duration)} s`,
      `行程：${(seg.travelStart!=null||seg.travelEnd!=null) ? `${fmtTravel(seg.travelStart)}${fmtUnit(seg.travelUnit)} → ${fmtTravel(seg.travelEnd)}${fmtUnit(seg.travelUnit)}` : '—'}`,
    ].join('\n'));
  }

  /* ---------- 导出 PNG ---------- */
  function renderGanttPngCanvas() {
    const meta = G.lastRenderMeta;
    if (!meta || !meta.sceneWidth) return null;
    const selEl = G.labelLayer.querySelector('.selected');
    if (selEl) selEl.classList.remove('selected');
    const out = document.createElement('canvas');
    out.width = Math.ceil(meta.sceneWidth);
    out.height = Math.ceil(meta.sceneHeight);
    const octx = out.getContext('2d');
    octx.fillStyle = '#FBFCFD'; octx.fillRect(0,0,meta.sceneWidth,meta.sceneHeight);
    octx.drawImage(G.canvas, 0, 0, meta.sceneWidth, meta.sceneHeight);
    G.labelLayer.querySelectorAll('.gantt-label').forEach(el => {
      const fontSize = parseFloat(getComputedStyle(el).fontSize);
      octx.font = `${Number(getComputedStyle(el).fontWeight)>=600 ? 'bold ' : ''}${fontSize}px ${DEFAULT_FONT_FAMILY}`;
      octx.fillStyle = getComputedStyle(el).color || '#000000';
      octx.textBaseline = 'top';
      octx.fillText(el.textContent, parseFloat(el.style.left), parseFloat(el.style.top));
    });
    if (selEl) selEl.classList.add('selected');
    return out;
  }

  function ganttCacheMetadata(meta) {
    const rows = G.rows.map(row => {
      const top = Number(meta.rowTops.get(row.name) || meta.topMargin);
      const height = Number(meta.rowHeights.get(row.name) || meta.laneHeight + meta.rowGap);
      const bottom = top + height - meta.rowGap;
      return {
        name:row.name, drive_id:row.id, top, bottom,
        center:Number(meta.rowCenters.get(row.name) || (top + bottom) / 2),
        segments:G.segments.filter(seg => seg.rowName === row.name).map(seg => ({start:seg.start,end:seg.end})),
        value_series:[],
      };
    });
    return {
      format:'MUJOCO_XML_TOOL_GANTT_CACHE', format_version:1,
      axis_min:meta.axisMin, axis_max:meta.axisMax,
      chart_left:meta.leftMargin, chart_right:meta.leftMargin + meta.chartWidth,
      chart_top:meta.topMargin,
      chart_bottom:meta.topMargin + [...meta.rowHeights.values()].reduce((sum,value)=>sum+Number(value),0),
      scene_width:meta.sceneWidth, scene_height:meta.sceneHeight,
      image_width:Math.ceil(meta.sceneWidth), image_height:Math.ceil(meta.sceneHeight),
      simulation_time_offset:0, rows,
      segment_count:G.segments.length, drive_count:G.rows.length, source:'gantt_popup',
      drive_signature:viewerGanttDriveSignature(),
    };
  }

  async function saveGanttCache({announce=true}={}) {
    if (!state.project?.id) throw new Error('请先打开或保存项目');
    const meta = G.lastRenderMeta;
    const out = renderGanttPngCanvas();
    if (!meta || !out) throw new Error('暂无可导出的甘特图内容用于缓存');
    if (announce) setStatus('正在生成缓存图片并写入项目缓存…');
    const dataUrl = out.toDataURL('image/png');
    const res = await api(`/api/projects/${state.project.id}/gantt-cache`, {
      method:'POST',
      body:JSON.stringify({
        image_data:dataUrl.slice(dataUrl.indexOf(',') + 1),
        metadata:ganttCacheMetadata(meta),
      }),
    });
    if (announce) {
      const when = res.saved_at ? new Date(res.saved_at * 1000).toLocaleString('zh-CN') : '刚刚';
      setStatus(`已保存动画窗口使用的 PNG 缓存：${when}`);
      toast('甘特图缓存已更新，Viewer 将直接读取该 PNG。', 'success');
    }
    return res;
  }

  async function exportPng() {
    const out = renderGanttPngCanvas();
    if (!out) { setStatus('暂无可导出的甘特图内容。', true); return; }
    const base = (state.project?.name || '模型').replace(/[\/:*?"<>|]/g,'_').trim() || '模型';
    let stem=base;
    try {
      const naming=await api(`/api/projects/${state.project.id}/delivery-stem`);
      stem=String(naming.stem||base);
    } catch(error) { console.warn('[gantt-export] delivery stem fallback:',error); }
    const filename=`${stem}_甘特图.png`;
    const handle=await chooseLocalSaveHandle(filename,'image/png');
    if(!handle)return;
    const blob=await new Promise(resolve=>out.toBlob(resolve,'image/png'));
    if(!blob||!await writeBlobToChosenHandle(handle,blob,'甘特图 PNG'))return;
    try {
      await saveGanttCache({announce:false});
      setStatus(`已导出 PNG，并更新动画窗口使用的最新甘特图缓存：${filename}`);
    } catch (error) {
      setStatus(`已导出 PNG，但缓存更新失败：${error.message}`, true);
    }
  }

  /* ---------- 打开/关闭弹窗 ---------- */
  function open() {
    if (!G.popup) {
      G.popup = document.getElementById('ganttPopup');
      G.canvas = document.getElementById('ganttPCanvas');
      G.ctx = G.canvas.getContext('2d');
      G.labelLayer = document.getElementById('ganttPLabelLayer');
      G.viewport = document.getElementById('ganttPViewport');
      G.status = document.getElementById('ganttPStatus');
      G.badge = document.getElementById('ganttPopupBadge');
      bindToolbar();
      attachViewportInteractions();
    }
    G.savedDefaultPreset = readDefaultPreset();
    buildSegmentsFromSchedule();
    syncTextControls();
    // 重置选择
    G.selectedUid = null; G.selectedLabel = null;
    // 滚动到顶部
    requestAnimationFrame(() => {
      G.viewport.scrollTop = 0; G.viewport.scrollLeft = 0;
    });
    G.popup.classList.remove('hidden');
    // Use the existing "恢复默认" handler every time the popup becomes visible.
    // This synchronizes sliders AND redraws the canvas after layout is measurable.
    const resetZoom = document.getElementById('ganttPResetZoom');
    if (resetZoom) resetZoom.click(); else draw();
    setStatus('就绪（已自动恢复默认缩放）');
  }
  function close() { G.popup && G.popup.classList.add('hidden'); }

  // Serialize browser PNG publications; an Enter and a Viewer click must not
  // overwrite the same cache pair concurrently or steal the same canvas.
  let ganttCacheRefreshChain = Promise.resolve();
  function awaitCacheIdle() {return ganttCacheRefreshChain;}
  function refreshCache(projectId) {
    const task = ganttCacheRefreshChain.catch(() => null).then(() => renderAndSaveGanttCache(projectId));
    ganttCacheRefreshChain = task.catch(() => null);
    return task;
  }
  async function renderAndSaveGanttCache(projectId) {
    if (!projectId) throw new Error('请先选择模型');
    const previousProjectId=state.project?.id||'';
    const previousMode=state.editSessionMode;
    if (!state.project || state.project.id !== projectId) await loadProject(projectId, {force:true});
    // A cache refresh only needs the drive schedule, NOT the previous
    // simulation_result.json and mesh fingerprints. Keep this path independent
    // of the expensive /simulate Job and its polling loop.
    const revision = state.editRevision;
    await refreshDriveProjection(projectId, revision, {render:false, draft:state.dirty && canEditProject()});
    refreshCombinedGanttSchedule({render:false});
    const wasVisible = Boolean(G.popup && !G.popup.classList.contains('hidden'));
    open();
    if (!wasVisible) G.popup.style.visibility = 'hidden';
    try {
      document.getElementById('ganttPResetZoom')?.click();
      await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
      return await saveGanttCache({announce:false});
    } finally {
      G.popup.style.visibility = '';
      if (!wasVisible) close();
      if(previousProjectId&&previousProjectId!==projectId){
        try {
          await loadProject(previousProjectId,{force:true});
        } catch (error) {
          console.warn('恢复刷新前模型失败', error);
        }
        state.editSessionMode=previousMode;
      }
    }
  }

  /* ---------- 工具栏事件 ---------- */
  function bindToolbar() {
    document.getElementById('ganttPopupClose').addEventListener('click', close);
    // 遮罩点击关闭
    G.popup.addEventListener('click', ev => { if (ev.target === G.popup) close(); });
    document.addEventListener('keydown', ev => {
      if (G.popup.classList.contains('hidden')) return;
      if (ev.key === 'Escape') { close(); return; }
      if (ev.key === 'Delete' || ev.key === 'Backspace') {
        const t = ev.target; if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return;
        ev.preventDefault(); deleteCurrentSelection();
      }
    });

    const hz = document.getElementById('ganttPHZoom'), vz = document.getElementById('ganttPVZoom');
    const hzL = document.getElementById('ganttPHZoomLabel'), vzL = document.getElementById('ganttPVZoomLabel');
    const onScale = () => { G.options.hZoom = Number(hz.value)/100; G.options.vZoom = Number(vz.value)/100; hzL.textContent = hz.value+'%'; vzL.textContent = vz.value+'%'; draw(); };
    hz.addEventListener('input', onScale); vz.addEventListener('input', onScale);
    document.getElementById('ganttPResetZoom').addEventListener('click', () => {
      hz.value = 100; vz.value = 450; onScale();
    });
    document.getElementById('ganttPFontSize').addEventListener('change', ev => {
      G.options.labelFontSize = Math.max(6, Math.min(72, Number(ev.target.value)||16)); draw(); textConfigurationChanged();
    });
    const boldL = document.getElementById('ganttPBoldLabel');
    boldL.addEventListener('click', () => {
      G.options.labelBold = !G.options.labelBold;
      boldL.classList.toggle('active', G.options.labelBold);
      boldL.setAttribute('aria-pressed', G.options.labelBold); draw(); textConfigurationChanged();
    });
    document.getElementById('ganttPDriverSize').addEventListener('change', ev => {
      G.options.driverFontSize = Math.max(6, Math.min(72, Number(ev.target.value)||20)); draw(); textConfigurationChanged();
    });
    const boldA = document.getElementById('ganttPBoldAxis');
    boldA.addEventListener('click', () => {
      G.options.driverBold = !G.options.driverBold;
      boldA.classList.toggle('active', G.options.driverBold);
      boldA.setAttribute('aria-pressed', G.options.driverBold); draw(); textConfigurationChanged();
    });

    document.getElementById('ganttPSegmentColor').addEventListener('click', chooseMotionSegmentColor);
    document.getElementById('ganttPResetLabels').addEventListener('click', resetAllLabelState);
    document.getElementById('ganttPBlackFont').addEventListener('click', makeAllFontsBlack);

    document.getElementById('ganttPShowTime').addEventListener('change', ev => { G.options.showTime = ev.target.checked; draw(); textConfigurationChanged(); });
    document.getElementById('ganttPShowTravel').addEventListener('change', ev => { G.options.showTravel = ev.target.checked; draw(); textConfigurationChanged(); });
    document.getElementById('ganttPSetDefault').addEventListener('change', ev => {
      if (G.updatingDefaultCheckbox) return;
      if (ev.target.checked) {
        const preset = currentDefaultPreset();
        localStorage.setItem(DEFAULT_PRESET_KEY, JSON.stringify(preset));
        G.savedDefaultPreset = preset;
        setStatus('已将当前文本类别、文本属性和文本内容设置为默认值。');
      } else {
        localStorage.removeItem(DEFAULT_PRESET_KEY);
        G.savedDefaultPreset = null;
        setStatus('已取消默认预设；下次打开时使用代码内置默认值。');
      }
    });
    document.getElementById('ganttPExportPng').addEventListener('click', exportPng);
    document.getElementById('ganttPLoadCache').addEventListener('click', async () => {
      try { await saveGanttCache(); }
      catch (err) { setStatus(`保存缓存失败：${err.message}`, true); toast(`保存缓存失败：${err.message}`, 'error'); }
    });

    // Label dialog
    document.getElementById('ganttLabelDialogChoose').addEventListener('click', () => {
      const input = document.getElementById('ganttLabelDialogColor');
      input.value = G.tempLabelColor || '#2B353C';
      input.addEventListener('change', () => {
        G.tempLabelColor = input.value;
        updateLabelDialogPreview(input.value);
      }, {once: true});
      input.click();
    });
    document.getElementById('ganttLabelDialog').addEventListener('close', () => {
      const dlg = document.getElementById('ganttLabelDialog');
      if (dlg.returnValue === 'default' || dlg.returnValue === '') confirmLabelDialog();
    });
    // Resize 观察
    new ResizeObserver(() => { if (!G.popup.classList.contains('hidden')) draw(); }).observe(G.viewport);
  }

  /* ---------- 导出到全局 ---------- */
  window.__GanttPopup__ = { open, close, draw, refreshCache, awaitCacheIdle };
})();

/* 入口：甘特图弹窗按钮 */
function openGanttPopup() {
  if (!state.simulationSchedule || state.simulationSchedule.length === 0) {
    toast('先运行仿真生成时序数据后，再打开甘特图弹窗。', 'error'); return;
  }
  if (typeof window.__GanttPopup__?.open === 'function') window.__GanttPopup__.open();
}

boot().catch((err) => {
  // 兜底：如果 async boot() 本身抛错（未被内部 catch 捕获的），强制把 UI 挂起态改掉并给用户提示
  try {
    console.error('[boot fatal]', err);
    $('#apiDot').classList.add('error');
    $('#apiStatus').textContent = '启动异常（打开控制台查看）';
    toast('前端启动失败：' + (err && err.message ? err.message : String(err)), 'error');
    finishHubEntryTransition();
  } catch (_) {}
});
