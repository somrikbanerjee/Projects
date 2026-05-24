# Changelog

All notable changes to MMM Tool are documented here.

---

## v0.3.1 — UI Polish

### Added

- **Section completion indicators** — every numbered expander gains a blue left border once its section has been configured (e.g. Upload Dataset highlights after a file is loaded, Grouping Columns highlights after at least one group key is chosen). This gives an at-a-glance view of how far through the workflow you are.

### Changed

- **Multiselect tag spacing** — increased inner padding of the tag row so the first character of the first selected tag is no longer clipped at the container edge regardless of browser or display scaling.

### Removed

- **Dark mode** — the custom `@media (prefers-color-scheme: dark)` CSS block has been removed. The app is light-mode only. Streamlit's built-in dark theme can still be toggled via the Streamlit settings menu, but custom styling will not adapt to it.

---

## v0.3.0 — Tab 3: Prior Modeling

### Added

#### New module — `utils/modelling.py`

Statistical modelling backend for Tab 3. All models fitted via scikit-learn so that `positive` and `fit_intercept` are supported uniformly. Inference is derived analytically:

- **`fit_model(X, y, model_type, params) → dict`** — public API; returns `coef_df`, `stats`, `fitted`, `residuals`, `model_type`, `params`, `pvalue_method`.
- **`_ols_inference`** — exact OLS covariance `Cov(β) = σ² (X'X)⁻¹`; used for LinearRegression (unconstrained).
- **`_ridge_inference`** — sandwich covariance `Cov(β) ≈ σ² (X'X+αI)⁻¹ X'X (X'X+αI)⁻¹`; effective residual df from hat-matrix trace (Hastie, Tibshirani & Friedman §3.4).
- **`_active_set_inference`** — active-set OLS approximation for Lasso / ElasticNet / constrained OLS (`positive=True`): refit OLS on the non-zero coefficient support; zero (inactive) coefficients report `NaN`.
- **`_model_stats`** — R², Adj. R², F-statistic, F p-value, AIC, BIC, RMSE, MAE, n_obs, df_residual.
- **`_sig_stars`** — `***` / `**` / `*` / `.` significance markers.

#### Tab 3 — Prior Modeling (fully implemented)

**① Feature Selection**
- Multiselect from all available features: Tab 1 input channels (after any in-place Tab 2 transforms) and new columns created by Tab 2 (adstock / norm / saturation), colour-coded by origin.
- Target column auto-inherited from Tab 1 → ⑧; rows with missing values excluded before fitting with a count caption.

**② Model & Hyperparameters**
- Reactive — all widgets outside any form; model results update immediately on every parameter change.

| Model | Exposed hyperparameters |
|---|---|
| Linear Regression | `fit_intercept`, `positive` |
| Ridge | `fit_intercept`, `positive`, `alpha` |
| Lasso | `fit_intercept`, `positive`, `alpha`, `max_iter` |
| ElasticNet | `fit_intercept`, `positive`, `alpha`, `l1_ratio`, `max_iter` |

**Model Results (right panel)**
- **P-value method** note: identifies the inference approach used (exact OLS / Ridge sandwich / active-set OLS).
- **Coefficient Estimates table**: Feature, Coefficient, Std Error, t-stat, p-value (scientific notation for values < 0.001), Sig stars, with significance legend.
- **Model Statistics**: R², Adj. R², RMSE, MAE as metric cards; n observations, n parameters, df residual, F-statistic, F p-value, AIC, BIC in a secondary table.

#### Styling
- New CSS classes: `.coef-tag` (blue), `.model-stat-card`, `.model-stat-label`, `.model-stat-value`, `.pval-method-note` (cyan left-border).

#### Dependencies
- Added `scikit-learn ≥ 1.4` and `scipy ≥ 1.12` to requirements; replaced `statsmodels` (previously listed but unused).

---

## v0.2.1 — Tab 2 Refinements

### Changed

- **Date Filter moved after Transformations** — section order in Tab 2 is now ① Media Channels → ② Transformations → ③ Date Filter.
- **Pipeline execution order reversed** — Tab 2 signal transforms now run on the *full* date range first; the date filter is applied afterwards. This ensures adstock carry-over from early periods is computed correctly before the analysis window is narrowed. A note in the ③ Date Filter expander explains this behaviour.
- **Column scope restricted to Tab 1 input channels** — the media channel multiselect (①) and the source column selector in the Transformations form (②) now only expose the columns declared as **Input / media channels** in Tab 1 → ⑧. If no input channels have been set yet, a warning is shown and all Tab 1 columns are displayed as a fallback.

