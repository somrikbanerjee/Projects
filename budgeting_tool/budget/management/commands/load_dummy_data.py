"""
Management command: load 16 months of realistic dummy budget data for Hyderabad.

Fixed rules applied:
  - Investment = ₹50,000 if budget ≥ ₹70,000 else ₹0  (FY Apr 2026 base)
  - Loan EMI   = ₹28,168 until Sep 2028
  - Home floor = ₹38,500 (rent)

Usage:
    python manage.py load_dummy_data
    python manage.py load_dummy_data --clear
"""

from decimal import Decimal
from django.core.management.base import BaseCommand

from budget.models import MonthlyBudget, BudgetSplit, CostSnapshot, AppSettings
from budget.ml_engine import (
    _normalise, get_investment_parameters, _inv_amount, _apply_rent_floor,
    CATEGORIES, ML_CATEGORIES,
)

DUMMY_MONTHS = [
    (2025,  1), (2025,  2), (2025,  3), (2025,  4),
    (2025,  5), (2025,  6), (2025,  7), (2025,  8),
    (2025,  9), (2025, 10), (2025, 11), (2025, 12),
    (2026,  1), (2026,  2), (2026,  3), (2026,  4),
]

DUMMY_BUDGETS = {
    # Investment applies when budget - EMI(28168) - investment(50k) >= rent(38500)
    # i.e. budget >= 116668. Adjusted budgets reflect realistic dual-income Hyderabad HH.
    (2025,  1): 125000,  # good month, investment applies
    (2025,  2): 118000,  # investment applies
    (2025,  3): 130000,  # Holi travel bump, investment applies
    (2025,  4): 115000,  # investment applies (barely)
    (2025,  5): 120000,  # investment applies
    (2025,  6): 122000,  # investment applies
    (2025,  7): 140000,  # monsoon + bonus month, investment applies
    (2025,  8): 118000,  # investment applies
    (2025,  9): 116000,  # investment applies (just above threshold)
    (2025, 10): 155000,  # Durga Puja/Diwali prep, investment applies
    (2025, 11): 160000,  # Diwali peak, investment applies
    (2025, 12): 148000,  # Christmas/New Year, investment applies
    (2026,  1): 135000,  # New Year / Pongal
    (2026,  2):  95000,  # lean month — budget < effective threshold → no investment
    (2026,  3): 142000,  # Holi, investment applies
    (2026,  4): 128000,  # investment applies
}

# Non-investment, non-EMI splits as % of ML-spendable portion (sums to ~100)
# (groc, tran, food, hlth, home, entr, subs, shop, trav, othr)
NI_SPLITS = {
    (2025,  1):  [14.0, 7.5, 12.0, 4.5, 31.0, 4.0, 2.5, 8.5, 7.0, 9.0],
    (2025,  2):  [15.0, 8.0, 12.5, 5.0, 31.5, 3.5, 2.5, 7.5, 5.5, 9.0],
    (2025,  3):  [13.0, 7.5, 12.0, 4.0, 28.5, 5.0, 2.5, 7.5, 10.5, 9.5],  # Holi
    (2025,  4):  [15.5, 8.5, 13.0, 5.5, 30.0, 4.0, 2.5, 7.5, 5.0, 8.5],
    (2025,  5):  [15.0, 8.0, 13.0, 5.0, 31.0, 3.5, 2.5, 8.0, 5.0, 9.0],
    (2025,  6):  [14.5, 8.0, 12.5, 4.5, 30.5, 3.5, 2.5, 8.0, 6.5, 9.5],
    (2025,  7):  [13.5, 7.5, 13.0, 4.0, 27.0, 5.0, 2.5, 7.5, 10.0, 10.0],  # monsoon
    (2025,  8):  [14.0, 7.5, 12.5, 4.5, 29.0, 5.0, 2.5, 9.5, 8.0, 8.0],
    (2025,  9):  [15.0, 8.0, 13.0, 5.0, 30.5, 3.5, 2.5, 7.5, 5.5, 9.5],
    (2025, 10):  [12.5, 7.0, 13.0, 3.5, 25.5, 6.0, 2.5, 15.0, 10.5, 4.5],  # Durga Puja
    (2025, 11):  [11.5, 6.5, 13.5, 3.0, 22.5, 6.5, 2.5, 18.0, 11.0, 5.0],  # Diwali
    (2025, 12):  [12.5, 7.0, 13.0, 3.5, 25.0, 6.5, 2.5, 13.0, 12.0, 5.0],  # Christmas
    (2026,  1):  [13.5, 7.5, 12.5, 4.5, 28.5, 6.0, 2.5, 11.0, 10.0, 4.0],  # New Year
    (2026,  2):  [18.0, 10.0, 14.0, 5.0, 33.5, 5.0, 3.0, 5.5, 2.5, 3.5],   # lean
    (2026,  3):  [12.5, 7.0, 12.0, 3.5, 26.0, 5.0, 2.5, 8.5, 11.5, 11.5],  # Holi
    (2026,  4):  [14.0, 7.5, 12.5, 4.5, 28.5, 4.5, 2.5, 8.5, 7.0, 10.5],
}

