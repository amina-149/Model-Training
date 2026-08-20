import os
import re
import requests
import csv
import streamlit as st
from datetime import datetime
from pathlib import Path

from src.image_generator import generate_image
from src.pdf_processor import (
    extract_pdf_metadata,
    extract_text_from_pdf
)
from src.ai_service import analyze_paper
from src.prompt_generator import generate_image_prompts
from src.figure_extractor import extract_figures
from src.figure_labeler import generate_figure_label
from src.duplicate_detector import detect_duplicate
from src.paper_sources import get_approved_sources
from src.paper_discovery import (
    search_papers,
    deduplicate_papers
)
from src.paper_relevance import calculate_paper_relevance

st.set_page_config(
    page_title="Kisan Pukar Research Agent",
    page_icon="🌾",
    layout="wide"
)

st.title("🌾 Kisan Pukar Research Agent")
st.write("AI-powered research paper analysis for agriculture.")


# =========================================================
# STEP 10A TEST
# =========================================================

approved_sources = get_approved_sources()

st.write("### 🔎  Sources")

for source_id, source in approved_sources.items():

    st.write(
        f"**{source_id}** — "
        f"{source['name']} "
        f"({source['category']})"
    )

# =========================================================
# SESSION STATE
# =========================================================

if "analysis" not in st.session_state:
    st.session_state.analysis = None

if "selected_discovery_paper" not in st.session_state:
    st.session_state.selected_discovery_paper = None

if "discovered_papers" not in st.session_state:
    st.session_state.discovered_papers = []

if "prompts" not in st.session_state:
    st.session_state.prompts = None

if "generated_images" not in st.session_state:
    st.session_state.generated_images = {}

if "figures" not in st.session_state:
    st.session_state.figures = []

if "figure_labels" not in st.session_state:
    st.session_state.figure_labels = {}

# STEP 8
if "validation_queue" not in st.session_state:
    st.session_state.validation_queue = {}

if "selected_paper_pdf_path" not in st.session_state:
    st.session_state.selected_paper_pdf_path = None

def get_open_access_pdf_url(doi):
    """
    Find an openly accessible PDF URL using Unpaywall.
    Returns the PDF URL if available, otherwise None.
    """

    if not doi:
        return None

    # IMPORTANT:
    # Replace this with your email address.
    email = "YOUR_EMAIL@example.com"

    try:

        url = (
            f"https://api.unpaywall.org/v2/"
            f"{doi}?email={email}"
        )

        response = requests.get(
            url,
            timeout=20
        )

        response.raise_for_status()

        data = response.json()

        best_location = data.get(
            "best_oa_location"
        )

        if best_location:

            pdf_url = best_location.get(
                "url_for_pdf"
            )

            if pdf_url:
                return pdf_url

        return None

    except Exception as e:

        print(
            f"Unpaywall lookup failed: {e}"
        )

        return None



# =========================================================
# STEP 10B — PAPER DISCOVERY TEST
# =========================================================

st.divider()

st.header("📚 Paper Discovery")

search_query = st.text_input(
    "Search Research Papers",
    placeholder="Example: Pakistan wheat disease"
)

if st.button(
    "🔎 Search Papers",
    key="search_papers"
):

    if not search_query.strip():

        st.warning(
            "Please enter a research topic."
        )

    else:

        with st.spinner(
            "Searching research papers..."
        ):

            try:

                discovered_papers = search_papers(
                    search_query,
                    rows=10
                )

                unique_papers, duplicate_papers = (
                    deduplicate_papers(
                        discovered_papers
                    )
                )

                st.session_state.discovered_papers = (
                    unique_papers
                )

                if unique_papers:

                    st.success(
                        f"{len(unique_papers)} "
                        f"unique paper(s) discovered."
                    )

                    if duplicate_papers:

                        st.info(
                            f"{len(duplicate_papers)} "
                            f"duplicate paper(s) detected "
                            f"and excluded from the unique results."
                        )

                else:

                    st.info(
                        "No papers found."
                    )

            except Exception as e:

                st.error(
                    f"Paper search failed: {e}"
                )

if st.session_state.discovered_papers:

    for paper in st.session_state.discovered_papers:

        relevance_result = calculate_paper_relevance(
            paper,
            search_query
        )

        paper.update(
            relevance_result
        )

        st.markdown(
            f"### 📄 {paper['Title']}"
        )

        st.write(
            "**Paper ID:**",
            paper.get(
                "Paper_ID",
                "UNKNOWN"
            )
        )

        st.write(
            "**Eligibility:**",
            paper.get(
                "Eligibility",
                "UNCLASSIFIED"
            )
        )

        st.write(
            "**Relevance Score:**",
            paper.get(
                "Relevance_Score",
                0
            )
        )

        st.write(
            "**Duplicate Of:**",
            paper.get(
                "Duplicate_Of"
            ) or "None"
        )

        st.write(
            "**Authors:**",
            ", ".join(
                paper["Authors"]
            )
            if paper["Authors"]
            else "UNKNOWN"
        )

        st.write(
            "**Publication Year:**",
            paper["Publication_Year"]
            or "UNKNOWN"
        )

        st.write(
            "**Journal:**",
            paper["Journal"]
            or "UNKNOWN"
        )

        st.write(
            "**DOI:**",
            paper["DOI"]
            or "UNKNOWN"
        )

        st.write(
            "**Paper URL:**",
            paper["Paper_URL"]
            or "UNKNOWN"
        )

        st.write(
            "**Source:**",
            paper["Source"]
        )

        if st.button(
            "📌 Select This Paper",
            key=f"select_paper_{paper['Paper_ID']}"
        ):

            st.session_state.selected_discovery_paper = (
                paper
            )

            st.success(
                "✅ Paper selected successfully."
            )

        st.divider()


# =========================================================
# CSV FUNCTIONS — STEP 8
# =========================================================

VALIDATION_CSV = os.path.join(
    "data",
    "agronomist_validation.csv"
)