---

## v0.2.0 — Tab 2: Adstock & Saturation

### Added

#### New module — `utils/adstock.py`
- **Adstock weight functions**: `geometric_weights`, `weibull_weights`, `hill_weights`.
- **Causal convolution**: `apply_adstock_1d` — `y[t] = Σ w[l] · x[t−l]`, capped at max lags N.
- **Saturation**: `neg_exp_saturation` — `f(x) = c · (1 − exp(−d · x))`.
- **`build_output_col`** — derives output column name from source + transform type; adstock/norm/saturation append a suffix; all other types return the source name unchanged (in-place overwrite).
- **`CREATES_NEW_COLUMN`** — exported frozenset `{"adstock", "norm", "saturation"}` used by both the pipeline and UI.
- **`apply_tab2_transformations`** — full Tab 2 pipeline: applies a list of transforms in order; group-aware where applicable.

#### Tab 2 — Adstock & Saturation (fully implemented)

**① Media Channels**
- Multiselect from Tab 1 input channels to designate media/channel variables.
- Adstock and saturation transforms are only available for media channels and columns derived from them.
- Target variable and grouping columns are auto-inherited from Tab 1 → ⑧ and ③ respectively.

**② Transformations**
- Add any number of transforms in any order.
- Transform type selector placed **outside** the form so parameter fields update immediately on type change.
- Adstock method selector also outside the form, so geometric/Weibull/Hill parameter fields render dynamically.

| Transform | New column? | Suffix | Group-aware | Availability |
|---|---|---|---|---|
| Adstock (geometric) | ✓ | `_adstock` | — | Media channels only |
| Adstock (Weibull) | ✓ | `_adstock` | — | Media channels only |
| Adstock (Hill) | ✓ | `_adstock` | — | Media channels only |
| Saturation | ✓ | `_saturation` | — | Media channels only |
| Normalisation (minmax/mean/z-score) | ✓ | `_norm` | Yes | All input channels |
| Lag | in-place | — | Yes | All input channels |
| Lead | in-place | — | Yes | All input channels |
| Moving Average | in-place | — | Yes | All input channels |
| Mean Centering | in-place | — | Yes | All input channels |
| Zero Mask (by target) | in-place | — | — | All input channels |

- **Suffix chaining** — suffixes accumulate in the order transforms are added (e.g., `TV_adstock_norm_saturation`).
- **In-place transforms** — lag, lead, MA, mean-centering, and zero mask overwrite the source column directly; no new column is created.
- Delete any transform with the **✕** button.

**③ Date Filter**
- Calendar date-pickers (Start date / End date) to narrow the output to an analysis window.
- Default values = actual min/max dates in the dataset.
- Row-count feedback shows how many rows fall within the selected range.
- Applied *after* Tab 2 transforms so the full history is available for adstock carry-over calculations.

**Live Preview (right panel)**
- Shows the fully transformed and filtered dataset.
- New columns created by Tab 2 (adstock / norm / saturation) are highlighted as amber tags above the table.
- **⬇ CSV** and **⬇ XLSX** download buttons in the right panel (in addition to the nav bar).

#### `get_processed_df()` updated
- Refactored into `_get_tab1_df()` (Tab 1 pipeline only) + `get_processed_df()` (full pipeline: Tab 1 → Tab 2 transforms → date filter).
- Tab 1 live preview uses `_get_tab1_df()` so Tab 2 transforms don't bleed into the Tab 1 preview.

#### Styling
- New CSS tag class `.t2-tag` (amber) for Tab 2 new-column names.
- New CSS tag class `.media-tag` (pink) reserved for future media channel labels.

---

## v0.1.0 — Initial Release

### Added

