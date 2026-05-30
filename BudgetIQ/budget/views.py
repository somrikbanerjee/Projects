import json
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
from .mmbak_importer import import_actuals_for_month, import_all_available_actuals


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
    year, month = now.year, now.month

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

    # Keep recent_budgets for backward-compat chart data
    chart_labels, chart_totals = [], []
    for row in recent_rows:
        lbl = f"{calendar.month_abbr[row['month']]} {row['year']}"
        chart_labels.append(lbl)
        chart_totals.append(float(row['budget'].total_budget) if row['budget'] else 0)

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

    # Actuals summary card — average across all available months before today
    prev_actual_ref = _compute_actual_avg(year, month)

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
        'recent_rows':      recent_rows,
        'chart_labels':     json.dumps(chart_labels),
        'chart_totals':     json.dumps(chart_totals),
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

    return render(request, 'budget/history.html', {
        'history_rows':     history_rows,
        'chart_labels':     json.dumps(chart_labels),
        'category_series':  json.dumps(category_series),
        'actual_series':    json.dumps(actual_series),
        'total_series':     json.dumps(total_series),
        'actual_totals':    json.dumps([v if v is not None else 'null' for v in actual_totals]),
        'categories':       CATEGORIES,
        'category_icons':   CATEGORY_ICONS,
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
