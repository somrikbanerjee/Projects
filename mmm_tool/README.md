# MMM Tool

A browser-based **Marketing Mix Modelling** workbench built with Streamlit.  
Upload your raw media and sales data, pre-process it visually, and explore input–target relationships — all without writing code.

---

## Requirements

| Dependency | Version |
|---|---|
| Python | ≥ 3.11 |
| streamlit | ≥ 1.35 |
| pandas | ≥ 2.0 |
| numpy | ≥ 1.24 |
| plotly | ≥ 5.18 |
| openpyxl | ≥ 3.1 |
| scikit-learn | ≥ 1.4 |
| scipy | ≥ 1.12 |

---

## Installation

```bash
# 1. Clone or download the project
cd mmm_tool

# 2. Install dependencies
pip install -r requirements.txt

# 3. (Optional) Generate the built-in dummy dataset
python data/create_dummy.py
```

---

## Running the App

```bash
streamlit run app.py
```

The app opens at `http://localhost:8501` by default.

> **Theme:** MMM Tool is styled for **light mode only**. If your browser or OS is set to dark mode, Streamlit's built-in theme switcher may apply a dark background to native widgets, but the custom UI elements will retain their light-mode appearance. For the intended look, set Streamlit to the Light theme via **☰ → Settings → Theme → Light**.

---

## Navigation

The app is organised into **three tabs** accessible via the **◀ Prev** and **Next ▶** buttons at the top and bottom of every page.  
The active tab is highlighted as a blue pill in the centre of the navigation bar.  
**⬇ CSV** and **⬇ XLSX** download buttons are always visible in the navigation bar — they export the fully processed dataset (including all Tab 2 transforms and the date filter) at any point during your session.

---

## Tab 1 — Data Preprocessing

Work through the numbered sections in order. The **Live Preview** panel on the right updates automatically after every change.

### ① Upload Dataset

Click **Browse files** and select a `.csv` or `.xlsx` file.  
The file is parsed immediately and the raw data appears in the preview panel.  
Uploading a new file resets all transformation settings.

> **Tip:** A sample dataset (`data/dummy_data.csv` / `data/dummy_data.xlsx`) is included for testing. It contains columns `MONTH_DT`, `REGION`, `SALES_VALUE`, `INTERACTION_CHANNEL`, and `NUMBER_OF_INTERACTIONS`.

---

### ② Convert to Datetime

Select any columns that contain dates or timestamps.  
They will be cast to `datetime64` so that time-based sorting and charts work correctly.

---

### ③ Grouping Columns

Select one or more columns to act as **group keys** for subsequent grouped normalisations.  
When group keys are set, the **mean**, **minmax**, and **z-score** normalisations are computed within each group rather than across the entire dataset.

> Example: setting `REGION` as a grouping column means MinMax normalisation produces 0–1 within each region independently.

These grouping columns are also inherited by Tab 2 for group-aware transforms (lag, lead, MA, mean-centering, normalisation).

---

### ④ Pivot Dataset

Check **Enable pivot** to reshape long-format data into wide format.

| Field | Description |
|---|---|
| Index columns | Columns that remain as row identifiers (e.g. `MONTH_DT`, `REGION`, `SALES_VALUE`) |
| Column-header source | Column whose distinct values become new column names (e.g. `INTERACTION_CHANNEL`) |
| Values column | Column whose values fill the new columns (e.g. `NUMBER_OF_INTERACTIONS`) |
| Aggregation | How to aggregate when multiple rows map to the same cell (`sum`, `mean`, `first`, `max`, `min`) |

After pivoting, the available columns in all subsequent sections update to reflect the new shape.

> **Tip:** Include your target KPI column (e.g. `SALES_VALUE`) in the **Index columns** list to preserve it after the pivot.

---

### ⑤ Calculated Columns

Create derived columns from existing ones. Select an operation type — the input fields update immediately — then give the new column a name and click **Add Column**.

| Operation | Formula | Extra inputs |
|---|---|---|
| **lag** | Previous N rows of a column (NaN → 0) | Source column, N units |
| **lead** | Next N rows of a column (NaN → 0) | Source column, N units |
| **add** | Sum of two or more columns | Columns to sum |
| **multiply** | Product of two or more columns | Columns to multiply |
| **multiply scalar** | Column × constant | Source column, scalar value |

