"""Saved AI chat conversations: storage helpers and the list/open/clear endpoints.

A conversation keeps a snapshot of the chart it was about, so continuing it later
answers from the same chart even if the user has since calculated someone else's.
Every query is scoped to the owning user. A conversation is only listed once it
has a finished turn.
"""
import json
import zlib

from fastapi import APIRouter, HTTPException, Request

from src.core.config import (
    CHAT_MAX_CONVERSATIONS,
    CHAT_MAX_STORED_CHART_BYTES,
    DB_PATH,
    connect_db,
)
from src.api.deps import _session_user_or_401, logger

router = APIRouter()

_TITLE_CHARS = 80


def encode_chart(chart):
    """Compress a chart for storage. A chart too large to be real is refused, so
    call this before charging for the turn."""
    raw = json.dumps(chart).encode("utf-8")
    if len(raw) > CHAT_MAX_STORED_CHART_BYTES:
        raise HTTPException(status_code=413, detail="Chart data is too large to save with this chat.")
    return zlib.compress(raw)


def _title_from(query):
    text = " ".join((query or "").split())
    return text if len(text) <= _TITLE_CHARS else text[:_TITLE_CHARS].rstrip() + "…"


def _open_for_delete():
    conn = connect_db(DB_PATH)
    # Overwrite deleted rows, so cleared chats don't linger in the database file.
    conn.execute("PRAGMA secure_delete=ON;")
    return conn


def _delete_rows(conn, conversation_ids):
    if not conversation_ids:
        return
    marks = ",".join("?" * len(conversation_ids))
    conn.execute(f"DELETE FROM chat_messages WHERE conversation_id IN ({marks})", conversation_ids)
    conn.execute(f"DELETE FROM chat_conversations WHERE id IN ({marks})", conversation_ids)


def create_conversation(user_id, query, client_name, place_name, chart_blob, lang):
    """Start a conversation. Also removes this user's abandoned empty conversations
    and those beyond the per-user limit."""
    conn = _open_for_delete()
    try:
        cursor = conn.execute(
            "INSERT INTO chat_conversations (user_id, title, client_name, place_name, chart_blob, lang) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, _title_from(query), client_name or "", place_name or "", chart_blob, lang),
        )
        conversation_id = cursor.lastrowid
        # An empty one may be a first turn still streaming in another tab, so only
        # remove those that have clearly been abandoned.
        empty = [r[0] for r in conn.execute(
            "SELECT c.id FROM chat_conversations c WHERE c.user_id = ? AND c.id != ? "
            "AND c.created_at < datetime('now', '-1 hour') "
            "AND NOT EXISTS (SELECT 1 FROM chat_messages m WHERE m.conversation_id = c.id)",
            (user_id, conversation_id),
        )]
        _delete_rows(conn, empty)
        excess = [r[0] for r in conn.execute(
            "SELECT id FROM chat_conversations WHERE user_id = ? AND id != ? "
            "ORDER BY updated_at DESC, id DESC LIMIT -1 OFFSET ?",
            (user_id, conversation_id, max(CHAT_MAX_CONVERSATIONS - 1, 0)),
        )]
        _delete_rows(conn, excess)
        conn.commit()
        return conversation_id
    finally:
        conn.close()


