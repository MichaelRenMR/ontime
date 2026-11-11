# AGENTS.md

Context for AI agents working in this repo. The README covers the backend in detail (architecture, schema,
schedule, commands); this file covers what the README doesn't: how to work here, the product direction, the
UX design so far and the decisions behind it.

## What OnTime is

A web app that tells travellers how reliable a flight is. The backend collects departure and arrival boards
from AeroDataBox into Postgres on a Prefect schedule (live-only data, collection started 7 Oct 2026). The front
end and AI layer are not built; the UX exists as design mockups (below).

**Primary user story: booking time.** A traveller choosing what to book enters an origin airport, a destination
airport and an arrive-by date and time, sees the non-stop flights ranked by reliability (a prediction made weeks
or months out, from historical patterns), and opens one for the breakdown. Tracking a booked flight as the date
nears (live status, text alerts, the rating firming up) is the follow-on, and the same flight page serves both.
There are no user accounts for now: alerts go to a phone number. Wider ideas and their backend needs are in
`docs/product-ideas.md`.

**Next step:** backend design, driven from the UX below (what data and services the screens need).

## Working rules

- **The repo is public.** Never commit `.env`. Never print or echo API keys; check them by presence or length
  only. Provider responses (raw payloads, `backend/tests/fixtures/`) stay local and gitignored. Scan the staged
  diff for secrets before every commit or push.
- Tests must never use the real API key (the suite blanks it). Database backups go in the gitignored `backups/`.
- Commit or push only when the user asks.
- Don't add documentation of things the code or git history already records.

## UX design

### Where it lives

- Sources: `.design/itinerary-risk/project/*.dc.html` plus `canvas.json` (board positions, sizes, titles, notes).
- Published as a private Claude Design canvas: https://claude.ai/artifact/EGewaM8rhkLmJgMPM3AUos (only the
  owner can open it).
- Screenshots of earlier versions: `docs/screenshots/`, embedded in `docs/product-ideas.md`.

| Board | File | Screen |
|---|---|---|
| 1 | `Main.dc.html` | Track a flight: flight number + date, recent searches |
| 2, 3 | `Result.dc.html`, `ResultMobile.dc.html` | One flight's reliability (desktop, phone 390px) |
| 4 | `Route.dc.html` | Plan a trip (main landing): From / swap / To, Arrive by |
| 5, 6 | `RouteResults.dc.html`, `RouteResultsMobile.dc.html` | Non-stop flights on a route, ranked (desktop, phone) |

The two landing pages link to each other: the flight page's header link says "Plan trip" (its button "Track
flight"); the booking page's header link says "Track flight" (its button "Plan trip"). Result pages' back
arrow returns to wherever the user came from (stored in `sessionStorage` as `ontime.back`).

### Editing the `.dc.html` files

- Format: markup inside `<x-dc>` with `{{dotted.holes}}`, `<sc-if value>`, `<sc-for list as>`, and a
  `class Component extends DCLogic` script whose `renderVals()` returns the values (state via
  `this.state` / `this.setState`). Tweakable props are in the script tag's `data-props`.
- Inline SVG `<text>` inside `sc-for` doesn't render; use absolutely positioned HTML spans for chart labels.
- **The user edits the canvas directly.** Before publishing, check the live version (list the artifact's files
  and compare sizes, or read the file) and merge any changes made there, or you will overwrite their edits.
- To check layout, render headlessly: copy the files plus the runtime (`artifact-type/dc-runtime.js` from the
  artifact, saved as `support.js`) into a temp dir and run Chrome with `--headless=new --screenshot
  --virtual-time-budget=8000 --window-size=W,H`. Look at the screenshot before calling a change done.

### Data in the mockups

Flights, dates and outcomes are real, from the dev database: BA 305 (7 Oct – 9 Nov 2026) and the CDG→LHR
timetable and route stats (4/201 cancelled, 45/183 landed 15+ min late, average flight ~84 min). Illustrative
until the backend exists: every score and trend, airport checks, industry and airline averages, rebooking
chances, partner connections, and seat counts (typical cabin layouts; there is no seat data source). One known
inconsistency: the result pages show BA 305 as 11:40→12:00, but the real timetable is 11:15→11:40.

### Design principles (from the user's corrections; follow them)

- **Design the ideal UX first.** Don't hedge designs on current backend or data gaps; the backend will be built
  to serve the UX. Never present invented data as real.
- **Audience:** ordinary travellers, not analysts. Plain, positive words ("reliability", not "risk"); no
  aviation jargon as labels ("rotation", "ATC", "outstation").
- **Look:** boxy and dense (square corners, tight padding, more useful data per screen over decoration).
  Nothing templated or generic ("looks like Expedia" was a rejection). No maps, no plane logo.
- **Palette** (light take on the Material Firewatch VS Code theme): ink `#282C34`, slate `#343A46`, gold
  `#E5C07B`, teal `#56B6C2`, orange `#DD672C`, red `#E06C75` (`#A8323E` on white). Chips: Good `#E3F4F6`/`#1F5F67`,
  Fair `#FBF1DC`/`#7A5510`. Dark is used for landing heroes, header bars, the flight "ticket" and route stats;
  the rest is white.
