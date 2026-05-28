# Changelog

All notable changes to BudgetIQ are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

---

## [0.9.0] — 2026-05-28

### Added
- **Multi-city location support** — cost-of-living data, petrol prices, rent/groceries/restaurant indices, and ML budget suggestions are now calibrated per city rather than fixed to Hyderabad. 16 Indian cities are supported out of the box: Ahmedabad, Bangalore, Chandigarh, Chennai, Coimbatore, Delhi, Hyderabad, Indore, Jaipur, Kochi, Kolkata, Lucknow, Mumbai, Pune, Surat, Visakhapatnam.
- **Location picker in Settings** — a new section at the top of the Settings page shows the currently active city and a dropdown to switch to any supported city. The choice is saved with the rest of the settings form and persists across sessions.
- **"Detect My Location" button** — uses the browser Geolocation API to obtain the device's coordinates, then calls the new `/api/detect-location/` endpoint to reverse-geocode them (via OpenStreetMap Nominatim) to the best-matching supported city. The result is auto-populated in the dropdown; the user can still override it before saving.
- **`/api/detect-location/` endpoint** — `GET /api/detect-location/?lat=<lat>&lon=<lon>` accepts coordinates, calls Nominatim with a `User-Agent` header, resolves the city name (including alias handling for Bengaluru → Bangalore, New Delhi → Delhi, etc.), and returns `{ "city": "<name>", "supported_cities": [...] }`.
- **`CITY_BASELINES` dict in `cost_data.py`** — per-city calibrated baselines (rent index, groceries index, restaurant index, 2024 petrol base price, inflation fallback) sourced from Numbeo 2025–2026 surveys and state-level petrol pricing data.
- **`resolve_city_from_coords(lat, lon)`** in `cost_data.py` — reverse-geocodes coordinates and maps to a supported city with alias normalisation.
- **`location` field on `AppSettings`** — `CharField(max_length=100, default='Hyderabad')`; the singleton row persists the selected city.
- **`location` field on `CostSnapshot`** — each city gets its own monthly snapshot cache; `unique_together` changed from `(year, month)` to `(year, month, location)`.

### Changed
- `fetch_live_cost_data`, `get_or_fetch_cost_snapshot`, and `cost_snapshot_to_adjustments` all accept a `city` parameter and use that city's baseline instead of the hardcoded Hyderabad values.
- `get_prediction_for_month` in `ml_engine.py` reads `settings.location` and passes it through to the cost snapshot and adjustment functions so ML suggestions reflect the active city's cost structure.
- Dashboard subtitle ("Hyderabad Budget Intelligence"), empty-state text, Live Cost Data card header, and petrol price label are now dynamic — they render the active location name from context.
- Base page `<title>` tag no longer hardcodes "Hyderabad"; footer text updated to remove the city reference.
- Migration `0003_location_support` applied.

---

## [0.8.0] — 2026-05-28

### Changed
- **ML model upgraded from Ridge to Random Forest** — `_train` in `ml_engine.py` now uses `sklearn.ensemble.RandomForestRegressor` (`n_estimators=100`, `max_depth=4`, `random_state=42`) instead of a `Ridge + PolynomialFeatures + StandardScaler` pipeline. Random Forest captures non-linear patterns in spending behaviour (e.g. festive-season spikes, budget-level thresholds) that Ridge could not model. The `PolynomialFeatures` and `StandardScaler` pre-processing steps are removed as tree-based models are scale- and polynomial-invariant. The existing base-blend weighting (`min(n/12, 0.85)`), lag features, and rent-floor logic are unchanged.

---

## [0.7.0] — 2026-05-28

### Added
- **Favicon** — custom SVG bar-chart icon (`budget/static/budget/favicon.svg`, ascending bars in brand green and gold on a dark rounded background) registered as `<link rel="icon">` in `base.html`. Replaces the browser-generated "1" placeholder that appeared when bookmarking `127.0.0.1`.
- **Navbar brand icon** — the same SVG is used as an `<img>` in the navbar to the left of "BudgetIQ", keeping the header and browser tab/sidebar icon identical.
- **Delete current budget button** on dashboard — a red "Delete" button appears beside "Update Budget" whenever a budget exists for the current month. Clicking shows a browser confirmation dialog before submitting a POST to the existing `delete_budget` view. After deletion the user is returned to the dashboard (empty state) rather than History, via a `next=dashboard` POST parameter.
- **macOS background service** — `~/Library/LaunchAgents/com.budgetiq.server.plist` runs the app silently at login on `http://127.0.0.1:8080/` with `KeepAlive`, `ThrottleInterval 30`, and log output to `~/Library/Logs/BudgetIQ/server.log`. No terminal window or notifications.

