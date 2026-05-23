"""Data transformation pipeline for the MMM preprocessing tab."""
import pandas as pd
import numpy as np


# ─────────────────────────────── STEP 1 ─────────────────────────────────────

def apply_datetime_conversion(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    for col in config.get("datetime_columns", []):
        if col in df.columns:
            try:
                df[col] = pd.to_datetime(df[col])
            except Exception:
                pass
    return df


# ─────────────────────────────── STEP 2 ─────────────────────────────────────

def apply_pivot(df: pd.DataFrame, pivot_cfg: dict) -> pd.DataFrame:
    index_cols = pivot_cfg.get("index_cols", [])
    header_col = pivot_cfg.get("header_col")
    value_col = pivot_cfg.get("value_col")
    aggfunc = pivot_cfg.get("aggfunc", "sum")

    if not index_cols or not header_col or not value_col:
        return df
    missing = [c for c in index_cols + [header_col, value_col] if c not in df.columns]
    if missing:
        return df

    try:
        pivoted = df.pivot_table(
            index=index_cols,
            columns=header_col,
            values=value_col,
            aggfunc=aggfunc,
        ).reset_index()

        # Flatten any MultiIndex columns (happens with multiple value cols)
        if isinstance(pivoted.columns, pd.MultiIndex):
            pivoted.columns = [
                str(b) if b else str(a) for a, b in pivoted.columns
            ]
        else:
            pivoted.columns = [str(c) for c in pivoted.columns]

        pivoted.columns.name = None
        return pivoted
    except Exception:
        return df


# ─────────────────────────────── STEP 3 ─────────────────────────────────────

def apply_calculated_columns(
    df: pd.DataFrame, calc_list: list, groupby_cols: list
) -> pd.DataFrame:
    valid_grp = [c for c in groupby_cols if c in df.columns]

    for calc in calc_list:
        name = calc.get("name", "").strip()
        ctype = calc.get("type", "")
        params = calc.get("params", {})
        if not name or not ctype:
            continue

        try:
            if ctype in ("lag", "lead"):
                src = params.get("column")
                n = int(params.get("n", 1))
                shift = n if ctype == "lag" else -n
                if src and src in df.columns:
                    if valid_grp:
                        df[name] = (
                            df.groupby(valid_grp)[src].shift(shift).fillna(0)
                        )
                    else:
                        df[name] = df[src].shift(shift).fillna(0)

            elif ctype == "add":
                cols = [c for c in params.get("columns", []) if c in df.columns]
                if cols:
                    df[name] = df[cols].sum(axis=1)

            elif ctype == "multiply":
                cols = [c for c in params.get("columns", []) if c in df.columns]
                if len(cols) >= 2:
                    result = df[cols[0]].astype(float).copy()
                    for c in cols[1:]:
                        result = result * df[c].astype(float)
                    df[name] = result

            elif ctype == "multiply_scalar":
                src = params.get("column")
                scalar = float(params.get("scalar", 1.0))
                if src and src in df.columns:
                    df[name] = df[src].astype(float) * scalar

        except Exception:
            pass

    return df


# ─────────────────────────────── STEP 4 ─────────────────────────────────────

def apply_normalizations(
    df: pd.DataFrame, norm_list: list, groupby_cols: list
) -> pd.DataFrame:
    valid_grp = [c for c in groupby_cols if c in df.columns]

    for norm in norm_list:
        method = norm.get("method", "minmax")
        params = norm.get("params", {})

        try:
            # ── Column-division: overwrite each source ÷ divisor, no grouping ─
            if method == "column":
                sources = [c for c in params.get("columns", []) if c in df.columns]
                div_col = params.get("div_column")
                if div_col and div_col in df.columns and sources:
                    divisor = df[div_col].astype(float).replace(0, np.nan)
                    for _src in sources:
                        df[_src] = (df[_src].astype(float) / divisor)
                continue

            # ── Standard single-column methods (overwrite in place) ───────────
            src = norm.get("column")
            if not src or src not in df.columns:
                continue

            if method == "mean":
                if valid_grp:
                    mu = df.groupby(valid_grp)[src].transform("mean").replace(0, np.nan)
                    df[src] = (df[src].astype(float) / mu)
                else:
                    mu = df[src].mean()
                    df[src] = (df[src].astype(float) / mu) if mu != 0 else df[src].astype(float)

            elif method == "z-score":
                if valid_grp:
                    mu = df.groupby(valid_grp)[src].transform("mean")
                    sigma = (
                        df.groupby(valid_grp)[src].transform("std").fillna(1).replace(0, 1)
                    )
                    df[src] = ((df[src] - mu) / sigma).astype(float)
                else:
                    sigma = df[src].std()
                    sigma = sigma if sigma != 0 else 1
                    df[src] = ((df[src] - df[src].mean()) / sigma).astype(float)

            elif method == "minmax":
                if valid_grp:
                    mn = df.groupby(valid_grp)[src].transform("min")
                    mx = df.groupby(valid_grp)[src].transform("max")
                    rng = (mx - mn).replace(0, 1)
                    df[src] = ((df[src] - mn) / rng).astype(float)
                else:
                    mn, mx = df[src].min(), df[src].max()
                    rng = (mx - mn) if mx != mn else 1
                    df[src] = ((df[src] - mn) / rng).astype(float)

            elif method == "scalar":
                scalar = float(params.get("scalar", 1.0))
                if scalar != 0:
                    df[src] = (df[src].astype(float) / scalar)

        except Exception:
            pass

    return df


# ─────────────────────────────── STEP 5 ─────────────────────────────────────

def apply_sort(df: pd.DataFrame, sort_list: list) -> pd.DataFrame:
    valid = [s for s in sort_list if s.get("column") in df.columns]
    if not valid:
        return df
    try:
        cols = [s["column"] for s in valid]
        asc = [s.get("ascending", True) for s in valid]
        df = df.sort_values(by=cols, ascending=asc).reset_index(drop=True)
    except Exception:
        pass
    return df


# ─────────────────────────── FULL PIPELINE ───────────────────────────────────

def apply_all_transformations(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    if df is None:
        return None

    df = df.copy()
    groupby_cols = config.get("groupby_columns", [])

    df = apply_datetime_conversion(df, config)

    pivot_cfg = config.get("pivot") or {}
    if pivot_cfg.get("header_col") and pivot_cfg.get("value_col"):
        df = apply_pivot(df, pivot_cfg)

    df = apply_calculated_columns(df, config.get("calculated_columns", []), groupby_cols)
    df = apply_normalizations(df, config.get("normalizations", []), groupby_cols)
    df = apply_sort(df, config.get("sort_config", []))

    return df
