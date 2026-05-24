"""MMM Tool — Streamlit web application."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import time
import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO

from utils.preprocessing import apply_all_transformations
from utils.charts import make_input_target_charts
from utils.adstock import apply_tab2_transformations, build_output_col, CREATES_NEW_COLUMN
from utils.modelling import fit_model
from utils.autofit import (
    start_autofit, get_task, cancel_task, cleanup_task,
    METRIC_LABELS as _AF_METRIC_LABELS,
    describe_transforms as _af_describe_transforms,
)

# ─────────────────────────────── PAGE CONFIG ────────────────────────────────

st.set_page_config(
    page_title="MMM Tool",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
/* ── Palette ──────────────────────────────────────────────────────────── */
:root {
  --bg:       #f0f3fa;
  --surface:  #ffffff;
  --border:   #dde3f0;
  --primary:  #2563eb;
  --primary2: #4f46e5;
  --accent:   #0ea5e9;
  --text:     #111827;
  --muted:    #6b7280;
  --shadow:   0 2px 10px rgba(0,0,0,0.07);
  --radius:   10px;
}

/* ── Base ─────────────────────────────────────────────────────────────── */
[data-testid="stAppViewContainer"],
[data-testid="stApp"]              { background: var(--bg) !important; }
/* Remove Streamlit chrome */
[data-testid="stHeader"],
[data-testid="stToolbar"],
[data-testid="stDecoration"],
[data-testid="stStatusWidget"],
.reportview-container .main footer,
footer                             { display: none !important; }
#MainMenu                          { display: none !important; }
.block-container {
  padding-top:    1rem !important;
  padding-bottom: 1rem !important;
  max-width: 1400px !important;
}
.appview-container .main .block-container { padding-top: 1rem !important; }
section[data-testid="stSidebar"]   { display: none !important; }

/* ── App header ───────────────────────────────────────────────────────── */
.app-header {
  display: flex;
  align-items: center;
  gap: 0.85rem;
  background: linear-gradient(120deg, #0f172a 0%, #1e3a8a 100%);
  border-radius: var(--radius);
  padding: 0.9rem 1.5rem;
  margin-bottom: 1rem;
  color: #fff;
}
.app-header-icon  { font-size: 1.75rem; line-height: 1; }
.app-header-title { font-size: 1.2rem; font-weight: 700; letter-spacing: -0.01em; }
.app-header-sub   { font-size: 0.72rem; color: #93c5fd; margin-top: 2px; }
.app-header-badge {
  margin-left: auto;
  background: rgba(255,255,255,0.12);
  color: #bfdbfe;
  padding: 0.18rem 0.65rem;
  border-radius: 20px;
  font-size: 0.68rem;
  font-weight: 700;
  letter-spacing: 0.07em;
  text-transform: uppercase;
}

/* ── Nav bar ──────────────────────────────────────────────────────────── */
.tab-active {
  display: inline-block;
  background: var(--primary);
  color: #fff !important;
  padding: 0.22rem 0.85rem;
  border-radius: 20px;
  font-size: 0.83rem;
  font-weight: 600;
}
.tab-inactive {
  display: inline-block;
  color: var(--muted);
  padding: 0.22rem 0.5rem;
  font-size: 0.83rem;
}
.tab-sep { color: var(--border); padding: 0 0.25rem; }

/* ── Expanders → cards ────────────────────────────────────────────────── */
[data-testid="stExpander"] {
  background:    var(--surface) !important;
  border:        1px solid var(--border) !important;
  border-radius: var(--radius) !important;
  box-shadow:    var(--shadow) !important;
  margin-bottom: 0.5rem !important;
  overflow:      hidden !important;
}
[data-testid="stExpander"] details summary {
  font-weight: 600 !important;
  font-size:   0.9rem !important;
  color:       var(--text) !important;
  padding:     0.6rem 1rem !important;
  background:  transparent !important;
}
[data-testid="stExpander"] details[open] summary {
  color:         var(--primary) !important;
  border-bottom: 1px solid var(--border) !important;
  background:    #f5f8ff !important;
}

/* ── All buttons ──────────────────────────────────────────────────────── */
.stButton > button {
  border-radius: 8px !important;
  font-weight:   600 !important;
  font-size:     0.83rem !important;
  border:        1.5px solid var(--primary) !important;
  color:         var(--primary) !important;
  background:    #fff !important;
  transition:    all 0.17s ease !important;
  padding:       0.28rem 0.85rem !important;
}
.stButton > button:hover:not(:disabled) {
  background:  var(--primary) !important;
  color:       #fff !important;
  box-shadow:  0 4px 14px rgba(37,99,235,0.28) !important;
  transform:   translateY(-1px) !important;
}
.stButton > button:disabled {
  opacity: 0.3 !important;
  border-color: var(--muted) !important;
  color: var(--muted) !important;
}

/* ── Download buttons ─────────────────────────────────────────────────── */
.stDownloadButton > button {
  border-radius: 8px !important;
  font-weight:   600 !important;
  font-size:     0.8rem !important;
  background:    linear-gradient(135deg, var(--primary), var(--primary2)) !important;
  color:         #fff !important;
  border:        none !important;
  transition:    all 0.17s ease !important;
}
.stDownloadButton > button:hover {
  box-shadow: 0 4px 16px rgba(37,99,235,0.35) !important;
  transform:  translateY(-1px) !important;
}

/* ── Form submit buttons ──────────────────────────────────────────────── */
[data-testid="stFormSubmitButton"] > button {
  border-radius: 8px !important;
  background:    var(--primary) !important;
  color:         #fff !important;
  border:        none !important;
  font-weight:   600 !important;
  font-size:     0.83rem !important;
}
[data-testid="stFormSubmitButton"] > button:hover {
  background: var(--primary2) !important;
  box-shadow: 0 3px 10px rgba(37,99,235,0.3) !important;
}

/* ── Dataframe ────────────────────────────────────────────────────────── */
[data-testid="stDataFrame"] {
  border-radius: var(--radius) !important;
  border:        1px solid var(--border) !important;
  overflow:      hidden !important;
  box-shadow:    0 1px 6px rgba(0,0,0,0.04) !important;
}

/* ── Multiselect tags ─────────────────────────────────────────────────── */
[data-baseweb="tag"] {
  background-color: #dbeafe !important;
  color:            var(--primary) !important;
  border-radius:    5px !important;
}

/* ── Input / select ───────────────────────────────────────────────────── */
[data-baseweb="input"] > div,
[data-baseweb="select"] > div:first-child {
  border-radius: 7px !important;
}

/* ── Alerts ───────────────────────────────────────────────────────────── */
[data-testid="stAlert"] { border-radius: var(--radius) !important; }

/* ── Misc ─────────────────────────────────────────────────────────────── */
hr              { border-color: var(--border) !important; margin: 0.55rem 0 !important; }
.stCaption p    { color: var(--muted) !important; font-size: 0.77rem !important; }
h1              {
  font-size:      1.45rem !important;
  font-weight:    700 !important;
  color:          var(--text) !important;
  border-bottom:  3px solid var(--primary) !important;
  padding-bottom: 0.35rem !important;
  margin-bottom:  1rem !important;
  display:        inline-block !important;
}

/* ── Custom labels ────────────────────────────────────────────────────── */
.section-mini-label {
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--muted);
  margin: 0.6rem 0 0.2rem 0;
}
.preview-label {
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--primary);
  padding-bottom: 0.35rem;
  border-bottom: 2px solid #dbeafe;
  margin-bottom: 0.5rem;
}
.charts-label {
  font-size: 1rem;
  font-weight: 700;
  color: var(--text);
  border-left: 4px solid var(--accent);
  padding-left: 0.6rem;
  margin: 0.25rem 0 0.6rem 0;
}
.norm-tag {
  display: inline-block;
  background: #ede9fe;
  color: #5b21b6;
  border-radius: 5px;
  padding: 0.08rem 0.45rem;
  font-size: 0.78rem;
  font-weight: 600;
  margin-right: 3px;
}
.calc-tag {
  display: inline-block;
  background: #dcfce7;
  color: #166534;
  border-radius: 5px;
  padding: 0.08rem 0.45rem;
  font-size: 0.78rem;
  font-weight: 600;
}
.t2-tag {
  display: inline-block;
  background: #fef9c3;
  color: #713f12;
  border-radius: 5px;
  padding: 0.08rem 0.45rem;
  font-size: 0.78rem;
  font-weight: 600;
}
.media-tag {
  display: inline-block;
  background: #fce7f3;
  color: #831843;
  border-radius: 5px;
  padding: 0.08rem 0.45rem;
  font-size: 0.78rem;
  font-weight: 600;
  margin-right: 3px;
}
.coef-tag {
  display: inline-block;
  background: #e0f2fe;
  color: #075985;
  border-radius: 5px;
  padding: 0.08rem 0.45rem;
  font-size: 0.78rem;
  font-weight: 600;
  margin-right: 3px;
}
.model-stat-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 0.55rem 0.8rem;
  margin-bottom: 0.35rem;
}
.model-stat-label {
  font-size: 0.72rem;
  color: var(--muted);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
.model-stat-value {
  font-size: 1.05rem;
  font-weight: 700;
  color: var(--text);
}
.pval-method-note {
  font-size: 0.75rem;
  color: #6b7280;
  background: #f0f9ff;
  border-left: 3px solid #0ea5e9;
  padding: 0.3rem 0.6rem;
  border-radius: 0 5px 5px 0;
  margin-bottom: 0.5rem;
}
</style>
""", unsafe_allow_html=True)

TABS = ["Data Preprocessing", "Adstock & Saturation", "Prior Modeling"]
MAX_TAB = len(TABS) - 1

# ──────────────────────────── SESSION STATE ──────────────────────────────────

def _default_config() -> dict:
    return {
        "datetime_columns": [],
        "groupby_columns": [],
        "pivot": {},
        "calculated_columns": [],
        "normalizations": [],
        "sort_config": [],
        "input_columns": [],
        "target_column": None,
        # Tab 2
        "media_channels": [],
        "date_filter": {},
        "adstock_transforms": [],
        # Tab 3
        "model_config": {},
        # Auto-Fit
        "autofit": {
            "positive_coefficients": False,
            "positive_intercept":    False,
            "metric":          "adj_r2",
            "n_iter":          200,
            "max_pval":        0.10,
            "allowed_models":  ["linear", "ridge", "lasso", "elasticnet",
                                 "randomforest", "xgboost"],
            "result":          None,
        },
    }

for _k, _v in [
    ("current_tab", 0),
    ("df_original", None),
    ("uploaded_filename", None),
    ("config", _default_config()),
    ("widget_epoch", 0),
]:
    if _k not in st.session_state:
        st.session_state[_k] = _v

# ─────────────────────────────── HELPERS ─────────────────────────────────────

def wk(base: str) -> str:
    return f"{base}_e{st.session_state.widget_epoch}"


def _get_tab1_df() -> pd.DataFrame | None:
    """Tab 1 processed data (no date filter, no Tab 2 transforms)."""
    if st.session_state.df_original is None:
        return None
    return apply_all_transformations(
        st.session_state.df_original.copy(),
        st.session_state.config,
    )


