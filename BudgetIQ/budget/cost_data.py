"""
Fetches live cost-of-living data for Indian cities.

Sources used:
  1. World Bank API — India CPI & inflation
  2. City-specific baselines calibrated from Numbeo surveys (2025-2026)
  3. State petrol price estimates based on known 2024 prices

Data is cached in the CostSnapshot model and refreshed at most once per month per city.
"""

import datetime
import logging

import requests

logger = logging.getLogger(__name__)

WORLD_BANK_CPI_URL = (
    "https://api.worldbank.org/v2/country/IN/indicator/FP.CPI.TOTL"
    "?format=json&mrv=2&per_page=2"
)
WORLD_BANK_INFLATION_URL = (
    "https://api.worldbank.org/v2/country/IN/indicator/FP.CPI.TOTL.ZG"
    "?format=json&mrv=1&per_page=1"
)

# Per-city baselines calibrated to 2025-2026 Numbeo cost-of-living surveys.
# rent_index: % of typical budget going to rent
# groceries_index: relative groceries cost index
# restaurant_index: eating-out cost index
# petrol_base_2024: ₹/litre as of mid-2024 (varies by state tax)
# india_inflation_pct: shared national CPI inflation fallback
# india_cpi: shared national CPI fallback
CITY_BASELINES = {
    "Hyderabad": {
        "rent_index": 28.5,
        "groceries_index": 14.2,
        "restaurant_index": 11.0,
        "petrol_base_2024": 102.63,
        "india_inflation_pct": 5.2,
        "india_cpi": 193.5,
    },
    "Bangalore": {
        "rent_index": 42.75,
        "groceries_index": 15.62,
        "restaurant_index": 13.2,
        "petrol_base_2024": 102.86,
        "india_inflation_pct": 5.2,
        "india_cpi": 193.5,
    },
    "Mumbai": {
        "rent_index": 54.15,
        "groceries_index": 17.04,
        "restaurant_index": 14.3,
        "petrol_base_2024": 104.21,
        "india_inflation_pct": 5.2,
        "india_cpi": 193.5,
    },
    "Delhi": {
        "rent_index": 39.9,
        "groceries_index": 15.62,
        "restaurant_index": 12.65,
        "petrol_base_2024": 94.77,
        "india_inflation_pct": 5.2,
        "india_cpi": 193.5,
    },
    "Chennai": {
        "rent_index": 32.78,
        "groceries_index": 14.91,
        "restaurant_index": 11.55,
        "petrol_base_2024": 100.85,
        "india_inflation_pct": 5.2,
        "india_cpi": 193.5,
    },
    "Pune": {
        "rent_index": 32.78,
        "groceries_index": 14.2,
        "restaurant_index": 11.55,
        "petrol_base_2024": 104.32,
        "india_inflation_pct": 5.2,
        "india_cpi": 193.5,
    },
    "Kolkata": {
        "rent_index": 24.23,
        "groceries_index": 12.78,
        "restaurant_index": 9.35,
        "petrol_base_2024": 103.94,
        "india_inflation_pct": 5.2,
        "india_cpi": 193.5,
    },
    "Ahmedabad": {
        "rent_index": 22.8,
        "groceries_index": 12.07,
        "restaurant_index": 8.8,
        "petrol_base_2024": 96.63,
        "india_inflation_pct": 5.2,
        "india_cpi": 193.5,
    },
    "Jaipur": {
        "rent_index": 21.38,
        "groceries_index": 11.64,
        "restaurant_index": 8.58,
        "petrol_base_2024": 108.48,
        "india_inflation_pct": 5.2,
        "india_cpi": 193.5,
    },
    "Kochi": {
        "rent_index": 28.5,
        "groceries_index": 14.91,
        "restaurant_index": 11.0,
        "petrol_base_2024": 107.64,
        "india_inflation_pct": 5.2,
        "india_cpi": 193.5,
    },
    "Coimbatore": {
        "rent_index": 22.8,
        "groceries_index": 12.78,
        "restaurant_index": 9.35,
        "petrol_base_2024": 100.85,
        "india_inflation_pct": 5.2,
        "india_cpi": 193.5,
    },
    "Chandigarh": {
        "rent_index": 27.08,
        "groceries_index": 13.49,
        "restaurant_index": 9.9,
        "petrol_base_2024": 96.2,
        "india_inflation_pct": 5.2,
        "india_cpi": 193.5,
    },
    "Lucknow": {
        "rent_index": 21.38,
        "groceries_index": 11.36,
        "restaurant_index": 8.58,
        "petrol_base_2024": 94.65,
        "india_inflation_pct": 5.2,
        "india_cpi": 193.5,
    },
    "Visakhapatnam": {
        "rent_index": 25.65,
        "groceries_index": 13.06,
        "restaurant_index": 9.68,
        "petrol_base_2024": 108.12,
        "india_inflation_pct": 5.2,
        "india_cpi": 193.5,
    },
    "Indore": {
        "rent_index": 21.38,
        "groceries_index": 11.64,
        "restaurant_index": 8.58,
        "petrol_base_2024": 108.55,
        "india_inflation_pct": 5.2,
        "india_cpi": 193.5,
    },
    "Surat": {
        "rent_index": 24.23,
        "groceries_index": 12.35,
        "restaurant_index": 9.13,
        "petrol_base_2024": 96.63,
        "india_inflation_pct": 5.2,
        "india_cpi": 193.5,
    },
}

