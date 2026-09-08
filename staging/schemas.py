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

import re
from typing import ClassVar

from pydantic import BaseModel, Field, field_validator


def _coerce_str(v: object) -> str:
    """Convert None / NaN / non-string to empty string."""
    import math
    if v is None:
        return ""
    if isinstance(v, float) and math.isnan(v):
        return ""
    return str(v).strip()


def _looks_like_url(v: str) -> bool:
    return v.startswith(("http://", "https://"))


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
    PubMed_Central_Link: str = ""
    Authors: str = ""
    Affiliations: str = ""
    Title: str = ""
    Abstract: str = ""
    Keywords: str = ""
    Publication_Date: str = ""
    Data_Completeness: str = ""
    Fetched_With: str = ""
    # paperclip-only fields (query_method="paperclip"); blank for original/v2/v3/v4 rows.
    DOI: str = ""
    Verification_Status: str = ""
    Claim_Text: str = ""
    Rationale: str = ""
    Evidence: str = ""  # from paperclip's own repo verify/claims - maybe remove, that subsystem keeps proving unreliable

    # Map from scraper column names (with spaces) to model field names
    model_config = {
        "populate_by_name": True,
        "alias_generator": lambda s: s.replace("_", " "),
    }

    @field_validator(
        "PMID", "Resource_Name", "Abbreviation", "PubMed_Central_Link",
        "Authors", "Affiliations", "Title", "Abstract", "Keywords",
        "Publication_Date", "Data_Completeness", "Fetched_With",
        "DOI", "Verification_Status", "Claim_Text", "Rationale", "Evidence",
        mode="before",
    )
    @classmethod
    def to_str(cls, v: object) -> str:
        return _coerce_str(v)

    # App-facing column order
    COLUMNS: ClassVar[list[str]] = [
        "PMID", "DOI", "Resource Name", "Abbreviation",
        "PubMed Central Link", "Authors", "Affiliations",
        "Title", "Abstract", "Keywords", "Publication Date", "Data Completeness",
        "Verification Status", "Claim Text", "Rationale", "Evidence",
        "Fetched With",
    ]


# Real column-name shapes, verified against tables/final/*.tsv on 2026-09-08 -
# see the session that added this validation for how each was derived from
# actual bugs found in the data (a malformed DOI/PMC link never reaches here
# silently; PMID must be the bare digit string PubMed itself uses).
_PMID_RE = re.compile(r"^\d+$")
_DOI_RE = re.compile(r'^10\.\d{4,9}/[^\s?<>"\'\\]+$')
_PMC_LINK_RE = re.compile(r"^https://www\.ncbi\.nlm\.nih\.gov/pmc/articles/PMC\d+/?$")
_KNOWN_VERIFICATION_STATUSES = {"confirmed", "not_confirmed", "insufficient_evidence", "error"}


