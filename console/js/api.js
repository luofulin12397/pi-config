/* ============================================================
 * api.js —— 控制台 API 客户端（同源部署：/console + API 同在 :55001）
 * ============================================================ */
(function () {
  const TOKEN_KEY = "console_access_token";

  const Api = {
    token() { return localStorage.getItem(TOKEN_KEY) || ""; },
    setToken(t) { localStorage.setItem(TOKEN_KEY, t); },
    clearToken() { localStorage.removeItem(TOKEN_KEY); },

    async request(method, path, body) {
      const headers = { "Content-Type": "application/json" };
      const t = this.token();
      if (t) headers["Authorization"] = "Bearer " + t;
      const resp = await fetch(path, {
        method, headers,
        body: body ? JSON.stringify(body) : undefined,
      });
      if (resp.status === 401) { this.clearToken(); throw new Error("未登录或登录已过期"); }
      const json = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(json.detail || json.message || ("HTTP " + resp.status));
      return json.data !== undefined ? json.data : json;
    },

    login(username, password) {
      return this.request("POST", "/auth/login", { username, password });
    },
    me() { return this.request("GET", "/auth/me"); },
    async sseToken() {
      // SSE EventSource 无法带 Header，换取短效 sse token 走 query 参数
      const d = await this.request("POST", "/auth/sse-token", {});
      return d.sse_token || d.token || d.access_token || d;
    },

    /* 发起流式问答（受理后事件经 /stream/{sid} 推送） */
    async queryStream(query, sessionId) {
      const st = await this.sseToken();
      return this.request("POST", "/query", { query, is_stream: true, session_id: sessionId, top_k: 4 })
        .then(() => st);
    },
  };

  window.Api = Api;
})();
