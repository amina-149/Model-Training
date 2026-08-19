import pymupdf
from pathlib import Path
import re


# ============================================================
# CAPTION EXTRACTION
# ============================================================

def extract_figure_caption(
    page_text,
    figure_number
):
    """
    Extract the original visual caption from page text.

    Supports:
        Figure 1
        Fig. 1
        Fig 1
        Table 1
        Graph 1
        Chart 1
        Map 1
        Diagram 1
        Plate 1

    The extractor does not classify the visual type.
    """

    if not page_text:
        return "NOT_REPORTED"

    visual_labels = (
        r"(?:"
        r"Fig\.?"
        r"|Figure"
        r"|Table"
        r"|Graph"
        r"|Chart"
        r"|Map"
        r"|Diagram"
        r"|Plate"
        r")"
    )

    pattern = rf"""
        {visual_labels}
        \s*
        {re.escape(str(figure_number))}
        \s*
        [\.\:\-]?
        \s*
        (.+?)
        (?=
            \n\s*
            {visual_labels}
            \s*\d+
            |
            \Z
        )
    """

    match = re.search(
        pattern,
        page_text,
        flags=(
            re.IGNORECASE |
            re.VERBOSE |
            re.DOTALL
        )
    )

    if match:

        caption = match.group(1).strip()

        caption = re.sub(
            r"\s+",
            " ",
            caption
        ).strip()

        if caption:
            return caption

    return "NOT_REPORTED"


# ============================================================
# FIND ORIGINAL CAPTION WITH LABEL
# ============================================================

def find_visual_caption(
    page_text,
    figure_number
):
    """
    Return the complete original caption including its label.

    Example:
        Fig. 1. Leaf spots with dark coloured pycnidia

    This is useful because the original caption itself should
    be preserved and passed to the AI analyzer.
    """

    if not page_text:
        return "NOT_REPORTED"

    visual_labels = (
        r"(?:"
        r"Fig\.?"
        r"|Figure"
        r"|Table"
        r"|Graph"
        r"|Chart"
        r"|Map"
        r"|Diagram"
        r"|Plate"
        r")"
    )

    pattern = rf"""
        {visual_labels}
        \s*
        {re.escape(str(figure_number))}
        \s*
        [\.\:\-]?
        \s*
        .+?
        (?=
            \n\s*
            {visual_labels}
            \s*\d+
            |
            \Z
        )
    """

    match = re.search(
        pattern,
        page_text,
        flags=(
            re.IGNORECASE |
            re.VERBOSE |
            re.DOTALL
        )
    )

    if match:

        caption = match.group(0).strip()

        caption = re.sub(
            r"\s+",
            " ",
            caption
        ).strip()

        if caption:
            return caption

    return "NOT_REPORTED"


# ============================================================
# VISUAL LABEL TYPE (Fig / Table / Graph / Map / Diagram ...)
# ============================================================

def detect_visual_label_type(
    page_text,
    figure_number
):
    """
    Determine which visual label (Fig./Figure, Table, Graph,
    Chart, Map, Diagram, Plate) precedes this figure number in
    the page text.

    This is deterministic, paper-supported evidence and is used
    downstream to classify VISUAL_TYPE / CV category before any
    agricultural labelling happens, so that tables/graphs/maps
    are never mistaken for crop photographs.
    """

    if not page_text:
        return "UNKNOWN"

    label_map = [

        ("TABLE", r"Table"),
        ("GRAPH", r"Graph"),
        ("CHART", r"Chart"),
        ("MAP", r"Map"),
        ("DIAGRAM", r"Diagram"),
        ("PLATE", r"Plate"),
        ("FIGURE", r"Fig\.?|Figure")
    ]

    for label_name, label_pattern in label_map:

        pattern = rf"""
            \b{label_pattern}\b
            \s*
            {re.escape(str(figure_number))}
            \b
        """

        if re.search(
            pattern,
            page_text,
            flags=(
                re.IGNORECASE |
                re.VERBOSE
            )
        ):

            return label_name

    return "UNKNOWN"


