from dataclasses import dataclass, field
from typing import Iterator, Optional


@dataclass
class IngestDocument:
    doc_id: str
    source: str
    url: str
    title: str
    content: str
    metadata: dict = field(default_factory=dict)


class BaseConnector:
    name: str = "base"

    def fetch_documents(self, since_ts: Optional[float] = None) -> Iterator[IngestDocument]:
        """Yield ingest documents.

        If `since_ts` is provided (Unix timestamp), connectors should yield only
        documents modified at or after that time. Implementations that don't
        natively support filtering can fall back to yielding everything; the
        ingest pipeline still benefits from re-embedding only the returned set.
        """
        raise NotImplementedError
