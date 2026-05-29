# Changelog

All notable changes to BudgetIQ are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

---

## [1.0.0] — 2026-05-29

### Added

- **Money Manager backup importer** (`budget/mmbak_importer.py`) — reads `.mmbak` files (ReadBytes Money Manager Android exports) directly as SQLite databases. Finds the most recently modified file in `~/Google Drive/MoneyManager/`, extracts expense transactions for a given month by category, and upserts results into the new `MonthlyActual` / `ActualSplit` models. One record per month; newer imports overwrite older ones so the latest data always wins.

- **`MonthlyActual` and `ActualSplit` models** — parallel to `MonthlyBudget` / `BudgetSplit`; store actual category spending imported from `.mmbak` backups. `ActualSplit` records include amount, percentage, and normalised percentage (sums to exactly 100). Source filename stored for traceability. Migration `0004_monthly_actual` applied.

- **Automatic actuals import on budget set** — when the user enters a total budget in Step 1 of the Set Budget flow, the app automatically imports the previous month's actuals from the latest `.mmbak` before computing the AI suggestion. This ensures the model always retrains on the most recent real spending data before making a recommendation.

- **Previous month actuals reference panel on Set Budget Step 2** — a gold-bordered card above the split sliders shows the previous month's actual category breakdown (amounts and percentages). Lets the user compare real prior spending against the AI suggestion while adjusting.

- **Previous month actuals card on Dashboard** — a "Apr 2026 — Actual Spending" style card is always visible on the dashboard, displayed with progress bars for each category. Appears even before the current month's budget is set, giving immediate context.

- **Actuals-only months in Recent Months table and History** — months where spending was imported from `.mmbak` but no budget was explicitly set now appear in both the dashboard Recent Months table and the History page. Each such row shows a gold "Actual" badge and a `+` button to set a budget for that month.

- **Paired Budget/Actual rows in all tables** — dashboard Recent Months and History detail table show a green "Budget" row and gold "Actual" row for each month where both exist. The month label cell spans both rows.

- **Budget vs Actual total trend chart in History** — overlaid bar chart showing budgeted total (green) and actual total (gold) for the last 12 months side by side.

- **Budget / Actual toggle on History stacked chart** — two buttons switch the stacked category allocation chart between budgeted percentages and actual percentages.

- **MoM comparison chart extended** — when previous month actuals are available, a third dashed bar series is added to the Month-over-Month comparison chart on the dashboard.

- **`history_with_actual` in prediction response** — `get_prediction_for_month` now returns the count of history months that have confirmed actual spending, exposed in the API response and shown in the model info badge on Set Budget Step 2.

### Changed

- **ML model replaced: Random Forest → 1D-CNN + GRU** — the per-category Random Forest regressor is replaced by a two-stage sequence model implemented in pure NumPy (no scikit-learn dependency):
  - **1D-CNN (kernel=3, 8 filters, ReLU)** — convolves over the time axis to capture short-term month-to-month transition patterns.
  - **GRU (hidden=16)** — processes the convolved sequence to build a hidden state encoding long-range temporal dependencies (trend, drift, sustained seasonality).
  - **Linear readout** — maps the final GRU hidden state to a scalar allocation prediction per ML category.
  - Trained with ADAM (lr=3e-3, 200 epochs) and truncated BPTT (4 steps). Gradient clipping at norm 1.0.
  - For months with both a budget record and imported actuals, **actual percentages are used as training labels** (more accurate than intended splits). Actuals-only months (no budget row) are also included in training history.

- **`load_history_from_db`** now merges `MonthlyBudget` and `MonthlyActual` records. For months that have actuals, the actual split percentages replace the budget split percentages as the ML training signal. Actuals-only months are included with `total_actual` used as the budget proxy for feature engineering.

- **Dashboard view** rebuilt to unify budget and actuals data: queries both `MonthlyBudget` and `MonthlyActual` for recent months, merges them into a single `recent_rows` list (oldest-first for charts), and exposes `prev_actual_ref` for the reference card independently of whether a current budget exists.

- **History view** rebuilt to include actuals-only months: queries both models, builds a unified `history_rows` list (newest-first), and computes both `category_series` (budget %) and `actual_series` (actual %) for the chart toggle.

- **`cat-amt` CSS** — `width: 90px` → `min-width: 110px; white-space: nowrap` so large Indian-formatted amounts (e.g. ₹2,04,426.13) never wrap to a second line.

- scikit-learn is no longer a dependency.

### Fixed

- Django template error "Variables and attributes may not begin with underscores" — dynamic attribute set in the view renamed from `mb._actual` to `mb.actual_data`.

---

## [0.9.0] — 2026-05-28

### Added
- **Multi-city location support** — cost-of-living data, petrol prices, rent/groceries/restaurant indices, and ML budget suggestions are now calibrated per city rather than fixed to Hyderabad. 16 Indian cities supported: Ahmedabad, Bangalore, Chandigarh, Chennai, Coimbatore, Delhi, Hyderabad, Indore, Jaipur, Kochi, Kolkata, Lucknow, Mumbai, Pune, Surat, Visakhapatnam.
- **Location picker in Settings** — dropdown to switch to any supported city; choice persists across sessions.
- **"Detect My Location" button** — browser Geolocation API → `/api/detect-location/` → Nominatim reverse-geocode → best-matching supported city auto-populated.
- **`/api/detect-location/` endpoint** — `GET /api/detect-location/?lat=<lat>&lon=<lon>` returns `{ "city": "<name>", "supported_cities": [...] }`.
- **`CITY_BASELINES` dict** in `cost_data.py` — per-city calibrated baselines from Numbeo 2025–2026 surveys and state petrol pricing.
- **`resolve_city_from_coords(lat, lon)`** in `cost_data.py` — reverse-geocodes with alias normalisation (Bengaluru → Bangalore, etc.).
- **`location` field on `AppSettings`** and **`CostSnapshot`**; `unique_together` on `CostSnapshot` updated to `(year, month, location)`. Migration `0003_location_support` applied.

