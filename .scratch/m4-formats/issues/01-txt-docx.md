# 01: Word/TXT 解析分支

**Status:** resolved

**What to build:** 导入图入口支持 .txt/.docx：统一转换为 Markdown 后复用既有 MD 链路（图片处理/切片/向量化零改动）。

## 验收
- [x] DOCX 导入（标题样式映射为 # 层级、段落抽取、切片向量化）——实测切 2 片
- [x] TXT 导入（编码回退 utf-8→gbk、分段）——实测切 1 片
- [x] 转换失败/不支持类型进入 failed 状态不静默
- [x] 与四维权限联动：新导入默认拒绝，配置后即可检索（test_m4_formats.py 4/4）

## Comments
- text_convert_service：txt 直读回退编码；docx 用 python-docx（venv 已装）
- 已知边界：旧版 .doc 按 TXT 尽力读取（建议转存 .docx）；MinerU API 的 PDF 链路不受影响
