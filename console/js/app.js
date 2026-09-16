/* ============================================================
 * app.js —— 控制台应用（登录 + AI 问答工作台）
 * 事件协议：docs/api-contract.md §0（step/delta/refs/done/final）
 * ============================================================ */
(function () {
  const { createApp, reactive, nextTick } = Vue;

  /* ---------- 迷你 Markdown 渲染（与需求答复格式匹配） ---------- */
  function esc(s) { return (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }
  function inline(s) {
    return esc(s).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/`(.+?)`/g, "<code>$1</code>");
  }
  function mdRender(src) {
    const out = [];
    let listTag = "", inList = false;
    const closeList = () => { if (inList) { out.push("</" + listTag + ">"); inList = false; } };
    (src || "").split("\n").forEach(line => {
      const ul = line.match(/^\s*[-*]\s+(.*)/), ol = line.match(/^\s*\d+[.、]\s+(.*)/);
      if (ul) { if (!inList || listTag !== "ul") { closeList(); out.push("<ul>"); inList = "ul"; listTag = "ul"; } out.push("<li>" + inline(ul[1]) + "</li>"); }
      else if (ol) { if (!inList || listTag !== "ol") { closeList(); out.push("<ol>"); inList = "ol"; listTag = "ol"; } out.push("<li>" + inline(ol[1]) + "</li>"); }
      else if (/^>\s?/.test(line)) { closeList(); out.push("<blockquote>" + inline(line.replace(/^>\s?/, "")) + "</blockquote>"); }
      else if (/^#{1,4}\s/.test(line)) { closeList(); const lv = line.match(/^#+/)[0].length; out.push("<h" + (lv + 2) + ">" + inline(line.replace(/^#+\s*/, "")) + "</h" + (lv + 2) + ">"); }
      else if (line.trim() === "") { closeList(); }
      else { closeList(); out.push("<p>" + inline(line) + "</p>"); }
    });
    closeList();
    return out.join("");
  }

  const STEP_LABELS = {
    faq: "FAQ 缓存匹配", context: "多轮上下文处理", search: "混合检索（向量+关键词）",
    auth: "四维数据权限鉴权", compose: "提示词组装", generate: "大模型流式生成",
  };
  const STEP_ICONS = { pending: "○", running: "⟳", done: "✓", skipped: "—" };

  const state = reactive({
    view: "login",
    loginForm: { username: "", password: "" },
    loginError: "",
    user: null,
    draft: "",
    busy: false,
    messages: [],           // {role:'user'|'assistant', text, steps:[{key,label,status,detail}], refs, deniedCount, meta, streaming}
  });
  window.consoleState = state;

  function currentAssistant() {
    const m = state.messages;
    return m.length && m[m.length - 1].role === "assistant" ? m[m.length - 1] : null;
  }
  function ensureSteps(msg) {
    if (!msg.steps) msg.steps = Object.keys(STEP_LABELS).map(k => ({ key: k, label: STEP_LABELS[k], status: "pending", detail: "" }));
    return msg.steps;
  }
  function applyStep(msg, key, status, detail) {
    const steps = ensureSteps(msg);
    const s = steps.find(x => x.key === key);
    if (s) { s.status = status; if (detail) s.detail = detail; }
  }

  /* ---------- SSE 消费 ---------- */
  let es = null;
  function startStream(sessionId, assistantMsg, onFinished) {
    return Api.sseToken().then(st => {
      es = new EventSource(`/stream/${sessionId}?token=${encodeURIComponent(st)}`);
      es.addEventListener("step", e => {
        const d = JSON.parse(e.data);
        applyStep(assistantMsg, d.key, d.status, d.detail);
      });
      es.addEventListener("delta", e => {
        assistantMsg.text += JSON.parse(e.data).delta;
        assistantMsg.streaming = true;
      });
      es.addEventListener("refs", e => {
        const d = JSON.parse(e.data);
        assistantMsg.refs = (d.refs || []).map(c => ({
          title: c.title || c.file_title || "知识切片",
          score: c.score || (c.relevance_score != null ? c.relevance_score : null),
          text: c.content || c.text || c.snippet || "",
        }));
        assistantMsg.deniedCount = d.deniedCount || 0;
      });
      es.addEventListener("done", e => {
        const d = JSON.parse(e.data);
        assistantMsg.meta = { source: d.source, latency: d.latency, tokens: d.tokens };
      });
      es.addEventListener("final", e => {
        const d = JSON.parse(e.data);
        if (d.answer && !assistantMsg.text) assistantMsg.text = d.answer;
        if (d.citations && d.citations.length && !assistantMsg.refs) {
          assistantMsg.refs = d.citations;
          assistantMsg.deniedCount = assistantMsg.deniedCount || 0;
        }
        assistantMsg.streaming = false;
        stopStream();
        onFinished();
      });
      es.addEventListener("error", e => {
        let msgText = "服务异常";
        try { msgText = JSON.parse(e.data).error || msgText; } catch (_) {}
        if (!assistantMsg.text) assistantMsg.text = msgText;
        assistantMsg.streaming = false;
        stopStream();
        onFinished();
      });
    });
  }
  function stopStream() { if (es) { es.close(); es = null; } }

  /* ---------- 根组件 ---------- */
  const App = {
    data: () => ({ s: state, draft: "" }),
    computed: {
      busy() { return state.busy; },
      draftProxy: {
        get() { return state.draft; },
        set(v) { state.draft = v; },
      },
    },
    methods: {
      mdRender,
      stepIcon: (s) => STEP_ICONS[s] || "○",
      async doLogin() {
        state.loginError = "";
        try {
          const d = await Api.login(state.loginForm.username, state.loginForm.password);
          Api.setToken(d.access_token);
          state.user = await Api.me();
          state.view = "console";
        } catch (e) { state.loginError = e.message || "登录失败"; }
      },
      logout() { Api.clearToken(); state.view = "login"; state.user = null; state.messages = []; },
      async send() {
        const q = state.draft.trim();
        if (!q || state.busy) return;
        state.messages.push({ role: "user", text: q });
        state.draft = "";
        state.busy = true;
        const msg = reactive({ role: "assistant", text: "", steps: null, refs: null, deniedCount: 0, meta: null, streaming: false });
        state.messages.push(msg);
        await nextTick(); this.scrollBottom();

        const sessionId = crypto.randomUUID ? crypto.randomUUID() : "s-" + Date.now();
        try {
          await startStream(sessionId, msg, () => { state.busy = false; this.scrollBottom(); });
          await Api.queryStream(q, sessionId);
        } catch (e) {
          msg.text = "请求失败：" + (e.message || e);
          msg.streaming = false;
          state.busy = false;
        }
        this.scrollBottom();
      },
      scrollBottom() {
        nextTick(() => { const el = this.$refs.msgs; if (el) el.scrollTop = el.scrollHeight; });
      },
    },
    mounted() {
      // 已有 token 则直接进入控制台
      if (Api.token()) {
        Api.me().then(u => { state.user = u; state.view = "console"; }).catch(() => Api.clearToken());
      }
    },
    template: `
      <!-- 登录 -->
      <div v-if="s.view === 'login'" class="login-page">
        <div class="login-hero">
          <div class="login-logo">📚</div>
          <h1>华智智库 · RAG 知识库管理平台</h1>
          <p>多源知识维护 · 四维数据权限鉴权 · AI 鉴权检索问答 · 知识自动沉淀</p>
        </div>
        <div class="login-card">
          <h3>登录控制台</h3>
          <div class="form-row"><label>账号</label><input class="ipt" v-model="s.loginForm.username" placeholder="admin / zhangsan / zhaoliu" @keydown.enter="doLogin" /></div>
          <div class="form-row"><label>密码</label><input class="ipt" type="password" v-model="s.loginForm.password" @keydown.enter="doLogin" /></div>
          <p class="login-err" v-if="s.loginError">{{ s.loginError }}</p>
          <button class="btn primary block" @click="doLogin">登 录</button>
          <p class="muted" style="margin-top:10px">演示账号：admin/admin123 · zhangsan/zhang123（业务部）· zhaoliu/zhao123（管理层）</p>
        </div>
      </div>

      <!-- 控制台 -->
      <div v-else class="shell">
        <aside class="sidenav">
          <div class="logo">📚 华智智库</div>
          <div class="logo-sub">AI 鉴权问答工作台</div>
          <nav>
            <a class="on">AI 问答工作台</a>
            <a class="disabled" title="M2 后续迭代">知识维护与导入</a>
            <a class="disabled" title="M3">沉淀与运营</a>
            <a class="disabled" title="M3">运营看板</a>
            <a class="disabled" title="M2 后续迭代">组织与系统配置</a>
          </nav>
          <div class="side-foot">
            <div class="me">
              <div class="acc-avatar">{{ s.user.display_name[0] }}</div>
              <div class="me-info">
                <div class="me-name">{{ s.user.display_name }}</div>
                <div class="me-sub">{{ (s.user.roles || []).join(' / ') }}</div>
              </div>
            </div>
            <a class="link danger" @click="logout">退出登录</a>
          </div>
        </aside>
        <div class="chat-main">
          <div class="msgs" ref="msgs">
            <div v-if="s.messages.length === 0" class="chat-welcome">
              <h2>👋 你好，{{ s.user.display_name }}</h2>
              <p>回答基于你有权限访问的知识库内容；<br>无权限资料会被自动过滤并明确提示，不会越权泄露。</p>
            </div>
            <template v-for="(m, i) in s.messages" :key="i">
              <div v-if="m.role === 'user'" class="msg-user"><div class="bubble-user">{{ m.text }}</div></div>
              <div v-else class="msg-ai">
                <div v-if="m.steps" class="pipeline">
                  <div v-for="st in m.steps" :key="st.key" class="pstep" :class="st.status">
                    <span class="ps-icon">{{ stepIcon(st.status) }}</span>
                    <span class="ps-label">{{ st.label }}</span>
                    <span class="ps-detail" v-if="st.detail">{{ st.detail }}</span>
                  </div>
                </div>
                <div class="md" v-html="mdRender(m.text)"></div>
                <span v-if="m.streaming" class="cursor">▌</span>
                <div v-if="m.refs && m.refs.length" class="refs">
                  <div class="refs-title">📖 知识引用溯源</div>
                  <div v-for="(r, ri) in m.refs" :key="ri" class="ref-card">
                    <div class="ref-head">
                      <span class="ref-title">《{{ r.title }}》</span>
                      <span class="ref-score" v-if="r.score">相关度 {{ Math.round(r.score * 100) }}%</span>
                    </div>
                    <div class="ref-text" v-if="r.text">{{ r.text }}</div>
                  </div>
                </div>
                <div v-if="m.deniedCount > 0" class="denied-card">
                  🔒 部分参考资料因权限受限无法展示（{{ m.deniedCount }} 个切片已按四维权限规则拦截）。如需访问，请联系知识管理员申请权限。
                </div>
                <div v-if="m.meta" class="msg-meta">
                  <span class="tag" :class="m.meta.source">{{ { 'rag': 'RAG 检索', 'semantic-cache': '语义缓存', 'faq-cache': 'FAQ 缓存', 'denied': '权限受限', 'no-result': '未命中' }[m.meta.source] || m.meta.source }}</span>
                  <span>耗时 {{ m.meta.latency }} ms</span>
                  <span v-if="m.meta.tokens">≈{{ m.meta.tokens }} tokens</span>
                </div>
              </div>
            </template>
          </div>
          <div class="composer">
            <div class="composer-row">
              <textarea v-model="draftProxy" rows="2" placeholder="输入业务问题，Enter 发送（回答基于你有权限的知识库内容）…" @keydown.enter.exact.prevent="send"></textarea>
              <button class="btn primary" :disabled="busy || !draft.trim()" @click="send">{{ busy ? '回答中…' : '发送' }}</button>
            </div>
          </div>
        </div>
      </div>
    `,
  };

  createApp(App).mount("#app");
})();
