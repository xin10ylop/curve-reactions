# curve-reactions

Which scheduled US economic releases actually move the Treasury yield curve, and by how much?

Every month a few big reports are supposed to move interest rates: the CPI inflation report, the monthly jobs report, and the Federal Reserve's rate decisions (FOMC). This project measures what really happens to US Treasury yields (the 2, 10 and 30 year) on those days, and compares it to a normal trading day.

## See the report

You do not need to install or run anything to see the results. Just open the live page:

**https://xin10ylop.github.io/curve-reactions/**

It is one web page with the charts and the numbers. I generate the page; the person viewing it does not have to sign up for anything or set up a key.

As an example finding, on jobs-report days the 2 year yield moves about 1.9 times its normal daily range. The exact figures are on the page.

## What it measures

- The average size of the daily yield move on CPI, jobs, and Fed days, for each maturity.
- A reaction multiple: how many times bigger the move is than on a normal day. Above 1.0 means the release reliably moves that part of the curve.
- Whether the curve steepened or flattened on each type of day.
- Four charts, including the 2s10s spread over time with Fed decision days marked.

## How it works

The tool downloads daily Treasury yields from FRED (the St. Louis Fed data service) and the release dates from the official BLS and Federal Reserve calendars. It then computes the daily moves, labels each day by event type, runs the statistics, and writes the report. One command does the whole thing, and the analysis is plain repeatable math with no manual steps.

## Project layout

```
config.py        settings: series IDs, URLs, date range, thresholds
fetch_yields.py  download Treasury yields from FRED (with caching)
fetch_events.py  download CPI, jobs and FOMC dates from official calendars
analysis.py      daily moves, tagging, statistics, curve regimes
charts.py        the four charts
report.py        builds REPORT.md and report.html
main.py          runs everything end to end
```

## Data sources

- Treasury yields: FRED series DGS2, DGS10, DGS30 (Federal Reserve Bank of St. Louis).
- CPI and jobs-report dates: the BLS release calendar, https://www.bls.gov/schedule/.
- Fed decision dates: the Federal Reserve FOMC calendar.

## Data use and credit

This product uses the FRED® API but is not endorsed or certified by the Federal Reserve Bank of St. Louis.

The raw FRED data stays on the computer that runs the tool. It is never committed to this repository and never appears on the live page. The page shows only the charts and my own computed numbers.
