"""
NewsPulse chat API views.
"""

import logging

from django.conf import settings
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from .models import ChatMessage
from .serializers import ChatMessageSerializer
from .context_builder import ChatContextBuilder
from .llm import build_chat_completion_kwargs
from articles.models import TopicCluster

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
    """API for managing chat messages within a topic cluster thread."""

    queryset = ChatMessage.objects.all()
    serializer_class = ChatMessageSerializer
    http_method_names = ['get', 'head', 'options', 'post']

    def get_permissions(self):
        if self.action in ('send_message', 'list', 'retrieve'):
            return [IsAuthenticated()]
        return [AllowAny()]

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
        """Return messages only for the cluster_id query parameter."""
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
        """
        Sends a user message and returns the OpenAI assistant response.
        Expects: cluster_id (in body or query) and content (in body).

        Example Body:
        {
            "cluster_id": 1,
            "content": "What is this about?"
        }

        cluster_id is the numeric TopicCluster PK (same as GET /api/messages/?cluster_id=).
        Requires authentication.
        """
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
                "assistant_message": ChatMessageSerializer(assistant_msg).data
            }, status=status.HTTP_201_CREATED)

        except Exception:
            logger.exception("Chat LLM request failed for cluster %s", cluster_pk)
            return Response(
                {"error": "Failed to get AI response. Please try again later."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
