"""Data transformation pipeline for the MMM preprocessing tab (Tab 1).

This module implements the five-step preprocessing pipeline that runs whenever
the user configures a transformation in Tab 1 of the MMM Tool.  Each step
corresponds to one of the numbered expanders in the UI:

  Step 1  — DateTime conversion   (② Convert to Datetime)
  Step 2  — Pivot                 (④ Pivot Dataset)
  Step 3  — Calculated columns    (⑤ Calculated Columns)
  Step 4  — Normalisation         (⑥ Normalise Columns)
  Step 5  — Sort                  (⑦ Sort Data)

All functions accept a raw DataFrame plus a configuration dict (or list) and
return a *new* DataFrame — the original is never mutated.

Design notes
------------
* Every individual step silently skips entries it cannot process (wrong
  column name, bad parameters, numeric conversion errors).  This allows
  the user to iteratively build up their pipeline without breaking the
  live preview.
* Groupby-aware steps (calculated lag/lead, normalisation) respect the
  ``groupby_columns`` key so that per-market or per-channel data is
  handled without contaminating groups.
"""

import pandas as pd
import numpy as np


# ─────────────────────────────── STEP 1 ─────────────────────────────────────

def apply_datetime_conversion(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Convert specified columns to pandas datetime dtype (Step 1).

    Columns are converted in-place (same column name, new dtype).  Conversion
    failures are silently ignored so that the rest of the pipeline can
    continue.

    Parameters
    ----------
    df : pd.DataFrame
        Input DataFrame (mutated in-place — call on a copy if immutability
        is required).
    config : dict
        Pipeline configuration dict.  Reads ``config["datetime_columns"]``,
        a list of column names to convert.

    Returns
    -------
    pd.DataFrame
        The same DataFrame object with datetime columns converted.
    """
    for col in config.get("datetime_columns", []):
        if col in df.columns:
            try:
                df[col] = pd.to_datetime(df[col])
            except Exception:
                # If conversion fails (e.g. mixed formats) leave the column as-is
                pass
    return df


# ─────────────────────────────── STEP 2 ─────────────────────────────────────

def apply_pivot(df: pd.DataFrame, pivot_cfg: dict) -> pd.DataFrame:
    """Pivot a long-format DataFrame to wide format (Step 2).

    Converts a DataFrame where one column contains category labels (header_col)
    and another contains the corresponding values (value_col) into a wide
    DataFrame where each unique category becomes its own column.

    This is equivalent to the standard "melt → pivot" workflow used when the
    raw data file stores channel spend in a long format like:

        date  | channel | spend
        ------+---------+------
        Jan   | TV      | 1000
        Jan   | Radio   | 500
        Feb   | TV      | 1200

    After pivoting by date (index), channel (header), spend (value) the result:

        date  | TV   | Radio
        ------+------+------
        Jan   | 1000 | 500
        Feb   | 1200 | NaN

    Parameters
    ----------
    df : pd.DataFrame
        Input DataFrame in long format.
    pivot_cfg : dict
        Pivot configuration with keys:
          - ``index_cols``  : columns to keep as rows (e.g. ["date", "region"]).
          - ``header_col``  : column whose values become new column headers.
          - ``value_col``   : column containing the values to fill cells.
          - ``aggfunc``     : aggregation function if there are duplicate (index,
                              header) combinations — default "sum".

    Returns
    -------
    pd.DataFrame
        Wide-format DataFrame.  Returns the original df unchanged if:
        - Any required key is missing or empty, or
        - Any referenced column is not found in df, or
        - The pivot operation raises an exception.
    """
    index_cols = pivot_cfg.get("index_cols", [])
    header_col = pivot_cfg.get("header_col")
    value_col = pivot_cfg.get("value_col")
    aggfunc = pivot_cfg.get("aggfunc", "sum")

    # Guard: all three of index_cols, header_col, value_col must be specified
    if not index_cols or not header_col or not value_col:
        return df

    # Guard: every referenced column must exist in the DataFrame
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

        # Flatten any MultiIndex columns that arise when aggfunc returns multiple
        # columns (e.g. aggfunc=["sum", "mean"]).  The single-aggfunc case
        # produces a simple Index with the header_col values as column names.
        if isinstance(pivoted.columns, pd.MultiIndex):
            # (level-0 = value_col name, level-1 = header category)
            # Use the category name alone; fall back to the value-col name if empty.
            pivoted.columns = [
                str(b) if b else str(a) for a, b in pivoted.columns
            ]
        else:
            pivoted.columns = [str(c) for c in pivoted.columns]

        # Remove the residual .name attribute that pivot_table sets on the columns
        pivoted.columns.name = None
        return pivoted
    except Exception:
        return df


# ─────────────────────────────── STEP 3 ─────────────────────────────────────

def apply_calculated_columns(
    df: pd.DataFrame, calc_list: list, groupby_cols: list
) -> pd.DataFrame:
    """Compute and append derived columns to the DataFrame (Step 3).

    Supports four calculation types that cover the most common MMM
    pre-processing needs:

    - **lag / lead** : shift a column forward or backward in time.
      Group-aware: shifting is performed within each group independently so
      that the last row of one group does not bleed into the first of the next.
    - **add**        : element-wise sum of two or more columns.
    - **multiply**   : element-wise product of two or more columns.
    - **multiply_scalar** : multiply a column by a fixed constant (e.g. to
      change units or apply an exchange-rate).

    Parameters
    ----------
    df : pd.DataFrame
        Input DataFrame (mutated in-place — call on a copy if needed).
    calc_list : list[dict]
        Each dict describes one calculated column:
          - ``name``   : new column name (str, required).
          - ``type``   : calculation type key (str, required).
          - ``params`` : type-specific parameter dict (see below).
    groupby_cols : list[str]
        Columns to group by for lag / lead operations.  Columns absent from df
        are filtered out silently.

    Returns
    -------
    pd.DataFrame
        Same DataFrame with new columns appended.
    """
    # Filter groupby columns to those that exist in df
    valid_grp = [c for c in groupby_cols if c in df.columns]

    for calc in calc_list:
        name = calc.get("name", "").strip()
        ctype = calc.get("type", "")
        params = calc.get("params", {})
        # Skip entries with missing name or type
        if not name or not ctype:
            continue

        try:
            if ctype in ("lag", "lead"):
                # Lag: positive shift (values move to later rows → history).
                # Lead: negative shift (values move to earlier rows → future).
                src = params.get("column")
                n = int(params.get("n", 1))
                shift = n if ctype == "lag" else -n
                if src and src in df.columns:
                    if valid_grp:
                        # Shift within each group so group boundaries are respected
                        df[name] = (
                            df.groupby(valid_grp)[src].shift(shift).fillna(0)
                        )
                    else:
                        df[name] = df[src].shift(shift).fillna(0)

            elif ctype == "add":
                # Sum all specified columns row-by-row (handles NaN via sum's
                # default skipna=True, which treats NaN as 0 in the sum)
                cols = [c for c in params.get("columns", []) if c in df.columns]
                if cols:
                    df[name] = df[cols].sum(axis=1)

            elif ctype == "multiply":
                # Element-wise product of two or more columns.
                # Requires at least 2 columns to be meaningful.
                cols = [c for c in params.get("columns", []) if c in df.columns]
                if len(cols) >= 2:
                    result = df[cols[0]].astype(float).copy()
                    for c in cols[1:]:
                        result = result * df[c].astype(float)
                    df[name] = result

            elif ctype == "multiply_scalar":
                # Multiply a single column by a fixed scalar constant.
                # Common use: unit conversion (e.g. thousands → actual, or
                # currency conversion).
                src = params.get("column")
                scalar = float(params.get("scalar", 1.0))
                if src and src in df.columns:
                    df[name] = df[src].astype(float) * scalar

        except Exception:
            # Swallow errors so the pipeline can continue with subsequent columns
            pass

    return df


# ─────────────────────────────── STEP 4 ─────────────────────────────────────

def apply_normalizations(
    df: pd.DataFrame, norm_list: list, groupby_cols: list
) -> pd.DataFrame:
    """Normalise columns according to user-defined rules (Step 4).

    Normalisation is applied **in-place** — the source column is overwritten
    with the normalised values (as float).  This differs from Tab 2's norm
    transform which creates a new column.

    Supported normalisation methods:

    - **minmax**   : scale to [0, 1] using the column's min/max.
    - **mean**     : divide by the mean (result has mean = 1).
    - **z-score**  : subtract mean, divide by std (result has mean = 0, std = 1).
    - **scalar**   : divide by a user-supplied constant.
    - **column**   : divide one or more columns by a separate divisor column.

    All methods except ``column`` can be applied group-aware (within each
    group defined by ``groupby_cols``).  The ``column`` method is always
    global (no grouping).

    Parameters
    ----------
    df : pd.DataFrame
        Input DataFrame (mutated in-place — call on a copy if needed).
    norm_list : list[dict]
        Each dict describes one normalisation rule:
          - ``method``  : normalisation method key.
          - ``column``  : source column (required for single-column methods).
          - ``params``  : method-specific parameters
                          (``scalar`` for "scalar"; ``columns`` + ``div_column``
                          for "column").
    groupby_cols : list[str]
        Columns to group by for group-aware normalisation.

    Returns
    -------
    pd.DataFrame
        Same DataFrame with normalised column values.
    """
    valid_grp = [c for c in groupby_cols if c in df.columns]

    for norm in norm_list:
        method = norm.get("method", "minmax")
        params = norm.get("params", {})

        try:
            # ── Column-division: overwrite each source ÷ divisor, no grouping ─
            # Divides a set of columns by a single divisor column element-wise.
            # Example: normalise all spend columns by total market size.
            if method == "column":
                sources = [c for c in params.get("columns", []) if c in df.columns]
                div_col = params.get("div_column")
                if div_col and div_col in df.columns and sources:
                    # Replace zero divisors with NaN so we get NaN rather than inf
                    divisor = df[div_col].astype(float).replace(0, np.nan)
                    for _src in sources:
                        df[_src] = (df[_src].astype(float) / divisor)
                continue  # Done with this norm entry

            # ── Standard single-column methods (overwrite in place) ───────────
            src = norm.get("column")
            if not src or src not in df.columns:
                continue  # Missing or unknown column — skip

            if method == "mean":
                # Divide by the group (or global) mean so the result has mean ≈ 1.
                # Replace mean = 0 with NaN to avoid division by zero.
                if valid_grp:
                    mu = df.groupby(valid_grp)[src].transform("mean").replace(0, np.nan)
                    df[src] = (df[src].astype(float) / mu)
                else:
                    mu = df[src].mean()
                    df[src] = (df[src].astype(float) / mu) if mu != 0 else df[src].astype(float)

            elif method == "z-score":
                # Standardise: (x − μ) / σ.  Sigma = 1 if constant column (σ = 0).
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
                # Scale to [0, 1] using the group-level (or global) min/max.
                # When min == max the range is replaced with 1 to avoid div-by-zero,
                # resulting in a constant column of 0.
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
                # Divide by a user-specified constant.  Scalar = 0 is skipped
                # (would produce infinite values).
                scalar = float(params.get("scalar", 1.0))
                if scalar != 0:
                    df[src] = (df[src].astype(float) / scalar)

        except Exception:
            pass

    return df


# ─────────────────────────────── STEP 5 ─────────────────────────────────────

def apply_sort(df: pd.DataFrame, sort_list: list) -> pd.DataFrame:
    """Sort the DataFrame by one or more columns (Step 5).

    Applies a multi-key sort in the order the keys appear in ``sort_list``.
    Each key can independently be ascending or descending.  The index is
    reset to a clean 0-based integer index after sorting.

    This step is important in MMM because adstock convolution in Tab 2 is
    time-series order-sensitive: if the data is not sorted chronologically
    (oldest → newest) the causal convolution will produce wrong results.

    Parameters
    ----------
    df : pd.DataFrame
        Input DataFrame.
    sort_list : list[dict]
        Each dict specifies one sort key:
          - ``column``    : column name to sort by.
          - ``ascending`` : bool, default True (↑ ascending / ↓ descending).

    Returns
    -------
    pd.DataFrame
        Sorted DataFrame with a reset integer index.  Returns the original
        df unchanged if sort_list is empty or contains no valid columns.
    """
    # Filter to only valid sort entries (column must exist in df)
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


# ─────────────────────── FULL PIPELINE ───────────────────────────────────────

def apply_all_transformations(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Run the complete Tab 1 preprocessing pipeline on df.

    Executes the five preprocessing steps in the order required for correctness:

      1. DateTime conversion  — must happen before date-based operations.
      2. Pivot               — reshapes the raw data before column operations.
      3. Calculated columns  — lag/lead depend on correct data shape and dtypes.
      4. Normalisation       — applied after calculated columns so derived cols
                               can also be normalised.
      5. Sort                — chronological ordering for Tab 2 adstock.

    Parameters
    ----------
    df : pd.DataFrame
        Raw input DataFrame (not mutated — a copy is made internally).
    config : dict
        Full session-state configuration dict.  Reads the following keys:
          - ``groupby_columns``    : list[str]
          - ``datetime_columns``   : list[str]
          - ``pivot``              : dict (see apply_pivot)
          - ``calculated_columns`` : list[dict]
          - ``normalizations``     : list[dict]
          - ``sort_config``        : list[dict]

    Returns
    -------
    pd.DataFrame | None
        Transformed DataFrame, or None if the input is None.
    """
    if df is None:
        return None

    # Always work on a copy to preserve the caller's original data
    df = df.copy()
    groupby_cols = config.get("groupby_columns", [])

    # Step 1: Convert datetime columns
    df = apply_datetime_conversion(df, config)

    # Step 2: Pivot if configured (only runs when header_col and value_col are set)
    pivot_cfg = config.get("pivot") or {}
    if pivot_cfg.get("header_col") and pivot_cfg.get("value_col"):
        df = apply_pivot(df, pivot_cfg)

    # Step 3: Append calculated columns (lag, lead, add, multiply, multiply_scalar)
    df = apply_calculated_columns(df, config.get("calculated_columns", []), groupby_cols)

    # Step 4: Normalise columns in-place (minmax, mean, z-score, scalar, column)
    df = apply_normalizations(df, config.get("normalizations", []), groupby_cols)

    # Step 5: Sort by user-defined key(s) — ensures time-series order for adstock
    df = apply_sort(df, config.get("sort_config", []))

    return df
