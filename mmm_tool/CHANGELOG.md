# Changelog

All notable changes to MMM Tool are documented here.

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
