#!/usr/bin/env python3
"""CyberPulse static site builder.

Reads the raw article bodies in ``blog/*.html`` and rebuilds every page of the
site from a single set of templates:

* ``blog-index.json``  — deduplicated, dated, with a real per-post summary
* ``blog/*.html``      — full SEO head, reading time, share row, related posts
* ``category-*.html``  — one page per section
* ``index.html``       — server-rendered post list (crawlable without JS)
* ``about/contact/privacy/404.html``
* ``sitemap.xml``, ``feed.xml``, ``robots.txt``

The build is idempotent: dates and other metadata are read back out of the
previously rendered pages so re-running never rewrites history.

Usage:
    python3 tools/build.py            # build everything
    python3 tools/build.py --check    # build into memory, report drift, exit 1
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

sys.path.insert(0, str(Path(__file__).resolve().parent))

import templates as T  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BLOG_DIR = ROOT / "blog"
INDEX_PATH = ROOT / "blog-index.json"
ASSETS_DIR = ROOT / "assets"

STATIC_PAGES = {
    "about.html": {
        "title": "About CyberPulse",
        "description": (
            "CyberPulse is an independent, automation-assisted newsroom publishing a daily "
            "dispatch on cybersecurity, AI and technology policy. Meet the mission and the method."
        ),
    },
    "contact.html": {
        "title": "Contact CyberPulse",
        "description": (
            "Get in touch with the CyberPulse editorial team — tips, corrections, partnerships "
            "and press enquiries at contact.cyberpulse@gmail.com."
        ),
    },
    "privacy.html": {
        "title": "Privacy Policy",
        "description": "How CyberPulse collects, uses and protects visitor data.",
    },
}

# --- Section classifier ----------------------------------------------------
# (regex, weight). A hit in the <title> counts three times as much as a hit in
# the body, so the section reflects what the piece is *about*, not what it
# happens to mention once. Deterministic and free — no API call required.
CATEGORY_RULES: dict[str, list[tuple[str, int]]] = {
    "Cybersecurity": [
        (r"phish", 4), (r"malware", 4), (r"ransomware", 4), (r"cyber\s?-?attack", 4),
        (r"cybercrime", 4), (r"cybersecurity", 3), (r"zero[- ]day", 3), (r"\bCVE-\d", 4),
        (r"threat actor", 3), (r"\bDDoS\b", 3), (r"data breach", 3), (r"\bbreach", 2),
        (r"vulnerabilit", 3), (r"\bhack", 2), (r"exploit", 2), (r"botnet", 3),
        (r"espionage", 2), (r"\bCISA\b|\bNIST\b|\bFBI\b|\bInterpol\b", 3),
        (r"ransom", 3), (r"credential", 2), (r"two-factor|\b2FA\b|MFA", 2),
    ],
    "AI": [
        (r"artificial intelligence", 2), (r"machine learning", 2), (r"deep learning", 3),
        (r"neural network", 3), (r"deepfake", 3), (r"\bLLM\b|large language model", 3),
        (r"chatbot", 3), (r"generative", 2), (r"facial recognition", 2), (r"\bbias\b", 2),
        (r"misinformation|disinformation", 2), (r"drug discovery", 2), (r"\bmodel\b", 1),
        (r"algorithm", 1), (r"\bAI\b", 1), (r"training data", 2), (r"hallucinat", 3),
    ],
    "Policy": [
        (r"\bGDPR\b", 4), (r"AI Act", 4), (r"sovereignty", 3), (r"regulat", 3),
        (r"legislat|\bill\b|\blaw\b", 2), (r"directive", 3), (r"antitrust", 3),
        (r"sanction", 3), (r"\bEU\b|european union|brussels", 2), (r"europe", 2),
        (r"government|minister|parliament|commission", 2), (r"\bpolicy\b", 2),
        (r"geopolit", 2), (r"digital markets act|digital services act", 4),
        (r"tech dependence|digital defiance|iron curtain", 3),
    ],
    "Science": [
        (r"volcan|eruption", 5), (r"earthquake|seismic", 4), (r"telescope", 4),
        (r"\bspace\b|\bNASA\b|\bESA\b|rocket", 3), (r"genome|genetic", 3),
        (r"climate", 3), (r"quantum", 3), (r"research paper|peer-review", 2),
        (r"physic|biolog|chemistry", 2),
    ],
    "Startups": [
        (r"startup|start-up", 4), (r"venture capital|\bVC\b", 3), (r"funding round", 4),
        (r"\bIPO\b", 3), (r"acquisition|acquires", 3), (r"unicorn", 3),
        (r"raised \$|valuation", 3), (r"founder", 2),
    ],
    "Gadgets": [
        (r"smartphone|\biPhone\b|\bAndroid\b", 3), (r"laptop|macbook", 3),
        (r"wearable|smartwatch", 3), (r"\bgadget", 4), (r"hardware", 2),
        (r"\bchip\b|semiconductor|silicon", 2), (r"headphone|\bTV\b|console", 2),
    ],
}
CATEGORY_PRIORITY = ["Cybersecurity", "AI", "Policy", "Science", "Startups", "Gadgets"]

MARKER_RE = re.compile(r"<!--cp:category:([^>]+)-->")

# --- Tag vocabulary: matched against title + body text ---------------------
TAG_RULES = [
    ("phishing", r"phish", 4),
    ("malware", r"malware|ransomware|trojan|botnet", 4),
    ("deepfakes", r"deepfake|synthetic media|face swap", 4),
    ("misinformation", r"misinformation|disinformation|fake news", 4),
    ("AI safety", r"algorithmic bias|\bbias\b|alignment|\bethic|responsible ai", 3),
    ("facial recognition", r"facial recognition|biometric", 4),
    ("threat detection", r"threat detection|anomaly detection|intrusion detection|early warning|forecast(?:ing)? (?:cyber)?attacks|predict(?:ing)? cyberattacks", 4),
    ("data breaches", r"data breach|breach|exfiltrat", 3),
    ("regulation", r"regulat|\bGDPR\b|\bAI Act\b|legislat|compliance|directive", 3),
    ("EU tech", r"europe|european union|\bEU\b|brussels|sovereignty", 3),
    ("healthcare AI", r"drug discovery|pharma|clinical trial|molecul|healthcare", 3),
    ("chatbots", r"chatbot|conversational ai|customer service", 4),
    ("critical infrastructure", r"critical infrastructure|power grid|\benergy\b", 3),
    ("machine learning", r"machine learning|neural network|deep learning|model training", 3),
    ("science", r"volcan|eruption|seismic|climate|genome", 4),
    ("disinformation defence", r"detect(?:ing)? (?:fake news|misinformation|deepfakes)|fact-check", 4),
]

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------
MAIN_RE = re.compile(r'<main[^>]*class="[^"]*post-content[^"]*"[^>]*>(.*?)</main>', re.S)
H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.S)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.S)
TIME_RE = re.compile(r'<time[^>]*datetime="([^"]+)"')
PUBLISHED_RE = re.compile(r'<meta property="article:published_time" content="([^"]+)"')
SECTION_RE = re.compile(r'<meta property="article:section" content="([^"]+)"')
DESC_RE = re.compile(r'<meta name="description" content="([^"]*)"')
TAGS_RE = re.compile(r'<meta name="keywords" content="([^"]*)"')
P_RE = re.compile(r"<p[^>]*>(.*?)</p>", re.S)
STRIP_TAGS_RE = re.compile(r"<[^>]+>")
PLACEHOLDER_HREF = re.compile(
    r'<a\s+href="\[[^"]*\]"\s*>.*?</a>'          # <a href="[INSERT … ]" >[INSERT …]</a>
    r'|\[(?:Insert|INSERT)[^\]]*\]'                # bare [Insert …] text
    r'|\[https?://[^\]]+\]\(https?://[^)]+\)',   # markdown-pasted links
    re.S | re.I,
)
MD_LINK = re.compile(r"\[(https?://[^\]]+)\]\(\1\)")
MD_EM = re.compile(r"(?<![\w*>])\*([^*<>\n]{2,120})\*(?![\w<])")


def strip_tags(fragment: str) -> str:
    text = STRIP_TAGS_RE.sub(" ", fragment)
    text = text.replace("&amp;", "&").replace("&#x27;", "'").replace("&quot;", '"')
    text = text.replace("&rsquo;", "'").replace("&lsquo;", "'")
    text = text.replace("&mdash;", "—").replace("&ndash;", "–").replace("&hellip;", "…")
    text = text.replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", text).strip()


def clean_body(body: str) -> str:
    """Repair damage left behind by the old generator."""
    body = MD_LINK.sub(r"\1", body)                 # [url](url) -> url
    body = PLACEHOLDER_HREF.sub("", body)            # drop "[Insert Link ...]"
    body = MD_EM.sub(r"<em>\1</em>", body)           # *emphasis* -> <em>
    # Remove <p> wrappers that ended up empty after placeholder stripping.
    body = re.sub(
        r"<p[^>]*>\s*(?:<(?:b|strong)>\s*Source:?\s*</(?:b|strong)>)?\s*</p>", "", body, flags=re.S
    )
    # Drop a "Source:" lead-in left orphaned once its dead link is removed.
    body = re.sub(
        r"<p[^>]*>\s*<(?:b|strong)>\s*Source:?\s*</(?:b|strong)>\s*:?\s*</p>", "", body, flags=re.S
    )
    body = re.sub(r"[ \t]{2,}", " ", body)
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body.strip()


DIV_OPEN_RE = re.compile(r"<(/?)div\b", re.I)


def extract_div(html_text: str, cls: str, start: int = 0) -> str | None:
    """Return the inner HTML of the first ``<div class="cls">`` — depth aware."""
    needle = f'<div class="{cls}"'
    at = html_text.find(needle, start)
    if at == -1:
        return None
    i = html_text.index(">", at) + 1
    depth = 1
    for m in DIV_OPEN_RE.finditer(html_text, i):
        if m.group(1) == "/":
            depth -= 1
            if depth == 0:
                return html_text[i:m.start()]
        else:
            depth += 1
    return None


def extract_body(html_text: str) -> str:
    """Pull the article/page copy out of either template generation."""
    # New template (this builder): <main id="main" ...><div class="post-content">
    inner = extract_div(html_text, "post-content")
    if inner is not None:
        return inner
    # Legacy template (the original daily_post_generator.py): <main class="post-content">
    m = MAIN_RE.search(html_text)
    return m.group(1) if m else ""


def extract_title(html_text: str, body: str) -> str:
    """Newest template keeps the H1 in the article header, not in the body."""
    head_block = re.search(r'<header class="article-head">(.*?)</header>', html_text, re.S)
    candidates = []
    if head_block:
        candidates.append(H1_RE.search(head_block.group(1)))
    candidates.append(H1_RE.search(body))
    candidates.append(H1_RE.search(html_text))
    for m in candidates:
        if m:
            return re.sub(r"\s*[-|]\s*CyberPulse\s*$", "", strip_tags(m.group(1))).strip()
    m = TITLE_RE.search(html_text)
    return re.sub(r"\s*[-|]\s*CyberPulse\s*$", "", strip_tags(m.group(1))).strip() if m else "Untitled"


def source_link(html_text: str, body: str) -> str | None:
    """Pull the original-article URL out of the closing 'Source:' note."""
    aside = re.search(r'<aside class="source-note">(.*?)</aside>', html_text, re.S)
    for fragment in ([aside.group(1)] if aside else []) + list(reversed(P_RE.findall(body))):
        if "source" not in strip_tags(fragment).lower():
            continue
        href = re.search(r'<a href="(https?://[^"]+)"', fragment)
        if href and "insert link" not in href.group(1).lower():
            return href.group(1)
    return None


def make_summary(body: str, title: str) -> str:
    """Build a real, unique ~155-char meta description from the article lead."""
    for para in P_RE.findall(body):
        text = strip_tags(para)
        if len(text) < 60 or text.lower().startswith("source"):
            continue
        if len(text) <= 158:
            return text
        cut = text[:158]
        cut = cut.rsplit(" ", 1)[0].rstrip(",;:")
        return cut + "…"
    return f"{title} — a CyberPulse dispatch on the digital frontier."


def classify(title: str, body_text: str) -> str:
    """Assign a section from the article's own words (no API call needed)."""
    haystack_title = title.lower()
    haystack_body = body_text.lower()
    scores: dict[str, int] = {}
    for category, rules in CATEGORY_RULES.items():
        score = 0
        for pattern, weight in rules:
            hits = len(re.findall(pattern, haystack_title, re.I))
            if hits:
                score += weight * 3 * min(hits, 2)
            elif re.search(pattern, haystack_body, re.I):
                score += weight
        if score:
            scores[category] = score
    if not scores:
        return "AI"
    best = max(scores.values())
    # Deterministic tie-break using the declared priority order.
    for category in CATEGORY_PRIORITY:
        if scores.get(category) == best:
            return category
    return "AI"


