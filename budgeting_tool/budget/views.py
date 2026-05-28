import json
import calendar
import datetime

from decimal import Decimal, ROUND_HALF_UP
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.utils import timezone
from django.contrib import messages

from .models import MonthlyBudget, BudgetSplit, AppSettings, CATEGORIES, CATEGORY_ICONS
from .forms import BudgetInputForm, SplitAdjustmentForm, AppSettingsForm
from .ml_engine import get_prediction_for_month, pct_to_amounts, CATEGORIES as CATEGORY_KEYS
from .cost_data import get_or_fetch_cost_snapshot


def _now_india():
    return timezone.now().astimezone(
        datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    )


# ── Dashboard ────────────────────────────────────────────────────────────────

def dashboard(request):
    now = _now_india()
    year, month = now.year, now.month

    current_budget = (MonthlyBudget.objects
                      .filter(year=year, month=month, is_dummy=False)
                      .prefetch_related('splits')
                      .first())
    recent_budgets = (MonthlyBudget.objects
                      .filter(is_dummy=False)
                      .order_by('-year', '-month')
                      .prefetch_related('splits')[:6])

    chart_labels, chart_totals = [], []
    for mb in reversed(list(recent_budgets)):
        chart_labels.append(mb.month_year_label)
        chart_totals.append(float(mb.total_budget))

    # MoM comparison: current vs previous month (shown from Jun 2026 onwards)
    prev_month = month - 1 if month > 1 else 12
    prev_year  = year if month > 1 else year - 1
    prev_budget = (MonthlyBudget.objects
                   .filter(year=prev_year, month=prev_month, is_dummy=False)
                   .prefetch_related('splits')
                   .first())

    mom_data = None
    if current_budget and prev_budget:
        curr_splits = {s.category: float(s.amount) for s in current_budget.splits.all()}
        prev_splits = {s.category: float(s.amount) for s in prev_budget.splits.all()}
        mom_cat_labels = [label for _, label in CATEGORIES]
        mom_curr = [curr_splits.get(cat, 0) for cat, _ in CATEGORIES]
        mom_prev = [prev_splits.get(cat, 0) for cat, _ in CATEGORIES]
        mom_data = {
            'labels':       json.dumps(mom_cat_labels),
            'curr':         json.dumps(mom_curr),
            'prev':         json.dumps(mom_prev),
            'curr_label':   current_budget.month_year_label,
            'prev_label':   prev_budget.month_year_label,
        }

    settings = AppSettings.get()
    cost_snapshot = get_or_fetch_cost_snapshot(year, month)

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
        'current_budget': current_budget,
        'year': year, 'month': month,
        'month_name': calendar.month_name[month],
        'recent_budgets': recent_budgets,
        'chart_labels': json.dumps(chart_labels),
        'chart_totals': json.dumps(chart_totals),
        'mom_data': mom_data,
        'category_icons': CATEGORY_ICONS,
        'categories': CATEGORIES,
        'settings': settings,
        'cost_snapshot': cost_snapshot,
        'living_budget': living_budget,
        'investment_amt': investment_amt,
        'emi_amt': emi_amt,
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
        # Step 1 → compute AI suggestion
        form = BudgetInputForm(request.POST)
        if form.is_valid():
            total_budget = float(form.cleaned_data['total_budget'])
            prediction = get_prediction_for_month(total_budget, year, month, force_refresh=True)

            initial = {
                'year': year, 'month': month,
                'total_budget': form.cleaned_data['total_budget'],
                'notes': form.cleaned_data.get('notes', ''),
            }
            for cat in CATEGORY_KEYS:
                initial[f'pct_{cat}'] = round(prediction['percentages'][cat], 2)

            adj_form = SplitAdjustmentForm(initial=initial)
            splits_display = _build_splits_display(
                prediction['percentages'], prediction['amounts']
            )
            return render(request, 'budget/set_budget.html', {
                'step': 2,
                'input_form': form,
                'adj_form': adj_form,
                'total_budget': total_budget,
                'year': year, 'month': month,
                'month_name': calendar.month_name[month],
                'splits_display': splits_display,
                'history_count': prediction['history_count'],
                'cost_snapshot': prediction['cost_snapshot'],
                'investment_amount': prediction['investment'],
                'emi_amount': prediction['emi'],
                'rent_amount': prediction['rent'],
                'spendable': total_budget - prediction['investment'] - prediction['emi'],
                'inv_params': prediction['inv_params'],
                'category_icons': CATEGORY_ICONS,
                'categories': CATEGORIES,
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
    budgets = (MonthlyBudget.objects
               .filter(is_dummy=False)
               .prefetch_related('splits')
               .order_by('-year', '-month'))
    recent  = list(reversed(list(budgets[:12])))

    chart_labels     = [mb.month_year_label for mb in recent]
    category_series  = {}
    for cat, label in CATEGORIES:
        series = []
        for mb in recent:
            split = mb.splits.filter(category=cat).first()
            series.append(float(split.percentage) if split else 0.0)
        category_series[label] = series
    total_series = [float(mb.total_budget) for mb in recent]

    return render(request, 'budget/history.html', {
        'budgets': budgets,
        'chart_labels': json.dumps(chart_labels),
        'category_series': json.dumps(category_series),
        'total_series': json.dumps(total_series),
        'categories': CATEGORIES,
        'category_icons': CATEGORY_ICONS,
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
        'inv_amt': inv_amt,
        'inv_thresh': inv_thresh,
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
