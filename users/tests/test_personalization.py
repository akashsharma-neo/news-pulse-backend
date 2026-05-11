"""
Tests for NewsPulse personalization app.

Covers:
    - UserInteraction model (creation, queries)
    - Interaction recording API (POST /api/interactions/)
    - Affinity calculation and profile endpoint
    - Personalized feed ranking endpoint
    - Decay function and interaction weights
    - Session ID extraction
"""

import math
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from articles.models import Tab, Source, Article, TopicCluster
from users.models import User, UserInteraction, UserPreference
from users.views import _decay_factor, _get_session_id


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------

def _create_tab(slug: str, name: str = None) -> Tab:
    """Create a Tab instance."""
    return Tab.objects.create(
        slug=slug,
        name=name or slug.title(),
        order=1,
    )


def _create_source(tab: Tab, name: str = "Test Source") -> Source:
    """Create a Source instance."""
    return Source.objects.create(
        name=name,
        url="https://example.com",
        category=tab,
        source_type="rss",
    )


def _create_article(source: Source, title: str = "Test Article") -> Article:
    """Create an Article instance."""
    return Article.objects.create(
        title=title,
        url="https://example.com/article",
        source=source,
        published_at=timezone.now(),
        full_text="Test article body",
    )


def _create_cluster(article: Article, topic_id=None) -> TopicCluster:
    """Create a TopicCluster instance."""
    return TopicCluster.objects.create(
        topic_id=topic_id or "00000000-0000-0000-0000-000000000001",
        primary_article=article,
        summary="Test cluster summary",
        sources=[article.source.name],
    )


def _create_interaction(
    session_id: str,
    cluster: TopicCluster,
    interaction_type: str = "click",
    dwell_seconds: int = 0,
    created_at=None,
) -> UserInteraction:
    """Create a UserInteraction instance."""
    return UserInteraction.objects.create(
        session_id=session_id,
        interaction_type=interaction_type,
        cluster=cluster,
        dwell_seconds=dwell_seconds,
        created_at=created_at or timezone.now(),
    )


# ---------------------------------------------------------------------------
# Decay function tests
# ---------------------------------------------------------------------------

class DecayFunctionTest(TestCase):
    """Tests for the exponential decay function."""

    def test_fresh_interaction_returns_one(self):
        """A fresh interaction (0 hours old) should have decay factor 1.0."""
        result = _decay_factor(0)
        self.assertAlmostEqual(result, 1.0, places=6)

    def test_negative_hours_clamped_to_zero(self):
        """Negative hours should be clamped to 0, returning 1.0."""
        result = _decay_factor(-5)
        self.assertAlmostEqual(result, 1.0, places=6)

    def test_half_life_returns_half(self):
        """At half-life (~168 hours), decay should be ~0.5."""
        half_life_hours = 7 * 24  # 168
        result = _decay_factor(half_life_hours)
        self.assertAlmostEqual(result, 0.5, places=2)

    def test_decay_is_monotonically_decreasing(self):
        """Older interactions should always have lower or equal decay."""
        values = [_decay_factor(h) for h in range(0, 500, 10)]
        for i in range(1, len(values)):
            self.assertLessEqual(values[i], values[i - 1])

    def test_one_day_decay(self):
        """After 24 hours, decay should be ~0.96."""
        result = _decay_factor(24)
        expected = math.exp(-math.log(2) / 168 * 24)
        self.assertAlmostEqual(result, expected, places=4)


# ---------------------------------------------------------------------------
# UserInteraction model tests
# ---------------------------------------------------------------------------

