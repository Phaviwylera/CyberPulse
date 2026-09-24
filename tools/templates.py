"""Shared HTML templates for CyberPulse.

Every page on the site is rendered through these helpers so the header, footer,
SEO head and accessibility affordances stay identical across the home page,
category pages, articles and static pages.
"""

from __future__ import annotations

import html
import json
import os

SITE_NAME = "CyberPulse"
SITE_URL = os.getenv("SITE_URL", "https://cyberpulse24.netlify.app").rstrip("/")
TAGLINE = "The Beat of the Digital World"
SITE_DESCRIPTION = (
    "CyberPulse is a daily dispatch on cybersecurity, AI and technology policy — "
    "short, sharp briefings on the threats, tools and rules shaping the digital world."
)
CONTACT_EMAIL = "contact.cyberpulse@gmail.com"
TWITTER_HANDLE = os.getenv("TWITTER_HANDLE", "")
OG_IMAGE = f"{SITE_URL}/assets/og-default.jpg"

# Gradient + glyph used for the generated "cover art" block on cards.
CATEGORY_ART = {
    "Cybersecurity": ("linear-gradient(135deg,#0a63d4,#06b6a4)", "SEC"),
    "AI": ("linear-gradient(135deg,#7b5cff,#ff4d8d)", "AI"),
    "Policy": ("linear-gradient(135deg,#f59e0b,#ef4444)", "POL"),
    "Gadgets": ("linear-gradient(135deg,#14b8a6,#0ea5e9)", "GDT"),
    "Startups": ("linear-gradient(135deg,#8b5cf6,#22d3ee)", "STP"),
    "Science": ("linear-gradient(135deg,#22c55e,#0ea5e9)", "SCI"),
}
DEFAULT_ART = ("linear-gradient(135deg,#334155,#0a63d4)", "CP")

FONT_LINK = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?family=Roboto+Mono:wght@400;600;700&display=swap" rel="stylesheet">'
)

THEME_SCRIPT = """<script>
(function(){try{var s=localStorage.getItem('cp-theme');if(!s){s=window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';}document.documentElement.setAttribute('data-theme',s);}catch(e){}})();
</script>"""

SEARCH_ICON = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
    'stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/>'
    '<path d="m20 20-3.5-3.5"/></svg>'
)
SUN_ICON = (
    '<svg class="icon-sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/>'
    '<path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2'
    'M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>'
)
MOON_ICON = (
    '<svg class="icon-moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z"/></svg>'
)
MENU_ICON = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
    'stroke-linecap="round" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16"/></svg>'
)
RSS_ICON = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
    'stroke-linecap="round" aria-hidden="true"><path d="M4 11a9 9 0 0 1 9 9M4 4a16 16 0 0 1 16 16"/>'
    '<circle cx="5" cy="19" r="1.6" fill="currentColor" stroke="none"/></svg>'
)

CURRENT_CATEGORIES: list[str] = []

DEFAULT_NAV = [
    ("index.html", "Home"),
    ("category-cybersecurity.html", "Cybersecurity"),
    ("category-ai.html", "AI"),
    ("category-policy.html", "Policy"),
    ("about.html", "About"),
]


def nav_items(categories: list[str] | None = None) -> list[tuple[str, str]]:
    """Home + the sections with real depth + About. Falls back to a sane default."""
    if not categories:
        return DEFAULT_NAV
    items = [("index.html", "Home")]
    for cat in categories[:4]:
        items.append((f"category-{cat.lower().replace(' ', '-')}.html", cat))
    items.append(("about.html", "About"))
    return items


def e(value) -> str:
    """Escape a value for safe interpolation into HTML."""
    return html.escape(str(value if value is not None else ""), quote=True)


def abs_url(path: str) -> str:
    if path.startswith("http://") or path.startswith("https://"):
        return path
    return f"{SITE_URL}/{path.lstrip('/')}"


def category_art(category: str):
    return CATEGORY_ART.get((category or "").strip(), DEFAULT_ART)


