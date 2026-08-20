import os
import mimetypes
import json
import re
from io import BytesIO

from PIL import Image
from dotenv import load_dotenv
from google import genai


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    raise ValueError(
        "GEMINI_API_KEY not found in .env file"
    )

client = genai.Client(
    api_key=API_KEY
)


# ============================================================
# CONSTANTS
# ============================================================

UNKNOWN_VALUES = {
    "",
    "UNKNOWN",
    "NOT_REPORTED",
    "NONE",
    "NULL",
    "N/A",
    "NA"
}


ALLOWED_CONDITIONS = {
    "HEALTHY",
    "DISEASE",
    "PEST",
    "NUTRIENT_DEFICIENCY",
    "ABIOTIC_STRESS",
    "WEED",
    "PHYSICAL_DAMAGE",
    "UNKNOWN"
}


ALLOWED_PLANT_PARTS = {
    "WHOLE_PLANT",
    "LEAF",
    "STEM",
    "ROOT",
    "FLOWER",
    "FRUIT",
    "SEED",
    "POD",
    "EAR/PANICLE",
    "UNKNOWN"
}


ALLOWED_FIELD_TYPES = {
    "REAL_FIELD",
    "RESEARCH_FIELD",
    "CONTROLLED_ENVIRONMENT",
    "LABORATORY",
    "GREENHOUSE",
    "UNKNOWN"
}


ALLOWED_VISUAL_TYPES = {
    "PLANT_PHOTO",
    "LEAF_PHOTO",
    "STEM_PHOTO",
    "ROOT_PHOTO",
    "FRUIT_PHOTO",
    "SEED_PHOTO",
    "PEST_PHOTO",
    "DISEASE_PHOTO",
    "WEED_PHOTO",
    "FIELD_PHOTO",
    "SOIL_PHOTO",
    "SATELLITE_IMAGE",
    "MAP",
    "GRAPH",
    "TABLE",
    "DIAGRAM",
    "OTHER"
}


# A = CV_IMAGE (real visual evidence, usable for CV training)
# B = RESEARCH_VISUAL (useful for research/context, not CV training)
# C = NON_CV (must not be used at all)
ALLOWED_CV_CATEGORIES = {
    "CV_IMAGE",
    "RESEARCH_VISUAL",
    "NON_CV"
}


# Visual label found in the paper text (Table/Graph/Chart/Map/
# Diagram/Plate/Fig) mapped to a deterministic Visual_Type +
# CV_Category. This is paper-supported evidence and always wins
# over an AI visual guess, exactly like Crop/Disease/Location do
# elsewhere in this file.
LABEL_TYPE_TO_VISUAL_CLASSIFICATION = {

    "TABLE": (
        "TABLE",
        "NON_CV",
        "TEXT_ONLY"
    ),

    "GRAPH": (
        "GRAPH",
        "NON_CV",
        "GRAPH"
    ),

    "CHART": (
        "GRAPH",
        "NON_CV",
        "GRAPH"
    ),

    "MAP": (
        "MAP",
        "RESEARCH_VISUAL",
        None
    ),

    "DIAGRAM": (
        "DIAGRAM",
        "NON_CV",
        "DIAGRAM"
    )
}


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def is_unknown(value):
    if value is None:
        return True

    value_string = str(value).strip().upper()

    return value_string in UNKNOWN_VALUES


def clean_value(value):
    if value is None:
        return "UNKNOWN"

    if isinstance(value, str):

        value = value.strip()

        if not value:
            return "UNKNOWN"

    return value


def safe_text(value):
    if value is None:
        return ""

    return str(value).strip()


# ============================================================
# TEXT NORMALIZATION
# ============================================================

def normalize_text(text):
    if not text:
        return ""

    text = str(text)

    text = text.replace(
        "\u00a0",
        " "
    )

    text = re.sub(
        r"[ \t]+",
        " ",
        text
    )

    text = re.sub(
        r"\n{3,}",
        "\n\n",
        text
    )

    return text.strip()


# ============================================================
# CROP EXTRACTION
# ============================================================

def find_crop_from_paper(text):

    if not text:
        return "UNKNOWN"

    text = normalize_text(text)

    crop_patterns = [

        ("WHEAT", r"\bwheat\b"),
        ("RICE", r"\brice\b"),
        ("MAIZE", r"\bmaize\b"),
        ("MAIZE", r"\bcorn\b"),
        ("COTTON", r"\bcotton\b"),
        ("SUGARCANE", r"\bsugarcane\b"),
        ("TOMATO", r"\btomato\b"),
        ("POTATO", r"\bpotato\b"),
        ("CHICKPEA", r"\bchickpea\b"),
        ("PEA", r"\bpea\b"),
        ("LENTIL", r"\blentil\b"),
        ("BARLEY", r"\bbarley\b"),
        ("OAT", r"\boat\b"),
        ("MUSTARD", r"\bmustard\b"),
        ("SUNFLOWER", r"\bsunflower\b"),
        ("SOYBEAN", r"\bsoybean\b"),
        ("GROUNDNUT", r"\bgroundnut\b"),
        ("PEANUT", r"\bpeanut\b"),
        ("TOBACCO", r"\btobacco\b")
    ]

    text_lower = text.lower()

    for crop_name, pattern in crop_patterns:

        if re.search(
            pattern,
            text_lower,
            flags=re.IGNORECASE
        ):

            return crop_name

    return "UNKNOWN"


# ============================================================
# LOCATION EXTRACTION
# ============================================================

def find_location_from_paper(text):

    location = {

        "Country": "UNKNOWN",
        "Province": "UNKNOWN",
        "District": "UNKNOWN",
        "Tehsil": "UNKNOWN",
        "Village": "UNKNOWN",
        "Research_Station": "UNKNOWN",
        "GPS": "UNKNOWN"
    }

    if not text:
        return location

    text_lower = normalize_text(
        text
    ).lower()

    # Country
    if re.search(
        r"\bpakistan\b",
        text_lower
    ):

        location["Country"] = "PAKISTAN"

    # Provinces
    provinces = {

        "PUNJAB":
            r"\bpunjab\b",

        "SINDH":
            r"\bsindh\b",

        "KHYBER PAKHTUNKHWA":
            r"\bkhyber\s+pakhtunkhwa\b",

        "KPK":
            r"\bkpk\b",

        "BALOCHISTAN":
            r"\bbalochistan\b",

        "GILGIT BALTISTAN":
            r"\bgilgit\s+baltistan\b",

        "AZAD JAMMU AND KASHMIR":
            r"\bazad\s+jammu\s+and\s+kashmir\b"
    }

    for province, pattern in provinces.items():

        if re.search(
            pattern,
            text_lower,
            flags=re.IGNORECASE
        ):

            location["Province"] = province

            break

    return location

# ============================================================
# DISEASE EXTRACTION FROM PAPER
# ============================================================

