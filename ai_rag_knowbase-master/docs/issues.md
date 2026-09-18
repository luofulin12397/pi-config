---
last_updated: 2026-09-16
status: active
---
# 问题记录与经验教训
**查阅规则**：先读索引表，再按 ## ISS-XXX 定位读单条。

| ID | 现象 | 状态 |
|---|---|---|
| ISS-001 | 无图 MD 导入在图片节点崩溃 | 已修复 |
| ISS-002 | LLM 主体名返回带引号（字面 ""）写入 kb_item_names，问答主体确认永远失败 | 已修复 |
**维护规则**：
1. 新 ID = 索引表最大编号 + 1
2. 正文 newest-first
3. 归档阈值：正文 > 200 行或 resolved > 15 条
4. 状态：open / resolved / superseded
5. 经验升级：同类坑第二次踩中 -> 提炼为 conventions 或硬规
## 索引
| ID | 状态 | 一句话 | 位置 |
|---|---|---|---|

## ISS-001
- **现象**：直接上传无图片的 .md 文件导入时，node_md_img 抛 FileNotFoundError（images 目录不存在），导入中断
- **根因**：enrich_markdown_images 用 iterdir() 判空，但目录不存在时会先抛异常；原流程 MD 均由 PDF 转换生成（必然带 images 目录），纯 MD 直传场景未覆盖
- **解决**：先 exists() 再 iterdir()；无目录视为无图片直接放行
- **教训**：文件类节点对"目录/文件不存在"必须显式防御，不能假设上游产物必然存在


## ISS-002
- **现象**：导入成功但问答始终提示"没有识别主体"；Milvus kb_item_names 中 item_name 为字面量 `""`（两个引号字符）
- **根因**：item_name 识别用 StrOutputParser 直接取 LLM 输出，未剥离引号/空白；`if not item_name` 拦不住 `""` 字面量（真值）
- **解决**：识别结果 strip 引号与空白后再判空，空则回退 file_title
- **教训**：LLM 文本输出直接入库前必须 strip + 空值兜底；JSON 模式解析失败时同样需要回退
