# Changelog

All notable changes to BudgetIQ are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

---

## [1.0.6] — 2026-05-31

### Added

- **Auto-capping in Income Splitter** — when the page loads, balance caps are automatically derived from average monthly expenses computed from the latest `.mmbak` file:
  - HDFC = 1.5 × average monthly expenses (~6 weeks of spend float)
  - IDFC First = 1.0 × average monthly expenses (~1 month savings buffer)
  - Slice SFB = ₹25,000 (fixed small float, not expense-linked)
  - Union Bank = ₹20,00,000 (unchanged fixed ceiling)
  
  Auto-caps refresh on every page load so they always reflect the freshest data. Users can override any value in the cap table before submitting. A green info bar below the table shows the basis: *"Auto-computed from N months of expenses (avg ₹X/mo)"*.

- **`get_average_monthly_expenses(filepath)`** in `mmbak_importer.py` — queries `INOUTCOME` for all expense transactions (`DO_TYPE = 1, IS_DEL = 0`), groups by calendar month, and returns `(average_amount, n_months)`.

- **`_auto_caps(avg_monthly_expenses)`** helper in `views.py` — maps the average to per-bank cap values using the multipliers above. Falls back to `_DEFAULT_CAPS` when no mmbak data is available.

### Changed

- Income Splitter form defaults for HDFC, IDFC, and Slice caps now come from `_auto_caps()` rather than the hardcoded `_DEFAULT_CAPS` dict. Union Bank cap default remains ₹20,00,000.

### Performance

- **Dashboard no longer blocks on World Bank API calls** — `get_or_fetch_cost_snapshot` now returns immediately on every request:
  - Exact cache hit → returned directly (no network, unchanged).
  - Cache miss (any reason, including `force=True`) → spawns a daemon background thread to fetch live CPI/inflation data, then immediately returns the most recent stale snapshot for that city. If no stale snapshot exists, returns an unsaved `CostSnapshot` built from static `CITY_BASELINES` at zero latency; the background thread persists the real figures when it completes.
  - A module-level `_refresh_in_progress` set (protected by a `threading.Lock`) prevents duplicate concurrent refreshes for the same `(year, month, city)` key.
  - API request timeouts reduced from 8 s to 3 s so network failures resolve quickly in all code paths.
  - Dashboard and Set Budget response times drop from up to 16 s (two sequential 8 s timeouts) to < 10 ms in all but the very first load for a brand-new installation.

---

## [1.0.5] — 2026-05-31

### Added

- **Income Splitter tab** — new page (`/income-splitter/`) accessible from the main nav. Enter an income amount, choose which account it lands in, configure per-bank balance caps, and the app calculates how much to keep and how much to transfer to each account.

  - **Split rules**: fixed deductions (₹28,168 + ₹38,500, applied in order if the income covers them) are routed to HDFC; the remainder distributes 10 % Slice SFB / 20 % IDFC First / 20 % Union Bank / 50 % HDFC.
  - **Landing account selector** — income can land in any of the four banks; the "keep" instruction follows accordingly.
  - **Per-bank balance caps** — all four banks have configurable caps (defaults: HDFC 50 L, IDFC 20 L, Union 20 L, Slice 2 L) with a "No cap" checkbox per row. Caps are enforced after the percentage split: if a bank would exceed its cap, the overflow is redistributed to remaining banks weighted by base allocation (HDFC ≫ IDFC = Union ≫ Slice), giving the user-described ratios — e.g. HDFC + Slice capped → 50 : 50 IDFC : Union; IDFC + Slice capped → ~71 : 29 HDFC : Union.
  - **Pre-existing cap excess** — if a bank's current balance already exceeds its cap (read from the latest `.mmbak`), the excess is moved out and redistributed via the same weighted scheme. Handled automatically in both the income calculation and the dedicated Redistribute button.
  - **Redistribute Excess button** — POST action that reads the current cap configuration and shows a standalone "Cap Excess Redistribution" table without needing any income amount. Displays move-out amounts, received amounts, new balances, and a liquid-fund recommendation if all caps are simultaneously met.
  - **Liquid fund recommendation** — when all four caps are simultaneously met by the allocation, any unplaceable excess is displayed in a gold "invest in liquid fund" callout.
  - **Account balances from mmbak** — `get_all_account_balances()` added to `mmbak_importer.py`; computes each account's running balance from `INOUTCOME` transactions (`DO_TYPE` 0/7 income, 1 expense, 3 transfer-out, 4 transfer-in) joined to `ASSETS` by `assetUid`. The latest `.mmbak` is used automatically.
  - **Calculation breakdown card** — step-by-step display of deductions, distributable amount, percentage pills, and cap events.
  - **Allocation & New Balances table** — per-bank columns for cap, income allocation, current balance, and projected new balance. Rows colour-coded: green for HDFC, red for capped banks.
  - **Indian number formatting** throughout — all amounts in the Income Splitter use the existing `indian_number` / `indian_int` template filters.
  - **Bank logos** — Clearbit Logo API with branded coloured-initial fallback badges (HDFC blue, IDFC purple, Union red, Slice magenta) rendered via a JS `onerror` handler.
  - **Reset button** — clears form and results; appears once a calculation has been shown.