def find_disease_from_paper(text):
    """
    Find disease name from the research paper.

    Uses common agricultural disease phrases and
    prefers disease names appearing near disease-related
    terminology.
    """

    if not text:
        return "UNKNOWN"

    text = normalize_text(text)

    disease_patterns = [
        r"([A-Za-z][A-Za-z\s\-]+leaf spot(?: disease)?)",
        r"([A-Za-z][A-Za-z\s\-]+blight(?: disease)?)",
        r"([A-Za-z][A-Za-z\s\-]+rust(?: disease)?)",
        r"([A-Za-z][A-Za-z\s\-]+smut(?: disease)?)",
        r"([A-Za-z][A-Za-z\s\-]+wilt(?: disease)?)",
        r"([A-Za-z][A-Za-z\s\-]+mildew(?: disease)?)",
        r"([A-Za-z][A-Za-z\s\-]+rot(?: disease)?)",
        r"([A-Za-z][A-Za-z\s\-]+disease)"
    ]

    for pattern in disease_patterns:

        matches = re.findall(
            pattern,
            text,
            flags=re.IGNORECASE
        )

        for match in matches:

            value = normalize_text(match)

            if len(value) > 3:
                return value

    return "UNKNOWN"

# ============================================================
# FIELD TYPE FROM TEXT
# ============================================================

def find_field_type_from_text(text):

    if not text:
        return "UNKNOWN"

    text_lower = normalize_text(
        text
    ).lower()

    # Laboratory / microscopy
    if any(
        phrase in text_lower
        for phrase in [
            "laboratory",
            "laboratory conditions",
            "lab experiment",
            "microscopic",
            "microscope",
            "1000x magnification",
            "magnification",
            "conidia",
            "conidium"
        ]
    ):

        return "LABORATORY"

    # Greenhouse
    if any(
        phrase in text_lower
        for phrase in [
            "greenhouse",
            "glasshouse"
        ]
    ):

        return "GREENHOUSE"

    # Controlled environment
    if any(
        phrase in text_lower
        for phrase in [
            "controlled environment",
            "growth chamber"
        ]
    ):

        return "CONTROLLED_ENVIRONMENT"

    # Research field
    if any(
        phrase in text_lower
        for phrase in [
            "research field",
            "experimental field",
            "field experiment",
            "field trial"
        ]
    ):

        return "RESEARCH_FIELD"

    # Real field
    if any(
        phrase in text_lower
        for phrase in [
            "farm field",
            "farmer field",
            "farmers' field",
            "natural field",
            "field collected"
        ]
    ):

        return "REAL_FIELD"

    return "UNKNOWN"


# ============================================================
# CAPTION INFORMATION
# ============================================================

def infer_from_caption(
    caption,
    figure_number
):

    result = {

        "Plant_Part":
            "UNKNOWN",

        "Paper_Label":
            "UNKNOWN",

        "Condition":
            "UNKNOWN",

        "Field_Type":
            "UNKNOWN"
    }

    if not caption:
        return result

    caption_clean = normalize_text(
        caption
    )

    caption_lower = caption_clean.lower()

    # ========================================================
    # PAPER LABEL
    # ========================================================

    # IMPORTANT:
    # Preserve the original caption.
    result["Paper_Label"] = caption_clean

    # ========================================================
    # PLANT PART
    # ========================================================

    if re.search(
        r"\bleaf\b|leaf spots|leaf tissue",
        caption_lower
    ):

        result["Plant_Part"] = "LEAF"

    elif re.search(
        r"\bstem\b|internode|inter node",
        caption_lower
    ):

        result["Plant_Part"] = "STEM"

    elif re.search(
        r"\broot\b",
        caption_lower
    ):

        result["Plant_Part"] = "ROOT"

    elif re.search(
        r"\bflower\b",
        caption_lower
    ):

        result["Plant_Part"] = "FLOWER"

    elif re.search(
        r"\bfruit\b",
        caption_lower
    ):

        result["Plant_Part"] = "FRUIT"

    elif re.search(
        r"\bseed\b",
        caption_lower
    ):

        result["Plant_Part"] = "SEED"

    elif re.search(
        r"\bpod\b",
        caption_lower
    ):

        result["Plant_Part"] = "POD"

    # ========================================================
    # CONDITION
    # ========================================================

    disease_keywords = [

        "disease",
        "diseased",
        "symptom",
        "symptoms",
        "leaf spot",
        "leaf spots",
        "lesion",
        "lesions",
        "infection",
        "infected",
        "pycnidia"
    ]

    if any(
        keyword in caption_lower
        for keyword in disease_keywords
    ):

        result["Condition"] = "DISEASE"

    # ========================================================
    # LABORATORY
    # ========================================================

    if any(
        keyword in caption_lower
        for keyword in [

            "conidia",
            "conidium",
            "spore",
            "spores",
            "magnification",
            "microscopic",
            "1000x"
        ]
    ):

        result["Field_Type"] = "LABORATORY"

    return result


# ============================================================
# VISUAL TYPE / CV CATEGORY (DETERMINISTIC, PAPER-SUPPORTED)
# ============================================================

def classify_visual_deterministic(
    visual_label_type,
    caption
):
    """
    Classify VISUAL_TYPE and CV_Category using the paper's own
    visual label (Table/Graph/Chart/Map/Diagram/Fig) and caption
    wording, BEFORE any agricultural metadata is generated.

    This implements the mandatory split into:
        A = CV_IMAGE        (real visual evidence)
        B = RESEARCH_VISUAL  (useful for context, not CV training)
        C = NON_CV            (must not be used)

    Returns:
        (visual_type, cv_category, rejection_reason)

    visual_type / cv_category may be "UNKNOWN" when the label
    alone is not conclusive (e.g. "Fig." can be a photo, a
    diagram, or a satellite image) -- in that case the AI visual
    analysis is used to decide, never a guess made here.
    """

    label_type = (
        visual_label_type or "UNKNOWN"
    ).upper()

    if label_type in LABEL_TYPE_TO_VISUAL_CLASSIFICATION:

        return LABEL_TYPE_TO_VISUAL_CLASSIFICATION[
            label_type
        ]

    caption_lower = (
        caption or ""
    ).lower()

    # A caption can still reveal a non-CV visual even when the
    # label itself was "Fig."/"Figure" (common in papers that
    # label every visual, including charts, as "Figure").
    non_cv_caption_terms = [

        ("bar chart", "GRAPH", "GRAPH"),
        ("line graph", "GRAPH", "GRAPH"),
        ("scatter plot", "GRAPH", "GRAPH"),
        ("flowchart", "DIAGRAM", "DIAGRAM"),
        ("flow chart", "DIAGRAM", "DIAGRAM"),
        ("schematic", "DIAGRAM", "DIAGRAM"),
        ("bar graph", "GRAPH", "GRAPH")
    ]

    for term, visual_type, reason in non_cv_caption_terms:

        if term in caption_lower:

            return (
                visual_type,
                "NON_CV",
                reason
            )

    if "satellite" in caption_lower or "ndvi" in caption_lower:

        return (
            "SATELLITE_IMAGE",
            "RESEARCH_VISUAL",
            None
        )

    return (
        "UNKNOWN",
        "UNKNOWN",
        None
    )