### Fixed
- Allocation donut was rendering very small because the canvas had a hard `max-height: 180px` while the flex card grew around it. Fixed by making the card `d-flex flex-column`, setting the card-body to `flex: 1; min-height: 0; position: relative`, removing the canvas size constraint, and enabling `maintainAspectRatio: false` on the Chart.js config so the donut fills the full available card height.

### Changed
- `layout.padding` on the dashboard Allocation donut increased from 38 → 50 to give leader-line labels more space at the larger rendered size.
- `delete_budget` view now reads a `next` POST/GET parameter and redirects to `dashboard` or `history` accordingly (validated against an allowlist).
- `{% load static %}` added to `base.html`; Bootstrap icon `bi-graph-up-arrow` in the navbar brand replaced with the SVG favicon image.

---

## [0.6.0] — 2026-05-28

### Added
- **Living Budget card on dashboard** — new card above the Allocation donut showing the discretionary spending budget: Total Budget − Investment − Rent − Loan EMI. Displays the resulting amount prominently in gold with a compact formula breakdown below it (each fixed deduction labelled inline).
- Right column of the dashboard split breakdown is now a flex column (`d-flex flex-column`) whose three cards — Living Budget, Allocation, Live Cost Data — fill the full height of the adjacent Category Splits card.

### Changed
- `dashboard` view now prefetches `splits` on `current_budget` and computes `living_budget`, `investment_amt`, and `emi_amt` in Python before passing them to the template.
- Allocation donut canvas height reduced to 180 px (from 220 px) to accommodate the Living Budget card above it.

---

## [0.5.0] — 2026-05-28

### Added
- **Live Cost Data card on dashboard** — CPI inflation, petrol price, rent index, and groceries index now shown below the Allocation donut whenever a budget is set for the current month.
- **Force-refresh cost data on prediction** — every time "Get AI Split Suggestion" is clicked, the cached cost snapshot for that month is deleted and re-fetched from live sources; the ML model is re-trained on all saved history in the same call.
- **Indian number formatting** — all displayed currency amounts now use the Indian comma convention (e.g. ₹1,30,000.00) via a custom `indian_number` Django template filter across all pages (dashboard, set budget, history, settings).
- `{% load budget_filters %}` added to `settings.html`.

### Changed
- Allocation donut on dashboard reduced from 280 px to 220 px to accommodate the new cost data card below it.
- Allocation donut is no longer `h-100` (full-height card), giving it a more compact appearance.

---

## [0.4.0] — 2026-05-27

### Added
- **12-colour category palette** — each of the 12 categories now has a visually distinct colour (emerald, amber, cornflower, coral, violet, orange, teal, magenta-pink, terracotta, periwinkle, silver-grey, slate); replaces the earlier palette where Home and Groceries shared the same green and two categories shared pink.
- **Leader-line labels on both donuts** — the Allocation donut (dashboard) and Live Preview donut (set budget) now draw labelled leader lines (radial line → horizontal line → filled-circle arrowhead → label text) for every segment ≥ 5 %. Left-side labels are clamped to the canvas edge and shifted upward if they would overflow.
- **Rent stat pill** on dashboard shows the exact configured `rent_amount` with label "Rent" and sub-text "per month".
- **`step: '0.01'`** on all currency and percentage input fields so two-decimal values are accepted without browser validation warnings.
- **Fixed EMI amount computation** — the Loan EMI category amount is derived from the fixed `emi_amount` setting rather than back-computing from the rounded percentage, eliminating the ₹3 rounding error (e.g. ₹28,171 vs ₹28,168).

### Fixed
- Bootstrap 5.3 table cell colour was rendering black due to the high-specificity `--bs-table-color` CSS variable. Fixed by overriding `--bs-table-color`, `--bs-table-striped-color`, and `--bs-table-hover-color` on `.table`, plus adding `.table > :not(caption) > * > * { color: var(--fin-text); }` to win the cascade.
- Category Splits progress bars were misaligned because `cat-name` used `flex: 1`. Fixed with explicit `width: 115px; flex-shrink: 0` on `cat-name` and `width: 90px; flex-shrink: 0` on `cat-amt`.
- Leader-line label for large left-side segments (e.g. Loan EMI at ~33 %) was cropped at the canvas left edge. Fixed by clamping `tx` to `labelWidth + 6` and shifting the label up 10 px when it would overflow.

