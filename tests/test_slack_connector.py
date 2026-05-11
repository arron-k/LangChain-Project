import pytest

from src.internal_rag.connectors.slack import (
    SlackConnector,
    _resolve_user_mentions,
    _ts_to_url_fragment,
)


def test_ts_to_url_fragment_strips_dot():
    assert _ts_to_url_fragment("1700000000.123456") == "p1700000000123456"


def test_resolve_user_mentions_swaps_ids_for_names():
    out = _resolve_user_mentions(
        "Hello <@U111>, ping <@U222>",
        {"U111": "Alice", "U222": "Bob"},
    )
    assert out == "Hello @Alice, ping @Bob"


def test_resolve_user_mentions_keeps_unknown_id():
    out = _resolve_user_mentions("<@U999>", {})
    assert out == "@U999"


class FakeSlackClient:
    def __init__(self, channels, users, history, replies=None):
        self._channels = channels
        self._users = users
        self._history = history
        self._replies = replies or {}

    def users_list(self, cursor=None, limit=200):
        return {"members": self._users, "response_metadata": {"next_cursor": ""}}

    def conversations_list(self, types=None, exclude_archived=True, limit=200, cursor=None):
        return {"channels": self._channels, "response_metadata": {"next_cursor": ""}}

    def conversations_history(self, channel=None, oldest=None, limit=200, cursor=None):
        return {
            "messages": self._history.get(channel, []),
            "response_metadata": {"next_cursor": ""},
        }

    def conversations_replies(self, channel=None, ts=None, limit=200):
        return {"messages": self._replies.get((channel, ts), [])}


def _connector_with(fake_client) -> SlackConnector:
    c = SlackConnector(
        token="xoxb-test",
        channel_names=[],
        lookback_days=7,
        workspace_subdomain="acme",
    )
    c._client = lambda: fake_client  # type: ignore[assignment]
    return c


def test_slack_connector_yields_thread_documents():
    fake = FakeSlackClient(
        channels=[
            {"id": "C1", "name": "eng", "is_channel": True, "is_member": True},
        ],
        users=[
            {"id": "U1", "real_name": "Alice"},
            {"id": "U2", "real_name": "Bob"},
        ],
        history={
            "C1": [
                {
                    "ts": "1700000000.000100",
                    "user": "U1",
                    "text": "Deploy plan for v2",
                    "reply_count": 1,
                },
            ]
        },
        replies={
            ("C1", "1700000000.000100"): [
                {"ts": "1700000000.000100", "user": "U1", "text": "Deploy plan for v2"},
                {"ts": "1700000001.000200", "user": "U2", "text": "LGTM <@U1>"},
            ]
        },
    )
    conn = _connector_with(fake)
    docs = list(conn.fetch_documents())
    assert len(docs) == 1
    d = docs[0]
    assert d.source == "slack"
    assert d.doc_id == "slack:thread:C1:1700000000.000100"
    assert "Deploy plan" in d.content
    assert "@Alice" in d.content and "@Bob" in d.content
    assert d.url.startswith("https://acme.slack.com/archives/C1/p1700000000")
    assert d.metadata["channel_name"] == "eng"
    assert d.metadata["reply_count"] == 1


def test_slack_connector_filters_dms_and_mpims():
    fake = FakeSlackClient(
        channels=[
            {"id": "D1", "name": "alice-bob", "is_im": True},
            {"id": "G1", "name": "group-chat", "is_mpim": True},
            {"id": "C1", "name": "eng", "is_member": True},
        ],
        users=[],
        history={"C1": []},
    )
    conn = _connector_with(fake)
    docs = list(conn.fetch_documents())
    assert all(d.metadata.get("channel_id") == "C1" for d in docs)


def test_slack_connector_skips_bot_and_join_messages():
    fake = FakeSlackClient(
        channels=[{"id": "C1", "name": "eng", "is_member": True}],
        users=[],
        history={
            "C1": [
                {"ts": "1", "user": "U1", "text": "real msg"},
                {"ts": "2", "user": "U1", "subtype": "channel_join", "text": "joined"},
                {"ts": "3", "user": "U1", "subtype": "bot_message", "text": "auto"},
            ]
        },
    )
    conn = _connector_with(fake)
    docs = list(conn.fetch_documents())
    assert len(docs) == 1
    assert "real msg" in docs[0].content


def test_slack_connector_whitelists_channels():
    fake = FakeSlackClient(
        channels=[
            {"id": "C1", "name": "eng", "is_member": True},
            {"id": "C2", "name": "random", "is_member": True},
        ],
        users=[],
        history={"C1": [{"ts": "1", "user": "U1", "text": "a"}], "C2": [{"ts": "2", "user": "U1", "text": "b"}]},
    )
    conn = SlackConnector(token="x", channel_names=["eng"], lookback_days=7)
    conn._client = lambda: fake  # type: ignore[assignment]
    docs = list(conn.fetch_documents())
    assert len(docs) == 1
    assert docs[0].metadata["channel_name"] == "eng"


def test_slack_connector_raises_without_token(monkeypatch):
    monkeypatch.delenv("SLACK_TOKEN", raising=False)
    monkeypatch.delenv("SLACK_USER_TOKEN", raising=False)
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    conn = SlackConnector(token=None, channel_names=[], lookback_days=7)
    with pytest.raises(RuntimeError, match="Slack token missing"):
        next(conn.fetch_documents())


def test_slack_connector_accepts_user_token_env(monkeypatch):
    monkeypatch.setenv("SLACK_TOKEN", "xoxp-user-token")
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    conn = SlackConnector(channel_names=[], lookback_days=7)
    assert conn.token == "xoxp-user-token"


def test_slack_connector_legacy_bot_token_still_works(monkeypatch):
    monkeypatch.delenv("SLACK_TOKEN", raising=False)
    monkeypatch.delenv("SLACK_USER_TOKEN", raising=False)
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-legacy")
    conn = SlackConnector(channel_names=[], lookback_days=7)
    assert conn.token == "xoxb-legacy"


def test_ingest_get_connector_returns_slack():
    from src.internal_rag.ingest import _get_connector

    c = _get_connector("slack")
    assert isinstance(c, SlackConnector)
