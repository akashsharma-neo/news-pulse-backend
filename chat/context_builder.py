"""
Service for building structured prompts for the NewsPulse chat API.
Handles aggregation of article summaries, source links, and message history.
"""

from typing import List, Dict, Any
import openai
from django.db import models
from .models import ChatMessage
from articles.models import TopicCluster


class ChatContextBuilder:
    """Builds the conversation payload for OpenAI API calls."""

    def __run_query(self, cluster: TopicCluster) -> str:
        """Aggregates article summary and source info into a text block."""
        context = f"Article Summary: {cluster.summary}\n"
        if cluster.primary_article.source:
            context += f"Source: {cluster.primary_article.source.name}\n"
            context += f"URL: {cluster.primary_article.url}\n"
        return context

    def get_messages_for_api(self, cluster: TopicCluster) -> List[Dict[str, str]]:
        """
        Constructs the list of message objects (role/content) for the OpenAI API.
        Includes a system prompt with context and all recent chat history.
        """
        # 1. Build System Prompt with Article Context
        context_text = self._run_query(cluster)
        system_message = {
            "role": "system",
            "content": (
                "You are a helpful, concise news assistant for NewsPulse. "
                "Your goal is to provide accurate follow-up information based on the provided article context. "
                f"Context:\n{context_text}"
            )
        }

        # 2. Fetch Chat History
        history = ChatMessage.objects.filter(cluster=cluster).order_by('created_at')
        
        messages = [system_message]
        for msg in history:
            # Map internal role names to OpenAI compatible roles (user, assistant, system)
            messages.append({
                "role": msg.role,
                "content": msg.content
            })

        return messages
