"""CyberPulse daily post generator.

What this script does, and why it looks the way it does:

1. Pull the newest headlines from several RSS feeds.
2. Skip anything CyberPulse has already covered (the old version happily
   re-reported the same "AI phishing" story every day, which is how the
   archive ended up with eight near-identical posts).
3. Ask the model for a *structured* article built from the actual source
   material — with a standfirst, sub-headings and a "why it matters" list —
   instead of free-associating a topic.
4. Write the post with a ``<!--cp:category:-->`` marker so the site builder
   keeps the section the generator chose.
5. Hand over to ``tools/build.py``, which re-renders the whole site: home
   page, section pages, sitemap.xml, feed.xml and the search index.

Runs in GitHub Actions (see .github/workflows/main.yml) at 02:30 UTC daily.
"""

from __future__ import annotations

import datetime
import html
import json
import os
import re
import sys
from pathlib import Path

import feedparser
import requests

ROOT = Path(__file__).resolve().parent.parent.parent  # repo root
sys.path.insert(0, str(ROOT / "tools"))

try:  # the modern SDK; google-generativeai is deprecated
    from google import genai
    from google.genai import types
except ImportError:  # local development without the SDK installed
    genai = None  # type: ignore[assignment]
    types = None  # type: ignore[assignment]

import build as site_build  # the static-site builder  # noqa: E402
import templates as T  # noqa: E402

# --- Configuration ---------------------------------------------------------
API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

RSS_FEEDS = [
    "https://techcrunch.com/feed/",
    "https://www.wired.com/feed/category/technology/latest/rss",
    "https://feeds.arstechnica.com/arstechnica/technology-lab",
    "https://www.bleepingcomputer.com/feed/",
    "https://therecord.media/feed",
]

BLOG_POSTS_DIR = ROOT / "blog"
INDEX_PATH = ROOT / "blog-index.json"
REQUEST_TIMEOUT = 20

POST_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {
            "type": "string",
            "enum": ["AI", "Cybersecurity", "Policy", "Science", "Startups", "Gadgets"],
        },
        "title": {"type": "string", "description": "Headline, max 70 characters, no clickbait."},
        "standfirst": {
            "type": "string",
            "description": "A 1-2 sentence summary of the whole post, 120-160 characters. "
                           "This becomes the meta description, so it must stand alone.",
        },
        "body_html": {
            "type": "string",
            "description": "Pure HTML. 2-4 sections each led by an <h2>, plus paragraphs. "
                           "End with an <h2>Why it matters</h2> followed by a <ul> of 3 bullets.",
        },
        "takeaway": {"type": "string", "description": "One punchy closing sentence."},
    },
    "required": ["category", "title", "standfirst", "body_html", "takeaway"],
}


# --------------------------------------------------------------------------
# 1. Candidate articles
# --------------------------------------------------------------------------
def fetch_candidates(limit_per_feed: int = 6) -> list[dict]:
    """Newest-first list of candidate source articles across all feeds."""
    candidates: list[dict] = []
    seen_links: set[str] = set()
    for feed_url in RSS_FEEDS:
        try:
            response = requests.get(feed_url, timeout=REQUEST_TIMEOUT,
                                    headers={"User-Agent": "CyberPulseBot/1.0 (+feed reader)"})
            feed = feedparser.parse(response.content)
        except Exception as exc:  # a dead feed must not kill the run
            print(f"  ! feed {feed_url} failed: {exc}")
            continue
        for entry in feed.entries[:limit_per_feed]:
            link = entry.get("link", "")
            if not link or link in seen_links:
                continue
            seen_links.add(link)
            pub = entry.get("published_parsed") or entry.get("updated_parsed")
            candidates.append({
                "title": re.sub(r"\s+", " ", entry.get("title", "")).strip(),
                "summary": re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", entry.get("summary", ""))).strip()[:1800],
                "link": link,
                "published": datetime.datetime(*pub[:6], tzinfo=datetime.timezone.utc) if pub else None,
            })
    candidates.sort(key=lambda c: c["published"] or datetime.datetime.min.replace(tzinfo=datetime.timezone.utc),
                    reverse=True)
    print(f"Fetched {len(candidates)} candidate articles")
    return candidates


