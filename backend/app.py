
from flask import Flask, request, jsonify
from flask_cors import CORS
from contextlib import contextmanager
import sqlite3, re, uuid
from datetime import datetime, timezone
from pathlib import Path

app = Flask(__name__)
CORS(app)

DB_PATH = Path(__file__).with_name('hospital.db')

VALID_RE = re.compile(
    r'^WARD[A-Z]{2}[0-9]{2}-ALERT\[(CRITICAL|URGENT|ROUTINE|SUPPLY|MAINTENANCE)\]$'
)

CATEGORIES = {
    'CRITICAL', 'URGENT', 'ROUTINE', 'SUPPLY', 'MAINTENANCE'
}

# Deterministic routing table: category -> department, zone, priority
ROUTES = {
    'CRITICAL': {'department': 'Nursing Supervisor', 'zone': 'Emergency', 'priority': 1},
    'URGENT': {'department': 'Nursing Supervisor', 'zone': 'Ward Operations', 'priority': 2},
    'ROUTINE': {'department': 'Nursing Supervisor', 'zone': 'Ward Operations', 'priority': 4},
    'SUPPLY': {'department': 'Pharmacy', 'zone': 'Stores', 'priority': 3},
    'MAINTENANCE': {'department': 'Maintenance', 'zone': 'Engineering', 'priority': 3},
}

HANDLERS = {
    'Nursing Supervisor': ['Nurse Supervisor A', 'Nurse Supervisor B'],
    'Pharmacy': ['Pharmacist A', 'Pharmacist B'],
    'Maintenance': ['Maintenance Team A', 'Maintenance Team B'],
    'Biomedical Engineering': ['Biomedical Team A', 'Biomedical Team B'],
}


# Database connection management
@contextmanager
def connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row

    try:
        yield con
        con.commit()

    except Exception:
        con.rollback()
        raise

    finally:
        con.close()


# Initialize database and tables
def init_db():
    with connect() as con:

        con.execute('''CREATE TABLE IF NOT EXISTS reports (
            id TEXT PRIMARY KEY,
            reporter TEXT NOT NULL,
            ward TEXT NOT NULL,
            identifier TEXT NOT NULL,
            category TEXT,
            description TEXT NOT NULL,
            urgency TEXT NOT NULL,
            department TEXT,
            zone TEXT,
            priority INTEGER,
            handler TEXT,
            status TEXT NOT NULL,
            validation TEXT NOT NULL,
            validation_message TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )''')

        con.execute('''CREATE TABLE IF NOT EXISTS handlers (
            name TEXT PRIMARY KEY,
            department TEXT NOT NULL,
            available INTEGER NOT NULL DEFAULT 1,
            capacity INTEGER NOT NULL DEFAULT 5
        )''')

        for dept, names in HANDLERS.items():
            for name in names:
                con.execute(
                    'INSERT OR IGNORE INTO handlers(name,department,available,capacity) VALUES(?,?,1,5)',
                    (name, dept)
                )


# DFA-based identifier validation
def dfa_validate(identifier):
    fixed = "WARD"

    if not isinstance(identifier, str) or len(identifier) < len(fixed):
        return False

    state = 0

    # q0-q4: exact WARD prefix
    for char in identifier[:4]:
        if char != fixed[state]:
            return False
        state += 1

    # q4-q6: exactly two uppercase letters
    if len(identifier) < 8 or not all(
        c.isascii() and c.isupper() for c in identifier[4:6]
    ):
        return False

    # q6-q8: exactly two digits
    if not all(
        c.isdigit() and c.isascii() for c in identifier[6:8]
    ):
        return False

    # Check remaining suffix and category
    return bool(VALID_RE.fullmatch(identifier))


# Validate identifier
def validate(identifier):
    if not identifier:
        return False, 'Identifier is required.'

    if not dfa_validate(identifier):
        return False, (
            'Invalid identifier. Expected WARD + 2 uppercase letters '
            '+ 2 digits + -ALERT[CATEGORY].'
        )

    return True, 'Identifier accepted.'


# Classify report
def classify(identifier, urgency):
    category = identifier.rsplit('[', 1)[1][:-1]

    if category not in CATEGORIES:
        return None

    return category


# Dispatch report to an available handler
def dispatch(report_id, category, urgency):
    route = ROUTES[category].copy()

    # Critical urgency overrides normal routing
    if urgency.lower() == 'critical':
        route['priority'] = 1
        route['department'] = 'Nursing Supervisor'
        route['zone'] = 'Emergency'

    with connect() as con:

        rows = con.execute(
            'SELECT * FROM handlers WHERE department=? AND available=1 ORDER BY name',
            (route['department'],)
        ).fetchall()

        chosen = next(
            (
                r for r in rows
                if con.execute(
                    "SELECT COUNT(*) FROM reports WHERE handler=? AND status IN ('Assigned','In Progress')",
                    (r['name'],)
                ).fetchone()[0] < r['capacity']
            ),
            None
        )

        # Fallback to Nursing Supervisor
        if chosen is None:
            backups = con.execute(
                "SELECT * FROM handlers WHERE department='Nursing Supervisor' AND available=1 ORDER BY name"
            ).fetchall()

            chosen = next(
                (
                    r for r in backups
                    if con.execute(
                        "SELECT COUNT(*) FROM reports WHERE handler=? AND status IN ('Assigned','In Progress')",
                        (r['name'],)
                    ).fetchone()[0] < r['capacity']
                ),
                None
            )

        handler = chosen['name'] if chosen else None
        status = 'Assigned' if handler else 'Pending'

    return route, handler, status


# Convert database row into dictionary
def row_dict(row):
    return dict(row) if row else None


