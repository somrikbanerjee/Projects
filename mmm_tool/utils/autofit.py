"""Auto-Fit: random search over MMM transformation pipelines.

Algorithm
---------
Random search (Bergstra & Bengio, JMLR 2012) is used because the combined
space of feature subsets × transform combinations × model hyperparameters is
astronomical.  Each iteration independently samples:

  1. A random subset of the input columns.
  2. Per-column transform chain (fixed order):
       Moving Average → Mean Centering → Lag
       → Adstock*  → Normalisation*  → Saturation*   (* = media channels only)
       → Zero Mask
  3. ALL available model types (Linear, Ridge, Lasso, ElasticNet, Random
     Forest, XGBoost).  Positivity is enforced for linear models during
     fitting; for tree models the constraint flags are stored in params so
     the final refit can apply post-hoc SHAP clipping.
  4. Model-specific hyperparameters from log-uniform / uniform distributions.

After the random search, the best pipeline is refit once with full inference
(including TreeSHAP for tree models) via utils.modelling.fit_model so that
Tab 3 can display the complete result.

Before each model fit, the data is additionally trimmed to the last 12
calendar months (or all rows if no datetime column is available) so that the
model is evaluated on recent data only.

The search runs in a daemon background thread so the Streamlit UI remains
responsive and a Cancel button can interrupt it mid-run.

Threading model
---------------
``start_autofit()`` spawns a daemon thread that writes to a shared mutable
dict stored in the module-level ``_TASKS`` registry.  The Streamlit UI polls
this dict on each rerun (every ~0.5 s while a task is running) by calling
``get_task(task_id)``.  No locks are used; updates from the worker thread are
atomic enough for Python's GIL to keep the UI reads consistent.
"""
from __future__ import annotations

import threading
import time
from typing import Callable

import numpy as np
import pandas as pd
from scipy import stats as _scipy_stats

from utils.adstock import apply_tab2_transformations
from utils.modelling import fit_model


# ─────────────────────────────── CONSTANTS ────────────────────────────────────

# Human-readable labels for each optimisation metric, shown in the UI
METRIC_LABELS: dict[str, str] = {
    "r2":     "R²",
    "adj_r2": "Adj. R²",
    "rmse":   "RMSE",
    "mae":    "MAE",
    "aic":    "AIC",
    "bic":    "BIC",
}

# Metrics for which a HIGHER value is better.
# All other metrics (RMSE, MAE, AIC, BIC) are "lower is better" and are
# negated by _to_score() so the search always maximises the score.
_METRIC_HIGHER: frozenset = frozenset({"r2", "adj_r2"})


# ─────────────────────────────── TASK REGISTRY ────────────────────────────────
# Module-level dict — persists for the lifetime of the Streamlit server process.
# Keys are task_id strings (UUID4); values are mutable state dicts written by
# the worker thread and read by the UI polling loop.
#
# State dict schema:
#   status       : str  — "running" | "refitting" | "complete" | "no_result" | "cancelled"
#   progress     : float — fraction of iterations completed, 0.0–1.0
#   elapsed      : float — wall-clock seconds since task start
#   eta          : float — estimated seconds remaining
#   iter         : int   — last completed iteration index (1-based)
#   cancel       : bool  — set True by cancel_task() to signal the worker to stop
#   done         : bool  — True once the worker has exited its main loop
#   result       : dict | None — best_config dict (set on completion)
#   error        : str | None  — exception message if the worker crashed
#   best_score   : float — best metric value seen so far (for live display)
#   best_config  : dict | None — best config seen so far (for live display)

_TASKS: dict[str, dict] = {}


def get_task(task_id: str) -> dict | None:
    """Look up a running or completed task by its ID.

    Parameters
    ----------
    task_id : str
        UUID4 string returned by / passed to ``start_autofit()``.

    Returns
    -------
    dict | None
        The mutable task state dict, or None if the task_id is unknown.
    """
    return _TASKS.get(task_id)


def cancel_task(task_id: str) -> None:
    """Signal the worker thread to stop at its next iteration boundary.

    Sets ``task["cancel"] = True`` in the task state dict.  The worker checks
    this flag at the top of each iteration and exits cleanly when it is set.

    Parameters
    ----------
    task_id : str
        ID of the task to cancel.
    """
    if task_id in _TASKS:
        _TASKS[task_id]["cancel"] = True


def cleanup_task(task_id: str) -> None:
    """Remove a task from the registry, freeing its memory.

    Should be called by the UI after a task completes, cancels, or errors so
    that the module-level dict does not grow unboundedly across long sessions.

    Parameters
    ----------
    task_id : str
        ID of the task to remove.
    """
    _TASKS.pop(task_id, None)


# ─────────────────────────────── DATA HELPERS ─────────────────────────────────

def _apply_date_filter(df: pd.DataFrame, date_cfg: dict) -> pd.DataFrame:
    """Apply the user's Tab 2 date-range filter to a DataFrame.

    Mirrors the date-filter logic in ``get_processed_df()`` in app.py.  The
    Auto-Fit worker uses this to apply the same window the user has configured
    in the UI before fitting each candidate model.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame to filter.
    date_cfg : dict
        Date filter configuration with keys:
          - ``col``      : name of the date column.
          - ``min_date`` : start date (datetime.date).
          - ``max_date`` : end date (datetime.date).

    Returns
    -------
    pd.DataFrame
        Filtered DataFrame (reset index).  Returns df unchanged if date_cfg is
        incomplete or if the date column is not found.
    """
    if not (date_cfg.get("col") and date_cfg.get("min_date") is not None
            and date_cfg.get("max_date") is not None):
        return df
    col = date_cfg["col"]
    if col not in df.columns:
        return df
    try:
        dt   = pd.to_datetime(df[col])
        mask = (dt.dt.date >= date_cfg["min_date"]) & (dt.dt.date <= date_cfg["max_date"])
        return df[mask].reset_index(drop=True)
    except Exception:
        return df


