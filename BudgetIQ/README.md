# BudgetIQ

A personal budgeting web application for Indian cities. Enter your total available budget, and BudgetIQ uses a machine-learning model to suggest how to split it across 12 spending categories. Fixed expenses — rent, loan EMI, and investment — are deducted first; the remainder is split intelligently across everything else.

The model trains on two signals: your past budget splits **and** your actual month-by-month spending imported automatically from Money Manager (ReadBytes) `.mmbak` backup files. Actual spending data is preferred over budgeted figures when both are available, so recommendations tighten with every month of real data.

Supports 16 cities out of the box: Ahmedabad, Bangalore, Chandigarh, Chennai, Coimbatore, Delhi, Hyderabad, Indore, Jaipur, Kochi, Kolkata, Lucknow, Mumbai, Pune, Surat, Visakhapatnam.

## Features

### Budget intelligence
- **AI-suggested splits** — city base allocations for the first month, blending in your history as months accumulate, switching to a full CNN-GRU model at 3+ months
- **1D-CNN + GRU model** — a 1D convolution layer captures short-term month-to-month patterns; a GRU processes the full sequence for long-range temporal dependencies. Trained fresh on every prediction call so it always reflects the latest data
- **Actual-spending import** — each time you set a budget, the app finds the latest `.mmbak` file in `~/Google Drive/MoneyManager/`, opens it as a SQLite database, and imports **every month available** before the current budget month. All imported months are upserted as `MonthlyActual` records and immediately appear in the dashboard and history. The full multi-month spending history becomes the CNN-GRU training signal (more accurate than intended budget splits)
- **Model schedule**: 0 months → city base; 1–2 months → blend `(1−α)·base + α·actuals` (α = n/3); 3+ months → CNN-GRU weighted up to 0.85 at 12 months
- **Seasonal adjustments** — spending weights shift automatically for festive and travel months
- **Live cost data** — India CPI inflation and petrol prices fetched from the World Bank API on every prediction; per-city Numbeo-style rent, groceries, and restaurant indices applied as category multipliers

### Fixed-expense handling
- **Investment** — fixed at ₹50,000/month when budget ≥ ₹70,000; escalates 10% each April from FY 2026–27. Skipped automatically if paying it would leave less than zero after EMI and rent
- **Loan EMI** — fixed amount (₹28,168 default) deducted until a configurable end date, then zeroed automatically
- **Rent (home guarantee)** — rent is deducted as a fixed amount before the ML split. Home's final allocation = rent + home's proportional share of the ML pool, so home is always greater than rent with no fragile floor logic. ML pool = total − investment − EMI − rent; this remainder is split across all 10 ML categories including home

### Dashboard
- **After-25th next-month mode** — from the 25th of every month, the dashboard automatically shifts its "current" perspective to the following month. The header shows June 2026 (not May), the Category Splits card shows the June budget just set, the MoM chart compares June vs May, and the actuals average includes the current month's partial data. A subtitle reads "planning ahead from May 30" so the context is always clear. Before the 25th the behaviour is the standard current-month display.
- Stat pills: total budget, investment, rent
- Category splits with coloured progress bars, percentages, and amounts
- Right column: Living Budget card (total − investment − rent − EMI), allocation donut with leader-line labels, live cost data (CPI, petrol, indices)
- **Average actual spending card** — always visible on the dashboard; shows the average spending per category across all imported months (e.g. "Mar–Apr 2026 · 2-month avg"), with progress bars and a per-month average total. After the 25th, the current month's partial expenses are included in the average automatically. Grows richer as more months of history accumulate
- Month-over-month comparison chart: current budget vs previous budget and previous actuals side-by-side
- **Monthly Allocation Trend chart** — grouped bar chart showing green Budget bars and gold Actual bars per month; months with only actuals or only a budget each show their respective bar. Budget and Actual series are populated independently so no month appears blank
- Recent months table with paired Budget/Actual rows per month; actuals-only months appear with a `+` button to set a budget

### History
- **Total Budget vs Actual Spending** — overlaid grouped bar chart; green Budget bars for months with a saved budget, gold Actual bars for months with imported spending data; months can have one or both
- **Category Allocation Trend** with **Budget / Actual toggle** — stacked percentage chart; defaults to the mode (Budget or Actual) that has the most months of data so the chart is never blank on first load
- Full monthly detail table with paired Budget and Actual rows per month; actuals-only months included
- Each actual row shows the source `.mmbak` filename for traceability
- Edit and delete actions per month

### Set Budget — Step 2 (AI suggestion screen)
- Average actual spending across all available imported months shown as a reference panel (category-by-category averages with n-month badge) so you can compare real prior behaviour against the AI suggestion while adjusting splits
- Model info badge: base / blend / CNN-GRU, months of history, months confirmed by actuals
- Fixed-expense breakdown: Budget − Investment − EMI − Rent = ML Pool, with a note that home receives rent + its ML share
- Live preview donut with leader-line labels; real-time percentage and amount updates
- **Header shows total rupee amount** (₹X,XX,XXX.XX) that updates live as sliders are adjusted
- Category amounts computed using integer-paise arithmetic — the "Other" category absorbs rounding residual so the displayed amounts always sum to exactly the total budget

