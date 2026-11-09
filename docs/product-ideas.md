# Product ideas

Traveler-facing features under consideration. Nothing here is built yet; this is the list to organize the UX
around and to pick a first slice from. Each idea records what it would need from the backend and what we have
today, so the prioritization can weigh value against how much is missing.

Current state, for reference: AeroDataBox airport boards polled twice a day per tier (11h windows), so each
flight's status is observed only a few times. We store schedule, estimated and actual times, status, terminals,
airline, aircraft type and (for ~50% of flights) the tail. Data collection started live; there is no history
before that.

---

## 1. Single-flight risk assessment: "if this flight is cancelled, when do I get there?"

**Idea.** For one flight, give a probability distribution over when the traveler reaches the destination
*given that the flight is cancelled*. Factors:

- How easily the airline can substitute another aircraft (is the origin a hub or base for that airline?
  spare aircraft of a compatible type?).
- The next flight the traveler would likely be rebooked onto automatically.
- Other options if the automatic rebooking isn't acceptable (other flights by the same airline, its partners,
  other airlines, nearby airports).

**Needs.**

- Hub/base strength per airline per airport: derivable from our own movement data (share of departures).
- Upcoming schedules on the same route, and connecting alternatives, beyond the current 11h board windows.
- Seat availability or load factors on alternative flights. We have no source for this, and it is the biggest
  driver of "when will I actually get a seat".
- Airline rebooking behavior: which flights and partners they rebook onto, and how far out. Partly curated,
  partly learned.
- Ground truth to calibrate against. We see cancellations, but not where the passengers ended up. A first
  version would be a model of the options, not a learned distribution.

**Have.** Schedules and cancellations as observed, airlines, aircraft types, tails.

## 2. Multi-flight itineraries and connections

**Idea.** Extend (1) from single flights to itineraries with connections. Delays and cancellations of earlier
legs now decide whether later legs are reachable. Must account for:

- Whether the trip is one ticket (protected connection; the airline rebooks on a missed connection) or
  separately booked legs (self-transfer; a missed connection is the traveler's problem).
- Airline alliances and interline agreements.
- Baggage: through-checked or re-checked.
- Security and immigration re-screening at the connecting airport, and terminal changes.
- Airline timing leeway (minimum connection times; holding a connecting flight for a late inbound).

**Needs.**

- Distribution of arrival delay per flight, to get the probability of making each connection.
- Minimum connection times per airport, terminal pair and domestic/international. The official MCT data is
  proprietary (IATA/OAG); we may have to curate approximations.
- Alliance and interline membership (small curated table).
- Terminal per flight (we have it) and inter-terminal transfer times (curated).
- Rules for which connections need re-screening or immigration (curated, per airport/country).

**Have.** Terminals, scheduled and actual times, airlines.

## 3. Early cancellation prediction, with notifications

**Idea.** Predict a cancellation before the airline usually tells passengers, so travelers can act first
(rebook, change plans). Signals:

- Tracking the inbound aircraft (where is the plane that is supposed to operate this flight?).
- Airport conditions: weather, runway or gate restrictions, ground stops, ATC programs.
- Operating hours and curfews (a late inbound that pushes the departure past curfew).
- Crew duty limits, as a later refinement.

Requires accounts so users can enter or sync their itineraries, and notifications (push, email, or SMS) when we
anticipate a cancellation.

**Needs.**

- Aircraft rotations: linking a flight to the inbound flight by tail. We have tails for ~50% of flights, and
  many tails are only assigned close to departure.
- Much fresher status for tracked flights than twice-daily board polls, e.g. on-demand flight-status calls for
  flights users are tracking. That spends API units per tracked flight, so it needs its own budget line.
- Weather (METAR/TAF from aviationweather.gov, free) and US airport status (FAA NAS status, free; other regions
  vary).
- Curfews and operating hours (curated).
- A history of cancellations with what preceded them, to train and measure against. We can't observe when
  airlines notified passengers; the closest proxy is when the status changed in our polls, which is only as
  precise as the poll frequency.
- Auth, an itinerary store, itinerary import (manual entry first; email forwarding or calendar sync later), a
  notification channel, and an always-on host (the current laptop setup misses polls when it sleeps).

**Have.** Statuses and tails as observed. None of the live-tracking or user infrastructure.

## 4. Reliability score at booking time

**Idea.** The traveler enters a planned itinerary and gets a reliability score, with a natural-language
explanation of why (e.g. "the 7:05 leg is cancelled 3x more often than the route average; the 45-minute
connection at ORD is tight for a terminal change").

**Needs.**

- Historical on-time and cancellation rates per flight number, route, airline, airport, time of day, and
  season. This needs months of collected data before it is meaningful, and a full year for seasonality.
- Connection risk from (2) for itineraries with connections.
- The AI layer, to explain the score from the underlying numbers without inventing any.
- Handling of flights we don't poll (airports outside our tiers) and sparse data (new routes, rare flights).

**Have.** The data is starting to accumulate. This is the idea that most directly reuses what is collected
today.

---

## Shared foundations

Several ideas depend on the same backend pieces, which is worth weighing when picking an order:

| Foundation | 1 | 2 | 3 | 4 |
|---|---|---|---|---|
| Historical delay/cancellation stats | ✓ | ✓ | ✓ | ✓ |
| Schedule horizon beyond 11h (alternatives, future legs) | ✓ | ✓ | | ✓ |
| Itinerary model (legs, ticketing, connections) | | ✓ | ✓ | ✓ |
| Curated reference: hubs, alliances, MCT, curfews | ✓ | ✓ | ✓ | ✓ |
| Aircraft rotations by tail | ✓ | | ✓ | |
| Fresher status for tracked flights | | | ✓ | |
| Accounts and notifications | | | ✓ | |
| Seat availability / load factors (no source yet) | ✓ | | | |

## Open questions

- Who is the first user: travelers at booking time (4), travelers on the day of travel (1–3), or both?
- Do we need coverage beyond the airports we poll today for these ideas to be useful, and what would that cost
  in API units?
- Which source, if any, gives seat availability or load factors?
- How much history before scores and predictions are shown, and how is low confidence shown in the UI?
