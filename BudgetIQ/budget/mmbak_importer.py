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
    """Find the latest .mmbak, extract expenses for (year, month), save to DB."""
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


def get_average_monthly_expenses(filepath: str) -> tuple:
    """
    Compute average monthly total expense from all expense transactions
    (DO_TYPE = 1, IS_DEL = 0) in the .mmbak file.

    Returns (avg_amount: float, n_months: int).
    Returns (None, 0) on any error or if the file has no expense data.
    """
    sql = """
        SELECT
            strftime('%Y-%m', datetime(ZDATE/1000, 'unixepoch', 'localtime')) AS ym,
            ROUND(SUM(CAST(ZMONEY AS REAL)), 2)                               AS monthly_total
        FROM INOUTCOME
        WHERE IS_DEL = 0
          AND DO_TYPE = 1
        GROUP BY ym
        ORDER BY ym
    """
    try:
        conn = sqlite3.connect(filepath)
        cur  = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        conn.close()
        totals = [float(row[1]) for row in rows if row[1] is not None]
        if not totals:
            return None, 0
        return round(sum(totals) / len(totals), 2), len(totals)
    except Exception as exc:
        logger.warning("Failed to compute average monthly expenses from %s: %s", filepath, exc)
        return None, 0


def get_all_account_balances(filepath: str) -> dict:
    """
    Compute current account balances from a Money Manager .mmbak SQLite backup.

    Balances are derived from INOUTCOME transactions rather than a stored
    balance field (Money Manager does not persist balances in ASSETS).

    DO_TYPE semantics:
      '0' = income        → +
      '1' = expense       → −
      '3' = transfer out  → − (assetUid is the source account)
      '4' = transfer in   → + (assetUid is the destination account)
      '7' = opening bal   → +

    Returns {account_name: balance_float} for all accounts that appear in
    ASSETS, or {} on any read error.
    """
    _BALANCE_SQL = """
        SELECT
            a.NIC_NAME,
            ROUND(COALESCE(SUM(
                CASE
                    WHEN t.DO_TYPE IN ('0', '7') THEN  CAST(t.ZMONEY AS REAL)
                    WHEN t.DO_TYPE = '1'         THEN -CAST(t.ZMONEY AS REAL)
                    WHEN t.DO_TYPE = '4'         THEN  CAST(t.ZMONEY AS REAL)
                    WHEN t.DO_TYPE = '3'         THEN -CAST(t.ZMONEY AS REAL)
                    ELSE 0
                END
            ), 0), 2) AS balance
        FROM ASSETS a
        LEFT JOIN INOUTCOME t
               ON t.assetUid = a.uid
              AND t.IS_DEL   = 0
        GROUP BY a.uid, a.NIC_NAME
    """
    try:
        conn = sqlite3.connect(filepath)
        cur  = conn.cursor()
        cur.execute(_BALANCE_SQL)
        rows = cur.fetchall()
        conn.close()
        return {str(name): float(bal) for name, bal in rows if name}
    except Exception as exc:
        logger.warning("Failed to compute account balances from %s: %s", filepath, exc)
        return {}


def get_available_months(filepath: str,
                         before_year: int, before_month: int) -> list:
    """
    Return a sorted list of (year, month) tuples that have expense
    transactions in the .mmbak file and fall strictly before
    (before_year, before_month).
    """
    try:
        conn = sqlite3.connect(filepath)
        cur  = conn.cursor()
        cur.execute("""
            SELECT DISTINCT
                CAST(strftime('%Y', datetime(ZDATE/1000, 'unixepoch', 'localtime')) AS INTEGER),
                CAST(strftime('%m', datetime(ZDATE/1000, 'unixepoch', 'localtime')) AS INTEGER)
            FROM INOUTCOME
            WHERE IS_DEL = 0 AND DO_TYPE = 1
            ORDER BY 1, 2
        """)
        rows = cur.fetchall()
        conn.close()
        return [(yr, mo) for yr, mo in rows if (yr, mo) < (before_year, before_month)]
    except Exception as exc:
        logger.warning("Failed to list available months in %s: %s", filepath, exc)
        return []


def import_all_available_actuals(before_year: int,
                                  before_month: int) -> list:
    """
    Import actuals for every month available in the latest .mmbak file
    that falls strictly before (before_year, before_month).

    Each month is upserted — existing records are overwritten with the
    freshest data.  Returns a list of MonthlyActual instances imported.

    Called each time the user sets a budget so the full spending history
    (not just the immediately preceding month) is available for ML training
    and for display in the dashboard / history.
    """
    filepath = find_latest_mmbak()
    if not filepath:
        return []

    months   = get_available_months(filepath, before_year, before_month)
    imported = []
    for yr, mo in months:
        expenses = extract_monthly_expenses(filepath, yr, mo)
        if not expenses:
            continue
        ma = save_actuals_to_db(yr, mo, expenses, filepath)
        imported.append(ma)
        logger.info(
            "Imported actuals for %04d-%02d from %s  (total ₹%.2f)",
            yr, mo, os.path.basename(filepath), sum(expenses.values()),
        )

    logger.info(
        "Imported %d month(s) of actuals from %s",
        len(imported), os.path.basename(filepath),
    )
    return imported