def _last_n_months(df: pd.DataFrame, date_col: str | None, n: int = 12) -> pd.DataFrame:
    """Subset df to the last n calendar months relative to the most recent date.

    Auto-Fit evaluates each candidate on recent data only (last 12 months by
    default) so that the model is not dominated by old patterns.  This is
    applied *after* transforms so adstock carry-over from older periods is
    still correctly computed over the full history.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame to trim.
    date_col : str | None
        Name of the date column.  If None or not found, returns df unchanged.
    n : int
        Number of calendar months to keep (default 12).

    Returns
    -------
    pd.DataFrame
        Rows whose date falls strictly after (max_date − n months), reset index.
        Falls back to the full df if the date column is missing or invalid.
    """
    if not date_col or date_col not in df.columns:
        return df
    try:
        dt     = pd.to_datetime(df[date_col])
        max_dt = dt.max()
        cutoff = max_dt - pd.DateOffset(months=n)
        # Strictly after the cutoff (so the boundary month is excluded)
        return df[dt > cutoff].reset_index(drop=True)
    except Exception:
        return df


# ─────────────────────────────── METRIC HELPERS ───────────────────────────────

def _compute_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    n_params: int,
) -> dict:
    """Compute regression fit metrics from raw predictions (lightweight, no SHAP).

    Used during the random search iterations where speed is critical.  Avoids
    the full fit_model inference path (which calls TreeSHAP) in favour of a
    direct numpy implementation.

    Parameters
    ----------
    y_true : np.ndarray of shape (n,)
        Observed target values.
    y_pred : np.ndarray of shape (n,)
        Model predictions.
    n_params : int
        Total number of estimated parameters (used for Adj. R², AIC, BIC).

    Returns
    -------
    dict with keys: ``r2``, ``adj_r2``, ``rmse``, ``mae``, ``aic``, ``bic``
    """
    n   = len(y_true)
    res = y_true - y_pred
    rss = float(np.sum(res ** 2))
    tss = float(np.sum((y_true - y_true.mean()) ** 2))

    r2     = (1.0 - rss / tss) if tss > 0 else np.nan
    df_res = max(n - n_params, 1)
    adj_r2 = (1.0 - (1.0 - r2) * (n - 1) / df_res) if tss > 0 else np.nan
    rmse   = float(np.sqrt(rss / n))
    mae    = float(np.mean(np.abs(res)))

    # Information-theoretic criteria via Gaussian log-likelihood
    if rss > 0:
        log_lik = -0.5 * n * (np.log(rss / n) + 1.0 + np.log(2.0 * np.pi))
        aic = float(-2.0 * log_lik + 2.0 * n_params)
        bic = float(-2.0 * log_lik + np.log(n) * n_params)
    else:
        aic = bic = np.nan

    return {"r2": r2, "adj_r2": adj_r2, "rmse": rmse, "mae": mae,
            "aic": aic, "bic": bic}


def _to_score(metrics: dict, metric: str) -> float:
    """Normalise a metric value to a "higher is always better" score.

    Metrics in ``_METRIC_HIGHER`` (R², Adj. R²) are returned as-is.
    All other metrics (RMSE, MAE, AIC, BIC) are negated so maximising the
    score is equivalent to minimising those error/information metrics.

    Parameters
    ----------
    metrics : dict
        Metric dict returned by ``_compute_metrics()``.
    metric : str
        Metric key to extract and normalise.

    Returns
    -------
    float
        Normalised score: higher is always better.
        Returns ``-inf`` if the metric value is NaN or missing.
    """
    v = metrics.get(metric.lower(), np.nan)
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return -np.inf
    return float(v) if metric in _METRIC_HIGHER else -float(v)


# ─────────────────────────── P-VALUE CONSTRAINT CHECK ─────────────────────────