def get_processed_df() -> pd.DataFrame | None:
    """Full pipeline: Tab 1 → Tab 2 transforms → date filter."""
    df = _get_tab1_df()
    if df is None:
        return None

    cfg = st.session_state.config

    # ── Tab 2 transforms (run on full date range so adstock carry-over is correct)
    t2 = cfg.get("adstock_transforms", [])
    if t2:
        df = apply_tab2_transformations(
            df, t2,
            cfg.get("groupby_columns", []),
            cfg.get("target_column"),
        )

    # ── Date filter (applied after transforms) ────────────────────────────────
    df_cfg = cfg.get("date_filter", {})
    if df_cfg.get("col") and df_cfg.get("min_date") is not None and df_cfg.get("max_date") is not None:
        col = df_cfg["col"]
        if col in df.columns:
            try:
                dt = pd.to_datetime(df[col])
                df = df[
                    (dt.dt.date >= df_cfg["min_date"]) &
                    (dt.dt.date <= df_cfg["max_date"])
                ].reset_index(drop=True)
            except Exception:
                pass

    return df


def _download_buttons(df: pd.DataFrame, prefix: str) -> None:
    if df is None or df.empty:
        return
    c1, c2 = st.columns(2)
    with c1:
        st.download_button(
            "⬇ CSV", df.to_csv(index=False).encode("utf-8"),
            "processed_data.csv", "text/csv", key=f"dl_csv_{prefix}",
        )
    with c2:
        buf = BytesIO()
        df.to_excel(buf, index=False, engine="openpyxl")
        st.download_button(
            "⬇ XLSX", buf.getvalue(),
            "processed_data.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"dl_xlsx_{prefix}",
        )

# ─────────────────────────────── NAV BAR ─────────────────────────────────────

def nav_bar(position: str) -> None:
    idx = st.session_state.current_tab
    c_prev, c_next, c_tabs, c_dl = st.columns([1, 1, 5, 2])

    with c_prev:
        if st.button("◀  Prev", key=f"btn_prev_{position}", disabled=idx == 0):
            st.session_state.current_tab -= 1
            st.rerun()
    with c_next:
        if st.button("Next  ▶", key=f"btn_next_{position}", disabled=idx == MAX_TAB):
            st.session_state.current_tab += 1
            st.rerun()
    with c_tabs:
        parts = []
        for i, t in enumerate(TABS):
            if i == idx:
                parts.append(f'<span class="tab-active">→ {t}</span>')
            else:
                parts.append(f'<span class="tab-inactive">{t}</span>')
        st.markdown(
            '<span class="tab-sep">|</span>'.join(parts),
            unsafe_allow_html=True,
        )
    with c_dl:
        df = get_processed_df()
        if df is not None:
            _download_buttons(df, f"{position}_{idx}")

# ════════════════════════════════════════════════════════════════════════════
#  TAB 1 — DATA PREPROCESSING
# ════════════════════════════════════════════════════════════════════════════

def tab_preprocessing() -> None:
    st.title("Data Preprocessing")
    cfg = st.session_state.config

    left, right = st.columns([55, 45], gap="large")

    with left:

        # ── ① Upload ─────────────────────────────────────────────────────────
        with st.expander("① Upload Dataset", expanded=st.session_state.df_original is None):
            uploaded = st.file_uploader("CSV or XLSX", type=["csv", "xlsx", "xls"], key=wk("uploader"))
            if uploaded is not None and uploaded.name != st.session_state.uploaded_filename:
                try:
                    raw = (
                        pd.read_csv(uploaded)
                        if uploaded.name.lower().endswith(".csv")
                        else pd.read_excel(uploaded, engine="openpyxl")
                    )
                    st.session_state.df_original = raw
                    st.session_state.uploaded_filename = uploaded.name
                    st.session_state.config = _default_config()
                    st.session_state.widget_epoch += 1
                    st.success(f"Loaded **{uploaded.name}** — {len(raw):,} rows × {len(raw.columns)} cols")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to load: {e}")
            if st.session_state.df_original is not None:
                st.caption(f"Active file: **{st.session_state.uploaded_filename}**")

        if st.session_state.df_original is None:
            st.info("Upload a dataset above to get started.")
            return

        raw_cols = list(st.session_state.df_original.columns)

        def cur_cols_now():
            df = _get_tab1_df()
            return list(df.columns) if df is not None else raw_cols

        def cur_df_now():
            return _get_tab1_df()

        # ── ② Datetime ───────────────────────────────────────────────────────
        with st.expander("② Convert to Datetime"):
            dt_sel = st.multiselect("Columns to convert", raw_cols,
                                    default=cfg["datetime_columns"], key=wk("dt_cols"))
            if dt_sel != cfg["datetime_columns"]:
                cfg["datetime_columns"] = dt_sel
                st.rerun()

        # ── ③ Grouping ───────────────────────────────────────────────────────
        with st.expander("③ Grouping Columns  *(for mean / minmax normalisation)*"):
            grp_sel = st.multiselect("Group by", raw_cols,
                                     default=[c for c in cfg["groupby_columns"] if c in raw_cols],
                                     key=wk("grp_cols"))
            if grp_sel != cfg["groupby_columns"]:
                cfg["groupby_columns"] = grp_sel
                st.rerun()
            if grp_sel:
                st.caption(f"Mean/MinMax normalisation will use `{grp_sel}` as group keys.")

        # ── ④ Pivot ──────────────────────────────────────────────────────────
        with st.expander("④ Pivot Dataset"):
            p = cfg["pivot"] or {}
            enable_pivot = st.checkbox("Enable pivot", value=bool(p.get("header_col")), key=wk("pivot_enabled"))
            if enable_pivot:
                p_index = st.multiselect("Index columns (remain as rows)", raw_cols,
                                         default=[c for c in p.get("index_cols", []) if c in raw_cols],
                                         key=wk("pivot_index"))
                p_header = st.selectbox("Column-header source (values → column names)",
                                        [""] + raw_cols,
                                        index=([""] + raw_cols).index(p.get("header_col") or ""),
                                        key=wk("pivot_header"))
                p_value = st.selectbox("Values column",
                                       [""] + raw_cols,
                                       index=([""] + raw_cols).index(p.get("value_col") or ""),
                                       key=wk("pivot_value"))
                p_agg = st.selectbox("Aggregation", ["sum", "mean", "first", "max", "min"],
                                     index=["sum","mean","first","max","min"].index(p.get("aggfunc","sum")),
                                     key=wk("pivot_agg"))
                new_p = {"index_cols": p_index, "header_col": p_header or None,
                         "value_col": p_value or None, "aggfunc": p_agg}
                if new_p != cfg["pivot"]:
                    cfg["pivot"] = new_p
                    st.rerun()
            else:
                if cfg.get("pivot"):
                    cfg["pivot"] = {}
                    st.rerun()

        _cc = cur_cols_now()
        _cdf = cur_df_now()

        # ── ⑤ Calculated Columns ─────────────────────────────────────────────
        with st.expander("⑤ Calculated Columns"):
            to_del = None
            for i, calc in enumerate(cfg["calculated_columns"]):
                r1, r2, r3 = st.columns([3, 5, 1])
                t, p2 = calc["type"], calc["params"]
                with r1:
                    st.markdown(f'<span class="calc-tag">{calc["name"]}</span>', unsafe_allow_html=True)
                with r2:
                    if t in ("lag", "lead"):
                        st.caption(f"{t}({p2.get('column')}, n={p2.get('n')})")
                    elif t == "add":
                        st.caption("SUM(" + ", ".join(p2.get("columns", [])) + ")")
                    elif t == "multiply":
                        st.caption("PRODUCT(" + ", ".join(p2.get("columns", [])) + ")")
                    elif t == "multiply_scalar":
                        st.caption(f"{p2.get('column')} × {p2.get('scalar')}")
                with r3:
                    if st.button("✕", key=f"del_calc_{i}_{st.session_state.widget_epoch}"):
                        to_del = i
            if to_del is not None:
                cfg["calculated_columns"].pop(to_del)
                st.rerun()

            st.markdown("---")
            st.markdown('<p class="section-mini-label">Add calculated column</p>', unsafe_allow_html=True)

            num_cols = [c for c in _cc if _cdf is not None and pd.api.types.is_numeric_dtype(_cdf[c])] or _cc

            new_type = st.selectbox(
                "Operation",
                ["lag", "lead", "add", "multiply", "multiply_scalar"],
                key=wk("calc_op_type"),
            )

            with st.form(key=wk("form_calc"), clear_on_submit=True):
                new_name = st.text_input("New column name", key="fc_name")
                new_params: dict = {}

                if new_type in ("lag", "lead"):
                    ca, cb = st.columns(2)
                    with ca: src_col = st.selectbox("Source column", num_cols, key="fc_src")
                    with cb: n_units = st.number_input("Units", min_value=1, value=1, step=1, key="fc_n")
                    new_params = {"column": src_col, "n": int(n_units)}
                elif new_type in ("add", "multiply"):
                    sel = st.multiselect("Columns", num_cols, key="fc_multi")
                    new_params = {"columns": sel}
                elif new_type == "multiply_scalar":
                    ca, cb = st.columns(2)
                    with ca: src_col = st.selectbox("Source column", num_cols, key="fc_src_sc")
                    with cb: scalar = st.number_input("Scalar", value=1.0, key="fc_scalar")
                    new_params = {"column": src_col, "scalar": float(scalar)}

                if st.form_submit_button("Add Column"):
                    name_clean = (new_name or "").strip()
                    if not name_clean:
                        st.warning("Enter a column name.")
                    elif name_clean in _cc:
                        st.warning(f"'{name_clean}' already exists.")
                    elif new_type in ("add", "multiply") and len(new_params.get("columns", [])) < 2:
                        st.warning("Select at least 2 columns.")
                    else:
                        cfg["calculated_columns"].append(
                            {"name": name_clean, "type": new_type, "params": new_params})
                        st.rerun()

        _cc = cur_cols_now()
        _cdf = cur_df_now()

        # ── ⑥ Normalise ──────────────────────────────────────────────────────
        with st.expander("⑥ Normalise Columns"):
            to_del_n = None
            for i, norm in enumerate(cfg["normalizations"]):
                m = norm["method"]
                pp = norm.get("params", {})
                grp = cfg.get("groupby_columns", [])
                grp_str = (f" · grouped by {grp}" if grp else " · global")
                r1, r2, r3 = st.columns([4, 5, 1])
                if m == "column":
                    src_list = pp.get("columns", [])
                    div = pp.get("div_column", "")
                    with r1:
                        tags = " ".join(f'<span class="norm-tag">{c}</span>' for c in src_list)
                        st.markdown(tags or "—", unsafe_allow_html=True)
                    with r2:
                        st.caption(f"÷ `{div}`{grp_str}")
                else:
                    with r1:
                        st.markdown(f'<span class="norm-tag">{norm.get("column","")}</span>', unsafe_allow_html=True)
                    with r2:
                        if m == "mean":
                            st.caption(f"÷ mean{grp_str}")
                        elif m == "minmax":
                            st.caption(f"minmax{grp_str}")
                        elif m == "z-score":
                            st.caption(f"z-score  (x−μ)/σ{grp_str}")
                        elif m == "scalar":
                            st.caption(f"÷ scalar {pp.get('scalar')}{grp_str}")
                with r3:
                    if st.button("✕", key=f"del_norm_{i}_{st.session_state.widget_epoch}"):
                        to_del_n = i
            if to_del_n is not None:
                cfg["normalizations"].pop(to_del_n)
                st.rerun()

            st.markdown("---")
            st.markdown('<p class="section-mini-label">Add normalisation</p>', unsafe_allow_html=True)

            norm_method = st.selectbox(
                "Method", ["minmax", "mean", "z-score", "scalar", "column"],
                index=0,
                key=wk("norm_method_sel"),
            )

            with st.form(key=wk("form_norm"), clear_on_submit=True):
                norm_params: dict = {}
                grp = cfg.get("groupby_columns", [])
                grp_note = f"Grouped by {grp}." if grp else "No grouping set → global."

                if norm_method == "column":
                    sel_cols = st.multiselect("Columns to normalise", _cc, key="fn_cols_multi")
                    div_col = st.selectbox("Divide by column", _cc, key="fn_divcol")
                    norm_params = {"columns": sel_cols, "div_column": div_col}
                else:
                    norm_col = st.selectbox("Column to normalise", _cc, key="fn_col")
                    if norm_method == "scalar":
                        norm_scalar = st.number_input("Divide by scalar", value=1.0, key="fn_scalar")
                        norm_params = {"scalar": float(norm_scalar)}

                if grp:
                    st.info(f"Grouping: {grp}")
                else:
                    st.caption(grp_note)
                st.caption("Column is overwritten in place as float.")

                if st.form_submit_button("Add"):
                    if norm_method == "column":
                        if not norm_params.get("columns"):
                            st.warning("Select at least one column to normalise.")
                        else:
                            cfg["normalizations"].append({"method": "column", "params": norm_params})
                            st.rerun()
                    else:
                        cfg["normalizations"].append({
                            "column": norm_col,
                            "method": norm_method,
                            "params": norm_params,
                        })
                        st.rerun()

        _cc = cur_cols_now()

        # ── ⑦ Sort ───────────────────────────────────────────────────────────
        with st.expander("⑦ Sort Data"):
            to_del_s = None
            for i, s in enumerate(cfg["sort_config"]):
                r1, r2, r3 = st.columns([3, 2, 1])
                with r1: st.markdown(f"`{s['column']}`")
                with r2: st.caption("↑ Ascending" if s.get("ascending", True) else "↓ Descending")
                with r3:
                    if st.button("✕", key=f"del_sort_{i}_{st.session_state.widget_epoch}"):
                        to_del_s = i
            if to_del_s is not None:
                cfg["sort_config"].pop(to_del_s)
                st.rerun()

            st.markdown("---")
            with st.form(key=wk("form_sort"), clear_on_submit=True):
                sa, sb = st.columns(2)
                with sa: sort_col = st.selectbox("Column", _cc, key="fs_col")
                with sb: sort_dir = st.radio("Order", ["↑ Ascending", "↓ Descending"],
                                             horizontal=True, key="fs_dir")
                if st.form_submit_button("Add sort key"):
                    cfg["sort_config"].append(
                        {"column": sort_col, "ascending": sort_dir.startswith("↑")})
                    st.rerun()

        _cc = cur_cols_now()
        _cdf = cur_df_now()

        # ── ⑧ Input / Target ─────────────────────────────────────────────────
        with st.expander("⑧ Input & Target Columns", expanded=True):
            t_opts = [""] + _cc
            cur_t = cfg.get("target_column") or ""
            t_idx = t_opts.index(cur_t) if cur_t in t_opts else 0
            target_sel = st.selectbox("Target column (KPI)", t_opts, index=t_idx, key=wk("target_col"))
            if (target_sel or None) != cfg.get("target_column"):
                cfg["target_column"] = target_sel or None
                st.rerun()

            inp_opts = [c for c in _cc if c != (target_sel or None)]
            inp_sel = st.multiselect(
                "Input / media channels",
                inp_opts,
                default=[c for c in cfg.get("input_columns", []) if c in inp_opts],
                key=wk("input_cols"),
            )
            if inp_sel != cfg.get("input_columns", []):
                cfg["input_columns"] = inp_sel
                st.rerun()

    # ── Right panel: Live Preview ─────────────────────────────────────────────
    with right:
        st.markdown('<p class="preview-label">Live Preview</p>', unsafe_allow_html=True)
        cur_df = _get_tab1_df()
        if cur_df is not None:
            st.dataframe(cur_df.head(200), use_container_width=True, height=490)
            st.caption(
                f"Showing up to 200 of **{len(cur_df):,}** rows  ×  **{len(cur_df.columns)}** columns"
            )
            with st.expander("Column types"):
                dtype_df = pd.DataFrame({"Column": cur_df.columns,
                                          "dtype": [str(t) for t in cur_df.dtypes]})
                st.dataframe(dtype_df, use_container_width=True, hide_index=True)
        else:
            st.info("Preview appears here once data is loaded.")

    # ── Charts (full width) ───────────────────────────────────────────────────
    cur_df = _get_tab1_df()
    if cur_df is not None and cfg.get("input_columns") and cfg.get("target_column"):
        st.divider()
        st.markdown('<p class="charts-label">Input ↔ Target Charts</p>', unsafe_allow_html=True)
        charts = make_input_target_charts(cur_df, cfg["input_columns"], cfg["target_column"])
        if not charts:
            st.warning("No charts to display — check column selection.")
        else:
            for row_start in range(0, len(charts), 2):
                cols = st.columns(2)
                for j, (_, fig) in enumerate(charts[row_start: row_start + 2]):
                    with cols[j]:
                        st.plotly_chart(fig, use_container_width=True)


