# -*- coding: utf-8 -*-
# @Time : 2026/06/13
# @Author : lzm

"""
 @description 文档预览响应模型

 @dependency pydantic

 @output DocumentPreviewResponse
"""

from pydantic import BaseModel


class DocumentPreviewResponse(BaseModel):
    file_title: str
    content_html: str
    start_line: int | None = None
    end_line: int | None = None
    total_lines: int = 0
