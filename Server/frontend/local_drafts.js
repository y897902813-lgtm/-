/* MuJoCo Studio V2.16.7 · per-user, per-model browser draft/cache boundary.
 * The server remains the authority for ACL, checkout, published versions and
 * derived artifacts. No project is ever POSTed by this module.
 */
(function (global) {
  'use strict';
  const DATABASE = 'mujoco-studio-browser-drafts';
  const STORE = 'drafts';
  const AGE_MS = 14 * 86400000;
  const MAX_ENTRIES_PER_USER = 16;
  const MAX_DRAFT_BYTES = 8 * 1024 * 1024;
  const CATALOG_TTL_MS = 10 * 60 * 1000;
  const CATALOG_MAX_BYTES = 2 * 1024 * 1024;
  let opening = null;
  let chain = Promise.resolve();

  function key(username, projectId) {
    const user = String(username || '').trim().toLowerCase();
    const project = String(projectId || '').trim();
    if (!user || !project) throw new Error('draft_owner_or_project_missing');
    return `${user}\u001f${project}`;
  }

  function openDatabase() {
    if (!global.indexedDB) return Promise.resolve(null);
    if (opening) return opening;
    opening = new Promise(resolve => {
      let request;
      try { request = global.indexedDB.open(DATABASE, 1); }
      catch (_) { resolve(null); return; }
      request.onupgradeneeded = () => {
        const db = request.result;
        if (!db.objectStoreNames.contains(STORE)) db.createObjectStore(STORE, {keyPath:'key'});
      };
      request.onsuccess = () => {
        const db = request.result;
        db.onversionchange = () => { db.close(); opening = null; };
        resolve(db);
      };
      request.onerror = () => resolve(null);
      request.onblocked = () => resolve(null);
    });
    return opening;
  }

  function transact(db, mode, operation) {
    return new Promise((resolve, reject) => {
      let tx;
      try { tx = db.transaction(STORE, mode); }
      catch (error) { reject(error); return; }
      const store = tx.objectStore(STORE);
      let result;
      try { result = operation(store); }
      catch (error) { tx.abort(); reject(error); return; }
      tx.oncomplete = () => resolve(result?.result);
      tx.onerror = () => reject(tx.error || new Error('IndexedDB transaction failed'));
      tx.onabort = () => reject(tx.error || new Error('IndexedDB transaction aborted'));
    });
  }

  function serial(action) {
    const next = chain.catch(() => null).then(action);
    chain = next.catch(() => null);
    return next;
  }

  async function prune(db, owner) {
    const all = await transact(db, 'readonly', store => store.getAll());
    if (!Array.isArray(all)) return;
    const now = Date.now();
    const owned = all.filter(item => item?.owner === owner).sort((a,b) => (b.updatedAt || 0) - (a.updatedAt || 0));
    const stale = owned.filter((item,index) => index >= MAX_ENTRIES_PER_USER || now - Number(item.updatedAt || 0) > AGE_MS);
    if (!stale.length) return;
    await transact(db, 'readwrite', store => { stale.forEach(item => store.delete(item.key)); });
  }

  async function save(username, projectId, payload) {
    const id = key(username, projectId);
    const owner = String(username).trim().toLowerCase();
    const record = {key:id, owner, projectId:String(projectId), updatedAt:Date.now(), schema:1, payload};
    const serialized = JSON.stringify(record);
    if (serialized.length * 2 > MAX_DRAFT_BYTES) throw new Error('草稿超过 8MiB 本地存储预算，请立即同步或导出模型');
    return serial(async () => {
      const db = await openDatabase();
      if (!db) throw new Error('当前浏览器禁止 IndexedDB，草稿只能保留在当前标签页内');
      await transact(db, 'readwrite', store => store.put(JSON.parse(serialized)));
      await prune(db, owner);
      return true;
    });
  }

  async function read(username, projectId) {
    const id = key(username, projectId);
    return serial(async () => {
      const db = await openDatabase();
      if (!db) return null;
      const record = await transact(db, 'readonly', store => store.get(id));
      if (!record || record.schema !== 1 || Date.now() - Number(record.updatedAt || 0) > AGE_MS) return null;
      return record.payload && typeof record.payload === 'object' ? record : null;
    });
  }

  async function remove(username, projectId) {
    const id = key(username, projectId);
    return serial(async () => {
      const db = await openDatabase();
      if (!db) return false;
      await transact(db, 'readwrite', store => store.delete(id));
      return true;
    });
  }

  function catalogKey(username) { return `mujoco-studio-catalog-v21511:${String(username || '').toLowerCase()}`; }
  function saveCatalog(username, projects) {
    if (!username || !Array.isArray(projects)) return false;
    try {
      const record = JSON.stringify({updatedAt:Date.now(), projects});
      if (record.length * 2 > CATALOG_MAX_BYTES) return false;
      global.localStorage?.setItem(catalogKey(username), record);
      return true;
    } catch (_) { return false; }
  }
  function readCatalog(username) {
    if (!username) return null;
    try {
      const record = JSON.parse(global.localStorage?.getItem(catalogKey(username)) || 'null');
      if (!record || !Array.isArray(record.projects) || Date.now() - Number(record.updatedAt || 0) > CATALOG_TTL_MS) return null;
      return record.projects;
    } catch (_) { return null; }
  }

  global.MuJoCoLocalDrafts = Object.freeze({save, read, remove, saveCatalog, readCatalog});
})(window);
