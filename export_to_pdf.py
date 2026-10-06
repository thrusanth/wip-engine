#!/usr/bin/env python3
"""
Export an article-summary Markdown file to a styled PDF using ReportLab.

Usage:
    python3 export_to_pdf.py
    python3 export_to_pdf.py --input article_summary.md --output inventory_phantoms.pdf

Dependencies (install once):
    pip install reportlab

Optional: create ``article_summary.md`` in the repo root (or pass ``--input``).
Supports common Markdown: # headings, paragraphs, - bullets, fenced ``` code blocks,
and **bold** / `inline code` in body text.
"""

from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path
from typing import Iterator

try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        ListFlowable,
        ListItem,
        Paragraph,
        Preformatted,
        SimpleDocTemplate,
        Spacer,
    )
except ImportError as exc:  # pragma: no cover - user-facing install hint
    print(
        "ReportLab is required. Install with:\n\n    pip install reportlab\n",
        file=sys.stderr,
    )
    raise SystemExit(1) from exc

DEFAULT_INPUT = Path(__file__).resolve().parent / "article_summary.md"
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "inventory_phantoms_article.pdf"

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
BULLET_RE = re.compile(r"^(\s*)[-*+]\s+(.*)$")
FENCE_RE = re.compile(r"^```(\w*)?\s*$")


def _inline_md_to_reportlab(text: str) -> str:
    """Minimal inline Markdown → ReportLab Paragraph XML."""
    escaped = html.escape(text)
    escaped = re.sub(r"`([^`]+)`", r'<font face="Courier">\1</font>', escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", escaped)
    escaped = re.sub(r"\*([^*]+)\*", r"<i>\1</i>", escaped)
    return escaped


def _iter_blocks(lines: list[str]) -> Iterator[tuple[str, object]]:
    """Yield (block_type, content) tuples from Markdown lines."""
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if not stripped:
            index += 1
            yield ("spacer", None)
            continue

        fence = FENCE_RE.match(stripped)
        if fence:
            lang = fence.group(1) or ""
            index += 1
            code_lines: list[str] = []
            while index < len(lines) and not FENCE_RE.match(lines[index].strip()):
                code_lines.append(lines[index].rstrip("\n"))
                index += 1
            if index < len(lines):
                index += 1  # closing fence
            yield ("code", {"lang": lang, "text": "\n".join(code_lines)})
            continue

        heading = HEADING_RE.match(stripped)
        if heading:
            level = len(heading.group(1))
            yield ("heading", (level, heading.group(2).strip()))
            index += 1
            continue

        if BULLET_RE.match(line):
            bullets: list[str] = []
            while index < len(lines):
                match = BULLET_RE.match(lines[index])
                if not match:
                    break
                bullets.append(match.group(2).strip())
                index += 1
            yield ("bullets", bullets)
            continue

        para_lines = [stripped]
        index += 1
        while index < len(lines):
            nxt = lines[index].strip()
            if (
                not nxt
                or HEADING_RE.match(nxt)
                or FENCE_RE.match(nxt)
                or BULLET_RE.match(lines[index])
            ):
                break
            para_lines.append(nxt)
            index += 1
        yield ("paragraph", " ".join(para_lines))


def _build_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "ArticleTitle",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=26,
            spaceAfter=14,
            textColor=colors.HexColor("#1a1a2e"),
        ),
        "h1": ParagraphStyle(
            "H1",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=22,
            spaceBefore=16,
            spaceAfter=8,
            textColor=colors.HexColor("#16213e"),
        ),
        "h2": ParagraphStyle(
            "H2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=18,
            spaceBefore=12,
            spaceAfter=6,
            textColor=colors.HexColor("#0f3460"),
        ),
        "h3": ParagraphStyle(
            "H3",
            parent=base["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=15,
            spaceBefore=10,
            spaceAfter=4,
            textColor=colors.HexColor("#533483"),
        ),
        "body": ParagraphStyle(
            "Body",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=10.5,
            leading=14,
            alignment=TA_LEFT,
            spaceAfter=6,
            textColor=colors.HexColor("#222222"),
        ),
        "bullet": ParagraphStyle(
            "Bullet",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=10.5,
            leading=14,
            leftIndent=12,
            textColor=colors.HexColor("#222222"),
        ),
        "code_caption": ParagraphStyle(
            "CodeCaption",
            parent=base["BodyText"],
            fontName="Helvetica-Oblique",
            fontSize=8,
            textColor=colors.HexColor("#666666"),
            spaceAfter=4,
        ),
    }


def markdown_to_story(markdown_text: str) -> list:
    styles = _build_styles()
    story: list = []
    first_heading = True

    for block_type, content in _iter_blocks(markdown_text.splitlines()):
        if block_type == "spacer":
            story.append(Spacer(1, 0.12 * inch))
            continue

        if block_type == "heading":
            level, title = content
            style_key = "title" if level == 1 and first_heading else f"h{min(level, 3)}"
            if level == 1:
                first_heading = False
            story.append(Paragraph(_inline_md_to_reportlab(title), styles[style_key]))
            continue

        if block_type == "paragraph":
            story.append(Paragraph(_inline_md_to_reportlab(content), styles["body"]))
            continue

        if block_type == "bullets":
            items = [
                ListItem(Paragraph(_inline_md_to_reportlab(item), styles["bullet"]))
                for item in content
            ]
            story.append(
                ListFlowable(
                    items,
                    bulletType="bullet",
                    start="•",
                    leftIndent=18,
                    bulletFontName="Helvetica",
                    bulletFontSize=10,
                )
            )
            story.append(Spacer(1, 0.08 * inch))
            continue

        if block_type == "code":
            lang = content.get("lang") or "text"
            text = content.get("text") or ""
            if lang:
                story.append(Paragraph(f"Code ({lang}):", styles["code_caption"]))
            story.append(
                Preformatted(
                    text,
                    styles["body"],
                    maxLineLength=92,
                    newLineChars="\n",
                )
            )
            story.append(Spacer(1, 0.1 * inch))
            continue

    return story


def export_markdown_to_pdf(input_path: Path, output_path: Path) -> None:
    if not input_path.is_file():
        raise FileNotFoundError(
            f"Markdown input not found: {input_path}\n"
            "Create article_summary.md or pass --input /path/to/file.md"
        )

    markdown_text = input_path.read_text(encoding="utf-8")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        leftMargin=0.85 * inch,
        rightMargin=0.85 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        title=output_path.stem,
        author="WIP Exception Engine",
    )

    def _footer(canvas, doc_template):  # noqa: ANN001
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#888888"))
        canvas.drawString(
            doc_template.leftMargin,
            0.5 * inch,
            f"The Inventory Phantoms — {input_path.name}",
        )
        canvas.drawRightString(
            letter[0] - doc_template.rightMargin,
            0.5 * inch,
            f"Page {canvas.getPageNumber()}",
        )
        canvas.restoreState()

    story = markdown_to_story(markdown_text)
    if not story:
        story = [Paragraph("(Empty document)", _build_styles()["body"])]

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    print(f"Wrote PDF: {output_path}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compile article summary Markdown into a styled PDF (ReportLab)."
    )
    parser.add_argument(
        "--input",
        "-i",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"Source Markdown file (default: {DEFAULT_INPUT.name})",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Destination PDF (default: {DEFAULT_OUTPUT.name})",
    )
    args = parser.parse_args()

    try:
        export_markdown_to_pdf(args.input.resolve(), args.output.resolve())
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Export failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
