"""
NewsPulse chat API views.
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.conf import settings
from .models import ChatMessage
from .serializers import ChatMessageSerializer
from .context_builder import ChatContextBuilder
from articles.models import TopicCluster

# Lazy import to avoid hard dependency if openai isn't installed
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

    def get_queryset(self):
        """Return messages only for a specific cluster."""
        qs = super().get_queryset()
        cluster_id = self.request.query_params.get("cluster_id")
        if cluster_id:
            qs = qs.filter(cluster_id=cluster_id)
        return qs

    @action(detail=False, methods=['post'], url_path='send')
    def send_message(self, request):
        """
        Sends a user message and returns the OpenAI assistant response.
        Expects: cluster_id (in body or query) and content (in body).

        Example Body:
        {
            "cluster_id": "...",
            "content": "What is this about?"
        }
        """
        cluster_id = request.data.get("cluster_id")
        content = request.data.get("content")

        if not cluster_id or not content:
            return Response(
                {"error": "cluster_id and content are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            cluster = TopicCluster.objects.get(topic_id=cluster_id)
        except TopicCluster.DoesNotExist:
            return Response(
                {"error": "TopicCluster not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        # 1. Save User Message
        user_msg = ChatMessage.objects.create(
            cluster=cluster,
            role="user",
            content=content
        )

        # 2. Build Prompt using Context Builder (Task 3.2)
        builder = ChatContextBuilder()
        messages_for_api = builder.get_messages_for_api(cluster)

        # 3. Call OpenAI API
        client = get_openai_client()

        try:
            response = client.chat.completions.create(
                model=settings.OPENAI_COMPATIBLE_MODEL,
                messages=messages_for_api,
                max_tokens=512,
                temperature=0.7,
            )
            assistant_content = response.choices[0].message.content

            # 4. Save Assistant Message
            assistant_msg = ChatMessage.objects.create(
                cluster=cluster,
                role="assistant",
                content=assistant_content
            )

            return Response({
                "user_message": ChatMessageSerializer(user_msg).data,
                "assistant_message": ChatMessageSerializer(assistant_msg).data
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response(
                {"error": f"Failed to get AI response: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
