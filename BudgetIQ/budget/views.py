import json
import os
import calendar
import datetime

from decimal import Decimal, ROUND_HALF_UP
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.utils import timezone
from django.contrib import messages

from .models import (
    MonthlyBudget, BudgetSplit, MonthlyActual,
    AppSettings, CATEGORIES, CATEGORY_ICONS,
)
from .forms import BudgetInputForm, SplitAdjustmentForm, AppSettingsForm
from .ml_engine import get_prediction_for_month, pct_to_amounts, CATEGORIES as CATEGORY_KEYS
from .cost_data import get_or_fetch_cost_snapshot, resolve_city_from_coords, SUPPORTED_CITIES
from .mmbak_importer import (
    import_actuals_for_month, import_all_available_actuals,
    find_latest_mmbak, get_all_account_balances,
)


def _compute_actual_avg(before_year: int, before_month: int) -> dict | None:
    """
    Average actual spending per category across all MonthlyActual records
    strictly before (before_year, before_month).

    Returns a template-ready dict with keys:
      label     — human-readable range string
      total     — average monthly total (float)
      splits    — {cat: {'amount': float, 'percentage': float}}
      n_months  — number of months averaged
    or None if no actuals exist yet.
    """
    from django.db.models import Q
    qs = (MonthlyActual.objects
          .filter(Q(year__lt=before_year) | Q(year=before_year, month__lt=before_month))
          .prefetch_related('actual_splits')
          .order_by('year', 'month'))
    records = list(qs)
    if not records:
        return None

    n           = len(records)
    cat_totals  = {cat: 0.0 for cat in CATEGORY_KEYS}
    total_sum   = 0.0

    for ma in records:
        total_sum += float(ma.total_actual)
        for s in ma.actual_splits.all():
            cat_totals[s.category] += float(s.amount)

    avg_total = total_sum / n
    splits = {}
    for cat in CATEGORY_KEYS:
        avg_amt = cat_totals[cat] / n
        splits[cat] = {
            'amount':     round(avg_amt, 2),
            'percentage': round((avg_amt / avg_total * 100) if avg_total > 0 else 0.0, 1),
        }

    months = [f"{calendar.month_abbr[ma.month]} {ma.year}" for ma in records]
    label  = months[0] if n == 1 else f"{months[0]}–{months[-1]}"

    return {
        'label':    label,
        'total':    round(avg_total, 2),
        'splits':   splits,
        'n_months': n,
    }


# After this day-of-month, "Set Budget" defaults to the following month and
# the current month's partial expenses are included in actuals averages.
ADVANCE_BUDGET_DAY = 25


def _next_ym(year: int, month: int) -> tuple[int, int]:
    """Return the (year, month) tuple for the month after the given one."""
    return (year, month + 1) if month < 12 else (year + 1, 1)


def _now_india():
    return timezone.now().astimezone(
        datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    )


# ── Shared helper — build actuals lookup ──────────────────────────────────────

def _actuals_map(budget_qs):
    """Return {(year, month): MonthlyActual} for the same months as budget_qs."""
    pairs = [(mb.year, mb.month) for mb in budget_qs]
    if not pairs:
        return {}
    from django.db.models import Q
    q = Q()
    for y, m in pairs:
        q |= Q(year=y, month=m)
    return {
        (a.year, a.month): a
        for a in MonthlyActual.objects.filter(q).prefetch_related('actual_splits')
    }


# ── Dashboard ────────────────────────────────────────────────────────────────

