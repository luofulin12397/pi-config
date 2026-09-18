# -*- coding: utf-8 -*-
"""
TXT / Word 转换服务（M4）：统一转为 Markdown 后复用既有 MD 导入链路。

- .txt：读文本（utf-8 失败回退 gbk），按空行分段落写入 .md
- .docx：python-docx 提取段落；Heading 样式映射为 # 标题，普通段落原样保留

转换产物与源文件同目录（<stem>_converted.md），后续节点（图片处理/切片/向量化）零改动复用。
"""
from __future__ import annotations

from pathlib import Path

from app.shared.runtime.logger import logger


def _read_text_fallback(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        logger.info(f"{path.name} 非 UTF-8，回退 GBK 读取")
        return path.read_text(encoding="gbk")


def txt_to_markdown(path: Path) -> str:
    """TXT → Markdown：原文即纯文本，按空行分段保持可读性。"""
    return _read_text_fallback(path)


def docx_to_markdown(path: Path) -> str:
    """DOCX → Markdown：段落抽取 + 标题样式映射。"""
    from docx import Document

    document = Document(str(path))
    lines: list[str] = []
    for para in document.paragraphs:
        text = (para.text or "").strip()
        if not text:
            continue
        style = (para.style.name or "").lower()
        if style.startswith("heading 1") or style == "title":
            lines.append(f"# {text}")
        elif style.startswith("heading 2"):
            lines.append(f"## {text}")
        elif style.startswith("heading"):
            lines.append(f"### {text}")
        else:
            lines.append(text)
        lines.append("")
    return "\n".join(lines)


def convert_to_markdown(local_file_path: str) -> str:
    """按扩展名转换 TXT/DOCX 为 Markdown 文件，返回生成的 md 路径。"""
    src = Path(local_file_path)
    ext = src.suffix.lower()
    if ext == ".txt":
        content = txt_to_markdown(src)
    elif ext in (".docx", ".doc"):
        if ext == ".doc":
            logger.warning(".doc 为旧版格式，按 TXT 方式尽力读取（建议转存 .docx）")
            content = _read_text_fallback(src)
        else:
            content = docx_to_markdown(src)
    else:
        raise ValueError(f"不支持的转换类型: {ext}")

    out = src.with_name(f"{src.stem}_converted.md")
    out.write_text(content, encoding="utf-8")
    logger.info(f"{src.name} 已转换为 Markdown：{out.name}（{len(content)} 字符）")
    return str(out)