# ════════════════════════════════════════════════════════════════════════════
#  TAB 2 — ADSTOCK & SATURATION
# ════════════════════════════════════════════════════════════════════════════

# Transform type labels (display) → internal type key
_T_LABELS = [
    "Normalisation",
    "Lag",
    "Lead",
    "Moving Average",
    "Mean Centering",
    "Zero Mask (by target)",
    "Adstock",
    "Saturation",
]
_LABEL_TO_TYPE = {
    "Normalisation":        "norm",
    "Lag":                  "lag",
    "Lead":                 "lead",
    "Moving Average":       "moving_avg",
    "Mean Centering":       "mean_center",
    "Zero Mask (by target)":"zero_mask",
    "Adstock":              "adstock",
    "Saturation":           "saturation",
}
_MEDIA_ONLY = {"adstock", "saturation"}
# Mirror of adstock.CREATES_NEW_COLUMN — used throughout the UI layer.
_CREATES_NEW_COL: frozenset = CREATES_NEW_COLUMN


def _t2_describe(t: dict) -> str:
    """Short human-readable description for a transform entry."""
    src   = t.get("source_col", "?")
    ttype = t.get("type", "")
    p     = t.get("params", {})
    if ttype == "adstock":
        m = p.get("method", "geometric")
        ml = p.get("max_lag", 4)
        if m == "geometric":
            return f"{src} → adstock [geometric α={p.get('alpha', 0.5)}, lags≤{ml}]"
        elif m == "weibull":
            return f"{src} → adstock [Weibull shape={p.get('shape')}, scale={p.get('scale')}, lags≤{ml}]"
        elif m == "hill":
            return f"{src} → adstock [Hill α={p.get('alpha')}, γ={p.get('gamma')}, lags≤{ml}]"
    elif ttype == "saturation":
        return f"{src} → saturation [c={p.get('c', 1.0)}, d={p.get('d', 0.001)}]"
    elif ttype == "norm":
        return f"{src} → norm [{p.get('method', 'minmax')}]"
    elif ttype == "lag":
        return f"lag {p.get('n', 1)}  — overwrites {src}"
    elif ttype == "lead":
        return f"lead {p.get('n', 1)}  — overwrites {src}"
    elif ttype == "moving_avg":
        return f"MA({p.get('n', 3)})  — overwrites {src}"
    elif ttype == "mean_center":
        return f"mean-centred  — overwrites {src}"
    elif ttype == "zero_mask":
        return f"zero where target=0  — overwrites {src}"
    return f"{src} → {ttype}"


