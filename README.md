# curve-reactions — Yield Curve Event Reaction Tracker

**Which scheduled US economic releases actually move the Treasury yield curve —
by how much, and at which maturities?**

Every month a handful of data releases are supposed to matter for interest
rates: the **CPI** inflation report, the **jobs report** (Employment
Situation / non-farm payrolls), and **FOMC** rate decisions. This tool measures
what *actually* happens to US Treasury yields on those days. For each release it
compares the size of the daily move in the 2-, 10- and 30-year yields against an
ordinary trading day, and classifies how the shape of the curve changed
(steepening vs. flattening).

It runs end to end with one command, pulling all data automatically from
official sources — no manual downloads.

> **Example finding (placeholder — filled in automatically when you run it):**
> *"On CPI days the 2-year yield moved **X.Xx** its normal daily range; FOMC
> decisions moved the 30-year **Y.Yx**."* The real numbers are written into
> `output/REPORT.md` and `output/report.html` each run.

---

## How to run

1. **Get a free FRED API key** (takes a minute):
   https://fred.stlouisfed.org/docs/api/api_key.html
2. **Put the key in your environment** (it is only ever read from there — never
   hardcoded or written to a file):
   ```bash
   export FRED_API_KEY=your_key_here
   ```
3. **Install the dependencies** (Python 3.11+):
   ```bash
   pip install -r requirements.txt
   ```
4. **Run it:**
   ```bash
   python main.py                 # default window: 2018-01-01 → today
   # options:
   python main.py --start 2020-01-01
   python main.py --refresh       # force a fresh download of all caches
   ```

Outputs land in `output/`:

| File | What it is |
| --- | --- |
| `output/REPORT.md` | Markdown report: summary, statistics, regime table, charts |
| `output/report.html` | The same report as a single self-contained HTML file |
| `output/chart*.png` | The four charts |

## Viewing & hosting the report

- **Locally:** open `output/report.html` in any browser.
- **As a website:** `report.html` is fully self-contained — the charts are
  embedded inside the file (base64), the CSS is inline, and there is no
  JavaScript. You can host it as a static page (for example **GitHub Pages**) and
  link it from a CV. Because `output/` is git-ignored by default (it can hold a
  local data cache), copy the report to a published folder before deploying,
  e.g.:
  ```bash
  mkdir -p docs && cp output/report.html docs/index.html   # then enable GitHub Pages on /docs
  ```
  Only the report and charts are ever published — the raw FRED data stays local.

## What you get

- **Reaction statistics** per event type and tenor: count of days, mean and
  median absolute move (bp), and standard deviation.
- **Reaction multiples:** how much larger the average move is on a release day
  versus a normal day (a value above `1.0x` means the release reliably moves
  that tenor).
- **Curve regime classification:** each event day labelled a bull/bear
  steepener or flattener (or mixed/flat), with a frequency table.
- **Four charts:** average move by event/tenor, reaction multiples, the
  distribution of 2-year moves, and the 2s10s spread over time with FOMC days
  marked.

## How it works

```
config.py        constants: series IDs, URLs, date ranges, thresholds
fetch_yields.py  FRED data download + caching (data/yields.csv)
fetch_events.py  event dates from official calendars + caching (data/events.json)
analysis.py      daily changes, tagging, statistics, regime classification
charts.py        the four matplotlib charts
report.py        generates output/REPORT.md and output/report.html
main.py          CLI entry point that runs everything end to end
```

Daily yields come from FRED; event dates are scraped from official published
calendars at run time and cached. Re-running is idempotent (`--refresh` forces a
clean re-download). Dates are never generated from rules of thumb such as "first
Friday of the month" — only actually-published dates are used, which matters
because the **late-2025 US government shutdown delayed and merged several BLS
releases**, and the tool reflects that reality.

## Data sources

- **Treasury yields:** `DGS2`, `DGS10`, `DGS30` (constant-maturity, in percent),
  from [FRED](https://fred.stlouisfed.org/), Federal Reserve Bank of St. Louis.
- **CPI release dates:** [BLS schedule](https://www.bls.gov/schedule/) (yearly
  release calendar pages).
- **Employment Situation / NFP dates:** [BLS schedule](https://www.bls.gov/schedule/).
- **FOMC decision dates:** [Federal Reserve FOMC calendar](https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm)
  (the second/decision day of each meeting).

## Possible extensions

- **Surprise data:** condition reactions on how far each print beat or missed
  consensus (via a forecast/expectations feed) rather than just measuring
  realized moves.
- **Intraday data:** measure the move in the minutes around the 8:30 a.m. / 2:00
  p.m. release instead of close-to-close.
- **Other countries' curves:** apply the same framework to Gilts, Bunds, JGBs.
- **Interactive front end:** a small Streamlit app to explore the data live.

## Attribution

This product uses the FRED® API but is not endorsed or certified by the Federal Reserve Bank of St. Louis.

The cached raw data (`data/yields.csv`) is for local, personal, educational use
only and is never committed or redistributed; the reports contain only charts
and computed statistics.
