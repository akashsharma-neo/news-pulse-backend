"""Tests for Nex suggested-question generation and parsing."""

from django.test import SimpleTestCase

from articles.nex_prompts import (
    build_nex_prompts_request,
    fallback_nex_prompts,
    parse_nex_prompts_response,
)


class ParseNexPromptsTests(SimpleTestCase):
    def test_parses_json_array(self):
        raw = '["What are the main facts?", "Who is affected?", "What happens next?"]'
        result = parse_nex_prompts_response(raw)
        self.assertEqual(len(result), 3)
        self.assertTrue(result[0].endswith("?"))

    def test_parses_fenced_json(self):
        raw = """```json
["Fact one here?", "Who is involved?", "What is next step?"]
```"""
        result = parse_nex_prompts_response(raw)
        self.assertEqual(len(result), 3)

    def test_rejects_wrong_count(self):
        raw = '["Only one question?"]'
        self.assertIsNone(parse_nex_prompts_response(raw))

    def test_adds_question_mark(self):
        raw = '["Main facts here", "Who is affected", "What happens next"]'
        result = parse_nex_prompts_response(raw)
        self.assertIsNotNone(result)
        for q in result:
            self.assertTrue(q.endswith("?"))


class FallbackNexPromptsTests(SimpleTestCase):
    def test_title_aware_fallback(self):
        prompts = fallback_nex_prompts("PM visits Assam flood region")
        self.assertEqual(len(prompts), 3)
        self.assertIn("Assam", prompts[0])

    def test_empty_title_uses_generic(self):
        prompts = fallback_nex_prompts("")
        self.assertEqual(len(prompts), 3)


class BuildNexPromptsRequestTests(SimpleTestCase):
    def test_includes_story_fields(self):
        text = build_nex_prompts_request(
            title="Test headline",
            summary="Story summary here.",
            category_slug="india",
            source_names=["NDTV", "TOI"],
        )
        self.assertIn("Test headline", text)
        self.assertIn("Story summary", text)
        self.assertIn("india", text)