def make_tags(title: str, body_text: str, category: str) -> list[str]:
    """Score tag candidates by how strongly the article actually covers them."""
    t, b = title.lower(), body_text.lower()
    scored: list[tuple[int, str]] = []
    for tag, pattern, weight in TAG_RULES:
        score = 0
        hits = len(re.findall(pattern, t, re.I))
        if hits:
            score += weight * 3 * min(hits, 2)
        body_hits = len(re.findall(pattern, b, re.I))
        if body_hits:
            score += weight * min(body_hits, 3)
        if score >= 6:  # ignore incidental one-off mentions
            scored.append((score, tag))
    scored.sort(key=lambda x: (-x[0], x[1]))
    tags = [tag for _, tag in scored[:4]]
    # Always keep one tag that ties back to the section, for cross-linking.
    anchor = {"Cybersecurity": "security", "AI": "artificial intelligence",
              "Policy": "tech policy", "Science": "research",
              "Startups": "startups", "Gadgets": "hardware"}.get(category)
    if anchor and anchor not in tags:
        tags.append(anchor)
    return tags[:5]


def reading_time(body: str) -> int:
    words = len(strip_tags(body).split())
    return max(1, round(words / 220))


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[’']", "", text)
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")[:52]


def shingles(text: str, n: int = 5) -> set:
    words = re.sub(r"[^a-z0-9 ]", "", text.lower()).split()
    return {tuple(words[i:i + n]) for i in range(max(0, len(words) - n + 1))}


def title_similarity(a: str, b: str) -> float:
    import difflib

    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


def find_duplicate_clusters(posts: list[dict]) -> list[list[dict]]:
    """Group dispatches that cover the same ground.

    An unattended daily generator will happily write the same story eight times.
    Search engines punish that and readers bounce, so near-duplicates are
    detected here and collapsed onto a single canonical article.
    """
    parent = {p["url"]: p["url"] for p in posts}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    shingle_cache = {p["url"]: shingles(p["text"]) for p in posts}

    for i, a in enumerate(posts):
        for b in posts[i + 1:]:
            sa, sb = shingle_cache[a["url"]], shingle_cache[b["url"]]
            jaccard = len(sa & sb) / len(sa | sb) if sa and sb else 0.0
            if jaccard >= 0.30 or title_similarity(a["title"], b["title"]) >= 0.86:
                union(a["url"], b["url"])

    clusters: dict[str, list[dict]] = {}
    for p in posts:
        clusters.setdefault(find(p["url"]), []).append(p)
    # Only clusters with more than one member matter.
    return [members for members in clusters.values() if len(members) > 1]


# --------------------------------------------------------------------------
# Collection
# --------------------------------------------------------------------------
def load_existing_index() -> dict[str, dict]:
    if not INDEX_PATH.exists():
        return {}
    try:
        entries = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    out: dict[str, dict] = {}
    for entry in entries:  # first occurrence wins == most recently published
        url = entry.get("url", "")
        if url and url not in out:
            out[url] = entry
    return out


def anchor_date() -> dt.date:
    """The newest publish date we are allowed to invent for legacy posts."""
    try:
        import subprocess

        raw = subprocess.run(
            ["git", "log", "-1", "--format=%aI"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout.strip()
        if raw:
            return dt.datetime.fromisoformat(raw).date()
    except Exception:
        pass
    return dt.date.today()


OVERRIDES_PATH = ROOT / "content" / "overrides.json"


def load_overrides() -> dict[str, str]:
    """Manual, human-decided section assignments keyed by blog filename."""
    if not OVERRIDES_PATH.exists():
        return {}
    try:
        data = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
        return data.get("categories", {}) if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def collect_posts() -> list[dict]:
    old_index = load_existing_index()
    overrides = load_overrides()
    # Preserve the historical newest-first ordering from the old index.
    order = {url: i for i, url in enumerate(old_index.keys())}

    posts: list[dict] = []
    for path in sorted(BLOG_DIR.glob("*.html")):
        raw = path.read_text(encoding="utf-8")
        url = f"blog/{path.name}"
        body = clean_body(extract_body(raw))
        if not body:
            print(f"  ! skipped (no article body found): {path.name}")
            continue

        title = extract_title(raw, body)
        plain = strip_tags(body)

        # Recover the published date from the previously rendered page so that
        # re-running the build never rewrites history.
        published = None
        for pattern in (PUBLISHED_RE, TIME_RE):
            m = pattern.search(raw)
            if m:
                try:
                    published = dt.datetime.fromisoformat(m.group(1).replace("Z", "+00:00"))
                    break
                except ValueError:
                    continue

        # Category precedence:
        #   1. content/overrides.json  (an explicit human decision)
        #   2. <!--cp:category:--> marker written by the daily generator
        #   3. the keyword classifier, run over this article's own text
        marker = MARKER_RE.search(raw)
        category = (
            overrides.get(path.name)
            or (marker.group(1).strip() if marker else None)
            or classify(title, plain)
        )
        category = category.strip()
        if category.lower() != "ai":
            category = category.title()

        posts.append({
            "title": title,
            "url": url,
            "path": path,
            "category": category,
            "body": body,
            "text": plain,
            "summary": make_summary(body, title),
            "readingTime": reading_time(body),
            "source": source_link(raw, body),
            "published": published,
            "_order": order.get(url, 10_000 + len(posts)),
        })

    for post in posts:
        post["tags"] = make_tags(post["title"], post["text"], post["category"])

    # Newest first, falling back to the historical index order.
    posts.sort(key=lambda p: p["_order"])

    # Backfill dates for legacy posts: the pipeline ships one dispatch a day,
    # so walk backwards one day at a time from the anchor date.
    day = anchor_date()
    for post in posts:
        if post["published"] is None:
            post["published"] = dt.datetime(day.year, day.month, day.day, 9, 0, tzinfo=dt.timezone.utc)
            day -= dt.timedelta(days=1)
        else:
            day = post["published"].date() - dt.timedelta(days=1)

    posts.sort(key=lambda p: p["published"], reverse=True)

    for post in posts:
        d = post["published"]
        post["date"] = d.isoformat()
        post["dateLabel"] = f"{MONTHS[d.month - 1]} {d.day}, {d.year}"

    # Collapse near-duplicate coverage onto the newest article in each cluster.
    for post in posts:
        post["canonical"] = post["url"]
        post["noindex"] = False
        post["duplicates"] = []
    for cluster in find_duplicate_clusters(posts):
        keep = cluster[0]  # posts are already newest-first
        for other in cluster[1:]:
            other["canonical"] = keep["url"]
            other["noindex"] = True
            keep["duplicates"].append(other)
        print(f"  ~ duplicate cluster: keeping '{keep['title'][:52]}' "
              f"(+{len(cluster) - 1} older variant(s) canonicalised)")
    return posts


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------
def jsonld_post(post: dict) -> dict:
    ld = {
        "@context": "https://schema.org",
        "@type": "BlogPosting",
        "headline": post["title"],
        "description": post["summary"],
        "datePublished": post["date"],
        "dateModified": post["date"],
        "mainEntityOfPage": {"@type": "WebPage", "@id": T.abs_url(post["url"])},
        "author": {"@type": "Organization", "name": T.SITE_NAME, "url": T.SITE_URL},
        "publisher": {
            "@type": "Organization",
            "name": T.SITE_NAME,
            "url": T.SITE_URL,
            "logo": {"@type": "ImageObject", "url": T.OG_IMAGE},
        },
        "image": [T.OG_IMAGE],
        "articleSection": [post["category"]],
        "keywords": post["tags"],
        "inLanguage": "en",
    }
    if post.get("source"):
        ld["citation"] = post["source"]
    return ld


def render_post(post: dict, posts: list[dict], listing: list[dict]) -> str:
    year = dt.date.today().year
    idx = listing.index(post) if post in listing else -1
    newer = listing[idx - 1] if idx > 0 else None
    older = listing[idx + 1] if 0 <= idx + 1 < len(listing) else None

    related = [p for p in listing if p is not post and p["category"] == post["category"]][:3]
    if len(related) < 3:
        related += [p for p in listing if p is not post and p not in related][: 3 - len(related)]

    cat_slug = post["category"].lower().replace(" ", "-")
    share_url = T.abs_url(post["url"])
    share_title = T.e(post["title"])

    pager_bits = []
    if newer:
        pager_bits.append(
            f'<a class="prev" href="../{T.e(newer["url"])}" rel="prev"><span class="dir">← Newer</span>'
            f'<span class="t">{T.e(newer["title"])}</span></a>'
        )
    else:
        pager_bits.append('<span></span>')
    if older:
        pager_bits.append(
            f'<a class="next" href="../{T.e(older["url"])}" rel="next"><span class="dir">Older →</span>'
            f'<span class="t">{T.e(older["title"])}</span></a>'
        )

    tag_html = "".join(
        f'<a class="chip" href="../category-{cat_slug}.html" data-tag="{T.e(t)}">#{T.e(t)}</a>'
        for t in post["tags"]
    )

    source_html = ""
    if post.get("source"):
        source_html = (
            f'<aside class="source-note"><b>Source:</b> '
            f'<a href="{T.e(post["source"])}" rel="noopener noreferrer nofollow" target="_blank">'
            f'{T.e(post["source"])}</a> — reported and rewritten by CyberPulse.</aside>'
        )

    body_html = post["body"]
    # The H1 is rendered by the article header, so drop it from the body copy.
    body_html = H1_RE.sub("", body_html, count=1).strip()

    dup_note = ""
    if post["noindex"] and post["canonical"] != post["url"]:
        canon = next((p for p in posts if p["url"] == post["canonical"]), None)
        if canon:
            dup_note = (
                '<aside class="source-note"><b>Heads up:</b> CyberPulse has covered this story '
                'more than once. The up-to-date version is '
                f'<a href="../{T.e(canon["url"])}">{T.e(canon["title"])}</a>.</aside>'
            )

    related_html = "".join(T.post_card(p, root="../") for p in related)

    page = T.head(
        title=post["title"],
        description=post["summary"],
        path=post["url"],
        prefix="../",
        og_type="article",
        published=post["date"],
        section=post["category"],
        jsonld=None if post["noindex"] else jsonld_post(post),
        noindex=post["noindex"],
        canonical_path=post["canonical"],
        marker=f'<!--cp:category:{T.e(post["category"])}-->',
        extra=(
            f'<meta name="keywords" content="{T.e(", ".join(post["tags"]))}">'
            f'<meta name="author" content="{T.SITE_NAME}">'
        ),
    )
    page += T.header(post["url"], prefix="../", root="../")
    page += f"""
<div class="progress-bar" id="progress-bar" aria-hidden="true"></div>
<main id="main" class="article-shell">
    <article>
        <header class="article-head">
            <p class="eyebrow"><a class="category-tag" href="../category-{cat_slug}.html">{T.e(post['category'])}</a></p>
            <h1>{T.e(post['title'])}</h1>
            <p class="standfirst">{T.e(post['summary'])}</p>
            <div class="post-meta">
                <time datetime="{T.e(post['date'])}">{T.e(post['dateLabel'])}</time>
                <span class="dot" aria-hidden="true">•</span>
                <span>{post['readingTime']} min read</span>
                <span class="dot" aria-hidden="true">•</span>
                <span>By {T.SITE_NAME}</span>
            </div>
        </header>
        {dup_note}
        <div class="post-content">{body_html}</div>
        {source_html}
        <div class="article-extras">
            <div class="share-row">
                <span class="label">Share</span>
                <a class="share-btn" target="_blank" rel="noopener noreferrer"
                   href="https://twitter.com/intent/tweet?text={share_title}&amp;url={T.e(share_url)}">
                   X / Twitter</a>
                <a class="share-btn" target="_blank" rel="noopener noreferrer"
                   href="https://www.linkedin.com/sharing/share-offsite/?url={T.e(share_url)}">LinkedIn</a>
                <a class="share-btn" target="_blank" rel="noopener noreferrer"
                   href="https://news.ycombinator.com/submitlink?u={T.e(share_url)}&amp;t={share_title}">Hacker News</a>
                <a class="share-btn" href="mailto:?subject={share_title}&amp;body={T.e(share_url)}">Email</a>
                <button class="share-btn" type="button" data-copy="{T.e(share_url)}">Copy link</button>
            </div>
            <div class="tag-row">{tag_html}</div>
        </div>
    </article>
    <nav class="pager" aria-label="Article pagination">{''.join(pager_bits)}</nav>
    <section class="related">
        <h2>Keep reading</h2>
        <div class="post-list">{related_html}</div>
    </section>
</main>
"""
    page += T.footer(root="../", year=year)
    return page


def render_index(posts: list[dict], categories: list[str], counts: dict) -> str:
    year = dt.date.today().year
    featured = posts[0]
    rest = posts[1:]

    cards = "".join(T.post_card(p) for p in rest)
    total = len(posts)

    jsonld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "WebSite",
                "@id": T.abs_url("index.html"),
                "name": T.SITE_NAME,
                "url": T.SITE_URL,
                "description": T.SITE_DESCRIPTION,
                "publisher": {"@type": "Organization", "name": T.SITE_NAME, "url": T.SITE_URL},
                "potentialAction": {
                    "@type": "SearchAction",
                    "target": {"@type": "EntryPoint", "urlTemplate": T.abs_url("index.html") + "?q={search_term_string}"},
                    "query-input": "required name=search_term_string",
                },
            },
            {
                "@type": "Blog",
                "@id": T.abs_url("index.html") + "#blog",
                "name": T.SITE_NAME,
                "url": T.SITE_URL,
                "blogPost": [
                    {
                        "@type": "BlogPosting",
                        "headline": p["title"],
                        "url": T.abs_url(p["url"]),
                        "datePublished": p["date"],
                    }
                    for p in posts[:12]
                ],
            },
            {
                "@type": "ItemList",
                "itemListElement": [
                    {"@type": "ListItem", "position": i + 1, "url": T.abs_url(p["url"])}
                    for i, p in enumerate(posts)
                ],
            },
        ],
    }

    chips = [
        f'<a class="chip is-active" href="index.html" data-filter="all" aria-pressed="true">All<span class="count">{total}</span></a>'
    ]
    for cat in categories:
        slug = cat.lower().replace(" ", "-")
        chips.append(
            f'<a class="chip" href="category-{slug}.html" data-filter="{T.e(cat)}" aria-pressed="false">'
            f'{T.e(cat)}<span class="count">{counts.get(cat, 0)}</span></a>'
        )

    page = T.head(
        title=f"{T.SITE_NAME} — {T.TAGLINE}",
        description=T.SITE_DESCRIPTION,
        path="index.html",
        jsonld=jsonld,
    )
    page += T.header("index.html")
    page += f"""
<main id="main">
    <section class="hero">
        <div class="container">
            <p class="eyebrow">// {T.TAGLINE} //</p>
            <h1>The security &amp; AI briefing that writes itself — and reads like it shouldn't.</h1>
            <p class="lede">One dispatch a day on cyberattacks, artificial intelligence and the rules
            governing both. Short enough to finish with your coffee, sourced enough to quote in a meeting.</p>
            <p class="hero-stats">
                <span><b>{total}</b> dispatches published</span>
                <span><b>{len(categories)}</b> sections</span>
                <span><b>Daily</b> at 02:30 UTC</span>
                <span><b>Free</b> RSS &amp; no paywall</span>
            </p>
        </div>
    </section>

    <div class="toolbar">
        <div class="container">
            <div class="toolbar-row">
                <div class="search-wrap">
                    <label class="visually-hidden" for="search-input">Search dispatches</label>
                    {T.SEARCH_ICON}
                    <input type="search" id="search-input" placeholder="Search {total} dispatches — try “phishing”, “deepfake”, “EU”…" autocomplete="off" spellcheck="false">
                </div>
            </div>
            <div class="chip-row" role="group" aria-label="Filter by section">{''.join(chips)}</div>
            <p class="result-note" id="result-note" role="status" aria-live="polite"></p>
        </div>
    </div>

    <div class="container">
        <div id="featured-container">{T.featured_card(featured)}</div>
        <div id="post-list-container" class="post-list">{cards}</div>
        <button class="load-more" id="load-more" type="button" hidden>Show more dispatches</button>
        <div class="empty-state" id="empty-state" hidden>
            <h3>No dispatches match that search</h3>
            <p>Try a broader term — or browse the <a href="index.html">full archive</a>.</p>
        </div>

        <section class="cta-band">
            <h2>Get tomorrow's dispatch before the headlines do</h2>
            <p>CyberPulse publishes every morning at 02:30 UTC. Follow the feed you already live in —
            no account, no paywall, no tracking pixels.</p>
            <div class="cta-actions">
                <a class="btn btn-primary" href="feed.xml">{T.RSS_ICON} Subscribe via RSS</a>
                <a class="btn btn-ghost" href="about.html">How we work</a>
            </div>
        </section>
    </div>
</main>
"""
    page += T.footer(year=year)
    return page