# ---------------------------------------------------------------------------
# Table: Misc Publications (LIVE - the app's actual source)
# (tables/final/misc_publications_*.tsv, synced to web/public/data/publications.tsv)
#
# Deliberately a separate model from PublicationRow, not a shared one - despite
# both starting from a "publications" concept, misc_publications' real columns
# (Paperclip Repo/Doc ID, Inclusion Criteria, Fetched With) and PublicationRow's
# (Diseases Included, Data Completeness, the annotation-join columns) diverged
# from the legacy pubmed_central_*.tsv shape enough that one model can no
# longer honestly describe both real files - conflating them would mean
# validating misc_publications rows against fields it doesn't have, or vice
# versa. See staging/normalizer.py's VALIDATED_TARGETS for where this is
# actually enforced (PublicationRow itself is declared but never wired up -
# do not assume its presence in SCHEMA_REGISTRY means it runs anywhere).
# ---------------------------------------------------------------------------
class MiscPublicationRow(_Base):
    PMID: str = ""
    DOI: str = ""
    PubMed_Central_Link: str = ""
    Authors: str = ""
    Affiliations: str = ""
    Title: str = ""
    Abstract: str = ""
    Keywords: str = ""
    Publication_Date: str = ""
    Verification_Status: str = ""
    Paperclip_Repo: str = ""
    Paperclip_Doc_ID: str = ""
    Resource_Name: str = ""
    Abbreviation: str = ""
    Fetched_With: str = ""
    Inclusion_Criteria: str = ""
    Claim_Text: str = ""

    model_config = {
        "populate_by_name": True,
        "alias_generator": lambda s: s.replace("_", " "),
    }

    @field_validator(
        "PMID", "DOI", "PubMed_Central_Link", "Authors", "Affiliations",
        "Title", "Abstract", "Keywords", "Publication_Date",
        "Verification_Status", "Paperclip_Repo", "Paperclip_Doc_ID",
        "Resource_Name", "Abbreviation", "Fetched_With",
        "Inclusion_Criteria", "Claim_Text",
        mode="before",
    )
    @classmethod
    def to_str(cls, v: object) -> str:
        return _coerce_str(v)

    @field_validator("PMID")
    @classmethod
    def pmid_shape(cls, v: str) -> str:
        if v and not _PMID_RE.match(v):
            raise ValueError(f"PMID must be all-digits when present, got {v!r}")
        return v

    @field_validator("DOI")
    @classmethod
    def doi_shape(cls, v: str) -> str:
        if v and not _DOI_RE.match(v):
            raise ValueError(
                f"DOI {v!r} doesn't match the clean '10.xxxx/...' shape - looks like a "
                "URL-tracking-param or escape-character artifact glued onto a real DOI "
                "(see scripts/clean_malformed_dois.py for the exact bug class this catches)"
            )
        return v

    @field_validator("PubMed_Central_Link")
    @classmethod
    def pmc_link_shape(cls, v: str) -> str:
        if v and not _PMC_LINK_RE.match(v):
            raise ValueError(f"PubMed Central Link {v!r} isn't a clean PMC article URL")
        return v

    @field_validator("Resource_Name")
    @classmethod
    def resource_name_required(cls, v: str) -> str:
        if not v:
            raise ValueError("Resource Name is required - a publication row must be tied to a resource")
        return v

    @field_validator("Fetched_With")
    @classmethod
    def fetched_with_required(cls, v: str) -> str:
        if not v:
            raise ValueError("Fetched With is required - every row must record how it was discovered")
        return v

    @field_validator("Verification_Status")
    @classmethod
    def verification_status_known(cls, v: str) -> str:
        if v and v not in _KNOWN_VERIFICATION_STATUSES:
            raise ValueError(f"Verification Status {v!r} isn't one of {sorted(_KNOWN_VERIFICATION_STATUSES)}")
        return v

    COLUMNS: ClassVar[list[str]] = [
        "PMID", "DOI", "PubMed Central Link", "Authors", "Affiliations",
        "Title", "Abstract", "Keywords", "Publication Date",
        "Verification Status", "Paperclip Repo", "Paperclip Doc ID",
        "Resource Name", "Abbreviation", "Fetched With",
        "Inclusion Criteria", "Claim Text",
    ]


# ---------------------------------------------------------------------------
# Table: Code repositories   (tables/final/gits_to_reannotate_completed_*.tsv)
# ---------------------------------------------------------------------------
class CodeRepoRow(_Base):
    Resource_Name: str = ""
    Abbreviation: str = ""
    Repository_Link: str = ""
    Source: str = ""
    Owner: str = ""
    Contributors: str = ""
    Languages: str = ""
    Biomedical_Relevance: str = ""
    Relevance_Rationale: str = ""
    Code_Summary: str = ""
    Data_Types: str = ""
    Tooling: str = ""
    FAIR_Score: str = "10"
    FAIR_Issues: str = ""

    model_config = {
        "populate_by_name": True,
        "alias_generator": lambda s: s.replace("_", " "),
    }

    @field_validator(
        "Resource_Name", "Abbreviation", "Repository_Link",
        "Source", "Owner", "Contributors", "Languages", "Biomedical_Relevance",
        "Relevance_Rationale", "Code_Summary", "Data_Types", "Tooling",
        "FAIR_Score", "FAIR_Issues",
        mode="before",
    )
    @classmethod
    def to_str(cls, v: object) -> str:
        return _coerce_str(v)

    @field_validator("Repository_Link")
    @classmethod
    def repository_link_shape(cls, v: str) -> str:
        if not v:
            raise ValueError("Repository Link is required")
        if not _looks_like_url(v):
            raise ValueError(f"Repository Link {v!r} doesn't look like a URL")
        return v

    @field_validator("Resource_Name")
    @classmethod
    def resource_name_required(cls, v: str) -> str:
        if not v:
            raise ValueError("Resource Name is required")
        return v

    @field_validator("FAIR_Score")
    @classmethod
    def fair_score_numeric(cls, v: str) -> str:
        if v:
            try:
                float(v)
            except ValueError:
                raise ValueError(f"FAIR Score {v!r} isn't numeric") from None
        return v

    COLUMNS: ClassVar[list[str]] = [
        "Resource Name", "Abbreviation",
        "Repository Link", "Source", "Owner", "Contributors", "Languages",
        "Biomedical Relevance", "Relevance Rationale", "Code Summary",
        "Data Types", "Tooling", "FAIR Score", "FAIR Issues",
    ]