def tab_adstock() -> None:
    st.title("Adstock & Saturation")

    cfg = st.session_state.config

    # ── Guard: need Tab 1 data ────────────────────────────────────────────────
    tab1_df = _get_tab1_df()
    if tab1_df is None:
        st.info("Upload and preprocess a dataset in **Tab 1** first.")
        return

    tab1_cols = list(tab1_df.columns)

    # Ensure Tab 2 config keys exist (defensive, in case old session)
    cfg.setdefault("media_channels", [])
    cfg.setdefault("date_filter", {})
    cfg.setdefault("adstock_transforms", [])

    transforms     = cfg["adstock_transforms"]
    media_channels = cfg["media_channels"]
    target_col     = cfg.get("target_column")

    # Restrict available columns to those declared as input channels in Tab 1 → ⑧
    _input_cols = cfg.get("input_columns", [])
    base_cols = [c for c in _input_cols if c in tab1_cols]
    # Fallback: if no input channels set yet, use all Tab 1 columns
    if not base_cols:
        base_cols = tab1_cols

    # ── Build available-column and media-derived sets ─────────────────────────
    # Only transforms in _CREATES_NEW_COL add new columns; others overwrite in place.
    media_derived: set[str] = {c for c in media_channels if c in base_cols}
    avail_cols: list[str] = list(base_cols)
    for t in transforms:
        out    = t.get("output_col", "")
        ttype_t = t.get("type", "")
        if out and ttype_t in _CREATES_NEW_COL:
            if t.get("source_col") in media_derived:
                media_derived.add(out)
            if out not in avail_cols:
                avail_cols.append(out)

    media_avail = [c for c in avail_cols if c in media_derived]

    # ── Auto-Fit: ensure config key exists ────────────────────────────────────
    cfg.setdefault("autofit", {
        "positive_coefficients": False,
        "positive_intercept":    False,
        "metric":    "adj_r2",
        "n_iter":    200,
        "max_pval":  0.10,
        "allowed_models": ["linear", "ridge", "lasso", "elasticnet",
                           "randomforest", "xgboost"],
        "result":    None,
    })
    af_cfg = cfg["autofit"]

    # ── Auto-Fit: task state handler ─────────────────────────────────────────
    # Checked on every rerun.  If a task is active we either:
    #   a) process its completion and rerun (task done), or
    #   b) render the progress view, sleep 0.5 s, then rerun (task running).
    _af_task_id = af_cfg.get("task_id")
    if _af_task_id:
        _task = get_task(_af_task_id)
        if _task is None:
            # Task was cleaned up externally — clear the stale reference.
            af_cfg.pop("task_id", None)
            st.rerun()
        else:
            _done = _task.get("done", False)
            if _done:
                _status = _task.get("status", "unknown")
                if _status == "cancelled":
                    cleanup_task(_af_task_id)
                    af_cfg.pop("task_id", None)
                    st.rerun()
                else:
                    # Complete or no_result — apply best config to session.
                    _bc = _task.get("result")
                    if _bc:
                        cfg["adstock_transforms"] = list(_bc.get("best_transforms", []))
                        cfg.setdefault("model_config", {})
                        cfg["model_config"]["model_type"] = _bc.get("best_model_type", "linear")
                        cfg["model_config"]["params"]     = dict(_bc.get("best_params", {}))
                        cfg["model_config"]["features"]   = list(_bc.get("best_features", []))
                        af_cfg["result"] = _bc

                        # ── Propagate the 12-month date window used for fitting
                        # back to Tab 2's date filter so the live preview matches
                        # the data the model was actually trained on.
                        _fdc = _bc.get("fitted_date_col")
                        _fdm = _bc.get("fitted_date_min")
                        _fdx = _bc.get("fitted_date_max")
                        if _fdc and _fdm is not None and _fdx is not None:
                            cfg["date_filter"] = {
                                "col":      _fdc,
                                "min_date": _fdm,
                                "max_date": _fdx,
                            }

                    cleanup_task(_af_task_id)
                    af_cfg.pop("task_id", None)
                    if _bc:
                        st.session_state.current_tab = 2  # switch to Tab 3
                    st.rerun()
            else:
                # ── Running: render progress view, then rerun to poll ────────
                _n_iter   = af_cfg.get("n_iter", 200)
                _m_key    = af_cfg.get("metric", "adj_r2")
                _m_label  = _AF_METRIC_LABELS.get(_m_key, "Score")
                _progress = float(_task.get("progress", 0.0))
                _elapsed  = float(_task.get("elapsed",  0.0))
                _eta      = float(_task.get("eta",      0.0))
                _iter_n   = int(_task.get("iter",       0))
                _best_s   = _task.get("best_score", float("nan"))
                _best_bc  = _task.get("best_config")

                st.markdown("### 🔍 Auto-Fit Running…")
                _pbar_txt = (
                    f"Iteration **{_iter_n}** / {_n_iter}"
                    f"  ·  Elapsed {_elapsed:.0f}s  ·  ETA ≈ {_eta:.0f}s"
                )
                st.progress(_progress, text=_pbar_txt)

                _ca, _cb = st.columns([4, 1])
                with _ca:
                    try:
                        _bs_nan = isinstance(_best_s, float) and np.isnan(_best_s)
                    except Exception:
                        _bs_nan = True
                    if not _bs_nan:
                        st.metric(f"Best {_m_label} so far", f"{_best_s:.4f}")
                    else:
                        st.caption("Searching for first valid configuration…")
                    if _best_bc:
                        _bmt = _MODEL_LABEL_INV.get(
                            _best_bc.get("best_model_type", ""), "—"
                        )
                        _bfn = len(_best_bc.get("best_features", []))
                        st.caption(
                            f"Current best: **{_bmt}**  ·  **{_bfn}** features"
                        )
                with _cb:
                    if st.button("⏹ Cancel", key="af_cancel_btn"):
                        cancel_task(_af_task_id)

                time.sleep(0.5)
                st.rerun()

    # ── Layout ────────────────────────────────────────────────────────────────
    left, right = st.columns([55, 45], gap="large")

    with left:

        # ── ① Media Channels ─────────────────────────────────────────────────
        with st.expander("① Media Channels", expanded=True):
            st.caption(
                "Select columns that represent paid media/channel spend or impressions. "
                "Adstock and saturation transforms are only available for these columns."
            )
            if not _input_cols:
                st.warning("No input channels set — configure in Tab 1 → ⑧ first.")
            media_sel = st.multiselect(
                "Media / channel columns",
                base_cols,
                default=[c for c in media_channels if c in base_cols],
                key=wk("media_channels"),
            )
            if media_sel != media_channels:
                cfg["media_channels"] = media_sel
                # Recompute derived sets so the rest of the page is consistent
                media_derived = {c for c in media_sel if c in base_cols}
                for t in transforms:
                    out = t.get("output_col", "")
                    if (out and t.get("type") in _CREATES_NEW_COL
                            and t.get("source_col") in media_derived):
                        media_derived.add(out)
                media_avail = [c for c in avail_cols if c in media_derived]
                st.rerun()

            if target_col:
                st.caption(f"Target variable (from Tab 1): **{target_col}**")
            else:
                st.caption("No target variable set — configure in Tab 1 → ⑧.")

        # ── ② Auto-Fit ────────────────────────────────────────────────────────
        with st.expander("② Auto-Fit", expanded=False):
            st.caption(
                "Randomly search feature subsets, transformation pipelines, model "
                "types, and hyperparameters.  All six models are evaluated each "
                "iteration.  On completion the best configuration is applied to "
                "**③ Transformations** and **Tab 3 → Prior Modeling** automatically."
            )

            # ── Constraints ──────────────────────────────────────────────────
            st.markdown(
                '<p class="section-mini-label">Constraints</p>',
                unsafe_allow_html=True,
            )
            _af_ca, _af_cb = st.columns(2)
            with _af_ca:
                _af_pos_coef = st.checkbox(
                    "Non-negative coefficients",
                    value=bool(af_cfg.get("positive_coefficients", False)),
                    key=wk("af_pos_coef"),
                    help=(
                        "Linear models: constrain coefficients ≥ 0 during fitting.  "
                        "Tree models: mean SHAP values are clipped to ≥ 0 post-hoc."
                    ),
                )
            with _af_cb:
                _af_pos_int = st.checkbox(
                    "Non-negative intercept",
                    value=bool(af_cfg.get("positive_intercept", False)),
                    key=wk("af_pos_int"),
                    help=(
                        "Linear models: reject configurations where the fitted "
                        "intercept is negative.  "
                        "Tree models: SHAP base value clipped to ≥ 0 post-hoc."
                    ),
                )
            if _af_pos_coef != af_cfg.get("positive_coefficients", False):
                af_cfg["positive_coefficients"] = _af_pos_coef
                st.rerun()
            if _af_pos_int != af_cfg.get("positive_intercept", False):
                af_cfg["positive_intercept"] = _af_pos_int
                st.rerun()

            if _af_pos_coef or _af_pos_int:
                st.caption(
                    "ℹ️ For Random Forest and XGBoost, positivity is applied as "
                    "post-hoc clipping of SHAP contributions / base value.  "
                    "Both tree models remain active in the search."
                )

            # ── Optimisation metric ───────────────────────────────────────────
            st.markdown(
                '<p class="section-mini-label">Optimise by</p>',
                unsafe_allow_html=True,
            )
            _af_metric_opts   = list(_AF_METRIC_LABELS.keys())
            _af_metric_labels = [_AF_METRIC_LABELS[k] for k in _af_metric_opts]
            _af_stored_metric = af_cfg.get("metric", "adj_r2")
            _af_metric_idx    = (
                _af_metric_opts.index(_af_stored_metric)
                if _af_stored_metric in _af_metric_opts else 1
            )
            _af_sel_metric_lbl = st.selectbox(
                "Metric",
                _af_metric_labels,
                index=_af_metric_idx,
                key=wk("af_metric"),
                label_visibility="collapsed",
            )
            _af_sel_metric_key = _af_metric_opts[
                _af_metric_labels.index(_af_sel_metric_lbl)
            ]
            if _af_sel_metric_key != af_cfg.get("metric"):
                af_cfg["metric"] = _af_sel_metric_key
                st.rerun()

            # ── Iterations ────────────────────────────────────────────────────
            st.markdown(
                '<p class="section-mini-label">Search iterations</p>',
                unsafe_allow_html=True,
            )
            _af_sel_n_iter = st.slider(
                "Iterations",
                min_value=50, max_value=500, step=25,
                value=int(af_cfg.get("n_iter", 200)),
                key=wk("af_n_iter"),
                label_visibility="collapsed",
                help=(
                    "Number of random configurations to evaluate. "
                    "More iterations = better coverage but longer runtime."
                ),
            )
            if _af_sel_n_iter != af_cfg.get("n_iter"):
                af_cfg["n_iter"] = _af_sel_n_iter
                st.rerun()
            _af_est_lo = max(1, int(_af_sel_n_iter * 0.1))
            _af_est_hi = max(2, int(_af_sel_n_iter * 0.4))
            st.caption(
                f"Estimated runtime: **{_af_est_lo}–{_af_est_hi} seconds** "
                f"({_af_sel_n_iter} iterations × 0.1–0.4 s each; "
                "varies with dataset size)."
            )

            # ── Max p-value ────────────────────────────────────────────────────
            st.markdown(
                '<p class="section-mini-label">Max allowed p-value</p>',
                unsafe_allow_html=True,
            )
            _af_max_pval = st.slider(
                "Max p-value",
                min_value=0.01, max_value=1.00, step=0.01,
                value=float(af_cfg.get("max_pval", 0.10)),
                key=wk("af_max_pval"),
                label_visibility="collapsed",
                help=(
                    "Candidate configurations where any feature p-value exceeds "
                    "this threshold are rejected during the search.  "
                    "Linear models use active-set OLS.  "
                    "Tree models use the SHAP t-test (H₀: mean SHAP = 0).  "
                    "Set to 1.00 to disable the constraint."
                ),
            )
            if _af_max_pval != af_cfg.get("max_pval", 0.10):
                af_cfg["max_pval"] = _af_max_pval
                st.rerun()

            # ── Models to evaluate ────────────────────────────────────────────
            st.markdown(
                '<p class="section-mini-label">Models to evaluate</p>',
                unsafe_allow_html=True,
            )
            _af_model_opts = [
                "linear", "ridge", "lasso", "elasticnet",
                "randomforest", "xgboost",
            ]
            _af_model_labels_map = {
                "linear":       "Linear Regression",
                "ridge":        "Ridge",
                "lasso":        "Lasso",
                "elasticnet":   "ElasticNet",
                "randomforest": "Random Forest",
                "xgboost":      "XGBoost",
            }
            _stored_allowed = af_cfg.get("allowed_models", _af_model_opts)
            _sel_models = st.multiselect(
                "Models",
                options=_af_model_opts,
                format_func=lambda k: _af_model_labels_map[k],
                default=[m for m in _stored_allowed if m in _af_model_opts],
                key=wk("af_allowed_models"),
                label_visibility="collapsed",
                help=(
                    "Model types to consider during the Auto-Fit search.  "
                    "Deselect any you want to exclude."
                ),
            )
            if not _sel_models:
                st.warning("⚠️ Select at least one model type.")
                _sel_models = _stored_allowed
            if _sel_models != af_cfg.get("allowed_models", _af_model_opts):
                af_cfg["allowed_models"] = _sel_models
                st.rerun()

            # ── Launch button ─────────────────────────────────────────────────
            st.markdown("---")
            _af_can_run = bool(base_cols) and bool(target_col)
            if not _af_can_run:
                st.warning(
                    "Set at least one input channel (Tab 1 → ⑧) and a target "
                    "column before running Auto-Fit."
                )
            else:
                if st.button("🎯 Run Auto-Fit", key=wk("af_run_btn"), type="primary"):
                    import uuid as _uuid
                    _new_task_id = str(_uuid.uuid4())
                    # Detect date column for last-12-months subsetting
                    _af_date_col = None
                    _af_dt_cols  = [
                        c for c in tab1_cols
                        if pd.api.types.is_datetime64_any_dtype(tab1_df[c])
                    ]
                    if _af_dt_cols:
                        _af_df_cfg_col = cfg.get("date_filter", {}).get("col")
                        _af_date_col = (
                            _af_df_cfg_col
                            if _af_df_cfg_col in _af_dt_cols
                            else _af_dt_cols[0]
                        )
                    start_autofit(
                        task_id         = _new_task_id,
                        df              = tab1_df,
                        target_col      = target_col,
                        input_cols      = base_cols,
                        media_cols      = cfg.get("media_channels", []),
                        groupby_cols    = cfg.get("groupby_columns", []),
                        constraints     = {
                            "positive_coefficients": _af_pos_coef,
                            "positive_intercept":    _af_pos_int,
                            "max_pval":              _af_max_pval,
                            "allowed_models":        _sel_models,
                        },
                        metric          = _af_sel_metric_key,
                        n_iter          = _af_sel_n_iter,
                        seed            = 42,
                        date_filter_cfg = cfg.get("date_filter"),
                        date_col        = _af_date_col,
                    )
                    af_cfg["task_id"] = _new_task_id
                    af_cfg["n_iter"]  = _af_sel_n_iter
                    af_cfg["metric"]  = _af_sel_metric_key
                    st.rerun()

            # ── Previous result summary ───────────────────────────────────────
            _af_prev = af_cfg.get("result")
            if _af_prev:
                st.markdown("---")
                st.markdown(
                    '<p class="section-mini-label">Last Auto-Fit result</p>',
                    unsafe_allow_html=True,
                )
                _af_pm = _MODEL_LABEL_INV.get(_af_prev.get("best_model_type", ""), "—")
                _af_pf = len(_af_prev.get("best_features", []))
                _af_ps = _af_prev.get("best_score", float("nan"))
                _af_pk = _af_prev.get("metric_label", "Score")
                _af_pi = _af_prev.get("iterations_run", "—")
                try:
                    _af_score_str = f"{_af_ps:.4f}"
                except Exception:
                    _af_score_str = str(_af_ps)
                st.caption(
                    f"**{_af_pm}** · **{_af_pf}** features · "
                    f"{_af_pk} = **{_af_score_str}** · "
                    f"{_af_pi} iterations evaluated"
                )
                _af_tr_df = _af_describe_transforms(
                    _af_prev.get("best_transforms", [])
                )
                if not _af_tr_df.empty:
                    st.dataframe(
                        _af_tr_df, use_container_width=True, hide_index=True
                    )
                if st.button("▶ Go to Prior Modeling", key="af_goto_tab3"):
                    st.session_state.current_tab = 2
                    st.rerun()

        # ── ③ Transformations ─────────────────────────────────────────────────
        with st.expander("③ Transformations", expanded=True):
            st.caption(
                "Add transforms in any order. "
                "Adstock / norm / saturation create a new column with a suffix; "
                "all other transforms (lag, lead, MA, mean-centering, zero mask) "
                "overwrite the source column in place. "
                "Adstock and saturation are only available for media channel columns."
            )

            # List existing transforms
            to_del_t = None
            if transforms:
                for i, t in enumerate(transforms):
                    out = t.get("output_col", "")
                    r1, r2, r3 = st.columns([3, 6, 1])
                    with r1:
                        if t.get("type") in _CREATES_NEW_COL:
                            # New column — show output name
                            st.markdown(
                                f'<span class="t2-tag">{out}</span>',
                                unsafe_allow_html=True,
                            )
                        else:
                            # In-place — show source column name
                            st.markdown(
                                f'<span class="calc-tag">{t.get("source_col", "")}</span>',
                                unsafe_allow_html=True,
                            )
                    with r2:
                        st.caption(_t2_describe(t))
                    with r3:
                        if st.button("✕", key=f"del_t2_{i}_{st.session_state.widget_epoch}"):
                            to_del_t = i

                if to_del_t is not None:
                    cfg["adstock_transforms"].pop(to_del_t)
                    st.rerun()
            else:
                st.caption("No transforms added yet.")

            st.markdown("---")
            st.markdown('<p class="section-mini-label">Add transform</p>', unsafe_allow_html=True)

            # ── Transform type selector (OUTSIDE form) ────────────────────────
            t_label = st.selectbox(
                "Transform type",
                _T_LABELS,
                key=wk("t2_type"),
            )
            t_type = _LABEL_TO_TYPE[t_label]

            # ── Adstock method selector (OUTSIDE form, only for adstock) ──────
            adstock_method: str | None = None
            if t_type == "adstock":
                adstock_method = st.selectbox(
                    "Adstock method",
                    ["geometric", "weibull", "hill"],
                    key=wk("t2_adstock_method"),
                )

            # ── Determine available source columns for this type ──────────────
            # Saturation is restricted to columns that already carry the
            # _adstock suffix (i.e. adstock has been applied).
            if t_type == "saturation":
                src_options = [
                    c for c in avail_cols
                    if c.endswith("_adstock") and c in media_derived
                ]
            elif t_type == "adstock":
                src_options = media_avail
            else:
                src_options = avail_cols

            if t_type == "saturation" and not src_options:
                st.warning(
                    "Saturation requires a column with adstock already applied "
                    "(name ending in `_adstock`). "
                    "Add an **Adstock** transform to a media channel first, "
                    "then come back to add Saturation."
                )
            elif t_type == "adstock" and not src_options:
                st.warning(
                    "No media channels available. "
                    "Select media columns in ① above first."
                )
            elif not src_options:
                st.warning("No source columns available.")
            else:
                # ── Parameter form ────────────────────────────────────────────
                with st.form(key=wk("form_t2"), clear_on_submit=True):
                    new_params: dict = {}

                    src_col = st.selectbox(
                        "Source column",
                        src_options,
                        key=f"ft2_src_{t_label}",
                    )

                    # ── Adstock params ────────────────────────────────────────
                    if t_type == "adstock":
                        max_lag = st.number_input(
                            "Max lags (N)",
                            min_value=1, max_value=104, value=4, step=1,
                            key=f"ft2_adstock_ml_{adstock_method}",
                        )
                        new_params["max_lag"] = int(max_lag)
                        new_params["method"]  = adstock_method

                        if adstock_method == "geometric":
                            alpha = st.slider(
                                "Decay rate (α)  — 0 = instant, 1 = no decay",
                                min_value=0.01, max_value=0.99,
                                value=0.50, step=0.01,
                                key="ft2_geo_alpha",
                            )
                            new_params["alpha"] = float(alpha)

                        elif adstock_method == "weibull":
                            ca, cb = st.columns(2)
                            with ca:
                                shape = st.number_input(
                                    "Shape", min_value=0.1, value=2.0, step=0.1,
                                    key="ft2_wb_shape",
                                )
                            with cb:
                                scale = st.number_input(
                                    "Scale", min_value=0.1, value=2.0, step=0.1,
                                    key="ft2_wb_scale",
                                )
                            new_params["shape"] = float(shape)
                            new_params["scale"] = float(scale)

                        elif adstock_method == "hill":
                            ca, cb = st.columns(2)
                            with ca:
                                h_alpha = st.number_input(
                                    "Alpha", min_value=0.1, value=2.0, step=0.1,
                                    key="ft2_hill_alpha",
                                )
                            with cb:
                                h_gamma = st.number_input(
                                    "Gamma", min_value=0.1, value=2.0, step=0.1,
                                    key="ft2_hill_gamma",
                                )
                            new_params["alpha"] = float(h_alpha)
                            new_params["gamma"] = float(h_gamma)

                    # ── Saturation params ─────────────────────────────────────
                    elif t_type == "saturation":
                        ca, cb = st.columns(2)
                        with ca:
                            c_val = st.number_input(
                                "Asymptote (c)",
                                min_value=0.001, value=1.0, step=0.1,
                                format="%.3f",
                                key="ft2_sat_c",
                            )
                        with cb:
                            d_val = st.number_input(
                                "Curvature (d)",
                                min_value=0.0001, value=0.001, step=0.0001,
                                format="%.4f",
                                key="ft2_sat_d",
                            )
                        new_params = {"c": float(c_val), "d": float(d_val)}

                    # ── Norm params ───────────────────────────────────────────
                    elif t_type == "norm":
                        nm = st.selectbox(
                            "Method",
                            ["minmax", "mean", "z-score"],
                            key="ft2_norm_method",
                        )
                        new_params = {"method": nm}
                        grp = cfg.get("groupby_columns", [])
                        if grp:
                            st.caption(f"Group-aware — grouped by {grp}.")
                        else:
                            st.caption("Global (no grouping set in Tab 1 → ③).")

                    # ── Lag / Lead params ─────────────────────────────────────
                    elif t_type in ("lag", "lead"):
                        n_val = st.number_input(
                            "Units (N)", min_value=1, value=1, step=1,
                            key=f"ft2_ll_n_{t_type}",
                        )
                        new_params = {"n": int(n_val)}
                        grp = cfg.get("groupby_columns", [])
                        if grp:
                            st.caption(f"Computed within groups: {grp}.")

                    # ── Moving average params ─────────────────────────────────
                    elif t_type == "moving_avg":
                        n_val = st.number_input(
                            "Window (N periods)", min_value=1, value=3, step=1,
                            key="ft2_ma_n",
                        )
                        new_params = {"n": int(n_val)}
                        grp = cfg.get("groupby_columns", [])
                        if grp:
                            st.caption(f"Computed within groups: {grp}.")

                    # ── Mean centering (no extra params) ──────────────────────
                    elif t_type == "mean_center":
                        grp = cfg.get("groupby_columns", [])
                        if grp:
                            st.caption(f"Mean subtracted within groups: {grp}.")
                        else:
                            st.caption("Subtracts global mean from each value.")

                    # ── Zero mask ─────────────────────────────────────────────
                    elif t_type == "zero_mask":
                        if target_col:
                            st.caption(
                                f"Sets values to 0 wherever **{target_col}** = 0."
                            )
                        else:
                            st.warning(
                                "No target column set — configure in Tab 1 → ⑧. "
                                "Transform will copy the column unchanged."
                            )

                    # ── Output preview ────────────────────────────────────────
                    out_preview = build_output_col(src_col, t_type, new_params)
                    if t_type in _CREATES_NEW_COL:
                        st.caption(f"Creates new column: **`{out_preview}`**")
                    else:
                        st.caption(
                            f"Overwrites **`{src_col}`** in place — no new column."
                        )

                    if st.form_submit_button("Add Transform"):
                        # Duplicate guard only needed for new-column transforms
                        if t_type in _CREATES_NEW_COL and out_preview in avail_cols:
                            st.warning(
                                f"Column **`{out_preview}`** already exists. "
                                "Delete the existing entry or choose a different source."
                            )
                        else:
                            cfg["adstock_transforms"].append(
                                {
                                    "source_col": src_col,
                                    "type":       t_type,
                                    "params":     new_params,
                                    "output_col": out_preview,
                                }
                            )
                            st.rerun()

        # ── ④ Date Filter (applied after transforms) ──────────────────────────
        with st.expander("④ Date Filter"):
            st.caption(
                "Subset the analysis window. "
                "Transforms run on the full date range first so adstock carry-over is "
                "calculated correctly; this filter is applied afterwards."
            )
            dt_cols = [
                c for c in tab1_cols
                if pd.api.types.is_datetime64_any_dtype(tab1_df[c])
            ]
            if not dt_cols:
                st.caption(
                    "No datetime columns detected. "
                    "Convert a column in Tab 1 → ② first."
                )
            else:
                df_cfg = cfg["date_filter"]
                stored_col = df_cfg.get("col")
                default_col = stored_col if stored_col in dt_cols else dt_cols[0]

                date_col_sel = st.selectbox(
                    "Date column",
                    dt_cols,
                    index=dt_cols.index(default_col),
                    key=wk("df_col"),
                )

                date_series = pd.to_datetime(tab1_df[date_col_sel]).dropna()
                if not date_series.empty:
                    actual_min = date_series.min().date()
                    actual_max = date_series.max().date()

                    # Reset stored dates if column changed
                    if stored_col != date_col_sel:
                        stored_min, stored_max = actual_min, actual_max
                    else:
                        stored_min = df_cfg.get("min_date", actual_min)
                        stored_max = df_cfg.get("max_date", actual_max)

                    # Clamp to valid range
                    stored_min = max(actual_min, stored_min)
                    stored_max = min(actual_max, stored_max)

                    ca, cb = st.columns(2)
                    with ca:
                        sel_min = st.date_input(
                            "Start date",
                            value=stored_min,
                            min_value=actual_min,
                            max_value=actual_max,
                            key=wk(f"df_min_{date_col_sel}"),
                        )
                    with cb:
                        sel_max = st.date_input(
                            "End date",
                            value=stored_max,
                            min_value=actual_min,
                            max_value=actual_max,
                            key=wk(f"df_max_{date_col_sel}"),
                        )

                    new_df_cfg = {
                        "col": date_col_sel,
                        "min_date": sel_min,
                        "max_date": sel_max,
                    }
                    if new_df_cfg != {k: df_cfg.get(k) for k in new_df_cfg}:
                        cfg["date_filter"] = new_df_cfg
                        st.rerun()

                    # Row-count feedback
                    try:
                        filtered_n = int(
                            (
                                (pd.to_datetime(tab1_df[date_col_sel]).dt.date >= sel_min) &
                                (pd.to_datetime(tab1_df[date_col_sel]).dt.date <= sel_max)
                            ).sum()
                        )
                        total_n = len(tab1_df)
                        if filtered_n < total_n:
                            st.caption(
                                f"Active filter: **{filtered_n:,}** of {total_n:,} rows "
                                f"included after transforms."
                            )
                        else:
                            st.caption(
                                f"Full range selected — all **{total_n:,}** rows included."
                            )
                    except Exception:
                        pass

    # ── Right panel: Live Preview ─────────────────────────────────────────────
    with right:
        st.markdown('<p class="preview-label">Live Preview</p>', unsafe_allow_html=True)

        full_df = get_processed_df()

        if full_df is not None:
            # Download buttons (in addition to those in the nav bar)
            _download_buttons(full_df, "tab2_right")

            # Highlight columns newly created by Tab 2 (adstock/norm/saturation)
            new_cols = [
                t.get("output_col", "")
                for t in transforms
                if t.get("type") in _CREATES_NEW_COL
                and t.get("output_col", "") in full_df.columns
            ]
            if new_cols:
                tags = " ".join(
                    f'<span class="t2-tag">{c}</span>' for c in new_cols
                )
                st.markdown(
                    f'<div style="margin-bottom:0.4rem;font-size:0.75rem;'
                    f'color:#6b7280;">New columns: {tags}</div>',
                    unsafe_allow_html=True,
                )

            st.dataframe(full_df.head(200), use_container_width=True, height=430)
            st.caption(
                f"Showing up to 200 of **{len(full_df):,}** rows  ×  "
                f"**{len(full_df.columns)}** columns"
            )
            with st.expander("Column types"):
                dtype_df = pd.DataFrame(
                    {
                        "Column": full_df.columns,
                        "dtype":  [str(d) for d in full_df.dtypes],
                    }
                )
                st.dataframe(dtype_df, use_container_width=True, hide_index=True)
        else:
            st.info("Preview appears here once data is loaded in Tab 1.")