def render_category(category: str, posts: list[dict], counts: dict, categories: list[str]) -> str:
    year = dt.date.today().year
    slug = category.lower().replace(" ", "-")
    filename = f"category-{slug}.html"
    cards = "".join(T.post_card(p) for p in posts)

    descriptions = {
        "Cybersecurity": "Attacks, breaches, malware and defence — every CyberPulse dispatch on keeping systems standing.",
        "AI": "Model releases, AI safety, deepfakes and machine-learning breakthroughs, filed by CyberPulse.",
        "Policy": "Regulation, sovereignty and the rules of the road for technology — CyberPulse policy dispatches.",
    }
    description = descriptions.get(
        category,
        f"All {len(posts)} CyberPulse dispatches filed under {category}.",
    )

    jsonld = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": f"{category} — {T.SITE_NAME}",
        "url": T.abs_url(filename),
        "description": description,
        "isPartOf": {"@type": "WebSite", "name": T.SITE_NAME, "url": T.SITE_URL},
        "mainEntity": {
            "@type": "ItemList",
            "itemListElement": [
                {"@type": "ListItem", "position": i + 1, "url": T.abs_url(p["url"])}
                for i, p in enumerate(posts)
            ],
        },
    }

    chips = []
    for cat in categories:
        cslug = cat.lower().replace(" ", "-")
        active = ' is-active" aria-pressed="true' if cat == category else '" aria-pressed="false'
        chips.append(
            f'<a class="chip{active}" href="category-{cslug}.html" data-filter="{T.e(cat)}">'
            f'{T.e(cat)}<span class="count">{counts.get(cat, 0)}</span></a>'
        )

    page = T.head(
        title=f"{category} dispatches",
        description=description,
        path=filename,
        jsonld=jsonld,
    )
    page += T.header(filename)
    page += f"""
<main id="main">
    <div class="page-head">
        <div class="container">
            <p class="eyebrow">Section</p>
            <h1>{T.e(category)}</h1>
            <p>{T.e(description)}</p>
        </div>
    </div>
    <div class="toolbar">
        <div class="container">
            <div class="toolbar-row">
                <div class="search-wrap">
                    <label class="visually-hidden" for="search-input">Search {T.e(category)} dispatches</label>
                    {T.SEARCH_ICON}
                    <input type="search" id="search-input" placeholder="Search this section…" autocomplete="off" spellcheck="false">
                </div>
            </div>
            <div class="chip-row" role="group" aria-label="Filter by section">{''.join(chips)}</div>
            <p class="result-note" id="result-note" role="status" aria-live="polite">{len(posts)} dispatches</p>
        </div>
    </div>
    <div class="container">
        <div id="post-list-container" class="post-list">{cards}</div>
        <button class="load-more" id="load-more" type="button" hidden>Show more dispatches</button>
        <div class="empty-state" id="empty-state" hidden>
            <h3>Nothing matches that search</h3>
            <p>Try a different term, or <a href="index.html">browse every dispatch</a>.</p>
        </div>
    </div>
</main>
"""
    page += T.footer(year=year)
    return page