NI_CAT_ORDER = [
    'groceries', 'transport', 'food', 'healthcare', 'home',
    'entertainment', 'subscriptions', 'shopping', 'travel', 'other',
]

DUMMY_COST = {
    (2025,  1): dict(india_inflation_pct=5.4, petrol_price_hyd=103.2, rent_index=28.5, groceries_index=14.1, restaurant_index=11.0),
    (2025,  7): dict(india_inflation_pct=5.1, petrol_price_hyd=103.8, rent_index=28.8, groceries_index=14.3, restaurant_index=11.2),
    (2025, 11): dict(india_inflation_pct=5.3, petrol_price_hyd=104.5, rent_index=29.2, groceries_index=14.6, restaurant_index=11.5),
    (2026,  1): dict(india_inflation_pct=5.2, petrol_price_hyd=104.0, rent_index=29.5, groceries_index=14.8, restaurant_index=11.7),
    (2026,  4): dict(india_inflation_pct=5.0, petrol_price_hyd=104.8, rent_index=29.7, groceries_index=15.0, restaurant_index=11.9),
}


def _nearest_cost(year, month):
    best = sorted(DUMMY_COST.keys())[0]
    for ym in sorted(DUMMY_COST.keys()):
        if (ym[0] * 12 + ym[1]) <= (year * 12 + month):
            best = ym
    return DUMMY_COST[best]


