from datetime import datetime, timezone
from pathlib import Path
import re
from .analysis import form_summary, match_probabilities, pct
from .api_football import APIFootballError

def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")

def kickoff_local(iso, timezone_name):
    try:
        from zoneinfo import ZoneInfo
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.astimezone(ZoneInfo(timezone_name)).strftime("%Y-%m-%d %H:%M %Z")
    except Exception:
        return iso or "Unavailable"

def fmt(value, suffix=""):
    return "Unavailable" if value is None else f"{value}{suffix}"

def fixture_parts(f):
    teams, league = f.get("teams", {}), f.get("league", {})
    return teams.get("home", {}), teams.get("away", {}), league

def optional_api_data(api, method, fixture_id, label):
    try:
        return getattr(api, method)(fixture_id)
    except APIFootballError as exc:
        print(f"WARNING: Could not retrieve {label} for fixture {fixture_id}: {exc}")
        return []

def make_pre_report(api, fixture, cfg):
    fid = fixture["fixture"]["id"]
    home, away, league = fixture_parts(fixture)
    home_form = form_summary(api.team_recent(home["id"], cfg["analysis"]["recent_matches"]), home["id"])
    away_form = form_summary(api.team_recent(away["id"], cfg["analysis"]["recent_matches"]), away["id"])
    h2h = api.head_to_head(home["id"], away["id"], cfg["analysis"]["head_to_head_matches"])
    injuries = api.injuries(fid)
    predictions = match_probabilities(
        home_form, away_form,
        cfg["analysis"]["poisson_max_goals"],
        cfg["analysis"]["smoothing_goals"]
    )
    lines = [
        f"# Pre-match intelligence: {home.get('name')} vs {away.get('name')}",
        "",
        f"- **Competition:** {league.get('name', 'Unavailable')} ({league.get('country', 'Unavailable')})",
        f"- **Stage:** {league.get('round', 'Unavailable')}",
        f"- **Kick-off:** {kickoff_local(fixture['fixture'].get('date'), cfg['automation']['timezone'])}",
        f"- **Venue:** {fixture['fixture'].get('venue', {}).get('name') or 'Unavailable'}",
        f"- **Fixture ID:** `{fid}`",
        "",
        "## Executive overview",
        f"This report compares the latest available form and historical head-to-head data for {home.get('name')} and {away.get('name')}. Missing fields are not inferred.",
        "",
        "## Recent form",
        f"### {home.get('name')}",
        f"- Record: {home_form['wins']}W / {home_form['draws']}D / {home_form['losses']}L from {home_form['played']} available matches",
        f"- Results sequence (provider order): `{home_form['sequence']}`",
        f"- Average goals for / against: {fmt(round(home_form['goals_for'], 2) if home_form['goals_for'] is not None else None)} / {fmt(round(home_form['goals_against'], 2) if home_form['goals_against'] is not None else None)}",
        "",
        f"### {away.get('name')}",
        f"- Record: {away_form['wins']}W / {away_form['draws']}D / {away_form['losses']}L from {away_form['played']} available matches",
        f"- Results sequence (provider order): `{away_form['sequence']}`",
        f"- Average goals for / against: {fmt(round(away_form['goals_for'], 2) if away_form['goals_for'] is not None else None)} / {fmt(round(away_form['goals_against'], 2) if away_form['goals_against'] is not None else None)}",
        "",
        "## Head-to-head",
        f"- Available meetings: **{len(h2h)}**",
    ]
    for item in h2h[:cfg["analysis"]["head_to_head_matches"]]:
        ht, at = fixture_parts(item)[:2]
        goals = item.get("goals", {})
        date = item.get("fixture", {}).get("date", "date unavailable")
        lines.append(f"- {date[:10]} — {ht.get('name')} {goals.get('home', '?')}–{goals.get('away', '?')} {at.get('name')}")
    lines += ["", "## Availability", f"- Injury/suspension records returned by provider: **{len(injuries)}**"]
    if injuries:
        for item in injuries[:30]:
            player = item.get("player", {}).get("name", "Unknown player")
            team = item.get("team", {}).get("name", "Unknown team")
            reason = item.get("player", {}).get("type") or item.get("player", {}).get("reason") or "Reason unavailable"
            lines.append(f"- {player} ({team}) — {reason}")
    else:
        lines.append("- No records returned. This does **not** confirm that both squads are fully available.")
    lines += ["", "## Model outlook"]
    if predictions:
        lines += [
            "> Exploratory estimate from recent goals using independent Poisson scoring rates. Not betting odds, not a guarantee, and not a full-strength predictive model.",
            f"- Estimated goals: **{predictions['home_lambda']:.2f} – {predictions['away_lambda']:.2f}**",
            f"- Home win: **{pct(predictions['home_win'])}**",
            f"- Draw: **{pct(predictions['draw'])}**",
            f"- Away win: **{pct(predictions['away_win'])}**",
        ]
    else:
        lines.append("Insufficient recent scoring data to calculate a responsible 1X2 estimate.")
    lines += [
        "",
        "## Tactical questions to monitor",
        "- Which side controls territory and second balls?",
        "- Can the away side progress through the first press?",
        "- Do either team's recent scoring/conceding patterns translate into high-quality chances?",
        "",
        "## Data quality and limitations",
        "- Recent form is calculated from the last available finished fixtures returned by the provider.",
        "- Provider injury coverage may be incomplete.",
        "- Confirmed starting lineups may not yet be published.",
        "- Expected-goal figures above are modelled goal rates, **not** official xG.",
        "",
        f"_Generated automatically at {datetime.now(timezone.utc).isoformat()}._",
    ]
    return "\n".join(lines), predictions


