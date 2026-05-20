"""Tests for the chat API — message listing, sending, context building, and permissions."""

from unittest.mock import patch, MagicMock

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

_THROTTLE_OVERRIDE = {
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_THROTTLE_CLASSES': (
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
        'rest_framework.throttling.ScopedRateThrottle',
    ),
    'DEFAULT_THROTTLE_RATES': {
        'anon': '1000000/hour',
        'user': '1000000/hour',
        'auth': '1000000/hour',
        'chat_send': '1000000/hour',
        'digest_subscribe': '1000000/hour',
    },
}

from articles.models import Tab, Source, Article, TopicCluster
from chat.models import ChatMessage
from chat.context_builder import ChatContextBuilder
from chat.llm import build_chat_completion_kwargs, chat_web_search_enabled


class ChatModelTest(TestCase):
    def setUp(self):
        self.tab = Tab.objects.create(name="Global", slug="global", order=1)
        self.source = Source.objects.create(
            name="BBC", url="https://bbc.com/feed", category=self.tab,
        )
        self.article = Article.objects.create(
            title="Story", url="https://bbc.com/1",
            source=self.source, published_at=timezone.now(),
        )
        self.cluster = TopicCluster.objects.create(
            topic_id="00000000-0000-0000-0000-000000000001",
            primary_article=self.article, summary="Test summary.",
        )
        self.msg = ChatMessage.objects.create(
            cluster=self.cluster, role="user", content="What is this about?",
        )

    def test_chat_message_creation(self):
        self.assertEqual(self.msg.role, "user")
        self.assertEqual(self.msg.content, "What is this about?")
        self.assertEqual(self.msg.cluster, self.cluster)

    def test_chat_message_str(self):
        self.assertIn("user", str(self.msg))
        self.assertIn("What is this about?", str(self.msg))

    def test_string_content_property(self):
        self.assertEqual(self.msg.string_content, "What is this about?")

    def test_chat_message_ordering(self):
        ChatMessage.objects.create(cluster=self.cluster, role="assistant", content="Reply")
        msgs = ChatMessage.objects.all()
        self.assertEqual(msgs[0].role, "user")
        self.assertEqual(msgs[1].role, "assistant")


class ChatContextBuilderTest(TestCase):
    def setUp(self):
        self.tab = Tab.objects.create(name="Global", slug="global", order=1)
        self.source = Source.objects.create(
            name="BBC", url="https://bbc.com/feed", category=self.tab,
        )
        self.article = Article.objects.create(
            title="Story", url="https://bbc.com/1",
            source=self.source, published_at=timezone.now(),
        )
        self.cluster = TopicCluster.objects.create(
            topic_id="00000000-0000-0000-0000-000000000001",
            primary_article=self.article, summary="Test summary.",
        )
        ChatMessage.objects.create(cluster=self.cluster, role="user", content="Hello")
        ChatMessage.objects.create(cluster=self.cluster, role="assistant", content="Hi there")

    def test_get_messages_for_api_includes_context(self):
        builder = ChatContextBuilder()
        messages = builder.get_messages_for_api(self.cluster)
        self.assertEqual(len(messages), 3)
        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("Test summary", messages[0]["content"])
        self.assertIn("BBC", messages[0]["content"])
        self.assertEqual(messages[1]["role"], "user")
        self.assertEqual(messages[1]["content"], "Hello")
        self.assertEqual(messages[2]["role"], "assistant")
        self.assertEqual(messages[2]["content"], "Hi there")

    def test_run_query_includes_summary_and_source(self):
        builder = ChatContextBuilder()
        context = builder._run_query(self.cluster)
        self.assertIn("Test summary", context)
        self.assertIn("BBC", context)
        self.assertIn("https://bbc.com/1", context)

    def test_system_prompt_mentions_web_search(self):
        builder = ChatContextBuilder()
        messages = builder.get_messages_for_api(self.cluster)
        self.assertIn("search the web", messages[0]["content"])


class ChatLLMTest(TestCase):
    @override_settings(
        CHAT_WEB_SEARCH_ENABLED=True,
        CHAT_WEB_SEARCH_MAX_RESULTS=3,
        CHAT_WEB_SEARCH_MAX_TOTAL_RESULTS=8,
        OPENAI_COMPATIBLE_MODEL="meta-llama/llama-3.1-8b-instruct",
    )
    def test_build_kwargs_includes_web_search_tool(self):
        messages = [{"role": "user", "content": "What happened today?"}]
        kwargs = build_chat_completion_kwargs(messages)
        self.assertTrue(chat_web_search_enabled())
        tools = kwargs["extra_body"]["tools"]
        self.assertEqual(tools[0]["type"], "openrouter:web_search")
        self.assertEqual(tools[0]["parameters"]["max_results"], 3)
        self.assertEqual(tools[0]["parameters"]["max_total_results"], 8)

    @override_settings(CHAT_WEB_SEARCH_ENABLED=False, OPENAI_COMPATIBLE_MODEL="gpt-4o-mini")
    def test_build_kwargs_omits_web_search_when_disabled(self):
        kwargs = build_chat_completion_kwargs([{"role": "user", "content": "Hi"}])
        self.assertNotIn("extra_body", kwargs)


