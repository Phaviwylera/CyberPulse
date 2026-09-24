# CyberPulse

> **// The Beat of the Digital World //**

CyberPulse is an automation-assisted tech-security newsroom: a GitHub Action runs every
morning at **02:30 UTC**, picks the freshest story from a set of RSS feeds, has an LLM
rewrite it as an original briefing, and commits a fully rebuilt static site. The site is
published as plain HTML/CSS/JS on Netlify — no server, no database, no build step at
deploy time.

---

## What's in this repository

| Path | Purpose |
| --- | --- |
| `index.html`, `category-*.html`, `about/contact/privacy/404.html` | Generated pages |
| `blog/*.html` | One file per dispatch (the source of truth for article copy) |
| `blog-index.json` | The search/listing API: title, summary, URL, section, date, tags |
| `sitemap.xml`, `feed.xml`, `robots.txt` | Discovery for search engines and readers |
| `assets/` | Brand image, favicons, web manifest |
| `tools/build.py` | The static-site builder (standard library only) |
| `tools/templates.py` | Every shared template: head, header, footer, cards |
| `.github/workflows/daily_post_generator.py` | The daily AI pipeline |
| `.github/workflows/main.yml` | Schedule, dependencies, commit-and-push |
| `content/overrides.json` | Manual section assignments, when a human disagrees with the classifier |

## Local development

```bash
python3 tools/build.py          # rebuild every page from blog/*.html
python3 -m http.server 8000     # then open http://localhost:8000
```

The build is **idempotent** — running it twice produces byte-identical output, because
dates, sections and summaries are read back out of the previously rendered pages.

`python3 tools/build.py --check` reports whether a rebuild would change anything
(useful as a CI gate).

Set `SITE_URL` to change the canonical domain (defaults to the production URL):

```bash
SITE_URL=https://staging.example.com python3 tools/build.py
```

## The daily pipeline

```
RSS feeds ─▶ dedupe against archive ─▶ LLM (structured JSON) ─▶ blog/<date>-<slug>.html
                                                                        │
                                                                        ▼
                                        tools/build.py re-renders the whole site
                                        (index, sections, sitemap, RSS, search index)
                                                                        │
                                                                        ▼
                                              git-auto-commit-action ─▶ Netlify
```

Notable behaviours:

* **Never re-files a story we already covered.** Candidate headlines are compared
  against the archive (word-overlap + sequence similarity) before being written.
* **Structured output.** The model must return
  `{category, title, standfirst, body_html, takeaway}` conforming to a JSON schema, so a
  stray code fence can't corrupt a page.
* **The section is recorded** in a `<!--cp:category:…-->` marker inside each post, which
  the builder treats as authoritative. Legacy posts without a marker are classified by a
  keyword scorer in `tools/build.py`.

## How the site wins readers

* **Crawlable without JavaScript.** Article lists are rendered server-side; JS only adds
  search, filtering, pagination and theming on top.
* **Real metadata everywhere.** Every page ships a unique meta description, canonical
  URL, Open Graph + Twitter cards, `BlogPosting`/`CollectionPage` JSON-LD, and an
  `article:published_time`.
* **No duplicate-content penalty.** Near-identical dispatches are clustered; the older
  copies get `rel=canonical` + `noindex` and a pointer to the live version instead of
  competing with it in search results.
* **Discoverability.** `sitemap.xml`, an RSS 2.0 `feed.xml` (also at `/rss` and `/feed`),
  `robots.txt`, and a web manifest.
* **Retention UX.** Dark mode, reading-progress bar, reading time, related posts,
  new/old pagination, share buttons, section chips, and full keyboard/AT support
  (skip link, focus rings, `aria-current`, live-region result counts).
* **Fast.** System fonts for body text, one subsetted web font for accents, quantised
  brand imagery (~68 KB social card), and cache/security headers in `netlify.toml`.

## Editing content by hand

* Change an article's section: add it to `content/overrides.json`
  (`{"categories": {"my-post.html": "Policy"}}`) and rebuild.
* Change any copy: edit the `<div class="post-content">` block in the `blog/*.html` file
  and rebuild. The builder preserves dates and everything else.
