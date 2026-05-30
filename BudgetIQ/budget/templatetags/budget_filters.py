from decimal import Decimal, ROUND_HALF_UP
from django import template

register = template.Library()


@register.filter
def indian_number(value):
    """Format a number as Indian currency: 1,30,000.00"""
    try:
        d = Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    except Exception:
        return value
    negative = d < 0
    d = abs(d)
    s = str(d)
    integer_str, decimal_str = (s.split('.') + ['00'])[:2]
    decimal_str = decimal_str.ljust(2, '0')[:2]
    if len(integer_str) <= 3:
        formatted = integer_str
    else:
        last3 = integer_str[-3:]
        rest = integer_str[:-3]
        parts = []
        while rest:
            parts.insert(0, rest[-2:] if len(rest) >= 2 else rest)
            rest = rest[:-2]
        formatted = ','.join(parts) + ',' + last3
    return ('-' if negative else '') + formatted + '.' + decimal_str


@register.filter
def indian_int(value):
    """Format a number as Indian integer with no decimal places: 1,30,000"""
    try:
        n = abs(int(round(float(str(value)))))
        negative = float(str(value)) < 0
    except Exception:
        return value
    integer_str = str(n)
    if len(integer_str) <= 3:
        formatted = integer_str
    else:
        last3 = integer_str[-3:]
        rest = integer_str[:-3]
        parts = []
        while rest:
            parts.insert(0, rest[-2:] if len(rest) >= 2 else rest)
            rest = rest[:-2]
        formatted = ','.join(parts) + ',' + last3
    return ('-' if negative else '') + formatted


@register.filter
def get_item(dictionary, key):
    """{{ my_dict|get_item:key }}"""
    return dictionary.get(key, '')


@register.filter
def get_field(form, cat_key):
    """Render the pct_<cat_key> input field from a SplitAdjustmentForm."""
    field_name = f'pct_{cat_key}'
    return form[field_name]
