"""
bank_rate_fetcher.py
====================
Best-effort scraper for Indian bank savings / FD rates.

Strategy
--------
- Each bank has a small list of candidate URLs to try.
- We do a simple HTTP GET (no JS rendering) and apply regex patterns to extract
  rate values.  Bank websites change structure frequently, so every parser is
  wrapped in a try/except; any failure falls back to the hardcoded baseline.
- Results are cached in  budget/bank_data_cache.json  and refreshed in a
  background daemon thread at most once every REFRESH_INTERVAL_HOURS.
- The recommender in views.py calls  get_cached_bank_features()  which returns
  the merged (cached + baseline) feature dict with no blocking.

Adding / updating a bank
------------------------
1. Add an entry to SCRAPERS with URL(s) and a parse function.
2. The parse function receives the response text and returns a partial dict
   (only the fields you can reliably extract; others stay from baseline).
"""

import datetime
import json
import logging
import re
import threading
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

CACHE_PATH              = Path(__file__).parent / 'bank_data_cache.json'
REFRESH_INTERVAL_HOURS  = 24
REQUEST_TIMEOUT         = 5   # seconds per attempt

_refresh_running = threading.Lock()   # prevents concurrent refresh threads

# ── Regex helpers ──────────────────────────────────────────────────────────────

def _first_float(pattern: str, text: str) -> float | None:
    """Return the first float matched by `pattern` in `text`, or None."""
    m = re.search(pattern, text, re.IGNORECASE)
    if m:
        try:
            return float(m.group(1))
        except (ValueError, IndexError):
            pass
    return None


def _max_float(pattern: str, text: str) -> float | None:
    """Return the maximum float among all matches of `pattern` in `text`."""
    vals = [float(v) for v in re.findall(pattern, text, re.IGNORECASE) if v]
    return max(vals) if vals else None


# ── Per-bank parsers ───────────────────────────────────────────────────────────
# Each parser receives response.text and returns a partial feature dict.
# Only include fields you can reliably extract; unknown fields are left at baseline.

def _parse_hdfc(text: str) -> dict:
    updates = {}
    # Savings rate: HDFC publishes "X% p.a." or "X% per annum"
    rate = _max_float(r'(\d+\.?\d*)\s*%\s*(?:p\.?a\.?|per\s+annum)', text)
    if rate and 2.0 <= rate <= 8.0:
        updates['savings_rate_pct'] = rate
    # FD rate: look for "up to X% p.a." near "fixed deposit"
    fd_rate = _max_float(r'up\s+to\s+(\d+\.?\d*)\s*%', text)
    if fd_rate and 5.0 <= fd_rate <= 10.0:
        updates['fd_rate_pct'] = fd_rate
    return updates


def _parse_idfc(text: str) -> dict:
    updates = {}
    rate = _max_float(r'(\d+\.?\d*)\s*%\s*(?:p\.?a\.?|per\s+annum)', text)
    if rate and 3.0 <= rate <= 10.0:
        updates['savings_rate_pct'] = rate
    fd_rate = _max_float(r'up\s+to\s+(\d+\.?\d*)\s*%', text)
    if fd_rate and 5.0 <= fd_rate <= 10.0:
        updates['fd_rate_pct'] = fd_rate
    return updates


def _parse_union(text: str) -> dict:
    updates = {}
    rate = _max_float(r'(\d+\.?\d*)\s*%\s*(?:p\.?a\.?|per\s+annum)', text)
    if rate and 2.0 <= rate <= 8.0:
        updates['savings_rate_pct'] = rate
    fd_rate = _max_float(r'up\s+to\s+(\d+\.?\d*)\s*%', text)
    if fd_rate and 5.0 <= fd_rate <= 10.0:
        updates['fd_rate_pct'] = fd_rate
    return updates


# ── Scraper configuration ─────────────────────────────────────────────────────

