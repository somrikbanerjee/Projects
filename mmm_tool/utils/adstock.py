"""Adstock, saturation, and general signal transforms for MMM Tab 2."""
import numpy as np
import pandas as pd


# ─────────────────────── ADSTOCK WEIGHT FUNCTIONS ────────────────────────────

def geometric_weights(max_lag: int, alpha: float) -> np.ndarray:
    """Geometric decay: w[l] = alpha^l for l = 0..max_lag."""
    return np.array([alpha ** l for l in range(max_lag + 1)], dtype=float)


def weibull_weights(max_lag: int, shape: float, scale: float) -> np.ndarray:
    """Weibull PDF weights, normalised to sum to 1 (1-indexed lags)."""
    lags = np.arange(1, max_lag + 2, dtype=float)
    w = (shape / scale) * ((lags / scale) ** (shape - 1)) * np.exp(-((lags / scale) ** shape))
    total = w.sum()
    return (w / total) if total > 0 else np.ones(max_lag + 1) / (max_lag + 1)


def hill_weights(max_lag: int, alpha: float, gamma: float) -> np.ndarray:
    """Hill function weights f(l) = l^alpha / (l^alpha + gamma^alpha), normalised."""
    lags = np.arange(1, max_lag + 2, dtype=float)
    w = (lags ** alpha) / (lags ** alpha + gamma ** alpha)
    total = w.sum()
    return (w / total) if total > 0 else np.ones(max_lag + 1) / (max_lag + 1)


# ─────────────────────── CAUSAL CONVOLUTION ──────────────────────────────────

def apply_adstock_1d(x: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """y[t] = Σ w[l] · x[t−l], causal, capped at max_lag = len(weights)−1."""
    n = len(x)
    y = np.zeros(n, dtype=float)
    for l, w in enumerate(weights):
        if l == 0:
            y += w * x.astype(float)
        else:
            y[l:] += w * x[: n - l].astype(float)
    return y


# ─────────────────────── SATURATION ──────────────────────────────────────────

def neg_exp_saturation(x: np.ndarray, c: float, d: float) -> np.ndarray:
    """Negative-exponential saturation: f(x) = c · (1 − exp(−d · x))."""
    return c * (1.0 - np.exp(-d * np.asarray(x, dtype=float)))


# ─────────────────────── OUTPUT COLUMN NAMING ────────────────────────────────

# These transforms produce a new column with a suffix.
# All other transforms (lag, lead, moving_avg, mean_center, zero_mask)
# overwrite the source column in place — no new column, no suffix.
CREATES_NEW_COLUMN: frozenset = frozenset({"adstock", "saturation", "norm"})


def build_output_col(source: str, ttype: str, params: dict) -> str:
    """Return output column name.

    For adstock / saturation / norm: appends a suffix (new column).
    For all other types: returns ``source`` unchanged (overwrite in place).
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
    """Apply all Tab 2 transforms in listed order, creating new output columns."""
    if df is None or not transforms:
        return df

    df = df.copy()
    valid_grp = [c for c in groupby_cols if c in df.columns]

    for t in transforms:
        src = t.get("source_col", "")
        ttype = t.get("type", "")
        params = t.get("params", {})
        out_col = t.get("output_col", "")

        if not src or not ttype or not out_col or src not in df.columns:
            continue

        try:
            # ── Adstock ──────────────────────────────────────────────────────
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
                    continue
                df[out_col] = apply_adstock_1d(df[src].astype(float).values, w)

            # ── Saturation ───────────────────────────────────────────────────
            elif ttype == "saturation":
                c = float(params.get("c", 1.0))
                d = float(params.get("d", 0.001))
                df[out_col] = neg_exp_saturation(df[src].astype(float).values, c, d)

            # ── Normalisation (creates new column, group-aware) ──────────────
            elif ttype == "norm":
                method = params.get("method", "minmax")
                s = df[src].astype(float)
                if method == "minmax":
                    if valid_grp:
                        mn = df.groupby(valid_grp)[src].transform("min")
                        mx = df.groupby(valid_grp)[src].transform("max")
                        df[out_col] = ((s - mn) / (mx - mn).replace(0, 1)).astype(float)
                    else:
                        mn, mx = s.min(), s.max()
                        df[out_col] = ((s - mn) / ((mx - mn) if mx != mn else 1)).astype(float)
                elif method == "mean":
                    if valid_grp:
                        mu = df.groupby(valid_grp)[src].transform("mean").replace(0, np.nan)
                        df[out_col] = (s / mu).astype(float)
                    else:
                        mu = s.mean()
                        df[out_col] = (s / mu).astype(float) if mu != 0 else s.copy()
                elif method == "z-score":
                    if valid_grp:
                        mu = df.groupby(valid_grp)[src].transform("mean")
                        sigma = (
                            df.groupby(valid_grp)[src]
                            .transform("std")
                            .fillna(1)
                            .replace(0, 1)
                        )
                        df[out_col] = ((s - mu) / sigma).astype(float)
                    else:
                        sigma = s.std()
                        sigma = sigma if sigma != 0 else 1
                        df[out_col] = ((s - s.mean()) / sigma).astype(float)

            # ── Lag ──────────────────────────────────────────────────────────
            elif ttype == "lag":
                n = int(params.get("n", 1))
                if valid_grp:
                    df[out_col] = df.groupby(valid_grp)[src].shift(n).fillna(0)
                else:
                    df[out_col] = df[src].shift(n).fillna(0)

            # ── Lead ─────────────────────────────────────────────────────────
            elif ttype == "lead":
                n = int(params.get("n", 1))
                if valid_grp:
                    df[out_col] = df.groupby(valid_grp)[src].shift(-n).fillna(0)
                else:
                    df[out_col] = df[src].shift(-n).fillna(0)

            # ── Moving Average ───────────────────────────────────────────────
            elif ttype == "moving_avg":
                n = int(params.get("n", 3))
                if valid_grp:
                    df[out_col] = df.groupby(valid_grp)[src].transform(
                        lambda s: s.rolling(n, min_periods=1).mean()
                    )
                else:
                    df[out_col] = df[src].rolling(n, min_periods=1).mean()

            # ── Mean Centering ───────────────────────────────────────────────
            elif ttype == "mean_center":
                if valid_grp:
                    mu = df.groupby(valid_grp)[src].transform("mean")
                else:
                    mu = df[src].mean()
                df[out_col] = (df[src].astype(float) - mu).astype(float)

            # ── Zero Mask (set values to 0 where target = 0) ─────────────────
            elif ttype == "zero_mask":
                out = df[src].astype(float).copy()
                if target_col and target_col in df.columns:
                    out[df[target_col] == 0] = 0.0
                df[out_col] = out

        except Exception:
            pass

    return df
