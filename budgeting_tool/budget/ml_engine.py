"""
ML engine for budget split prediction.

Fixed-expense deduction order
------------------------------
1. Investment  : ₹50,000 if budget ≥ ₹70,000 (escalates 10 % each April)
2. Loan EMI    : ₹28,168/month until Sep 2028 (configurable in AppSettings)
3. Home floor  : Home allocation ≥ rent_amount (₹38,500 by default, configurable)

The remainder after (1) and (2) is split among the 9 remaining categories
(all except 'investment' and 'emi') using Ridge regression blended with
Hyderabad base allocations.  'home' has a minimum floor = rent_amount.

Model schedule
--------------
  0 months   → 100 % Hyderabad base
  1–2 months → blend: (1-α)·base + α·rolling avg,  α = n/3
  3+ months  → Ridge regression (ML weight caps at 0.85)
"""

import math
from decimal import Decimal, ROUND_HALF_UP

import numpy as np

CATEGORIES = [
    'groceries', 'transport', 'food', 'healthcare', 'home',
    'entertainment', 'subscriptions', 'shopping', 'travel',
    'investment', 'emi', 'other',
]

# Categories that the ML model predicts (excludes investment and emi)
ML_CATEGORIES = [c for c in CATEGORIES if c not in ('investment', 'emi')]

# ── Investment escalation ─────────────────────────────────────────────────────

_BASE_INV_AMOUNT = 50_000.0
_BASE_INV_THRESH = 70_000.0
_ESC_RATE        = 0.10
_ESC_FY_START    = 2026


def get_investment_parameters(year: int, month: int) -> tuple[float, float]:
    """
    Returns (fixed_investment_amount, min_budget_threshold).

    FY Apr 2026 – Mar 2027 : ₹50,000 / ₹70,000
    FY Apr 2027 – Mar 2028 : ₹55,000 / ₹77,000
    Each subsequent April escalates by 10 %.
    Months before Apr 2026 use FY-index 0.
    """
    fy_start = year if month >= 4 else year - 1
    fy_index = max(fy_start - _ESC_FY_START, 0)
    factor   = (1 + _ESC_RATE) ** fy_index
    return round(_BASE_INV_AMOUNT * factor, 2), round(_BASE_INV_THRESH * factor, 2)


def _inv_amount(total_budget: float, year: int, month: int) -> float:
    """
    Return the fixed investment amount if:
      (a) total_budget >= threshold, AND
      (b) after paying EMI + investment, there is still enough left to cover
          at least rent (so basic housing is always affordable).
    If (b) fails, skip investment to protect essential expenses.
    """
    inv_amt, thresh = get_investment_parameters(year, month)
    if total_budget < thresh:
        return 0.0
    try:
        emi  = _emi_amount(year, month)
        rent = _rent_amount()
        if total_budget - emi - inv_amt < rent:
            return 0.0
    except Exception:
        pass
    return inv_amt


# ── AppSettings helpers ───────────────────────────────────────────────────────

def _get_settings():
    from budget.models import AppSettings
    return AppSettings.get()


def _emi_amount(year: int, month: int) -> float:
    s = _get_settings()
    return s.get_emi_for_month(year, month)


def _rent_amount() -> float:
    return float(_get_settings().rent_amount)


# ── Base allocations (Hyderabad, % of ML-spendable portion) ──────────────────

BASE_HIGH_ML = {   # investment applies (budget ≥ threshold)
    'groceries':    12.0,
    'transport':     7.0,
    'food':         11.5,
    'healthcare':    4.5,
    'home':         24.0,
    'entertainment': 4.5,
    'subscriptions': 2.5,
    'shopping':      8.0,
    'travel':        7.5,
    'other':        18.5,
}
BASE_LOW_ML = {    # investment = 0 and/or EMI active
    'groceries':    14.5,
    'transport':     8.0,
    'food':         12.5,
    'healthcare':    5.0,
    'home':         26.0,
    'entertainment': 4.5,
    'subscriptions': 3.0,
    'shopping':      6.5,
    'travel':        4.0,
    'other':        16.0,
}