def _pvals_ok(
    mdl,
    model_type: str,
    X_arr: np.ndarray,
    y_arr: np.ndarray,
    max_pval: float,
) -> bool:
    """Return True if every non-NaN feature p-value is ≤ max_pval.

    When the user sets a maximum p-value constraint in Auto-Fit, each candidate
    configuration is tested here before being admitted as a valid solution.
    The inference method used during the search matches what ``fit_model()``
    will use in the final refit, so the check is consistent with what Tab 3
    will ultimately display.

    Inference methods by model type:
      Ridge            → sandwich covariance  (Cov(β) ≈ σ² (X'X+αI)⁻¹ X'X (X'X+αI)⁻¹)
      Linear / Lasso / ElasticNet → active-set OLS on non-zero support
      Tree models      → TreeSHAP t-test: H₀: mean(SHAP) = 0, df = n−1

    Parameters
    ----------
    mdl
        Fitted scikit-learn compatible model.
    model_type : str
        Model type key (same values as fit_model()).
    X_arr : np.ndarray of shape (n, k)
        Feature matrix.
    y_arr : np.ndarray of shape (n,)
        Target vector.
    max_pval : float
        Maximum allowed p-value for any feature.

    Returns
    -------
    bool
        True → all feature p-values ≤ max_pval (or max_pval ≥ 1.0, which
        disables the constraint).
        On any exception the function returns True (accept the candidate) so
        that SHAP unavailability never silently prunes all tree models.
    """
    if max_pval >= 1.0:
        return True   # Constraint disabled — accept all candidates
    try:
        n, k = X_arr.shape

        # ── Tree models ──────────────────────────────────────────────────────
        # Use the TreeSHAP t-test: t = mean_SHAP / (std_SHAP / √n)
        if model_type in ("randomforest", "xgboost"):
            try:
                import shap as _shap
                exp     = _shap.TreeExplainer(mdl)
                sv      = np.array(exp.shap_values(X_arr), dtype=float)  # (n, k)
                mean_sv = sv.mean(axis=0)
                std_sv  = sv.std(axis=0, ddof=1)
                se      = np.where(std_sv > 1e-12, std_sv / np.sqrt(n), np.nan)
                with np.errstate(invalid="ignore", divide="ignore"):
                    t_vals = mean_sv / se
                    p_vals = 2.0 * _scipy_stats.t.sf(np.abs(t_vals), df=float(n - 1))
                valid_p = p_vals[~np.isnan(p_vals)]
                return bool((valid_p <= max_pval).all()) if len(valid_p) > 0 else True
            except Exception:
                return True   # SHAP unavailable → accept candidate without p-value check

        beta = np.asarray(mdl.coef_).ravel()
        ic   = float(np.atleast_1d(mdl.intercept_)[0])
        fi   = getattr(mdl, "fit_intercept", True)

        # ── Ridge — sandwich covariance (mirrors _ridge_inference) ────────────
        if model_type == "ridge":
            alpha_val = float(getattr(mdl, "alpha", 1.0))
            residuals = y_arr - (X_arr @ beta + ic if fi else X_arr @ beta)
            XtX       = X_arr.T @ X_arr
            A         = XtX + alpha_val * np.eye(k)
            A_inv     = np.linalg.pinv(A)
            df_fit    = float(np.trace(XtX @ A_inv)) + (1.0 if fi else 0.0)
            df_res    = max(n - df_fit, 1.0)
            s2        = float(np.sum(residuals ** 2) / df_res)
            cov       = s2 * A_inv @ XtX @ A_inv
            se_coef   = np.sqrt(np.maximum(np.diag(cov), 0.0))
            with np.errstate(invalid="ignore", divide="ignore"):
                t_vals = beta / se_coef
                p_vals = 2.0 * _scipy_stats.t.sf(np.abs(t_vals), df_res)
            valid_p = p_vals[~np.isnan(p_vals)]
            return bool((valid_p <= max_pval).all()) if len(valid_p) > 0 else True

        # ── Linear / Lasso / ElasticNet — active-set OLS ─────────────────────
        # Augment with intercept column if needed, then limit to active (non-zero) params.
        if fi:
            X_aug = np.column_stack([np.ones(n), X_arr])
            b     = np.concatenate([[ic], beta])
        else:
            X_aug = X_arr
            b     = beta

        active = np.abs(b) > 1e-12
        if not active.any():
            return True   # All coefficients zero → vacuously satisfied

        X_act = X_aug[:, active]
        b_act = b[active]

        residuals = y_arr - X_aug @ b
        df_res    = max(n - int(active.sum()), 1)
        s2        = float(np.sum(residuals ** 2) / df_res)
        XtX_inv   = np.linalg.pinv(X_act.T @ X_act)
        se        = np.sqrt(np.maximum(s2 * np.diag(XtX_inv), 0.0))

        with np.errstate(invalid="ignore", divide="ignore"):
            t_vals = b_act / se
            p_vals = 2.0 * _scipy_stats.t.sf(np.abs(t_vals), df_res)

        valid_p = p_vals[~np.isnan(p_vals)]
        return bool((valid_p <= max_pval).all()) if len(valid_p) > 0 else True

    except Exception:
        return True   # On any unexpected error accept the candidate


# ─────────────────────────────── TRANSFORM SAMPLING ──────────────────────────