### Fixed

- **Weighted redistribution rounding drift** — `_weighted_redistribute` now gives the last absorber the exact arithmetic remainder (`pool − Σ others`) instead of an independently rounded share, guaranteeing that the sum of redistributed amounts always equals the source pool to the paisa.

---

## [1.0.4] — 2026-05-30

### Fixed

- **All charts blank — two JS syntax errors** — every Chart.js chart on the dashboard and history pages was silently failing to initialise due to two compounding bugs:

  1. **`PIE_LABELS = {{ categories|safe }}`** — `categories` is a Python list of tuples. Django renders it using Python's `repr`, producing `[('groceries', 'Groceries'), ...]` — a Python tuple literal, not valid JavaScript. This crashed the pie-chart `<script>` block entirely, preventing `trendChart` (in the same block) from being registered even though its canvas existed.

  2. **Missing `|safe` on all JSON template variables inside `<script>` blocks** — Django's auto-escaping converts `"` → `&quot;` in template variable output. `json.dumps` produces strings with double-quoted keys and values (e.g. `["Apr 2026", "May 2026"]`, `{"Groceries": [...]}`). Without `|safe`, these were rendered as `[&quot;Apr 2026&quot;, ...]` and `{&quot;Groceries&quot;: ...}`, which are invalid JavaScript and caused `Unexpected token '&'` parse errors. Affected variables: `chart_labels`, `mom_data.labels/curr/prev/prev_actual`, `category_series`, `actual_series` in both `dashboard.html` and `history.html`. Number-only arrays (`total_series`, `actual_totals`, `chart_totals`) required no change since `json.dumps` produces no quoted strings for numbers or `null`.

  `|safe` added to all affected variables; `PIE_LABELS` switched from `{{ categories|safe }}` (which uses Python repr) to a proper Django for-loop that builds a valid JS array of strings.

### Added

- **Dashboard Monthly Allocation Trend now shows actuals alongside budget** — `chart_actual_totals` (actual spending totals per month) added to the dashboard view context and rendered as a second gold "Actual" bar dataset alongside the existing green "Budget" bars. Months with only actuals (no budget set) show a gold actual bar; months with only a budget show a green budget bar. Card renamed "Monthly Allocation Trend" with a Budget/Actual colour legend in the header.

- **History "Category Allocation Trend" smart default mode** — the view now computes `default_stack_mode`: `'actual'` when more months have actuals than budgets, `'budget'` otherwise. The stacked chart initialises with the mode that has the most data, and `showStack(DEFAULT_STACK_MODE)` syncs the button highlight to match. Previously the chart always defaulted to "Budget" mode, appearing blank when most months were actuals-only.

- **History "Total Budget vs Actual Spending" — corrected `null` encoding** — changed `json.dumps([..., 'null'])` (which produced the JSON *string* `"null"`) to `json.dumps([..., None])` (which produces the JSON *value* `null`). The previous encoding required a `.map(v => v === 'null' ? null : v)` workaround in every chart; the workaround is now removed.

---

## [1.0.3] — 2026-05-30

### Added

- **`ADVANCE_BUDGET_DAY = 25`** constant in `views.py` — single threshold controlling when the app shifts into "next-month planning" mode.

- **`_next_ym(year, month)`** helper in `views.py` — returns `(year, month+1)` with December roll-over.

### Changed

- **After the 25th, the dashboard displays the next month** rather than the current calendar month. `year, month` in the dashboard view is set to `_next_ym(now.year, now.month)` when `now.day >= ADVANCE_BUDGET_DAY`, so every downstream computation — `current_budget` lookup, Category Splits card, Living Budget, allocation donut, MoM chart, trend chart, actuals avg cutoff — automatically resolves to the correct next-month values. Before the 25th the behaviour is unchanged.

- **Dashboard header** shows "June 2026" (not "May 2026") when in next-month mode. The subtitle appends "— planning ahead from May 30" so the user knows why the month has shifted.

- **"Set Budget" button on dashboard** links to `set_budget_month budget_year budget_month`, which is now the same as the display month — June after the 25th, current month before it. Label reads "Set Jun Budget" dynamically.

- **`set_budget` default month** — when accessed via the default URL (no explicit year/month in the path) after the 25th, the form targets next month's budget. If the user navigates directly to `/set-budget/YYYY/MM/`, the explicit month is always respected.

- **Actuals avg cutoff** in the dashboard simplified — no longer needs a separate `if after_25th` branch. Because `year, month` already equals next month after the 25th, `_compute_actual_avg(year, month)` naturally includes the current month's partial expenses (Apr + May when displaying June from May 30).

- **MoM comparison chart** now shows the correct pairing: after the 25th it compares June budget vs May budget/actual rather than May vs April.

---

## [1.0.2] — 2026-05-30

### Added

