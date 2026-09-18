---
last_updated: 2026-07-17
status: active
owner: developer
harness_version: 4
---
# ai_0119_rag - Agent Guidelines
## 项目简介
RAG 知识库系统 — 基于 FastAPI + LangChain + LangGraph + Milvus + MongoDB 的知识问答平台
## 快速导航
| 你想做什么 | 去哪里看 | 加载 |
|---|---|---|
| 当前迭代 / 活跃待办 | `docs/plan.md` | 常读 |
| 历史已完成 / 已废弃方案 | `docs/plan-archive.md` | 默认不读 |
| 详细架构 | `docs/architecture.md` | 按需 |
| 编码约定 | `docs/conventions.md` | 按需 |
| 踩坑记录（ISS-XXX） | `docs/issues.md` | 按需 |
| 已归档的历史 ISS | `docs/issues-archive.md` | 默认不读 |
| 产品视图（面向 PM） | `docs/pm-overview.md` | 按需 |
> `docs/` 允许按主题增设子目录；新增即按 HM1 补导航行。
> 查 `issues.md` 先读头部索引表，再按 `## ISS-XXX` 定位读单条。
---
## 硬性规则（编号化）
### WF - 工作流 (Workflow)
- **WF1** > 5 个文件或非一行改动，先更新 `docs/plan.md` 再动手
- **WF2** 解决一个非平凡 bug 后立即追加 `docs/issues.md` 一条 ISS-XXX
- **WF3** 改动 > 500 行后主动问用户经验
- **WF4** 破坏性改动用 worktree 隔离
- **WF5** 宣称完成前必须先运行验证命令
- **WF6** 代码有显著变更（新增模块 / 重构 / 修改 API 边界）后，考虑运行 `openwiki --update` 同步代码文档
### HM - Harness 维护
- **HM1** 新增/移动 docs 文件 -> 更新快速导航表
- **HM2** 修改 docs -> 更新 frontmatter last_updated
- **HM3** 项目定位变化 -> 更新项目简介
- **HM4** 只写绝对日期 YYYY-MM-DD
- **HM5** docs/ 不引用仓库外路径
- **HM6** 问题状态的唯一权威是 docs/issues.md
- **HM7** 常载预算：AGENTS.md <= 150 行
---
## 提交规范
feat:/fix:/docs:/refactor:/chore + 中文描述
---
## 技术栈
python, langchain, fastapi
---
## 项目目录
```
[粘贴项目目录树]
```
---
## 常用命令
```bash
[dev / build / lint / start / stop / deploy]
```
