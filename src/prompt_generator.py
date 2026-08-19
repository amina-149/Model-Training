import os
import re

from dotenv import load_dotenv
from google import genai

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    raise ValueError("GEMINI_API_KEY not found in .env file")

client = genai.Client(api_key=API_KEY)


def generate_image_prompts(text, analysis):
    """
    Generate 3 scientific image prompts from a research paper.
    """

    prompt = f"""
You are an AI scientific visualization assistant.

Based on the research paper and its analysis, generate exactly 3
detailed image-generation prompts.

The prompts should help visually explain the research paper.

Each prompt should describe:
- Main subject
- Crop or plant involved
- Disease/pathogen if relevant
- Visible symptoms or scientific characteristics
- Environment/context
- Scientific visualization style
- Important visual details

Do not generate the actual images.
Only generate the prompts.

Research Paper Analysis:

Disease:
{analysis.disease_name}

Pathogen:
{analysis.pathogen}

Affected Crop:
{analysis.affected_crop}

Key Finding:
{analysis.key_finding}

Research Paper Text:
{text}

Return exactly 3 prompts in this format:

PROMPT 1:
...

PROMPT 2:
...

PROMPT 3:
...
"""

    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=prompt
    )

    response_text = response.text.strip()

    # Split the AI response into individual prompts
    parts = re.split(
        r"PROMPT\s+\d+\s*:",
        response_text,
        flags=re.IGNORECASE
    )

    # Remove empty parts
    prompts = [
        part.strip()
        for part in parts
        if part.strip()
    ]

    # Make sure only the first 3 prompts are returned
    return prompts[:3]
