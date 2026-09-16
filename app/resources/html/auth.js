/**
 * 掌柜智库 - 前端鉴权工具（Query :8001 / Import :8000 共用 JWT）
 */
(function (global) {
  const AUTH_BASE = location.origin.startsWith('http')
    ? location.origin
    : 'http://127.0.0.1:8001';

  const STORAGE_ACCESS = 'rag_access_token';
  const STORAGE_REFRESH = 'rag_refresh_token';
  const STORAGE_REMEMBER = 'rag_remember_me';
  const IMPORT_ENTRY_KEY = 'rag_import_entry_allowed';

  function queryHomeUrl() {
    if (location.protocol === 'file:') return 'chat_new.html';
    return `${AUTH_BASE}/html/new`;
  }

  function importPageUrl() {
    if (location.protocol === 'file:') return 'import_new.html';
    return `${AUTH_BASE}/html/import`;
  }

  function getImportApiBase() {
    if (location.protocol === 'file:') return 'http://127.0.0.1:8000';
    const host = location.hostname || '127.0.0.1';
    return `${location.protocol}//${host}:8000`;
  }

  function grantImportEntry() {
    sessionStorage.setItem(IMPORT_ENTRY_KEY, '1');
  }

  function checkImportEntry() {
    return sessionStorage.getItem(IMPORT_ENTRY_KEY) === '1';
  }

  /** 导入页入口守卫：须从问答页跳转进入 */
  function guardImportPage() {
    if (location.protocol === 'file:') return true;
    if (checkImportEntry()) return true;
    location.replace(queryHomeUrl());
    return false;
  }

  function navigateToImport() {
    grantImportEntry();
    location.href = importPageUrl();
  }

  function isRememberMe() {
    return localStorage.getItem(STORAGE_REMEMBER) === '1';
  }

  function tokenStorage() {
    return isRememberMe() ? localStorage : sessionStorage;
  }

  function getAccessToken() {
    return tokenStorage().getItem(STORAGE_ACCESS) || sessionStorage.getItem(STORAGE_ACCESS) || localStorage.getItem(STORAGE_ACCESS);
  }

  function getRefreshToken() {
    return tokenStorage().getItem(STORAGE_REFRESH) || sessionStorage.getItem(STORAGE_REFRESH) || localStorage.getItem(STORAGE_REFRESH);
  }

  function saveTokens(accessToken, refreshToken, rememberMe) {
    localStorage.setItem(STORAGE_REMEMBER, rememberMe ? '1' : '0');
    sessionStorage.removeItem(STORAGE_ACCESS);
    sessionStorage.removeItem(STORAGE_REFRESH);
    localStorage.removeItem(STORAGE_ACCESS);
    localStorage.removeItem(STORAGE_REFRESH);
    const store = rememberMe ? localStorage : sessionStorage;
    store.setItem(STORAGE_ACCESS, accessToken);
    if (refreshToken) store.setItem(STORAGE_REFRESH, refreshToken);
  }

  function clearTokens() {
    sessionStorage.removeItem(STORAGE_ACCESS);
    sessionStorage.removeItem(STORAGE_REFRESH);
    sessionStorage.removeItem(IMPORT_ENTRY_KEY);
    localStorage.removeItem(STORAGE_ACCESS);
    localStorage.removeItem(STORAGE_REFRESH);
    localStorage.removeItem(STORAGE_REMEMBER);
  }

  function loginPageUrl() {
    if (location.protocol === 'file:') return 'login.html';
    return `${AUTH_BASE}/html/login`;
  }

  function redirectToLogin() {
    clearTokens();
    location.href = loginPageUrl();
  }

  let refreshPromise = null;

  async function refreshAccessToken() {
    if (refreshPromise) return refreshPromise;
    refreshPromise = (async () => {
      const rt = getRefreshToken();
      if (!rt) throw new Error('no refresh token');
      const res = await fetch(`${AUTH_BASE}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: rt }),
      });
      if (!res.ok) throw new Error('refresh failed');
      const json = await res.json();
      const data = json.data || json;
      const store = tokenStorage();
      store.setItem(STORAGE_ACCESS, data.access_token);
      return data.access_token;
    })();
    try {
      return await refreshPromise;
    } finally {
      refreshPromise = null;
    }
  }

  async function authFetch(url, options = {}) {
    const opts = { ...options };
    opts.headers = { ...(opts.headers || {}) };
    const token = getAccessToken();
    if (token) opts.headers['Authorization'] = `Bearer ${token}`;

    let res = await fetch(url, opts);
    if (res.status !== 401) return res;

    try {
      const newToken = await refreshAccessToken();
      opts.headers['Authorization'] = `Bearer ${newToken}`;
      res = await fetch(url, opts);
    } catch {
      redirectToLogin();
      throw new Error('登录已过期，请重新登录');
    }
    if (res.status === 401) redirectToLogin();
    return res;
  }

  async function login(username, password, rememberMe) {
    const res = await fetch(`${AUTH_BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password, remember_me: rememberMe }),
    });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail = json.detail || json.message;
      throw new Error(typeof detail === 'string' ? detail : (Array.isArray(detail) ? detail[0]?.msg : '登录失败') || '登录失败');
    }
    const data = json.data || json;
    saveTokens(data.access_token, data.refresh_token, rememberMe);
    return data.user;
  }

  async function logout() {
    const rt = getRefreshToken();
    try {
      await authFetch(`${AUTH_BASE}/auth/logout`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: rt || '' }),
      });
    } catch (_) { /* ignore */ }
    clearTokens();
    redirectToLogin();
  }

  async function fetchMe() {
    const res = await authFetch(`${AUTH_BASE}/auth/me`);
    if (!res.ok) throw new Error('未登录');
    const json = await res.json();
    return (json.data || json);
  }

  async function fetchRoles() {
    const res = await authFetch(`${AUTH_BASE}/auth/roles`);
    if (!res.ok) return [];
    const json = await res.json();
    return json.data || [];
  }

  async function requireAuth() {
    if (!getAccessToken()) {
      redirectToLogin();
      return null;
    }
    try {
      return await fetchMe();
    } catch {
      redirectToLogin();
      return null;
    }
  }

  function bindUserSidebar(user, opts = {}) {
    const nameEl = document.querySelector(opts.nameSelector || '.user-name');
    const roleEl = document.querySelector(opts.roleSelector || '.user-role');
    const avatarEl = document.querySelector(opts.avatarSelector || '.user-avatar');
    if (nameEl) nameEl.textContent = user.display_name || user.username;
    if (roleEl) {
      const labels = (user.roles || []).join(', ') || '普通用户';
      roleEl.textContent = labels;
    }
    if (avatarEl) {
      const ch = (user.display_name || user.username || '?').charAt(0).toUpperCase();
      avatarEl.textContent = ch;
    }
  }

  async function fetchSseToken() {
    const res = await authFetch(`${AUTH_BASE}/auth/sse-token`, { method: 'POST' });
    if (!res.ok) throw new Error('无法获取 SSE Token');
    const json = await res.json();
    const data = json.data || json;
    return data.sse_token;
  }

  global.RagAuth = {
    AUTH_BASE,
    getAccessToken,
    getImportApiBase,
    authFetch,
    fetchSseToken,
    login,
    logout,
    fetchMe,
    fetchRoles,
    requireAuth,
    bindUserSidebar,
    redirectToLogin,
    clearTokens,
    grantImportEntry,
    checkImportEntry,
    guardImportPage,
    navigateToImport,
    queryHomeUrl,
    importPageUrl,
  };
})(window);
