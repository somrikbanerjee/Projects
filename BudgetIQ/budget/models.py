import calendar
from django.db import models

CATEGORIES = [
    ('groceries',     'Groceries'),
    ('transport',     'Transport'),
    ('food',          'Food'),
    ('healthcare',    'Healthcare'),
    ('home',          'Home'),
    ('entertainment', 'Entertainment'),
    ('subscriptions', 'Subscriptions'),
    ('shopping',      'Shopping'),
    ('travel',        'Travel'),
    ('investment',    'Investment'),
    ('emi',           'Loan EMI'),
    ('other',         'Other'),
]

CATEGORY_KEYS = [c[0] for c in CATEGORIES]

CATEGORY_ICONS = {
    'groceries':     '🛒',
    'transport':     '🚗',
    'food':          '🍽️',
    'healthcare':    '🏥',
    'home':          '🏠',
    'entertainment': '🎬',
    'subscriptions': '📱',
    'shopping':      '🛍️',
    'travel':        '✈️',
    'investment':    '📈',
    'emi':           '🏦',
    'other':         '💰',
}


class AppSettings(models.Model):
    """Singleton model for user-configurable fixed monthly expenses."""
    rent_amount    = models.DecimalField(max_digits=10, decimal_places=2, default=38500)
    emi_amount     = models.DecimalField(max_digits=10, decimal_places=2, default=28168)
    emi_end_year   = models.IntegerField(default=2028)
    emi_end_month  = models.IntegerField(default=9)
    location       = models.CharField(max_length=100, default='Hyderabad')
    updated_at     = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'App Settings'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def emi_active(self, year: int, month: int) -> bool:
        return (year, month) <= (self.emi_end_year, self.emi_end_month)

    def get_emi_for_month(self, year: int, month: int) -> float:
        return float(self.emi_amount) if self.emi_active(year, month) else 0.0

    def __str__(self):
        return f"AppSettings (rent=₹{self.rent_amount:,.2f}, emi=₹{self.emi_amount:,.2f})"


class MonthlyBudget(models.Model):
    year         = models.IntegerField()
    month        = models.IntegerField()
    total_budget = models.DecimalField(max_digits=12, decimal_places=2)
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)
    notes        = models.TextField(blank=True, default='')
    is_dummy     = models.BooleanField(default=False)

    class Meta:
        unique_together = ('year', 'month')
        ordering = ['-year', '-month']

    def __str__(self):
        return f"{calendar.month_name[self.month]} {self.year} — ₹{self.total_budget:,.2f}"

    @property
    def month_name(self):
        return calendar.month_name[self.month]

    @property
    def month_year_label(self):
        return f"{calendar.month_abbr[self.month]} {self.year}"

    def get_splits_dict(self):
        return {s.category: float(s.percentage) for s in self.splits.all()}


class BudgetSplit(models.Model):
    monthly_budget = models.ForeignKey(MonthlyBudget, on_delete=models.CASCADE,
                                       related_name='splits')
    category   = models.CharField(max_length=50, choices=CATEGORIES)
    amount     = models.DecimalField(max_digits=12, decimal_places=2)
    percentage = models.DecimalField(max_digits=6, decimal_places=3)

    class Meta:
        unique_together = ('monthly_budget', 'category')
        ordering = ['category']

    def __str__(self):
        return (f"{self.monthly_budget} | {self.get_category_display()}: "
                f"₹{self.amount:,.2f} ({self.percentage:.1f}%)")

    @property
    def icon(self):
        return CATEGORY_ICONS.get(self.category, '💰')


class MonthlyActual(models.Model):
    """Actual spending per month, imported from Money Manager .mmbak backups."""
    year         = models.IntegerField()
    month        = models.IntegerField()
    total_actual = models.DecimalField(max_digits=12, decimal_places=2)
    source_file  = models.CharField(max_length=255, blank=True, default='')
    imported_at  = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('year', 'month')
        ordering = ['-year', '-month']

    def __str__(self):
        return f"{calendar.month_name[self.month]} {self.year} Actuals — ₹{self.total_actual:,.2f}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

    @property
    def month_name(self):
        return calendar.month_name[self.month]

    @property
    def month_year_label(self):
        return f"{calendar.month_abbr[self.month]} {self.year}"

    def get_splits_dict(self):
        return {s.category: float(s.amount) for s in self.actual_splits.all()}


class ActualSplit(models.Model):
    monthly_actual = models.ForeignKey(MonthlyActual, on_delete=models.CASCADE,
                                       related_name='actual_splits')
    category   = models.CharField(max_length=50, choices=CATEGORIES)
    amount     = models.DecimalField(max_digits=12, decimal_places=2)
    percentage = models.DecimalField(max_digits=6, decimal_places=3)

    class Meta:
        unique_together = ('monthly_actual', 'category')
        ordering = ['category']

    def __str__(self):
        return (f"{self.monthly_actual} | {self.get_category_display()}: "
                f"₹{self.amount:,.2f} ({self.percentage:.1f}%)")

    @property
    def icon(self):
        return CATEGORY_ICONS.get(self.category, '💰')


class CostSnapshot(models.Model):
    """Stores monthly fetched cost-of-living and CPI data per city."""
    year           = models.IntegerField()
    month          = models.IntegerField()
    location       = models.CharField(max_length=100, default='Hyderabad')
    fetched_at     = models.DateTimeField(auto_now_add=True)
    india_cpi             = models.FloatField(null=True, blank=True)
    india_inflation_pct   = models.FloatField(null=True, blank=True)
    petrol_price_hyd      = models.FloatField(null=True, blank=True)
    rent_index            = models.FloatField(null=True, blank=True)
    groceries_index       = models.FloatField(null=True, blank=True)
    restaurant_index      = models.FloatField(null=True, blank=True)
    fetch_error           = models.TextField(blank=True, default='')
    raw_data              = models.JSONField(default=dict, blank=True)

    class Meta:
        unique_together = ('year', 'month', 'location')
        ordering = ['-year', '-month']

    def __str__(self):
        return f"CostSnapshot {self.location} {calendar.month_abbr[self.month]} {self.year}"
