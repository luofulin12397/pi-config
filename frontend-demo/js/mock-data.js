/* ============================================================
 * mock-data.js —— 种子数据
 * 数据结构对齐后端将来的 MongoDB 集合：
 *   departments / users / roles / knowledge / chunks(向量库kb_chunks) /
 *   faq_published / faq_candidates / gaps(知识缺口) / logs(问答流水) / settings(模型与阈值参数)
 * ============================================================ */
(function () {
  // 固定种子伪随机，保证每次刷新看板数据一致
  const rnd = (function (seed) {
    let t = seed;
    return function () {
      t |= 0; t = (t + 0x6D2B79F5) | 0;
      let r = Math.imul(t ^ (t >>> 15), 1 | t);
      r = (r + Math.imul(r ^ (r >>> 7), 61 | r)) ^ r;
      return ((r ^ (r >>> 14)) >>> 0) / 4294967296;
    };
  })(20240917);

  const DAY = 86400000;
  const now = Date.now();

  /* ---------- 四维数据权限核心判定（OR 逻辑，唯一权威实现，services 复用） ---------- */
  // perms: { global, departmentIds[], roleIds[], userIds[] }；默认状态下无任何公开权限
  window.PermCore = {
    hasAccess(user, item) {
      const p = item.perms || {};
      if (p.global) return true;                                    // 全局公开
      if ((p.userIds || []).includes(user.id)) return true;         // 个人专属
      if ((p.departmentIds || []).includes(user.departmentId)) return true; // 直属部门
      if ((p.roleIds || []).some(r => (user.roleIds || []).includes(r))) return true; // 角色
      return false;                                                 // 全部未配置 => 拒绝
    },
  };

  /* ---------- 组织架构 ---------- */
  const departments = [
    { id: 'd0', name: '华智科技集团', parentId: null },
    { id: 'd1', name: '财务部', parentId: 'd0' },
    { id: 'd2', name: '人力资源部', parentId: 'd0' },
    { id: 'd3', name: '业务运营部', parentId: 'd0' },
    { id: 'd4', name: '客服部', parentId: 'd0' },
    { id: 'd5', name: '采购部', parentId: 'd0' },
    { id: 'd9', name: '总经理办公室', parentId: 'd0' },
  ];

  /* ---------- 菜单与按钮权限定义（RBAC 功能权限） ---------- */
  const menus = [
    { key: 'chat', label: 'AI 问答工作台' },
    { key: 'knowledge', label: '知识维护与导入' },
    { key: 'ops', label: '沉淀与运营' },
    { key: 'dashboard', label: '运营看板' },
    { key: 'org', label: '组织与系统配置' },
  ];
  const buttonDefs = [
    { menu: 'chat', key: 'ask', label: '发起提问' },
    { menu: 'knowledge', key: 'import', label: '文档导入' },
    { menu: 'knowledge', key: 'edit', label: '编辑知识' },
    { menu: 'knowledge', key: 'delete', label: '删除知识' },
    { menu: 'knowledge', key: 'perm', label: '权限配置' },
    { menu: 'ops', key: 'faq-publish', label: 'FAQ 审核发布' },
    { menu: 'ops', key: 'cache-toggle', label: '缓存开关控制' },
    { menu: 'ops', key: 'gap-task', label: '缺口转建任务' },
    { menu: 'org', key: 'dept-manage', label: '部门维护' },
    { menu: 'org', key: 'user-manage', label: '用户管理' },
    { menu: 'org', key: 'role-manage', label: '角色授权' },
    { menu: 'org', key: 'model-config', label: '模型配置' },
  ];

  const roles = [
    { id: 'r_emp', name: '普通员工', menus: ['chat'], buttons: ['ask'] },
    { id: 'r_km', name: '知识管理员', menus: ['chat', 'knowledge', 'ops'], buttons: ['ask', 'import', 'edit', 'delete', 'perm', 'faq-publish', 'cache-toggle', 'gap-task'] },
    { id: 'r_admin', name: '系统管理员', menus: ['chat', 'knowledge', 'ops', 'dashboard', 'org'], buttons: buttonDefs.map(b => b.key) },
    { id: 'r_hr', name: 'HR 专员', menus: ['chat'], buttons: ['ask'] },
    { id: 'r_mgmt', name: '管理层', menus: ['chat'], buttons: ['ask'] },
    { id: 'r_cs', name: '客服专员', menus: ['chat'], buttons: ['ask'] },
  ];

  const users = [
    { id: 'u001', name: '张三', username: 'zhangsan', departmentId: 'd3', roleIds: ['r_emp'], enabled: true },   // 业务部普通员工（主演示账号）
    { id: 'u002', name: '李四', username: 'lisi', departmentId: 'd1', roleIds: ['r_km'], enabled: true },        // 财务部知识管理员
    { id: 'u003', name: '王五', username: 'wangwu', departmentId: 'd2', roleIds: ['r_hr'], enabled: true },
    { id: 'u004', name: '赵六', username: 'zhaoliu', departmentId: 'd9', roleIds: ['r_mgmt'], enabled: true },   // 管理层（薪酬权限演示）
    { id: 'u005', name: '系统管理员', username: 'admin', departmentId: 'd9', roleIds: ['r_admin'], enabled: true },
    { id: 'u006', name: '孙七', username: 'sunqi', departmentId: 'd4', roleIds: ['r_cs'], enabled: true },
    { id: 'u007', name: '周八', username: 'zhouba', departmentId: 'd1', roleIds: ['r_emp'], enabled: true },
  ];

  /* ---------- 知识单元台账 + 切片（对应 Milvus kb_chunks） ---------- */
  const P = (o) => Object.assign({ global: false, departmentIds: [], roleIds: [], userIds: [] }, o);
  const knowledge = [
    { id: 'k001', title: '差旅报销标准', format: 'pdf', category: '财务制度', enabled: true, updatedAt: now - 12 * DAY, createdBy: 'u002', perms: P({ global: true }) },
    { id: 'k002', title: '高管薪酬与股权激励细则', format: 'pdf', category: '薪酬福利', enabled: true, updatedAt: now - 6 * DAY, createdBy: 'u002', perms: P({ departmentIds: ['d2'], roleIds: ['r_mgmt'] }) },
    { id: 'k003', title: '员工考勤与假期管理制度', format: 'docx', category: '人事制度', enabled: true, updatedAt: now - 20 * DAY, createdBy: 'u003', perms: P({ global: true }) },
    { id: 'k004', title: '生鲜商品退换货处理规范', format: 'docx', category: '客服规范', enabled: true, updatedAt: now - 3 * DAY, createdBy: 'u006', perms: P({ global: true }) },
    { id: 'k006', title: '客服话术标准手册', format: 'md', category: '客服规范', enabled: true, updatedAt: now - 30 * DAY, createdBy: 'u006', perms: P({ global: true }) },
    { id: 'k007', title: '供应商准入负面清单', format: 'txt', category: '采购管理', enabled: true, updatedAt: now - 2 * DAY, createdBy: 'u002', perms: P({ userIds: ['u002'] }) }, // 个人专属示例
  ];

  const chunks = [
    { id: 'c1-1', kid: 'k001', text: '员工出差住宿报销标准：一线城市（北京、上海、广州、深圳）每晚不超过 500 元，二线城市不超过 380 元；市内交通费凭有效票据实报销，单日上限 100 元。' },
    { id: 'c1-2', kid: 'k001', text: '差旅途餐补贴标准：早餐 20 元、午餐 40 元、晚餐 40 元；报销须在返程后 5 个工作日内在 OA 提交差旅报销申请，并附发票、审批单与行程单。' },
    { id: 'c2-1', kid: 'k002', text: '高管薪酬由基本年薪、绩效年薪与长期激励三部分构成；股权激励计划分四年归属，行权价格为授予日市价的 80%，离职时按归属状态结算。' },
    { id: 'c2-2', kid: 'k002', text: '绩效年薪与公司年度经营 KPI 考核结果挂钩，考核系数区间 0.6 - 1.5；本细则仅限人力资源部及管理层查阅，严禁外传或截屏留存。' },
    { id: 'c3-1', kid: 'k003', text: '年假安排：累计工作满 1 年不满 10 年的年休假 5 天，满 10 年不满 20 年的年休假 10 天；年假原则上当年使用，经审批最多可跨年结转至次年 3 月底。' },
    { id: 'c3-2', kid: 'k003', text: '考勤管理：工作日 9:00 - 18:00，每月补卡不超过 3 次；考勤异常可在 OA 提交申诉，由人力资源部在 3 个工作日内核实处理。' },
    { id: 'c4-1', kid: 'k004', text: '生鲜商品签收后 24 小时内发现破损、变质、腐烂的，客户可凭商品照片在 APP 内申请仅退款；客服审核通过后 1 - 3 个工作日内原路退回，无需退货。' },
    { id: 'c4-2', kid: 'k004', text: '生鲜类投诉处理时效：普通破损 2 小时内响应，重大质量投诉（食品安全）30 分钟内响应并升级至客诉专员，同步冻结同批次库存。' },
    { id: 'c6-1', kid: 'k006', text: '客服开场白标准话术：您好，华智客服工号 XXX 很高兴为您服务；结束语：请对我的服务作出评价。服务过程中禁止使用质问、催促语气。' },
    { id: 'c7-1', kid: 'k007', text: '供应商准入负面清单：存在商业贿赂记录、被列为失信被执行人、近两年发生重大质量安全事故或环保处罚的供应商，实行一票否决，禁止准入与合作。' },
  ];

  /* ---------- FAQ：已发布（缓存）与候选（聚类推荐） ---------- */
  const faqPublished = [
    { id: 'f001', question: '发票开票信息在哪里维护？', answer: '登录 OA 后进入【个人中心 → 发票信息维护】，即可新增或修改开票抬头、税号与邮寄地址；修改后实时生效，无需重新审批。', cacheEnabled: true, hitCount: 26, publishedAt: now - 5 * DAY, confidence: 0.91 },
  ];
  // fc001 的 freq=52 与下方日志中“生鲜退款”提问数一致（真实实现：由日志聚类产出）
  const faqCandidates = [
    { id: 'fc001', questions: ['生鲜食品破损如何申请退款', '买的生鲜坏了怎么退款', '收到的水果烂了怎么申请退款'], freq: 52, relatedKnowledgeIds: ['k004'], draftAnswer: '生鲜商品签收后 24 小时内如发现破损或变质，请直接在 APP 订单页拍照申请"仅退款"，客服审核通过后 1-3 个工作日原路退回，无需退还商品。', confidence: 0.93, status: 'pending' },
    { id: 'fc002', questions: ['年假可以跨年攒吗', '去年年假没休完怎么办'], freq: 11, relatedKnowledgeIds: ['k003'], draftAnswer: '年假原则上当年使用，经部门负责人审批后最多可结转至次年 3 月 31 日，逾期未休按制度清零（特殊岗位另有补偿安排）。', confidence: 0.88, status: 'pending' },
    { id: 'fc003', questions: ['食堂饭卡怎么挂失'], freq: 3, relatedKnowledgeIds: [], draftAnswer: '', confidence: 0.72, status: 'pending' },
  ];

  /* ---------- 问答流水日志（近 7 日，驱动看板与沉淀） ---------- */
  function genLogs() {
    const logs = [];
    const push = (o) => logs.push(Object.assign({ session: 's-' + Math.floor(rnd() * 1e6), allowedIds: [], deniedIds: [] }, o));
    const shengxian = [5, 7, 8, 9, 10, 7, 6]; // 生鲜退款提问按天分布，共 52
    const others = [
      ['打印机怎么连接公司无线网络', null],
      ['客户投诉升级流程是什么', 'k006'],
      ['考勤异常怎么申诉', 'k003'],
      ['报销发票丢失了怎么处理', 'k001'],
      ['供应商准入有什么负面清单要求', 'k007'],
    ];
    const uids = ['u001', 'u006', 'u007', 'u003', 'u004', 'u002'];
    const pickUid = () => uids[Math.floor(rnd() * uids.length)];
    const lat = () => Math.round(1200 + rnd() * 4200);
    const tk = () => Math.round(300 + rnd() * 1300);

    for (let d = 6; d >= 0; d--) {
      const dayStart = now - d * DAY;
      const n = 10 + Math.floor(rnd() * 8);
      for (let i = 0; i < n; i++) {
        const [q, kid] = others[Math.floor(rnd() * others.length)];
        const uid = pickUid();
        const u = users.find(x => x.id === uid);
        const allowed = [], denied = [];
        if (kid) {
          const item = knowledge.find(k => k.id === kid);
          (window.PermCore.hasAccess(u, item) ? allowed : denied).push(kid);
        }
        push({ ts: dayStart - Math.floor(rnd() * DAY * 0.9), uid, q, source: 'rag', latency: lat(), tokens: tk(), allowedIds: allowed, deniedIds: denied });
      }
      for (let i = 0; i < shengxian[6 - d]; i++) {
        push({ ts: dayStart - Math.floor(rnd() * DAY * 0.9), uid: ['u006', 'u001', 'u007'][Math.floor(rnd() * 3)], q: '生鲜食品破损如何申请退款', source: 'rag', latency: lat(), tokens: tk(), allowedIds: ['k004'] });
      }
      const faqN = d >= 5 ? 3 : 4; // 发票问题走 FAQ 缓存直出，共 26 条
      for (let i = 0; i < faqN; i++) {
        push({ ts: dayStart - Math.floor(rnd() * DAY * 0.9), uid: pickUid(), q: '发票开票信息在哪里维护？', source: 'faq-cache', latency: Math.round(60 + rnd() * 120), tokens: 0, faqId: 'f001' });
      }
    }
    // 无权用户追问薪酬 → 鉴权拦截（对应 2.9.9 场景一）
    for (let i = 0; i < 5; i++) {
      push({ ts: now - Math.floor(rnd() * 5 * DAY), uid: rnd() < 0.5 ? 'u001' : 'u006', q: '高管薪酬与股权激励是怎么规定的？', source: 'rag', latency: Math.round(1800 + rnd() * 900), tokens: Math.round(180 + rnd() * 80), deniedIds: ['k002'], blocked: true });
    }
    // 知识管理员凭个人专属权限命中 k007
    for (let i = 0; i < 2; i++) {
      push({ ts: now - Math.floor(rnd() * 2 * DAY), uid: 'u002', q: '供应商准入有什么负面清单要求', source: 'rag', latency: lat(), tokens: tk(), allowedIds: ['k007'] });
    }
    logs.sort((a, b) => a.ts - b.ts);
    return logs;
  }

  /* ---------- 张三的历史会话（演示多轮会话侧边栏） ---------- */
  const seedSessions = {
    u001: [{
      id: 's-seed-1', title: '年假可以跨年保留吗？', createdAt: now - DAY, messages: [
        { role: 'user', text: '年假可以跨年保留吗？' },
        {
          role: 'assistant',
          text: '根据《员工考勤与假期管理制度》：年假原则上当年使用，经部门负责人审批后，最多可跨年结转至**次年 3 月底**，逾期未休部分按制度清零。\n\n> 📌 以上内容引用自《员工考勤与假期管理制度》，请以制度原文为准。',
          refs: [{ kid: 'k003', title: '员工考勤与假期管理制度', score: 0.82, text: chunks[4].text }],
          steps: [], meta: { source: 'rag', latency: 2340, tokens: 456 },
        },
      ],
    }],
  };

  /* ---------- 系统设置（模型参数 + 沉淀阈值，真实实现放配置中心） ---------- */
  const settings = {
    apiBase: 'https://api.example.com/v1',
    apiKey: 'sk-********************（演示脱敏）',
    chatModel: 'qwen-plus',
    embedModel: 'BAAI/bge-m3',
    temperature: 0.3,
    topK: 4,                 // 混合检索召回 Top-K
    confThreshold: 0.25,     // 检索置信度阈值：低于则视为未命中 → 知识缺口
    faqHitThreshold: 0.5,    // FAQ 缓存命中相似度阈值
    faqRecommendThreshold: 10, // 聚类频次达到该值自动生成推荐 FAQ
    suggestPool: [
      '差旅报销标准是什么？住宿和餐补怎么规定的？',
      '高管薪酬与股权激励是怎么规定的？',
      '生鲜食品破损如何申请退款？',
      '年假可以跨年保留吗？',
      '海外直邮保税仓清关延误怎么办？',
      '供应商准入有什么负面清单要求？',
      '发票开票信息在哪里维护？',
    ],
  };

  window.SEED = { departments, menus, buttonDefs, roles, users, knowledge, chunks, faqPublished, faqCandidates, gaps: [], logs: genLogs(), seedSessions, settings };
})();