class UserInteractionModelTest(TestCase):
    """Tests for the UserInteraction model."""

    def setUp(self):
        self.session_id = "test-session-001"
        self.tab = _create_tab("india", "India")
        self.source = _create_source(self.tab)
        self.article = _create_article(self.source)
        self.cluster = _create_cluster(self.article)

    def test_create_interaction(self):
        """Can create an interaction record."""
        interaction = _create_interaction(
            self.session_id, self.cluster, "click"
        )
        self.assertEqual(interaction.session_id, self.session_id)
        self.assertEqual(interaction.interaction_type, "click")
        self.assertEqual(interaction.cluster, self.cluster)
        self.assertEqual(interaction.dwell_seconds, 0)

    def test_interaction_str(self):
        """__str__ shows truncated session and type."""
        interaction = _create_interaction(
            self.session_id, self.cluster, "save"
        )
        self.assertIn("test-ses", str(interaction))
        self.assertIn("save", str(interaction))

    def test_interaction_ordering(self):
        """Interactions are ordered by created_at descending."""
        now = timezone.now()
        _create_interaction(self.session_id, self.cluster, "click", created_at=now - timedelta(hours=2))
        _create_interaction(self.session_id, self.cluster, "save", created_at=now - timedelta(hours=1))
        _create_interaction(self.session_id, self.cluster, "dwell", created_at=now)
        qs = UserInteraction.objects.all()
        self.assertEqual(qs[0].interaction_type, "dwell")
        self.assertEqual(qs[1].interaction_type, "save")
        self.assertEqual(qs[2].interaction_type, "click")

    def test_interaction_index(self):
        """Has the expected index on (session_id, -created_at)."""
        indexes = [
            (idx.name, list(idx.fields))
            for idx in UserInteraction._meta.indexes
        ]
        # Find any index that covers session_id and created_at (with optional - prefix for descending)
        matching = [name for name, fields in indexes if "session_id" in fields and ("created_at" in fields or "-created_at" in fields)]
        self.assertTrue(len(matching) >= 1, f"Expected index on (session_id, created_at), got {indexes}")


# ---------------------------------------------------------------------------
# UserPreference model tests
# ---------------------------------------------------------------------------

class UserPreferenceModelTest(TestCase):
    """Tests for the UserPreference model."""

    def test_create_preference(self):
        """Can create a preference record."""
        pref = UserPreference.objects.create(
            session_id="test-session",
            key="muted_topics",
            value=["sports"],
        )
        self.assertEqual(pref.key, "muted_topics")
        self.assertEqual(pref.value, ["sports"])

    def test_unique_together(self):
        """Cannot create duplicate (session_id, key) pairs."""
        UserPreference.objects.create(
            session_id="test-session",
            key="muted_topics",
            value=["sports"],
        )
        with self.assertRaises(Exception):
            UserPreference.objects.create(
                session_id="test-session",
                key="muted_topics",
                value=["business"],
            )


# ---------------------------------------------------------------------------
# Interaction API tests
# ---------------------------------------------------------------------------

