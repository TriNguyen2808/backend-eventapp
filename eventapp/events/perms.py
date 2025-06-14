from  rest_framework import permissions
from rest_framework.permissions import BasePermission


class OwnerIsAuthenticated(permissions.IsAuthenticated):
    def has_object_permission(self, request, view, obj):
        return (self.has_permission(request, view) and request.user == obj.user) or request.user.is_superuser

class OwnerUser(permissions.IsAuthenticated):
    def has_object_permission(self, request, view, obj):
        return (self.has_permission(request, view) and request.user == obj) or request.user.is_superuser

class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_superuser

class IsOrganizer(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and (
                request.user.role_id == 2 or request.user.is_superuser
        )

class IsAttendee(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and (
                request.user.role_id == 3 or request.user.is_superuser
        )