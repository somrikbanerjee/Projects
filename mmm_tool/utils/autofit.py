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

METRIC_LABELS: dict[str, str] = {
    "r2":     "R²",
    "adj_r2": "Adj. R²",
    "rmse":   "RMSE",
    "mae":    "MAE",
    "aic":    "AIC",
    "bic":    "BIC",
}

_METRIC_HIGHER: frozenset = frozenset({"r2", "adj_r2"})


# ─────────────────────────────── TASK REGISTRY ────────────────────────────────
# Module-level dict — persists for the lifetime of the Streamlit server process.
# Keys are task_id strings; values are mutable state dicts written by the worker
# thread and read by the UI polling loop.

_TASKS: dict[str, dict] = {}


def get_task(task_id: str) -> dict | None:
    return _TASKS.get(task_id)


def cancel_task(task_id: str) -> None:
    if task_id in _TASKS:
        _TASKS[task_id]["cancel"] = True


def cleanup_task(task_id: str) -> None:
    _TASKS.pop(task_id, None)


# ─────────────────────────────── DATA HELPERS ─────────────────────────────────

def _apply_date_filter(df: pd.DataFrame, date_cfg: dict) -> pd.DataFrame:
    """Mirror of get_processed_df's date-filter logic."""
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
    """Trim df to the last n calendar months using date_col.  Falls back gracefully."""
    if not date_col or date_col not in df.columns:
        return df
    try:
        dt     = pd.to_datetime(df[date_col])
        max_dt = dt.max()
        cutoff = max_dt - pd.DateOffset(months=n)
        return df[dt > cutoff].reset_index(drop=True)
    except Exception:
        return df


# ─────────────────────────────── METRIC HELPERS ───────────────────────────────

def _compute_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    n_params: int,
) -> dict:
    """Compute R², Adj.R², RMSE, MAE, AIC, BIC from raw predictions (no SHAP)."""
    n   = len(y_true)
    res = y_true - y_pred
    rss = float(np.sum(res ** 2))
    tss = float(np.sum((y_true - y_true.mean()) ** 2))

    r2     = (1.0 - rss / tss) if tss > 0 else np.nan
    df_res = max(n - n_params, 1)
    adj_r2 = (1.0 - (1.0 - r2) * (n - 1) / df_res) if tss > 0 else np.nan
    rmse   = float(np.sqrt(rss / n))
    mae    = float(np.mean(np.abs(res)))

    if rss > 0:
        log_lik = -0.5 * n * (np.log(rss / n) + 1.0 + np.log(2.0 * np.pi))
        aic = float(-2.0 * log_lik + 2.0 * n_params)
        bic = float(-2.0 * log_lik + np.log(n) * n_params)
    else:
        aic = bic = np.nan

    return {"r2": r2, "adj_r2": adj_r2, "rmse": rmse, "mae": mae,
            "aic": aic, "bic": bic}