# ════════════════════════════════════════════════════════════════════════════
#  TAB 3 — PRIOR MODELING
# ════════════════════════════════════════════════════════════════════════════

_MODEL_LABELS = [
    "Linear Regression", "Ridge", "Lasso", "ElasticNet",
    "Random Forest", "XGBoost",
]
_MODEL_TYPE = {
    "Linear Regression": "linear",
    "Ridge":             "ridge",
    "Lasso":             "lasso",
    "ElasticNet":        "elasticnet",
    "Random Forest":     "randomforest",
    "XGBoost":           "xgboost",
}
_MODEL_LABEL_INV  = {v: k for k, v in _MODEL_TYPE.items()}
_LINEAR_MODELS    = {"linear", "ridge", "lasso", "elasticnet"}
_TREE_MODELS      = {"randomforest", "xgboost"}


# ─────────────────────────── IMPACTABLE HELPERS ──────────────────────────────

def _get_target_norm_scale(
    target_col: str,
    cfg: dict,
    df_original: pd.DataFrame | None,
    full_model_rows: pd.DataFrame,
) -> float | np.ndarray:
    """Return the inverse-normalisation scale for the target column (Tab 1 only).

    Returns
    -------
    float    — scalar multiplier (mean, minmax range, std, or scalar divisor)
    ndarray  — per-row multiplier vector (column-divisor normalisation)
    1.0      — no Tab 1 normalisation found for this column
    """
    for norm in cfg.get("normalizations", []):
        method = norm.get("method")
        if method == "column":
            if target_col in norm.get("params", {}).get("columns", []):
                div_col = norm.get("params", {}).get("div_column", "")
                if div_col and div_col in full_model_rows.columns:
                    vals = full_model_rows[div_col].values.astype(float)
                    return np.where(np.abs(vals) > 1e-10, vals, np.nan)
                return 1.0
        elif norm.get("column") == target_col:
            p = norm.get("params", {})
            if method == "scalar":
                s = float(p.get("scalar", 1.0))
                return s if s != 0.0 else 1.0
            if df_original is not None and target_col in df_original.columns:
                src = df_original[target_col].astype(float).dropna()
                if method == "mean":
                    mu = float(src.mean())
                    return mu if mu != 0.0 else 1.0
                if method == "minmax":
                    r = float(src.max() - src.min())
                    return r if r != 0.0 else 1.0
                if method == "z-score":
                    sigma = float(src.std())
                    return sigma if sigma != 0.0 else 1.0
    return 1.0


