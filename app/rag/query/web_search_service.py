import asyncio
import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

from agents.mcp import MCPServerStreamableHttp

from app.process.query.agent.state import QueryGraphState
from app.shared.runtime.logger import logger, step_log
from app.infra.config.providers import infra_config

_MCP_TIMEOUT_SECONDS = 310


def _run_coro_in_new_loop(coro):
    """在独立线程的新事件循环中运行协程，避免 LangGraph 并发节点内 asyncio 冲突。"""

    def _runner():
        return asyncio.run(coro)

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_runner)
        return future.result(timeout=_MCP_TIMEOUT_SECONDS)


@step_log("get_rewritten_query_and_validate")
def get_rewritten_query_and_validate(state) -> str:
    rewritten_query = state.get("rewritten_query")
    if not rewritten_query:
        logger.error("rewritten_query没有内容,业务无法继续进行!")
        raise ValueError("rewritten_query没有内容,业务无法继续进行!")
    return rewritten_query


@step_log("web_search_docs")
async def web_search_docs(rewritten_query: str):
    mcp_server = MCPServerStreamableHttp(
        name="web_search_mcp",
        client_session_timeout_seconds=300,
        params={
            "url": infra_config.mcp.mcp_base_url,
            "headers": {"Authorization": f"Bearer {infra_config.mcp.api_key}"},
            "timeout": 300,
        },
        cache_tools_list=True,
        max_retry_attempts=3,
    )
    try:
        await mcp_server.connect()
        tool_list = await mcp_server.list_tools()
        logger.info(f"本次链接服务对应的工具列表:{tool_list}")
        return await mcp_server.call_tool(
            tool_name="bailian_web_search",
            arguments={"query": rewritten_query, "count": 5},
        )
    except Exception:
        logger.exception(f"调用 MCP 网络搜索失败, query={rewritten_query}")
        return None
    finally:
        try:
            await mcp_server.cleanup()
        except Exception:
            logger.warning("MCP cleanup 失败，已忽略")


def _parse_mcp_result(mcp_result) -> list[dict]:
    if not mcp_result or not getattr(mcp_result, "content", None):
        return []
    search_text = mcp_result.content[0].text
    if not search_text:
        return []
    pages = json.loads(search_text).get("pages", [])
    return pages if isinstance(pages, list) else []


@step_log("search_by_web")
def search_by_web(state: QueryGraphState) -> list[dict]:
    """
    网络搜索服务：MCP 调用失败时返回空列表，不阻断主 RAG 流程。
    """
    rewritten_query = get_rewritten_query_and_validate(state)

    if not infra_config.mcp.mcp_base_url or not infra_config.mcp.api_key:
        logger.warning("MCP 未配置(MCP_DASHSCOPE_BASE_URL / OPENAI_API_KEY_Q)，跳过网络搜索")
        return []

    try:
        mcp_result = _run_coro_in_new_loop(web_search_docs(rewritten_query))
    except FuturesTimeoutError:
        logger.error(f"网络搜索超时({_MCP_TIMEOUT_SECONDS}s): {rewritten_query}")
        return []
    except Exception:
        logger.exception(f"网络搜索线程执行失败: {rewritten_query}")
        return []

    try:
        web_search_docs_list = _parse_mcp_result(mcp_result)
        logger.info(f"{rewritten_query} 联网查询结果数量: {len(web_search_docs_list)}")
        return web_search_docs_list
    except Exception:
        logger.exception(f"解析网络搜索结果失败: {rewritten_query}")
        return []
