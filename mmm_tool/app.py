"""MMM Tool — Streamlit web application."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO

from utils.preprocessing import apply_all_transformations
from utils.charts import make_input_target_charts

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
/* Remove Streamlit chrome — header bar, footer bar, deploy button */
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
/* Remove the top gap Streamlit reserves for its header bar */
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
</style>
""", unsafe_allow_html=True)

TABS = ["Data Preprocessing", "Adstock & Saturation"]
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

def get_processed_df() -> pd.DataFrame | None:
    if st.session_state.df_original is None:
        return None
    return apply_all_transformations(
        st.session_state.df_original.copy(),
        st.session_state.config,
    )

def wk(base: str) -> str:
    return f"{base}_e{st.session_state.widget_epoch}"

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
            df = get_processed_df()
            return list(df.columns) if df is not None else raw_cols

        def cur_df_now():
            return get_processed_df()

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

            # Selectbox OUTSIDE the form so changing it immediately rerenders the fields
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

            # Method selectbox OUTSIDE the form so it immediately swaps the fields on change
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
        cur_df = get_processed_df()
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
    cur_df = get_processed_df()
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
#  TAB 2 — ADSTOCK & SATURATION  (placeholder)
# ════════════════════════════════════════════════════════════════════════════

def tab_adstock() -> None:
    st.title("Adstock & Saturation")
    st.info(
        "🚧  This tab is under construction. "
        "Adstock decay and saturation curve transformations will be configured here."
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

nav_bar("bottom")
