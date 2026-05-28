# BudgetIQ

A personal budgeting web application tailored for Hyderabad, India. Enter your monthly salary, and BudgetIQ uses a machine-learning model (Ridge regression blended with Hyderabad cost-of-living baselines) to suggest how to split it across 12 spending categories. Fixed expenses — rent, loan EMI, and investment — are deducted first; the remainder is split intelligently across everything else.

## Features

- **AI-suggested splits** — base Hyderabad allocations for the first month, blending in your personal history as months accumulate, switching to full Ridge regression at 3+ months
- **Fixed-expense deductions** — investment (auto-escalating 10 % each April), loan EMI (active until a configurable end date), and a rent floor that guarantees your home allocation never drops below your rent amount
- **Seasonal adjustments** — spending weights shift automatically for festive months (Diwali, New Year, summer travel, etc.)
- **Live cost data** — CPI inflation and petrol prices are fetched each time you request a new prediction; the results are shown as a Live Cost Data card on the dashboard
- **Dashboard** — stat pills for total budget, investment, and rent; category splits with coloured progress bars; three right-column cards (Living Budget breakdown, allocation donut with leader-line labels, live cost data); month-over-month comparison chart; trend chart; recent months table; Update and Delete buttons for the current month's budget
- **History** — full budget history with a total-budget trend line, stacked category allocation chart, and a detailed monthly breakdown table
- **Settings** — configure rent amount, loan EMI amount, and EMI end date
- **Indian number formatting** — all currency amounts display in the Indian comma convention (e.g. ₹1,30,000.00)
- **Favicon & branding** — custom SVG bar-chart icon used as the browser favicon and in the navbar
- **Background service** — ships as a macOS LaunchAgent; starts automatically at login and serves on `http://127.0.0.1:8080/` with no UI or notifications

## Tech Stack

| Layer | Library / Version |
|---|---|
| Language | Python 3.14 |
| Web framework | Django 6.0.5 |
| ML | scikit-learn 1.8 · numpy 2.4 |
| Frontend | Bootstrap 5.3 · Bootstrap Icons 1.11 · Chart.js 4.4 |
| Database | SQLite (default) |

## Project Structure

```
budgeting_tool/
├── budget/
│   ├── models.py          # AppSettings, MonthlyBudget, BudgetSplit, CostSnapshot
│   ├── views.py           # Dashboard, set-budget (2-step), history, settings, API
│   ├── ml_engine.py       # Prediction engine — base allocations, Ridge regression, seasonal logic
│   ├── cost_data.py       # Live cost-data fetch (World Bank CPI, petrol estimate, Numbeo indices)
│   ├── forms.py           # BudgetInputForm, SplitAdjustmentForm, AppSettingsForm
│   ├── urls.py            # URL routing
│   ├── static/budget/
│   │   └── favicon.svg    # Brand icon (bar chart, green/gold)
│   ├── templatetags/
│   │   └── budget_filters.py  # indian_number, get_item, get_field template filters
│   ├── templates/budget/
│   │   ├── base.html
│   │   ├── dashboard.html
│   │   ├── set_budget.html
│   │   ├── history.html
│   │   └── settings.html
│   └── management/commands/
│       └── load_dummy_data.py
└── budgeting_tool/
    └── settings.py        # Django project settings
```

## Setup

```bash
# 1. Clone / download the project
cd budgeting_tool

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install django scikit-learn numpy requests

# 4. Apply migrations
python manage.py migrate

# 5. (Optional) Load sample data to see the app with pre-filled months
python manage.py load_dummy_data

# 6. Start the development server
python manage.py runserver 127.0.0.1:8080 --noreload
```

Then open `http://127.0.0.1:8080/` in your browser.

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

1. **Dashboard** — the landing page shows the current month's budget (if set), split breakdown, and three cards on the right: a **Living Budget** card (total − investment − rent − loan EMI), the **Allocation donut**, and **Live Cost Data** (CPI, petrol, indices). Below that: historical charts and a recent months table.
2. **Set Budget** — enter your total monthly income. The AI generates a suggested split; review and adjust percentages, then confirm to save.
3. **History** — browse all saved months, edit or delete individual entries.
4. **Settings** — update your monthly rent, loan EMI amount, and the month/year the EMI ends.

### How the model works

| History available | Strategy |
|---|---|
| 0 months | Hyderabad base allocations (adjusted for season and live cost data) |
| 1–2 months | Blend: `(1 − α) × base + α × rolling average`, where `α = n / 3` |
| 3+ months | Ridge regression on the 10 ML categories, blended with base at `min(n/12, 0.85)` weight |

Investment and loan EMI are **fixed amounts** (not predicted); they are deducted before any split is computed. The home category has a **rent floor** — it will never be allocated less than your configured rent amount.

## API

`GET /api/predict/?budget=<amount>&year=<year>&month=<month>`

Returns a JSON object with predicted percentages and amounts for each category, plus investment, EMI, and rent values.

## Notes

- The `SECRET_KEY` in `settings.py` is the Django development default. Replace it before any deployment.
- `DEBUG = True` by default — set to `False` and configure `ALLOWED_HOSTS` for production.
- The database is SQLite (`db.sqlite3`) in the project root — suitable for single-user local use.
