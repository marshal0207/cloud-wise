from rest_framework import permissions

class IsProjectOwner(permissions.BasePermission):
    """
    Permission to ensure only authenticated users can access projects,
    and object-level access is strictly confined to the project owner.
    """
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        return getattr(obj, 'user_id', None) == request.user.id


class IsProjectRolePermission(permissions.BasePermission):
    """
    Custom permission for Role-Based Access Control (RBAC):
    - Must be authenticated
    - Owner & Admin: Full access (create, view, edit, delete)
    - Editor: Create, view, edit (cannot delete)
    - Viewer: View only (cannot create, edit, delete)
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        role = getattr(request.user, 'role', 'owner') or 'owner'

        if request.method in permissions.SAFE_METHODS:
            return True

        if role == 'viewer':
            return False

        if request.method == 'DELETE' and role not in ['owner', 'admin']:
            return False

        return True

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False

        # Must be the project owner
        if getattr(obj, 'user_id', None) != request.user.id:
            return False

        role = getattr(request.user, 'role', getattr(obj, 'user_role', 'owner')) or 'owner'

        if request.method in permissions.SAFE_METHODS:
            return True

        if role == 'viewer':
            return False

        if request.method == 'DELETE' and role not in ['owner', 'admin']:
            return False

        return True