SEASONAL = {
    1:  {'shopping': 1.10, 'travel': 1.15, 'entertainment': 1.10, 'food': 1.05},
    3:  {'travel': 1.20, 'entertainment': 1.10, 'shopping': 1.05},
    4:  {'shopping': 1.05, 'travel': 1.05},
    7:  {'travel': 1.20, 'entertainment': 1.15, 'groceries': 1.05, 'food': 1.10},
    8:  {'shopping': 1.10, 'entertainment': 1.10},
    10: {'shopping': 1.30, 'entertainment': 1.20, 'travel': 1.20,
         'food': 1.15, 'groceries': 1.10},
    11: {'shopping': 1.45, 'entertainment': 1.30, 'travel': 1.30,
         'food': 1.25, 'groceries': 1.15},
    12: {'shopping': 1.20, 'entertainment': 1.25, 'travel': 1.30, 'food': 1.15},
}


# ── Pure helpers ──────────────────────────────────────────────────────────────

def _normalise(d: dict) -> dict:
    total = sum(d.values())
    if total == 0:
        eq = 100.0 / len(d)
        return {k: eq for k in d}
    factor = 100.0 / total
    out    = {k: v * factor for k, v in d.items()}
    out[max(out, key=out.get)] += 100.0 - sum(out.values())
    return out


def _apply_seasonal(d: dict, month: int) -> dict:
    result = dict(d)
    for cat, mult in SEASONAL.get(month, {}).items():
        if cat in result:
            result[cat] *= mult
    return result


def _apply_cost_adj(d: dict, adj: dict) -> dict:
    result = dict(d)
    for cat, mult in adj.items():
        if cat in result:
            result[cat] *= mult
    return result


def _base_ml_alloc(investment_applies: bool, month: int,
                   cost_adj: dict = None) -> dict:
    """Base % for ML categories (as % of ML-spendable). Sums to 100."""
    raw = dict(BASE_HIGH_ML if investment_applies else BASE_LOW_ML)
    raw = _apply_seasonal(raw, month)
    if cost_adj:
        raw = _apply_cost_adj(raw, {k: v for k, v in cost_adj.items()
                                    if k in ML_CATEGORIES})
    return _normalise(raw)


# ── Convert between ML-spendable % and total-budget % ───────────────────────

def _ml_to_total_pcts(ml_pcts: dict, inv: float, emi: float,
                      total_budget: float) -> dict:
    """Convert % of ML-spendable → % of total budget."""
    inv_pct = inv / total_budget * 100.0
    emi_pct = emi / total_budget * 100.0
    ml_pct  = 100.0 - inv_pct - emi_pct
    result  = {cat: pct * ml_pct / 100.0 for cat, pct in ml_pcts.items()}
    result['investment'] = inv_pct
    result['emi']        = emi_pct
    return result


def _total_to_ml_pcts(total_pcts: dict, inv: float, emi: float,
                      total_budget: float) -> dict:
    """Convert % of total → % of ML-spendable."""
    ml_spendable = total_budget - inv - emi
    if ml_spendable <= 0:
        eq = 100.0 / len(ML_CATEGORIES)
        return {cat: eq for cat in ML_CATEGORIES}
    result = {}
    for cat in ML_CATEGORIES:
        amount = total_pcts.get(cat, 0.0) / 100.0 * total_budget
        result[cat] = amount / ml_spendable * 100.0
    return _normalise(result)


# ── Home rent floor ───────────────────────────────────────────────────────────

def _apply_rent_floor(ml_amounts: dict, ml_spendable: float, rent: float) -> dict:
    """
    Ensure home allocation >= rent. Shortfall is shared proportionally
    from the other ML categories.
    """
    result = dict(ml_amounts)
    if result.get('home', 0) >= rent:
        return result
    shortfall = rent - result['home']
    result['home'] = rent
    other_cats = [c for c in ML_CATEGORIES if c != 'home']
    other_total = sum(result[c] for c in other_cats)
    if other_total >= shortfall:
        for cat in other_cats:
            result[cat] = max(result[cat] - shortfall * result[cat] / other_total, 0)
    return result


# ── Feature engineering ───────────────────────────────────────────────────────