def head(
    *,
    title: str,
    description: str,
    path: str,
    prefix: str = "",
    extra: str = "",
    og_type: str = "website",
    published: str = "",
    section: str = "",
    jsonld: dict | None = None,
    noindex: bool = False,
    canonical_path: str | None = None,
    marker: str = "",
) -> str:
    """Render a complete, SEO-ready <head>.

    `canonical_path` overrides the self-referencing canonical URL — used to
    collapse near-duplicate dispatches onto a single canonical article.
    """
    canonical = abs_url(canonical_path or ("./" if path == "index.html" else path))
    if canonical.endswith("/index.html"):
        canonical = canonical[: -len("index.html")]
    full_title = (
        title
        if title == SITE_NAME or title.startswith(SITE_NAME + " ") or title.startswith(SITE_NAME + "—")
        else f"{title} | {SITE_NAME}"
    )
    meta = [
        '<meta charset="UTF-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
        f"<title>{e(full_title)}</title>",
        f'<meta name="description" content="{e(description)}">',
        f'<link rel="canonical" href="{e(canonical)}">',
        '<meta name="theme-color" content="#0a63d4" media="(prefers-color-scheme: light)">',
        '<meta name="theme-color" content="#0c0e12" media="(prefers-color-scheme: dark)">',
        f'<meta property="og:site_name" content="{e(SITE_NAME)}">',
        f'<meta property="og:type" content="{e(og_type)}">',
        f'<meta property="og:title" content="{e(title)}">',
        f'<meta property="og:description" content="{e(description)}">',
        f'<meta property="og:url" content="{e(canonical)}">',
        f'<meta property="og:image" content="{e(OG_IMAGE)}">',
        '<meta property="og:image:width" content="1200">',
        '<meta property="og:image:height" content="630">',
        '<meta name="twitter:card" content="summary_large_image">',
        f'<meta name="twitter:title" content="{e(title)}">',
        f'<meta name="twitter:description" content="{e(description)}">',
        f'<meta name="twitter:image" content="{e(OG_IMAGE)}">',
    ]
    if TWITTER_HANDLE:
        meta.append(f'<meta name="twitter:site" content="@{e(TWITTER_HANDLE)}">')
    if published:
        meta.append(f'<meta property="article:published_time" content="{e(published)}">')
    if section:
        meta.append(f'<meta property="article:section" content="{e(section)}">')
    if noindex:
        meta.append('<meta name="robots" content="noindex,follow">')

    links = [
        '<link rel="stylesheet" href="style.css">',
        '<link rel="icon" href="assets/favicon.svg" type="image/svg+xml">',
        '<link rel="icon" href="assets/icon-192.png" type="image/png" sizes="192x192">',
        '<link rel="icon" href="assets/icon-512.png" type="image/png" sizes="512x512">',
        '<link rel="apple-touch-icon" href="assets/icon-192.png">',
        '<link rel="manifest" href="assets/site.webmanifest">',
        '<link rel="alternate" type="application/rss+xml" title="CyberPulse — Latest dispatches" href="feed.xml">',
    ]
    if prefix == "../":
        links[0] = '<link rel="stylesheet" href="../style.css">'
        links[1] = '<link rel="icon" href="../assets/favicon.svg" type="image/svg+xml">'
        links[2] = '<link rel="icon" href="../assets/icon-192.png" type="image/png" sizes="192x192">'
        links[3] = '<link rel="icon" href="../assets/icon-512.png" type="image/png" sizes="512x512">'
        links[4] = '<link rel="apple-touch-icon" href="../assets/icon-192.png">'
        links[5] = '<link rel="manifest" href="../assets/site.webmanifest">'
        links[6] = (
            '<link rel="alternate" type="application/rss+xml" '
            'title="CyberPulse — Latest dispatches" href="../feed.xml">'
        )

    ld = ""
    if jsonld:
        ld = '<script type="application/ld+json">' + json.dumps(jsonld, ensure_ascii=False) + "</script>"

    return "\n".join(
        ["<!DOCTYPE html>", '<html lang="en" data-theme="light">', "<head>"]
        + ["    " + m for m in meta]
        + ["    " + l for l in links]
        + ["    " + FONT_LINK, "    " + THEME_SCRIPT]
        + (["    " + ld] if ld else [])
        + (["    " + extra] if extra else [])
        + (["    " + marker] if marker else [])
        + ["</head>", "<body>"]
    )


def header(path: str, *, prefix: str = "", root: str = "",
           categories: list[str] | None = None) -> str:
    """Site header. `path` is the current file name (e.g. 'about.html')."""
    if categories is None:
        categories = CURRENT_CATEGORIES or None
    links = []
    for href, label in nav_items(categories):
        current = ' aria-current="page"' if href == path else ""
        links.append(f'<a href="{root}{href}"{current}>{label}</a>')
    return f"""<a class="skip-link" href="#main">Skip to content</a>
<header class="site-header">
    <div class="container header-inner">
        <a class="logo-link" href="{root}index.html"><span class="logo-mark" aria-hidden="true"></span>{SITE_NAME}</a>
        <button class="icon-btn nav-toggle" id="nav-toggle" aria-expanded="false" aria-controls="site-nav" aria-label="Toggle navigation menu">{MENU_ICON}</button>
        <nav class="site-nav" id="site-nav" aria-label="Primary">{''.join(links)}</nav>
        <a class="icon-btn" href="{root}feed.xml" aria-label="Subscribe to the RSS feed" title="RSS feed">{RSS_ICON}</a>
        <button class="icon-btn" id="theme-toggle" aria-label="Switch colour theme">{SUN_ICON}{MOON_ICON}</button>
    </div>
</header>"""


