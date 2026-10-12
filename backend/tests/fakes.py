from datetime import UTC, date, datetime, timedelta

from ontime.ingest.base import Movement

START = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
END = START + timedelta(hours=6)
MOVE = Movement(source="fake", airport_iata="JFK", side="dep", airline_iata="UA", flight_number="888",
                sched_date_local=date(2026, 10, 1), sched_utc=START + timedelta(hours=1), terminal="7")


class FakeProvider:
    name = "fake"
    max_window = timedelta(hours=11)

    def __init__(self, board=None, fail=None, parse_error=False, fail_first=None):
        self.board = board if board is not None else {"flights": [1]}
        self.fail, self.parse_error, self.fail_first = fail, parse_error, fail_first
        self.fetches, self.seen_tz = 0, []

    def cost_units(self, kind):
        return {"board": 2, "airport": 1}[kind]

    def fetch_board_payloads(self, airport_iata, start_utc, end_utc, tz):
        self.fetches += 1
        self.seen_tz.append(tz)
        if self.fail_first and self.fetches == 1:
            raise self.fail_first
        if self.fail:
            raise self.fail
        return [self.board]

    def parse_board(self, airport_iata, payload):
        if self.parse_error:
            raise ValueError("bad shape")
        return [MOVE]
