# Football Match Intelligence

Automated, English-language football pre-match and post-match intelligence reports, published as Markdown files in your GitHub repository.

## What it does

- Discovers fixtures across competitions available to your API-Football subscription.
- Creates pre-match reports for fixtures kicking off within a configurable window.
- Creates post-match reports after fixtures finish.
- Collects recent form, head-to-head history, injuries, lineups, events, and match statistics where the API makes them available.
- Estimates 1X2 probabilities using a transparent Poisson model based on recent goals. These are model estimates, not betting advice or guarantees.
- Stores reports under `reports/YYYY/MM/DD/`.
- Runs on GitHub Actions and commits new reports to the repository.

> Coverage note: "All competitions" means all competitions returned by the configured data provider and enabled by your subscription. API coverage, historical depth, injuries, lineups, and live statistics vary by competition and plan.

## 1. Get an API-Football key

Create an account with [API-Football](https://www.api-football.com/) and obtain an API key. Check the plan's request quota and competition coverage before enabling broad global coverage.

## 2. Add GitHub Actions secrets

In your repository, open **Settings → Secrets and variables → Actions → New repository secret**.

Required:
- `APISPORTS_KEY`: your API-Football key.

Optional:
- `OPENAI_API_KEY`: reserved for a future LLM narrative enhancement. The current release works without it.
- `OPENAI_MODEL`: optional model name if you later enable LLM enhancement.

Never put API keys in source files or commit them.

## 3. Install locally

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Put APISPORTS_KEY in .env
python -m src.main --mode both --days-ahead 2
```

## 4. Run on GitHub

1. Create a GitHub repository named `football-match-intelligence`.
2. Upload/push this project.
3. Add `APISPORTS_KEY` as a repository secret.
4. Open **Actions** and enable workflows if GitHub asks.
5. Run **Football reports** manually using **Run workflow** for a first test.

The scheduled workflow runs every 30 minutes. GitHub scheduled workflows can be delayed during high load and are not a real-time guarantee. A report is generated on the next successful run after a match enters its reporting window.

## Configuration

Edit `config.yaml`:

- `pre_match_hours`: create a preview within this many hours before kickoff.
- `post_match_delay_minutes`: wait after the final whistle before creating the post-match report.
- `lookback_days`: how far back to search for finished fixtures.
- `days_ahead`: how far ahead to discover upcoming fixtures.
- `competitions`: leave empty to include all competitions exposed by the provider; optionally restrict by league IDs.
- `timezone`: timezone used for display in reports.

## Report lifecycle

The workflow is idempotent: an existing report for the same fixture and report type is not overwritten unless `FORCE_REPORTS=true` is set.

```text
reports/
  2026/11/08/
    123456-psg-v-inter-pre-match.md
    123456-psg-v-inter-post-match.md
```

## Data and model limitations

- Missing provider fields are labelled as unavailable rather than invented.
- Probabilities are computed from recent goals with a small smoothing prior. They are not official bookmaker odds and do not include every contextual factor.
- Expected goals in this release are goal-rate estimates, not provider xG.
- Confirmed lineups usually become available close to kickoff, not days before.
- Injury and suspension coverage depends on provider availability and competition.
- The post-match report uses final fixture status plus available events/statistics. If the provider has not finalized a match, it will wait for a later run.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

## License

MIT. Review the football data provider's terms before redistributing data.