def _to_score(metrics: dict, metric: str) -> float:
    """Normalise to 'higher is better'."""
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

    Each model type uses the same inference method that ``fit_model`` will use
    in the final refit, so the check during search is consistent with what
    Tab 3 will display.

    Ridge → sandwich covariance  (Cov(β) ≈ σ² (X'X+αI)⁻¹ X'X (X'X+αI)⁻¹)
    Linear / Lasso / ElasticNet → active-set OLS
    Tree models → TreeSHAP t-test: H₀: mean(SHAP) = 0, df = n−1
    """
    if max_pval >= 1.0:
        return True
    try:
        n, k = X_arr.shape

        # ── Tree models ──────────────────────────────────────────────────────
        if model_type in ("randomforest", "xgboost"):
            try:
                import shap as _shap
                exp    = _shap.TreeExplainer(mdl)
                sv     = np.array(exp.shap_values(X_arr), dtype=float)  # (n, k)
                mean_sv = sv.mean(axis=0)
                std_sv  = sv.std(axis=0, ddof=1)
                se      = np.where(std_sv > 1e-12, std_sv / np.sqrt(n), np.nan)
                with np.errstate(invalid="ignore", divide="ignore"):
                    t_vals = mean_sv / se
                    p_vals = 2.0 * _scipy_stats.t.sf(np.abs(t_vals), df=float(n - 1))
                valid_p = p_vals[~np.isnan(p_vals)]
                return bool((valid_p <= max_pval).all()) if len(valid_p) > 0 else True
            except Exception:
                return True   # SHAP unavailable → accept candidate

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
        if fi:
            X_aug = np.column_stack([np.ones(n), X_arr])
            b     = np.concatenate([[ic], beta])
        else:
            X_aug = X_arr
            b     = beta

        active = np.abs(b) > 1e-12
        if not active.any():
            return True   # all coefficients zero → vacuously satisfied

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
        return True   # on any error, accept the candidate


# ─────────────────────────────── TRANSFORM SAMPLING ──────────────────────────

def _sample_col_transforms(
    col: str,
    is_media: bool,
    has_target_zeros: bool,
    rng: np.random.Generator,
) -> tuple[list[dict], str]:
    """Sample a random transform chain for one column.

    Returns (transform_list, final_column_name).
    Probabilities are tuned for typical MMM datasets.
    """
    T:   list[dict] = []
    cur: str        = col

    # 1 · Moving Average (in-place, group-aware) ───────────────────────────────
    if rng.random() < 0.35:
        win = int(rng.choice([2, 3, 4, 6, 12]))
        T.append({"source_col": cur, "type": "moving_avg",
                  "params": {"n": win}, "output_col": cur})

    # 2 · Mean Centering (in-place, group-aware) ───────────────────────────────
    if rng.random() < 0.25:
        T.append({"source_col": cur, "type": "mean_center",
                  "params": {}, "output_col": cur})

    # 3 · Lag (in-place, group-aware) ──────────────────────────────────────────
    if rng.random() < 0.35:
        n_lag = int(rng.choice([1, 2, 3, 4]))
        T.append({"source_col": cur, "type": "lag",
                  "params": {"n": n_lag}, "output_col": cur})

    # 4 · Adstock — media only (creates new column) ────────────────────────────
    if is_media and rng.random() < 0.60:
        method  = str(rng.choice(["geometric", "weibull", "hill"]))
        max_lag = int(rng.choice([2, 4, 6, 8, 12]))
        p: dict = {"method": method, "max_lag": max_lag}
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
        cur = out

    # 5 · Norm — media only (creates new column) ───────────────────────────────
    if is_media and rng.random() < 0.50:
        method = str(rng.choice(["minmax", "mean", "z-score"]))
        out    = f"{cur}_norm"
        T.append({"source_col": cur, "type": "norm",
                  "params": {"method": method}, "output_col": out})
        cur = out

    # 6 · Saturation — media only, and only when adstock already applied ────────
    # Saturation on a raw (non-adstocked) signal is not meaningful in MMM.
    if is_media and cur.endswith("_adstock") and rng.random() < 0.40:
        c_val = float(rng.uniform(0.5, 2.0))
        d_val = float(10 ** rng.uniform(-4, -1))   # log-uniform 0.0001–0.1
        out   = f"{cur}_saturation"
        T.append({"source_col": cur, "type": "saturation",
                  "params": {"c": c_val, "d": d_val}, "output_col": out})
        cur = out

    # 7 · Zero Mask (in-place) ─────────────────────────────────────────────────
    if has_target_zeros and rng.random() < 0.30:
        T.append({"source_col": cur, "type": "zero_mask",
                  "params": {}, "output_col": cur})

    return T, cur


# ─────────────────────────────── MULTI-MODEL FAST FIT ─────────────────────────

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
    """Fit the allowed model types and return the best (model_type, params, metrics).

    Tree models are always evaluated regardless of positivity constraints.
    Positivity is enforced for linear models during fitting; for tree models,
    constraint flags are stored in params so the final refit can apply
    post-hoc SHAP clipping to contributions and the base value.

    When max_pval < 1.0 candidates where any feature p-value exceeds that
    threshold are rejected — using the same inference method as fit_model:
    Ridge sandwich covariance; active-set OLS for other linear models;
    SHAP t-test for tree models.

    n_estimators is capped at 30 (RF) / 20 (XGB) during search for speed.
    """
    if allowed_models is None:
        allowed_models = _ALL_MODEL_TYPES
    from sklearn.linear_model import LinearRegression, Ridge, Lasso, ElasticNet
    from sklearn.ensemble import RandomForestRegressor

    candidates: list[tuple[float, str, dict, dict]] = []  # (score, model_type, params, metrics)

    def _add(model_type: str, mdl, p_used: dict, n_par: int) -> None:
        try:
            y_pred = mdl.predict(X_arr)
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
    alpha_r  = float(10 ** rng.uniform(-3, 2))    # Ridge alpha
    alpha_l  = float(10 ** rng.uniform(-3, 1))    # Lasso / EN alpha
    l1_ratio = float(rng.uniform(0.1, 0.9))

    lm_kw = {"fit_intercept": True, "positive": pos_coef}
    n_lin = n_features + 1  # +1 for intercept

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
    if "randomforest" in allowed_models:
        rf_depth = int(rng.choice([3, 5, 7, 0]))  # 0 → None (unlimited)
        rf_leaf  = int(rng.choice([1, 2, 3, 5]))
        # Constraint flags stored for final refit; not passed to sklearn constructor.
        rf_p = {
            "n_estimators":       30,
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
            _add("randomforest", mdl, rf_p, n_features)
        except Exception:
            pass

    if "xgboost" in allowed_models:
        try:
            from xgboost import XGBRegressor
            xgb_depth = int(rng.choice([3, 4, 5, 6]))
            xgb_lr    = float(rng.choice([0.05, 0.1, 0.2, 0.3]))
            xgb_p = {
                "n_estimators":       20,
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
        return None
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
    task = _TASKS[task_id]
    rng  = np.random.default_rng(seed)

    media_set        = set(media_cols)
    has_target_zeros = (
        bool((df[target_col] == 0).any()) if target_col in df.columns else False
    )
    pos_coef       = bool(constraints.get("positive_coefficients", False))
    pos_int        = bool(constraints.get("positive_intercept",    False))
    max_pval       = float(constraints.get("max_pval", 1.0))
    allowed_models = frozenset(
        constraints.get("allowed_models", list(_ALL_MODEL_TYPES))
    )

    best_score  = -np.inf
    best_config: dict | None = None
    start = time.time()

    try:
        for i in range(n_iter):
            # ── Cancel check ──────────────────────────────────────────────────
            if task.get("cancel"):
                break

            try:
                # ── Sample column subset ──────────────────────────────────────
                # Non-media columns are randomly included (70 % chance each).
                # All media channels are ALWAYS included — users expect every
                # declared media variable to appear in every fitted model.
                mask = rng.random(len(input_cols)) < 0.70
                for _mi, _mc in enumerate(input_cols):
                    if _mc in media_set:
                        mask[_mi] = True      # media channels are mandatory
                if not mask.any():
                    mask[int(rng.integers(0, len(input_cols)))] = True
                selected = [c for c, ok in zip(input_cols, mask) if ok]

                # ── Sample transform chain per column ─────────────────────────
                all_t: list[dict] = []
                feats:  list[str] = []
                for col in selected:
                    t_list, final = _sample_col_transforms(
                        col, col in media_set, has_target_zeros, rng
                    )
                    all_t.extend(t_list)
                    feats.append(final)

                # Deduplicate feature names (preserve order)
                seen_f: set = set()
                feats = [f for f in feats if not (f in seen_f or seen_f.add(f))]

                # ── Apply transforms on a fresh copy ──────────────────────────
                dfc = df.copy()
                if all_t:
                    dfc = apply_tab2_transformations(
                        dfc, all_t, groupby_cols, target_col
                    )

                # Apply date filter (correct adstock carry-over already computed)
                if date_filter_cfg:
                    dfc = _apply_date_filter(dfc, date_filter_cfg)

                # Trim to last 12 months before fitting
                dfc = _last_n_months(dfc, date_col, n=12)

                valid = [f for f in feats if f in dfc.columns]
                if not valid:
                    continue

                # ── Prepare X, y ──────────────────────────────────────────────
                mdf = dfc[valid + [target_col]].dropna()
                if len(mdf) < max(3, len(valid) + 1):
                    continue

                X_arr = mdf[valid].values.astype(float)
                y_arr = mdf[target_col].values.astype(float)

                # Skip zero-variance columns
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
                    task["best_config"] = best_config  # visible to UI immediately
                    task["best_score"]  = raw_val

            except Exception:
                pass

            # ── Update progress ────────────────────────────────────────────────
            elapsed = time.time() - start
            task["progress"] = (i + 1) / n_iter
            task["elapsed"]  = elapsed
            task["eta"]      = (elapsed / max(i + 1, 1)) * (n_iter - i - 1)
            task["iter"]     = i + 1

        # ── Refit best config with full inference (including SHAP for trees) ───
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
                # This is propagated back to cfg["date_filter"] in the UI so
                # Tab 2 shows the same 12-month subset the model was trained on.
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
        task["error"] = str(exc)

    finally:
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
    """Launch the auto-fit search in a background daemon thread."""
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
            task_id        = task_id,
            df             = df.copy(),   # snapshot so UI changes don't interfere
            target_col     = target_col,
            input_cols     = list(input_cols),
            media_cols     = list(media_cols),
            groupby_cols   = list(groupby_cols),
            constraints    = dict(constraints),
            metric         = metric,
            n_iter         = n_iter,
            seed           = seed,
            date_filter_cfg= date_filter_cfg,
            date_col       = date_col,
        ),
        daemon=True,
    )
    thread.start()


# ─────────────────────────────── DISPLAY HELPER ───────────────────────────────

def describe_transforms(transforms: list[dict]) -> pd.DataFrame:
    """Return a display DataFrame describing a flat transform list."""
    rows = []
    for i, t in enumerate(transforms):
        src   = t.get("source_col", "")
        ttype = t.get("type", "")
        out   = t.get("output_col", "")
        p     = t.get("params", {})
        inplace = ttype not in {"adstock", "norm", "saturation"}

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
            ps = "—"
        elif ttype == "zero_mask":
            ps = "where target = 0"
        else:
            ps = str(p)

        rows.append({
            "#":          i + 1,
            "Source":     src,
            "Transform":  ttype.replace("_", " ").title(),
            "Output":     out + (" ↩" if inplace else ""),
            "Parameters": ps,
        })

    return (
        pd.DataFrame(rows)
        if rows
        else pd.DataFrame(columns=["#", "Source", "Transform", "Output", "Parameters"])
    )
