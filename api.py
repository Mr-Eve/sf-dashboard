from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import sqlite3
from datetime import datetime, timedelta
import os

app = Flask(__name__)
CORS(app)

def ensure_schema(db: sqlite3.Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            date_display TEXT NOT NULL,
            event_date TEXT NOT NULL,
            time TEXT
        )
    ''')
    db.commit()

@app.route('/')
def index():
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), 'dashboard.html')

@app.route('/events')
def get_events():
    db = sqlite3.connect('events.db')
    ensure_schema(db)
    
    # Delete events that have passed
    db.execute('DELETE FROM events WHERE event_date < date("now")')
    db.commit()
    
    # Return each event once, ordered
    cur = db.execute('''
        SELECT id, title, date_display, event_date, time 
        FROM events 
        WHERE event_date >= date('now') 
        ORDER BY event_date, time
    ''')
    events = []
    for row in cur:
        events.append({
            'id': row[0],
            'title': row[1],
            'date': row[2]
        })
    db.close()
    return jsonify(events)

@app.route('/add-event', methods=['POST'])
def add_event():
    try:
        data = request.get_json(silent=True, force=False) or {}
        db = sqlite3.connect('events.db')
        ensure_schema(db)

        title = (data.get('title') or '').strip()
        date_display = (data.get('date') or data.get('date_display') or '').strip()
        event_date = (data.get('event_date') or '').strip()
        time_str = (data.get('time') or '').strip()

        if not title:
            return jsonify({"status": "error", "message": "title is required"}), 400

        # Default event_date to today if not provided
        if not event_date:
            event_date = datetime.now().strftime('%Y-%m-%d')

        # Default date_display if not provided
        if not date_display:
            # Use e.g. "Sun Sep 21 3pm" or just date if no time
            if time_str:
                date_display = f"{datetime.now().strftime('%a %b %d')} {time_str}"
            else:
                date_display = datetime.now().strftime('%a %b %d')

        cur = db.execute(
            'INSERT INTO events (title, date_display, event_date, time) VALUES (?, ?, ?, ?)',
            (title, date_display, event_date, time_str)
        )
        db.commit()
        new_id = cur.lastrowid
        db.close()
        return jsonify({"status": "ok", "id": new_id})

    except Exception as e:
        try:
            db.close()
        except Exception:
            pass
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/delete-event/<int:event_id>', methods=['DELETE'])
def delete_event(event_id):
    try:
        db = sqlite3.connect('events.db')
        db.execute('DELETE FROM events WHERE id = ?', (event_id,))
        db.commit()
        deleted = db.total_changes
        db.close()
        
        if deleted:
            return jsonify({"status": "ok", "message": "Event deleted"})
        else:
            return jsonify({"status": "error", "message": "Event not found"}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/clear-all', methods=['POST'])
def clear_all():
    try:
        db = sqlite3.connect('events.db')
        db.execute('DELETE FROM events')
        db.commit()
        db.close()
        return jsonify({"status": "ok", "message": "All events cleared"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