def already_covered(candidate: dict, existing_titles: list[str]) -> bool:
    """Rough title-overlap guard so we never re-file the same story."""
    import difflib

    words = set(re.sub(r"[^a-z0-9 ]", "", candidate["title"].lower()).split())
    words -= {"the", "a", "an", "of", "to", "in", "on", "for", "and", "with", "new", "how", "why"}
    if not words:
        return False
    for title in existing_titles:
        other = set(re.sub(r"[^a-z0-9 ]", "", title.lower()).split())
        overlap = len(words & other) / max(1, min(len(words), len(other)))
        ratio = difflib.SequenceMatcher(None, candidate["title"].lower(), title.lower()).ratio()
        if overlap >= 0.6 or ratio >= 0.8:
            return True
    return False


def pick_article(candidates: list[dict]) -> dict | None:
    if not INDEX_PATH.exists():
        return candidates[0] if candidates else None
    try:
        existing = [e["title"] for e in json.loads(INDEX_PATH.read_text(encoding="utf-8"))]
    except json.JSONDecodeError:
        existing = []
    for candidate in candidates:
        if not already_covered(candidate, existing):
            print(f"Selected: {candidate['title']}")
            return candidate
    print("  ! every candidate looks like an existing story; skipping today")
    return None


# --------------------------------------------------------------------------
# 2. Generation
# --------------------------------------------------------------------------
PROMPT = """You are the staff writer for CyberPulse, a tech-security newsletter with a
sharp, plainspoken house style. You are rewriting the source article below in your own
words — never copy sentences from it.

SOURCE TITLE: {title}
SOURCE URL: {link}
SOURCE TEXT:
{summary}

Write an original briefing of 450-650 words. Rules:
- Title: specific and factual; name the actor, tool or rule if you can.
- Open with the standfirst: what happened and why a busy reader should care.
- body_html must be pure HTML (no markdown fences) with 2-4 sections, each led by an
  <h2>. Use <p> paragraphs. Quote at most one short phrase from the source.
- Do NOT include an <h1> (the site renders the headline) and do NOT include the source
  link (the site renders it from metadata).
- Finish body_html with <h2>Why it matters</h2> and a <ul> of exactly 3 <li> bullets.
- Be concrete: numbers, dates, named organisations. No filler, no "in today's digital
  landscape", no rhetorical questions.
- category must be the single best section for this story.
"""


def generate_post(client: genai.Client, article: dict) -> dict | None:
    prompt = PROMPT.format(
        title=article["title"],
        link=article["link"],
        summary=article["summary"] or article["title"],
    )
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.8,
                response_mime_type="application/json",
                response_schema=POST_SCHEMA,
            ),
        )
        data = json.loads(response.text)
    except Exception as exc:
        print(f"  ! generation failed: {exc}")
        return None

    # Defensive cleaning — models occasionally still wrap output in fences.
    body = data.get("body_html", "")
    body = re.sub(r"^```(?:html)?\s*", "", body.strip())
    body = re.sub(r"\s*```$", "", body.strip())
    body = re.sub(r"<h1[^>]*>.*?</h1>", "", body, flags=re.S | re.I).strip()
    data["body_html"] = body
    return data if body else None


# --------------------------------------------------------------------------
# 3. Writing files
# --------------------------------------------------------------------------
def slug_for(title: str, when: datetime.date) -> str:
    slug = title.lower().strip()
    slug = re.sub(r"[’']", "", slug)
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
    slug = re.sub(r"-(?:a|an|the|of|in|on|for|to|and|with)$", "", slug)  # drop trailing stop-words
    return f"{when:%Y-%m-%d}-{slug[:64].strip('-')}"


