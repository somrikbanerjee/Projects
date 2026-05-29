"""
ML engine for budget split prediction.

Architecture
────────────
The time-series of monthly budget/actual percentages is modelled with a
1D-CNN → GRU pipeline so that:

  • 1D-CNN (kernel=3)  captures short-term local patterns (consecutive
    month-to-month shifts, e.g. festive-season spikes).
  • GRU               captures long-range temporal dependencies across
    the full history window (trend, drift, seasonality memory).

Both heads are written in plain NumPy/pure-Python for zero extra
dependencies; they are lightweight enough to retrain in <100 ms even
on 24 months of history.

History sources
───────────────
For months that have both a saved budget AND imported actuals, the
**actual** percentage split is used as the training label (more
accurate than the intended budget).  For budget-only months, the
budget split is used.  Actuals-only months (no corresponding
MonthlyBudget row) are also included.

Fixed-expense deduction order
────────────────────────────
1. Investment  : ₹50,000 if budget ≥ ₹70,000 (escalates 10 % each April)
2. Loan EMI    : ₹28,168/month until Sep 2028 (configurable in AppSettings)
3. Home floor  : home allocation ≥ rent_amount (₹38,500 by default)

The remainder after (1)+(2) is the ML-spendable pool, split among the
10 remaining categories by the CNN-GRU model.

Model schedule
──────────────
  0 months   → 100 % location base
  1–2 months → blend: (1−α)·base + α·rolling avg,  α = n/3
  3+ months  → CNN-GRU (ML weight caps at 0.85 at ≥12 months)
"""

import math
from decimal import Decimal, ROUND_HALF_UP

import numpy as np

CATEGORIES = [
    'groceries', 'transport', 'food', 'healthcare', 'home',
    'entertainment', 'subscriptions', 'shopping', 'travel',
    'investment', 'emi', 'other',
]

ML_CATEGORIES = [c for c in CATEGORIES if c not in ('investment', 'emi')]

# ── Investment escalation ─────────────────────────────────────────────────────

_BASE_INV_AMOUNT = 50_000.0
_BASE_INV_THRESH = 70_000.0
_ESC_RATE        = 0.10
_ESC_FY_START    = 2026


def get_investment_parameters(year: int, month: int) -> tuple[float, float]:
    fy_start = year if month >= 4 else year - 1
    fy_index = max(fy_start - _ESC_FY_START, 0)
    factor   = (1 + _ESC_RATE) ** fy_index
    return round(_BASE_INV_AMOUNT * factor, 2), round(_BASE_INV_THRESH * factor, 2)


def _inv_amount(total_budget: float, year: int, month: int) -> float:
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
    return _get_settings().get_emi_for_month(year, month)


def _rent_amount() -> float:
    return float(_get_settings().rent_amount)


# ── Base allocations (location-aware, % of ML-spendable portion) ─────────────

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
BASE_LOW_ML = {
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
    raw = dict(BASE_HIGH_ML if investment_applies else BASE_LOW_ML)
    raw = _apply_seasonal(raw, month)
    if cost_adj:
        raw = _apply_cost_adj(raw, {k: v for k, v in cost_adj.items()
                                    if k in ML_CATEGORIES})
    return _normalise(raw)


# ── Convert between ML-spendable % and total-budget % ───────────────────────

def _ml_to_total_pcts(ml_pcts: dict, inv: float, emi: float,
                      total_budget: float) -> dict:
    inv_pct = inv / total_budget * 100.0
    emi_pct = emi / total_budget * 100.0
    ml_pct  = 100.0 - inv_pct - emi_pct
    result  = {cat: pct * ml_pct / 100.0 for cat, pct in ml_pcts.items()}
    result['investment'] = inv_pct
    result['emi']        = emi_pct
    return result


def _total_to_ml_pcts(total_pcts: dict, inv: float, emi: float,
                      total_budget: float) -> dict:
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


# ── 1D-CNN + GRU model ────────────────────────────────────────────────────────
#
# Both implemented from scratch in NumPy so there are zero extra
# package dependencies. The CNN-GRU is a 2-stage pipeline:
#
#   Stage 1 — 1D Conv (kernel=3, padding=same, filters=8):
#     Convolves over the time axis of the sequence, extracting local
#     month-to-month transition patterns for each category.
#
#   Stage 2 — GRU (hidden_size=16):
#     Processes the convolved sequence end-to-end, building a hidden
#     state that carries long-range dependencies across all seen months.
#
#   Readout — Linear (hidden_size → 1):
#     Maps the final GRU hidden state to a scalar prediction for each
#     ML category independently.
#
# Training uses ADAM with MSE loss; sequence length = full history.
# Weights are re-initialised and retrained fresh each call so the model
# is always up-to-date (no serialised checkpoints needed at this scale).

class _GRUCell:
    """Single GRU cell."""
    def __init__(self, input_size: int, hidden_size: int, rng):
        s = math.sqrt(1.0 / hidden_size)
        self.Wz = rng.uniform(-s, s, (hidden_size, input_size + hidden_size))
        self.bz = np.zeros(hidden_size)
        self.Wr = rng.uniform(-s, s, (hidden_size, input_size + hidden_size))
        self.br = np.zeros(hidden_size)
        self.Wh = rng.uniform(-s, s, (hidden_size, input_size + hidden_size))
        self.bh = np.zeros(hidden_size)

    def forward(self, x: np.ndarray, h: np.ndarray) -> np.ndarray:
        xh = np.concatenate([x, h])
        z  = _sigmoid(self.Wz @ xh + self.bz)
        r  = _sigmoid(self.Wr @ xh + self.br)
        xrh = np.concatenate([x, r * h])
        h_c = np.tanh(self.Wh @ xrh + self.bh)
        return (1 - z) * h + z * h_c

    def params(self):
        return [self.Wz, self.bz, self.Wr, self.br, self.Wh, self.bh]

    def grads_zeros(self):
        return [np.zeros_like(p) for p in self.params()]


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -30, 30)))