def _sample_col_transforms(
    col: str,
    is_media: bool,
    has_target_zeros: bool,
    rng: np.random.Generator,
) -> tuple[list[dict], str]:
    """Sample a random transform chain for one column.

    Transforms are applied in a fixed order that respects the causal and
    statistical dependencies between steps:

      1. Moving Average  — smoothing before adstock; optional for all columns.
      2. Mean Centering  — remove the level before lagging; optional.
      3. Lag             — shift in time before adstock carry-over.
      4. Adstock         — carry-over model; media columns only.
      5. Normalisation   — scale after adstock so regression coefficients are
                           comparable; media columns only.
      6. Saturation      — diminishing returns; only after adstock (not raw spend).
      7. Zero Mask       — zero out periods where the KPI is zero; optional.

    Probabilities are tuned heuristically for typical weekly / monthly MMM
    datasets:
      - MA and lag are included in roughly 1/3 of iterations.
      - Adstock is included 60 % of the time for media (the main MMM transform).
      - Saturation follows adstock 40 % of the time (requires adstock first).
      - Zero mask is applied 30 % of the time when the KPI has zero periods.

    Parameters
    ----------
    col : str
        Source column name.
    is_media : bool
        Whether this column is a declared media / paid channel.  Adstock,
        normalisation, and saturation are only applied to media columns.
    has_target_zeros : bool
        Whether the target column contains any zeros.  Zero mask is only
        sampled when True (meaningless otherwise).
    rng : np.random.Generator
        Seeded NumPy random number generator for reproducibility.

    Returns
    -------
    tuple[list[dict], str]
        (transform_list, final_column_name)
        ``transform_list`` — flat list of transform dicts for
                             apply_tab2_transformations().
        ``final_column_name`` — the column name after all transforms are applied
                                 (may differ from ``col`` when adstock/norm/saturation
                                 creates new columns with suffixes).
    """
    T:   list[dict] = []   # Accumulated transform dicts
    cur: str        = col  # Tracks the current output column name

    # 1 · Moving Average (in-place, group-aware) ───────────────────────────────
    # Applied before adstock to smooth noisy weekly spend data.
    if rng.random() < 0.35:
        win = int(rng.choice([2, 3, 4, 6, 12]))
        T.append({"source_col": cur, "type": "moving_avg",
                  "params": {"n": win}, "output_col": cur})

    # 2 · Mean Centering (in-place, group-aware) ───────────────────────────────
    # Removes the series mean so the lag transform doesn't introduce a step.
    if rng.random() < 0.25:
        T.append({"source_col": cur, "type": "mean_center",
                  "params": {}, "output_col": cur})

    # 3 · Lag (in-place, group-aware) ──────────────────────────────────────────
    # Models the delayed response of a predictor (e.g. competitor price last month).
    if rng.random() < 0.35:
        n_lag = int(rng.choice([1, 2, 3, 4]))
        T.append({"source_col": cur, "type": "lag",
                  "params": {"n": n_lag}, "output_col": cur})

    # 4 · Adstock — media only (creates new column) ────────────────────────────
    # Carry-over model: spend today continues to influence sales in future periods.
    if is_media and rng.random() < 0.60:
        method  = str(rng.choice(["geometric", "weibull", "hill"]))
        max_lag = int(rng.choice([2, 4, 6, 8, 12]))
        p: dict = {"method": method, "max_lag": max_lag}
        # Sample method-specific parameters
        if method == "geometric":
            p["alpha"] = float(rng.uniform(0.1, 0.9))
        elif method == "weibull":
            p["shape"] = float(rng.uniform(0.5, 5.0))
            p["scale"] = float(rng.uniform(0.5, 5.0))
        else:  # hill
            p["alpha"] = float(rng.uniform(0.5, 5.0))
            p["gamma"] = float(rng.uniform(0.5, 5.0))
        out = f"{cur}_adstock"
        T.append({"source_col": cur, "type": "adstock",
                  "params": p, "output_col": out})
        cur = out   # Future transforms operate on the adstock column

    # 5 · Norm — media only (creates new column) ───────────────────────────────
    # Scales the adstock series so coefficients across channels are comparable.
    if is_media and rng.random() < 0.50:
        method = str(rng.choice(["minmax", "mean", "z-score"]))
        out    = f"{cur}_norm"
        T.append({"source_col": cur, "type": "norm",
                  "params": {"method": method}, "output_col": out})
        cur = out

    # 6 · Saturation — media only, and only when adstock already applied ────────
    # Saturation on raw (non-adstocked) spend is not meaningful in MMM because
    # the spend spike in a single period doesn't represent true cumulative exposure.
    if is_media and cur.endswith("_adstock") and rng.random() < 0.40:
        c_val = float(rng.uniform(0.5, 2.0))
        d_val = float(10 ** rng.uniform(-4, -1))   # log-uniform 0.0001–0.1
        out   = f"{cur}_saturation"
        T.append({"source_col": cur, "type": "saturation",
                  "params": {"c": c_val, "d": d_val}, "output_col": out})
        cur = out

    # 7 · Zero Mask (in-place) ─────────────────────────────────────────────────
    # Forces feature values to 0 where the KPI is also 0 — useful for "dark"
    # periods (channel spend recorded but no KPI activity, e.g. store closures).
    if has_target_zeros and rng.random() < 0.30:
        T.append({"source_col": cur, "type": "zero_mask",
                  "params": {}, "output_col": cur})

    return T, cur


# ─────────────────────────────── MULTI-MODEL FAST FIT ─────────────────────────

# All model types considered during the Auto-Fit search
_ALL_MODEL_TYPES: frozenset = frozenset(
    {"linear", "ridge", "lasso", "elasticnet", "randomforest", "xgboost"}
)