def dashboard(request):
    now = _now_india()
    after_25th = now.day >= ADVANCE_BUDGET_DAY

    # After the 25th: the dashboard displays the *next* month (the one being
    # budgeted) so the newly set budget is visible in the main split view.
    # Before the 25th: display the current calendar month as usual.
    year, month = _next_ym(now.year, now.month) if after_25th else (now.year, now.month)

    current_budget = (MonthlyBudget.objects
                      .filter(year=year, month=month, is_dummy=False)
                      .prefetch_related('splits')
                      .first())

    # Recent budgets (up to 6), oldest first for charts
    recent_budgets_qs = list(MonthlyBudget.objects
                             .filter(is_dummy=False)
                             .order_by('-year', '-month')
                             .prefetch_related('splits')[:6])

    # All actuals (up to 6 most recent) — covers months that may have no budget row
    recent_actuals_qs = list(MonthlyActual.objects
                             .order_by('-year', '-month')
                             .prefetch_related('actual_splits')[:6])

    # Build a unified ordered set of (year, month) across both sources
    budget_months  = {(mb.year, mb.month): mb for mb in recent_budgets_qs}
    actuals_by_month = {(ma.year, ma.month): ma for ma in recent_actuals_qs}
    all_months = sorted(
        set(budget_months) | set(actuals_by_month),
        reverse=True,
    )[:6]

    # Build the combined recent-month rows for the template
    recent_rows = []
    for ym in reversed(all_months):   # oldest first for charts
        mb = budget_months.get(ym)
        ma = actuals_by_month.get(ym)
        if mb:
            mb.actual_data = ma
        recent_rows.append({'budget': mb, 'actual': ma, 'year': ym[0], 'month': ym[1]})

    chart_labels, chart_totals, chart_actual_totals = [], [], []
    for row in recent_rows:
        chart_labels.append(f"{calendar.month_abbr[row['month']]} {row['year']}")
        chart_totals.append(float(row['budget'].total_budget) if row['budget'] else 0)
        chart_actual_totals.append(
            float(row['actual'].total_actual) if row['actual'] else None
        )

    # Previous month — needed for MoM and the reference panel
    prev_month = month - 1 if month > 1 else 12
    prev_year  = year if month > 1 else year - 1
    prev_budget = budget_months.get((prev_year, prev_month)) or (
        MonthlyBudget.objects
        .filter(year=prev_year, month=prev_month, is_dummy=False)
        .prefetch_related('splits').first()
    )
    prev_actual = actuals_by_month.get((prev_year, prev_month)) or (
        MonthlyActual.objects
        .filter(year=prev_year, month=prev_month)
        .prefetch_related('actual_splits').first()
    )

    # MoM comparison chart — current budget vs prev budget (+prev actual if available)
    mom_data = None
    if current_budget and prev_budget:
        curr_splits = {s.category: float(s.amount) for s in current_budget.splits.all()}
        prev_splits = {s.category: float(s.amount) for s in prev_budget.splits.all()}
        prev_act    = ({s.category: float(s.amount) for s in prev_actual.actual_splits.all()}
                       if prev_actual else None)
        mom_data = {
            'labels':       json.dumps([label for _, label in CATEGORIES]),
            'curr':         json.dumps([curr_splits.get(cat, 0) for cat, _ in CATEGORIES]),
            'prev':         json.dumps([prev_splits.get(cat, 0) for cat, _ in CATEGORIES]),
            'curr_label':   current_budget.month_year_label,
            'prev_label':   prev_budget.month_year_label,
        }
        if prev_act:
            mom_data['prev_actual']       = json.dumps([prev_act.get(cat, 0) for cat, _ in CATEGORIES])
            mom_data['prev_actual_label'] = f"{prev_budget.month_year_label} Actual"

    # Actuals avg: use year/month as cutoff — already equals next month after the 25th,
    # so Apr+May actuals are included automatically when displaying June.
    prev_actual_ref = _compute_actual_avg(year, month)

    budget_year, budget_month = year, month

    settings = AppSettings.get()
    cost_snapshot = get_or_fetch_cost_snapshot(year, month, city=settings.location)

    living_budget = investment_amt = emi_amt = None
    if current_budget:
        split_map = {s.category: s.amount for s in current_budget.splits.all()}
        investment_amt = split_map.get('investment', Decimal('0'))
        emi_amt        = split_map.get('emi', Decimal('0'))
        living_budget  = (current_budget.total_budget
                          - investment_amt
                          - emi_amt
                          - settings.rent_amount)

    context = {
        'current_budget':   current_budget,
        'year': year, 'month': month,
        'month_name':       calendar.month_name[month],
        'budget_year':       budget_year,
        'budget_month':      budget_month,
        'budget_month_name': calendar.month_abbr[budget_month],
        'after_25th':        after_25th,
        'cal_month_name':    calendar.month_name[now.month],
        'cal_day':           now.day,
        'recent_rows':      recent_rows,
        'chart_labels':        json.dumps(chart_labels),
        'chart_totals':        json.dumps(chart_totals),
        'chart_actual_totals': json.dumps(
            [v if v is not None else None for v in chart_actual_totals]
        ),
        'mom_data':         mom_data,
        'prev_actual_ref':  prev_actual_ref,
        'category_icons':   CATEGORY_ICONS,
        'categories':       CATEGORIES,
        'settings':         settings,
        'location':         settings.location,
        'cost_snapshot':    cost_snapshot,
        'living_budget':    living_budget,
        'investment_amt':   investment_amt,
        'emi_amt':          emi_amt,
    }
    return render(request, 'budget/dashboard.html', context)