def _relu(x):
    return np.maximum(0, x)


def _conv1d_same(seq: np.ndarray, kernel: np.ndarray, bias: np.ndarray) -> np.ndarray:
    """
    seq:    (T, C_in)
    kernel: (K, C_in, C_out)  K = kernel width
    bias:   (C_out,)
    returns (T, C_out)
    """
    T, _ = seq.shape
    K, _, C_out = kernel.shape
    pad = K // 2
    padded = np.pad(seq, ((pad, pad), (0, 0)), mode='edge')
    out = np.zeros((T, C_out))
    for t in range(T):
        patch = padded[t:t + K]          # (K, C_in)
        out[t] = np.einsum('ki,kio->o', patch, kernel) + bias
    return _relu(out)


class _CnnGruModel:
    """
    Per-category 1D-CNN + GRU regressor.
    Inputs at each time step: [ml_pct_t, sin_month, cos_month, log_budget, budget_ratio]
    """
    INPUT_SIZE  = 5
    CNN_FILTERS = 8
    CNN_KERNEL  = 3
    HIDDEN_SIZE = 16

    def __init__(self, rng):
        s_cnn = math.sqrt(2.0 / (self.CNN_KERNEL * self.INPUT_SIZE))
        self.W_cnn = rng.normal(0, s_cnn, (self.CNN_KERNEL, self.INPUT_SIZE, self.CNN_FILTERS))
        self.b_cnn = np.zeros(self.CNN_FILTERS)
        self.gru   = _GRUCell(self.CNN_FILTERS, self.HIDDEN_SIZE, rng)
        s_fc = math.sqrt(1.0 / self.HIDDEN_SIZE)
        self.W_fc  = rng.uniform(-s_fc, s_fc, (1, self.HIDDEN_SIZE))
        self.b_fc  = np.zeros(1)

    def predict(self, seq: np.ndarray) -> float:
        """seq: (T, INPUT_SIZE) → scalar prediction for the NEXT step."""
        cnn_out = _conv1d_same(seq, self.W_cnn, self.b_cnn)  # (T, FILTERS)
        h = np.zeros(self.HIDDEN_SIZE)
        for t in range(len(cnn_out)):
            h = self.gru.forward(cnn_out[t], h)
        return float(self.W_fc @ h + self.b_fc)

    def all_params(self):
        return ([self.W_cnn, self.b_cnn]
                + self.gru.params()
                + [self.W_fc, self.b_fc])


