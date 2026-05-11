import os
import re
import time
from typing import Iterator, Optional

from src.internal_rag.connectors.base import BaseConnector, IngestDocument


def _ts_to_url_fragment(ts: str) -> str:
    return "p" + ts.replace(".", "")


def _resolve_user_mentions(text: str, users: dict[str, str]) -> str:
    def repl(m: re.Match[str]) -> str:
        uid = m.group(1)
        return f"@{users.get(uid, uid)}"

    return re.sub(r"<@([A-Z0-9]+)>", repl, text or "")


class SlackConnector(BaseConnector):
    name = "slack"

    def __init__(
        self,
        token: Optional[str] = None,
        channel_names: Optional[list[str]] = None,
        lookback_days: int = 30,
        max_threads_per_channel: int = 500,
        workspace_subdomain: Optional[str] = None,
    ):
        self.token = (
            token
            or os.getenv("SLACK_TOKEN")
            or os.getenv("SLACK_USER_TOKEN")
            or os.getenv("SLACK_BOT_TOKEN")
        )
        env_channels = os.getenv("SLACK_CHANNELS", "")
        self.channel_names = (
            channel_names
            if channel_names is not None
            else [c.strip() for c in env_channels.split(",") if c.strip()]
        )
        self.lookback_days = int(os.getenv("SLACK_LOOKBACK_DAYS", str(lookback_days)))
        self.max_threads_per_channel = max_threads_per_channel
        self.workspace_subdomain = workspace_subdomain or os.getenv("SLACK_WORKSPACE_SUBDOMAIN", "")
        self._users: dict[str, str] = {}

    def _client(self):
        from slack_sdk import WebClient
        from slack_sdk.http_retry.builtin_handlers import RateLimitErrorRetryHandler

        if not self.token:
            raise RuntimeError(
                "Slack token missing — set SLACK_TOKEN (xoxp- for user, xoxb- for bot)"
            )
        client = WebClient(token=self.token)
        client.retry_handlers.append(RateLimitErrorRetryHandler(max_retry_count=3))
        return client

    def _load_users(self, client) -> dict[str, str]:
        if self._users:
            return self._users
        cursor = None
        while True:
            resp = client.users_list(cursor=cursor, limit=200)
            for m in resp.get("members", []):
                uid = m.get("id")
                name = m.get("real_name") or m.get("profile", {}).get("display_name") or m.get("name") or uid
                if uid:
                    self._users[uid] = name
            cursor = (resp.get("response_metadata") or {}).get("next_cursor")
            if not cursor:
                break
        return self._users

    def _channels(self, client) -> Iterator[dict]:
        include_private = os.getenv("SLACK_INCLUDE_PRIVATE", "false").lower() in {"1", "true", "yes"}
        types = "public_channel,private_channel" if include_private else "public_channel"
        cursor = None
        while True:
            resp = client.conversations_list(types=types, exclude_archived=True, limit=200, cursor=cursor)
            for ch in resp.get("channels", []):
                if ch.get("is_im") or ch.get("is_mpim"):
                    continue
                if not ch.get("is_member", False):
                    continue
                name = ch.get("name", "")
                if self.channel_names and name not in self.channel_names:
                    continue
                yield ch
            cursor = (resp.get("response_metadata") or {}).get("next_cursor")
            if not cursor:
                break

    def _thread_content(self, root: dict, replies: list[dict], users: dict[str, str]) -> str:
        lines = []
        for m in [root] + (replies or []):
            user = users.get(m.get("user", ""), m.get("user", ""))
            text = _resolve_user_mentions(m.get("text", ""), users)
            if text.strip():
                lines.append(f"@{user}: {text}")
        return "\n".join(lines)

    def fetch_documents(self, since_ts=None) -> Iterator[IngestDocument]:
        client = self._client()
        users = self._load_users(client)
        base_oldest = time.time() - self.lookback_days * 86400
        effective_oldest = max(base_oldest, since_ts) if since_ts is not None else base_oldest
        oldest = str(int(effective_oldest))

        for ch in self._channels(client):
            ch_id = ch.get("id")
            ch_name = ch.get("name", "")
            count = 0
            cursor = None
            seen_thread_ts: set[str] = set()
            while True:
                hist = client.conversations_history(
                    channel=ch_id, oldest=oldest, limit=200, cursor=cursor
                )
                for msg in hist.get("messages", []):
                    if msg.get("subtype") in {"channel_join", "channel_leave", "bot_message"}:
                        continue
                    thread_ts = msg.get("thread_ts") or msg.get("ts")
                    if thread_ts in seen_thread_ts:
                        continue
                    seen_thread_ts.add(thread_ts)

                    replies: list[dict] = []
                    reply_count = msg.get("reply_count", 0) if msg.get("thread_ts") is None else 0
                    if reply_count and reply_count > 0:
                        try:
                            r = client.conversations_replies(channel=ch_id, ts=thread_ts, limit=200)
                            replies = r.get("messages", [])[1:]
                        except Exception:
                            replies = []

                    content = self._thread_content(msg, replies, users)
                    if not content.strip():
                        continue

                    url = "https://slack.com/archives/" + ch_id + "/" + _ts_to_url_fragment(thread_ts)
                    if self.workspace_subdomain:
                        url = f"https://{self.workspace_subdomain}.slack.com/archives/{ch_id}/{_ts_to_url_fragment(thread_ts)}"

                    title_first_line = (msg.get("text") or "").splitlines()[0][:80] or f"#{ch_name}"

                    yield IngestDocument(
                        doc_id=f"slack:thread:{ch_id}:{thread_ts}",
                        source="slack",
                        url=url,
                        title=f"#{ch_name}: {title_first_line}",
                        content=content,
                        metadata={
                            "channel_id": ch_id,
                            "channel_name": ch_name,
                            "thread_ts": thread_ts,
                            "last_modified": thread_ts,
                            "reply_count": len(replies),
                        },
                    )
                    count += 1
                    if count >= self.max_threads_per_channel:
                        break
                cursor = (hist.get("response_metadata") or {}).get("next_cursor")
                if not cursor or count >= self.max_threads_per_channel:
                    break
