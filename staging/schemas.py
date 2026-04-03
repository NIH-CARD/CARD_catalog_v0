"""
Pydantic row models for each CARD Catalog output table.

Column names use the exact strings the Streamlit app expects (with spaces).
snake_case aliases are accepted on input so the normalizer can feed either style.

Validation rules:

- ``str`` fields coerce ``None``/``NaN`` to ``""``
- Semicolon-joined list fields are normalized by the normalizer before
  validation; schemas just enforce the type.
"""
from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, field_validator


def _coerce_str(v: object) -> str:
    """Convert None / NaN / non-string to empty string."""
    import math
    if v is None:
        return ""
    if isinstance(v, float) and math.isnan(v):
        return ""
    return str(v).strip()


class _Base(BaseModel):
    model_config = {"populate_by_name": True, "str_strip_whitespace": True}

    @field_validator("*", mode="before")
    @classmethod
    def coerce_to_str(cls, v: object) -> object:
        # Only coerce fields typed as str; leave others alone
        return v


# ---------------------------------------------------------------------------
# Table: Publications   (tables/final/pubmed_central_*.tsv)
# ---------------------------------------------------------------------------
class PublicationRow(_Base):
    PMID: str = ""
    Resource_Name: str = ""
    Abbreviation: str = ""
    Diseases_Included: str = ""
    Coarse_Data_Modality: str = ""
    Granular_Data_Modality: str = ""
    PubMed_Central_Link: str = ""
    Authors: str = ""
    Affiliations: str = ""
    Title: str = ""
    Abstract: str = ""
    Keywords: str = ""

    # Map from scraper column names (with spaces) to model field names
    model_config = {
        "populate_by_name": True,
        "alias_generator": lambda s: s.replace("_", " "),
    }

    @field_validator(
        "PMID", "Resource_Name", "Abbreviation", "Diseases_Included",
        "Coarse_Data_Modality", "Granular_Data_Modality", "PubMed_Central_Link",
        "Authors", "Affiliations", "Title", "Abstract", "Keywords",
        mode="before",
    )
    @classmethod
    def to_str(cls, v: object) -> str:
        return _coerce_str(v)

    # App-facing column order
    COLUMNS: ClassVar[list[str]] = [
        "PMID", "Resource Name", "Abbreviation",
        "Diseases Included", "Coarse Data Modality", "Granular Data Modality",
        "PubMed Central Link", "Authors", "Affiliations",
        "Title", "Abstract", "Keywords",
    ]


# ---------------------------------------------------------------------------
# Table: Code repositories   (tables/final/gits_to_reannotate_completed_*.tsv)
# ---------------------------------------------------------------------------
class CodeRepoRow(_Base):
    Resource_Name: str = ""
    Abbreviation: str = ""
    Diseases_Included: str = ""
    Repository_Link: str = ""
    Owner: str = ""
    Contributors: str = ""
    Languages: str = ""
    Biomedical_Relevance: str = ""
    Code_Summary: str = ""
    Data_Types: str = ""
    Tooling: str = ""

    model_config = {
        "populate_by_name": True,
        "alias_generator": lambda s: s.replace("_", " "),
    }

    @field_validator(
        "Resource_Name", "Abbreviation", "Diseases_Included", "Repository_Link",
        "Owner", "Contributors", "Languages", "Biomedical_Relevance",
        "Code_Summary", "Data_Types", "Tooling",
        mode="before",
    )
    @classmethod
    def to_str(cls, v: object) -> str:
        return _coerce_str(v)

    COLUMNS: ClassVar[list[str]] = [
        "Resource Name", "Abbreviation", "Diseases Included",
        "Repository Link", "Owner", "Contributors", "Languages",
        "Biomedical Relevance", "Code Summary", "Data Types", "Tooling",
    ]


