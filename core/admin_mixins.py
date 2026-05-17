"""Shared Django admin mixins for NewsPulse."""


class TotalCountChangeListMixin:
    """Show full-table row count on every admin changelist page."""

    change_list_template = "admin/change_list_with_count.html"

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["model_total_count"] = self.model.objects.count()
        return super().changelist_view(request, extra_context)