# ── Set Budget ───────────────────────────────────────────────────────────────

def set_budget(request, year=None, month=None):
    now = _now_india()
    if year is None and month is None:
        # After the 25th: default to next month's budget so current month's
        # partial expenses can be included as training/reference data.
        if now.day >= ADVANCE_BUDGET_DAY:
            year, month = _next_ym(now.year, now.month)
        else:
            year, month = now.year, now.month
    else:
        if year is None:
            year = now.year
        if month is None:
            month = now.month

    existing = MonthlyBudget.objects.filter(year=year, month=month).first()

    if (request.method == 'POST'
            and 'total_budget' in request.POST
            and 'pct_groceries' not in request.POST):
        # Step 1 → import previous month's actuals, then compute AI suggestion
        form = BudgetInputForm(request.POST)
        if form.is_valid():
            total_budget = float(form.cleaned_data['total_budget'])

            # Import ALL available months from the latest .mmbak so the model
            # trains on the full spending history, not just the prior month.
            import_all_available_actuals(year, month)

            prediction = get_prediction_for_month(total_budget, year, month,
                                                  force_refresh=True)

            initial = {
                'year': year, 'month': month,
                'total_budget': form.cleaned_data['total_budget'],
                'notes': form.cleaned_data.get('notes', ''),
            }
            for cat in CATEGORY_KEYS:
                initial[f'pct_{cat}'] = round(prediction['percentages'][cat], 2)

            adj_form       = SplitAdjustmentForm(initial=initial)
            splits_display = _build_splits_display(
                prediction['percentages'], prediction['amounts']
            )
            actual_avg_ref = _compute_actual_avg(year, month)

            return render(request, 'budget/set_budget.html', {
                'step': 2,
                'input_form': form,
                'adj_form': adj_form,
                'total_budget': total_budget,
                'year': year, 'month': month,
                'month_name': calendar.month_name[month],
                'splits_display': splits_display,
                'history_count': prediction['history_count'],
                'history_with_actual': prediction['history_with_actual'],
                'cost_snapshot': prediction['cost_snapshot'],
                'investment_amount': prediction['investment'],
                'emi_amount': prediction['emi'],
                'rent_amount': prediction['rent'],
                'spendable': total_budget - prediction['investment'] - prediction['emi'] - prediction['rent'],
                'inv_params': prediction['inv_params'],
                'category_icons': CATEGORY_ICONS,
                'categories': CATEGORIES,
                'actual_avg_ref': actual_avg_ref,
            })
        adj_form = None

    elif request.method == 'POST' and 'pct_groceries' in request.POST:
        # Step 2 → save
        adj_form = SplitAdjustmentForm(request.POST)
        if adj_form.is_valid():
            total_budget = adj_form.cleaned_data['total_budget']
            pcts         = adj_form.get_percentages()
            total_pct    = sum(pcts.values())
            if total_pct > 0:
                pcts = {k: v / total_pct * 100 for k, v in pcts.items()}

            save_year  = adj_form.cleaned_data['year']
            save_month = adj_form.cleaned_data['month']
            amounts = pct_to_amounts(pcts, float(total_budget), save_year, save_month)

            mb, _ = MonthlyBudget.objects.update_or_create(
                year=save_year, month=save_month,
                defaults={
                    'total_budget': total_budget,
                    'notes': adj_form.cleaned_data.get('notes', ''),
                    'is_dummy': False,
                },
            )
            BudgetSplit.objects.filter(monthly_budget=mb).delete()
            for cat in CATEGORY_KEYS:
                BudgetSplit.objects.create(
                    monthly_budget=mb,
                    category=cat,
                    amount=amounts[cat],
                    percentage=Decimal(str(round(pcts[cat], 3))),
                )
            messages.success(request, f'Budget for {mb.month_name} {mb.year} saved!')
            return redirect('dashboard')

        total_budget = float(request.POST.get('total_budget', 0))
        input_form = BudgetInputForm(
            initial={'total_budget': total_budget, 'year': year, 'month': month}
        )
        return render(request, 'budget/set_budget.html', {
            'step': 2, 'input_form': input_form, 'adj_form': adj_form,
            'total_budget': total_budget,
            'year': year, 'month': month,
            'month_name': calendar.month_name[month],
            'category_icons': CATEGORY_ICONS, 'categories': CATEGORIES,
        })
    else:
        form = BudgetInputForm(initial={
            'year': year, 'month': month,
            'total_budget': float(existing.total_budget) if existing else '',
        })
        adj_form = None

    return render(request, 'budget/set_budget.html', {
        'step': 1, 'input_form': form, 'adj_form': adj_form,
        'existing': existing,
        'year': year, 'month': month,
        'month_name': calendar.month_name[month],
        'category_icons': CATEGORY_ICONS, 'categories': CATEGORIES,
    })


