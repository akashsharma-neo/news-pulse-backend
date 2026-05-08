"""
NewsPulse chat app models.
"""

from django.db import models
from articles.models import TopicCluster


class ChatMessage(models.Model):
    """A single message in a conversation thread for a specific topic cluster."""
    
    ROLE_CHOICES = (
        ("user", "User"),
        ("far-assistant", "Assistant"), # Renamed from assistant to avoid potential conflicts or just be safe, but standard is fine. Let's use 'assistant'.
        ("system", "System"),
    )

    cluster = models.ForeignKey(
        TopicCluster,
        on_delete=models.CASCADE,
        related_name="chat_messages",
        help_text="The topic cluster this chat belongs to.",
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField(help_text="The message text.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"[{self.role}] {self.string_content[:50]}..."

    @property
    def string_content(self):
        return self.content