def render_static(name: str, meta: dict, body_html: str) -> str:
    year = dt.date.today().year
    extra = ""
    if name == "about.html":
        extra = '<meta name="author" content="CyberPulse">'
    page = T.head(
        title=meta["title"],
        description=meta["description"],
        path=name,
        jsonld={
            "@context": "https://schema.org",
            "@type": "WebPage",
            "name": meta["title"],
            "url": T.abs_url(name),
            "description": meta["description"],
            "isPartOf": {"@type": "WebSite", "name": T.SITE_NAME, "url": T.SITE_URL},
        },
        extra=extra,
    )
    page += T.header(name)
    page += f"""
<main id="main" class="static-page">
    <div class="container">
        <div class="post-content">{body_html}</div>
    </div>
</main>
"""
    page += T.footer(year=year)
    return page


def render_404() -> str:
    year = dt.date.today().year
    page = T.head(
        title="Page not found (404)",
        description="That dispatch has moved or never existed. Head back to the CyberPulse archive.",
        path="404.html",
        noindex=True,
    )
    page += T.header("404.html")
    page += f"""
<main id="main" class="static-page">
    <div class="container">
        <div class="post-content" style="text-align:center">
            <p class="eyebrow">Error 404</p>
            <h1>Signal lost</h1>
            <p>The page you were looking for isn't on this frequency. It may have been renamed,
            moved, or it never existed in the first place.</p>
            <p><a class="btn btn-primary" href="index.html">Back to the archive</a></p>
        </div>
    </div>
</main>
"""
    page += T.footer(year=year)
    return page


