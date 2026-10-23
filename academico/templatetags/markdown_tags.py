import re
from html import escape
from django import template
from django.utils.safestring import mark_safe

register = template.Library()


def _inline(text):
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", text)
    return text


@register.filter
def render_markdown(value):
    """Small escaped Markdown renderer for headings, paragraphs, lists, quotes and code."""
    lines = str(value or "").splitlines()
    out, paragraph, list_kind, code = [], [], None, False

    def flush_paragraph():
        if paragraph:
            out.append("<p>" + _inline(" ".join(paragraph)) + "</p>")
            paragraph.clear()

    def close_list():
        nonlocal list_kind
        if list_kind:
            out.append(f"</{list_kind}>")
            list_kind = None

    for raw in lines:
        line = raw.strip()
        if line.startswith("```"):
            flush_paragraph(); close_list()
            if code:
                out.append("</code></pre>")
            else:
                out.append("<pre><code>")
            code = not code
            continue
        if code:
            out.append(escape(raw) + "\n")
            continue
        if not line:
            flush_paragraph(); close_list(); continue
        heading = re.match(r"^(#{1,4})\s+(.+)$", line)
        if heading:
            flush_paragraph(); close_list()
            level = len(heading.group(1))
            out.append(f"<h{level}>{_inline(escape(heading.group(2)))}</h{level}>")
            continue
        bullet = re.match(r"^\s*[-*+]\s+(.+)$", raw)
        numbered = re.match(r"^\s*\d+[.)]\s+(.+)$", raw)
        if bullet or numbered:
            flush_paragraph()
            kind = "ul" if bullet else "ol"
            if list_kind != kind:
                close_list(); out.append(f"<{kind}>"); list_kind = kind
            out.append("<li>" + _inline(escape((bullet or numbered).group(1))) + "</li>")
            continue
        quote = re.match(r"^>\s?(.*)$", line)
        if quote:
            flush_paragraph(); close_list()
            out.append("<blockquote>" + _inline(escape(quote.group(1))) + "</blockquote>")
            continue
        close_list()
        paragraph.append(escape(line))
    flush_paragraph(); close_list()
    if code:
        out.append("</code></pre>")
    return mark_safe("\n".join(out))