### Changed
- Progress bar CSS class names changed from ad-hoc colour names to `c1`–`c12` to match the new 12-colour system.
- Text muted colour brightened: `--fin-muted: #adbac7`, `--fin-text-soft: #dde3ea`.

---

## [0.3.0] — 2026-05-26

### Added
- **AppSettings model** — stores `rent_amount`, `emi_amount`, `emi_end_year`, `emi_end_month`; singleton row enforced via `update_or_create`.
- **Loan EMI category** — 12th category `emi` added alongside the existing 11. Fixed amount (₹28,168 default) deducted from total budget before any ML split is computed. EMI is automatically zeroed after the configured end month.
- **Investment auto-escalation** — fixed investment amount (₹50,000 default) escalates 10 % each April from FY 2026–27 onward. Investment is skipped entirely if the budget is too low to cover rent after paying investment + EMI.
- **Rent floor** — home allocation is guaranteed to be at least `rent_amount`; shortfall is distributed proportionally across other ML categories.
- **Settings page** (`/settings/`) — form to update rent, EMI amount, and EMI end date; read-only summary of the current investment rule.
- **Fixed-expense breakdown bar** on set-budget step 2 — shows Budget − Investment − Loan EMI = Spendable, plus the home rent floor.
- **Month-over-month comparison chart** on dashboard — grouped bar chart comparing current vs previous month's category amounts (shown from the second recorded month onward).
- **`is_dummy` flag** on `MonthlyBudget` — seed/test records are marked `is_dummy=True`; all dashboard, history, and recent-months queries filter to `is_dummy=False` only.

### Changed
- `get_prediction_for_month` returns `investment`, `emi`, `rent`, and `inv_params` so the set-budget view can display exact fixed amounts.
- `pct_to_amounts` derives investment and EMI from fixed amounts (not from percentages) to avoid rounding drift.

---

## [0.2.0] — 2026-05-25

### Added
- **ML prediction engine** (`ml_engine.py`):
  - 0 months of history → Hyderabad base allocations.
  - 1–2 months → blended rolling average weighted by `α = n / 3`.
  - 3+ months → per-category Ridge regression (scikit-learn) with polynomial features, standard scaling, seasonal lag features, and a base-blend cap of 0.85. *(Upgraded to Random Forest in v0.8.0.)*
- **Seasonal multipliers** for months 1, 3, 4, 7, 8, 10, 11, 12 covering shopping, travel, entertainment, food, and groceries.
- **Live cost data** (`cost_data.py`) — fetches India CPI and inflation from the World Bank API, estimates Hyderabad petrol price, and computes Numbeo-style rent/groceries/restaurant indices. Results cached in the `CostSnapshot` model for the month.
- **`CostSnapshot` model** — stores per-month cost indicators; used to adjust base category weights via `cost_snapshot_to_adjustments`.
- **Prediction API endpoint** — `GET /api/predict/?budget=&year=&month=` returns category percentages and amounts as JSON.
- **Model info badge** on set-budget step 2 — shows which strategy was used (base, blended, or ML) and whether live cost data was fetched.
- **Market Data Used card** on set-budget step 2 — displays CPI inflation %, petrol price, and rent cost index used in the current prediction.

### Changed
- `BudgetInputForm` and `SplitAdjustmentForm` use Bootstrap 5 styled widgets.

---

## [0.1.0] — 2026-05-24

### Added
- Initial Django project (`budgeting_tool`) with `budget` app.
- **Models**: `MonthlyBudget` (year, month, total\_budget, notes, is\_dummy), `BudgetSplit` (category, amount, percentage, icon).
- **11 spending categories**: Groceries, Transport, Food & Dining, Healthcare, Home, Entertainment, Subscriptions, Shopping, Travel, Investment, Other.
- **Set Budget flow** (two steps):
  1. Enter total monthly budget and optional notes.
  2. Review AI-suggested percentage splits, adjust sliders, confirm and save.
- **Live Preview donut** on set-budget step 2 with real-time percentage and amount labels.
- **Dashboard** with category splits (coloured progress bars), allocation donut chart, monthly budget trend bar chart, and a recent months table.
- **History page** with a total-budget trend line chart, stacked category allocation chart (%), and full monthly detail table with edit and delete actions.
- **Dark theme** — GitHub-inspired palette (`#0d1117` background, `#00c896` emerald primary, `#f0b429` gold accent).
- **`indian_number` template filter** skeleton; `get_item` and `get_field` filters for form rendering.
- Django management command `load_dummy_data` for seeding test records.
