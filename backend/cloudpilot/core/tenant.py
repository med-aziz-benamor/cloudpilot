"""Tenant isolation — the second, redundant layer of defense after RBAC.

A request-scoped ``ContextVar`` holds the current organization id. A SQLAlchemy
``do_orm_execute`` event listener inspects every SELECT and, when the target entity
carries an ``organization_id`` column, transparently appends
``WHERE organization_id = :current_org``.

This means that even if an RBAC check is bypassed or a service forgets to filter,
a query can never return another tenant's rows.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import ORMExecuteState, with_loader_criteria

# Holds the active organization id for the duration of a request / task.
_current_org_id: ContextVar[uuid.UUID | None] = ContextVar("current_org_id", default=None)


def set_current_org(org_id: uuid.UUID | None) -> None:
    """Bind the current organization id to the request context."""
    _current_org_id.set(org_id)


def get_current_org() -> uuid.UUID | None:
    """Return the organization id bound to the current context, if any."""
    return _current_org_id.get()


class TenantContext:
    """Context manager / async context manager that scopes queries to one org.

    Usage::

        async with TenantContext(org_id):
            ...  # all queries auto-filtered
    """

    def __init__(self, org_id: uuid.UUID | None) -> None:
        self._org_id = org_id
        self._token = None

    def __enter__(self) -> "TenantContext":
        self._token = _current_org_id.set(self._org_id)
        return self

    def __exit__(self, *exc: object) -> None:
        if self._token is not None:
            _current_org_id.reset(self._token)

    async def __aenter__(self) -> "TenantContext":
        return self.__enter__()

    async def __aexit__(self, *exc: object) -> None:
        self.__exit__(*exc)


def _install_listener() -> None:
    """Register the global ORM execute listener on the session factory."""

    @event.listens_for(AsyncSession.sync_session_class, "do_orm_execute")
    def _tenant_filter(state: ORMExecuteState) -> None:
        # Only constrain plain SELECTs; never touch writes or relationship loads.
        if not state.is_select or state.is_column_load or state.is_relationship_load:
            return
        org_id = _current_org_id.get()
        if org_id is None:
            return
        # Apply the criterion to EVERY mapped entity that declares organization_id.
        # Stopping at the first one (as this used to) left every later org-scoped
        # entity in the statement unfiltered — a two-entity select bound to org A
        # would happily return org B's rows on the trailing side. An FK-correlated
        # join masks that, which is why it went unnoticed.
        seen: set[type] = set()
        for mapper in state.all_mappers:
            if "organization_id" not in mapper.columns:
                continue
            entity = mapper.entity
            if entity in seen:
                continue
            seen.add(entity)
            state.statement = state.statement.options(
                with_loader_criteria(
                    entity,
                    lambda cls: cls.organization_id == org_id,
                    include_aliases=True,
                )
            )


_install_listener()
