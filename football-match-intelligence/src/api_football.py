
import os
import time
import requests
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime


class APIFootballError(RuntimeError):
    pass


class APIFootball:
    def __init__(self, base_url, timeout=30, retries=3):
        key = os.getenv("APISPORTS_KEY")

        if not key:
            raise APIFootballError(
                "Missing APISPORTS_KEY environment variable."
            )

        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retries = retries
        self.session = requests.Session()
        self.session.headers.update({"x-apisports-key": key})

        # Limit requests to approximately 10 per minute.
        self.min_request_interval = 6.2
        self.last_request_time = 0

    def wait_before_request(self):
        elapsed = time.monotonic() - self.last_request_time
        wait = self.min_request_interval - elapsed

        if wait > 0:
            time.sleep(wait)

        self.last_request_time = time.monotonic()

    def retry_delay(self, response, attempt):
        # Use the delay requested by the API, if provided.
        retry_after = response.headers.get("Retry-After")

        if retry_after:
            try:
                return max(1, float(retry_after))
            except ValueError:
                try:
                    retry_date = parsedate_to_datetime(retry_after)
                    if retry_date.tzinfo is None:
                        retry_date = retry_date.replace(tzinfo=timezone.utc)

                    return max(
                        1,
                        (retry_date - datetime.now(timezone.utc)).total_seconds()
                    )
                except (TypeError, ValueError):
                    pass

        # Otherwise, progressively increase the waiting time.
        return min(60 * (2 ** attempt), 300)

    def get(self, endpoint, **params):
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        last_error = None

        # Allow extra attempts for rate-limit responses.
        max_attempts = max(self.retries, 5)

        for attempt in range(max_attempts):
            self.wait_before_request()

            try:
                response = self.session.get(
                    url,
                    params=params,
                    timeout=self.timeout
                )

                if response.status_code == 429:
                    last_error = "HTTP 429: API rate limit reached"

                    if attempt + 1 < max_attempts:
                        delay = self.retry_delay(response, attempt)
                        print(
                            f"API rate limit reached. "
                            f"Waiting {delay:.0f} seconds before retry..."
                        )
                        time.sleep(delay)
                        continue

                    break

                response.raise_for_status()

                payload = response.json()
                errors = payload.get("errors")

                if errors:
                    raise APIFootballError(
                        f"Provider returned errors: {errors}"
                    )

                return payload.get("response", [])

            except requests.exceptions.HTTPError as exc:
                last_error = exc

                # Do not retry ordinary client errors such as HTTP 400 or 403.
                status = (
                    exc.response.status_code
                    if exc.response is not None
                    else None
                )

                if status is not None and 400 <= status < 500:
                    break

                if attempt + 1 < max_attempts:
                    delay = min(5 * (2 ** attempt), 60)
                    print(
                        f"Temporary API error. "
                        f"Waiting {delay} seconds before retry..."
                    )
                    time.sleep(delay)

            except (requests.RequestException, ValueError) as exc:
                last_error = exc

                if attempt + 1 < max_attempts:
                    delay = min(5 * (2 ** attempt), 60)
                    print(
                        f"Connection error. "
                        f"Waiting {delay} seconds before retry..."
                    )
                    time.sleep(delay)

            except APIFootballError:
                raise

        raise APIFootballError(
            f"API request failed for {endpoint}: {last_error}"
        )

    def fixtures_by_date(self, date):
        return self.get("fixtures", date=date)

    def fixture(self, fixture_id):
        rows = self.get("fixtures", id=fixture_id)
        return rows[0] if rows else None

    def team_recent(self, team_id, last=5):
        return self.get("fixtures", team=team_id, last=last, status="FT")

    def head_to_head(self, home_id, away_id, last=5):
        return self.get(
            "fixtures/headtohead",
            h2h=f"{home_id}-{away_id}",
            last=last
        )

    def injuries(self, fixture_id):
        return self.get("injuries", fixture=fixture_id)

    def lineups(self, fixture_id):
        return self.get("fixtures/lineups", fixture=fixture_id)

    def events(self, fixture_id):
        return self.get("fixtures/events", fixture=fixture_id)

    def statistics(self, fixture_id):
        return self.get("fixtures/statistics", fixture=fixture_id)