def _try_all_models(
    X_arr: np.ndarray,
    y_arr: np.ndarray,
    n_features: int,
    rng: np.random.Generator,
    pos_coef: bool,
    pos_int: bool,
    metric: str,
    max_pval: float = 1.0,
    allowed_models: frozenset | set | None = None,
) -> tuple[str, dict, dict] | None:
    """Fit all allowed model types and return the best (model_type, params, metrics).

    This is the inner loop of the random search.  For speed, tree models use
    reduced n_estimators (RF: 30, XGB: 20) during the search; the final refit
    (after the search completes) uses the user-specified counts.

    Model selection
    ---------------
    All allowed model types are fitted with randomly sampled hyperparameters.
    For linear models, positivity is enforced during fitting (sklearn's
    ``positive=True``).  For tree models, positivity flags are stored in the
    params dict and applied post-hoc to SHAP outputs in the final refit.

    When ``max_pval < 1.0``, candidates where any feature p-value exceeds the
    threshold are rejected via ``_pvals_ok()``.

    Parameters
    ----------
    X_arr : np.ndarray of shape (n, k)
        Feature matrix for the current candidate configuration.
    y_arr : np.ndarray of shape (n,)
        Target vector.
    n_features : int
        Number of features (= k, for parameter counting in metrics).
    rng : np.random.Generator
        Seeded random number generator.
    pos_coef : bool
        Enforce non-negative coefficients (linear models) / clip SHAP (trees).
    pos_int : bool
        Reject models with negative intercept (linear) / clip base value (trees).
    metric : str
        Optimisation metric key (e.g. ``"adj_r2"``).
    max_pval : float
        Maximum allowed p-value for any feature.  1.0 disables the check.
    allowed_models : frozenset | set | None
        Set of model type keys to consider.  None means all model types.

    Returns
    -------
    tuple[str, dict, dict] | None
        (model_type, params, metrics) for the best admitted candidate, or None
        if no candidate passed all constraints.
    """
    if allowed_models is None:
        allowed_models = _ALL_MODEL_TYPES
    from sklearn.linear_model import LinearRegression, Ridge, Lasso, ElasticNet
    from sklearn.ensemble import RandomForestRegressor

    # Accumulates all admitted (score, model_type, params, metrics) tuples
    candidates: list[tuple[float, str, dict, dict]] = []

    def _add(model_type: str, mdl, p_used: dict, n_par: int) -> None:
        """Score a fitted model and add it to candidates if constraints pass."""
        try:
            y_pred = mdl.predict(X_arr)
            # Reject if intercept constraint is violated (linear models)
            if pos_int and hasattr(mdl, "intercept_"):
                ic = float(np.atleast_1d(mdl.intercept_)[0])
                if ic < 0:
                    return
            # ── P-value constraint ────────────────────────────────────────────
            if not _pvals_ok(mdl, model_type, X_arr, y_arr, max_pval):
                return
            m = _compute_metrics(y_arr, y_pred, n_par)
            s = _to_score(m, metric)
            candidates.append((s, model_type, p_used, m))
        except Exception:
            pass

    # ── Linear models ─────────────────────────────────────────────────────────
    # Hyperparameters are sampled from log-uniform distributions which give
    # better coverage over several orders of magnitude than uniform sampling.
    alpha_r  = float(10 ** rng.uniform(-3, 2))    # Ridge: α in [0.001, 100]
    alpha_l  = float(10 ** rng.uniform(-3, 1))    # Lasso/EN: α in [0.001, 10]
    l1_ratio = float(rng.uniform(0.1, 0.9))       # EN mixing ratio

    lm_kw = {"fit_intercept": True, "positive": pos_coef}
    n_lin = n_features + 1  # +1 for intercept in parameter count

    if "linear" in allowed_models:
        try:
            mdl = LinearRegression(**lm_kw)
            mdl.fit(X_arr, y_arr)
            _add("linear", mdl, lm_kw, n_lin)
        except Exception:
            pass

    if "ridge" in allowed_models:
        try:
            p = {**lm_kw, "alpha": alpha_r}
            mdl = Ridge(**p)
            mdl.fit(X_arr, y_arr)
            _add("ridge", mdl, p, n_lin)
        except Exception:
            pass

    if "lasso" in allowed_models:
        try:
            p = {**lm_kw, "alpha": alpha_l, "max_iter": 5000}
            mdl = Lasso(**p)
            mdl.fit(X_arr, y_arr)
            _add("lasso", mdl, p, n_lin)
        except Exception:
            pass

    if "elasticnet" in allowed_models:
        try:
            p = {**lm_kw, "alpha": alpha_l, "l1_ratio": l1_ratio, "max_iter": 5000}
            mdl = ElasticNet(**p)
            mdl.fit(X_arr, y_arr)
            _add("elasticnet", mdl, p, n_lin)
        except Exception:
            pass

    # ── Tree models (positivity applied post-hoc to SHAP outputs) ─────────────
    # n_estimators is intentionally capped at 30/20 during the search loop for
    # speed.  The final refit (after the loop) uses the user-specified counts.
    if "randomforest" in allowed_models:
        rf_depth = int(rng.choice([3, 5, 7, 0]))  # 0 → None (unlimited depth)
        rf_leaf  = int(rng.choice([1, 2, 3, 5]))
        # Store positivity flags in params so _fit_tree_model can apply them at refit
        rf_p = {
            "n_estimators":       30,   # Reduced for search speed
            "max_depth":          None if rf_depth == 0 else rf_depth,
            "min_samples_leaf":   rf_leaf,
            "max_features":       "sqrt",
            "random_state":       42,
            "n_jobs":             -1,
            "positive":           pos_coef,
            "positive_intercept": pos_int,
        }
        try:
            mdl = RandomForestRegressor(
                n_estimators=rf_p["n_estimators"],
                max_depth=rf_p["max_depth"],
                min_samples_leaf=rf_p["min_samples_leaf"],
                max_features=rf_p["max_features"],
                random_state=rf_p["random_state"],
                n_jobs=-1,
            )
            mdl.fit(X_arr, y_arr)
            # Use n_features (not n_lin) — tree models don't have an intercept term
            _add("randomforest", mdl, rf_p, n_features)
        except Exception:
            pass

    if "xgboost" in allowed_models:
        try:
            from xgboost import XGBRegressor
            xgb_depth = int(rng.choice([3, 4, 5, 6]))
            xgb_lr    = float(rng.choice([0.05, 0.1, 0.2, 0.3]))
            xgb_p = {
                "n_estimators":       20,   # Reduced for search speed
                "max_depth":          xgb_depth,
                "learning_rate":      xgb_lr,
                "subsample":          0.8,
                "colsample_bytree":   0.8,
                "reg_alpha":          0.1,
                "reg_lambda":         1.0,
                "random_state":       42,
                "verbosity":          0,
                "positive":           pos_coef,
                "positive_intercept": pos_int,
            }
            mdl = XGBRegressor(
                n_estimators=xgb_p["n_estimators"],
                max_depth=xgb_p["max_depth"],
                learning_rate=xgb_p["learning_rate"],
                subsample=xgb_p["subsample"],
                colsample_bytree=xgb_p["colsample_bytree"],
                reg_alpha=xgb_p["reg_alpha"],
                reg_lambda=xgb_p["reg_lambda"],
                random_state=xgb_p["random_state"],
                verbosity=0,
            )
            mdl.fit(X_arr, y_arr)
            _add("xgboost", mdl, xgb_p, n_features)
        except Exception:
            pass

    if not candidates:
        return None   # No admitted candidate found
    # Return the candidate with the highest normalised score
    best = max(candidates, key=lambda x: x[0])
    return best[1], best[2], best[3]   # model_type, params, metrics