### Changed
- `fetch_live_cost_data`, `get_or_fetch_cost_snapshot`, `cost_snapshot_to_adjustments`, and `get_prediction_for_month` all accept and propagate a `city` parameter.
- Dashboard subtitle, empty-state text, cost data card label, and petrol price label render the active location name dynamically.

---

## [0.8.0] — 2026-05-28

### Changed
- **ML model upgraded from Ridge to Random Forest** — `_train` uses `RandomForestRegressor` (`n_estimators=100`, `max_depth=4`) instead of a Ridge + PolynomialFeatures + StandardScaler pipeline. Captures non-linear festive-season and budget-threshold patterns. *(Superseded by CNN-GRU in v1.0.0.)*

---

## [0.7.0] — 2026-05-28

### Added
- **Favicon** — custom SVG bar-chart icon in `budget/static/budget/favicon.svg`; used in `<link rel="icon">` and the navbar brand image.
- **Delete current budget button** on dashboard — red button with confirmation dialog; redirects back to dashboard via `next=dashboard` POST parameter.
- **macOS background service** — `~/Library/LaunchAgents/com.budgetiq.server.plist`; runs at login on `http://127.0.0.1:8080/` with `KeepAlive`, `ThrottleInterval 30`, log to `~/Library/Logs/BudgetIQ/server.log`.

### Fixed
- Allocation donut rendering too small due to hard `max-height: 180px` on canvas. Fixed with `d-flex flex-column` card, `flex: 1; min-height: 0; position: relative` on body, `maintainAspectRatio: false`.

### Changed
- `layout.padding` on Allocation donut: 38 → 50 to give leader-line labels more space.
- `delete_budget` view reads `next` POST/GET parameter and redirects to `dashboard` or `history` (allowlisted).

---

## [0.6.0] — 2026-05-28

### Added
- **Living Budget card** on dashboard — Total Budget − Investment − Rent − Loan EMI displayed prominently in gold with inline formula breakdown.
- Right column of split breakdown is now a flex column; Living Budget, Allocation, and Live Cost Data cards fill the full height.

### Changed
- `dashboard` view computes `living_budget`, `investment_amt`, `emi_amt` in Python.

---

## [0.5.0] — 2026-05-28

### Added
- **Live Cost Data card** on dashboard — CPI inflation, petrol price, rent index, groceries index.
- **Force-refresh cost data** on every "Get AI Split Suggestion" click.
- **Indian number formatting** — `indian_number` template filter across all pages.

---

## [0.4.0] — 2026-05-27

### Added
- **12-colour category palette** — each category has a visually distinct colour via `c1`–`c12` CSS classes.
- **Leader-line labels** on dashboard Allocation donut and Set Budget Live Preview donut for segments ≥ 5 %.
- **Rent stat pill** on dashboard.
- **`step: '0.01'`** on all currency/percentage inputs.
- **Fixed EMI amount computation** — derived from `emi_amount` setting, not back-computed from percentage (eliminates ₹3 rounding error).

### Fixed
- Bootstrap 5 table cell colour rendering black (overrode `--bs-table-color` cascade).
- Category Splits progress bar misalignment — explicit `width: 115px` on `cat-name`, `width: 90px` on `cat-amt`.
- Leader-line label cropped at canvas left edge for large left-side segments — clamped `tx` and shifted label up 10 px.

---

## [0.3.0] — 2026-05-26

### Added
- **`AppSettings` model** — `rent_amount`, `emi_amount`, `emi_end_year`, `emi_end_month`; singleton row.
- **Loan EMI category** — 12th category; fixed amount deducted before ML split.
- **Investment auto-escalation** — 10 % each April from FY 2026–27; skipped if budget too low to cover rent.
- **Rent floor** — home ≥ `rent_amount`; shortfall redistributed proportionally.
- **Settings page** (`/settings/`) — rent, EMI amount, EMI end date form.
- **Fixed-expense breakdown bar** on Set Budget Step 2.
- **Month-over-month comparison chart** on dashboard.
- **`is_dummy` flag** on `MonthlyBudget`; all user-facing queries filter `is_dummy=False`.

---

## [0.2.0] — 2026-05-25

### Added
- **ML prediction engine** (`ml_engine.py`) — 0 months: base; 1–2 months: blend; 3+ months: Ridge regression with polynomial features, standard scaling, seasonal lag features. *(Ridge replaced by Random Forest in v0.8.0, then by CNN-GRU in v1.0.0.)*
- **Seasonal multipliers** for months 1, 3, 4, 7, 8, 10, 11, 12.
- **Live cost data** (`cost_data.py`) — World Bank CPI/inflation, petrol estimate, Numbeo-style indices. Cached in `CostSnapshot`.
- **Prediction API** — `GET /api/predict/?budget=&year=&month=`.
- **Model info badge** and **Market Data Used card** on Set Budget Step 2.

---

## [0.1.0] — 2026-05-24

### Added
- Initial Django project with `budget` app.
- **Models**: `MonthlyBudget`, `BudgetSplit`.
- **11 spending categories**: Groceries, Transport, Food, Healthcare, Home, Entertainment, Subscriptions, Shopping, Travel, Investment, Other.
- **Set Budget two-step flow** with live preview donut.
- **Dashboard** — category splits, allocation donut, trend chart, recent months table.
- **History page** — trend line, stacked chart, detail table.
- **Dark theme** — `#0d1117` background, `#00c896` emerald, `#f0b429` gold.
- `indian_number`, `get_item`, `get_field` template filters.
