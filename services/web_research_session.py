from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WebResearchPage:
    query: str
    start: int
    end: int
    total: int
    rows: list[tuple[float, str, str]]


class WebResearchSessionStore:
    """In-memory cache for web research continuation state."""

    def __init__(self) -> None:
        self._query: str = ""
        self._results: list[tuple[float, str, str]] = []
        self._cursor: int = 0

    @property
    def query(self) -> str:
        return self._query

    @property
    def results(self) -> list[tuple[float, str, str]]:
        return list(self._results)

    @property
    def cursor(self) -> int:
        return self._cursor

    def result_count(self) -> int:
        return len(self._results)

    def has_results(self) -> bool:
        return bool(self._results)

    def set_results(self, query: str, rows: list[tuple[float, str, str]]) -> None:
        self._query = str(query or "").strip()
        self._results = list(rows or [])
        self._cursor = 0

    def set_state(self, query: str, rows: list[tuple[float, str, str]], cursor: int = 0) -> None:
        self._query = str(query or "").strip()
        self._results = list(rows or [])
        self._cursor = max(0, min(int(cursor or 0), len(self._results)))

    def next_page(self, max_results: int) -> WebResearchPage | None:
        if not self._results:
            return None
        start = max(0, int(self._cursor))
        end = min(len(self._results), start + max(1, int(max_results or 1)))
        if start >= len(self._results):
            return WebResearchPage(
                query=self._query,
                start=start,
                end=end,
                total=len(self._results),
                rows=[],
            )
        page = WebResearchPage(
            query=self._query,
            start=start,
            end=end,
            total=len(self._results),
            rows=self._results[start:end],
        )
        self._cursor = end
        return page

    def remaining_count(self) -> int:
        return max(0, len(self._results) - int(self._cursor))

    def clear(self) -> None:
        self._query = ""
        self._results = []
        self._cursor = 0