def make_post_report(api, fixture, cfg, pre_predictions=None):
    fid = fixture["fixture"]["id"]
    home, away, league = fixture_parts(fixture)
    goals = fixture.get("goals", {})
    status = fixture.get("fixture", {}).get("status", {})

    # These data sources are optional: one failure must not stop the report.
    events = optional_api_data(api, "events", fid, "events")
    stats = optional_api_data(api, "statistics", fid, "statistics")
    lineups = optional_api_data(api, "lineups", fid, "lineups")

    lines = [
        f"# Post-match report: {home.get('name')} vs {away.get('name')}",
        "",
        f"- **Competition:** {league.get('name', 'Unavailable')}",
        f"- **Date:** {fixture.get('fixture', {}).get('date', 'Unavailable')}",
        f"- **Final score:** **{home.get('name')} {goals.get('home', '?')}–{goals.get('away', '?')} {away.get('name')}**",
        f"- **Status:** {status.get('long', status.get('short', 'Unavailable'))}",
        f"- **Venue:** {fixture.get('fixture', {}).get('venue', {}).get('name') or 'Unavailable'}",
        "",
        "## Match narrative",
    ]

    if events:
        for e in events:
            elapsed = e.get("time", {}).get("elapsed", "?")
            extra = e.get("time", {}).get("extra")
            minute = f"{elapsed}+{extra}" if extra else str(elapsed)
            team = e.get("team", {}).get("name", "Unknown team")
            player = e.get("player", {}).get("name", "Unknown player")
            detail = e.get("detail") or e.get("type") or "Event"
            assist = e.get("assist", {}).get("name")
            suffix = f" (assist: {assist})" if assist else ""
            lines.append(
                f"- **{minute}'** — {team}: {detail}; {player}{suffix}"
            )
    else:
        lines.append("No event timeline was returned by the provider.")

    lines += ["", "## Team statistics"]

    if stats:
        for team_stats in stats:
            team_name = team_stats.get("team", {}).get("name", "Unknown team")
            lines.append(f"### {team_name}")

            for stat in team_stats.get("statistics", []):
                lines.append(
                    f"- {stat.get('type', 'Statistic')}: "
                    f"{stat.get('value', 'Unavailable')}"
                )
    else:
        lines.append("No team statistics were returned.")

    lines += ["", "## Starting lineups"]

    if lineups:
        for lineup in lineups:
            team_name = lineup.get("team", {}).get("name", "Unknown team")
            formation = lineup.get("formation") or "Formation unavailable"
            lines.append(f"### {team_name} — {formation}")

            starters = lineup.get("startXI", [])
            names = [
                x.get("player", {}).get("name", "Unknown")
                for x in starters
            ]

            lines.append(
                ", ".join(names) if names else "Starting XI unavailable."
            )
    else:
        lines.append(
            "Lineup information is unavailable. "
            "The report was generated without it."
        )

    lines += ["", "## Prediction review"]

    if pre_predictions:
        home_goals = goals.get("home") or 0
        away_goals = goals.get("away") or 0

        actual = (
            "home win" if home_goals > away_goals
            else "away win" if home_goals < away_goals
            else "draw"
        )

        probability_keys = {
            "home win": "home_win",
            "draw": "draw",
            "away win": "away_win",
        }

        chosen = max(
            probability_keys,
            key=lambda k: pre_predictions[probability_keys[k]]
        )

        lines += [
            f"- Highest pre-match probability: **{chosen}**",
            f"- Actual outcome: **{actual}**",
            f"- Top outcome prediction: **{'Correct' if chosen == actual else 'Incorrect'}**",
            f"- Pre-match probabilities: home {pct(pre_predictions['home_win'])}, draw {pct(pre_predictions['draw'])}, away {pct(pre_predictions['away_win'])}",
            "- A single match is not enough to assess model quality; evaluate calibration over a large sample.",
        ]
    else:
        lines.append(
            "No saved pre-match probability was available for this run."
        )

    lines += [
        "",
        "## Performance notes",
        "- Player ratings and official xG are not synthesized when the provider does not return them.",
        "- Interpret possession and shot volume in context; they do not alone establish performance superiority.",
        "- Some information may be missing because of API availability or plan restrictions.",
        "",
        f"_Generated automatically at {datetime.now(timezone.utc).isoformat()}._",
    ]

    return "\n".join(lines)
