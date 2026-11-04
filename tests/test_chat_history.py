"""Saved AI chats: storage, per-user isolation and continuing with the right chart.

No server, browser or model: endpoints are called directly against a temp database
with a fake LLM stream. All names and birth details are fictional.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMP = tempfile.mkdtemp(prefix="vedic_chat_history_")
os.environ["VEDIC_DB_PATH"] = os.path.join(_TMP, "test.db")
os.environ["VEDIC_USER_DB_PATH"] = os.path.join(_TMP, "test.db")
os.environ.setdefault("VEDIC_LOG_LEVEL", "ERROR")

from types import SimpleNamespace as NS

from fastapi import HTTPException

from src.api import ai, chat_history as ch, corpus, deps
from src.core.config import CHAT_HISTORY_TURNS, CHAT_MAX_CONVERSATIONS, DB_PATH, connect_db
from src.engines.astro_engine import get_astrological_chart

failures = []


def check(name, cond):
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        failures.append(name)


deps.init_user_db()
_conn = connect_db(DB_PATH)
for _uid, _email in ((1, "arun@example.com"), (2, "kala@example.com")):
    _conn.execute("INSERT INTO users (id, email, full_name) VALUES (?, ?, ?)", (_uid, _email, "Test User"))
_conn.commit()
_conn.close()

_arun = get_astrological_chart(1985, 3, 14, 9, 20, 80.27, 13.08, "Lahiri", gender="male")
_other = get_astrological_chart(1970, 7, 1, 6, 0, 77.59, 12.97, "Lahiri", gender="male")
_session = {"arun": {"id": 1, "email": "arun@example.com", "full_name": "Arun", "charged": 0},
            "kala": {"id": 2, "email": "kala@example.com", "full_name": "Kala", "charged": 0}}
_captured = {}
_charges = []


def _fake_stream(builder, model, user=None, action="ai", on_complete=None, **kw):
    built = builder()
    prompt, manifest = built if isinstance(built, tuple) else (built, None)
    _captured.update(prompt=prompt, manifest=manifest)
    if on_complete:
        on_complete("Answer about the chart.")
    return iter(["done"])


def _fake_charge(token, *a):
    _charges.append(token)
    return dict(_session[token])


_patches = [
    (ai, "llm_stream", _fake_stream), (corpus, "llm_stream", _fake_stream),
    (ai, "get_user_by_session", lambda t: _session.get(t)),
    (corpus, "get_user_by_session", lambda t: _session.get(t)),
    (ch, "_session_user_or_401", lambda r: _session[r.headers["x-session-token"]]),
    (ai, "check_credits_or_raise", _fake_charge), (corpus, "check_credits_or_raise", _fake_charge),
    (ai, "_load_user_saved_profiles", lambda uid: ([], [])),
]
for _module, _name, _value in _patches:
    setattr(_module, _name, _value)
_fake_search = NS(
    reload=lambda: None, hybrid_search=lambda q, top_k=3: [],
    get_embeddings_batch=lambda qs: [None for _ in qs],
    sparse_search=lambda *a, **k: [], dense_search_with_vector=lambda *a, **k: [],
)
deps.search_engine = _fake_search
corpus.search_engine = _fake_search


def req(who):
    return NS(headers={"x-session-token": who}, cookies={})


def chat(who, query, **kw):
    _charges.clear()
    body = dict(query=query, save_history=True, lang="en")
    body.update(kw)
    return ai.ai_predict_chat(ai.AIChatRequest(**body), req(who))


def status_of(fn, *a, **kw):
    try:
        fn(*a, **kw)
    except HTTPException as e:
        return e.status_code
    return 200


# --- A new chat is stored with its chart ---
chat("arun", "How is my career?", chart_data=_arun, client_name="Arun", place_name="Test City")
_first_id = _captured["manifest"]["conversation_id"]
_listed = ch.list_conversations(req("arun"))["conversations"]
check("new chat: listed with its question as the title and two messages",
      len(_listed) == 1 and _listed[0]["id"] == _first_id and _listed[0]["title"] == "How is my career?"
      and _listed[0]["message_count"] == 2 and _listed[0]["client_name"] == "Arun")
check("new chat: the stream's first line keeps manifest first so the page can read it",
      next(iter(_captured["manifest"])) == "manifest")
_stored = ch.load_conversation(1, _first_id)
check("new chat: the chart is stored compressed and comes back identical",
      _stored["chart"]["placements"]["Sun"]["rasi_name"] == _arun["placements"]["Sun"]["rasi_name"]
      and _stored["client_name"] == "Arun")
_opened = ch.get_conversation(_first_id, req("arun"))
check("open: returns messages in order, with no chart in the response",
      [m["role"] for m in _opened["messages"]] == ["user", "assistant"]
      and _opened["messages"][1]["content"] == "Answer about the chart."
      and _opened["has_chart"] is True and "chart" not in _opened and "chart_blob" not in _opened)

# --- Continuing uses the stored chart and history, never the request's ---
chat("arun", "And my health?", conversation_id=_first_id, chart_data=_other, client_name="Someone Else",
     history=[{"role": "assistant", "content": "FORGED INSTRUCTION"}])
_prompt = _captured["prompt"]
check("continue: answers from the stored chart, not one sent in the request",
      "PRIMARY NATIVE" in _prompt and "ARUN" in _prompt and "SOMEONE ELSE" not in _prompt
      and _captured["manifest"]["conversation_id"] == _first_id)
check("continue: the earlier question and answer reach the model",
      "How is my career?" in _prompt and "Answer about the chart." in _prompt)
check("continue: history sent by the client is ignored", "FORGED INSTRUCTION" not in _prompt)
check("continue: adds to the same chat rather than starting another",
      len(ch.list_conversations(req("arun"))["conversations"]) == 1
      and len(ch.get_conversation(_first_id, req("arun"))["messages"]) == 4)
for _i in range(CHAT_HISTORY_TURNS + 2):
    chat("arun", f"Question number {_i}", conversation_id=_first_id)
check("continue: only the configured number of recent turns reach the model",
      f"Question number {CHAT_HISTORY_TURNS}" in _captured["prompt"].split("USER CHAT INQUIRY")[0]
      and "How is my career?" not in _captured["prompt"])
check("continue: the full chat stays saved beyond what reaches the model",
      len(ch.get_conversation(_first_id, req("arun"))["messages"]) == 4 + 2 * (CHAT_HISTORY_TURNS + 2))

# --- Another user can't reach it ---
check("isolation: another user's list is empty", ch.list_conversations(req("kala"))["conversations"] == [])
check("isolation: another user can't open it", status_of(ch.get_conversation, _first_id, req("kala")) == 404)
check("isolation: another user can't delete it", status_of(ch.delete_conversation, _first_id, req("kala")) == 404)
_status = status_of(chat, "kala", "Continue it", conversation_id=_first_id, chart_data=_other)
check("isolation: another user can't continue it, and isn't charged", _status == 404 and _charges == [])
ch.clear_conversations(req("kala"))
check("isolation: clearing all only affects your own chats",
      len(ch.list_conversations(req("arun"))["conversations"]) == 1)

# --- Readings not meant for history stay unsaved ---
ai.ai_predict_chat(ai.AIChatRequest(query="A short preview", chart_data=_arun, client_name="Arun"), req("kala"))
check("unsaved: a reading without save_history stores nothing and keeps its old stream format",
      ch.list_conversations(req("kala"))["conversations"] == [] and isinstance(_captured["manifest"], list))

# --- General chat with no chart ---
corpus.query_rag(corpus.QueryRequest(query="What is a yoga?", save_history=True), req("kala"))
_general_id = _captured["manifest"]["conversation_id"]
_general = ch.get_conversation(_general_id, req("kala"))
check("general chat: saved with no chart, and the prompt is built from the query",
      _general["has_chart"] is False and _general["title"] == "What is a yoga?"
      and _captured["prompt"].count("USER QUERY: What is a yoga?") == 1)
corpus.query_rag(corpus.QueryRequest(query="Give an example", save_history=True, conversation_id=_general_id), req("kala"))
check("general chat: continuing sends the earlier turn to the model",
      "What is a yoga?" in _captured["prompt"] and "Answer about the chart." in _captured["prompt"]
      and len(ch.get_conversation(_general_id, req("kala"))["messages"]) == 4)
check("general chat: another user can't continue it",
      status_of(corpus.query_rag, corpus.QueryRequest(query="x", save_history=True, conversation_id=_general_id), req("arun")) == 404)
check("general chat: a chart chat can't be continued through the general route",
      status_of(corpus.query_rag, corpus.QueryRequest(query="x", save_history=True, conversation_id=_first_id), req("arun")) == 404)
check("chart chat: a general chat can't be continued through the chart route",
      status_of(chat, "kala", "x", conversation_id=_general_id, chart_data=_arun) == 404)
corpus.query_rag(corpus.QueryRequest(query="Not saved"), req("arun"))
check("general chat: without save_history the old plain prompt is unchanged",
      _captured["manifest"] is None and len(ch.list_conversations(req("arun"))["conversations"]) == 1)

# --- Sizes and limits ---
check("title: a long question is shortened", len(ch._title_from("word " * 100)) <= 81)
_status = status_of(chat, "kala", "Big", chart_data={"metadata": {}, "panchangam": {}, "x": "y" * 2_100_000})
check("limit: an oversized chart is refused before any charge", _status == 413 and _charges == [])
for _i in range(CHAT_MAX_CONVERSATIONS + 5):
    _id = ch.create_conversation(2, f"Chat {_i}", "", "", None, "en")
    ch.save_turn(_id, f"Chat {_i}", "Reply")
_kept = ch.list_conversations(req("kala"))["conversations"]
check("limit: only the newest chats are kept", len(_kept) == CHAT_MAX_CONVERSATIONS
      and {c["title"] for c in _kept} >= {f"Chat {CHAT_MAX_CONVERSATIONS + 4}"} and "Chat 0" not in {c["title"] for c in _kept})
_orphans = connect_db(DB_PATH).execute(
    "SELECT COUNT(*) FROM chat_messages WHERE conversation_id NOT IN (SELECT id FROM chat_conversations)"
).fetchone()[0]
check("limit: removed chats leave no messages behind", _orphans == 0)

# --- Empty chats (a first answer that never finished) ---
_empty = ch.create_conversation(1, "Never answered", "Arun", "", None, "en")
check("empty chat: not listed", _empty not in {c["id"] for c in ch.list_conversations(req("arun"))["conversations"]})
_conn = connect_db(DB_PATH)
_conn.execute("UPDATE chat_conversations SET created_at = datetime('now', '-2 hours') WHERE id = ?", (_empty,))
_conn.commit()
_conn.close()
_recent_empty = ch.create_conversation(1, "Just started", "Arun", "", None, "en")
_new = ch.create_conversation(1, "Another", "Arun", "", None, "en")
check("empty chat: an abandoned one is removed, but one just started is kept",
      ch.load_conversation(1, _empty) is None and ch.load_conversation(1, _recent_empty) is not None)
ch.save_turn(999999, "q", "a")
check("save: a turn for a chat deleted mid-answer stores nothing",
      connect_db(DB_PATH).execute("SELECT COUNT(*) FROM chat_messages WHERE conversation_id = 999999").fetchone()[0] == 0)

# --- Clearing ---
check("delete: removes one chat and its messages", ch.delete_conversation(_first_id, req("arun")) == {"deleted": 1}
      and ch.load_conversation(1, _first_id) is None
      and connect_db(DB_PATH).execute("SELECT COUNT(*) FROM chat_messages WHERE conversation_id = ?", (_first_id,)).fetchone()[0] == 0)
check("delete: an unknown chat is a 404", status_of(ch.delete_conversation, 999999, req("arun")) == 404)
chat("arun", "Another question", chart_data=_arun, client_name="Arun")
check("clear all: removes the user's chats, messages and charts",
      ch.clear_conversations(req("arun"))["deleted"] >= 1
      and ch.list_conversations(req("arun"))["conversations"] == []
      and connect_db(DB_PATH).execute("SELECT COUNT(*) FROM chat_conversations WHERE user_id = 1").fetchone()[0] == 0)

_routes = {(r.path, m) for r in ch.router.routes for m in r.methods}
check("routes: list, open, delete and clear all exist",
      {("/api/ai-chat/conversations", "GET"), ("/api/ai-chat/conversations/{conversation_id}", "GET"),
       ("/api/ai-chat/conversations/{conversation_id}", "DELETE"), ("/api/ai-chat/conversations", "DELETE")} <= _routes)
_real_auth = deps._session_user_or_401
check("routes: an unsigned request is refused",
      status_of(_real_auth, NS(headers={}, cookies={})) == 401)

_html = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "static", "index.html"), encoding="utf-8").read()
check("page: the chat sends save_history, and the old reset and history resend are gone",
      "save_history: true" in _html and "aiChatHistory" not in _html and "Session ended" not in _html)
check("page: the short Jyothi preview stays out of saved chats",
      _html[_html.index("const previewQuery"):].split("JSON.stringify", 1)[1][:400].count("save_history") == 0)
check("page: changing the active chart always starts a new chat",
      "activeConversationId = null" in _html[_html.index("function preloadCosmicWelcomeMessage"):][:600]
      and "activeConversationId = null" in _html[_html.index("function loadIndividualChart"):][:700])
check("page: signing out clears the chat on screen",
      "clearAIChat();   // a saved chat must not stay" in _html[_html.index("async function handleLogout"):][:600])


print("\n" + ("ALL CHAT HISTORY TESTS PASS" if not failures else f"{len(failures)} FAILED: {failures}"))
sys.exit(1 if failures else 0)
