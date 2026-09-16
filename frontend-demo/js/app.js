/* ============================================================
 * app.js —— Vue 3 应用（页面组件 + 交互逻辑）
 * 页面对应需求 2.9.3：登录 / 问答工作台 / 知识导入中心 / 沉淀运营 / 看板 / 组织配置
 * ============================================================ */
(function () {
  const { createApp, reactive, computed, watch, nextTick, onMounted, onBeforeUnmount, ref } = Vue;

  /* ---------- 全局状态 ---------- */
  const store = reactive({
    user: null,
    view: 'chat',
    guideOpen: false,
    chatDraft: '',          // 演示剧本填充问题用
    toasts: [],
    toast(type, text) { const id = Date.now() + Math.random(); this.toasts.push({ id, type, text }); setTimeout(() => { this.toasts = this.toasts.filter(t => t.id !== id); }, 3200); },
  });
  // 初始化数据库（每次刷新重置为种子数据；登录态存 sessionStorage）
  window.DB = JSON.parse(JSON.stringify(window.SEED));
  const savedUid = sessionStorage.getItem('demo_uid');
  if (savedUid) {
    const u = DB.users.find(x => x.id === savedUid && x.enabled);
    if (u) { store.user = u; DB.sessionUserId = u.id; ensureSessions(u); }
  }
  function ensureSessions(user) {
    DB.sessions = DB.sessions || {};
    if (!DB.sessions[user.id]) {
      DB.sessions[user.id] = clone(DB.seedSessions[user.id] || [{ id: 's' + Date.now(), title: '新会话', createdAt: Date.now(), messages: [] }]);
    }
  }
  window.store = store;

  /* ---------- 迷你 Markdown 渲染（标题/加粗/行内码/代码块/引用/列表） ---------- */
  function esc(s) { return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
  function inline(s) {
    return esc(s)
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/`(.+?)`/g, '<code>$1</code>');
  }
  window.mdRender = function (src) {
    const parts = String(src || '').split('```');
    let html = '';
    parts.forEach((part, idx) => {
      if (idx % 2 === 1) { // 代码块
        const lines = part.split('\n'); if (lines[0].trim() && lines[0].length < 20 && !lines[0].includes(' ')) lines.shift();
        html += '<pre><code>' + esc(lines.join('\n')) + '</code></pre>';
        return;
      }
      let inList = false, listTag = '';
      const out = [];
      part.split('\n').forEach(raw => {
        const line = raw.trimEnd();
        const ul = line.match(/^\s*[-*]\s+(.*)/), ol = line.match(/^\s*\d+[.、]\s+(.*)/);
        const closeList = () => { if (inList) { out.push('</' + listTag + '>'); inList = false; } };
        if (ul) { if (!inList || listTag !== 'ul') { closeList(); out.push('<ul>'); inList = true; listTag = 'ul'; } out.push('<li>' + inline(ul[1]) + '</li>'); }
        else if (ol) { if (!inList || listTag !== 'ol') { closeList(); out.push('<ol>'); inList = true; listTag = 'ol'; } out.push('<li>' + inline(ol[1]) + '</li>'); }
        else if (/^#{1,4}\s/.test(line)) { closeList(); const lv = line.match(/^#+/)[0].length; out.push('<h' + (lv + 2) + '>' + inline(line.replace(/^#+\s*/, '')) + '</h' + (lv + 2) + '>'); }
        else if (/^>\s?/.test(line)) { closeList(); out.push('<blockquote>' + inline(line.replace(/^>\s?/, '')) + '</blockquote>'); }
        else if (line.trim() === '') { closeList(); }
        else { closeList(); out.push('<p>' + inline(line) + '</p>'); }
      });
      closeList();
      html += out.join('');
    });
    return html;
  };

  /* ---------- 通用工具 ---------- */
  const fmtTime = (ts) => { const d = new Date(ts); return d.getMonth() + 1 + '-' + d.getDate() + ' ' + String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0'); };
  function hasBtn(menu, key) {
    const u = store.user; if (!u) return false;
    return u.roleIds.some(rid => { const r = DB.roles.find(x => x.id === rid); return r && r.buttons.includes(key); });
  }
  function hasMenu(key) {
    const u = store.user; if (!u) return false;
    return u.roleIds.some(rid => { const r = DB.roles.find(x => x.id === rid); return r && r.menus.includes(key); });
  }

  /* ============================================================
   * DeptTree —— 部门树（多选 / 单选高亮复用）
   * ============================================================ */
  const DeptTree = {
    name: 'DeptTree',
    props: { modelValue: { type: Array, default: () => [] }, multiple: { type: Boolean, default: true }, activeId: { type: String, default: '' } },
    emits: ['update:modelValue', 'select'],
    computed: {
      roots() { return DB.departments.filter(d => !d.parentId); },
    },
    methods: {
      children(pid) { return DB.departments.filter(d => d.parentId === pid); },
      deptName(id) { const d = DB.departments.find(x => x.id === id); return d ? d.name : id; },
      toggle(id) {
        if (!this.multiple) { this.$emit('select', id); return; }
        const v = this.modelValue.includes(id) ? this.modelValue.filter(x => x !== id) : this.modelValue.concat(id);
        this.$emit('update:modelValue', v);
      },
      selectOne(id) { this.$emit('select', id); },
    },
    template: `
      <div class="dept-tree">
        <template v-for="root in roots" :key="root.id">
          <div class="dt-node">
            <div class="dt-row" :class="{on: modelValue.includes(root.id) || activeId===root.id}" @click="multiple ? toggle(root.id) : selectOne(root.id)">
              <span v-if="multiple" class="dt-check" :class="{on: modelValue.includes(root.id)}"></span>
              <span class="dt-name">{{ deptName(root.id) }}</span>
            </div>
            <div class="dt-children" v-if="children(root.id).length">
              <div v-for="c in children(root.id)" :key="c.id" class="dt-row sub" :class="{on: modelValue.includes(c.id) || activeId===c.id}" @click="multiple ? toggle(c.id) : selectOne(c.id)">
                <span v-if="multiple" class="dt-check" :class="{on: modelValue.includes(c.id)}"></span>
                <span class="dt-name">{{ c.name }}</span>
              </div>
            </div>
          </div>
        </template>
      </div>`,
  };

  /* ============================================================
   * LoginView —— 登录页（演示：账号一键登录，密码不校验）
   * ============================================================ */
  const LoginView = {
    data: () => ({ username: 'zhangsan', password: '' }),
    computed: {
      accounts() {
        return DB.users.filter(u => u.enabled).map(u => ({
          u,
          roleName: u.roleIds.map(r => (DB.roles.find(x => x.id === r) || {}).name).join(' / '),
          deptName: (DB.departments.find(d => d.id === u.departmentId) || {}).name,
        }));
      },
    },
    methods: {
      login(username) {
        const u = DB.users.find(x => x.username === username && x.enabled);
        if (!u) { store.toast('error', '账号不存在或已停用'); return; }
        store.user = u; DB.sessionUserId = u.id;
        sessionStorage.setItem('demo_uid', u.id);
        ensureSessions(u);
        store.view = 'chat';
        store.toast('ok', '欢迎，' + u.name + '（演示环境不校验密码）');
      },
    },
    template: `
      <div class="login-page">
        <div class="login-hero">
          <div class="login-logo">📚</div>
          <h1>华智智库 · RAG 知识库管理平台</h1>
          <p>多源知识维护 · 四维数据权限鉴权 · AI 鉴权检索问答 · 运营看板 · 知识自动沉淀</p>
          <p class="login-tip">前端交互 Demo：所有数据为内置 mock，检索 / 鉴权 / FAQ 缓存 / 缺口闭环逻辑均在前端真实运行</p>
        </div>
        <div class="login-card">
          <h3>选择演示账号登录</h3>
          <p class="muted" style="margin:4px 0 12px">点击卡片即登录，用于体验不同角色的菜单与数据权限差异</p>
          <div v-for="a in accounts" :key="a.u.id" class="acc" @click="login(a.u.username)">
            <div class="acc-avatar">{{ a.u.name[0] }}</div>
            <div class="acc-info">
              <div class="acc-name">{{ a.u.name }} <span class="tag">{{ a.roleName }}</span></div>
              <div class="acc-sub">{{ a.deptName }} · {{ a.u.username }}</div>
            </div>
            <span class="acc-go">登录 ›</span>
          </div>
        </div>
      </div>`,
  };

  /* ============================================================
   * ChatView —— AI 智能问答工作台
   * ============================================================ */
  const ChatView = {
    data: () => ({ draft: '', busy: false }),
    computed: {
      sessions() { return DB.sessions[store.user.id] || []; },
      current() { return this.sessions.find(s => s.id === store.curSessionId) || this.sessions[0]; },
      messages() { return this.current ? this.current.messages : []; },
      suggestions() {
        const pool = [...DB.faqPublished.map(f => f.question), ...DB.settings.suggestPool];
        const uniq = [...new Set(pool)];
        if (!this.draft.trim()) return uniq.slice(0, 4);
        return uniq.filter(q => q.includes(this.draft.trim()) && q !== this.draft.trim()).slice(0, 6);
      },
    },
    watch: {
      'store.chatDraft': { handler(v) { if (v) { this.draft = v; store.chatDraft = ''; } }, immediate: true },
      messages: { deep: true, handler() { this.scrollBottom(); } },
    },
    mounted() { if (!store.curSessionId && this.sessions.length) store.curSessionId = this.sessions[0].id; this.scrollBottom(); },
    methods: {
      fmtTime,
      newSession() {
        const s = { id: 's' + Date.now(), title: '新会话', createdAt: Date.now(), messages: [] };
        this.sessions.unshift(s); store.curSessionId = s.id;
      },
      openSession(s) { store.curSessionId = s.id; },
      removeSession(s) {
        const i = this.sessions.indexOf(s); if (i < 0) return;
        this.sessions.splice(i, 1);
        if (store.curSessionId === s.id) store.curSessionId = this.sessions[0] ? this.sessions[0].id : null;
      },
      pick(q) { this.draft = q; this.send(); },
      async send() {
        if (!hasBtn('chat', 'ask')) { store.toast('error', '当前角色无「发起提问」操作权限'); return; }
        const q = this.draft.trim();
        if (!q || this.busy) return;
        if (!this.current) this.newSession();
        const sess = this.current;
        if (sess.messages.length === 0) sess.title = q.slice(0, 14);
        sess.messages.push({ role: 'user', text: q, ts: Date.now() });
        this.draft = ''; this.busy = true;
        const msg = reactive({ role: 'assistant', text: '', steps: null, refs: null, deniedCount: 0, faq: null, meta: null, streaming: false });
        sess.messages.push(msg);
        await nextTick(); this.scrollBottom();
        const historyRounds = sess.messages.filter(m => m.meta || m.role === 'user').length;
        try {
          await Services.runPipeline({ user: store.user, question: q, historyRounds: Math.max(0, Math.floor((historyRounds - 1) / 2)), msg });
        } catch (e) { msg.text = '系统异常：' + e.message; }
        this.busy = false;
      },
      scrollBottom() {
        nextTick(() => { const el = this.$refs.msgs; if (el) el.scrollTop = el.scrollHeight; });
      },
      stepIcon(s) { return { pending: '○', running: '⟳', done: '✓', skipped: '—' }[s.status] || '○'; },
    },
    template: `
      <div class="chat-layout">
        <aside class="chat-side">
          <button class="btn primary block" @click="newSession">＋ 新建会话</button>
          <div v-for="s in sessions" :key="s.id" class="sess" :class="{on: current && s.id===current.id}" @click="openSession(s)">
            <div class="sess-title">{{ s.title }}</div>
            <div class="sess-meta">
              <span>{{ fmtTime(s.createdAt) }}</span>
              <a class="link danger" @click.stop="removeSession(s)">删除</a>
            </div>
          </div>
        </aside>
        <div class="chat-main">
          <div class="msgs" ref="msgs">
            <template v-if="messages.length === 0">
              <div class="chat-welcome">
                <h2>👋 你好，{{ store.user.name }}</h2>
                <p>我是华智智库 AI 助手。回答将基于你有权限访问的知识库内容，<br>无权限的资料会被自动过滤并明确提示，不会越权泄露。</p>
                <div class="chips">
                  <span v-for="q in suggestions" :key="q" class="chip" @click="pick(q)">{{ q }}</span>
                </div>
              </div>
            </template>
            <template v-for="(m, i) in messages" :key="i">
              <div v-if="m.role === 'user'" class="msg-user"><div class="bubble-user">{{ m.text }}</div></div>
              <div v-else class="msg-ai">
                <!-- 问答管线步骤条：对应 LangGraph 查询编排 -->
                <div v-if="m.steps" class="pipeline">
                  <div v-for="st in m.steps" :key="st.key" class="pstep" :class="st.status">
                    <span class="ps-icon">{{ stepIcon(st) }}</span>
                    <span class="ps-label">{{ st.label }}</span>
                    <span class="ps-detail" v-if="st.detail">{{ st.detail }}</span>
                  </div>
                </div>
                <div class="md" v-html="mdRender(m.text)"></div>
                <span v-if="m.streaming" class="cursor">▌</span>

                <!-- FAQ 缓存命中徽标 -->
                <div v-if="m.faq" class="faq-badge">⚡ FAQ 缓存命中直出（未调用大模型，毫秒级返回）</div>

                <!-- 知识引用溯源卡片 -->
                <div v-if="m.refs && m.refs.length" class="refs">
                  <div class="refs-title">📖 知识引用溯源</div>
                  <div v-for="(r, ri) in m.refs" :key="ri" class="ref-card">
                    <div class="ref-head"><span class="ref-title">《{{ r.title }}》</span><span class="ref-score">相关度 {{ Math.round(r.score*100) }}%</span></div>
                    <div class="ref-text">{{ r.text }}</div>
                  </div>
                </div>

                <!-- 权限缺失安全提示气泡 -->
                <div v-if="m.deniedCount > 0" class="denied-card">
                  🔒 部分参考资料因权限受限无法展示（{{ m.deniedCount }} 个切片已按四维权限规则拦截）。如需访问，请联系知识管理员申请权限。
                </div>

                <div v-if="m.meta" class="msg-meta">
                  <span class="tag" :class="m.meta.source">{{ { 'faq-cache': 'FAQ 缓存', 'rag': 'RAG 检索', 'no-result': '未命中' }[m.meta.source] }}</span>
                  <span>耗时 {{ m.meta.latency }} ms</span>
                  <span v-if="m.meta.tokens">≈{{ m.meta.tokens }} tokens</span>
                </div>
              </div>
            </template>
          </div>
          <div class="composer">
            <div v-if="draft.trim() && suggestions.length" class="ac-box">
              <div v-for="q in suggestions" :key="q" class="ac-item" @click="pick(q)">{{ q }}</div>
            </div>
            <div class="composer-row">
              <textarea v-model="draft" rows="2" placeholder="输入业务问题，Enter 发送（回答基于你有权限的知识库内容）…" @keydown.enter.exact.prevent="send"></textarea>
              <button class="btn primary" :disabled="busy || !draft.trim()" @click="send">{{ busy ? '回答中…' : '发送' }}</button>
            </div>
          </div>
        </div>
      </div>`,
  };

  /* ============================================================
   * KnowledgeView —— 知识维护与导入中心
   * ============================================================ */
  const PermDialog = {
    props: ['item'],
    emits: ['close'],
    data() { return { form: clone(this.item.perms), userSearch: '' }; },
    computed: {
      roleList() { return DB.roles; },
      userGroups() {
        const q = this.userSearch.trim();
        return DB.departments
          .map(d => ({ dept: d, users: DB.users.filter(u => u.departmentId === d.id && u.enabled && (!q || u.name.includes(q) || u.username.includes(q))) }))
          .filter(g => g.users.length);
      },
    },
    methods: {
      toggleUser(id) {
        const v = this.form.userIds.includes(id) ? this.form.userIds.filter(x => x !== id) : this.form.userIds.concat(id);
        this.form.userIds = v;
      },
      save() {
        Services.setPerm(this.item.id, clone(this.form));
        store.toast('ok', '权限已保存并同步鉴权引擎缓存');
        this.$emit('close');
      },
    },
    template: `
      <div class="modal-mask" @click.self="$emit('close')">
        <div class="modal perm-dialog">
          <div class="modal-head">
            <h3>四维数据权限配置 —《{{ item.title }}》</h3>
            <a class="x" @click="$emit('close')">✕</a>
          </div>
          <p class="muted">OR 充分条件逻辑：满足以下任意一项即可访问；全部为空时无任何用户可访问（默认拒绝）。</p>
          <div class="perm-grid">
            <div class="perm-block span4">
              <label class="switch-row">
                <span class="perm-tag global">全局 global</span>
                <span>全员公开访问</span>
                <input type="checkbox" v-model="form.global" />
              </label>
            </div>
            <div class="perm-block span2">
              <h4><span class="perm-tag dept">部门 department</span></h4>
              <dept-tree v-model="form.departmentIds" :multiple="true"></dept-tree>
            </div>
            <div class="perm-block span2">
              <h4><span class="perm-tag role">角色 role</span></h4>
              <label v-for="r in roleList" :key="r.id" class="check-row">
                <input type="checkbox" :value="r.id" v-model="form.roleIds" /> {{ r.name }}
              </label>
            </div>
            <div class="perm-block span4">
              <h4><span class="perm-tag user">个人 user</span></h4>
              <input class="ipt sm" v-model="userSearch" placeholder="搜索姓名 / 账号…" />
              <div class="user-groups">
                <div v-for="g in userGroups" :key="g.dept.id" class="ugroup">
                  <div class="ug-name">{{ g.dept.name }}</div>
                  <label v-for="u in g.users" :key="u.id" class="check-row">
                    <input type="checkbox" :checked="form.userIds.includes(u.id)" @change="toggleUser(u.id)" />
                    {{ u.name }} <span class="muted">({{ u.username }})</span>
                  </label>
                </div>
              </div>
            </div>
          </div>
          <div class="modal-foot">
            <button class="btn" @click="$emit('close')">取消</button>
            <button class="btn primary" @click="save">保存并生效</button>
          </div>
        </div>
      </div>`,
  };

  const ImportDrawer = {
    emits: ['close'],
    data: () => ({ jobs: [], dragging: false }),
    computed: {
      running() { return this.jobs.some(j => j.progress < 100); },
    },
    methods: {
      addFiles(fileList) {
        const ok = ['pdf', 'md', 'doc', 'docx', 'txt'];
        for (const f of fileList) {
          const ext = (f.name.split('.').pop() || '').toLowerCase();
          if (!ok.includes(ext)) { store.toast('error', '不支持的格式：' + f.name + '（仅支持 PDF / Markdown / Word / TXT）'); continue; }
          if (this.jobs.some(j => j.name === f.name)) continue;
          this.jobs.push({ name: f.name, size: (f.size / 1024).toFixed(0) + ' KB', ext, progress: 0, stage: '排队中', done: false });
        }
        this.runNext();
      },
      onDrop(e) { this.dragging = false; this.addFiles(e.dataTransfer.files); },
      pickFiles(e) { this.addFiles(e.target.files); e.target.value = ''; },
      async runNext() {
        // 防并发：同一时刻只跑一个任务（真实实现为后台导入队列）
        if (this.running) return;
        const job = this.jobs.find(j => j.progress < 100);
        if (!job) return;
        const stages = [['文本清洗', 25, 700], ['智能分块 Chunking', 50, 800], ['语义向量化 Embedding', 85, 1200], ['索引入库 Milvus', 100, 600]];
        for (const [name, p, dur] of stages) {
          job.stage = name + '…';
          await new Promise(r => setTimeout(r, dur));
          job.progress = p;
        }
        job.done = true;
        Services.addImported(job.name.replace(/\.[^.]+$/, ''), job.ext);
        store.toast('ok', '《' + job.name + '》解析入库完成，默认无公开权限，请配置四维权限后发布');
        this.runNext();
      },
    },
    template: `
      <div class="drawer-mask" @click.self="$emit('close')">
        <div class="drawer">
          <div class="drawer-head">
            <h3>批量文档导入</h3>
            <a class="x" @click="$emit('close')">✕</a>
          </div>
          <p class="muted">支持 PDF / Markdown / Word / TXT，可拖拽文件或整个文件夹；解析流程：文本清洗 → 分块 → 向量化 → 入库。</p>
          <div class="dropzone" :class="{drag: dragging}"
               @dragover.prevent="dragging = true" @dragleave="dragging = false" @drop.prevent="onDrop">
            <div class="dz-icon">📂</div>
            <p>将文件或文件夹拖拽到此处</p>
            <div class="dz-btns">
              <label class="btn ghost">选择文件<input type="file" multiple accept=".pdf,.md,.doc,.docx,.txt" hidden @change="pickFiles" /></label>
              <label class="btn ghost">选择文件夹<input type="file" webkitdirectory hidden @change="pickFiles" /></label>
            </div>
          </div>
          <div v-if="jobs.length" class="jobs">
            <div v-for="j in jobs" :key="j.name" class="job">
              <div class="job-head">
                <span class="job-name">{{ j.name }}</span>
                <span class="muted">{{ j.size }} · {{ j.ext.toUpperCase() }}</span>
              </div>
              <div class="bar"><div class="bar-in" :class="{ok: j.done}" :style="{width: j.progress + '%'}"></div></div>
              <div class="job-foot">
                <span>{{ j.done ? '✅ 入库完成' : j.stage }}</span><span class="muted">{{ j.progress }}%</span>
              </div>
            </div>
          </div>
          <div class="drawer-foot">
            <button class="btn primary" :disabled="running" @click="$emit('close')">完成{{ running ? '（解析中…）' : '' }}</button>
          </div>
        </div>
      </div>`,
  };

  const KnowledgeView = {
    components: { PermDialog, ImportDrawer, DeptTree },
    data: () => ({ kw: '', cat: '', showImport: false, permItem: null, editItem: null, editForm: null, chunksItem: null }),
    computed: {
      list() {
        return DB.knowledge.filter(k =>
          (!this.kw || k.title.includes(this.kw)) &&
          (!this.cat || k.category === this.cat));
      },
      categories() { return [...new Set(DB.knowledge.map(k => k.category))]; },
      fmtName() { return { pdf: 'PDF', md: 'Markdown', docx: 'Word', doc: 'Word', txt: 'TXT' }; },
    },
    methods: {
      hasBtn,
      fmtTime,
      deptName(id) { return (DB.departments.find(d => d.id === id) || {}).name || id; },
      roleName(id) { return (DB.roles.find(r => r.id === id) || {}).name || id; },
      userName(id) { return (DB.users.find(u => u.id === id) || {}).name || id; },
      permBadges(k) {
        const p = k.perms, out = [];
        if (p.global) out.push({ t: '全局公开', cls: 'global' });
        if (p.departmentIds.length) out.push({ t: '部门 ×' + p.departmentIds.length, cls: 'dept' });
        if (p.roleIds.length) out.push({ t: '角色 ×' + p.roleIds.length, cls: 'role' });
        if (p.userIds.length) out.push({ t: '个人 ×' + p.userIds.length, cls: 'user' });
        if (!out.length) out.push({ t: '未配置（默认拒绝）', cls: 'none' });
        return out;
      },
      openEdit(k) { this.editItem = k; this.editForm = { title: k.title, category: k.category, enabled: k.enabled }; },
      saveEdit() { Services.updateKnowledge(this.editItem.id, this.editForm); this.editItem = null; store.toast('ok', '知识单元已更新'); },
      del(k) {
        if (!confirm('确认删除《' + k.title + '》？将同步删除其全部切片与向量索引。')) return;
        Services.deleteKnowledge(k.id); store.toast('ok', '已删除');
      },
      chunksOf(k) { return DB.chunks.filter(c => c.kid === k.id); },
      toggleEnabled(k) { Services.updateKnowledge(k.id, { enabled: !k.enabled }); },
    },
    template: `
      <div class="page">
        <div class="page-head">
          <h2>知识维护与导入中心</h2>
          <button v-if="hasBtn('knowledge','import')" class="btn primary" @click="showImport = true">⬆ 导入文档（单篇 / 批量拖拽）</button>
        </div>
        <div class="toolbar">
          <input class="ipt" v-model="kw" placeholder="搜索知识标题…" />
          <select class="ipt sel" v-model="cat">
            <option value="">全部分类</option>
            <option v-for="c in categories" :key="c" :value="c">{{ c }}</option>
          </select>
          <span class="muted">共 {{ list.length }} 个知识单元（含切片 {{ DB.chunks.length }} 条）</span>
        </div>
        <div class="card table-card">
          <table>
            <thead><tr>
              <th>编号</th><th>标题</th><th>格式</th><th>分类</th><th>四维权限标签</th><th>切片</th><th>启用</th><th>更新时间</th><th>操作</th>
            </tr></thead>
            <tbody>
              <tr v-for="k in list" :key="k.id">
                <td class="mono">{{ k.id }}</td>
                <td class="strong">{{ k.title }}</td>
                <td><span class="tag fmt">{{ fmtName[k.format] || k.format }}</span></td>
                <td>{{ k.category }}</td>
                <td>
                  <span v-for="b in permBadges(k)" :key="b.t" class="perm-tag sm" :class="b.cls">{{ b.t }}</span>
                </td>
                <td>{{ chunksOf(k).length }}</td>
                <td><label class="switch"><input type="checkbox" :checked="k.enabled" @change="toggleEnabled(k)" /><i></i></label></td>
                <td class="muted">{{ fmtTime(k.updatedAt) }}</td>
                <td class="ops">
                  <a v-if="hasBtn('knowledge','perm')" class="link" @click="permItem = k">权限</a>
                  <a v-if="hasBtn('knowledge','edit')" class="link" @click="openEdit(k)">编辑</a>
                  <a class="link" @click="chunksItem = k">切片</a>
                  <a v-if="hasBtn('knowledge','delete')" class="link danger" @click="del(k)">删除</a>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <import-drawer v-if="showImport" @close="showImport = false"></import-drawer>
        <perm-dialog v-if="permItem" :item="permItem" @close="permItem = null"></perm-dialog>

        <div v-if="editItem" class="modal-mask" @click.self="editItem = null">
          <div class="modal">
            <div class="modal-head"><h3>编辑知识单元</h3><a class="x" @click="editItem = null">✕</a></div>
            <div class="form-row"><label>标题</label><input class="ipt" v-model="editForm.title" /></div>
            <div class="form-row"><label>分类</label><input class="ipt" v-model="editForm.category" /></div>
            <div class="form-row"><label>启用</label><input type="checkbox" v-model="editForm.enabled" /></div>
            <div class="modal-foot">
              <button class="btn" @click="editItem = null">取消</button>
              <button class="btn primary" @click="saveEdit">保存</button>
            </div>
          </div>
        </div>

        <div v-if="chunksItem" class="drawer-mask" @click.self="chunksItem = null">
          <div class="drawer">
            <div class="drawer-head"><h3>切片预览 —《{{ chunksItem.title }}》</h3><a class="x" @click="chunksItem = null">✕</a></div>
            <p class="muted">真实实现：每片含稠密 + 稀疏双向量与元数据（编号/标题/分类/权限标签），存于 Milvus kb_chunks。</p>
            <div v-for="c in chunksOf(chunksItem)" :key="c.id" class="chunk-card">
              <div class="chunk-id mono">{{ c.id }}</div>
              <div>{{ c.text }}</div>
            </div>
          </div>
        </div>
      </div>`,
  };

  /* ============================================================
   * OpsView —— 知识沉淀与运营管理（FAQ 候选 / 已发布 / 知识缺口 / 审计）
   * ============================================================ */
  const OpsView = {
    data: () => ({ tab: 'candidates', editCand: null, editForm: null, gapItem: null, gapForm: null }),
    computed: {
      candidates() { return DB.faqCandidates; },
      published() { return [...DB.faqPublished].sort((a, b) => b.publishedAt - a.publishedAt); },
      gaps() { return [...DB.gaps].sort((a, b) => b.freq - a.freq); },
      auditLogs() { return [...DB.logs].slice(-60).reverse(); },
      threshold() { return DB.settings.faqRecommendThreshold; },
    },
    methods: {
      hasBtn, fmtTime,
      kTitle(id) { return (DB.knowledge.find(k => k.id === id) || {}).title || id; },
      uName(id) { return (DB.users.find(u => u.id === id) || {}).name || id; },
      openPublish(c) { this.editCand = c; this.editForm = { question: c.questions[0], answer: c.draftAnswer }; },
      confirmPublish() {
        if (!this.editForm.question.trim() || !this.editForm.answer.trim()) { store.toast('error', '问题与答案不能为空'); return; }
        Services.publishFaq(this.editCand.id, this.editForm);
        this.editCand = null;
        store.toast('ok', 'FAQ 已发布并写入高速缓存；可在问答台提问验证毫秒级直出');
      },
      reject(c) { if (confirm('驳回该推荐 FAQ？')) { Services.rejectFaq(c.id); store.toast('ok', '已驳回'); } },
      openGap(g) { this.gapItem = g; this.gapForm = { title: g.question, category: g.suggestedCategory, global: true, note: '' }; },
      confirmGap() {
        const kid = Services.convertGap(this.gapItem.id, this.gapForm);
        this.gapItem = null;
        store.toast('ok', '已创建知识补全任务并导入《' + this.gapForm.title + '》（含向量化切片），相关提问现在可以被检索命中');
      },
    },
    template: `
      <div class="page">
        <div class="page-head"><h2>知识沉淀与运营管理</h2></div>
        <div class="tabs">
          <a :class="{on: tab==='candidates'}" @click="tab='candidates'">FAQ 挖掘与审核发布 <span class="badge">{{ candidates.filter(c=>c.status==='pending').length }}</span></a>
          <a :class="{on: tab==='published'}" @click="tab='published'">已发布 FAQ 知识库 <span class="badge">{{ published.length }}</span></a>
          <a :class="{on: tab==='gaps'}" @click="tab='gaps'">知识缺口清单 <span class="badge warn">{{ gaps.filter(g=>g.status==='open').length }}</span></a>
          <a v-if="store.user.roleIds.includes('r_admin')" :class="{on: tab==='audit'}" @click="tab='audit'">问答审计日志</a>
        </div>

        <!-- FAQ 候选 -->
        <div v-if="tab==='candidates'" class="grid2">
          <div v-for="c in candidates" :key="c.id" class="card faq-cand" :class="{dim: c.status!=='pending'}">
            <div class="faq-cand-head">
              <span class="tag cluster">聚类问题簇</span>
              <span class="freq" :class="{ok: c.freq >= threshold}">近7日频次 {{ c.freq }}</span>
            </div>
            <ul class="cluster-list"><li v-for="q in c.questions" :key="q">{{ q }}</li></ul>
            <div class="conf-row">置信度 <div class="bar"><div class="bar-in" :style="{width: Math.round(c.confidence*100)+'%'}"></div></div> {{ Math.round(c.confidence*100) }}%</div>
            <div class="muted" v-if="c.relatedKnowledgeIds.length">关联知识：{{ c.relatedKnowledgeIds.map(kTitle).join('、') }}</div>
            <template v-if="c.status==='pending'">
              <template v-if="c.freq >= threshold">
                <textarea class="ipt" rows="4" v-model="c.draftAnswer" placeholder="推荐标准答案（可在线润色）"></textarea>
                <div class="ops-row">
                  <button v-if="hasBtn('ops','faq-publish')" class="btn primary sm" @click="openPublish(c)">✓ 审核并发布上线</button>
                  <button class="btn sm" @click="reject(c)">✕ 驳回</button>
                </div>
              </template>
              <p v-else class="muted">频次未达推荐阈值（{{ threshold }}），持续聚合计数中…</p>
            </template>
            <p v-else class="tag done-tag">{{ { published: '✓ 已发布', rejected: '已驳回' }[c.status] }}</p>
          </div>
          <div v-if="!candidates.length" class="card empty">暂无候选 FAQ，系统持续从问答日志中聚类挖掘</div>
        </div>

        <!-- 已发布 FAQ -->
        <div v-if="tab==='published'" class="card table-card">
          <table>
            <thead><tr><th>标准问题</th><th>标准答案</th><th>缓存生效</th><th>命中次数</th><th>发布时间</th><th>操作</th></tr></thead>
            <tbody>
              <tr v-for="f in published" :key="f.id">
                <td class="strong">{{ f.question }}</td>
                <td class="muted clip">{{ f.answer }}</td>
                <td>
                  <label class="switch"><input type="checkbox" :checked="f.cacheEnabled" :disabled="!hasBtn('ops','cache-toggle')" @change="Services.toggleFaqCache(f.id)" /><i></i></label>
                  <span class="muted">{{ f.cacheEnabled ? '命中直出' : '已停用' }}</span>
                </td>
                <td>{{ f.hitCount }}</td>
                <td class="muted">{{ fmtTime(f.publishedAt) }}</td>
                <td><a class="link danger" @click="DB.faqPublished = DB.faqPublished.filter(x=>x!==f)">删除</a></td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- 知识缺口 -->
        <div v-if="tab==='gaps'" class="card table-card">
          <table>
            <thead><tr><th>未命中提问</th><th>提问部门</th><th>频次</th><th>最高相似度</th><th>建议分类</th><th>状态</th><th>最近提问</th><th>操作</th></tr></thead>
            <tbody>
              <tr v-for="g in gaps" :key="g.id">
                <td class="strong">{{ g.question }}</td>
                <td>{{ g.department }}</td>
                <td><span class="freq" :class="{ok: g.freq>=3}">{{ g.freq }}</span></td>
                <td>{{ Math.round(g.maxScore*100) }}%（低于阈值 {{ Math.round(DB.settings.confThreshold*100) }}%）</td>
                <td>{{ g.suggestedCategory }}</td>
                <td><span class="tag" :class="g.status==='open' ? 'warn-tag' : 'done-tag'">{{ g.status==='open' ? '待补全' : '已建任务' }}</span></td>
                <td class="muted">{{ fmtTime(g.lastAt) }}</td>
                <td><a v-if="g.status==='open' && hasBtn('ops','gap-task')" class="link" @click="openGap(g)">一键转知识补全任务</a></td>
              </tr>
              <tr v-if="!gaps.length"><td colspan="8" class="empty">暂无知识缺口；在问答台提问知识库中不存在的内容（如“海外直邮保税仓清关延误怎么办”）即可触发</td></tr>
            </tbody>
          </table>
        </div>

        <!-- 审计日志（管理员） -->
        <div v-if="tab==='audit'" class="card table-card">
          <p class="muted" style="padding:8px 12px 0">单次问答审计记录：真实实现异步落库，含召回/放行/拦截列表（对应需求 2.9.8 输出格式）</p>
          <table>
            <thead><tr><th>时间</th><th>用户</th><th>提问</th><th>来源</th><th>鉴权放行</th><th>鉴权拦截</th><th>Token</th><th>耗时</th></tr></thead>
            <tbody>
              <tr v-for="(l, i) in auditLogs" :key="i">
                <td class="muted">{{ fmtTime(l.ts) }}</td>
                <td>{{ uName(l.uid) }}</td>
                <td class="clip">{{ l.q }}</td>
                <td><span class="tag" :class="l.source">{{ { 'faq-cache': 'FAQ缓存', 'rag': 'RAG', 'no-result': '未命中' }[l.source] }}</span></td>
                <td><span v-for="id in l.allowedIds" :key="id" class="perm-tag sm dept">{{ kTitle(id) }}</span><span v-if="!l.allowedIds.length" class="muted">—</span></td>
                <td><span v-for="id in l.deniedIds" :key="id" class="perm-tag sm none">{{ kTitle(id) }}</span><span v-if="!l.deniedIds.length" class="muted">—</span></td>
                <td>{{ l.tokens }}</td>
                <td>{{ l.latency }} ms</td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- FAQ 发布确认弹窗 -->
        <div v-if="editCand" class="modal-mask" @click.self="editCand = null">
          <div class="modal">
            <div class="modal-head"><h3>审核发布 FAQ</h3><a class="x" @click="editCand = null">✕</a></div>
            <div class="form-row"><label>标准问题</label><input class="ipt" v-model="editForm.question" /></div>
            <div class="form-row"><label>标准答案</label><textarea class="ipt" rows="5" v-model="editForm.answer"></textarea></div>
            <p class="muted">发布后将注入高速缓存：相似提问毫秒级直出，不再调用大模型。</p>
            <div class="modal-foot">
              <button class="btn" @click="editCand = null">取消</button>
              <button class="btn primary" @click="confirmPublish">确认发布</button>
            </div>
          </div>
        </div>

        <!-- 缺口转任务弹窗 -->
        <div v-if="gapItem" class="modal-mask" @click.self="gapItem = null">
          <div class="modal">
            <div class="modal-head"><h3>转知识补全任务</h3><a class="x" @click="gapItem = null">✕</a></div>
            <div class="form-row"><label>文档标题</label><input class="ipt" v-model="gapForm.title" /></div>
            <div class="form-row"><label>所属分类</label><input class="ipt" v-model="gapForm.category" /></div>
            <div class="form-row"><label>补充说明</label><textarea class="ipt" rows="3" v-model="gapForm.note" placeholder="选填"></textarea></div>
            <div class="form-row"><label>全员公开</label><input type="checkbox" v-model="gapForm.global" /> <span class="muted">开启后所有用户可检索（OR 规则之全局维度）</span></div>
            <p class="muted">演示：确认后模拟“导入文档 → 解析切片 → 向量化入库”完成，缺口关联提问立即变为可命中。</p>
            <div class="modal-foot">
              <button class="btn" @click="gapItem = null">取消</button>
              <button class="btn primary" @click="confirmGap">创建任务并导入</button>
            </div>
          </div>
        </div>
      </div>`,
  };

  /* ============================================================
   * DashboardView —— 运营看板与数据大盘
   * ============================================================ */
  const DashboardView = {
    setup() {
      const c1 = ref(null), c2 = ref(null), c3 = ref(null), c4 = ref(null);
      let charts = [];
      const d = () => Services.dashboard();
      const data = reactive(d());

      function render() {
        Object.assign(data, d());
        const axis = { axisLabel: { color: '#64748b' }, axisLine: { lineStyle: { color: '#e2e8f0' } }, splitLine: { lineStyle: { color: '#f1f5f9' } } };
        charts[0].setOption({
          grid: { left: 50, right: 16, top: 30, bottom: 26 }, tooltip: { trigger: 'axis' },
          xAxis: { type: 'category', data: data.days, ...axis }, yAxis: { type: 'value', ...axis },
          series: [{ name: 'Token 消耗', type: 'line', smooth: true, areaStyle: { opacity: 0.12 }, data: data.dayTokens, itemStyle: { color: '#2563eb' } }, { name: '提问量 PV', type: 'line', smooth: true, data: data.dayPv, itemStyle: { color: '#10b981' } }],
        });
        charts[1].setOption({
          grid: { left: 10, right: 30, top: 10, bottom: 26, containLabel: true }, tooltip: {},
          xAxis: { type: 'value', ...axis }, yAxis: { type: 'category', data: data.topQuestions.map(x => x.q).reverse(), ...axis, splitLine: { show: false } },
          series: [{ type: 'bar', data: data.topQuestions.map(x => x.n).reverse(), itemStyle: { color: '#2563eb', borderRadius: [0, 4, 4, 0] }, barWidth: 14 }],
        });
        charts[2].setOption({
          grid: { left: 10, right: 30, top: 10, bottom: 26, containLabel: true }, tooltip: {},
          xAxis: { type: 'value', ...axis }, yAxis: { type: 'category', data: data.topKnowledge.map(x => x.title).reverse(), ...axis, splitLine: { show: false } },
          series: [{ type: 'bar', data: data.topKnowledge.map(x => x.n).reverse(), itemStyle: { color: '#8b5cf6', borderRadius: [0, 4, 4, 0] }, barWidth: 14 }],
        });
        charts[3].setOption({
          grid: { left: 40, right: 16, top: 30, bottom: 26 }, tooltip: {},
          xAxis: { type: 'category', data: data.latencyDist.map(x => x.label), ...axis }, yAxis: { type: 'value', ...axis },
          series: [{ type: 'bar', data: data.latencyDist.map(x => x.n), itemStyle: { color: '#f59e0b', borderRadius: [4, 4, 0, 0] }, barWidth: 26 }],
        });
      }
      onMounted(() => {
        charts = [echarts.init(c1.value), echarts.init(c2.value), echarts.init(c3.value), echarts.init(c4.value)];
        render();
        window.addEventListener('resize', render);
      });
      watch(() => DB.logs.length, () => render());
      onBeforeUnmount(() => charts.forEach(c => c && c.dispose()));
      return { c1, c2, c3, c4, data };
    },
    template: `
      <div class="page">
        <div class="page-head"><h2>运营看板与数据大盘</h2><span class="muted">数据来自问答流水日志实时聚合（含本次演示产生的问答）</span></div>
        <div class="kpi-grid">
          <div class="card kpi"><div class="kpi-label">今日访问量 PV</div><div class="kpi-val">{{ data.pv }}</div></div>
          <div class="card kpi"><div class="kpi-label">今日独立提问人数 UV</div><div class="kpi-val">{{ data.uv }}</div></div>
          <div class="card kpi"><div class="kpi-label">知识单元总数</div><div class="kpi-val">{{ data.kbTotal }}</div></div>
          <div class="card kpi"><div class="kpi-label">FAQ 缓存命中率</div><div class="kpi-val">{{ data.faqHitRate }}%</div></div>
          <div class="card kpi"><div class="kpi-label">今日 Token 消耗</div><div class="kpi-val">{{ data.tokenToday.toLocaleString() }}</div></div>
          <div class="card kpi"><div class="kpi-label">平均响应延时（RAG）</div><div class="kpi-val">{{ data.avgLat }} <small>ms</small></div></div>
        </div>
        <div class="chart-grid">
          <div class="card"><h3>Token 消耗与提问量趋势（近7日）</h3><div class="chart" ref="c1"></div></div>
          <div class="card"><h3>高频问题 TOP5（近7日）</h3><div class="chart" ref="c2"></div></div>
          <div class="card"><h3>高频引用知识 TOP5</h3><div class="chart" ref="c3"></div></div>
          <div class="card"><h3>响应延时分布（近7日 · RAG）</h3><div class="chart" ref="c4"></div></div>
        </div>
      </div>`,
  };

  /* ============================================================
   * OrgView —— 组织架构与系统配置
   * ============================================================ */
  const OrgView = {
    components: { DeptTree },
    data: () => ({
      activeDept: 'd0',
      deptForm: { id: 'd0', name: '华智科技集团', parentId: null },
      userEdit: null, userForm: null,
      roleTab: 'perm', roleId: 'r_km',
      settings: clone(DB.settings),
    }),
    computed: {
      deptUsers() { return DB.users.filter(u => u.departmentId === this.activeDept); },
      allUsers() { return DB.users; },
      currentRole() { return DB.roles.find(r => r.id === this.roleId); },
      roleButtons() {
        const map = {};
        DB.menus.forEach(m => { map[m.key] = { label: m.label, items: DB.buttonDefs.filter(b => b.menu === m.key) }; });
        return map;
      },
    },
    methods: {
      hasBtn, fmtTime,
      deptName(id) { return (DB.departments.find(d => d.id === id) || {}).name || '—'; },
      roleNames(u) { return u.roleIds.map(r => (DB.roles.find(x => x.id === r) || {}).name).join('、'); },
      selectDept(id) { this.activeDept = id; const d = DB.departments.find(x => x.id === id); this.deptForm = { id: d.id, name: d.name, parentId: d.parentId }; },
      saveDept() {
        if (!this.hasBtn('org', 'dept-manage')) { store.toast('error', '无部门维护权限'); return; }
        Services.upsertDept(this.deptForm); store.toast('ok', '部门已保存');
      },
      addChildDept() {
        const name = prompt('新部门名称（隶属于 ' + this.deptForm.name + '）'); if (!name) return;
        Services.upsertDept({ name, parentId: this.deptForm.id }); store.toast('ok', '已新增子部门');
      },
      delDept() {
        if (this.deptForm.id === 'd0') { store.toast('error', '根部门不可删除'); return; }
        if (DB.departments.some(d => d.parentId === this.deptForm.id)) { store.toast('error', '存在子部门，不可删除'); return; }
        if (DB.users.some(u => u.departmentId === this.deptForm.id)) { store.toast('error', '部门下存在用户，不可删除'); return; }
        Services.deleteDept(this.deptForm.id); this.selectDept('d0'); store.toast('ok', '已删除');
      },
      openUser(u) { this.userEdit = u || {}; this.userForm = u ? { id: u.id, name: u.name, username: u.username, departmentId: u.departmentId, roleIds: [...u.roleIds], enabled: u.enabled } : { name: '', username: '', departmentId: this.activeDept, roleIds: ['r_emp'], enabled: true }; },
      saveUser() {
        if (!this.userForm.name.trim() || !this.userForm.username.trim()) { store.toast('error', '姓名与账号必填'); return; }
        Services.upsertUser(clone(this.userForm)); this.userEdit = null; store.toast('ok', '用户已保存');
      },
      toggleUserEnabled(u) { u.enabled = !u.enabled; store.toast('ok', u.name + (u.enabled ? ' 已启用' : ' 已停用')); },
      toggleRoleMenu(key) {
        const r = this.currentRole;
        r.menus = r.menus.includes(key) ? r.menus.filter(x => x !== key) : r.menus.concat(key);
      },
      toggleRoleBtn(key) {
        const r = this.currentRole;
        r.buttons = r.buttons.includes(key) ? r.buttons.filter(x => x !== key) : r.buttons.concat(key);
      },
      saveSettings() { Object.assign(DB.settings, clone(this.settings)); store.toast('ok', '模型与阈值配置已保存（演示仅前端生效）'); },
    },
    template: `
      <div class="page">
        <div class="page-head"><h2>组织架构与系统配置</h2></div>
        <div class="org-grid">
          <!-- 部门树维护 -->
          <div class="card">
            <h3>部门结构</h3>
            <dept-tree :multiple="false" :active-id="activeDept" @select="selectDept"></dept-tree>
            <div class="dept-form" v-if="deptForm.id !== 'd0' || true">
              <div class="form-row"><label>部门名称</label><input class="ipt" v-model="deptForm.name" /></div>
              <div class="form-row"><label>上级部门</label><span>{{ deptForm.parentId ? deptName(deptForm.parentId) : '（根）' }}</span></div>
              <div class="ops-row">
                <button v-if="hasBtn('org','dept-manage')" class="btn sm primary" @click="saveDept">保存</button>
                <button v-if="hasBtn('org','dept-manage')" class="btn sm" @click="addChildDept">＋ 子部门</button>
                <button v-if="hasBtn('org','dept-manage')" class="btn sm danger" @click="delDept">删除</button>
              </div>
            </div>
          </div>

          <!-- 用户管理 -->
          <div class="card span2">
            <div class="card-head">
              <h3>用户账号（{{ allUsers.length }}）</h3>
              <button v-if="hasBtn('org','user-manage')" class="btn primary sm" @click="openUser(null)">＋ 新增用户</button>
            </div>
            <table>
              <thead><tr><th>姓名</th><th>账号</th><th>部门</th><th>角色</th><th>状态</th><th>操作</th></tr></thead>
              <tbody>
                <tr v-for="u in allUsers" :key="u.id">
                  <td class="strong">{{ u.name }}</td>
                  <td class="mono">{{ u.username }}</td>
                  <td>{{ deptName(u.departmentId) }}</td>
                  <td><span v-for="r in u.roleIds" :key="r" class="tag">{{ roleNames({roleIds:[r]}) }}</span></td>
                  <td><label class="switch"><input type="checkbox" :checked="u.enabled" @change="toggleUserEnabled(u)" /><i></i></label></td>
                  <td><a v-if="hasBtn('org','user-manage')" class="link" @click="openUser(u)">编辑</a></td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- 角色权限 + 模型配置 -->
          <div class="card span2">
            <div class="tabs sub">
              <a :class="{on: roleTab==='perm'}" @click="roleTab='perm'">角色功能权限树</a>
              <a :class="{on: roleTab==='model'}" @click="roleTab='model'">模型服务配置</a>
            </div>
            <template v-if="roleTab==='perm'">
              <div class="form-row"><label>选择角色</label>
                <select class="ipt sel" v-model="roleId">
                  <option v-for="r in DB.roles" :key="r.id" :value="r.id">{{ r.name }}</option>
                </select>
              </div>
              <div class="perm-tree">
                <div v-for="(g, mk) in roleButtons" :key="mk" class="pt-group">
                  <label class="pt-menu"><input type="checkbox" :checked="currentRole.menus.includes(mk)" @change="toggleRoleMenu(mk)" /> <b>{{ g.label }}</b>（菜单）</label>
                  <div class="pt-btns">
                    <label v-for="b in g.items" :key="b.key" class="pt-btn" :class="{off: !currentRole.menus.includes(mk)}">
                      <input type="checkbox" :disabled="!currentRole.menus.includes(mk)" :checked="currentRole.buttons.includes(b.key)" @change="toggleRoleBtn(b.key)" /> {{ b.label }}
                    </label>
                  </div>
                </div>
              </div>
              <p class="muted">改动即时生效：切换到其他角色账号即可验证菜单 / 按钮级权限（如取消知识管理员的「FAQ 审核发布」按钮）。</p>
            </template>
            <template v-else>
              <div class="form-row"><label>API 地址</label><input class="ipt" v-model="settings.apiBase" /></div>
              <div class="form-row"><label>API Key</label><input class="ipt" v-model="settings.apiKey" /></div>
              <div class="form-row"><label>对话模型</label><input class="ipt" v-model="settings.chatModel" /></div>
              <div class="form-row"><label>嵌入模型</label><input class="ipt" v-model="settings.embedModel" /></div>
              <div class="form-row"><label>温度</label><input class="ipt" type="number" step="0.1" v-model="settings.temperature" /></div>
              <div class="form-row"><label>检索 Top-K</label><input class="ipt" type="number" v-model="settings.topK" /></div>
              <div class="form-row"><label>置信度阈值</label><input class="ipt" type="number" step="0.05" v-model="settings.confThreshold" /> <span class="muted">低于该相似度 → 知识缺口</span></div>
              <div class="form-row"><label>FAQ 命中阈值</label><input class="ipt" type="number" step="0.05" v-model="settings.faqHitThreshold" /></div>
              <div class="form-row"><label>FAQ 推荐阈值</label><input class="ipt" type="number" v-model="settings.faqRecommendThreshold" /> <span class="muted">聚类频次达标自动生成候选</span></div>
              <button v-if="hasBtn('org','model-config')" class="btn primary" @click="saveSettings">保存配置</button>
            </template>
          </div>
        </div>

        <!-- 用户编辑弹窗 -->
        <div v-if="userEdit !== null" class="modal-mask" @click.self="userEdit = null">
          <div class="modal">
            <div class="modal-head"><h3>{{ userForm.id ? '编辑用户' : '新增用户' }}</h3><a class="x" @click="userEdit = null">✕</a></div>
            <div class="form-row"><label>姓名</label><input class="ipt" v-model="userForm.name" /></div>
            <div class="form-row"><label>账号</label><input class="ipt" v-model="userForm.username" /></div>
            <div class="form-row"><label>部门</label>
              <select class="ipt sel" v-model="userForm.departmentId">
                <option v-for="d in DB.departments" :key="d.id" :value="d.id">{{ d.name }}</option>
              </select>
            </div>
            <div class="form-row"><label>角色</label>
              <label v-for="r in DB.roles" :key="r.id" class="check-row inline">
                <input type="checkbox" :value="r.id" v-model="userForm.roleIds" /> {{ r.name }}
              </label>
            </div>
            <div class="modal-foot">
              <button class="btn" @click="userEdit = null">取消</button>
              <button class="btn primary" @click="saveUser">保存</button>
            </div>
          </div>
        </div>
      </div>`,
  };

  /* ============================================================
   * GuideDrawer —— 演示剧本（对应 2.9.9 两个示例场景的端到端路径）
   * ============================================================ */
  const GuideDrawer = {
    emits: ['close'],
    methods: {
      loginAs(username) {
        const u = DB.users.find(x => x.username === username);
        store.user = u; DB.sessionUserId = u.id; sessionStorage.setItem('demo_uid', u.id);
        ensureSessions(u); store.view = 'chat';
      },
      go(view, q, username) {
        if (username) this.loginAs(username);
        store.view = view;
        if (q) store.chatDraft = q;
        store.guideOpen = false;
      },
    },
    template: `
      <div class="drawer-mask" @click.self="$emit('close')">
        <div class="drawer">
          <div class="drawer-head"><h3>🎬 端到端演示剧本</h3><a class="x" @click="$emit('close')">✕</a></div>
          <p class="muted">按顺序执行即可走通需求 2.9.9 的两个示例场景。每步点击「执行」自动切换账号 / 页面并填入问题。</p>

          <div class="guide-step"><div class="gs-head"><b>场景一 · 权限隔离</b><span>对应「跨部门财务与薪酬制度问答隔离」</span></div></div>
          <div class="guide-step">
            <div class="gs-head">① 张三提问差旅标准（公开知识，正常回答）</div>
            <p class="muted">《差旅报销标准》为全局公开，应正常召回并附引用溯源。</p>
            <button class="btn sm primary" @click="go('chat', '差旅报销标准是什么？住宿和餐补怎么规定的？', 'zhangsan')">执行</button>
          </div>
          <div class="guide-step">
            <div class="gs-head">② 张三追问高管薪酬（无权限 → 受限提示）</div>
            <p class="muted">该文档仅人力资源部 + 管理层角色可见：检索命中但被鉴权拦截，回答提示“无权查阅”，不泄露内容。</p>
            <button class="btn sm primary" @click="go('chat', '高管薪酬与股权激励是怎么规定的？', 'zhangsan')">执行</button>
          </div>
          <div class="guide-step">
            <div class="gs-head">③ 赵六（管理层）问同一问题（正常回答）</div>
            <p class="muted">同样的问题，有权限的用户正常获得答案 —— 体现“同一知识单元按用户身份动态鉴权”。</p>
            <button class="btn sm primary" @click="go('chat', '高管薪酬与股权激励是怎么规定的？', 'zhaoliu')">执行</button>
          </div>

          <div class="guide-step"><div class="gs-head"><b>场景二 · FAQ 沉淀与缺口闭环</b><span>对应「客服高频退换货问答沉淀」</span></div></div>
          <div class="guide-step">
            <div class="gs-head">④ 李四（知识管理员）发布生鲜退款 FAQ</div>
            <p class="muted">运营页第一条候选：近7日频次 52 达阈值 → 在线润色答案并发布，写入高速缓存。</p>
            <button class="btn sm primary" @click="go('ops', null, 'lisi')">执行</button>
          </div>
          <div class="guide-step">
            <div class="gs-head">⑤ 张三再次提问 → FAQ 缓存毫秒级直出</div>
            <p class="muted">观察步骤条：FAQ 缓存匹配直接命中，跳过检索与生成，耗时仅几十毫秒。</p>
            <button class="btn sm primary" @click="go('chat', '生鲜食品破损如何申请退款？', 'zhangsan')">执行</button>
          </div>
          <div class="guide-step">
            <div class="gs-head">⑥ 张三提问库外问题 → 进入知识缺口</div>
            <p class="muted">知识库中无“保税仓清关延误”内容 → 未命中回答 + 自动记入缺口池。</p>
            <button class="btn sm primary" @click="go('chat', '海外直邮保税仓清关延误怎么办？', 'zhangsan')">执行</button>
          </div>
          <div class="guide-step">
            <div class="gs-head">⑦ 李四在缺口清单一键转补全任务</div>
            <p class="muted">模拟补导文档并入库后，再提问该问题即可被检索命中 —— 沉淀闭环完成。最后可去「运营看板」查看本次演示产生的 PV / Token / 延时变化。</p>
            <button class="btn sm primary" @click="go('ops', null, 'lisi')">执行</button>
          </div>
        </div>
      </div>`,
  };

  /* ============================================================
   * App —— 应用外壳（侧边导航按角色菜单过滤）
   * ============================================================ */
  const App = {
    components: { LoginView, ChatView, KnowledgeView, OpsView, DashboardView, OrgView, GuideDrawer },
    computed: {
      allowedMenus() { return DB.menus.filter(m => hasMenu(m.key)); },
      viewComp() { return { chat: 'ChatView', knowledge: 'KnowledgeView', ops: 'OpsView', dashboard: 'DashboardView', org: 'OrgView' }[store.view] || 'ChatView'; },
      roleName() { return store.user.roleIds.map(r => (DB.roles.find(x => x.id === r) || {}).name).join(' / '); },
      deptName() { return (DB.departments.find(d => d.id === store.user.departmentId) || {}).name; },
    },
    methods: {
      go(key) { store.view = key; },
      logout() { store.user = null; sessionStorage.removeItem('demo_uid'); },
    },
    template: `
      <login-view v-if="!store.user"></login-view>
      <div v-else class="shell">
        <aside class="sidenav">
          <div class="logo">📚 华智智库</div>
          <div class="logo-sub">RAG 知识库管理平台 · 前端 Demo</div>
          <nav>
            <a v-for="m in allowedMenus" :key="m.key" :class="{on: store.view === m.key}" @click="go(m.key)">{{ m.label }}</a>
          </nav>
          <div class="side-foot">
            <button class="btn ghost block" @click="store.guideOpen = true">🎬 端到端演示剧本</button>
            <div class="me">
              <div class="acc-avatar">{{ store.user.name[0] }}</div>
              <div class="me-info">
                <div class="me-name">{{ store.user.name }} <span class="tag">{{ roleName }}</span></div>
                <div class="me-sub">{{ deptName }}</div>
              </div>
            </div>
            <a class="link danger" @click="logout">退出登录</a>
          </div>
        </aside>
        <main class="main">
          <component :is="viewComp"></component>
        </main>
        <guide-drawer v-if="store.guideOpen" @close="store.guideOpen = false"></guide-drawer>
      </div>
      <div class="toasts"><div v-for="t in store.toasts" :key="t.id" class="toast" :class="t.type">{{ t.text }}</div></div>`,
  };

  const app = createApp(App);
  app.component('DeptTree', DeptTree);
  app.mount('#app');
})();
