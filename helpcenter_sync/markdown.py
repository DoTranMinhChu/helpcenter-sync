import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag
from markdownify import MarkdownConverter

from helpcenter_sync.zendesk import Article

REMOVE_TAGS = ("script", "style", "noscript", "nav", "header", "footer", "form", "button", "svg", "hr")
UNWRAP_TAGS = ("span", "font", "u", "colgroup", "col", "article", "section", "figure")
HEADINGS = ("h1", "h2", "h3", "h4", "h5", "h6")


def _video_url(src: str) -> str:
    parsed = urlparse(src)
    if "youtube" in parsed.netloc and parsed.path.startswith("/embed/"):
        return f"https://www.youtube.com/watch?v={parsed.path.split('/')[2]}"
    return src


def _is_callout_table(table: Tag) -> bool:
    rows = table.find_all("tr")
    return bool(rows) and all(len(r.find_all(["td", "th"], recursive=False)) == 1 for r in rows)


def clean_html(html: str) -> BeautifulSoup:
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup.find_all(REMOVE_TAGS):
        tag.decompose()
    for tag in soup.find_all(UNWRAP_TAGS):
        tag.unwrap()

    for iframe in soup.find_all("iframe"):
        src = iframe.get("src", "")
        if not src:
            iframe.decompose()
            continue
        link = soup.new_tag("a", href=_video_url("https:" + src if src.startswith("//") else src))
        link.string = "Watch the video"
        p = soup.new_tag("p")
        p.append(link)
        iframe.replace_with(p)

    # Links are kept exactly as authored (relative ones stay relative); only href-less anchors go.
    for a in soup.find_all("a"):
        if not (a.get("href") or "").strip():
            a.unwrap()
    for img in soup.find_all("img"):
        if not (img.get("src") or "").strip():
            img.decompose()

    for table in soup.find_all("table"):
        # Zendesk's single-cell tables are "IMPORTANT"/"NOTE" boxes, not data.
        if _is_callout_table(table):
            quote = soup.new_tag("blockquote")
            for cell in table.find_all(["td", "th"]):
                quote.extend(list(cell.contents))
            table.replace_with(quote)
            continue
        # Screenshot-comparison tables leave empty rows once images can't sit in a Markdown cell.
        for img in table.find_all("img"):
            img.decompose()
        for row in table.find_all("tr"):
            if not row.get_text(strip=True):
                row.decompose()
        first_row = table.find("tr")
        if first_row is None:
            table.decompose()
        elif not table.find("th"):
            # Authors bold the first row instead of using <th>; without this Markdown gets an empty header.
            for cell in first_row.find_all("td", recursive=False):
                cell.name = "th"

    for tag in soup.find_all(["th", *HEADINGS]):
        for bold in tag.find_all(["strong", "b"]):
            bold.unwrap()

    for p in soup.find_all("p"):
        if not p.get_text(strip=True) and not p.find("img"):
            p.decompose()

    return soup


def _tidy(markdown: str) -> str:
    markdown = markdown.replace("\xa0", " ").replace("​", "")
    markdown = re.sub(r"[ \t]+\n", "\n", markdown)
    markdown = re.sub(r"\n{3,}", "\n\n", markdown)
    return markdown.strip()


def html_to_markdown(html: str) -> str:
    converter = MarkdownConverter(heading_style="ATX", bullets="-",
                                  escape_underscores=False, escape_asterisks=False)
    return _tidy(converter.convert_soup(clean_html(html)))


def article_to_markdown(article: Article) -> str:
    return f"# {article.title}\n\nArticle URL: {article.html_url}\n\n{html_to_markdown(article.body_html)}\n"


def article_slug(article: Article) -> str:
    tail = article.html_url.rstrip("/").rsplit("/", 1)[-1]
    slug = re.sub(r"^\d+-", "", tail).lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
    return slug or str(article.id)
