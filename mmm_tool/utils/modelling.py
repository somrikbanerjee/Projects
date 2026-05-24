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
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import ElasticNet, Lasso, LinearRegression, Ridge
from sklearn.ensemble import RandomForestRegressor as _RF

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
    """Exact OLS inference for ``beta`` given the *augmented* design matrix."""
    n, k = X_aug.shape
    residuals = y - X_aug @ beta
    df_res = max(n - k, 1)

    s2 = np.sum(residuals ** 2) / df_res
    try:
        XtX_inv = np.linalg.pinv(X_aug.T @ X_aug)
        se = np.sqrt(np.maximum(s2 * np.diag(XtX_inv), 0.0))
    except Exception:
        se = np.full(k, np.nan)

    with np.errstate(invalid="ignore", divide="ignore"):
        t = beta / se
        p = 2.0 * stats.t.sf(np.abs(t), df_res)

    return {"se": se, "t": t, "p": p, "df_res": float(df_res), "residuals": residuals}


def _ridge_inference(
    X: np.ndarray,
    y: np.ndarray,
    beta_coef: np.ndarray,
    intercept: float,
    alpha: float,
    fit_intercept: bool,
) -> dict:
    """Sandwich covariance for Ridge: Cov(β) ≈ σ² (X'X+αI)⁻¹ X'X (X'X+αI)⁻¹.

    Effective df = trace of hat matrix  H = X (X'X+αI)⁻¹ X'.
    """
    n, k = X.shape
    residuals = y - (X @ beta_coef + intercept)

    XtX = X.T @ X
    A = XtX + alpha * np.eye(k)
    try:
        A_inv = np.linalg.pinv(A)
    except Exception:
        return _fallback_inference(beta_coef, intercept, fit_intercept, residuals, n)

    # Effective df from hat-matrix trace (feature part only)
    df_fit = float(np.trace(XtX @ A_inv))
    if fit_intercept:
        df_fit += 1.0            # account for the intercept
    df_res = max(n - df_fit, 1.0)

    s2 = np.sum(residuals ** 2) / df_res

    # Sandwich covariance for feature coefficients
    cov_beta = s2 * (A_inv @ XtX @ A_inv)
    se_coef = np.sqrt(np.maximum(np.diag(cov_beta), 0.0))

    if fit_intercept:
        se_int = np.sqrt(max(s2 / n, 0.0))        # centred-design approximation
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

    For non-zero coefficients, refit OLS on that sub-design and report
    exact p-values.  Zero (inactive) coefficients get NaN.
    """
    n = len(y)
    k_total = len(beta_coef) + (1 if fit_intercept else 0)
    residuals = y - (X @ beta_coef + intercept)

    active = np.where(np.abs(beta_coef) > 1e-10)[0]

    se_out = np.full(k_total, np.nan)
    t_out  = np.full(k_total, np.nan)
    p_out  = np.full(k_total, np.nan)

    if len(active) == 0:
        df_res = max(n - k_total, 1)
        return {"se": se_out, "t": t_out, "p": p_out, "df_res": float(df_res),
                "residuals": residuals}

    X_A = X[:, active]
    if fit_intercept:
        X_A_aug = np.column_stack([np.ones(n), X_A])
        beta_A  = np.concatenate([[intercept], beta_coef[active]])
    else:
        X_A_aug = X_A
        beta_A  = beta_coef[active]

    inf = _ols_inference(X_A_aug, y, beta_A)
    se_A, t_A, p_A = inf["se"], inf["t"], inf["p"]
    df_res = inf["df_res"]

    if fit_intercept:
        se_out[0] = se_A[0]
        t_out[0]  = t_A[0]
        p_out[0]  = p_A[0]
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
    """Return NaN inference when matrix operations fail."""
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
    """TreeSHAP-based 'beta' inference for ensemble tree models.

    Coefficient = mean SHAP value across observations — the average marginal
                  contribution of each feature to the model output, relative
                  to the SHAP base value E[f(x)].
    SE          = std(SHAP values across observations) / √n
                  — standard error of the sample mean SHAP.
    t-stat      = mean_SHAP / SE.
    p-value     = two-sided t-test, H₀: mean contribution = 0,  df = n − 1.

    The test is a standard one-sample t-test on the empirical distribution of
    per-observation SHAP values.  A significant p-value means the feature's
    average directional push on the model output is unlikely to be zero by
    chance across the observed data.

    When ``positive_coef=True`` mean SHAP values are clipped to ≥ 0 before
    computing SE / t / p (post-hoc; the underlying tree model is unconstrained).
    When ``positive_intercept=True`` the SHAP base value is clipped to ≥ 0.
    """
    n, k = X_arr.shape
    fitted    = mdl.predict(X_arr).astype(float)
    residuals = y_arr.astype(float) - fitted
    _nan_inf  = {
        "se": np.full(k, np.nan), "t": np.full(k, np.nan),
        "p":  np.full(k, np.nan), "df_res": float(max(n - k, 1)),
        "residuals": residuals,   "base_value": float(np.mean(y_arr)),
        "mean_shap": np.full(k, np.nan),
    }

    if not _HAS_SHAP:
        return _nan_inf

    try:
        explainer  = _shap.TreeExplainer(mdl)
        sv         = np.array(explainer.shap_values(X_arr), dtype=float)  # (n, k)
        base_value = float(np.atleast_1d(explainer.expected_value)[0])
    except Exception:
        return _nan_inf

    mean_shap = sv.mean(axis=0)                               # (k,)

    # ── Post-hoc positivity constraints ───────────────────────────────────────
    if positive_coef:
        mean_shap = np.maximum(mean_shap, 0.0)
    if positive_intercept:
        base_value = max(base_value, 0.0)

    std_shap  = sv.std(axis=0, ddof=1)                        # (k,)
    se        = np.where(std_shap > 1e-12, std_shap / np.sqrt(n), np.nan)

    with np.errstate(invalid="ignore", divide="ignore"):
        t = mean_shap / se
        p = 2.0 * stats.t.sf(np.abs(t), df=float(n - 1))

    return {
        "se":         se,
        "t":          t,
        "p":          p,
        "df_res":     float(max(n - k, 1)),
        "residuals":  residuals,
        "base_value": base_value,
        "mean_shap":  mean_shap,
    }


# ─────────────────────── OVERALL MODEL STATISTICS ────────────────────────────

def _model_stats(
    y: np.ndarray,
    residuals: np.ndarray,
    n_params: int,
    fit_intercept: bool,
    df_res_override: float | None = None,
) -> dict:
    """R², adj-R², F-stat, AIC, BIC, RMSE, MAE."""
    n   = len(y)
    rss = float(np.sum(residuals ** 2))
    tss = float(np.sum((y - y.mean()) ** 2)) if fit_intercept else float(np.sum(y ** 2))

    k      = n_params - (1 if fit_intercept else 0)      # feature count
    df_res = df_res_override if df_res_override is not None else max(n - n_params, 1)

    r2     = (1.0 - rss / tss) if tss > 0 else np.nan
    adj_r2 = (1.0 - (1.0 - r2) * (n - (1 if fit_intercept else 0)) / df_res
              ) if (tss > 0 and df_res > 0) else np.nan

    # F-statistic  (based on ESS)
    if k > 0 and df_res > 0 and tss > 0 and rss > 0:
        ess    = tss - rss
        f_stat = (ess / k) / (rss / df_res)
        f_pval = float(stats.f.sf(f_stat, k, df_res))
    else:
        f_stat = np.nan
        f_pval = np.nan

    # AIC / BIC via Gaussian log-likelihood
    if rss > 0:
        log_lik = -0.5 * n * (np.log(rss / n) + 1.0 + np.log(2.0 * np.pi))
        aic = float(-2.0 * log_lik + 2.0 * n_params)
        bic = float(-2.0 * log_lik + np.log(n) * n_params)
    else:
        aic = bic = np.nan

    return {
        "n_obs":      n,
        "n_params":   n_params,
        "df_residual": df_res,
        "r2":         r2,
        "adj_r2":     adj_r2,
        "f_stat":     f_stat,
        "f_pval":     f_pval,
        "aic":        aic,
        "bic":        bic,
        "rmse":       float(np.sqrt(rss / n)),
        "mae":        float(np.mean(np.abs(residuals))),
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
    """Fit Random Forest or XGBoost and return TreeSHAP-based inference dict."""
    n, k = X_arr.shape

    # ── Build model ───────────────────────────────────────────────────────────
    if model_type == "randomforest":
        _md = params.get("max_depth")
        max_depth    = None if (_md is None or int(_md) == 0) else int(_md)
        max_features = params.get("max_features", "sqrt")
        if max_features == "all":
            max_features = None
        mdl = _RF(
            n_estimators    = int(params.get("n_estimators",    100)),
            max_depth       = max_depth,
            min_samples_split = int(params.get("min_samples_split", 2)),
            min_samples_leaf  = int(params.get("min_samples_leaf",  1)),
            max_features    = max_features,
            random_state    = int(params.get("random_state", 42)),
            n_jobs          = -1,
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
            n_estimators    = int(params.get("n_estimators",   100)),
            max_depth       = int(params.get("max_depth",        6)),
            learning_rate   = float(params.get("learning_rate", 0.3)),
            subsample       = float(params.get("subsample",      1.0)),
            colsample_bytree= float(params.get("colsample_bytree", 1.0)),
            reg_alpha       = float(params.get("reg_alpha",  0.0)),
            reg_lambda      = float(params.get("reg_lambda", 1.0)),
            random_state    = int(params.get("random_state", 42)),
            verbosity       = 0,
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
    inf        = _tree_shap_inference(mdl, X_arr, y_arr,
                                       positive_coef=_positive_coef,
                                       positive_intercept=_positive_int)
    beta_coef  = inf["mean_shap"]
    base_value = inf["base_value"]
    residuals  = inf["residuals"]
    df_res     = inf["df_res"]
    se, t_stat, pval = inf["se"], inf["t"], inf["p"]

    # ── Coefficient DataFrame ─────────────────────────────────────────────────
    feat_names = list(X.columns)
    coef_df = pd.DataFrame({
        "Feature":     feat_names,
        "Coefficient": beta_coef,
        "Std Error":   se,
        "t-stat":      t_stat,
        "p-value":     pval,
        "Sig": [_sig_stars(float(p)) if not np.isnan(float(p)) else "" for p in pval],
    })

    # ── Overall model stats ───────────────────────────────────────────────────
    # Use feature count as effective parameter count (lower bound; trees are
    # much more complex, so Adj-R²/AIC/BIC are approximate / optimistic).
    fitted     = mdl.predict(X_arr).astype(float)
    stats_dict = _model_stats(
        y_arr, residuals, n_params=k,
        fit_intercept=False, df_res_override=df_res,
    )
    stats_dict["base_value"] = base_value   # SHAP E[f(x)] for display

    return {
        "coef_df":       coef_df,
        "stats":         stats_dict,
        "fitted":        fitted,
        "residuals":     residuals,
        "model_type":    model_type,
        "params":        params,
        "pvalue_method": pvalue_method,
    }


# ─────────────────────── PUBLIC API ──────────────────────────────────────────

def fit_model(
    X: pd.DataFrame,
    y: pd.Series,
    model_type: str,
    params: dict,
) -> dict:
    """Fit a linear model and return coefficients, inference, and model stats.

    Parameters
    ----------
    X           : feature DataFrame (numeric, no NaN)
    y           : target Series (numeric, no NaN)
    model_type  : one of ``"linear"``, ``"ridge"``, ``"lasso"``, ``"elasticnet"``
    params      : dict of model hyperparameters; ``fit_intercept`` and
                  ``positive`` are always honoured.

    Returns
    -------
    dict with keys:
        ``coef_df``   — DataFrame: Feature / Coefficient / Std Error / t-stat / p-value / Sig
        ``stats``     — dict of overall model statistics
        ``fitted``    — np.ndarray of fitted values
        ``residuals`` — np.ndarray of residuals
        ``model_type``, ``params``, ``pvalue_method``
    """
    X_arr = X.values.astype(float)
    y_arr = y.values.astype(float)
    n, k  = X_arr.shape

    # ── Dispatch tree models ──────────────────────────────────────────────────
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

    beta_coef = np.asarray(mdl.coef_, dtype=float).ravel()   # shape (k,)
    intercept = float(np.atleast_1d(mdl.intercept_)[0])

    # ── Inference ─────────────────────────────────────────────────────────────
    if model_type == "linear" and not positive:
        # Exact OLS
        if fit_intercept:
            X_aug  = np.column_stack([np.ones(n), X_arr])
            beta_a = np.concatenate([[intercept], beta_coef])
        else:
            X_aug  = X_arr
            beta_a = beta_coef
        inf = _ols_inference(X_aug, y_arr, beta_a)
        pvalue_method = "exact OLS"

    elif model_type == "ridge":
        alpha_val = float(params.get("alpha", 1.0))
        inf = _ridge_inference(X_arr, y_arr, beta_coef, intercept,
                               alpha_val, fit_intercept)
        pvalue_method = "Ridge sandwich (hat-matrix trace)"

    else:
        # Lasso, ElasticNet, or constrained OLS (positive=True)
        inf = _active_set_inference(X_arr, y_arr, beta_coef, intercept,
                                    fit_intercept)
        if positive and model_type == "linear":
            pvalue_method = "active-set OLS (NNLS support)"
        else:
            pvalue_method = "active-set OLS (Lasso/ElasticNet support)"

    se, t_stat, pval, df_res = inf["se"], inf["t"], inf["p"], inf["df_res"]
    residuals = inf["residuals"]

    # ── Coefficient DataFrame ─────────────────────────────────────────────────
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
    n_params   = len(feat_names)
    fitted     = X_arr @ beta_coef + intercept
    stats_dict = _model_stats(y_arr, residuals, n_params, fit_intercept,
                               df_res_override=df_res)

    return {
        "coef_df":      coef_df,
        "stats":        stats_dict,
        "fitted":       fitted,
        "residuals":    residuals,
        "model_type":   model_type,
        "params":       params,
        "pvalue_method": pvalue_method,
    }
