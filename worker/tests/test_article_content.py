"""Tests for article body extraction and summarization helpers."""

from unittest.mock import MagicMock

from django.test import SimpleTestCase
from bs4 import BeautifulSoup

from worker.article_content import (
    MAX_SUMMARY_SOURCE_CHARS,
    TARGET_SUMMARY_WORDS_MAX,
    TARGET_SUMMARY_WORDS_MIN,
    TARGET_SUMMARY_FALLBACK_WORDS,
    build_summarize_prompt,
    clean_article_text,
    enrich_article_content,
    extract_listing_content,
    extract_rss_entry_content,
    fallback_summary_from_article,
    gather_articles_for_summary,
    html_to_plain_text,
    is_summary_too_short,
    is_usable_article_body,
    truncate_at_sentence_boundary,
    word_count,
)


class CleanArticleTextTests(SimpleTestCase):
    def test_strips_html_and_tags(self):
        raw = "<p>Prime Minister announced reforms today in a major policy speech.</p>"
        text = clean_article_text(raw)
        self.assertNotIn("<p>", text)
        self.assertIn("Prime Minister", text)

    def test_removes_login_boilerplate(self):
        raw = (
            "Subscribe to continue reading this story on The Hindu. "
            "The cabinet approved the infrastructure bill after a lengthy debate in parliament."
        )
        text = clean_article_text(raw)
        self.assertNotIn("Subscribe", text)
        self.assertIn("infrastructure bill", text)

    def test_is_usable_rejects_subscribe_only(self):
        self.assertFalse(is_usable_article_body("Subscribe to continue reading this story."))

    def test_is_usable_accepts_news_body(self):
        body = " ".join(["Officials confirmed the policy details today."] * 8)
        self.assertTrue(is_usable_article_body(body))


class TruncateAtSentenceBoundaryTests(SimpleTestCase):
    def test_truncates_with_ellipsis_when_no_sentence_end(self):
        text = " ".join(["word"] * 150)
        result = truncate_at_sentence_boundary(text, 120)
        self.assertLessEqual(word_count(result), 121)
        self.assertTrue(result.endswith("..."))

    def test_prefers_sentence_boundary(self):
        sentences = " ".join([f"Sentence number {i} has enough words here." for i in range(20)])
        result = truncate_at_sentence_boundary(sentences, 30)
        self.assertTrue(result.endswith(".") or result.endswith("..."))


class HtmlToPlainTextTests(SimpleTestCase):
    def test_strips_html_tags(self):
        html = "<p>First paragraph with enough words here.</p><p>Second paragraph also long enough.</p>"
        text = html_to_plain_text(html)
        self.assertIn("First paragraph", text)
        self.assertNotIn("<p>", text)

    def test_empty_string(self):
        self.assertEqual(html_to_plain_text(""), "")

    def test_no_html_tags(self):
        self.assertEqual(html_to_plain_text("Plain text only"), "Plain text only")

    def test_nested_tags(self):
        html = "<div><p><b>Bold</b> and <i>italic</i></p></div>"
        text = html_to_plain_text(html)
        self.assertIn("Bold", text)
        self.assertIn("italic", text)
        self.assertNotIn("<div>", text)


