"""
语义缓存功能集成测试脚本。
运行方式（项目根目录）:
    .venv\\Scripts\\python.exe scripts\\test_semantic_cache.py
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timedelta

# 使用独立测试版本，避免污染生产缓存
TEST_VERSION = "test_semantic_cache_v1"
os.environ.setdefault("KNOWLEDGE_VERSION", TEST_VERSION)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from bson import ObjectId

from app.infra.llm.providers import llm_provider
from app.infra.persistence.qa_cache_repository import qa_cache_repository
from app.process.query.agent.main_graph import query_graph_app
from app.process.query.agent.nodes.node_query_cache import node_query_cache
from app.process.query.agent.nodes.node_save_cache import node_save_cache
from app.process.query.agent.state import create_query_default_state
from app.rag.query.cache_service import lookup_semantic_cache, save_semantic_cache
from app.shared.clients.mongo_history_utils import get_history_mongo_tool
from app.shared.clients.mongo_qa_cache_utils import _get_qa_cache_collection
from app.shared.config.cache_config import cache_config

PASS = 0
FAIL = 0


def ok(name: str, cond: bool, detail: str = ""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}" + (f" — {detail}" if detail else ""))
    else:
        FAIL += 1
        print(f"  [FAIL] {name}" + (f" — {detail}" if detail else ""))


def cleanup_test_cache():
    col = _get_qa_cache_collection()
    result = col.delete_many({"knowledge_version": TEST_VERSION})
    print(f"  清理测试缓存 {result.deleted_count} 条 (version={TEST_VERSION})")


def test_mongo_and_index():
    print("\n=== 1. MongoDB 连接与 TTL 索引 ===")
    tool = get_history_mongo_tool()
    ok("MongoDB 连接", tool.db is not None, f"db={tool.db_name}")

    col = _get_qa_cache_collection()
    indexes = col.index_information()
    ok("expire_time TTL 索引存在", "expire_time_1" in indexes, str(indexes.keys()))
    ok("knowledge_version 索引存在", "knowledge_version_1" in indexes)


def test_repository_crud():
    print("\n=== 2. QaCacheRepository CRUD ===")
    cleanup_test_cache()

    embedding = llm_provider.embed_documents(["怎么上传PDF"])["dense"][0]
    cache_id = qa_cache_repository.save(
        question="怎么上传PDF",
        question_embedding=embedding,
        answer="在导入页面点击上传按钮，选择 PDF 文件即可。",
        knowledge_version=TEST_VERSION,
    )
    ok("写入缓存", bool(cache_id), f"id={cache_id}")

    entries = qa_cache_repository.list_by_version(TEST_VERSION)
    ok("按版本查询", len(entries) == 1, f"count={len(entries)}")
    ok("字段完整", entries[0]["question"] == "怎么上传PDF" and entries[0]["hit_count"] == 0)

    qa_cache_repository.record_hit(cache_id)
    updated = col_find_one(cache_id)
    ok("命中计数更新", updated["hit_count"] == 1, f"hit_count={updated['hit_count']}")
    ok("last_hit_time 已更新", updated.get("last_hit_time") is not None)
    return cache_id, embedding


def col_find_one(cache_id: str):
    return _get_qa_cache_collection().find_one({"_id": ObjectId(cache_id)})


def test_lookup_hit_and_miss():
    print("\n=== 3. 语义缓存查询（命中 / 未命中）===")
    cleanup_test_cache()

    question = "怎么上传PDF文件"
    answer = "进入导入服务，选择 PDF 上传即可。"
    embedding = llm_provider.embed_documents([question])["dense"][0]
    qa_cache_repository.save(
        question=question,
        question_embedding=embedding,
        answer=answer,
        knowledge_version=TEST_VERSION,
    )

    # 相同问题应命中
    state_hit = create_query_default_state(
        session_id=f"test_hit_{uuid.uuid4().hex[:8]}",
        original_query=question,
        is_stream=False,
    )
    cache_config.knowledge_version = TEST_VERSION
    state_hit = lookup_semantic_cache(state_hit)
    ok("相同问题命中缓存", state_hit.get("cache_hit") is True, state_hit.get("answer", "")[:40])
    ok("返回答案正确", state_hit.get("answer") == answer)

    # 完全不同的问题应未命中
    state_miss = create_query_default_state(
        session_id=f"test_miss_{uuid.uuid4().hex[:8]}",
        original_query="量子纠缠的物理本质是什么",
        is_stream=False,
    )
    state_miss = lookup_semantic_cache(state_miss)
    ok("无关问题未命中", state_miss.get("cache_hit") is False)

    # 语义相似问题应命中（BGE-M3 对 paraphrase 通常 > 0.92）
    state_similar = create_query_default_state(
        session_id=f"test_sim_{uuid.uuid4().hex[:8]}",
        original_query="如何上传 PDF 文档",
        is_stream=False,
    )
    state_similar = lookup_semantic_cache(state_similar)
    ok(
        "相似问题命中缓存",
        state_similar.get("cache_hit") is True,
        f"answer={str(state_similar.get('answer', ''))[:30]}",
    )


def test_save_conditions():
    print("\n=== 4. 写入缓存条件判断 ===")
    cleanup_test_cache()
    cache_config.knowledge_version = TEST_VERSION

    # cache_hit=True 时不写入
    s1 = create_query_default_state(
        session_id="test_save_1",
        original_query="测试",
        cache_hit=True,
        answer="已有答案",
        reranked_docs=[{"text": "doc"}],
    )
    save_semantic_cache(s1)
    ok("cache_hit 时跳过写入", len(qa_cache_repository.list_by_version(TEST_VERSION)) == 0)

    # 无 reranked_docs 时不写入
    s2 = create_query_default_state(
        session_id="test_save_2",
        original_query="测试写入",
        cache_hit=False,
        answer="答案内容",
        reranked_docs=[],
        question_embedding=llm_provider.embed_documents(["测试写入"])["dense"][0],
    )
    save_semantic_cache(s2)
    ok("无 reranked_docs 时跳过写入", len(qa_cache_repository.list_by_version(TEST_VERSION)) == 0)

    # 完整 RAG 结果应写入
    s3 = create_query_default_state(
        session_id="test_save_3",
        original_query="HAK180 怎么换电池",
        cache_hit=False,
        answer="打开后盖，取出旧电池，装入新电池。",
        reranked_docs=[{"text": "电池更换步骤", "title": "手册", "score": 0.9, "type": "milvus"}],
        question_embedding=llm_provider.embed_documents(["HAK180 怎么换电池"])["dense"][0],
    )
    save_semantic_cache(s3)
    entries = qa_cache_repository.list_by_version(TEST_VERSION)
    ok("完整 RAG 流程写入缓存", len(entries) == 1, f"question={entries[0]['question'] if entries else 'N/A'}")


def test_image_urls_cache():
    print("\n=== 4b. 图片 URL 写入与命中恢复 ===")
    cleanup_test_cache()
    cache_config.knowledge_version = TEST_VERSION

    question = "HAK180 高级设置与维护"
    answer = (
        "四、高级设置与维护\n"
        "【图片】\n"
        "http://example.com/img-a.jpg\n"
        "http://example.com/img-b.jpg\n"
    )
    image_urls = [
        "http://example.com/img-a.jpg",
        "http://example.com/img-b.jpg",
    ]
    embedding = llm_provider.embed_documents([question])["dense"][0]
    qa_cache_repository.save(
        question=question,
        question_embedding=embedding,
        answer=answer,
        image_urls=image_urls,
        knowledge_version=TEST_VERSION,
    )
    entries = qa_cache_repository.list_by_version(TEST_VERSION)
    ok("qa_cache 写入 image_urls", len(entries[0].get("image_urls") or []) == 2)

    state = create_query_default_state(
        session_id=f"test_img_{uuid.uuid4().hex[:8]}",
        original_query=question,
        is_stream=False,
    )
    state = lookup_semantic_cache(state)
    ok("缓存命中恢复 image_urls", len(state.get("image_urls") or []) == 2)
    ok("image_urls 内容正确", state.get("image_urls") == image_urls)

    # 旧缓存无 image_urls 字段时，从 answer【图片】区块 fallback
    cleanup_test_cache()
    qa_cache_repository.save(
        question=question,
        question_embedding=embedding,
        answer=answer,
        knowledge_version=TEST_VERSION,
    )
    state2 = create_query_default_state(
        session_id=f"test_img_fb_{uuid.uuid4().hex[:8]}",
        original_query=question,
        is_stream=False,
    )
    state2 = lookup_semantic_cache(state2)
    ok("旧缓存 fallback 解析【图片】", len(state2.get("image_urls") or []) == 2)


def test_langgraph_cache_hit_short_circuit():
    print("\n=== 5. LangGraph 缓存命中短路 ===")
    cleanup_test_cache()
    cache_config.knowledge_version = TEST_VERSION

    question = "烫金机 HAK180 怎么用"
    answer = "接通电源，设置温度后即可使用。"
    embedding = llm_provider.embed_documents([question])["dense"][0]
    qa_cache_repository.save(
        question=question,
        question_embedding=embedding,
        answer=answer,
        knowledge_version=TEST_VERSION,
    )

    session_id = f"graph_hit_{uuid.uuid4().hex[:8]}"
    state = create_query_default_state(
        session_id=session_id,
        original_query=question,
        is_stream=False,
    )
    result = query_graph_app.invoke(state)

    ok("图执行 cache_hit=True", result.get("cache_hit") is True)
    ok("图执行返回答案", result.get("answer") == answer)
    ok("跳过后续节点 reranked_docs 为空", len(result.get("reranked_docs") or []) == 0)

    done_nodes = result.get("_done_nodes")  # langgraph may not expose this
    # 通过 state 字段间接验证：item_names 未被 item_name_confirm 填充
    ok("未进入 item_name_confirm（item_names 仍为空）", result.get("item_names") == [])


def test_langgraph_nodes_directly():
    print("\n=== 6. 节点层直接调用 ===")
    cleanup_test_cache()
    cache_config.knowledge_version = TEST_VERSION

    q = "怎么导入知识库文档"
    ans = "访问导入服务 /import 接口上传文件。"
    emb = llm_provider.embed_documents([q])["dense"][0]
    qa_cache_repository.save(
        question=q,
        question_embedding=emb,
        answer=ans,
        knowledge_version=TEST_VERSION,
    )

    state = create_query_default_state(
        session_id=f"node_{uuid.uuid4().hex[:8]}",
        original_query=q,
        is_stream=False,
    )
    state = node_query_cache(state)
    ok("node_query_cache 命中", state.get("cache_hit") is True)

    state = node_save_cache(state)
    entries = qa_cache_repository.list_by_version(TEST_VERSION)
    ok("命中后 node_save_cache 不重复写入", len(entries) == 1 and entries[0]["hit_count"] >= 1)


def main():
    print("=" * 60)
    print("语义缓存集成测试")
    print(f"测试版本: {TEST_VERSION}, 阈值: {cache_config.cache_threshold}")
    print("=" * 60)

    try:
        test_mongo_and_index()
        test_repository_crud()
        test_lookup_hit_and_miss()
        test_save_conditions()
        test_image_urls_cache()
        test_langgraph_cache_hit_short_circuit()
        test_langgraph_nodes_directly()
    finally:
        cleanup_test_cache()

    print("\n" + "=" * 60)
    print(f"测试结果: {PASS} 通过, {FAIL} 失败")
    print("=" * 60)
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
