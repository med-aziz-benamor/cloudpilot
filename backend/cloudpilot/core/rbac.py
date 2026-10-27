"""Role-based access control.

This is the FIRST layer of authorization. The SECOND, redundant layer is the
tenant filter in ``core/tenant.py`` which scopes every query to the caller's org.

Roles (descending privilege): admin > analyst > viewer.
"""

from __future__ import annotations

from cloudpilot.models.user import UserRole

# Permission matrix: maps a logical permission to the set of roles that hold it.
PERMISSIONS: dict[str, set[UserRole]] = {
    # Read access — everyone authenticated.
    "read": {UserRole.ADMIN, UserRole.ANALYST, UserRole.VIEWER},
    # Process recommendations (accept/reject/snooze) — analysts and admins.
    "recommendations.write": {UserRole.ADMIN, UserRole.ANALYST},
    # Use the Cloud Advisor chat — analysts and admins.
    "chat.use": {UserRole.ADMIN, UserRole.ANALYST},
    # Manage cloud account credentials — admins only.
    "cloud_accounts.manage": {UserRole.ADMIN},
    # Set the organization's monthly budget — admins only. It changes what
    # every overrun alert in the platform is measured against, so it sits with
    # the other org-wide configuration rather than with analyst workflows.
    "budget.manage": {UserRole.ADMIN},
    # Manage users — admins only.
    "users.manage": {UserRole.ADMIN},
    # View the audit log — admins only.
    "audit.read": {UserRole.ADMIN},
    # Trigger agents manually — admins only.
    "agents.trigger": {UserRole.ADMIN},
}


def role_has_permission(role: UserRole, permission: str) -> bool:
    """Return True if ``role`` holds ``permission``."""
    allowed = PERMISSIONS.get(permission, set())
    return role in allowed


def require_roles(*roles: UserRole) -> set[UserRole]:
    """Helper returning the role set, used to build FastAPI dependencies in deps.py."""
    return set(roles)
