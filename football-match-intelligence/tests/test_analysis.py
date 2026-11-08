from src.analysis import form_summary, match_probabilities

def fixture(home_id, away_id, hg, ag):
    return {
        "teams": {"home": {"id": home_id}, "away": {"id": away_id}},
        "goals": {"home": hg, "away": ag}
    }

def test_form_summary_counts_results():
    rows = [fixture(1, 2, 2, 0), fixture(3, 1, 1, 1), fixture(1, 4, 0, 2)]
    result = form_summary(rows, 1)
    assert result["played"] == 3
    assert (result["wins"], result["draws"], result["losses"]) == (1, 1, 1)

def test_probabilities_sum_to_one():
    home = {"goals_for": 1.8, "goals_against": 0.8}
    away = {"goals_for": 1.2, "goals_against": 1.1}
    result = match_probabilities(home, away)
    assert result is not None
    assert abs(result["home_win"] + result["draw"] + result["away_win"] - 1) < 1e-9