def render_post_html(data: dict, article: dict, when: datetime.date) -> tuple[str, dict]:
    """Assemble the article body, then return (html_fragment, post_record)."""
    title = html.escape(data["title"]).strip()
    standfirst = html.escape(data["standfirst"]).strip()
    body = data["body_html"]
    takeaway = html.escape(data["takeaway"]).strip()

    fragment = (
        f'<h1>{title}</h1>\n<p><em>{standfirst}</em></p>\n{body}\n'
        f"<p><strong>The takeaway:</strong> {takeaway}</p>"
    )

    record = {
        "title": data["title"],
        "summary": data["standfirst"],
        "url": "",  # filled in by the caller once the filename is known
        "category": data.get("category", "AI"),
        "date": when.isoformat(),
        "source": article["link"],
    }
    return fragment, record


def write_post(fragment: str, record: dict) -> Path:
    when = datetime.date.today()
    BLOG_POSTS_DIR.mkdir(exist_ok=True)
    filename = slug_for(record["title"], when) + ".html"
    path = BLOG_POSTS_DIR / filename
    counter = 2
    while path.exists():
        filename = f"{slug_for(record['title'], when)}-{counter}.html"
        path = BLOG_POSTS_DIR / filename
        counter += 1

    record["url"] = f"blog/{filename}"

    source_html = (
        f'<aside class="source-note"><b>Source:</b> '
        f'<a href="{html.escape(record["source"])}" rel="noopener noreferrer nofollow" '
        f'target="_blank">{html.escape(record["source"])}</a> '
        f"— reported and rewritten by CyberPulse.</aside>"
    )

    page = T.head(
        title=record["title"],
        description=record["summary"],
        path=record["url"],
        prefix="../",
        og_type="article",
        published=f"{when.isoformat()}T09:00:00+00:00",
        section=record["category"],
        marker=f'<!--cp:category:{html.escape(record["category"])}-->',
    )
    page += T.header(record["url"], prefix="../", root="../")
    page += f"""
<div class="progress-bar" id="progress-bar" aria-hidden="true"></div>
<main id="main" class="article-shell">
    <article>
        <header class="article-head">
            <p class="eyebrow"><a class="category-tag"
               href="../category-{record['category'].lower().replace(' ', '-')}.html">
               {html.escape(record['category'])}</a></p>
            <h1>{html.escape(record['title'])}</h1>
            <p class="standfirst">{html.escape(record['summary'])}</p>
            <div class="post-meta">
                <time datetime="{when.isoformat()}">{when:%b %d, %Y}</time>
                <span class="dot" aria-hidden="true">•</span>
                <span>By {T.SITE_NAME}</span>
            </div>
        </header>
        <div class="post-content">{re.sub(r'<h1[^>]*>.*?</h1>', '', fragment, flags=re.S | re.I)}</div>
        {source_html}
        <div class="article-extras">
            <div class="share-row">
                <span class="label">Share</span>
                <button class="share-btn" type="button"
                        data-copy="{html.escape(T.abs_url(record['url']))}">Copy link</button>
            </div>
        </div>
    </article>
</main>
"""
    page += T.footer(root="../", year=when.year)
    path.write_text(page, encoding="utf-8")
    print(f"Created {path}")
    return path


# --------------------------------------------------------------------------
def main() -> int:
    if not API_KEY:
        print("Error: GEMINI_API_KEY not found. Skipping post generation.")
        return 0

    candidates = fetch_candidates()
    article = pick_article(candidates)
    if not article:
        print("No fresh story to cover today. Rebuilding the site anyway.")
        return site_build.build()

    if genai is None:
        print("  ! google-genai SDK not installed")
        return None
    client = genai.Client(api_key=API_KEY)
    data = generate_post(client, article)
    if not data:
        print("Generation failed; no post today.")
        return site_build.build()

    fragment, record = render_post_html(data, article, datetime.date.today())
    write_post(fragment, record)

    # Re-render the entire site so the new post lands in the index, the section
    # pages, sitemap.xml and feed.xml in the same commit.
    return site_build.build()


if __name__ == "__main__":
    sys.exit(main())
