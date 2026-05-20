"""
Datasets & Supplementary Files page.

Two sections:
- Publication Datasets: datasets referenced or used by cataloged publications.
- Supplementary Files: supplementary materials attached to cataloged publications.
"""

import logging
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.append(str(Path(__file__).parent.parent))

from utils.data_loader import (
    filter_dataframe,
    get_unique_values,
    load_pub_datasets,
    load_pub_supplementary,
    load_scilite_annotations,
    search_across_columns,
)
from utils.export_utils import (
    export_dataframe_csv,
    export_dataframe_json,
    export_dataframe_tsv,
    export_text_summary,
)

st.set_page_config(
    page_title="Datasets & Supplementary Files - CARD Catalog",
    page_icon="🗂️",
    layout="wide",
)

logger = logging.getLogger(__name__)

css_file = Path(__file__).parent.parent / "assets" / "style.css"
if css_file.exists():
    with open(css_file) as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _multiselect_from_col(df: pd.DataFrame, col: str, label: str, key: str) -> list:
    """Return a multiselect widget populated from a DataFrame column."""
    if col not in df.columns:
        return []
    options = sorted(df[col].replace("", pd.NA).dropna().unique().tolist())
    return st.multiselect(label, options=options, key=key)


def _download_row(filtered: pd.DataFrame, base_name: str) -> None:
    """Render a row of export download buttons for *filtered*."""
    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "📥 Export as CSV",
            export_dataframe_csv(filtered),
            f"{base_name}.csv",
            "text/csv",
        )
        st.download_button(
            "📥 Export as TSV",
            export_dataframe_tsv(filtered),
            f"{base_name}.tsv",
            "text/tab-separated-values",
        )
    with col2:
        st.download_button(
            "📥 Export as JSON",
            export_dataframe_json(filtered),
            f"{base_name}.json",
            "application/json",
        )
        st.download_button(
            "📥 Export as Text",
            export_text_summary(filtered, base_name.replace("_", " ").title()),
            f"{base_name}.txt",
            "text/plain",
        )


# ---------------------------------------------------------------------------
# Datasets tab
# ---------------------------------------------------------------------------

def _render_datasets_tab() -> None:
    df = load_pub_datasets()

    if df.empty:
        st.error("No publication dataset records available. Please check data files.")
        return

    pmc_filter = st.session_state.get("resource_pmc_filter")
    if pmc_filter and "source_url" in df.columns:
        df = df[df["source_url"].astype(str).str.contains(pmc_filter, na=False)]

    with st.expander("🔍 Filters", expanded=False):
        search_term = st.text_input(
            "Search across all columns",
            key="ds_search",
            help="Case-insensitive keyword search across all dataset fields",
        )
        fc1, fc2, fc3 = st.columns(3)
        with fc1:
            selected_studies = _multiselect_from_col(
                df, "Source Resource Name", "Study", "ds_studies"
            )
        with fc2:
            selected_citation = _multiselect_from_col(
                df, "Citation Type", "Citation Type", "ds_citation"
            )
        with fc3:
            selected_repos = _multiselect_from_col(
                df, "Data Repository", "Data Repository", "ds_repos"
            )

    filtered = df.copy()
    if search_term:
        filtered = search_across_columns(filtered, search_term)

    field_filters: dict = {}
    if selected_studies:
        field_filters["Source Resource Name"] = selected_studies
    if selected_citation:
        field_filters["Citation Type"] = selected_citation
    if selected_repos:
        field_filters["Data Repository"] = selected_repos
    if field_filters:
        filtered = filter_dataframe(filtered, field_filters)

    st.info(f"Showing {len(filtered)} of {len(df)} dataset references")

    tab_table, tab_browse, tab_export = st.tabs(["📊 Table", "📋 Browse", "📥 Export"])

    with tab_table:
        if filtered.empty:
            st.warning("No dataset records match the current filters.")
        else:
            st.dataframe(filtered, use_container_width=True, height=600)

    with tab_browse:
        if filtered.empty:
            st.warning("No dataset records match the current filters.")
        else:
            for _, row in filtered.iterrows():
                identifier = row.get("Dataset Identifier", "") or row.get("Source Resource Name", "Unknown")
                study = row.get("Source Resource Name", "")
                header = f"**{identifier}**"
                if study and study != identifier:
                    header += f" — {study}"

                with st.expander(header):
                    c1, c2 = st.columns(2)
                    with c1:
                        if row.get("Source Resource Name"):
                            st.markdown(f"**Study:** {row['Source Resource Name']}")
                        if row.get("Citation Type"):
                            st.markdown(f"**Citation Type:** {row['Citation Type']}")
                        if row.get("Data Repository"):
                            st.markdown(f"**Data Repository:** {row['Data Repository']}")
                        if row.get("raw data format"):
                            st.markdown(f"**Raw Data Format:** {row['raw data format']}")
                    with c2:
                        webpage = row.get("Dataset Webpage", "")
                        if webpage:
                            st.markdown(f"**Dataset Webpage:** [{webpage}]({webpage})")
                        source_url = row.get("source url", "")
                        if source_url:
                            st.markdown(f"**Source Publication:** [{source_url}]({source_url})")

                    usage = row.get("Usage Description", "")
                    if usage:
                        with st.expander("Usage Description"):
                            st.markdown(usage)

                    rationale = row.get("Decision Rationale", "")
                    if rationale:
                        with st.expander("Decision Rationale"):
                            st.markdown(rationale)

    with tab_export:
        if filtered.empty:
            st.warning("No records to export.")
        else:
            st.markdown(f"**Export {len(filtered)} dataset records**")
            _download_row(filtered, "pub_datasets")


