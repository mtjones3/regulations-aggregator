import argparse
import os
import sys
import requests
import json
import sqlite3
from datetime import datetime, timedelta

# Configuration via environment variables
FEDERAL_API_KEY = os.environ.get('REGULATIONS_GOV_API_KEY', '')
STATE_API_KEY = os.environ.get('NYS_LEGISLATURE_API_KEY', '')
DB_FILE = os.environ.get('REGULATIONS_DB_FILE', 'regulations.db')

# Food & beverage industry filter
FEDERAL_SEARCH_TERM = 'food OR beverage OR dairy OR meat OR poultry OR seafood OR alcohol'
STATE_KEYWORDS = ['food', 'beverage', 'dairy', 'meat', 'poultry', 'seafood',
                  'alcohol', 'restaurant', 'nutrition', 'drink']


def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS regulations (
            id TEXT PRIMARY KEY,
            level TEXT,  -- federal, state
            title TEXT,
            description TEXT,
            published_date TEXT,
            full_text TEXT,
            source_url TEXT,
            source_last_modified TEXT,
            last_updated TEXT
        )
    ''')
    conn.commit()
    conn.close()


def store_records(level, records, source_url):
    """Store normalized records into the database.

    Each record should be a dict with keys:
        id, title, description, published_date, full_text, source_last_modified
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    now = datetime.now().isoformat()

    for rec in records:
        doc_id = rec.get('id')
        if not doc_id:
            continue

        source_mod = rec.get('source_last_modified', '')

        # Skip if we already have this record and the source hasn't changed
        cursor.execute(
            'SELECT source_last_modified FROM regulations WHERE id = ?',
            (doc_id,)
        )
        existing = cursor.fetchone()
        if existing and existing[0] and source_mod and existing[0] >= source_mod:
            print(f"Skipping {doc_id} (no update at source).")
            continue

        cursor.execute('''
            INSERT OR REPLACE INTO regulations
                (id, level, title, description, published_date,
                 full_text, source_url, source_last_modified, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            doc_id,
            level,
            rec.get('title', ''),
            rec.get('description', ''),
            rec.get('published_date', ''),
            rec.get('full_text', ''),
            source_url,
            source_mod,
            now,
        ))
        print(f"Stored/Updated: {rec.get('title', doc_id)} ({level})")

    conn.commit()
    conn.close()


# -- Federal: Regulations.gov API (JSON:API format) --------------------------

def normalize_federal(data):
    """Normalize JSON:API items from Regulations.gov v4."""
    records = []
    for item in data:
        attrs = item.get('attributes', {})
        records.append({
            'id': attrs.get('documentId') or item.get('id', ''),
            'title': attrs.get('title', ''),
            'description': attrs.get('summary', '') or attrs.get('abstract', ''),
            'published_date': attrs.get('postedDate', ''),
            'full_text': json.dumps(attrs),
            'source_last_modified': attrs.get('lastModifiedDate', '')
                                    or attrs.get('postedDate', ''),
        })
    return records


def fetch_federal_updates(days_back=7, page_size=10):
    if not FEDERAL_API_KEY:
        print("Skipping federal: REGULATIONS_GOV_API_KEY not set.")
        return
    base_url = 'https://api.regulations.gov/v4/documents'
    from_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
    params = {
        'filter[searchTerm]': FEDERAL_SEARCH_TERM,
        'filter[postedDate][ge]': from_date,
        'sort': '-postedDate',
        'page[size]': page_size,
        'api_key': FEDERAL_API_KEY,
    }
    try:
        response = requests.get(base_url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json().get('data', [])
        records = normalize_federal(data)
        store_records('federal', records, base_url)
    except requests.RequestException as e:
        print(f"Federal fetch failed: {e}")


# -- State: NYS Open Legislation API ----------------------------------------

def normalize_state(items):
    """Normalize items from the NYS Open Legislation updates API."""
    records = []
    for item in items:
        item_id = item.get('id', {})
        if isinstance(item_id, dict):
            law_id = item_id.get('lawId', '')
            active_date = item_id.get('activeDate', '')
        else:
            law_id = str(item_id)
            active_date = ''
        content_type = item.get('contentType', '')
        doc_id = f"nys-{law_id}-{active_date}"
        records.append({
            'id': doc_id,
            'title': f"{content_type} {law_id}".strip(),
            'description': item.get('sourceId', ''),
            'published_date': active_date,
            'full_text': json.dumps(item),
            'source_last_modified': item.get('sourceDateTime', '') or active_date,
        })
    return records


def fetch_state_updates(days_back=7, page_size=10):
    if not STATE_API_KEY:
        print("Skipping state: NYS_LEGISLATURE_API_KEY not set.")
        return
    from_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
    to_date = datetime.now().strftime('%Y-%m-%d')
    base_url = (
        f'https://legislation.nysenate.gov/api/3/laws/updates'
        f'/{from_date}/{to_date}?limit={page_size}&key={STATE_API_KEY}'
    )
    try:
        response = requests.get(base_url, timeout=30)
        response.raise_for_status()
        data = response.json().get('result', {}).get('items', [])
        records = normalize_state(data)
        records = [r for r in records if any(
            kw in (r.get('title', '') + ' ' + r.get('description', '') +
                   ' ' + r.get('full_text', '')).lower()
            for kw in STATE_KEYWORDS
        )]
        store_records('state', records, base_url)
    except requests.RequestException as e:
        print(f"State fetch failed: {e}")


# -- Main --------------------------------------------------------------------

VALID_SOURCES = ['federal', 'state']

FETCH_FUNCTIONS = {
    'federal': fetch_federal_updates,
    'state': fetch_state_updates,
}


def aggregate_updates(sources=None, days_back=7, page_size=10):
    sources = sources or VALID_SOURCES
    init_db()
    for source in sources:
        print(f"Fetching {source} updates...")
        FETCH_FUNCTIONS[source](days_back=days_back, page_size=page_size)
    print(f"Aggregation complete. Data stored in {DB_FILE}")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Fetch regulatory updates from federal and state APIs."
    )
    parser.add_argument(
        '--days-back', type=int, default=7,
        help="Number of days to look back (default: 7)"
    )
    parser.add_argument(
        '--page-size', type=int, default=10,
        help="Max results per source (default: 10)"
    )
    parser.add_argument(
        '--sources', nargs='+', choices=VALID_SOURCES, default=None,
        help="Sources to fetch (default: all configured)"
    )
    parser.add_argument(
        '--db-file', default=None,
        help="Path to SQLite database (overrides REGULATIONS_DB_FILE)"
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = parse_args()

    if args.db_file:
        DB_FILE = args.db_file

    if not any([FEDERAL_API_KEY, STATE_API_KEY]):
        print("No API keys configured. Set one or more environment variables:")
        print("  REGULATIONS_GOV_API_KEY  - https://api.data.gov/signup/")
        print("  NYS_LEGISLATURE_API_KEY  - https://legislation.nysenate.gov/")
        sys.exit(1)

    aggregate_updates(
        sources=args.sources,
        days_back=args.days_back,
        page_size=args.page_size,
    )
