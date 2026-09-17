/* ============================================================
 * app.js —— 控制台应用
 * 视图：登录 / AI 问答工作台（M2-01）/ 知识维护与导入中心（M2-02）
 * 事件协议：docs/api-contract.md §0（step/delta/refs/done/final）
 * ============================================================ */
(function () {
  const { createApp, reactive, nextTick } = Vue;

  // 全局 toast 兜底（mounted 时替换为带 UI 的实现）；不依赖可选链语法
  window.__cs = { toast: function () {} };

  /* ---------- Markdown 渲染 ---------- */
  function esc(s) { return (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }
  function inline(s) {
    return esc(s).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/`(.+?)`/g, "<code>$1</code>");
  }
  function mdRender(src) {
    const out = [];
    let listTag = "", inList = false;
    function closeList() { if (inList) { out.push("</" + listTag + ">"); inList = false; } }
    (src || "").split("\n").forEach(function (line) {
      var ul = line.match(/^\s*[-*]\s+(.*)/), ol = line.match(/^\s*\d+[.、]\s+(.*)/);
      if (ul) { if (!inList || listTag !== "ul") { closeList(); out.push("<ul>"); inList = true; listTag = "ul"; } out.push("<li>" + inline(ul[1]) + "</li>"); }
      else if (ol) { if (!inList || listTag !== "ol") { closeList(); out.push("<ol>"); inList = true; listTag = "ol"; } out.push("<li>" + inline(ol[1]) + "</li>"); }
      else if (/^>\s?/.test(line)) { closeList(); out.push("<blockquote>" + inline(line.replace(/^>\s?/, "")) + "</blockquote>"); }
      else if (/^#{1,4}\s/.test(line)) { closeList(); var lv = line.match(/^#+/)[0].length; out.push("<h" + (lv + 2) + ">" + inline(line.replace(/^#+\s*/, "")) + "</h" + (lv + 2) + ">"); }
      else if (line.trim() === "") { closeList(); }
      else { closeList(); out.push("<p>" + inline(line) + "</p>"); }
    });
    closeList();
    return out.join("");
  }

  var STEP_LABELS = {
    faq: "FAQ 缓存匹配", context: "多轮上下文处理", search: "混合检索（向量+关键词）",
    auth: "四维数据权限鉴权", compose: "提示词组装", generate: "大模型流式生成",
  };
  var STEP_ICONS = { pending: "○", running: "⟳", done: "✓", skipped: "—" };

  /* ---------- 全局状态 ---------- */
  var state = reactive({
    view: "login",
    tab: "chat",
    loginForm: { username: "", password: "" },
    loginError: "",
    user: null,
    draft: "",
    busy: false,
    toastText: "",
    messages: [],
    kb: {
      units: [], kw: "", loading: false,
      importJobs: [], importing: false,
      edit: null, chunks: null,
      perm: null, permForm: null,
      depts: [], roles: [], users: [],
    },
  });

  function hasBtn(key) {
    return ((state.user && state.user.buttons) || []).indexOf(key) >= 0;
  }

  /* ---------- SSE / 聊天 ---------- */
  var es = null;
  function ensureSteps(msg) {
    if (!msg.steps) {
      msg.steps = Object.keys(STEP_LABELS).map(function (k) {
        return { key: k, label: STEP_LABELS[k], status: "pending", detail: "" };
      });
    }
    return msg.steps;
  }
  function applyStep(msg, key, status, detail) {
    var arr = ensureSteps(msg);
    for (var i = 0; i < arr.length; i++) {
      if (arr[i].key === key) { arr[i].status = status; if (detail) arr[i].detail = detail; }
    }
  }
  function startStream(sessionId, msg, onFinished) {
    return Api.sseToken().then(function (st) {
      es = new EventSource("/stream/" + sessionId + "?token=" + encodeURIComponent(st));
      es.addEventListener("step", function (e) {
        var d = JSON.parse(e.data);
        applyStep(msg, d.key, d.status, d.detail);
      });
      es.addEventListener("delta", function (e) {
        msg.text += JSON.parse(e.data).delta;
        msg.streaming = true;
      });
      es.addEventListener("refs", function (e) {
        var d = JSON.parse(e.data);
        msg.refs = (d.refs || []).map(function (c) {
          return { title: c.title || c.name || "知识切片", score: c.score || null, text: c.content || c.text || "" };
        });
        msg.deniedCount = d.deniedCount || 0;
      });
      es.addEventListener("done", function (e) { msg.meta = JSON.parse(e.data); });
      es.addEventListener("final", function (e) {
        var d = JSON.parse(e.data);
        if (d.answer && !msg.text) msg.text = d.answer;
        if (d.citations && d.citations.length && !msg.refs) msg.refs = d.citations;
        msg.streaming = false;
        stopStream(); onFinished();
      });
      es.addEventListener("error", function (e) {
        var t = "服务异常";
        try { t = JSON.parse(e.data).error || t; } catch (_) {}
        if (!msg.text) msg.text = t;
        msg.streaming = false;
        stopStream(); onFinished();
      });
    });
  }
  function stopStream() { if (es) { es.close(); es = null; } }

  /* ---------- 知识中心 ---------- */
  function loadKnowledge() {
    var kb = state.kb;
    kb.loading = true;
    var qs = kb.kw ? "?kw=" + encodeURIComponent(kb.kw) : "";
    Api.request("GET", "/admin/knowledge" + qs)
      .then(function (units) { kb.units = units || []; })
      .catch(function (e) { window.__cs.toast(e.message); })
      .then(function () { kb.loading = false; });
  }
  function openPerm(unit) {
    var kb = state.kb;
    Api.request("GET", "/admin/knowledge/" + unit.id + "/permissions").then(function (perms) {
      var p = perms.perms || {};
      kb.perm = unit;
      kb.permForm = {
        global_: !!p.global,
        department_ids: (p.department_ids || []).slice(),
        role_ids: (p.role_ids || []).slice(),
        user_ids: (p.user_ids || []).slice(),
      };
      Api.request("GET", "/admin/departments").then(function (d) { kb.depts = d || []; });
      Api.request("GET", "/admin/users").then(function (u) { kb.users = u || []; });
      Api.request("GET", "/auth/roles").then(function (r) {
        kb.roles = (r || []).map(function (x) { return { code: x.code || x.id, name: x.name }; });
      });
    });
  }
  function savePermCurrent() {
    var kb = state.kb;
    Api.request("PUT", "/admin/knowledge/" + kb.perm.id + "/permissions", kb.permForm)
      .then(function () {
        window.__cs.toast("权限已保存并即时生效");
        kb.perm = null;
        loadKnowledge();
      });
  }
  function toggleIn(list, v) {
    var i = list.indexOf(v);
    if (i >= 0) list.splice(i, 1); else list.push(v);
  }
  function importOne(job) {
    var kb = state.kb;
    job.stage = "上传中…";
    var fd = new FormData();
    fd.append("files", fileStore[job.name]);
    fd.append("allowed_roles", '["admin","common_user"]');
    return fetch("/admin/import/upload", {
      method: "POST",
      headers: { Authorization: "Bearer " + Api.token() },
      body: fd,
    }).then(function (resp) {
      return resp.json().then(function (json) {
        if (!resp.ok) throw new Error(json.detail || "上传失败");
        job.taskId = json.task_ids[0];
        function poll() {
          return Api.request("GET", "/admin/import/status/" + job.taskId).then(function (st) {
            var total = (st.done_list || []).length + (st.running_list || []).length;
            job.progress = total ? Math.round((st.done_list || []).length / total * 100) : 5;
            job.stage = (st.running_list || [])[0] || "处理中…";
            if (st.status === "completed") { job.progress = 100; job.stage = "入库完成"; job.done = true; return; }
            if (st.status === "failed") { job.stage = "失败"; throw new Error("导入失败"); }
            return new Promise(function (r) { setTimeout(poll, 2000); });
          });
        }
        return poll();
      });
    });
  }
  var fileStore = {};
  function importFiles(files) {
    var kb = state.kb;
    var ok = ["pdf", "md", "doc", "docx", "txt"];
    var queue = [];
    Array.from(files).forEach(function (f) {
      var ext = (f.name.split(".").pop() || "").toLowerCase();
      if (ok.indexOf(ext) < 0) { window.__cs.toast("不支持的格式：" + f.name); return; }
      fileStore[f.name] = f;
      kb.importJobs.push({ name: f.name, progress: 0, stage: "排队中…", done: false });
      queue.push(f.name);
    });
    kb.importing = true;
    var chain = Promise.resolve();
    queue.forEach(function (name) {
      var job = null;
      for (var i = kb.importJobs.length - 1; i >= 0; i--) if (kb.importJobs[i].name === name) { job = kb.importJobs[i]; break; }
      chain = chain.then(function () { return importOne(job); })
        .then(function () { window.__cs.toast("《" + name + "》导入完成"); })
        .catch(function (e) { job.stage = "失败：" + (e.message || e); });
    });
    chain.then(function () {
      kb.importing = false;
      loadKnowledge();
    });
  }

  /* ---------- 根组件 ---------- */
  var App = {
    data: function () { return { s: state, draft: "" }; },
    computed: {
      draftProxy: {
        get: function () { return state.draft; },
        set: function (v) { state.draft = v; },
      },
      kbUnitsFiltered: function () {
        var kw = state.kb.kw.trim();
        if (!kw) return state.kb.units;
        return state.kb.units.filter(function (u) { return (u.title || "").indexOf(kw) >= 0; });
      },
      groupUsers: function () {
        var groups = {};
        state.kb.users.forEach(function (u) {
          (groups[u.departmentId] = groups[u.departmentId] || []).push(u);
        });
        return Object.keys(groups).map(function (dept) {
          return { dept: dept, users: groups[dept] };
        });
      },
    },
    methods: {
      mdRender: mdRender,
      stepIcon: function (s) { return STEP_ICONS[s] || "○"; },
      hasBtn: hasBtn,
      hasMenu: hasMenu,
      go: function (tab) {
        state.tab = tab;
        if (tab === "knowledge") loadKnowledge();
      },
      doLogin: function () {
        state.loginError = "";
        Api.login(state.loginForm.username, state.loginForm.password).then(function (d) {
          Api.setToken(d.access_token);
          Api.me().then(function (u) {
            state.user = u;
            state.view = "console";
            state.tab = "chat";
          });
        }).catch(function (e) { state.loginError = e.message || "登录失败"; });
      },
      logout: function () {
        Api.clearToken();
        state.view = "login";
        state.user = null;
        state.messages = [];
      },
      send: function () {
        var q = state.draft.trim();
        if (!q || state.busy) return;
        state.messages.push({ role: "user", text: q });
        state.draft = "";
        state.busy = true;
        var msg = reactive({ role: "assistant", text: "", steps: null, refs: null, deniedCount: 0, meta: null, streaming: false });
        state.messages.push(msg);
        nextTick(); this.scrollBottom();
        var sessionId = (window.crypto && window.crypto.randomUUID) ? window.crypto.randomUUID() : "s-" + Date.now();
        var self = this;
        startStream(sessionId, msg, function () { state.busy = false; self.scrollBottom(); })
          .then(function () { return Api.queryStream(q, sessionId); })
          .catch(function (e) {
            msg.text = "请求失败：" + (e.message || e);
            msg.streaming = false;
            state.busy = false;
          });
        this.scrollBottom();
      },
      scrollBottom: function () {
        nextTick(function () {
          var el = document.querySelector(".msgs");
          if (el) el.scrollTop = el.scrollHeight;
        });
      },
      onImportFiles: function (e) {
        importFiles(e.target.files);
        e.target.value = "";
      },
      toggleEnabled: function (u) {
        Api.request("PUT", "/admin/knowledge/" + u.id, { enabled: !u.enabled }).then(function () {
          u.enabled = !u.enabled;
          window.__cs.toast(u.enabled ? "已启用" : "已停用（检索不可命中）");
        });
      },
      saveEdit: function () {
        var e = state.kb.edit;
        Api.request("PUT", "/admin/knowledge/" + e.id, { title: e.title, category: e.category })
          .then(function () { state.kb.edit = null; window.__cs.toast("已保存"); loadKnowledge(); });
      },
      del: function (u) {
        if (!confirm("确认删除《" + u.title + "》？将同步清理向量索引。")) return;
        Api.request("DELETE", "/admin/knowledge/" + u.id)
          .then(function () { window.__cs.toast("已删除"); loadKnowledge(); });
      },
      openChunks: function (u) {
        Api.request("GET", "/admin/knowledge/" + u.id + "/chunks")
          .then(function (list) { state.kb.chunks = { title: u.title, list: list || [] }; });
      },
      openPerm: function (u) { openPerm(u); },
      toggleArr: function (list, v) { toggleIn(list, v); },
      savePerm: function () { savePermCurrent(); },
      fmtTime: function (iso) {
        if (!iso) return "—";
        var d = new Date(iso);
        return (d.getMonth() + 1) + "-" + d.getDate() + " " +
          String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0");
      },
    },
    mounted: function () {
      window.__cs.toast = function (t) {
        state.toastText = t;
        setTimeout(function () { state.toastText = ""; }, 2600);
      };
      if (Api.token()) {
        var self = this;
        Api.me().then(function (u) {
          state.user = u;
          state.view = "console";
        }).catch(function () { Api.clearToken(); });
      }
    },
    template: `
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

      <div v-else class="shell">
        <aside class="sidenav">
          <div class="logo">📚 华智智库</div>
          <div class="logo-sub">RAG 知识库管理平台</div>
          <nav>
            <a :class="{on: s.tab === 'chat'}" @click="go('chat')">AI 问答工作台</a>
            <a v-if="hasMenu('knowledge')" :class="{on: s.tab === 'knowledge'}" @click="go('knowledge')">知识维护与导入</a>
            <a class="disabled" title="M3">沉淀与运营</a>
            <a class="disabled" title="M3">运营看板</a>
            <a class="disabled" title="后续迭代">组织与系统配置</a>
          </nav>
          <div class="side-foot">
            <div class="me">
              <div class="acc-avatar">{{ (s.user.display_name || '?')[0] }}</div>
              <div class="me-info">
                <div class="me-name">{{ s.user.display_name }}</div>
                <div class="me-sub">{{ (s.user.roles || []).join(' / ') }}</div>
              </div>
            </div>
            <a class="link danger" @click="logout">退出登录</a>
          </div>
        </aside>

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
                  <td><span v-for="l in (u.permLabels || [])" :key="l" class="perm-tag">{{ l }}</span></td>
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

          <div v-if="s.kb.importJobs.length" class="card" style="margin-top:14px">
            <h3>导入任务</h3>
            <div v-for="j in s.kb.importJobs" :key="j.name" class="job">
              <div class="job-head"><span class="job-name">{{ j.name }}</span><span class="muted">{{ j.progress }}%</span></div>
              <div class="bar"><div class="bar-in" :class="{ok: j.done}" :style="{width: j.progress + '%'}"></div></div>
              <div class="job-foot"><span>{{ j.stage }}</span></div>
            </div>
          </div>

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
                    <input type="checkbox" :checked="s.kb.permForm.department_ids.indexOf(d.id) >= 0" @change="toggleArr(s.kb.permForm.department_ids, d.id)" /> {{ d.name }}
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
                      <input type="checkbox" :checked="s.kb.permForm.user_ids.indexOf(u.id) >= 0" @change="toggleArr(s.kb.permForm.user_ids, u.id)" />
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

        <div class="toast-fixed" v-if="s.toastText">{{ s.toastText }}</div>
      </div>
    `,
  };

  var app = createApp(App);
  // 渲染错误直接上屏（Vue 自行捕获渲染异常，window error 事件收不到）
  app.config.errorHandler = function (err, _vm, info) {
    var el = document.createElement("pre");
    el.style.cssText = "position:fixed;top:0;left:0;right:0;z-index:99999;background:#7f1d1d;color:#fff;padding:10px;font-size:12px;white-space:pre-wrap;";
    el.textContent = "[Vue 渲染错误] " + ((err && err.message) || err) + "\n阶段: " + info;
    document.body.appendChild(el);
    if (window.console && console.error) console.error("[Vue errorHandler]", err, info);
  };
  app.mount("#app");

  function hasMenu(key) {
    return ((state.user && state.user.menus) || []).indexOf(key) >= 0;
  }
})();
