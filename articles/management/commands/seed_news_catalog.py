"""Seed ``Tab`` and ``Source`` rows for local / Docker dev.

Creates navigation tabs (including ``just-for-you`` with no sources) and up to
10 news sources per category. Re-running is safe: tabs are upserted by slug;
sources are upserted by ``(name, category)`` without duplicating rows.

Run inside Docker::

    docker compose exec django python manage.py seed_news_catalog

Or locally (with DB env set)::

    python manage.py seed_news_catalog
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from articles.models import Source, Tab

# (display_name, slug, order) — order matches frontend TabNavigation fallback.
TABS: list[tuple[str, str, int]] = [
    ("India", "india", 1),
    ("Just For You", "just-for-you", 2),
    ("Sports", "sports", 3),
    ("Business", "business", 4),
    ("Global", "global", 5),
]

# Tab slug -> up to 10 sources: (name, url, source_type)
# Names aligned with worker.tasks.SCRAPER_CONFIGS where applicable so in-code
# URL/source_type overrides still apply for those entries.
SOURCES_BY_TAB_SLUG: dict[str, list[tuple[str, str, str]]] = {
    "india": [
        ("NDTV", "https://feeds.ndtv.com/ndtv/index.xml", "rss"),
        (
            "Times of India",
            "https://timesofindia.indiatimes.com/india",
            "web",
        ),
        ("Indian Express", "https://indianexpress.com/feed/", "rss"),
        (
            "The Hindu",
            "https://www.thehindu.com/news/national/feeder/default.rss",
            "rss",
        ),
        ("India Today", "https://www.indiatoday.in/rss/home", "rss"),
        (
            "Hindustan Times",
            "https://www.hindustantimes.com/feeds/rss/india-news/rssfeed.xml",
            "rss",
        ),
        ("Deccan Herald", "https://www.deccanherald.com/rss.xml", "rss"),
        ("Scroll.in", "https://scroll.in/feed", "rss"),
        ("Livemint", "https://www.livemint.com/rss/news", "rss"),
        ("The Wire", "https://thewire.in/rss", "rss"),
    ],
    "sports": [
        (
            "ESPNcricinfo",
            "https://www.espncricinfo.com/series",
            "web",
        ),
        ("Sportskeeda", "https://www.sportskeeda.com/feed/", "rss"),
        ("BBC Sport", "http://feeds.bbci.co.uk/sport/rss.xml", "rss"),
        ("The Guardian Sport", "https://www.theguardian.com/sport/rss", "rss"),
        ("ESPN", "https://www.espn.com/espn/rss/news", "rss"),
        (
            "NDTV Sports",
            "https://feeds.feedburner.com/ndtvnews-sports",
            "rss",
        ),
        (
            "Sportstar",
            "https://sportstar.thehindu.com/feeder/default.rss",
            "rss",
        ),
        ("Reuters Sports", "https://feeds.reuters.com/reuters/sportsNews", "rss"),
        ("Cricbuzz", "https://www.cricbuzz.com/rss/feed", "rss"),
        ("The Independent Sport", "https://www.independent.co.uk/sport/rss", "rss"),
    ],
    "business": [
        (
            "Moneycontrol",
            "https://www.moneycontrol.com/news/india/",
            "web",
        ),
        (
            "Economic Times",
            "https://economictimes.indiatimes.com/newsfeed.rss",
            "rss",
        ),
        ("Livemint Markets", "https://www.livemint.com/rss/markets", "rss"),
        (
            "Business Standard",
            "https://www.business-standard.com/rss/latest-news",
            "rss",
        ),
        (
            "Moneycontrol RSS",
            "https://www.moneycontrol.com/rss/latestnews.xml",
            "rss",
        ),
        ("Reuters Business", "https://feeds.reuters.com/reuters/businessNews", "rss"),
        ("CNBC", "https://www.cnbc.com/id/100003114/device/rss/rss.html", "rss"),
        ("Financial Express", "https://www.financialexpress.com/feed/", "rss"),
        ("Mint Companies", "https://www.livemint.com/rss/companies", "rss"),
        ("Forbes", "https://www.forbes.com/real-time/feed2/", "rss"),
    ],
    "global": [
        ("BBC", "http://feeds.bbci.co.uk/news/world/rss.xml", "rss"),
        ("CNN", "http://rss.cnn.com/rss/cnn_world.rss", "rss"),
        ("Reuters", "https://feeds.reuters.com/reuters/topNews", "rss"),
        ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml", "rss"),
        ("The Guardian World", "https://www.theguardian.com/world/rss", "rss"),
        ("NPR World", "https://feeds.npr.org/1001/rss.xml", "rss"),
        ("DW", "https://rss.dw.com/rdf/rss-en-world", "rss"),
        ("France 24", "https://www.france24.com/en/rss", "rss"),
        ("Sky News World", "https://feeds.skynews.com/feeds/rss/world.xml", "rss"),
        ("CBS News", "https://www.cbsnews.com/latest/rss/world", "rss"),
    ],
}


def _upsert_source(tab: Tab, name: str, url: str, source_type: str) -> str:
    row = Source.objects.filter(name=name, category=tab).first()
    if row:
        row.url = url
        row.source_type = source_type
        row.active = True
        row.save()
        return "updated"
    Source.objects.create(
        name=name,
        url=url,
        category=tab,
        source_type=source_type,
        active=True,
    )
    return "created"


class Command(BaseCommand):
    help = "Seed Tab rows and up to 10 Source rows per category (idempotent)."

    def handle(self, *args, **options):
        for name, slug, order in TABS:
            Tab.objects.update_or_create(
                slug=slug,
                defaults={"name": name, "order": order},
            )
            self.stdout.write(self.style.NOTICE(f"Tab OK: {slug}"))

        tabs_by_slug = {t.slug: t for t in Tab.objects.all()}

        created = 0
        updated = 0
        for slug, rows in SOURCES_BY_TAB_SLUG.items():
            tab = tabs_by_slug.get(slug)
            if not tab:
                self.stdout.write(self.style.ERROR(f"Missing tab slug={slug}, skip sources"))
                continue
            for name, url, source_type in rows[:10]:
                action = _upsert_source(tab, name, url, source_type)
                if action == "created":
                    created += 1
                else:
                    updated += 1
                self.stdout.write(f"  Source {action}: {name} ({slug})")

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Sources created={created}, updated={updated}. "
                "Tab 'just-for-you' has no sources (personalized feed is separate)."
            )
        )