SUPPORTED_CITIES = sorted(CITY_BASELINES.keys())

# Nominatim reverse-geocode endpoint (OpenStreetMap, free, no key required)
NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"


def get_baseline(city: str) -> dict:
    """Return the baseline dict for a city, falling back to Hyderabad."""
    return CITY_BASELINES.get(city, CITY_BASELINES["Hyderabad"])


def resolve_city_from_coords(lat: float, lon: float) -> str:
    """
    Reverse-geocode lat/lon via Nominatim and return the best matching
    supported city name, or 'Hyderabad' if nothing matches.
    """
    try:
        resp = requests.get(
            NOMINATIM_REVERSE_URL,
            params={"format": "json", "lat": lat, "lon": lon, "zoom": 10},
            headers={"User-Agent": "BudgetIQ/1.0 (somrik.banerjee@gmail.com)"},
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json()
        addr = data.get("address", {})
        # Nominatim returns city/town/village/county in priority order
        raw_city = (
            addr.get("city")
            or addr.get("town")
            or addr.get("village")
            or addr.get("county")
            or ""
        )
        raw_city = raw_city.strip()
        # Exact match first
        for city in SUPPORTED_CITIES:
            if city.lower() == raw_city.lower():
                return city
        # Partial match (e.g. "Bengaluru" → "Bangalore")
        ALIASES = {
            "bengaluru": "Bangalore",
            "new delhi": "Delhi",
            "bombay": "Mumbai",
            "madras": "Chennai",
            "calcutta": "Kolkata",
            "vizag": "Visakhapatnam",
            "vishakhapatnam": "Visakhapatnam",
        }
        for alias, canonical in ALIASES.items():
            if alias in raw_city.lower():
                return canonical
        for city in SUPPORTED_CITIES:
            if city.lower() in raw_city.lower() or raw_city.lower() in city.lower():
                return city
    except Exception as exc:
        logger.warning("Nominatim reverse-geocode failed: %s", exc)
    return "Hyderabad"


def _fetch_world_bank_inflation():
    """Return (cpi_value, inflation_pct) from World Bank API or (None, None) on error."""
    try:
        resp = requests.get(WORLD_BANK_INFLATION_URL, timeout=8)
        resp.raise_for_status()
        data = resp.json()
        entries = data[1] if len(data) > 1 else []
        for entry in entries:
            if entry.get("value") is not None:
                return None, round(float(entry["value"]), 2)
    except Exception as exc:
        logger.warning("World Bank inflation fetch failed: %s", exc)
    return None, None


def _fetch_world_bank_cpi():
    """Return latest India CPI value or None."""
    try:
        resp = requests.get(WORLD_BANK_CPI_URL, timeout=8)
        resp.raise_for_status()
        data = resp.json()
        entries = data[1] if len(data) > 1 else []
        for entry in entries:
            if entry.get("value") is not None:
                return round(float(entry["value"]), 2)
    except Exception as exc:
        logger.warning("World Bank CPI fetch failed: %s", exc)
    return None


def fetch_live_cost_data(year: int, month: int, city: str = "Hyderabad") -> dict:
    """
    Fetch and return a dict of cost indicators for the given month and city.
    Falls back gracefully to city baselines when APIs are unavailable.
    """
    baseline = get_baseline(city)
    raw = {}

    cpi_val = _fetch_world_bank_cpi()
    _, inflation_pct = _fetch_world_bank_inflation()

    if cpi_val:
        raw["india_cpi"] = cpi_val
    if inflation_pct:
        raw["india_inflation_pct"] = inflation_pct

    base_petrol = baseline["petrol_base_2024"]
    years_since_base = (year - 2024) + (month - 6) / 12
    estimated_petrol = base_petrol * (1 + 0.025 * years_since_base)
    raw["petrol_price_hyd"] = round(estimated_petrol, 2)

    inflation_factor = 1.0
    if inflation_pct:
        years_elapsed = (year - 2025) + (month - 1) / 12
        inflation_factor = (1 + inflation_pct / 100) ** max(years_elapsed, 0)

    raw["rent_index"] = round(baseline["rent_index"] * inflation_factor, 2)
    raw["groceries_index"] = round(baseline["groceries_index"] * inflation_factor, 2)
    raw["restaurant_index"] = round(baseline["restaurant_index"] * inflation_factor, 2)

    for key, default in baseline.items():
        if key != "petrol_base_2024":
            raw.setdefault(key, default)

    raw["fetch_error"] = ""
    raw["year"] = year
    raw["month"] = month
    raw["city"] = city
    return raw


def get_or_fetch_cost_snapshot(year: int, month: int, city: str = "Hyderabad", force: bool = False):
    """
    Return a CostSnapshot for the given month and city, fetching if not yet cached.
    Pass force=True to delete the cached snapshot and re-fetch live data.
    """
    from budget.models import CostSnapshot

    if force:
        CostSnapshot.objects.filter(year=year, month=month, location=city).delete()
    else:
        try:
            return CostSnapshot.objects.get(year=year, month=month, location=city)
        except CostSnapshot.DoesNotExist:
            pass

    data = fetch_live_cost_data(year, month, city)

    snap = CostSnapshot(
        year=year,
        month=month,
        location=city,
        india_cpi=data.get("india_cpi"),
        india_inflation_pct=data.get("india_inflation_pct"),
        petrol_price_hyd=data.get("petrol_price_hyd"),
        rent_index=data.get("rent_index"),
        groceries_index=data.get("groceries_index"),
        restaurant_index=data.get("restaurant_index"),
        fetch_error=data.get("fetch_error", ""),
        raw_data=data,
    )
    snap.save()
    return snap


def cost_snapshot_to_adjustments(snap, city: str = "Hyderabad") -> dict:
    """
    Convert a CostSnapshot into category adjustment multipliers.
    Returns dict of {category: multiplier} relative to the neutral baseline of 1.0.
    """
    baseline = get_baseline(city)

    inflation = snap.india_inflation_pct or baseline["india_inflation_pct"]
    petrol = snap.petrol_price_hyd or baseline["petrol_base_2024"]
    rent_idx = snap.rent_index or baseline["rent_index"]
    groceries_idx = snap.groceries_index or baseline["groceries_index"]
    restaurant_idx = snap.restaurant_index or baseline["restaurant_index"]

    baseline_inflation = baseline["india_inflation_pct"]
    inflation_delta = (inflation - baseline_inflation) / 100

    baseline_petrol = baseline["petrol_base_2024"]
    petrol_factor = petrol / baseline_petrol

    rent_factor = rent_idx / baseline["rent_index"]
    groceries_factor = groceries_idx / baseline["groceries_index"]
    restaurant_factor = restaurant_idx / baseline["restaurant_index"]

    return {
        "groceries": groceries_factor,
        "transport": petrol_factor * 0.6 + 0.4,
        "food": restaurant_factor,
        "healthcare": 1.0 + inflation_delta * 1.5,
        "home": rent_factor,
        "entertainment": 1.0 + inflation_delta * 0.5,
        "subscriptions": 1.0 + inflation_delta * 0.3,
        "shopping": 1.0 + inflation_delta * 0.8,
        "travel": petrol_factor * 0.4 + 0.6,
        "investment": 1.0,
        "other": 1.0 + inflation_delta,
    }