# --------------------------------------------------------------------------
# Feeds & discovery files
# --------------------------------------------------------------------------
def write_index_json(posts: list[dict]) -> list[dict]:
    entries = [
        {
            "title": p["title"],
            "summary": p["summary"],
            "url": p["url"],
            "category": p["category"],
            "date": p["date"],
            "tags": p["tags"],
            "readingTime": p["readingTime"],
        }
        for p in posts
    ]
    INDEX_PATH.write_text(json.dumps(entries, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")
    return entries


def write_sitemap(posts: list[dict], categories: list[str]) -> None:
    today = dt.date.today().isoformat()
    urls = [("index.html", today, "weekly", "1.0"), ("about.html", today, "monthly", "0.5"),
            ("contact.html", today, "yearly", "0.3"), ("privacy.html", today, "yearly", "0.3")]
    for cat in categories:
        urls.append((f"category-{cat.lower().replace(' ', '-')}.html", today, "daily", "0.8"))
    body = []
    for loc, lastmod, freq, prio in urls:
        body.append(
            f"  <url>\n    <loc>{xml_escape(T.abs_url(loc))}</loc>\n"
            f"    <lastmod>{lastmod}</lastmod>\n    <changefreq>{freq}</changefreq>\n"
            f"    <priority>{prio}</priority>\n  </url>"
        )
    for p in posts:
        body.append(
            f"  <url>\n    <loc>{xml_escape(T.abs_url(p['url']))}</loc>\n"
            f"    <lastmod>{p['published'].date().isoformat()}</lastmod>\n"
            f"    <changefreq>monthly</changefreq>\n    <priority>0.7</priority>\n  </url>"
        )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(body)
        + "\n</urlset>\n"
    )
    (ROOT / "sitemap.xml").write_text(xml, encoding="utf-8")


def write_feed(posts: list[dict]) -> None:
    items = []
    for p in posts[:30]:
        cat_slug = p["category"].lower().replace(" ", "-")
        items.append(
            "    <item>\n"
            f"      <title>{xml_escape(p['title'])}</title>\n"
            f"      <link>{xml_escape(T.abs_url(p['url']))}</link>\n"
            f"      <guid isPermaLink=\"true\">{xml_escape(T.abs_url(p['url']))}</guid>\n"
            f"      <pubDate>{p['published'].strftime('%a, %d %b %Y %H:%M:%S +0000')}</pubDate>\n"
            f"      <category>{xml_escape(p['category'])}</category>\n"
            f"      <description>{xml_escape(p['summary'])}</description>\n"
            f"      <dc:creator>{xml_escape(T.SITE_NAME)}</dc:creator>\n"
            "    </item>"
        )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
        "  <channel>\n"
        f"    <title>{xml_escape(T.SITE_NAME)} — {xml_escape(T.TAGLINE)}</title>\n"
        f"    <link>{xml_escape(T.SITE_URL)}</link>\n"
        f"    <description>{xml_escape(T.SITE_DESCRIPTION)}</description>\n"
        "    <language>en</language>\n"
        f"    <lastBuildDate>{posts[0]['published'].strftime('%a, %d %b %Y %H:%M:%S +0000') if posts else ''}</lastBuildDate>\n"
        f"    <atom:link href=\"{xml_escape(T.abs_url('feed.xml'))}\" rel=\"self\" type=\"application/rss+xml\"/>\n"
        f"    <image><url>{xml_escape(T.OG_IMAGE)}</url><title>{xml_escape(T.SITE_NAME)}</title>"
        f"<link>{xml_escape(T.SITE_URL)}</link></image>\n"
        + "\n".join(items)
        + "\n  </channel>\n</rss>\n"
    )
    (ROOT / "feed.xml").write_text(xml, encoding="utf-8")


