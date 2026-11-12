
import os
import time
import requests

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime


class APIFootballError(RuntimeError):
    pass


class APIFootball:
    def __init__(self, base_url, timeout=30, retries=1):
        key = os.getenv("APISPORTS_KEY")

        if not key:
            raise APIFootballError(
                "Missing APISPORTS_KEY environment variable."
            )

        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retries = max(1, retries)

        self.session = requests.Session()
        self.session.headers.update({
            "x-apisports-key": key
        })

        # Avoid exceeding the approximate per-minute API limit.
        self.min_request_interval = 6.2
        self.last_request_time = 0

    def wait_before_request(self):
        elapsed = time.monotonic() - self.last_request_time
        wait = self.min_request_interval - elapsed

        if wait > 0:
            time.sleep(wait)

        self.last_request_time = time.monotonic()

    def retry_delay(self, response, attempt):
        retry_after = response.headers.get("Retry-After")

        if retry_after:
            try:
                return max(1, float(retry_after))
            except ValueError:
                try:
                    retry_date = parsedate_to_datetime(retry_after)

                    if retry_date.tzinfo is None:
                        retry_date = retry_date.replace(
                            tzinfo=timezone.utc
                        )

                    return max(
                        1,
                        (
                            retry_date - datetime.now(timezone.utc)
                        ).total_seconds()
                    )
                except (TypeError, ValueError):
                    pass

        return min(5 * (2 ** attempt), 60)

    def get(self, endpoint, **params):
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        last_error = None

        for attempt in range(self.retries):
            self.wait_before_request()

            try:
                response = self.session.get(
                    url,
                    params=params,
                    timeout=self.timeout
                )

                # Handle HTTP 429 separately.
                if response.status_code == 429:
                    last_error = (
                        "HTTP 429: API rate limit reached."
                    )

                    if attempt + 1 < self.retries:
                        delay = self.retry_delay(response, attempt)

                        print(
                            f"API rate limit reached. "
                            f"Waiting {delay:.0f} seconds."
                        )

                        time.sleep(delay)
                        continue

                    break

                # Do not retry ordinary client errors.
                if 400 <= response.status_code < 500:
                    response.raise_for_status()

                response.raise_for_status()

                payload = response.json()

                errors = payload.get("errors")

                if errors:
                    error_message = str(errors)

                    # Daily quota exhaustion must stop immediately.
                    quota_messages = (
                        "request limit for the day",
                        "reached the request limit",
                        "daily request limit",
                    )

                    if any(
                        message in error_message.lower()
                        for message in quota_messages
                    ):
                        raise APIFootballError(
                            f"Daily API quota exhausted: {error_message}"
                        )

                    # Provider errors are not temporary connection errors.
                    raise APIFootballError(
                        f"Provider returned errors: {error_message}"
                    )

                return payload.get("response", [])

            except APIFootballError:
                raise

            except requests.exceptions.HTTPError as exc:
                last_error = exc

                status = (
                    exc.response.status_code
                    if exc.response is not None
                    else None
                )

                if status is not None and 400 <= status < 500:
                    break

                if attempt + 1 < self.retries:
                    delay = self.retry_delay(
                        exc.response, attempt
                    ) if exc.response is not None else 5

                    print(
                        f"Temporary HTTP error. "
                        f"Waiting {delay:.0f} seconds."
                    )

                    time.sleep(delay)

            except (requests.RequestException, ValueError) as exc:
                last_error = exc

                if attempt + 1 < self.retries:
                    delay = min(5 * (2 ** attempt), 60)

                    print(
                        f"Temporary connection error. "
                        f"Waiting {delay:.0f} seconds."
                    )

                    time.sleep(delay)

        raise APIFootballError(
            f"API request failed for {endpoint}: {last_error}"
        )

    def fixtures_by_date(self, date):
        return self.get("fixtures", date=date)

    def fixture(self, fixture_id):
        rows = self.get("fixtures", id=fixture_id)
        return rows[0] if rows else None

    def team_recent(self, team_id, last=5):
        return self.get(
            "fixtures",
            team=team_id,
            last=last,
            status="FT"
        )

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
