from app.shared.clients.mongo_history_utils import (
    clear_history_by_user,
    get_all_messages_by_user,
    get_recent_messages_by_user,
    get_top_frequent_questions_by_user,
    get_user_context,
    clear_history,
    get_all_messages,
    get_recent_messages,
    get_session_context,
    save_chat_message,
    update_message_item_names,
    upsert_user_context,
    get_query_cache_entry,
    upsert_query_cache_entry,
    save_import_task,
    get_import_task,
    list_import_tasks,
    delete_import_task,
    upsert_session_context,
)


class HistoryRepository:
    def list_recent_by_user(self, user_id: str, limit: int = 10) -> list[dict]:
        return get_recent_messages_by_user(user_id, limit=limit)

    def top_frequent_questions(self, user_id: str, limit: int = 10) -> list[dict]:
        return get_top_frequent_questions_by_user(user_id, limit=limit)

    def save_message(
        self,
        *,
        session_id: str,
        user_id: str,
        role: str,
        text: str,
        rewritten_query: str = "",
        item_names: list[str] | None = None,
        image_urls: list[str] | None = None,
        citations: list[dict] | None = None,
        message_id: str | None = None,
    ) -> str:
        return save_chat_message(
            session_id=session_id,
            user_id=user_id,
            role=role,
            text=text,
            rewritten_query=rewritten_query,
            item_names=item_names,
            image_urls=image_urls,
            citations=citations,
            message_id=message_id,
        )

    def clear_user(self, user_id: str) -> int:
        return clear_history_by_user(user_id)

    def list_all_by_user(self, user_id: str) -> list[dict]:
        return get_all_messages_by_user(user_id)

    def get_user_context(self, user_id: str) -> dict | None:
        return get_user_context(user_id)

    def save_user_context(self, user_id: str, data: dict) -> bool:
        return upsert_user_context(user_id, data)

    def get_query_cache(self, cache_key: str) -> dict | None:
        return get_query_cache_entry(cache_key)

    def save_query_cache(self, cache_key: str, data: dict) -> bool:
        return upsert_query_cache_entry(cache_key, data)

    def update_item_names(self, ids: list[str], item_names: list[str]) -> int:
        return update_message_item_names(ids, item_names)

    def list_all(self, session_id: str) -> list[dict]:
        return get_all_messages(session_id)

    def get_session_context(self, session_id: str) -> dict | None:
        return get_session_context(session_id)

    def save_session_context(self, session_id: str, data: dict) -> bool:
        return upsert_session_context(session_id, data)


history_repository = HistoryRepository()
