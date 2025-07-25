import os
import feedparser
import google.generativeai as genai
import datetime
import json
from pathlib import Path
import re

# --- Configuration ---
RSS_FEEDS = [
    'https://techcrunch.com/feed/',
    'https://www.wired.com/feed/category/technology/latest/rss',
    'https://www.reuters.com/pf/api/v2/content/assets/v1/collection/id/43664/feed/rss/'
]
API_KEY = os.getenv('GEMINI_API_KEY')
BLOG_INDEX_PATH = Path("blog-index.json")
BLOG_POSTS_DIR = Path("blog")
ROOT_DIR = Path(".")

# --- (Functions 1, 2, and 3: get_latest_article, generate_blog_post are unchanged) ---
genai.configure(api_key=API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

def get_latest_article():
    print("Fetching articles from RSS feeds...")
    latest_article = None
    latest_pub_date = None
    for feed_url in RSS_FEEDS:
        feed = feedparser.parse(feed_url)
        for entry in feed.entries:
            pub_date = entry.get('published_parsed') or entry.get('updated_parsed')
            if pub_date:
                current_article_date = datetime.datetime(*pub_date[:6], tzinfo=datetime.timezone.utc)
                if latest_pub_date is None or current_article_date > latest_pub_date:
                    latest_pub_date = current_article_date
                    latest_article = entry
    if latest_article:
        print(f"Found latest article: '{latest_article.title}'")
        return { "title": latest_article.title, "summary": latest_article.summary, "link": latest_article.link }
    return None

def generate_blog_post(article):
    print("Generating new blog post with AI...")
    prompt = f"""
    You have two tasks.
    Task 1: Analyze the content of the following news article and determine the most relevant, single-word category for it. Choose from options like: AI, Cybersecurity, Gadgets, Startups, Policy, Science.
    Task 2: Act as a tech blogger for 'CyberPulse'. Write a new, original blog post of 300-400 words based on the article. Start with a compelling H1 title. At the end, include a bolded "Source:" line with a link to the original article.
    Your final output MUST be a single JSON object with two keys: "category" and "post_html".
    The "post_html" value must be pure HTML, with no markdown like ```html.
    """
    response = model.generate_content(prompt)
    clean_response_text = response.text.strip().replace("```json", "").replace("```", "")
    try:
        data = json.loads(clean_response_text)
        clean_html = data.get("post_html", "").strip()
        clean_html = re.sub(r'^```html\n?', '', clean_html, flags=re.MULTILINE)
        clean_html = re.sub(r'\n?```$', '', clean_html, flags=re.MULTILINE)
        data["post_html"] = clean_html.strip()
        return data
    except json.JSONDecodeError:
        print("Error: AI did not return valid JSON. Cannot proceed.")
        return None

def create_new_post_files(post_data):
    # This function is now only responsible for the single post and updating the index
    post_html = post_data.get("post_html")
    category = post_data.get("category", "Tech News")
    print(f"Creating new post files under category: {category}...")
    from xml.etree import ElementTree as ET
    try:
        root = ET.fromstring(f"<root>{post_html}</root>")
        h1_element = root.find('h1')
        title = h1_element.text if h1_element is not None else "New CyberPulse Post"
    except Exception:
        title = "New CyberPulse Post"
    slug = title.lower().replace(' ', '-').replace('?', '').replace(':', '').replace("'", "")[:50]
    filename = f"{slug}.html"
    filepath = BLOG_POSTS_DIR / filename
    full_html_content = f"""
<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>{title} - CyberPulse</title><link rel="stylesheet" href="../style.css">
<link rel="preconnect" href="[https://fonts.googleapis.com](https://fonts.googleapis.com)"><link rel="preconnect" href="[https://fonts.gstatic.com](https://fonts.gstatic.com)" crossorigin><link href="[https://fonts.googleapis.com/css2?family=Roboto+Mono:wght@400;700&display=swap](https://fonts.googleapis.com/css2?family=Roboto+Mono:wght@400;700&display=swap)" rel="stylesheet"></head>
<body><header><a href="../index.html" class="logo-link"><div class="logo">CyberPulse</div></a><p class="tagline">// The Beat of the Digital World //</p></header>
<main class="post-content">{post_html}</main>
<footer><div class="footer-links"><a href="../index.html">Home</a> | <a href="../about.html">About</a> | <a href="../privacy.html">Privacy Policy</a> | <a href="../contact.html">Contact</a></div><p>&copy; {datetime.datetime.now().year} CyberPulse. All rights reserved.</p></footer></body></html>
"""
    BLOG_POSTS_DIR.mkdir(exist_ok=True)
    filepath.write_text(full_html_content, encoding='utf-8')
    print(f"Created new post file: {filepath}")

    summary = "A new dispatch from the digital frontier. Read the full post..."
    new_entry = { "title": title, "summary": summary, "url": f"blog/{filename}", "category": category }
    current_index = []
    if BLOG_INDEX_PATH.exists():
        with open(BLOG_INDEX_PATH, 'r', encoding='utf-8') as f:
            current_index = json.load(f)
    current_index.insert(0, new_entry)
    with open(BLOG_INDEX_PATH, 'w', encoding='utf-8') as f:
        json.dump(current_index, f, indent=4)
    print(f"Updated blog index: {BLOG_INDEX_PATH}")


# --- 4. **NEW FUNCTION** to build category pages ---
def rebuild_category_pages():
    print("Rebuilding category pages...")
    if not BLOG_INDEX_PATH.exists():
        print("Blog index not found. Skipping category page build.")
        return

    with open(BLOG_INDEX_PATH, 'r', encoding='utf-8') as f:
        all_posts = json.load(f)

    categories = {}
    for post in all_posts:
        cat = post.get("category", "Tech News")
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(post)

    for category, posts in categories.items():
        category_slug = category.lower().replace(' ', '-')
        category_filename = f"category-{category_slug}.html"
        category_filepath = ROOT_DIR / category_filename
        
        posts_html = ""
        for post in posts:
            posts_html += f"""
            <a href="{post['url']}" class="post-link">
                <h2>{post['title']}</h2>
                <p>{post['summary']}</p>
            </a>
            """

        full_category_html = f"""
<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Posts in '{category}' - CyberPulse</title><link rel="stylesheet" href="style.css">
<link rel="preconnect" href="[https://fonts.googleapis.com](https://fonts.googleapis.com)"><link rel="preconnect" href="[https://fonts.gstatic.com](https://fonts.gstatic.com)" crossorigin><link href="[https://fonts.googleapis.com/css2?family=Roboto+Mono:wght@400;700&display=swap](https://fonts.googleapis.com/css2?family=Roboto+Mono:wght@400;700&display=swap)" rel="stylesheet"></head>
<body><header><a href="index.html" class="logo-link"><div class="logo">CyberPulse</div></a><p class="tagline">// The Beat of the Digital World //</p></header>
<main id="post-list-container"><h1>Category: {category}</h1>{posts_html}</main>
<footer><div class="footer-links"><a href="index.html">Home</a> | <a href="about.html">About</a> | <a href="privacy.html">Privacy Policy</a> | <a href="contact.html">Contact</a></div><p>&copy; {datetime.datetime.now().year} CyberPulse. All rights reserved.</p></footer></body></html>
"""
        category_filepath.write_text(full_category_html, encoding='utf-8')
        print(f"Built category page: {category_filepath}")


# --- Main Execution ---
if __name__ == "__main__":
    if not API_KEY:
        print("Error: GEMINI_API_KEY not found. Skipping post generation.")
    else:
        latest_article_data = get_latest_article()
        if latest_article_data:
            generated_data = generate_blog_post(latest_article_data)
            if generated_data:
                create_new_post_files(generated_data)
                rebuild_category_pages() # Run the new function
        else:
            print("No new articles found to process.")