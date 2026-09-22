# EU ETS Carbon Market: Data Availability and Contract Mechanics (as of September 2026)

Scope note: this file is written for a developer building a systematic research pipeline. Every figure below is
either (a) taken from a primary exchange/Commission page and cited, or (b) listed under **Gaps** as unverified.
Where a download could not be executed in this session (the sandbox HTTPS proxy returned 403 on
`public.eex-group.com`), the URL is given but the file's internal schema is flagged as unverified.

---

## 1. EUA futures contract specifications (ICE Endex and EEX)

### Takeaway
ICE and EEX EUA futures are near-identical in economics — 1,000 allowances per lot, EUR, €0.01/tonne tick
(= €10.00 per lot), physically delivered by allowance transfer, with a "last Monday of the contract month"
expiry rule adjusted for UK bank holidays. Both list far more than December-only: ICE Endex lists up to 7
Decembers, 9 quarterlies, 3 Augusts and 2 monthlies; EEX lists monthlies, 11 quarterlies plus Jul/Aug/Dec.
The December annual contract is the liquidity benchmark by convention, not by contract design.

### Cited Findings — ICE Endex EUA Futures
- Contract symbol: **"C"** — [ICE EUA Futures](https://www.ice.com/products/197/EUA-Futures)
- Contract size: **"One lot of 1,000 EUAs. Each EUA being an Allowance which is an entitlement to emit one tonne of carbon dioxide equivalent gas."** — [ICE](https://www.ice.com/products/197/EUA-Futures)
- Currency / quotation: **"The contract price is in Euros and Euro cents per metric tonne"** — [ICE](https://www.ice.com/products/197/EUA-Futures)
- Minimum price fluctuation: **1 Euro cent per tonne (€0.01/tonne)**; tick value **€10.00 per lot** — [ICE](https://www.ice.com/products/197/EUA-Futures)
- Contract series: **"Up to 7 December, 9 quarterly, 3 August and 2 monthly contracts or as otherwise determined and announced by ICE Endex"** — [ICE](https://www.ice.com/products/197/EUA-Futures)
- Last trading day: **"Trading will cease at the close of business on the last Monday of the contract month. However, if the last Monday is a UK Bank Holiday or there is a UK Bank Holiday in the 4 days following the last Monday, the last day of trading will be the penultimate Monday"** — [ICE](https://www.ice.com/products/197/EUA-Futures)
- Settlement method: **Physical Delivery** — [ICE](https://www.ice.com/products/197/EUA-Futures)
- Delivery window: begins **09:00 (LLT) the business day following last trading day**; ends **15:00 (LLT) on the third business day** after, extendable to the fourth business day if delays occur — [ICE](https://www.ice.com/products/197/EUA-Futures)
- Exchange / clearing: listed on **ICE Endex**, cleared at **ICEU (ICE Clear Europe)** — [ICE](https://www.ice.com/products/197/EUA-Futures)
- Trading hours: London **07:00–17:00** (New York 02:00–12:00; Singapore 14:00–00:00 local) — [ICE](https://www.ice.com/products/197/EUA-Futures)
- A separate **ICE EUA Daily Future** exists as a distinct product — [ICE EUA Daily Future](https://www.ice.com/products/18709519/EUA-Daily-Future)

### Cited Findings — EEX EUA Futures / Spot / Options
- EUA **Spot**: contract size **1,000 EUA (1 lot)**; minimum tick **€0.01 per EUA** = **€10.00 per lot**; EUR; physical delivery, with fulfilment on the **"First ECC business day after the conclusion of the contract for trades concluded before 4:00 p.m. CET"** — [EEX EU ETS Spot, Futures & Options](https://www.eex.com/en/markets/environmentals/eu-ets-spot-futures-options)
- EUA **Futures**: contract size **1,000 EUA (1 lot)**; minimum tick **€0.01 per EUA / €10.00 per lot**; EUR — [EEX](https://www.eex.com/en/markets/environmentals/eu-ets-spot-futures-options)
- EEX expiry months: **monthly (current + next 2), quarterly (current + next 11), plus July, August and December contracts** — [EEX](https://www.eex.com/en/markets/environmentals/eu-ets-spot-futures-options)
- EEX last trading day: **"The last Monday of the maturity month that fulfills the following prerequisite: Neither this Monday nor one of the following four calendar days is a public holiday in Great Britain."** — [EEX](https://www.eex.com/en/markets/environmentals/eu-ets-spot-futures-options)
- EEX settlement: physical — **"ECC transfers the purchased Emission Rights into the internal account of the purchaser in the ECC internal account system"**; delivery on **"the second ECC business day after the last trading day"** — [EEX](https://www.eex.com/en/markets/environmentals/eu-ets-spot-futures-options)
- EEX **EUA Options**: underlying is **EUA December Futures**; **European** exercise style; maturities monthly (current + 2), quarterly (current + 11), plus August and December; last trading day is **"The third exchange trading day prior to the Last Trading Day of the EEX EUA Month Future that expires in the same month"**; automatic exercise **at 3 p.m. if in the money**; future-style (daily premium settlement) — [EEX](https://www.eex.com/en/markets/environmentals/eu-ets-spot-futures-options)
- EEX auction product (primary market) differs from the futures: auction unit is **1 EUA with a minimum lot size of 500 allowances**, tick **€0.01 per allowance**, settlement **delivery-versus-payment, t+1** — [EEX EU ETS1 Auctions](https://www.eex.com/en/markets/environmental-markets/eu-ets-auctions)
- EEX publishes a consolidated contract specification PDF (versioned, with track changes), e.g. the 29 Jan 2026 edition — [EEX Contract Specifications PDF](https://www.eex.com/fileadmin/EEX/Downloads/Rules/Contract_Specifications/20260129_EEX_Contract_Spezifications_0100a_E_FINAL_track_changes.pdf)

### Inferences
- The ICE and EEX last-trading-day rules are **worded differently but resolve to the same calendar day** in
  virtually all months (both are "last Monday, pushed back if a GB/UK bank holiday falls on it or within the
  following four days"). A pipeline should still compute the roll date independently from a UK bank-holiday
  calendar rather than assuming ICE == EEX, and should verify the two against each other each December.
- Delivery lag differs: ICE's delivery window opens the **business day after** last trading day; EEX delivers
  on the **second ECC business day after**. This matters for financing/carry calculations on the spot-futures
  basis, not for price series construction.
- Because both venues list monthlies and quarterlies, "the EUA front contract" is ambiguous. Most published
  research and most free data series use the **December annual** contract (Dec-YY), which is the deepest.
  A continuous series must state its roll convention explicitly; a naive "nearest expiry" roll will pick up
  thin monthly contracts and produce spurious returns.
- Tick value €10/lot with a €1,000-per-€1 notional sensitivity means a 1-tick move is 0.01% of notional at a
  €100 price — fine granularity, so tick-size effects are negligible for daily-frequency research.

### Gaps
- **ICE Endex vs ICE Futures Europe listing venue.** The ICE product page for symbol "C" states ICE Endex as
  the exchange and ICEU as the clearing venue. Historically EUA futures were on ICE Futures Europe before the
  2021 migration to ICE Endex (Brexit-driven). I did **not** verify the exact migration date from a primary
  ICE circular. Anyone joining pre-2021 and post-2021 ICE data must confirm this themselves — the venue code
  and possibly the instrument identifier changed.
- **Exact ICE contract months currently listed** (which specific Decembers/quarterlies are live today) — the
  spec gives maxima ("up to 7 December…"), not the live chain. Requires a live listing query.
- **EEX minimum/maximum order quantities, position limits, and exchange fees** — not verified.
- **Whether ICE's "last Monday" rule references UK bank holidays even though the contract is now on ICE Endex
  (Dutch entity)** — the spec text says "UK Bank Holiday", which I have quoted verbatim, but I did not find a
  supplementary circular confirming no Dutch-holiday overlay.

---

## 2. The auction calendar and auction result data

### Takeaway
EEX operates the Common Auction Platform and publishes auction results as a **single cumulative XLSX per year**
at a stable, public, no-login URL on `public.eex-group.com`, with a 2012–2025 history archive as ZIP. There is
**no documented free REST API** — it is file download only. Auction days are Mon/Tue/Thu (common platform),
Fri (Germany), alternate Wed (Poland), plus a single annual Northern Ireland auction.

### Cited Findings — schedule and volumes
- Common Auction Platform (CAP3): **"Weekly auctions on Mondays, Tuesdays and Thursdays"**; **Germany**: weekly Friday auctions; **Poland**: **"Bi-weekly auctions on Wednesdays"**; **UK (Northern Ireland electricity)**: annual auction — [EEX EU ETS1 Auctions](https://www.eex.com/en/markets/environmental-markets/eu-ets-auctions)
- 2025 volumes: CAP3 scheduled to auction **461,902,500 EUAs**; **Germany 73,503,500**; **Poland 52,532,500** — [EEX EU ETS1 Auctions](https://www.eex.com/en/markets/environmental-markets/eu-ets-auctions)
- 2027 schedule: common platform Mon/Tue/Thu **starting 7 January 2027**; Germany Fridays **starting 8 January**; Poland bi-weekly Wednesdays **starting 13 January**; Northern Ireland a single auction on **13 October 2027** — [European Commission, 30 July 2026](https://climate.ec.europa.eu/news-other-reads/news/revised-2026-and-2027-eu-ets1-auction-calendars-published-2026-07-30_en)
- **190,494,202 allowances** to be placed in the MSR for the **September 2026 – August 2027** period, which is why the 2026 calendar was revised — [European Commission, 30 July 2026](https://climate.ec.europa.eu/news-other-reads/news/revised-2026-and-2027-eu-ets1-auction-calendars-published-2026-07-30_en)
- **50 million allowances** designated for the **Social Climate Fund in 2026** — [European Commission, 30 July 2026](https://climate.ec.europa.eu/news-other-reads/news/revised-2026-and-2027-eu-ets1-auction-calendars-published-2026-07-30_en)
- **RRF / REPowerEU auctioning "has been completed June and July 2026"**, so subsequent calendars exclude RRF auctions — [European Commission, 30 July 2026](https://climate.ec.europa.eu/news-other-reads/news/revised-2026-and-2027-eu-ets1-auction-calendars-published-2026-07-30_en)
- Calendar publication is governed by **Article 12(2) of the Auctioning Regulation**; the revised 2026 and new 2027 ETS1 calendars were to be published by EEX **"before 31 July"** 2026; the **ETS2 calendar** was to be published **"at the latest in September 2026"** — [European Commission, 2 July 2026](https://climate.ec.europa.eu/news-other-reads/news/timing-publication-eu-ets-auction-calendar-2026-07-02_en)
- EEX auction calendar page: [https://www.eex.com/en/trading-resources/trading-information/calendar#5401](https://www.eex.com/en/trading-resources/trading-information/calendar#5401) — [EEX](https://www.eex.com/en/markets/environmental-markets/eu-ets-auctions)

### Cited Findings — result files, formats, history, access
- Landing page: [EEX EUA Primary Auction Spot download](https://www.eex.com/en/market-data/market-data-hub/environmentals/eex-eua-primary-auction-spot-download)
- Current-year file (cumulative, XLSX): **`https://public.eex-group.com/eex/eua-auction-report/emission-spot-primary-market-auction-report-2026-data.xlsx`** — [EEX](https://www.eex.com/en/market-data/market-data-hub/environmentals/eex-eua-primary-auction-spot-download)
- History: **"History Emission Spot Primary Market Auction Report 2012 - 2025"** offered as a ZIP archive on eex.com fileadmin; legacy separate datasets also exist for **Germany, Lithuania and the Netherlands** (opt-out national platforms) — [EEX](https://www.eex.com/en/market-data/market-data-hub/environmentals/eex-eua-primary-auction-spot-download)
- **No login is required** for these downloads based on the page content — [EEX](https://www.eex.com/en/market-data/market-data-hub/environmentals/eex-eua-primary-auction-spot-download)
- EEX also publishes free **Emissions Open Interest** daily Excel files on the environmentals data hub — [EEX Environmentals Market Data](https://www.eex.com/en/market-data/market-data-hub/environmentals-data)
- Licence constraint stated on EEX market data pages: **"Any systematic republication or dissemination of substantial amount of Data is only permitted with the express permission of EEX AG"** — [EEX](https://www.eex.com/en/market-data/environmentals/eu-ets-auctions)
- Real-time and end-of-day price data are sold via **EEX Group DataSource** / the webshop at `https://webshop.eex-group.com/`; market data contact `datasource@eex-group.com`, +49 341 2156-288 — [EEX](https://www.eex.com/en/market-data/environmentals/eu-ets-auctions)
- EEX auction rules and access pages: [Rules & Regulations](https://www.eex.com/en/markets/environmental-markets/eu-ets-auctions/rules-and-regulations), [Access to the auctions](https://www.eex.com/en/markets/environmental-markets/eu-ets-auctions/access-to-the-auctions)

### Inferences
- The `public.eex-group.com/eex/eua-auction-report/...-<YEAR>-data.xlsx` pattern is **year-parameterised and
  stable**, so a pipeline can poll a single URL daily and diff for new rows rather than scraping HTML. It is
  a cumulative file, not per-auction files, so an incremental loader should key on auction date + auction
  platform.
- Because the file is cumulative and rewritten, **revisions are silent**. A pipeline should checksum and
  version each snapshot so that a retroactive correction to a past clearing price is detectable; otherwise a
  backtest silently changes when re-run.
- The "no systematic republication" clause restricts **redistribution**, not download for internal research.
  Downloading the public auction XLSX for in-house model building is materially different from rebroadcasting
  it. Legal sign-off is advisable before any product exposes EEX-sourced values to third parties.
- The Poland auctions being **bi-weekly Wednesdays** and Germany **weekly Fridays** means daily auction supply
  is lumpy and predictable — a supply-surprise feature must be constructed against the *scheduled* calendar,
  not against a naive weekly average.
- Auction calendars are **revised intra-year** (2026 was revised in July). Any feature using "scheduled
  auction volume" must be point-in-time: store the calendar as it stood on each date, not the final version.

### Gaps
- **Field-by-field schema of the auction report XLSX is NOT verified.** The sandbox proxy returned HTTP 403 on
  `public.eex-group.com`, so I could not open the file, and no EEX page I fetched lists the columns. The
  commonly-cited fields (auction date, auction name/platform, product, auction volume, clearing price, total
  amount of bids, cover ratio, number of bidders, number of successful bidders, minimum/maximum bid, auction
  charge, auction fee) are **not confirmed here** — the developer must open the file and enumerate columns
  before writing a parser. Do not code against a remembered schema.
- **Exact URL of the 2012–2025 history ZIP** — the page references it but the fetched content did not surface
  the literal fileadmin path.
- **Whether EEX exposes any JSON/REST endpoint for auction results** — none documented on any page fetched;
  EEX pages point exclusively to the webshop for programmatic feeds. Treat "no free API" as the working
  assumption, verified only to the extent that no page advertises one.
- **2026 and 2027 total auction volumes in allowances** — the Commission news item gives the MSR intake and
  the SCF carve-out but the fetched content did not state 2026/2027 CAP3/Germany/Poland totals.
- **EUAA (aviation) auction schedule and volumes** — not covered by any page fetched.

---

## 3. The Market Stability Reserve (MSR)

### Takeaway
The MSR is a rule-based supply valve keyed to the TNAC, published annually by the Commission (deadline moved
from 15 May to **1 June** by the 2023 revision) and effective for the **following September–August** auction
year. Since 2024 there is a two-tier intake: 24% of TNAC above 1,096m, and a "difference to 833m" taper in
the 833–1,096m band. Below 400m, 100m allowances are released.

### Cited Findings
- Upper threshold: when TNAC exceeds **1,096 million** allowances, the MSR withdraws **"24% of the TNAC, over a 12-month period"** — [European Commission, MSR](https://climate.ec.europa.eu/eu-action/eu-emissions-trading-system-eu-ets/market-stability-reserve_en)
- Lower threshold: when TNAC falls below **400 million**, the MSR releases **100 million allowances for auction** — [European Commission](https://climate.ec.europa.eu/eu-action/eu-emissions-trading-system-eu-ets/market-stability-reserve_en)
- Mitigated ("threshold effect") band from **2024**: when TNAC is between **833 and 1,096 million**, intake equals **the difference between the TNAC and 833 million** — [European Commission](https://climate.ec.europa.eu/eu-action/eu-emissions-trading-system-eu-ets/market-stability-reserve_en)
- The **24% intake rate** has been maintained from the 2018 ETS revision through the 2023 revision (Directive (EU) 2023/959) — [European Commission](https://climate.ec.europa.eu/eu-action/eu-emissions-trading-system-eu-ets/market-stability-reserve_en)
- Invalidation: from **1 January 2023**, allowances held in the MSR above a threshold are permanently invalidated annually. For **2023** the threshold equalled the volume auctioned in **2022**; from **2024** onward it is a fixed **400 million allowances** — [European Commission](https://climate.ec.europa.eu/eu-action/eu-emissions-trading-system-eu-ets/market-stability-reserve_en)
- TNAC publication deadline **"moved from 15 May to 1 June"** under the 2023 revision — [European Commission](https://climate.ec.europa.eu/eu-action/eu-emissions-trading-system-eu-ets/market-stability-reserve_en)
- Most recent publication cited on that page: **4 June 2025 (C/2025/3120)** for 2024 TNAC data, in EUR-Lex — [EUR-Lex CELEX 52025XC03180](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A52025XC03180)
- Resulting 2026/27 MSR intake: **190,494,202 allowances** to be placed in the MSR over **September 2026 – August 2027** — [European Commission, 30 July 2026](https://climate.ec.europa.eu/news-other-reads/news/revised-2026-and-2027-eu-ets1-auction-calendars-published-2026-07-30_en)

### Inferences
- The TNAC-to-supply transmission has a **known, exploitable lag structure**: TNAC for year *Y-1* is published
  by 1 June of year *Y*, and the resulting auction adjustment runs **September of year Y to August of year
  Y+1**. A scarcity model can therefore treat the September–August supply path as *known* from early June,
  and the informational event is the TNAC publication itself, not the auction calendar revision.
- The 190,494,202 figure implies a TNAC comfortably above the 1,096m upper threshold (24% intake) or a large
  taper amount — but I did not verify the underlying TNAC value, so do not back it out arithmetically for
  publication without checking the source notice.
- The 2023 invalidation rule caps the MSR at 400m and makes withdrawn allowances **permanently destroyed**
  rather than deferred. For a long-horizon scarcity model this converts what was a timing mechanism into a
  genuine cumulative-cap reduction — a structural break in any pre-2023-calibrated supply model.
- The two-tier intake introduces a **kink** in the supply response function around TNAC = 1,096m and a second
  one at 833m. Linear supply-elasticity specifications estimated across the kink will be misspecified.

### Gaps
- **The 2026 TNAC publication (for 2025 data) — its exact date, value, and CELEX number** were not verified.
  The MSR page cited the 2025 publication. A pipeline needs the current-year notice; check EUR-Lex and the
  Commission MSR page directly.
- **Whether a machine-readable TNAC series exists.** The TNAC is published as a Commission Communication in
  EUR-Lex (HTML/PDF), not as a dataset. No structured endpoint was found.
- **Exact MSR feed-in mechanics for aviation allowances and ETS2** (ETS2 has its own separate stability
  mechanism) — not verified here.

---

## 4. Free secondary-market price data

### Takeaway
There is **no free, licence-clean, deep-history, machine-readable EUA settlement price series from a primary
venue**. EEX and ICE both gate real-time/EOD prices behind commercial subscriptions and EEX explicitly
prohibits systematic republication. The genuinely free, well-documented option is the **Zenodo EU ETS Data
Package (CC-BY-4.0)**, which bundles EEX primary auction prices and volumes — auction clearing prices, not
exchange settlement prices. Derived trackers (Bruegel, Sandbag) are usable for charting but thin on licence
and download documentation.

### Cited Findings
**EEX public pages**
- Free: **EUA Primary Auction Reports (2025, 2026)**, **Emissions Open Interest daily Excel files**, and German nEHS market data — [EEX Environmentals Market Data](https://www.eex.com/en/market-data/market-data-hub/environmentals-data)
- Licence: **"Any systematic republication or dissemination of substantial amount of Data is only permitted with the express permission of EEX AG"** — [EEX](https://www.eex.com/en/market-data/environmentals/eu-ets-auctions)
- Real-time and EOD prices are commercial, via **EEX Group DataSource** and `https://webshop.eex-group.com/` — [EEX](https://www.eex.com/en/market-data/environmentals/eu-ets-auctions)
- No API is mentioned anywhere on the environmentals data hub — [EEX](https://www.eex.com/en/market-data/market-data-hub/environmentals-data)

**ICE**
- ICE Report Center states that **"End of day report packages in .csv format are available for purchase on a subscription basis"** — [ICE Report Center](https://www.ice.com/marketdata/reports/278)
- Report URLs follow the pattern `https://www.ice.com/report/[number]` — [ICE Report Center](https://www.ice.com/marketdata/reports/278)

**Zenodo — EU ETS Data Package (the strongest free option)**
- DOI **10.5281/zenodo.20509231**; **version 1, published 2 June 2026, modified 20 June 2026** — [Zenodo](https://zenodo.org/records/20509231)
- Single archive **`eutl_data_package_2026-06-20.zip`, 492.7 MB**, containing **"interlinked CSV tables with a full schema descriptor"** (Frictionless Data Package) — [Zenodo](https://zenodo.org/records/20509231)
- Contents include installation compliance records (verified emissions, allocations, surrendered allowances), registry accounts and account holders, unit-level transactions, CDM/JI offset projects, geocoded installation coordinates, NACE codes, and **"EUA primary auction prices and volumes from the European Energy Exchange"** — [Zenodo](https://zenodo.org/records/20509231)
- Licence: **CC-BY-4.0** covering **"the compilation, structuring, and transformations contributed by the authors,"** with underlying data subject to original provider terms — [Zenodo](https://zenodo.org/records/20509231)
- **Programmatic access available via REST API and direct file URLs** — [Zenodo](https://zenodo.org/records/20509231)
- Maintainer: **Jan Abrell (University of Basel)**; processing code at [https://jabrell.github.io/euetsinfo/](https://jabrell.github.io/euetsinfo/) — [Zenodo](https://zenodo.org/records/20509231)

**Bruegel ETS Tracker**
- Covers ETS1 emissions compliance data, free allocation, **auction revenues and allowance prices**, and installation-level information (compliance, ownership, location, activity type) — [Bruegel ETS Tracker](https://www.bruegel.org/dataset/ets-tracker)
- Released **15 July 2026**; DOI **https://doi.org/10.64153/HWZB9221**; interactive site at [https://ets.bruegel.org/](https://ets.bruegel.org/) — [Bruegel](https://www.bruegel.org/dataset/ets-tracker)
- Authors include **Jan Abrell** — the same maintainer as the Zenodo package — [Bruegel](https://www.bruegel.org/dataset/ets-tracker)

**Sandbag Carbon Price Viewer**
- Series: **EUA price** ("the price of emitting 1 tonne of CO2-equivalent for a European industrial installation or airline covered by the Emissions Trading System") — [Sandbag Carbon Price Viewer](https://sandbag.be/carbon-price-viewer/)
- History **since 2008** (start of Phase 2); current through **April 2026** — [Sandbag](https://sandbag.be/carbon-price-viewer/)
- Source is **spliced**: pre-December 2009 from **Quandl (spot-month continuous contract)**; post-December 2009 from **ICAP (auction settlement prices from European Energy Exchange AG)** — [Sandbag](https://sandbag.be/carbon-price-viewer/)

**Ember**
- Ember publishes a data API — [Ember API](https://ember-energy.org/data/api/) — and European wholesale electricity price data — [Ember](https://ember-energy.org/data/european-wholesale-electricity-price-data/) — but I found **no dedicated free EUA price dataset** from Ember in searches.

### Inferences
- The **Zenodo package is the right backbone** for a research pipeline: CC-BY-4.0, versioned with a DOI,
  Frictionless schema descriptor, and a Zenodo REST API for automated retrieval. Its price content is
  **auction clearing prices**, which is a legitimate daily EUA price series (one observation per auction day)
  but is *not* the exchange futures settlement curve. It cannot support term-structure or roll-yield work.
- The Sandbag series is **spliced across two different definitions** (a continuous spot-month contract before
  Dec-2009, auction settlement prices after). That splice is a manufactured discontinuity at end-2009 and the
  series should not be used for return calculations across that boundary without an adjustment.
- Bruegel's tracker and the Zenodo package share an author (Abrell), so they are **not independent
  corroboration** — treat them as one source family, both ultimately derived from EUTL plus EEX auction files.
- Practical conclusion: for a systematic futures strategy you will need a **paid** feed (EEX DataSource, ICE
  Consolidated Feed, or a redistributor such as Databento/Refinitiv/Bloomberg) for settlement prices. Free
  data is sufficient for the *fundamental supply side* (auctions, TNAC, emissions) but not the *price side*.

### Gaps
- **ICE free/delayed data**: I could not verify from ICE's own pages whether any delayed EUA settlement price
  is published free of charge, what the delay is, or the terms. The Report Center page fetched was a
  directory, not a product page. This needs a direct check of the specific ICE report for ICE Endex
  settlements.
- **Bruegel ETS Tracker download format, history depth, update cadence and licence** — the dataset page did
  not state them; the interactive site would need to be inspected.
- **Sandbag download URL and licence** — the page does not advertise a CSV/XLSX download or state terms.
- **Zenodo package coverage year range** — the record does not state explicit start/end years.
- **Zenodo update cadence** — "active development" is implied but no stated schedule; version 1 is dated
  June 2026, so treat it as roughly annual until proven otherwise.
- **Whether Ember has any EUA price product at all** — not confirmed either way.

---

## 5. Registry and compliance data (EUTL / Union Registry)

### Takeaway
Installation-level verified emissions, free allocation and surrendered allowances are published on the Union
Registry public website as **XLSX reports**, with verified emissions typically in **April** and compliance
status in **early October**. Transaction-level data carries roughly a **three-year** publication lag by design.
For 2026 the verified emissions report for compliance year 2025 was announced for **9 April 2026 at the latest**.

### Cited Findings
- Public site: **https://union-registry-data.ec.europa.eu/** — [European Commission, Union Registry](https://climate.ec.europa.eu/areas-action/carbon-markets/eu-emissions-trading-system-eu-ets/union-registry_en)
- Published content: **"Data on free allocation, verified emissions, and compliance status of operators"** and **"Transactions taking place in the Registry, as well as data on account holders"** — [European Commission](https://climate.ec.europa.eu/areas-action/carbon-markets/eu-emissions-trading-system-eu-ets/union-registry_en)
- Format: downloadable reports in **XLSX**, including annual Verified Emissions reports, annual Compliance data reports, the List of operators in the EU ETS, and the List of transactions — [European Commission](https://climate.ec.europa.eu/areas-action/carbon-markets/eu-emissions-trading-system-eu-ets/union-registry_en)
- Timetable: Verified Emissions typically **April** each year; Compliance data typically **early October** each year — [European Commission](https://climate.ec.europa.eu/areas-action/carbon-markets/eu-emissions-trading-system-eu-ets/union-registry_en)
- Transaction lag: as of **31 October 2025**, the published transaction list covered transactions **up to 1 October 2022** — i.e. approximately a **three-year** delay — [European Commission](https://climate.ec.europa.eu/areas-action/carbon-markets/eu-emissions-trading-system-eu-ets/union-registry_en)
- 2026 announcement: **"this year's ETS Verified Emissions Report will be published on April 9, 2026, at the latest"**, announced **18 February 2026** — [European Commission, 18 Feb 2026](https://climate.ec.europa.eu/news-other-reads/news/publication-verified-emissions-report-2025-2026-02-18_en)
- Historical precedent for the timing: the Commission has announced release dates each March for an early-April publication, e.g. **"On 1 April 2019 the European Commission will release verified EU ETS emissions data and compliance information for 2018"** — [European Commission, 2019](https://climate.ec.europa.eu/news-your-voice/news/1-april-2019-european-commission-will-release-verified-eu-ets-emissions-data-and-compliance-2019-03-18_en); and a 2025 notice — [European Commission, 20 Mar 2025](https://climate.ec.europa.eu/news-other-reads/news/eu-ets-publication-verified-emissions-data-2025-03-20_en)
- Alternate curated access: the **EEA EU ETS data viewer** — [EEA dashboards](https://www.eea.europa.eu/en/analysis/maps-and-charts/emissions-trading-viewer-1-dashboards) and the [EEA EUTL dataset](https://www.eea.europa.eu/data-and-maps/data/european-union-emissions-trading-scheme-16)

### Inferences
- **The look-ahead trap is concrete and datable.** Verified emissions for compliance year *Y* become public in
  **early April of year Y+1** (9 April in 2026; 1 April in 2019), and compliance/surrender status in **early
  October of Y+1**. Any feature using year-*Y* emissions must be lagged to at least the April *Y+1* release,
  and any feature using surrender/compliance status to October *Y+1*. Using calendar-year-end alignment
  injects 3–9 months of look-ahead.
- The publication date **moves year to year** (1 April 2019 vs 9 April 2026), so a fixed "1 April" lag is
  itself unsafe. The correct construction is to store the **actual release date** of each annual file and
  align features to that, which means maintaining a small table of announced release dates from the
  Commission news feed.
- The **three-year transaction lag** means account-level flow data is useless for live signals and only
  supports structural/academic work. Do not design a positioning or flow feature on EUTL transactions.
- Verified emissions data is also **revised** after first publication (late reporters, corrections). A
  point-in-time store of each annual snapshot is required, not just the latest file.
- The compliance deadline structure changed under the revised Directive (surrender moved later in the year),
  which is consistent with the October compliance-report timing — but see Gaps.

### Gaps
- **The current surrender deadline** — whether it remains 30 April or has moved to 30 September under the
  revised ETS Directive — was **not confirmed** from a primary source in this session. The 18 Feb 2026
  Commission notice I fetched addressed only the report publication date. This matters for modelling the
  compliance-buying seasonal and must be verified against the consolidated Directive text before use.
- **Exact file URLs and filename patterns** on `union-registry-data.ec.europa.eu` — not enumerated.
- **Whether the Union Registry site offers any API** — not stated; assume XLSX download only.
- **Whether free allocation figures are published on the same April timetable** or separately (NIMs / final
  allocation decisions follow their own cycle) — not verified.

---

## 6. UK ETS

### Takeaway
The UK ETS auctions on ICE Futures Europe, **every other Wednesday**, with results in the ICE Report Centre.
Free data availability is materially worse documented than the EU side: ICE publishes auction calendars as
public PDF circulars, but I could not confirm that historical UKA auction results or price series are freely
downloadable in machine-readable form.

### Cited Findings
- Auctions occur **"every other Wednesday throughout the year, between 12.00 and 14.00 UK time"**, the first having taken place on **19 May 2021** — [ICE, Auctions for UK Emission Allowances](https://www.ice.com/emissions/auctions/uk-emission-allowances)
- Results are published through **"the ICE Report Centre for UKA auction results"**, at [https://www.ice.com/marketdata/reports/278](https://www.ice.com/marketdata/reports/278) — [ICE](https://www.ice.com/emissions/auctions/uk-emission-allowances)
- Auction fee: successful bidders pay **"£1.75 per contract, which equates to £0.0035 per allowance"** — [ICE](https://www.ice.com/emissions/auctions/uk-emission-allowances) (this implies a 500-allowance auction contract)
- Related listed products: **ICE UKA Auction, ICE UKA Futures, ICE UKA Daily Futures** — [ICE](https://www.ice.com/emissions/auctions/uk-emission-allowances)
- Auction calendars are published as public ICE circular PDFs, e.g. [2026 UK ETS Auction Calendar, Circular 25/146](https://www.ice.com/publicdocs/circulars/25146.pdf), [2025, Circular 24/137](https://www.ice.com/publicdocs/circulars/24137.pdf), [2024, Circular 23/149](https://www.ice.com/publicdocs/circulars/23149.pdf)
- UK government guidance on participating in UK ETS markets — [GOV.UK](https://www.gov.uk/government/publications/taking-part-in-the-uk-emissions-trading-scheme-markets/taking-part-in-the-uk-emissions-trading-scheme-markets)

### Inferences
- The **£1.75 per contract ÷ £0.0035 per allowance = 500 allowances per auction contract** arithmetic is
  internally consistent with the EU auction lot convention (EEX minimum lot 500), so the UKA auction unit is
  very likely 500. I am stating this as an inference, not a verified spec.
- Circular numbering is **year-prefixed and sequential** (`23/149`, `24/137`, `25/146`), so the URL pattern
  `https://www.ice.com/publicdocs/circulars/YYNNN.pdf` is discoverable but **not predictable** — the sequence
  number changes. A pipeline must scrape the circular index rather than construct URLs.
- The UK–EU relative-value trade is structurally attractive (both physically delivered, both allowance-based)
  but the UKA series starts only **May 2021**, giving a short sample, and it spans the 2023–2025 period of
  UK–EU linkage negotiation, which is a regime the history cannot span.

### Gaps
- **UKA futures contract specifications** (lot size, tick, expiry months, last trading day, delivery) — the
  ICE UKA product pages were not fetched; the auction page lists the products without specs. **Unverified.**
- **Whether UKA auction results in the ICE Report Centre are free without login, their format, their fields,
  and how far back they go** — not confirmed. The Report Centre page states EOD CSV packages are a paid
  subscription, which suggests at least some of this is gated.
- **UK ETS auction volumes and cap schedule for 2026/2027** — not verified.
- **Status of UK–EU ETS linkage as of September 2026** — not researched; this is a first-order risk for any
  UKA/EUA spread strategy and should be checked separately.
- **Any free UKA price series equivalent to the Zenodo/Bruegel EU datasets** — none found.

---

## 7. Known traps for a backtest

### Takeaway
The EU ETS has had at least five distinct structural breaks a naive backtest will get wrong: the Phase 3→4
boundary at 2021, the 2021 venue migration from ICE Futures Europe to ICE Endex, the REPowerEU auction
front-loading (2023–mid-2026), the 2024 maritime and aviation changes, and the MSR rule change in 2023 that
made withdrawn allowances permanently invalid. Plus the pending ETS2 launch, which has been **postponed to
2028** — a change that contradicts materials still published in mid-2026.

### Cited Findings
**Phase and cap changes**
- Phase 3 = **2013–2020**; Phase 4 = **2021–2030** — [ICAP, EU ETS](https://icapcarbonaction.com/en/ets/eu-emissions-trading-system-eu-ets)
- Linear reduction factor: **2.2% for 2021–2023**, **4.3% for 2024–2027**, **4.4% from 2028** — [ICAP](https://icapcarbonaction.com/en/ets/eu-emissions-trading-system-eu-ets)
- One-off cap rebasings: **−90 million allowances in 2024** and **−27 million in 2026** — [ICAP](https://icapcarbonaction.com/en/ets/eu-emissions-trading-system-eu-ets)

**Aviation**
- Aviation included in the EU ETS in **2012** with a separately calculated cap; scope limited to EEA flights from **2013**, and that limited scope **"was extended until the end of 2026"** — [ICAP](https://icapcarbonaction.com/en/ets/eu-emissions-trading-system-eu-ets)
- Aviation free allocation phase-out: **75% in 2024, 50% in 2025, 0% from 2026** — [ICAP](https://icapcarbonaction.com/en/ets/eu-emissions-trading-system-eu-ets)

**Maritime**
- Shipping included **from 2024**, covering **all large ships of 5,000 gross tonnage and above** — [ICAP](https://icapcarbonaction.com/en/ets/eu-emissions-trading-system-eu-ets)
- Surrender phase-in: **40% of emissions reported in 2024**, **70% of 2025**, **100% of 2026 and later** — [ICAP](https://icapcarbonaction.com/en/ets/eu-emissions-trading-system-eu-ets)

**Auction supply shifts**
- RRF (REPowerEU) auctioning **"has been completed June and July 2026"**; calendars from 2027 exclude RRF auctions — [European Commission, 30 July 2026](https://climate.ec.europa.eu/news-other-reads/news/revised-2026-and-2027-eu-ets1-auction-calendars-published-2026-07-30_en)
- 2026 calendar was **revised mid-year** (published before 31 July 2026) because of the MSR intake calculation — [European Commission, 2 July 2026](https://climate.ec.europa.eu/news-other-reads/news/timing-publication-eu-ets-auction-calendar-2026-07-02_en)

**MSR rule change**
- From **1 January 2023**, MSR holdings above the threshold are **permanently invalidated** (threshold = 2022 auction volume for 2023; **400 million** fixed from 2024) — [European Commission, MSR](https://climate.ec.europa.eu/eu-action/eu-emissions-trading-system-eu-ets/market-stability-reserve_en)

**ETS2 — direct source conflict, flagged**
- The Commission's 30 July 2026 news item states: **"The auctioning of allowances in respect of buildings, road transport and additional sectors (ETS2 allowances) will start in January 2027"** — [European Commission, 30 July 2026](https://climate.ec.europa.eu/news-other-reads/news/revised-2026-and-2027-eu-ets1-auction-calendars-published-2026-07-30_en)
- ICAP's EU ETS profile states EU ETS 2 is **"to start in 2028"** — [ICAP](https://icapcarbonaction.com/en/ets/eu-emissions-trading-system-eu-ets)
- Multiple secondary sources report that Parliament and Council agreed to **postpone ETS2 to 2028**: [CLECAT — EP and Council confirm ETS2 postponement to 2028](https://www.clecat.org/news/newsletters/ep-and-council-confirm-ets2-postponement-to-2028); [EU Perspectives, Feb 2026 — "Plenary approved 2040 Climate Target, ETS2 postponed until 2028"](https://euperspectives.eu/2026/02/plenary-approved-2040-climate-target-ets2-postponed-until-2028/); [BUILD UP (EC portal) — "EU postpones carbon pricing for buildings to 2028 in climate law deal"](https://build-up.ec.europa.eu/en/news-and-events/news/eu-postpones-carbon-pricing-buildings-2028-climate-law-deal)

**Price series splice**
- Sandbag's EUA series changes definition at December 2009 (Quandl spot-month continuous → ICAP/EEX auction settlement prices) — [Sandbag](https://sandbag.be/carbon-price-viewer/)

**Registry look-ahead**
- Verified emissions for year *Y* published early April of *Y+1* (9 April in 2026); compliance data early October of *Y+1*; transactions ~3 years lagged — [European Commission](https://climate.ec.europa.eu/areas-action/carbon-markets/eu-emissions-trading-system-eu-ets/union-registry_en); [European Commission, 18 Feb 2026](https://climate.ec.europa.eu/news-other-reads/news/publication-verified-emissions-report-2025-2026-02-18_en)

### Inferences
- **The ETS2 date is genuinely contested in the sources I fetched.** The Commission's own July 2026 auction
  calendar news says January 2027; ICAP and several February 2026 reports say 2028. The most likely
  reconciliation is that the legislative postponement to 2028 post-dates or supersedes the auction-calendar
  drafting, or that the calendar news reflects the pre-amendment legal baseline. **This must be resolved from
  the published amending Directive before anything is built on it** — do not pick a side from this note.
- **Phase 3 → Phase 4 (2020→2021) is the single most dangerous joint.** Phase 3 allowances were bankable into
  Phase 4, so the price series is continuous in a way the 2012→2013 joint was not — but the December contract
  vintages changed, the LRF changed, and the ICE venue migrated. Treat 2021 as a regime boundary and test
  pre/post stability of any signal rather than assuming continuity.
- **The 2013 joint is a hard break.** Phase 2 allowances were not bankable into Phase 3 in the same way, and
  the Phase 2 price collapse (2011–2013) reflects a different asset. Backtests that start in 2008 are
  effectively testing two different instruments.
- **REPowerEU front-loading (2023 to mid-2026) is a pure supply shock with a known end date.** Auction volumes
  were elevated and are now stepping down as RRF auctioning completed in June–July 2026. Any supply feature
  estimated on 2023–2026 data is estimated in an unrepresentative regime, and any model that keys on
  auction volume will see a level shift in H2 2026.
- **Maritime is a demand shock phased in over 2024–2026** (40/70/100%), so covered emissions rise mechanically
  independent of economic activity. Emissions-based demand features must normalise for scope changes or they
  will read the 2024–2026 scope ramp as demand growth.
- **Aviation free allocation going to zero in 2026** converts airlines from partially-hedged recipients to
  full auction/market buyers — a structural demand step in 2026, distinct from the maritime ramp.
- **The MSR invalidation from 2023 changed the asset's long-run supply.** Any cointegration or fair-value
  model calibrated on pre-2023 data is calibrated on a system where withdrawn allowances eventually returned.
- **Continuous-contract construction is the quiet killer.** With Decembers, quarterlies, monthlies and Augusts
  all listed, "front contract" is ambiguous; the December-to-December roll is the market convention and the
  Dec/Dec spread has its own carry dynamic. Document the roll rule and produce both unadjusted and
  back-adjusted series.

### Gaps
- **Total REPowerEU/RRF front-loaded volume and its year-by-year distribution** — not verified from a primary
  source. ICAP's page did not contain it and I did not fetch the relevant Regulation.
- **Exact date of the ICE EUA futures migration from ICE Futures Europe to ICE Endex** — unverified (see §1).
- **The definitive legal status and date of ETS2** — conflicting sources, unresolved (see above).
- **Whether the aviation scope "stop-the-clock" extension to end-2026 was further extended, and what applies
  from 2027** — not verified.
- **Whether any EUA price series discontinuity exists at the 2021 ICE venue migration** (settlement price
  methodology change, instrument ID change) — not verified.
- **Historical revisions to published auction results** — no source found documenting whether EEX restates
  past auction rows.

---

## Cross-cutting summary for the pipeline builder

**What is reliably buildable free, today:**
1. Auction supply and clearing prices: EEX cumulative XLSX per year at
   `https://public.eex-group.com/eex/eua-auction-report/emission-spot-primary-market-auction-report-<YEAR>-data.xlsx`,
   plus a 2012–2025 history ZIP. No login. Schema must be inspected before parsing (unverified here).
2. Structural registry/compliance data: Zenodo EU ETS Data Package, CC-BY-4.0, DOI 10.5281/zenodo.20509231,
   CSV with Frictionless schema, Zenodo REST API. Includes EEX auction prices and volumes.
3. Institutional supply rules: Commission MSR page + annual TNAC Communication in EUR-Lex (by 1 June each
   year, effective September–August).
4. Installation-level emissions: Union Registry public site, XLSX, early April (emissions) and early October
   (compliance) of the following year.

**What requires payment:** EUA futures settlement and intraday prices (EEX DataSource / ICE subscription).
There is no free primary-venue settlement curve with a licence permitting programmatic use.

**The three things most likely to invalidate a first attempt:**
- Aligning verified emissions to the calendar year instead of its actual April *Y+1* release date.
- Treating the auction calendar as static when it is revised intra-year and was revised in July 2026.
- Building a continuous futures series without an explicit December-roll convention across the 2021 phase and
  venue boundary.
