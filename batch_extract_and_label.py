"""
Run every PDF in data/ through: extract figures -> AI label ->
duplicate detection -> CSV dataset row.

Output goes to outputs/final_dataset_batch.csv (kept separate from
data/final_dataset.csv, which already holds real reviewed rows from
prior UI runs -- this script never touches that file).

Expert_Label stays PENDING on every row; nothing here is auto-approved.
Human review still happens afterwards, same as the Streamlit flow.
"""

import csv
import glob
import os
import re

from PIL import Image

from src.pdf_processor import extract_pdf_metadata
from src.figure_extractor import extract_figures
from src.figure_labeler import generate_figure_label
from src.duplicate_detector import detect_duplicate

DATA_DIR = "data"
OUTPUT_CSV = os.path.join("outputs", "final_dataset_batch.csv")

MIN_IMAGE_DIMENSION = 80


def is_too_small(image_path):
    try:
        with Image.open(image_path) as image:
            width, height = image.size
        return width < MIN_IMAGE_DIMENSION or height < MIN_IMAGE_DIMENSION
    except Exception:
        return False

MONTAGE_KEYWORDS = [
    "dataset", "sample images", "examples of", "collection of",
    "various", "grid", "montage", "several images", "sample dataset"
]

COLUMNS = [
    "Image_ID", "Paper_ID", "Image_File", "Figure_Number",
    "Page_Number", "Paper_Title", "Authors", "Visual_Type",
    "CV_Category", "Caption", "Evidence_Text", "Crop", "Condition",
    "Disease_Name", "Pest_Name", "Nutrient", "Stress_Type",
    "Plant_Part", "Severity", "Original_Severity", "Growth_Stage",
    "Original_Growth_Stage", "Location", "Field_Type", "Paper_Label",
    "AI_Prediction", "Label_Source", "Expert_Label", "Image_Quality",
    "Duplicate_Status", "Permission_Status", "CV_Suitability",
    "Possible_Montage", "Validation_Status"
]


def paper_id_from_filename(pdf_path):
    name = os.path.splitext(os.path.basename(pdf_path))[0]
    return re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").upper()


def build_location(record):
    fields = [
        record.get("Country"), record.get("Province"),
        record.get("District"), record.get("Tehsil"),
        record.get("Village"), record.get("Research_Station")
    ]
    parts = [
        value for value in fields
        if value and value != "UNKNOWN"
    ]
    return ", ".join(parts) if parts else "UNKNOWN"


def flag_possible_montage(record):
    caption = (record.get("Caption") or "").lower()
    return any(keyword in caption for keyword in MONTAGE_KEYWORDS)


def main():
    import sys

    pdf_paths = sorted(glob.glob(os.path.join(DATA_DIR, "*.pdf")))

    only = sys.argv[1:]
    if only:
        pdf_paths = [p for p in pdf_paths if os.path.basename(p) in only]

    print(f"Found {len(pdf_paths)} PDFs to process")

    os.makedirs("outputs", exist_ok=True)

    rows = []
    hash_history = []

    if os.path.exists(OUTPUT_CSV):
        with open(OUTPUT_CSV, "r", newline="", encoding="utf-8") as f:
            existing_rows = list(csv.DictReader(f))
        rows.extend(existing_rows)
        for row in existing_rows:
            hash_history.append({
                "Image_ID": row.get("Image_ID"),
                "image_hash": None,
                "perceptual_hash": None
            })
        print(f"Loaded {len(existing_rows)} existing rows from {OUTPUT_CSV}")

    for pdf_path in pdf_paths:

        paper_id = paper_id_from_filename(pdf_path)

        print(f"\n=== {os.path.basename(pdf_path)} (Paper_ID={paper_id}) ===")

        try:
            metadata = extract_pdf_metadata(pdf_path)
        except Exception as e:
            print(f"  metadata FAILED: {e}")
            metadata = {}

        try:
            figures = extract_figures(
                pdf_path,
                output_dir=os.path.join("outputs", "figures", paper_id)
            )
        except Exception as e:
            print(f"  extract_figures FAILED: {e}")
            continue

        print(f"  {len(figures)} figures extracted")

        for figure in figures:

            if is_too_small(figure["image_path"]):
                print(f"  figure {figure.get('figure_number')} skipped (too small, likely a logo/icon)")
                continue

            try:
                record = generate_figure_label(figure, paper_id)
            except Exception as e:
                print(f"  figure {figure.get('figure_number')} label FAILED: {e}")
                continue

            try:
                duplicate = detect_duplicate(
                    figure["image_path"],
                    record["Image_ID"],
                    hash_history
                )
            except Exception as e:
                print(f"  figure {figure.get('figure_number')} dup-check FAILED: {e}")
                duplicate = {"status": "UNKNOWN"}

            hash_history.append({
                "Image_ID": record["Image_ID"],
                "image_hash": duplicate.get("image_hash"),
                "perceptual_hash": duplicate.get("perceptual_hash")
            })

            row = {
                "Image_ID": record.get("Image_ID"),
                "Paper_ID": paper_id,
                "Image_File": os.path.basename(figure["image_path"]),
                "Figure_Number": record.get("Figure_Number"),
                "Page_Number": record.get("Page_Number"),
                "Paper_Title": metadata.get("title", "Not available"),
                "Authors": metadata.get("authors", "Not available"),
                "Visual_Type": record.get("Visual_Type"),
                "CV_Category": record.get("CV_Category"),
                "Caption": record.get("Caption"),
                "Evidence_Text": record.get("Evidence_Text"),
                "Crop": record.get("Crop"),
                "Condition": record.get("Condition"),
                "Disease_Name": record.get("Disease_Name"),
                "Pest_Name": record.get("Pest_Name"),
                "Nutrient": record.get("Nutrient"),
                "Stress_Type": record.get("Stress_Type"),
                "Plant_Part": record.get("Plant_Part"),
                "Severity": record.get("Severity"),
                "Original_Severity": record.get("Original_Severity"),
                "Growth_Stage": record.get("Growth_Stage"),
                "Original_Growth_Stage": record.get("Original_Growth_Stage"),
                "Location": build_location(record),
                "Field_Type": record.get("Field_Type"),
                "Paper_Label": record.get("Paper_Label"),
                "AI_Prediction": record.get("AI_Prediction"),
                "Label_Source": record.get("Label_Source"),
                "Expert_Label": "PENDING",
                "Image_Quality": str(record.get("Image_Quality")),
                "Duplicate_Status": str(duplicate),
                "Permission_Status": str(record.get("Permission_Status")),
                "CV_Suitability": str(record.get("CV_Suitability")),
                "Possible_Montage": flag_possible_montage(record),
                "Validation_Status": "PENDING"
            }

            rows.append(row)

            print(
                f"  fig#{record.get('Figure_Number')} "
                f"CV_Category={record.get('CV_Category')} "
                f"Crop={record.get('Crop')} "
                f"Condition={record.get('Condition')} "
                f"montage_flag={row['Possible_Montage']}"
            )

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nWrote {len(rows)} rows to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
