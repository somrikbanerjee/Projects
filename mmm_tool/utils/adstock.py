"""Adstock, saturation, and general signal transforms for MMM Tab 2.

Marketing Mix Modelling requires that advertising spend (or impressions) be
transformed before entering a regression model for two reasons:

1. **Adstock (carry-over):** Advertising has a delayed effect — an ad seen
   today may influence a purchase next week or next month.  Adstock transforms
   a raw spend series into a weighted average of current and past spend,
   where the weights represent the decay of advertising memory over time.

2. **Saturation:** Each additional pound of advertising has diminishing
   returns — doubling spend does not double response.  Saturation functions
   map the carry-over-adjusted spend to a concave response curve.

This module provides:
  - Three families of adstock weight functions (geometric, Weibull, Hill).
  - A causal convolution kernel that applies any weight vector to a 1-D signal.
  - A negative-exponential saturation function.
  - Column-naming conventions (which transforms create new columns vs. overwrite).
  - A single entry-point (``apply_tab2_transformations``) that executes the
    full ordered list of Tab 2 transforms on a DataFrame.
"""

import numpy as np
import pandas as pd


# ─────────────────────── ADSTOCK WEIGHT FUNCTIONS ────────────────────────────
# Each weight function returns an array of length (max_lag + 1) representing
# the relative contribution of spend at lag 0, 1, 2, … max_lag to the current
# period's effective exposure.  After computing the weights the array is used
# in a causal convolution (apply_adstock_1d) to transform the spend series.

def geometric_weights(max_lag: int, alpha: float) -> np.ndarray:
    """Return geometric decay weights: w[l] = alpha^l for l = 0 … max_lag.

    Geometric decay is the simplest adstock model: the carry-over effect from
    l periods ago is a constant fraction (alpha) of the effect from l−1
    periods ago.  When alpha = 0 there is no carry-over (only the current
    period matters); when alpha = 1 there is no decay at all.

    Parameters
    ----------
    max_lag : int
        Maximum number of past periods included in the convolution.
    alpha : float
        Decay rate in [0, 1).  Common MMM values are 0.3–0.8.

    Returns
    -------
    np.ndarray of shape (max_lag + 1,)
        Unnormalised weights (sum ≠ 1 in general).

    Examples
    --------
    >>> geometric_weights(3, 0.5)
    array([1.   , 0.5  , 0.25 , 0.125])
    """
    return np.array([alpha ** l for l in range(max_lag + 1)], dtype=float)


def weibull_weights(max_lag: int, shape: float, scale: float) -> np.ndarray:
    """Return Weibull PDF weights, normalised to sum to 1 (1-indexed lags).

    The Weibull distribution is more flexible than geometric decay — it can
    produce a peak delayed effect (shape > 1) or a very steep initial drop
    (shape < 1).  Lags are 1-indexed so the weight for lag l = 1 is the
    Weibull PDF evaluated at l = 1 (not 0).

    Parameters
    ----------
    max_lag : int
        Maximum number of past periods.  The returned array still has length
        max_lag + 1 to match the geometric convention (index 0 = current period).
    shape : float
        Weibull shape parameter (k > 0).  k < 1 → heavy early decay;
        k = 1 → exponential; k > 1 → hump-shaped carry-over pattern.
    scale : float
        Weibull scale parameter (λ > 0).  Larger values spread the carry-over
        over more periods.

    Returns
    -------
    np.ndarray of shape (max_lag + 1,)
        Weights normalised to sum to 1.  Falls back to uniform weights if the
        raw PDF sums to zero.
    """
    # Evaluate the Weibull PDF at each integer lag (1-indexed)
    lags = np.arange(1, max_lag + 2, dtype=float)
    w = (shape / scale) * ((lags / scale) ** (shape - 1)) * np.exp(-((lags / scale) ** shape))
    total = w.sum()
    # Normalise so weights sum to 1; fall back to uniform if total ≈ 0
    return (w / total) if total > 0 else np.ones(max_lag + 1) / (max_lag + 1)