# ---------------------------------------------------------------------------
# Table: Publication datasets   (tables/final/pub_datasets_*.tsv)
#
# Audited 2026-09-08 against the real current file - this model previously
# had a completely different, unrelated field set (Source_PMID/Usage_
# Description/Dataset_Scope/Results_Relationship/Decision_Rationale, none of
# which exist in the real file) and would have silently validated every row
# as "fine" using nothing but defaults, since none of its fields could ever
# bind to the real column names. Rebuilt to match the real (lowercase
# snake_case - this table was never Title-Cased, unlike misc_publications/
# code) columns exactly. The real current file also carries `I`, `II` (both
# 100% blank) and `dataset_context_context_from_paper`/`dataset_context_
# about_paper` (a doubled-name near-duplicate of dataset_context_from_paper,
# <0.1% populated) - scraping artifacts, deliberately excluded here so
# normalize()'s COLUMNS-based output filtering drops them from tables/final/.
# ---------------------------------------------------------------------------
class PubDatasetRow(_Base):
    pub_title: str = ""
    source_url: str = ""
    raw_data_format: str = ""
    dataset_identifier: str = ""
    data_repository: str = ""
    dataset_context_from_paper: str = ""
    dataset_keywords: str = ""
    citation_type: str = ""
    dataset_webpage: str = ""
    access_mode: str = ""

    @field_validator(
        "pub_title", "source_url", "raw_data_format", "dataset_identifier",
        "data_repository", "dataset_context_from_paper", "dataset_keywords",
        "citation_type", "dataset_webpage", "access_mode",
        mode="before",
    )
    @classmethod
    def to_str(cls, v: object) -> str:
        return _coerce_str(v)

    @field_validator("source_url")
    @classmethod
    def source_url_required(cls, v: str) -> str:
        if not v:
            raise ValueError("source_url is required - the join key back to the citing publication")
        return v

    @field_validator("dataset_identifier")
    @classmethod
    def dataset_identifier_required(cls, v: str) -> str:
        if not v:
            raise ValueError("dataset_identifier is required - a dataset mention must identify a dataset")
        return v

    @field_validator("citation_type")
    @classmethod
    def citation_type_known(cls, v: str) -> str:
        if v and v not in {"Primary", "Secondary"}:
            raise ValueError(f"citation_type {v!r} isn't 'Primary' or 'Secondary'")
        return v

    COLUMNS: ClassVar[list[str]] = [
        "pub_title", "source_url", "raw_data_format", "dataset_identifier",
        "data_repository", "dataset_context_from_paper", "dataset_keywords",
        "citation_type", "dataset_webpage", "access_mode",
    ]