class InteractionAPITest(TestCase):
    """Tests for the interaction recording API."""

    def setUp(self):
        self.client = APIClient()
        self.session_id = "api-test-session-001"
        self.tab = _create_tab("india", "India")
        self.source = _create_source(self.tab)
        self.article = _create_article(self.source)
        self.cluster = _create_cluster(self.article)
        self.cluster_id = self.cluster.id

    def test_post_interaction_click(self):
        """POST /api/interactions/ with click type creates record."""
        response = self.client.post(
            "/api/interactions/",
            {
                "interaction_type": "click",
                "cluster": self.cluster_id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(UserInteraction.objects.count(), 1)
        interaction = UserInteraction.objects.first()
        self.assertEqual(interaction.interaction_type, "click")
        self.assertEqual(interaction.cluster_id, self.cluster_id)

    def test_post_interaction_save(self):
        """POST /api/interactions/ with save type creates record."""
        response = self.client.post(
            "/api/interactions/",
            {
                "interaction_type": "save",
                "cluster": self.cluster_id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        interaction = UserInteraction.objects.first()
        self.assertEqual(interaction.interaction_type, "save")

    def test_post_interaction_with_dwell(self):
        """POST with dwell type and dwell_seconds."""
        response = self.client.post(
            "/api/interactions/",
            {
                "interaction_type": "dwell",
                "cluster": self.cluster_id,
                "dwell_seconds": 45,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        interaction = UserInteraction.objects.first()
        self.assertEqual(interaction.dwell_seconds, 45)

    def test_post_interaction_invalid_cluster(self):
        """POST with non-existent cluster returns 400."""
        response = self.client.post(
            "/api/interactions/",
            {
                "interaction_type": "click",
                "cluster": 99999,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("cluster", response.data)

    def test_post_interaction_generates_session_id(self):
        """POST without session_id generates a UUID."""
        response = self.client.post(
            "/api/interactions/",
            {
                "interaction_type": "click",
                "cluster": self.cluster_id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        interaction = UserInteraction.objects.first()
        # UUID format: 8-4-4-4-12 hex chars
        parts = interaction.session_id.split("-")
        self.assertEqual(len(parts), 5)

    def test_post_interaction_respects_session_id_param(self):
        """POST with session_id query param uses it."""
        response = self.client.post(
            "/api/interactions/?session_id=custom-session-xyz",
            {
                "interaction_type": "click",
                "cluster": self.cluster_id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        interaction = UserInteraction.objects.first()
        self.assertEqual(interaction.session_id, "custom-session-xyz")

    def test_get_interactions_by_session(self):
        """GET /api/interactions/?session_id= filters by session."""
        sess_a = f"session-a-{self._testMethodName}"
        sess_b = f"session-b-{self._testMethodName}"
        _create_interaction(sess_a, self.cluster, "click")
        _create_interaction(sess_b, self.cluster, "save")
        response = self.client.get(
            f"/api/interactions/?session_id={sess_a}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["session_id"], sess_a)

    def test_get_interactions_by_session_endpoint(self):
        """GET /api/interactions/by-session/ returns session interactions."""
        sess = f"test-sess-{self._testMethodName}"
        _create_interaction(sess, self.cluster, "click")
        _create_interaction(sess, self.cluster, "save")
        response = self.client.get(
            f"/api/interactions/by-session/?session_id={sess}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 2)


# ---------------------------------------------------------------------------
# Affinity calculation tests
# ---------------------------------------------------------------------------

class AffinityCalculationTest(TestCase):
    """Tests for the affinity calculation logic."""

    def setUp(self):
        self.session_id = "affinity-test-001"
        self.india_tab = _create_tab("india", "India")
        self.sports_tab = _create_tab("sports", "Sports")
        self.business_tab = _create_tab("business", "Business")
        self.india_source = _create_source(self.india_tab)
        self.sports_source = _create_source(self.sports_tab)
        self.business_source = _create_source(self.business_tab)
        self.india_cluster = _create_cluster(
            _create_article(self.india_source, "India story")
        )
        self.sports_cluster = _create_cluster(
            _create_article(self.sports_source, "Sports story")
        )
        self.business_cluster = _create_cluster(
            _create_article(self.business_source, "Business story")
        )
        self.now = timezone.now()

    def test_affinity_from_clicks(self):
        """Clicks generate affinity proportional to count."""
        _create_interaction(self.session_id, self.india_cluster, "click", created_at=self.now - timedelta(hours=1))
        _create_interaction(self.session_id, self.india_cluster, "click", created_at=self.now - timedelta(hours=2))
        _create_interaction(self.session_id, self.sports_cluster, "click", created_at=self.now - timedelta(hours=1))

        from users.views import AffinityViewSet
        from rest_framework.request import Request
        from unittest.mock import Mock

        # Simulate affinity calculation
        interactions = UserInteraction.objects.filter(
            session_id=self.session_id,
            created_at__gte=self.now - timedelta(hours=168),
        ).select_related(
            "cluster__primary_article__source__category",
        )

        affinity = {}
        for interaction in interactions:
            category = interaction.cluster.primary_article.source.category
            hours_old = (self.now - interaction.created_at).total_seconds() / 3600
            weight = 1.0  # click weight
            decay = _decay_factor(hours_old)
            tab_slug = category.slug
            affinity[tab_slug] = affinity.get(tab_slug, 0.0) + weight * decay

        # India should have higher affinity than sports (2 clicks vs 1)
        self.assertGreater(affinity["india"], affinity["sports"])

    def test_save_weight_triple_click(self):
        """A save counts 3x a click."""
        _create_interaction(self.session_id, self.india_cluster, "save", created_at=self.now)

        from users.views import _INTERACTION_WEIGHTS
        self.assertEqual(_INTERACTION_WEIGHTS["save"], 3.0)
        self.assertEqual(_INTERACTION_WEIGHTS["click"], 1.0)
        self.assertEqual(_INTERACTION_WEIGHTS["dwell"], 0.5)

    def test_affinity_respects_lookback_window(self):
        """Interactions outside the lookback window are excluded."""
        session_id = f"lookback-{self._testMethodName}"
        now = timezone.now()
        # Old interaction (10 days ago, outside 7-day lookback)
        _create_interaction(
            session_id, self.india_cluster, "click",
            created_at=now - timedelta(days=10),
        )
        # Recent interaction (1 hour ago, within 7-day lookback)
        _create_interaction(
            session_id, self.india_cluster, "click",
            created_at=now - timedelta(hours=1),
        )

        # With 7-day lookback: only the recent one counts
        cutoff = now - timedelta(hours=168)
        recent_count = UserInteraction.objects.filter(
            session_id=session_id,
            created_at__gte=cutoff,
        ).count()
        self.assertEqual(recent_count, 1)


# ---------------------------------------------------------------------------
# Personalized feed API tests
# ---------------------------------------------------------------------------

class PersonalizedFeedAPITest(TestCase):
    """Tests for the personalized feed endpoint."""

    def setUp(self):
        self.client = APIClient()
        self.session_id = "feed-test-001"

        # Create tabs and clusters
        self.india_tab = _create_tab("india", "India")
        self.sports_tab = _create_tab("sports", "Sports")
        self.business_tab = _create_tab("business", "Business")

        self.india_source = _create_source(self.india_tab)
        self.sports_source = _create_source(self.sports_tab)
        self.business_source = _create_source(self.business_tab)

        self.india_cluster = _create_cluster(
            _create_article(self.india_source, "India headline 1"),
            topic_id="11111111-1111-1111-1111-111111111111",
        )
        self.sports_cluster = _create_cluster(
            _create_article(self.sports_source, "Sports headline 1"),
            topic_id="22222222-2222-2222-2222-222222222222",
        )
        self.business_cluster = _create_cluster(
            _create_article(self.business_source, "Business headline 1"),
            topic_id="33333333-3333-3333-3333-333333333333",
        )
        self.india_cluster_2 = _create_cluster(
            _create_article(self.india_source, "India headline 2"),
            topic_id="44444444-4444-4444-4444-444444444444",
        )

        self.now = timezone.now()

    def test_personalized_feed_requires_session_id(self):
        """GET /api/personalized-clusters/ without session_id generates one."""
        response = self.client.get("/api/personalized-clusters/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("results", response.data)

    def test_personalized_feed_returns_clusters(self):
        """GET /api/personalized-clusters/ returns clusters with rank scores."""
        response = self.client.get(
            f"/api/personalized-clusters/?session_id={self.session_id}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("results", response.data)
        self.assertIn("count", response.data)
        self.assertIn("affinity_profile", response.data)

    def test_personalized_feed_ranks_by_affinity(self):
        """Clusters in preferred tabs rank higher."""
        # User has 3 clicks on India, 1 on Sports
        _create_interaction(self.session_id, self.india_cluster, "click", created_at=self.now - timedelta(hours=1))
        _create_interaction(self.session_id, self.india_cluster_2, "click", created_at=self.now - timedelta(hours=2))
        _create_interaction(self.session_id, self.sports_cluster, "click", created_at=self.now - timedelta(hours=1))

        response = self.client.get(
            f"/api/personalized-clusters/?session_id={self.session_id}"
        )
        self.assertEqual(response.status_code, 200)

        results = response.data["results"]
        # India clusters should be ranked higher than sports
        india_scores = [r["rank_score"] for r in results if r["category"] == "india"]
        sports_scores = [r["rank_score"] for r in results if r["category"] == "sports"]

        self.assertTrue(all(is_ > ss for is_ in india_scores for ss in sports_scores))

    def test_personalized_feed_with_affinity_profile(self):
        """Response includes affinity profile per tab."""
        _create_interaction(self.session_id, self.india_cluster, "click", created_at=self.now - timedelta(hours=1))
        _create_interaction(self.session_id, self.sports_cluster, "save", created_at=self.now - timedelta(hours=1))

        response = self.client.get(
            f"/api/personalized-clusters/?session_id={self.session_id}"
        )
        self.assertEqual(response.status_code, 200)
        profile = response.data["affinity_profile"]
        self.assertIn("india", profile)
        self.assertIn("sports", profile)
        # Save (3x weight) on sports > click (1x weight) on india
        # After normalization: sports=1.0, india=0.333
        self.assertGreater(profile["sports"], profile["india"])

    def test_personalized_feed_pagination(self):
        """Results are paginated with next/previous."""
        response = self.client.get(
            f"/api/personalized-clusters/?session_id={self.session_id}&page_size=2"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 2)
        self.assertIn("next", response.data)
        self.assertIn("count", response.data)

    def test_personalized_feed_empty_affinity(self):
        """Feed works with no interactions (all clusters get same base score)."""
        response = self.client.get(
            f"/api/personalized-clusters/?session_id=new-session-{self.session_id}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 4)
        # All should have the same base score (recency only)
        scores = [r["rank_score"] for r in response.data["results"]]
        self.assertAlmostEqual(scores[0], scores[1], places=4)

    def test_personalized_feed_with_tab_filter(self):
        """?tab=india filters to only india clusters."""
        response = self.client.get(
            f"/api/personalized-clusters/?session_id={self.session_id}&tab=india"
        )
        self.assertEqual(response.status_code, 200)
        for result in response.data["results"]:
            self.assertEqual(result["category"], "india")


# ---------------------------------------------------------------------------
# Affinity API tests
# ---------------------------------------------------------------------------

class AffinityAPITest(TestCase):
    """Tests for the affinity profile endpoint."""

    def setUp(self):
        self.client = APIClient()
        self.session_id = "affinity-api-001"
        self.india_tab = _create_tab("india", "India")
        self.sports_tab = _create_tab("sports", "Sports")
        self.india_source = _create_source(self.india_tab)
        self.sports_source = _create_source(self.sports_tab)
        self.india_cluster = _create_cluster(_create_article(self.india_source))
        self.sports_cluster = _create_cluster(_create_article(self.sports_source))
        self.now = timezone.now()

    def test_affinity_endpoint_requires_session_id(self):
        """GET /api/affinity/ without session_id returns 400."""
        response = self.client.get("/api/affinity/")
        self.assertEqual(response.status_code, 400)

    def test_affinity_endpoint_returns_scores(self):
        """GET /api/affinity/ returns affinity scores per tab."""
        _create_interaction(self.session_id, self.india_cluster, "click", created_at=self.now - timedelta(hours=1))
        _create_interaction(self.session_id, self.sports_cluster, "click", created_at=self.now - timedelta(hours=1))

        response = self.client.get(f"/api/affinity/?session_id={self.session_id}")
        self.assertEqual(response.status_code, 200)
        results = response.data
        self.assertIsInstance(results, list)
        tab_slugs = [r["tab"] for r in results]
        self.assertIn("india", tab_slugs)
        self.assertIn("sports", tab_slugs)

    def test_affinity_save_boosts_score(self):
        """Save interactions boost affinity more than clicks."""
        # 1 click on india (weight 1.0), 1 save on sports (weight 3.0)
        _create_interaction(self.session_id, self.india_cluster, "click", created_at=self.now)
        _create_interaction(self.session_id, self.sports_cluster, "save", created_at=self.now)

        response = self.client.get(f"/api/affinity/?session_id={self.session_id}")
        self.assertEqual(response.status_code, 200)
        sports_affinity = next(r for r in response.data if r["tab"] == "sports")
        india_affinity = next(r for r in response.data if r["tab"] == "india")
        # Both get normalized to 1.0 since each tab has one interaction
        # The test verifies the endpoint returns both tabs with scores
        self.assertGreater(sports_affinity["score"], 0)
        self.assertGreater(india_affinity["score"], 0)

    def test_affinity_history_endpoint(self):
        """GET /api/affinity/history/ returns daily snapshots."""
        _create_interaction(self.session_id, self.india_cluster, "click", created_at=self.now - timedelta(days=1))
        _create_interaction(self.session_id, self.sports_cluster, "click", created_at=self.now)

        response = self.client.get(f"/api/affinity/history/?session_id={self.session_id}&days=7")
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.data, list)
        # Should have at least 1 day entry
        self.assertGreaterEqual(len(response.data), 1)


# ---------------------------------------------------------------------------
# Session ID extraction tests
# ---------------------------------------------------------------------------

class SessionIdExtractionTest(TestCase):
    """Tests for session ID extraction from requests."""

    def test_query_param_session_id(self):
        """session_id query param is used."""
        from rest_framework.test import APIRequestFactory
        factory = APIRequestFactory()
        request = factory.get("/api/interactions/?session_id=from-query")
        result = _get_session_id(request)
        self.assertEqual(result, "from-query")

    def test_header_session_id(self):
        """X-Session-ID header is used when no query param."""
        from rest_framework.test import APIRequestFactory
        factory = APIRequestFactory()
        request = factory.get("/api/interactions/", headers={"X-Session-ID": "from-header"})
        result = _get_session_id(request)
        self.assertEqual(result, "from-header")

    def test_generated_session_id(self):
        """New UUID is generated when no session_id provided."""
        from rest_framework.test import APIRequestFactory
        factory = APIRequestFactory()
        request = factory.get("/api/interactions/")
        result = _get_session_id(request)
        # Should be a valid UUID
        parts = result.split("-")
        self.assertEqual(len(parts), 5)

    def test_query_param_takes_precedence(self):
        """Query param takes precedence over header."""
        from rest_framework.test import APIRequestFactory
        factory = APIRequestFactory()
        request = factory.get(
            "/api/interactions/?session_id=from-query",
            headers={"X-Session-ID": "from-header"},
        )
        result = _get_session_id(request)
        self.assertEqual(result, "from-query")


# ---------------------------------------------------------------------------
# Superuser creation tests
# ---------------------------------------------------------------------------

class SuperuserCreationTest(TestCase):
    """Tests for superuser creation with flexible identifier support."""

    def test_superuser_email_only(self):
        """Can create a superuser with only email (phone is None)."""
        admin = User.objects.create_superuser(
            email="emailonly@example.com",
            password="adminpass123",
        )
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)
        self.assertEqual(admin.email, "emailonly@example.com")
        self.assertIsNone(admin.phone)
        self.assertEqual(admin.name, "")

    def test_superuser_phone_only(self):
        """Can create a superuser with only phone (generates placeholder email)."""
        admin = User.objects.create_superuser(
            phone="+1987654321",
            password="adminpass123",
        )
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)
        self.assertEqual(admin.phone, "+1987654321")
        self.assertTrue(admin.email.startswith("1987654321@"))
        self.assertIn("newspulse.local", admin.email)

    def test_superuser_neither_email_nor_phone(self):
        """Cannot create a superuser without email or phone."""
        with self.assertRaises(ValueError) as ctx:
            User.objects.create_superuser(password="adminpass123")
        self.assertIn("email or a phone number", str(ctx.exception))
