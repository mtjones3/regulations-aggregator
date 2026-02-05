# Food & Bev Legal Guru — Regulations Aggregator

## What this project does
A Flask web app that aggregates food & beverage regulatory updates from federal (Regulations.gov) and state (NYS Open Legislation) APIs, stores them in SQLite, and uses Claude AI to generate plain-language "Monday Morning Briefs" for business owners.

## Tech stack
- **Python 3.13** on Windows
- **Flask** — web framework, templates are inline Jinja2 strings (no template files)
- **SQLite** — single-file DB (`regulations.db`), two tables: `regulations` and `briefs`
- **Anthropic SDK** — Claude 3.5 Haiku for brief generation
- **Requests** — external API calls

## Project structure
```
regulations_aggregator.py   # Core logic: DB init, API fetchers, AI brief generation
app.py                      # Flask routes and inline HTML templates
test_regulations_aggregator.py  # pytest suite (19 tests)
requirements.txt            # Python dependencies
static/nighthawks.jpg       # Banner image
regulations.db              # SQLite DB (gitignored, created at runtime)
```

## Environment variables
| Variable | Purpose |
|---|---|
| `REGULATIONS_GOV_API_KEY` | Federal Regulations.gov API |
| `NYS_LEGISLATURE_API_KEY` | NYS Open Legislation API |
| `ANTHROPIC_API_KEY` | Claude AI for brief generation |
| `REGULATIONS_DB_FILE` | Override default DB path (optional) |

## How to run
```bash
pip install -r requirements.txt
python app.py                # Start Flask dev server on http://127.0.0.1:5000
```

## How to run tests
```bash
python -m pytest test_regulations_aggregator.py -v
```
Tests use a temp DB via monkeypatch — no real API calls or DB side effects.

## Key routes
- `/` — Paginated regulation list with search and level filters
- `/fetch` — Trigger API data fetch
- `/brief` — Monday Morning Brief (last 14 days, AI-analyzed)
- `/brief/generate` — POST to generate briefs for un-analyzed regulations
- `/record/<id>` — Detail view for a single regulation

## Design notes
- Templates are inline Python strings using Jinja2 `extends` with a `DictLoader`, not separate `.html` files
- Visual theme: warm "Nighthawks" palette (browns, creams, navy) with Playfair Display font
- Brief generation uses `claude-3-5-haiku-latest` to keep costs low
- Briefs are cached in the `briefs` table — only regulations without a brief get analyzed
- The Monday Brief defaults to a 14-day lookback window
