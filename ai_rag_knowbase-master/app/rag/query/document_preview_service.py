# -*- coding: utf-8 -*-
# @Time : 2026/06/13
# @Author : lzm

"""
 @description 文档原文预览服务

 @dependency permission_repository

 @output get_document_preview / build_preview_html
"""

import html
from pathlib import Path

from fastapi import HTTPException, status

from app.infra.persistence.permission_repository import permission_repository
from app.infra.security.role_utils import ADMIN_ROLE


def _check_doc_access(allowed_roles: list[str], user_roles: list[str]) -> None:
    """
    校验用户是否有文档预览权限
    :param allowed_roles: 文档允许的角色列表
    :param user_roles: 当前用户角色列表
    :return: None，无权限抛 403
    """
    if ADMIN_ROLE in user_roles:
        return
    if not set(user_roles) & set(allowed_roles or []):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权查看该文档")


def _read_md_lines(md_path: str) -> list[str]:
    """
    读取 Markdown 文件所有行
    :param md_path: 文件路径
    :return: 行列表
    """
    path = Path(md_path)
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="源文档不存在")
    return path.read_text(encoding="utf-8", errors="ignore").splitlines()


def get_document_preview(
    *,
    file_title: str,
    user_roles: list[str],
    start_line: int | None = None,
    end_line: int | None = None,
) -> dict:
    """
    获取文档预览数据
    :param file_title: 文档标题
    :param user_roles: 当前用户角色
    :param start_line: 起始行（1-based）
    :param end_line: 结束行（1-based）
    :return: 预览数据字典
    """
    perm = permission_repository.find_latest_by_file_title(file_title)
    if not perm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到文档权限记录")

    _check_doc_access(perm.get("allowed_roles") or [], user_roles)

    md_path = perm.get("source_md_path") or ""
    if not md_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档源路径未配置")

    all_lines = _read_md_lines(md_path)
    total = len(all_lines)

    s = max(1, start_line) if start_line else 1
    e = min(total, end_line) if end_line else total
    if s > e:
        s, e = e, s

    slice_lines = all_lines[s - 1:e]
    content_html = "<br>".join(html.escape(line) for line in slice_lines)

    return {
        "file_title": file_title,
        "content_html": content_html,
        "start_line": s,
        "end_line": e,
        "total_lines": total,
    }


def build_preview_html(data: dict) -> str:
    """
    构建文档预览 HTML 页面
    :param data: get_document_preview 返回的数据
    :return: HTML 字符串
    """
    title = html.escape(data.get("file_title", ""))
    start_line = data.get("start_line")
    end_line = data.get("end_line")
    range_text = f"L{start_line}-L{end_line}" if start_line and end_line else ""
    body = data.get("content_html", "")
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>{title} 原文预览</title>
<style>
body {{ font-family: sans-serif; margin: 24px; line-height: 1.6; }}
h1 {{ font-size: 18px; color: #334155; }}
.meta {{ color: #64748b; font-size: 13px; margin-bottom: 16px; }}
.content {{ background: #f8fafc; padding: 16px; border-radius: 8px; white-space: pre-wrap; }}
</style>
</head>
<body>
<h1>{title}</h1>
<div class="meta">{range_text}</div>
<div class="content">{body}</div>
</body>
</html>"""
