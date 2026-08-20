import pymupdf
import os
import re


def extract_text_from_pdf(pdf_path):
    """
    Extract all text from a PDF file.
    """

    document = pymupdf.open(pdf_path)

    text = ""

    for page in document:
        text += page.get_text()

    document.close()

    return text


def extract_pdf_metadata(pdf_path):
    """
    Extract basic metadata from a PDF.
    """

    document = pymupdf.open(pdf_path)

    file_size = os.path.getsize(pdf_path)

    metadata = {
        "file_name": os.path.basename(pdf_path),
        "file_size": f"{file_size / 1024:.2f} KB",
        "file_type": "PDF",
        "pages": len(document),
        "title": document.metadata.get("title") or "Not available",
        "authors": document.metadata.get("author") or "Not available"
    }

    document.close()

    return metadata


CAPTION_PATTERN = re.compile(
    r"((?:Fig(?:ure)?|Table|Chart|Graph|Plate|Map)\.?\s*\d+[:.\-]?\s*[^\n]*)",
    re.IGNORECASE
)

MIN_IMAGE_DIMENSION = 80


def _find_caption_near(page_text, rect, page):
    """
    Find the figure/table caption line closest to the image's
    bounding box on the page (captions are usually just below,
    sometimes above, the image).
    """

    blocks = page.get_text("blocks")

    candidates = []

    for block in blocks:

        x0, y0, x1, y1, text = block[0], block[1], block[2], block[3], block[4]

        match = CAPTION_PATTERN.search(text)

        if not match:
            continue

        distance = min(
            abs(y0 - rect.y1),
            abs(rect.y0 - y1)
        )

        candidates.append((distance, match.group(1).strip()))

    if candidates:
        candidates.sort(key=lambda item: item[0])
        return candidates[0][1]

    match = CAPTION_PATTERN.search(page_text or "")

    if match:
        return match.group(1).strip()

    return "NOT_REPORTED"


def _visual_label_type_from_caption(caption):

    match = re.match(
        r"\s*(Fig(?:ure)?|Table|Chart|Graph|Plate|Map)",
        caption or "",
        re.IGNORECASE
    )

    if not match:
        return "UNKNOWN"

    word = match.group(1).upper()

    if word.startswith("FIG"):
        return "FIG"

    return word


def extract_figures(pdf_path, output_dir="outputs/figures"):
    """
    Extract images embedded in the PDF, paired with the paper
    text/caption evidence each image needs to be labeled.
    """

    document = pymupdf.open(pdf_path)

    os.makedirs(output_dir, exist_ok=True)

    page_texts = [page.get_text() for page in document]

    full_paper_text = "\n".join(page_texts)

    figures = []

    figure_number = 0

    for page_index, page in enumerate(document):

        page_number = page_index + 1

        page_text = page_texts[page_index]

        images = page.get_images(full=True)

        for image_number, image in enumerate(images, start=1):

            xref = image[0]

            image_data = document.extract_image(xref)

            image_bytes = image_data["image"]
            image_ext = image_data["ext"]
            image_width = image_data.get("width", 0)
            image_height = image_data.get("height", 0)

            if (
                image_width < MIN_IMAGE_DIMENSION
                or image_height < MIN_IMAGE_DIMENSION
            ):
                # Skip tiny images (logos, icons, decorative rules)
                continue

            figure_number += 1

            file_name = (
                f"page_{page_number}_image_{image_number}.{image_ext}"
            )

            output_path = os.path.join(output_dir, file_name)

            with open(output_path, "wb") as image_file:
                image_file.write(image_bytes)

            rects = page.get_image_rects(xref)
            rect = rects[0] if rects else pymupdf.Rect(0, 0, 0, 0)

            caption = _find_caption_near(page_text, rect, page)

            context_start = max(0, page_text.find(caption[:30]) - 500) \
                if caption != "NOT_REPORTED" else 0

            context = page_text[context_start:context_start + 1500]

            figures.append({
                "image_path": output_path,
                "figure_number": figure_number,
                "page_number": page_number,
                "caption": caption,
                "context": context if context else "NOT_REPORTED",
                "page_text": page_text,
                "full_paper_text": full_paper_text,
                "visual_label_type": _visual_label_type_from_caption(caption)
            })

    document.close()

    return figures
