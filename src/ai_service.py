import os
from dotenv import load_dotenv
from google import genai

from src.models import PaperAnalysis

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    raise ValueError("GEMINI_API_KEY not found in .env file")

client = genai.Client(api_key=API_KEY)


def analyze_paper(text):
    """
    Analyze research paper text using Gemini AI
    and return a structured PaperAnalysis object.
    """

    prompt = f"""
You are an AI research assistant for an agriculture research system.

Analyze the following research paper and return ONLY valid JSON.

Use exactly these five keys:

{{
    "short_summary": "A concise summary of the paper",
    "disease_name": "Name of the disease",
    "pathogen": "Name of the pathogen",
    "affected_crop": "Affected crop",
    "key_finding": "Most important finding"
}}

Important:
- Only use information supported by the paper.
- Do not add explanations outside the JSON.
- Keep each field concise.

Research Paper Text:
{text}
"""

    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=prompt
    )

    result = response.text.strip()

    # Remove markdown code fences if Gemini adds them
    if result.startswith("```json"):
        result = result[7:]

    if result.startswith("```"):
        result = result[3:]

    if result.endswith("```"):
        result = result[:-3]

    result = result.strip()

    import json

    data = json.loads(result)

    return PaperAnalysis(
        short_summary=data["short_summary"],
        disease_name=data["disease_name"],
        pathogen=data["pathogen"],
        affected_crop=data["affected_crop"],
        key_finding=data["key_finding"]
    )