# ─────────────────────────────── WORKER THREAD ────────────────────────────────

def _autofit_worker(
    task_id: str,
    df: pd.DataFrame,
    target_col: str,
    input_cols: list[str],
    media_cols: list[str],
    groupby_cols: list[str],
    constraints: dict,
    metric: str,
    n_iter: int,
    seed: int,
    date_filter_cfg: dict | None,
    date_col: str | None,
) -> None:
    """Execute the random search in a background daemon thread.

    This function runs the full Auto-Fit random search algorithm and writes
    progress / results back into the shared ``_TASKS[task_id]`` dict.  It is
    never called directly — use ``start_autofit()`` instead.

    Algorithm (per iteration)
    -------------------------
    1. Sample a random subset of input columns (media cols always included).
    2. For each selected column, sample a random transform chain.
    3. Apply all transforms to a fresh copy of df (full date range so adstock
       carry-over is correct).
    4. Apply the date filter (if configured) and trim to the last 12 months.
    5. Fit all allowed model types and select the best by the chosen metric.
    6. Update best_config if this iteration beats the current best score.

    After the loop the best configuration is refit once with full inference
    (TreeSHAP for trees, sandwich/OLS for linear models) via fit_model().

    Parameters
    ----------
    task_id : str
        UUID4 key in ``_TASKS``.  Must be pre-populated before calling.
    df : pd.DataFrame
        Snapshot of the Tab 1 processed data (already copied by start_autofit).
    target_col : str
        Name of the target (KPI) column.
    input_cols : list[str]
        All available input column names (media + non-media).
    media_cols : list[str]
        Subset of input_cols that are declared media / channel columns.
    groupby_cols : list[str]
        Groupby columns passed to apply_tab2_transformations().
    constraints : dict
        Keys:
          - ``positive_coefficients`` (bool)
          - ``positive_intercept``    (bool)
          - ``max_pval``              (float)
          - ``allowed_models``        (list[str])
    metric : str
        Optimisation metric key (e.g. ``"adj_r2"``).
    n_iter : int
        Total number of random configurations to evaluate.
    seed : int
        Random seed for reproducibility.
    date_filter_cfg : dict | None
        Date filter configuration from Tab 2 (applied after transforms).
    date_col : str | None
        Name of the datetime column used for the last-12-months trim.
    """
    task = _TASKS[task_id]
    rng  = np.random.default_rng(seed)

    media_set        = set(media_cols)
    # Pre-compute whether the target column has any zero values for zero-mask sampling
    has_target_zeros = (
        bool((df[target_col] == 0).any()) if target_col in df.columns else False
    )
    pos_coef       = bool(constraints.get("positive_coefficients", False))
    pos_int        = bool(constraints.get("positive_intercept",    False))
    max_pval       = float(constraints.get("max_pval", 1.0))
    allowed_models = frozenset(
        constraints.get("allowed_models", list(_ALL_MODEL_TYPES))
    )

    best_score  = -np.inf       # Tracks the best normalised score seen
    best_config: dict | None = None
    start = time.time()

    try:
        for i in range(n_iter):
            # ── Cancel check ──────────────────────────────────────────────────
            # The UI sets task["cancel"] = True when the user clicks "Cancel".
            if task.get("cancel"):
                break

            try:
                # ── Sample column subset ──────────────────────────────────────
                # Non-media columns are randomly included (70 % chance each).
                # Media columns are ALWAYS included — users expect every declared
                # media channel to appear in every fitted model.
                mask = rng.random(len(input_cols)) < 0.70
                for _mi, _mc in enumerate(input_cols):
                    if _mc in media_set:
                        mask[_mi] = True      # media channels are mandatory
                # Ensure at least one column is always included
                if not mask.any():
                    mask[int(rng.integers(0, len(input_cols)))] = True
                selected = [c for c, ok in zip(input_cols, mask) if ok]

                # ── Sample transform chain per column ─────────────────────────
                all_t: list[dict] = []   # All transform dicts for this iteration
                feats:  list[str] = []   # Final column names after transforms
                for col in selected:
                    t_list, final = _sample_col_transforms(
                        col, col in media_set, has_target_zeros, rng
                    )
                    all_t.extend(t_list)
                    feats.append(final)

                # Deduplicate feature names (preserve order) — can happen when
                # two columns share the same final name after in-place transforms
                seen_f: set = set()
                feats = [f for f in feats if not (f in seen_f or seen_f.add(f))]

                # ── Apply transforms on a fresh copy ──────────────────────────
                # Fresh copy for each iteration so transforms don't accumulate
                dfc = df.copy()
                if all_t:
                    dfc = apply_tab2_transformations(
                        dfc, all_t, groupby_cols, target_col
                    )

                # Apply the date filter AFTER transforms so adstock carry-over
                # from before the window boundary is correctly computed
                if date_filter_cfg:
                    dfc = _apply_date_filter(dfc, date_filter_cfg)

                # Trim to last 12 months before fitting
                dfc = _last_n_months(dfc, date_col, n=12)

                # Only keep feature columns that survived the transform pipeline
                valid = [f for f in feats if f in dfc.columns]
                if not valid:
                    continue

                # ── Prepare X, y ──────────────────────────────────────────────
                # Drop rows with any NaN in features or target
                mdf = dfc[valid + [target_col]].dropna()
                # Need at least k+1 rows to fit a model with k features
                if len(mdf) < max(3, len(valid) + 1):
                    continue

                X_arr = mdf[valid].values.astype(float)
                y_arr = mdf[target_col].values.astype(float)

                # Skip configurations with zero-variance features (can't be modelled)
                if (X_arr.std(axis=0) == 0).any():
                    continue

                # ── Try all models and pick best ───────────────────────────────
                triple = _try_all_models(
                    X_arr, y_arr, len(valid), rng, pos_coef, pos_int,
                    metric, max_pval, allowed_models,
                )
                if triple is None:
                    continue

                model_type, params, metrics = triple
                score = _to_score(metrics, metric)

                # Update best config if this is the best score seen so far
                if score > best_score:
                    best_score = score
                    raw_val    = metrics.get(metric, np.nan)
                    best_config = {
                        "best_transforms": all_t,
                        "best_features":   valid,
                        "best_model_type": model_type,
                        "best_params":     params,
                        "best_score":      raw_val,
                        "metric":          metric,
                        "metric_label":    METRIC_LABELS.get(metric, metric),
                        "iterations_run":  i + 1,
                    }
                    # Write to shared task dict immediately so UI can show live progress
                    task["best_config"] = best_config
                    task["best_score"]  = raw_val

            except Exception:
                pass   # Swallow per-iteration errors to keep the search running

            # ── Update progress ────────────────────────────────────────────────
            elapsed = time.time() - start
            task["progress"] = (i + 1) / n_iter
            task["elapsed"]  = elapsed
            # ETA: average time per iteration × remaining iterations
            task["eta"]      = (elapsed / max(i + 1, 1)) * (n_iter - i - 1)
            task["iter"]     = i + 1

        # ── Refit best config with full inference (including SHAP for trees) ───
        # After the search loop, the best configuration is refit via fit_model()
        # which computes full TreeSHAP values (for trees) or exact inference
        # (for linear models).  This is what Tab 3 displays.
        if best_config and not task.get("cancel"):
            task["status"] = "refitting"
            try:
                dfc = df.copy()
                if best_config["best_transforms"]:
                    dfc = apply_tab2_transformations(
                        dfc,
                        best_config["best_transforms"],
                        groupby_cols,
                        target_col,
                    )
                if date_filter_cfg:
                    dfc = _apply_date_filter(dfc, date_filter_cfg)
                dfc = _last_n_months(dfc, date_col, n=12)

                # ── Record the actual date window used for the final fit ──────
                # Propagated back to cfg["date_filter"] in the UI so that Tab 2's
                # live preview shows the same 12-month subset the model was trained on.
                if date_col and date_col in dfc.columns:
                    try:
                        _dt = pd.to_datetime(dfc[date_col]).dropna()
                        best_config["fitted_date_col"] = date_col
                        best_config["fitted_date_min"] = _dt.min().date()
                        best_config["fitted_date_max"] = _dt.max().date()
                    except Exception:
                        pass

                valid = best_config["best_features"]
                mdf   = dfc[valid + [target_col]].dropna()
                # Full inference refit using fit_model (includes TreeSHAP if applicable)
                full_result = fit_model(
                    mdf[valid],
                    mdf[target_col],
                    best_config["best_model_type"],
                    best_config["best_params"],
                )
                best_config["best_result"] = full_result
            except Exception as e:
                best_config["refit_error"] = str(e)

        task["result"] = best_config

    except Exception as exc:
        # Worker-level exception — store the error message for the UI to display
        task["error"] = str(exc)

    finally:
        # Always update task status on exit so the UI knows the worker finished
        cancelled = task.get("cancel", False)
        task["status"] = (
            "cancelled" if cancelled
            else ("complete" if best_config else "no_result")
        )
        task["done"] = True