SCRAPERS = {
    'hdfc': {
        'urls': [
            'https://www.hdfcbank.com/personal/save/accounts/savings-accounts',
            'https://www.hdfcbank.com/content/api/contentmanager?slug=/personal/save/accounts/savings-accounts',
        ],
        'parser': _parse_hdfc,
    },
    'idfc': {
        'urls': [
            'https://www.idfcfirstbank.com/personal-banking/accounts/savings-account',
            'https://www.idfcfirstbank.com/content/dam/idfcfirstbank/pdf/savings-account-interest-rates.pdf',
        ],
        'parser': _parse_idfc,
    },
    'union': {
        'urls': [
            'https://www.unionbankofindia.co.in/english/Deposit-Interest-Rates.aspx',
            'https://www.unionbankofindia.co.in/english/SavingsDeposit-Interest-Rates.aspx',
        ],
        'parser': _parse_union,
    },
}

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0.0.0 Safari/537.36'
    ),
    'Accept-Language': 'en-IN,en;q=0.9',
}


# ── Cache I/O ─────────────────────────────────────────────────────────────────

def _load_cache() -> dict:
    """Return cached bank data, or {} if absent / corrupt."""
    try:
        if CACHE_PATH.exists():
            return json.loads(CACHE_PATH.read_text())
    except Exception as exc:
        logger.debug("bank_rate_fetcher: cache load failed: %s", exc)
    return {}


def _save_cache(data: dict) -> None:
    try:
        CACHE_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    except Exception as exc:
        logger.warning("bank_rate_fetcher: cache save failed: %s", exc)


def _cache_is_stale(cache: dict) -> bool:
    fetched = cache.get('fetched_at')
    if not fetched:
        return True
    try:
        age = datetime.datetime.now() - datetime.datetime.fromisoformat(fetched)
        return age.total_seconds() / 3600 >= REFRESH_INTERVAL_HOURS
    except Exception:
        return True


# ── Scraping ──────────────────────────────────────────────────────────────────

def _fetch_bank_updates(bank_key: str) -> dict:
    """
    Try each URL for `bank_key`, apply parser, return partial feature dict.
    Returns {} on all failures.
    """
    cfg = SCRAPERS.get(bank_key, {})
    for url in cfg.get('urls', []):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT,
                                allow_redirects=True)
            if resp.ok:
                updates = cfg['parser'](resp.text)
                if updates:
                    logger.info("bank_rate_fetcher: %s — fetched %s", bank_key, updates)
                    return updates
        except Exception as exc:
            logger.debug("bank_rate_fetcher: %s %s failed: %s", bank_key, url, exc)
    return {}


def _do_refresh() -> None:
    """Fetch rates for all banks and update the cache (called in background thread)."""
    cache = _load_cache()
    rates = cache.get('rates', {})
    any_updated = False

    for key in SCRAPERS:
        updates = _fetch_bank_updates(key)
        if updates:
            rates[key] = {**(rates.get(key) or {}), **updates}
            any_updated = True

    if any_updated or not cache:
        cache['rates'] = rates
        cache['fetched_at'] = datetime.datetime.now().isoformat()
        _save_cache(cache)
        logger.info("bank_rate_fetcher: cache updated")


def _refresh_in_background() -> None:
    """Spawn a single daemon thread to refresh rates; noop if one is already running."""
    if not _refresh_running.acquire(blocking=False):
        return
    def _run():
        try:
            _do_refresh()
        finally:
            _refresh_running.release()
    t = threading.Thread(target=_run, daemon=True)
    t.start()


# ── Public API ────────────────────────────────────────────────────────────────

def get_cached_bank_features(baseline: dict) -> tuple[dict, str | None]:
    """
    Return (merged_features, fetched_at_iso_str).

    merged_features: baseline bank features overridden with any successfully
                     scraped values from the cache.  Always returns a usable dict.
    fetched_at:      ISO timestamp of when the cache was last refreshed, or None.
    """
    cache = _load_cache()

    # Kick off a background refresh if the cache is stale
    if _cache_is_stale(cache):
        _refresh_in_background()

    rates    = cache.get('rates', {})
    features = {}
    for key, base in baseline.items():
        merged = dict(base)
        merged.update(rates.get(key) or {})
        features[key] = merged

    return features, cache.get('fetched_at')


def force_refresh() -> None:
    """Trigger an immediate synchronous refresh (used by the manual-refresh endpoint)."""
    _do_refresh()
