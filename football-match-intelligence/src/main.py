import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from .config import load_config, project_path
from .api_football import APIFootball
from .reporting import make_pre_report, make_post_report, fixture_parts, slug

def report_path(cfg, fixture, kind):
    dt = datetime.fromisoformat(fixture["fixture"]["date"].replace("Z", "+00:00"))
    home, away, _ = fixture_parts(fixture)
    directory = project_path(cfg["reports"]["output_dir"]) / dt.strftime("%Y/%m/%d")
    filename = f"{fixture['fixture']['id']}-{slug(home.get('name','home'))}-v-{slug(away.get('name','away'))}-{kind}.md"
    return directory / filename

def load_saved_prediction(pre_path):
    # Predictions are stored in a small JSON sidecar to make post-match review reproducible.
    sidecar = pre_path.with_suffix(".json")
    if sidecar.exists():
        try:
            return json.loads(sidecar.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return None
    return None

def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description="Generate automated football match reports.")
    parser.add_argument("--mode", choices=["pre", "post", "both"], default="both")
    parser.add_argument("--days-ahead", type=int, default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    cfg = load_config()
    api = APIFootball(cfg["provider"]["base_url"], cfg["provider"]["timeout_seconds"], cfg["provider"]["max_retries"])
    now = datetime.now(timezone.utc)
    ahead = args.days_ahead if args.days_ahead is not None else cfg["automation"]["days_ahead"]
    lookback = cfg["automation"]["lookback_days"]
    pre_window = timedelta(hours=cfg["automation"]["pre_match_hours"])
    post_delay = timedelta(minutes=cfg["automation"]["post_match_delay_minutes"])
    candidates = {}
    for offset in range(-lookback, ahead + 1):
        day = (now + timedelta(days=offset)).date().isoformat()
        for fixture in api.fixtures_by_date(day):
            if cfg["automation"]["competitions"] and fixture.get("league", {}).get("id") not in cfg["automation"]["competitions"]:
                continue
            candidates[fixture["fixture"]["id"]] = fixture

    generated = 0
    for fixture in candidates.values():
        kickoff = datetime.fromisoformat(fixture["fixture"]["date"].replace("Z", "+00:00"))
        status = fixture.get("fixture", {}).get("status", {}).get("short", "")
        fid = fixture["fixture"]["id"]
        pre_path = report_path(cfg, fixture, "pre-match")
        post_path = report_path(cfg, fixture, "post-match")
        if args.mode in ("pre", "both") and now <= kickoff <= now + pre_window:
            if args.force or not pre_path.exists():
                content, prediction = make_pre_report(api, fixture, cfg)
                pre_path.parent.mkdir(parents=True, exist_ok=True)
                pre_path.write_text(content, encoding="utf-8")
                if prediction:
                    pre_path.with_suffix(".json").write_text(json.dumps(prediction, indent=2), encoding="utf-8")
                generated += 1
                print(f"Created {pre_path}")
        if args.mode in ("post", "both") and status in ("FT", "AET", "PEN") and now >= kickoff + post_delay:
            if args.force or not post_path.exists():
                prediction = load_saved_prediction(pre_path)
                content = make_post_report(api, fixture, cfg, prediction)
                post_path.parent.mkdir(parents=True, exist_ok=True)
                post_path.write_text(content, encoding="utf-8")
                generated += 1
                print(f"Created {post_path}")
    print(f"Finished. Generated {generated} report(s) from {len(candidates)} fixture(s).")

if __name__ == "__main__":
    main()
