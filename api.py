from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import sqlite3
from datetime import datetime, timedelta
import os
import requests as http_requests

app = Flask(__name__)
CORS(app)

ADJ_API_KEY = 'beta_3ZfqFapWvTbEfgjx3rozBhKd'
ADJ_BASE_URL = 'https://api.data.adj.news'

# Cache for doomsday data
doomsday_cache = {
    'data': None,
    'last_updated': None
}

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
    db.execute('''
        CREATE TABLE IF NOT EXISTS tracked_markets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            market_id TEXT UNIQUE NOT NULL,
            question TEXT NOT NULL,
            platform TEXT,
            link TEXT,
            added_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            market_id TEXT NOT NULL,
            probability REAL NOT NULL,
            recorded_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (market_id) REFERENCES tracked_markets(market_id)
        )
    ''')
    db.commit()

@app.route('/')
def index():
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), 'dashboard.html')

@app.route('/fonts/<path:filename>')
def serve_fonts(filename):
    return send_from_directory(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fonts'), filename)

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

def adj_api_request(endpoint, params=None):
    """Make a request to the Adjacent News API"""
    url = f"{ADJ_BASE_URL}{endpoint}"
    headers = {'Authorization': f'Bearer {ADJ_API_KEY}'}
    try:
        response = http_requests.get(url, headers=headers, params=params, timeout=15)
        if response.ok:
            return response.json()
        print(f"API request failed: {response.status_code} - {response.text[:100]}")
        return None
    except Exception as e:
        print(f"API request failed: {e}")
        return None

@app.route('/markets')
def get_markets():
    """Get tracked markets with latest prices"""
    db = sqlite3.connect('events.db')
    ensure_schema(db)

    cur = db.execute('''
        SELECT m.market_id, m.question, m.platform, m.link,
               (SELECT probability FROM price_history
                WHERE market_id = m.market_id
                ORDER BY recorded_at DESC LIMIT 1) as current_prob
        FROM tracked_markets m
    ''')

    markets = []
    for row in cur:
        markets.append({
            'market_id': row[0],
            'question': row[1],
            'platform': row[2],
            'link': row[3],
            'probability': row[4] or 0
        })

    db.close()
    return jsonify(markets)

@app.route('/markets/search')
def search_markets():
    """Search for markets on Adjacent News API"""
    query = request.args.get('q', '')
    if not query:
        return jsonify({"error": "Missing query parameter 'q'"}), 400

    data = adj_api_request('/api/search/query', params={'q': query, 'limit': 10})
    if not data or 'data' not in data:
        return jsonify({"error": "API request failed"}), 500

    results = []
    for m in data['data']:
        results.append({
            'market_id': m.get('market_id'),
            'question': m.get('question'),
            'platform': m.get('platform'),
            'probability': m.get('probability', 0),
            'link': m.get('link')
        })

    return jsonify(results)

@app.route('/markets/track', methods=['POST'])
def track_market():
    """Add a market to track"""
    data = request.get_json() or {}
    market_id = data.get('market_id')

    if not market_id:
        return jsonify({"error": "Missing market_id"}), 400

    # Fetch market details from API
    api_data = adj_api_request(f'/api/markets/{market_id}')
    if not api_data or 'data' not in api_data:
        return jsonify({"error": "Market not found"}), 404

    market = api_data['data']

    db = sqlite3.connect('events.db')
    ensure_schema(db)

    try:
        db.execute('''
            INSERT OR REPLACE INTO tracked_markets (market_id, question, platform, link)
            VALUES (?, ?, ?, ?)
        ''', (market_id, market.get('question', ''), market.get('platform', ''), market.get('link', '')))

        # Record initial price
        prob = market.get('probability', 0)
        db.execute('''
            INSERT INTO price_history (market_id, probability)
            VALUES (?, ?)
        ''', (market_id, prob))

        db.commit()
        db.close()
        return jsonify({"status": "ok", "message": "Market added"})
    except Exception as e:
        db.close()
        return jsonify({"error": str(e)}), 500

@app.route('/markets/untrack', methods=['POST'])
def untrack_market():
    """Remove a market from tracking"""
    data = request.get_json() or {}
    market_id = data.get('market_id')

    if not market_id:
        return jsonify({"error": "Missing market_id"}), 400

    db = sqlite3.connect('events.db')
    db.execute('DELETE FROM price_history WHERE market_id = ?', (market_id,))
    db.execute('DELETE FROM tracked_markets WHERE market_id = ?', (market_id,))
    db.commit()
    db.close()

    return jsonify({"status": "ok"})

@app.route('/markets/refresh', methods=['POST'])
def refresh_markets():
    """Fetch latest prices for all tracked markets"""
    db = sqlite3.connect('events.db')
    ensure_schema(db)

    cur = db.execute('SELECT market_id FROM tracked_markets')
    market_ids = [row[0] for row in cur.fetchall()]

    updated = 0
    for market_id in market_ids:
        api_data = adj_api_request(f'/api/markets/{market_id}')
        if api_data and 'data' in api_data:
            prob = api_data['data'].get('probability', 0)
            # Update the tracked market's current probability
            db.execute('''
                UPDATE tracked_markets SET question = ?
                WHERE market_id = ?
            ''', (api_data['data'].get('question', ''), market_id))
            db.execute('''
                INSERT INTO price_history (market_id, probability)
                VALUES (?, ?)
            ''', (market_id, prob))
            updated += 1

    db.commit()
    db.close()

    return jsonify({"status": "ok", "updated": updated})

def calculate_doomsday():
    """Calculate daily probability of catastrophic event based on prediction markets"""
    # Search terms for existential risks with estimated time horizons (in days)
    # and severity multipliers (how catastrophic if it happens)
    risk_categories = [
        {'query': 'nuclear war', 'horizon_days': 1000, 'severity': 1.0},
        {'query': 'world war', 'horizon_days': 1000, 'severity': 0.7},
        {'query': 'AI catastrophe', 'horizon_days': 1500, 'severity': 1.0},
        {'query': 'AGI', 'horizon_days': 1500, 'severity': 0.5},
        {'query': 'pandemic', 'horizon_days': 500, 'severity': 0.3},
        {'query': 'extinction', 'horizon_days': 2000, 'severity': 1.0},
    ]

    all_markets = []
    daily_probs = []  # Daily probability for each market

    for category in risk_categories:
        data = adj_api_request('/api/search/query', params={'q': category['query'], 'limit': 5})
        if data and 'data' in data:
            for m in data['data']:
                prob = m.get('probability', 0)
                # Normalize to 0-1 range
                if prob > 1:
                    prob = prob / 100

                # Only include markets with meaningful probabilities
                if 0 < prob < 1 and m.get('question'):
                    # Convert market probability to daily probability
                    # P(event in N days) = prob, so P(event today) ≈ prob / N (simplified)
                    # Apply severity to weight how "doomsday-like" this event is
                    daily_prob = (prob / category['horizon_days']) * category['severity']
                    daily_probs.append(daily_prob)

                    all_markets.append({
                        'market_id': m.get('market_id'),
                        'question': m.get('question'),
                        'probability': prob * 100,  # Store as percentage
                        'daily_prob': daily_prob * 100,  # Daily prob as percentage
                        'category': category['query']
                    })

    if not all_markets:
        return {
            'risk_score': 0,
            'daily_probability': 0,
            'minutes_to_midnight': 60,
            'clock_time': '11:00',
            'markets': [],
            'message': 'No data available'
        }

    # Calculate combined daily probability of ANY catastrophic event
    # P(any event today) = 1 - (1-p1)(1-p2)(1-p3)...
    survival_prob = 1.0
    for dp in daily_probs:
        survival_prob *= (1 - dp)
    combined_daily_prob = 1 - survival_prob

    # Convert to percentage for display
    daily_pct = combined_daily_prob * 100

    # Scale for clock display (use log scale since daily probs are tiny)
    # 0.0001% = 11:00 (very safe), 1% = 11:59 (extremely dangerous)
    import math
    if daily_pct > 0:
        # Log scale: -4 (0.0001%) to 0 (1%) maps to 0-59 minutes
        log_prob = math.log10(daily_pct)
        # Clamp between -4 and 0
        log_prob = max(-4, min(0, log_prob))
        # Map to minutes: -4 -> 0 min, 0 -> 59 min
        minutes_past_11 = int((log_prob + 4) * (59 / 4))
    else:
        minutes_past_11 = 0

    minutes_to_midnight = 60 - minutes_past_11
    clock_time = f"11:{minutes_past_11:02d}"

    # Sort markets by daily probability contribution
    all_markets.sort(key=lambda x: x['daily_prob'], reverse=True)

    return {
        'risk_score': round(daily_pct, 6),  # Daily probability as percentage
        'daily_probability': round(daily_pct, 6),
        'minutes_to_midnight': round(minutes_to_midnight, 1),
        'clock_time': clock_time,
        'markets': all_markets[:10],
        'market_count': len(all_markets)
    }

@app.route('/markets/doomsday')
def get_doomsday():
    """Return cached doomsday data or default if not yet calculated"""
    global doomsday_cache

    # Return cached data if available
    if doomsday_cache['data']:
        return jsonify(doomsday_cache['data'])

    # Return default if no cache yet
    return jsonify({
        'risk_score': 0,
        'minutes_to_midnight': 60,
        'clock_time': '11:00',
        'markets': [],
        'message': 'Calculating...'
    })

@app.route('/markets/doomsday/refresh', methods=['POST'])
def refresh_doomsday():
    """Refresh the doomsday cache"""
    global doomsday_cache
    doomsday_cache['data'] = calculate_doomsday()
    doomsday_cache['last_updated'] = datetime.now().isoformat()
    return jsonify({'status': 'ok'})

@app.route('/markets/top')
def get_top_markets():
    """Fetch top active markets from Adjacent News API"""
    limit = request.args.get('limit', 10, type=int)

    # Fetch active markets sorted by volume
    data = adj_api_request('/api/markets', params={
        'status': 'active',
        'limit': limit * 2,  # Fetch extra to filter
        'sort_by': 'volume',
        'sort_order': 'desc'
    })

    if not data or 'data' not in data:
        return jsonify([])

    # Filter to markets with meaningful probabilities (between 5-95%)
    markets = []
    for m in data['data']:
        prob = m.get('probability', 0)
        if 5 <= prob <= 95 and m.get('question'):
            markets.append({
                'market_id': m.get('market_id'),
                'question': m.get('question'),
                'platform': m.get('platform'),
                'probability': prob,
                'link': m.get('link')
            })
        if len(markets) >= limit:
            break

    return jsonify(markets)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