# ============================================================
# FIND FIGURE-SPECIFIC EVIDENCE
# ============================================================

def find_figure_evidence(
    full_text,
    figure_number,
    caption
):

    if not full_text:
        return ""

    text = normalize_text(
        full_text
    )

    # --------------------------------------------------------
    # First try exact caption
    # --------------------------------------------------------

    if caption and caption != "NOT_REPORTED":

        caption_clean = normalize_text(
            caption
        )

        position = text.lower().find(
            caption_clean.lower()
        )

        if position != -1:

            start = max(
                0,
                position - 1200
            )

            end = min(
                len(text),
                position +
                len(caption_clean) +
                2000
            )

            return text[start:end]

    # --------------------------------------------------------
    # Try figure number
    # --------------------------------------------------------

    pattern = rf"""
        (?:
            Fig\.?
            |
            Figure
        )
        \s*
        {figure_number}
        \b
    """

    match = re.search(
        pattern,
        text,
        flags=re.IGNORECASE |
              re.VERBOSE
    )

    if match:

        start = max(
            0,
            match.start() - 1200
        )

        end = min(
            len(text),
            match.end() + 2500
        )

        return text[start:end]

    return ""


# ============================================================
# FIND IMPORTANT PAPER EVIDENCE
# ============================================================

def find_relevant_paper_evidence(
    full_text,
    caption,
    figure_number
):

    if not full_text:
        return ""

    text = normalize_text(
        full_text
    )

    chunks = []

    # --------------------------------------------------------
    # Figure-specific section
    # --------------------------------------------------------

    figure_evidence = find_figure_evidence(
        text,
        figure_number,
        caption
    )

    if figure_evidence:
        chunks.append(
            "FIGURE-SPECIFIC EVIDENCE:\n"
            + figure_evidence
        )

    # --------------------------------------------------------
    # Search crop/disease/location keywords
    # --------------------------------------------------------

    keywords = [

        "wheat",
        "rice",
        "maize",
        "corn",
        "cotton",
        "tomato",
        "potato",
        "chickpea",
        "barley",
        "mustard",
        "disease",
        "pathogen",
        "fungus",
        "fungal",
        "infection",
        "leaf spot",
        "pycnidia",
        "conidia",
        "symptom",
        "symptoms",
        "pakistan",
        "punjab",
        "sindh",
        "balochistan",
        "khyber",
        "faisalabad",
        "lahore",
        "islamabad"
    ]

    sentences = re.split(
        r"(?<=[.!?])\s+",
        text
    )

    relevant_sentences = []

    for sentence in sentences:

        sentence_lower = sentence.lower()

        if any(
            keyword in sentence_lower
            for keyword in keywords
        ):

            relevant_sentences.append(
                sentence.strip()
            )

    if relevant_sentences:

        # Limit evidence size
        relevant_sentences = (
            relevant_sentences[:30]
        )

        chunks.append(
            "RELEVANT PAPER EVIDENCE:\n"
            + "\n".join(
                relevant_sentences
            )
        )

    return "\n\n".join(
        chunks
    )


# ============================================================
# CV SUITABILITY
# ============================================================

def calculate_cv_suitability(result):

    # ========================================================
    # NON-CV VISUALS ARE ALWAYS REJECTED FOR CV DATASET USE
    # ========================================================

    cv_category = result.get(
        "CV_Category",
        "UNKNOWN"
    )

    if cv_category == "NON_CV":

        return {

            "score": 0,

            "category": "REJECT",

            "factors": {
                "cv_category": {
                    "value": cv_category,
                    "score": 0,
                    "max_score": 100
                }
            },

            "reason": (
                f"Visual is classified as CV_Category=NON_CV "
                f"(Visual_Type={result.get('Visual_Type', 'UNKNOWN')}). "
                "Non-CV visuals (tables, graphs, diagrams) are never "
                "eligible for the CV image dataset."
            )
        }

    score = 0

    factors = {}

    # ========================================================
    # CROP
    # ========================================================

    crop = result.get(
        "Crop",
        "UNKNOWN"
    )

    if not is_unknown(crop):

        crop_score = 15
        crop_value = True

    else:

        crop_score = 0
        crop_value = "UNKNOWN"

    score += crop_score

    factors["crop_identifiable"] = {

        "value": crop_value,
        "score": crop_score,
        "max_score": 15
    }

    # ========================================================
    # CONDITION
    # ========================================================

    condition = result.get(
        "Condition",
        "UNKNOWN"
    )

    if (
        condition in ALLOWED_CONDITIONS
        and condition != "UNKNOWN"
    ):

        condition_score = 20
        condition_value = True

    else:

        condition_score = 0
        condition_value = "UNKNOWN"

    score += condition_score

    factors["condition_identifiable"] = {

        "value": condition_value,
        "score": condition_score,
        "max_score": 20
    }

    # ========================================================
    # PAPER LABEL
    # ========================================================

    paper_label = result.get(
        "Paper_Label",
        "UNKNOWN"
    )

    if not is_unknown(paper_label):

        research_label_score = 20
        research_label_value = True

    else:

        research_label_score = 0
        research_label_value = "UNKNOWN"

    score += research_label_score

    factors["research_label_available"] = {

        "value": research_label_value,
        "score": research_label_score,
        "max_score": 20
    }

    # ========================================================
    # IMAGE QUALITY
    # ========================================================

    image_quality = result.get(
        "Image_Quality",
        {}
    )

    if not isinstance(
        image_quality,
        dict
    ):

        image_quality = {}

    quality_overall = image_quality.get(
        "overall",
        "UNKNOWN"
    )

    quality_scores = {

        "EXCELLENT": 15,
        "GOOD": 12,
        "USABLE": 9,
        "POOR": 3,
        "REJECT": 0,
        "UNKNOWN": 0
    }

    image_quality_score = quality_scores.get(
        quality_overall,
        0
    )

    score += image_quality_score

    factors["image_quality"] = {

        "value": quality_overall,
        "score": image_quality_score,
        "max_score": 15
    }

    # ========================================================
    # FIELD TYPE
    # ========================================================

    field_type = result.get(
        "Field_Type",
        "UNKNOWN"
    )

    if field_type == "REAL_FIELD":

        real_field_score = 10
        real_field_value = True

    elif field_type == "RESEARCH_FIELD":

        real_field_score = 7
        real_field_value = "RESEARCH_FIELD"

    elif field_type in {
        "CONTROLLED_ENVIRONMENT",
        "LABORATORY",
        "GREENHOUSE"
    }:

        real_field_score = 0
        real_field_value = field_type

    else:

        real_field_score = 0
        real_field_value = "UNKNOWN"

    score += real_field_score

    factors["real_field_image"] = {

        "value": real_field_value,
        "score": real_field_score,
        "max_score": 10
    }

    # ========================================================
    # METADATA COMPLETENESS
    # ========================================================

    metadata_fields = [

        "Crop",
        "Condition",
        "Disease_Name",
        "Pest_Name",
        "Nutrient",
        "Stress_Type",
        "Plant_Part",
        "Severity",
        "Growth_Stage",
        "Field_Type"
    ]

    available_metadata = 0

    for field in metadata_fields:

        value = result.get(
            field
        )

        if not is_unknown(value):

            available_metadata += 1

    metadata_ratio = (
        available_metadata /
        len(metadata_fields)
    )

    metadata_score = round(
        metadata_ratio * 10
    )

    score += metadata_score

    factors["metadata_completeness"] = {

        "available_fields":
            available_metadata,

        "total_fields":
            len(metadata_fields),

        "score":
            metadata_score,

        "max_score":
            10
    }

    # ========================================================
    # PAKISTAN RELEVANCE
    # ========================================================

    pakistan_relevance = "UNKNOWN"

    location_fields = [

        "Country",
        "Province",
        "District",
        "Tehsil",
        "Village",
        "Research_Station"
    ]

    for field in location_fields:

        value = result.get(
            field
        )

        if is_unknown(value):
            continue

        value_lower = str(
            value
        ).lower()

        if "pakistan" in value_lower:

            pakistan_relevance = True

            break

        if field == "Country":

            pakistan_relevance = False

    pakistan_score = (

        10
        if pakistan_relevance is True
        else 0
    )

    score += pakistan_score

    factors["pakistan_relevance"] = {

        "value":
            pakistan_relevance,

        "score":
            pakistan_score,

        "max_score":
            10
    }

    # ========================================================
    # CATEGORY
    # ========================================================

    score = max(
        0,
        min(
            100,
            score
        )
    )

    if score >= 80:

        category = "HIGH_VALUE"

    elif score >= 60:

        category = "REVIEW"

    elif score >= 40:

        category = "LOW_VALUE"

    else:

        category = "REJECT"

    # ========================================================
    # REASONS
    # ========================================================

    reasons = []

    if crop_value == "UNKNOWN":

        reasons.append(
            "Crop is not clearly identified."
        )

    if condition_value == "UNKNOWN":

        reasons.append(
            "Agricultural condition is not clearly identified."
        )

    if research_label_value == "UNKNOWN":

        reasons.append(
            "Research/Paper label is not available."
        )

    if quality_overall in {
        "POOR",
        "REJECT",
        "UNKNOWN"
    }:

        reasons.append(
            "Image quality is limited or unknown."
        )

    if field_type == "UNKNOWN":

        reasons.append(
            "Field type is not explicitly established."
        )

    elif field_type not in {
        "REAL_FIELD",
        "RESEARCH_FIELD"
    }:

        reasons.append(
            f"Image is classified as {field_type}, "
            "not a real field image."
        )

    if metadata_score < 10:

        reasons.append(
            "Some agricultural metadata is incomplete."
        )

    if pakistan_relevance == "UNKNOWN":

        reasons.append(
            "Pakistan relevance is not explicitly established."
        )

    elif pakistan_relevance is False:

        reasons.append(
            "The available location information "
            "does not establish Pakistan relevance."
        )

    if not reasons:

        reasons.append(
            "Image has strong characteristics "
            "for CV dataset consideration."
        )

    return {

        "score": score,

        "category": category,

        "factors": factors,

        "reason":
            " ".join(reasons)
    }


