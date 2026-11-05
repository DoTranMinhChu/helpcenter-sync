from helpcenter_sync.markdown import article_slug, article_to_markdown, html_to_markdown
from helpcenter_sync.zendesk import Article


def _article(body: str = "<p>Hello</p>") -> Article:
    return Article(id=123, title="How to Add a YouTube Video",
                   html_url="https://support.optisigns.com/hc/en-us/articles/123-How-to-Add-a-YouTube-Video",
                   body_html=body, updated_at="2026-01-01T00:00:00Z")


def test_file_starts_with_title_and_citable_url():
    md = article_to_markdown(_article())
    assert md.startswith("# How to Add a YouTube Video\n\nArticle URL: https://support.optisigns.com/hc/")


def test_headings_code_blocks_and_lists_are_preserved():
    md = html_to_markdown("<h2>Setup</h2><ul><li>One</li></ul><pre><code>npm start</code></pre>")
    assert "## Setup" in md
    assert "- One" in md
    assert "```\nnpm start\n```" in md


def test_relative_links_are_preserved_as_authored():
    md = html_to_markdown('<p><a href="/hc/en-us/articles/9">Guide</a> <a href="#Steps">Steps</a> '
                          '<a href="https://www.optisigns.com/pricing">Pricing</a></p>')
    assert "[Guide](/hc/en-us/articles/9)" in md
    assert "[Steps](#Steps)" in md
    assert "[Pricing](https://www.optisigns.com/pricing)" in md


def test_nav_scripts_and_empty_markup_are_removed():
    html = ('<nav>Menu</nav><script>track()</script><p><span style="color:red">Text</span></p>'
            '<p>&nbsp;</p><hr><button>Vote</button>')
    assert html_to_markdown(html) == "Text"


def test_single_cell_table_becomes_callout():
    md = html_to_markdown("<table><tr><td><strong>IMPORTANT</strong></td></tr>"
                          "<tr><td><p>Back up first.</p></td></tr></table>")
    assert md.startswith("> **IMPORTANT**")
    assert "> Back up first." in md


def test_bold_first_row_becomes_table_header():
    md = html_to_markdown("<table><tbody><tr><td><strong>Country</strong></td><td><strong>Currency</strong></td></tr>"
                          "<tr><td>Canada</td><td>CAD</td></tr></tbody></table>")
    assert md.splitlines()[:3] == ["| Country | Currency |", "| --- | --- |", "| Canada | CAD |"]


def test_screenshot_only_rows_are_dropped():
    md = html_to_markdown('<table><tr><th>1.0</th><th>Updated</th></tr>'
                          '<tr><td><img src="/a.png"></td><td><img src="/b.png"></td></tr></table>')
    assert md == "| 1.0 | Updated |\n| --- | --- |"


def test_youtube_embed_becomes_watch_link():
    md = html_to_markdown('<iframe src="https://www.youtube.com/embed/abc123?rel=0"></iframe>')
    assert "[Watch the video](https://www.youtube.com/watch?v=abc123)" in md


def test_slug_comes_from_url_without_id():
    assert article_slug(_article()) == "how-to-add-a-youtube-video"
