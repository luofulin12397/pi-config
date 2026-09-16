# -*- coding: utf-8 -*-
# @Time : 2026/06/13
# @Author : lzm

"""
 @description 节点调试延迟工具

 @dependency 无

 @output maybe_node_delay
"""

import os
import time

_SSE_ARTIFICIAL_DELAY: float = float(os.getenv("SSE_ARTIFICIAL_DELAY", "0"))


def maybe_node_delay() -> None:
    """
    按环境变量插入节点间延迟（调试用）
    NODE_DELAY_MS 优先，其次 SSE_ARTIFICIAL_DELAY
    :return: None
    """
    raw = os.getenv("NODE_DELAY_MS", "").strip()
    if raw:
        try:
            time.sleep(int(raw) / 1000.0)
            return
        except ValueError:
            pass
    if _SSE_ARTIFICIAL_DELAY > 0:
        time.sleep(_SSE_ARTIFICIAL_DELAY)
