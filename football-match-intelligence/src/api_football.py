import os
import time
import requests

class APIFootballError(RuntimeError):
    pass

class APIFootball:
    def __init__(self, base_url, timeout=30, retries=3):
        key = os.getenv("APISPORTS_KEY")
        if not key:
            raise APIFootballError("Missing APISPORTS_KEY environment variable.")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retries = retries
        self.session = requests.Session()
        self.session.headers.update({"x-apisports-key": key})

    def get(self, endpoint, **params):
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        last_error = None
        for attempt in range(self.retries):
            try:
                response = self.session.get(url, params=params, timeout=self.timeout)
                response.raise_for_status()
                payload = response.json()
                errors = payload.get("errors")
                if errors:
                    raise APIFootballError(f"Provider returned errors: {errors}")
                return payload.get("response", [])
            except (requests.RequestException, ValueError, APIFootballError) as exc:
                last_error = exc
                if attempt + 1 < self.retries:
                    time.sleep(2 ** attempt)
        raise APIFootballError(f"API request failed for {endpoint}: {last_error}")

    def fixtures_by_date(self, date):
        return self.get("fixtures", date=date)

    def fixture(self, fixture_id):
        rows = self.get("fixtures", id=fixture_id)
        return rows[0] if rows else None

    def team_recent(self, team_id, last=5):
        return self.get("fixtures", team=team_id, last=last, status="FT")

    def head_to_head(self, home_id, away_id, last=5):
        return self.get("fixtures/headtohead", h2h=f"{home_id}-{away_id}", last=last)

    def injuries(self, fixture_id):
        return self.get("injuries", fixture=fixture_id)

    def lineups(self, fixture_id):
        return self.get("fixtures/lineups", fixture=fixture_id)

    def events(self, fixture_id):
        return self.get("fixtures/events", fixture=fixture_id)

    def statistics(self, fixture_id):
        return self.get("fixtures/statistics", fixture=fixture_id)