# ============================================================
# FIGURE CONTEXT
# ============================================================

def extract_figure_context(
    page_text,
    caption
):
    """
    Extract text surrounding the visual caption.
    """

    if not page_text:
        return "NOT_REPORTED"

    if caption == "NOT_REPORTED":
        return "NOT_REPORTED"

    # --------------------------------------------------------
    # First try exact caption
    # --------------------------------------------------------

    caption_position = page_text.find(
        caption
    )

    # --------------------------------------------------------
    # If complete caption was not found, try normalized text
    # --------------------------------------------------------

    if caption_position == -1:

        normalized_page_text = re.sub(
            r"\s+",
            " ",
            page_text
        )

        normalized_caption = re.sub(
            r"\s+",
            " ",
            caption
        ).strip()

        caption_position = (
            normalized_page_text.find(
                normalized_caption
            )
        )

        if caption_position == -1:
            return caption

        page_text = normalized_page_text
        caption = normalized_caption

    # --------------------------------------------------------
    # Take surrounding context
    # --------------------------------------------------------

    context_start = max(
        0,
        caption_position - 500
    )

    context_end = min(
        len(page_text),
        caption_position +
        len(caption) +
        500
    )

    context = page_text[
        context_start:context_end
    ]

    context = re.sub(
        r"\s+",
        " ",
        context
    ).strip()

    return context


# ============================================================
# CLEAN PAPER TEXT
# ============================================================

def clean_paper_text(
    text
):
    """
    Clean extracted PDF text while preserving the actual
    research-paper content.
    """

    if not text:
        return ""

    # Normalize line endings
    text = text.replace(
        "\r\n",
        "\n"
    ).replace(
        "\r",
        "\n"
    )

    # Remove excessive blank lines
    text = re.sub(
        r"\n{3,}",
        "\n\n",
        text
    )

    # Remove excessive spaces
    text = re.sub(
        r"[ \t]+",
        " ",
        text
    )

    return text.strip()


# ============================================================
# EXTRACT FIGURES / VISUALS
# ============================================================