def hill_weights(max_lag: int, alpha: float, gamma: float) -> np.ndarray:
    """Return Hill function weights f(l) = l^alpha / (l^alpha + gamma^alpha), normalised.

    The Hill (or S-curve) function is commonly used in pharmacokinetics and
    can model carry-over patterns that rise to a peak before decaying.  Here
    it is applied over discrete lags rather than continuous concentrations.

    Parameters
    ----------
    max_lag : int
        Maximum number of past periods.
    alpha : float
        Hill exponent (steepness parameter, > 0).  Large values → sharper
        sigmoid; values near 1 → approximately linear rise then plateau.
    gamma : float
        Half-saturation lag — the lag at which the weight is 50 % of its
        asymptote.  Larger gamma → peak at a later lag.

    Returns
    -------
    np.ndarray of shape (max_lag + 1,)
        Weights normalised to sum to 1.  Falls back to uniform weights if the
        raw sum is zero.
    """
    # Evaluate the Hill function at each integer lag (1-indexed)
    lags = np.arange(1, max_lag + 2, dtype=float)
    w = (lags ** alpha) / (lags ** alpha + gamma ** alpha)
    total = w.sum()
    return (w / total) if total > 0 else np.ones(max_lag + 1) / (max_lag + 1)


# ─────────────────────── CAUSAL CONVOLUTION ──────────────────────────────────

