/* ============================================================
 * app.js —— 控制台应用
 * 视图：登录 / AI 问答工作台（M2-01）/ 知识维护与导入中心（M2-02）
 * 事件协议：docs/api-contract.md §0（step/delta/refs/done/final）
 * ============================================================ */
(function () {
  const { createApp, reactive, nextTick } = Vue;

  // 全局 toast 兜底（mounted 时替换为带 UI 的实现）；避免依赖可选链语法
  window.__cs = { toast: function () {} };

  /* ---------- Markdown 渲染 ---------- */
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

  /* ---------- 全局状态 ---------- */
  const state = reactive({
    view: "login",
    tab: "chat",
    loginForm: { username: "", password: "" },
    loginError: "",
    user: null,
    draft: "",
    busy: false,
    messages: [],
    kb: {
      units: [], kw: "", loading: false,
      importJobs: [], importing: false,
      edit: null, chunks: null,
      perm: null, permForm: null,
      depts: [], roles: [], users: [],
    },
  });
  window.consoleState = state;

  function hasBtn(key) {
    return ((state.user && state.user.buttons) || []).includes(key);
  }

  /* ---------- SSE / 聊天（M2-01） ---------- */
  let es = null;
  function currentAssistant() {
    const m = state.messages;
    return m.length && m[m.length - 1].role === "assistant" ? m[m.length - 1] : null;
  }
  function ensureSteps(msg) {
    if (!msg.steps) msg.steps = Object.keys(STEP_LABELS).map(k => ({ key: k, label: STEP_LABELS[k], status: "pending", detail: "" }));
    return msg.steps;
  }
  function applyStep(msg, key, status, detail) {
    const s = ensureSteps(msg).find(x => x.key === key);
    if (s) { s.status = status; if (detail) s.detail = detail; }
  }
  function startStream(sessionId, msg, onFinished) {
    return Api.sseToken().then(st => {
      es = new EventSource(`/stream/${sessionId}?token=${encodeURIComponent(st)}`);
      es.addEventListener("step", e => applyStep(msg, ...((d => [d.key, d.status, d.detail])(JSON.parse(e.data)))));
      es.addEventListener("delta", e => { msg.text += JSON.parse(e.data).delta; msg.streaming = true; });
      es.addEventListener("refs", e => {
        const d = JSON.parse(e.data);
        msg.refs = (d.refs || []).map(c => ({ title: c.title || c.name || "知识切片", score: c.score || null, text: c.content || "" }));
        msg.deniedCount = d.deniedCount || 0;
      });
      es.addEventListener("done", e => { msg.meta = JSON.parse(e.data); });
      es.addEventListener("final", e => {
        const d = JSON.parse(e.data);
        if (d.answer && !msg.text) msg.text = d.answer;
        if (d.citations && d.citations.length && !msg.refs) msg.refs = d.citations;
        msg.streaming = false;
        stopStream(); onFinished();
      });
      es.addEventListener("error", e => {
        let t = "服务异常";
        try { t = JSON.parse(e.data).error || t; } catch (_) {}
        if (!msg.text) msg.text = t;
        msg.streaming = false;
        stopStream(); onFinished();
      });
    });
  }
  function stopStream() { if (es) { es.close(); es = null; } }

  /* ---------- 知识中心（M2-02） ---------- */
  async function loadKnowledge() {
    const kb = state.kb;
    kb.loading = true;
    try {
      kb.units = await Api.request("GET", "/admin/knowledge" + (kb.kw ? "?kw=" + encodeURIComponent(kb.kw) : ""));
    } catch (e) { window.__cs.toast(e.message); }
    kb.loading = false;
  }
  async function openPerm(unit) {
    const kb = state.kb;
    const perms = await Api.request("GET", `/admin/knowledge/${unit.id}/permissions`);
    kb.depts = await Api.request("GET", "/admin/departments");
    kb.users = await Api.request("GET", "/admin/users");
    const roleData = await Api.request("GET", "/auth/roles");
    kb.roles = (roleData || []).map(r => ({ code: r.code || r.id, name: r.name }));
    const p = perms.perms || {};
    kb.perm = unit;
    kb.permForm = {
      global_: !!p.global,
      department_ids: [...(p.department_ids || [])],
      role_ids: [...(p.role_ids || [])],
      user_ids: [...(p.user_ids || [])],
    };
  }
  async function savePerm() {
    const kb = state.kb;
    await Api.request("PUT", `/admin/knowledge/${kb.perm.id}/permissions`, kb.permForm);
    window.__cs.toast("权限已保存并即时生效");
    kb.perm = null;
    await loadKnowledge();
  }
  function toggleIn(list, v) {
    const i = list.indexOf(v);
    i >= 0 ? list.splice(i, 1) : list.push(v);
  }
  async function importFiles(fileList) {
    const kb = state.kb;
    const ok = ["pdf", "md", "doc", "docx", "txt"];
    for (const f of fileList) {
      const ext = (f.name.split(".").pop() || "").toLowerCase();
      if (!ok.includes(ext)) { window.__cs.toast(`不支持的格式：${f.name}`); continue; }
      if (kb.importJobs.some(j => j.name === f.name && !j.done)) continue;
      kb.importJobs.push({ name: f.name, progress: 0, stage: "上传中…", done: false });
    }
    kb.importing = true;
    for (const job of kb.importJobs.filter(j => !j.done)) {
      try {
        job.stage = "上传中…";
        const fd = new FormData();
        fd.append("files", fileStore[job.name] || job.file);
        fd.append("allowed_roles", '["admin","common_user"]');
        const resp = await fetch("/admin/import/upload", {
          method: "POST",
          headers: { Authorization: "Bearer " + Api.token() },
          body: fd,
        });
        const json = await resp.json();
        if (!resp.ok) throw new Error(json.detail || "上传失败");
        job.taskId = json.task_ids[0];
        // 轮询导入状态（done_list/running_list 驱动进度）
        while (true) {
          const st = await Api.request("GET", `/admin/import/status/${job.taskId}`);
          const total = (st.done_list || []).length + (st.running_list || []).length;
          job.progress = total ? Math.round((st.done_list || []).length / total * 100) : (job.progress || 5);
          job.stage = (st.running_list || [])[0] || "处理中…";
          if (st.status === "completed") { job.progress = 100; job.stage = "入库完成"; job.done = true; break; }
          if (st.status === "failed") { job.stage = "失败"; throw new Error("导入失败"); }
          await new Promise(r => setTimeout(r, 2000));
        }
        window.__cs.toast(`《${job.name}》导入完成`);
      } catch (e) {
        job.stage = "失败：" + (e.message || e);
        job.done = true;
      }
    }
    kb.importing = false;
    await loadKnowledge();
  }
  const fileStore = {};

  /* ---------- 根组件 ---------- */
  const App = {
    data: () => ({ s: state }),
    computed: {
      draftProxy: {
        get() { return state.draft; },
        set(v) { state.draft = v; },
      },
      kbUnitsFiltered() {
        const kw = state.kb.kw.trim();
        if (!kw) return state.kb.units;
        return state.kb.units.filter(u => (u.title || "").includes(kw));
      },
    },
    methods: {
      mdRender,
      stepIcon: (s) => STEP_ICONS[s] || "○",
      hasBtn,
      go(tab) {
        if (tab === "knowledge") { state.tab = "knowledge"; loadKnowledge(); }
        else state.tab = tab;
      },
      async doLogin() {
        state.loginError = "";
        try {
          const d = await Api.login(state.loginForm.username, state.loginForm.password);
          Api.setToken(d.access_token);
          state.user = await Api.me();
          state.view = "console";
          state.tab = "chat";
        } catch (e) { state.loginError = e.message || "登录失败"; }
      },
      logout() { Api.clearToken(); state.view = "login"; state.user = null; state.messages = []; },

      /* 聊天 */
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

      /* 知识中心 */
      onImportFiles(e) {
        for (const f of e.target.files) fileStore[f.name] = f;
        this.importFiles(Array.from(e.target.files));
        e.target.value = "";
      },
      onDrop(e) {
        for (const f of e.dataTransfer.files) fileStore[f.name] = f;
        this.importFiles(Array.from(e.dataTransfer.files));
      },
      toggleEnabled(u) {
        Api.request("PUT", `/admin/knowledge/${u.id}`, { enabled: !u.enabled })
          .then(() => { u.enabled = !u.enabled; window.__cs.toast(u.enabled ? "已启用" : "已停用（检索不可命中）"); });
      },
      saveEdit() {
        const e = state.kb.edit;
        Api.request("PUT", `/admin/knowledge/${e.id}`, { title: e.title, category: e.category })
          .then(() => { state.kb.edit = null; window.__cs.toast("已保存"); loadKnowledge(); });
      },
      del(u) {
        if (!confirm(`确认删除《${u.title}》？将同步清理向量索引。`)) return;
        Api.request("DELETE", `/admin/knowledge/${u.id}`)
          .then(() => { window.__cs.toast("已删除"); loadKnowledge(); });
      },
      openChunks(u) {
        Api.request("GET", `/admin/knowledge/${u.id}/chunks`)
          .then(list => { state.kb.chunks = { title: u.title, list }; });
      },
      openPerm(u) {
        openPerm(u);
      },
      toggleArr(list, v) { toggleIn(list, v); },
      savePerm() { savePerm(); },
      fmtTime(iso) {
        if (!iso) return "—";
        const d = new Date(iso);
        return `${d.getMonth() + 1}-${d.getDate()} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
      },
    },
    mounted() {
      window.__cs.toast = (t) => { state.toastText = t; setTimeout(() => { state.toastText = ""; }, 2600); };
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
          <p class="muted" style="margin-top:10px">演示账号：admin/admin123 · zhangsan/zhang123 · zhaoliu/zhao123</p>
        </div>
      </div>

      <!-- 控制台 -->
      <div v-else class="shell">
        <aside class="sidenav">
          <div class="logo">📚 华智智库</div>
          <div class="logo-sub">RAG 知识库管理平台</div>
          <nav>
            <a :class="{on: s.tab === 'chat'}" @click="go('chat')">AI 问答工作台</a>
            <a v-if="((s.user && s.user.menus) || []).includes('knowledge')" :class="{on: s.tab === 'knowledge'}" @click="go('knowledge')">知识维护与导入</a>
            <a class="disabled" title="M3">沉淀与运营</a>
            <a class="disabled" title="M3">运营看板</a>
            <a class="disabled" title="后续迭代">组织与系统配置</a>
          </nav>
          <div class="side-foot">
            <div class="me">
              <div class="acc-avatar">{{ ((s.user && s.user.display_name) || '?')[0] }}</div>
              <div class="me-info">
                <div class="me-name">{{ s.user.display_name }}</div>
                <div class="me-sub">{{ ((s.user && s.user.roles) || []).join(' / ') }}</div>
              </div>
            </div>
            <a class="link danger" @click="logout">退出登录</a>
          </div>
        </aside>

        <!-- ===== AI 问答工作台 ===== -->
        <div v-if="s.tab === 'chat'" class="chat-main">
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
                  🔒 部分参考资料因权限受限无法展示（{{ m.deniedCount }} 个切片已按四维权限规则拦截）。
                </div>
                <div v-if="m.meta" class="msg-meta">
                  <span class="tag" :class="m.meta.source">{{ ({ 'rag': 'RAG 检索', 'semantic-cache': '语义缓存', 'faq-cache': 'FAQ 缓存', 'denied': '权限受限', 'no-result': '未命中' })[m.meta.source] || m.meta.source }}</span>
                  <span>耗时 {{ m.meta.latency }} ms</span>
                  <span v-if="m.meta.tokens">≈{{ m.meta.tokens }} tokens</span>
                </div>
              </div>
            </template>
          </div>
          <div class="composer">
            <div class="composer-row">
              <textarea v-model="draftProxy" rows="2" placeholder="输入业务问题，Enter 发送…" @keydown.enter.exact.prevent="send"></textarea>
              <button class="btn primary" :disabled="busy || !draft.trim()" @click="send">{{ busy ? '回答中…' : '发送' }}</button>
            </div>
          </div>
        </div>

        <!-- ===== 知识维护与导入中心 ===== -->
        <div v-else-if="s.tab === 'knowledge'" class="page">
          <div class="page-head">
            <h2>知识维护与导入中心</h2>
            <label v-if="hasBtn('import')" class="btn primary" style="cursor:pointer">
              ⬆ 导入文档（支持多选）
              <input type="file" multiple accept=".pdf,.md,.doc,.docx,.txt" hidden @change="onImportFiles" />
            </label>
          </div>
          <div class="toolbar">
            <input class="ipt" style="width:240px" v-model="s.kb.kw" placeholder="搜索知识标题…" @input="loadKnowledge" />
            <span class="muted">共 {{ kbUnitsFiltered.length }} 个知识单元</span>
          </div>
          <div class="card table-card">
            <table>
              <thead><tr><th>标题</th><th>格式</th><th>分类</th><th>权限标签</th><th>切片</th><th>启用</th><th>更新时间</th><th>操作</th></tr></thead>
              <tbody>
                <tr v-for="u in kbUnitsFiltered" :key="u.id">
                  <td class="strong">{{ u.title }}</td>
                  <td><span class="tag fmt">{{ (u.format || '').toUpperCase() }}</span></td>
                  <td>{{ u.category }}</td>
                  <td>
                    <span v-for="l in (u.permLabels || [])" :key="l" class="perm-tag">{{ l }}</span>
                  </td>
                  <td>{{ u.chunksCount }}</td>
                  <td><label class="switch"><input type="checkbox" :checked="u.enabled" @change="toggleEnabled(u)" /><i></i></label></td>
                  <td class="muted">{{ fmtTime(u.updatedAt) }}</td>
                  <td class="ops">
                    <a v-if="hasBtn('perm')" class="link" @click="openPerm(u)">权限</a>
                    <a v-if="hasBtn('edit')" class="link" @click="s.kb.edit = { id: u.id, title: u.title, category: u.category }">编辑</a>
                    <a class="link" @click="openChunks(u)">切片</a>
                    <a v-if="hasBtn('delete')" class="link danger" @click="del(u)">删除</a>
                  </td>
                </tr>
                <tr v-if="s.kb.loading"><td colspan="8" class="empty">加载中…</td></tr>
                <tr v-if="!s.kb.loading && !kbUnitsFiltered.length"><td colspan="8" class="empty">暂无知识单元，点击右上角「导入文档」开始</td></tr>
              </tbody>
            </table>
          </div>

          <!-- 导入任务进度 -->
          <div v-if="s.kb.importJobs.length" class="card" style="margin-top:14px">
            <h3>导入任务</h3>
            <div v-for="j in s.kb.importJobs" :key="j.name" class="job">
              <div class="job-head"><span class="job-name">{{ j.name }}</span><span class="muted">{{ j.progress }}%</span></div>
              <div class="bar"><div class="bar-in" :class="{ok: j.done}" :style="{width: j.progress + '%'}"></div></div>
              <div class="job-foot"><span>{{ j.stage }}</span></div>
            </div>
          </div>

          <!-- 编辑弹窗 -->
          <div v-if="s.kb.edit" class="modal-mask" @click.self="s.kb.edit = null">
            <div class="modal">
              <div class="modal-head"><h3>编辑知识单元</h3><a class="x" @click="s.kb.edit = null">✕</a></div>
              <div class="form-row"><label>标题</label><input class="ipt" v-model="s.kb.edit.title" /></div>
              <div class="form-row"><label>分类</label><input class="ipt" v-model="s.kb.edit.category" /></div>
              <div class="modal-foot">
                <button class="btn" @click="s.kb.edit = null">取消</button>
                <button class="btn primary" @click="saveEdit">保存</button>
              </div>
            </div>
          </div>

          <!-- 切片预览抽屉 -->
          <div v-if="s.kb.chunks" class="drawer-mask" @click.self="s.kb.chunks = null">
            <div class="drawer">
              <div class="drawer-head"><h3>切片预览 —《{{ s.kb.chunks.title }}》</h3><a class="x" @click="s.kb.chunks = null">✕</a></div>
              <div v-for="c in s.kb.chunks.list" :key="c.id" class="chunk-card">
                <div class="chunk-id mono">{{ c.title }} {{ c.lines }}</div>
                <div>{{ c.text }}</div>
              </div>
              <p v-if="!s.kb.chunks.list.length" class="empty">无切片</p>
            </div>
          </div>

          <!-- 四维权限弹窗 -->
          <div v-if="s.kb.perm" class="modal-mask" @click.self="s.kb.perm = null">
            <div class="modal perm-dialog">
              <div class="modal-head"><h3>四维数据权限 —《{{ s.kb.perm.title }}》</h3><a class="x" @click="s.kb.perm = null">✕</a></div>
              <p class="muted">OR 逻辑：满足任意一项即可访问；全部为空时默认拒绝。</p>
              <div class="perm-grid">
                <div class="perm-block span4">
                  <label class="switch-row">
                    <span class="perm-tag global">全局 global</span><span>全员公开访问</span>
                    <input type="checkbox" v-model="s.kb.permForm.global_" />
                  </label>
                </div>
                <div class="perm-block span2">
                  <h4><span class="perm-tag dept">部门 department</span></h4>
                  <label v-for="d in s.kb.depts" :key="d.id" class="check-row">
                    <input type="checkbox" :checked="s.kb.permForm.department_ids.includes(d.id)" @change="toggleArr(s.kb.permForm.department_ids, d.id)" /> {{ d.name }}
                  </label>
                </div>
                <div class="perm-block span2">
                  <h4><span class="perm-tag role">角色 role</span></h4>
                  <label v-for="r in s.kb.roles" :key="r.code" class="check-row">
                    <input type="checkbox" :value="r.code" v-model="s.kb.permForm.role_ids" /> {{ r.name }}
                  </label>
                </div>
                <div class="perm-block span4">
                  <h4><span class="perm-tag user">个人 user</span></h4>
                  <div v-for="g in groupUsers" :key="g.dept" class="ugroup">
                    <div class="ug-name">{{ g.dept || '未分配部门' }}</div>
                    <label v-for="u in g.users" :key="u.id" class="check-row inline">
                      <input type="checkbox" :checked="s.kb.permForm.user_ids.includes(u.id)" @change="toggleArr(s.kb.permForm.user_ids, u.id)" />
                      {{ u.name }} <span class="muted">({{ u.username }})</span>
                    </label>
                  </div>
                </div>
              </div>
              <div class="modal-foot">
                <button class="btn" @click="s.kb.perm = null">取消</button>
                <button class="btn primary" @click="savePerm">保存并生效</button>
              </div>
            </div>
          </div>
        </div>

        <!-- Toast -->
        <div class="toast-fixed" v-if="s.toastText">{{ s.toastText }}</div>
      </div>
    `,
    computed: {
      groupUsers() {
        const kb = state.kb;
        const groups = {};
        kb.users.forEach(u => {
          (groups[u.departmentId] = groups[u.departmentId] || []).push(u);
        });
        return Object.entries(groups).map(([dept, users]) => ({ dept, users }));
      },
    },
  };

  createApp(App).mount("#app");
})();
