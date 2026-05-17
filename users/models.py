"""
NewsPulse users app models — authentication, personalization, and interaction tracking.

Models:
    User — Custom user model (email/phone based auth)
    UserInteraction — Tracks user interactions with clusters
    UserPreference — Stored user preferences for personalization tuning
"""

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


# ---------------------------------------------------------------------------
# Custom User Model
# ---------------------------------------------------------------------------

class UserManager(BaseUserManager):
    """Custom manager for the User model."""

    def create_user(self, email, phone=None, name=None, password=None, **extra_fields):
        """Create and return a regular user."""
        if not email:
            raise ValueError("The Email field must be set")
        email = self.normalize_email(email)
        name = name or ""
        user = self.model(email=email, phone=phone, name=name, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email=None, phone=None, name=None, password=None, **extra_fields):
        """Create and return a superuser.

        Accepts either email or phone (at least one required).
        If only phone is provided, a placeholder email is generated.
        """
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        if not email and not phone:
            raise ValueError("Superuser must have at least an email or a phone number.")

        # If only phone provided, generate a placeholder email for the USERNAME_FIELD
        if not email and phone:
            phone_clean = phone.replace(" ", "").replace("-", "").replace("+", "")
            email = f"{phone_clean}@newspulse.local"

        return self.create_user(email, phone, name, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """Custom user model using email as the unique identifier.

    Supports login via email or phone number.
    """

    email = models.EmailField(max_length=254, unique=True)
    phone = models.CharField(max_length=20, blank=True, null=True, unique=True)
    name = models.CharField(max_length=150, blank=True, default="")
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(default=timezone.now, editable=False)
    is_staff = models.BooleanField(default=False)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["phone"]

    class Meta:
        db_table = "users_user"

    def __str__(self):
        return self.email

    @property
    def full_name(self):
        """Return the user's full name."""
        return self.name.strip() if self.name else ""


# ---------------------------------------------------------------------------
# Interaction / Preference Models
# ---------------------------------------------------------------------------

class UserInteraction(models.Model):
    """Records a user's interaction with a topic cluster.

    Used by the personalization engine to build topic affinity profiles
    for each anonymous session (or authenticated user in the future).

    Interaction types:
        - **click**: User clicked on a cluster card in the feed
        - **save**: User saved/bookmarked a cluster
        - **dwell**: User spent significant time reading a cluster (future)

    Affinity is calculated by aggregating interactions per category/tab,
    weighted by recency using exponential decay (half-life ~7 days).
    """

    INTERACTION_TYPES = (
        ("click", "User clicked on the cluster"),
        ("save", "User saved/bookmarked the cluster"),
        ("dwell", "User spent significant time on the cluster"),
    )

    session_id = models.CharField(
        max_length=128,
        help_text="Anonymous session ID (UUID). Later replaced by user FK.",
    )
    interaction_type = models.CharField(
        max_length=10,
        choices=INTERACTION_TYPES,
        help_text="Type of interaction recorded",
    )
    cluster = models.ForeignKey(
        "articles.TopicCluster",
        on_delete=models.CASCADE,
        related_name="interactions",
        help_text="The cluster the user interacted with",
    )
    dwell_seconds = models.PositiveIntegerField(
        default=0,
        help_text="Time spent on the cluster in seconds (for 'dwell' type)",
    )
    created_at = models.DateTimeField(
        default=timezone.now,
        help_text="When this interaction was recorded",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["session_id", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.session_id[:8]}: {self.interaction_type} → {self.cluster}"


class UserPreference(models.Model):
    """Stored user preferences for personalization tuning.

    Currently stores explicit preferences (e.g., muted topics, preferred
    sources). Later can store saved search queries, notification settings, etc.

    This model is a placeholder for Phase 5 (polish) — the personalization
    engine primarily relies on implicit signals from UserInteraction.
    """

    session_id = models.CharField(
        max_length=128,
        help_text="Anonymous session ID. Later replaced by user FK.",
    )
    key = models.CharField(
        max_length=100,
        help_text="Preference key, e.g. 'muted_topics', 'preferred_sources'",
    )
    value = models.JSONField(
        default=dict,
        blank=True,
        help_text="Preference value as JSON",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["-updated_at"]
        unique_together = ["session_id", "key"]

    def __str__(self):
        return f"{self.session_id[:8]}: {self.key}"