When grouping columns are set, **lag** and **lead** are computed within each group.  
Click **✕** on any row to remove a calculated column.

---

### ⑥ Normalise Columns

Normalise numeric columns in place (source column is overwritten as `float64`). Select a method — fields update immediately — configure the parameters, then click **Add**.

| Method | Formula | Group-aware |
|---|---|---|
| **minmax** | `(x − min) / (max − min)` | Yes |
| **mean** | `x / mean(x)` | Yes |
| **z-score** | `(x − mean) / std` | Yes |
| **scalar** | `x / constant` | — |
| **column** | `x / divisor_column` (element-wise) | — |

- For **minmax**, **mean**, and **z-score**: if grouping columns are set the statistic (min/max/mean/std) is computed within each group; otherwise the entire column is used.
- For **column**: select one or more source columns and a single divisor column. Each source column is divided element-wise by the divisor and overwritten.

Click **✕** on any row to remove a normalisation.

---

### ⑦ Sort Data

Add one or more sort keys. Each key has an independent **Ascending ↑** or **Descending ↓** direction.  
Keys are applied in the order listed (first key is the primary sort).  
Click **✕** to remove a key.

---

### ⑧ Input & Target Columns

| Field | Description |
|---|---|
| **Target column** | The KPI you want to model (e.g. `SALES_VALUE`) |
| **Input / media channels** | Predictor columns (e.g. `TV`, `Email`, `Display`) |

Once both are set, the **Input ↔ Target Charts** section appears below the preview.

> **Important:** The input columns selected here are the only columns available in Tab 2. Set them before switching tabs.

---

### Input ↔ Target Charts

One interactive chart is rendered per input column:

| Input column type | Chart type |
|---|---|
| Numeric | Scatter plot with OLS trend line |
| Datetime | Line chart |
| Categorical / ≤ 15 unique values | Bar chart (mean target per category) |

All charts support **hover tooltips** (x and y values), **zoom**, and **pan**.

---

### Downloading the Processed Dataset

Use the **⬇ CSV** or **⬇ XLSX** buttons in the navigation bar at any time to export the fully transformed dataset as it currently appears in the preview.

---

## Tab 2 — Adstock & Saturation

The dataset preprocessed in Tab 1 flows through automatically. The **target column**, **grouping columns**, and **input channels** set in Tab 1 are all inherited here — no re-entry required.

> **Prerequisite:** Set your input channels in Tab 1 → ⑧ before working in this tab. Only those columns will appear as options.

### ① Media Channels

Select which of the Tab 1 input channels represent paid media/channel spend or impressions.  
**Adstock** and **saturation** transforms are restricted to these columns (and any columns derived from them).  
All other transforms (norm, lag, lead, MA, mean-centering, zero mask) are available for every input channel.

The **target variable** (from Tab 1 → ⑧) is shown here for reference.

---

### ② Transformations

Add signal transforms in any order. Each row applies one transform to one source column.

**Transforms that create a new column (suffix appended):**

| Transform | Suffix | Availability |
|---|---|---|
| Adstock — geometric | `_adstock` | Media channels only |
| Adstock — Weibull | `_adstock` | Media channels only |
| Adstock — Hill | `_adstock` | Media channels only |
| Saturation (negative-exponential) | `_saturation` | Media channels only |
| Normalisation (minmax / mean / z-score) | `_norm` | All input channels |

**Transforms that overwrite the source column in place (no new column):**

| Transform | Behaviour | Group-aware |
|---|---|---|
| **Lag** | Shifts column back N rows (NaN → 0) | Yes |
| **Lead** | Shifts column forward N rows (NaN → 0) | Yes |
| **Moving Average** | Rolling mean over N periods | Yes |
| **Mean Centering** | Subtracts the group/global mean | Yes |
| **Zero Mask** | Sets values to 0 wherever the target column = 0 | — |

**Suffix chaining example:**

```
TV  →  adstock  →  TV_adstock
        ↓
     norm  →  TV_adstock_norm
               ↓
            saturation  →  TV_adstock_norm_saturation
```

