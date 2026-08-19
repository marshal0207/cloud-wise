from rest_framework import permissions

class IsProjectRolePermission(permissions.BasePermission):
    """
    Custom permission for Role-Based Access Control (RBAC):
    - Owner & Admin: Full access (create, view, edit, delete)
    - Editor: Create, view, edit (cannot delete)
    - Viewer: View only (cannot create, edit, delete)
    """

    def has_permission(self, request, view):
        role = request.headers.get('x-user-role', 'owner')
        if request.user.is_authenticated and hasattr(request.user, 'role'):
            role = request.user.role or role

        # Safe read-only methods are allowed for all
        if request.method in permissions.SAFE_METHODS:
            return True

        if role == 'viewer':
            return False

        if request.method == 'DELETE' and role not in ['owner', 'admin']:
            return False

        return True

    def has_object_permission(self, request, view, obj):
        role = request.headers.get('x-user-role', getattr(obj, 'user_role', 'owner'))
        if request.user.is_authenticated and hasattr(request.user, 'role'):
            role = request.user.role or role

        if request.method in permissions.SAFE_METHODS:
            return True

        if role == 'viewer':
            return False

        if request.method == 'DELETE' and role not in ['owner', 'admin']:
            return False

        return True