# ---------------------------------------------------------------------------
# Table: Supplementary files   (tables/final/pub_supplementary_*.tsv)
#
# Audited 2026-09-08 - same "completely different field set, would validate
# everything as fine" problem as PubDatasetRow, plus this table's real file
# has the worst raw-scraper leakage found in this audit: `a_attr_href`,
# `a_attr_class`, `a_attr_data-ga-action`, `a_attr_target`, `a_attr_rel` are
# literal HTML anchor-tag attributes (<1% populated) that never should have
# left the scraper, alongside `retrieval_pattern`/`file_info`/`section_class`/
# `repository_reference` (also near-fully blank). `id` and `content_type` ARE
# real, well-populated columns (id: ~99% populated, e.g. "SD1"/"SD2" labels)
# that simply weren't in the old field list at all - rebuilt below.
# ---------------------------------------------------------------------------
class SupplementaryRow(_Base):
    link: str = ""
    source_url: str = ""
    download_link: str = ""
    title: str = ""
    content_type: str = ""
    id: str = ""
    caption: str = ""
    description: str = ""
    source_section: str = ""
    context_description: str = ""
    file_extension: str = ""
    pub_title: str = ""
    raw_data_format: str = ""
    dataset_identifier: str = ""
    data_repository: str = ""
    dataset_webpage: str = ""
    access_mode: str = ""

    @field_validator(
        "link", "source_url", "download_link", "title", "content_type", "id",
        "caption", "description", "source_section", "context_description",
        "file_extension", "pub_title", "raw_data_format", "dataset_identifier",
        "data_repository", "dataset_webpage", "access_mode",
        mode="before",
    )
    @classmethod
    def to_str(cls, v: object) -> str:
        return _coerce_str(v)

    @field_validator("source_url")
    @classmethod
    def source_url_required(cls, v: str) -> str:
        if not v:
            raise ValueError("source_url is required - the join key back to the citing publication")
        return v

    COLUMNS: ClassVar[list[str]] = [
        "link", "source_url", "download_link", "title", "content_type", "id",
        "caption", "description", "source_section", "context_description",
        "file_extension", "pub_title", "raw_data_format", "dataset_identifier",
        "data_repository", "dataset_webpage", "access_mode",
    ]


# ---------------------------------------------------------------------------
# Table: Publication grants   (tables/final/pub_grants_*.tsv)
#
# Audited 2026-09-08 - rebuilt to the real lowercase snake_case columns (same
# "wrong field set entirely" issue as the two tables above). The real current
# file also carries `following`/`V`/`PI`/`grants`/`Union.`/`ID` - all <0.05%
# populated, and the `grants` column's own content is a literal stringified
# Python dict fragment ("[{'funder_name': 'n/a', ...") - a real upstream
# extraction bug (a multi-grant JSON list getting mis-flattened into stray
# columns), not just a naming mismatch. Excluded here; the actual bug lives
# in whatever produces pub_grants_*.tsv and is out of scope for this audit.
# ---------------------------------------------------------------------------
class PubGrantRow(_Base):
    funder_name: str = ""
    funding_context_from_paper: str = ""
    recipient: str = ""
    grant_number: str = ""
    source_url: str = ""

    @field_validator(
        "funder_name", "funding_context_from_paper", "recipient",
        "grant_number", "source_url",
        mode="before",
    )
    @classmethod
    def to_str(cls, v: object) -> str:
        return _coerce_str(v)

    @field_validator("source_url")
    @classmethod
    def source_url_required(cls, v: str) -> str:
        if not v:
            raise ValueError("source_url is required - the join key back to the citing publication")
        return v

    COLUMNS: ClassVar[list[str]] = [
        "funder_name", "funding_context_from_paper", "recipient",
        "grant_number", "source_url",
    ]