def footer(*, root: str = "", year: int = 2025) -> str:
    return f"""<footer class="site-footer">
    <div class="container">
        <div class="footer-grid">
            <div>
                <h3>{SITE_NAME}</h3>
                <p class="footer-blurb">// {TAGLINE} // — a daily, independent dispatch on
                cybersecurity, artificial intelligence and technology policy.</p>
            </div>
            <div>
                <h3>Sections</h3>
                <ul>
                    <li><a href="{root}category-cybersecurity.html">Cybersecurity</a></li>
                    <li><a href="{root}category-ai.html">AI</a></li>
                    <li><a href="{root}category-policy.html">Policy</a></li>
                    <li><a href="{root}index.html">All dispatches</a></li>
                </ul>
            </div>
            <div>
                <h3>About</h3>
                <ul>
                    <li><a href="{root}about.html">About CyberPulse</a></li>
                    <li><a href="{root}contact.html">Contact</a></li>
                    <li><a href="{root}privacy.html">Privacy Policy</a></li>
                    <li><a href="{root}feed.xml">RSS feed</a></li>
                </ul>
            </div>
        </div>
        <div class="footer-bottom">
            <span>&copy; {year} {SITE_NAME}. All rights reserved.</span>
            <span><a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a></span>
        </div>
    </div>
</footer>
<button class="icon-btn back-to-top" id="back-to-top" aria-label="Back to top">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 19V5M5 12l7-7 7 7"/></svg>
</button>
<script src="{root}blog.js" defer></script>
</body>
</html>"""


def post_card(post: dict, *, heading: str = "h3", root: str = "", show_excerpt: bool = True) -> str:
    """Compact list card used on the home page and category pages."""
    gradient, glyph = category_art(post.get("category"))
    excerpt = f'<p class="excerpt">{e(post.get("summary", ""))}</p>' if show_excerpt else ""
    meta_bits = []
    if post.get("dateLabel"):
        meta_bits.append(f'<time datetime="{e(post.get("date", ""))}">{e(post["dateLabel"])}</time>')
    if post.get("readingTime"):
        meta_bits.append(f'<span>{e(post["readingTime"])} min read</span>')
    meta_inner = '<span class="dot" aria-hidden="true">•</span>'.join(meta_bits)
    cat = post.get("category")
    cat_html = (
        f'<a class="category-tag" href="{root}category-{cat.lower().replace(" ", "-")}.html">{e(cat)}</a>'
        if cat else ""
    )
    return f"""<article class="post-card" data-category="{e(cat)}" data-tags="{e(' '.join(post.get('tags', [])))}" data-title="{e(post.get('title','').lower())}" data-summary="{e(post.get('summary','').lower())}">
    <div class="post-meta">{cat_html}{f'<span class="dot" aria-hidden="true">•</span>' if cat_html and meta_inner else ''}{meta_inner}</div>
    <{heading}><a href="{root}{e(post['url'])}">{e(post['title'])}</a></{heading}>
    {excerpt}
    <a class="read-more" href="{root}{e(post['url'])}" tabindex="-1" aria-hidden="true">Read the dispatch</a>
</article>"""


def featured_card(post: dict, *, root: str = "") -> str:
    gradient, glyph = category_art(post.get("category"))
    cat = post.get("category")
    cat_html = (
        f'<a class="category-tag" href="{root}category-{cat.lower().replace(" ", "-")}.html">{e(cat)}</a>'
        if cat else ""
    )
    return f"""<a class="featured" href="{root}{e(post['url'])}">
    <div>
        <p class="eyebrow">Latest dispatch</p>
        <h2>{e(post['title'])}</h2>
        <p class="excerpt">{e(post.get('summary',''))}</p>
        <div class="post-meta">{cat_html}<span class="dot" aria-hidden="true">•</span><time datetime="{e(post.get('date',''))}">{e(post.get('dateLabel',''))}</time><span class="dot" aria-hidden="true">•</span><span>{e(post.get('readingTime','2'))} min read</span></div>
        <span class="read-more">Read the dispatch</span>
    </div>
    <div class="featured-art" style="background:{gradient}" aria-hidden="true">{e(glyph)}</div>
</a>"""


def toolbar(*, categories: list, counts: dict, total: int, root: str = "") -> str:
    chips = [
        f'<a class="chip is-active" href="{root}index.html" data-filter="all" aria-pressed="true">All<span class="count">{total}</span></a>'
    ]
    for cat in categories:
        slug = cat.lower().replace(" ", "-")
        chips.append(
            f'<a class="chip" href="{root}category-{slug}.html" data-filter="{e(cat)}" aria-pressed="false">'
            f'{e(cat)}<span class="count">{counts.get(cat, 0)}</span></a>'
        )
    return f"""<div class="toolbar">
    <div class="container">
        <div class="toolbar-row">
            <div class="search-wrap">
                <label class="visually-hidden" for="search-input">Search dispatches</label>
                {SEARCH_ICON}
                <input type="search" id="search-input" placeholder="Search 96 dispatches — try “phishing”, “deepfake”, “EU”…" autocomplete="off" spellcheck="false">
            </div>
        </div>
        <div class="chip-row" role="group" aria-label="Filter by section">{''.join(chips)}</div>
        <p class="result-note" id="result-note" role="status" aria-live="polite"></p>
    </div>
</div>"""
