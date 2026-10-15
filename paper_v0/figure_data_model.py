"""Generate the CARD Catalog conceptual data-model figure (SVG + PNG).

Relationships drawn here mirror the Connections page's join model exactly -
web/src/lib/connectionsGraph.ts (PUBLICATION_FIELDS / RESOURCE_FIELDS) and
staging/publication_glue.py::join_cellular_model_publications for the two
precomputed Human Cellular Models columns. Update this file if either changes.

Run: venv/bin/python paper_v0/figure_data_model.py

Counts are computed at render time from the same files web/scripts/sync-data.sh
copies into the app (newest by mtime), using the same key extraction as
connectionsGraph.ts (PMC ID, falling back to DOI; semicolon-split multivalues).
Every number drawn is also written to v0.4/figure_data_model_counts.tsv.
"""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
import unicodedata
from pathlib import Path
from xml.sax.saxutils import escape

import pandas as pd

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
TABLES_DIR = PROJECT_ROOT / "tables"
FINAL_DIR = TABLES_DIR / "final"
HITS_DIR = TABLES_DIR / "hits"
OUTPUT_DIR = Path(__file__).parent / "v0.4"
PNG_DPI_SCALE = 3  # 1780 px wide viewBox -> 5340 px PNG (~600 dpi at 180 mm width)

W = 1780
FONT = "Helvetica, Arial, sans-serif"

# Join domains (connectionsGraph.ts Domain) - one colour each.
PUB = "#2b5d9b"   # publication domain: PMC ID / DOI
RES = "#c0631b"   # resource domain: Resource Name
VAR = "#2e7d4f"   # variant/gene key: HCM dbSNP / Gene <-> SciLite Tag Name / Exact
INK = "#1d2430"
MUTED = "#5b6574"
RULE = "#d5dae1"

CORE_FILL, CORE_HEAD = "#ffffff", "#e9eef5"
HUB_HEAD = "#dde7f3"
SUPPORT_FILL, SUPPORT_HEAD = "#ffffff", "#f3f4f6"

CORE_ROW_H, SUPPORT_ROW_H = 27, 25
CORE_HEAD_H, SUPPORT_HEAD_H = 72, 62

# Key fields come first in every list - edges anchor to rows by index.
# (name, key colour or None, derived)
KEYS = {
    "Resources": [("Resource Name", RES, False)],
    "Publications": [("Resource Name", RES, False), ("PubMed Central Link (PMC ID)", PUB, False),
                     ("DOI", PUB, False)],
    "Code Repositories": [("Resource Name", RES, False)],
    "Human Cellular Models": [("dbSNP", VAR, False), ("Gene", VAR, False)],
}
# Pipeline-added columns (join_cellular_model_publications) - listed last, as in the TSV.
ADDED = {
    "Human Cellular Models": [("Linked Publications (PMC IDs)", PUB, True),
                              ("Linked Studies (Resource Names)", RES, True)],
}
SOURCE_URL_KEY = [("source_url  →  PMC ID / DOI", PUB, False)]

CURATED = {
    "Resources": ["Abbreviation", "Resource Type", "Diseases Included", "Coarse / Granular Data Modality",
                  "Access URL"],
    "Publications": ["PMID", "Title / Abstract", "Authors / Affiliations", "Keywords · Publication Year"],
    "Code Repositories": ["Repository Link", "Owner / Contributors", "Languages · Tooling", "Data Types",
                          "FAIR Score / FAIR Issues"],
    "Human Cellular Models": ["Product Code · Parental Line", "Gene Variant · Genotype", "Condition"],
    "Cited Datasets": ["dataset_identifier · data_repository", "access_mode"],
    "Supplementary Files": ["content_type · file_extension"],
    "Grants": ["funder_name · grant_number"],
    "Software Mentions": ["software_name · url"],
    "Models": ["model_name · url"],
    "SciLite Annotations": ["Type · Section"],
}

