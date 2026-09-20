"""
Copyright (c) 2013-present Matic Kukovec.
Released under the GNU GPL3 license.

For more information check the 'LICENSE.txt' file.
For complete license information of the dependencies, check the 'additional_licenses' directory.
"""

##  FILE DESCRIPTION:
##      Converts Markdown text to a self-contained HTML page
##      using the 'markdown' and 'pygments' libraries.

import html
import os
import re
from typing import Optional


def render(text: str, title: Optional[str] = None) -> str:
    """Render *text* as a self-contained GitHub-flavoured HTML page."""
    import markdown
    import pygments.formatters

    body = markdown.markdown(
        text,
        extensions=[
            "extra",
            "toc",
            "sane_lists",
            "codehilite",
        ],
        output_format="html",
    )

    formatter = pygments.formatters.HtmlFormatter(
        noclasses=True,
        wrapcode=True,
    )
    pyg_css = formatter.get_style_defs(".codehilite")

    safe_title = html.escape(title) if title else "Markdown Preview"
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        "<title>{title}</title>\n"
        "<style>\n"
        "body {{\n"
        '  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;\n'
        "  line-height: 1.6;\n"
        "  max-width: 52em;\n"
        "  margin: 2em auto;\n"
        "  padding: 0 1em;\n"
        "  color: #24292e;\n"
        "  background: #fff;\n"
        "}}\n"
        "h1, h2, h3, h4, h5, h6 {{ margin-top: 1.5em; margin-bottom: 0.5em; font-weight: 600; }}\n"
        "h1 {{ font-size: 2em; border-bottom: 1px solid #eaecef; padding-bottom: 0.3em; }}\n"
        "h2 {{ font-size: 1.5em; border-bottom: 1px solid #eaecef; padding-bottom: 0.3em; }}\n"
        "code {{ background: #f6f8fa; padding: 0.2em 0.4em; border-radius: 3px; font-size: 85%; }}\n"
        "pre {{ background: #f6f8fa; padding: 1em; overflow-x: auto; border-radius: 6px; }}\n"
        "pre code {{ background: none; padding: 0; font-size: 100%; }}\n"
        "table {{ border-collapse: collapse; width: 100%; margin: 1em 0; }}\n"
        "th, td {{ border: 1px solid #dfe2e5; padding: 6px 13px; }}\n"
        "th {{ background: #f6f8fa; font-weight: 600; }}\n"
        "tr:nth-child(2n) {{ background: #f6f8fa; }}\n"
        "blockquote {{ border-left: 4px solid #dfe2e5; margin: 1em 0; padding: 0 1em; color: #6a737d; }}\n"
        "a {{ color: #0366d6; text-decoration: none; }}\n"
        "a:hover {{ text-decoration: underline; }}\n"
        "img {{ max-width: 100%; }}\n"
        "hr {{ border: none; border-top: 2px solid #eaecef; margin: 2em 0; }}\n"
        "ul.task-list {{ list-style: none; padding-left: 1.5em; }}\n"
        "ul.task-list li {{ position: relative; padding-left: 0.5em; }}\n"
        "ul.task-list li input[type=checkbox] {{ position: absolute; left: -1.5em; }}\n"
        "{pyg_css}\n"
        ".codehilite {{ background: #f6f8fa; border-radius: 6px; padding: 1em; overflow-x: auto; }}\n"
        "</style>\n"
        "</head>\n"
        "<body>\n"
        "{body}\n"
        "</body>\n"
        "</html>\n"
    ).format(title=safe_title, pyg_css=pyg_css, body=body)


def absolutize_links(html_text: str, base_dir: str) -> str:
    """Turn relative ``src`` and ``href`` values into absolute ``file:///`` URLs."""

    def _abs(m: re.Match) -> str:
        attr = m.group(1)
        url = m.group(2)
        if url.startswith(
            ("http://", "https://", "mailto:", "#", "data:", "file:///")
        ) or url.startswith(("javascript:",)):
            return m.group(0)
        # Don't absolutize if already absolute
        if os.path.isabs(url):
            abs_url = "file:///{}".format(url.replace("\\", "/"))
        else:
            joined = os.path.normpath(os.path.join(base_dir, url))
            abs_url = "file:///{}".format(joined.replace("\\", "/"))
        return '{}="{}"'.format(attr, abs_url)

    return re.sub(r'((?:src|href)=")([^"]*)"', _abs, html_text)
