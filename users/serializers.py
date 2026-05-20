"""
NewsPulse personalization serializers.

Maps UserInteraction and UserPreference models to JSON for API responses.
"""

from rest_framework import serializers
from .models import UserInteraction, UserPreference, User
from articles.models import TopicCluster


class UserInteractionSerializer(serializers.ModelSerializer):
    """Serialize a UserInteraction record.

    Extra fields:
        cluster_title: Title of the clustered story.
        category: Tab/category slug of the cluster.
    """

    cluster_title = serializers.CharField(
        source="cluster.primary_article.title",
        read_only=True,
    )
    category = serializers.CharField(
        source="cluster.primary_article.source.category.slug",
        read_only=True,
    )

    class Meta:
        model = UserInteraction
        fields = [
            "id", "session_id", "interaction_type",
            "cluster", "cluster_title", "category",
            "dwell_seconds", "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class UserPreferenceSerializer(serializers.ModelSerializer):
    """Serialize a UserPreference record.

    Extra fields:
        session_id: Truncated to 8 chars for privacy.
    """

    class Meta:
        model = UserPreference
        fields = ["id", "session_id", "key", "value", "created_at", "updated_at"]
        read_only_fields = fields


class PersonalizedRankScoreSerializer(serializers.Serializer):
    """Response shape for the personalized ranking endpoint.

    Each item includes the cluster data plus a computed rank_score
    that combines topic affinity with recency decay.
    """

    cluster = serializers.SerializerMethodField(
        help_text="The TopicCluster data (same shape as standard cluster serializer)",
    )
    rank_score = serializers.FloatField(
        help_text="Computed ranking score: affinity_weighted + recency_decay",
    )
    category = serializers.CharField(
        help_text="Tab/category slug of the cluster",
    )

    def get_cluster(self, obj: dict) -> dict:
        """Return the cluster data from the cached serializer."""
        return obj["cluster_data"]


# ---------------------------------------------------------------------------
# Auth Serializers
# ---------------------------------------------------------------------------

class UserRegisterSerializer(serializers.ModelSerializer):
    """Serializer for user registration.

    Creates a new user and returns a token pair via the view.
    """

    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ["email", "phone", "name", "password", "password_confirm"]

    def validate(self, data):
        if data["password"] != data["password_confirm"]:
            raise serializers.ValidationError({"password_confirm": "Passwords do not match."})
        return data

    def create(self, validated_data):
        validated_data.pop("password_confirm")
        validated_data.setdefault("name", "")
        validated_data["email_verified"] = False
        return User.objects.create_user(**validated_data)


class UserSerializer(serializers.ModelSerializer):
    """Serializer for the current user's profile."""

    monthly_ai_chat_remaining = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "email", "phone", "name", "date_joined",
            "email_verified", "phone_verified",
            "monthly_ai_chat_used", "monthly_ai_chat_limit", "monthly_ai_chat_remaining",
        ]
        read_only_fields = [
            "email", "date_joined", "email_verified", "phone_verified",
            "monthly_ai_chat_used", "monthly_ai_chat_limit", "monthly_ai_chat_remaining",
        ]

    def get_monthly_ai_chat_remaining(self, obj) -> int:
        if obj.monthly_ai_chat_limit <= 0:
            return 0
        return max(0, obj.monthly_ai_chat_limit - obj.monthly_ai_chat_used)


class TokenObtainPairSerializer(serializers.Serializer):
    """Custom token obtain pair serializer that accepts email OR phone.

    Extends simplejwt's TokenObtainPairSerializer to allow login
    with either email or phone number.
    """

    email = serializers.EmailField(required=False)
    phone = serializers.CharField(required=False)
    password = serializers.CharField(required=True, write_only=True)

    def validate(self, data):
        credentials = {}
        email = data.get("email", "").strip()
        phone = data.get("phone", "").strip()
        password = data.get("password", "")

        if not email and not phone:
            raise serializers.ValidationError(
                "Either 'email' or 'phone' must be provided."
            )
        if not password:
            raise serializers.ValidationError("Password is required.")

        # Try to find user by email first, then phone
        user = None
        if email:
            try:
                user = User.objects.get(email=email)
            except User.DoesNotExist:
                pass
        elif phone:
            try:
                user = User.objects.get(phone=phone)
            except User.DoesNotExist:
                pass

        if user is None:
            raise serializers.ValidationError("Invalid credentials.")
        if not user.check_password(password):
            raise serializers.ValidationError("Invalid credentials.")
        if not user.is_active:
            raise serializers.ValidationError("User account is disabled.")
        if not user.email_verified:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied(
                {"code": "email_not_verified", "detail": "Please verify your email before signing in."}
            )

        from .auth_tokens import jwt_response
        return jwt_response(user)


class VerifyEmailSerializer(serializers.Serializer):
    token = serializers.UUIDField()


class ResendVerificationSerializer(serializers.Serializer):
    email = serializers.EmailField()


class FirebaseAuthSerializer(serializers.Serializer):
    id_token = serializers.CharField()
