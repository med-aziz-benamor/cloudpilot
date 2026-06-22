"""Pagination helpers used across list endpoints."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class PageParams:
    page: int = 1
    page_size: int = 25

    def __post_init__(self) -> None:
        self.page = max(1, self.page)
        self.page_size = min(200, max(1, self.page_size))

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size


def has_next(total: int, page: int, page_size: int) -> bool:
    """Return True if there is a page after the current one."""
    return page * page_size < total
