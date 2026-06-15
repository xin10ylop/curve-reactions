"""Build data/events.json: a map of date -> [event types] for CPI, NFP and FOMC.

All dates come from official published calendars fetched at run time:

  * CPI / Employment Situation (NFP): the BLS yearly schedule pages,
    ``www.bls.gov/schedule/<year>/home.htm`` — one request per year.
  * FOMC decisions: the Federal Reserve calendar (current page for recent years
    plus ``fomchistorical<year>.htm`` for earlier ones), always taking the
    SECOND (decision) day of each two-day meeting.

No dates are ever generated from rules of thumb ("first Friday", "mid-month"):
the late-2025 US government shutdown delayed and merged several BLS releases, so
only actually-published dates are trustworthy. Provenance (source URL and fetch
timestamp) is recorded per event type in the JSON. Implausible parses raise
loudly for BLS data and fall back to a verified hardcoded list for FOMC —
the program never silently invents dates.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import logging
import re

import requests

import config

log = logging.getLogger(__name__)

# First three letters of a month name (lower-case) -> month number. This covers
# both full names ("January") and the abbreviations the Fed uses ("Jan", "Sept").
MONTHS: dict[str, int] = {
    name[:3].lower(): num
    for num, name in enumerate(
        ["January", "February", "March", "April", "May", "June", "July",
         "August", "September", "October", "November", "December"], start=1)
}


def _get(url: str) -> str:
    """Fetch a URL with browser headers and return the decoded HTML text."""
    resp = requests.get(url, headers=config.BROWSER_HEADERS, timeout=config.HTTP_TIMEOUT)
    resp.raise_for_status()
    return resp.text


def _strip_tags(fragment: str) -> str:
    """Collapse an HTML fragment to clean, unescaped, single-spaced text."""
    return html.unescape(re.sub(r"<[^>]+>", " ", fragment)).strip()


# --- BLS (CPI / NFP) ----------------------------------------------------------

# Each release on a BLS yearly schedule page is a table row with a date cell and
# a description cell, e.g.
#   <td class="date-cell"><p>Friday, January 06, 2023</p></td> ...
#   <td class="desc-cell"><p><strong>Employment Situation</strong> for ...</p></td>
_BLS_ROW = re.compile(
    r'class="date-cell"[^>]*>\s*<p>(.*?)</p>.*?class="desc-cell"[^>]*>\s*<p>(.*?)</p>',
    re.S,
)


def _parse_bls_year(year_html: str) -> dict[str, list[str]]:
    """Parse one BLS yearly schedule page into ``{"CPI": [...], "NFP": [...]}``."""
    found: dict[str, list[str]] = {"CPI": [], "NFP": []}
    for date_cell, desc_cell in _BLS_ROW.findall(year_html):
        strong = re.search(r"<strong>(.*?)</strong>", desc_cell, re.S)
        if not strong:
            continue
        event = config.BLS_RELEASE_TO_EVENT.get(_strip_tags(strong.group(1)))
        if not event:
            continue
        date_text = _strip_tags(date_cell)
        try:
            day = dt.datetime.strptime(date_text, "%A, %B %d, %Y").date()
        except ValueError:
            log.warning("Unparseable BLS date %r", date_text)
            continue
        found[event].append(day.isoformat())
    return found


def fetch_bls_events(start_year: int, end_year: int) -> dict[str, list[str]]:
    """Fetch CPI and NFP release dates for every year in [start_year, end_year]."""
    cpi: list[str] = []
    nfp: list[str] = []
    for year in range(start_year, end_year + 1):
        parsed = _parse_bls_year(_get(config.BLS_YEAR_SCHEDULE_URL.format(year=year)))
        log.info("BLS %d: %d CPI, %d NFP dates", year, len(parsed["CPI"]), len(parsed["NFP"]))
        _check_bls_count(year, "CPI", len(parsed["CPI"]))
        _check_bls_count(year, "NFP", len(parsed["NFP"]))
        cpi += parsed["CPI"]
        nfp += parsed["NFP"]
    return {"CPI": sorted(set(cpi)), "NFP": sorted(set(nfp))}


def _check_bls_count(year: int, label: str, count: int) -> None:
    """Raise loudly on an implausible BLS count for a *complete* year."""
    if year >= dt.date.today().year:
        return  # current (partial) year: counts are naturally incomplete
    lo, hi = config.BLS_COUNT_PER_FULL_YEAR
    if not (lo <= count <= hi):
        raise ValueError(
            f"BLS {label} for {year} parsed to {count} dates (expected {lo}-{hi}). "
            "The BLS page structure may have changed — refusing to invent dates."
        )


# --- FOMC --------------------------------------------------------------------

def _decision_day_iso(year: int, text: str) -> str:
    """Return the ISO date of a meeting's second (decision) day from free text.

    Handles same-month ranges ("27-28"), cross-month ranges ("Jul/Aug 31-1",
    "30-May 1") and single days. The decision is always the last day named, in
    the most recently named month.
    """
    tokens = re.findall(r"[A-Za-z]+|\d{1,2}", text.replace("–", "-"))
    current_month = last_day = last_month = None
    for token in tokens:
        if token.isdigit():
            last_day = int(token)
            last_month = current_month
        else:
            month = MONTHS.get(token[:3].lower())
            if month:
                current_month = month
    if last_day is None or last_month is None:
        raise ValueError(f"Could not parse FOMC meeting text: {text!r}")
    return dt.date(year, last_month, last_day).isoformat()


def _is_skippable(text: str) -> bool:
    """True if the meeting text marks a non-scheduled action (skip it)."""
    low = text.lower()
    return any(flag in low for flag in config.FOMC_SKIP_ANNOTATIONS)


def _parse_fomc_modern(page: str) -> dict[int, list[str]]:
    """Parse the current FOMC calendar page (year panels, recent years)."""
    by_year: dict[int, list[str]] = {}
    parts = re.split(r"(\d{4})\s+FOMC Meetings", page)
    for i in range(1, len(parts) - 1, 2):
        year = int(parts[i])
        block = parts[i + 1]
        months = re.findall(r'fomc-meeting__month[^>]*>(.*?)</div>', block, re.S)
        dates = re.findall(r'fomc-meeting__date[^>]*>(.*?)</div>', block, re.S)
        for month_frag, date_frag in zip(months, dates):
            month_text, date_text = _strip_tags(month_frag), _strip_tags(date_frag)
            if _is_skippable(month_text) or _is_skippable(date_text):
                log.info("FOMC %d: skip non-scheduled %r %r", year, month_text, date_text)
                continue
            by_year.setdefault(year, []).append(
                _decision_day_iso(year, f"{month_text} {date_text}")
            )
    return by_year


def _parse_fomc_historical(page: str, year: int) -> list[str]:
    """Parse a Fed historical FOMC page for one year (panel-heading format)."""
    dates: list[str] = []
    for heading in re.findall(r'panel-heading[^>]*>(.*?)</div>', page, re.S):
        match = re.match(r"(.+?)\s+Meeting\s*-\s*(\d{4})", _strip_tags(heading))
        if not match or int(match.group(2)) != year:
            continue
        meeting_text = match.group(1)
        if _is_skippable(meeting_text):
            log.info("FOMC %d: skip non-scheduled %r", year, meeting_text)
            continue
        dates.append(_decision_day_iso(year, meeting_text))
    return sorted(set(dates))


def fetch_fomc_events(start_year: int, end_year: int) -> list[str]:
    """Fetch scheduled FOMC decision dates for [start_year, end_year].

    Recent years come from the live calendar page; years before its coverage
    come from the Fed's historical pages. Per-year counts are checked; for years
    with a verified fallback list the fallback is used when parsing is missing or
    implausible. A year that cannot be parsed and has no fallback raises rather
    than guessing.
    """
    try:
        modern = _parse_fomc_modern(_get(config.FOMC_CALENDAR_URL))
    except Exception as exc:  # network or parse failure -> rely on historical/fallback
        log.error("FOMC calendar page failed (%s); will use historical/fallback", exc)
        modern = {}
    modern_min = min(modern) if modern else end_year + 1

    all_dates: list[str] = []
    for year in range(start_year, end_year + 1):
        if year in modern:
            parsed = sorted(set(modern[year]))
        elif year < modern_min:
            try:
                parsed = _parse_fomc_historical(
                    _get(config.FOMC_HISTORICAL_URL.format(year=year)), year
                )
            except Exception as exc:
                log.error("FOMC historical %d failed: %s", year, exc)
                parsed = []
        else:
            parsed = []
        dates = _reconcile_fomc(year, parsed)
        log.info("FOMC %d: %d scheduled decision dates", year, len(dates))
        all_dates += dates
    return sorted(set(all_dates))


def _reconcile_fomc(year: int, parsed: list[str]) -> list[str]:
    """Validate parsed FOMC dates against the count band and any fallback list."""
    lo, hi = config.FOMC_COUNT_PER_FULL_YEAR
    is_current = year >= dt.date.today().year
    plausible = is_current or (lo <= len(parsed) <= hi)

    if year in config.FOMC_FALLBACK:
        fallback = config.FOMC_FALLBACK[year]
        if not parsed:
            log.warning("FOMC %d: nothing parsed; using verified fallback list", year)
            return list(fallback)
        if sorted(parsed) != sorted(fallback):
            log.warning("FOMC %d: parsed dates differ from fallback; using fallback "
                        "(parsed=%s)", year, parsed)
            return list(fallback)
        return list(parsed)

    if not plausible:
        raise ValueError(
            f"FOMC {year} parsed to {len(parsed)} dates (expected {lo}-{hi}) and "
            "no fallback exists for that year. Refusing to guess — check the Fed page."
        )
    return parsed


# --- Assembly ----------------------------------------------------------------

def build_events(start: str, end: str, refresh: bool = False) -> dict:
    """Build (or load) data/events.json mapping each date to its event-type list.

    Covers [start, end] but never beyond today: future scheduled dates have no
    yield reaction yet and are excluded. A date hosting two releases keeps both
    types (the analysis tags such days MULTI). Provenance is recorded per type.
    """
    if config.EVENTS_JSON.exists() and not refresh:
        log.info("Loading cached events from %s", config.EVENTS_JSON)
        return json.loads(config.EVENTS_JSON.read_text())

    start_date = dt.date.fromisoformat(start)
    horizon = min(dt.date.fromisoformat(end), dt.date.today())
    log.info("Building events for %s .. %s", start_date, horizon)

    bls = fetch_bls_events(start_date.year, horizon.year)
    fomc = fetch_fomc_events(start_date.year, horizon.year)
    by_type = {"CPI": bls["CPI"], "NFP": bls["NFP"], "FOMC": fomc}

    events: dict[str, list[str]] = {}
    for event_type, dates in by_type.items():
        for iso in dates:
            if start_date <= dt.date.fromisoformat(iso) <= horizon:
                events.setdefault(iso, [])
                if event_type not in events[iso]:
                    events[iso].append(event_type)
    events = {iso: sorted(types) for iso, types in sorted(events.items())}

    fetched_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    bls_src = "BLS yearly schedule pages (www.bls.gov/schedule/<year>/home.htm)"
    payload = {
        "window": {"start": start_date.isoformat(), "end": horizon.isoformat()},
        "events": events,
        "provenance": {
            "CPI": {"source": bls_src, "fetched_at": fetched_at},
            "NFP": {"source": bls_src, "fetched_at": fetched_at},
            "FOMC": {
                "source": f"{config.FOMC_CALENDAR_URL} (+ fomchistorical<year>.htm "
                          "for years before the live page)",
                "fetched_at": fetched_at,
                "note": "Second (decision) day of each scheduled meeting; "
                        "cancelled / unscheduled / notation-vote actions excluded.",
            },
        },
    }
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.EVENTS_JSON.write_text(json.dumps(payload, indent=2))
    n_multi = sum(1 for types in events.values() if len(types) > 1)
    log.info("Events: %d dates (%d multi-event) written to %s",
             len(events), n_multi, config.EVENTS_JSON)
    return payload