def _feats(month, year, total_budget, offset):
    return [
        math.sin(2 * math.pi * month / 12),
        math.cos(2 * math.pi * month / 12),
        math.log(max(total_budget, 1)),
        total_budget / _BASE_INV_THRESH,
        float(offset),
    ]


def _train(cat: str, hist_ml: list):
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import PolynomialFeatures, StandardScaler

    base_abs = hist_ml[0]['year'] * 12 + hist_ml[0]['month']
    X, y = [], []
    for i, rec in enumerate(hist_ml):
        offset = rec['year'] * 12 + rec['month'] - base_abs
        fs = _feats(rec['month'], rec['year'], rec['total_budget'], offset)
        for lag in range(1, 4):
            fs.append(hist_ml[i - lag]['ml_pcts'].get(cat, 0.0) if i - lag >= 0 else 0.0)
        X.append(fs)
        y.append(rec['ml_pcts'].get(cat, 0.0))

    pipe = Pipeline([
        ('poly',   PolynomialFeatures(degree=1, include_bias=False)),
        ('scaler', __import__('sklearn.preprocessing',
                               fromlist=['StandardScaler']).StandardScaler()),
        ('ridge',  Ridge(alpha=10.0)),
    ])
    pipe.fit(np.array(X, float), np.array(y, float))
    return pipe


# ── Main prediction ───────────────────────────────────────────────────────────

def predict_split(total_budget: float, year: int, month: int,
                  history: list, cost_adj: dict = None) -> dict:
    """
    Returns {category: % of total}  summing to 100.
    investment = fixed amount / total * 100  (or 0).
    emi        = fixed amount / total * 100  (or 0 after end date).
    """
    inv  = _inv_amount(total_budget, year, month)
    emi  = _emi_amount(year, month)
    rent = _rent_amount()
    ml_spendable = total_budget - inv - emi

    inv_applies = inv > 0
    base_ml = _base_ml_alloc(inv_applies, month, cost_adj)
    n = len(history)

    # Convert history records to ml_pcts
    def to_ml(rec):
        rec_inv = _inv_amount(rec['total_budget'], rec['year'], rec['month'])
        rec_emi = float(_get_settings().get_emi_for_month(rec['year'], rec['month']))
        return _total_to_ml_pcts(rec['splits'], rec_inv, rec_emi, rec['total_budget'])

    if n == 0:
        ml_pcts = base_ml
    elif n < 3:
        avg = {cat: sum(to_ml(r).get(cat, 0.0) for r in history) / n
               for cat in ML_CATEGORIES}
        avg     = _normalise(avg)
        alpha   = n / 3.0
        ml_pcts = {cat: (1 - alpha) * base_ml[cat] + alpha * avg[cat]
                   for cat in ML_CATEGORIES}
        ml_pcts = _normalise(ml_pcts)
    else:
        hist_ml = [{**r, 'ml_pcts': to_ml(r)} for r in history]
        ml_weight  = min(n / 12.0, 0.85)
        base_abs   = hist_ml[0]['year'] * 12 + hist_ml[0]['month']
        target_off = year * 12 + month - base_abs
        t_fs       = _feats(month, year, total_budget, target_off)

        ml_pred = {}
        for cat in ML_CATEGORIES:
            try:
                pipe = _train(cat, hist_ml)
                lags = [hist_ml[-lag]['ml_pcts'].get(cat, 0.0)
                        if lag <= len(hist_ml) else 0.0
                        for lag in range(1, 4)]
                ml_pred[cat] = max(float(pipe.predict(np.array([t_fs + lags]))[0]), 0.0)
            except Exception:
                ml_pred[cat] = base_ml[cat]

        ml_pred = _apply_seasonal(ml_pred, month)
        if cost_adj:
            ml_pred = _apply_cost_adj(ml_pred, {k: v for k, v in cost_adj.items()
                                                 if k in ML_CATEGORIES})
        ml_pred = _normalise({k: ml_pred.get(k, base_ml[k]) for k in ML_CATEGORIES})
        ml_pcts = {cat: (1 - ml_weight) * base_ml[cat] + ml_weight * ml_pred[cat]
                   for cat in ML_CATEGORIES}
        ml_pcts = _normalise(ml_pcts)

    # Apply rent floor on amounts, then convert back to %
    if ml_spendable > 0:
        ml_amounts = {cat: ml_pcts[cat] / 100.0 * ml_spendable for cat in ML_CATEGORIES}
        ml_amounts = _apply_rent_floor(ml_amounts, ml_spendable, rent)
        ml_pcts    = {cat: ml_amounts[cat] / ml_spendable * 100.0 for cat in ML_CATEGORIES}
        ml_pcts    = _normalise(ml_pcts)

    return _ml_to_total_pcts(ml_pcts, inv, emi, total_budget)


