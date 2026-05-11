import os
from datetime import datetime, timezone
from typing import Iterator, Optional

from src.internal_rag.connectors.base import BaseConnector, IngestDocument


def _html_to_text(html: str) -> str:
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html or "", "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        return " ".join(soup.get_text(separator=" ").split())
    except Exception:
        return html or ""


class ConfluenceConnector(BaseConnector):
    name = "wiki"

    def __init__(
        self,
        url: str | None = None,
        username: str | None = None,
        api_token: str | None = None,
        space_keys: list[str] | None = None,
        page_limit: int | None = None,
    ):
        self.url = url or os.getenv("CONFLUENCE_URL")
        self.username = username or os.getenv("CONFLUENCE_USER")
        self.api_token = api_token or os.getenv("CONFLUENCE_API_TOKEN")
        spaces_env = os.getenv("CONFLUENCE_SPACE_KEYS", "")
        self.space_keys = space_keys if space_keys is not None else [
            s.strip() for s in spaces_env.split(",") if s.strip()
        ]
        self.page_limit = page_limit

    def _client(self):
        from atlassian import Confluence

        if not (self.url and self.username and self.api_token):
            raise RuntimeError(
                "Confluence credentials missing. Set CONFLUENCE_URL / CONFLUENCE_USER / CONFLUENCE_API_TOKEN."
            )
        return Confluence(url=self.url, username=self.username, password=self.api_token, cloud=True)

    def _list_spaces(self, client) -> list[str]:
        if self.space_keys:
            return self.space_keys
        resp = client.get_all_spaces(limit=100)
        results = resp.get("results", resp) if isinstance(resp, dict) else resp
        keys = []
        for s in results or []:
            k = s.get("key") or ""
            if k and not k.startswith("~"):
                keys.append(k)
        return keys

    def fetch_documents(self, since_ts: Optional[float] = None) -> Iterator[IngestDocument]:
        client = self._client()
        spaces = self._list_spaces(client)
        fetched = 0
        for space_key in spaces:
            start = 0
            while True:
                resp = client.get_all_pages_from_space(
                    space=space_key,
                    start=start,
                    limit=50,
                    expand="body.storage,version",
                )
                if not resp:
                    break
                for page in resp:
                    last_mod = (page.get("version") or {}).get("when", "")
                    if since_ts is not None and last_mod:
                        try:
                            mod_dt = datetime.fromisoformat(last_mod.replace("Z", "+00:00"))
                            if mod_dt.tzinfo is None:
                                mod_dt = mod_dt.replace(tzinfo=timezone.utc)
                            if mod_dt.timestamp() < since_ts:
                                continue
                        except Exception:
                            pass

                    body_html = (page.get("body") or {}).get("storage", {}).get("value", "")
                    content = _html_to_text(body_html)
                    if not content.strip():
                        continue
                    page_id = page.get("id")
                    title = page.get("title", "")
                    base = self.url.rstrip("/")
                    page_url = f"{base}/wiki/spaces/{space_key}/pages/{page_id}"
                    yield IngestDocument(
                        doc_id=f"confluence:page:{page_id}",
                        source="wiki",
                        url=page_url,
                        title=title,
                        content=content,
                        metadata={
                            "space_key": space_key,
                            "last_modified": last_mod,
                            "page_id": page_id,
                        },
                    )
                    fetched += 1
                    if self.page_limit and fetched >= self.page_limit:
                        return
                if len(resp) < 50:
                    break
                start += 50