### Income Splitter

A dedicated tab (`/income-splitter/`) that turns a salary deposit into a precise transfer plan.

- **Split rules** — fixed deductions (₹28,168 + ₹38,500) route to HDFC first; remaining distributable splits 10 % Slice SFB / 20 % IDFC First / 20 % Union Bank / 50 % HDFC
- **Landing account** — choose which bank the income lands in; all transfer instructions follow from that choice
- **Per-bank balance caps** — configurable ceiling per account (defaults: HDFC 50 L, IDFC 20 L, Union 20 L, Slice 2 L); "No cap" toggle per row. When a bank would exceed its cap, overflow redistributes to uncapped banks weighted by base allocation (HDFC ≫ IDFC = Union ≫ Slice), giving intuitive ratios: HDFC + Slice capped → 50:50 IDFC:Union; IDFC + Slice capped → ~71:29 HDFC:Union; etc.
- **Pre-existing excess handling** — if a bank's live balance already exceeds its cap, the excess is redistributed on the same weighted scheme — shown both in the income calculation and via the standalone **Redistribute Excess** button (no income required)
- **Liquid fund callout** — if all four caps are simultaneously met, unplaceable surplus is flagged for liquid fund investment
- **Auto-capping** — on every page load, balance caps are derived automatically from average monthly expenses in the latest `.mmbak`: HDFC = 1.5× avg, IDFC = 1× avg, Slice = ₹25,000 fixed, Union = ₹20 L fixed. An info bar shows the data source and multipliers; any cap can be overridden before submitting
- **Live balances** — reads the latest `.mmbak` backup using a new transaction-based balance engine (`get_all_account_balances` in `mmbak_importer.py`)
- **Step-by-step breakdown, allocation table, and action checklist** — shows exactly what to keep and what to transfer, with projected new balances per account
- **Bank logos** — Clearbit Logo API with branded coloured-initial fallback badges

### Other
- **Multi-city support** — 16 Indian cities; all baselines calibrated per city. Change city in Settings at any time
- **Detect My Location** — one-click auto-detect via browser Geolocation + Nominatim reverse-geocode
- **Indian number formatting** — all amounts display in the Indian comma convention (₹1,30,000.00)
- **Background service** — ships as a macOS LaunchAgent; starts at login, serves on `http://127.0.0.1:8080/`
- **Non-blocking cost data** — the dashboard never waits for the World Bank API. `get_or_fetch_cost_snapshot` returns a cached or static-baseline snapshot immediately and refreshes live CPI/inflation data in a background daemon thread. API timeouts are capped at 3 s; duplicate refresh threads are deduplicated via a module-level lock

## Tech Stack

| Layer | Library / Version |
|---|---|
| Language | Python 3.14 |
| Web framework | Django 6.0.5 |
| ML | NumPy 2.4 (CNN-GRU implemented from scratch) |
| Frontend | Bootstrap 5.3 · Bootstrap Icons 1.11 · Chart.js 4.4 |
| Database | SQLite |
| Backup parsing | Python `sqlite3` stdlib (reads `.mmbak` files directly) |

> scikit-learn is no longer required — the CNN-GRU model is implemented in pure NumPy.

## Project Structure

```
budgeting_tool/
├── budget/
│   ├── models.py           # AppSettings, MonthlyBudget, BudgetSplit,
│   │                       # MonthlyActual, ActualSplit, CostSnapshot
│   ├── views.py            # Dashboard, set-budget (2-step), history, settings, API
│   ├── ml_engine.py        # 1D-CNN + GRU prediction engine; load_history_from_db
│   ├── cost_data.py        # Live cost-data fetch (World Bank, Numbeo baselines)
│   ├── mmbak_importer.py   # Money Manager backup reader; actual-spending importer;
│   │                       # account balance engine; average-expense calculator
│   ├── forms.py            # BudgetInputForm, SplitAdjustmentForm, AppSettingsForm
│   ├── urls.py             # URL routing
│   ├── static/budget/
│   │   └── favicon.svg     # Brand icon (bar chart, green/gold)
│   ├── templatetags/
│   │   └── budget_filters.py   # indian_number, indian_int, get_item, get_field
│   ├── templates/budget/
│   │   ├── base.html
│   │   ├── dashboard.html
│   │   ├── set_budget.html
│   │   ├── history.html
│   │   ├── settings.html
│   │   └── income_splitter.html
│   └── migrations/
│       ├── 0001_initial.py
│       ├── 0002_appsettings_alter_budgetsplit_category.py
│       ├── 0003_location_support.py
│       └── 0004_monthly_actual.py
└── budgeting_tool/
    └── settings.py         # Django project settings
```

## Setup