# ── History ──────────────────────────────────────────────────────────────────

def history(request):
    budgets_qs = list(MonthlyBudget.objects
                      .filter(is_dummy=False)
                      .prefetch_related('splits')
                      .order_by('-year', '-month'))
    actuals_qs = list(MonthlyActual.objects
                      .prefetch_related('actual_splits')
                      .order_by('-year', '-month'))

    budget_map  = {(mb.year, mb.month): mb for mb in budgets_qs}
    actuals_map = {(ma.year, ma.month): ma for ma in actuals_qs}

    # Attach actual_data to each budget row
    for mb in budgets_qs:
        mb.actual_data = actuals_map.get((mb.year, mb.month))

    # Build unified month list: budget months + actuals-only months, newest first
    all_months = sorted(
        set(budget_map) | set(actuals_map),
        reverse=True,
    )

    # Combined rows for the detail table
    history_rows = []
    for ym in all_months:
        mb = budget_map.get(ym)
        ma = actuals_map.get(ym)
        if mb:
            mb.actual_data = ma
        history_rows.append({'budget': mb, 'actual': ma, 'year': ym[0], 'month': ym[1]})

    # Chart uses the last 12 months (oldest first)
    recent_rows = list(reversed(history_rows[:12]))
    chart_labels = [f"{calendar.month_abbr[r['month']]} {r['year']}" for r in recent_rows]

    category_series, actual_series = {}, {}
    for cat, label in CATEGORIES:
        bseries, aseries = [], []
        for r in recent_rows:
            mb, ma = r['budget'], r['actual']
            split = mb.splits.filter(category=cat).first() if mb else None
            bseries.append(float(split.percentage) if split else 0.0)
            if ma:
                as_ = ma.actual_splits.filter(category=cat).first()
                aseries.append(float(as_.percentage) if as_ else 0.0)
            else:
                aseries.append(None)
        category_series[label] = bseries
        actual_series[label]   = aseries

    total_series  = [float(r['budget'].total_budget) if r['budget'] else 0 for r in recent_rows]
    actual_totals = [float(r['actual'].total_actual) if r['actual'] else None for r in recent_rows]

    # Determine the default mode for the stacked chart: whichever source has
    # more months of data.  Typically actuals accumulate faster than budgets.
    actual_months_count = sum(1 for r in recent_rows if r['actual'])
    budget_months_count = sum(1 for r in recent_rows if r['budget'])
    default_stack_mode  = 'actual' if actual_months_count >= budget_months_count else 'budget'

    return render(request, 'budget/history.html', {
        'history_rows':       history_rows,
        'chart_labels':       json.dumps(chart_labels),
        'category_series':    json.dumps(category_series),
        'actual_series':      json.dumps(actual_series),   # None → JSON null via json.dumps
        'total_series':       json.dumps(total_series),
        'actual_totals':      json.dumps(actual_totals),   # None → JSON null via json.dumps
        'default_stack_mode': default_stack_mode,
        'categories':         CATEGORIES,
        'category_icons':     CATEGORY_ICONS,
    })


# ── App Settings ─────────────────────────────────────────────────────────────

def app_settings(request):
    settings = AppSettings.get()
    if request.method == 'POST':
        form = AppSettingsForm(request.POST, instance=settings)
        if form.is_valid():
            form.save()
            messages.success(request, 'Settings saved.')
            return redirect('app_settings')
    else:
        form = AppSettingsForm(instance=settings)

    from .ml_engine import get_investment_parameters
    now = _now_india()
    inv_amt, inv_thresh = get_investment_parameters(now.year, now.month)

    return render(request, 'budget/settings.html', {
        'form': form,
        'settings': settings,
        'location': settings.location,
        'inv_amt': inv_amt,
        'inv_thresh': inv_thresh,
        'supported_cities': SUPPORTED_CITIES,
    })


# ── API ───────────────────────────────────────────────────────────────────────

