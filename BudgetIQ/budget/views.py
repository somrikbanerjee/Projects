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
_SLICE_CAP          = 200_000.0   # Slice SFB balance ceiling


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


def _split_5_3_2(amount: float):
    """Split `amount` in HDFC:IDFC:Union = 5:3:2 (50 % : 30 % : 20 %).
    Returns (to_hdfc, to_idfc, to_union) — remainder goes to HDFC."""
    to_idfc  = round(amount * 0.30, 2)
    to_union = round(amount * 0.20, 2)
    to_hdfc  = round(amount - to_idfc - to_union, 2)
    return to_hdfc, to_idfc, to_union


def income_splitter(request):
    filepath     = find_latest_mmbak()
    mmbak_name   = os.path.basename(filepath) if filepath else None
    all_balances = get_all_account_balances(filepath) if filepath else {}
    mmbak_error  = None if filepath else "No .mmbak backup file found in the MoneyManager folder."

    current = {}
    matched = {}
    for key, target in _SPLITTER_ACCOUNT_KEYS.items():
        bal, name = _match_account(target, all_balances)
        current[key] = bal
        matched[key] = name

    slice_cur = current.get('slice')

    # Slice overflow check — computed on every load so REDISTRIBUTE is always fresh.
    # Also exposed as a standalone result when ?redistribute=1 is passed.
    slice_overflow_preview = None
    if slice_cur is not None and slice_cur > _SLICE_CAP:
        excess = round(slice_cur - _SLICE_CAP, 2)
        p_hdfc, p_idfc, p_union = _split_5_3_2(excess)
        slice_overflow_preview = {
            'excess':   excess,
            'to_hdfc':  p_hdfc,
            'to_idfc':  p_idfc,
            'to_union': p_union,
        }

    # Standalone redistribute mode — show overflow result on the right panel
    redistribute_result = None
    if request.method == 'GET' and request.GET.get('redistribute'):
        if slice_overflow_preview:
            # Enrich with new balances for each account
            rdist = dict(slice_overflow_preview)
            rdist['slice_new']  = round(_SLICE_CAP, 2)
            rdist['hdfc_new']   = (round(current['hdfc'] + rdist['to_hdfc'], 2)
                                   if current['hdfc'] is not None else None)
            rdist['idfc_new']   = (round(current['idfc'] + rdist['to_idfc'], 2)
                                   if current['idfc'] is not None else None)
            rdist['union_new']  = (round(current['union'] + rdist['to_union'], 2)
                                   if current['union'] is not None else None)
            redistribute_result = rdist
        else:
            redistribute_result = {}   # empty dict = "nothing to redistribute" sentinel

    result            = None
    income_input      = None
    error             = None
    landing_key       = 'slice'      # default; updated from POST below
    slice_cap_form    = _SLICE_CAP   # value shown in the form input; updated from POST

    if request.method == 'POST':
        try:
            raw = request.POST.get('income', '').replace(',', '').strip()
            income_input = float(raw)
            landing_key  = request.POST.get('landing_account', 'slice')
            if landing_key not in _SPLITTER_ACCOUNT_KEYS:
                landing_key = 'slice'

            # User-configurable Slice cap (default 2 L)
            cap_raw = request.POST.get('slice_cap_input', '').replace(',', '').strip()
            try:
                slice_cap_used = round(float(cap_raw), 2) if cap_raw else _SLICE_CAP
                if slice_cap_used < 0:
                    slice_cap_used = _SLICE_CAP
            except ValueError:
                slice_cap_used = _SLICE_CAP
            slice_cap_form = slice_cap_used   # persist in form for re-render

            if income_input <= 0:
                raise ValueError("Income must be a positive amount.")

            X    = income_input
            ded1 = 0.0
            ded2 = 0.0
            if X >= _INCOME_FIXED_DED_1:
                ded1 = float(_INCOME_FIXED_DED_1); X -= ded1
            if X >= _INCOME_FIXED_DED_2:
                ded2 = float(_INCOME_FIXED_DED_2); X -= ded2

            distributable = round(X, 2)
            post_ded1     = round(income_input - ded1, 2)

            # ── Base income allocations (before any cap adjustment) ──────
            slice_normal = round(distributable * 0.10, 2)
            idfc_base    = round(distributable * 0.20, 2)
            union_base   = round(distributable * 0.20, 2)

            cap_case              = None
            slice_alloc           = slice_normal
            slice_income_overflow = 0.0   # Slice's income share redirected to others
            slice_excess          = 0.0   # Pre-existing Slice excess to move out (Case 2)

            if slice_cur is not None:
                if slice_cur >= slice_cap_used:
                    # Case 2: Slice already over cap — give it nothing, move excess out
                    cap_case              = 'pre'
                    slice_alloc           = 0.0
                    slice_income_overflow = slice_normal
                    slice_excess          = round(slice_cur - slice_cap_used, 2)
                elif round(slice_cur + slice_normal, 2) > slice_cap_used:
                    # Case 3: Top Slice up to exactly the cap, redirect the rest
                    cap_case              = 'post'
                    slice_alloc           = round(slice_cap_used - slice_cur, 2)
                    slice_income_overflow = round(slice_normal - slice_alloc, 2)

            # ── Redistribute Slice's income overflow (5:3:2 → HDFC:IDFC:Union) ──
            inc_ov_hdfc, inc_ov_idfc, inc_ov_union = _split_5_3_2(slice_income_overflow)

            idfc_income  = round(idfc_base + inc_ov_idfc,  2)
            union_income = round(union_base + inc_ov_union, 2)
            hdfc_var_inc = round(distributable - slice_alloc - idfc_income - union_income, 2)

            # ── Redistribute pre-existing Slice excess (Case 2, 5:3:2) ──────────
            exc_hdfc, exc_idfc, exc_union = _split_5_3_2(slice_excess)

            # ── Final combined allocations ───────────────────────────────────────
            idfc_alloc  = round(idfc_income  + exc_idfc,  2)
            union_alloc = round(union_income + exc_union, 2)
            hdfc_var    = round(hdfc_var_inc + exc_hdfc,  2)
            hdfc_alloc  = round(hdfc_var + ded1 + ded2,   2)

            # ── New balances ─────────────────────────────────────────────────────
            # mmbak balances are pre-income; new balance = current + allocation for all accounts.
            def _new_bal(cur_bal, alloc):
                return round(cur_bal + alloc, 2) if cur_bal is not None else None

            # Slice new balance caps at the user-set cap when either cap case fires
            if cap_case and slice_cur is not None:
                slice_new_bal = round(slice_cap_used, 2)
            else:
                slice_new_bal = _new_bal(slice_cur, slice_alloc)

            # pct label for the allocation table
            if cap_case == 'pre':
                slice_pct = '0 % (over cap)'
            elif cap_case == 'post':
                p = round(slice_alloc / distributable * 100, 1) if distributable else 0
                slice_pct = f'{p} % (capped)'
            else:
                slice_pct = '10 %'

            result = {
                'income':        income_input,
                'ded1':          ded1,
                'ded2':          ded2,
                'post_ded1':     post_ded1,
                'distributable': distributable,
                'hdfc_var':      hdfc_var,
                'rows': [
                    {
                        'key':     'slice',
                        'name':    matched['slice'],
                        'pct':     slice_pct,
                        'alloc':   slice_alloc,
                        'current': slice_cur,
                        'new_bal': slice_new_bal,
                    },
                    {
                        'key':     'idfc',
                        'name':    matched['idfc'],
                        'pct':     '20 %' if not cap_case else '20 % + overflow',
                        'alloc':   idfc_alloc,
                        'current': current['idfc'],
                        'new_bal': _new_bal(current['idfc'], idfc_alloc),
                    },
                    {
                        'key':     'union',
                        'name':    matched['union'],
                        'pct':     '20 %' if not cap_case else '20 % + overflow',
                        'alloc':   union_alloc,
                        'current': current['union'],
                        'new_bal': _new_bal(current['union'], union_alloc),
                    },
                    {
                        'key':     'hdfc',
                        'name':    matched['hdfc'],
                        'pct':     'Remainder',
                        'alloc':   hdfc_alloc,
                        'current': current['hdfc'],
                        'new_bal': _new_bal(current['hdfc'], hdfc_alloc),
                    },
                ],
                # Total leaving the landing account
                'landing_key':  landing_key,
                'landing_name': matched[landing_key],
                'total_out': round(
                    sum(a for k, a in [
                        ('slice', slice_alloc), ('idfc', idfc_alloc),
                        ('union', union_alloc), ('hdfc', hdfc_alloc),
                    ] if k != landing_key),
                    2,
                ),
                # Cap meta — used by the template for "What to do" section
                'cap_case':              cap_case,
                'slice_cap_used':        slice_cap_used,
                'slice_income_overflow': slice_income_overflow,
                'slice_excess':          slice_excess,
                'exc_hdfc':              exc_hdfc,
                'exc_idfc':              exc_idfc,
                'exc_union':             exc_union,
                # Income-only amounts (needed to break down Case 2 "What to do")
                'idfc_from_income':   idfc_income,
                'union_from_income':  union_income,
                'hdfc_from_income':   round(hdfc_var_inc + ded1 + ded2, 2),
            }

        except (ValueError, TypeError) as exc:
            error = str(exc)

    return render(request, 'budget/income_splitter.html', {
        'current':                current,
        'matched':                matched,
        'all_balances':           all_balances,
        'mmbak_error':            mmbak_error,
        'mmbak_name':             mmbak_name,
        'result':                 result,
        'income_input':           income_input,
        'error':                  error,
        'ded1':                   _INCOME_FIXED_DED_1,
        'ded2':                   _INCOME_FIXED_DED_2,
        'slice_cap':              int(_SLICE_CAP),    # default cap (for redistribute / preview)
        'slice_cap_form':         slice_cap_form,     # persists form input across submits
        'slice_overflow_preview': slice_overflow_preview,
        'redistribute_result':    redistribute_result,
        'landing_key':            landing_key,
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