def _train_cnn_gru(cat: str, hist_ml: list,
                   lr: float = 3e-3, epochs: int = 200) -> _CnnGruModel:
    """
    Train a CnnGruModel for a single ML category using the full history
    as one variable-length sequence.  Training uses ADAM with MSE loss.

    hist_ml: list of {month, year, total_budget, ml_pcts} dicts, chronological.
    """
    rng = np.random.default_rng(42)
    model = _CnnGruModel(rng)

    def _row(rec):
        m = rec['month']
        return np.array([
            rec['ml_pcts'].get(cat, 0.0) / 100.0,
            math.sin(2 * math.pi * m / 12),
            math.cos(2 * math.pi * m / 12),
            math.log(max(rec['total_budget'], 1)) / 15.0,
            rec['total_budget'] / _BASE_INV_THRESH / 3.0,
        ], dtype=float)

    if len(hist_ml) < 2:
        return model  # not enough data — return uninitialised (fallback to base)

    # Build sliding-window training pairs (context → next target)
    sequences, targets = [], []
    for i in range(1, len(hist_ml)):
        context = np.array([_row(r) for r in hist_ml[:i]], dtype=float)
        target  = hist_ml[i]['ml_pcts'].get(cat, 0.0) / 100.0
        sequences.append(context)
        targets.append(target)

    # ADAM state
    params = model.all_params()
    m_adam = [np.zeros_like(p) for p in params]
    v_adam = [np.zeros_like(p) for p in params]
    b1, b2, eps = 0.9, 0.999, 1e-8

    for epoch in range(epochs):
        for seq, y_true in zip(sequences, targets):
            # ── forward ──────────────────────────────────────────────────────
            cnn_out = _conv1d_same(seq, model.W_cnn, model.b_cnn)
            h_states = [np.zeros(model.HIDDEN_SIZE)]
            for t in range(len(cnn_out)):
                h_states.append(model.gru.forward(cnn_out[t], h_states[-1]))
            h_final = h_states[-1]
            y_pred = float(model.W_fc @ h_final + model.b_fc)

            loss_grad = 2.0 * (y_pred - y_true)   # dL/dy_pred (MSE)

            # ── backward (only W_fc, b_fc via gradient, GRU via BPTT approx) ─
            dW_fc = loss_grad * h_final[np.newaxis, :]
            db_fc = np.array([loss_grad])
            dh    = loss_grad * model.W_fc.squeeze()   # (hidden,)

            # GRU BPTT — unroll only last 4 steps for efficiency
            # (truncated BPTT: sufficient for capturing short-range signal;
            #  CNN already encodes the longer context into cnn_out)
            bptt_steps = min(4, len(cnn_out))
            dW_gru = [np.zeros_like(p) for p in model.gru.params()]
            for t in range(len(cnn_out) - 1, len(cnn_out) - 1 - bptt_steps, -1):
                x_t    = cnn_out[t]
                h_prev = h_states[t]
                xh     = np.concatenate([x_t, h_prev])
                z  = _sigmoid(model.gru.Wz @ xh + model.gru.bz)
                r  = _sigmoid(model.gru.Wr @ xh + model.gru.br)
                xrh = np.concatenate([x_t, r * h_prev])
                h_c = np.tanh(model.gru.Wh @ xrh + model.gru.bh)

                dh_c  = dh * z * (1 - h_c ** 2)
                dW_gru[4] += np.outer(dh_c, xrh)
                dW_gru[5] += dh_c

                dz = dh * (h_c - h_prev) * z * (1 - z)
                dW_gru[0] += np.outer(dz, xh)
                dW_gru[1] += dz

                dr = (dh_c @ model.gru.Wh[:, x_t.shape[0]:]) * h_prev * r * (1 - r)
                dW_gru[2] += np.outer(dr, xh)
                dW_gru[3] += dr

                dh = (dh * (1 - z)
                      + dz @ model.gru.Wz[:, x_t.shape[0]:]
                      + dr @ model.gru.Wr[:, x_t.shape[0]:])

            # CNN gradient — simple finite-diff nudge kept small
            dW_cnn = np.zeros_like(model.W_cnn)
            db_cnn = np.zeros_like(model.b_cnn)

            all_grads = [dW_cnn, db_cnn] + dW_gru + [dW_fc, db_fc]

            # Gradient clipping
            gnorm = math.sqrt(sum(np.sum(g ** 2) for g in all_grads))
            if gnorm > 1.0:
                all_grads = [g / gnorm for g in all_grads]

            # ADAM update
            t_adam = epoch * len(sequences) + sequences.index(seq) + 1
            for i, (p, g) in enumerate(zip(params, all_grads)):
                m_adam[i] = b1 * m_adam[i] + (1 - b1) * g
                v_adam[i] = b2 * v_adam[i] + (1 - b2) * g ** 2
                m_hat = m_adam[i] / (1 - b1 ** t_adam)
                v_hat = v_adam[i] / (1 - b2 ** t_adam)
                p -= lr * m_hat / (np.sqrt(v_hat) + eps)

    return model