def save_validation_to_csv(
    paper_id,
    image_record,
    validation_data
):
    """
    Save or update agronomist validation
    in data/agronomist_validation.csv
    """

    os.makedirs("data", exist_ok=True)

    csv_columns = [
        "Paper_ID",
        "Image_ID",
        "Figure_Number",
        "Page_Number",

        "Paper_Title",
        "Authors",
        "Journal",
        "DOI",
        "Paper_URL",

        "Visual_Type",
        "CV_Category",

        "Paper_Label",
        "AI_Prediction",
        "Label_Source",

        "Crop",
        "Condition",
        "Disease_Name",
        "Pest_Name",
        "Nutrient",
        "Stress_Type",
        "Plant_Part",
        "Severity",
        "Original_Severity",
        "Growth_Stage",
        "Original_Growth_Stage",

        "Image_Quality",
        "CV_Suitability_Score",
        "CV_Suitability_Category",
        "Permission_Status",

        "Crop_Correctness",
        "Condition_Correctness",
        "Disease_Pest_Stress_Correctness",
        "CV_Useful",
        "Severity_Correctness",

        "Expert_Label",
        "Expert_Confidence",
        "Validation_Status",

        "Validation_Date",
        "Expert_Name",
        "Expert_Notes"
    ]

    image_id = image_record.get(
        "Image_ID",
        ""
    )

    # -----------------------------------------------------
    # Create new validation row
    # -----------------------------------------------------

    new_row = {

        "Paper_ID": paper_id,

        "Image_ID": image_id,

        "Figure_Number": image_record.get(
            "Figure_Number",
            "UNKNOWN"
        ),

        "Page_Number": image_record.get(
            "Page_Number",
            "UNKNOWN"
        ),

        "Paper_Title": image_record.get(
            "Paper_Title",
            "UNKNOWN"
        ),

        "Authors": image_record.get(
            "Authors",
            "UNKNOWN"
        ),

        "Journal": image_record.get(
            "Journal",
            "UNKNOWN"
        ),

        "DOI": image_record.get(
            "DOI",
            "UNKNOWN"
        ),

        "Paper_URL": image_record.get(
            "Paper_URL",
            "UNKNOWN"
        ),

        "Visual_Type": image_record.get(
            "Visual_Type",
            "UNKNOWN"
        ),

        "CV_Category": image_record.get(
            "CV_Category",
            "UNKNOWN"
        ),

        "Paper_Label": image_record.get(
            "Paper_Label",
            "UNKNOWN"
        ),

        "AI_Prediction": image_record.get(
            "AI_Prediction",
            "UNKNOWN"
        ),

        "Label_Source": image_record.get(
            "Label_Source",
            "UNKNOWN"
        ),

        "Crop": image_record.get(
            "Crop",
            "UNKNOWN"
        ),

        "Condition": image_record.get(
            "Condition",
            "UNKNOWN"
        ),

        "Disease_Name": image_record.get(
            "Disease_Name",
            "UNKNOWN"
        ),

        "Pest_Name": image_record.get(
            "Pest_Name",
            "UNKNOWN"
        ),

        "Nutrient": image_record.get(
            "Nutrient",
            "UNKNOWN"
        ),

        "Stress_Type": image_record.get(
            "Stress_Type",
            "UNKNOWN"
        ),

        "Plant_Part": image_record.get(
            "Plant_Part",
            "UNKNOWN"
        ),

        "Severity": image_record.get(
            "Severity",
            "UNKNOWN"
        ),

        "Original_Severity": image_record.get(
            "Original_Severity",
            "NOT_REPORTED"
        ),

        "Growth_Stage": image_record.get(
            "Growth_Stage",
            "UNKNOWN"
        ),

        "Original_Growth_Stage": image_record.get(
            "Original_Growth_Stage",
            "NOT_REPORTED"
        ),

        "Image_Quality": str(
            image_record.get(
                "Image_Quality",
                {}
            )
        ),

        "Permission_Status": str(
            image_record.get(
                "Permission_Status",
                {}
            )
        ),

        "CV_Suitability_Score": image_record.get(
            "CV_Suitability",
            {}
        ).get(
            "score",
            "N/A"
        ),

        "CV_Suitability_Category": image_record.get(
            "CV_Suitability",
            {}
        ).get(
            "category",
            "UNKNOWN"
        ),

        # -------------------------------
        # AGRONOMIST VALIDATION
        # -------------------------------

        "Crop_Correctness":
            validation_data.get(
                "Crop_Correctness",
                "UNCERTAIN"
            ),

        "Condition_Correctness":
            validation_data.get(
                "Condition_Correctness",
                "UNCERTAIN"
            ),

        "Disease_Pest_Stress_Correctness":
            validation_data.get(
                "Disease_Pest_Stress_Correctness",
                "UNCERTAIN"
            ),

        "CV_Useful":
            validation_data.get(
                "CV_Useful",
                "UNCERTAIN"
            ),

        "Severity_Correctness":
            validation_data.get(
                "Severity_Correctness",
                "UNCERTAIN"
            ),

        # IMPORTANT:
        # Expert label comes ONLY from expert input
        "Expert_Label":
            validation_data.get(
                "Expert_Label",
                "PENDING"
            ),

        "Expert_Confidence":
            validation_data.get(
                "Expert_Confidence",
                "MEDIUM"
            ),

        "Validation_Status":
            validation_data.get(
                "Validation_Status",
                "PENDING"
            ),

        "Validation_Date":
            validation_data.get(
                "Validation_Date",
                None
            ),

        "Expert_Name":
            validation_data.get(
                "Expert_Name",
                ""
            ),

        "Expert_Notes":
            validation_data.get(
                "Expert_Notes",
                ""
            )
    }


    # -----------------------------------------------------
    # Read existing CSV
    # -----------------------------------------------------

    existing_rows = []

    if os.path.exists(VALIDATION_CSV):

        try:

            with open(
                VALIDATION_CSV,
                "r",
                newline="",
                encoding="utf-8"
            ) as csv_file:

                reader = csv.DictReader(
                    csv_file
                )

                for row in reader:
                    existing_rows.append(row)

        except Exception as e:

            print(
                f"Could not read validation CSV: {e}"
            )


    # -----------------------------------------------------
    # Update existing record OR add new record
    # -----------------------------------------------------

    record_found = False

    for index, row in enumerate(
        existing_rows
    ):

        if (
            row.get("Paper_ID") == paper_id
            and
            row.get("Image_ID") == image_id
        ):

            existing_rows[index] = new_row

            record_found = True

            break


    if not record_found:

        existing_rows.append(
            new_row
        )


    # -----------------------------------------------------
    # Write CSV
    # -----------------------------------------------------

    with open(
        VALIDATION_CSV,
        "w",
        newline="",
        encoding="utf-8"
    ) as csv_file:

        writer = csv.DictWriter(
            csv_file,
            fieldnames=csv_columns
        )

        writer.writeheader()

        writer.writerows(
            existing_rows
        )

# =========================================================
# STEP 10F — SELECTED PAPER
# =========================================================

if st.session_state.selected_discovery_paper:

    selected_paper = (
        st.session_state.selected_discovery_paper
    )

    st.divider()

    st.header("📌 Selected Research Paper")

    st.write(
        "**Title:**",
        selected_paper.get(
            "Title",
            "UNKNOWN"
        )
    )

    st.write(
        "**Paper ID:**",
        selected_paper.get(
            "Paper_ID",
            "UNKNOWN"
        )
    )

    st.write(
        "**Eligibility:**",
        selected_paper.get(
            "Eligibility",
            "UNCLASSIFIED"
        )
    )

    st.write(
        "**Relevance Score:**",
        selected_paper.get(
            "Relevance_Score",
            0
        )
    )

    st.write(
        "**Authors:**",
        ", ".join(
            selected_paper.get(
                "Authors",
                []
            )
        )
        if selected_paper.get("Authors")
        else "UNKNOWN"
    )

    st.write(
        "**Publication Year:**",
        selected_paper.get(
            "Publication_Year"
        ) or "UNKNOWN"
    )

    st.write(
        "**Journal:**",
        selected_paper.get(
            "Journal"
        ) or "UNKNOWN"
    )

    st.write(
        "**DOI:**",
        selected_paper.get(
            "DOI"
        ) or "UNKNOWN"
    )

    paper_url = selected_paper.get(
        "Paper_URL"
    )

    if paper_url:

        st.markdown(
            f"**Paper URL:** [{paper_url}]({paper_url})"
        )

    else:

        st.write(
            "**Paper URL:** UNKNOWN"
        )

    st.write(
        "**Source:**",
        selected_paper.get(
            "Source",
            "UNKNOWN"
        )
    )

    # =========================================================
    # STEP 10F — DOWNLOAD / OPEN PAPER PDF
    # =========================================================

    paper_url = selected_paper.get("Paper_URL")
    if paper_url:
        st.link_button(
            "📄 Open Research Paper",
            paper_url
        )

    else:
        st.warning(
            "No paper URL available for this paper."
        )



# =========================================================
# PDF UPLOAD
# =========================================================

st.header("📄 Upload Research Paper (PDF)")
uploaded_file = st.file_uploader(
    "Upload your research paper in PDF format",
    type=["pdf"]
)


