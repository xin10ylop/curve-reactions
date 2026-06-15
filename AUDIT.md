# curve-reactions — Independent Code Audit

**Auditor role:** skeptical senior quant developer. Every number below was
re-derived independently (fresh FRED fetches, an independent calendar parser,
and primary-evidence URLs from BLS/Fed), not taken on faith from the source.

## Verdict

**FIX FIRST** → after fixes applied and re-verified: **SHIP** (see *Fix
Verification* at the bottom).

Two Major issues were found and fixed; both are correctness/security hardening,
not methodology changes. Everything else verified clean.

---

## Findings

| Severity | Location | Issue | Evidence | Fix | Status |
|---|---|---|---|---|---|
| **Major** | `analysis.py` `classify_regimes` | Dead-band boundary is decided by floating-point noise. `DGS*.diff()*100` yields e.g. `-1.0000000000000231` for a 1 bp move, so the test `d < -1.0` treats some nominal-1 bp legs as directional and others as flat. | Of 650 legs whose \|Δ\| rounds to 1.0 bp, **341 are FP-represented `>1.0` (counted directional) and 309 `<1.0` (flat)** — identical economic moves classified oppositely. **17 event days flip regime**, changing 9 cells of the regime table (e.g. CPI mixed/flat 44→48, FOMC mixed/flat 33→37). | Round Δ to remove FP noise before the dead-band comparison (keeps the existing "flat iff \|Δ\| ≤ 1.0 bp" intent, now deterministic). | ✅ Fixed |
| **Major** | `fetch_yields.py` `_fetch_series` | FRED API key can leak into a traceback/log. `resp.raise_for_status()` (and any `requests` connection/timeout error) puts the full request URL — including `api_key=...` — into the exception message. | Demonstrated with a dummy key: `HTTPError("400 ... for url: https://api.stlouisfed.org/...&api_key=DUMMYKEY_abc123")` — the key string is present in the message. | Wrap the request; on any failure raise a sanitized `RuntimeError` (series id + status only, `from None` to drop the URL-bearing cause); replace `raise_for_status()` with an explicit status check that never echoes the URL. | ✅ Fixed |
| Minor | `README.md` | The required FRED attribution line is wrapped across two source lines, so it is not a contiguous verbatim string (renders fine, but fails a strict grep). | `grep "...Federal Reserve Bank of St. Louis"` → 0 hits in README.md (1 hit in REPORT.md and report.html). | Put the attribution on one unbroken line. | ✅ Fixed |
| Minor | `report.py`, `analysis.py`, `charts.py` | Spec requires a docstring + type hints on every function; several helpers were missing one or the other (`_md_table`, `_regime_rows`, `_write_markdown`, `_html_table`, `_write_html`, nested `mult()`/`regime()` lacked docstrings; `_citation(fig)`, `_grouped_bars(ax)` lacked param type hints). | AST coverage scan listed 9 gaps. | Add docstrings and the missing type hints. | ✅ Fixed |

### Recommendations (methodology — not changed; confirm if you want them)

- **Dead-band boundary convention.** After the FP fix, a clean ±1.0 bp leg is
  treated as *flat* (directional requires \|Δ\| > 1.0 bp), matching the code's
  existing `> deadband` intent. The spec's parenthetical "moves smaller than
  1.0 bp count as flat" could instead be read as ±1.0 bp being *directional*
  (flat iff \|Δ\| < 1.0). With 1 bp-granular Treasury data this only affects
  exactly-1 bp legs. I kept the existing convention; tell me if you prefer the
  stricter `<` reading.
- **Mixed-direction days** (one tenor up, the other down beyond the band) are
  labelled `mixed/flat` per the spec. A desk might call some of these twist
  steepeners/flatteners. Per-spec; flagged only.