# ---------------------------------------------------------------------------
# Table: Publication software mentions   (tables/final/pub_software_*.tsv)
#
# Audited 2026-09-08 - rebuilt to the real lowercase snake_case columns. The
# real current file also carries `software_mentions` (<0.1% populated, the
# same mis-flattened-list artifact as pub_grants' `grants` column) - excluded
# for the same reason.
# ---------------------------------------------------------------------------
class PubSoftwareRow(_Base):
    software_name: str = ""
    version: str = ""
    mention_type: str = ""
    url: str = ""
    context_from_paper: str = ""
    source_url: str = ""

    @field_validator(
        "software_name", "version", "mention_type", "url",
        "context_from_paper", "source_url",
        mode="before",
    )
    @classmethod
    def to_str(cls, v: object) -> str:
        return _coerce_str(v)

    @field_validator("source_url")
    @classmethod
    def source_url_required(cls, v: str) -> str:
        if not v:
            raise ValueError("source_url is required - the join key back to the citing publication")
        return v

    @field_validator("software_name")
    @classmethod
    def software_name_required(cls, v: str) -> str:
        if not v:
            raise ValueError("software_name is required - a software mention must name the software")
        return v

    @field_validator("mention_type")
    @classmethod
    def mention_type_known(cls, v: str) -> str:
        if v and v not in {"used", "created"}:
            raise ValueError(f"mention_type {v!r} isn't 'used' or 'created'")
        return v

    COLUMNS: ClassVar[list[str]] = [
        "software_name", "version", "mention_type", "url",
        "context_from_paper", "source_url",
    ]


# ---------------------------------------------------------------------------
# Table: Publication pretrained-model mentions   (tables/final/pub_models_*.tsv)
#
# Audited 2026-09-08 - rebuilt to the real lowercase snake_case columns (this
# table's real file has no extra junk columns, unlike its siblings above).
# ---------------------------------------------------------------------------
class PubModelRow(_Base):
    model_name: str = ""
    version: str = ""
    mention_type: str = ""
    url: str = ""
    context_from_paper: str = ""
    source_url: str = ""

    @field_validator(
        "model_name", "version", "mention_type", "url",
        "context_from_paper", "source_url",
        mode="before",
    )
    @classmethod
    def to_str(cls, v: object) -> str:
        return _coerce_str(v)

    @field_validator("source_url")
    @classmethod
    def source_url_required(cls, v: str) -> str:
        if not v:
            raise ValueError("source_url is required - the join key back to the citing publication")
        return v

    @field_validator("model_name")
    @classmethod
    def model_name_required(cls, v: str) -> str:
        if not v:
            raise ValueError("model_name is required - a model mention must name the model")
        return v

    COLUMNS: ClassVar[list[str]] = [
        "model_name", "version", "mention_type", "url",
        "context_from_paper", "source_url",
    ]


# ---------------------------------------------------------------------------
# Table: Publication verification results   (tables/final/pub_verification_*.tsv)
#
# NOT audited 2026-09-08, NOT in VALIDATED_TARGETS - pipelines/pub_verification.py
# is explicitly WIP ("not yet wired into orchestrator.py" per its own module
# docstring) and has never produced a tables/final/ file (only tables/hits/
# pub_verification_*.tsv exists). Audit this one for real once that stage
# actually ships.
# ---------------------------------------------------------------------------
class PubVerificationRow(_Base):
    Resource_Name: str = ""
    Doc_ID: str = ""
    URL: str = ""
    Verification_Status: str = ""
    Claim_Text: str = ""
    Rationale: str = ""
    Method: str = ""

    model_config = {
        "populate_by_name": True,
        "alias_generator": lambda s: s.replace("_", " "),
    }

    @field_validator(
        "Resource_Name", "Doc_ID", "URL", "Verification_Status",
        "Claim_Text", "Rationale", "Method",
        mode="before",
    )
    @classmethod
    def to_str(cls, v: object) -> str:
        return _coerce_str(v)

    COLUMNS: ClassVar[list[str]] = [
        "Resource Name", "Doc ID", "URL", "Verification Status",
        "Claim Text", "Rationale", "Method",
    ]