SUPPORTS = [
    ("Cited Datasets", "Datasets cited in a paper", SOURCE_URL_KEY),
    ("Supplementary Files", "Files deposited with a paper", SOURCE_URL_KEY),
    ("Grants", "Funding acknowledged in a paper", SOURCE_URL_KEY),
    ("Software Mentions", "Software used in a paper", SOURCE_URL_KEY),
    ("Models", "ML/AI models used in a paper", SOURCE_URL_KEY),
    ("SciLite Annotations", "Europe PMC text-mined entities", [
        ("PMC ID", PUB, False),
        ("Tag Name  [RefSNP subset]", VAR, False),
        ("Exact  [Gene_Proteins subset]", VAR, False),
    ]),
]


# --- Counts --------------------------------------------------------------

_DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>]+")
_PMC_RE = re.compile(r"PMC\d+")


def _pub_key(value: str) -> str:
    """PMC ID, else normalised DOI, else "" - mirrors connectionsGraph.ts publicationKey()."""
    m = _PMC_RE.search(value)
    if m:
        return m.group(0)
    m = _DOI_RE.search(value)
    return re.sub(r"[.,;)\]]+$", "", m.group(0).lower()) if m else ""


def _split(value: str) -> list[str]:
    return [v.strip() for v in value.split(";") if v.strip()]


_APOSTROPHE_VARIANTS_RE = re.compile("[\u2019\u02BC\u0060\u00B4\u2018\u201B]")


def _resource_key(value: str) -> str:
    """Resource Name join key - mirrors connectionsGraph.ts resourceKey()."""
    return _APOSTROPHE_VARIANTS_RE.sub("'", unicodedata.normalize("NFKC", value)).strip()


def _repo_key(url: str) -> str:
    """owner/repo, lower-cased (GitHub URLs are case-insensitive), without .git."""
    m = re.search(r"github\.com/([\w.\-]+)/([\w.\-]+)", url, re.I)
    if not m:
        return ""
    name = m.group(2)[:-4] if m.group(2).endswith(".git") else m.group(2)
    return f"{m.group(1)}/{name}".lower()


