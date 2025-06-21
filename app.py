from flask import Flask, request, render_template_string
import requests
from bs4 import BeautifulSoup

app = Flask(__name__)

TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>HT Article Reader</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <!-- Bootstrap 5 & Google Fonts -->
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700&family=Merriweather:wght@700&display=swap" rel="stylesheet">
    <style>
        body {
            background: #f2f2f2;
            font-family: 'Inter', Arial, sans-serif;
            color: #222;
        }
        .reader-container {
            max-width: 760px;
            margin: 48px auto 40px auto;
            background: #fff;
            border-radius: 14px;
            box-shadow: 0 8px 40px #cbd0d8a3;
            padding: 40px 26px 48px 26px;
        }
        .ht-title {
            font-family: 'Merriweather', serif;
            font-size: 2.3rem;
            font-weight: 700;
            color: #23272f;
            margin-bottom: 10px;
            line-height: 1.2;
        }
        .ht-subtitle {
            font-family: 'Inter', sans-serif;
            font-size: 1.25rem;
            color: #666;
            margin-bottom: 24px;
        }
        .ht-meta {
            font-size: 1rem;
            color: #8a91a5;
            margin-bottom: 28px;
        }
        .article-body {
            font-family: 'Inter', sans-serif;
            font-size: 1.15rem;
            line-height: 1.8;
            color: #242424;
            margin-top: 18px;
        }
        .article-body p {
            margin-bottom: 1.6em;
        }
        .article-body img, .article-body figure img {
            max-width: 100%;
            border-radius: 8px;
            margin: 1.5em 0 0.5em 0;
            box-shadow: 0 2px 12px #cbd0d86f;
        }
        .article-body figure {
            margin: 2.5em auto 2.5em auto;
            text-align: center;
        }
        .article-body figcaption {
            font-size: 1rem;
            color: #888;
            margin-top: 0.6em;
        }
        .premium {
            background: #fffbe8;
            border-left: 4px solid #ffe066;
            padding: 14px 20px;
            border-radius: 8px;
            margin-bottom: 1.5em;
        }
        .ht-form {
            background: #f8fafc;
            border-radius: 8px;
            box-shadow: 0 1px 7px #e2e6ed6c;
            padding: 20px 16px 16px 16px;
            margin-bottom: 30px;
        }
        @media (max-width: 600px) {
            .reader-container { padding: 17px 2vw 30px 2vw;}
            .ht-title { font-size: 1.25rem;}
        }
    </style>
</head>
<body>
    <div class="reader-container">
        <div class="ht-form mb-4">
            <form method="post" class="row g-2">
                <div class="col-12 col-md-9">
                    <input type="text" name="url" class="form-control" placeholder="Paste Hindustan Times article URL here" required value="{{ url or '' }}">
                </div>
                <div class="col-12 col-md-3 d-grid">
                    <button class="btn btn-dark" type="submit">Show Article</button>
                </div>
            </form>
            {% if error %}
                <div class="alert alert-danger mt-3 mb-0">{{ error }}</div>
            {% endif %}
        </div>
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
    headline_html = f'<div class="ht-title">{headline.get_text(strip=True)}</div>' if headline else ""

    # Subheadline
    subheadline = soup.find("h2")
    subheadline_html = f'<div class="ht-subtitle">{subheadline.get_text(strip=True)}</div>' if subheadline else ""

    # Author/date
    author, date = "", ""
    author_div = soup.select_one(".storyBy .economistName")
    if author_div:
        author = author_div.get_text(strip=True)
    date_div = soup.select_one(".actionDiv .dateTime") or soup.select_one(".storyBy .dateTime")
    if date_div:
        date = date_div.get_text(strip=True)
    author_date_html = ""
    if author or date:
        author_date_html = f'<div class="ht-meta">'
        if author: author_date_html += f'By {author}'
        if author and date: author_date_html += ' &nbsp;|&nbsp; '
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
    seen = set()
    for child in content_div.children:
        if getattr(child, 'name', None) in ['p', 'figure', 'blockquote']:
            key = str(child)
            if key in seen:
                continue
            seen.add(key)
            # Mark paywall/premium paragraphs for highlight
            classes = child.get("class") or []
            if "paywall" in classes or "premium" in classes:
                article_body += f'<div class="premium">{str(child)}</div>'
            else:
                article_body += str(child)
        elif getattr(child, 'name', None) == 'div' and 'paywall' in (child.get("class") or []):
            for sub in child.find_all(['p', 'figure', 'blockquote'], recursive=False):
                key = str(sub)
                if key in seen:
                    continue
                seen.add(key)
                article_body += f'<div class="premium">{str(sub)}</div>'
        elif getattr(child, 'name', None) == 'div' and 'storyParagraphFigure' in (child.get("class") or []):
            for sub in child.find_all(['figure', 'img'], recursive=False):
                key = str(sub)
                if key in seen:
                    continue
                seen.add(key)
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
    port = int(os.environ.get("PORT", 5000))  # Default to 5000 locally
    app.run(debug=True, host="0.0.0.0", port=port)