def api_predict(request):
    try:
        total_budget = float(request.GET.get('budget', 0))
        year  = int(request.GET.get('year',  _now_india().year))
        month = int(request.GET.get('month', _now_india().month))
        if total_budget <= 0:
            return JsonResponse({'error': 'Invalid budget'}, status=400)
        prediction = get_prediction_for_month(total_budget, year, month)
        result = {
            cat: {
                'percentage': round(prediction['percentages'][cat], 2),
                'amount': float(prediction['amounts'][cat]),
            }
            for cat in CATEGORY_KEYS
        }
        return JsonResponse({
            'splits': result,
            'history_count': prediction['history_count'],
            'history_with_actual': prediction['history_with_actual'],
            'investment': prediction['investment'],
            'emi': prediction['emi'],
            'rent': prediction['rent'],
        })
    except Exception as exc:
        return JsonResponse({'error': str(exc)}, status=500)


# ── Delete Budget ─────────────────────────────────────────────────────────────

def delete_budget(request, year, month):
    mb = get_object_or_404(MonthlyBudget, year=year, month=month)
    if request.method == 'POST':
        label = f"{mb.month_name} {mb.year}"
        mb.delete()
        messages.success(request, f'Budget for {label} deleted.')
        next_url = request.POST.get('next') or request.GET.get('next')
        return redirect(next_url if next_url in ('dashboard', 'history') else 'history')
    return redirect('history')


# ── Detect Location ───────────────────────────────────────────────────────────

def api_detect_location(request):
    try:
        lat = float(request.GET.get('lat', ''))
        lon = float(request.GET.get('lon', ''))
    except (TypeError, ValueError):
        return JsonResponse({'error': 'lat and lon are required'}, status=400)

    city = resolve_city_from_coords(lat, lon)
    return JsonResponse({'city': city, 'supported_cities': SUPPORTED_CITIES})


# ── helpers ───────────────────────────────────────────────────────────────────

# ── Income Splitter ───────────────────────────────────────────────────────────

_SPLITTER_ACCOUNT_KEYS = {
    'hdfc':  'HDFC Bank',
    'idfc':  'IDFC First Bank',
    'union': 'Union Bank of India',
    'slice': 'Slice Small Finance Bank',
}

_INCOME_FIXED_DED_1 = 28_168
_INCOME_FIXED_DED_2 = 38_500

# Bank logos via Clearbit Logo API (returns square PNGs, works well for Indian banks).
# onerror fallback in the template renders a branded coloured badge.
_BANK_LOGOS = {
    'hdfc':  'https://logo.clearbit.com/hdfcbank.com',
    'idfc':  'https://logo.clearbit.com/idfcfirstbank.com',
    'union': 'https://logo.clearbit.com/unionbankofindia.co.in',
    'slice': 'https://logo.clearbit.com/sliceit.com',
}

# Default caps per account (user can override in the form)
_DEFAULT_CAPS = {
    'hdfc':  50_00_000.0,   # 50 L
    'idfc':  20_00_000.0,   # 20 L
    'union': 20_00_000.0,   # 20 L
    'slice':  2_00_000.0,   #  2 L
}

# Redistribution weights (proportional to base allocation share).
# When overflow is redistributed to uncapped banks, amounts are split in
# proportion to these weights so that HDFC (primary) absorbs the most, then
# IDFC/Union (secondary, equal), then Slice (tertiary).
# This naturally gives: HDFC+Slice capped → 50:50 IDFC:Union;
#                        IDFC+Slice capped → ~71:29 HDFC:Union;
#                        IDFC+Union capped → ~83:17 HDFC:Slice.
_BASE_WEIGHTS = {'hdfc': 0.50, 'idfc': 0.20, 'union': 0.20, 'slice': 0.10}

# Display order used throughout
_ACCOUNT_ORDER = ['slice', 'idfc', 'union', 'hdfc']


def _match_account(target: str, all_balances: dict):
    """Return (balance, matched_name) via exact → case-insensitive → partial match."""
    if target in all_balances:
        return all_balances[target], target
    for name, bal in all_balances.items():
        if name.lower() == target.lower():
            return bal, name
    tl = target.lower()
    for name, bal in all_balances.items():
        if tl in name.lower() or name.lower() in tl:
            return bal, name
    return None, target