def _latest(directory: Path, pattern: str) -> Path:
    """Newest file by mtime - the same rule sync-data.sh uses to pick what the app serves."""
    files = list(directory.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No {pattern} in {directory}")
    return max(files, key=lambda f: f.stat().st_mtime)


def compute_counts() -> tuple[dict[str, int], list[tuple[str, int, str]]]:
    """Row and link counts for every number drawn on the figure.

    Returns:
        (counts by key, [(metric, value, source file)] for the sidecar TSV).
    """
    rows: list[tuple[str, int, str]] = []
    c: dict[str, int] = {}

    def put(key: str, metric: str, value: int, source: Path) -> None:
        c[key] = int(value)
        rows.append((metric, int(value), source.name))

    def load(directory: Path, pattern: str, **kw) -> tuple[Path, pd.DataFrame]:
        f = _latest(directory, pattern)
        logger.info(f"Loading {f.name}")
        return f, pd.read_csv(f, sep="\t", dtype=str, **kw).fillna("")

    f_res, res = load(TABLES_DIR, "resources-inventory-*")
    res_names = set(res["Resource Name"].map(_resource_key)) - {""}
    put("res_n", "Resources: rows", len(res), f_res)

    f_pub, pub = load(FINAL_DIR, "misc_publications_*.tsv")
    pub_keys = {k for col in ("PubMed Central Link", "DOI") for k in pub[col].map(_pub_key) if k}
    put("pub_n", "Publications: rows", len(pub), f_pub)
    pub_res = pub["Resource Name"].map(lambda v: [n for n in map(_resource_key, _split(v)) if n in res_names])
    put("pub_res_rows", "Publications -> Resources: papers with a Resource Name in Resources",
        (pub_res.str.len() > 0).sum(), f_pub)
    put("pub_res_targets", "Publications -> Resources: distinct Resources reached",
        len({n for ns in pub_res for n in ns}), f_pub)

    f_code, code = load(FINAL_DIR, "gits_to_reannotate_completed_*.tsv")
    put("code_n", "Code Repositories: rows", len(code), f_code)
    code_res = code["Resource Name"].map(lambda v: [n for n in map(_resource_key, _split(v)) if n in res_names])
    put("code_res_rows", "Code Repositories -> Resources: repositories with a Resource Name in Resources",
        (code_res.str.len() > 0).sum(), f_code)
    put("code_res_targets", "Code Repositories -> Resources: distinct Resources reached",
        len({n for ns in code_res for n in ns}), f_code)

    for key, pattern in [("datasets", "pub_datasets_*.tsv"), ("supp", "pub_supplementary_*.tsv"),
                         ("grants", "pub_grants_*.tsv"), ("software", "pub_software_*.tsv"),
                         ("models", "pub_models_*.tsv")]:
        f, df = load(FINAL_DIR, pattern)
        put(f"{key}_n", f"{key}: rows", len(df), f)
        linked = set(df["source_url"].map(_pub_key)) & pub_keys
        put(f"{key}_papers", f"{key} -> Publications: distinct papers matched", len(linked), f)

    # Code Repositories provenance: union of two discovery routes (orchestrator.py hands GitHub
    # links from pub_software to github_search via --extra-repos). A repo counts as "software
    # mention" if its Source is the citing paper's URL, or its link appears in Software Mentions
    # or in any extra_repos_from_software_* handoff file; "GitHub search" if its Source says so,
    # or Source is blank and it never came through the software-mention route.
    f_sw = _latest(FINAL_DIR, "pub_software_*.tsv")
    sw_repos = set(pd.read_csv(f_sw, sep="\t", dtype=str).fillna("")["url"].map(_repo_key)) - {""}
    for f in HITS_DIR.glob("extra_repos_from_software_*.tsv"):
        sw_repos |= set(pd.read_csv(f, sep="\t", dtype=str).fillna("")["Repository Link"].map(_repo_key)) - {""}
    repo = code["Repository Link"].map(_repo_key)
    src = code["Source"].str.strip()
    via_sw = src.str.startswith("http") | repo.isin(sw_repos)
    via_gh = src.str.startswith("GitHub search") | ((src == "") & ~repo.isin(sw_repos))
    put("code_via_gh", "Code Repositories: found via GitHub search", via_gh.sum(), f_code)
    put("code_via_sw", "Code Repositories: found via paper software mentions", via_sw.sum(), f_code)
    put("code_via_both", "Code Repositories: found via both routes", (via_gh & via_sw).sum(), f_code)
    if (via_gh | via_sw).sum() != len(code):
        logger.warning(f"{len(code) - (via_gh | via_sw).sum()} code repositories attributed to neither route")

    f_sc = _latest(FINAL_DIR, "scilite_annotations_*.tsv")
    logger.info(f"Loading {f_sc.name}")
    sc = pd.read_csv(f_sc, sep="\t", dtype=str,
                     usecols=["PMC ID", "Type", "subType", "Exact", "Tag Name"]).fillna("")
    put("scilite_n", "SciLite Annotations: rows", len(sc), f_sc)
    put("scilite_papers", "SciLite -> Publications: distinct papers matched",
        len(set(sc["PMC ID"].str.strip()) & pub_keys), f_sc)

    f_hcm, hcm = load(FINAL_DIR, "cellular_models_*.tsv")
    put("hcm_n", "Human Cellular Models: rows", len(hcm), f_hcm)
    lp = hcm["Linked Publications"].map(lambda v: [k for k in _split(v) if k in pub_keys])
    put("hcm_pub_rows", "HCM -> Publications: lines with a Linked Publication in Publications",
        (lp.str.len() > 0).sum(), f_hcm)
    put("hcm_pub_targets", "HCM -> Publications: distinct papers reached", len({k for ks in lp for k in ks}), f_hcm)
    ls = hcm["Linked Studies"].map(lambda v: [n for n in map(_resource_key, _split(v)) if n in res_names])
    put("hcm_res_rows", "HCM -> Resources: lines with a Linked Study in Resources",
        (ls.str.len() > 0).sum(), f_hcm)
    put("hcm_res_targets", "HCM -> Resources: distinct Resources reached", len({n for ns in ls for n in ns}), f_hcm)

    refsnp = set(sc.loc[(sc["Type"] == "Accession Numbers") & (sc["subType"] == "RefSNP"), "Tag Name"].str.strip())
    dbsnp = hcm["dbSNP"].str.strip()
    put("hcm_rs_rows", "HCM dbSNP = SciLite RefSNP Tag Name: lines matched", dbsnp.isin(refsnp - {""}).sum(), f_sc)
    put("hcm_rs_values", "HCM dbSNP = SciLite RefSNP Tag Name: distinct variants matched",
        len((set(dbsnp) - {""}) & refsnp), f_sc)
    genes_sc = set(sc.loc[sc["Type"] == "Gene_Proteins", "Exact"].str.strip())
    gene = hcm["Gene"].str.strip()
    put("hcm_gene_rows", "HCM Gene = SciLite Gene_Proteins Exact: lines matched", gene.isin(genes_sc - {""}).sum(), f_sc)
    put("hcm_gene_values", "HCM Gene = SciLite Gene_Proteins Exact: distinct genes matched",
        len((set(gene) - {""}) & genes_sc), f_sc)
    return c, rows


# --- Drawing -------------------------------------------------------------

def text(x, y, s, size=17, weight="normal", fill=INK, anchor="start", style="normal"):
    return (f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" font-weight="{weight}" '
            f'font-style="{style}" fill="{fill}" text-anchor="{anchor}">{escape(s)}</text>')


def label(x, y, s, color, size=16, anchor="middle", weight="bold"):
    """Edge label on a white halo so it stays legible over lines."""
    return (f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" font-weight="{weight}" fill="{color}" '
            f'text-anchor="{anchor}" stroke="#ffffff" stroke-width="6" paint-order="stroke" '
            f'stroke-linejoin="round">{escape(s)}</text>')


def row_y(box_y, index, tier="core"):
    """Vertical centre of field row `index` in an entity box (for edge anchors)."""
    head_h, row_h = (SUPPORT_HEAD_H, SUPPORT_ROW_H) if tier == "support" else (CORE_HEAD_H, CORE_ROW_H)
    return box_y + head_h + 8 + row_h * index + row_h * 0.72 - 5.5


def count_label(x, y, s, color):
    """Secondary (count) line under an edge label."""
    return label(x, y, s, color, size=15, weight="normal")


def label_with_count(x, y, head, count, color, anchor="start"):
    """Bold edge label followed by a regular-weight count on the same line."""
    return (f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="16" fill="{color}" text-anchor="{anchor}" '
            f'stroke="#ffffff" stroke-width="6" paint-order="stroke" stroke-linejoin="round">'
            f'<tspan font-weight="bold">{escape(head)}</tspan><tspan font-size="15" dx="12">{escape(count)}</tspan></text>')


def fmt(n: int) -> str:
    return f"{n:,}"


def entity(x, y, w, title, subtitle, fields, *, tier="core", n=None):
    """Entity box. fields: list of (name, key_colour_or_None, derived: bool)."""
    head_h, row_h = (SUPPORT_HEAD_H, SUPPORT_ROW_H) if tier == "support" else (CORE_HEAD_H, CORE_ROW_H)
    h = head_h + 14 + row_h * len(fields)
    fill, head = {"hub": (CORE_FILL, HUB_HEAD), "core": (CORE_FILL, CORE_HEAD),
                  "support": (SUPPORT_FILL, SUPPORT_HEAD)}[tier]
    stroke_w = {"hub": 2.6, "core": 1.8, "support": 1.2}[tier]
    stroke = {"hub": PUB, "core": "#7d8896", "support": "#aab2bd"}[tier]
    title_size = {"hub": 27, "core": 25, "support": 20}[tier]
    out = [
        "<g>",
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="9" fill="{fill}" stroke="none"/>',
        f'<path d="M{x},{y + head_h} V{y + 9} a9,9 0 0 1 9,-9 H{x + w - 9} a9,9 0 0 1 9,9 V{y + head_h} Z" '
        f'fill="{head}" stroke="none"/>',
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="9" fill="none" stroke="{stroke}" stroke-width="{stroke_w}"/>',
        f'<line x1="{x}" y1="{y + head_h}" x2="{x + w}" y2="{y + head_h}" stroke="{RULE}" stroke-width="1"/>',
        text(x + 18, y + (34 if tier != "support" else 29), title, title_size, "bold"),
        text(x + w - 16, y + (34 if tier != "support" else 29), f"n = {fmt(n)}" if n is not None else "",
             17 if tier != "support" else 15, "bold", MUTED, anchor="end"),
        text(x + 18, y + (59 if tier != "support" else 51), subtitle, 15 if tier == "support" else 16,
             fill=MUTED, style="italic"),
    ]
    for i, (name, key, derived) in enumerate(fields):
        fy = y + head_h + 8 + row_h * i + row_h * 0.72
        if key:
            out.append(f'<circle cx="{x + 24}" cy="{fy - 5.5}" r="5" fill="{key if not derived else "#ffffff"}" '
                       f'stroke="{key}" stroke-width="1.8"/>')
            out.append(text(x + 38, fy, name, 16.5, "bold", key))
        else:
            out.append(text(x + 38, fy, name, 16.5, fill=INK))
    out.append("</g>")
    return "\n".join(out), h


DASHED_W, DASH = 1.5, "7 5"  # derived links: thinner than the 2.4 direct links


def path(d, color, dashed=False, width=2.4):
    if dashed:
        width = DASHED_W
    dash = f' stroke-dasharray="{DASH}"' if dashed else ""
    marker = f' marker-end="url(#arrow-{ {PUB: "pub", RES: "res", VAR: "var"}[color]})"'
    return (f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}" '
            f'stroke-linejoin="round" stroke-linecap="round"{dash}{marker}/>')