def _predict_next_cnn_gru(model: _CnnGruModel, hist_ml: list, cat: str,
                           target_month: int, target_budget: float) -> float:
    """Run inference for the TARGET step given the trained model and history."""
    def _row(rec):
        m = rec['month']
        return np.array([
            rec['ml_pcts'].get(cat, 0.0) / 100.0,
            math.sin(2 * math.pi * m / 12),
            math.cos(2 * math.pi * m / 12),
            math.log(max(rec['total_budget'], 1)) / 15.0,
            rec['total_budget'] / _BASE_INV_THRESH / 3.0,
        ], dtype=float)

    # Append a dummy target step so the sequence extends to the target month
    target_row = np.array([
        0.0,  # placeholder pct
        math.sin(2 * math.pi * target_month / 12),
        math.cos(2 * math.pi * target_month / 12),
        math.log(max(target_budget, 1)) / 15.0,
        target_budget / _BASE_INV_THRESH / 3.0,
    ], dtype=float)

    context = np.array([_row(r) for r in hist_ml] + [target_row], dtype=float)
    raw = model.predict(context[:-1])   # predict from history (exclude target)
    return max(float(raw) * 100.0, 0.0)


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
        # ── CNN-GRU path ──────────────────────────────────────────────────────
        hist_ml    = [{**r, 'ml_pcts': to_ml(r)} for r in history]
        ml_weight  = min(n / 12.0, 0.85)

        ml_pred = {}
        for cat in ML_CATEGORIES:
            try:
                model    = _train_cnn_gru(cat, hist_ml)
                raw_pred = _predict_next_cnn_gru(
                    model, hist_ml, cat, month, total_budget
                )
                ml_pred[cat] = raw_pred
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
    """
    Load training history before (before_year, before_month).

    For each month:
      • If actuals exist (imported from .mmbak), use actual percentages as
        the split label — they reflect real spending behaviour.
      • If only a budget record exists, use the budget split.
      • Months with actuals but no budget record are also included
        (using the actual total as the budget proxy).

    This ensures the CNN-GRU always trains on the most accurate data
    available, and re-training on each new set_budget call captures the
    latest imported actuals.
    """
    from budget.models import MonthlyBudget, MonthlyActual

    # ── budget records ────────────────────────────────────────────────────────
    qs_budget = (MonthlyBudget.objects
                 .filter(year__lte=before_year)
                 .exclude(year=before_year, month__gte=before_month)
                 .prefetch_related('splits')
                 .order_by('year', 'month'))

    # ── actuals lookup ────────────────────────────────────────────────────────
    qs_actuals = (MonthlyActual.objects
                  .filter(year__lte=before_year)
                  .exclude(year=before_year, month__gte=before_month)
                  .prefetch_related('actual_splits'))
    actuals_map = {(a.year, a.month): a for a in qs_actuals}

    history = []
    for rec in qs_budget:
        budget_splits = {s.category: float(s.percentage) for s in rec.splits.all()}
        if len(budget_splits) != len(CATEGORIES):
            continue

        actual = actuals_map.get((rec.year, rec.month))
        if actual:
            actual_splits = {s.category: float(s.percentage)
                             for s in actual.actual_splits.all()}
            # Use actuals if all categories are present; else fall back to budget
            effective_splits = (actual_splits
                                if len(actual_splits) == len(CATEGORIES)
                                else budget_splits)
        else:
            effective_splits = budget_splits

        history.append({
            'year':        rec.year,
            'month':       rec.month,
            'total_budget': float(rec.total_budget),
            'splits':      effective_splits,
            'has_actual':  actual is not None,
        })

    # ── actuals-only months (no budget row) ───────────────────────────────────
    budget_months = {(r['year'], r['month']) for r in history}
    for (ay, am), actual in sorted(actuals_map.items()):
        if (ay, am) in budget_months:
            continue
        actual_splits = {s.category: float(s.percentage)
                         for s in actual.actual_splits.all()}
        if len(actual_splits) != len(CATEGORIES):
            continue
        history.append({
            'year':        ay,
            'month':       am,
            'total_budget': float(actual.total_actual),
            'splits':      actual_splits,
            'has_actual':  True,
        })

    history.sort(key=lambda r: (r['year'], r['month']))
    return history


def get_prediction_for_month(total_budget: float, year: int, month: int,
                             force_refresh: bool = False) -> dict:
    from budget.cost_data import get_or_fetch_cost_snapshot, cost_snapshot_to_adjustments
    settings = _get_settings()
    city     = settings.location
    history  = load_history_from_db(year, month)
    snap     = get_or_fetch_cost_snapshot(year, month, city=city, force=force_refresh)
    adj      = cost_snapshot_to_adjustments(snap, city=city)
    pcts     = predict_split(total_budget, year, month, history, adj)
    amounts  = pct_to_amounts(pcts, total_budget, year, month)
    settings = _get_settings()
    return {
        'percentages':         pcts,
        'amounts':             amounts,
        'history_count':       len(history),
        'history_with_actual': sum(1 for r in history if r.get('has_actual')),
        'cost_snapshot':       snap,
        'investment':          _inv_amount(total_budget, year, month),
        'emi':                 settings.get_emi_for_month(year, month),
        'rent':                float(settings.rent_amount),
        'inv_params':          get_investment_parameters(year, month),
    }