- **`get_available_months(filepath, before_year, before_month)`** in `mmbak_importer.py` — queries the .mmbak SQLite file for all distinct year-month pairs that have expense transactions and fall strictly before the given cutoff date.

- **`import_all_available_actuals(before_year, before_month)`** in `mmbak_importer.py` — calls `get_available_months` and upserts a `MonthlyActual` record for every month found. Each month's existing record is overwritten with the freshest data (idempotent). Replaces the single-month `import_actuals_for_month` call in the set-budget flow so the complete spending history from the backup is imported in one pass.

- **`_compute_actual_avg(before_year, before_month)`** helper in `views.py` — queries all `MonthlyActual` records strictly before the cutoff, averages amounts and percentages per category across however many months are available, and returns a template-ready dict with `label`, `total` (average monthly total), `splits` (`{cat: {amount, percentage}}`), and `n_months`. Used by both the dashboard and set-budget views.

### Changed

- **Set Budget Step 1** now calls `import_all_available_actuals(year, month)` instead of `import_actuals_for_month(prev_year, prev_month)`. Every month available in the latest `.mmbak` before the budget month is imported and upserted before the AI recommendation is generated. This gives the CNN-GRU model the full available spending history as training data, not just the immediately preceding month.

- **Dashboard actuals card** previously showed only the previous month's spending. It now shows the **average actual spending per category** across all imported months, with a dynamic label (e.g. "Mar–Apr 2026 · 2-month avg") and a `/mo` suffix on the total. When only one month exists the label shows that month name without an avg badge.

- **Set Budget Step 2 reference panel** previously showed only the previous month's actuals. It now shows the same averaged data (all imported months), updated label, and `n_months` count badge when more than one month is available.

- Dashboard and History **Recent Months table and charts** now automatically reflect all imported months since `import_all_available_actuals` upserts every available month — no template changes required. Each imported month appears as a gold "Actual" row (paired with a "Budget" row when a budget exists for that month).

- Three separate context variables (`prev_actual`, `prev_actual_splits`, `prev_month_label`) removed from the set-budget view; replaced by the single `actual_avg_ref` dict.

---

## [1.0.1] — 2026-05-29

### Fixed

- **Home always below rent (₹38,500)** — the previous architecture applied a rent floor inside `predict_split` on intermediate floating-point amounts, then converted back to percentages. By the time `pct_to_amounts` reconstructed rupee figures from those rounded percentages, up to ₹4.50 of precision had been lost, producing a home amount like ₹38,495.50. Replaced the fragile floor with a structural fix: rent is now deducted as a fixed amount before the ML split (alongside EMI and investment). `_ml_to_total_pcts` bakes rent into home's total-budget percentage; `pct_to_amounts` distributes `total − investment − EMI` proportionally, and home's final amount naturally comes out to rent + ML share — always above rent with no separate floor logic. `_apply_rent_floor` removed entirely.

- **Set Budget "Adjust Splits" header showed "100.0%" instead of total amount** — the card header now shows the live total in Indian rupee format (e.g. ₹1,14,060.73) rather than a percentage. The total updates in real time as the user drags sliders.

- **Displayed category amounts summed to ₹6.41 more than the budget** — the old JavaScript `resolveAmt` computed non-fixed amounts as `pct / 100 × TOTAL_BUDGET`. Because EMI and investment are exact fixed values, this effectively inflated the pool by their share. Fixed by computing non-fixed amounts as a proportional share of `ML_REM = TOTAL_BUDGET − EMI − investment`, matching the Python `pct_to_amounts` logic. Gap dropped from ₹6.41 to ₹0.00.

- **Residual ₹0.01 discrepancy between displayed amounts and budget** — even with the corrected formula, rounding 12 independent amounts to 2 decimal places and summing them can be off by ₹0.01 because `Σ round(xᵢ, 2) ≠ round(Σ xᵢ, 2)`. Fixed by switching to integer-paise arithmetic (×100) in `refreshTotals`: amounts for 11 categories are computed and rounded to the nearest paisa, then "Other" receives `ML_REM_PAISE − running_paise` as the exact integer residual. Total is always `TB_PAISE / 100 = TOTAL_BUDGET` exactly — guaranteed. Identical to the Python `ml_cats[-1] = ml_rem − running` pattern.

### Changed

- `predict_split` ML-pool is now `total − investment − EMI − rent` (was `total − investment − EMI`). `_ml_to_total_pcts` and `_total_to_ml_pcts` updated with a `rent` parameter. For historical records, home's discretionary-above-rent portion (`max(home_actual − rent, 0)`) is used as the ML training signal so the model learns discretionary home behaviour independently of the fixed rent component.
- Set Budget Step 2 fixed-expense formula bar updated from "Budget − Investment − EMI = Spendable" to "Budget − Investment − EMI − Rent = ML Pool" with a note that home receives rent + its ML share.
- `cat-amt` CSS widened from `width: 90px` to `min-width: 110px; white-space: nowrap` to prevent large Indian-formatted amounts (e.g. ₹2,04,426.13) from wrapping to a second line.

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