# ---------------------------------------------------------------------------
# Supplementary Files tab
# ---------------------------------------------------------------------------

def _render_supplementary_tab() -> None:
    df = load_pub_supplementary()

    if df.empty:
        st.error("No supplementary file records available. Please check data files.")
        return

    pmc_filter = st.session_state.get("resource_pmc_filter")
    if pmc_filter and "source_url" in df.columns:
        df = df[df["source_url"].astype(str).str.contains(pmc_filter, na=False)]

    # Decide which column represents the file type for filtering
    ext_col = (
        "File Extension" if "File Extension" in df.columns
        else "content type" if "content type" in df.columns
        else None
    )

    with st.expander("🔍 Filters", expanded=False):
        search_supp = st.text_input(
            "Search across all columns",
            key="supp_search",
            help="Case-insensitive keyword search across all supplementary file fields",
        )
        fc1, fc2 = st.columns(2)
        with fc1:
            selected_types: list = []
            if ext_col:
                label = "File Extension" if ext_col == "File Extension" else "Content Type"
                selected_types = _multiselect_from_col(df, ext_col, label, "supp_type")
        with fc2:
            selected_kws: list = []
            if "Keywords" in df.columns:
                kws = get_unique_values(df, "Keywords", delimiter=";")
                if kws:
                    selected_kws = st.multiselect(
                        "Keywords", options=kws[:100], key="supp_kw"
                    )

    filtered = df.copy()
    if search_supp:
        filtered = search_across_columns(filtered, search_supp)

    field_filters: dict = {}
    if selected_types and ext_col:
        field_filters[ext_col] = selected_types
    if selected_kws:
        field_filters["Keywords"] = selected_kws
    if field_filters:
        filtered = filter_dataframe(filtered, field_filters)

    st.info(f"Showing {len(filtered)} of {len(df)} supplementary file records")

    tab_table, tab_browse, tab_export = st.tabs(["📊 Table", "📋 Browse", "📥 Export"])

    with tab_table:
        if filtered.empty:
            st.warning("No supplementary file records match the current filters.")
        else:
            st.dataframe(filtered, use_container_width=True, height=600)

    with tab_browse:
        if filtered.empty:
            st.warning("No records match the current filters.")
        else:
            for _, row in filtered.iterrows():
                fname = row.get("File Name", "") or row.get("title", "Unknown File")
                with st.expander(f"**{fname}**"):
                    c1, c2 = st.columns(2)
                    with c1:
                        if row.get("Source Resource Name"):
                            st.markdown(f"**Study:** {row['Source Resource Name']}")
                        if row.get("File Extension"):
                            st.markdown(f"**Extension:** {row['File Extension']}")
                        elif row.get("content type"):
                            st.markdown(f"**Content Type:** {row['content type']}")
                        if row.get("File Format"):
                            st.markdown(f"**Format:** {row['File Format']}")
                        elif row.get("retrieval pattern"):
                            st.markdown(f"**Retrieved via:** {row['retrieval pattern']}")
                    with c2:
                        file_url = row.get("File URL", "")
                        if file_url:
                            st.markdown(f"**Download:** [{fname}]({file_url})")
                        source_url = row.get("source url", "")
                        if source_url:
                            st.markdown(f"**Source Publication:** [{source_url}]({source_url})")
                        if row.get("Keywords"):
                            st.markdown(f"**Keywords:** {row['Keywords']}")

                    caption = row.get("caption", "")
                    if caption and caption not in ("No description", ""):
                        st.markdown(f"**Caption:** {caption}")

    with tab_export:
        if filtered.empty:
            st.warning("No records to export.")
        else:
            st.markdown(f"**Export {len(filtered)} supplementary file records**")
            _download_row(filtered, "pub_supplementary")


# ---------------------------------------------------------------------------
# SciLite Annotations tab
# ---------------------------------------------------------------------------

