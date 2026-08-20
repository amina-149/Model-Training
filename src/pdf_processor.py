import pymupdf
import os


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


def extract_figures(pdf_path, output_dir="outputs/figures"):
    """
    Extract images embedded in the PDF.
    """

    document = pymupdf.open(pdf_path)

    os.makedirs(output_dir, exist_ok=True)

    figures = []

    for page_number, page in enumerate(document, start=1):

        images = page.get_images(full=True)

        for image_number, image in enumerate(images, start=1):

            xref = image[0]

            image_data = document.extract_image(xref)

            image_bytes = image_data["image"]
            image_ext = image_data["ext"]

            file_name = (
                f"page_{page_number}_image_{image_number}.{image_ext}"
            )

            output_path = os.path.join(output_dir, file_name)

            with open(output_path, "wb") as image_file:
                image_file.write(image_bytes)

            figures.append(output_path)

    document.close()

    return figures