- **Type:** Geist everywhere. Rejected: Atkinson Hyperlegible, B612 Mono and Space Mono.
- **Ratings:** 0–10 score with a word band (Good ≥7, Fair ≥4, Poor) and a 10-cell segmented meter. Trend
  icons are thick double chevrons with no tail (up better, down worse, » unchanged), never arrows.
- **Day changes always shown:** a time on a different calendar day from the reference date gets a bold +1/−1
  superscript with a "Next day"/"Previous day" tooltip, on every screen.
- **Every interactive element has a hover state** (~0.12 s): rows tint, buttons darken, links go gold on dark.
- Other flights' numbers are plain links to that flight's page (don't design those pages). Whole rows are links
  where a row is clickable. No rating chips or popovers on those links (tried, too much).
- Don't add chart axis or tick labels to the outlook history, arrival histogram or radar charts unprompted; the
  user will supply them.

### Screen decisions

**Landing pages.** Full-screen dark hero. Headline as split-flap departure-board tiles, uppercase, one tile
per character, flipping in once on load (reduced motion respected): "GET THERE, / ON TIME." (booking) and
"HOW'S YOUR FLIGHT / LOOKING?" (tracking). Gold Plan trip / Track flight button, one-line recent searches
below. Wordmark: small glowing gold square + "OnTime". The booking search takes airport codes (placeholder
"Airport, e.g. CDG"), not cities, and a single "Arrive by (date and time)" field, with no separate date
picker anywhere. "Non-stop flights only, for now." Rejected: a "Just cancelled" list, a blank ticket
filling in as you type, date-chip pickers.

**Route results.** Header "CDG → LHR" + "Arrive by Sat 21 Nov, 13:00"; slate search band (From, To, Arrive by).
Then a dark route-stats dropdown row, closed by default: "Last 4 weeks on this route" over "2% cancelled  25%
landed 15+ min late", chevron at far right. Opening it shows:
- "Arrivals by day": one cell per day with average minutes early/late, cancelled days as inverted white
  "N Cxl", late days ≥15 min in gold.
- An hourly histogram with a Departures | Arrivals toggle (arrivals default, teal, dashed arrive-by marker;
  departures gold), bars ~45% of the slot, header including "average flight 1 h 23 min".
- A "Share of seats" pie by airline, weighted by seats not flights, header "· 13 flights a day".

On desktop the histogram and pie share a row; on phone they stack and the "Arrive by" legend sits right of
the toggle. Below: a "Departing" day filter (3 days ending on the arrival date), then "N flights" and a sort
toggle (Most reliable | Least time to spare = latest arrival first). Toggles are grey segmented controls with
a dark selected segment. Rows: band chip + score + trend over a meter, flight + airline, times + duration,
"X h Y min to spare", aircraft type rightmost, chevron. Flights landing after the arrive-by time aren't listed.

Removed and not to be re-added unprompted: column headers on desktop, cancelled and landed-late columns, a
"Land after" section, a "no backup" warning icon (parked in `docs/product-ideas.md` under Future UX ideas).

Phone: the rating sits on the left in a narrow stacked column (~62px: chip over score + trend + meter). To its
right are three lines: flight + airline, times + duration, "Time to spare: …" with the aircraft type.

**Flight result page.** Header: back arrow, "BA 305  Sat 21 Nov". Dark top:
- **Flight outlook band** (slate): "Flight outlook", a live dot with "Updated 6 min ago" (grey when updates
  pause), and Fair 4.6/10 + meter + trend. A chevron at the far right expands to the rating-history line chart,
  then a "When you'll arrive" histogram (10-min bins plus a red Cancelled bar), then a radar chart against the
  industry and airline averages. Each chart has its own row, never side by side.
- **Ticket:** large times (44px; 34px phone) with origin/destination and terminals. Below them, one grid of
  fields: Aircraft, Tail number, Aircraft age, Incoming flight ("BA 304 · lands 10:35", no route), and Time on
  the ground. Missing values show "Pending". No per-field uncertainty marks.

Then on white:
- A "Get text alerts" row.
- **Rating breakdown:** flat single-line rows sorted worst first. Each row has the trend chevron at the far
  left, a tag (Risk / Watch / Good), the factor name and an expand chevron. Expanding shows the factor's own
  score, the finding, a chart or table, and a muted "Based on …" line with its data source and horizon (e.g.
  historical weather for the month at long range, upgrading automatically as better data arrives). The factors
  are Past flights, Your plane, Weather, Airport operations, Airline operations and Travel notices.
- **Cancellation options:** two collapsed groups. "Likely automatic rebooks" covers the airline and its
  alliance, each option with a % chance. "Other airlines, same direct route" is tagged "New ticket". Backup
  flights live here, never inside the reliability score.

### Open items (offered, not yet agreed)

- Fix BA 305's times on the result pages to the real 11:15→11:40.
- Remove "Sign in" (there are no accounts).
- Make the route search the only home page; rename or rewire Track flight.
- The user may tone down the split-flap headlines (mixed case, or booking page only).