def _render_scilite_tab() -> None:
    df = load_scilite_annotations()

    if df.empty:
        st.error("No SciLite annotation records available. Please check data files.")
        return

    pmc_filter = st.session_state.get("resource_pmc_filter")
    if pmc_filter and "PMC ID" in df.columns:
        df = df[df["PMC ID"] == pmc_filter]

    with st.expander("🔍 Filters", expanded=False):
        search_sci = st.text_input(
            "Search across all columns",
            key="sci_search",
            help="Case-insensitive keyword search across all annotation fields",
        )
        fc1, fc2, fc3 = st.columns(3)
        with fc1:
            selected_types = _multiselect_from_col(df, "Type", "Annotation Type", "sci_types")
        with fc2:
            selected_sections = _multiselect_from_col(df, "Section", "Section", "sci_sections")
        with fc3:
            selected_tags = _multiselect_from_col(df, "Tag Name", "Tag (concept)", "sci_tags")

    filtered = df.copy()
    if search_sci:
        filtered = search_across_columns(filtered, search_sci)

    field_filters: dict = {}
    if selected_types:
        field_filters["Type"] = selected_types
    if selected_sections:
        field_filters["Section"] = selected_sections
    if selected_tags:
        field_filters["Tag Name"] = selected_tags
    if field_filters:
        filtered = filter_dataframe(filtered, field_filters)

    st.info(f"Showing {len(filtered)} of {len(df)} annotations")

    tab_table, tab_summary, tab_export = st.tabs(["📊 Table", "📈 Summary", "📥 Export"])

    with tab_table:
        if filtered.empty:
            st.warning("No annotations match the current filters.")
        else:
            st.dataframe(filtered, use_container_width=True, height=600)

    with tab_summary:
        if filtered.empty:
            st.warning("No annotations to summarise.")
        else:
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**By Type**")
                st.dataframe(
                    filtered["Type"].value_counts().rename_axis("Type").reset_index(name="Count"),
                    use_container_width=True, hide_index=True,
                )
            with c2:
                st.markdown("**Top Tags**")
                st.dataframe(
                    filtered["Tag Name"].value_counts().head(50)
                        .rename_axis("Tag Name").reset_index(name="Count"),
                    use_container_width=True, hide_index=True,
                )
            st.markdown("**Annotations per PMC (top 20)**")
            st.dataframe(
                filtered.groupby("PMC ID").size().sort_values(ascending=False).head(20)
                    .rename_axis("PMC ID").reset_index(name="Count"),
                use_container_width=True, hide_index=True,
            )

    with tab_export:
        if filtered.empty:
            st.warning("No records to export.")
        else:
            st.markdown(f"**Export {len(filtered)} annotation records**")
            _download_row(filtered, "scilite_annotations")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

_TAB_LABELS = [
    "📦 Publication Datasets",
    "📎 Supplementary Files",
    "🏷️ SciLite Annotations",
]
_TAB_KEYS = ["datasets", "supplementary", "scilite"]


def main() -> None:
    """Main entry point for the Datasets & Supplementary Files page."""
    st.title("🗂️ Datasets & Supplementary Files")
    st.markdown(
        "Explore datasets referenced by publications, supplementary materials, "
        "and Europe PMC SciLite annotations across cataloged studies."
    )

    pmc_filter = st.session_state.get("resource_pmc_filter")
    if pmc_filter:
        c_msg, c_clear = st.columns([5, 1])
        with c_msg:
            st.info(f"🔎 Filtered to publication **{pmc_filter}** (from Publications page)")
        with c_clear:
            if st.button("Clear filter", key="clear_pmc_filter"):
                st.session_state.pop("resource_pmc_filter", None)
                st.session_state.pop("resource_focus_tab", None)
                st.rerun()

    with st.sidebar:
        st.markdown("### App Controls")
        if st.button("🔄 Restart App", help="Restart the Streamlit application"):
            st.rerun()
        if st.button("🗑️ Clear Cache", help="Clear cached data and reload"):
            st.cache_data.clear()
            st.rerun()
        st.markdown("---")

    focus = st.session_state.pop("resource_focus_tab", None)
    if focus in _TAB_KEYS:
        # Reorder tabs so the requested one shows up first
        idx = _TAB_KEYS.index(focus)
        order = [idx] + [i for i in range(len(_TAB_KEYS)) if i != idx]
    else:
        order = list(range(len(_TAB_KEYS)))

    labels = [_TAB_LABELS[i] for i in order]
    keys = [_TAB_KEYS[i] for i in order]
    tabs = st.tabs(labels)

    renderers = {
        "datasets": _render_datasets_tab,
        "supplementary": _render_supplementary_tab,
        "scilite": _render_scilite_tab,
    }
    for tab, key in zip(tabs, keys):
        with tab:
            renderers[key]()


if __name__ == "__main__":
    main()