def _build_impactable_df(
    coef_df: pd.DataFrame,
    model_df: pd.DataFrame,        # rows used for fitting (features + target, model scale)
    full_model_rows: pd.DataFrame, # same rows but all columns (for column-norm divisor)
    target_col: str,
    cfg: dict,
    is_tree: bool = False,
) -> pd.DataFrame | None:
    """Compute per-channel impactable contributions and % of total KPI.

    What an impactable is
    ----------------------
    For feature i, the impactable represents how much of the original (pre-
    normalised) KPI total can be attributed to that channel.

    Linear models — contribution of feature i across all observations:
        abs_impactable_i  =  β_i  ×  Σ_t x_it  ×  scale_y

    Tree models (SHAP) — SHAP values are not the same as β × x;
    the mean SHAP is the average marginal contribution per observation, so
    the total contribution across all n observations is n × mean_SHAP:
        abs_impactable_i  =  mean_SHAP_i  ×  n  ×  scale_y

    scale_y is the inverse-normalisation scale of the *target* column
    (from Tab 1 only).  If the target was not normalised in Tab 1, scale_y = 1
    and the impactable is already in the original target units.

    Denominator
    -----------
    total_target  =  Σ_t y_t  ×  scale_y   (total KPI in original units)

    Impactable %  =  abs_impactable_i / total_target × 100

    The intercept / SHAP base value is intentionally excluded — channels only.
    For positive-intercept marketing models, the sum of channel percentages
    will be ≤ 100 % (the remainder is the model baseline).
    """
    df_orig = st.session_state.get("df_original")
    n       = len(model_df)

    scale_y = _get_target_norm_scale(target_col, cfg, df_orig, full_model_rows)

    # ── Total target in original KPI units ───────────────────────────────────
    y_arr = model_df[target_col].values.astype(float)
    if isinstance(scale_y, np.ndarray):
        total_target = float(np.nansum(y_arr * scale_y))
    else:
        total_target = float(np.nansum(y_arr) * scale_y)

    rows_out: list[dict] = []

    for _, coef_row in coef_df.iterrows():
        feat = coef_row["Feature"]

        # Intercept / base-value rows are excluded from the channel table
        if feat in {"(Intercept)", "(Base Value)"}:
            continue

        try:
            beta = float(coef_row["Coefficient"])
            if np.isnan(beta):
                continue
        except Exception:
            continue

        if feat not in model_df.columns:
            continue

        # ── Compute raw contribution (model scale) ─────────────────────────
        if is_tree:
            # For tree models: total SHAP contribution = n × mean_SHAP
            # (each observation contributes mean_SHAP regardless of feature value)
            if isinstance(scale_y, np.ndarray):
                # Column-norm: weight each "slot" by its per-row scale
                abs_imp = float(np.nansum(beta * scale_y))  # beta × Σ scale_y_t
            else:
                abs_imp = float(beta * n * scale_y)
        else:
            # For linear models: total contribution = β × Σ x_t
            x_arr = model_df[feat].values.astype(float)
            if isinstance(scale_y, np.ndarray):
                abs_imp = float(np.nansum(beta * x_arr * scale_y))
            else:
                abs_imp = float(beta * float(np.nansum(x_arr)) * scale_y)

        imp_pct = (
            abs_imp / total_target * 100.0
            if (total_target != 0.0 and not np.isnan(total_target))
            else np.nan
        )

        rows_out.append({
            "Feature":             feat,
            "Absolute Impactable": abs_imp,
            "Impactable %":        imp_pct,
        })

    if not rows_out:
        return None
    return pd.DataFrame(rows_out)


def _fmt_pval(v) -> str:
    """Format a p-value: NaN → '—', tiny → scientific, else 4 dp."""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    if v < 0.001:
        return f"{v:.2e}"
    return f"{v:.4f}"


def _fmt_float(v, digits: int = 6) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    return f"{v:.{digits}f}"