class Command(BaseCommand):
    help = 'Load 16 months of realistic dummy budget data for Hyderabad'

    def add_arguments(self, parser):
        parser.add_argument('--clear', action='store_true',
                            help='Delete existing dummy records first')

    def handle(self, *args, **options):
        settings = AppSettings.get()
        rent_amount = float(settings.rent_amount)

        if options['clear']:
            deleted, _ = MonthlyBudget.objects.filter(is_dummy=True).delete()
            self.stdout.write(self.style.WARNING(f'Deleted {deleted} existing dummy records.'))

        created = 0
        for year, month in DUMMY_MONTHS:
            total = float(DUMMY_BUDGETS[(year, month)])

            investment = _inv_amount(total, year, month)   # includes feasibility check
            emi_amount = settings.get_emi_for_month(year, month)
            ml_spendable = total - investment - emi_amount

            # Build ni amounts
            ni_raw = dict(zip(NI_CAT_ORDER, NI_SPLITS[(year, month)]))
            ni_pct = _normalise(ni_raw)

            if ml_spendable > 0:
                ni_amounts = {cat: ni_pct[cat] / 100.0 * ml_spendable for cat in NI_CAT_ORDER}
                ni_amounts = _apply_rent_floor(ni_amounts, ml_spendable, rent_amount)
                ni_pct = {cat: ni_amounts[cat] / ml_spendable * 100.0 for cat in NI_CAT_ORDER}
                ni_pct = _normalise(ni_pct)

            # Convert to % of total
            pct_dict = {}
            for cat in NI_CAT_ORDER:
                pct_dict[cat] = ni_pct[cat] * (ml_spendable / total) if total > 0 else 0.0
            pct_dict['investment'] = investment / total * 100.0 if total > 0 else 0.0
            pct_dict['emi']        = emi_amount / total * 100.0 if total > 0 else 0.0
            pct_dict = _normalise(pct_dict)

            mb, was_created = MonthlyBudget.objects.get_or_create(
                year=year, month=month,
                defaults={
                    'total_budget': Decimal(str(total)),
                    'is_dummy': True,
                    'notes': 'Dummy data',
                },
            )
            if not was_created:
                self.stdout.write(f'  Skipping {year}-{month:02d} (exists)')
                continue

            # Save splits with exact investment + EMI amounts
            inv_dec  = Decimal(str(round(investment, 2)))
            emi_dec  = Decimal(str(round(emi_amount, 2)))
            ml_dec   = Decimal(str(total)) - inv_dec - emi_dec
            running  = Decimal('0')
            ml_cats  = [c for c in CATEGORIES if c not in ('investment', 'emi')]
            ml_sum   = sum(pct_dict[c] for c in ml_cats)

            for cat in ml_cats[:-1]:
                share = Decimal(str(pct_dict[cat])) / Decimal(str(ml_sum)) if ml_sum > 0 else Decimal('0')
                amt   = (share * ml_dec).quantize(Decimal('0.01'))
                running += amt
                BudgetSplit.objects.create(
                    monthly_budget=mb, category=cat,
                    amount=amt,
                    percentage=Decimal(str(round(pct_dict[cat], 3))),
                )
            # Last ML category absorbs rounding residual (or re-route to food/entertainment)
            last_cat = ml_cats[-1]
            last_amt = ml_dec - running
            # Re-route residual to food/entertainment
            food_pct  = pct_dict.get('food', 0)
            entr_pct  = pct_dict.get('entertainment', 0)
            if last_cat not in ('food', 'entertainment') and last_amt != Decimal('0'):
                route_to = 'food' if food_pct <= entr_pct else 'entertainment'
                existing_split = BudgetSplit.objects.filter(monthly_budget=mb, category=route_to).first()
                if existing_split:
                    existing_split.amount += last_amt
                    existing_split.save()
                    last_amt = Decimal('0')
            BudgetSplit.objects.create(
                monthly_budget=mb, category=last_cat,
                amount=last_amt,
                percentage=Decimal(str(round(pct_dict[last_cat], 3))),
            )
            BudgetSplit.objects.create(
                monthly_budget=mb, category='investment',
                amount=inv_dec,
                percentage=Decimal(str(round(pct_dict['investment'], 3))),
            )
            BudgetSplit.objects.create(
                monthly_budget=mb, category='emi',
                amount=emi_dec,
                percentage=Decimal(str(round(pct_dict['emi'], 3))),
            )

            CostSnapshot.objects.get_or_create(
                year=year, month=month,
                defaults={**_nearest_cost(year, month), 'fetch_error': '',
                          'raw_data': _nearest_cost(year, month)},
            )

            flags = []
            if investment > 0: flags.append(f'inv=₹{investment:,.0f}')
            if emi_amount > 0:  flags.append(f'emi=₹{emi_amount:,.0f}')
            flag_str = '  ' + '  '.join(flags) if flags else ''
            self.stdout.write(f'  {year}-{month:02d}: ₹{total:,.0f}{flag_str}')
            created += 1

        self.stdout.write(self.style.SUCCESS(f'\nDone. Created {created} records.'))