# ── Amounts computation ───────────────────────────────────────────────────────

def pct_to_amounts(pct_dict: dict, total_budget: float,
                   year: int = None, month: int = None) -> dict:
    """Convert % dict to exact rupee amounts.
    investment and emi are fixed amounts (not derived from %)."""
    import datetime
    if year is None or month is None:
        now = datetime.datetime.now()
        year, month = now.year, now.month

    inv_dec = Decimal(str(_inv_amount(total_budget, year, month)))
    emi_dec = Decimal(str(_emi_amount(year, month)))
    ml_rem  = Decimal(str(total_budget)) - inv_dec - emi_dec

    ml_cats    = [c for c in CATEGORIES if c not in ('investment', 'emi')]
    ml_pct_sum = sum(pct_dict.get(c, 0.0) for c in ml_cats)

    amounts, running = {}, Decimal('0')
    for cat in ml_cats[:-1]:
        share = (Decimal(str(pct_dict.get(cat, 0.0))) / Decimal(str(ml_pct_sum))
                 if ml_pct_sum > 0 else Decimal('0'))
        amt   = (share * ml_rem).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        amounts[cat] = amt
        running     += amt

    amounts[ml_cats[-1]] = ml_rem - running
    amounts['investment'] = inv_dec
    amounts['emi']        = emi_dec

    # Route any residual (from rounding) to Food or Entertainment, whichever is less.
    total_computed = sum(amounts.values())
    residual = Decimal(str(total_budget)) - total_computed
    if residual != Decimal('0'):
        if amounts.get('food', Decimal('0')) <= amounts.get('entertainment', Decimal('0')):
            amounts['food'] = amounts.get('food', Decimal('0')) + residual
        else:
            amounts['entertainment'] = amounts.get('entertainment', Decimal('0')) + residual

    return amounts


# ── DB helpers ────────────────────────────────────────────────────────────────

def load_history_from_db(before_year: int, before_month: int) -> list:
    from budget.models import MonthlyBudget
    qs = (MonthlyBudget.objects
          .filter(year__lte=before_year)
          .exclude(year=before_year, month__gte=before_month)
          .prefetch_related('splits')
          .order_by('year', 'month'))
    history = []
    for rec in qs:
        splits = {s.category: float(s.percentage) for s in rec.splits.all()}
        if len(splits) == len(CATEGORIES):
            history.append({'year': rec.year, 'month': rec.month,
                             'total_budget': float(rec.total_budget),
                             'splits': splits})
    return history


def get_prediction_for_month(total_budget: float, year: int, month: int,
                             force_refresh: bool = False) -> dict:
    from budget.cost_data import get_or_fetch_cost_snapshot, cost_snapshot_to_adjustments
    history = load_history_from_db(year, month)
    snap    = get_or_fetch_cost_snapshot(year, month, force=force_refresh)
    adj     = cost_snapshot_to_adjustments(snap)
    pcts    = predict_split(total_budget, year, month, history, adj)
    amounts = pct_to_amounts(pcts, total_budget, year, month)
    settings = _get_settings()
    return {
        'percentages':   pcts,
        'amounts':       amounts,
        'history_count': len(history),
        'cost_snapshot': snap,
        'investment':    _inv_amount(total_budget, year, month),
        'emi':           settings.get_emi_for_month(year, month),
        'rent':          float(settings.rent_amount),
        'inv_params':    get_investment_parameters(year, month),
    }
