import logging

from django.conf import settings
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from .models import ChatMessage
from .serializers import ChatMessageSerializer
from .context_builder import ChatContextBuilder
from .llm import build_chat_completion_kwargs
from articles.models import TopicCluster
from core.quota import QuotaManager, RateLimiter

logger = logging.getLogger(__name__)


class ChatSendThrottle(ScopedRateThrottle):
    scope = 'chat_send'


_openai_client = None


def get_openai_client():
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI
        _openai_client = OpenAI(
            api_key=settings.OPENAI_COMPATIBLE_API_KEY,
            base_url=settings.OPENAI_COMPATIBLE_BASE_URL,
        )
    return _openai_client


class ChatMessageViewSet(viewsets.ModelViewSet):
    queryset = ChatMessage.objects.all()
    serializer_class = ChatMessageSerializer
    http_method_names = ['get', 'head', 'options', 'post']
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        return Response(
            {'error': 'Use POST /api/messages/send/ with cluster_id and content.'},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def update(self, request, *args, **kwargs):
        return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)

    def partial_update(self, request, *args, **kwargs):
        return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)

    def destroy(self, request, *args, **kwargs):
        return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)

    def list(self, request, *args, **kwargs):
        cluster_id = request.query_params.get("cluster_id")
        if not cluster_id:
            return Response(
                {"error": "cluster_id query parameter is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        cluster_id = self.request.query_params.get("cluster_id")
        if not cluster_id:
            return ChatMessage.objects.none()
        try:
            cluster_pk = int(cluster_id)
        except (TypeError, ValueError):
            return ChatMessage.objects.none()
        return super().get_queryset().filter(cluster_id=cluster_pk)

    @action(detail=False, methods=['post'], url_path='send', throttle_classes=[ChatSendThrottle])
    def send_message(self, request):
        cluster_id = request.data.get("cluster_id")
        content = request.data.get("content")

        if cluster_id is None or not content:
            return Response(
                {"error": "cluster_id and content are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            cluster_pk = int(cluster_id)
        except (TypeError, ValueError):
            return Response(
                {"error": "cluster_id must be a numeric TopicCluster primary key."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Identity resolution
        if request.user.is_authenticated:
            identity_type = "user"
            identity_id = str(request.user.pk)
            user = request.user
        else:
            identity_type = "anon"
            identity_id = request.headers.get("X-Device-ID", "")
            user = None
            if not identity_id:
                return Response(
                    {"error": "X-Device-ID header is required for anonymous users."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Rate limit check
        if not RateLimiter.check(identity_type, identity_id, "chat", 30, 3600):
            return Response(
                {"error": "Too many requests. Please slow down.", "code": "rate_limited"},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        if not RateLimiter.check(identity_type, identity_id, "chat_burst", 5, 60):
            return Response(
                {"error": "Too many requests. Please slow down.", "code": "rate_limited"},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        # Quota check
        allowed, quota = QuotaManager.try_consume_ai_chat(identity_type, identity_id, user)
        if not allowed:
            return Response(
                {
                    "error": "Monthly AI chat limit reached. Resets on your new billing cycle.",
                    "code": "quota_exceeded",
                    "quota": quota,
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        try:
            cluster = TopicCluster.objects.get(id=cluster_pk)
        except TopicCluster.DoesNotExist:
            return Response(
                {"error": "TopicCluster not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        user_msg = ChatMessage.objects.create(
            cluster=cluster,
            role="user",
            content=content
        )

        builder = ChatContextBuilder()
        messages_for_api = builder.get_messages_for_api(cluster)

        try:
            client = get_openai_client()
            response = client.chat.completions.create(
                **build_chat_completion_kwargs(messages_for_api),
            )
            assistant_content = response.choices[0].message.content

            assistant_msg = ChatMessage.objects.create(
                cluster=cluster,
                role="assistant",
                content=assistant_content
            )

            return Response({
                "user_message": ChatMessageSerializer(user_msg).data,
                "assistant_message": ChatMessageSerializer(assistant_msg).data,
                "quota": quota,
            }, status=status.HTTP_201_CREATED)

        except Exception:
            logger.exception("Chat LLM request failed for cluster %s", cluster_pk)
            return Response(
                {"error": "Failed to get AI response. Please try again later."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
