from math import exp, factorial

def _goals_for(row, team_id):
    teams = row.get("teams", {})
    goals = row.get("goals", {})
    if teams.get("home", {}).get("id") == team_id:
        return goals.get("home")
    if teams.get("away", {}).get("id") == team_id:
        return goals.get("away")
    return None

def _goals_against(row, team_id):
    teams = row.get("teams", {})
    goals = row.get("goals", {})
    if teams.get("home", {}).get("id") == team_id:
        return goals.get("away")
    if teams.get("away", {}).get("id") == team_id:
        return goals.get("home")
    return None

def form_summary(fixtures, team_id):
    played = []
    for f in fixtures:
        gf, ga = _goals_for(f, team_id), _goals_against(f, team_id)
        if isinstance(gf, int) and isinstance(ga, int):
            played.append((gf, ga))
    if not played:
        return {"played": 0, "wins": 0, "draws": 0, "losses": 0,
                "goals_for": None, "goals_against": None, "sequence": "N/A"}
    wins = sum(gf > ga for gf, ga in played)
    draws = sum(gf == ga for gf, ga in played)
    losses = len(played) - wins - draws
    sequence = "".join("W" if gf > ga else "D" if gf == ga else "L" for gf, ga in played)
    return {
        "played": len(played), "wins": wins, "draws": draws, "losses": losses,
        "goals_for": sum(x[0] for x in played) / len(played),
        "goals_against": sum(x[1] for x in played) / len(played),
        "sequence": sequence
    }

def poisson_probability(k, lam):
    return exp(-lam) * (lam ** k) / factorial(k)

def match_probabilities(home_form, away_form, max_goals=10, smoothing=0.15):
    # Estimate scoring rates from each side's recent goals for/against.
    # Home advantage is a modest transparent multiplier, not a fitted league model.
    h_for = home_form.get("goals_for")
    h_against = home_form.get("goals_against")
    a_for = away_form.get("goals_for")
    a_against = away_form.get("goals_against")
    if None in (h_for, h_against, a_for, a_against):
        return None
    home_lambda = max(0.15, ((h_for + a_against) / 2 + smoothing) * 1.08)
    away_lambda = max(0.15, (a_for + h_against) / 2 + smoothing)
    home_win = draw = away_win = 0.0
    for hg in range(max_goals + 1):
        ph = poisson_probability(hg, home_lambda)
        for ag in range(max_goals + 1):
            p = ph * poisson_probability(ag, away_lambda)
            if hg > ag:
                home_win += p
            elif hg == ag:
                draw += p
            else:
                away_win += p
    total = home_win + draw + away_win
    return {
        "home_lambda": home_lambda, "away_lambda": away_lambda,
        "home_win": home_win / total, "draw": draw / total,
        "away_win": away_win / total
    }

def pct(value):
    return f"{value * 100:.1f}%"