def apply_adstock_1d(x: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Apply adstock weights as a causal (one-sided) discrete convolution.

    For each time point t the output is the weighted sum of present and past
    values of x:

        y[t] = Σ_{l=0}^{max_lag} w[l] · x[t − l]

    The convolution is causal: only past observations (x[t], x[t-1], …) are
    used, never future values.  This ensures the model cannot "look ahead".
    Missing past periods at the start of the series (t < l) are simply not
    included, which is equivalent to assuming x = 0 before the series begins.

    Parameters
    ----------
    x : np.ndarray of shape (n,)
        Raw spend or impression series (1-D, numeric).
    weights : np.ndarray of shape (max_lag + 1,)
        Adstock weight vector, e.g. from geometric_weights().  weights[0]
        multiplies the current period x[t]; weights[1] multiplies x[t-1], etc.

    Returns
    -------
    np.ndarray of shape (n,)
        Carry-over-adjusted series y, same length as x.
    """
    n = len(x)
    y = np.zeros(n, dtype=float)
    for l, w in enumerate(weights):
        if l == 0:
            # Current period: add w[0] * x[t] for all t
            y += w * x.astype(float)
        else:
            # Lag l: add w[l] * x[t-l] for t >= l (earlier periods have no prior data)
            y[l:] += w * x[: n - l].astype(float)
    return y


# ─────────────────────── SATURATION ──────────────────────────────────────────

def neg_exp_saturation(x: np.ndarray, c: float, d: float) -> np.ndarray:
    """Apply negative-exponential (Michaelis-Menten style) saturation: f(x) = c · (1 − exp(−d · x)).

    This concave function models the diminishing-returns relationship between
    advertising exposure and consumer response:

    - At x = 0  →  f(x) = 0  (no spend, no response).
    - As x → ∞  →  f(x) → c  (response asymptotes at c, the theoretical maximum).
    - Curvature is controlled by d: large d means the curve saturates quickly.

    Parameters
    ----------
    x : np.ndarray
        Input series (post-adstock spend/impressions, ≥ 0 values expected).
    c : float
        Asymptote / maximum theoretical response.  Controls the vertical scale.
    d : float
        Curvature / decay rate (> 0).  Small d → shallow curve; large d → steep.

    Returns
    -------
    np.ndarray
        Saturated series with the same shape as x, values in [0, c).
    """
    return c * (1.0 - np.exp(-d * np.asarray(x, dtype=float)))


# ─────────────────────── OUTPUT COLUMN NAMING ────────────────────────────────
# MMM Tab 2 transforms fall into two categories:
#
#  1. Transforms that CREATE A NEW COLUMN (the source column is left intact):
#       adstock    → appends "_adstock"  (e.g. tv_spend → tv_spend_adstock)
#       saturation → appends "_saturation"
#       norm       → appends "_norm"
#
#  2. Transforms that OVERWRITE IN PLACE (the source column name is reused):
#       lag, lead, moving_avg, mean_center, zero_mask
#
# This distinction matters for the UI (showing the output column name) and for
# the transform pipeline (knowing which columns to pass downstream).

# Frozen set of transform type keys that produce a new column with a suffix.
# All other transform types modify the source column in-place.
CREATES_NEW_COLUMN: frozenset = frozenset({"adstock", "saturation", "norm"})


def build_output_col(source: str, ttype: str, params: dict) -> str:
    """Return the output column name for a transform.

    For adstock / saturation / norm: appends a suffix to source, creating a
    new column name.  The source column is left untouched in the DataFrame.

    For all other types (lag, lead, moving_avg, mean_center, zero_mask):
    returns ``source`` unchanged, indicating an in-place overwrite.

    Parameters
    ----------
    source : str
        Name of the source column (e.g. ``"tv_spend_adstock"``).
    ttype : str
        Transform type key (e.g. ``"adstock"``, ``"lag"``, ``"norm"``).
    params : dict
        Transform parameters (currently unused — reserved for future parameterised
        naming, e.g. a user-defined suffix).

    Returns
    -------
    str
        Output column name.  Same as ``source`` for in-place transforms.
    """
    if ttype == "adstock":
        return f"{source}_adstock"
    elif ttype == "saturation":
        return f"{source}_saturation"
    elif ttype == "norm":
        return f"{source}_norm"
    # lag, lead, moving_avg, mean_center, zero_mask → in-place, no suffix
    return source


# ─────────────────────── FULL TAB 2 PIPELINE ─────────────────────────────────

def apply_tab2_transformations(
    df: pd.DataFrame,
    transforms: list,
    groupby_cols: list,
    target_col: str | None,
) -> pd.DataFrame:
    """Apply all Tab 2 transforms in listed order, writing results back to df.

    This is the single entry-point called by both the Streamlit UI and the
    Auto-Fit worker to materialise the user's transform configuration.  It
    iterates the ``transforms`` list in order, dispatching each entry to the
    appropriate computation.

    Transform entries are dicts with the following mandatory keys:
      - ``source_col``  : column to read from (must exist in df).
      - ``type``        : one of the CREATES_NEW_COLUMN types or an in-place type.
      - ``params``      : dict of type-specific hyperparameters (see below).
      - ``output_col``  : column name to write the result to.

    Transforms that ``type in CREATES_NEW_COLUMN`` write to a new column;
    others overwrite the source column in-place.

    Groupby-aware transforms (norm, lag, lead, moving_avg, mean_center):
    operations are computed *within* each group defined by ``groupby_cols``
    when those columns are present in df.

    Parameters
    ----------
    df : pd.DataFrame
        Input DataFrame.  Copied internally so the original is not mutated.
    transforms : list[dict]
        Ordered list of transform specifications.  Invalid entries (missing
        keys, source column not in df) are silently skipped.
    groupby_cols : list[str]
        Column names to group by for group-aware transforms.  Columns not
        found in df are filtered out before use.
    target_col : str | None
        Name of the target (KPI) column — used only by the ``zero_mask``
        transform to identify rows where the target equals zero.

    Returns
    -------
    pd.DataFrame
        New DataFrame with transforms applied.  The original df is unchanged.

    Notes
    -----
    Exceptions within individual transform steps are silently caught and
    skipped so that a badly configured transform does not abort the whole
    pipeline.  This is intentional: the UI already validates params before
    storing them, and the Auto-Fit worker benefits from resilience.
    """
    if df is None or not transforms:
        return df

    # Work on a copy so we don't mutate the caller's DataFrame
    df = df.copy()
    # Filter groupby columns to those that actually exist in df
    valid_grp = [c for c in groupby_cols if c in df.columns]

    for t in transforms:
        src = t.get("source_col", "")
        ttype = t.get("type", "")
        params = t.get("params", {})
        out_col = t.get("output_col", "")

        # Skip entries with missing required fields or a missing source column
        if not src or not ttype or not out_col or src not in df.columns:
            continue

        try:
            # ── Adstock ──────────────────────────────────────────────────────
            # Builds the requested weight vector then applies causal convolution.
            if ttype == "adstock":
                method = params.get("method", "geometric")
                max_lag = max(1, int(params.get("max_lag", 4)))
                if method == "geometric":
                    w = geometric_weights(max_lag, float(params.get("alpha", 0.5)))
                elif method == "weibull":
                    w = weibull_weights(
                        max_lag,
                        float(params.get("shape", 2.0)),
                        float(params.get("scale", 2.0)),
                    )
                elif method == "hill":
                    w = hill_weights(
                        max_lag,
                        float(params.get("alpha", 2.0)),
                        float(params.get("gamma", 2.0)),
                    )
                else:
                    continue  # Unknown adstock method — skip silently
                # Apply the convolution and write to the (new) output column
                df[out_col] = apply_adstock_1d(df[src].astype(float).values, w)

            # ── Saturation ───────────────────────────────────────────────────
            # Applies the negative-exponential saturation curve element-wise.
            elif ttype == "saturation":
                c = float(params.get("c", 1.0))
                d = float(params.get("d", 0.001))
                df[out_col] = neg_exp_saturation(df[src].astype(float).values, c, d)

            # ── Normalisation (creates new column, group-aware) ──────────────
            # Supports minmax, mean-normalisation, and z-score.
            # When groupby columns are present the statistics are computed
            # within each group using pandas transform().
            elif ttype == "norm":
                method = params.get("method", "minmax")
                s = df[src].astype(float)
                if method == "minmax":
                    # Scale to [0, 1] within each group (or globally)
                    if valid_grp:
                        mn = df.groupby(valid_grp)[src].transform("min")
                        mx = df.groupby(valid_grp)[src].transform("max")
                        df[out_col] = ((s - mn) / (mx - mn).replace(0, 1)).astype(float)
                    else:
                        mn, mx = s.min(), s.max()
                        df[out_col] = ((s - mn) / ((mx - mn) if mx != mn else 1)).astype(float)
                elif method == "mean":
                    # Divide by the group (or global) mean
                    if valid_grp:
                        mu = df.groupby(valid_grp)[src].transform("mean").replace(0, np.nan)
                        df[out_col] = (s / mu).astype(float)
                    else:
                        mu = s.mean()
                        df[out_col] = (s / mu).astype(float) if mu != 0 else s.copy()
                elif method == "z-score":
                    # Standardise: (x − μ) / σ within each group (or globally)
                    if valid_grp:
                        mu = df.groupby(valid_grp)[src].transform("mean")
                        sigma = (
                            df.groupby(valid_grp)[src]
                            .transform("std")
                            .fillna(1)   # NaN std (single-element group) → 1
                            .replace(0, 1)  # zero std → 1 (avoid division by zero)
                        )
                        df[out_col] = ((s - mu) / sigma).astype(float)
                    else:
                        sigma = s.std()
                        sigma = sigma if sigma != 0 else 1
                        df[out_col] = ((s - s.mean()) / sigma).astype(float)

            # ── Lag ──────────────────────────────────────────────────────────
            # Shifts the series forward by n periods (values move to later rows).
            # Missing values at the start are filled with 0.
            elif ttype == "lag":
                n = int(params.get("n", 1))
                if valid_grp:
                    # Shift within each group independently to avoid
                    # bleeding the last row of one group into the first of the next
                    df[out_col] = df.groupby(valid_grp)[src].shift(n).fillna(0)
                else:
                    df[out_col] = df[src].shift(n).fillna(0)

            # ── Lead ─────────────────────────────────────────────────────────
            # Shifts the series backward by n periods (values move to earlier rows).
            # Missing values at the end are filled with 0.
            elif ttype == "lead":
                n = int(params.get("n", 1))
                if valid_grp:
                    df[out_col] = df.groupby(valid_grp)[src].shift(-n).fillna(0)
                else:
                    df[out_col] = df[src].shift(-n).fillna(0)

            # ── Moving Average ───────────────────────────────────────────────
            # Smooths the series with a trailing window of n periods.
            # min_periods=1 ensures non-NaN output even at the start of the series.
            elif ttype == "moving_avg":
                n = int(params.get("n", 3))
                if valid_grp:
                    df[out_col] = df.groupby(valid_grp)[src].transform(
                        lambda s: s.rolling(n, min_periods=1).mean()
                    )
                else:
                    df[out_col] = df[src].rolling(n, min_periods=1).mean()

            # ── Mean Centering ───────────────────────────────────────────────
            # Subtracts the group (or global) mean so the column has zero mean.
            # Useful before adstock / saturation to remove the level-shift effect.
            elif ttype == "mean_center":
                if valid_grp:
                    mu = df.groupby(valid_grp)[src].transform("mean")
                else:
                    mu = df[src].mean()
                df[out_col] = (df[src].astype(float) - mu).astype(float)

            # ── Zero Mask (set values to 0 where target = 0) ─────────────────
            # Forces feature values to 0 in periods where the KPI is zero.
            # Useful for excluding "dark" periods (e.g. channel paused while
            # the KPI happened to be zero) from the model.
            elif ttype == "zero_mask":
                out = df[src].astype(float).copy()
                if target_col and target_col in df.columns:
                    out[df[target_col] == 0] = 0.0
                df[out_col] = out

        except Exception:
            # Individual transform failures are swallowed to keep the pipeline
            # running.  The UI validates inputs before adding them; this guard
            # mainly protects the Auto-Fit random-search loop.
            pass

    return df