def _weighted_redistribute(pool: float, absorbers: list) -> dict:
    """
    Distribute `pool` among `absorbers` proportionally by _BASE_WEIGHTS,
    respecting each absorber's capacity ceiling.

    absorbers: [(key, max_additional_capacity), ...]   capacity=inf means no cap.
    Returns {key: amount_assigned}.

    The last absorber in each iteration receives the exact remainder so the
    sum of assigned values always equals pool (no rounding drift).
    """
    remaining = round(pool, 2)
    avail = list(absorbers)
    assigned = {}

    for _ in range(20):
        if remaining < 0.005 or not avail:
            break
        total_w = sum(_BASE_WEIGHTS.get(k, 0.1) for k, _ in avail)
        new_avail = []
        new_remaining = 0.0
        so_far = 0.0
        n = len(avail)

        for i, (key, cap) in enumerate(avail):
            if i < n - 1:
                share = round(remaining * _BASE_WEIGHTS.get(key, 0.1) / total_w, 2)
            else:
                # Last absorber gets the exact remainder — prevents rounding drift.
                share = round(remaining - so_far, 2)

            actual = min(share, cap) if cap != float('inf') else share
            actual = round(actual, 2)
            assigned[key] = round(assigned.get(key, 0) + actual, 2)
            so_far += actual

            leftover = round(share - actual, 2)
            if leftover > 0.005:
                new_remaining += leftover
            elif cap != float('inf') and cap - actual > 0.005:
                new_avail.append((key, round(cap - actual, 2)))

        avail = new_avail
        remaining = round(new_remaining, 2)

    return assigned


def _apply_income_caps(base_alloc: dict, current: dict, caps: dict):
    """
    Apply per-bank caps to income allocations.
    Overflow is redistributed by _BASE_WEIGHTS among banks with remaining capacity.

    Returns:
      alloc       – final per-bank income allocations
      liquid      – amount that could not be placed (all caps met)
      capped      – {key: overflow_amount} for banks whose cap was hit
    """
    alloc = dict(base_alloc)
    pool = 0.0
    capped = {}

    for key, cap in caps.items():
        if cap is None:
            continue
        cur = current.get(key) or 0
        alloc_k = alloc.get(key, 0)
        capacity = max(0.0, cap - cur)
        if alloc_k > capacity + 0.005:
            overflow = round(alloc_k - capacity, 2)
            pool += overflow
            alloc[key] = round(capacity, 2)
            capped[key] = overflow

    pool = round(pool, 2)
    liquid = 0.0

    for _ in range(20):
        if pool < 0.005:
            break
        absorbers = []
        for key in _ACCOUNT_ORDER:
            cap = caps.get(key)
            cur = current.get(key) or 0
            new_bal = cur + alloc.get(key, 0)
            if cap is None:
                absorbers.append((key, float('inf')))
            elif new_bal < cap - 0.005:
                absorbers.append((key, round(cap - new_bal, 2)))
        if not absorbers:
            liquid = round(pool, 2)
            pool = 0
            break
        added = _weighted_redistribute(pool, absorbers)
        new_pool = pool - sum(added.values())
        for key, amt in added.items():
            alloc[key] = round(alloc.get(key, 0) + amt, 2)
        pool = round(max(0, new_pool), 2)

    return alloc, round(liquid, 2), capped


def _compute_pre_excess(current: dict, caps: dict):
    """
    Find pre-existing excess (current balance > cap) and redistribute by _BASE_WEIGHTS.

    Returns:
      excess_out  – {key: amount to move OUT of this account}
      received    – {key: amount received from redistribution}
      liquid      – amount that couldn't be placed (all other caps met)
    """
    excess_out = {}
    pool = 0.0
    for key, cap in caps.items():
        if cap is None:
            continue
        cur = current.get(key) or 0
        if cur > cap + 0.005:
            exc = round(cur - cap, 2)
            excess_out[key] = exc
            pool += exc

    pool = round(pool, 2)
    if pool < 0.005:
        return {}, {}, 0.0

    received = {}
    liquid = 0.0

    for _ in range(20):
        if pool < 0.005:
            break
        absorbers = []
        for key in _ACCOUNT_ORDER:
            if key in excess_out:
                continue
            cap = caps.get(key)
            cur = current.get(key) or 0
            cur_recv = received.get(key, 0)
            if cap is None:
                absorbers.append((key, float('inf')))
            elif cur + cur_recv < cap - 0.005:
                absorbers.append((key, round(cap - cur - cur_recv, 2)))
        if not absorbers:
            liquid = round(pool, 2)
            pool = 0
            break
        added = _weighted_redistribute(pool, absorbers)
        new_pool = pool - sum(added.values())
        for key, amt in added.items():
            received[key] = round(received.get(key, 0) + amt, 2)
        pool = round(max(0, new_pool), 2)

    return excess_out, {k: v for k, v in received.items() if v > 0.005}, round(liquid, 2)