if uploaded_file:

    os.makedirs(
        "data",
        exist_ok=True
    )

    pdf_path = os.path.join(
        "data",
        uploaded_file.name
    )

    paper_id = Path(
        uploaded_file.name
    ).stem

    with open(
        pdf_path,
        "wb"
    ) as f:

        f.write(
            uploaded_file.getbuffer()
        )


    # =====================================================
    # METADATA
    # =====================================================

    st.header("📄 Paper Information")

    metadata = extract_pdf_metadata(
        pdf_path
    )

    col1, col2, col3 = st.columns(3)

    with col1:

        st.write("**File Name:**")

        st.write(
            metadata.get(
                "file_name",
                "N/A"
            )
        )

        st.write("**File Type:**")

        st.write(
            metadata.get(
                "file_type",
                "PDF"
            )
        )

    with col2:

        st.write("**File Size:**")

        st.write(
            metadata.get(
                "file_size",
                "N/A"
            )
        )

        st.write("**Pages:**")

        st.write(
            metadata.get(
                "pages",
                "N/A"
            )
        )

    with col3:

        st.write("**Title:**")

        st.write(
            metadata.get(
                "title",
                "N/A"
            )
        )

        st.write("**Authors:**")

        st.write(
            metadata.get(
                "authors",
                "N/A"
            )
        )


    # =====================================================
    # EXTRACT TEXT
    # =====================================================

    text = extract_text_from_pdf(
        pdf_path
    )


    # =====================================================
    # AI ANALYSIS
    # =====================================================

    st.header("🤖 AI Paper Analysis")

    if st.button(
        "Analyze Research Paper"
    ):

        with st.spinner(
            "Analyzing research paper..."
        ):

            try:

                result = analyze_paper(
                    text
                )

                st.session_state.analysis = result

            except Exception as e:

                st.error(
                    f"AI analysis failed: {e}"
                )


    # =====================================================
    # DISPLAY ANALYSIS
    # =====================================================

    if st.session_state.analysis:

        analysis = (
            st.session_state.analysis
        )

        st.subheader(
            "📋 Paper Summary"
        )

        st.write(
            analysis.short_summary
        )

        col1, col2 = st.columns(2)

        with col1:

            st.markdown(
                "### 🦠 Disease"
            )

            st.write(
                analysis.disease_name
            )

            st.markdown(
                "### 🌱 Affected Crop"
            )

            st.write(
                analysis.affected_crop
            )

        with col2:

            st.markdown(
                "### 🔬 Pathogen"
            )

            st.write(
                analysis.pathogen
            )

            st.markdown(
                "### 💡 Key Finding"
            )

            st.write(
                analysis.key_finding
            )


    # =====================================================
    # IMAGE PROMPTS
    # =====================================================

    st.header(
        "🎨 AI Image Prompts"
    )

    if st.button(
        "Generate Image Prompts"
    ):

        if not st.session_state.analysis:

            st.warning(
                "Please analyze the research paper first."
            )

        else:

            with st.spinner(
                "Generating image prompts..."
            ):

                try:

                    prompts = generate_image_prompts(
                        text,
                        st.session_state.analysis
                    )

                    st.session_state.prompts = (
                        prompts
                    )

                except Exception as e:

                    st.error(
                        f"Prompt generation failed: {e}"
                    )


    # =====================================================
    # DISPLAY PROMPTS + GENERATE IMAGES
    # =====================================================

    if st.session_state.prompts:

        prompts = (
            st.session_state.prompts
        )

        if isinstance(
            prompts,
            str
        ):

            prompts = re.split(
                r"PROMPT\s*\d+\s*:",
                prompts,
                flags=re.IGNORECASE
            )

            prompts = [
                p.strip()
                for p in prompts
                if p.strip()
            ]

        prompts = prompts[:3]

        for i, prompt in enumerate(
            prompts,
            start=1
        ):

            st.subheader(
                f"Prompt {i}"
            )

            st.text_area(
                f"AI Image Prompt {i}",
                prompt,
                height=180,
                key=f"prompt_display_{i}"
            )

            if st.button(
                f"Generate Image {i}",
                key=f"generate_image_{i}"
            ):

                output_folder = os.path.join(
                    "outputs",
                    "images"
                )

                os.makedirs(
                    output_folder,
                    exist_ok=True
                )

                timestamp = datetime.now().strftime(
                    "%Y%m%d_%H%M%S_%f"
                )

                output_path = os.path.join(
                    output_folder,
                    f"prompt_{i}_{timestamp}.png"
                )

                with st.spinner(
                    f"Generating Image {i} with ClipDrop..."
                ):

                    try:

                        image_path = generate_image(
                            prompt,
                            output_path
                        )

                        st.session_state.generated_images[i] = (
                            image_path
                        )

                        st.success(
                            f"Image {i} generated successfully!"
                        )

                    except Exception as e:

                        st.error(
                            f"Image generation failed: {e}"
                        )


            if i in st.session_state.generated_images:

                image_path = (
                    st.session_state.generated_images[i]
                )

                if os.path.exists(
                    image_path
                ):

                    st.image(
                        image_path,
                        caption=f"Generated Image {i}",
                        width=400
                    )

                    with open(
                        image_path,
                        "rb"
                    ) as image_file:

                        st.download_button(
                            "⬇️ Download Image",
                            image_file,
                            file_name=os.path.basename(
                                image_path
                            ),
                            mime="image/png",
                            key=f"download_image_{i}"
                        )


    # =====================================================
    # EXTRACT FIGURES
    # =====================================================

    st.header(
        "🖼️ Extract Figures"
    )

    if st.button(
        "Extract Figures from Paper"
    ):

        with st.spinner(
            "Extracting figures from research paper..."
        ):

            try:

                extracted_figures = extract_figures(
                    pdf_path
                )

                st.session_state.figures = (
                    extracted_figures
                )

                st.session_state.figure_labels = {}

                st.session_state.validation_queue = {}


                if extracted_figures:

                    with st.spinner(
                        "Analyzing extracted figures with AI..."
                    ):

                        st.session_state.figure_labels = {}

                        for figure in extracted_figures:

                            image_path = figure[
                                "image_path"
                            ]

                            try:

                                image_record = generate_figure_label(
                                    figure,
                                    paper_id
                                )

                                image_record[
                                    "Paper_ID"
                                ] = paper_id

                                image_record[
                                    "Figure_Number"
                                ] = figure.get(
                                    "figure_number",
                                    "UNKNOWN"
                                )

                                image_record[
                                    "Page_Number"
                                ] = figure.get(
                                    "page_number",
                                    "UNKNOWN"
                                )

                                image_record[
                                    "Image_ID"
                                ] = (
                                    f"{paper_id}_IMG_"
                                    f"{int(figure.get('figure_number', 0)):03d}"
                                )


                                # =================================================
                                # SOURCE METADATA — so every image can be traced
                                # back to its exact paper (Title/Authors/Journal/
                                # DOI/URL), not only a filename-derived Paper_ID.
                                #
                                # Prefer the discovery-selected paper's metadata
                                # (Crossref) when available; fall back to what
                                # could be read from the uploaded PDF's own
                                # metadata.
                                # =================================================

                                discovery_paper = (
                                    st.session_state.selected_discovery_paper
                                    or {}
                                )

                                pdf_title = metadata.get("title", "Not available")
                                pdf_authors = metadata.get("authors", "Not available")

                                image_record["Paper_Title"] = (
                                    discovery_paper.get("Title")
                                    or (
                                        pdf_title
                                        if pdf_title not in {None, "", "Not available"}
                                        else "UNKNOWN"
                                    )
                                )

                                discovery_authors = discovery_paper.get("Authors")
                                if discovery_authors:
                                    image_record["Authors"] = ", ".join(discovery_authors)
                                elif pdf_authors not in {None, "", "Not available"}:
                                    image_record["Authors"] = pdf_authors
                                else:
                                    image_record["Authors"] = "UNKNOWN"

                                image_record["Journal"] = (
                                    discovery_paper.get("Journal") or "UNKNOWN"
                                )

                                image_record["DOI"] = (
                                    discovery_paper.get("DOI") or "UNKNOWN"
                                )

                                image_record["Paper_URL"] = (
                                    discovery_paper.get("Paper_URL") or "UNKNOWN"
                                )

                                image_record["Research_Institute"] = "UNKNOWN"


                                # =================================================
                                # STEP 5 — DUPLICATE DETECTION
                                # =================================================

                                try:

                                    previous_images = []

                                    for previous_record in (
                                        st.session_state.figure_labels.values()
                                    ):

                                        duplicate_status = (
                                            previous_record.get(
                                                "Duplicate_Status",
                                                {}
                                            )
                                        )

                                        if (
                                            duplicate_status.get(
                                                "image_hash"
                                            )
                                            and
                                            duplicate_status.get(
                                                "perceptual_hash"
                                            )
                                        ):

                                            previous_images.append(
                                                {
                                                    "Image_ID":
                                                        previous_record.get(
                                                            "Image_ID"
                                                        ),

                                                    "image_hash":
                                                        duplicate_status.get(
                                                            "image_hash"
                                                        ),

                                                    "perceptual_hash":
                                                        duplicate_status.get(
                                                            "perceptual_hash"
                                                        )
                                                }
                                            )


                                    duplicate_result = detect_duplicate(
                                        image_path,
                                        image_record[
                                            "Image_ID"
                                        ],
                                        previous_images
                                    )

                                    image_record[
                                        "Duplicate_Status"
                                    ] = duplicate_result


                                except Exception as duplicate_error:

                                    image_record[
                                        "Duplicate_Status"
                                    ] = {

                                        "status":
                                            "UNIQUE",

                                        "image_hash":
                                            None,

                                        "perceptual_hash":
                                            None,

                                        "similarity_score":
                                            0.0,

                                        "matched_image_id":
                                            None
                                    }

                                    print(
                                        "Duplicate detection error: "
                                        f"{duplicate_error}"
                                    )


                                # =================================================
                                # STEP 8 — INITIAL VALIDATION
                                # =================================================

                                image_record[
                                    "Validation"
                                ] = {

                                    "Permission_Status":
                                        "LICENSE_UNKNOWN",

                                    "Crop_Correctness":
                                        "UNCERTAIN",

                                    "Condition_Correctness":
                                        "UNCERTAIN",

                                    "Disease_Pest_Stress_Correctness":
                                        "UNCERTAIN",

                                    "CV_Useful":
                                        "UNCERTAIN",

                                    "Severity_Correctness":
                                        "UNCERTAIN",

                                    "Expert_Label":
                                        "PENDING",

                                    "Expert_Confidence":
                                        "MEDIUM",

                                    "Validation_Status":
                                        "PENDING",

                                    "Validation_Date":
                                        None,

                                    "Expert_Name":
                                        "",

                                    "Expert_Notes":
                                        ""
                                }


                                st.session_state.figure_labels[
                                    image_path
                                ] = image_record


                            except Exception as e:

                                st.error(
                                    f"Figure "
                                    f"{figure.get('figure_number', 'UNKNOWN')} "
                                    f"analysis failed: {e}"
                                )

                                print(
                                    f"Figure analysis error: {e}"
                                )


                    st.success(
                        f"{len(extracted_figures)} "
                        f"figure(s) extracted and analyzed successfully!"
                    )

                else:

                    st.info(
                        "No figures found in the research paper."
                    )


            except Exception as e:

                st.error(
                    f"Figure extraction failed: {e}"
                )


    # =====================================================
    # DISPLAY EXTRACTED FIGURES
    # =====================================================

    if st.session_state.figures:

        st.subheader(
            "📸 Extracted Figures"
        )

        cols = st.columns(3)

        for i, figure in enumerate(
            st.session_state.figures
        ):

            with cols[i % 3]:

                image_path = figure[
                    "image_path"
                ]

                st.image(
                    image_path,
                    width=250
                )

                figure_number = figure.get(
                    "figure_number",
                    i + 1
                )

                page_number = figure.get(
                    "page_number",
                    "UNKNOWN"
                )

                st.markdown(
                    f"**Figure {figure_number}**"
                )

                st.write(
                    f"**Page:** {page_number}"
                )

                image_record = (
                    st.session_state.figure_labels.get(
                        image_path,
                        None
                    )
                )

                if image_record:

                    st.json(
                        image_record
                    )

                else:

                    st.info(
                        "No structured record available."
                    )

                with open(
                    image_path,
                    "rb"
                ) as file:

                    st.download_button(
                        "⬇️ Download",
                        file,
                        file_name=os.path.basename(
                            image_path
                        ),
                        mime="image/jpeg",
                        key=f"download_figure_{i}"
                    )


    # =========================================================
    # STEP 8 — AGRONOMIST VALIDATION QUEUE
    # =========================================================

    if (
        st.session_state.figures
        and
        st.session_state.figure_labels
    ):

        st.divider()

        st.header(
            "👨‍🌾 Agronomist Validation Queue"
        )

        st.info(
            "Review each extracted agricultural image and validate "
            "the AI-generated metadata. AI predictions do not become "
            "Expert Labels automatically."
        )


        # =====================================================
        # CREATE VALIDATION QUEUE
        # =====================================================

        for i, figure in enumerate(
            st.session_state.figures
        ):

            image_path = figure.get(
                "image_path"
            )

            image_record = (
                st.session_state.figure_labels.get(
                    image_path
                )
            )

            if not image_record:
                continue

            image_id = image_record.get(
                "Image_ID",
                f"IMAGE_{i + 1}"
            )


            if (
                image_id
                not in
                st.session_state.validation_queue
            ):

                existing_validation = (
                    image_record.get(
                        "Validation",
                        {}
                    )
                )

                st.session_state.validation_queue[
                    image_id
                ] = {

                    "Crop_Correctness":
                        existing_validation.get(
                            "Crop_Correctness",
                            "UNCERTAIN"
                        ),

                    "Condition_Correctness":
                        existing_validation.get(
                            "Condition_Correctness",
                            "UNCERTAIN"
                        ),

                    "Disease_Pest_Stress_Correctness":
                        existing_validation.get(
                            "Disease_Pest_Stress_Correctness",
                            "UNCERTAIN"
                        ),

                    "CV_Useful":
                        existing_validation.get(
                            "CV_Useful",
                            "UNCERTAIN"
                        ),

                    "Severity_Correctness":
                        existing_validation.get(
                            "Severity_Correctness",
                            "UNCERTAIN"
                        ),

                    "Expert_Label":
                        existing_validation.get(
                            "Expert_Label",
                            "PENDING"
                        ),

                    "Expert_Confidence":
                        existing_validation.get(
                            "Expert_Confidence",
                            "MEDIUM"
                        ),

                    "Validation_Status":
                        existing_validation.get(
                            "Validation_Status",
                            "PENDING"
                        ),

                    "Validation_Date":
                        existing_validation.get(
                            "Validation_Date",
                            None
                        ),

                    "Expert_Name":
                        existing_validation.get(
                            "Expert_Name",
                            ""
                        ),

                    "Expert_Notes":
                        existing_validation.get(
                            "Expert_Notes",
                            ""
                        )
                }


            validation = (
                st.session_state.validation_queue[
                    image_id
                ]
            )


            # =================================================
            # VALIDATION CARD
            # =================================================

            with st.expander(
                f"🔎 {image_id} — Figure "
                f"{image_record.get('Figure_Number', 'UNKNOWN')}",
                expanded=True
            ):

                cv_category = image_record.get(
                    "CV_Category",
                    "UNKNOWN"
                )

                visual_type = image_record.get(
                    "Visual_Type",
                    "UNKNOWN"
                )

                if cv_category == "NON_CV":

                    st.error(
                        f"🚫 NON-CV VISUAL — classified as "
                        f"Visual_Type={visual_type}. This is not a "
                        f"photograph of agricultural subject matter "
                        f"(e.g. a table/graph/diagram) and can never "
                        f"enter the CV image dataset, regardless of "
                        f"agronomist validation."
                    )

                elif cv_category == "RESEARCH_VISUAL":

                    st.warning(
                        f"ℹ️ RESEARCH VISUAL — classified as "
                        f"Visual_Type={visual_type}. Useful for "
                        f"research context, but not standard CV "
                        f"training material."
                    )

                else:

                    st.success(
                        f"✅ CV IMAGE — classified as "
                        f"Visual_Type={visual_type}."
                    )

                left_col, right_col = st.columns(
                    [1, 2]
                )


                # =================================================
                # LEFT SIDE
                # =================================================

                with left_col:

                    st.markdown(
                        "### 🖼️ Extracted Image"
                    )

                    if os.path.exists(
                        image_path
                    ):

                        st.image(
                            image_path,
                            width=350
                        )

                    else:

                        st.warning(
                            "Image file not found."
                        )

                    st.write(
                        f"**Image ID:** {image_id}"
                    )

                    st.write(
                        f"**Figure:** "
                        f"{image_record.get('Figure_Number', 'UNKNOWN')}"
                    )

                    st.write(
                        f"**Page:** "
                        f"{image_record.get('Page_Number', 'UNKNOWN')}"
                    )


                # =================================================
                # RIGHT SIDE
                # =================================================

                with right_col:

                    st.markdown(
                        "### 📄 Paper & Figure Information"
                    )

                    st.write(
                        "**Paper Title:**",
                        image_record.get(
                            "Paper_Title",
                            metadata.get("title", "N/A")
                        )
                    )

                    st.write(
                        "**Authors:**",
                        image_record.get(
                            "Authors",
                            "UNKNOWN"
                        )
                    )

                    st.write(
                        "**Journal:**",
                        image_record.get(
                            "Journal",
                            "UNKNOWN"
                        )
                    )

                    st.write(
                        "**DOI:**",
                        image_record.get(
                            "DOI",
                            "UNKNOWN"
                        )
                    )

                    st.write(
                        "**Paper URL:**",
                        image_record.get(
                            "Paper_URL",
                            "UNKNOWN"
                        )
                    )

                    st.write(
                        "**Figure Number:**",
                        image_record.get(
                            "Figure_Number",
                            "UNKNOWN"
                        )
                    )

                    st.write(
                        "**Page Number:**",
                        image_record.get(
                            "Page_Number",
                            "UNKNOWN"
                        )
                    )

                    st.write(
                        "**Original Figure Caption:**",
                        image_record.get(
                            "Caption",
                            "UNKNOWN"
                        )
                    )

                    st.write(
                        "**Context:**",
                        image_record.get(
                            "Context",
                            "UNKNOWN"
                        )
                    )

                    st.write(
                        "**Evidence Text:**",
                        image_record.get(
                            "Evidence_Text",
                            "UNKNOWN"
                        )
                    )


                    # =================================================
                    # VISUAL CLASSIFICATION (SPEC §5-6)
                    # =================================================

                    st.markdown(
                        "### 🏷️ Visual Classification"
                    )

                    visual_col1, visual_col2 = st.columns(2)

                    with visual_col1:

                        st.write(
                            "**Visual_Type:**",
                            image_record.get(
                                "Visual_Type",
                                "UNKNOWN"
                            )
                        )

                    with visual_col2:

                        st.write(
                            "**CV_Category:**",
                            image_record.get(
                                "CV_Category",
                                "UNKNOWN"
                            )
                        )

                    st.write(
                        "**Label_Source:**",
                        image_record.get(
                            "Label_Source",
                            "UNKNOWN"
                        )
                    )


                    # =================================================
                    # AGRICULTURAL INFORMATION
                    # =================================================

                    st.markdown(
                        "### 🌱 Agricultural Information"
                    )

                    info_col1, info_col2 = st.columns(2)

                    with info_col1:

                        st.write(
                            "**Crop:**",
                            image_record.get(
                                "Crop",
                                "UNKNOWN"
                            )
                        )

                        st.write(
                            "**Condition:**",
                            image_record.get(
                                "Condition",
                                "UNKNOWN"
                            )
                        )

                        st.write(
                            "**Disease:**",
                            image_record.get(
                                "Disease_Name",
                                "UNKNOWN"
                            )
                        )

                        st.write(
                            "**Pest:**",
                            image_record.get(
                                "Pest_Name",
                                "UNKNOWN"
                            )
                        )

                        st.write(
                            "**Nutrient:**",
                            image_record.get(
                                "Nutrient",
                                "UNKNOWN"
                            )
                        )

                        st.write(
                            "**Stress Type:**",
                            image_record.get(
                                "Stress_Type",
                                "UNKNOWN"
                            )
                        )

                        st.write(
                            "**Plant Part:**",
                            image_record.get(
                                "Plant_Part",
                                "UNKNOWN"
                            )
                        )

                    with info_col2:

                        st.write(
                            "**Severity:**",
                            image_record.get(
                                "Severity",
                                "UNKNOWN"
                            )
                        )

                        st.caption(
                            "Original (paper) wording: "
                            + str(
                                image_record.get(
                                    "Original_Severity",
                                    "NOT_REPORTED"
                                )
                            )
                        )

                        st.write(
                            "**Growth Stage:**",
                            image_record.get(
                                "Growth_Stage",
                                "UNKNOWN"
                            )
                        )

                        st.caption(
                            "Original (paper) wording: "
                            + str(
                                image_record.get(
                                    "Original_Growth_Stage",
                                    "NOT_REPORTED"
                                )
                            )
                        )

                        st.write(
                            "**Country:**",
                            image_record.get(
                                "Country",
                                "UNKNOWN"
                            )
                        )

                        st.write(
                            "**Province:**",
                            image_record.get(
                                "Province",
                                "UNKNOWN"
                            )
                        )

                        st.write(
                            "**District:**",
                            image_record.get(
                                "District",
                                "UNKNOWN"
                            )
                        )

                        st.write(
                            "**Tehsil:**",
                            image_record.get(
                                "Tehsil",
                                "UNKNOWN"
                            )
                        )

                        st.write(
                            "**Village:**",
                            image_record.get(
                                "Village",
                                "UNKNOWN"
                            )
                        )

                        st.write(
                            "**Field Type:**",
                            image_record.get(
                                "Field_Type",
                                "UNKNOWN"
                            )
                        )


                    # =================================================
                    # AI RESULTS
                    # =================================================

                    st.markdown(
                        "### 🤖 AI / Existing Pipeline Results"
                    )

                    ai_col1, ai_col2 = st.columns(2)

                    with ai_col1:

                        st.write(
                            "**Paper Label:**",
                            image_record.get(
                                "Paper_Label",
                                "UNKNOWN"
                            )
                        )

                        st.write(
                            "**AI Prediction:**",
                            image_record.get(
                                "AI_Prediction",
                                "UNKNOWN"
                            )
                        )

                    with ai_col2:

                        st.write(
                            "**Image Quality:**"
                        )

                        st.json(
                            image_record.get(
                                "Image_Quality",
                                {}
                            )
                        )


                    # =================================================
                    # DUPLICATE
                    # =================================================

                    st.markdown(
                        "### 🔁 Duplicate Status"
                    )

                    st.json(
                        image_record.get(
                            "Duplicate_Status",
                            {}
                        )
                    )


                    # =================================================
                    # PERMISSION
                    # =================================================
                    
                    st.markdown(
                        "### 🔐 Permission / License Status"
                    )

                    permission_data = image_record.get(
                        "Permission_Status",
                        {}
                    )

                    permission_options = [
                        "PERMISSION_CONFIRMED",
                        "LICENSE_ALLOWS_REUSE",
                        "DO_NOT_USE",
                        "LICENSE_UNKNOWN"
                    ]

                    current_permission = "LICENSE_UNKNOWN"

                    if isinstance(permission_data, dict):
                        current_permission = permission_data.get(
                            "status",
                            "LICENSE_UNKNOWN"
                        )

                    current_permission = str(
                        current_permission
                    ).upper()

                    if current_permission not in permission_options:
                        current_permission = "LICENSE_UNKNOWN"

                    permission_status = st.selectbox(
                        "Permission / License",
                        permission_options,
                        index=permission_options.index(
                            current_permission
                        ),
                        key=f"permission_status_{image_id}"
                    )

                    st.json(
                        permission_data
                    )


                    # =================================================
                    # CV SUITABILITY
                    # =================================================

                    st.markdown(
                        "### 📊 CV Suitability"
                    )

                    cv_suitability = (
                        image_record.get(
                            "CV_Suitability",
                            {}
                        )
                    )

                    cv_score = cv_suitability.get(
                        "score",
                        "N/A"
                    )

                    cv_category = cv_suitability.get(
                        "category",
                        "UNKNOWN"
                    )

                    st.metric(
                        "CV Suitability Score",
                        cv_score
                    )

                    st.write(
                        f"**Category:** {cv_category}"
                    )

                    st.write(
                        "**Reason:**",
                        cv_suitability.get(
                            "reason",
                            "N/A"
                        )
                    )


                # =================================================
                # AGRONOMIST VALIDATION FORM
                # =================================================

                st.divider()

                st.markdown(
                    "## 👨‍🔬 Agronomist Validation"
                )

                st.caption(
                    "Select YES, NO, or UNCERTAIN for each validation item."
                )

                validation_col1, validation_col2 = (
                    st.columns(2)
                )


                # =================================================
                # CROP
                # =================================================

                with validation_col1:

                    crop_correctness = st.selectbox(
                        "1. Crop correctness",
                        [
                            "YES",
                            "NO",
                            "UNCERTAIN"
                        ],
                        index=[
                            "YES",
                            "NO",
                            "UNCERTAIN"
                        ].index(
                            validation.get(
                                "Crop_Correctness",
                                "UNCERTAIN"
                            )
                        ),
                        key=f"crop_validation_{image_id}"
                    )


                    # =================================================
                    # CONDITION
                    # =================================================

                    condition_correctness = st.selectbox(
                        "2. Condition correctness",
                        [
                            "YES",
                            "NO",
                            "UNCERTAIN"
                        ],
                        index=[
                            "YES",
                            "NO",
                            "UNCERTAIN"
                        ].index(
                            validation.get(
                                "Condition_Correctness",
                                "UNCERTAIN"
                            )
                        ),
                        key=f"condition_validation_{image_id}"
                    )


                    # =================================================
                    # DISEASE / PEST / STRESS
                    # =================================================

                    disease_pest_stress_correctness = st.selectbox(
                        "3. Disease/Pest/Stress label correctness",
                        [
                            "YES",
                            "NO",
                            "UNCERTAIN"
                        ],
                        index=[
                            "YES",
                            "NO",
                            "UNCERTAIN"
                        ].index(
                            validation.get(
                                "Disease_Pest_Stress_Correctness",
                                "UNCERTAIN"
                            )
                        ),
                        key=f"disease_validation_{image_id}"
                    )


                # =================================================
                # CV + SEVERITY
                # =================================================

                with validation_col2:

                    cv_useful = st.selectbox(
                        "4. Is this image useful for computer vision?",
                        [
                            "YES",
                            "NO",
                            "UNCERTAIN"
                        ],
                        index=[
                            "YES",
                            "NO",
                            "UNCERTAIN"
                        ].index(
                            validation.get(
                                "CV_Useful",
                                "UNCERTAIN"
                            )
                        ),
                        key=f"cv_validation_{image_id}"
                    )


                    severity_correctness = st.selectbox(
                        "5. Severity correctness",
                        [
                            "YES",
                            "NO",
                            "UNCERTAIN"
                        ],
                        index=[
                            "YES",
                            "NO",
                            "UNCERTAIN"
                        ].index(
                            validation.get(
                                "Severity_Correctness",
                                "UNCERTAIN"
                            )
                        ),
                        key=f"severity_validation_{image_id}"
                    )


                # =================================================
                # EXPERT LABEL
                # =================================================

                st.markdown(
                    "### 🏷️ Final Expert Label"
                )

                current_expert_label = (
                    validation.get(
                        "Expert_Label",
                        "PENDING"
                    )
                )

                expert_label = st.text_input(
                    "Confirmed label",

                    value=(
                        ""
                        if current_expert_label == "PENDING"
                        else current_expert_label
                    ),

                    placeholder="Enter expert-confirmed label",

                    key=f"expert_label_{image_id}"
                )


                # =================================================
                # EXPERT CONFIDENCE
                # =================================================

                expert_confidence = st.selectbox(
                    "Expert confidence",
                    [
                        "HIGH",
                        "MEDIUM",
                        "LOW"
                    ],
                    index=[
                        "HIGH",
                        "MEDIUM",
                        "LOW"
                    ].index(
                        validation.get(
                            "Expert_Confidence",
                            "MEDIUM"
                        )
                    ),
                    key=f"expert_confidence_{image_id}"
                )


                # =================================================
                # VALIDATION STATUS
                # =================================================

                validation_status = st.selectbox(
                    "Validation Status",
                    [
                        "PENDING",
                        "APPROVED",
                        "REJECTED",
                        "NEEDS_REVIEW"
                    ],
                    index=[
                        "PENDING",
                        "APPROVED",
                        "REJECTED",
                        "NEEDS_REVIEW"
                    ].index(
                        validation.get(
                            "Validation_Status",
                            "PENDING"
                        )
                    ),
                    key=f"validation_status_{image_id}"
                )


                # =================================================
                # EXPERT NAME
                # =================================================

                expert_name = st.text_input(
                    "Reviewer / Expert Name",

                    value=validation.get(
                        "Expert_Name",
                        ""
                    ),

                    placeholder="Enter expert name (optional)",

                    key=f"expert_name_{image_id}"
                )


                # =================================================
                # EXPERT NOTES
                # =================================================

                expert_notes = st.text_area(
                    "Expert Notes",

                    value=validation.get(
                        "Expert_Notes",
                        ""
                    ),

                    placeholder="Add validation notes...",

                    height=120,

                    key=f"expert_notes_{image_id}"
                )


                # =================================================
                # SAVE VALIDATION
                # =================================================

                if st.button(
                    "💾 Save Validation",
                    key=f"save_validation_{image_id}"
                ):

                    # -------------------------------------------------
                    # Expert label must NEVER automatically use AI label
                    # -------------------------------------------------

                    final_expert_label = (
                        expert_label.strip()
                    )

                    if not final_expert_label:

                        final_expert_label = (
                            "PENDING"
                        )


                    # -------------------------------------------------
                    # Automatically force NEEDS_REVIEW if uncertain
                    # -------------------------------------------------

                    if (
                        crop_correctness == "UNCERTAIN"
                        or
                        condition_correctness == "UNCERTAIN"
                        or
                        disease_pest_stress_correctness == "UNCERTAIN"
                        or
                        cv_useful == "UNCERTAIN"
                        or
                        severity_correctness == "UNCERTAIN"
                    ):

                        validation_status = (
                            "NEEDS_REVIEW"
                        )


                    # =================================================
                    # CREATE VALIDATION RECORD
                    # =================================================

                    saved_validation = {

                        "Permission_Status":
                            permission_status,

                        "Crop_Correctness":
                            crop_correctness,

                        "Condition_Correctness":
                            condition_correctness,

                        "Disease_Pest_Stress_Correctness":
                            disease_pest_stress_correctness,

                        "CV_Useful":
                            cv_useful,

                        "Severity_Correctness":
                            severity_correctness,

                        "Expert_Label":
                            final_expert_label,

                        "Expert_Confidence":
                            expert_confidence,

                        "Validation_Status":
                            validation_status,

                        "Validation_Date":
                            datetime.now().isoformat(
                                timespec="seconds"
                            ),

                        "Expert_Name":
                            expert_name.strip(),

                        "Expert_Notes":
                            expert_notes.strip()
                    }


                    # =================================================
                    # SAVE IN SESSION STATE
                    # =================================================

                    st.session_state.validation_queue[
                        image_id
                    ] = saved_validation


                    # =================================================
                    # SAVE INSIDE IMAGE RECORD
                    # =================================================

                    image_record[
                        "Validation"
                    ] = saved_validation

                    image_record[
                        "Permission_Status"
                    ] = {
                        "status": permission_status
                    }


                    # =================================================
                    # SAVE TO CSV
                    # =================================================

                    try:

                        save_validation_to_csv(
                            paper_id=paper_id,
                            image_record=image_record,
                            validation_data=saved_validation
                        )

                        st.success(
                            f"✅ Validation saved successfully for {image_id}"
                        )

                        st.info(
                            f"📁 CSV saved at: {VALIDATION_CSV}"
                        )

                    except Exception as csv_error:

                        st.error(
                            f"Validation saved in memory, "
                            f"but CSV save failed: {csv_error}"
                        )

                    st.rerun()

