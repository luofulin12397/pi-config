# 02: 知识单元台账

**What to build:** 导入完成的文档自动登记为知识单元；管理员可列表查看（编号/标题/格式/分类/切片数/启停/更新时间）、编辑标题与分类、启停、删除。删除需同步清理向量索引，停用后问答检索不再命中。台账接口同时为 M1-03 的权限配置与标签展示提供挂载点。

**Blocked by:** None (can start immediately)

**Status:** claimed

- [ ] 导入一篇文档完成后，台账列表出现该知识单元（代码完成，待集成验证）
- [ ] 编辑标题/分类、启停即时生效；停用后检索不可命中（代码完成，待集成验证）
- [ ] 删除后台账与向量库均不可再检索到（代码完成，待集成验证）

## Comments

- 代码交付（后端仓库 448d02c）：knowledge_repository（file_title 派生 kid 幂等、编辑白名单、停用清单）+ 导入图登记 + 双检索服务停用过滤 + admin_routes（require_admin，删除同步清 Milvus）
- 已验证：9 文件 py_compile、perm_engine 回归 17/17
- 待验证：接口行为需 Mongo+Milvus+LLM 联调环境（.env 的 API key 指向原环境，需提供有效 key）；验证通过后再置 resolved
