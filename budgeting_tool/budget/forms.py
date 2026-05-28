from django import forms
from .models import CATEGORIES, AppSettings


class BudgetInputForm(forms.Form):
    total_budget = forms.DecimalField(
        label='Total Monthly Budget (₹)',
        min_value=1000,
        max_value=10_000_000,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': 'e.g. 65000',
            'autofocus': True,
            'step': '0.01',
        }),
    )
    year = forms.IntegerField(widget=forms.HiddenInput())
    month = forms.IntegerField(
        min_value=1, max_value=12,
        widget=forms.HiddenInput(),
    )
    notes = forms.CharField(
        required=False,
        label='Notes (optional)',
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': 'Any notes for this month…',
        }),
    )


class SplitAdjustmentForm(forms.Form):
    """Lets user tweak individual category percentages after the AI suggestion."""
    year = forms.IntegerField(widget=forms.HiddenInput())
    month = forms.IntegerField(widget=forms.HiddenInput(), min_value=1, max_value=12)
    total_budget = forms.DecimalField(widget=forms.HiddenInput(), min_value=0)
    notes = forms.CharField(required=False, widget=forms.HiddenInput())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for key, label in CATEGORIES:
            self.fields[f'pct_{key}'] = forms.DecimalField(
                label=label,
                min_value=0,
                max_value=100,
                decimal_places=2,
                widget=forms.NumberInput(attrs={
                    'class': 'form-control pct-input',
                    'step': '0.01',
                    'data-cat': key,
                }),
            )

    def get_percentages(self):
        data = self.cleaned_data
        return {key: float(data[f'pct_{key}']) for key, _ in CATEGORIES}


class AppSettingsForm(forms.ModelForm):
    class Meta:
        model = AppSettings
        fields = ['rent_amount', 'emi_amount', 'emi_end_year', 'emi_end_month']
        widgets = {
            'rent_amount': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '0.01',
                'placeholder': '38500.00',
            }),
            'emi_amount': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '0.01',
                'placeholder': '28168.00',
            }),
            'emi_end_year': forms.NumberInput(attrs={
                'class': 'form-control', 'min': '2024', 'max': '2040',
            }),
            'emi_end_month': forms.NumberInput(attrs={
                'class': 'form-control', 'min': '1', 'max': '12',
            }),
        }
        labels = {
            'rent_amount':   'Monthly Rent (₹)',
            'emi_amount':    'Loan EMI Amount (₹/month)',
            'emi_end_year':  'EMI End Year',
            'emi_end_month': 'EMI End Month',
        }
