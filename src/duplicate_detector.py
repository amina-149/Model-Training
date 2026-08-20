import hashlib
from PIL import Image


# --------------------------------
# Calculate exact image hash
# --------------------------------

def calculate_image_hash(image_path):
    """
    Creates SHA-256 hash of the original image file.

    Same file bytes = same hash.
    """

    with open(image_path, "rb") as image_file:
        image_bytes = image_file.read()

    return hashlib.sha256(image_bytes).hexdigest()


# --------------------------------
# Calculate perceptual hash
# --------------------------------

def calculate_perceptual_hash(image_path):
    """
    Creates a simple perceptual hash (pHash-like)
    using image resizing and grayscale comparison.
    """

    image = Image.open(image_path)

    # Convert to grayscale
    image = image.convert("L")

    # Resize image
    image = image.resize((32, 32))

    pixels = list(image.getdata())

    average = sum(pixels) / len(pixels)

    hash_bits = ""

    for pixel in pixels:
        if pixel >= average:
            hash_bits += "1"
        else:
            hash_bits += "0"

    return hash_bits


# --------------------------------
# Calculate perceptual similarity
# --------------------------------

def calculate_similarity(hash1, hash2):
    """
    Calculates similarity between two perceptual hashes.

    Returns value between 0.0 and 1.0.
    """

    if not hash1 or not hash2:
        return 0.0

    if len(hash1) != len(hash2):
        return 0.0

    different_bits = sum(
        bit1 != bit2
        for bit1, bit2 in zip(hash1, hash2)
    )

    total_bits = len(hash1)

    similarity = 1 - (
        different_bits / total_bits
    )

    return round(similarity, 4)


# --------------------------------
# Detect duplicate
# --------------------------------

def detect_duplicate(
    image_path,
    image_id,
    previous_images
):
    """
    Compare current image with previously processed images.

    previous_images contains records like:

    {
        "Image_ID": "...",
        "image_hash": "...",
        "perceptual_hash": "..."
    }
    """

    image_hash = calculate_image_hash(
        image_path
    )

    perceptual_hash = calculate_perceptual_hash(
        image_path
    )

    best_similarity = 0.0
    matched_image_id = None

    # --------------------------------
    # Compare with previous images
    # --------------------------------

    for previous in previous_images:

        # --------------------------------
        # Exact duplicate check
        # --------------------------------

        if image_hash == previous["image_hash"]:

            return {
                "status": "EXACT_DUPLICATE",
                "image_hash": image_hash,
                "perceptual_hash": perceptual_hash,
                "similarity_score": 1.0,
                "matched_image_id": previous["Image_ID"]
            }

        # --------------------------------
        # Perceptual similarity
        # --------------------------------

        similarity = calculate_similarity(
            perceptual_hash,
            previous["perceptual_hash"]
        )

        if similarity > best_similarity:

            best_similarity = similarity

            matched_image_id = (
                previous["Image_ID"]
            )

    # --------------------------------
    # Classify similarity
    # --------------------------------

    if best_similarity >= 0.95:

        status = "LIKELY_DUPLICATE"

    elif best_similarity >= 0.80:

        status = "SIMILAR_IMAGE"

    else:

        status = "UNIQUE"

        matched_image_id = None

    return {
        "status": status,
        "image_hash": image_hash,
        "perceptual_hash": perceptual_hash,
        "similarity_score": best_similarity,
        "matched_image_id": matched_image_id
    }