# ─────────────────────────────── PUBLIC API ───────────────────────────────────

def start_autofit(
    task_id: str,
    df: pd.DataFrame,
    target_col: str,
    input_cols: list[str],
    media_cols: list[str],
    groupby_cols: list[str],
    constraints: dict,
    metric: str              = "adj_r2",
    n_iter: int              = 200,
    seed: int                = 42,
    date_filter_cfg: dict | None = None,
    date_col: str | None         = None,
) -> None:
    """Launch the Auto-Fit random search in a background daemon thread.

    Registers a new task entry in ``_TASKS``, snapshots the input DataFrame,
    and starts a daemon thread running ``_autofit_worker()``.

    The caller is responsible for polling ``get_task(task_id)`` to check
    progress and retrieve the result when ``task["done"]`` becomes True.
    After processing the completed task the caller should call
    ``cleanup_task(task_id)`` to free memory.

    Parameters
    ----------
    task_id : str
        Unique identifier for this task (UUID4 recommended).
    df : pd.DataFrame
        The Tab 1 processed DataFrame.  A snapshot copy is taken immediately
        so subsequent UI changes do not affect the running search.
    target_col : str
        Name of the target (KPI) column.
    input_cols : list[str]
        All candidate feature columns (including media channels).
    media_cols : list[str]
        Subset of input_cols that should receive adstock / saturation.
    groupby_cols : list[str]
        Groupby columns for group-aware transforms.
    constraints : dict
        Search constraints with keys:
          - ``positive_coefficients`` (bool) — enforce non-negative coefficients.
          - ``positive_intercept``    (bool) — reject negative intercept configs.
          - ``max_pval``              (float) — maximum allowed feature p-value.
          - ``allowed_models``        (list[str]) — model types to include.
    metric : str
        Metric to optimise (default ``"adj_r2"``).  Must be a key in METRIC_LABELS.
    n_iter : int
        Number of random configurations to evaluate (default 200).
    seed : int
        Random seed for reproducibility (default 42).
    date_filter_cfg : dict | None
        Optional Tab 2 date filter to apply after transforms.
    date_col : str | None
        Name of the datetime column used for the 12-month trim.
    """
    # Initialise the task state dict before starting the thread so get_task()
    # always returns a valid dict from the moment start_autofit() returns.
    _TASKS[task_id] = {
        "status":      "running",
        "progress":    0.0,
        "elapsed":     0.0,
        "eta":         0.0,
        "iter":        0,
        "cancel":      False,
        "done":        False,
        "result":      None,
        "error":       None,
        "best_score":  float("nan"),
        "best_config": None,
    }
    thread = threading.Thread(
        target=_autofit_worker,
        kwargs=dict(
            task_id         = task_id,
            df              = df.copy(),   # Snapshot so UI changes don't interfere
            target_col      = target_col,
            input_cols      = list(input_cols),
            media_cols      = list(media_cols),
            groupby_cols    = list(groupby_cols),
            constraints     = dict(constraints),
            metric          = metric,
            n_iter          = n_iter,
            seed            = seed,
            date_filter_cfg = date_filter_cfg,
            date_col        = date_col,
        ),
        daemon=True,   # Daemon so thread dies when the Streamlit server exits
    )
    thread.start()


