# -*- coding: utf-8 -*-
# @Time : 2026/06/13
# @Author : lzm

"""
 @description 答案生成服务：Prompt 拼接、LLM 生成、图片提取、溯源引用、历史写入

 @dependency history_repository, llm_provider, citation_utils

 @output state.answer, state.image_urls, state.citations
"""

import re

from app.infra.llm.providers import llm_provider
from app.infra.persistence.history_repository import history_repository
from app.process.query.agent.state import QueryGraphState
from app.rag.query.citation_utils import append_citations_to_answer, build_citations
from app.shared.runtime.load_prompt import load_prompt
from app.shared.runtime.logger import logger
from app.shared.utils.sse_utils import SSEEvent
from app.shared.utils.task_utils import push_to_session

_IMAGE_EXT = (".jpg", ".png", ".gif", ".jpeg", ".svg", ".webp", ".bmp")
_MD_IMAGE_REG = re.compile(r"\!\[.*?\]\((.*?)\)")
_ANSWER_IMAGE_BLOCK_REG = re.compile(r"【\s*图片\s*】|\[\s*图片\s*\]")
_LOOSE_URL_REG = re.compile(r"(https?://[^\s]+)")


def check_state_has_answer(state):
    """
    检测是否已有前置 answer（追问/拒绝/权限拒绝场景）
    :param state: 查询图状态
    :return: True 表示已有 answer，跳过后续 LLM 生成
    """
    answer = state.get("answer")
    if not answer:
        logger.info("没有 answer，进入正常 RAG 生成流程")
        return False
    if state.get("is_stream"):
        for ch in answer:
            push_to_session(state.get("session_id"), SSEEvent.DELTA, {"delta": ch})
    return True


def _build_history_text(state) -> str:
    """
    构建历史上下文：优先压缩摘要，否则按 user_id 查最近消息
    :param state: 查询图状态
    :return: 历史文本
    """
    history_context = state.get("history_context", "")
    if history_context:
        return history_context

    history = history_repository.list_recent_by_user(state.get("user_id", ""), limit=10)
    final_message_list = [
        item for item in history
        if item.get("item_names") and len(item.get("item_names", [])) > 0
    ]
    if not final_message_list:
        return "没有对话记录!"

    lines = []
    for index, item in enumerate(final_message_list, start=1):
        role_text = "提问" if item["role"] == "user" else "回答"
        content = item["rewritten_query"] if item["role"] == "user" else item["text"]
        lines.append(
            f"序号:{index},类型:{role_text},内容:{content},"
            f"关联主体:{','.join(item['item_names'])}"
        )
    return "\n".join(lines) + "\n"


def get_data_and_validates(state):
    """
    获取并校验生成答案所需参数
    :param state: 查询图状态
    :return: (reranked_docs, history_text, item_names, rewritten_query, denied_item_names)
    """
    reranked_docs = state.get("reranked_docs", [])
    item_names = state.get("item_names", [])
    rewritten_query = state.get("rewritten_query")
    denied_item_names = state.get("denied_item_names", [])

    if not reranked_docs or not item_names or not rewritten_query:
        logger.info("缺少 reranked_docs/item_names/rewritten_query，无法生成答案")
        raise ValueError("缺少 reranked_docs/item_names/rewritten_query，无法生成答案")

    history_text = _build_history_text(state)
    return reranked_docs, history_text, item_names, rewritten_query, denied_item_names


def load_prompt_text(reranker_docs, history_text, item_names, rewritten_query, denied_item_names) -> str:
    """
    拼接 Prompt 上下文（含溯源序号与行号）
    :param reranker_docs: 重排文档列表
    :param history_text: 历史对话文本
    :param item_names: 关联主体
    :param rewritten_query: 改写后问题
    :param denied_item_names: 无权限主体列表
    :return: 完整 Prompt 文本
    """
    context = ""
    ref_index = 0
    for doc in reranker_docs:
        if doc.get("type") == "web":
            ref_index += 1
            context += (
                f"[{ref_index}] 来源: 网络搜索 | 标题: {doc.get('title', '')} | "
                f"reranker模型评分: {doc.get('score')} \n"
                f"内容: {doc.get('text')}\n\n"
            )
            continue
        ref_index += 1
        file_title = doc.get("file_title") or "未知文档"
        start_line = doc.get("start_line")
        end_line = doc.get("end_line")
        if start_line is not None and end_line is not None:
            line_info = f"L{start_line}-L{end_line}" if start_line != end_line else f"L{start_line}"
        else:
            line_info = "行号未知"
        context += (
            f"[{ref_index}] 文档: {file_title} | 行 {line_info} | 标题: {doc.get('title', '')} | "
            f"reranker模型评分: {doc.get('score')} \n"
            f"内容: {doc.get('text')}\n\n"
        )

    denied_text = ",".join(denied_item_names) if denied_item_names else "无"
    return load_prompt(
        "answer_out",
        context=context,
        history=history_text or "没有对话记录!",
        item_names=",".join(item_names),
        question=rewritten_query,
        denied_item_names=denied_text,
    )


