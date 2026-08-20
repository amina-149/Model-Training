# =========================================================
# STEP 10A — APPROVED PAPER SOURCES
# =========================================================

APPROVED_SOURCES = {

    "HEC": {
        "name": "HEC Research Repositories / Publications / Projects",
        "category": "HEC",
        "enabled": True,
        "base_url": None
    },

    "PAKISTANI_UNIVERSITIES": {
        "name": "Pakistani University Research Repositories",
        "category": "University Repository",
        "enabled": True,
        "base_url": None
    },

    "PUNJAB_AGRICULTURE": {
        "name": "Punjab Agriculture Department / Government Publications",
        "category": "Government Agriculture",
        "enabled": True,
        "base_url": None
    },

    "FAO": {
        "name": "FAO Resources",
        "category": "International Agriculture",
        "enabled": True,
        "base_url": None
    },

    "MNFSR": {
        "name": "MNFSR Resources",
        "category": "Government Agriculture",
        "enabled": True,
        "base_url": None
    },

    "RESEARCH_JOURNALS": {
        "name": "Approved Research Journals",
        "category": "Research Journal",
        "enabled": True,
        "base_url": None
    }
}


def get_approved_sources():
    """
    Return only sources that are currently enabled.
    """

    return {
        key: source
        for key, source in APPROVED_SOURCES.items()
        if source.get("enabled", False)
    }
