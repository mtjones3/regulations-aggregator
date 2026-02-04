# Regulations Aggregator

Fetches recent regulatory updates from federal and state government APIs and stores them in a local SQLite database.

## Data Sources

| Level | Source | API |
|-------|--------|-----|
| Federal | Regulations.gov | [v4 Documents API](https://api.regulations.gov) |
| State | NYS Open Legislation | [Laws Updates API](https://legislation.nysenate.gov) |

## Setup

Install dependencies:

```
pip install requests
```

Set one or more API key environment variables:

```
export REGULATIONS_GOV_API_KEY=your_key    # https://api.data.gov/signup/
export NYS_LEGISLATURE_API_KEY=your_key    # https://legislation.nysenate.gov/
```

Optionally set a custom database path (defaults to `regulations.db`):

```
export REGULATIONS_DB_FILE=/path/to/database.db
```

## Usage

```
python regulations_aggregator.py [options]
```

### Options

| Flag | Description | Default |
|------|-------------|---------|
| `--days-back N` | Number of days to look back | 7 |
| `--page-size N` | Max results per source | 10 |
| `--sources federal state` | Which sources to fetch | all configured |
| `--db-file PATH` | Path to SQLite database | `regulations.db` |

### Examples

```
# Fetch from all sources, last 7 days
python regulations_aggregator.py

# Fetch only federal, last 30 days, 20 results
python regulations_aggregator.py --sources federal --days-back 30 --page-size 20

# Fetch state only, save to custom DB
python regulations_aggregator.py --sources state --db-file /path/to/my.db
```

## Database Schema

Records are stored in a single `regulations` table:

| Column | Description |
|--------|-------------|
| `id` | Unique document identifier |
| `level` | `federal` or `state` |
| `title` | Document title |
| `description` | Summary or abstract |
| `published_date` | Original publication date |
| `full_text` | Full text or raw JSON payload |
| `source_url` | API endpoint used |
| `source_last_modified` | Last modification date from the source |
| `last_updated` | When the record was last written locally |
