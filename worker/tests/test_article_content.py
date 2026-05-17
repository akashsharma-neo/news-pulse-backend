"""Tests for article body extraction and summarization helpers."""

from unittest.mock import MagicMock

from django.test import SimpleTestCase
from bs4 import BeautifulSoup

from worker.article_content import (
    MAX_SUMMARY_SOURCE_CHARS,
    build_summarize_prompt,
    enrich_article_content,
    extract_listing_content,
    extract_rss_entry_content,
    fallback_summary_from_article,
    gather_articles_for_summary,
    html_to_plain_text,
    is_summary_too_short,
    word_count,
)


class ArticleContentTests(SimpleTestCase):
    def test_html_to_plain_text_strips_tags(self):
        html = "<p>First paragraph with enough words here.</p><p>Second paragraph also long enough.</p>"
        text = html_to_plain_text(html)
        self.assertIn("First paragraph", text)
        self.assertNotIn("<p>", text)

    def test_extract_listing_content_joins_paragraphs(self):
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

    def test_enrich_fetches_when_listing_thin(self):
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

    def test_extract_rss_entry_prefers_content_encoded(self):
        entry = MagicMock()
        entry.content = [{"value": "<p>RSS full body with enough words to be useful for summarization pipelines.</p>"}]
        entry.get = MagicMock(return_value="")
        text = extract_rss_entry_content(entry)
        self.assertIn("RSS full body", text)

    def test_build_summarize_prompt_requires_word_band(self):
        prompt = build_summarize_prompt(
            title="Test headline",
            source_name="BBC",
            url="https://example.com",
            source_material="Body text here.",
            source_names=["BBC", "CNN"],
        )
        self.assertIn("60 and 80 words", prompt)
        self.assertIn("BBC, CNN", prompt)

    def test_is_summary_too_short(self):
        self.assertTrue(is_summary_too_short("Just a tiny line."))
        self.assertFalse(
            is_summary_too_short(
                " ".join(["word"] * 45)
            )
        )

    def test_fallback_summary_truncates_long_body(self):
        article = MagicMock()
        article.summary = ""
        article.title = "Headline"
        article.full_text = " ".join(["word"] * 100)
        summary = fallback_summary_from_article(article)
        self.assertEqual(word_count(summary), 60)
        self.assertTrue(summary.endswith("..."))

    def test_gather_articles_skips_related_for_single_source(self):
        primary = MagicMock()
        primary.title = "Story"
        primary.full_text = "Body " * 50
        primary.source.name = "BBC"
        related = [MagicMock()]
        material = gather_articles_for_summary(primary, related, source_names=["BBC"])
        self.assertNotIn("Related", material)
        self.assertLessEqual(len(material), MAX_SUMMARY_SOURCE_CHARS)

    def test_gather_articles_includes_one_related_for_multi_source(self):
        primary = MagicMock()
        primary.title = "Story"
        primary.full_text = "Body"
        primary.source.name = "BBC"
        related = MagicMock()
        related.title = "Same story"
        related.full_text = "Other angle"
        related.source.name = "CNN"
        material = gather_articles_for_summary(
            primary, [related], source_names=["BBC", "CNN"]
        )
        self.assertIn("Related 1", material)
        self.assertIn("CNN", material)
