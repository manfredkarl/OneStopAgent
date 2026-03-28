"""PowerPoint generation service using python-pptx."""

import os
import uuid
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor


OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")


def create_pptx(slides: list[dict], customer_name: str = "Customer") -> str:
    """Create a PPTX file from structured slide data. Returns the file path."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    prs = Presentation()
    prs.slide_width = Inches(13.333)  # 16:9
    prs.slide_height = Inches(7.5)

    for slide_data in slides:
        slide_type = slide_data.get("type", "content")

        if slide_type == "title":
            _add_title_slide(prs, slide_data)
        elif slide_type == "table":
            _add_table_slide(prs, slide_data)
        else:
            _add_content_slide(prs, slide_data)

    filename = f"OneStopAgent-{customer_name.replace(' ', '_')}-{uuid.uuid4().hex[:8]}.pptx"
    filepath = os.path.join(OUTPUT_DIR, filename)
    prs.save(filepath)
    return filepath


def _add_title_slide(prs, data):
    slide = prs.slides.add_slide(prs.slide_layouts[0])  # Title layout
    slide.shapes.title.text = data.get("title", "")
    if slide.placeholders[1]:
        slide.placeholders[1].text = data.get("subtitle", "")


def _add_content_slide(prs, data):
    slide = prs.slides.add_slide(prs.slide_layouts[1])  # Title + content
    slide.shapes.title.text = data.get("title", "")
    body = slide.placeholders[1].text_frame
    body.clear()

    text = data.get("body", "")
    for i, line in enumerate(text.split("\n")):
        if i == 0:
            body.paragraphs[0].text = line.strip()
            body.paragraphs[0].font.size = Pt(14)
        else:
            p = body.add_paragraph()
            p.text = line.strip()
            p.font.size = Pt(14)

    # Add speaker notes
    notes = data.get("notes", "")
    if notes:
        notes_slide = slide.notes_slide
        notes_slide.notes_text_frame.text = notes


def _add_table_slide(prs, data):
    slide = prs.slides.add_slide(prs.slide_layouts[5])  # Blank layout

    # Add title
    txBox = slide.shapes.add_textbox(Inches(0.5), Inches(0.3), Inches(12), Inches(0.8))
    tf = txBox.text_frame
    tf.text = data.get("title", "")
    tf.paragraphs[0].font.size = Pt(24)
    tf.paragraphs[0].font.bold = True
    tf.paragraphs[0].font.color.rgb = RGBColor(0x0F, 0x6C, 0xBD)

    headers = data.get("headers", [])
    rows = data.get("rows", [])

    if not headers or not rows:
        return

    n_cols = len(headers)
    n_rows = len(rows) + 1  # +1 for header

    table_shape = slide.shapes.add_table(
        n_rows, n_cols,
        Inches(0.5), Inches(1.3),
        Inches(12), Inches(min(n_rows * 0.4, 5.5))
    )
    table = table_shape.table

    # Header row
    for j, h in enumerate(headers):
        cell = table.cell(0, j)
        cell.text = h
        for paragraph in cell.text_frame.paragraphs:
            paragraph.font.size = Pt(11)
            paragraph.font.bold = True

    # Data rows
    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            cell = table.cell(i + 1, j)
            cell.text = str(val)
            for paragraph in cell.text_frame.paragraphs:
                paragraph.font.size = Pt(10)

    # Footer
    footer = data.get("footer", "")
    if footer:
        txBox2 = slide.shapes.add_textbox(Inches(0.5), Inches(6.8), Inches(12), Inches(0.5))
        tf2 = txBox2.text_frame
        tf2.text = footer
        tf2.paragraphs[0].font.size = Pt(9)
        tf2.paragraphs[0].font.italic = True