def extract_figures(
    pdf_path: str,
    output_dir: str = "outputs/figures"
):
    """
    Extract research-paper visuals.

    Embedded images are extracted using:

        page.get_images(full=True)

    Images are saved using globally unique sequential names:

        image_01.png
        image_02.jpg
        image_03.jpeg
        ...

    The original image extension is preserved.

    The extracted record also contains:

        full_paper_text

    so downstream AI analysis can use the complete paper
    instead of relying only on the current page.
    """

    pdf_file = Path(
        pdf_path
    )

    output_path = Path(
        output_dir
    )

    output_path.mkdir(
        parents=True,
        exist_ok=True
    )

    # ========================================================
    # OPEN PDF
    # ========================================================

    doc = pymupdf.open(
        pdf_file
    )

    extracted_figures = []

    # ========================================================
    # EXTRACT COMPLETE PAPER TEXT
    # ========================================================

    all_page_text = []

    for page in doc:

        try:

            text = page.get_text(
                "text"
            )

        except Exception:

            text = ""

        if text:

            all_page_text.append(
                text
            )

    full_paper_text = "\n\n".join(
        all_page_text
    )

    full_paper_text = clean_paper_text(
        full_paper_text
    )

    # ========================================================
    # FIGURE COUNTER
    # ========================================================
    # This counter is for the figure number inside the paper.
    # Example:
    #
    # Figure 1
    # Figure 2
    # Figure 3
    #
    # It is separate from the global image filename.

    figure_counter = 1

    # ========================================================
    # GLOBAL IMAGE NUMBER
    # ========================================================
    # Find the highest existing image number so images from
    # previous papers are not overwritten.
    #
    # Example:
    #
    # image_01.png
    # image_02.jpg
    # image_03.jpeg
    #
    # Next image will become:
    #
    # image_04.png

    existing_numbers = []

    for existing_file in output_path.iterdir():

        if not existing_file.is_file():
            continue

        file_stem = existing_file.stem

        if not file_stem.startswith(
            "image_"
        ):
            continue

        number_part = file_stem[
            len("image_") :
        ]

        try:

            number = int(
                number_part
            )

            existing_numbers.append(
                number
            )

        except ValueError:

            continue

    if existing_numbers:

        next_image_number = (
            max(existing_numbers) + 1
        )

    else:

        next_image_number = 1

    # ========================================================
    # PROCESS EVERY PAGE
    # ========================================================

    for page_number, page in enumerate(
        doc,
        start=1
    ):

        # ====================================================
        # EXISTING EMBEDDED IMAGE EXTRACTION
        # ====================================================

        images = page.get_images(
            full=True
        )

        # ====================================================
        # CURRENT PAGE TEXT
        # ====================================================

        try:

            page_text = page.get_text(
                "text"
            )

        except Exception:

            page_text = ""

        page_text = clean_paper_text(
            page_text
        )

        # ====================================================
        # PROCESS EMBEDDED IMAGES
        # ====================================================

        for image_number, image in enumerate(
            images,
            start=1
        ):

            try:

                xref = image[0]

                image_data = doc.extract_image(
                    xref
                )

                image_bytes = image_data[
                    "image"
                ]

                image_ext = image_data[
                    "ext"
                ]

                # --------------------------------------------
                # UNIQUE SEQUENTIAL IMAGE NAME
                # --------------------------------------------
                #
                # The original extension is preserved.
                #
                # Examples:
                #
                # image_01.png
                # image_02.jpeg
                # image_03.jpg

                image_name = (
                    f"image_{next_image_number:02d}"
                    f".{image_ext}"
                )

                image_path = (
                    output_path /
                    image_name
                )

                # --------------------------------------------
                # SAVE IMAGE
                # --------------------------------------------

                with open(
                    image_path,
                    "wb"
                ) as image_file:

                    image_file.write(
                        image_bytes
                    )

                # --------------------------------------------
                # ORIGINAL CAPTION
                # --------------------------------------------

                caption = find_visual_caption(
                    page_text,
                    figure_counter
                )

                # --------------------------------------------
                # CAPTION TEXT ONLY
                # --------------------------------------------

                caption_text = (
                    extract_figure_caption(
                        page_text,
                        figure_counter
                    )
                )

                # --------------------------------------------
                # VISUAL LABEL TYPE
                # Fig / Table / Graph / Map / etc.
                # --------------------------------------------

                visual_label_type = (
                    detect_visual_label_type(
                        page_text,
                        figure_counter
                    )
                )

                # --------------------------------------------
                # CONTEXT
                # --------------------------------------------

                context = extract_figure_context(
                    page_text,
                    caption
                )

                # --------------------------------------------
                # VISUAL RECORD
                # --------------------------------------------

                figure_record = {

                    # Existing fields
                    "image_path":
                        str(image_path),

                    "figure_number":
                        figure_counter,

                    "page_number":
                        page_number,

                    "page_text":
                        page_text,

                    "caption":
                        caption,

                    "context":
                        context,

                    # Full paper information
                    "full_paper_text":
                        full_paper_text,

                    # Additional extraction metadata
                    "visual_source":
                        "embedded_image",

                    # New unique image identifier
                    "visual_identifier":
                        f"image_{next_image_number:02d}",

                    "visual_label_type":
                        visual_label_type,

                    "bounding_box":
                        None,

                    # Caption without visual label
                    "caption_text":
                        caption_text
                }

                extracted_figures.append(
                    figure_record
                )

                # --------------------------------------------
                # INCREMENT GLOBAL IMAGE NUMBER
                # --------------------------------------------

                next_image_number += 1

                # --------------------------------------------
                # INCREMENT PAPER FIGURE NUMBER
                # --------------------------------------------

                figure_counter += 1

            except Exception as e:

                # --------------------------------------------
                # Do not stop extraction because one image
                # fails.
                # --------------------------------------------

                print(
                    "Image extraction error "
                    f"on page {page_number}: {e}"
                )

                continue

    # ========================================================
    # CLOSE PDF
    # ========================================================

    doc.close()

    return extracted_figures
