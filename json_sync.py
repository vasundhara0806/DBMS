import os
import json
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_STATE_PATH = os.path.join(BASE_DIR, 'database_state.json')
ACTIVITY_LOG_PATH = os.path.join(BASE_DIR, 'activity_log.json')

def get_database_state_path():
    return DATABASE_STATE_PATH

def get_activity_log_path():
    return ACTIVITY_LOG_PATH

def export_database_to_json(last_action_summary=None):
    """
    Exports the current state of all database tables into database_state.json.
    Ensures clean, readable JSON formatted with indent=2.
    """
    import database

    conn = database.get_db()
    try:
        if database.ACTIVE_ENGINE == 'sqlite':
            cur = conn.cursor()
            def fetch_all(sql, params=()):
                cur.execute(database.adapt_sql(sql), params)
                return [dict(r) for r in cur.fetchall()]
        else:
            cur = conn.cursor(dictionary=True)
            def fetch_all(sql, params=()):
                cur.execute(database.adapt_sql(sql), params)
                return cur.fetchall()

        cities = fetch_all("SELECT * FROM city ORDER BY city_id")
        theaters = fetch_all("""
            SELECT t.*, c.city_name, c.state
            FROM theater t
            JOIN city c ON c.city_id = t.city_id
            ORDER BY t.theater_id
        """)
        screens = fetch_all("""
            SELECT sc.*, t.theater_name, c.city_name
            FROM screen sc
            JOIN theater t ON t.theater_id = sc.theater_id
            JOIN city c ON c.city_id = t.city_id
            ORDER BY sc.screen_id
        """)
        seat_categories = fetch_all("SELECT * FROM seat_category ORDER BY category_id")
        genres = fetch_all("SELECT * FROM genre ORDER BY genre_id")
        slots = fetch_all("SELECT * FROM slot ORDER BY slot_id")

        movies = fetch_all("""
            SELECT m.*, GROUP_CONCAT(g.genre_name ORDER BY g.genre_name SEPARATOR ', ') AS genres
            FROM movie m
            LEFT JOIN movie_genre mg ON mg.movie_id = m.movie_id
            LEFT JOIN genre g ON g.genre_id = mg.genre_id
            GROUP BY m.movie_id
            ORDER BY m.movie_id
        """)

        screenings = fetch_all("""
            SELECT s.*, m.title AS movie_title, m.dimension, m.language,
                   t.theater_name, t.location_area, c.city_name,
                   sc.screen_name, sc.screen_type,
                   sl.slot_name, sl.start_time
            FROM screening s
            JOIN movie m ON m.movie_id = s.movie_id
            JOIN screen sc ON sc.screen_id = s.screen_id
            JOIN theater t ON t.theater_id = sc.theater_id
            JOIN city c ON c.city_id = t.city_id
            JOIN slot sl ON sl.slot_id = s.slot_id
            ORDER BY s.screening_date DESC, s.screening_id DESC
        """)

        # Exclude password_hash for security
        customers = fetch_all("""
            SELECT customer_id, full_name, email, phone, role, created_at
            FROM customer
            ORDER BY customer_id
        """)

        concession_items = fetch_all("SELECT * FROM concession_item ORDER BY item_id")

        bookings = fetch_all("""
            SELECT b.*, cust.full_name AS customer_name, cust.email AS customer_email, cust.phone AS customer_phone,
                   m.title AS movie_title, t.theater_name, sc.screen_name,
                   s.screening_date, sl.slot_name, sl.start_time,
                   p.payment_method, p.payment_status, p.transaction_reference, p.payment_time
            FROM booking b
            JOIN customer cust ON cust.customer_id = b.customer_id
            JOIN screening s ON s.screening_id = b.screening_id
            JOIN movie m ON m.movie_id = s.movie_id
            JOIN screen sc ON sc.screen_id = s.screen_id
            JOIN theater t ON t.theater_id = sc.theater_id
            JOIN slot sl ON sl.slot_id = s.slot_id
            LEFT JOIN payment p ON p.booking_id = b.booking_id
            ORDER BY b.booking_id DESC
        """)

        booking_seats = fetch_all("""
            SELECT bs.*, s.row_label, s.seat_number, cat.category_name, t.ticket_code, t.ticket_status
            FROM booking_seat bs
            JOIN seat s ON s.seat_id = bs.seat_id
            JOIN seat_category cat ON cat.category_id = s.category_id
            LEFT JOIN ticket t ON t.booking_seat_id = bs.booking_seat_id
            ORDER BY bs.booking_seat_id DESC
        """)

        tickets = fetch_all("""
            SELECT t.*, b.booking_reference, cust.full_name AS passenger_name
            FROM ticket t
            JOIN booking_seat bs ON bs.booking_seat_id = t.booking_seat_id
            JOIN booking b ON b.booking_id = bs.booking_id
            JOIN customer cust ON cust.customer_id = b.customer_id
            ORDER BY t.ticket_id DESC
        """)

        payments = fetch_all("""
            SELECT p.*, b.booking_reference, b.booking_status
            FROM payment p
            JOIN booking b ON b.booking_id = p.booking_id
            ORDER BY p.payment_id DESC
        """)

        booking_concessions = fetch_all("""
            SELECT bc.*, ci.item_name, ci.category, ci.price AS unit_price
            FROM booking_concession bc
            JOIN concession_item ci ON ci.item_id = bc.item_id
            ORDER BY bc.booking_concession_id DESC
        """)

        cur.close()

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        summary_counts = {
            "movies": len(movies),
            "screenings": len(screenings),
            "theaters": len(theaters),
            "screens": len(screens),
            "bookings": len(bookings),
            "tickets": len(tickets),
            "payments": len(payments),
            "concession_items": len(concession_items),
            "customers": len(customers),
            "seat_categories": len(seat_categories)
        }

        full_data = {
            "_metadata": {
                "system": "CineSphere Cinema Management & DBMS Portal",
                "purpose": "Live Database Snapshot & Real-Time Sync File",
                "last_synced_at": now_str,
                "last_action": last_action_summary or "Database synchronization completed",
                "active_engine": database.ACTIVE_ENGINE,
                "summary_counts": summary_counts
            },
            "movies": movies,
            "screenings": screenings,
            "theaters": theaters,
            "screens": screens,
            "seat_categories": seat_categories,
            "concession_items": concession_items,
            "bookings": bookings,
            "booking_seats": booking_seats,
            "tickets": tickets,
            "payments": payments,
            "booking_concessions": booking_concessions,
            "customers": customers,
            "slots": slots,
            "genres": genres,
            "cities": cities
        }

        # Safe atomic write to database_state.json
        temp_path = DATABASE_STATE_PATH + '.tmp'
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(full_data, f, indent=2, default=str)
        if os.path.exists(DATABASE_STATE_PATH):
            os.replace(temp_path, DATABASE_STATE_PATH)
        else:
            os.rename(temp_path, DATABASE_STATE_PATH)

        return full_data
    finally:
        conn.close()