# ─────────────────────────────── DISPLAY HELPER ───────────────────────────────

def describe_transforms(transforms: list[dict]) -> pd.DataFrame:
    """Convert a flat transform list into a human-readable display DataFrame.

    Used in Tab 2's Auto-Fit result section and Tab 3's "Applied Transformations"
    expander to give users a clear, tabular summary of which transforms are active.

    Parameters
    ----------
    transforms : list[dict]
        Flat list of transform dicts (same schema as stored in
        cfg["adstock_transforms"]).

    Returns
    -------
    pd.DataFrame
        Columns: ``#`` (step number), ``Source``, ``Transform``, ``Output``,
        ``Parameters``.  Empty DataFrame with headers if transforms is empty.
        The ``Output`` column appends " ↩" for in-place transforms (no new column)
        to distinguish them from new-column transforms.
    """
    rows = []
    for i, t in enumerate(transforms):
        src   = t.get("source_col", "")
        ttype = t.get("type", "")
        out   = t.get("output_col", "")
        p     = t.get("params", {})
        # In-place transforms don't create a new column
        inplace = ttype not in {"adstock", "norm", "saturation"}

        # Build a human-readable parameter summary for each transform type
        if ttype == "adstock":
            m  = p.get("method", "geometric")
            ml = p.get("max_lag", 4)
            if m == "geometric":
                ps = f"geometric  α={p.get('alpha', 0):.3f}  lags≤{ml}"
            elif m == "weibull":
                ps = (f"Weibull  shape={p.get('shape', 0):.2f}"
                      f"  scale={p.get('scale', 0):.2f}  lags≤{ml}")
            else:
                ps = (f"Hill  α={p.get('alpha', 0):.2f}"
                      f"  γ={p.get('gamma', 0):.2f}  lags≤{ml}")
        elif ttype == "saturation":
            ps = f"c={p.get('c', 1):.3f}  d={p.get('d', 0):.5f}"
        elif ttype == "norm":
            ps = p.get("method", "minmax")
        elif ttype in ("lag", "lead"):
            ps = f"n={p.get('n', 1)}"
        elif ttype == "moving_avg":
            ps = f"window={p.get('n', 3)}"
        elif ttype == "mean_center":
            ps = "—"   # No parameters needed
        elif ttype == "zero_mask":
            ps = "where target = 0"
        else:
            ps = str(p)

        rows.append({
            "#":          i + 1,
            "Source":     src,
            "Transform":  ttype.replace("_", " ").title(),
            # Append ↩ to the output name for in-place transforms as a visual cue
            "Output":     out + (" ↩" if inplace else ""),
            "Parameters": ps,
        })

    return (
        pd.DataFrame(rows)
        if rows
        else pd.DataFrame(columns=["#", "Source", "Transform", "Output", "Parameters"])
    )
