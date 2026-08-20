# =========================================================
# STEP 10B — PAPER DISCOVERY
# =========================================================

import requests
from datetime import datetime
import hashlib


CROSSREF_API_URL = "https://api.crossref.org/v1/works"


def generate_paper_id(doi, title, authors):
    """
    Generate a stable internal Paper_ID.

    DOI is preferred when available.
    If DOI is unavailable, title + authors are used.
    """

    if doi:
        identifier = str(doi).strip().lower()

    else:
        identifier = (
            f"{title}|"
            f"{'|'.join(authors)}"
        ).strip().lower()

    if not identifier:
        identifier = "UNKNOWN"

    return (
        "PAPER_"
        + hashlib.sha256(
            identifier.encode("utf-8")
        ).hexdigest()[:12].upper()
    )

def search_papers(query, rows=10):
    """
    Search research paper metadata using Crossref.

    Crossref is used only as a metadata discovery backend.
    It is NOT treated as an approved research source.
    """

    query = query.strip()

    if not query:
        return []

    params = {
        "query.bibliographic": query,
        "rows": rows
    }

    try:

        response = requests.get(
            CROSSREF_API_URL,
            params=params,
            timeout=20
        )

        response.raise_for_status()

        data = response.json()

        items = data.get(
            "message",
            {}
        ).get(
            "items",
            []
        )

        papers = []

        for item in items:

            titles = item.get(
                "title",
                []
            )

            title = (
                titles[0]
                if titles
                else "UNKNOWN"
            )

            authors = []

            for author in item.get(
                "author",
                []
            ):

                given = author.get(
                    "given",
                    ""
                )

                family = author.get(
                    "family",
                    ""
                )

                full_name = (
                    f"{given} {family}"
                ).strip()

                if full_name:
                    authors.append(
                        full_name
                    )

            published = item.get(
                "published-print"
            ) or item.get(
                "published-online"
            ) or item.get(
                "published"
            )

            publication_year = None

            if published:

                date_parts = published.get(
                    "date-parts",
                    []
                )

                if date_parts:

                    if date_parts[0]:

                        publication_year = (
                            date_parts[0][0]
                        )

            paper = {

                "Paper_ID":
                    generate_paper_id(
                        item.get("DOI"),
                        title,
                        authors
                    ),

                "Title":
                    title,

                "Authors":
                    authors,

                "Publication_Year":
                    publication_year,

                "Journal":
                    (
                        item.get(
                            "container-title",
                            [None]
                        )[0]
                        if item.get(
                            "container-title"
                        )
                        else None
                    ),

                "DOI":
                    item.get(
                        "DOI",
                        None
                    ),

                "Paper_URL":
                    (
                        f"https://doi.org/"
                        f"{item.get('DOI')}"
                        if item.get("DOI")
                        else None
                    ),

                "Source":
                    "Crossref",

                "Abstract":
                    item.get(
                        "abstract",
                        None
                    ),

                "Keywords":
                    item.get(
                        "subject",
                        []
                    ),

                "Country":
                    None,

                "Research_Location":
                    None,

                "Discovery_Date":
                    datetime.now().isoformat(
                        timespec="seconds"
                    ),
            }

            papers.append(
                paper
            )

        return papers

    except requests.RequestException as e:

        raise RuntimeError(
            f"Crossref search failed: {e}"
        )

    except Exception as e:

        raise RuntimeError(
            f"Paper discovery failed: {e}"
        )

def _normalize_text(value):
    """
    Normalize text for duplicate comparison.
    """

    if not value:
        return ""

    return " ".join(
        str(value)
        .lower()
        .strip()
        .split()
    )


def _paper_duplicate_key(paper):
    """
    Create reliable duplicate keys.

    Priority:
    1. DOI
    2. Paper URL
    3. Title + Authors
    """

    doi = _normalize_text(
        paper.get("DOI")
    )

    if doi:
        return (
            "DOI",
            doi
        )

    paper_url = _normalize_text(
        paper.get("Paper_URL")
    )

    if paper_url:
        return (
            "URL",
            paper_url
        )

    title = _normalize_text(
        paper.get("Title")
    )

    authors = paper.get(
        "Authors",
        []
    )

    normalized_authors = [
        _normalize_text(author)
        for author in authors
    ]

    normalized_authors = [
        author
        for author in normalized_authors
        if author
    ]

    if title:

        return (
            "TITLE_AUTHORS",
            title,
            tuple(normalized_authors)
        )

    return (
        "PAPER_ID",
        paper.get(
            "Paper_ID"
        )
    )


def deduplicate_papers(papers):
    """
    Remove likely duplicate papers from
    a discovered paper list.

    Returns:
        unique_papers,
        duplicate_papers
    """

    unique_papers = []
    duplicate_papers = []

    seen = {}

    for paper in papers:

        key = _paper_duplicate_key(
            paper
        )

        if key in seen:

            duplicate_paper = dict(
                paper
            )

            duplicate_paper[
                "Eligibility"
            ] = "DUPLICATE"

            duplicate_paper[
                "Duplicate_Of"
            ] = seen[key].get(
                "Paper_ID"
            )

            duplicate_papers.append(
                duplicate_paper
            )

        else:

            paper_record = dict(
                paper
            )

            paper_record[
                "Eligibility"
            ] = "UNCLASSIFIED"

            paper_record[
                "Duplicate_Of"
            ] = None

            seen[key] = paper_record

            unique_papers.append(
                paper_record
            )

    return (
        unique_papers,
        duplicate_papers
    )