#### Application Shell
- Streamlit-based single-page app with a two-tab layout: **Data Preprocessing** and **Adstock & Saturation**.
- Top and bottom navigation bars with **◀ Prev** / **Next ▶** buttons to move between tabs.
- **Download CSV** and **Download XLSX** buttons embedded in both navigation bars — available on every tab at all times.
- Gradient app header banner (title + subtitle + beta badge).
- Custom CSS design: soft blue-grey page background, white card-style expanders with shadows, styled primary/download/form-submit buttons, pill-shaped active tab indicator.
- All Streamlit chrome (header bar, footer bar, toolbar, deploy button) hidden for a clean full-page look.

#### Tab 1 — Data Preprocessing

**① Upload Dataset**
- Accepts `.csv`, `.xlsx`, and `.xls` files.
- On new upload, all transformation configurations are automatically reset.

**② Convert to Datetime**
- Multi-select any columns to cast to `datetime64`.

**③ Grouping Columns**
- Multi-select columns to use as group keys for grouped normalisation (mean, minmax, z-score).

**④ Pivot Dataset**
- Optional pivot with configurable index columns, column-header source column, values column, and aggregation function (`sum`, `mean`, `first`, `max`, `min`).
- Post-pivot column names are flattened from any MultiIndex automatically.

**⑤ Calculated Columns**
- Add any number of derived columns with four operation types:
  - **lag / lead** — shift a column by N rows (optionally within groups); NaN filled with 0.
  - **add** — element-wise sum of two or more columns.
  - **multiply** — element-wise product of two or more columns.
  - **multiply scalar** — multiply a column by a constant.
- Each entry can be individually deleted.
- Operation type selector placed **outside** the form so the relevant input fields render immediately on change without requiring a form submit.

**⑥ Normalise Columns**
- Five normalisation methods, all overwriting the source column in place as `float64`:
  - **minmax** — `(x − min) / (max − min)`, group-aware.
  - **mean** — `x / mean(x)`, group-aware.
  - **z-score** — `(x − mean) / std`, group-aware.
  - **scalar** — `x / constant`.
  - **column** — divide a set of columns element-wise by a single divisor column.
- When grouping columns are set, mean / minmax / z-score normalise within each group; when no grouping is set, the entire series is used.
- Method selector placed **outside** the form so fields swap immediately on method change.
- Default method pre-selected as **minmax**.
- Grouping context shown in the add-form and display list for all methods.

**⑦ Sort Data**
- Add multiple sort keys with independent ascending/descending order per key.
- Keys are applied in the order listed.

**⑧ Input & Target Columns**
- Single-select **target column** (KPI / dependent variable).
- Multi-select **input / media channels** (independent variables).

**Live Preview**
- Right-side panel updates automatically on every configuration change, showing up to 200 rows.
- Expandable column-type inspector below the preview table.

**Input ↔ Target Charts**
- Full-width chart section rendered below the configuration/preview area when both input and target columns are selected.
- Chart type chosen automatically per column dtype:
  - **Numeric** → scatter plot with OLS trend line.
  - **Datetime** → line chart.
  - **Categorical / low-cardinality** → vertical bar chart with mean target per category.
- All charts are interactive: hover tooltips with x/y values, zoom, pan.

#### Tab 2 — Adstock & Saturation
- Placeholder tab accessible via navigation.
- Dataset processed in Tab 1 persists and is available here via the download buttons in the nav bar.

#### Dummy Dataset
- `data/dummy_data.csv` and `data/dummy_data.xlsx` included for testing.
- Schema: `MONTH_DT`, `REGION`, `SALES_VALUE`, `INTERACTION_CHANNEL`, `NUMBER_OF_INTERACTIONS`.
- 480 rows: 4 regions × 24 months × 5 channels.

### Fixed
- Calculated-column operation type selector and normalisation method selector moved outside their respective `st.form` containers — Streamlit forms freeze widget state until submit, so the dynamic field switching was broken when the selectors were inside the form.
- Normalisations now overwrite source columns rather than creating `_norm`-suffixed copies.
- All normalisation outputs explicitly cast to `float64`.
- `mean` normalisation formula corrected from z-score `(x − μ) / σ` to `x / μ`.
- "Dataset carried over from Tab X" preview removed from Tab 2.
- Navigation bar white bars removed — `st.markdown('<div ...>')` renders as a standalone empty element in Streamlit and cannot wrap widget columns; the wrapper divs were removed.
- `column`-type normalisation redesigned to accept multiple source columns (multi-select) divided by a single divisor column; output column names no longer appended with `_by_<divisor>`.