# ---------------------------------------------------------------------------
# Table: Publication datasets   (tables/final/pub_datasets_*.tsv)
# ---------------------------------------------------------------------------
class PubDatasetRow(_Base):
    Source_PMID: str = ""
    Source_Resource_Name: str = ""
    Dataset_Identifier: str = ""
    Data_Repository: str = ""
    Dataset_Webpage: str = ""
    Citation_Type: str = ""
    Usage_Description: str = ""
    Dataset_Scope: str = ""
    Results_Relationship: str = ""
    Decision_Rationale: str = ""

    model_config = {
        "populate_by_name": True,
        "alias_generator": lambda s: s.replace("_", " "),
    }

    @field_validator(
        "Source_PMID", "Source_Resource_Name", "Dataset_Identifier",
        "Data_Repository", "Dataset_Webpage", "Citation_Type",
        "Usage_Description", "Dataset_Scope", "Results_Relationship",
        "Decision_Rationale",
        mode="before",
    )
    @classmethod
    def to_str(cls, v: object) -> str:
        return _coerce_str(v)

    COLUMNS: ClassVar[list[str]] = [
        "Source PMID", "Source Resource Name", "Dataset Identifier",
        "Data Repository", "Dataset Webpage", "Citation Type",
        "Usage Description", "Dataset Scope", "Results Relationship",
        "Decision Rationale",
    ]


# ---------------------------------------------------------------------------
# Table: Supplementary files   (tables/final/pub_supplementary_*.tsv)
# ---------------------------------------------------------------------------
class SupplementaryRow(_Base):
    Source_PMID: str = ""
    Source_Resource_Name: str = ""
    File_URL: str = ""
    File_Name: str = ""
    File_Extension: str = ""
    File_Format: str = ""
    Keywords: str = ""
    Data_Repository: str = ""
    Number_Of_Files: str = ""
    File_License: str = ""

    model_config = {
        "populate_by_name": True,
        "alias_generator": lambda s: s.replace("_", " "),
    }

    @field_validator(
        "Source_PMID", "Source_Resource_Name", "File_URL", "File_Name",
        "File_Extension", "File_Format", "Keywords", "Data_Repository",
        "Number_Of_Files", "File_License",
        mode="before",
    )
    @classmethod
    def to_str(cls, v: object) -> str:
        return _coerce_str(v)

    COLUMNS: ClassVar[list[str]] = [
        "Source PMID", "Source Resource Name", "File URL", "File Name",
        "File Extension", "File Format", "Keywords", "Data Repository",
        "Number Of Files", "File License",
    ]


# ---------------------------------------------------------------------------
# Table: New Corpus   (tables/final/new_corpus_*.tsv)
# ---------------------------------------------------------------------------
class NewCorpusRow(_Base):
    Resource_Name: str = ""
    Diseases_Included: str = ""
    Coarse_Data_Modality: str = ""
    Granular_Data_Modality: str = ""
    Sample_Size: str = ""
    Access_URL: str = ""
    Publication_URLs: str = ""
    Rationale: str = ""

    model_config = {
        "populate_by_name": True,
        "alias_generator": lambda s: s.replace("_", " "),
    }

    @field_validator(
        "Resource_Name", "Diseases_Included", "Coarse_Data_Modality",
        "Granular_Data_Modality", "Sample_Size", "Access_URL",
        "Publication_URLs", "Rationale",
        mode="before",
    )
    @classmethod
    def to_str(cls, v: object) -> str:
        return _coerce_str(v)

    COLUMNS: ClassVar[list[str]] = [
        "Resource Name", "Diseases Included", "Coarse Data Modality",
        "Granular Data Modality", "Sample Size",
        "Access URL", "Publication URLs", "Rationale",
    ]


# ---------------------------------------------------------------------------
# Hits file schemas  (intermediate outputs in tables/hits/)
# These match the scraper's own column order exactly.
# ---------------------------------------------------------------------------
PUBMED_HITS_COLUMNS: list[str] = [
    "PMID",
    "Resource Name",
    "Abbreviation",
    "Diseases Included",
    "Coarse Data Modality",
    "Granular Data Modality",
    "PubMed Central Link",
    "Authors",
    "Affiliations",
    "Title",
    "Abstract",
    "Keywords",
]

GITHUB_HITS_COLUMNS: list[str] = [
    "Resource Name",
    "Abbreviation",
    "Diseases Included",
    "Repository Link",
    "Owner",
    "Contributors",
    "Languages",
    "Content_For_Analysis",   # dropped by normalizer; present in hits only
    "Biomedical Relevance",
    "Code Summary",
    "Data Types",
    "Tooling",
]


# ---------------------------------------------------------------------------
# Registry — maps schema name used in hits files to (model, column_list)
# ---------------------------------------------------------------------------
SCHEMA_REGISTRY: dict[str, type[_Base]] = {
    "publications": PublicationRow,
    "code": CodeRepoRow,
    "pub_datasets": PubDatasetRow,
    "supplementary": SupplementaryRow,
    "new_corpus": NewCorpusRow,
}
