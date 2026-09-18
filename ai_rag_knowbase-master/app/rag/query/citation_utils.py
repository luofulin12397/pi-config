# -*- coding: utf-8 -*-
# @Time : 2026/06/13
# @Author : lzm

"""
 @description 回答溯源引用构建工具

 @dependency 无

 @output build_citations / append_citations_to_answer
"""


def _format_page(start_line, end_line) -> str:
    """
    格式化行号展示文本
    :param start_line: 起始行
    :param end_line: 结束行
    :return: 行号字符串
    """
    if start_line is None or end_line is None:
        return ""
    if start_line == end_line:
        return f"L{start_line}"
    return f"L{start_line}-L{end_line}"


def build_citations(reranked_docs: list[dict]) -> list[dict]:
    """
    从重排文档构建 citations 列表（对齐前端 updateRefs）
    :param reranked_docs: 重排后的文档列表
    :return: citations 列表
    """
    citations: list[dict] = []
    seen: set[str] = set()

    for doc in reranked_docs or []:
        doc_type = doc.get("type", "milvus")
        if doc_type == "web":
            url = doc.get("url") or ""
            key = f"web:{url}"
            if not url or key in seen:
                continue
            seen.add(key)
            citations.append({
                "type": "web",
                "name": doc.get("title") or "网络搜索",
                "title": doc.get("title") or "",
                "url": url,
                "score": doc.get("score"),
            })
            continue

        chunk_id = doc.get("chunk_id") or ""
        file_title = doc.get("file_title") or "未知文档"
        key = chunk_id or f"{file_title}:{doc.get('start_line')}:{doc.get('end_line')}"
        if key in seen:
            continue
        seen.add(key)

        start_line = doc.get("start_line")
        end_line = doc.get("end_line")
        page = _format_page(start_line, end_line)
        citations.append({
            "type": "milvus",
            "name": file_title,
            "file_title": file_title,
            "title": doc.get("title") or doc.get("parent_title") or "",
            "parent_title": doc.get("parent_title") or "",
            "part": doc.get("part") or "",
            "item_name": doc.get("item_name") or "",
            "page": page,
            "start_line": start_line,
            "end_line": end_line,
            "score": doc.get("score"),
        })

    return citations


def append_citations_to_answer(answer: str, citations: list[dict]) -> str:
    """
    将引用来源格式化为文本块追加到答案末尾
    :param answer: 原始答案（此处未使用，保留签名兼容）
    :param citations: 引用列表
    :return: 引用文本块，无引用时返回空字符串
    """
    if not citations:
        return ""

    lines = ["\n\n【引用来源】"]
    for idx, c in enumerate(citations, start=1):
        if c.get("type") == "web":
            lines.append(f"{idx}. [网络] {c.get('title') or c.get('name', '')}")
            if c.get("url"):
                lines.append(f"   {c['url']}")
            continue
        file_title = c.get("file_title") or c.get("name") or "未知文档"
        title = c.get("title") or ""
        page = c.get("page") or ""
        page_part = f" ({page})" if page else ""
        title_part = f" - {title}" if title else ""
        lines.append(f"{idx}. {file_title}{title_part}{page_part}")

    return "\n".join(lines)
