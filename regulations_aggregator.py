import os
import sys
import requests
import json
import sqlite3
from datetime import datetime, timedelta

# Configuration via environment variables
FEDERAL_API_KEY = os.environ.get('REGULATIONS_GOV_API_KEY', '')
STATE_API_KEY = os.environ.get('NYS_LEGISLATURE_API_KEY', '')
LOCAL_API_TOKEN = os.environ.get('LEGISTAR_API_TOKEN', '')
DB_FILE = os.environ.get('REGULATIONS_DB_FILE', 'regulations.db')


def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS regulations (
            id TEXT PRIMARY KEY,
            level TEXT,  -- federal, state, local
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
            'id': item.get('id', ''),
            'title': attrs.get('title', ''),
            'description': attrs.get('summary', '') or attrs.get('abstract', ''),
            'published_date': attrs.get('postedDate', ''),
            'full_text': json.dumps(attrs),
            'source_last_modified': attrs.get('lastModifiedDate', '')
                                    or attrs.get('postedDate', ''),
        })
    return records


def fetch_federal_updates(days_back=7):
    if not FEDERAL_API_KEY:
        print("Skipping federal: REGULATIONS_GOV_API_KEY not set.")
        return
    base_url = 'https://api.regulations.gov/v4/documents'
    from_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
    params = {
        'filter[postedDate][ge]': from_date,
        'sort': '-postedDate',
        'page[size]': 10,
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
        result = item.get('result', item)
        law_id = result.get('lawId', '') or item.get('id', '')
        doc_id = f"nys-{law_id}-{result.get('activeDate', '')}"
        records.append({
            'id': doc_id,
            'title': result.get('docType', '') + ' ' + law_id,
            'description': result.get('docLevelId', ''),
            'published_date': result.get('activeDate', ''),
            'full_text': json.dumps(result),
            'source_last_modified': item.get('sourceDateTime', '')
                                    or result.get('activeDate', ''),
        })
    return records


def fetch_state_updates(days_back=7):
    if not STATE_API_KEY:
        print("Skipping state: NYS_LEGISLATURE_API_KEY not set.")
        return
    from_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
    to_date = datetime.now().strftime('%Y-%m-%d')
    base_url = (
        f'https://legislation.nysenate.gov/api/3/laws/updates'
        f'/{from_date}/{to_date}?limit=10&key={STATE_API_KEY}'
    )
    try:
        response = requests.get(base_url, timeout=30)
        response.raise_for_status()
        data = response.json().get('result', {}).get('items', [])
        records = normalize_state(data)
        store_records('state', records, base_url)
    except requests.RequestException as e:
        print(f"State fetch failed: {e}")


# -- Local: NYC Legistar API -------------------------------------------------

def normalize_local(items):
    """Normalize items from the NYC Legistar Matters API."""
    records = []
    for item in items:
        matter_id = str(item.get('MatterId', ''))
        records.append({
            'id': f"nyc-{matter_id}",
            'title': item.get('MatterTitle', '') or item.get('MatterName', ''),
            'description': item.get('MatterBodyName', ''),
            'published_date': item.get('MatterIntroDate', ''),
            'full_text': json.dumps(item),
            'source_last_modified': item.get('MatterLastModifiedUtc', ''),
        })
    return records


def fetch_local_updates(days_back=7):
    if not LOCAL_API_TOKEN:
        print("Skipping local: LEGISTAR_API_TOKEN not set.")
        return
    client = 'nyc'
    from_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%dT%H:%M:%S')
    base_url = f'https://webapi.legistar.com/v1/{client}/Matters'
    params = {
        '$filter': f"MatterLastModifiedUtc gt datetime'{from_date}'",
        '$orderby': 'MatterLastModifiedUtc desc',
        '$top': 10,
        'token': LOCAL_API_TOKEN,
    }
    try:
        response = requests.get(base_url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        records = normalize_local(data)
        store_records('local', records, base_url)
    except requests.RequestException as e:
        print(f"Local fetch failed: {e}")


# -- Main --------------------------------------------------------------------

def aggregate_updates():
    init_db()
    print("Fetching federal updates...")
    fetch_federal_updates()
    print("Fetching state (NY) updates...")
    fetch_state_updates()
    print("Fetching local (NYC) updates...")
    fetch_local_updates()
    print("Aggregation complete. Data stored in regulations.db")


if __name__ == "__main__":
    if not any([FEDERAL_API_KEY, STATE_API_KEY, LOCAL_API_TOKEN]):
        print("No API keys configured. Set one or more environment variables:")
        print("  REGULATIONS_GOV_API_KEY  - https://api.data.gov/signup/")
        print("  NYS_LEGISLATURE_API_KEY  - https://legislation.nysenate.gov/")
        print("  LEGISTAR_API_TOKEN       - https://www.legistar.com/")
        print("  REGULATIONS_DB_FILE      - (optional) path to SQLite DB")
        sys.exit(1)
    aggregate_updates()
