from dataclasses import dataclass


@dataclass
class PaperAnalysis:
    short_summary: str
    disease_name: str
    pathogen: str
    affected_crop: str
    key_finding: str