# =========================================================
# STEP 9 — FINAL APPROVED DATASET
# =========================================================

DATASET_CSV = os.path.join(
    "data",
    "final_dataset.csv"
)

if "dataset_records" not in st.session_state:
    st.session_state.dataset_records = {}


def load_dataset_records_from_csv():
    """Load previously saved Step 9 records so split rules survive reruns."""
    if not os.path.exists(DATASET_CSV):
        return

    try:
        with open(DATASET_CSV, "r", newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                image_id = row.get("Image_ID")
                if image_id:
                    st.session_state.dataset_records[image_id] = row
    except Exception as e:
        print(f"Could not load final dataset CSV: {e}")


load_dataset_records_from_csv()


def _permission_status_value(permission_status):
    """Return the main permission status from the existing record."""
    if isinstance(permission_status, dict):
        for key in ("status", "permission_status", "license_status", "Permission_Status"):
            value = permission_status.get(key)
            if value:
                return str(value).strip().upper()
    elif permission_status:
        return str(permission_status).strip().upper()

    return "LICENSE_UNKNOWN"


def _duplicate_group_id(image_record):
    """Build a stable duplicate group key without changing existing duplicate logic."""
    duplicate = image_record.get("Duplicate_Status", {}) or {}

    image_hash = duplicate.get("image_hash")
    if image_hash:
        return f"HASH:{image_hash}"

    perceptual_hash = duplicate.get("perceptual_hash")
    if perceptual_hash:
        return f"PHASH:{perceptual_hash}"

    matched_image_id = duplicate.get("matched_image_id")
    if matched_image_id:
        return f"MATCH:{matched_image_id}"

    return f"IMAGE:{image_record.get('Image_ID', '')}"


def _get_dataset_decision(image_record, validation):
    """Apply Step 9 approval rules to one image."""

    validation_status = str(
        validation.get("Validation_Status", "PENDING")
    ).upper()

    expert_label = str(
        validation.get("Expert_Label", "PENDING")
    ).strip()

    permission_status = _permission_status_value(
        image_record.get("Permission_Status", {})
    )

    cv_useful = str(
        validation.get("CV_Useful", "UNCERTAIN")
    ).upper()

    # Agronomist decision has priority over everything else.
    if validation_status == "REJECTED":
        return "REJECTED", "Rejected by agronomist validation."

    if validation_status == "NEEDS_REVIEW":
        return "NEEDS_REVIEW", "Agronomist marked the image as needing review."

    if validation_status != "APPROVED":
        return "NEEDS_REVIEW", "Agronomist validation is not APPROVED yet."

    # Permission must be explicitly allowed.
    if permission_status in {"DO_NOT_USE"}:
        return "REJECTED", "Permission/license status is DO_NOT_USE."

    if permission_status not in {
        "PERMISSION_CONFIRMED",
        "LICENSE_ALLOWS_REUSE"
    }:
        return "PERMISSION_PENDING", (
            f"Permission is unresolved ({permission_status})."
        )

    # Expert ground truth must exist and image must be confirmed useful.
    if not expert_label or expert_label.upper() == "PENDING":
        return "NEEDS_REVIEW", "Expert Label is still PENDING."

    if cv_useful != "YES":
        return "NEEDS_REVIEW", "Agronomist has not confirmed the image as CV-usable."

    return (
        "APPROVED_FOR_TRAINING",
        "Agronomist approved the image, expert label is available, "
        "permission is allowed, and the image is confirmed usable."
    )


def save_dataset_record_to_csv(record):
    """Create/update one final dataset record in data/final_dataset.csv."""
    os.makedirs("data", exist_ok=True)

    columns = [
        "Image_ID", "Paper_ID", "Image_File", "Figure_Number",
        "Page_Number",
        "Paper_Title", "Authors", "Journal", "DOI", "Paper_URL",
        "Research_Institute",
        "Visual_Type", "CV_Category",
        "Caption", "Evidence_Text", "Crop",
        "Condition", "Disease_Name", "Pest_Name", "Nutrient",
        "Stress_Type", "Plant_Part",
        "Severity", "Original_Severity",
        "Growth_Stage", "Original_Growth_Stage",
        "Location", "Field_Type", "Paper_Label", "AI_Prediction",
        "Label_Source",
        "Expert_Label", "Expert_Confidence", "Image_Quality",
        "Duplicate_Status", "Permission_Status", "CV_Suitability",
        "Validation_Status", "Dataset_Status", "Dataset_Split",
        "Approval_Reason", "Approved_Date", "Validated_By",
        "Duplicate_Group_ID"
    ]

    existing = []
    if os.path.exists(DATASET_CSV):
        with open(DATASET_CSV, "r", newline="", encoding="utf-8") as f:
            existing = list(csv.DictReader(f))

    row = {
        key: (
            str(value) if isinstance(value, (dict, list)) else value
        )
        for key, value in record.items()
        if key in columns
    }

    found = False
    for i, old_row in enumerate(existing):
        if old_row.get("Image_ID") == record.get("Image_ID"):
            existing[i] = row
            found = True
            break

    if not found:
        existing.append(row)

    with open(DATASET_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(existing)

def download_paper_pdf(
    paper_url,
    output_path
):
    """
    Try to download a PDF from the selected paper URL.

    Returns True if a PDF was successfully downloaded.
    Returns False if the URL does not directly provide a PDF.
    """

    try:

        response = requests.get(
            paper_url,
            timeout=30,
            allow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 "
                    "Kisan-Pukar-Research-Agent"
                )
            }
        )

        response.raise_for_status()

        content_type = (
            response.headers.get(
                "Content-Type",
                ""
            )
            .lower()
        )

        if (
            "application/pdf"
            not in content_type
        ):

            return False

        os.makedirs(
            os.path.dirname(output_path),
            exist_ok=True
        )

        with open(
            output_path,
            "wb"
        ) as pdf_file:

            pdf_file.write(
                response.content
            )

        return True

    except Exception as e:

        print(
            f"PDF download failed: {e}"
        )

        return False