# Health check API
@app.get('/api/health')
def health():
    return jsonify({
        'status': 'ok',
        'service': 'Hospital Ward Alert Dispatcher'
    })


# Submit a new report
@app.post('/api/reports')
def create_report():
    data = request.get_json(silent=True) or {}

    reporter = str(data.get('reporter', '')).strip()
    ward = str(data.get('ward', '')).strip()
    identifier = str(data.get('identifier', '')).strip()
    description = str(data.get('description', '')).strip()
    urgency = str(data.get('urgency', 'Normal')).strip()

    if not reporter or not ward or not description:
        return jsonify({
            'error': 'Reporter, ward, and description are required.'
        }), 400

    valid, message = validate(identifier)

    now = datetime.now(timezone.utc).isoformat()
    report_id = 'HWA-' + uuid.uuid4().hex[:8].upper()

    # Store invalid reports as rejected
    if not valid:
        with connect() as con:
            con.execute(
                '''INSERT INTO reports VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (
                    report_id, reporter, ward, identifier, None,
                    description, urgency, None, None, None, None,
                    'Rejected', 'Invalid', message, now, now
                )
            )

        return jsonify({
            'report_id': report_id,
            'validation': 'Invalid',
            'message': message,
            'status': 'Rejected'
        }), 400

    category = classify(identifier, urgency)

    if category is None:
        return jsonify({
            'error': 'Unknown or unmapped category; report was not dispatched.'
        }), 400

    route, handler, status = dispatch(report_id, category, urgency)

    with connect() as con:
        con.execute(
            '''INSERT INTO reports VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (
                report_id, reporter, ward, identifier, category,
                description, urgency, route['department'],
                route['zone'], route['priority'], handler, status,
                'Valid', 'Identifier accepted.', now, now
            )
        )

        report = con.execute(
            'SELECT * FROM reports WHERE id=?',
            (report_id,)
        ).fetchone()

    return jsonify(row_dict(report)), 201


# Get all reports
@app.get('/api/reports')
def get_reports():
    with connect() as con:
        rows = con.execute(
            'SELECT * FROM reports ORDER BY priority IS NULL, priority, created_at'
        ).fetchall()

    return jsonify([row_dict(r) for r in rows])


# Search report by ID
@app.get('/api/reports/<report_id>')
def get_report(report_id):
    with connect() as con:
        row = con.execute(
            'SELECT * FROM reports WHERE id=?',
            (report_id,)
        ).fetchone()

    return (
        jsonify(row_dict(row)), 200
    ) if row else (
        jsonify({'error': 'Report ID not found.'}), 404
    )


# Update report status
@app.patch('/api/reports/<report_id>/status')
def update_status(report_id):
    data = request.get_json(silent=True) or {}
    status = data.get('status')

    if status not in {'Pending', 'Assigned', 'In Progress', 'Resolved'}:
        return jsonify({
            'error': 'Status must be Pending, Assigned, In Progress, or Resolved.'
        }), 400

    now = datetime.now(timezone.utc).isoformat()

    with connect() as con:
        cur = con.execute(
            "UPDATE reports SET status=?, updated_at=? WHERE id=? AND validation='Valid'",
            (status, now, report_id)
        )

        row = con.execute(
            'SELECT * FROM reports WHERE id=?',
            (report_id,)
        ).fetchone()

    return (
        jsonify(row_dict(row)), 200
    ) if cur.rowcount else (
        jsonify({'error': 'Valid report not found.'}), 404
    )


# Update handler availability and capacity
@app.patch('/api/handlers/<name>')
def update_handler(name):
    data = request.get_json(silent=True) or {}

    available = data.get('available')
    capacity = data.get('capacity')

    if (
        available is None
        or not isinstance(available, bool)
        or not isinstance(capacity, int)
        or isinstance(capacity, bool)
        or capacity < 1
    ):
        return jsonify({
            'error': 'Provide available as boolean and capacity as a positive integer.'
        }), 400

    with connect() as con:
        cur = con.execute(
            'UPDATE handlers SET available=?, capacity=? WHERE name=?',
            (int(available), capacity, name)
        )

    return (
        jsonify({'message': 'Handler updated.'}), 200
    ) if cur.rowcount else (
        jsonify({'error': 'Handler not found.'}), 404
    )


# Get all handlers and their current workload
@app.get('/api/handlers')
def get_handlers():
    with connect() as con:
        rows = con.execute(
            '''SELECT h.*,
            (SELECT COUNT(*) FROM reports r
            WHERE r.handler=h.name
            AND r.status IN ('Assigned','In Progress')) AS current_load
            FROM handlers h ORDER BY department,name'''
        ).fetchall()

    return jsonify([row_dict(r) for r in rows])


# Analytics dashboard API
@app.get('/api/analytics')
def analytics():
    with connect() as con:

        total = con.execute(
            'SELECT COUNT(*) FROM reports'
        ).fetchone()[0]

        statuses = {
            r['status']: r['n']
            for r in con.execute(
                'SELECT status,COUNT(*) n FROM reports GROUP BY status'
            )
        }

        categories = {
            r['category'] or 'Invalid': r['n']
            for r in con.execute(
                'SELECT category,COUNT(*) n FROM reports GROUP BY category'
            )
        }

        zones = {
            r['zone'] or 'Unassigned': r['n']
            for r in con.execute(
                'SELECT zone,COUNT(*) n FROM reports GROUP BY zone'
            )
        }

    return jsonify({
        'total': total,
        'statuses': statuses,
        'categories': categories,
        'zones': zones
    })


# Initialize database
init_db()


# Run Flask application
if __name__ == '__main__':
    app.run(debug=True, port=5000)
