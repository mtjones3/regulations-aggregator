# Regulations Aggregator

Fetches recent regulatory updates from federal, state, and local government APIs and stores them in a local SQLite database.

## Data Sources

| Level | Source | API |
|-------|--------|-----|
| Federal | Regulations.gov | [v4 Documents API](https://api.regulations.gov) |
| State | NYS Open Legislation | [Laws Updates API](https://legislation.nysenate.gov) |
| Local | NYC Legistar | [Matters API](https://webapi.legistar.com) |

## Setup

Install dependencies:

```
pip install requests
```

Set one or more API key environment variables:

```
export REGULATIONS_GOV_API_KEY=your_key    # https://api.data.gov/signup/
export NYS_LEGISLATURE_API_KEY=your_key    # https://legislation.nysenate.gov/
export LEGISTAR_API_TOKEN=your_token       # https://www.legistar.com/
```

Optionally set a custom database path (defaults to `regulations.db`):

```
export REGULATIONS_DB_FILE=/path/to/database.db
```

## Usage

```
python regulations_aggregator.py
```

The script fetches documents from the last 7 days for each configured source and stores them in a local SQLite database. Sources without a configured API key are skipped.

## Database Schema

Records are stored in a single `regulations` table:

| Column | Description |
|--------|-------------|
| `id` | Unique document identifier |
| `level` | `federal`, `state`, or `local` |
| `title` | Document title |
| `description` | Summary or abstract |
| `published_date` | Original publication date |
| `full_text` | Full text or raw JSON payload |
| `source_url` | API endpoint used |
| `source_last_modified` | Last modification date from the source |
| `last_updated` | When the record was last written locally |