def load_conversation(user_id, conversation_id):
    """The user's conversation including its chart, or None if it isn't theirs."""
    conn = connect_db(DB_PATH)
    try:
        row = conn.execute(
            "SELECT id, title, client_name, place_name, chart_blob, lang, comparison_ids, updated_at "
            "FROM chat_conversations WHERE id = ? AND user_id = ?",
            (conversation_id, user_id),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    chart = json.loads(zlib.decompress(row[4])) if row[4] else None
    return {
        "id": row[0], "title": row[1], "client_name": row[2], "place_name": row[3],
        "chart": chart, "lang": row[5], "comparison_ids": json.loads(row[6] or "[]"),
        "updated_at": row[7],
    }


def recent_messages(conversation_id, limit):
    """The latest `limit` messages, oldest first."""
    conn = connect_db(DB_PATH)
    try:
        rows = conn.execute(
            "SELECT role, content FROM chat_messages WHERE conversation_id = ? "
            "ORDER BY id DESC LIMIT ?",
            (conversation_id, limit),
        ).fetchall()
    finally:
        conn.close()
    return [{"role": role, "content": content} for role, content in reversed(rows)]


def save_turn(conversation_id, query, reply, meta=None, comparison_ids=()):
    """Store one finished question and answer. Does nothing if the conversation was
    deleted while the answer was streaming."""
    conn = connect_db(DB_PATH)
    try:
        updated = conn.execute(
            "UPDATE chat_conversations SET updated_at = CURRENT_TIMESTAMP, comparison_ids = ? WHERE id = ?",
            (json.dumps(list(comparison_ids)), conversation_id),
        )
        if updated.rowcount == 0:
            return
        conn.execute(
            "INSERT INTO chat_messages (conversation_id, role, content) VALUES (?, 'user', ?)",
            (conversation_id, query),
        )
        conn.execute(
            "INSERT INTO chat_messages (conversation_id, role, content, meta) VALUES (?, 'assistant', ?, ?)",
            (conversation_id, reply, json.dumps(meta) if meta else None),
        )
        conn.commit()
    finally:
        conn.close()


@router.get("/api/ai-chat/conversations")
def list_conversations(request: Request):
    user = _session_user_or_401(request)
    conn = connect_db(DB_PATH)
    try:
        rows = conn.execute(
            "SELECT c.id, c.title, c.client_name, c.updated_at, COUNT(m.id) "
            "FROM chat_conversations c JOIN chat_messages m ON m.conversation_id = c.id "
            "WHERE c.user_id = ? GROUP BY c.id ORDER BY c.updated_at DESC, c.id DESC",
            (user["id"],),
        ).fetchall()
    finally:
        conn.close()
    return {"conversations": [
        {"id": r[0], "title": r[1], "client_name": r[2], "updated_at": r[3], "message_count": r[4]}
        for r in rows
    ]}


@router.get("/api/ai-chat/conversations/{conversation_id}")
def get_conversation(conversation_id: int, request: Request):
    user = _session_user_or_401(request)
    conversation = load_conversation(user["id"], conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Chat not found.")
    conn = connect_db(DB_PATH)
    try:
        rows = conn.execute(
            "SELECT role, content, meta FROM chat_messages WHERE conversation_id = ? ORDER BY id",
            (conversation_id,),
        ).fetchall()
    finally:
        conn.close()
    has_chart = conversation.pop("chart") is not None
    return {
        **conversation,
        "has_chart": has_chart,
        "messages": [
            {"role": role, "content": content, "meta": json.loads(meta) if meta else None}
            for role, content, meta in rows
        ],
    }


@router.delete("/api/ai-chat/conversations/{conversation_id}")
def delete_conversation(conversation_id: int, request: Request):
    user = _session_user_or_401(request)
    conn = _open_for_delete()
    try:
        owned = conn.execute(
            "SELECT 1 FROM chat_conversations WHERE id = ? AND user_id = ?",
            (conversation_id, user["id"]),
        ).fetchone()
        if not owned:
            raise HTTPException(status_code=404, detail="Chat not found.")
        _delete_rows(conn, [conversation_id])
        conn.commit()
    finally:
        conn.close()
    return {"deleted": 1}


@router.delete("/api/ai-chat/conversations")
def clear_conversations(request: Request):
    user = _session_user_or_401(request)
    conn = _open_for_delete()
    try:
        ids = [r[0] for r in conn.execute(
            "SELECT id FROM chat_conversations WHERE user_id = ?", (user["id"],)
        )]
        _delete_rows(conn, ids)
        conn.commit()
    finally:
        conn.close()
    logger.info("Cleared %d chat conversation(s) for user %s", len(ids), user["id"])
    return {"deleted": len(ids)}