class ExtractListingContentTests(SimpleTestCase):
    def test_joins_paragraphs(self):
        html = """
        <div class="card">
          <p>Deck line that is too short.</p>
          <p>This is the first real paragraph of the story with enough words to count.</p>
          <p>This is the second paragraph continuing the story with more detail and context.</p>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        container = soup.select_one(".card")
        text = extract_listing_content(container, ["p"])
        self.assertGreater(word_count(text), 15)
        self.assertIn("second paragraph", text)

    def test_empty_container(self):
        from bs4 import BeautifulSoup
        container = BeautifulSoup("", "html.parser")
        text = extract_listing_content(container, ["p"])
        self.assertEqual(text, "")

    def test_falls_back_to_container_text_when_no_matching_selectors(self):
        from bs4 import BeautifulSoup
        container = BeautifulSoup('<div class="card"><span>No paragraphs here</span></div>', "html.parser")
        text = extract_listing_content(container, ["p"])
        self.assertIn("No paragraphs here", text)


class EnrichArticleContentTests(SimpleTestCase):
    def test_fetches_when_listing_thin(self):
        listing = "Short deck only."
        article_html = """
        <article>
          <p>This is a full article body paragraph with substantially more detail about the event and its implications for readers.</p>
          <p>A second paragraph adds further context and quotes from officials involved in the announcement today.</p>
        </article>
        """

        def fetch(_url):
            return article_html

        result = enrich_article_content(
            "https://example.com/story",
            listing,
            {},
            fetch,
        )
        self.assertGreater(word_count(result), word_count(listing))

    def test_returns_listing_when_already_long(self):
        listing = " ".join(["word"] * 80)

        def fetch(_url):
            return "<p>Full body</p>"

        result = enrich_article_content(
            "https://example.com/story", listing, {}, fetch,
        )
        self.assertEqual(result, listing)

    def test_returns_listing_on_fetch_failure(self):
        listing = "Short deck."

        def fetch(_url):
            return ""

        result = enrich_article_content(
            "https://example.com/story", listing, {}, fetch,
        )
        self.assertEqual(result, listing)

    def test_fetch_returns_none_returns_listing(self):
        listing = "Short deck."

        def fetch(_url):
            return None

        result = enrich_article_content(
            "https://example.com/story", listing, {}, fetch,
        )
        self.assertEqual(result, listing)

    def test_prefers_rss_when_page_is_login_wall(self):
        listing = (
            "The cabinet approved the infrastructure bill after a lengthy debate in parliament "
            "with cross-party support for the core funding measures announced today."
        )
        page_html = """
        <article>
          <p>Subscribe to continue reading this story on The Hindu website today.</p>
          <p>Sign in to your account to access premium journalism content.</p>
        </article>
        """

        def fetch(_url):
            return page_html

        result = enrich_article_content(
            "https://thehindu.com/story",
            listing,
            {"prefer_rss_body": True},
            fetch,
        )
        self.assertIn("infrastructure bill", result)
        self.assertNotIn("Subscribe", result)


class ExtractRssEntryContentTests(SimpleTestCase):
    def test_prefers_content_encoded(self):
        entry = MagicMock()
        entry.content = [{"value": "<p>RSS full body with enough words to be useful for summarization pipelines.</p>"}]
        entry.get = MagicMock(return_value="")
        text = extract_rss_entry_content(entry)
        self.assertIn("RSS full body", text)

    def test_falls_back_to_summary(self):
        entry = MagicMock()
        entry.content = []
        entry.get = MagicMock(return_value="<p>Summary content with enough words for the test case here.</p>")
        text = extract_rss_entry_content(entry)
        self.assertIn("Summary content", text)

    def test_returns_empty_when_nothing(self):
        entry = MagicMock()
        entry.content = []
        entry.get = MagicMock(return_value="")
        text = extract_rss_entry_content(entry)
        self.assertEqual(text, "")


class BuildSummarizePromptTests(SimpleTestCase):
    def test_requires_word_band(self):
        prompt = build_summarize_prompt(
            title="Test headline",
            source_name="BBC",
            url="https://example.com",
            source_material="Body text here.",
            source_names=["BBC", "CNN"],
        )
        self.assertIn(f"{TARGET_SUMMARY_WORDS_MIN} and {TARGET_SUMMARY_WORDS_MAX} words", prompt)
        self.assertIn("BBC, CNN", prompt)

    def test_includes_title_and_source(self):
        prompt = build_summarize_prompt(
            title="Election Results",
            source_name="NDTV",
            url="https://ndtv.com/article",
            source_material="Detailed body text with multiple sentences for the summarizer to process into a concise output.",
            source_names=["NDTV"],
        )
        self.assertIn("Election Results", prompt)
        self.assertIn("NDTV", prompt)

    def test_single_source_name(self):
        prompt = build_summarize_prompt(
            title="Title", source_name="BBC", url="https://bbc.com",
            source_material="Body text content here for testing the prompt building functionality.",
            source_names=["BBC"],
        )
        self.assertIn("BBC", prompt)


class IsSummaryTooShortTests(SimpleTestCase):
    def test_very_short_is_true(self):
        self.assertTrue(is_summary_too_short("Just a tiny line."))

    def test_long_enough_is_false(self):
        self.assertFalse(is_summary_too_short(" ".join(["word"] * 90)))

    def test_empty_string_is_true(self):
        self.assertTrue(is_summary_too_short(""))

    def test_exactly_at_threshold(self):
        self.assertFalse(is_summary_too_short(" ".join(["word"] * 85)))


class FallbackSummaryTests(SimpleTestCase):
    def test_truncates_long_body(self):
        article = MagicMock()
        article.summary = ""
        article.title = "Headline"
        article.full_text = " ".join(["word"] * 200)
        summary = fallback_summary_from_article(article)
        self.assertLessEqual(word_count(summary), TARGET_SUMMARY_FALLBACK_WORDS + 1)
        self.assertTrue(summary.endswith("...") or summary.endswith("."))

    def test_returns_existing_summary(self):
        article = MagicMock()
        article.summary = "Existing summary text with enough words to test."
        article.title = "Headline"
        article.full_text = " ".join(["word"] * 100)
        summary = fallback_summary_from_article(article)
        self.assertEqual(summary, "Existing summary text with enough words to test.")

    def test_returns_title_when_no_text(self):
        article = MagicMock()
        article.summary = ""
        article.title = "Just a Title"
        article.full_text = ""
        summary = fallback_summary_from_article(article)
        self.assertEqual(summary, "Just a Title")

    def test_short_body_no_truncation(self):
        article = MagicMock()
        article.summary = ""
        article.title = "Title"
        article.full_text = "Short body."
        summary = fallback_summary_from_article(article)
        self.assertEqual(summary, "Short body.")


class GatherArticlesForSummaryTests(SimpleTestCase):
    def test_skips_related_for_single_source(self):
        primary = MagicMock()
        primary.title = "Story"
        primary.full_text = "Body " * 50
        primary.source.name = "BBC"
        related = [MagicMock()]
        material = gather_articles_for_summary(primary, related, source_names=["BBC"])
        self.assertNotIn("Related", material)
        self.assertLessEqual(len(material), MAX_SUMMARY_SOURCE_CHARS)

    def test_includes_related_for_multi_source(self):
        primary = MagicMock()
        primary.title = "Story"
        primary.full_text = (
            "The cabinet approved the infrastructure bill after debate in parliament today "
            "with support from several regional parties and industry representatives present."
        )
        primary.source.name = "BBC"
        related = MagicMock()
        related.title = "Same story"
        related.full_text = (
            "Officials confirmed the same policy details in a briefing outlining economic "
            "impacts and regional timelines for implementation of the new government rules."
        )
        related.source.name = "CNN"
        material = gather_articles_for_summary(
            primary, [related], source_names=["BBC", "CNN"]
        )
        self.assertIn("Related 1", material)
        self.assertIn("CNN", material)

    def test_returns_primary_only_when_no_related(self):
        primary = MagicMock()
        primary.title = "Story"
        primary.full_text = (
            "The cabinet approved the infrastructure bill after debate in parliament today "
            "with support from several regional parties and industry representatives present."
        )
        primary.source.name = "BBC"
        material = gather_articles_for_summary(primary, [], source_names=["BBC"])
        self.assertIn("infrastructure bill", material)
        self.assertNotIn("Related", material)

    def test_truncates_long_text(self):
        primary = MagicMock()
        primary.title = "Story"
        primary.full_text = "word " * MAX_SUMMARY_SOURCE_CHARS
        primary.source.name = "BBC"
        material = gather_articles_for_summary(primary, [], source_names=["BBC"])
        self.assertLessEqual(len(material), MAX_SUMMARY_SOURCE_CHARS)


class WordCountTests(SimpleTestCase):
    def test_counts_words(self):
        self.assertEqual(word_count("one two three"), 3)

    def test_empty(self):
        self.assertEqual(word_count(""), 0)

    def test_whitespace(self):
        self.assertEqual(word_count("   "), 0)

    def test_none_returns_zero(self):
        self.assertEqual(word_count(None), 0)