def build_svg(c: dict[str, int]) -> str:
    """Render the data-model figure as an SVG string.

    Args:
        c: Counts from compute_counts().

    Returns:
        SVG document text.
    """
    def fields(table):
        return KEYS[table] + [(f, None, False) for f in CURATED[table]] + ADDED.get(table, [])

    body: list[str] = []

    # Section headings
    body.append(text(60, 42, "CORE ENTITIES", 15, "bold", MUTED))
    body.append(text(1310, 42, "PUBLICATION-LINKED ANNOTATIONS", 15, "bold", MUTED))
    body.append(f'<line x1="60" y1="54" x2="1090" y2="54" stroke="{RULE}" stroke-width="1"/>')
    body.append(f'<line x1="1310" y1="54" x2="1720" y2="54" stroke="{RULE}" stroke-width="1"/>')

    # --- Core entities ---------------------------------------------------
    top = 80
    res_x, res_w = 60, 400
    pub_x, pub_w = 650, 440
    box, res_h = entity(res_x, top, res_w, "Resources", "AD/ADRD studies & data resources", fields("Resources"),
                        n=c["res_n"])
    body.append(box)
    box, pub_h = entity(pub_x, top, pub_w, "Publications", "Papers using catalogued resources",
                        fields("Publications"), tier="hub", n=c["pub_n"])
    body.append(box)

    lower = top + max(res_h, pub_h) + 190  # room for the vertical edge labels
    code_x, code_w = res_x, res_w
    hcm_x, hcm_w = pub_x, pub_w
    box, code_h = entity(code_x, lower, code_w, "Code Repositories", "Analysis code tied to resources",
                         fields("Code Repositories"), n=c["code_n"])
    body.append(box)
    # Provenance note: the table is a union of two discovery routes.
    body.append(text(code_x + 4, lower + code_h + 26,
                     f"= {fmt(c['code_via_gh'])} via GitHub search  ∪  {fmt(c['code_via_sw'])} via software mentions",
                     15, fill=MUTED))
    body.append(text(code_x + 4, lower + code_h + 46, f"({fmt(c['code_via_both'])} found by both)", 15, fill=MUTED))
    box, hcm_h = entity(hcm_x, lower, hcm_w, "Human Cellular Models", "iPSC lines with engineered variants",
                        fields("Human Cellular Models"), n=c["hcm_n"])
    body.append(box)

    # --- Supporting / annotation entities --------------------------------
    sup_x, sup_w = 1310, 410
    sy = top
    sup_mid_ys = []
    sup_keys = ["datasets", "supp", "grants", "software", "models", "scilite"]
    for (table, sub, keys), ck in zip(SUPPORTS, sup_keys):
        box, h = entity(sup_x, sy, sup_w, table, sub, keys + [(f, None, False) for f in CURATED[table]],
                        tier="support", n=c[f"{ck}_n"])
        body.append(box)
        sup_mid_ys.append(row_y(sy, 0, "support"))  # PMC ID / source_url row
        sci_y, sci_h = sy, h  # last box is SciLite Annotations
        sy += h + 16
    sup_bottom = sy - 16

    # --- Relationships ---------------------------------------------------
    # Every edge leaves/enters its box at the height of the key row it joins on.
    hcm_rows = fields("Human Cellular Models")
    y_res_name = row_y(top, 0)            # Resources.Resource Name == Publications.Resource Name (row 0)
    y_pub_pmc = row_y(top, 1)             # Publications.PubMed Central Link
    y_hcm_dbsnp = row_y(lower, 0)
    y_hcm_gene = row_y(lower, 1)
    y_hcm_lp = row_y(lower, len(hcm_rows) - 2)   # Linked Publications
    y_hcm_ls = row_y(lower, len(hcm_rows) - 1)   # Linked Studies
    y_sci_tag = row_y(sci_y, 1, "support")
    y_sci_exact = row_y(sci_y, 2, "support")

    # Resource domain: shared Resource Name (solid = direct column match).
    gap_mid = (res_x + res_w + pub_x) / 2
    body.append(path(f"M{pub_x},{y_res_name} H{res_x + res_w + 2}", RES))
    body.append(label(gap_mid, y_res_name - 10, "Resource Name", RES))
    body.append(count_label(gap_mid - 10, y_res_name + 24, f"{fmt(c['pub_res_rows'])} papers", RES))
    body.append(count_label(gap_mid - 10, y_res_name + 43, f"→ {fmt(c['pub_res_targets'])} resources", RES))

    res_bottom = top + res_h
    body.append(path(f"M{code_x + 200},{lower} V{res_bottom + 2}", RES))
    body.append(label(code_x + 200, (lower + res_bottom) / 2 + 6, "Resource Name", RES))
    body.append(count_label(code_x + 200, (lower + res_bottom) / 2 + 27,
                            f"{fmt(c['code_res_rows'])} repositories → {fmt(c['code_res_targets'])} resources", RES))

    # Human Cellular Models -> Publications (derived, dashed): Linked Publications row -> PMC ID row.
    lp_x = pub_x - 28
    body.append(path(f"M{hcm_x},{y_hcm_lp} H{lp_x} V{y_pub_pmc} H{pub_x - 2}", PUB, dashed=True))
    pub_bottom = top + pub_h
    lp_label_y = (pub_bottom + lower) / 2 - 4
    body.append(label(lp_x + 14, lp_label_y, "Linked Publications → PMC ID", PUB, anchor="start"))
    body.append(label(lp_x + 14, lp_label_y + 21,
                      f"{fmt(c['hcm_pub_rows'])} lines → {fmt(c['hcm_pub_targets'])} papers", PUB,
                      size=15, weight="normal", anchor="start"))

    # Human Cellular Models -> Resources (derived, dashed): Linked Studies row -> Resource Name side.
    ls_x = 535
    y_res_in = res_bottom - 40
    body.append(path(f"M{hcm_x},{y_hcm_ls} H{ls_x} V{y_res_in} H{res_x + res_w + 2}", RES, dashed=True))
    # In the Resources/Code gap, clear of the Code Repositories box below.
    mid = (res_bottom + lower) / 2 - 25
    body.append(label(ls_x, mid, "Linked Studies", RES))
    body.append(label(ls_x, mid + 20, "→ Resource Name", RES))
    body.append(count_label(ls_x, mid + 41, f"{fmt(c['hcm_res_rows'])} lines", RES))
    body.append(count_label(ls_x, mid + 60, f"→ {fmt(c['hcm_res_targets'])} resources", RES))

    # Publication domain: annotation tables (key row) -> Publications (PMC ID row).
    bus_x = 1215
    body.append(f'<line x1="{bus_x}" y1="{min(sup_mid_ys[0], y_pub_pmc)}" x2="{bus_x}" y2="{sup_mid_ys[-1]}" '
                f'stroke="{PUB}" stroke-width="2.4" stroke-linecap="round"/>')
    for my in sup_mid_ys:
        body.append(f'<line x1="{bus_x}" y1="{my}" x2="{sup_x}" y2="{my}" stroke="{PUB}" stroke-width="2.4"/>')
        body.append(f'<circle cx="{bus_x}" cy="{my}" r="3.6" fill="{PUB}"/>')
    for my, ck in zip(sup_mid_ys, sup_keys):
        body.append(label((bus_x + sup_x) / 2 + 2, my - 8, f"{fmt(c[f'{ck}_papers'])} papers", PUB,
                          size=14, weight="normal"))
    body.append(path(f"M{bus_x},{y_pub_pmc} H{pub_x + pub_w + 2}", PUB))
    body.append(label((bus_x + pub_x + pub_w) / 2, y_pub_pmc + 26, "PMC ID / DOI", PUB))

    # Variant/gene keys: HCM dbSNP / Gene rows -> SciLite Tag Name / Exact rows (direct value match).
    # dbSNP takes the outer lane so the two elbows never cross.
    x_rs, x_gene = hcm_x + hcm_w + 90, hcm_x + hcm_w + 60
    body.append(path(f"M{hcm_x + hcm_w},{y_hcm_dbsnp} H{x_rs} V{y_sci_tag} H{sup_x - 2}", VAR))
    body.append(path(f"M{hcm_x + hcm_w},{y_hcm_gene} H{x_gene} V{y_sci_exact} H{sup_x - 2}", VAR))
    # Gene caption sits right against its (inner) lane. The dbSNP caption sits further out,
    # with a thin leader rising to its (outer) lane - it simply crosses the Gene lane.
    gl_x, gl_y = x_gene - 14, lower + hcm_h + 45
    rs_x, rs_y = gl_x - 90, gl_y - 8
    rs_x += 0.25 * (x_rs - rs_x)  # nudge right by a quarter of the text-to-lane gap
    body.append(label(rs_x, rs_y, "dbSNP = Tag Name (RefSNP)", VAR, anchor="end"))
    body.append(label(rs_x, rs_y + 20, f"{fmt(c['hcm_rs_rows'])} lines · {fmt(c['hcm_rs_values'])} variants", VAR,
                      size=15, weight="normal", anchor="end"))
    body.append(label(gl_x, gl_y + 52, "Gene = Exact (Gene_Proteins)", VAR, anchor="end"))
    body.append(label(gl_x, gl_y + 72, f"{fmt(c['hcm_gene_rows'])} lines · {fmt(c['hcm_gene_values'])} genes", VAR,
                      size=15, weight="normal", anchor="end"))
    lx0, ly0 = rs_x + 8, rs_y - 5.5
    # Stop a few px short of the dbSNP lane - a small gap between pointer and edge.
    lx1, ly1 = x_rs, ly0 - 70
    seg = ((lx1 - lx0) ** 2 + (ly1 - ly0) ** 2) ** 0.5
    gap = 5
    lx1, ly1 = lx1 - gap * (lx1 - lx0) / seg, ly1 - gap * (ly1 - ly0) / seg
    body.append(f'<line x1="{lx0}" y1="{ly0}" x2="{lx1:.1f}" y2="{ly1:.1f}" stroke="{INK}" stroke-width="0.9"/>')

    # --- Legend ----------------------------------------------------------
    ly = max(lower + max(code_h, hcm_h) + 125, gl_y + 140, sci_y + sci_h + 75)
    lx = 60
    body.append(text(lx, ly - 30, "Join key", 15, "bold", MUTED))
    body.append(f'<line x1="{lx}" y1="{ly - 6}" x2="{lx + 46}" y2="{ly - 6}" stroke="{PUB}" stroke-width="3"/>')
    body.append(text(lx + 56, ly, "Publication (PMC ID / DOI)", 15.5))
    body.append(f'<line x1="{lx}" y1="{ly + 22}" x2="{lx + 46}" y2="{ly + 22}" stroke="{RES}" stroke-width="3"/>')
    body.append(text(lx + 56, ly + 28, "Resource (Resource Name)", 15.5))
    body.append(f'<line x1="{lx}" y1="{ly + 50}" x2="{lx + 46}" y2="{ly + 50}" stroke="{VAR}" stroke-width="3"/>')
    body.append(text(lx + 56, ly + 56, "Variant / gene (dbSNP, Gene)", 15.5))

    lx2 = 330
    body.append(text(lx2, ly - 30, "Relationship", 15, "bold", MUTED))
    body.append(f'<line x1="{lx2}" y1="{ly - 6}" x2="{lx2 + 46}" y2="{ly - 6}" stroke="{INK}" stroke-width="2.4"/>')
    body.append(text(lx2 + 56, ly, "Direct: shared key column", 15.5))
    body.append(f'<line x1="{lx2}" y1="{ly + 22}" x2="{lx2 + 46}" y2="{ly + 22}" stroke="{INK}" '
                f'stroke-width="{DASHED_W}" stroke-dasharray="{DASH}"/>')
    body.append(text(lx2 + 56, ly + 28, "Derived: precomputed via the dbSNP = RefSNP match", 15.5))

    lx3 = 900
    body.append(text(lx3, ly - 30, "Fields", 15, "bold", MUTED))
    body.append(f'<circle cx="{lx3 + 6}" cy="{ly - 6}" r="5" fill="{INK}"/>')
    body.append(text(lx3 + 20, ly, "Key column", 15.5))
    body.append(f'<circle cx="{lx3 + 6}" cy="{ly + 22}" r="5" fill="#ffffff" stroke="{INK}" stroke-width="1.8"/>')
    body.append(text(lx3 + 20, ly + 28, "Derived key column", 15.5))

    lx4 = 1120
    body.append(text(lx4, ly - 30, "Numbers", 15, "bold", MUTED))
    body.append(text(lx4, ly, "n = rows in the table", 15.5))
    body.append(text(lx4, ly + 28, "On links: rows matched by that key", 15.5))

    h = int(max(ly + 90, sup_bottom + 40))
    head = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{h}" viewBox="0 0 {W} {h}">',
        f"""<defs>
  <marker id="arrow-pub" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
    <path d="M0,0 L10,5 L0,10 z" fill="{PUB}"/></marker>
  <marker id="arrow-var" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
    <path d="M0,0 L10,5 L0,10 z" fill="{VAR}"/></marker>
  <marker id="arrow-res" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
    <path d="M0,0 L10,5 L0,10 z" fill="{RES}"/></marker>
</defs>""",
        f'<rect width="{W}" height="{h}" fill="#ffffff"/>',
    ]
    return "\n".join(head + body + ["</svg>"])


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    svg_path, png_path = OUTPUT_DIR / "figure_data_model.svg", OUTPUT_DIR / "figure_data_model.png"
    counts, count_rows = compute_counts()
    counts_path = OUTPUT_DIR / "figure_data_model_counts.tsv"
    pd.DataFrame(count_rows, columns=["metric", "value", "source_file"]).to_csv(counts_path, sep="\t", index=False)
    logger.info(f"Wrote {len(count_rows)} counts → {counts_path.name}")
    svg_path.write_text(build_svg(counts), encoding="utf-8")
    logger.info(f"Wrote {svg_path}")
    if not shutil.which("rsvg-convert"):
        logger.warning("rsvg-convert not found - skipping PNG export (brew install librsvg)")
        return
    subprocess.run(["rsvg-convert", "-z", str(PNG_DPI_SCALE), "-b", "white", "-o", str(png_path), str(svg_path)],
                   check=True)
    logger.info(f"Wrote {png_path}")


if __name__ == "__main__":
    main()