def tab_modelling() -> None:
    st.title("Prior Modeling")

    cfg = st.session_state.config

    # ── Guard: need processed data ───────────────────────────────────────────
    full_df = get_processed_df()
    if full_df is None:
        st.info("Upload and preprocess a dataset in **Tab 1** first.")
        return

    target_col = cfg.get("target_column")
    if not target_col or target_col not in full_df.columns:
        st.warning(
            "No target column found in the processed data. "
            "Set a target column in **Tab 1 → ⑧** before modelling."
        )
        return

    # ── Available feature columns ────────────────────────────────────────────
    # Tab 1 input columns (possibly modified in-place by Tab 2) +
    # columns newly created by Tab 2 adstock/norm/saturation transforms.
    input_cols   = cfg.get("input_columns", [])
    t2_new_cols  = [
        t.get("output_col", "")
        for t in cfg.get("adstock_transforms", [])
        if t.get("type") in _CREATES_NEW_COL
        and t.get("output_col", "") in full_df.columns
    ]
    # Deduplicate while preserving order
    seen: set = set()
    avail_features: list = []
    for c in input_cols + t2_new_cols:
        if c not in seen and c in full_df.columns and c != target_col:
            seen.add(c)
            avail_features.append(c)

    if not avail_features:
        st.warning(
            "No input features available. "
            "Set input channels in **Tab 1 → ⑧** before modelling."
        )
        return

    # Ensure model_config key exists
    cfg.setdefault("model_config", {})
    mcfg = cfg["model_config"]

    # ── Applied Transformations — always shown at the top, full-width ─────────
    _t2_transforms = cfg.get("adstock_transforms", [])
    if _t2_transforms:
        with st.expander(
            f"📋 Applied Transformations  ({len(_t2_transforms)} step"
            + ("s" if len(_t2_transforms) != 1 else "")
            + ")",
            expanded=True,
        ):
            st.caption(
                "Transformations applied in Tab 2, in the order they were added. "
                "These are used by both manual fit and Auto-Fit."
            )
            _tr_df = _af_describe_transforms(_t2_transforms)
            if not _tr_df.empty:
                st.dataframe(_tr_df, use_container_width=True, hide_index=True)
    else:
        st.info(
            "ℹ️ No Tab 2 transformations are applied — modelling uses the "
            "Tab 1 columns directly. Add adstock / saturation / normalisation "
            "transforms in **Tab 2** if needed."
        )

    left, right = st.columns([42, 58], gap="large")

    with left:

        # ── ① Feature Selection ──────────────────────────────────────────────
        with st.expander("① Feature Selection", expanded=True):
            st.caption(
                "Choose columns from Tab 1 input channels (including any in-place "
                "transforms from Tab 2) and new columns created by Tab 2."
            )
            feat_sel = st.multiselect(
                "Features",
                avail_features,
                default=[c for c in mcfg.get("features", []) if c in avail_features],
                key=wk("m_features"),
            )
            if feat_sel != mcfg.get("features", []):
                mcfg["features"] = feat_sel
                st.rerun()

            # Tag new vs base features
            if avail_features:
                base_tags = " ".join(
                    f'<span class="coef-tag">{c}</span>'
                    for c in avail_features if c not in t2_new_cols
                )
                t2_tags = " ".join(
                    f'<span class="t2-tag">{c}</span>'
                    for c in avail_features if c in t2_new_cols
                )
                if base_tags:
                    st.markdown(
                        f'<div style="margin-top:0.3rem;font-size:0.73rem;'
                        f'color:#6b7280;">Tab 1: {base_tags}</div>',
                        unsafe_allow_html=True,
                    )
                if t2_tags:
                    st.markdown(
                        f'<div style="margin-top:0.2rem;font-size:0.73rem;'
                        f'color:#6b7280;">Tab 2 (new): {t2_tags}</div>',
                        unsafe_allow_html=True,
                    )

            st.caption(f"Target: **{target_col}**")

        # ── ② Model & Hyperparameters ────────────────────────────────────────
        with st.expander("② Model & Hyperparameters", expanded=True):

            stored_model = mcfg.get("model_type", "linear")
            stored_label = _MODEL_LABEL_INV.get(stored_model, "Linear Regression")

            model_label = st.selectbox(
                "Model type",
                _MODEL_LABELS,
                index=_MODEL_LABELS.index(stored_label),
                key=wk("m_model"),
            )
            model_type = _MODEL_TYPE[model_label]

            stored_params = mcfg.get("params", {})
            new_params: dict = {}

            # ════════════════════════════════════════════════════════════════
            #  LINEAR MODEL HYPERPARAMETERS
            # ════════════════════════════════════════════════════════════════
            if model_type in _LINEAR_MODELS:

                st.markdown(
                    '<p class="section-mini-label">Common options</p>',
                    unsafe_allow_html=True,
                )
                fit_intercept = st.checkbox(
                    "Fit intercept",
                    value=bool(stored_params.get("fit_intercept", True)),
                    key=wk("m_fit_intercept"),
                    help="Include a constant (intercept) term in the model.",
                )
                positive = st.checkbox(
                    "Non-negative coefficients",
                    value=bool(stored_params.get("positive", False)),
                    key=wk("m_positive"),
                    help="Constrain all coefficients to be ≥ 0 (positive=True). "
                         "For Lasso/ElasticNet p-values fall back to active-set OLS.",
                )
                new_params["fit_intercept"] = fit_intercept
                new_params["positive"]      = positive

                if model_type in ("ridge", "lasso", "elasticnet"):
                    st.markdown(
                        '<p class="section-mini-label">Regularisation</p>',
                        unsafe_allow_html=True,
                    )
                    alpha = st.number_input(
                        "Alpha  (regularisation strength)",
                        min_value=0.0001,
                        value=float(stored_params.get("alpha", 1.0)),
                        step=0.1, format="%.4f",
                        key=wk("m_alpha"),
                        help="Higher = stronger regularisation, smaller coefficients.",
                    )
                    new_params["alpha"] = float(alpha)

                if model_type == "elasticnet":
                    l1_ratio = st.slider(
                        "L1 ratio  (0 = Ridge, 1 = Lasso)",
                        min_value=0.0, max_value=1.0,
                        value=float(stored_params.get("l1_ratio", 0.5)),
                        step=0.01,
                        key=wk("m_l1_ratio"),
                    )
                    new_params["l1_ratio"] = float(l1_ratio)

                if model_type in ("lasso", "elasticnet"):
                    max_iter = st.number_input(
                        "Max iterations",
                        min_value=100, max_value=100_000,
                        value=int(stored_params.get("max_iter", 10_000)),
                        step=500,
                        key=wk("m_max_iter"),
                    )
                    new_params["max_iter"] = int(max_iter)

            # ════════════════════════════════════════════════════════════════
            #  RANDOM FOREST HYPERPARAMETERS
            # ════════════════════════════════════════════════════════════════
            elif model_type == "randomforest":

                st.markdown(
                    '<p class="section-mini-label">Forest structure</p>',
                    unsafe_allow_html=True,
                )
                ca, cb = st.columns(2)
                with ca:
                    n_est = st.number_input(
                        "Trees (n_estimators)",
                        min_value=10, max_value=2000,
                        value=int(stored_params.get("n_estimators", 100)),
                        step=10,
                        key=wk("m_rf_n_est"),
                        help="Number of trees in the forest.",
                    )
                with cb:
                    max_depth_rf = st.number_input(
                        "Max depth  (0 = unlimited)",
                        min_value=0, max_value=50,
                        value=int(stored_params.get("max_depth", 0)),
                        step=1,
                        key=wk("m_rf_depth"),
                        help="Maximum depth of each tree. 0 means no limit.",
                    )
                new_params["n_estimators"] = int(n_est)
                new_params["max_depth"]    = int(max_depth_rf)

                st.markdown(
                    '<p class="section-mini-label">Split criteria</p>',
                    unsafe_allow_html=True,
                )
                ca, cb = st.columns(2)
                with ca:
                    min_split = st.number_input(
                        "Min samples to split",
                        min_value=2, max_value=200,
                        value=int(stored_params.get("min_samples_split", 2)),
                        step=1,
                        key=wk("m_rf_min_split"),
                        help="Minimum number of samples required to split a node.",
                    )
                with cb:
                    min_leaf = st.number_input(
                        "Min samples per leaf",
                        min_value=1, max_value=200,
                        value=int(stored_params.get("min_samples_leaf", 1)),
                        step=1,
                        key=wk("m_rf_min_leaf"),
                        help="Minimum number of samples required at a leaf node.",
                    )
                new_params["min_samples_split"] = int(min_split)
                new_params["min_samples_leaf"]  = int(min_leaf)

                ca, cb = st.columns(2)
                with ca:
                    max_feat_opts = ["sqrt", "log2", "all"]
                    stored_mf     = stored_params.get("max_features", "sqrt")
                    max_feat = st.selectbox(
                        "Max features per split",
                        max_feat_opts,
                        index=max_feat_opts.index(stored_mf) if stored_mf in max_feat_opts else 0,
                        key=wk("m_rf_max_feat"),
                        help="'sqrt' = √p features; 'log2' = log₂p; 'all' = all features.",
                    )
                with cb:
                    rf_seed = st.number_input(
                        "Random seed",
                        min_value=0, max_value=99999,
                        value=int(stored_params.get("random_state", 42)),
                        step=1,
                        key=wk("m_rf_seed"),
                    )
                new_params["max_features"]  = max_feat
                new_params["random_state"]  = int(rf_seed)

                st.markdown(
                    '<p class="section-mini-label">Positivity constraints</p>',
                    unsafe_allow_html=True,
                )
                ca, cb = st.columns(2)
                with ca:
                    rf_pos_coef = st.checkbox(
                        "Non-negative SHAP contributions",
                        value=bool(stored_params.get("positive", False)),
                        key=wk("m_rf_pos_coef"),
                        help=(
                            "Clip mean SHAP values to ≥ 0 after inference.  "
                            "The tree model itself is unconstrained during training — "
                            "this applies post-hoc to the displayed coefficients."
                        ),
                    )
                with cb:
                    rf_pos_int = st.checkbox(
                        "Non-negative base value",
                        value=bool(stored_params.get("positive_intercept", False)),
                        key=wk("m_rf_pos_int"),
                        help="Clip the SHAP base value E[f(x)] to ≥ 0 after inference.",
                    )
                new_params["positive"]           = rf_pos_coef
                new_params["positive_intercept"] = rf_pos_int

            # ════════════════════════════════════════════════════════════════
            #  XGBOOST HYPERPARAMETERS
            # ════════════════════════════════════════════════════════════════
            elif model_type == "xgboost":

                st.markdown(
                    '<p class="section-mini-label">Boosting structure</p>',
                    unsafe_allow_html=True,
                )
                ca, cb = st.columns(2)
                with ca:
                    n_est_xgb = st.number_input(
                        "Boosting rounds (n_estimators)",
                        min_value=10, max_value=2000,
                        value=int(stored_params.get("n_estimators", 100)),
                        step=10,
                        key=wk("m_xgb_n_est"),
                        help="Number of gradient boosting rounds.",
                    )
                with cb:
                    max_depth_xgb = st.number_input(
                        "Max depth",
                        min_value=1, max_value=20,
                        value=int(stored_params.get("max_depth", 6)),
                        step=1,
                        key=wk("m_xgb_depth"),
                        help="Maximum depth of each booster tree.",
                    )
                new_params["n_estimators"] = int(n_est_xgb)
                new_params["max_depth"]    = int(max_depth_xgb)

                lr_xgb = st.number_input(
                    "Learning rate (eta)",
                    min_value=0.001, max_value=1.0,
                    value=float(stored_params.get("learning_rate", 0.3)),
                    step=0.01, format="%.3f",
                    key=wk("m_xgb_lr"),
                    help="Shrinks feature weights after each step to prevent overfitting.",
                )
                new_params["learning_rate"] = float(lr_xgb)

                st.markdown(
                    '<p class="section-mini-label">Subsampling</p>',
                    unsafe_allow_html=True,
                )
                ca, cb = st.columns(2)
                with ca:
                    subsample_xgb = st.slider(
                        "Row subsample",
                        min_value=0.1, max_value=1.0,
                        value=float(stored_params.get("subsample", 1.0)),
                        step=0.05,
                        key=wk("m_xgb_sub"),
                        help="Fraction of rows sampled per boosting round.",
                    )
                with cb:
                    colsample_xgb = st.slider(
                        "Column subsample",
                        min_value=0.1, max_value=1.0,
                        value=float(stored_params.get("colsample_bytree", 1.0)),
                        step=0.05,
                        key=wk("m_xgb_col"),
                        help="Fraction of features sampled per tree.",
                    )
                new_params["subsample"]        = float(subsample_xgb)
                new_params["colsample_bytree"] = float(colsample_xgb)

                st.markdown(
                    '<p class="section-mini-label">Regularisation</p>',
                    unsafe_allow_html=True,
                )
                ca, cb, cc = st.columns(3)
                with ca:
                    reg_alpha_xgb = st.number_input(
                        "L1 (reg_alpha)",
                        min_value=0.0, value=float(stored_params.get("reg_alpha", 0.0)),
                        step=0.1, format="%.4f",
                        key=wk("m_xgb_alpha"),
                        help="L1 regularisation on leaf weights.",
                    )
                with cb:
                    reg_lambda_xgb = st.number_input(
                        "L2 (reg_lambda)",
                        min_value=0.0, value=float(stored_params.get("reg_lambda", 1.0)),
                        step=0.1, format="%.4f",
                        key=wk("m_xgb_lambda"),
                        help="L2 regularisation on leaf weights (default = 1).",
                    )
                with cc:
                    xgb_seed = st.number_input(
                        "Random seed",
                        min_value=0, max_value=99999,
                        value=int(stored_params.get("random_state", 42)),
                        step=1,
                        key=wk("m_xgb_seed"),
                    )
                new_params["reg_alpha"]    = float(reg_alpha_xgb)
                new_params["reg_lambda"]   = float(reg_lambda_xgb)
                new_params["random_state"] = int(xgb_seed)

                st.markdown(
                    '<p class="section-mini-label">Positivity constraints</p>',
                    unsafe_allow_html=True,
                )
                ca, cb = st.columns(2)
                with ca:
                    xgb_pos_coef = st.checkbox(
                        "Non-negative SHAP contributions",
                        value=bool(stored_params.get("positive", False)),
                        key=wk("m_xgb_pos_coef"),
                        help=(
                            "Clip mean SHAP values to ≥ 0 after inference.  "
                            "The tree model itself is unconstrained during training — "
                            "this applies post-hoc to the displayed coefficients."
                        ),
                    )
                with cb:
                    xgb_pos_int = st.checkbox(
                        "Non-negative base value",
                        value=bool(stored_params.get("positive_intercept", False)),
                        key=wk("m_xgb_pos_int"),
                        help="Clip the SHAP base value E[f(x)] to ≥ 0 after inference.",
                    )
                new_params["positive"]           = xgb_pos_coef
                new_params["positive_intercept"] = xgb_pos_int

            # ── Persist changes ───────────────────────────────────────────────
            if model_type != mcfg.get("model_type") or new_params != mcfg.get("params", {}):
                mcfg["model_type"] = model_type
                mcfg["params"]     = new_params
                st.rerun()

    # ── Right panel: Model results ─────────────────────────────────────────────
    with right:
        st.markdown('<p class="preview-label">Model Results</p>', unsafe_allow_html=True)

        features = [f for f in mcfg.get("features", []) if f in full_df.columns]

        if not features:
            st.info("Select one or more features in **① Feature Selection** to fit the model.")
        else:
            # Drop rows where any feature or target is NaN
            cols_needed = features + [target_col]
            model_df    = full_df[cols_needed].dropna()
            n_dropped   = len(full_df) - len(model_df)

            if len(model_df) < max(3, len(features) + 1):
                st.warning(
                    f"Only **{len(model_df)}** rows remain after dropping NaNs "
                    f"({n_dropped} dropped). Need at least {len(features) + 1} rows "
                    "to fit this model."
                )
            else:
                if n_dropped > 0:
                    st.caption(
                        f"ℹ️ {n_dropped} rows with missing values excluded "
                        f"— fitting on {len(model_df):,} rows."
                    )

                X = model_df[features]
                y = model_df[target_col]

                cur_model_type = mcfg.get("model_type", "linear")
                cur_params     = mcfg.get("params", {})

                try:
                    result = fit_model(X, y, cur_model_type, cur_params)
                except Exception as exc:
                    st.error(f"Model fitting failed: {exc}")
                    st.stop()

                # ── P-value method note ──────────────────────────────────────
                st.markdown(
                    f'<div class="pval-method-note">'
                    f'P-value method: <strong>{result["pvalue_method"]}</strong>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

                # ── Coefficient table ────────────────────────────────────────
                _is_tree = cur_model_type in _TREE_MODELS
                st.markdown(
                    '<p class="charts-label">'
                    + ("SHAP Feature Contributions" if _is_tree else "Coefficient Estimates")
                    + '</p>',
                    unsafe_allow_html=True,
                )
                coef_df = result["coef_df"].copy()

                # Apply readable formatting
                coef_display = pd.DataFrame({
                    "Feature":     coef_df["Feature"],
                    "Coefficient": coef_df["Coefficient"].map(lambda v: _fmt_float(v, 6)),
                    "Std Error":   coef_df["Std Error"].map(lambda v: _fmt_float(v, 6)),
                    "t-stat":      coef_df["t-stat"].map(lambda v: _fmt_float(v, 4)),
                    "p-value":     coef_df["p-value"].map(_fmt_pval),
                    "Sig":         coef_df["Sig"],
                })

                # Column-config tooltips differ between linear and tree models
                if _is_tree:
                    _coef_help = (
                        "Mean SHAP value — the average marginal contribution of this "
                        "feature to model predictions, relative to the base value E[f(x)]. "
                        "Positive = feature pushes predictions up on average; "
                        "negative = pushes predictions down."
                    )
                    _se_help = (
                        "Standard error of the mean SHAP value: std(SHAP)/√n. "
                        "Measures how consistently the feature's directional contribution "
                        "holds across observations."
                    )
                    _t_help = (
                        "t-statistic = mean SHAP / SE. "
                        "Tests whether the average directional contribution is "
                        "significantly different from zero."
                    )
                    _p_help = (
                        "Two-sided p-value from the t-distribution (df = n−1). "
                        "Tests H₀: mean SHAP contribution = 0. "
                        "Small values indicate the feature's average directional effect "
                        "is unlikely to be zero across the observed data."
                    )
                    _feat_help = "Input feature name."
                else:
                    _coef_help = (
                        "Estimated β — the change in the target for a one-unit increase "
                        "in this feature, holding all others constant."
                    )
                    _se_help = (
                        "Standard error of the coefficient estimate. "
                        "Smaller values indicate a more precise estimate. "
                        "Shown as '—' for inactive (zero) Lasso/ElasticNet coefficients."
                    )
                    _t_help = (
                        "t-statistic = Coefficient ÷ Std Error. "
                        "Large absolute values (typically |t| > 2) suggest the "
                        "coefficient is statistically distinguishable from zero."
                    )
                    _p_help = (
                        "Two-sided p-value from the t-distribution with df_residual "
                        "degrees of freedom. Small values (< 0.05) indicate the "
                        "coefficient is statistically significant."
                    )
                    _feat_help = (
                        "Parameter name. '(Intercept)' is the constant term; "
                        "all other rows are predictor coefficients."
                    )

                st.dataframe(
                    coef_display,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Feature":     st.column_config.TextColumn("Feature",     help=_feat_help),
                        "Coefficient": st.column_config.TextColumn("Coefficient", help=_coef_help),
                        "Std Error":   st.column_config.TextColumn("Std Error",   help=_se_help),
                        "t-stat":      st.column_config.TextColumn("t-stat",      help=_t_help),
                        "p-value":     st.column_config.TextColumn("p-value",     help=_p_help),
                        "Sig": st.column_config.TextColumn(
                            "Sig",
                            help=(
                                "Significance stars derived from the p-value:\n"
                                "  ***  p < 0.001  (highly significant)\n"
                                "   **  p < 0.01\n"
                                "    *  p < 0.05   (conventionally significant)\n"
                                "    .  p < 0.10   (marginally significant)\n"
                                " (blank)  p ≥ 0.10  (not significant)\n\n"
                                "Blank also appears for inactive coefficients (Lasso/ElasticNet) "
                                "or when no p-value can be computed."
                            ),
                        ),
                    },
                )

                # ── Model statistics ─────────────────────────────────────────
                st.markdown(
                    '<p class="charts-label" style="margin-top:0.8rem;">Model Statistics</p>',
                    unsafe_allow_html=True,
                )
                s = result["stats"]

                # Primary metrics: 4 columns
                c1, c2, c3, c4 = st.columns(4)
                def _metric(col, label, value):
                    col.markdown(
                        f'<div class="model-stat-card">'
                        f'<div class="model-stat-label">{label}</div>'
                        f'<div class="model-stat-value">{value}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

                _metric(c1, "R²",        _fmt_float(s["r2"], 4))
                _metric(c2, "Adj. R²",   _fmt_float(s["adj_r2"], 4))
                _metric(c3, "RMSE",      _fmt_float(s["rmse"], 4))
                _metric(c4, "MAE",       _fmt_float(s["mae"], 4))

                # Secondary metrics table
                stat_rows = [
                    ("n observations",  f"{s['n_obs']:,}"),
                    ("n parameters",    f"{s['n_params']:,}"),
                    ("df residual",     f"{s['df_residual']:.2f}"),
                    ("F-statistic",     _fmt_float(s["f_stat"], 4)),
                    ("F p-value",       _fmt_pval(s["f_pval"])),
                    ("AIC",             _fmt_float(s["aic"], 4)),
                    ("BIC",             _fmt_float(s["bic"], 4)),
                ]

                # For tree models add SHAP base value and a complexity note
                if _is_tree:
                    bv = s.get("base_value")
                    stat_rows.insert(0, (
                        "SHAP base value",
                        _fmt_float(bv, 4) if bv is not None else "—",
                    ))
                    st.caption(
                        "ℹ️ **n parameters** = number of input features (lower bound on "
                        "tree complexity). F-statistic, AIC and BIC are approximations "
                        "based on this effective parameter count."
                    )

                stat_df = pd.DataFrame(stat_rows, columns=["Statistic", "Value"])
                st.dataframe(stat_df, use_container_width=True, hide_index=True)

                # ── Impactable Decomposition ──────────────────────────────────
                st.markdown(
                    '<p class="charts-label" style="margin-top:0.8rem;">'
                    "Impactable Decomposition"
                    "</p>",
                    unsafe_allow_html=True,
                )

                # Use all columns from full_df aligned to the model rows
                full_model_rows = full_df.loc[model_df.index]

                imp_df = _build_impactable_df(
                    result["coef_df"],
                    model_df,
                    full_model_rows,
                    target_col,
                    cfg,
                    is_tree=_is_tree,
                )

                if imp_df is None or imp_df.empty:
                    st.caption("No impactable data available.")
                else:
                    # Build the display note
                    _target_normed = any(
                        (n.get("column") == target_col and n.get("method") != "column")
                        or (n.get("method") == "column"
                            and target_col in n.get("params", {}).get("columns", []))
                        for n in cfg.get("normalizations", [])
                    )
                    _imp_notes: list[str] = []
                    if _is_tree:
                        _imp_notes.append(
                            "Tree model: coefficient = mean SHAP value; "
                            "impactable is an approximation."
                        )
                    if _target_normed:
                        _imp_notes.append(
                            f"Target (**{target_col}**) Tab 1 normalisation scale "
                            "applied uniformly to all contributions — "
                            "values are in original KPI units."
                        )
                    else:
                        _imp_notes.append(
                            "No Tab 1 normalisation detected for the target column — "
                            "contributions are in model scale."
                        )
                    st.caption("  ·  ".join(_imp_notes))

                    imp_display = imp_df.copy()
                    imp_display["Absolute Impactable"] = (
                        imp_df["Absolute Impactable"].map(lambda v: f"{v:,.4f}")
                    )
                    imp_display["Impactable %"] = imp_df["Impactable %"].map(
                        lambda v: f"{v:.2f}%" if not (isinstance(v, float) and np.isnan(v)) else "—"
                    )
                    st.dataframe(
                        imp_display,
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "Feature": st.column_config.TextColumn(
                                "Feature",
                                help="Input feature name.",
                            ),
                            "Absolute Impactable": st.column_config.TextColumn(
                                "Absolute Impactable",
                                help=(
                                    "Σ (β × feature_value × scale_y) across all observations, "
                                    "where scale_y is the inverse of the target column's "
                                    "Tab 1 normalisation (scale only, no offset). "
                                    "For tree models β = mean SHAP value. "
                                    "The intercept (or SHAP base value for trees) is "
                                    "treated as β × 1 per observation."
                                ),
                            ),
                            "Impactable %": st.column_config.TextColumn(
                                "Impactable %",
                                help=(
                                    "Absolute Impactable ÷ Total Denormed Target × 100. "
                                    "The sum of all rows ≈ 100 % for well-fitting models "
                                    "(since Σ ŷ ≈ Σ y when the model has an intercept). "
                                    "Represents this feature's share of total KPI."
                                ),
                            ),
                        },
                    )


# ════════════════════════════════════════════════════════════════════════════
#  MAIN
# ════════════════════════════════════════════════════════════════════════════

st.markdown("""
<div class="app-header">
  <div class="app-header-icon">📊</div>
  <div>
    <div class="app-header-title">MMM Tool</div>
    <div class="app-header-sub">Marketing Mix Modelling</div>
  </div>
  <div class="app-header-badge">Beta</div>
</div>
""", unsafe_allow_html=True)

nav_bar("top")

tab = st.session_state.current_tab
if tab == 0:
    tab_preprocessing()
elif tab == 1:
    tab_adstock()
elif tab == 2:
    tab_modelling()

nav_bar("bottom")
