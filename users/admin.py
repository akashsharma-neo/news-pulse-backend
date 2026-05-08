"""
NewsPulse users app admin registration.

Registers User, UserInteraction and UserPreference in Django admin.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, UserInteraction, UserPreference


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Admin interface for the custom User model.

    Uses email as the username field and supports login via
    email or phone number.
    """

    list_display = ["email", "phone", "name", "is_active", "is_staff", "date_joined"]
    list_filter = ["is_active", "is_staff", "date_joined"]
    search_fields = ["email", "phone", "name"]
    ordering = ["-date_joined"]

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("phone", "name")}),
        ("Permissions", {
            "fields": ("is_active", "is_staff", "is_superuser"),
        }),
        ("Important dates", {
            "fields": ("last_login", "date_joined"),
        }),
    )

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": (
                "email", "phone", "name", "password1", "password2",
                "is_active", "is_staff",
            ),
        }),
    )

    readonly_fields = ["date_joined", "last_login"]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs


@admin.register(UserInteraction)
class UserInteractionAdmin(admin.ModelAdmin):
    """Admin interface for user interaction records."""

    list_display = ["session_preview", "interaction_type", "cluster_title", "category", "created_at"]
    list_filter = ["interaction_type", "created_at", "cluster__primary_article__source__category"]
    search_fields = ["session_id", "cluster__primary_article__title"]
    readonly_fields = ["session_id", "interaction_type", "cluster", "dwell_seconds", "created_at"]
    date_hierarchy = "created_at"

    def session_preview(self, obj):
        return obj.session_id[:16] + "…"

    def cluster_title(self, obj):
        return obj.cluster.primary_article.title[:60]

    def category(self, obj):
        return obj.cluster.primary_article.source.category.slug

    cluster_title.short_description = "Cluster Title"
    category.short_description = "Category"
    session_preview.short_description = "Session"


@admin.register(UserPreference)
class UserPreferenceAdmin(admin.ModelAdmin):
    """Admin interface for user preference records."""

    list_display = ["session_preview", "key", "value_preview", "updated_at"]
    list_filter = ["key"]
    search_fields = ["session_id", "key"]
    readonly_fields = ["session_id", "key", "value", "created_at", "updated_at"]

    def session_preview(self, obj):
        return obj.session_id[:16] + "…"

    def value_preview(self, obj):
        val = obj.value
        if isinstance(val, str):
            return val[:60] + "…" if len(val) > 60 else val
        return str(val)[:60]

    session_preview.short_description = "Session"
    value_preview.short_description = "Value"
