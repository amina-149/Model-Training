import os
import requests
from dotenv import load_dotenv

load_dotenv()

CLIPDROP_API_KEY = os.getenv("CLIPDROP_API_KEY")
CLIPDROP_URL = "https://clipdrop-api.co/text-to-image/v1"


def generate_image(prompt, output_path):
    """
    Generate an image from a text prompt using ClipDrop API.
    """

    if not CLIPDROP_API_KEY:
        raise ValueError(
            "CLIPDROP_API_KEY is not set in the .env file."
        )

    if not prompt or not prompt.strip():
        raise ValueError(
            "Image prompt cannot be empty."
        )

    headers = {
        "x-api-key": CLIPDROP_API_KEY
    }

    files = {
        "prompt": (
            None,
            prompt,
            "text/plain"
        )
    }

    try:

        response = requests.post(
            CLIPDROP_URL,
            headers=headers,
            files=files,
            timeout=60,
            verify=False
        )

        if response.status_code != 200:

            try:
                error_details = response.json()
            except Exception:
                error_details = response.text

            raise RuntimeError(
                f"ClipDrop API error "
                f"{response.status_code}: "
                f"{error_details}"
            )

        os.makedirs(
            os.path.dirname(output_path),
            exist_ok=True
        )

        with open(
            output_path,
            "wb"
        ) as image_file:

            image_file.write(
                response.content
            )

        print(
            f"Image generated successfully: "
            f"{output_path}"
        )

        return output_path

    except requests.exceptions.RequestException as e:

        raise RuntimeError(
            f"Could not connect to ClipDrop API: {e}"
        )