Group-aware transforms use the **grouping columns** set in Tab 1 → ③.

**Adstock methods and parameters:**

| Method | Parameters |
|---|---|
| Geometric | Decay rate α (0–1), max lags N |
| Weibull | Shape, Scale, max lags N |
| Hill | Alpha, Gamma, max lags N |

**Saturation:** negative-exponential `f(x) = c · (1 − e^(−d·x))`

| Parameter | Description |
|---|---|
| `c` | Asymptote — maximum possible value |
| `d` | Curvature — how quickly saturation is reached |

Click **✕** on any row to remove a transform.

---

### ③ Date Filter

Optionally restrict the output to an analysis sub-window.

| Field | Description |
|---|---|
| Date column | Any datetime column from the Tab 1 output |
| Start date | Calendar picker; default = earliest date in the data |
| End date | Calendar picker; default = latest date in the data |

> **Note:** All transforms in ② run on the *full* date range first — this ensures adstock carry-over from early periods is calculated correctly. The date filter is applied afterwards to trim the output window. The row count after filtering is shown below the date pickers.

---

### Downloading the Transformed Dataset

Use the **⬇ CSV** or **⬇ XLSX** buttons in the navigation bar **or** in the right-panel preview to export the fully transformed and filtered dataset at any point.

---

## Tab 3 — Prior Modeling

The fully transformed and date-filtered dataset from Tabs 1 & 2 flows through automatically.

### ① Feature Selection

Choose which columns to use as model inputs (predictors). The multiselect shows:

- **Tab 1 input channels** — as they appear after any in-place Tab 2 transforms (lag, lead, MA, mean-centring, zero mask).
- **Tab 2 new columns** — adstock, normalisation, or saturation outputs (highlighted in amber).

The **target column** (set in Tab 1 → ⑧) is shown for reference and is automatically excluded from the feature list.

Rows with missing values in any selected feature or the target are excluded before fitting.

---

### ② Model & Hyperparameters

| Model | Hyperparameters |
|---|---|
| **Linear Regression** | `fit_intercept`, `positive` |
| **Ridge** | `fit_intercept`, `positive`, `alpha` |
| **Lasso** | `fit_intercept`, `positive`, `alpha`, `max_iter` |
| **ElasticNet** | `fit_intercept`, `positive`, `alpha`, `l1_ratio`, `max_iter` |

All widgets update the model results immediately — no separate "Run" button required.

| Parameter | Description |
|---|---|
| `fit_intercept` | Include a constant (intercept) term |
| `positive` | Constrain all coefficients to be ≥ 0 |
| `alpha` | Regularisation strength (higher = smaller coefficients) |
| `l1_ratio` | Mix between Ridge (0) and Lasso (1) for ElasticNet |
| `max_iter` | Maximum solver iterations (Lasso / ElasticNet) |

---

### Model Results

**Coefficient Estimates table** — one row per parameter (including intercept if fitted):

| Column | Description |
|---|---|
| Feature | Parameter name (`(Intercept)` or column name) |
| Coefficient | Estimated β value |
| Std Error | Standard error of the estimate |
| t-stat | `Coefficient / Std Error` |
| p-value | Two-sided p-value from t-distribution |
| Sig | Significance stars: `***` < 0.001, `**` < 0.01, `*` < 0.05, `.` < 0.1 |

> For **Lasso / ElasticNet** (and `positive=True` constrained regression): coefficients shrunk exactly to zero are shown with `—` for SE / t / p (active-set OLS approximation on the non-zero support).

**Model Statistics** (displayed as metric cards + table):

| Statistic | Description |
|---|---|
| R² | Coefficient of determination |
| Adj. R² | R² adjusted for number of predictors |
| RMSE | Root mean squared error |
| MAE | Mean absolute error |
| F-statistic | Overall model significance (ESS-based) |
| F p-value | p-value for the F-test |
| AIC | Akaike information criterion (Gaussian log-likelihood) |
| BIC | Bayesian information criterion |
| n observations | Rows used in fitting (after NaN removal) |
| df residual | Residual degrees of freedom (effective for Ridge) |

