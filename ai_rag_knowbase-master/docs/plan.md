---
last_updated: 2026-09-18
status: active
---
# ai_0119_rag - 实施计划
> 只记活跃迭代和待办。
---
## 当前活跃：部署配置（Dockerfile / uv / 便携打包）
**目标**：支持把仓库下载到另一台机器一键部署（不再依赖宿主机 uv run），并顺带纠正依赖声明与实际导入不符的问题
**影响文件**：
- `Dockerfile`（新增：python-slim + uv，双服务共用镜像，SLIM 构建参数剔除未使用的重依赖）
- `.dockerignore`（新增：排除 .env / .venv / output / logs / doc / models）
- `.env.example`（新增：全量键名占位，不含真实密钥）
- `deploy/docker-compose.full.yml`（新增：4 个数据服务 + 2 个应用服务，容器内网络改走服务名）
- `scripts/package_release.sh`（新增：产出来源包 tar.gz，排除运行产物与密钥）
- `deploy/README.md`（新增：目标机部署步骤）
**关键发现**：`app/` 对 torch / flagembedding / magic_pdf / unstructured / datasets / transformers 的导入数均为 0（embedding、rerank 已 API 化，MinerU 走 HTTP），故 SLIM 镜像可行
**验收**：
- [x] docker compose config 校验通过（6 服务，容器网络地址替换正确）
- [x] docker build 通过（本机无 buildx，未用 --check，改为真实构建 + 冒烟）——镜像 815 MB
- [x] 瘦依赖集在隔离 venv 中导入双服务通过（import 18 / query 52 路由），容器内同样通过
- [x] 打包产物不含 .env 与运行产物（1.4 MB / 245 文件）
- [x] 容器冒烟：/health 200、/console/ 200、JWT 默认值告警按预期触发

**实施记录（踩坑与修正）**：
- `uv sync --no-install-package torch` 只剔除包本身，torch 的传递依赖（数 GB nvidia-cu12）仍会被安装 → 改为 `scripts/gen_deploy_requirements.py` 做依赖图可达性分析，产出 `deploy/requirements.deploy.txt`（111 包，带上 PEP 508 平台标记）
- 首版打包脚本两个真实缺陷：① tar 排除模式带 `./` 前缀与实际归档路径不匹配 → 误打包 694 MB 的 output/doc/logs；② 安全校验用 `echo "$巨量列表" | grep -q` 在 pipefail 下触发 SIGPIPE，导致「命中禁止项」永远检测不到 → 改为列表落盘后 grep
- `PUBLIC_HOST` 不能放仓库根 .env：compose 的 `${...}` 插值只读与 compose 文件同目录的 `deploy/.env`（env_file 只注入容器内部）→ 已拆分为两份 env 模板并实测两种插值路径
- 锁文件由 Windows 生成，含 pywin32 等平台专属包 → 依赖清单必须保留平台标记，否则 Linux 安装直接失败

---

## 进度总览
| 里程碑 | 状态 | 说明 |
|---|---|---|
| M1 | 进行中 | [首个目标] |
---
## 当前活跃：M1 四维权限引擎
**目标**：权限从角色单维升级为四维（全局/部门/角色/个人，OR 判定、默认拒绝），并贯通到问答管线（无权召回零泄露、明确受限提示）。工单：外层 `.scratch/m1-perm-engine/issues/`；契约：外层 `docs/api-contract.md` §8
**影响文件**：
- `app/infra/security/perm_engine.py`（新增，判引擎）
- `app/infra/persistence/permission_repository.py`（expand：按 knowledge_id 的四维读写）
- 问答管线访问控制服务（M1-05）
**验收**：
- [x] M1-01 四维模型 + OR 判定 + 旧格式兼容（scripts/test_perm_engine.py 17/17）
- [ ] M1-02 台账 / M1-03 权限配置接口 / M1-04 auth-me / M1-05 管线过滤 / M1-06 SSE 事件
---
## 待办 / Backlog
| 优先级 | 功能 | 说明 |
|---|---|---|
---
## 文档同步 TODO
- [ ] 更新 docs/conventions.md
