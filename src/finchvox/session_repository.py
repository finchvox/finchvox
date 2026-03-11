import math
from dataclasses import dataclass
from pathlib import Path

from finchvox.session import Session

DEFAULT_PAGE_SIZE = 50


@dataclass
class PaginatedSessions:
    sessions: list[dict]
    total_count: int
    total_pages: int
    page: int
    page_size: int
    has_previous_page: bool
    has_next_page: bool
    data_dir: str

    def to_dict(self) -> dict:
        return {
            "sessions": self.sessions,
            "total_count": self.total_count,
            "total_pages": self.total_pages,
            "page": self.page,
            "page_size": self.page_size,
            "has_previous_page": self.has_previous_page,
            "has_next_page": self.has_next_page,
            "data_dir": self.data_dir,
        }


class SessionRepository:
    def __init__(self, sessions_base_dir: Path, page_size: int = DEFAULT_PAGE_SIZE):
        self.sessions_base_dir = sessions_base_dir
        self.page_size = page_size

    def _load_all_sessions(self) -> list[dict]:
        if not self.sessions_base_dir.exists():
            return []

        sessions = []
        for session_dir in self.sessions_base_dir.iterdir():
            if not session_dir.is_dir():
                continue

            session_id = session_dir.name
            trace_file = session_dir / f"trace_{session_id}.jsonl"

            if not trace_file.exists():
                continue

            try:
                session = Session(session_dir)
                sessions.append(session.to_dict())
            except Exception as e:
                print(f"Error reading session {session_dir}: {e}")
                continue

        sessions.sort(key=lambda s: s.get("start_time") or 0, reverse=True)
        return sessions

    def list_paginated(self, page: int = 1) -> PaginatedSessions:
        all_sessions = self._load_all_sessions()
        total_count = len(all_sessions)
        total_pages = max(1, math.ceil(total_count / self.page_size))

        page = max(1, min(page, total_pages))

        start_index = (page - 1) * self.page_size
        end_index = start_index + self.page_size
        page_sessions = all_sessions[start_index:end_index]

        return PaginatedSessions(
            sessions=page_sessions,
            total_count=total_count,
            total_pages=total_pages,
            page=page,
            page_size=self.page_size,
            has_previous_page=page > 1,
            has_next_page=page < total_pages,
            data_dir=str(self.sessions_base_dir),
        )
