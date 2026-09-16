/* ============================================================
 * services.js —— 前端模拟服务层（用 mock 实现后端将来要做的逻辑）
 * 每个函数对应需求 2.9.6 的一个后端模块，便于对照分析实现逻辑：
 *   PermCore.hasAccess        → 动态数据权限鉴权引擎
 *   searchChunks              → 知识导入与解析服务产出的向量库 + 混合检索
 *   faqMatch                  → FAQ 高速缓存匹配
 *   runPipeline               → AI 鉴权问答引擎（LangGraph 编排的模拟）
 *   addGap / convertGap       → 知识缺口闭环
 *   logQa / dashboard         → 日志采集与看板服务
 * ============================================================ */
(function () {
  const DAY = 86400000;
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  const rnd = (n) => Math.floor(Math.random() * n);
  const clone = (o) => JSON.parse(JSON.stringify(o));

  /* ---------- 简易相似度：中文 bigram 覆盖率（演示用，真实实现为 bge-m3 向量余弦 + BM25 融合） ---------- */
  // 剔除标点与常见虚词，避免「是什么/怎么办」等词稀释相关度
  const STOP_RE = /[？?！!。，,、：:；;（）()\[\]{}"'“”‘’的是了怎办何如哪嘛吗呢吧啊么样的有和与及或对于在很也非常十分请告诉]/g;
  function bigrams(s) {
    const t = (s || '').toLowerCase().replace(/\s+/g, '').replace(STOP_RE, '');
    const g = new Set();
    for (let i = 0; i < t.length - 1; i++) g.add(t.slice(i, i + 2));
    if (t.length === 1) g.add(t);
    return g;
  }
  // 问题 bigram 在目标文本中的覆盖率（目标文本通常更长，取 |A∩B|/|A|）
  function coverage(question, text) {
    const a = bigrams(question), b = bigrams(text);
    if (!a.size) return 0;
    let hit = 0;
    a.forEach(x => { if (b.has(x)) hit++; });
    return hit / a.size;
  }

  const S = {
    /* ---------- 混合检索模拟：在启用知识单元的切片中找 Top-K ---------- */
    searchChunks(question, topK) {
      const titleOf = (kid) => (DB.knowledge.find(k => k.id === kid) || {}).title || '';
      const enabledIds = new Set(DB.knowledge.filter(k => k.enabled).map(k => k.id));
      const scored = DB.chunks
        .filter(c => enabledIds.has(c.kid))
        .map(c => {
          const cs = coverage(question, c.text);
          const ts = coverage(question, titleOf(c.kid)) * 0.9; // 标题匹配加权
          return { kid: c.kid, title: titleOf(c.kid), text: c.text, score: Math.min(0.98, Math.max(cs, ts)) };
        })
        .filter(c => c.score > 0.12)
        .sort((a, b) => b.score - a.score);
      // 同一知识单元最多取 2 片，避免单文档霸榜
      const perKid = {}, out = [];
      for (const c of scored) {
        perKid[c.kid] = (perKid[c.kid] || 0) + 1;
        if (perKid[c.kid] <= 2) out.push(c);
        if (out.length >= topK) break;
      }
      return out;
    },

    /* ---------- 鉴权过滤：接收用户上下文与候选切片，返回放行/拦截两组 ---------- */
    permFilter(user, candidates) {
      const allowed = [], denied = [];
      for (const c of candidates) {
        const item = DB.knowledge.find(k => k.id === c.kid);
        if (item && window.PermCore.hasAccess(user, item)) allowed.push(c); else denied.push(c);
      }
      return { allowed, denied };
    },

    /* ---------- FAQ 缓存匹配（真实实现：问题向量与 FAQ 向量余弦相似） ---------- */
    faqMatch(question) {
      let best = null;
      for (const f of DB.faqPublished) {
        if (!f.cacheEnabled) continue;
        const sim = Math.max(coverage(question, f.question), coverage(f.question, question));
        if (!best || sim > best.sim) best = { ...f, sim };
      }
      return best && best.sim >= DB.settings.faqHitThreshold ? best : null;
    },

    /* ---------- 问答管线：对应 LangGraph 查询编排的每一步，onStep 驱动 UI 步骤条 ---------- */
    async runPipeline({ user, question, historyRounds, msg }) {
      const st = DB.settings;
      const t0 = Date.now();
      msg.steps = clone(STEPS).map(s => ({ ...s, status: 'pending', detail: '' }));
      const setStep = (key, status, detail) => {
        const s = msg.steps.find(x => x.key === key);
        if (s) { s.status = status; if (detail !== undefined) s.detail = detail; }
      };
      const finish = (extra) => {
        msg.meta = Object.assign({ source: 'rag', latency: Date.now() - t0, tokens: estTokens(question) + estTokens(msg.text) }, extra || {});
        S.logQa({
          ts: Date.now(), uid: user.id, q: question, source: msg.meta.source,
          latency: msg.meta.latency, tokens: msg.meta.tokens,
          allowedIds: (msg.refs || []).map(r => r.kid),
          deniedIds: msg.deniedKids || [], blocked: !!msg.deniedCount, gap: msg.meta.source === 'no-result',
        });
      };

      // 1. FAQ 缓存匹配：命中则跳过检索与生成，毫秒级直出
      setStep('faq', 'running'); await sleep(250 + rnd(350));
      const hit = S.faqMatch(question);
      if (hit) {
        setStep('faq', 'done', '语义命中「' + hit.question + '」（相似度 ' + pct(hit.sim) + '%），跳过检索与生成');
        ['context', 'search', 'auth', 'compose', 'generate'].forEach(k => setStep(k, 'skipped'));
        msg.faq = hit; msg.streaming = true;
        await typeWriter(msg, hit.answer);
        msg.meta = { source: 'faq-cache', latency: Date.now() - t0, tokens: 0 };
        const f = DB.faqPublished.find(x => x.id === hit.id); if (f) f.hitCount++;
        S.logQa({ ts: Date.now(), uid: user.id, q: question, source: 'faq-cache', latency: msg.meta.latency, tokens: 0, faqId: hit.id });
        return;
      }
      setStep('faq', 'done', '未命中缓存，进入 RAG 链路');

      // 2. 多轮上下文：真实实现为 LLM 压缩历史摘要
      setStep('context', 'running'); await sleep(200 + rnd(300));
      setStep('context', 'done', historyRounds > 0 ? '携带 ' + historyRounds + ' 轮历史对话（压缩为摘要后参与检索与 Prompt）' : '首轮提问，无历史上下文');

      // 3. 混合检索（向量召回 + 关键词召回 → 融合）
      setStep('search', 'running'); await sleep(300 + rnd(400));
      const cands = S.searchChunks(question, st.topK);
      const top = cands.length ? cands[0].score : 0;
      setStep('search', 'done', '向量召回 + 关键词召回融合，候选 ' + cands.length + ' 个切片，最高相似度 ' + pct(top) + '%');

      // 4. 四维数据权限鉴权过滤（检索后、拼 Prompt 前）
      setStep('auth', 'running'); await sleep(250 + rnd(300));
      const relevant = cands.filter(c => c.score >= st.confThreshold);
      const { allowed, denied } = S.permFilter(user, relevant);
      msg.deniedKids = [...new Set(denied.map(d => d.kid))];
      if (!relevant.length) {
        setStep('auth', 'done', '无可信切片（最高相似度低于置信度阈值 ' + pct(st.confThreshold) + '%），无需鉴权');
      } else {
        setStep('auth', 'done', '放行 ' + allowed.length + ' 个切片；拦截 ' + denied.length + ' 个（涉及 ' + msg.deniedKids.length + ' 篇无权文档，已按权限隔离）');
      }

      // 5. 提示词组装 + 6. 流式生成
      setStep('compose', 'running'); await sleep(150 + rnd(200));

      // 分支 A：未命中任何可信知识 → 知识缺口
      if (!relevant.length) {
        setStep('compose', 'done', '无可引用内容');
        setStep('generate', 'running');
        const ans = '抱歉，知识库中暂未找到与「' + question + '」直接相关的内容。\n\n该问题已被自动记录到**知识缺口清单**，知识管理员会根据提问频次评估并补充对应文档。您也可以联系相关部门获取人工支持。';
        await typeWriter(msg, ans);
        setStep('generate', 'done');
        msg.meta = {}; finish({ source: 'no-result' });
        S.addGap(question, top, user);
        return;
      }
      // 分支 B：有命中但全部无权 → 明确提示，严禁拼入受限内容
      if (!allowed.length) {
        setStep('compose', 'done', '命中内容均无权限，Prompt 不拼入任何受限切片');
        setStep('generate', 'running');
        const ans = '检测到相关制度文档，但您当前所属部门/角色无权查阅该内容。\n\n如因工作需要访问，请联系知识管理员为您的部门或角色申请对应知识单元的权限。';
        await typeWriter(msg, ans);
        setStep('generate', 'done');
        msg.deniedCount = denied.length;
        finish({ source: 'rag' });
        return;
      }
      // 分支 C：正常生成
      setStep('compose', 'done', '拼入 ' + allowed.length + ' 个有权切片' + (historyRounds ? ' + ' + historyRounds + ' 轮历史摘要' : ''));
      setStep('generate', 'running');
      const ans = composeAnswer(question, allowed, denied);
      await typeWriter(msg, ans);
      setStep('generate', 'done');
      msg.refs = allowed.map(c => ({ kid: c.kid, title: c.title, score: c.score, text: c.text }));
      msg.deniedCount = denied.length;
      finish({ source: 'rag' });
    },

    /* ---------- 知识缺口池：相似问题聚合频次 ---------- */
    addGap(question, maxScore, user) {
      const exist = DB.gaps.find(g => coverage(g.question, question) > 0.8 || coverage(question, g.question) > 0.8);
      const dept = (DB.departments.find(d => d.id === user.departmentId) || {}).name || '';
      if (exist) { exist.freq++; exist.maxScore = Math.max(exist.maxScore, maxScore); exist.lastAt = Date.now(); return; }
      DB.gaps.push({ id: 'g' + Date.now(), question, department: dept, freq: 1, maxScore, status: 'open', createdAt: Date.now(), lastAt: Date.now(), suggestedCategory: guessCategory(question) });
    },
    // 缺口转知识补全任务：通用闭环——模拟管理员补导文档后立即可被检索命中
    convertGap(gapId, form) {
      const g = DB.gaps.find(x => x.id === gapId); if (!g) return;
      const kid = 'k' + Date.now();
      DB.knowledge.push({
        id: kid, title: form.title, format: 'docx', category: form.category, enabled: true,
        updatedAt: Date.now(), createdBy: DB.sessionUserId, perms: { global: !!form.global, departmentIds: [], roleIds: [], userIds: [] },
      });
      DB.chunks.push({ id: kid + '-1', kid, text: '关于「' + g.question + '」的业务说明：' + form.title + '。' + (form.note || '本文档由知识缺口补全任务生成，详细条款由知识管理员维护。') });
      g.status = 'task-created';
      return kid;
    },

    /* ---------- FAQ 审核发布：通过后写入高速缓存 ---------- */
    publishFaq(candId, form) {
      const c = DB.faqCandidates.find(x => x.id === candId); if (!c) return;
      c.status = 'published';
      DB.faqPublished.push({ id: 'f' + Date.now(), question: form.question, answer: form.answer, cacheEnabled: true, hitCount: 0, publishedAt: Date.now(), confidence: c.confidence });
    },
    rejectFaq(candId) { const c = DB.faqCandidates.find(x => x.id === candId); if (c) c.status = 'rejected'; },
    toggleFaqCache(id) { const f = DB.faqPublished.find(x => x.id === id); if (f) f.cacheEnabled = !f.cacheEnabled; },

    /* ---------- 知识单元管理 ---------- */
    setPerm(id, perms) { const k = DB.knowledge.find(x => x.id === id); if (k) k.perms = perms; },
    updateKnowledge(id, patch) { const k = DB.knowledge.find(x => x.id === id); if (k) Object.assign(k, patch, { updatedAt: Date.now() }); },
    deleteKnowledge(id) {
      DB.knowledge = DB.knowledge.filter(x => x.id !== id);
      DB.chunks = DB.chunks.filter(c => c.kid !== id);
    },
    // 模拟导入完成：真实实现为异步管线（清洗→分块→嵌入→入库），此处直接产出切片
    addImported(title, ext) {
      const kid = 'k' + Date.now();
      const fmt = { pdf: 'pdf', md: 'md', doc: 'docx', docx: 'docx', txt: 'txt' }[ext] || 'txt';
      DB.knowledge.push({
        id: kid, title, format: fmt, category: '未分类', enabled: true, updatedAt: Date.now(),
        createdBy: DB.sessionUserId, perms: { global: false, departmentIds: [], roleIds: [], userIds: [] }, // 默认无任何公开权限
      });
      DB.chunks.push({ id: kid + '-1', kid, text: '《' + title + '》总体要求与适用范围：本制度适用于集团全体员工，自发布之日起施行，由归口管理部门负责解释与修订。' });
      DB.chunks.push({ id: kid + '-2', kid, text: '《' + title + '》正文条款由导入服务自动解析切片生成；如需调整分块粒度，可在知识详情中重新切片并向量化。' });
      return kid;
    },

    /* ---------- 日志与看板聚合 ---------- */
    logQa(entry) { DB.logs.push(entry); },
    dashboard() {
      const dayStart = new Date(); dayStart.setHours(0, 0, 0, 0);
      const today = DB.logs.filter(l => l.ts >= dayStart.getTime());
      const week = DB.logs.filter(l => l.ts >= Date.now() - 7 * DAY);
      const uv = new Set(today.map(l => l.uid)).size;
      const faqHits = today.filter(l => l.source === 'faq-cache').length;
      const ragToday = today.filter(l => l.source === 'rag');
      const avgLat = ragToday.length ? Math.round(ragToday.reduce((s, l) => s + l.latency, 0) / ragToday.length) : 0;
      // 按天 Token 趋势
      const days = [], dayTokens = [], dayPv = [];
      for (let d = 6; d >= 0; d--) {
        const s0 = new Date(); s0.setHours(0, 0, 0, 0); const start = s0.getTime() - d * DAY, end = start + DAY;
        const ls = DB.logs.filter(l => l.ts >= start && l.ts < end);
        days.push((new Date(start)).getMonth() + 1 + '/' + (new Date(start)).getDate());
        dayTokens.push(ls.reduce((s, l) => s + (l.tokens || 0), 0));
        dayPv.push(ls.length);
      }
      // 高频问题 TOP5（真实实现为语义聚类后按簇聚合；demo 按原文聚合）
      const qMap = {};
      week.forEach(l => { qMap[l.q] = (qMap[l.q] || 0) + 1; });
      const topQuestions = Object.entries(qMap).sort((a, b) => b[1] - a[1]).slice(0, 5).map(([q, n]) => ({ q, n }));
      // 热门知识 TOP5（被引用次数）
      const kMap = {};
      week.forEach(l => (l.allowedIds || []).forEach(id => { kMap[id] = (kMap[id] || 0) + 1; }));
      const topKnowledge = Object.entries(kMap).sort((a, b) => b[1] - a[1]).slice(0, 5)
        .map(([kid, n]) => ({ title: (DB.knowledge.find(k => k.id === kid) || {}).title || kid, n }));
      // 延时分布
      const buckets = [[0, 1000, '<1s'], [1000, 2000, '1-2s'], [2000, 3000, '2-3s'], [3000, 5000, '3-5s'], [5000, Infinity, '>5s']];
      const latencyDist = buckets.map(b => ({ label: b[2], n: week.filter(l => l.source === 'rag' && l.latency >= b[0] && l.latency < b[1]).length }));
      return {
        pv: today.length, uv, kbTotal: DB.knowledge.filter(k => k.enabled).length,
        faqHitRate: today.length ? Math.round(faqHits / today.length * 100) : 0,
        avgLat, tokenToday: today.reduce((s, l) => s + (l.tokens || 0), 0),
        gapOpen: DB.gaps.filter(g => g.status === 'open').length,
        days, dayTokens, dayPv, topQuestions, topKnowledge, latencyDist,
      };
    },

    /* ---------- 组织管理 ---------- */
    upsertUser(form) {
      if (form.id) { Object.assign(DB.users.find(u => u.id === form.id), form); }
      else DB.users.push(Object.assign({ id: 'u' + Date.now(), enabled: true }, form));
    },
    upsertDept(form) {
      if (form.id) { const d = DB.departments.find(x => x.id === form.id); if (d) d.name = form.name; }
      else DB.departments.push({ id: 'd' + Date.now(), name: form.name, parentId: form.parentId });
    },
    deleteDept(id) { DB.departments = DB.departments.filter(d => d.id !== id); },
    updateRole(id, patch) { const r = DB.roles.find(x => x.id === id); if (r) Object.assign(r, patch); },
  };

  /* ---------- 管线步骤定义（与将来 LangGraph 节点一一对应） ---------- */
  const STEPS = [
    { key: 'faq', label: 'FAQ 缓存匹配' },
    { key: 'context', label: '多轮上下文处理' },
    { key: 'search', label: '混合检索（向量+关键词）' },
    { key: 'auth', label: '四维数据权限鉴权' },
    { key: 'compose', label: '提示词组装' },
    { key: 'generate', label: '大模型流式生成' },
  ];

  const pct = (v) => Math.round((v || 0) * 100);
  const estTokens = (s) => Math.round((s || '').length / 1.6);

  async function typeWriter(msg, text) {
    msg.streaming = true; msg.text = '';
    const step = Math.max(1, Math.round(text.length / 140));
    for (let i = 0; i < text.length; i += step) {
      msg.text += text.slice(i, i + step);
      await sleep(12 + Math.random() * 18);
    }
    msg.text = text; msg.streaming = false;
  }

  function composeAnswer(question, allowed, denied) {
    let out = '根据知识库资料，为您解答「' + question + '」：\n\n';
    allowed.slice(0, 3).forEach((c, i) => {
      out += '**' + (i + 1) + '. ' + c.title + '**\n' + c.text + '\n\n';
    });
    out += '> 📌 以上内容引用自 ' + [...new Set(allowed.map(c => '《' + c.title + '》'))].join('、') + '，请以制度原文为准。';
    if (denied.length) {
      out += '\n\n> ⚠️ 检测到相关制度文档，但您当前所属部门/角色无权查阅该内容，部分参考资料已按权限过滤。';
    }
    return out;
  }

  function guessCategory(q) {
    if (/退款|退货|破损|投诉/.test(q)) return '客服规范';
    if (/报销|差旅|发票/.test(q)) return '财务制度';
    if (/年假|考勤|薪酬|入职/.test(q)) return '人事制度';
    if (/清关|物流|直邮|保税/.test(q)) return '物流运营';
    return '未分类';
  }

  window.Services = S;
  window.STEPS = STEPS;
})();