- **Inner join across DGS2/10/30** drops a date for *all* tenors if any one
  series is missing that day (per the spec "keep only dates where all three
  exist"). Correct per spec; noted for transparency.

---

## Independent re-computations (derived value vs tool value)

### 1. Reproducibility
- Clean-state `python main.py --refresh` → exit 0, produced 4 PNGs + REPORT.md + report.html, no manual steps.
- Ran twice: `yields.csv` **identical**, `events.json` events mapping **identical** (only provenance `fetched_at` timestamps differ — by design), all 4 charts **byte-identical**, REPORT.md/HTML identical except the generation timestamp. → **Idempotent.**
- API key: absent from working tree, `data/`, `output/`, run logs (0 hits), and **every git commit**. Only referenced as `os.environ.get("FRED_API_KEY")` + help text.

### 2. Yield data (independent FRED fetch)
- **15/15** random dates (5 each × DGS2/10/30) fetched directly from FRED **matched `yields.csv` exactly**.
- `yields.csv`: 2111 rows, all `float64`, **0 NaN**, no `"."` survived; values within [0.09, 5.19]% ⊂ [0,15]%.
- bp conversion & previous-trading-day (manual vs tool): Mon 2023-06-12 → prev Fri 2023-06-09, **−4.0 = −4.0**; post-Jul-4 2023-07-05 → prev 2023-07-03 (07-04 absent), **+0.0 = +0.0**; post-Thanksgiving 2024-11-29 → prev 2024-11-27, **−6.0 = −6.0**; plain 2023-03-15 → 2023-03-14, **−27.0 = −27.0**.

### 3. Event dates (independent parse + primary evidence)
- Independent re-parse of BLS yearly pages + Fed calendar/historical pages, diffed vs `events.json` (window 2018-01-01..2026-06-15): **CPI 101=101, NFP 101=101, FOMC 66=66 — sets identical.**
- FOMC per full year: 2018-2025 = **8** each except **2020 = 7** (March meeting cancelled; COVID emergency actions excluded); 2026 = 3 (partial, ≤ today).
- Primary-evidence URLs: **all 22** 2025 CPI/NFP dates → BLS archived release `HTTP 200`; **10/10** cross-year sample `200`; 8 FOMC dates → Fed statement `200` (day-one 2023-01-31 → `404`, proving day-two).
- Shutdown: NFP **2025-11-20** title = "*2025 M09 Results*" and CPI **2025-10-24** = "*2025 M09 Results*" → the **September data really was published in Oct/Nov 2025**. Fabricated "first-Friday" 2025-10-03 and "mid-month" 2025-11-13 are **absent from data and 404 at BLS**.
- No future-dated events (max = 2026-06-10 ≤ today). Only off-calendar event = CPI 2020-04-10 (Good Friday) → **logged and excluded**, not shifted.

### 4. Statistics
- CPI / 2y recomputed by hand: **n=97, mean\|Δ\|=5.6186 (REPORT 5.6), median\|Δ\|=3.0 (REPORT 3.0).** Match.
- **NORMAL baseline: 0 event dates leak in** (excludes CPI/NFP/FOMC/MULTI); n=1846.
- MULTI days = {2019-12-11, 2020-06-10, 2024-06-12}, all genuine CPI+FOMC (verified Dec-2019 & Jun-2024 CPI landed on FOMC Wednesdays); **excluded from single-event buckets**.
- Top \|move\|: 2y 57 bp (2023-03-13, SVB), 10y 30 bp (2022-11-10, CPI), 30y 31 bp (2020-03-06, COVID) — all real, all < 100 bp; none flagged.

### 5. Regimes
- Independent regime table == tool table (**0 mismatches** on current data).
- 6 hand-picked days reproduce all four regimes + mixed/flat. Boundary probe is what exposed the FP bug above.

### 6 / 6b. Report & FRED compliance
- Summary paragraph numbers are programmatic and match the table (CPI/2y 1.6x, NFP/2y 1.9x, FOMC/2y 1.6x, FOMC/30y 0.9x); all 12 table multiples match computed values to 2 dp.
- Charts: axes labelled in bp, n= shown, multiples chart has the 1.0x line, 2s10s chart has the zero line + FOMC dots.
- `report.html`: self-contained (4 inline base64 PNGs, **0** external refs, **0** `<script>`), same numbers as REPORT.md.
- Attribution present in REPORT.md + report.html (README fixed below). Source citation present alongside charts. **No LLM/AI dependency** anywhere; requirements = requests/pandas/matplotlib only.
- **No raw FRED data published**: `data/` (incl. `yields.csv`) git-ignored and absent from all history; reports contain only charts + computed stats (5 dates in prose, no observation table).

### 7. Code quality
- `pyflakes`: clean (no unused imports / undefined names). Browser User-Agent present for BLS. Docstring/type-hint gaps fixed (see findings).

---

## Fix Verification

Re-ran the full pipeline after applying the fixes (`python main.py --refresh`
from a clean state → exit 0; all four charts + REPORT.md + report.html produced;
no manual steps). A second (cached) run produced an **identical REPORT.md (minus
the timestamp) and byte-identical charts** → still idempotent.

- **Major #1 — regime FP boundary → FIXED & confirmed.** `classify_regimes` now
  rounds Δ before the dead-band test, so a clean ±1.0 bp leg is *consistently*
  treated as flat. The regime table is now deterministic and matches the
  predicted post-fix counts exactly (row sums preserved at 97/101/63/3):

  | Event | bull steep | bull flat | bear flat | bear steep | mixed/flat |
  |---|---|---|---|---|---|
  | CPI  | 11 | 14 | 13 | 11 | 48 |
  | NFP  | 10 | 16 | 26 | 13 | 36 |
  | FOMC | 13 |  4 |  7 |  2 | 37 |
  | MULTI|  1 |  2 |  0 |  0 |  0 |

  Isolation check: reaction statistics and multiples run on separate code paths
  and are **unchanged by the fix** (CPI/2y mean\|Δ\| = 5.6186 before and after).

- **Major #2 — API-key leak → FIXED & confirmed.** A forced FRED error now
  raises `RuntimeError: FRED request for DGS10 failed with HTTP 400.`; the key
  string appears in **neither the message nor the full traceback** (tested with
  a dummy key).

- **Minor — README attribution → FIXED:** single contiguous verbatim line.
- **Minor — docstrings/type hints → FIXED:** AST coverage scan reports 0 gaps;
  `pyflakes` clean.

*Note:* FRED published one new trading day (**2026-06-12**) during the audit, so
a fresh run's headline stats differ by that single data point from figures
quoted above (computed through 2026-06-11); 0 existing rows were revised. The
regime table is unaffected (2026-06-12 is not an event day).

**Final verdict: SHIP.**