```bash
# 1. Clone / download the project
cd budgeting_tool

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install django numpy requests

# 4. Apply migrations
python manage.py migrate

# 5. Start the development server
python manage.py runserver 127.0.0.1:8080 --noreload
```

Then open `http://127.0.0.1:8080/` in your browser.

### Money Manager backup location

BudgetIQ looks for `.mmbak` files in:

```
~/Library/CloudStorage/GoogleDrive-somrik.banerjee@gmail.com/My Drive/MoneyManager/
```

The most recently modified file in that directory is used automatically. No configuration needed — if the directory is empty or unavailable, the app falls back gracefully to location-base recommendations.

## Running as a background service (macOS)

BudgetIQ is configured as a **macOS LaunchAgent** that starts automatically at login and runs silently in the background — no terminal window, no notifications.

| File | Path |
|---|---|
| Plist | `~/Library/LaunchAgents/com.budgetiq.server.plist` |
| Log | `~/Library/Logs/BudgetIQ/server.log` |
| URL | `http://127.0.0.1:8080/` |

Useful `launchctl` commands:

```bash
# Check status / PID
launchctl list com.budgetiq.server

# Restart (e.g. after code changes)
launchctl kickstart -k gui/$(id -u)/com.budgetiq.server

# Stop permanently (until next login)
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.budgetiq.server.plist

# Re-enable after stopping
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.budgetiq.server.plist

# View live logs
tail -f ~/Library/Logs/BudgetIQ/server.log
```

The server runs with `--noreload` to prevent Django's file-watcher from polling the Google Drive directory.

## Usage

1. **Dashboard** — landing page shows the current month's budget split (if set), Living Budget breakdown, allocation donut, and live cost data. The previous month's actual spending is always shown as a reference card. Below: MoM comparison chart, trend chart, and a Recent Months table with Budget/Actual paired rows.
2. **Set Budget** — enter your total monthly income. BudgetIQ automatically imports **every available month** of actuals from the latest `.mmbak` backup (including the current month's partial data when after the 25th), retrains the CNN-GRU model on the full history, and generates a suggested split. The averaged actuals across all imported months are displayed as a reference panel while you review and adjust. Before the 25th the form targets the current month; from the 25th onwards it defaults to next month.
3. **Income Splitter** — enter an income amount (e.g. salary), pick the landing bank, set per-bank balance caps, and get a precise "keep / transfer" plan. Hit **Redistribute Excess** at any time (no income needed) to see if any bank is over its cap and where to move the excess. The app reads live balances from the latest `.mmbak` backup automatically.
4. **History** — all recorded months in a unified table (budget + actuals side by side); months with actuals but no budget also appear. Toggle the stacked chart between budgeted and actual allocations.
5. **Settings** — select your city, update monthly rent, loan EMI amount, and EMI end date.

### How the model works

| History available | Strategy |
|---|---|
| 0 months | City-specific base allocations (seasonal + live cost adjustments) |
| 1–2 months | Blend: `(1 − α) × base + α × actual/budget average`, α = n/3 |
| 3+ months | 1D-CNN → GRU sequence model, blended with base at `min(n/12, 0.85)` weight |

For months where actual spending has been imported, the **actual** category percentages are used as training labels instead of the budgeted percentages. This means the model learns from real behaviour, not intentions.

Investment and EMI are **fixed amounts** deducted before the ML split. Rent is also deducted as a fixed amount; home then receives rent plus its proportional share of the remaining ML pool — always above rent, with no fragile floor arithmetic.

### Money Manager category mapping

| Money Manager | BudgetIQ |
|---|---|
| 🛒 Groceries | Groceries |
| 🚖 Transport | Transport |
| 🍔 Food | Food |
| ❤️ Healthcare | Healthcare |
| 🏡 Home | Home |
| 🎈 Entertainment | Entertainment |
| 🔁 Subscriptions | Subscriptions |
| 🛍 Shopping | Shopping |
| 🧳 Travel | Travel |
| 💲 Investment | Investment |
| ⭕ Loan EMI | Loan EMI |
| everything else | Other |

## API

`GET /api/predict/?budget=<amount>&year=<year>&month=<month>`

Returns predicted percentages and amounts for each category, plus `history_count`, `history_with_actual`, investment, EMI, and rent values.

`GET /api/detect-location/?lat=<latitude>&lon=<longitude>`

Reverse-geocodes the supplied coordinates (via OpenStreetMap Nominatim) and returns the best-matching supported city name alongside the full list.

```json
{ "city": "Bangalore", "supported_cities": ["Ahmedabad", "Bangalore", ...] }
```

## Notes

- The `SECRET_KEY` in `settings.py` is the Django development default. Replace it before any deployment.
- `DEBUG = True` by default — set to `False` and configure `ALLOWED_HOSTS` for production.
- The database is SQLite (`db.sqlite3`) in the project root — suitable for single-user local use.
- scikit-learn is no longer a dependency; remove it from your environment if previously installed.