# ============================================================
# GENERATE FIGURE LABEL
# ============================================================

def generate_figure_label(
    figure_record,
    paper_id
):

    try:

        # ====================================================
        # BASIC INFORMATION
        # ====================================================

        image_path = figure_record[
            "image_path"
        ]

        figure_number = figure_record[
            "figure_number"
        ]

        page_number = figure_record[
            "page_number"
        ]

        page_text = figure_record.get(
            "page_text",
            ""
        )

        caption = figure_record.get(
            "caption",
            "NOT_REPORTED"
        )

        context = figure_record.get(
            "context",
            "NOT_REPORTED"
        )

        full_paper_text = figure_record.get(
            "full_paper_text",
            ""
        )

        # ====================================================
        # IMAGE ID
        # ====================================================

        image_id = figure_record.get(
            "image_id",
            f"{paper_id}_IMG_{figure_number:03d}"
        )

        # ====================================================
        # READ IMAGE
        # ====================================================

        with open(
            image_path,
            "rb"
        ) as image_file:

            image_bytes = image_file.read()

        mime_type, _ = mimetypes.guess_type(
            image_path
        )

        if not mime_type:

            mime_type = "image/jpeg"

        # ====================================================
        # IMAGE DIMENSIONS
        # ====================================================

        try:

            image = Image.open(
                BytesIO(image_bytes)
            )

            image_width, image_height = (
                image.size
            )

        except Exception:

            image_width = "UNKNOWN"
            image_height = "UNKNOWN"

        # ====================================================
        # NORMALIZE TEXT
        # ====================================================

        full_paper_text = normalize_text(
            full_paper_text
        )

        page_text = normalize_text(
            page_text
        )

        caption = normalize_text(
            caption
        )

        context = normalize_text(
            context
        )

        # ====================================================
        # DETERMINISTIC PAPER EXTRACTION
        # ====================================================

        paper_crop = find_crop_from_paper(
            full_paper_text
        )

        paper_disease = find_disease_from_paper(
            full_paper_text
        )

        paper_location = find_location_from_paper(
            full_paper_text
        )

        paper_field_type = find_field_type_from_text(
            full_paper_text
        )

        caption_info = infer_from_caption(
            caption,
            figure_number
        )

        figure_evidence = find_relevant_paper_evidence(
            full_paper_text,
            caption,
            figure_number
        )

        # ====================================================
        # VISUAL TYPE / CV CATEGORY (DETERMINISTIC)
        # ====================================================

        visual_label_type = figure_record.get(
            "visual_label_type",
            "UNKNOWN"
        )

        (
            deterministic_visual_type,
            deterministic_cv_category,
            deterministic_rejection_reason
        ) = classify_visual_deterministic(
            visual_label_type,
            caption
        )

        # ====================================================
        # FIELD TYPE PRIORITY
        # ====================================================

        if caption_info["Field_Type"] != "UNKNOWN":

            deterministic_field_type = (
                caption_info["Field_Type"]
            )

        else:

            deterministic_field_type = (
                paper_field_type
            )

        # ====================================================
        # PAPER TEXT LIMIT
        # ====================================================

        MAX_PAPER_TEXT = 70000

        if len(full_paper_text) > MAX_PAPER_TEXT:

            full_paper_text_for_ai = (
                full_paper_text[
                    :MAX_PAPER_TEXT
                ]
            )

        else:

            full_paper_text_for_ai = (
                full_paper_text
            )

        # ====================================================
        # GEMINI PROMPT
        # ====================================================
        
        prompt = f"""
You are an agricultural research-paper figure analysis
and AI metadata extraction system.

Your task is to analyze the figure using TWO sources:

SOURCE 1 = RESEARCH PAPER EVIDENCE
SOURCE 2 = VISUAL AI ANALYSIS OF THE IMAGE

You MUST use both sources.

The final metadata should NOT unnecessarily contain UNKNOWN.

====================================================
IMPORTANT DECISION RULE
====================================================

For every metadata field:

STEP 1:
Search the COMPLETE PAPER TEXT, caption, context and
page text for explicit evidence.

STEP 2:
If the paper provides the value, use the paper-supported
value.

STEP 3:
If the paper does NOT provide the value, analyze the
IMAGE VISUALLY and provide the best AI prediction.

STEP 4:
If both paper evidence and visual evidence exist, prefer
the paper-supported value for metadata.

STEP 5:
Only use UNKNOWN when the information cannot reasonably
be determined from either:
- the research paper
- the figure caption/context
- the visual image

DO NOT return UNKNOWN merely because the paper does not
mention the field.

====================================================
VERY IMPORTANT
====================================================

There are TWO different concepts:

Paper-supported metadata
and
AI-predicted metadata.

Paper-supported metadata must come from the research
paper.

AI-predicted metadata may come from visual analysis.

Do NOT put visual guesses into Evidence_Text.

Do NOT pretend that an AI prediction came from the paper.

====================================================
FIGURE INFORMATION
====================================================

Image ID:
{image_id}

Paper ID:
{paper_id}

Figure Number:
{figure_number}

Page Number:
{page_number}

Image Width:
{image_width}

Image Height:
{image_height}

====================================================
ORIGINAL FIGURE CAPTION
====================================================

{caption}

====================================================
FIGURE CONTEXT
====================================================

{context}

====================================================
CURRENT PAGE TEXT
====================================================

{page_text}

====================================================
COMPLETE RESEARCH PAPER TEXT
====================================================

{full_paper_text_for_ai}

====================================================
VISUAL TYPE AND CV CATEGORY (DO THIS FIRST)
====================================================

Before analyzing any agricultural content, classify what kind
of visual this actually is.

Visual_Type must be exactly one of:

PLANT_PHOTO, LEAF_PHOTO, STEM_PHOTO, ROOT_PHOTO, FRUIT_PHOTO,
SEED_PHOTO, PEST_PHOTO, DISEASE_PHOTO, WEED_PHOTO, FIELD_PHOTO,
SOIL_PHOTO, SATELLITE_IMAGE, MAP, GRAPH, TABLE, DIAGRAM, OTHER

CV_Category must be exactly one of:

CV_IMAGE
    Real photographic/visual evidence of a plant, pest, leaf,
    field, soil, etc. Usable for computer-vision training.

RESEARCH_VISUAL
    Useful for research context but NOT normal CV training
    material (example: a satellite/NDVI map).

NON_CV
    Not a photograph of agricultural subject matter at all
    (example: a bar chart, line graph, data table, flowchart,
    schematic diagram). Must never be treated as CV training
    data.

Look at the actual image pixels, not just the label:

- If the image shows bars, lines, plotted points, or axes with
  numeric scales => Visual_Type = GRAPH, CV_Category = NON_CV.
- If the image is a grid of rows/columns of text/numbers =>
  Visual_Type = TABLE, CV_Category = NON_CV.
- If the image is a schematic/flowchart/process diagram with
  boxes and arrows and no real photograph content =>
  Visual_Type = DIAGRAM, CV_Category = NON_CV.
- If the image is an actual photograph or micrograph of a
  plant/leaf/stem/root/fruit/seed/pest/field/soil =>
  choose the matching *_PHOTO value, CV_Category = CV_IMAGE.
- If the image is a geographic/satellite/NDVI map =>
  Visual_Type = MAP or SATELLITE_IMAGE, CV_Category =
  RESEARCH_VISUAL.

If genuinely uncertain, use Visual_Type = OTHER and
CV_Category = NON_CV rather than guessing CV_IMAGE.

When CV_Category = NON_CV, still fill Crop/Condition/etc. as
UNKNOWN or NOT_APPLICABLE -- do NOT invent agricultural labels
for a chart, table, or diagram just because it appeared in an
agricultural paper.

====================================================
CROP
====================================================

First search the paper for the crop.

Look for:

- crop name
- host plant
- plant species
- scientific name
- experimental crop
- infected crop
- sampled crop

If explicitly found in the paper:

Crop = paper-supported crop.

If NOT found in the paper:

Analyze the image and caption.

Predict the most likely crop from visible characteristics.

For example:

leaf morphology
stem morphology
fruit morphology
plant structure
host characteristics
caption description

If the crop cannot reasonably be predicted:

Crop = UNKNOWN

IMPORTANT:
A visual crop prediction is allowed.

====================================================
CONDITION
====================================================

Determine the condition using BOTH paper evidence and
visual analysis.

Allowed values:

HEALTHY
DISEASE
PEST
NUTRIENT_DEFICIENCY
ABIOTIC_STRESS
WEED
PHYSICAL_DAMAGE
UNKNOWN

If the paper explicitly describes disease/symptoms,
use:

DISEASE

If paper does not clearly identify the condition,
analyze the image.

Visible symptoms may be used for AI prediction.

====================================================
DISEASE NAME
====================================================

Search the complete paper first.

If a disease name is explicitly stated:

use that disease name.

If the disease name is NOT explicitly stated:

analyze the image and caption.

Predict the most likely disease based on:

- visible symptoms
- lesion pattern
- discoloration
- spots
- tissue damage
- fungal structures
- bacterial signs
- disease morphology
- caption terminology

Example:

Caption:
"Leaf spots with dark coloured pycnidia"

Possible AI prediction:

"Fungal leaf spot disease"

If the exact disease cannot be determined,
DO NOT invent a highly specific disease name.

Use a reasonable general prediction such as:

"Fungal leaf spot disease"

rather than:

"Alternaria leaf spot"

unless there is sufficient evidence.

====================================================
PEST NAME
====================================================

Search the paper first.

If the paper identifies a pest, use it.

If not, inspect the image.

Look for:

- insects
- larvae
- eggs
- feeding damage
- holes
- mines
- webbing
- pest bodies

If a pest can reasonably be identified,
provide the AI prediction.

Otherwise:

UNKNOWN

====================================================
NUTRIENT
====================================================

Search the paper first.

If not available, visually analyze symptoms such as:

- chlorosis
- necrosis
- interveinal chlorosis
- leaf discoloration
- abnormal growth

Predict a likely nutrient deficiency ONLY when
visual evidence reasonably supports it.

Otherwise:

UNKNOWN

====================================================
STRESS TYPE
====================================================

Search the paper first.

If not available, analyze the image for:

- drought stress
- heat stress
- cold stress
- waterlogging
- salinity
- mechanical stress
- environmental damage

Provide the most likely AI prediction when supported.

Otherwise:

UNKNOWN

====================================================
PLANT PART
====================================================

Determine from paper/caption first.

If not explicitly available, inspect the image.

Allowed values:

WHOLE_PLANT
LEAF
STEM
ROOT
FLOWER
FRUIT
SEED
POD
EAR/PANICLE
UNKNOWN

Example:

"Leaf spots"

=> LEAF

"Twist symptoms on internode"

=> STEM

"Conidia with appendages"

=> UNKNOWN

because this is a microscopic fungal structure rather
than a visible plant part.

====================================================
SEVERITY
====================================================

First search the paper for explicit severity.

If severity is explicitly reported, use it.

If not reported, visually estimate severity ONLY if the
image clearly shows enough affected plant tissue.

Allowed:

NONE
EARLY
MILD
MODERATE
SEVERE
NOT_REPORTED

IMPORTANT:

If severity is visually estimated, this is an AI prediction
and MUST NOT be written as paper evidence.

Use:

Original_Severity = NOT_REPORTED

when the paper does not explicitly report severity.

====================================================
GROWTH STAGE
====================================================

First search the paper.

If not available, visually estimate only if the plant
development stage is clearly visible.

Allowed:

SEEDLING
VEGETATIVE
TILLERING
FLOWERING
FRUITING
MATURITY
HARVEST
UNKNOWN

If the image is only a close-up leaf/stem/microscopic image
and growth stage cannot be determined:

UNKNOWN

====================================================
LOCATION
====================================================

Country, Province, District, Tehsil, Village,
Research_Station and GPS should primarily come from
the research paper.

DO NOT infer geographic location from visual appearance.

DO NOT infer Pakistan from authors or universities.

If no location exists in the paper:

keep location fields UNKNOWN.

====================================================
FIELD TYPE
====================================================

Use paper evidence first.

Allowed:

REAL_FIELD
RESEARCH_FIELD
CONTROLLED_ENVIRONMENT
LABORATORY
GREENHOUSE
UNKNOWN

Visual analysis may be used when the image clearly shows
a laboratory, greenhouse, field, or controlled environment.

For example:

A microscopic image of conidia at 1000x magnification:

Field_Type = LABORATORY

====================================================
PAPER LABEL
====================================================

Paper_Label MUST represent the original paper-supported
label.

Prefer the original figure caption.

Example:

"Leaf spots with dark coloured pycnidia"

DO NOT replace Paper_Label with an AI disease guess.

====================================================
AI PREDICTION
====================================================

AI_Prediction should summarize the visual interpretation
of the image.

It may contain:

- likely crop
- likely condition
- likely disease/pest/stress
- visible symptoms
- visible structures

Examples:

"Likely fungal leaf spot disease showing leaf lesions
with dark pycnidia."

"Stem internode showing twisting symptoms."

"Microscopic view of fungal conidia with terminal
appendages."

AI_Prediction is NOT ground truth.

====================================================
EVIDENCE TEXT
====================================================

Evidence_Text must contain actual information from the
research paper supporting the metadata.

Prefer exact sentences or phrases from the paper.

If a value was determined only visually:

DO NOT claim that visual prediction is paper evidence.

If no paper evidence exists:

Evidence_Text = "NOT_REPORTED"

====================================================
LABEL SOURCE
====================================================

Use:

FIGURE_CAPTION
when the information comes from the figure caption.

PAPER_TEXT
when the information comes from another section of the
research paper.

AI_INFERENCE
when the information is determined only through visual
analysis.

If mixed evidence exists, prefer:

PAPER_TEXT

or

FIGURE_CAPTION

for the metadata field.

====================================================
IMAGE QUALITY
====================================================

Analyze:

- resolution
- blur
- lighting
- visibility
- occlusion
- crop visibility
- symptom visibility

Overall must be one of:

EXCELLENT
GOOD
USABLE
POOR
REJECT

====================================================
PERMISSION
====================================================

Do not assume permission.

If explicit permission/license information is unavailable:

status = LICENSE_UNKNOWN

====================================================
RETURN ONLY VALID JSON
====================================================

Return exactly this structure:

{{
    "Image_ID": "{image_id}",
    "Paper_ID": "{paper_id}",

    "Visual_Type": "OTHER",
    "CV_Category": "NON_CV",

    "Crop": "UNKNOWN",
    "Condition": "UNKNOWN",
    "Disease_Name": "UNKNOWN",
    "Pest_Name": "UNKNOWN",
    "Nutrient": "UNKNOWN",
    "Stress_Type": "UNKNOWN",
    "Plant_Part": "UNKNOWN",

    "Severity": "NOT_REPORTED",
    "Original_Severity": "NOT_REPORTED",

    "Growth_Stage": "UNKNOWN",
    "Original_Growth_Stage": "NOT_REPORTED",

    "Country": "UNKNOWN",
    "Province": "UNKNOWN",
    "District": "UNKNOWN",
    "Tehsil": "UNKNOWN",
    "Village": "UNKNOWN",
    "Research_Station": "UNKNOWN",
    "GPS": "UNKNOWN",

    "Field_Type": "UNKNOWN",

    "Figure_Number": {figure_number},
    "Page_Number": {page_number},

    "Caption": "{caption}",
    "Context": "{context}",

    "Evidence_Text": "NOT_REPORTED",

    "Label_Source": "UNKNOWN",

    "Paper_Label": "{caption}",

    "AI_Prediction": "UNKNOWN",

    "Expert_Label": "PENDING",

    "Image_Quality": {{
        "overall": "UNKNOWN",
        "resolution": "UNKNOWN",
        "blur": "UNKNOWN",
        "lighting": "UNKNOWN",
        "visibility": "UNKNOWN",
        "occlusion": "UNKNOWN",
        "crop_visibility": "UNKNOWN",
        "symptom_visibility": "UNKNOWN",
        "rejection_reasons": []
    }},

    "Permission_Status": {{
        "status": "LICENSE_UNKNOWN",
        "paper_url": null,
        "doi": null,
        "license": null,
        "license_url": null,
        "source": null,
        "permission_evidence": null
    }}
}}
"""

        # ====================================================
        # GEMINI
        # ====================================================

        response = client.models.generate_content(

            model="gemini-flash-latest",

            contents=[

                prompt,

                {
                    "inline_data": {
                        "mime_type":
                            mime_type,

                        "data":
                            image_bytes
                    }
                }
            ]
        )

        response_text = response.text.strip()

        # ====================================================
        # CLEAN JSON
        # ====================================================

        if response_text.startswith("```"):

            response_text = (
                response_text
                .replace(
                    "```json",
                    ""
                )
                .replace(
                    "```",
                    ""
                )
                .strip()
            )

        result = json.loads(
            response_text
        )

        # ====================================================
        # APPLY DETERMINISTIC CAPTION INFORMATION
        # ====================================================
        
        caption_info = infer_from_caption(
            caption,
            figure_number
        )
        # Paper label always comes from original caption
        if not is_unknown(caption):
            result["Paper_Label"] = caption

        # Plant part from caption is more reliable than
        # an unnecessary AI guess
        if (
            caption_info["Plant_Part"] != "UNKNOWN"
        ):
            result["Plant_Part"] = (
                caption_info["Plant_Part"]
            )

        # Condition from caption
        if (
            caption_info["Condition"] != "UNKNOWN"
            and result.get("Condition") == "UNKNOWN"
        ):
            result["Condition"] = (
                caption_info["Condition"]
            )

        # Laboratory evidence from caption
        if (
            caption_info["Field_Type"] != "UNKNOWN"
            and result.get("Field_Type") == "UNKNOWN"
        ):
            result["Field_Type"] = (
                caption_info["Field_Type"]
            )

        # ====================================================
        # APPLICATION CONTROLLED FIELDS
        # ====================================================

        result["Image_ID"] = image_id

        result["Paper_ID"] = paper_id

        result["Figure_Number"] = (
            figure_number
        )

        result["Page_Number"] = (
            page_number
        )

        result["Caption"] = caption

        result["Context"] = context

        result["Expert_Label"] = (
            "PENDING"
        )

        # ====================================================
        # DETERMINISTIC OVERRIDES
        # ====================================================

        # ----------------------------------------------------
        # VISUAL TYPE / CV CATEGORY
        #
        # The paper's own visual label (Table/Graph/Chart/Map/
        # Diagram) is ground truth and always wins over the AI's
        # visual guess -- this is what stops bar charts, tables
        # and diagrams from being classified as CV_IMAGE and
        # flowing into agricultural labelling and the CV dataset.
        # ----------------------------------------------------

        if deterministic_visual_type != "UNKNOWN":

            result["Visual_Type"] = (
                deterministic_visual_type
            )

        if deterministic_cv_category != "UNKNOWN":

            result["CV_Category"] = (
                deterministic_cv_category
            )

        # ----------------------------------------------------
        # PAPER LABEL
        # ----------------------------------------------------

        if caption != "NOT_REPORTED":

            result["Paper_Label"] = caption

            result["Label_Source"] = (
                "FIGURE_CAPTION"
            )

        # ----------------------------------------------------
        # PLANT PART
        # ----------------------------------------------------

        if (
            caption_info["Plant_Part"]
            != "UNKNOWN"
        ):

            result["Plant_Part"] = (
                caption_info[
                    "Plant_Part"
                ]
            )

        # ----------------------------------------------------
        # CONDITION
        # ----------------------------------------------------

        if (
            caption_info["Condition"]
            != "UNKNOWN"
        ):

            result["Condition"] = (
                caption_info[
                    "Condition"
                ]
            )

        # ----------------------------------------------------
        # CROP
        # ----------------------------------------------------

        # If deterministic paper extraction found
        # a crop, do not allow Gemini to erase it.

        if paper_crop != "UNKNOWN":

            result["Crop"] = paper_crop

            if result.get(
                "Label_Source"
            ) != "FIGURE_CAPTION":

                result["Label_Source"] = (
                    "PAPER_TEXT"
                )

        # ----------------------------------------------------
        # DISEASE NAME
        # ----------------------------------------------------
        if paper_disease != "UNKNOWN":
            result["Disease_Name"] = paper_disease

            if result.get("Label_Source") not in {
                "FIGURE_CAPTION"
            }:
                result["Label_Source"] = "PAPER_TEXT"

        # ----------------------------------------------------
        # DISEASE-SPECIFIC NON-APPLICABLE FIELDS
        # ----------------------------------------------------
        if (
            result.get("Condition") == "DISEASE"
            or paper_disease != "UNKNOWN"
        ):
            if is_unknown(
                result.get("Pest_Name")
            ):
                result["Pest_Name"] = "NOT_APPLICABLE"

            if is_unknown(
                result.get("Nutrient")
            ):
                result["Nutrient"] = "NOT_APPLICABLE"

            if is_unknown(
                result.get("Stress_Type")
            ):
                result["Stress_Type"] = "NOT_APPLICABLE"

        # ----------------------------------------------------
        # LOCATION
        # ----------------------------------------------------

        for field in [

            "Country",
            "Province",
            "District",
            "Tehsil",
            "Village",
            "Research_Station",
            "GPS"
        ]:

            paper_value = paper_location.get(
                field,
                "UNKNOWN"
            )

            if not is_unknown(
                paper_value
            ):

                result[field] = (
                    paper_value
                )

        # ----------------------------------------------------
        # FIELD TYPE
        # ----------------------------------------------------

        if deterministic_field_type != "UNKNOWN":

            result["Field_Type"] = (
                deterministic_field_type
            )

        # ----------------------------------------------------
        # EVIDENCE TEXT
        # ----------------------------------------------------

        if figure_evidence:

            result["Evidence_Text"] = (
                figure_evidence[:5000]
            )

        # ----------------------------------------------------
        # GROWTH STAGE
        # ----------------------------------------------------
        if result.get("Growth_Stage") in {
            None,
            "",
            "UNKNOWN"
        }:
            result["Growth_Stage"] = "NOT_REPORTED"

        if result.get("Original_Growth_Stage") in {
            None,
            "",
            "UNKNOWN"
        }:
            result["Original_Growth_Stage"] = "NOT_REPORTED"

        # ----------------------------------------------------
        # SEVERITY
        # ----------------------------------------------------
        allowed_severity = {
            "NONE",
            "EARLY",
            "MILD",
            "MODERATE",
            "SEVERE",
            "NOT_REPORTED"
        }
        if result.get("Severity") not in allowed_severity:
            result["Severity"] = "NOT_REPORTED"

        if result.get("Original_Severity") in {
            None,
            "",
            "UNKNOWN"
        }:
            result["Original_Severity"] = "NOT_REPORTED"

        # ----------------------------------------------------
        # NON-CV ENFORCEMENT
        #
        # Runs LAST, after every paper-text override above, so
        # that a table/graph/diagram can never end up carrying
        # a Crop/Condition/Disease label just because the
        # surrounding paper text happened to mention one.
        # ----------------------------------------------------

        if result.get("CV_Category") == "NON_CV":

            for field in [
                "Crop",
                "Disease_Name",
                "Pest_Name",
                "Nutrient",
                "Stress_Type"
            ]:
                result[field] = "NOT_APPLICABLE"

            result["Condition"] = "UNKNOWN"

            quality = result.get("Image_Quality", {})
            if not isinstance(quality, dict):
                quality = {}
            quality["overall"] = "REJECT"
            if deterministic_rejection_reason:
                quality["rejection_reasons"] = [
                    deterministic_rejection_reason
                ]
            elif not quality.get("rejection_reasons"):
                quality["rejection_reasons"] = ["IRRELEVANT"]
            result["Image_Quality"] = quality

        # ====================================================
        # DEFAULT VALUES
        # ====================================================

        default_values = {

            "Crop":
                "UNKNOWN",

            "Condition":
                "UNKNOWN",

            "Disease_Name":
                "UNKNOWN",

            "Pest_Name":
                "UNKNOWN",

            "Nutrient":
                "UNKNOWN",

            "Stress_Type":
                "UNKNOWN",

            "Plant_Part":
                "UNKNOWN",

            "Severity":
                "NOT_REPORTED",

            "Original_Severity":
                "NOT_REPORTED",

            "Growth_Stage":
                "UNKNOWN",

            "Original_Growth_Stage":
                "NOT_REPORTED",

            "Country":
                "UNKNOWN",

            "Province":
                "UNKNOWN",

            "District":
                "UNKNOWN",

            "Tehsil":
                "UNKNOWN",

            "Village":
                "UNKNOWN",

            "Research_Station":
                "UNKNOWN",

            "GPS":
                "UNKNOWN",

            "Field_Type":
                "UNKNOWN",

            "Evidence_Text":
                "NOT_REPORTED",

            "Label_Source":
                "UNKNOWN",

            "Paper_Label":
                caption,

            "AI_Prediction":
                "UNKNOWN",

            "Visual_Type":
                "OTHER",

            "CV_Category":
                "NON_CV"
        }

        for key, default_value in (
            default_values.items()
        ):

            if (
                key not in result
                or result[key] is None
                or str(
                    result[key]
                ).strip() == ""
            ):

                result[key] = default_value

        # ====================================================
        # FINAL CONDITION VALIDATION
        # ====================================================

        if (
            result["Condition"]
            not in ALLOWED_CONDITIONS
        ):

            result["Condition"] = (
                "UNKNOWN"
            )

        # ====================================================
        # FINAL PLANT PART VALIDATION
        # ====================================================

        if (
            result["Plant_Part"]
            not in ALLOWED_PLANT_PARTS
        ):

            result["Plant_Part"] = (
                "UNKNOWN"
            )

        # ====================================================
        # FINAL FIELD TYPE VALIDATION
        # ====================================================

        if (
            result["Field_Type"]
            not in ALLOWED_FIELD_TYPES
        ):

            result["Field_Type"] = (
                "UNKNOWN"
            )

        # ====================================================
        # FINAL VISUAL TYPE / CV CATEGORY VALIDATION
        # ====================================================

        if (
            result.get("Visual_Type")
            not in ALLOWED_VISUAL_TYPES
        ):

            result["Visual_Type"] = "OTHER"

        if (
            result.get("CV_Category")
            not in ALLOWED_CV_CATEGORIES
        ):

            # Fail safe: an unrecognized category must never be
            # silently treated as usable CV training data.
            result["CV_Category"] = "NON_CV"

        # ====================================================
        # QUALITY
        # ====================================================

        quality = result.get(
            "Image_Quality",
            {}
        )

        if not isinstance(
            quality,
            dict
        ):

            quality = {}

        allowed_quality = {

            "EXCELLENT",
            "GOOD",
            "USABLE",
            "POOR",
            "REJECT"
        }

        allowed_blur = {

            "NONE",
            "LOW",
            "MODERATE",
            "HIGH",
            "UNKNOWN"
        }

        allowed_lighting = {

            "GOOD",
            "ADEQUATE",
            "POOR",
            "UNKNOWN"
        }

        allowed_visibility = {

            "GOOD",
            "PARTIAL",
            "POOR",
            "UNKNOWN"
        }

        allowed_occlusion = {

            "NONE",
            "LOW",
            "MODERATE",
            "HIGH",
            "UNKNOWN"
        }

        allowed_crop_visibility = {

            "GOOD",
            "PARTIAL",
            "POOR",
            "NOT_VISIBLE",
            "UNKNOWN"
        }

        allowed_symptom_visibility = {

            "GOOD",
            "PARTIAL",
            "POOR",
            "NOT_VISIBLE",
            "UNKNOWN"
        }

        allowed_rejection_reasons = {

            "LOW_RESOLUTION",
            "BLURRY",
            "IRRELEVANT",
            "DUPLICATE",
            "DIAGRAM",
            "GRAPH",
            "TEXT_ONLY",
            "CROP_NOT_VISIBLE",
            "SYMPTOM_NOT_VISIBLE",
            "EXCESSIVE_OCCLUSION",
            "UNUSABLE_BACKGROUND",
            "UNKNOWN"
        }

        if (
            quality.get("overall")
            not in allowed_quality
        ):

            quality["overall"] = "UNKNOWN"

        if (
            quality.get("blur")
            not in allowed_blur
        ):

            quality["blur"] = "UNKNOWN"

        if (
            quality.get("lighting")
            not in allowed_lighting
        ):

            quality["lighting"] = "UNKNOWN"

        if (
            quality.get("visibility")
            not in allowed_visibility
        ):

            quality["visibility"] = "UNKNOWN"

        if (
            quality.get("occlusion")
            not in allowed_occlusion
        ):

            quality["occlusion"] = "UNKNOWN"

        if (
            quality.get("crop_visibility")
            not in allowed_crop_visibility
        ):

            quality["crop_visibility"] = "UNKNOWN"

        if (
            quality.get("symptom_visibility")
            not in allowed_symptom_visibility
        ):

            quality["symptom_visibility"] = "UNKNOWN"

        if not isinstance(
            quality.get(
                "rejection_reasons"
            ),
            list
        ):

            quality[
                "rejection_reasons"
            ] = []

        quality[
            "rejection_reasons"
        ] = [

            reason

            for reason in quality[
                "rejection_reasons"
            ]

            if reason
            in allowed_rejection_reasons
        ]

        if (
            quality["overall"]
            != "REJECT"
        ):

            quality[
                "rejection_reasons"
            ] = []

        # Better deterministic resolution
        if (
            image_width != "UNKNOWN"
            and image_height != "UNKNOWN"
        ):

            quality["resolution"] = (
                f"{image_width}x{image_height} pixels"
            )

        result[
            "Image_Quality"
        ] = quality

        # ====================================================
        # PERMISSION
        # ====================================================

        permission = result.get(
            "Permission_Status",
            {}
        )

        if not isinstance(
            permission,
            dict
        ):

            permission = {}

        allowed_permission_statuses = {

            "PERMISSION_CONFIRMED",
            "LICENSE_ALLOWS_REUSE",
            "PERMISSION_REQUIRED",
            "LICENSE_UNKNOWN",
            "DO_NOT_USE"
        }

        if (
            permission.get("status")
            not in allowed_permission_statuses
        ):

            permission["status"] = (
                "LICENSE_UNKNOWN"
            )

        permission_fields = [

            "paper_url",
            "doi",
            "license",
            "license_url",
            "source",
            "permission_evidence"
        ]

        for field in permission_fields:

            if field not in permission:

                permission[field] = None

            elif (
                permission[field]
                is not None
                and not isinstance(
                    permission[field],
                    str
                )
            ):

                permission[field] = None

        if not permission.get(
            "permission_evidence"
        ):

            if permission["status"] in {

                "PERMISSION_CONFIRMED",
                "LICENSE_ALLOWS_REUSE"

            }:

                permission["status"] = (
                    "LICENSE_UNKNOWN"
                )

        result[
            "Permission_Status"
        ] = permission

        # ====================================================
        # CV SUITABILITY
        # ====================================================

        result[
            "CV_Suitability"
        ] = calculate_cv_suitability(
            result
        )

        return result

    except Exception as e:

        print(
            f"Figure analysis error: {e}"
        )

        raise