def write_robots() -> None:
    (ROOT / "robots.txt").write_text(
        "User-agent: *\nAllow: /\nDisallow: /tools/\n\n"
        f"Sitemap: {T.abs_url('sitemap.xml')}\n",
        encoding="utf-8",
    )


def write_favicon() -> None:
    ASSETS_DIR.mkdir(exist_ok=True)
    (ASSETS_DIR / "favicon.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
        '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
        '<stop offset="0" stop-color="#0a63d4"/><stop offset="1" stop-color="#7b5cff"/>'
        '</linearGradient></defs>'
        '<rect width="64" height="64" rx="14" fill="url(#g)"/>'
        '<path d="M8 34h10l5-14 7 26 6-18 4 8h16" fill="none" stroke="#fff" '
        'stroke-width="4.5" stroke-linecap="round" stroke-linejoin="round"/></svg>\n',
        encoding="utf-8",
    )


def write_manifest() -> None:
    ASSETS_DIR.mkdir(exist_ok=True)
    manifest = {
        "name": f"{T.SITE_NAME} — {T.TAGLINE}",
        "short_name": T.SITE_NAME,
        "description": T.SITE_DESCRIPTION,
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "background_color": "#0c0e12",
        "theme_color": "#0a63d4",
        "categories": ["news", "technology", "security"],
        "icons": [
            {"src": "/assets/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/assets/icon-512.png", "sizes": "512x512", "type": "image/png"},
        ],
    }
    (ASSETS_DIR / "site.webmanifest").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def write_netlify_config() -> None:
    (ROOT / "netlify.toml").write_text(
        """# Netlify configuration for CyberPulse
[build]
  publish = "."
  command = "python3 tools/build.py"

[[redirects]]
  from = "/feed"
  to = "/feed.xml"
  status = 301

[[redirects]]
  from = "/rss"
  to = "/feed.xml"
  status = 301

[[headers]]
  for = "/*"
  [headers.values]
    X-Content-Type-Options = "nosniff"
    Referrer-Policy = "strict-origin-when-cross-origin"
    Permissions-Policy = "geolocation=(), microphone=(), camera=()"
    X-Frame-Options = "SAMEORIGIN"

[[headers]]
  for = "/style.css"
  [headers.values]
    Cache-Control = "public, max-age=3600, must-revalidate"

[[headers]]
  for = "/blog.js"
  [headers.values]
    Cache-Control = "public, max-age=3600, must-revalidate"
""",
        encoding="utf-8",
    )


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def build() -> int:
    print(f"Site URL: {T.SITE_URL}")
    posts = collect_posts()
    # Only canonical (non-duplicate) dispatches appear in listings and feeds.
    listing = [p for p in posts if not p["noindex"]]
    hidden = len(posts) - len(listing)
    print(f"Collected {len(posts)} articles "
          f"({len(listing)} listed, {hidden} duplicate(s) canonicalised)")

    counts: dict[str, int] = {}
    for p in listing:
        counts[p["category"]] = counts.get(p["category"], 0) + 1
    categories = sorted(counts, key=lambda c: (-counts[c], c))
    T.CURRENT_CATEGORIES = categories
    print("Sections: " + ", ".join(f"{c} ({counts[c]})" for c in categories))

    # 1. Articles
    for post in posts:
        post["path"].write_text(render_post(post, posts, listing), encoding="utf-8")
    print(f"Rendered {len(posts)} article pages")

    # 2. Index JSON (the API the client-side search uses)
    entries = write_index_json(listing)
    print(f"Wrote blog-index.json ({len(entries)} entries, "
          f"{len(set(e['summary'] for e in entries))} unique summaries)")

    # 3. Home page + category pages
    (ROOT / "index.html").write_text(render_index(listing, categories, counts), encoding="utf-8")
    for cat in categories:
        cat_posts = [p for p in listing if p["category"] == cat]
        filename = f"category-{cat.lower().replace(' ', '-')}.html"
        (ROOT / filename).write_text(
            render_category(cat, cat_posts, counts, categories), encoding="utf-8"
        )
    # Retire category pages whose section no longer exists.
    for stale in ROOT.glob("category-*.html"):
        if stale.stem.replace("category-", "") not in {c.lower().replace(" ", "-") for c in categories}:
            stale.unlink()
            print(f"Removed stale category page: {stale.name}")
    print(f"Rendered index.html + {len(categories)} category pages")

    # 4. Static pages: re-wrap their existing copy in the new chrome.
    for name, meta in STATIC_PAGES.items():
        path = ROOT / name
        if not path.exists():
            continue
        body = clean_body(extract_body(path.read_text(encoding="utf-8")))
        if not body:
            print(f"  ! {name}: no body found, left untouched")
            continue
        if name == "contact.html":
            body = body.replace(
                "<strong>contact.cyberpulse@gmail.com</strong>",
                '<a href="mailto:contact.cyberpulse@gmail.com">contact.cyberpulse@gmail.com</a>',
            )
        path.write_text(render_static(name, meta, body), encoding="utf-8")
    (ROOT / "404.html").write_text(render_404(), encoding="utf-8")
    print("Rendered static pages + 404.html")

    # 5. Discovery & feeds
    write_sitemap(listing, categories)
    write_feed(listing)
    write_robots()
    write_favicon()
    write_manifest()
    write_netlify_config()
    print("Wrote sitemap.xml, feed.xml, robots.txt, favicon, manifest, netlify.toml")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build the CyberPulse static site")
    parser.add_argument("--check", action="store_true", help="build, then report changed files")
    args = parser.parse_args()

    before: dict[str, str] = {}
    if args.check:
        for p in list(ROOT.glob("*.html")) + list(BLOG_DIR.glob("*.html")) + [INDEX_PATH]:
            if p.exists():
                before[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()

    code = build()

    if args.check:
        changed = [
            name for name, digest in before.items()
            if not (ROOT / name).exists()
            or hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest
        ]
        print(f"\n--check: {len(changed)} file(s) would change: {', '.join(sorted(changed)) or 'none'}")
        code = 1 if changed else 0
    sys.exit(code)