# ---------------------------------------------------------------------------
# Table: New Corpus   (tables/final/new_corpus_*.tsv)
#
# NOT audited 2026-09-08, NOT in VALIDATED_TARGETS, and not a good fit for
# fixed-schema row validation at all - the real file's shape is inherently
# dynamic: one column per scraped page/URL, exploded further into per-index
# array columns (e.g. "new_corpus.<page-url>[i]"), different for every
# resource's own publications-listing page. staging/publication_glue.py's
# extract_new_corpus_publications() is what turns this into a fixed,
# validate-able shape - and that output already flows into misc_publications,
# which IS validated (see MiscPublicationRow). Validating new_corpus itself
# would mean validating a table that's supposed to look different every run.
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
# Table: SciLite annotations   (tables/final/scilite_annotations_*.tsv)
#
# Audited 2026-09-08 - the real current file (957,709 rows) also carries
# subType/frequency/fileName, which the Title-Case-with-space alias_generator
# below can't produce aliases for (they're camelCase/lowercase, not Title
# Case) - given explicit per-field aliases instead, which Pydantic v2 lets
# override the model-level alias_generator. Kept intentionally lightweight
# (few validators) given this table's row count - a per-row Pydantic call is
# cheap, but not free at ~1M rows.
# ---------------------------------------------------------------------------
class SciLiteAnnotationRow(_Base):
    PMC_ID: str = ""
    Type: str = ""
    Exact: str = ""
    Prefix: str = ""
    Postfix: str = ""
    Section: str = ""
    Provider: str = ""
    Annotation_ID: str = ""
    Tag_Name: str = ""
    Tag_URI: str = ""
    subType: str = Field(default="", alias="subType")
    frequency: str = Field(default="", alias="frequency")
    fileName: str = Field(default="", alias="fileName")

    model_config = {
        "populate_by_name": True,
        "alias_generator": lambda s: s.replace("_", " "),
    }

    @field_validator(
        "PMC_ID", "Type", "Exact", "Prefix", "Postfix", "Section",
        "Provider", "Annotation_ID", "Tag_Name", "Tag_URI",
        "subType", "frequency", "fileName",
        mode="before",
    )
    @classmethod
    def to_str(cls, v: object) -> str:
        return _coerce_str(v)

    @field_validator("PMC_ID")
    @classmethod
    def pmc_id_required(cls, v: str) -> str:
        if not v:
            raise ValueError("PMC ID is required - an annotation must be tied to a publication")
        return v

    @field_validator("Type")
    @classmethod
    def type_required(cls, v: str) -> str:
        if not v:
            raise ValueError("Type is required")
        return v

    COLUMNS: ClassVar[list[str]] = [
        "PMC ID", "Type", "Exact", "Prefix", "Postfix", "Section",
        "Provider", "Annotation ID", "Tag Name", "Tag URI",
        "subType", "frequency", "fileName",
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
#
# NOTE (2026-09-08): this registry is currently NOT wired into
# staging/normalizer.py's normalize() - it's declared here but nothing looks
# it up. Don't assume a target listed here is actually being validated
# anywhere; see VALIDATED_TARGETS below for the (currently much smaller) set
# that genuinely is.
# ---------------------------------------------------------------------------
SCHEMA_REGISTRY: dict[str, type[_Base]] = {
    "publications": PublicationRow,
    "misc_publications": MiscPublicationRow,
    "code": CodeRepoRow,
    "pub_datasets": PubDatasetRow,
    "supplementary": SupplementaryRow,
    "pub_grants": PubGrantRow,
    "pub_software": PubSoftwareRow,
    "pub_models": PubModelRow,
    "pub_verification": PubVerificationRow,
    "new_corpus": NewCorpusRow,
    "scilite": SciLiteAnnotationRow,
}


# ---------------------------------------------------------------------------
# Targets normalize() actually validates (hard-reject to tables/hits/
# rejected_{target}_{ts}.tsv) - deliberately a small, explicit opt-in list,
# NOT "every key in SCHEMA_REGISTRY". Every model in this file was audited on
# 2026-09-08 against its table's real current tables/final/ columns; the
# ones below matched (code) or were rebuilt to match (everything else except
# publications/pub_verification/new_corpus - see those classes' own
# docstrings/comments for why they're excluded). Add a new target here only
# after the same audit: confirm the model's fields match the real file's
# columns, or every row will validate as trivially "fine" using nothing but
# field defaults.
# ---------------------------------------------------------------------------
VALIDATED_TARGETS: dict[str, type[_Base]] = {
    "misc_publications": MiscPublicationRow,
    "code": CodeRepoRow,
    "pub_datasets": PubDatasetRow,
    "supplementary": SupplementaryRow,
    "pub_grants": PubGrantRow,
    "pub_software": PubSoftwareRow,
    "pub_models": PubModelRow,
    "scilite": SciLiteAnnotationRow,
}
