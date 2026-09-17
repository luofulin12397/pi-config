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
    sessionId: null,
    sessions: [],
    org: {
      users: [], roles: [], loading: false,
      userEdit: null, roleEdit: null, roleCode: "common_user",
    },
    ops: {
      tab: "candidates", loading: false,
      audit: [], candidates: [], published: [], gaps: [],
      addForm: null,
      convertForm: null,
    },
    dash: { loading: false, data: null },
    kb: {
      units: [], kw: "", loading: false,
      importJobs: [], importing: false,
      edit: null, chunks: null,
      perm: null, permForm: null,
      depts: [], roles: [], users: [],
    },
  });

  window.consoleState = state;   // 调试钩子（控制台可查状态）

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
        var STAGE_OF_NODE = {
          upload_file: "文本清洗", node_pdf_to_md: "文本清洗", node_md_img: "文本清洗",
          node_document_split: "智能分块", node_item_name_recognition: "智能分块",
          node_bge_embedding: "语义向量化",
          node_import_milvus: "索引入库",
        };
        var STAGE_ORDER = ["文本清洗", "智能分块", "语义向量化", "索引入库"];
        function poll() {
          return Api.request("GET", "/admin/import/status/" + job.taskId).then(function (st) {
            var done = st.done_list || [], running = st.running_list || [];
            var total = done.length + running.length;
            var currentStage = STAGE_OF_NODE[running[0]] || (st.status === "completed" ? "索引入库" : "文本清洗");
            job.progress = total ? Math.min(99, Math.round(done.length / total * 100)) : 5;
            job.stage = "当前阶段：" + currentStage;
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

  /* ---------- 会话历史（M2-03） ---------- */
  function loadSessions() {
    Api.request("GET", "/history?limit=200").then(function (d) {
      var items = (d && d.items) || [];
      var by = {};
      items.forEach(function (it) {
        if (!it.session_id) return;
        var g = by[it.session_id] = by[it.session_id] || { id: it.session_id, msgs: [] };
        g.msgs.push(it);
      });
      state.sessions = Object.keys(by).map(function (k) {
        var g = by[k];
        g.msgs.sort(function (a, b) { return (a.id || 0) - (b.id || 0); });
        var firstUser = null;
        for (var i = 0; i < g.msgs.length; i++) if (g.msgs[i].role === "user") { firstUser = g.msgs[i]; break; }
        return {
          id: k,
          title: ((firstUser && firstUser.text) || g.msgs[0].text || "会话").slice(0, 14),
          count: g.msgs.length,
          messages: g.msgs.map(function (m) {
            return { role: m.role === "user" ? "user" : "assistant", text: m.text || "" };
          }),
        };
      }).sort(function (a, b) { return b.count - a.count; });
    }).catch(function () {});
  }

  /* ---------- 组织与系统配置（M2-04） ---------- */
  var MENU_DEFS = [
    { key: "chat", label: "AI 问答工作台", buttons: [{ key: "ask", label: "发起提问" }] },
    { key: "knowledge", label: "知识维护与导入", buttons: [{ key: "import", label: "文档导入" }, { key: "edit", label: "编辑知识" }, { key: "delete", label: "删除知识" }, { key: "perm", label: "权限配置" }] },
    { key: "ops", label: "沉淀与运营", buttons: [{ key: "faq-publish", label: "FAQ 审核发布" }, { key: "cache-toggle", label: "缓存开关控制" }, { key: "gap-task", label: "缺口转建任务" }] },
    { key: "dashboard", label: "运营看板", buttons: [] },
    { key: "org", label: "组织与系统配置", buttons: [{ key: "user-manage", label: "用户管理" }, { key: "role-manage", label: "角色授权" }] },
  ];

  function loadOrg() {
    state.org.loading = true;
    Promise.all([
      Api.request("GET", "/admin/users"),
      Api.request("GET", "/auth/roles"),
    ]).then(function (r) {
      state.org.users = r[0] || [];
      state.org.roles = (r[1] || []).map(function (x) { return { code: x.code || x.id, name: x.name }; });
    }).catch(function (e) { window.__cs.toast(e.message); })
      .then(function () { state.org.loading = false; });
  }

  /* ---------- 根组件 ---------- */
  var App = {
    data: function () { return { s: state, draft: "", menuDefs: MENU_DEFS }; },
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
        if (tab === "ops") this.loadOps();
        if (tab === "dashboard") this.loadDashboard();
        if (tab === "org") loadOrg();
      },
      doLogin: function () {
        state.loginError = "";
        Api.login(state.loginForm.username, state.loginForm.password).then(function (d) {
          Api.setToken(d.access_token);
          Api.me().then(function (u) {
            state.user = u;
            state.view = "console";
            state.tab = "chat";
            loadSessions();
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
        var sessionId = state.sessionId || ((window.crypto && window.crypto.randomUUID) ? window.crypto.randomUUID() : "s-" + Date.now());
        state.sessionId = sessionId;
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
      newSession: function () {
        state.sessionId = null;
        state.messages = [];
        state.busy = false;
      },
      openSession: function (sess) {
        state.sessionId = sess.id;
        state.messages = sess.messages.map(function (m) {
          return reactive({ role: m.role, text: m.text, steps: null, refs: null, deniedCount: 0, meta: null, streaming: false });
        });
        state.busy = false;
      },
      loadSessionsWrap: function () { loadSessions(); },
      loadOrg: function () { loadOrg(); },
      startEditUser: function (u) {
        state.org.userEdit = {
          id: u.id, username: u.username, display_name: u.name,
          department_id: u.departmentId, role_codes: (u.roleCodes || []).slice(),
          enabled: u.enabled, password: "",
        };
      },
      startNewUser: function () {
        state.org.userEdit = { id: null, username: "", display_name: "", department_id: "", role_codes: ["common_user"], enabled: true, password: "" };
      },
      saveUser: function () {
        var f = state.org.userEdit;
        var p = f.id
          ? Api.request("PUT", "/admin/users/" + f.id, {
              display_name: f.display_name, department_id: f.department_id,
              enabled: f.enabled, role_codes: f.role_codes,
              password: f.password || undefined,
            })
          : Api.request("POST", "/admin/users", {
              username: f.username, password: f.password, display_name: f.display_name,
              department_id: f.department_id, enabled: f.enabled, role_codes: f.role_codes,
            });
        p.then(function () {
          state.org.userEdit = null;
          window.__cs.toast("已保存");
          loadOrg();
        }).catch(function (e) { window.__cs.toast(e.message); });
      },
      toggleUserEnabled: function (u) {
        Api.request("PUT", "/admin/users/" + u.id, { enabled: !u.enabled })
          .then(function () { u.enabled = !u.enabled; window.__cs.toast(u.enabled ? "已启用" : "已禁用"); }).catch(function (e) { window.__cs.toast(e.message || "操作失败"); });
      },
      resetPwd: function (u) {
        var p = prompt("为「" + u.name + "」设置新密码：");
        if (!p) return;
        Api.request("PUT", "/admin/users/" + u.id, { password: p })
          .then(function () { window.__cs.toast("密码已重置"); }).catch(function (e) { window.__cs.toast(e.message || "操作失败"); });
      },
      delUser: function (u) {
        if (!confirm("确认删除用户「" + u.name + "」？")) return;
        Api.request("DELETE", "/admin/users/" + u.id)
          .then(function () { window.__cs.toast("已删除"); loadOrg(); });
      },
      startRoleEdit: function (code) {
        state.org.roleCode = code;
        var role = null;
        state.org.roles.forEach(function (r) { if (r.code === code) role = r; });
        var perms = { menus: [], buttons: [] };
        Api.request("GET", "/admin/roles/" + code + "/perms").then(function (d) {
          perms = d;
        }).catch(function () {}).then(function () {
          state.org.roleEdit = { code: code, menus: (perms.menus || []).slice(), buttons: (perms.buttons || []).slice() };
        });
      },
      toggleRoleMenu: function (key) {
        var f = state.org.roleEdit;
        var i = f.menus.indexOf(key);
        if (i >= 0) f.menus.splice(i, 1); else f.menus.push(key);
      },
      toggleRoleButton: function (key) {
        var f = state.org.roleEdit;
        var i = f.buttons.indexOf(key);
        if (i >= 0) f.buttons.splice(i, 1); else f.buttons.push(key);
      },
      saveRole: function () {
        var f = state.org.roleEdit;
        Api.request("PUT", "/admin/roles/" + f.code, { menus: f.menus, buttons: f.buttons })
          .then(function () { window.__cs.toast("角色权限已保存并即时生效"); }).catch(function (e) { window.__cs.toast(e.message || "操作失败"); });
      },
      onImportFiles: function (e) {
        importFiles(e.target.files);
        e.target.value = "";
      },
      onDrop: function (e) {
        if (e.dataTransfer && e.dataTransfer.files.length) importFiles(e.dataTransfer.files);
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
          .then(function () { window.__cs.toast("已删除"); loadKnowledge(); }).catch(function (e) { window.__cs.toast(e.message || "操作失败"); });
      },
      openChunks: function (u) {
        Api.request("GET", "/admin/knowledge/" + u.id + "/chunks")
          .then(function (list) { state.kb.chunks = { title: u.title, list: list || [] }; });
      },
      openPerm: function (u) { openPerm(u); },
      toggleArr: function (list, v) { toggleIn(list, v); },
      savePerm: function () { savePermCurrent(); },
      hasMenu: function (k) { return hasMenu(k); },
      loadOps: function () {
        var self = this;
        state.ops.loading = true;
        Promise.all([
          Api.request("GET", "/ops/audit/logs?limit=50"),
          Api.request("GET", "/ops/faq/candidates"),
          Api.request("GET", "/ops/faqs"),
          Api.request("GET", "/ops/gaps"),
        ]).then(function (r) {
          state.ops.audit = r[0] || [];
          state.ops.candidates = r[1] || [];
          state.ops.published = r[2] || [];
          state.ops.gaps = r[3] || [];
        }).catch(function (e) { window.__cs.toast(e.message); })
          .then(function () { state.ops.loading = false; });
      },
      runMining: function () {
        var self = this;
        state.ops.loading = true;
        Api.request("POST", "/admin/mining/run", { days: 7 })
          .then(function (d) {
            var m = d.mining || {};
            window.__cs.toast("挖掘完成：扫描 " + m.scannedQuestions + " 问，生成 " + (m.createdCandidates || []).length + " 个候选；缺口同步 " + (d.gaps || {}).noResultQuestions + " 问");
            return self.loadOps();
          }).catch(function (e) { window.__cs.toast(e.message); })
          .then(function () { state.ops.loading = false; });
      },
      startAdd: function () { state.ops.addForm = { question: "", answer: "" }; },
      saveCandidate: function () {
        var self = this;
        var f = state.ops.addForm;
        Api.request("POST", "/ops/faq/candidates", { question: f.question, answer: f.answer })
          .then(function () { state.ops.addForm = null; window.__cs.toast("候选已添加"); self.loadOps(); }).catch(function (e) { window.__cs.toast(e.message || "操作失败"); });
      },
      publish: function (c) {
        var q = prompt("确认/修改标准问法：", c.question);
        if (q === null) return;
        var a = prompt("确认/修改标准答案：", c.answer || "");
        if (a === null) return;
        Api.request("POST", "/ops/faq/candidates/" + c.candidate_id + "/publish", { question: q, answer: a })
          .then(function () { window.__cs.toast("已发布并写入高速缓存"); return this.loadOps(); }.bind(this)).catch(function (e) { window.__cs.toast(e.message || "操作失败"); });
      },
      reject: function (c) {
        Api.request("POST", "/ops/faq/candidates/" + c.candidate_id + "/reject", {})
          .then(function () { window.__cs.toast("已驳回"); return this.loadOps(); }.bind(this)).catch(function (e) { window.__cs.toast(e.message || "操作失败"); });
      },
      toggleFaqCache: function (f) {
        Api.request("PUT", "/ops/faqs/" + f.faq_id + "/cache", { enabled: !f.cacheEnabled })
          .then(function () { f.cacheEnabled = !f.cacheEnabled; window.__cs.toast(f.cacheEnabled ? "缓存已启用" : "缓存已停用"); });
      },
      delFaq: function (f) {
        if (!confirm("删除该 FAQ？")) return;
        Api.request("DELETE", "/ops/faqs/" + f.faq_id)
          .then(function () { window.__cs.toast("已删除"); return this.loadOps(); }.bind(this)).catch(function (e) { window.__cs.toast(e.message || "操作失败"); });
      },
      convertGap: function (g) {
        state.ops.convertForm = { gap: g, title: g.question, category: "待补充" };
      },
      saveConvert: function () {
        var self = this;
        var f = state.ops.convertForm;
        Api.request("POST", "/ops/gaps/" + f.gap.gap_id + "/convert", { title: f.title, category: f.category })
          .then(function (d) {
            state.ops.convertForm = null;
            window.__cs.toast("已创建补全任务《" + d.title + "》（占位停用，补充内容并启用后可被检索）");
            self.loadOps();
          })
          .catch(function (e) { window.__cs.toast((e && e.message) || "操作失败"); });
      },
      loadDashboard: function () {
        var self = this;
        state.dash.loading = true;
        Api.request("GET", "/admin/dashboard/overview?days=7").then(function (d) {
          state.dash.data = d;
          nextTick(function () { self.renderCharts(d); });
        }).catch(function (e) { window.__cs.toast(e.message); })
          .then(function () { state.dash.loading = false; });
      },
      renderCharts: function (d) {
        if (!window.echarts) return;
        var axis = { axisLabel: { color: "#64748b" }, axisLine: { lineStyle: { color: "#e2e8f0" } }, splitLine: { lineStyle: { color: "#f1f5f9" } } };
        var c1 = echarts.init(document.getElementById("chart-trend"));
        c1.setOption({ grid: { left: 50, right: 16, top: 30, bottom: 26 }, tooltip: { trigger: "axis" },
          legend: { data: ["Token", "PV"], top: 0 },
          xAxis: Object.assign({ type: "category", data: d.trend.days }, { axisLabel: axis.axisLabel }),
          yAxis: [Object.assign({ type: "value" }, axis), Object.assign({ type: "value", splitLine: { show: false } }, axis)],
          series: [{ name: "Token", type: "line", smooth: true, areaStyle: { opacity: .12 }, data: d.trend.tokens, itemStyle: { color: "#2563eb" } },
                   { name: "PV", type: "line", smooth: true, yAxisIndex: 1, data: d.trend.pv, itemStyle: { color: "#10b981" } }] });
        var c2 = echarts.init(document.getElementById("chart-tq"));
        c2.setOption({ grid: { left: 10, right: 30, top: 10, bottom: 20, containLabel: true }, tooltip: {},
          xAxis: Object.assign({ type: "value" }, axis),
          yAxis: { type: "category", data: d.topQuestions.map(function (x) { return x.q; }).reverse(), axisLabel: { color: "#64748b", width: 130, overflow: "truncate" } },
          series: [{ type: "bar", data: d.topQuestions.map(function (x) { return x.n; }).reverse(), itemStyle: { color: "#2563eb", borderRadius: [0, 4, 4, 0] }, barWidth: 14 }] });
        var c3 = echarts.init(document.getElementById("chart-tk"));
        var nameMap = {};
        state.kb.units.forEach(function (u) { nameMap[u.id] = u.title; });
        (d.denied_knowledge_ids = d.denied_knowledge_ids || []);
        c3.setOption({ grid: { left: 10, right: 30, top: 10, bottom: 20, containLabel: true }, tooltip: {},
          xAxis: Object.assign({ type: "value" }, axis), yAxis: { type: "category", data: d.topKnowledge.map(function (x) { return nameMap[x.kid] || x.kid; }).reverse(), axisLabel: { color: "#64748b" } },
          series: [{ type: "bar", data: d.topKnowledge.map(function (x) { return x.n; }).reverse(), itemStyle: { color: "#8b5cf6", borderRadius: [0, 4, 4, 0] }, barWidth: 14 }] });
        var c4 = echarts.init(document.getElementById("chart-lat"));
        c4.setOption({ grid: { left: 40, right: 16, top: 30, bottom: 26 }, tooltip: {},
          xAxis: { type: "category", data: d.latencyDist.map(function (x) { return x.label; }), axisLabel: axis.axisLabel },
          yAxis: Object.assign({ type: "value" }, axis),
          series: [{ type: "bar", data: d.latencyDist.map(function (x) { return x.n; }), itemStyle: { color: "#f59e0b", borderRadius: [4, 4, 0, 0] }, barWidth: 26 }] });
      },
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
          loadSessions();
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
            <a v-if="hasMenu('ops')" :class="{on: s.tab === 'ops'}" @click="go('ops')">沉淀与运营</a>
            <a v-if="hasMenu('dashboard')" :class="{on: s.tab === 'dashboard'}" @click="go('dashboard')">运营看板</a>
            <a v-if="hasMenu('org')" :class="{on: s.tab === 'org'}" @click="go('org')">组织与系统配置</a>
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

        <div v-if="s.tab === 'chat'" class="chat-main chat-with-side">
          <aside class="chat-side">
            <button class="btn primary block" @click="newSession">＋ 新建会话</button>
            <div v-for="sess in s.sessions" :key="sess.id" class="sess" :class="{on: s.sessionId === sess.id}" @click="openSession(sess)">
              <div class="sess-title">{{ sess.title }}</div>
              <div class="sess-meta"><span>{{ sess.count }} 条</span></div>
            </div>
            <p class="muted" v-if="!s.sessions.length" style="margin-top:10px">暂无历史会话</p>
            <a class="link" style="margin-top:8px;display:inline-block" @click="loadSessions()">刷新</a>
          </aside>
          <div class="chat-body">
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
        </div>

        <div v-else-if="s.tab === 'knowledge'" class="page" @dragover.prevent @drop.prevent="onDrop">
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


        <!-- ===== 沉淀与运营（M3） ===== -->
        <div v-else-if="s.tab === 'ops'" class="page">
          <div class="page-head">
            <h2>沉淀与运营</h2>
            <button class="btn primary" @click="runMining">⛏ 立即挖掘（聚合近7日问答）</button>
          </div>
          <div class="tabs">
            <a :class="{on: s.ops.tab === 'candidates'}" @click="s.ops.tab = 'candidates'">FAQ 候选 <span class="badge">{{ s.ops.candidates.filter(function(c){return c.status==='pending'}).length }}</span></a>
            <a :class="{on: s.tab === 'x'}" style="display:none"></a>
            <a :class="{on: s.ops.tab === 'published'}" @click="s.ops.tab = 'published'">已发布 FAQ <span class="badge">{{ s.ops.published.length }}</span></a>
            <a :class="{on: s.ops.tab === 'gaps'}" @click="s.ops.tab = 'gaps'">知识缺口 <span class="badge warn">{{ s.ops.gaps.length }}</span></a>
            <a :class="{on: s.ops.tab === 'audit'}" @click="s.ops.tab = 'audit'">问答审计</a>
          </div>

          <div v-if="s.ops.tab === 'candidates'">
            <div class="card" style="margin-bottom:14px">
              <h3>➕ 手动添加候选</h3>
              <div class="form-row" v-if="s.ops.addForm">
                <input class="ipt" style="flex:1" v-model="s.ops.addForm.question" placeholder="标准问题（如：生鲜破损怎么退款）" />
                <input class="ipt" style="flex:2" v-model="s.ops.addForm.answer" placeholder="标准答案（可发布时再润色）" />
                <button class="btn primary sm" @click="saveCandidate">添加</button>
              </div>
              <button v-else class="btn sm" @click="startAdd">＋ 新建候选 FAQ</button>
            </div>
            <div class="card table-card">
              <table>
                <thead><tr><th>标准问题（初稿）</th><th>频次</th><th>状态</th><th>标准答案（可在线润色）</th><th>操作</th></tr></thead>
                <tbody>
                  <tr v-for="c in s.ops.candidates" :key="c.candidate_id">
                    <td class="strong">{{ c.question }}</td>
                    <td><b>{{ c.freq }}</b></td>
                    <td><span class="tag" :class="c.status === 'pending' ? '' : c.status">{{ { pending: '待审核', published: '已发布', rejected: '已驳回' }[c.status] }}</span></td>
                    <td><textarea class="ipt" rows="2" v-model="c.answer" placeholder="（空）" :disabled="c.status !== 'pending'"></textarea></td>
                    <td class="ops">
                      <template v-if="c.status === 'pending'">
                        <a v-if="hasBtn('faq-publish')" class="link" @click="publish(c)">审核发布</a>
                        <a class="link danger" @click="reject(c)">驳回</a>
                      </template>
                    </td>
                  </tr>
                  <tr v-if="!s.ops.candidates.length"><td colspan="5" class="empty">暂无候选；点击右上角「立即挖掘」从问答日志聚类生成，或手动添加</td></tr>
                </tbody>
              </table>
            </div>
          </div>

          <div v-if="s.ops.tab === 'published'" class="card table-card">
            <table>
              <thead><tr><th>标准问题</th><th>标准答案</th><th>缓存直出</th><th>命中次数</th><th>发布时间</th><th>操作</th></tr></thead>
              <tbody>
                <tr v-for="f in s.ops.published" :key="f.faq_id">
                  <td class="strong">{{ f.question }}</td>
                  <td class="muted clip">{{ f.answer }}</td>
                  <td>
                    <label class="switch"><input type="checkbox" :checked="f.cacheEnabled" :disabled="!hasBtn('cache-toggle')" @change="toggleFaqCache(f)" /><i></i></label>
                    <span class="muted">{{ f.cacheEnabled ? '命中直出' : '已停用' }}</span>
                  </td>
                  <td>{{ f.hitCount }}</td>
                  <td class="muted">{{ fmtTime(f.publishedAt) }}</td>
                  <td><a v-if="hasBtn('faq-publish')" class="link danger" @click="delFaq(f)">删除</a></td>
                </tr>
                <tr v-if="!s.ops.published.length"><td colspan="6" class="empty">暂无已发布 FAQ</td></tr>
              </tbody>
            </table>
          </div>

          <div v-if="s.ops.tab === 'gaps'" class="card table-card">
            <table>
              <thead><tr><th>未命中提问</th><th>提问部门</th><th>频次</th><th>最近提问</th><th>状态</th><th>操作</th></tr></thead>
              <tbody>
                <tr v-for="g in s.ops.gaps" :key="g.gap_id">
                  <td class="strong">{{ g.question }}</td>
                  <td>{{ g.department || '—' }}</td>
                  <td><b>{{ g.freq }}</b></td>
                  <td class="muted">{{ fmtTime(g.lastAt) }}</td>
                  <td><span class="tag">待补全</span></td>
                  <td><a v-if="hasBtn('gap-task')" class="link" @click="convertGap(g)">转知识补全任务</a></td>
                </tr>
                <tr v-if="!s.ops.gaps.length"><td colspan="6" class="empty">暂无缺口；问答未命中知识库的问题会自动进入缺口池（触发「立即挖掘」后聚合展示）</td></tr>
              </tbody>
            </table>
          </div>

          <div v-if="s.ops.tab === 'audit'" class="card table-card">
            <table>
              <thead><tr><th>时间</th><th>来源</th><th>提问</th><th>放行</th><th>拦截</th><th>Token</th><th>耗时</th></tr></thead>
              <tbody>
                <tr v-for="(l, i) in s.ops.audit" :key="i">
                  <td class="muted">{{ fmtTime(l.ts) }}</td>
                  <td><span class="tag" :class="l.source">{{ { 'faq-cache': 'FAQ缓存', 'semantic-cache': '语义缓存', 'rag': 'RAG', 'denied': '权限受限', 'no-result': '未命中' }[l.source] || l.source }}</span></td>
                  <td class="clip">{{ l.question }}</td>
                  <td><span class="muted">{{ (l.allowed_ids || []).length }} 个</span></td>
                  <td><span class="muted" :style="(l.denied_ids || []).length ? 'color:#b45309' : ''">{{ (l.denied_ids || []).length }} 个</span></td>
                  <td>{{ l.tokens }}</td>
                  <td>{{ l.latency }} ms</td>
                </tr>
                <tr v-if="!s.ops.audit.length"><td colspan="7" class="empty">暂无审计记录</td></tr>
              </tbody>
            </table>
          </div>

          <div v-if="s.ops.convertForm" class="modal-mask" @click.self="s.ops.convertForm = null">
            <div class="modal">
              <div class="modal-head"><h3>转知识补全任务</h3><a class="x" @click="s.ops.convertForm = null">✕</a></div>
              <div class="form-row"><label>文档标题</label><input class="ipt" v-model="s.ops.convertForm.title" /></div>
              <div class="form-row"><label>所属分类</label><input class="ipt" v-model="s.ops.convertForm.category" /></div>
              <p class="muted">创建停用占位知识单元；管理员补充正文内容并启用后，该缺口提问即可被检索命中（闭环）。</p>
              <div class="modal-foot">
                <button class="btn" @click="s.ops.convertForm = null">取消</button>
                <button class="btn primary" @click="saveConvert">创建任务</button>
              </div>
            </div>
          </div>
        </div>

        <!-- ===== 运营看板（M3） ===== -->
        <div v-else-if="s.tab === 'dashboard'" class="page">
          <div class="page-head"><h2>运营看板</h2><span class="muted">近 7 日 · 数据来自问答审计日志</span></div>
          <div class="kpi-grid" v-if="s.dash.data">
            <div class="card kpi"><div class="kpi-label">今日访问量 PV</div><div class="kpi-val">{{ s.dash.data.pv }}</div></div>
            <div class="card kpi"><div class="kpi-label">今日独立提问 UV</div><div class="kpi-val">{{ s.dash.data.uv }}</div></div>
            <div class="card kpi"><div class="kpi-label">知识单元总数</div><div class="kpi-val">{{ s.dash.data.kbTotal }}</div></div>
            <div class="card kpi"><div class="kpi-label">FAQ 缓存命中率</div><div class="kpi-val">{{ s.dash.data.faqHitRate }}<small>%</small></div></div>
            <div class="card kpi"><div class="kpi-label">今日 Token 消耗</div><div class="kpi-val">{{ s.dash.data.tokenToday.toLocaleString() }}</div></div>
            <div class="card kpi"><div class="kpi-label">平均响应延时（RAG）</div><div class="kpi-val">{{ s.dash.data.avgLatency }}<small>ms</small></div></div>
          </div>
          <div class="chart-grid" v-if="s.dash.data">
            <div class="card"><h3>Token 与提问量趋势</h3><div class="chart" id="chart-trend"></div></div>
            <div class="card"><h3>高频问题 TOP5</h3><div class="chart" id="chart-tq"></div></div>
            <div class="card"><h3>高频引用知识 TOP5</h3><div class="chart" id="chart-tk"></div></div>
            <div class="card"><h3>响应延时分布（RAG）</h3><div class="chart" id="chart-lat"></div></div>
          </div>
        </div>


        <!-- ===== 组织与系统配置（M2-04） ===== -->
        <div v-else-if="s.tab === 'org'" class="page">
          <div class="page-head"><h2>组织与系统配置</h2>
            <button class="btn" @click="loadOrg(); loadSessions()">↻ 刷新</button>
          </div>
          <div class="org-grid">
            <div class="card">
              <h3>用户管理</h3>
              <button v-if="hasBtn('user-manage')" class="btn primary sm" style="margin-bottom:10px" @click="startNewUser">＋ 新增用户</button>
              <table>
                <thead><tr><th>姓名</th><th>账号</th><th>部门</th><th>状态</th><th>操作</th></tr></thead>
                <tbody>
                  <tr v-for="u in s.org.users" :key="u.id">
                    <td class="strong">{{ u.name }}</td>
                    <td class="mono">{{ u.username }}</td>
                    <td>{{ u.departmentId || '—' }}</td>
                    <td><span class="tag" :class="u.status === 'disabled' ? 'rejected' : ''">{{ u.status === 'disabled' ? '已禁用' : '正常' }}</span></td>
                    <td class="ops">
                      <a v-if="hasBtn('user-manage')" class="link" @click="startEditUser(u)">编辑</a>
                      <a v-if="hasBtn('user-manage')" class="link" @click="resetPwd(u)">重置密码</a>
                      <a v-if="hasBtn('user-manage') && u.id !== s.user.id" class="link danger" @click="delUser(u)">删除</a>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div class="card">
              <h3>角色功能权限</h3>
              <div class="form-row"><label>角色</label>
                <select class="ipt" style="width:auto" v-model="s.org.roleCode" @change="startRoleEdit(s.org.roleCode)">
                  <option v-for="r in s.org.roles" :key="r.code" :value="r.code">{{ r.name }}（{{ r.code }}）</option>
                </select>
              </div>
              <div v-if="s.org.roleEdit">
                <div v-for="m in menuDefs" :key="m.key" class="pt-group">
                  <label class="pt-menu"><b>{{ m.label }}</b> <span class="muted">（菜单）</span>
                    <input type="checkbox" style="margin-left:6px" :checked="s.org.roleEdit.menus.indexOf(m.key) >= 0" @change="toggleRoleMenu(m.key)" />
                  </label>
                  <div class="pt-btns">
                    <label v-for="b in m.buttons" :key="b.key" class="pt-btn">
                      <input type="checkbox" :disabled="s.org.roleEdit.menus.indexOf(m.key) < 0" :checked="s.org.roleEdit.buttons.indexOf(b.key) >= 0" @change="toggleRoleButton(b.key)" /> {{ b.label }}
                    </label>
                  </div>
                </div>
                <button v-if="hasBtn('role-manage')" class="btn primary sm" @click="saveRole">保存角色权限</button>
                <p class="muted">保存后该角色用户重新登录即生效。</p>
              </div>
            </div>
            <div class="card span2">
              <h3>模型服务配置（当前生效）</h3>
              <div class="form-row"><label>对话模型</label><span class="mono">deepseek-v4-flash @ api.deepseek.com</span></div>
              <div class="form-row"><label>Embedding</label><span class="mono">BAAI/bge-m3 @ 硅基流动 API</span></div>
              <div class="form-row"><label>Reranker</label><span class="mono">BAAI/bge-reranker-v2-m3 @ 硅基流动 API</span></div>
              <p class="muted">修改请在 .env 中调整后重启双服务（安全起见 API Key 不在页面展示）。</p>
            </div>
          </div>

          <div v-if="s.org.userEdit" class="modal-mask" @click.self="s.org.userEdit = null">
            <div class="modal">
              <div class="modal-head"><h3>{{ s.org.userEdit.id ? '编辑用户' : '新增用户' }}</h3><a class="x" @click="s.org.userEdit = null">✕</a></div>
              <div class="form-row"><label>账号</label><input class="ipt" v-model="s.org.userEdit.username" :disabled="!!s.org.userEdit.id" /></div>
              <div class="form-row"><label>姓名</label><input class="ipt" v-model="s.org.userEdit.display_name" /></div>
              <div class="form-row" v-if="!s.org.userEdit.id"><label>初始密码</label><input class="ipt" v-model="s.org.userEdit.password" /></div>
              <div class="form-row"><label>重置密码</label><input class="ipt" v-if="s.org.userEdit.id" v-model="s.org.userEdit.password" /><span v-else class="muted">（见上）</span></div>
              <div class="form-row"><label>部门</label><input class="ipt" v-model="s.org.userEdit.department_id" placeholder="如 dept-biz" /></div>
              <div class="form-row"><label>角色</label>
                <label v-for="r in s.org.roles" :key="r.code" class="check-row inline">
                  <input type="checkbox" :value="r.code" v-model="s.org.userEdit.role_codes" /> {{ r.name }}
                </label>
              </div>
              <div class="form-row"><label>启用</label><input type="checkbox" v-model="s.org.userEdit.enabled" /></div>
              <div class="modal-foot">
                <button class="btn" @click="s.org.userEdit = null">取消</button>
                <button class="btn primary" @click="saveUser">保存</button>
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