**P-value methods:**

| Model | Method |
|---|---|
| Linear Regression | Exact OLS: `Cov(β) = σ² (X'X)⁻¹` |
| Ridge | Sandwich covariance: `Cov(β) ≈ σ² (X'X+αI)⁻¹ X'X (X'X+αI)⁻¹`; effective df from hat-matrix trace (Hastie, Tibshirani & Friedman §3.4) |
| Lasso / ElasticNet / constrained OLS | Active-set OLS: exact OLS refitted on the non-zero coefficient support; zero (inactive) coefficients show `—` |

---

## Project Structure

```
mmm_tool/
├── app.py                  # Main Streamlit application
├── requirements.txt
├── CHANGELOG.md
├── README.md
├── utils/
│   ├── preprocessing.py    # Tab 1 data transformation pipeline
│   ├── adstock.py          # Tab 2 adstock / saturation / signal transforms
│   ├── modelling.py        # Tab 3 linear model fitting & inference
│   └── charts.py           # Plotly chart builders
└── data/
    ├── create_dummy.py     # Script to regenerate dummy data
    ├── dummy_data.csv
    └── dummy_data.xlsx
```

---

## Walkthrough: Testing with the Dummy Dataset

The following sequence exercises all current features across both tabs.

### Tab 1

1. **Upload** `data/dummy_data.csv`.
2. **Section ②** — Convert `MONTH_DT` to datetime.
3. **Section ③** — Set `REGION` as a grouping column.
4. **Section ④** — Enable pivot: index = `[MONTH_DT, REGION, SALES_VALUE]`, header = `INTERACTION_CHANNEL`, values = `NUMBER_OF_INTERACTIONS`, aggregation = `sum`.
5. **Section ⑦** — Add sort keys: `REGION` ascending, then `MONTH_DT` ascending.
6. **Section ⑤** — Add calculated columns, for example:
   - `TV_lag1` — lag `TV` by 1
   - `Email_Social` — add `Email` + `Social`
7. **Section ⑥** — Add normalisations, for example:
   - MinMax on `TV` (grouped by `REGION`)
   - Mean on `Display` (grouped by `REGION`)
   - Column-division: normalise `Email`, `Social`, `Search` by `SALES_VALUE`
8. **Section ⑧** — Set `SALES_VALUE` as target; select `TV`, `Email`, `Social`, `Display`, `Search` as inputs.
9. Inspect the **charts** below, then download via **⬇ CSV** or **⬇ XLSX**.

### Tab 2

10. Navigate to **Adstock & Saturation** via **Next ▶**.
11. **Section ①** — Select `TV`, `Email`, `Social` as media channels.
12. **Section ②** — Add transforms, for example:
    - Source: `TV`, type: **Adstock**, method: geometric, α = 0.6, max lags = 4 → creates `TV_adstock`
    - Source: `TV_adstock`, type: **Normalisation**, method: minmax → creates `TV_adstock_norm`
    - Source: `TV_adstock_norm`, type: **Saturation**, c = 1.0, d = 0.005 → creates `TV_adstock_norm_saturation`
    - Source: `Email`, type: **Lag**, N = 1 → overwrites `Email` in place
    - Source: `Social`, type: **Mean Centering** → overwrites `Social` in place
13. **Section ③** — Set Start date and End date to narrow the analysis window if needed.
14. Inspect the **Live Preview** on the right, then download via **⬇ CSV** or **⬇ XLSX**.

### Tab 3

15. Navigate to **Prior Modeling** via **Next ▶**.
16. **Section ①** — Select features, for example: `TV_adstock_norm_saturation`, `Email`, `Social`, `Display`, `Search`.
17. **Section ②** — Choose **Linear Regression** with `fit_intercept = True`, `positive = False`.
    - Coefficient table appears immediately with SE, t-stats, and p-values.
    - Switch to **Ridge** and increase alpha to see coefficient shrinkage.
    - Try **ElasticNet** with `l1_ratio = 0.5` to observe mixed L1/L2 regularisation.
18. Inspect R², Adj. R², F-statistic, AIC, and BIC in the **Model Statistics** panel.
