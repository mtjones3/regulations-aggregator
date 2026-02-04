"""Flask web interface for the Regulations Aggregator."""

import sqlite3
from flask import Flask, request, redirect, url_for, render_template_string

from regulations_aggregator import DB_FILE, init_db, aggregate_updates

app = Flask(__name__)
init_db()

PAGE_SIZE = 25

BASE_HTML = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ title }} - Food &amp; Bev Legal Guru</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
         max-width: 960px; margin: 0 auto; padding: 1rem; color: #222; }
  h1 { margin-bottom: 0.25rem; }
  a { color: #0057b7; text-decoration: none; }
  a:hover { text-decoration: underline; }
  nav { margin-bottom: 1rem; font-size: 0.9rem; }
  nav a { margin-right: 1rem; }
  table { width: 100%; border-collapse: collapse; margin-top: 0.5rem; }
  th, td { text-align: left; padding: 0.4rem 0.6rem; border-bottom: 1px solid #ddd; }
  th { background: #f5f5f5; }
  tr:hover { background: #fafafa; }
  .badge { display: inline-block; padding: 0.15rem 0.5rem; border-radius: 3px;
           font-size: 0.8rem; color: #fff; }
  .badge-federal { background: #2b6cb0; }
  .badge-state { background: #2f855a; }
  .search-bar { margin-bottom: 1rem; }
  .search-bar input[type=text] { padding: 0.4rem; width: 250px; }
  .search-bar button { padding: 0.4rem 0.8rem; }
  .filters a, .filters span { margin-right: 0.75rem; font-size: 0.9rem; }
  .filters .active { font-weight: bold; }
  .pagination { margin-top: 1rem; }
  .pagination a, .pagination span { margin-right: 0.5rem; }
  .detail-table td:first-child { font-weight: bold; width: 160px; vertical-align: top; }
  pre { background: #f5f5f5; padding: 0.75rem; overflow-x: auto; font-size: 0.85rem;
        max-height: 400px; overflow-y: auto; }
  .btn { display: inline-block; padding: 0.4rem 1rem; background: #0057b7; color: #fff;
         border: none; border-radius: 4px; cursor: pointer; font-size: 0.9rem; }
  .btn:hover { background: #003d82; text-decoration: none; }
  .msg { padding: 0.5rem 1rem; background: #e6ffed; border: 1px solid #b7e1c1;
         border-radius: 4px; margin-bottom: 1rem; }
</style>
</head>
<body>
<h1>Food &amp; Bev Legal Guru</h1>
<nav>
  <a href="{{ url_for('index') }}">Home</a>
  <a href="{{ url_for('fetch') }}">Fetch Updates</a>
</nav>
{% block content %}{% endblock %}
</body>
</html>
"""

INDEX_HTML = (
    '{% extends "base" %}'
    "{% block content %}"
    "{% if message %}<div class='msg'>{{ message }}</div>{% endif %}"
    "<form class='search-bar' method='get' action='{{ url_for(\"index\") }}'>"
    "{% if level %}<input type='hidden' name='level' value='{{ level }}'>{% endif %}"
    "<input type='text' name='q' value='{{ q }}' placeholder='Search title or description'> "
    "<button type='submit'>Search</button>"
    "{% if q %} <a href='{{ url_for(\"index\", level=level) }}'>Clear</a>{% endif %}"
    "</form>"
    "<div class='filters'>"
    "<a class='{% if not level %}active{% endif %}' href='{{ url_for(\"index\", q=q) }}'>All</a>"
    "<a class='{% if level==\"federal\" %}active{% endif %}' href='{{ url_for(\"index\", level=\"federal\", q=q) }}'>Federal</a>"
    "<a class='{% if level==\"state\" %}active{% endif %}' href='{{ url_for(\"index\", level=\"state\", q=q) }}'>State</a>"
    "</div>"
    "<table><tr><th>Date</th><th>Level</th><th>Title</th></tr>"
    "{% for r in records %}"
    "<tr>"
    "<td>{{ r.published_date or '—' }}</td>"
    "<td><span class='badge badge-{{ r.level }}'>{{ r.level }}</span></td>"
    "<td><a href='{{ url_for(\"detail\", record_id=r.id) }}'>{{ r.title or r.id }}</a></td>"
    "</tr>"
    "{% else %}"
    "<tr><td colspan='3'>No records found.</td></tr>"
    "{% endfor %}"
    "</table>"
    "<div class='pagination'>"
    "{% if page > 1 %}<a href='{{ url_for(\"index\", page=page-1, level=level, q=q) }}'>&laquo; Previous</a>{% endif %}"
    "<span>Page {{ page }}</span>"
    "{% if has_next %}<a href='{{ url_for(\"index\", page=page+1, level=level, q=q) }}'>Next &raquo;</a>{% endif %}"
    "</div>"
    "{% endblock %}"
)

DETAIL_HTML = (
    '{% extends "base" %}'
    "{% block content %}"
    "<p><a href='{{ url_for(\"index\") }}'>&laquo; Back to list</a></p>"
    "<h2>{{ record.title or record.id }}</h2>"
    "<table class='detail-table'>"
    "<tr><td>ID</td><td>{{ record.id }}</td></tr>"
    "<tr><td>Level</td><td><span class='badge badge-{{ record.level }}'>{{ record.level }}</span></td></tr>"
    "<tr><td>Published</td><td>{{ record.published_date or '—' }}</td></tr>"
    "<tr><td>Description</td><td>{{ record.description or '—' }}</td></tr>"
    "<tr><td>Source URL</td><td>{% if record.source_url %}<a href='{{ record.source_url }}'>{{ record.source_url }}</a>{% else %}—{% endif %}</td></tr>"
    "<tr><td>Source Modified</td><td>{{ record.source_last_modified or '—' }}</td></tr>"
    "<tr><td>Last Updated</td><td>{{ record.last_updated or '—' }}</td></tr>"
    "</table>"
    "<h3>Full Text</h3>"
    "<pre>{{ record.full_text or '(none)' }}</pre>"
    "{% endblock %}"
)

FETCH_HTML = (
    '{% extends "base" %}'
    "{% block content %}"
    "<h2>Fetch Updates</h2>"
    "<p>Trigger a fresh data fetch from all configured API sources.</p>"
    "<form method='post' action='{{ url_for(\"do_fetch\") }}'>"
    "<button class='btn' type='submit'>Fetch Updates Now</button>"
    "</form>"
    "{% endblock %}"
)


def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def render(template_str, **kwargs):
    """Render a template that extends the base layout."""
    from jinja2 import DictLoader

    env = app.jinja_env.overlay(loader=DictLoader({"base": BASE_HTML}))
    tmpl = env.from_string(template_str)
    return tmpl.render(**kwargs, url_for=url_for)


@app.route("/")
def index():
    q = request.args.get("q", "").strip()
    level = request.args.get("level", "").strip()
    page = request.args.get("page", 1, type=int)
    message = request.args.get("message", "")
    if page < 1:
        page = 1

    offset = (page - 1) * PAGE_SIZE
    sql = "SELECT * FROM regulations WHERE 1=1"
    params = []

    if level in ("federal", "state"):
        sql += " AND level = ?"
        params.append(level)
    if q:
        sql += " AND (title LIKE ? OR description LIKE ?)"
        params.extend([f"%{q}%", f"%{q}%"])

    sql += " ORDER BY published_date DESC LIMIT ? OFFSET ?"
    params.extend([PAGE_SIZE + 1, offset])

    conn = get_db()
    rows = conn.execute(sql, params).fetchall()
    conn.close()

    has_next = len(rows) > PAGE_SIZE
    records = rows[:PAGE_SIZE]

    return render(
        INDEX_HTML,
        title="Home",
        records=records,
        page=page,
        has_next=has_next,
        q=q,
        level=level,
        message=message,
    )


@app.route("/record/<path:record_id>")
def detail(record_id):
    conn = get_db()
    record = conn.execute(
        "SELECT * FROM regulations WHERE id = ?", (record_id,)
    ).fetchone()
    conn.close()

    if record is None:
        return render(
            '{% extends "base" %}{% block content %}'
            "<p>Record not found.</p>"
            '<p><a href="{{ url_for(\'index\') }}">&laquo; Back to list</a></p>'
            "{% endblock %}",
            title="Not Found",
        ), 404

    return render(DETAIL_HTML, title=record["title"] or record["id"], record=record)


@app.route("/fetch")
def fetch():
    return render(FETCH_HTML, title="Fetch Updates")


@app.route("/fetch", methods=["POST"])
def do_fetch():
    aggregate_updates()
    return redirect(url_for("index", message="Fetch complete."))


if __name__ == "__main__":
    app.run(debug=True)
