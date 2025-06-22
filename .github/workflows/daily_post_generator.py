import os
import feedparser
import google.generativeai as genai
import datetime
import json
from pathlib import Path

# --- Configuration ---
RSS_FEEDS = [
    'https://techcrunch.com/feed/',
    'https://www.wired.com/feed/category/technology/latest/rss',
    'https://www.reuters.com/pf/api/v2/content/assets/v1/collection/id/43664/feed/rss/'
]
API_KEY = os.getenv('GEMINI_API_KEY')
BLOG_INDEX_PATH = Path("blog-index.json")
BLOG_POSTS_DIR = Path("blog")

# --- 1. Configure the AI ---
genai.configure(api_key=API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# --- 2. Fetch latest news from RSS feeds ---
def get_latest_article():
    print("Fetching articles from RSS feeds...")
    latest_article = None
    latest_pub_date = None

    for feed_url in RSS_FEEDS:
        feed = feedparser.parse(feed_url)
        for entry in feed.entries:
            pub_date = entry.get('published_parsed') or entry.get('updated_parsed')
            if pub_date:
                # Convert to aware datetime object
                current_article_date = datetime.datetime(*pub_date[:6], tzinfo=datetime.timezone.utc)
                if latest_pub_date is None or current_article_date > latest_pub_date:
                    latest_pub_date = current_article_date
                    latest_article = entry
    
    if latest_article:
        print(f"Found latest article: '{latest_article.title}'")
        return { "title": latest_article.title, "summary": latest_article.summary, "link": latest_article.link }
    else:
        print("No articles found.")
        return None

# --- 3. Use AI to generate a new blog post ---
def generate_blog_post(article):
    print("Generating new blog post with AI...")
    prompt = f"""
    Act as a tech blogger for a website called 'CyberPulse'. Your tone is sharp, futuristic, and insightful.
    Based on the following news article, write a new, original blog post of about 300-400 words.
    
    Do NOT copy sentences from the original article. Create a new take on the subject.
    Start the blog post with a compelling H1 title.
    
    At the end of the post, include a short, bolded "Source:" line with a link to the original article.

    Original Article Title: {article['title']}
    Original Article Summary: {article['summary']}
    Original Article Link: {article['link']}

    Your response should be only the HTML content for the blog post, starting with the <h1> title.
    """
    
    response = model.generate_content(prompt)
    return response.text

# --- 4. Create the new HTML and update the JSON index ---
def create_new_post_files(post_html):
    print("Creating new post files...")
    
    # Extract H1 title for filename and JSON
    from xml.etree import ElementTree as ET
    try:
        # Wrap in a root element to parse
        root = ET.fromstring(f"<root>{post_html}</root>")
        h1_element = root.find('h1')
        if h1_element is not None:
            title = h1_element.text
        else:
            raise ValueError("No H1 tag found")
    except Exception as e:
        print(f"Could not parse title from HTML, using default. Error: {e}")
        title = "New CyberPulse Post"

    # Create a safe filename
    slug = title.lower().replace(' ', '-').replace('?', '').replace(':', '').replace("'", "")[:50]
    filename = f"{slug}.html"
    filepath = BLOG_POSTS_DIR / filename
    
    # Create the full HTML page for the post
    full_html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - CyberPulse</title>
    <link rel="stylesheet" href="../style.css">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Roboto+Mono:wght@400;700&display=swap" rel="stylesheet">
</head>
<body>
    <header>
        <a href="../index.html" class="logo-link"><div class="logo">CyberPulse</div></a>
        <p class="tagline">// The Beat of the Digital World //</p>
    </header>
    <main class="post-content">
        {post_html}
    </main>
    <footer>
        <p>&copy; {datetime.datetime.now().year} CyberPulse. All rights reserved.</p>
    </footer>
</body>
</html>
"""
    # Write the new blog post HTML file
    BLOG_POSTS_DIR.mkdir(exist_ok=True)
    filepath.write_text(full_html_content, encoding='utf-8')
    print(f"Created new post file: {filepath}")

    # Update the JSON index
    summary = "A new dispatch from the digital frontier. Read the full post..."
    new_entry = {
        "title": title,
        "summary": summary,
        "url": f"blog/{filename}"
    }
    
    current_index = []
    if BLOG_INDEX_PATH.exists():
        with open(BLOG_INDEX_PATH, 'r', encoding='utf-8') as f:
            current_index = json.load(f)
    
    # Add new entry to the top of the list
    current_index.insert(0, new_entry)
    
    with open(BLOG_INDEX_PATH, 'w', encoding='utf-8') as f:
        json.dump(current_index, f, indent=4)
    print(f"Updated blog index: {BLOG_INDEX_PATH}")


# --- Main Execution ---
if __name__ == "__main__":
    latest_article_data = get_latest_article()
    if latest_article_data and API_KEY:
        generated_html = generate_blog_post(latest_article_data)
        create_new_post_files(generated_html)
    else:
        print("Skipping post generation due to missing article or API key.")