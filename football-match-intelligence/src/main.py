
import argparse
import json
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from .config import load_config, project_path
from .api_football import APIFootball, APIFootballError
from .reporting import (
    make_pre_report,
    make_post_report,
    fixture_parts,
    slug,
)


MAX_MATCHES_PER_DAY = 5


def report_path(cfg, fixture, kind):
    dt = datetime.fromisoformat(
        fixture["fixture"]["date"].replace("Z", "+00:00")
    )
    home, away, _ = fixture_parts(fixture)

    directory = (
        project_path(cfg["reports"]["output_dir"])
        / dt.strftime("%Y/%m/%d")
    )

    filename = (
        f"{fixture['fixture']['id']}-"
        f"{slug(home.get('name', 'home'))}-"
        f"v-{slug(away.get('name', 'away'))}-{kind}.md"
    )

    return directory / filename


def load_saved_prediction(pre_path):
    sidecar = pre_path.with_suffix(".json")

    if sidecar.exists():
        try:
            return json.loads(
                sidecar.read_text(encoding="utf-8")
            )
        except (ValueError, OSError):
            return None

    return None


def quota_exhausted(error):
    message = str(error).lower()

    return (
        "request limit for the day" in message
        or "reached the request limit" in message
        or "daily request limit" in message
    )


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Generate automated football match reports."
    )

    parser.add_argument(
        "--mode",
        choices=["pre", "post", "both"],
        default=os.getenv("MODE", "both").lower()
    )

    parser.add_argument("--days-ahead", type=int, default=None)

    parser.add_argument(
        "--force",
        action="store_true",
        default=os.getenv("FORCE", "false").lower() == "true"
    )

    args = parser.parse_args()

    cfg = load_config()

    api = APIFootball(
        cfg["provider"]["base_url"],
        cfg["provider"]["timeout_seconds"],
        cfg["provider"]["max_retries"]
    )

    timezone_name = cfg["automation"]["timezone"]
    local_tz = ZoneInfo(timezone_name)

    now = datetime.now(timezone.utc)
    local_today = now.astimezone(local_tz).date()

    ahead = (
        args.days_ahead
        if args.days_ahead is not None
        else cfg["automation"]["days_ahead"]
    )

    lookback = cfg["automation"]["lookback_days"]

    # Keep the existing date-access window restriction.
    allowed_start = local_today - timedelta(days=1)
    allowed_end = local_today + timedelta(days=1)

    requested_start = local_today - timedelta(days=lookback)
    requested_end = local_today + timedelta(days=ahead)

    start_date = max(requested_start, allowed_start)
    end_date = min(requested_end, allowed_end)

    if start_date > end_date:
        print("No dates available within the permitted API date window.")
        return

    pre_window = timedelta(
        hours=cfg["automation"]["pre_match_hours"]
    )

    post_delay = timedelta(
        minutes=cfg["automation"]["post_match_delay_minutes"]
    )

    competitions = set(cfg["automation"].get("competitions", []))

    candidates_by_day = defaultdict(list)

    # Retrieve fixtures, stopping immediately if the daily quota is exhausted.
    current_day = start_date

    try:
        while current_day <= end_date:
            day = current_day.isoformat()

            print(f"Searching fixtures for {day}...")

            fixtures = api.fixtures_by_date(day)

            for fixture in fixtures:
                league_id = fixture.get("league", {}).get("id")

                if competitions and league_id not in competitions:
                    continue

                kickoff = datetime.fromisoformat(
                    fixture["fixture"]["date"].replace("Z", "+00:00")
                )

                fixture_day = kickoff.astimezone(local_tz).date()

                candidates_by_day[fixture_day].append(fixture)

            current_day += timedelta(days=1)

    except APIFootballError as exc:
        if quota_exhausted(exc):
            print("Daily API quota exhausted. Stopping safely.")
            return

        raise

    generated = 0
    selected_count = 0

    for fixture_day in sorted(candidates_by_day):
        fixtures = sorted(
            candidates_by_day[fixture_day],
            key=lambda item: item["fixture"]["date"]
        )

        eligible = []

        # Keep only matches that need a report.
        for fixture in fixtures:
            kickoff = datetime.fromisoformat(
                fixture["fixture"]["date"].replace("Z", "+00:00")
            )

            status = fixture.get("fixture", {}).get(
                "status", {}
            ).get("short", "")

            pre_path = report_path(cfg, fixture, "pre-match")
            post_path = report_path(cfg, fixture, "post-match")

            needs_pre = (
                args.mode in ("pre", "both")
                and now <= kickoff <= now + pre_window
                and (args.force or not pre_path.exists())
            )

            needs_post = (
                args.mode in ("post", "both")
                and status in ("FT", "AET", "PEN")
                and now >= kickoff + post_delay
                and (args.force or not post_path.exists())
            )

            if needs_pre or needs_post:
                eligible.append((fixture, needs_pre, needs_post))

        # Maximum five selected matches for each local fixture date.
        selected = eligible[:MAX_MATCHES_PER_DAY]

        print(
            f"{fixture_day}: {len(selected)} match(es) selected "
            f"out of {len(eligible)} eligible."
        )

        for fixture, needs_pre, needs_post in selected:
            selected_count += 1

            pre_path = report_path(cfg, fixture, "pre-match")
            post_path = report_path(cfg, fixture, "post-match")

            try:
                if needs_pre:
                    content, prediction = make_pre_report(
                        api, fixture, cfg
                    )

                    pre_path.parent.mkdir(
                        parents=True, exist_ok=True
                    )

                    pre_path.write_text(
                        content, encoding="utf-8"
                    )

                    if prediction:
                        pre_path.with_suffix(".json").write_text(
                            json.dumps(prediction, indent=2),
                            encoding="utf-8"
                        )

                    generated += 1
                    print(f"Created {pre_path}")

                if needs_post:
                    prediction = load_saved_prediction(pre_path)

                    content = make_post_report(
                        api, fixture, cfg, prediction
                    )

                    post_path.parent.mkdir(
                        parents=True, exist_ok=True
                    )

                    post_path.write_text(
                        content, encoding="utf-8"
                    )

                    generated += 1
                    print(f"Created {post_path}")

            except APIFootballError as exc:
                if quota_exhausted(exc):
                    print(
                        "Daily API quota exhausted. "
                        "Stopping remaining reports."
                    )
                    print(
                        f"Generated {generated} report(s) before stopping."
                    )
                    return

                print(
                    f"Could not process fixture "
                    f"{fixture['fixture']['id']}: {exc}"
                )

    print(
        f"Finished. Generated {generated} report(s) "
        f"from {selected_count} selected match(es)."
    )


if __name__ == "__main__":
    main()
