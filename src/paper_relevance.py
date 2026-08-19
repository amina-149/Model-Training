# =========================================================
# STEP 10D — PAPER RELEVANCE / ELIGIBILITY
# =========================================================


def _text(value):
    """
    Safely convert a value into searchable lowercase text.
    """
    if value is None:
        return ""

    if isinstance(value, list):
        return " ".join(
            str(item) for item in value
        ).lower()

    return str(value).lower()


def calculate_paper_relevance(
    paper,
    search_query=""
):
    """
    Calculate a 0–100 prioritization score
    for a discovered research paper.

    This is NOT scientific truth.
    It is only a prioritization mechanism.
    """

    title = _text(
        paper.get("Title")
    )

    abstract = _text(
        paper.get("Abstract")
    )

    keywords = _text(
        paper.get("Keywords")
    )

    country = _text(
        paper.get("Country")
    )

    research_location = _text(
        paper.get("Research_Location")
    )

    journal = _text(
        paper.get("Journal")
    )

    combined_text = " ".join([
        title,
        abstract,
        keywords,
        country,
        research_location
    ])

    query_text = _text(
        search_query
    )

    # =====================================================
    # 1. Pakistan Relevance — 20 points
    # =====================================================

    pakistan_score = 0

    pakistan_terms = [
        "pakistan",
        "pakistani",
        "punjab",
        "sindh",
        "khyber pakhtunkhwa",
        "kpk",
        "balochistan",
        "islamabad"
    ]

    if any(
        term in combined_text
        for term in pakistan_terms
    ):
        pakistan_score = 20


    # =====================================================
    # 2. Agriculture Relevance — 20 points
    # =====================================================

    agriculture_score = 0

    agriculture_terms = [
        "agriculture",
        "agricultural",
        "crop",
        "plant",
        "farming",
        "farmer",
        "agronomy",
        "plant pathology",
        "horticulture",
        "cultivation",
        "yield"
    ]

    agriculture_matches = sum(
        term in combined_text
        for term in agriculture_terms
    )

    if agriculture_matches >= 2:
        agriculture_score = 20

    elif agriculture_matches == 1:
        agriculture_score = 10


    # =====================================================
    # 3. Crop Relevance — 15 points
    # =====================================================

    crop_score = 0

    crop_terms = [
        "wheat",
        "rice",
        "maize",
        "corn",
        "cotton",
        "sugarcane",
        "potato",
        "tomato",
        "mango",
        "citrus",
        "crop",
        "plant"
    ]

    crop_matches = sum(
        term in combined_text
        for term in crop_terms
    )

    if crop_matches >= 2:
        crop_score = 15

    elif crop_matches == 1:
        crop_score = 8


    # =====================================================
    # 4. Disease / Pest / Stress — 20 points
    # =====================================================

    condition_score = 0

    condition_terms = [
        "disease",
        "diseases",
        "pathogen",
        "virus",
        "bacteria",
        "fungus",
        "fungal",
        "pest",
        "insect",
        "weed",
        "stress",
        "drought",
        "salinity",
        "heat stress",
        "nutrient deficiency",
        "rust",
        "blight",
        "spot"
    ]

    condition_matches = sum(
        term in combined_text
        for term in condition_terms
    )

    if condition_matches >= 2:
        condition_score = 20

    elif condition_matches == 1:
        condition_score = 10


    # =====================================================
    # 5. Image Availability — 15 points
    # =====================================================

    image_score = 0

    image_terms = [
        "image",
        "images",
        "photograph",
        "photographs",
        "photo",
        "figure",
        "figures",
        "plate",
        "plates",
        "visual",
        "microscopy",
        "microscopic"
    ]

    image_matches = sum(
        term in combined_text
        for term in image_terms
    )

    if image_matches >= 2:
        image_score = 15

    elif image_matches == 1:
        image_score = 8


    # =====================================================
    # 6. Research Quality — 10 points
    # =====================================================

    quality_score = 0

    if paper.get("DOI"):
        quality_score += 4

    if journal:
        quality_score += 3

    if paper.get("Publication_Year"):
        quality_score += 2

    if paper.get("Authors"):
        quality_score += 1


    # =====================================================
    # Final Score
    # =====================================================

    total_score = (
        pakistan_score
        + agriculture_score
        + crop_score
        + condition_score
        + image_score
        + quality_score
    )

    total_score = min(
        100,
        max(0, total_score)
    )


    # =====================================================
    # Eligibility Classification
    # =====================================================

    if total_score >= 80:
        eligibility = "RELEVANT"

    elif total_score >= 50:
        eligibility = "PARTIALLY_RELEVANT"

    else:
        eligibility = "NOT_RELEVANT"


    return {
        "Relevance_Score": total_score,
        "Eligibility": eligibility,

        "Relevance_Breakdown": {
            "Pakistan_Relevance": pakistan_score,
            "Agriculture_Relevance": agriculture_score,
            "Crop_Relevance": crop_score,
            "Disease_Pest_Stress_Relevance": condition_score,
            "Image_Availability": image_score,
            "Research_Quality": quality_score
        }
    }