def log_activity(action, table, summary, details=None, user=None):
    """
    Appends a new mutation / operation entry into activity_log.json.
    """
    entries = []
    if os.path.exists(ACTIVITY_LOG_PATH):
        try:
            with open(ACTIVITY_LOG_PATH, 'r', encoding='utf-8') as f:
                entries = json.load(f)
                if not isinstance(entries, list):
                    entries = []
        except Exception:
            entries = []

    new_id = len(entries) + 1
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    entry = {
        "id": new_id,
        "timestamp": now_str,
        "action": action,
        "table": table,
        "user": user or "System / Manager",
        "summary": summary,
        "details": details or {}
    }

    entries.append(entry)

    temp_path = ACTIVITY_LOG_PATH + '.tmp'
    with open(temp_path, 'w', encoding='utf-8') as f:
        json.dump(entries, f, indent=2, default=str)
    if os.path.exists(ACTIVITY_LOG_PATH):
        os.replace(temp_path, ACTIVITY_LOG_PATH)
    else:
        os.rename(temp_path, ACTIVITY_LOG_PATH)

    return entry

def sync_all(action, table, summary, details=None, user=None):
    """
    Master sync function:
    1. Records change in activity_log.json
    2. Updates complete database_state.json
    Returns dict with sync information.
    """
    activity_entry = log_activity(action, table, summary, details=details, user=user)
    db_state = export_database_to_json(last_action_summary=summary)
    return {
        "status": "success",
        "timestamp": activity_entry["timestamp"],
        "activity": activity_entry,
        "summary_counts": db_state["_metadata"]["summary_counts"]
    }

def get_activity_log(limit=None):
    """
    Returns activity log entries, newest first.
    """
    if not os.path.exists(ACTIVITY_LOG_PATH):
        return []
    try:
        with open(ACTIVITY_LOG_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, list):
                if limit:
                    return list(reversed(data))[:limit]
                return list(reversed(data))
            return []
    except Exception:
        return []

def get_database_state():
    """
    Returns current database_state.json content or regenerates if missing.
    """
    if not os.path.exists(DATABASE_STATE_PATH):
        return export_database_to_json("Initial database JSON generation")
    try:
        with open(DATABASE_STATE_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return export_database_to_json("Re-generated after read error")