def _read_caps_from_post(post) -> dict:
    """Parse per-bank caps from POST data. Returns {key: float_or_None}."""
    caps = {}
    for key, default in _DEFAULT_CAPS.items():
        nocap = bool(post.get(f'nocap_{key}'))
        if nocap:
            caps[key] = None
        else:
            raw = post.get(f'cap_{key}', '').replace(',', '').strip()
            try:
                val = round(float(raw), 2) if raw else default
                caps[key] = max(0.0, val)
            except ValueError:
                caps[key] = default
    return caps


def _caps_to_form(caps: dict) -> dict:
    """Convert caps dict to {key: {value, nocap}} for template rendering."""
    return {
        key: {'value': caps.get(key), 'nocap': caps.get(key) is None}
        for key in _DEFAULT_CAPS
    }


def income_splitter(request):
    filepath     = find_latest_mmbak()
    mmbak_name   = os.path.basename(filepath) if filepath else None
    all_balances = get_all_account_balances(filepath) if filepath else {}
    mmbak_error  = None if filepath else "No .mmbak backup file found."

    current = {}
    matched = {}
    for key, target in _SPLITTER_ACCOUNT_KEYS.items():
        bal, name = _match_account(target, all_balances)
        current[key] = bal
        matched[key] = name

    # Default caps (used for GET-state previews)
    default_caps = dict(_DEFAULT_CAPS)

    # ── Pre-existing overflow preview (shown in left panel on load) ─────────
    exc_preview_out, exc_preview_recv, exc_preview_liq = _compute_pre_excess(
        {k: v for k, v in current.items() if v is not None}, default_caps
    )
    overflow_preview = None
    if exc_preview_out:
        rows_preview = []
        for key in _ACCOUNT_ORDER:
            cap = default_caps.get(key)
            cur = current.get(key)
            out = exc_preview_out.get(key, 0)
            recv = exc_preview_recv.get(key, 0)
            if out > 0 or recv > 0.005:
                rows_preview.append({
                    'key': key, 'name': matched[key],
                    'out': out, 'recv': recv,
                    'new_bal': round(cur - out + recv, 2) if cur is not None else None,
                    'cap': cap,
                })
        overflow_preview = {
            'rows': rows_preview,
            'liquid': exc_preview_liq,
        }

    result            = None
    redistribute_only = None   # result for "Redistribute" button (no income)
    income_input      = None
    landing_key       = 'slice'
    error             = None
    caps_form         = _caps_to_form(default_caps)   # pre-fill form with defaults

    if request.method == 'POST':
        caps_used = _read_caps_from_post(request.POST)
        caps_form = _caps_to_form(caps_used)
        action    = request.POST.get('action', 'calculate')

        if action == 'redistribute':
            # ── Redistribute only (no income) ────────────────────────────
            cur_known = {k: v for k, v in current.items() if v is not None}
            exc_out, exc_recv, exc_liq = _compute_pre_excess(cur_known, caps_used)
            rows_r = []
            for key in _ACCOUNT_ORDER:
                cur = current.get(key)
                cap = caps_used.get(key)
                out  = exc_out.get(key, 0)
                recv = exc_recv.get(key, 0)
                rows_r.append({
                    'key':     key,
                    'name':    matched[key],
                    'cap':     cap,
                    'current': cur,
                    'out':     out,
                    'recv':    recv,
                    'new_bal': (round(cur - out + recv, 2) if cur is not None else None),
                })
            redistribute_only = {
                'rows':   rows_r,
                'liquid': exc_liq,
                'any':    bool(exc_out),
            }

        else:
            # ── Full income calculation ───────────────────────────────────
            try:
                raw = request.POST.get('income', '').replace(',', '').strip()
                income_input = float(raw)
                if income_input <= 0:
                    raise ValueError("Income must be a positive amount.")

                landing_key = request.POST.get('landing_account', 'slice')
                if landing_key not in _SPLITTER_ACCOUNT_KEYS:
                    landing_key = 'slice'

                X    = income_input
                ded1 = 0.0
                ded2 = 0.0
                if X >= _INCOME_FIXED_DED_1:
                    ded1 = float(_INCOME_FIXED_DED_1); X -= ded1
                if X >= _INCOME_FIXED_DED_2:
                    ded2 = float(_INCOME_FIXED_DED_2); X -= ded2

                distributable = round(X, 2)
                post_ded1     = round(income_input - ded1, 2)

                # Base allocations (10 / 20 / 20 / 50%)
                base = {
                    'slice': round(distributable * 0.10, 2),
                    'idfc':  round(distributable * 0.20, 2),
                    'union': round(distributable * 0.20, 2),
                }
                base['hdfc'] = round(income_input - base['slice'] - base['idfc'] - base['union'], 2)

                # Apply caps to income allocations
                cur_known = {k: (v or 0) for k, v in current.items()}
                income_alloc, income_liq, capped_by_income = _apply_income_caps(
                    base, cur_known, caps_used
                )

                # Pre-existing excess redistribution (independent of income)
                pre_exc_out, pre_exc_recv, pre_exc_liq = _compute_pre_excess(
                    cur_known, caps_used
                )

                total_liquid = round(income_liq + pre_exc_liq, 2)

                # Build per-bank rows
                base_pct = {'slice': '10 %', 'idfc': '20 %', 'union': '20 %', 'hdfc': 'Rem.'}
                rows = []
                for key in _ACCOUNT_ORDER:
                    alloc    = income_alloc.get(key, 0)
                    cur      = current.get(key)
                    cap      = caps_used.get(key)
                    capped   = key in capped_by_income
                    pre_out  = pre_exc_out.get(key, 0)
                    pre_recv = pre_exc_recv.get(key, 0)

                    if capped:
                        pv = round(alloc / distributable * 100, 1) if distributable else 0
                        pct_label = f'{pv} % (capped)' if alloc > 0.005 else '0 % (capped)'
                    else:
                        pct_label = base_pct[key]

                    new_bal = (
                        round(cur + alloc + pre_recv - pre_out, 2)
                        if cur is not None else None
                    )

                    rows.append({
                        'key':      key,
                        'name':     matched[key],
                        'pct':      pct_label,
                        'alloc':    alloc,
                        'current':  cur,
                        'cap':      cap,
                        'capped':   capped,
                        'pre_out':  pre_out,
                        'pre_recv': pre_recv,
                        'new_bal':  new_bal,
                    })

                alloc_map = {r['key']: r['alloc'] for r in rows}
                total_out = round(
                    sum(v for k, v in alloc_map.items() if k != landing_key), 2
                )

                result = {
                    'income':        income_input,
                    'ded1':          ded1,
                    'ded2':          ded2,
                    'post_ded1':     post_ded1,
                    'distributable': distributable,
                    'hdfc_var':      round(base['hdfc'] - ded1 - ded2, 2),
                    'rows':          rows,
                    'base':          base,
                    'landing_key':   landing_key,
                    'landing_name':  matched[landing_key],
                    'total_out':     total_out,
                    'any_cap':       bool(capped_by_income),
                    'capped_banks':  list(capped_by_income.keys()),
                    'pre_exc_out':   pre_exc_out,
                    'pre_exc_recv':  pre_exc_recv,
                    'income_liq':    income_liq,
                    'pre_exc_liq':   pre_exc_liq,
                    'total_liquid':  total_liquid,
                    'caps':          caps_used,
                }

            except (ValueError, TypeError) as exc:
                error = str(exc)

    return render(request, 'budget/income_splitter.html', {
        'current':          current,
        'matched':          matched,
        'all_balances':     all_balances,
        'mmbak_error':      mmbak_error,
        'mmbak_name':       mmbak_name,
        'result':           result,
        'redistribute_only': redistribute_only,
        'overflow_preview': overflow_preview,
        'income_input':     income_input,
        'landing_key':      landing_key,
        'error':            error,
        'ded1':             _INCOME_FIXED_DED_1,
        'ded2':             _INCOME_FIXED_DED_2,
        'caps_form':        caps_form,
        'default_caps':     _DEFAULT_CAPS,
        'bank_logos':       _BANK_LOGOS,
    })


def _build_splits_display(percentages: dict, amounts: dict) -> list:
    rows = []
    for cat, label in CATEGORIES:
        rows.append({
            'key': cat,
            'label': label,
            'icon': CATEGORY_ICONS.get(cat, ''),
            'percentage': round(percentages.get(cat, 0), 2),
            'amount': amounts.get(cat, Decimal('0')),
        })
    return rows