def call_llm_generate(answer_prompt_text, state):
    """
    调用 LLM 生成答案
    :param answer_prompt_text: 完整 Prompt
    :param state: 查询图状态
    :return: None，结果写入 state.answer
    """
    llm_client = llm_provider.chat()
    final_answer = ""
    if state.get("is_stream"):
        for chunk in llm_client.stream(answer_prompt_text):
            current_content = chunk.content
            push_to_session(state.get("session_id"), SSEEvent.DELTA, {"delta": current_content})
            final_answer += current_content
    else:
        final_answer = llm_client.invoke(answer_prompt_text).content
    state["answer"] = final_answer


def _is_image_url(url: str) -> bool:
    """
    判断 URL 是否指向图片资源
    :param url: 待检测 URL
    :return: True 表示图片 URL
    """
    u = (url or "").strip()
    if not u:
        return False
    lower = u.lower()
    return any(lower.endswith(ext) or f"{ext}?" in lower or f"{ext}#" in lower for ext in _IMAGE_EXT)


def _extract_loose_urls(text: str) -> list[str]:
    """
    从文本中提取裸 URL
    :param text: 原始文本
    :return: URL 列表
    """
    head_chars = "<([{'\"＜（【["
    tail_chars = ")]}'\">，。,;；]】）＞"
    urls = []
    for raw in _LOOSE_URL_REG.findall(text or ""):
        u = raw.strip().strip(head_chars).rstrip(tail_chars)
        if u:
            urls.append(u)
    return urls


def parse_image_block_from_answer(answer: str) -> list[str]:
    """
    解析 answer 末尾【图片】区块中的 URL
    :param answer: LLM 完整答案
    :return: 图片 URL 列表
    """
    raw = answer or ""
    last_idx, last_len = -1, 0
    for m in _ANSWER_IMAGE_BLOCK_REG.finditer(raw):
        last_idx, last_len = m.start(), len(m.group(0))
    if last_idx == -1:
        return []

    block_text = raw[last_idx + last_len:].strip()
    urls: list[str] = []
    for line in block_text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("http://") or line.startswith("https://"):
            urls.append(line)
        else:
            urls.extend(_extract_loose_urls(line))

    seen: set[str] = set()
    result: list[str] = []
    for u in urls:
        if _is_image_url(u) and u not in seen:
            seen.add(u)
            result.append(u)
    return result


def _merge_image_urls(*sources: list[str]) -> list[str]:
    """
    合并多路图片 URL 并去重
    :param sources: 若干 URL 列表
    :return: 去重后的 URL 列表
    """
    seen: set[str] = set()
    merged: list[str] = []
    for group in sources:
        for url in group or []:
            u = (url or "").strip()
            if u and u not in seen:
                seen.add(u)
                merged.append(u)
    return merged


def extract_image_urls(reranker_docs, state):
    """
    从 reranked_docs 与 answer【图片】区块提取图片 URL
    :param reranker_docs: 重排文档列表
    :param state: 查询图状态
    :return: 更新 image_urls 后的 state
    """
    doc_urls: list[str] = []
    for doc in reranker_docs or []:
        url = doc.get("url", "")
        text = doc.get("text", "")
        if url and _is_image_url(url):
            doc_urls.append(url)
        for image_url in _MD_IMAGE_REG.findall(text or ""):
            if _is_image_url(image_url):
                doc_urls.append(image_url)

    answer_urls = parse_image_block_from_answer(state.get("answer", ""))
    state["image_urls"] = _merge_image_urls(doc_urls, answer_urls)
    logger.info(f"提取图片 URL 数量: {len(state['image_urls'])}")
    return state


def apply_citations(state, reranker_docs):
    """
    构建 citations 并追加引用区块到 answer
    :param state: 查询图状态
    :param reranker_docs: 重排文档列表
    :return: 更新 citations/answer 后的 state
    """
    citations = build_citations(reranker_docs)
    state["citations"] = citations
    citation_block = append_citations_to_answer("", citations)
    if not citation_block:
        return state

    base_answer = state.get("answer") or ""
    state["answer"] = base_answer + citation_block
    if state.get("is_stream"):
        push_to_session(state.get("session_id"), SSEEvent.DELTA, {"delta": citation_block})
    return state


def save_history_message(state):
    """
    写入助手消息到 Mongo chat_message
    :param state: 查询图状态
    :return: None
    """
    history_repository.save_message(
        session_id=state.get("session_id"),
        user_id=state.get("user_id", ""),
        role="assistant",
        text=state.get("answer"),
        rewritten_query=state.get("rewritten_query"),
        item_names=state.get("item_names", []),
        image_urls=state.get("image_urls", []),
        citations=state.get("citations", []),
    )


def generate_answer(state: QueryGraphState) -> QueryGraphState:
    """
    答案生成主流程
    :param state: 查询图状态
    :return: 更新 answer/image_urls/citations 后的 state
    """
    has_answer = check_state_has_answer(state)
    if not has_answer:
        reranker_docs, history_text, item_names, rewritten_query, denied_item_names = get_data_and_validates(state)
        answer_prompt_text = load_prompt_text(
            reranker_docs, history_text, item_names, rewritten_query, denied_item_names
        )
        call_llm_generate(answer_prompt_text, state)
        extract_image_urls(reranker_docs, state)
        apply_citations(state, reranker_docs)
    else:
        state.setdefault("citations", [])
        state.setdefault("image_urls", [])

    save_history_message(state)
    return state
