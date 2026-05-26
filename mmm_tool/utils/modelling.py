"""Prior modelling utilities for MMM Tab 3.

All models are fitted via scikit-learn so that ``positive`` and
``fit_intercept`` are supported uniformly.  Inference statistics are
derived analytically:

* **Linear Regression** — exact OLS covariance.
* **Ridge** — sandwich covariance with effective df from the hat-matrix
  trace (Hastie, Tibshirani & Friedman §3.4).
* **Lasso / ElasticNet** — active-set OLS approximation: refit OLS on the
  non-zero coefficient support; SE / t / p are exact for that sub-model.
  Zero (inactive) coefficients are labelled NaN.
* **Random Forest / XGBoost** — TreeSHAP-based inference:
  coefficient = mean SHAP value; SE = std(SHAP)/√n; two-sided t-test
  H₀: mean SHAP = 0, df = n − 1.

Public API
----------
The only function that callers (app.py, autofit.py) should use is:

    result = fit_model(X, y, model_type, params)

All other names are internal helpers prefixed with an underscore.

Result dict keys
----------------
coef_df       : pd.DataFrame — Feature / Coefficient / Std Error / t-stat / p-value / Sig
stats         : dict — R², adj-R², RMSE, MAE, AIC, BIC, F-stat, n_obs, n_params, df_residual
fitted        : np.ndarray — fitted (predicted) values for every observation
residuals     : np.ndarray — y − ŷ for every observation
model_type    : str — the model_type string passed in
params        : dict — the params dict passed in
pvalue_method : str — human-readable description of the inference method used
mean_abs_shap_by_feature : dict (tree models only) — {feature: mean |SHAP|}
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import ElasticNet, Lasso, LinearRegression, Ridge
from sklearn.ensemble import RandomForestRegressor as _RF

# Optional dependencies — gracefully degrade when not installed
try:
    from xgboost import XGBRegressor as _XGB
    _HAS_XGB = True
except ImportError:  # pragma: no cover
    _HAS_XGB = False

try:
    import shap as _shap
    _HAS_SHAP = True
except ImportError:  # pragma: no cover
    _HAS_SHAP = False


# ─────────────────────── LOW-LEVEL INFERENCE HELPERS ─────────────────────────

def _sig_stars(p: float) -> str:
    """Convert a p-value to a significance star string.

    Uses the conventional R-style coding:
      *** → p < 0.001   (highly significant)
       ** → p < 0.01
        * → p < 0.05   (conventionally significant)
        . → p < 0.10   (marginally significant)
     (blank) → p ≥ 0.10

    Parameters
    ----------
    p : float
        P-value in [0, 1].  NaN returns an empty string.

    Returns
    -------
    str
        Star string.
    """
    if np.isnan(p):
        return ""
    if p < 0.001:
        return "***"
    if p < 0.01:
        return "**"
    if p < 0.05:
        return "*"
    if p < 0.1:
        return "."
    return ""


def _ols_inference(X_aug: np.ndarray, y: np.ndarray, beta: np.ndarray) -> dict:
    """Compute exact OLS inference for a given design matrix and coefficient vector.

    Given the augmented design matrix X_aug (which may already include a
    column of ones for the intercept) and the corresponding coefficient vector
    beta, this function computes:

      - Residuals:  e = y − X_aug @ beta
      - Residual df: n − k  (n observations, k parameters)
      - Residual variance: s² = e'e / df_res
      - Covariance matrix: Cov(β̂) = s² (X'X)⁻¹  (via pseudo-inverse)
      - Standard errors: SE = sqrt(diag(Cov(β̂)))
      - t-statistics: t = β / SE
      - Two-sided p-values from the t-distribution with df_res degrees of freedom

    Parameters
    ----------
    X_aug : np.ndarray of shape (n, k)
        Augmented design matrix (already includes intercept column if needed).
    y : np.ndarray of shape (n,)
        Target (response) vector.
    beta : np.ndarray of shape (k,)
        Coefficient vector (must align with columns of X_aug).

    Returns
    -------
    dict with keys: ``se``, ``t``, ``p``, ``df_res``, ``residuals``
    """
    n, k = X_aug.shape
    residuals = y - X_aug @ beta
    df_res = max(n - k, 1)  # Prevent division by zero in degenerate models

    # Residual variance estimate: s² = RSS / df_res
    s2 = np.sum(residuals ** 2) / df_res
    try:
        # Use pseudo-inverse for numerical stability with near-collinear predictors
        XtX_inv = np.linalg.pinv(X_aug.T @ X_aug)
        se = np.sqrt(np.maximum(s2 * np.diag(XtX_inv), 0.0))  # clamp to ≥ 0
    except Exception:
        se = np.full(k, np.nan)

    with np.errstate(invalid="ignore", divide="ignore"):
        t = beta / se
        p = 2.0 * stats.t.sf(np.abs(t), df_res)  # Two-sided p-value

    return {"se": se, "t": t, "p": p, "df_res": float(df_res), "residuals": residuals}


def _ridge_inference(
    X: np.ndarray,
    y: np.ndarray,
    beta_coef: np.ndarray,
    intercept: float,
    alpha: float,
    fit_intercept: bool,
) -> dict:
    """Compute sandwich covariance inference for Ridge regression.

    Ridge shrinks coefficients toward zero which biases OLS covariance estimates.
    The sandwich covariance provides a better-calibrated SE:

        Cov(β̂_ridge) ≈ σ² (X'X + αI)⁻¹ X'X (X'X + αI)⁻¹

    The effective degrees of freedom for Ridge is computed via the hat-matrix
    trace (Hastie, Tibshirani & Friedman, "Elements of Statistical Learning",
    §3.4), which accounts for the shrinkage:

        df_eff = trace(X (X'X + αI)⁻¹ X') + (1 if fit_intercept else 0)
        df_res  = n − df_eff

    Parameters
    ----------
    X : np.ndarray of shape (n, k)
        Feature matrix (NOT augmented — intercept is handled separately).
    y : np.ndarray of shape (n,)
        Target vector.
    beta_coef : np.ndarray of shape (k,)
        Ridge coefficient estimates (excluding intercept).
    intercept : float
        Ridge intercept estimate.
    alpha : float
        Ridge regularisation strength λ.  Must match what was used to fit.
    fit_intercept : bool
        Whether the model was fitted with an intercept.

    Returns
    -------
    dict with keys: ``se``, ``t``, ``p``, ``df_res``, ``residuals``
        Lengths of se/t/p = k + 1 (intercept first) when fit_intercept=True,
        or k when fit_intercept=False.
    """
    n, k = X.shape
    residuals = y - (X @ beta_coef + intercept)

    # Build the Ridge normal equations: A = X'X + αI
    XtX = X.T @ X
    A = XtX + alpha * np.eye(k)
    try:
        A_inv = np.linalg.pinv(A)
    except Exception:
        # Fallback: return NaN inference when matrix inversion fails
        return _fallback_inference(beta_coef, intercept, fit_intercept, residuals, n)

    # Effective df from hat-matrix trace (feature part only)
    # H = X (X'X + αI)⁻¹ X'  →  trace(H) = trace(X'X (X'X + αI)⁻¹)
    df_fit = float(np.trace(XtX @ A_inv))
    if fit_intercept:
        df_fit += 1.0   # Intercept counts as one additional effective parameter
    df_res = max(n - df_fit, 1.0)

    # Residual variance using effective df
    s2 = np.sum(residuals ** 2) / df_res

    # Sandwich covariance for feature coefficients
    cov_beta = s2 * (A_inv @ XtX @ A_inv)
    se_coef = np.sqrt(np.maximum(np.diag(cov_beta), 0.0))

    if fit_intercept:
        # Approximate intercept SE under the centred-design assumption
        se_int = np.sqrt(max(s2 / n, 0.0))
        se   = np.concatenate([[se_int], se_coef])
        beta = np.concatenate([[intercept], beta_coef])
    else:
        se   = se_coef
        beta = beta_coef

    with np.errstate(invalid="ignore", divide="ignore"):
        t = beta / se
        p = 2.0 * stats.t.sf(np.abs(t), df_res)

    return {"se": se, "t": t, "p": p, "df_res": df_res, "residuals": residuals}


def _active_set_inference(
    X: np.ndarray,
    y: np.ndarray,
    beta_coef: np.ndarray,
    intercept: float,
    fit_intercept: bool,
) -> dict:
    """Active-set OLS approximation for Lasso / ElasticNet / constrained OLS.

    Lasso and ElasticNet zero out many coefficients (sparse solutions).
    Standard covariance theory does not apply to the zero (inactive)
    coefficients.  The active-set approximation:

    1. Identifies the **active set** A = {j : |β_j| > ε} (non-zero coefficients).
    2. Refits ordinary OLS *only on the sub-design X_A* (the columns corresponding
       to active predictors).
    3. Reports exact OLS standard errors / t-statistics / p-values for active
       coefficients and NaN for inactive (zeroed) ones.

    This is equivalent to treating the Lasso solution as the "selected model"
    and computing post-selection inference under that selection.

    Parameters
    ----------
    X : np.ndarray of shape (n, k)
        Feature matrix.
    y : np.ndarray of shape (n,)
        Target vector.
    beta_coef : np.ndarray of shape (k,)
        Lasso / ElasticNet coefficients (may contain exact zeros).
    intercept : float
        Model intercept estimate.
    fit_intercept : bool
        Whether the model includes an intercept term.

    Returns
    -------
    dict with keys: ``se``, ``t``, ``p``, ``df_res``, ``residuals``
        Arrays of length k_total = k + (1 if fit_intercept else 0).
        Inactive coefficient positions are filled with NaN.
    """
    n = len(y)
    k_total = len(beta_coef) + (1 if fit_intercept else 0)
    residuals = y - (X @ beta_coef + intercept)

    # Identify active (non-zero) predictors — threshold at 1e-10 to handle
    # floating-point near-zeros from the solver
    active = np.where(np.abs(beta_coef) > 1e-10)[0]

    # Pre-fill output arrays with NaN (inactive coefficients stay NaN)
    se_out = np.full(k_total, np.nan)
    t_out  = np.full(k_total, np.nan)
    p_out  = np.full(k_total, np.nan)

    # Edge case: all coefficients zeroed out (fully sparse solution)
    if len(active) == 0:
        df_res = max(n - k_total, 1)
        return {"se": se_out, "t": t_out, "p": p_out, "df_res": float(df_res),
                "residuals": residuals}

    # Build the sub-design from active columns
    X_A = X[:, active]
    if fit_intercept:
        # Augment with a column of ones for the intercept
        X_A_aug = np.column_stack([np.ones(n), X_A])
        beta_A  = np.concatenate([[intercept], beta_coef[active]])
    else:
        X_A_aug = X_A
        beta_A  = beta_coef[active]

    # Fit exact OLS on the reduced design matrix
    inf = _ols_inference(X_A_aug, y, beta_A)
    se_A, t_A, p_A = inf["se"], inf["t"], inf["p"]
    df_res = inf["df_res"]

    # Map the sub-model inference back into the full-size output arrays
    if fit_intercept:
        # Index 0 in the full array is always the intercept
        se_out[0] = se_A[0]
        t_out[0]  = t_A[0]
        p_out[0]  = p_A[0]
        # Remaining entries correspond to active feature indices (offset by 1
        # because position 0 is the intercept in X_A_aug)
        for arr_i, col_j in enumerate(active):
            se_out[col_j + 1] = se_A[arr_i + 1]
            t_out[col_j + 1]  = t_A[arr_i + 1]
            p_out[col_j + 1]  = p_A[arr_i + 1]
    else:
        for arr_i, col_j in enumerate(active):
            se_out[col_j] = se_A[arr_i]
            t_out[col_j]  = t_A[arr_i]
            p_out[col_j]  = p_A[arr_i]

    return {"se": se_out, "t": t_out, "p": p_out, "df_res": df_res,
            "residuals": residuals}


def _fallback_inference(
    beta_coef: np.ndarray,
    intercept: float,
    fit_intercept: bool,
    residuals: np.ndarray,
    n: int,
) -> dict:
    """Return an all-NaN inference dict when matrix operations fail.

    Used as the last resort when numpy raises a LinAlgError or similar.
    All SE / t / p values are NaN so the UI can still display the
    coefficient values without crashing.

    Parameters
    ----------
    beta_coef : np.ndarray
        Coefficient array (used only to determine output array lengths).
    intercept : float
        Intercept estimate (unused, kept for signature consistency).
    fit_intercept : bool
        Whether the model has an intercept.
    residuals : np.ndarray
        Residual vector (returned as-is so model stats can be computed).
    n : int
        Number of observations (for df_res computation).

    Returns
    -------
    dict with keys: ``se``, ``t``, ``p``, ``df_res``, ``residuals``
    """
    k = len(beta_coef) + (1 if fit_intercept else 0)
    df_res = max(n - k, 1.0)
    return {
        "se": np.full(k, np.nan),
        "t":  np.full(k, np.nan),
        "p":  np.full(k, np.nan),
        "df_res": float(df_res),
        "residuals": residuals,
    }


# ─────────────────────── TREE MODEL INFERENCE (TreeSHAP) ─────────────────────

def _tree_shap_inference(
    mdl,
    X_arr: np.ndarray,
    y_arr: np.ndarray,
    positive_coef: bool = False,
    positive_intercept: bool = False,
) -> dict:
    """Compute TreeSHAP-based pseudo-inference for ensemble tree models.

    SHAP (SHapley Additive exPlanations) decomposes each model prediction
    into additive feature contributions.  For tree ensembles TreeSHAP computes
    exact Shapley values efficiently (Lundberg et al., 2020, Nature MI).

    Mapping to "coefficient table" quantities
    ------------------------------------------
    Coefficient  = mean SHAP value across all observations.
                   Represents the average directional push of each feature on
                   predictions, relative to the base value E[f(x)].
    SE           = std(SHAP values) / √n  — standard error of the mean SHAP.
    t-statistic  = mean_SHAP / SE.
    p-value      = two-sided t-test, H₀: mean contribution = 0,  df = n − 1.

    A significant p-value means the feature's average directional effect is
    unlikely to be zero across the observed data — not a formal hypothesis
    test in the OLS sense, but a useful signal for variable importance.

    Positivity constraints (post-hoc)
    ----------------------------------
    Tree models cannot enforce sign constraints during training.  When the user
    requests non-negative coefficients / base value, the SHAP outputs are clipped
    *after* the fact:
      - positive_coef → mean_shap = max(mean_shap, 0)
      - positive_intercept → base_value = max(base_value, 0)

    Parameters
    ----------
    mdl
        A fitted scikit-learn compatible tree model (RandomForest, XGBoost, etc.)
        that is supported by the SHAP TreeExplainer.
    X_arr : np.ndarray of shape (n, k)
        Feature matrix used for prediction and SHAP value computation.
    y_arr : np.ndarray of shape (n,)
        Target vector (used to compute residuals).
    positive_coef : bool
        If True, clip mean SHAP values to ≥ 0 before computing SE / t / p.
    positive_intercept : bool
        If True, clip the SHAP base value (E[f(x)]) to ≥ 0.

    Returns
    -------
    dict with keys:
        ``se``, ``t``, ``p``, ``df_res``, ``residuals``,
        ``base_value``, ``mean_shap``, ``mean_abs_shap``
    """
    n, k = X_arr.shape
    fitted    = mdl.predict(X_arr).astype(float)
    residuals = y_arr.astype(float) - fitted

    # Fallback values returned when SHAP is unavailable or raises
    _nan_inf = {
        "se": np.full(k, np.nan), "t": np.full(k, np.nan),
        "p":  np.full(k, np.nan), "df_res": float(max(n - k, 1)),
        "residuals": residuals,   "base_value": float(np.mean(y_arr)),
        "mean_shap":     np.full(k, np.nan),
        "mean_abs_shap": np.full(k, np.nan),
    }

    if not _HAS_SHAP:
        return _nan_inf

    try:
        # TreeExplainer computes exact Shapley values for tree models in O(TLD²)
        explainer  = _shap.TreeExplainer(mdl)
        sv         = np.array(explainer.shap_values(X_arr), dtype=float)  # shape (n, k)
        base_value = float(np.atleast_1d(explainer.expected_value)[0])
    except Exception:
        return _nan_inf

    # Mean SHAP across all n observations — the "coefficient" for tree models
    mean_shap     = sv.mean(axis=0)                            # shape (k,)
    # Mean absolute SHAP — used for proportional impactable allocation in Tab 3.
    # Computed BEFORE positivity clipping so it reflects true feature importance.
    mean_abs_shap = np.abs(sv).mean(axis=0)                    # shape (k,) — before clipping

    # ── Post-hoc positivity constraints ───────────────────────────────────────
    if positive_coef:
        mean_shap = np.maximum(mean_shap, 0.0)
    if positive_intercept:
        base_value = max(base_value, 0.0)

    # Standard error of the mean SHAP: std(SHAP_i) / √n
    std_shap = sv.std(axis=0, ddof=1)                         # shape (k,)
    # Use NaN for features whose SHAP values have essentially zero variance
    se = np.where(std_shap > 1e-12, std_shap / np.sqrt(n), np.nan)

    with np.errstate(invalid="ignore", divide="ignore"):
        t = mean_shap / se
        p = 2.0 * stats.t.sf(np.abs(t), df=float(n - 1))

    return {
        "se":             se,
        "t":              t,
        "p":              p,
        "df_res":         float(max(n - k, 1)),
        "residuals":      residuals,
        "base_value":     base_value,
        "mean_shap":      mean_shap,
        "mean_abs_shap":  mean_abs_shap,   # Unclipped, for impactable allocation
    }


# ─────────────────────── OVERALL MODEL STATISTICS ────────────────────────────

def _model_stats(
    y: np.ndarray,
    residuals: np.ndarray,
    n_params: int,
    fit_intercept: bool,
    df_res_override: float | None = None,
) -> dict:
    """Compute overall model fit statistics from residuals.

    Computes R², adjusted R², F-statistic and its p-value, AIC, BIC, RMSE,
    and MAE.  All information-theoretic statistics (AIC, BIC) are computed via
    the Gaussian log-likelihood under the assumption of i.i.d. Normal errors.

    Parameters
    ----------
    y : np.ndarray of shape (n,)
        Observed target values.
    residuals : np.ndarray of shape (n,)
        Model residuals = y − ŷ.
    n_params : int
        Total number of estimated parameters (including intercept if applicable).
    fit_intercept : bool
        Whether the model has an intercept.  Affects TSS and the R² denominator.
    df_res_override : float | None
        If provided, overrides the default df_res = n − n_params.  Used by
        Ridge (effective df from hat-matrix trace) and tree models (n − k).

    Returns
    -------
    dict with keys:
        ``n_obs``, ``n_params``, ``df_residual``,
        ``r2``, ``adj_r2``,
        ``f_stat``, ``f_pval``,
        ``aic``, ``bic``,
        ``rmse``, ``mae``
    """
    n   = len(y)
    rss = float(np.sum(residuals ** 2))
    # TSS is measured around the mean when an intercept is fit;
    # measured around zero otherwise (consistent with sklearn convention)
    tss = float(np.sum((y - y.mean()) ** 2)) if fit_intercept else float(np.sum(y ** 2))

    # k = number of *feature* coefficients (excluding intercept for F-stat)
    k      = n_params - (1 if fit_intercept else 0)
    df_res = df_res_override if df_res_override is not None else max(n - n_params, 1)

    # R² and adjusted R²
    r2     = (1.0 - rss / tss) if tss > 0 else np.nan
    adj_r2 = (1.0 - (1.0 - r2) * (n - (1 if fit_intercept else 0)) / df_res
              ) if (tss > 0 and df_res > 0) else np.nan

    # F-statistic: tests H₀ that all feature coefficients are simultaneously zero.
    # F = (ESS / k) / (RSS / df_res) where ESS = TSS − RSS.
    if k > 0 and df_res > 0 and tss > 0 and rss > 0:
        ess    = tss - rss
        f_stat = (ess / k) / (rss / df_res)
        f_pval = float(stats.f.sf(f_stat, k, df_res))
    else:
        f_stat = np.nan
        f_pval = np.nan

    # AIC / BIC via Gaussian log-likelihood (assuming homoscedastic Normal errors)
    # log L = −n/2 · (log(RSS/n) + 1 + log(2π))
    if rss > 0:
        log_lik = -0.5 * n * (np.log(rss / n) + 1.0 + np.log(2.0 * np.pi))
        aic = float(-2.0 * log_lik + 2.0 * n_params)
        bic = float(-2.0 * log_lik + np.log(n) * n_params)
    else:
        aic = bic = np.nan

    return {
        "n_obs":       n,
        "n_params":    n_params,
        "df_residual": df_res,
        "r2":          r2,
        "adj_r2":      adj_r2,
        "f_stat":      f_stat,
        "f_pval":      f_pval,
        "aic":         aic,
        "bic":         bic,
        "rmse":        float(np.sqrt(rss / n)),
        "mae":         float(np.mean(np.abs(residuals))),
    }


# ─────────────────────── TREE MODEL FITTER ───────────────────────────────────

def _fit_tree_model(
    X: pd.DataFrame,
    y: pd.Series,
    X_arr: np.ndarray,
    y_arr: np.ndarray,
    model_type: str,
    params: dict,
) -> dict:
    """Fit a tree ensemble model (Random Forest or XGBoost) and return the full result dict.

    The result dict has the same schema as ``fit_model()`` for linear models,
    so the UI can display it uniformly.  The "coefficient" values are mean SHAP
    values computed via TreeSHAP (see ``_tree_shap_inference``).

    An additional key ``mean_abs_shap_by_feature`` is included — a dict mapping
    each feature name to its mean absolute SHAP value — which is used by the
    impactable decomposition in Tab 3 to allocate KPI proportionally.

    Parameters
    ----------
    X : pd.DataFrame
        Feature DataFrame (column names preserved for the result table).
    y : pd.Series
        Target Series.
    X_arr : np.ndarray of shape (n, k)
        Numpy view of X.values.astype(float).
    y_arr : np.ndarray of shape (n,)
        Numpy view of y.values.astype(float).
    model_type : str
        Either ``"randomforest"`` or ``"xgboost"``.
    params : dict
        Model hyperparameters.  Special keys ``positive`` and
        ``positive_intercept`` control post-hoc SHAP clipping and are NOT
        passed to the sklearn / xgboost constructors.

    Returns
    -------
    dict — same schema as fit_model()

    Raises
    ------
    ImportError
        If model_type == "xgboost" and xgboost is not installed.
    ValueError
        If model_type is neither "randomforest" nor "xgboost".
    """
    n, k = X_arr.shape

    # ── Build model ───────────────────────────────────────────────────────────
    if model_type == "randomforest":
        # max_depth = 0 in the UI means "unlimited" (None in sklearn)
        _md = params.get("max_depth")
        max_depth    = None if (_md is None or int(_md) == 0) else int(_md)
        max_features = params.get("max_features", "sqrt")
        if max_features == "all":
            max_features = None   # sklearn uses None for "all features"
        mdl = _RF(
            n_estimators      = int(params.get("n_estimators",    100)),
            max_depth         = max_depth,
            min_samples_split = int(params.get("min_samples_split", 2)),
            min_samples_leaf  = int(params.get("min_samples_leaf",  1)),
            max_features      = max_features,
            random_state      = int(params.get("random_state", 42)),
            n_jobs            = -1,   # Use all available CPU cores
        )
        pvalue_method = (
            "TreeSHAP (Random Forest): coefficient = mean SHAP value; "
            "SE = std(SHAP)/√n; two-sided t-test H₀: mean contribution = 0 (df = n−1). "
            "R²/F/AIC/BIC use feature count as effective parameter count."
        )

    elif model_type == "xgboost":
        if not _HAS_XGB:
            raise ImportError("xgboost is not installed. Run: pip install xgboost")
        mdl = _XGB(
            n_estimators     = int(params.get("n_estimators",   100)),
            max_depth        = int(params.get("max_depth",        6)),
            learning_rate    = float(params.get("learning_rate", 0.3)),
            subsample        = float(params.get("subsample",      1.0)),
            colsample_bytree = float(params.get("colsample_bytree", 1.0)),
            reg_alpha        = float(params.get("reg_alpha",  0.0)),
            reg_lambda       = float(params.get("reg_lambda", 1.0)),
            random_state     = int(params.get("random_state", 42)),
            verbosity        = 0,   # Suppress XGBoost's own verbose output
        )
        pvalue_method = (
            "TreeSHAP (XGBoost): coefficient = mean SHAP value; "
            "SE = std(SHAP)/√n; two-sided t-test H₀: mean contribution = 0 (df = n−1). "
            "R²/F/AIC/BIC use feature count as effective parameter count."
        )

    else:
        raise ValueError(f"Unknown tree model_type: {model_type!r}")

    mdl.fit(X_arr, y_arr)

    # ── Positivity constraints (post-hoc; tree models cannot enforce via training)
    # The tree itself is unconstrained; we clip SHAP values after inference.
    _positive_coef = bool(params.get("positive",           False))
    _positive_int  = bool(params.get("positive_intercept", False))
    if _positive_coef or _positive_int:
        _notes: list[str] = []
        if _positive_coef:
            _notes.append("SHAP contributions clipped ≥ 0")
        if _positive_int:
            _notes.append("base value clipped ≥ 0")
        pvalue_method += f"  [Post-hoc positivity: {'; '.join(_notes)}]"

    # ── TreeSHAP inference ────────────────────────────────────────────────────
    inf           = _tree_shap_inference(mdl, X_arr, y_arr,
                                          positive_coef=_positive_coef,
                                          positive_intercept=_positive_int)
    beta_coef     = inf["mean_shap"]        # "Coefficient" column in the UI
    mean_abs_shap = inf["mean_abs_shap"]    # Unclipped, for impactable allocation
    base_value    = inf["base_value"]       # E[f(x)] — the SHAP baseline
    residuals     = inf["residuals"]
    df_res        = inf["df_res"]
    se, t_stat, pval = inf["se"], inf["t"], inf["p"]

    # ── Coefficient DataFrame ─────────────────────────────────────────────────
    feat_names = list(X.columns)
    coef_df = pd.DataFrame({
        "Feature":     feat_names,
        "Coefficient": beta_coef,
        "Std Error":   se,
        "t-stat":      t_stat,
        "p-value":     pval,
        # Significance stars (NaN p-values get an empty string)
        "Sig": [_sig_stars(float(p)) if not np.isnan(float(p)) else "" for p in pval],
    })

    # ── Overall model stats ───────────────────────────────────────────────────
    # For tree models n_params is the number of features (a lower bound on the
    # true model complexity — trees are far more complex, so Adj-R²/AIC/BIC
    # are approximate and likely optimistic).
    fitted     = mdl.predict(X_arr).astype(float)
    stats_dict = _model_stats(
        y_arr, residuals, n_params=k,
        fit_intercept=False, df_res_override=df_res,
    )
    stats_dict["base_value"] = base_value   # SHAP E[f(x)] for display in Tab 3

    return {
        "coef_df":                coef_df,
        "stats":                  stats_dict,
        "fitted":                 fitted,
        "residuals":              residuals,
        "model_type":             model_type,
        "params":                 params,
        "pvalue_method":          pvalue_method,
        # Per-feature mean(|SHAP|) keyed by feature name.
        # Stored as a dict so it survives column reordering in coef_df.
        "mean_abs_shap_by_feature": dict(zip(feat_names, mean_abs_shap.tolist())),
    }


# ─────────────────────── PUBLIC API ──────────────────────────────────────────

def fit_model(
    X: pd.DataFrame,
    y: pd.Series,
    model_type: str,
    params: dict,
) -> dict:
    """Fit a regression model and return coefficients, inference statistics, and model stats.

    This is the **sole public entry point** of this module.  It dispatches to
    the appropriate sklearn estimator, fits the model, computes inference
    statistics using the method appropriate for each model type (see module
    docstring), and returns a unified result dict.

    Parameters
    ----------
    X : pd.DataFrame
        Feature matrix.  Must be numeric with no NaN values.  Column names are
        preserved in the output ``coef_df``.
    y : pd.Series
        Target Series.  Must be numeric with no NaN values.
    model_type : str
        One of:
        - ``"linear"``      — OLS linear regression (exact inference).
        - ``"ridge"``       — Ridge regression (sandwich covariance inference).
        - ``"lasso"``       — Lasso (active-set OLS inference).
        - ``"elasticnet"``  — ElasticNet (active-set OLS inference).
        - ``"randomforest"``— Random Forest (TreeSHAP inference).
        - ``"xgboost"``     — XGBoost (TreeSHAP inference; requires xgboost pkg).
    params : dict
        Model hyperparameters.  Common keys across model types:
        - ``fit_intercept`` (bool, default True) — include a constant term.
        - ``positive``      (bool, default False) — non-negative coefficients.
        Model-specific keys:
        - ``alpha``           — regularisation strength (Ridge / Lasso / EN).
        - ``l1_ratio``        — L1 vs L2 mixing ratio (ElasticNet only).
        - ``max_iter``        — solver iteration limit (Lasso / EN).
        - ``n_estimators``    — number of trees (RF / XGB).
        - ``max_depth``       — maximum tree depth (RF / XGB).
        - ``learning_rate``   — step-size shrinkage (XGB).
        - ``positive_intercept`` — clip SHAP base value ≥ 0 (RF / XGB only).

    Returns
    -------
    dict with keys:
        ``coef_df``     — pd.DataFrame: Feature / Coefficient / Std Error / t-stat / p-value / Sig
        ``stats``       — dict of overall model statistics (R², adj-R², RMSE, MAE, AIC, BIC, …)
        ``fitted``      — np.ndarray: ŷ for every observation in X
        ``residuals``   — np.ndarray: y − ŷ for every observation
        ``model_type``  — str: as passed in
        ``params``      — dict: as passed in
        ``pvalue_method``  — str: description of the inference method used
        ``mean_abs_shap_by_feature`` — dict: {feature → mean |SHAP|} (tree models only)

    Raises
    ------
    ValueError
        If model_type is not one of the supported strings.
    """
    X_arr = X.values.astype(float)
    y_arr = y.values.astype(float)
    n, k  = X_arr.shape

    # ── Dispatch tree models ──────────────────────────────────────────────────
    # Tree models have a completely different inference path (TreeSHAP)
    # so they are handled by a dedicated helper.
    if model_type in ("randomforest", "xgboost"):
        return _fit_tree_model(X, y, X_arr, y_arr, model_type, params)

    fit_intercept = bool(params.get("fit_intercept", True))
    positive      = bool(params.get("positive", False))

    # ── Fit ──────────────────────────────────────────────────────────────────
    if model_type == "linear":
        mdl = LinearRegression(fit_intercept=fit_intercept, positive=positive)
    elif model_type == "ridge":
        mdl = Ridge(
            alpha=float(params.get("alpha", 1.0)),
            fit_intercept=fit_intercept,
            positive=positive,
        )
    elif model_type == "lasso":
        mdl = Lasso(
            alpha=float(params.get("alpha", 1.0)),
            fit_intercept=fit_intercept,
            positive=positive,
            max_iter=int(params.get("max_iter", 10_000)),
        )
    elif model_type == "elasticnet":
        mdl = ElasticNet(
            alpha=float(params.get("alpha", 1.0)),
            l1_ratio=float(params.get("l1_ratio", 0.5)),
            fit_intercept=fit_intercept,
            positive=positive,
            max_iter=int(params.get("max_iter", 10_000)),
        )
    else:
        raise ValueError(f"Unknown model_type: {model_type!r}")

    mdl.fit(X_arr, y_arr)

    # Extract fitted coefficients from sklearn's model object
    beta_coef = np.asarray(mdl.coef_, dtype=float).ravel()   # shape (k,)
    intercept = float(np.atleast_1d(mdl.intercept_)[0])       # scalar

    # ── Inference ─────────────────────────────────────────────────────────────
    # Choose the inference method based on model type and whether positivity was
    # requested (constrained OLS uses active-set like Lasso/EN).
    if model_type == "linear" and not positive:
        # Exact OLS inference — augment the design matrix with an intercept column
        if fit_intercept:
            X_aug  = np.column_stack([np.ones(n), X_arr])
            beta_a = np.concatenate([[intercept], beta_coef])
        else:
            X_aug  = X_arr
            beta_a = beta_coef
        inf = _ols_inference(X_aug, y_arr, beta_a)
        pvalue_method = "exact OLS"

    elif model_type == "ridge":
        # Ridge sandwich covariance with effective df from hat-matrix trace
        alpha_val = float(params.get("alpha", 1.0))
        inf = _ridge_inference(X_arr, y_arr, beta_coef, intercept,
                               alpha_val, fit_intercept)
        pvalue_method = "Ridge sandwich (hat-matrix trace)"

    else:
        # Lasso, ElasticNet, or constrained OLS (positive=True):
        # use active-set OLS on the non-zero coefficient support
        inf = _active_set_inference(X_arr, y_arr, beta_coef, intercept,
                                    fit_intercept)
        if positive and model_type == "linear":
            pvalue_method = "active-set OLS (NNLS support)"
        else:
            pvalue_method = "active-set OLS (Lasso/ElasticNet support)"

    se, t_stat, pval, df_res = inf["se"], inf["t"], inf["p"], inf["df_res"]
    residuals = inf["residuals"]

    # ── Coefficient DataFrame ─────────────────────────────────────────────────
    # When fit_intercept=True the intercept is the first row of the table.
    if fit_intercept:
        feat_names = ["(Intercept)"] + list(X.columns)
        coef_vals  = np.concatenate([[intercept], beta_coef])
    else:
        feat_names = list(X.columns)
        coef_vals  = beta_coef

    coef_df = pd.DataFrame({
        "Feature":     feat_names,
        "Coefficient": coef_vals,
        "Std Error":   se,
        "t-stat":      t_stat,
        "p-value":     pval,
        "Sig":         [_sig_stars(float(p)) for p in pval],
    })

    # ── Overall stats ─────────────────────────────────────────────────────────
    n_params   = len(feat_names)   # includes intercept when fit_intercept=True
    fitted     = X_arr @ beta_coef + intercept
    stats_dict = _model_stats(y_arr, residuals, n_params, fit_intercept,
                               df_res_override=df_res)

    return {
        "coef_df":       coef_df,
        "stats":         stats_dict,
        "fitted":        fitted,
        "residuals":     residuals,
        "model_type":    model_type,
        "params":        params,
        "pvalue_method": pvalue_method,
    }