@override_settings(REST_FRAMEWORK=_THROTTLE_OVERRIDE)
class ChatAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.tab = Tab.objects.create(name="Global", slug="global", order=1)
        self.source = Source.objects.create(
            name="BBC", url="https://bbc.com/feed", category=self.tab,
        )
        self.article = Article.objects.create(
            title="Story", url="https://bbc.com/1",
            source=self.source, published_at=timezone.now(),
        )
        self.cluster = TopicCluster.objects.create(
            topic_id="00000000-0000-0000-0000-000000000001",
            primary_article=self.article, summary="Test summary.",
        )

    def _login(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user = User.objects.create_user(
            email="chat@example.com", password="testpass123",
        )
        self.client.force_authenticate(user=user)

    def test_list_messages_requires_cluster_id(self):
        self._login()
        response = self.client.get("/api/messages/")
        self.assertEqual(response.status_code, 400)

    def test_list_messages_with_cluster_id(self):
        self._login()
        ChatMessage.objects.create(cluster=self.cluster, role="user", content="Hi")
        response = self.client.get(f"/api/messages/?cluster_id={self.cluster.pk}")
        self.assertEqual(response.status_code, 200)
        results = response.data.get("results", [response.data] if isinstance(response.data, list) else [])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["content"], "Hi")

    def test_list_messages_anonymous(self):
        """Chat history is publicly accessible per cluster (no auth needed)."""
        response = self.client.get(f"/api/messages/?cluster_id={self.cluster.pk}")
        self.assertEqual(response.status_code, 200)

    def test_send_message_requires_device_id(self):
        """Anonymous send requires X-Device-ID header."""
        response = self.client.post("/api/messages/send/", {"cluster_id": 1, "content": "Hi"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("X-Device-ID", str(response.data))

    def test_send_message_missing_fields(self):
        self._login()
        response = self.client.post("/api/messages/send/", {}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("cluster_id and content are required", str(response.data))

    def test_send_message_invalid_cluster_id(self):
        self._login()
        response = self.client.post("/api/messages/send/",
                                     {"cluster_id": "abc", "content": "Hi"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_send_message_nonexistent_cluster(self):
        self._login()
        response = self.client.post("/api/messages/send/",
                                     {"cluster_id": 99999, "content": "Hi"}, format="json")
        self.assertEqual(response.status_code, 404)

    @override_settings(
        OPENAI_COMPATIBLE_API_KEY="sk-test",
        OPENAI_COMPATIBLE_MODEL="gpt-4o-mini",
        CHAT_WEB_SEARCH_ENABLED=True,
    )
    @patch("chat.views.get_openai_client")
    def test_send_message_creates_messages(self, mock_get_client):
        self._login()
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="AI response."))],
        )
        response = self.client.post("/api/messages/send/",
                                     {"cluster_id": self.cluster.pk, "content": "Explain this"},
                                     format="json")
        self.assertEqual(response.status_code, 201)
        self.assertIn("user_message", response.data)
        self.assertIn("assistant_message", response.data)
        self.assertEqual(response.data["user_message"]["content"], "Explain this")
        self.assertEqual(response.data["assistant_message"]["content"], "AI response.")
        self.assertEqual(ChatMessage.objects.count(), 2)
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        self.assertEqual(
            call_kwargs["extra_body"]["tools"][0]["type"],
            "openrouter:web_search",
        )

    @override_settings(OPENAI_COMPATIBLE_API_KEY="sk-test", OPENAI_COMPATIBLE_MODEL="gpt-4o-mini")
    @patch("chat.views.get_openai_client")
    def test_send_message_handles_openai_error(self, mock_get_client):
        self._login()
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.chat.completions.create.side_effect = Exception("API Error")
        response = self.client.post("/api/messages/send/",
                                     {"cluster_id": self.cluster.pk, "content": "Hi"},
                                     format="json")
        self.assertEqual(response.status_code, 500)
        self.assertIn("Failed to get AI response", str(response.data))

    def test_create_disabled(self):
        self._login()
        response = self.client.post("/api/messages/", {"role": "user", "content": "test"}, format="json")
        self.assertEqual(response.status_code, 405)

    def test_update_disabled(self):
        self._login()
        msg = ChatMessage.objects.create(cluster=self.cluster, role="user", content="test")
        response = self.client.put(f"/api/messages/{msg.pk}/", {"content": "new"}, format="json")
        self.assertEqual(response.status_code, 405)

    def test_delete_disabled(self):
        self._login()
        msg = ChatMessage.objects.create(cluster=self.cluster, role="user", content="test")
        response = self.client.delete(f"/api/messages/{msg.pk}/")
        self.assertEqual(response.status_code, 405)
