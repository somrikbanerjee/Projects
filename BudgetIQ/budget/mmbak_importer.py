"""
Imports actual spending data from Money Manager (.mmbak) SQLite backups.

.mmbak files are standard SQLite3 databases exported by ReadBytes Money Manager
(Android).  They live in:
  ~/Library/CloudStorage/GoogleDrive-…/My Drive/MoneyManager/

Category mapping: Money Manager emoji-labelled category names → BudgetIQ keys.
Expense transactions are DO_TYPE = 1.  Opening-balance (7/8) and transfers
(3/4) are excluded.
"""

import glob
import logging
import os
import sqlite3

logger = logging.getLogger(__name__)

# ── Backup location ───────────────────────────────────────────────────────────

BACKUP_DIR = os.path.expanduser(
    "~/Library/CloudStorage/"
    "GoogleDrive-somrik.banerjee@gmail.com/"
    "My Drive/MoneyManager"
)

# ── Money Manager category name → BudgetIQ category key ─────────────────────

_MM_TO_CAT = {
    "🛒 Groceries":     "groceries",
    "🚖 Transport":     "transport",
    "🍔 Food":          "food",
    "❤️ Healthcare":   "healthcare",
    "🏡 Home":          "home",
    "🎈 Entertainment": "entertainment",
    "🔁 Subscriptions": "subscriptions",
    "🛍 Shopping":      "shopping",
    "🧳 Travel":        "travel",
    "💲Investment":     "investment",
    "⭕ Loan EMI":      "emi",
}

# SQL CASE expression built once from the mapping
_CASE_EXPR = "\n".join(
    f"        WHEN '{mm}' THEN '{cat}'" for mm, cat in _MM_TO_CAT.items()
)

_EXTRACT_SQL = f"""
WITH cat_lookup AS (
    SELECT uid,
        CASE NAME
{_CASE_EXPR}
        ELSE 'other'
        END AS budget_cat
    FROM ZCATEGORY
    WHERE COALESCE(C_IS_DEL, 0) = 0
)
SELECT cl.budget_cat,
       ROUND(SUM(CAST(tx.ZMONEY AS REAL)), 2) AS total_amount
FROM INOUTCOME tx
JOIN cat_lookup cl ON tx.ctgUid = cl.uid
WHERE tx.IS_DEL = 0
  AND tx.DO_TYPE = 1
  AND strftime('%Y-%m', datetime(tx.ZDATE / 1000, 'unixepoch', 'localtime')) = ?
GROUP BY cl.budget_cat
"""


# ── Public helpers ────────────────────────────────────────────────────────────

def find_latest_mmbak(backup_dir: str = BACKUP_DIR) -> str | None:
    """Return the path to the most recently modified .mmbak file, or None."""
    pattern = os.path.join(backup_dir, "*.mmbak")
    files = glob.glob(pattern)
    if not files:
        logger.warning("No .mmbak files found in %s", backup_dir)
        return None
    return max(files, key=os.path.getmtime)


def extract_monthly_expenses(filepath: str, year: int, month: int) -> dict:
    """
    Read a .mmbak file and return {budget_cat: total_amount} for expense
    transactions in the given year-month.

    Returns an empty dict on any read error or if no transactions match.
    """
    month_str = f"{year:04d}-{month:02d}"
    try:
        conn = sqlite3.connect(filepath)
        cur = conn.cursor()
        cur.execute(_EXTRACT_SQL, (month_str,))
        rows = cur.fetchall()
        conn.close()
        return {row[0]: float(row[1]) for row in rows if row[1] is not None}
    except Exception as exc:
        logger.warning("Failed to read .mmbak %s: %s", filepath, exc)
        return {}


def save_actuals_to_db(
    year: int, month: int, expenses: dict, source_file: str
) -> "MonthlyActual":
    """
    Upsert a MonthlyActual record and its ActualSplit rows.

    If a record already exists for (year, month) it is overwritten so the
    freshest data always wins (one record per month).

    Returns the MonthlyActual instance.
    """
    from budget.models import MonthlyActual, ActualSplit, CATEGORY_KEYS

    total = sum(expenses.values())

    ma, _ = MonthlyActual.objects.update_or_create(
        year=year,
        month=month,
        defaults={
            "total_actual": round(total, 2),
            "source_file": os.path.basename(source_file),
        },
    )

    # Wipe and rewrite splits so stale categories are never left behind.
    ActualSplit.objects.filter(monthly_actual=ma).delete()

    # Normalise percentages to sum exactly to 100.
    if total > 0:
        raw_pcts = {cat: expenses.get(cat, 0.0) / total * 100.0 for cat in CATEGORY_KEYS}
    else:
        eq = 100.0 / len(CATEGORY_KEYS)
        raw_pcts = {cat: eq for cat in CATEGORY_KEYS}

    # Assign residual from float rounding to the largest category.
    pct_sum = sum(raw_pcts.values())
    if pct_sum != 100.0 and CATEGORY_KEYS:
        biggest = max(raw_pcts, key=raw_pcts.get)
        raw_pcts[biggest] += 100.0 - pct_sum

    for cat in CATEGORY_KEYS:
        ActualSplit.objects.create(
            monthly_actual=ma,
            category=cat,
            amount=round(expenses.get(cat, 0.0), 2),
            percentage=round(raw_pcts[cat], 3),
        )

    return ma


def import_actuals_for_month(year: int, month: int) -> "MonthlyActual | None":
    """
    Find the latest .mmbak, extract expenses for (year, month), save to DB.

    Called automatically each time the user sets a budget — imports the
    previous month's actuals before generating the AI recommendation.

    Returns the saved MonthlyActual or None if no data is available.
    """
    filepath = find_latest_mmbak()
    if not filepath:
        return None

    expenses = extract_monthly_expenses(filepath, year, month)
    if not expenses:
        logger.info(
            "No expense transactions found in %s for %04d-%02d",
            filepath, year, month,
        )
        return None

    logger.info(
        "Imported actuals for %04d-%02d from %s  (total ₹%.2f)",
        year, month, os.path.basename(filepath), sum(expenses.values()),
    )
    return save_actuals_to_db(year, month, expenses, filepath)
