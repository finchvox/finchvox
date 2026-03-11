import json
import tempfile
from pathlib import Path

import pytest

from finchvox.session_repository import SessionRepository, DEFAULT_PAGE_SIZE


@pytest.fixture
def temp_sessions_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "sessions"


@pytest.fixture
def single_session_dir(temp_sessions_dir):
    create_session(temp_sessions_dir, "session1", 1000000000000000000)
    return temp_sessions_dir


def create_session(sessions_dir: Path, session_id: str, start_time_nano: int):
    session_dir = sessions_dir / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    trace_file = session_dir / f"trace_{session_id}.jsonl"
    span = {
        "name": "test-span",
        "start_time_unix_nano": start_time_nano,
        "end_time_unix_nano": start_time_nano + 1000000000,
    }
    with trace_file.open("w") as f:
        json.dump(span, f)
        f.write("\n")


def create_sessions(sessions_dir: Path, count: int):
    for i in range(count):
        create_session(sessions_dir, f"session{i:03d}", i * 1000000000000000000)


class TestSessionRepository:
    def test_empty_directory_returns_empty_result(self, temp_sessions_dir):
        repo = SessionRepository(temp_sessions_dir)
        result = repo.list_paginated()

        assert result.sessions == []
        assert result.total_count == 0
        assert result.total_pages == 1
        assert result.page == 1
        assert result.has_previous_page is False
        assert result.has_next_page is False

    def test_nonexistent_directory_returns_empty_result(self, temp_sessions_dir):
        repo = SessionRepository(temp_sessions_dir / "nonexistent")
        result = repo.list_paginated()

        assert result.sessions == []
        assert result.total_count == 0

    def test_sessions_sorted_by_start_time_descending(self, temp_sessions_dir):
        create_session(temp_sessions_dir, "session1", 1000000000000000000)
        create_session(temp_sessions_dir, "session2", 3000000000000000000)
        create_session(temp_sessions_dir, "session3", 2000000000000000000)

        repo = SessionRepository(temp_sessions_dir)
        result = repo.list_paginated()

        assert len(result.sessions) == 3
        assert result.sessions[0]["session_id"] == "session2"
        assert result.sessions[1]["session_id"] == "session3"
        assert result.sessions[2]["session_id"] == "session1"

    def test_first_page_returns_correct_sessions(self, temp_sessions_dir):
        create_sessions(temp_sessions_dir, 75)

        repo = SessionRepository(temp_sessions_dir, page_size=50)
        result = repo.list_paginated(page=1)

        assert len(result.sessions) == 50
        assert result.total_count == 75
        assert result.total_pages == 2
        assert result.page == 1
        assert result.page_size == 50
        assert result.has_previous_page is False
        assert result.has_next_page is True

    def test_second_page_returns_remaining_sessions(self, temp_sessions_dir):
        create_sessions(temp_sessions_dir, 75)

        repo = SessionRepository(temp_sessions_dir, page_size=50)
        result = repo.list_paginated(page=2)

        assert len(result.sessions) == 25
        assert result.total_count == 75
        assert result.total_pages == 2
        assert result.page == 2
        assert result.has_previous_page is True
        assert result.has_next_page is False

    @pytest.mark.parametrize("invalid_page", [0, -1, -5])
    def test_invalid_page_clamped_to_one(self, single_session_dir, invalid_page):
        repo = SessionRepository(single_session_dir)
        result = repo.list_paginated(page=invalid_page)

        assert result.page == 1

    def test_invalid_page_too_high_clamped_to_max(self, temp_sessions_dir):
        create_sessions(temp_sessions_dir, 10)

        repo = SessionRepository(temp_sessions_dir, page_size=5)
        result = repo.list_paginated(page=100)

        assert result.page == 2
        assert result.total_pages == 2

    def test_total_pages_calculation(self, temp_sessions_dir):
        create_sessions(temp_sessions_dir, 101)

        repo = SessionRepository(temp_sessions_dir, page_size=50)
        result = repo.list_paginated()

        assert result.total_pages == 3
        assert result.total_count == 101

    def test_single_session_returns_one_page(self, single_session_dir):
        repo = SessionRepository(single_session_dir)
        result = repo.list_paginated()

        assert result.total_pages == 1
        assert result.total_count == 1
        assert result.has_previous_page is False
        assert result.has_next_page is False

    def test_to_dict_returns_all_fields(self, single_session_dir):
        repo = SessionRepository(single_session_dir)
        result = repo.list_paginated()
        d = result.to_dict()

        assert "sessions" in d
        assert "total_count" in d
        assert "total_pages" in d
        assert "page" in d
        assert "page_size" in d
        assert "has_previous_page" in d
        assert "has_next_page" in d
        assert "data_dir" in d

    def test_default_page_size_is_50(self):
        assert DEFAULT_PAGE_SIZE == 50
