from flask import Flask, request, render_template_string
import requests
from bs4 import BeautifulSoup

app = Flask(__name__)

TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Hindustan Times Article Viewer</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <!-- Bootstrap 5 CDN -->
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background: #f8f9fa; }
        .container { max-width: 760px; margin-top: 40px; margin-bottom: 40px; background: #fff; border-radius: 10px; box-shadow: 0 0 12px #ddd; padding: 30px 26px; }
        .article-title { font-size: 2rem; font-weight: 700; margin-bottom: 10px;}
        .article-subtitle { font-size:1.25rem; color: #555; margin-bottom:20px;}
        .author-date { font-size:1rem; color: #888; margin-bottom: 30px;}
        .article-body p { font-size: 1.15rem; margin: 1.2em 0; line-height: 1.7;}
        .article-body img { max-width: 100%; display: block; margin: 20px auto; border-radius: 7px;}
        .article-body figure { margin: 1.5em 0; text-align: center;}
        .article-body figcaption { font-size: 0.98rem; color: #666; margin-top: 5px;}
        .premium {background: #fff3cd; border-left: 5px solid #ffe066; padding: 10px 18px;}
        .form-control {font-size: 1.1rem;}
        .btn-primary {font-size: 1.1rem;}
        @media (max-width: 600px) {
            .container {padding: 16px 4vw;}
            .article-title { font-size: 1.25rem;}
        }
    </style>
</head>
<body>
    <div class="container">
        <h2 class="mb-4">Hindustan Times Article Viewer</h2>
        <form method="post" class="row g-2 mb-4">
            <div class="col-9 col-sm-10">
                <input type="text" name="url" class="form-control" placeholder="Paste Hindustan Times article URL here" required value="{{ url or '' }}">
            </div>
            <div class="col-3 col-sm-2">
                <button class="btn btn-primary w-100" type="submit">Show Article</button>
            </div>
        </form>
        {% if error %}
            <div class="alert alert-danger">{{ error }}</div>
        {% endif %}
        {% if article %}
            {{ article|safe }}
        {% endif %}
    </div>
</body>
</html>
"""

def extract_full_article(html):
    soup = BeautifulSoup(html, "html.parser")
    # Headline
    headline = soup.find("h1")
    headline_html = f'<div class="article-title">{headline.get_text(strip=True)}</div>' if headline else ""

    # Subheadline
    subheadline = soup.find("h2")
    subheadline_html = f'<div class="article-subtitle">{subheadline.get_text(strip=True)}</div>' if subheadline else ""

    # Author/date (try to find in known places)
    author, date = "", ""
    author_div = soup.select_one(".storyBy .economistName")
    if author_div:
        author = author_div.get_text(strip=True)
    date_div = soup.select_one(".actionDiv .dateTime") or soup.select_one(".storyBy .dateTime")
    if date_div:
        date = date_div.get_text(strip=True)
    author_date_html = ""
    if author or date:
        author_date_html = f'<div class="author-date">'
        if author: author_date_html += f'By {author}'
        if author and date: author_date_html += ' | '
        if date: author_date_html += date
        author_date_html += '</div>'

    # Main article content (including paywall)
    content_div = soup.select_one("div.storyDetails div.detail")
    if not content_div:
        return "<div class='alert alert-warning'>Article content not found.</div>"

    # Remove ads, share, unrelated
    for unwanted in content_div.select(
        ".adMinHeight313, .storyAd, .shareArticle, .relatedStoryCricket, .relatedStory2, .us-ad, .saranyuPlayer, script, style, .trendTops, .trendInlineSeo, .bottomSeoParaEcho, .bottomBreadCrumb, input"
    ):
        unwanted.decompose()

    # Gather all <p>, <figure>, <blockquote> (including inside .paywall and outside)
    article_body = ""
    # To avoid duplicates, only render direct children of content_div, and also anything inside .paywall
    # Render in the order they appear
    for child in content_div.children:
        if getattr(child, 'name', None) in ['p', 'figure', 'blockquote']:
            # Mark paywall/premium paragraphs for highlight
            classes = child.get("class") or []
            if "paywall" in classes or "premium" in classes:
                article_body += f'<div class="premium">{str(child)}</div>'
            else:
                article_body += str(child)
        elif getattr(child, 'name', None) == 'div' and 'paywall' in (child.get("class") or []):
            # Render all paragraphs inside paywall div
            for sub in child.find_all(['p', 'figure', 'blockquote'], recursive=False):
                article_body += f'<div class="premium">{str(sub)}</div>'
        # Also check for image/figure containers outside paywall
        elif getattr(child, 'name', None) == 'div' and 'storyParagraphFigure' in (child.get("class") or []):
            for sub in child.find_all(['figure', 'img'], recursive=False):
                article_body += str(sub)

    # Clean up: Remove empty <p> and <div> tags
    soup2 = BeautifulSoup(article_body, "html.parser")
    for tag in soup2.find_all(['p','div']):
        if not tag.get_text(strip=True) and not tag.find('img'):
            tag.decompose()
    article_body = str(soup2)

    # Final HTML
    return f"""
    {headline_html}
    {subheadline_html}
    {author_date_html}
    <div class="article-body">{article_body}</div>
    """

@app.route("/", methods=["GET", "POST"])
def index():
    article, error, url = None, None, None
    if request.method == "POST":
        url = request.form.get("url")
        if not url.startswith("http"):
            error = "Please enter a valid URL."
        else:
            try:
                resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
                if "hindustantimes.com" not in url.lower():
                    error = "Only Hindustan Times URLs are supported."
                elif resp.status_code != 200:
                    error = f"Failed to fetch article (status code {resp.status_code})"
                else:
                    article = extract_full_article(resp.text)
            except Exception as e:
                error = f"Error: {e}"
    return render_template_string(TEMPLATE, article=article, error=error, url=url)

if __name__ == "__main__":
    app.run(debug=True)