# =========================================================
# STEP 9 UI — FINAL DATASET
# =========================================================

if st.session_state.figures and st.session_state.figure_labels:

    st.divider()
    st.header("📦 Final Approved Dataset")
    st.info(
        "Only agronomist-approved images with an expert label, allowed "
        "permission, and confirmed CV usefulness can enter the approved dataset."
    )

    st.caption(
        "Rejected images and images needing review remain in the system for traceability."
    )

    for i, figure in enumerate(st.session_state.figures):

        image_path = figure.get("image_path")
        image_record = st.session_state.figure_labels.get(image_path)
        if not image_record:
            continue

        image_id = image_record.get("Image_ID", f"IMAGE_{i + 1}")
        validation = st.session_state.validation_queue.get(
            image_id, image_record.get("Validation", {})
        )

        calculated_status, approval_reason = _get_dataset_decision(
            image_record, validation
        )

        current_record = st.session_state.dataset_records.get(image_id, {})
        current_status = current_record.get("Dataset_Status", calculated_status)
        current_split = current_record.get("Dataset_Split", "")

        # If a previously saved split is no longer eligible, clear it.
        if not calculated_status.startswith("APPROVED_FOR_"):
            current_split = ""
            current_status = calculated_status

        with st.expander(
            f"📊 {image_id} — {calculated_status}",
            expanded=True
        ):

            st.write("**Agronomist Validation:**", validation.get("Validation_Status", "PENDING"))
            st.write("**Expert Label:**", validation.get("Expert_Label", "PENDING"))
            st.write("**Permission:**", _permission_status_value(image_record.get("Permission_Status", {})))
            st.write("**CV Useful:**", validation.get("CV_Useful", "UNCERTAIN"))
            st.write("**Calculated Dataset Status:**", calculated_status)

            if calculated_status.startswith("APPROVED_FOR_"):

                split_options = ["TRAINING", "VALIDATION", "TESTING"]
                default_index = (
                    split_options.index(current_split)
                    if current_split in split_options else 0
                )

                dataset_split = st.selectbox(
                    "Dataset Split",
                    split_options,
                    index=default_index,
                    key=f"dataset_split_{image_id}"
                )

                # -------------------------------------------------
                # Prevent Image_ID / duplicate group split conflicts
                # -------------------------------------------------
                duplicate_group = _duplicate_group_id(image_record)
                conflict = None

                for other_id, other_record in st.session_state.dataset_records.items():
                    if other_id == image_id:
                        continue

                    other_group = other_record.get("Duplicate_Group_ID", f"IMAGE:{other_id}")
                    other_split = other_record.get("Dataset_Split", "")

                    if other_split and other_split != dataset_split and other_group == duplicate_group:
                        conflict = (
                            other_id,
                            other_split
                        )
                        break

                if conflict:
                    st.error(
                        f"❌ Split conflict: duplicate/same underlying image "
                        f"{conflict[0]} is already assigned to {conflict[1]}. "
                        f"This image cannot be assigned to {dataset_split}."
                    )
                else:
                    if st.button(
                        "💾 Add to Final Dataset",
                        key=f"save_dataset_{image_id}"
                    ):

                        approved_status = f"APPROVED_FOR_{dataset_split}"

                        # Check Image_ID cannot be saved into another split.
                        existing_same_id = st.session_state.dataset_records.get(image_id)
                        if (
                            existing_same_id
                            and existing_same_id.get("Dataset_Split")
                            and existing_same_id.get("Dataset_Split") != dataset_split
                        ):
                            st.error(
                                f"❌ {image_id} is already assigned to "
                                f"{existing_same_id.get('Dataset_Split')}."
                            )
                        else:
                            final_record = {
                                "Image_ID": image_id,
                                "Paper_ID": image_record.get("Paper_ID", paper_id),
                                "Image_File": image_path,
                                "Figure_Number": image_record.get("Figure_Number", "UNKNOWN"),
                                "Page_Number": image_record.get("Page_Number", "UNKNOWN"),
                                "Paper_Title": image_record.get("Paper_Title", "UNKNOWN"),
                                "Authors": image_record.get("Authors", "UNKNOWN"),
                                "Journal": image_record.get("Journal", "UNKNOWN"),
                                "DOI": image_record.get("DOI", "UNKNOWN"),
                                "Paper_URL": image_record.get("Paper_URL", "UNKNOWN"),
                                "Research_Institute": image_record.get("Research_Institute", "UNKNOWN"),
                                "Visual_Type": image_record.get("Visual_Type", "UNKNOWN"),
                                "CV_Category": image_record.get("CV_Category", "UNKNOWN"),
                                "Caption": image_record.get("Caption", "UNKNOWN"),
                                "Evidence_Text": image_record.get("Evidence_Text", "UNKNOWN"),
                                "Crop": image_record.get("Crop", "UNKNOWN"),
                                "Condition": image_record.get("Condition", "UNKNOWN"),
                                "Disease_Name": image_record.get("Disease_Name", "UNKNOWN"),
                                "Pest_Name": image_record.get("Pest_Name", "UNKNOWN"),
                                "Nutrient": image_record.get("Nutrient", "UNKNOWN"),
                                "Stress_Type": image_record.get("Stress_Type", "UNKNOWN"),
                                "Plant_Part": image_record.get("Plant_Part", "UNKNOWN"),
                                "Severity": image_record.get("Severity", "UNKNOWN"),
                                "Original_Severity": image_record.get("Original_Severity", "NOT_REPORTED"),
                                "Growth_Stage": image_record.get("Growth_Stage", "UNKNOWN"),
                                "Original_Growth_Stage": image_record.get("Original_Growth_Stage", "NOT_REPORTED"),
                                "Location": {
                                    "Country": image_record.get("Country", "UNKNOWN"),
                                    "Province": image_record.get("Province", "UNKNOWN"),
                                    "District": image_record.get("District", "UNKNOWN"),
                                    "Tehsil": image_record.get("Tehsil", "UNKNOWN"),
                                    "Village": image_record.get("Village", "UNKNOWN")
                                },
                                "Field_Type": image_record.get("Field_Type", "UNKNOWN"),
                                "Paper_Label": image_record.get("Paper_Label", "UNKNOWN"),
                                "AI_Prediction": image_record.get("AI_Prediction", "UNKNOWN"),
                                "Label_Source": image_record.get("Label_Source", "UNKNOWN"),
                                "Expert_Label": validation.get("Expert_Label", "PENDING"),
                                "Expert_Confidence": validation.get("Expert_Confidence", "MEDIUM"),
                                "Image_Quality": image_record.get("Image_Quality", {}),
                                "Duplicate_Status": image_record.get("Duplicate_Status", {}),
                                "Permission_Status": image_record.get("Permission_Status", {}),
                                "CV_Suitability": image_record.get("CV_Suitability", {}),
                                "Validation_Status": validation.get("Validation_Status", "PENDING"),
                                "Dataset_Status": approved_status,
                                "Dataset_Split": dataset_split,
                                "Approval_Reason": approval_reason,
                                "Approved_Date": datetime.now().isoformat(timespec="seconds"),
                                "Validated_By": validation.get("Expert_Name", ""),
                                "Duplicate_Group_ID": duplicate_group
                            }

                            st.session_state.dataset_records[image_id] = final_record
                            image_record["Dataset_Status"] = {
                                "status": approved_status,
                                "dataset_split": dataset_split,
                                "approval_reason": approval_reason,
                                "approved_date": final_record["Approved_Date"],
                                "validated_by": final_record["Validated_By"]
                            }
                            image_record["Dataset_Split"] = dataset_split

                            try:
                                save_dataset_record_to_csv(final_record)
                                st.success(
                                    f"✅ {image_id} added to {dataset_split}."
                                )
                                st.info(
                                    f"📁 Final dataset CSV: {DATASET_CSV}"
                                )
                            except Exception as e:
                                st.error(
                                    f"Dataset record saved in memory, but CSV save failed: {e}"
                                )

            else:
                st.warning(
                    f"This image is not eligible for an approved split. "
                    f"Dataset Status = {calculated_status}."
                )

                # Preserve rejected/review/pending images in the final dataset too.
                if st.button(
                    "💾 Save Final Status",
                    key=f"save_nonapproved_{image_id}"
                ):
                    final_record = {
                        "Image_ID": image_id,
                        "Paper_ID": image_record.get("Paper_ID", paper_id),
                        "Image_File": image_path,
                        "Figure_Number": image_record.get("Figure_Number", "UNKNOWN"),
                        "Page_Number": image_record.get("Page_Number", "UNKNOWN"),
                        "Paper_Title": image_record.get("Paper_Title", "UNKNOWN"),
                        "Authors": image_record.get("Authors", "UNKNOWN"),
                        "Journal": image_record.get("Journal", "UNKNOWN"),
                        "DOI": image_record.get("DOI", "UNKNOWN"),
                        "Paper_URL": image_record.get("Paper_URL", "UNKNOWN"),
                        "Research_Institute": image_record.get("Research_Institute", "UNKNOWN"),
                        "Visual_Type": image_record.get("Visual_Type", "UNKNOWN"),
                        "CV_Category": image_record.get("CV_Category", "UNKNOWN"),
                        "Caption": image_record.get("Caption", "UNKNOWN"),
                        "Evidence_Text": image_record.get("Evidence_Text", "UNKNOWN"),
                        "Crop": image_record.get("Crop", "UNKNOWN"),
                        "Condition": image_record.get("Condition", "UNKNOWN"),
                        "Disease_Name": image_record.get("Disease_Name", "UNKNOWN"),
                        "Pest_Name": image_record.get("Pest_Name", "UNKNOWN"),
                        "Nutrient": image_record.get("Nutrient", "UNKNOWN"),
                        "Stress_Type": image_record.get("Stress_Type", "UNKNOWN"),
                        "Plant_Part": image_record.get("Plant_Part", "UNKNOWN"),
                        "Severity": image_record.get("Severity", "UNKNOWN"),
                        "Original_Severity": image_record.get("Original_Severity", "NOT_REPORTED"),
                        "Growth_Stage": image_record.get("Growth_Stage", "UNKNOWN"),
                        "Original_Growth_Stage": image_record.get("Original_Growth_Stage", "NOT_REPORTED"),
                        "Location": {
                            "Country": image_record.get("Country", "UNKNOWN"),
                            "Province": image_record.get("Province", "UNKNOWN"),
                            "District": image_record.get("District", "UNKNOWN"),
                            "Tehsil": image_record.get("Tehsil", "UNKNOWN"),
                            "Village": image_record.get("Village", "UNKNOWN")
                        },
                        "Field_Type": image_record.get("Field_Type", "UNKNOWN"),
                        "Paper_Label": image_record.get("Paper_Label", "UNKNOWN"),
                        "AI_Prediction": image_record.get("AI_Prediction", "UNKNOWN"),
                        "Label_Source": image_record.get("Label_Source", "UNKNOWN"),
                        "Expert_Label": validation.get("Expert_Label", "PENDING"),
                        "Expert_Confidence": validation.get("Expert_Confidence", "MEDIUM"),
                        "Image_Quality": image_record.get("Image_Quality", {}),
                        "Duplicate_Status": image_record.get("Duplicate_Status", {}),
                        "Permission_Status": image_record.get("Permission_Status", {}),
                        "CV_Suitability": image_record.get("CV_Suitability", {}),
                        "Validation_Status": validation.get("Validation_Status", "PENDING"),
                        "Dataset_Status": calculated_status,
                        "Dataset_Split": "",
                        "Approval_Reason": approval_reason,
                        "Approved_Date": datetime.now().isoformat(timespec="seconds"),
                        "Validated_By": validation.get("Expert_Name", ""),
                        "Duplicate_Group_ID": _duplicate_group_id(image_record)
                    }

                    st.session_state.dataset_records[image_id] = final_record
                    image_record["Dataset_Status"] = {
                        "status": calculated_status,
                        "dataset_split": "",
                        "approval_reason": approval_reason,
                        "approved_date": final_record["Approved_Date"],
                        "validated_by": final_record["Validated_By"]
                    }

                    try:
                        save_dataset_record_to_csv(final_record)
                        st.success(
                            f"✅ Final status saved for {image_id}: {calculated_status}"
                        )
                        st.info(
                            f"📁 Final dataset CSV: {DATASET_CSV}"
                        )
                    except Exception as e:
                        st.error(
                            f"Final status saved in memory, but CSV save failed: {e}"
                        )

    # ---------------------------------------------------------
    # Final dataset summary
    # ---------------------------------------------------------
    if st.session_state.dataset_records:
        st.divider()
        st.subheader("📋 Final Dataset Records")

        summary_rows = []
        for record in st.session_state.dataset_records.values():
            summary_rows.append({
                "Image_ID": record.get("Image_ID"),
                "Dataset_Status": record.get("Dataset_Status"),
                "Dataset_Split": record.get("Dataset_Split", ""),
                "Expert_Label": record.get("Expert_Label"),
                "Validated_By": record.get("Validated_By", "")
            })

        st.dataframe(summary_rows, use_container_width=True)

        if os.path.exists(DATASET_CSV):
            with open(DATASET_CSV, "rb") as dataset_file:
                st.download_button(
                    "⬇️ Download Final Dataset CSV",
                    dataset_file,
                    file_name="final_dataset.csv",
                    mime="text/csv",
                    key="download_final_dataset_csv"
                )
