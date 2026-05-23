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
| statsmodels | ≥ 0.14 |

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

---

## Navigation

The app is organised into **tabs** accessible via the **◀ Prev** and **Next ▶** buttons at the top and bottom of every page.  
The active tab is highlighted as a blue pill in the centre of the navigation bar.  
**⬇ CSV** and **⬇ XLSX** download buttons are always visible in the navigation bar — they export the fully processed dataset at any point during your session.

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

## Tab 2 — Adstock & Saturation *(coming soon)*

This tab will host adstock decay and saturation curve transformations.  
The dataset prepared in Tab 1 is carried through automatically and will be available here once the tab is implemented.

---

## Project Structure

```
mmm_tool/
├── app.py                  # Main Streamlit application
├── requirements.txt
├── CHANGELOG.md
├── README.md
├── utils/
│   ├── preprocessing.py    # Data transformation pipeline
│   └── charts.py           # Plotly chart builders
└── data/
    ├── create_dummy.py     # Script to regenerate dummy data
    ├── dummy_data.csv
    └── dummy_data.xlsx
```

---

## Walkthrough: Testing with the Dummy Dataset

The following sequence exercises all current features.

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
