import os
import sqlite3
from datetime import date, datetime, timedelta
from werkzeug.security import generate_password_hash
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv('DB_HOST', '127.0.0.1')
DB_PORT = int(os.getenv('DB_PORT', '3306'))
DB_USER = os.getenv('DB_USER', 'root')
DB_PASSWORD = os.getenv('DB_PASSWORD', '')
DB_NAME = os.getenv('DB_NAME', 'cinesphere')
SQLITE_DB_PATH = os.path.join(os.path.dirname(__file__), 'cinesphere.db')

# Force engine or auto-detect
# Options: 'auto', 'mysql', 'sqlite'
DB_ENGINE = os.getenv('DB_ENGINE', 'auto').lower()

def can_connect_mysql():
    try:
        import mysql.connector
        conn = mysql.connector.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            connection_timeout=2
        )
        conn.close()
        return True
    except Exception:
        return False

def get_engine():
    if DB_ENGINE == 'mysql':
        return 'mysql'
    if DB_ENGINE == 'sqlite':
        return 'sqlite'
    # Auto-detect
    if can_connect_mysql():
        return 'mysql'
    return 'sqlite'

ACTIVE_ENGINE = get_engine()

def get_db():
    if ACTIVE_ENGINE == 'mysql':
        import mysql.connector
        return mysql.connector.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )
    else:
        conn = sqlite3.connect(SQLITE_DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys = ON;')
        # Emulate MySQL functions
        conn.create_function('CURDATE', 0, lambda: date.today().isoformat())
        conn.create_function('NOW', 0, lambda: datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        return conn

def adapt_sql(sql):
    if ACTIVE_ENGINE == 'sqlite':
        # Replace MySQL parameter placeholder %s with SQLite ?
        sql = sql.replace('%s', '?')
        # Replace MySQL GROUP_CONCAT syntax if needed
        # SQLite supports GROUP_CONCAT(expr, separator)
        if 'ORDER BY' in sql and 'SEPARATOR' in sql:
            # Simple replacement for standard GROUP_CONCAT(col ORDER BY col SEPARATOR ', ')
            import re
            sql = re.sub(
                r"GROUP_CONCAT\((.+?)\s+ORDER\s+BY\s+.+?\s+SEPARATOR\s+(.+?)\)",
                r"GROUP_CONCAT(\1, \2)",
                sql,
                flags=re.IGNORECASE
            )
        sql = sql.replace("FOR UPDATE", "")
    return sql

def query(sql, params=(), one=False):
    sql = adapt_sql(sql)
    conn = get_db()
    try:
        if ACTIVE_ENGINE == 'mysql':
            cur = conn.cursor(dictionary=True)
            cur.execute(sql, params)
            result = cur.fetchone() if one else cur.fetchall()
            cur.close()
            return result
        else:
            cur = conn.cursor()
            cur.execute(sql, params)
            if one:
                row = cur.fetchone()
                result = dict(row) if row else None
            else:
                rows = cur.fetchall()
                result = [dict(r) for r in rows]
            cur.close()
            return result
    finally:
        conn.close()

def execute(sql, params=()):
    sql = adapt_sql(sql)
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        conn.commit()
        last_id = cur.lastrowid
        cur.close()
        return last_id
    finally:
        conn.close()

# ==========================================================
# DATABASE OBJECTS: VIEWS, STORED PROCEDURES & TRIGGERS
# ==========================================================
# These objects are created natively by init_schema.sql on MySQL.
# SQLite does not support stored procedures, so the same procedures
# are emulated with Python handlers below. Views and triggers are
# created natively in SQLite as well.

DB_VIEWS = {
    'vw_booking_totals': {
        'description': 'Booking-level totals with seat counts (one row per booking).',
        'sql': """
        CREATE VIEW vw_booking_totals AS
        SELECT b.booking_id, b.booking_reference, b.customer_id, b.screening_id,
               b.booking_date, b.total_amount, b.booking_status,
               COUNT(bs.booking_seat_id) AS tickets
        FROM booking b
        LEFT JOIN booking_seat bs ON bs.booking_id = b.booking_id
        GROUP BY b.booking_id, b.booking_reference, b.customer_id, b.screening_id,
                 b.booking_date, b.total_amount, b.booking_status
        """
    },
    'vw_booking_details': {
        'description': 'Complete audit view: customer, movie, theater, screen, slot and payment.',
        'sql': """
        CREATE VIEW vw_booking_details AS
        SELECT b.booking_id, b.booking_reference, b.booking_date, b.total_amount, b.booking_status,
               cust.customer_id, cust.full_name AS customer_name, cust.email AS customer_email,
               cust.phone AS customer_phone,
               m.movie_id, m.title AS movie_title, m.language, m.dimension,
               t.theater_id, t.theater_name, t.location_area, c.city_name,
               sc.screen_id, sc.screen_name, sc.screen_type,
               s.screening_id, s.screening_date, sl.slot_name, sl.start_time,
               p.payment_method, p.payment_status, p.transaction_reference
        FROM booking b
        JOIN customer cust ON cust.customer_id = b.customer_id
        JOIN screening s ON s.screening_id = b.screening_id
        JOIN movie m ON m.movie_id = s.movie_id
        JOIN screen sc ON sc.screen_id = s.screen_id
        JOIN theater t ON t.theater_id = sc.theater_id
        JOIN city c ON c.city_id = t.city_id
        JOIN slot sl ON sl.slot_id = s.slot_id
        LEFT JOIN payment p ON p.booking_id = b.booking_id
        """
    },
    'vw_movie_performance': {
        'description': 'Bookings, tickets sold and gross revenue aggregated per movie.',
        'sql': """
        CREATE VIEW vw_movie_performance AS
        SELECT m.movie_id, m.title, m.language, m.dimension,
               COUNT(DISTINCT bt.booking_id) AS total_bookings,
               COALESCE(SUM(CASE WHEN bt.booking_status = 'CONFIRMED' THEN bt.tickets ELSE 0 END), 0) AS tickets_sold,
               ROUND(COALESCE(SUM(CASE WHEN bt.booking_status = 'CONFIRMED' THEN bt.total_amount ELSE 0 END), 0), 2) AS gross_revenue
        FROM movie m
        LEFT JOIN screening s ON s.movie_id = m.movie_id
        LEFT JOIN vw_booking_totals bt ON bt.screening_id = s.screening_id
        GROUP BY m.movie_id, m.title, m.language, m.dimension
        """
    },
    'vw_theater_performance': {
        'description': 'Screens, bookings and gross revenue aggregated per theater / city.',
        'sql': """
        CREATE VIEW vw_theater_performance AS
        SELECT t.theater_id, t.theater_name, c.city_name, c.state,
               COUNT(DISTINCT sc.screen_id) AS total_screens,
               COUNT(DISTINCT bt.booking_id) AS total_bookings,
               ROUND(COALESCE(SUM(CASE WHEN bt.booking_status = 'CONFIRMED' THEN bt.total_amount ELSE 0 END), 0), 2) AS gross_revenue
        FROM theater t
        JOIN city c ON c.city_id = t.city_id
        LEFT JOIN screen sc ON sc.theater_id = t.theater_id
        LEFT JOIN screening s ON s.screen_id = sc.screen_id
        LEFT JOIN vw_booking_totals bt ON bt.screening_id = s.screening_id
        GROUP BY t.theater_id, t.theater_name, c.city_name, c.state
        """
    },
    'vw_screening_occupancy': {
        'description': 'Live seat occupancy for every screening (total vs booked seats).',
        'sql': """
        CREATE VIEW vw_screening_occupancy AS
        SELECT s.screening_id, s.screening_date, s.base_price, s.status,
               m.movie_id, m.title AS movie_title,
               t.theater_id, t.theater_name, c.city_name,
               sc.screen_id, sc.screen_name, sc.screen_type,
               sl.slot_name, sl.start_time,
               COUNT(DISTINCT se.seat_id) AS total_seats,
               COUNT(DISTINCT CASE WHEN b.booking_status = 'CONFIRMED' AND bs.seat_status = 'BOOKED'
                                   THEN bs.booking_seat_id END) AS booked_seats,
               ROUND(
                   CASE WHEN COUNT(DISTINCT se.seat_id) = 0 THEN 0
                        ELSE COUNT(DISTINCT CASE WHEN b.booking_status = 'CONFIRMED' AND bs.seat_status = 'BOOKED'
                                                 THEN bs.booking_seat_id END) * 100.0
                             / COUNT(DISTINCT se.seat_id)
                   END, 1) AS occupancy_percent
        FROM screening s
        JOIN movie m ON m.movie_id = s.movie_id
        JOIN screen sc ON sc.screen_id = s.screen_id
        JOIN theater t ON t.theater_id = sc.theater_id
        JOIN city c ON c.city_id = t.city_id
        JOIN slot sl ON sl.slot_id = s.slot_id
        LEFT JOIN seat se ON se.screen_id = sc.screen_id AND se.is_active = 1
        LEFT JOIN booking_seat bs ON bs.seat_id = se.seat_id
        LEFT JOIN booking b ON b.booking_id = bs.booking_id AND b.screening_id = s.screening_id
        GROUP BY s.screening_id, s.screening_date, s.base_price, s.status, m.movie_id, m.title,
                 t.theater_id, t.theater_name, c.city_name, sc.screen_id, sc.screen_name,
                 sc.screen_type, sl.slot_name, sl.start_time
        """
    },
    'vw_customer_spend': {
        'description': 'Customer booking history, tickets bought and total amount spent.',
        'sql': """
        CREATE VIEW vw_customer_spend AS
        SELECT c.customer_id, c.full_name, c.email, c.phone, c.role,
               COUNT(DISTINCT bt.booking_id) AS total_bookings,
               COUNT(DISTINCT CASE WHEN bt.booking_status = 'CONFIRMED' THEN bt.booking_id END) AS confirmed_bookings,
               COALESCE(SUM(CASE WHEN bt.booking_status = 'CONFIRMED' THEN bt.tickets ELSE 0 END), 0) AS tickets_bought,
               ROUND(COALESCE(SUM(CASE WHEN bt.booking_status = 'CONFIRMED' THEN bt.total_amount ELSE 0 END), 0), 2) AS total_spent
        FROM customer c
        LEFT JOIN vw_booking_totals bt ON bt.customer_id = c.customer_id
        GROUP BY c.customer_id, c.full_name, c.email, c.phone, c.role
        """
    },
    'vw_concession_sales': {
        'description': 'Food & beverage units sold and revenue for confirmed bookings.',
        'sql': """
        CREATE VIEW vw_concession_sales AS
        SELECT ci.item_id, ci.item_name, ci.category, ci.price,
               COALESCE(SUM(CASE WHEN b.booking_status = 'CONFIRMED' THEN bc.quantity ELSE 0 END), 0) AS units_sold,
               ROUND(COALESCE(SUM(CASE WHEN b.booking_status = 'CONFIRMED' THEN bc.subtotal ELSE 0 END), 0), 2) AS gross_revenue
        FROM concession_item ci
        LEFT JOIN booking_concession bc ON bc.item_id = ci.item_id
        LEFT JOIN booking b ON b.booking_id = bc.booking_id
        GROUP BY ci.item_id, ci.item_name, ci.category, ci.price
        """
    }
}

# Trigger metadata is shared by MySQL and SQLite. SQLite bodies are defined below.
DB_TRIGGERS = {
    'trg_booking_status_cascade': {
        'table': 'booking', 'timing': 'AFTER', 'event': 'UPDATE',
        'description': 'When a booking is cancelled, cascade CANCELLED to seats/tickets and REFUNDED to payments.'
    },
    'trg_booking_restore_on_confirm': {
        'table': 'booking', 'timing': 'AFTER', 'event': 'UPDATE',
        'description': 'When a cancelled booking is re-confirmed, restore its seats, tickets and payment.'
    },
    'trg_prevent_double_booking': {
        'table': 'booking_seat', 'timing': 'BEFORE', 'event': 'INSERT',
        'description': 'Blocks booking the same seat twice for the same screening.'
    },
    'trg_screening_conflict_insert': {
        'table': 'screening', 'timing': 'BEFORE', 'event': 'INSERT',
        'description': 'Prevents a screen from having two SCHEDULED shows in the same slot/date.'
    },
    'trg_screening_conflict_update': {
        'table': 'screening', 'timing': 'BEFORE', 'event': 'UPDATE',
        'description': 'Same slot conflict protection when a showtime is edited.'
    },
    'trg_screen_seat_count_insert': {
        'table': 'seat', 'timing': 'AFTER', 'event': 'INSERT',
        'description': 'Keeps screen.total_seats in sync when a seat is added.'
    },
    'trg_screen_seat_count_update': {
        'table': 'seat', 'timing': 'AFTER', 'event': 'UPDATE',
        'description': 'Keeps screen.total_seats in sync when a seat is activated/deactivated.'
    },
    'trg_screen_seat_count_delete': {
        'table': 'seat', 'timing': 'AFTER', 'event': 'DELETE',
        'description': 'Keeps screen.total_seats in sync when a seat is removed.'
    },
    'trg_booking_seat_ticket_sync': {
        'table': 'booking_seat', 'timing': 'AFTER', 'event': 'UPDATE',
        'description': 'Mirrors booking_seat.seat_status changes onto the linked ticket.'
    }
}

DB_SQLITE_TRIGGERS = {
    'trg_booking_status_cascade': """
        CREATE TRIGGER trg_booking_status_cascade
        AFTER UPDATE OF booking_status ON booking
        FOR EACH ROW
        WHEN NEW.booking_status = 'CANCELLED' AND OLD.booking_status <> 'CANCELLED'
        BEGIN
            UPDATE booking_seat SET seat_status = 'CANCELLED' WHERE booking_id = NEW.booking_id;
            UPDATE ticket SET ticket_status = 'CANCELLED'
             WHERE booking_seat_id IN (SELECT booking_seat_id FROM booking_seat WHERE booking_id = NEW.booking_id);
            UPDATE payment SET payment_status = 'REFUNDED'
             WHERE booking_id = NEW.booking_id AND payment_status = 'SUCCESS';
        END
    """,
    'trg_booking_restore_on_confirm': """
        CREATE TRIGGER trg_booking_restore_on_confirm
        AFTER UPDATE OF booking_status ON booking
        FOR EACH ROW
        WHEN NEW.booking_status = 'CONFIRMED' AND OLD.booking_status = 'CANCELLED'
        BEGIN
            UPDATE booking_seat SET seat_status = 'BOOKED' WHERE booking_id = NEW.booking_id;
            UPDATE ticket SET ticket_status = 'ACTIVE'
             WHERE booking_seat_id IN (SELECT booking_seat_id FROM booking_seat WHERE booking_id = NEW.booking_id);
            UPDATE payment SET payment_status = 'SUCCESS'
             WHERE booking_id = NEW.booking_id AND payment_status = 'REFUNDED';
        END
    """,
    'trg_prevent_double_booking': """
        CREATE TRIGGER trg_prevent_double_booking
        BEFORE INSERT ON booking_seat
        FOR EACH ROW
        WHEN EXISTS (
            SELECT 1
            FROM booking_seat bs
            JOIN booking b ON b.booking_id = bs.booking_id
            JOIN booking nb ON nb.booking_id = NEW.booking_id
            WHERE bs.seat_id = NEW.seat_id
              AND b.screening_id = nb.screening_id
              AND b.booking_status = 'CONFIRMED'
              AND bs.seat_status = 'BOOKED'
        )
        BEGIN
            SELECT RAISE(ABORT, 'Seat is already booked for this screening');
        END
    """,
    'trg_screening_conflict_insert': """
        CREATE TRIGGER trg_screening_conflict_insert
        BEFORE INSERT ON screening
        FOR EACH ROW
        WHEN NEW.status = 'SCHEDULED' AND EXISTS (
            SELECT 1 FROM screening s
            WHERE s.screen_id = NEW.screen_id
              AND s.slot_id = NEW.slot_id
              AND s.screening_date = NEW.screening_date
              AND s.status = 'SCHEDULED'
        )
        BEGIN
            SELECT RAISE(ABORT, 'Screening conflict: screen already booked for this date and slot');
        END
    """,
    'trg_screening_conflict_update': """
        CREATE TRIGGER trg_screening_conflict_update
        BEFORE UPDATE ON screening
        FOR EACH ROW
        WHEN NEW.status = 'SCHEDULED' AND EXISTS (
            SELECT 1 FROM screening s
            WHERE s.screen_id = NEW.screen_id
              AND s.slot_id = NEW.slot_id
              AND s.screening_date = NEW.screening_date
              AND s.status = 'SCHEDULED'
              AND s.screening_id <> NEW.screening_id
        )
        BEGIN
            SELECT RAISE(ABORT, 'Screening conflict: screen already booked for this date and slot');
        END
    """,
    'trg_screen_seat_count_insert': """
        CREATE TRIGGER trg_screen_seat_count_insert
        AFTER INSERT ON seat
        FOR EACH ROW
        BEGIN
            UPDATE screen
               SET total_seats = (SELECT COUNT(*) FROM seat WHERE screen_id = NEW.screen_id AND is_active = 1)
             WHERE screen_id = NEW.screen_id;
        END
    """,
    'trg_screen_seat_count_update': """
        CREATE TRIGGER trg_screen_seat_count_update
        AFTER UPDATE OF is_active ON seat
        FOR EACH ROW
        BEGIN
            UPDATE screen
               SET total_seats = (SELECT COUNT(*) FROM seat WHERE screen_id = NEW.screen_id AND is_active = 1)
             WHERE screen_id = NEW.screen_id;
        END
    """,
    'trg_screen_seat_count_delete': """
        CREATE TRIGGER trg_screen_seat_count_delete
        AFTER DELETE ON seat
        FOR EACH ROW
        BEGIN
            UPDATE screen
               SET total_seats = (SELECT COUNT(*) FROM seat WHERE screen_id = OLD.screen_id AND is_active = 1)
             WHERE screen_id = OLD.screen_id;
        END
    """,
    'trg_booking_seat_ticket_sync': """
        CREATE TRIGGER trg_booking_seat_ticket_sync
        AFTER UPDATE OF seat_status ON booking_seat
        FOR EACH ROW
        BEGIN
            UPDATE ticket
               SET ticket_status = CASE WHEN NEW.seat_status = 'CANCELLED' THEN 'CANCELLED' ELSE 'ACTIVE' END
             WHERE booking_seat_id = NEW.booking_seat_id;
        END
    """
}


def _install_sqlite_db_objects(cur):
    """Create/replace all SQLite views and triggers (idempotent)."""
    for name in DB_SQLITE_TRIGGERS:
        cur.execute(f"DROP TRIGGER IF EXISTS {name};")
    for name in DB_VIEWS:
        cur.execute(f"DROP VIEW IF EXISTS {name};")
    for meta in DB_VIEWS.values():
        cur.execute(meta['sql'])
    for sql in DB_SQLITE_TRIGGERS.values():
        cur.execute(sql)


def ensure_sqlite_db_objects():
    """Ensure views and triggers exist on an already initialized SQLite database."""
    if ACTIVE_ENGINE != 'sqlite':
        return False
    conn = sqlite3.connect(SQLITE_DB_PATH)
    try:
        cur = conn.cursor()
        _install_sqlite_db_objects(cur)
        conn.commit()
        return True
    finally:
        conn.close()


# ---------- Stored procedure emulation (SQLite) ----------

def _sp_get_customer_bookings(params):
    customer_id = int(params[0])
    return query(
        """
        SELECT booking_id, booking_reference, booking_date, total_amount, booking_status,
               movie_title, theater_name, city_name, screen_name,
               screening_date, slot_name, start_time
        FROM vw_booking_details
        WHERE customer_id = %s
        ORDER BY booking_date DESC
        """,
        (customer_id,)
    )


def _sp_get_movie_revenue(params):
    movie_id = int(params[0])
    row = query(
        "SELECT * FROM vw_movie_performance WHERE movie_id = %s",
        (movie_id,),
        one=True
    )
    return [row] if row else []


def _sp_get_available_seats(params):
    screening_id = int(params[0])
    return query(
        """
        SELECT se.seat_id, se.row_label, se.seat_number,
               cat.category_name,
               ROUND(s.base_price * cat.price_multiplier, 2) AS price
        FROM seat se
        JOIN seat_category cat ON cat.category_id = se.category_id
        JOIN screening s ON s.screening_id = %s
        WHERE se.screen_id = s.screen_id
          AND se.is_active = 1
          AND NOT EXISTS (
              SELECT 1
              FROM booking_seat bs
              JOIN booking b ON b.booking_id = bs.booking_id
              WHERE bs.seat_id = se.seat_id
                AND b.screening_id = s.screening_id
                AND b.booking_status = 'CONFIRMED'
                AND bs.seat_status = 'BOOKED'
          )
        ORDER BY se.row_label, se.seat_number
        """,
        (screening_id,)
    )


def _sp_revenue_report(params):
    start_date, end_date = str(params[0]), str(params[1])
    return query(
        """
        SELECT m.movie_id, m.title,
               COUNT(DISTINCT b.booking_id) AS total_bookings,
               COUNT(bs.booking_seat_id) AS tickets_sold,
               ROUND(COALESCE(SUM(bs.ticket_price), 0), 2) AS seat_revenue
        FROM booking b
        JOIN screening s ON s.screening_id = b.screening_id
        JOIN movie m ON m.movie_id = s.movie_id
        JOIN booking_seat bs ON bs.booking_id = b.booking_id AND bs.seat_status = 'BOOKED'
        WHERE b.booking_status = 'CONFIRMED'
          AND s.screening_date BETWEEN %s AND %s
        GROUP BY m.movie_id, m.title
        ORDER BY seat_revenue DESC
        """,
        (start_date, end_date)
    )


def _sp_schedule_screening(params):
    movie_id, screen_id, slot_id = int(params[0]), int(params[1]), int(params[2])
    screening_date, base_price = str(params[3]), float(params[4])
    conflict = query(
        """
        SELECT screening_id FROM screening
        WHERE screen_id = %s AND slot_id = %s AND screening_date = %s AND status = 'SCHEDULED'
        """,
        (screen_id, slot_id, screening_date),
        one=True
    )
    if conflict:
        return [{
            'result': 'CONFLICT',
            'message': 'This screen already has a scheduled show for the selected date and slot.',
            'screening_id': None
        }]
    new_id = execute(
        """
        INSERT INTO screening (movie_id, screen_id, slot_id, screening_date, base_price, status)
        VALUES (%s, %s, %s, %s, %s, 'SCHEDULED')
        """,
        (movie_id, screen_id, slot_id, screening_date, base_price)
    )
    return [{
        'result': 'SCHEDULED',
        'message': 'Showtime scheduled successfully.',
        'screening_id': new_id
    }]


def _sp_cancel_booking(params):
    booking_id = int(params[0])
    row = query("SELECT booking_status FROM booking WHERE booking_id = %s", (booking_id,), one=True)
    if not row:
        return [{'result': 'NOT_FOUND', 'message': f'Booking #{booking_id} was not found.'}]
    if row['booking_status'] != 'CONFIRMED':
        return [{'result': 'INVALID_STATE', 'message': f"Booking #{booking_id} is already {row['booking_status']}."}]
    execute("UPDATE booking SET booking_status = 'CANCELLED' WHERE booking_id = %s", (booking_id,))
    return [{
        'result': 'CANCELLED',
        'message': f'Booking #{booking_id} cancelled. Seats, tickets and payment were updated by triggers.'
    }]


DB_PROCEDURES = {
    'sp_get_customer_bookings': {
        'description': 'Returns the complete booking history for one customer.',
        'params': [
            {'name': 'customer_id', 'label': 'Customer', 'type': 'select', 'source': 'customers'}
        ],
        'sqlite_handler': _sp_get_customer_bookings
    },
    'sp_get_movie_revenue': {
        'description': 'Returns the revenue summary for one movie.',
        'params': [
            {'name': 'movie_id', 'label': 'Movie', 'type': 'select', 'source': 'movies'}
        ],
        'sqlite_handler': _sp_get_movie_revenue
    },
    'sp_get_available_seats': {
        'description': 'Lists every vacant seat with tier price for a screening.',
        'params': [
            {'name': 'screening_id', 'label': 'Screening', 'type': 'select', 'source': 'screenings'}
        ],
        'sqlite_handler': _sp_get_available_seats
    },
    'sp_revenue_report': {
        'description': 'Revenue by movie for confirmed bookings between two dates.',
        'params': [
            {'name': 'start_date', 'label': 'Start Date', 'type': 'date'},
            {'name': 'end_date', 'label': 'End Date', 'type': 'date'}
        ],
        'sqlite_handler': _sp_revenue_report
    },
    'sp_schedule_screening': {
        'description': 'Inserts a new showtime after checking for a slot conflict.',
        'params': [
            {'name': 'movie_id', 'label': 'Movie', 'type': 'select', 'source': 'movies'},
            {'name': 'screen_id', 'label': 'Screen', 'type': 'select', 'source': 'screens'},
            {'name': 'slot_id', 'label': 'Slot', 'type': 'select', 'source': 'slots'},
            {'name': 'screening_date', 'label': 'Date', 'type': 'date'},
            {'name': 'base_price', 'label': 'Base Price (Rs.)', 'type': 'number'}
        ],
        'sqlite_handler': _sp_schedule_screening
    },
    'sp_cancel_booking': {
        'description': 'Cancels a confirmed booking and lets triggers refund the payment.',
        'params': [
            {'name': 'booking_id', 'label': 'Booking', 'type': 'select', 'source': 'bookings'}
        ],
        'sqlite_handler': _sp_cancel_booking
    }
}

DB_TRIGGER_TESTS = {
    'double_booking': {
        'title': 'Double-booking guard',
        'description': 'Tries to insert the same seat twice for one screening inside a transaction.'
    },
    'screening_conflict': {
        'title': 'Showtime conflict guard',
        'description': 'Tries to insert a duplicate screen/date/slot showtime inside a transaction.'
    },
    'cancel_cascade': {
        'title': 'Cancellation cascade',
        'description': 'Cancels a confirmed booking inside a transaction and verifies seats, tickets and payment follow.'
    },
    'seat_count': {
        'title': 'Seat-count synchronizer',
        'description': 'Adds a seat inside a transaction and verifies screen.total_seats increments.'
    }
}


def get_db_objects():
    """Return installed views, procedures and triggers with descriptions."""
    installed_views, installed_procs, installed_triggers = {}, set(), {}
    view_sql = {}

    try:
        if ACTIVE_ENGINE == 'mysql':
            rows = query(
                "SELECT table_name AS name, view_definition AS definition "
                "FROM information_schema.views WHERE table_schema = DATABASE()"
            )
            for r in rows:
                installed_views[r['name'].lower()] = True
                view_sql[r['name'].lower()] = r.get('definition')
            rows = query(
                "SELECT routine_name AS name FROM information_schema.routines "
                "WHERE routine_schema = DATABASE() AND routine_type = 'PROCEDURE'"
            )
            installed_procs = {r['name'].lower() for r in rows}
            rows = query(
                "SELECT trigger_name AS name, action_timing, event_manipulation, "
                "event_object_table, action_statement FROM information_schema.triggers "
                "WHERE trigger_schema = DATABASE()"
            )
            for r in rows:
                installed_triggers[r['name'].lower()] = r
        else:
            rows = query("SELECT name, type, sql FROM sqlite_master WHERE type IN ('view', 'trigger')")
            for r in rows:
                if r['type'] == 'view':
                    installed_views[r['name'].lower()] = True
                    view_sql[r['name'].lower()] = r['sql']
                else:
                    installed_triggers[r['name'].lower()] = r
            installed_procs = {name.lower() for name in DB_PROCEDURES}
    except Exception:
        pass

    views = []
    for name, meta in DB_VIEWS.items():
        key = name.lower()
        views.append({
            'name': name,
            'description': meta['description'],
            'installed': key in installed_views,
            'sql': view_sql.get(key) or meta['sql'].strip()
        })

    procedures = []
    for name, meta in DB_PROCEDURES.items():
        procedures.append({
            'name': name,
            'description': meta['description'],
            'params': meta['params'],
            'installed': name.lower() in installed_procs,
            'native': ACTIVE_ENGINE == 'mysql',
            'engine_note': ('Native MySQL stored procedure' if ACTIVE_ENGINE == 'mysql'
                            else 'Emulated procedure (SQLite has no native stored procedures)')
        })

    triggers = []
    for name, meta in DB_TRIGGERS.items():
        key = name.lower()
        db_row = installed_triggers.get(key) or {}
        triggers.append({
            'name': name,
            'description': meta['description'],
            'table': meta['table'],
            'timing': meta['timing'],
            'event': meta['event'],
            'installed': key in installed_triggers,
            'sql': ((db_row.get('sql') or db_row.get('action_statement'))
                    if isinstance(db_row, dict) else None),
            'tests': [k for k, v in DB_TRIGGER_TESTS.items()]
        })

    return {
        'engine': ACTIVE_ENGINE,
        'views': views,
        'procedures': procedures,
        'triggers': triggers,
        'trigger_tests': DB_TRIGGER_TESTS
    }


def preview_db_view(name, limit=25):
    """Return up to `limit` rows from a whitelisted database view."""
    if name not in DB_VIEWS:
        raise ValueError(f"Unknown view: {name}")
    limit = max(1, min(int(limit), 200))
    return query(f"SELECT * FROM {name} LIMIT {limit}")


def call_db_procedure(name, params=()):
    """Execute a stored procedure (native on MySQL, emulated on SQLite)."""
    if name not in DB_PROCEDURES:
        raise ValueError(f"Unknown stored procedure: {name}")
    meta = DB_PROCEDURES[name]
    if len(params) != len(meta['params']):
        raise ValueError(f"{name} expects {len(meta['params'])} parameter(s), got {len(params)}")

    if ACTIVE_ENGINE == 'sqlite':
        return meta['sqlite_handler'](params)

    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        placeholders = ', '.join(['%s'] * len(params))
        cur.execute(f"CALL {name}({placeholders})", tuple(params))
        rows = []
        if cur.description:
            rows = cur.fetchall()
        try:
            while cur.nextset():
                if cur.description:
                    rows.extend(cur.fetchall())
        except Exception:
            pass
        conn.commit()
        return rows
    finally:
        conn.close()


def run_db_trigger_test(test_key):
    """Exercise a trigger safely inside a transaction and roll it back."""
    if test_key not in DB_TRIGGER_TESTS:
        raise ValueError(f"Unknown trigger test: {test_key}")

    result = {
        'key': test_key,
        'title': DB_TRIGGER_TESTS[test_key]['title'],
        'passed': False,
        'details': ''
    }

    conn = get_db()
    try:
        if ACTIVE_ENGINE == 'sqlite':
            cur = conn.cursor()
            cur.execute("BEGIN TRANSACTION")
        else:
            cur = conn.cursor(dictionary=True)
            conn.start_transaction()

        try:
            if test_key == 'double_booking':
                cur.execute(adapt_sql(
                    "SELECT bs.booking_id, bs.seat_id, b.screening_id, b.customer_id "
                    "FROM booking_seat bs JOIN booking b ON b.booking_id = bs.booking_id "
                    "WHERE b.booking_status = 'CONFIRMED' AND bs.seat_status = 'BOOKED' LIMIT 1"
                ))
                row = cur.fetchone()
                if not row:
                    result['details'] = 'No confirmed booking seat available to test.'
                else:
                    row = dict(row) if not isinstance(row, dict) else row
                    ref = f"TRG-TEST-{int(datetime.now().timestamp())}"
                    cur.execute(adapt_sql(
                        "INSERT INTO booking (booking_reference, customer_id, screening_id, booking_date, total_amount, booking_status) "
                        "VALUES (%s, %s, %s, NOW(), 0, 'CONFIRMED')"
                    ), (ref, row['customer_id'], row['screening_id']))
                    temp_booking_id = cur.lastrowid
                    try:
                        cur.execute(adapt_sql(
                            "INSERT INTO booking_seat (booking_id, seat_id, ticket_price, seat_status) "
                            "VALUES (%s, %s, 0, 'BOOKED')"
                        ), (temp_booking_id, row['seat_id']))
                        result['details'] = 'Trigger did NOT block the duplicate seat insert.'
                    except Exception as exc:
                        result['passed'] = True
                        result['details'] = f"Duplicate seat blocked as expected: {exc}"

            elif test_key == 'screening_conflict':
                cur.execute(adapt_sql(
                    "SELECT screening_id, movie_id, screen_id, slot_id, screening_date, base_price "
                    "FROM screening WHERE status = 'SCHEDULED' LIMIT 1"
                ))
                row = cur.fetchone()
                if not row:
                    result['details'] = 'No scheduled screening available to test.'
                else:
                    row = dict(row) if not isinstance(row, dict) else row
                    try:
                        cur.execute(adapt_sql(
                            "INSERT INTO screening (movie_id, screen_id, slot_id, screening_date, base_price, status) "
                            "VALUES (%s, %s, %s, %s, %s, 'SCHEDULED')"
                        ), (row['movie_id'], row['screen_id'], row['slot_id'], row['screening_date'], row['base_price']))
                        result['details'] = 'Trigger did NOT block the conflicting screening insert.'
                    except Exception as exc:
                        result['passed'] = True
                        result['details'] = f"Conflicting showtime blocked as expected: {exc}"

            elif test_key == 'cancel_cascade':
                cur.execute(adapt_sql(
                    "SELECT b.booking_id FROM booking b "
                    "WHERE b.booking_status = 'CONFIRMED' "
                    "AND EXISTS (SELECT 1 FROM booking_seat bs WHERE bs.booking_id = b.booking_id) "
                    "LIMIT 1"
                ))
                row = cur.fetchone()
                if not row:
                    result['details'] = 'No confirmed booking available to test.'
                else:
                    row = dict(row) if not isinstance(row, dict) else row
                    booking_id = row['booking_id']
                    cur.execute(adapt_sql("UPDATE booking SET booking_status = 'CANCELLED' WHERE booking_id = %s"), (booking_id,))
                    cur.execute(adapt_sql(
                        "SELECT (SELECT COUNT(*) FROM booking_seat WHERE booking_id = %s AND seat_status = 'CANCELLED') AS cancelled_seats, "
                        "(SELECT COUNT(*) FROM booking_seat WHERE booking_id = %s) AS total_seats, "
                        "(SELECT COUNT(*) FROM ticket t JOIN booking_seat bs ON bs.booking_seat_id = t.booking_seat_id "
                        " WHERE bs.booking_id = %s AND t.ticket_status = 'CANCELLED') AS cancelled_tickets, "
                        "(SELECT COUNT(*) FROM ticket t JOIN booking_seat bs ON bs.booking_seat_id = t.booking_seat_id "
                        " WHERE bs.booking_id = %s) AS total_tickets, "
                        "(SELECT COUNT(*) FROM payment WHERE booking_id = %s AND payment_status = 'REFUNDED') AS refunded_payments, "
                        "(SELECT COUNT(*) FROM payment WHERE booking_id = %s) AS total_payments"
                    ), (booking_id, booking_id, booking_id, booking_id, booking_id, booking_id))
                    counts = dict(cur.fetchone())
                    cascade_ok = (counts['cancelled_seats'] == counts['total_seats']
                                  and counts['cancelled_tickets'] == counts['total_tickets']
                                  and (counts['total_payments'] == 0 or counts['refunded_payments'] == counts['total_payments']))
                    result['passed'] = cascade_ok
                    result['details'] = (
                        f"Booking #{booking_id}: {counts['cancelled_seats']}/{counts['total_seats']} seats, "
                        f"{counts['cancelled_tickets']}/{counts['total_tickets']} tickets, "
                        f"{counts['refunded_payments']}/{counts['total_payments']} payments updated by triggers."
                    )

            elif test_key == 'seat_count':
                cur.execute(adapt_sql(
                    "SELECT screen_id, total_seats FROM screen "
                    "WHERE EXISTS (SELECT 1 FROM seat WHERE seat.screen_id = screen.screen_id) LIMIT 1"
                ))
                row = cur.fetchone()
                if not row:
                    result['details'] = 'No screen with seats available to test.'
                else:
                    row = dict(row) if not isinstance(row, dict) else row
                    screen_id = row['screen_id']
                    before = int(row['total_seats'])
                    try:
                        cur.execute(adapt_sql(
                            "INSERT INTO seat (screen_id, category_id, row_label, seat_number, is_active) "
                            "VALUES (%s, 1, 'Z', 99, 1)"
                        ), (screen_id,))
                    except Exception as exc:
                        result['details'] = f"Could not insert test seat: {exc}"
                    else:
                        cur.execute(adapt_sql("SELECT total_seats FROM screen WHERE screen_id = %s"), (screen_id,))
                        after_row = cur.fetchone()
                        after = int((dict(after_row) if not isinstance(after_row, dict) else after_row)['total_seats'])
                        result['passed'] = after == before + 1
                        result['details'] = f"Screen #{screen_id} seat count moved {before} -> {after} after test seat insert."

            else:
                result['details'] = 'Unknown trigger test.'
        finally:
            try:
                conn.rollback()
            except Exception:
                pass
    except Exception as exc:
        result['details'] = f"Trigger test error: {exc}"
    finally:
        conn.close()

    return result

def init_sqlite_db():
    """Initializes the complete 17-table schema and seeds realistic BookMyShow data in SQLite."""
    conn = sqlite3.connect(SQLITE_DB_PATH)
    cur = conn.cursor()
    cur.execute('PRAGMA foreign_keys = OFF;')

    # Drop dependent database objects first
    for view_name in DB_VIEWS:
        cur.execute(f"DROP VIEW IF EXISTS {view_name};")
    for trigger_name in DB_SQLITE_TRIGGERS:
        cur.execute(f"DROP TRIGGER IF EXISTS {trigger_name};")

    # Drop existing tables
    tables = [
        'booking_concession', 'payment', 'ticket', 'booking_seat', 'booking',
        'concession_item', 'customer', 'screening', 'slot', 'movie_genre',
        'movie', 'genre', 'seat', 'seat_category', 'screen', 'theater', 'city'
    ]
    for t in tables:
        cur.execute(f"DROP TABLE IF EXISTS {t};")

    cur.execute('PRAGMA foreign_keys = ON;')

    # 1. City
    cur.execute("""
    CREATE TABLE city (
        city_id INTEGER PRIMARY KEY AUTOINCREMENT,
        city_name TEXT NOT NULL UNIQUE,
        state TEXT NOT NULL
    );
    """)

    # 2. Theater
    cur.execute("""
    CREATE TABLE theater (
        theater_id INTEGER PRIMARY KEY AUTOINCREMENT,
        city_id INTEGER NOT NULL,
        theater_name TEXT NOT NULL,
        address TEXT NOT NULL,
        location_area TEXT NOT NULL,
        FOREIGN KEY (city_id) REFERENCES city(city_id) ON DELETE CASCADE
    );
    """)

    # 3. Screen
    cur.execute("""
    CREATE TABLE screen (
        screen_id INTEGER PRIMARY KEY AUTOINCREMENT,
        theater_id INTEGER NOT NULL,
        screen_name TEXT NOT NULL,
        screen_type TEXT DEFAULT 'Standard 2D',
        total_seats INTEGER DEFAULT 0,
        FOREIGN KEY (theater_id) REFERENCES theater(theater_id) ON DELETE CASCADE
    );
    """)

    # 4. Seat Category
    cur.execute("""
    CREATE TABLE seat_category (
        category_id INTEGER PRIMARY KEY AUTOINCREMENT,
        category_name TEXT NOT NULL UNIQUE,
        price_multiplier REAL NOT NULL DEFAULT 1.00,
        description TEXT
    );
    """)

    # 5. Seat
    cur.execute("""
    CREATE TABLE seat (
        seat_id INTEGER PRIMARY KEY AUTOINCREMENT,
        screen_id INTEGER NOT NULL,
        category_id INTEGER NOT NULL,
        row_label TEXT NOT NULL,
        seat_number INTEGER NOT NULL,
        is_active INTEGER DEFAULT 1,
        UNIQUE (screen_id, row_label, seat_number),
        FOREIGN KEY (screen_id) REFERENCES screen(screen_id) ON DELETE CASCADE,
        FOREIGN KEY (category_id) REFERENCES seat_category(category_id)
    );
    """)

    # 6. Genre
    cur.execute("""
    CREATE TABLE genre (
        genre_id INTEGER PRIMARY KEY AUTOINCREMENT,
        genre_name TEXT NOT NULL UNIQUE
    );
    """)

    # 7. Movie
    cur.execute("""
    CREATE TABLE movie (
        movie_id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        synopsis TEXT,
        language TEXT DEFAULT 'English',
        duration_minutes INTEGER NOT NULL,
        release_date TEXT,
        rating TEXT DEFAULT 'UA',
        dimension TEXT DEFAULT '2D'
    );
    """)

    # 8. Movie Genre
    cur.execute("""
    CREATE TABLE movie_genre (
        movie_id INTEGER NOT NULL,
        genre_id INTEGER NOT NULL,
        PRIMARY KEY (movie_id, genre_id),
        FOREIGN KEY (movie_id) REFERENCES movie(movie_id) ON DELETE CASCADE,
        FOREIGN KEY (genre_id) REFERENCES genre(genre_id) ON DELETE CASCADE
    );
    """)

    # 9. Slot
    cur.execute("""
    CREATE TABLE slot (
        slot_id INTEGER PRIMARY KEY AUTOINCREMENT,
        slot_name TEXT NOT NULL,
        start_time TEXT NOT NULL
    );
    """)

    # 10. Screening
    cur.execute("""
    CREATE TABLE screening (
        screening_id INTEGER PRIMARY KEY AUTOINCREMENT,
        movie_id INTEGER NOT NULL,
        screen_id INTEGER NOT NULL,
        slot_id INTEGER NOT NULL,
        screening_date TEXT NOT NULL,
        base_price REAL NOT NULL,
        status TEXT DEFAULT 'SCHEDULED',
        FOREIGN KEY (movie_id) REFERENCES movie(movie_id) ON DELETE CASCADE,
        FOREIGN KEY (screen_id) REFERENCES screen(screen_id) ON DELETE CASCADE,
        FOREIGN KEY (slot_id) REFERENCES slot(slot_id)
    );
    """)

    # 11. Customer
    cur.execute("""
    CREATE TABLE customer (
        customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        phone TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'CUSTOMER',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 12. Concession Item
    cur.execute("""
    CREATE TABLE concession_item (
        item_id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_name TEXT NOT NULL,
        category TEXT NOT NULL,
        price REAL NOT NULL
    );
    """)

    # 13. Booking
    cur.execute("""
    CREATE TABLE booking (
        booking_id INTEGER PRIMARY KEY AUTOINCREMENT,
        booking_reference TEXT NOT NULL UNIQUE,
        customer_id INTEGER NOT NULL,
        screening_id INTEGER NOT NULL,
        booking_date TEXT DEFAULT CURRENT_TIMESTAMP,
        total_amount REAL NOT NULL,
        booking_status TEXT DEFAULT 'CONFIRMED',
        FOREIGN KEY (customer_id) REFERENCES customer(customer_id),
        FOREIGN KEY (screening_id) REFERENCES screening(screening_id)
    );
    """)

    # 14. Booking Seat
    cur.execute("""
    CREATE TABLE booking_seat (
        booking_seat_id INTEGER PRIMARY KEY AUTOINCREMENT,
        booking_id INTEGER NOT NULL,
        seat_id INTEGER NOT NULL,
        ticket_price REAL NOT NULL,
        seat_status TEXT DEFAULT 'BOOKED',
        UNIQUE (booking_id, seat_id),
        FOREIGN KEY (booking_id) REFERENCES booking(booking_id) ON DELETE CASCADE,
        FOREIGN KEY (seat_id) REFERENCES seat(seat_id)
    );
    """)

    # 15. Ticket
    cur.execute("""
    CREATE TABLE ticket (
        ticket_id INTEGER PRIMARY KEY AUTOINCREMENT,
        booking_seat_id INTEGER NOT NULL UNIQUE,
        ticket_code TEXT NOT NULL UNIQUE,
        issued_at TEXT DEFAULT CURRENT_TIMESTAMP,
        ticket_status TEXT DEFAULT 'ACTIVE',
        FOREIGN KEY (booking_seat_id) REFERENCES booking_seat(booking_seat_id) ON DELETE CASCADE
    );
    """)

    # 16. Payment
    cur.execute("""
    CREATE TABLE payment (
        payment_id INTEGER PRIMARY KEY AUTOINCREMENT,
        booking_id INTEGER NOT NULL,
        payment_time TEXT DEFAULT CURRENT_TIMESTAMP,
        amount REAL NOT NULL,
        payment_method TEXT NOT NULL,
        payment_status TEXT DEFAULT 'SUCCESS',
        transaction_reference TEXT UNIQUE,
        FOREIGN KEY (booking_id) REFERENCES booking(booking_id) ON DELETE CASCADE
    );
    """)

    # 17. Booking Concession
    cur.execute("""
    CREATE TABLE booking_concession (
        booking_concession_id INTEGER PRIMARY KEY AUTOINCREMENT,
        booking_id INTEGER NOT NULL,
        item_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL DEFAULT 1,
        subtotal REAL NOT NULL,
        FOREIGN KEY (booking_id) REFERENCES booking(booking_id) ON DELETE CASCADE,
        FOREIGN KEY (item_id) REFERENCES concession_item(item_id)
    );
    """)

    # SEED DATA
    # Cities
    cur.executemany("INSERT INTO city (city_name, state) VALUES (?, ?);", [
        ('Hyderabad', 'Telangana'),
        ('Bengaluru', 'Karnataka'),
        ('Mumbai', 'Maharashtra')
    ])

    # Theaters
    cur.executemany("INSERT INTO theater (city_id, theater_name, address, location_area) VALUES (?, ?, ?, ?);", [
        (1, 'CineSphere Luxe Banjara', 'Road No. 2, Banjara Hills', 'Banjara Hills'),
        (1, 'CineSphere IMAX Forum Mall', 'Kukatpally Housing Board Colony', 'Kukatpally'),
        (1, 'CineSphere Riverside Gachibowli', 'Financial District, Nanakramguda', 'Gachibowli'),
        (2, 'CineSphere Forum Koramangala', 'Hosur Road, 7th Block, Koramangala', 'Koramangala'),
        (2, 'CineSphere Orion Mall', 'Dr Rajkumar Rd, Rajajinagar', 'Rajajinagar'),
        (3, 'CineSphere Palladium Luxe', 'High Street Phoenix, Lower Parel', 'Lower Parel')
    ])

    # Screens
    cur.executemany("INSERT INTO screen (theater_id, screen_name, screen_type, total_seats) VALUES (?, ?, ?, ?);", [
        (1, 'Screen 1 (IMAX 3D)', 'IMAX 3D', 60),
        (1, 'Screen 2 (Dolby Atmos)', 'Dolby Atmos 2D', 60),
        (1, 'Screen 3 (Gold Class)', 'VIP Gold Class', 36),
        (2, 'IMAX Laser Experience', 'IMAX Laser', 60),
        (2, 'Screen 2 (4DX)', '4DX Motion', 60),
        (3, 'Screen 1 (Dolby Vision)', 'Dolby Vision 4K', 60),
        (4, 'Screen 1 (IMAX)', 'IMAX 3D', 60),
        (5, 'Screen 1 (PXL Atmos)', 'Dolby Atmos', 60),
        (6, 'Screen 1 (Luxe Insignia)', 'VIP Gold Class', 36)
    ])

    # Seat Categories
    cur.executemany("INSERT INTO seat_category (category_name, price_multiplier, description) VALUES (?, ?, ?);", [
        ('VIP Recliner', 1.50, 'Plush leather motor-recliners with extra legroom'),
        ('Prime Gold', 1.20, 'Premium viewing angle with cushioned club seats'),
        ('Classic Silver', 1.00, 'Standard comfortable cinema seating')
    ])

    # Genres
    cur.executemany("INSERT INTO genre (genre_name) VALUES (?);", [
        ('Action',), ('Sci-Fi',), ('Drama',), ('Adventure',), ('Comedy',), ('Thriller',)
    ])

    # Movies
    cur.executemany("INSERT INTO movie (title, synopsis, language, duration_minutes, release_date, rating, dimension) VALUES (?, ?, ?, ?, ?, ?, ?);", [
        ('The Martian', 'An astronaut stranded on Mars uses his scientific knowledge and determination to survive and find a way back home.', 'English', 144, '2015-10-02', 'UA', '2D, 3D'),
        ('Project Hail Mary', 'A lone astronaut awakens on a desperate mission to save Earth and uncover the cosmic mystery threatening humanity.', 'English', 150, '2026-03-20', 'UA', 'IMAX 3D'),
        ('Gran Turismo', 'A skilled gamer gets the opportunity to turn his virtual racing abilities into a real-world motorsport career.', 'English', 134, '2023-08-25', 'UA', '4DX, 2D'),
        ('Spider-Man: Brand New Day', 'Spider-Man faces a new chapter of challenges and adventures as he protects his city from emerging high-tech threats.', 'English', 140, '2026-07-31', 'UA', 'IMAX 3D, 2D'),
        ('Interstellar', 'A team of explorers travel through a wormhole in space in an attempt to ensure humanity survival.', 'English', 169, '2014-11-07', 'UA', 'IMAX 70mm'),
        ('Dune: Part Two', 'Paul Atreides unites with Chani and the Fremen while seeking revenge against the conspirators who destroyed his family.', 'English', 166, '2024-03-01', 'UA', 'IMAX 3D')
    ])

    # Movie Genres
    cur.executemany("INSERT INTO movie_genre (movie_id, genre_id) VALUES (?, ?);", [
        (1, 2), (1, 3),
        (2, 2), (2, 4),
        (3, 1), (3, 3),
        (4, 1), (4, 2),
        (5, 2), (5, 3),
        (6, 1), (6, 2)
    ])

    # Slots
    cur.executemany("INSERT INTO slot (slot_name, start_time) VALUES (?, ?);", [
        ('Morning Show', '10:00:00'),
        ('Matinee Show', '13:30:00'),
        ('Evening Prime', '17:15:00'),
        ('Night Show', '20:45:00'),
        ('Late Night Show', '23:15:00')
    ])

    # Concession Items
    cur.executemany("INSERT INTO concession_item (item_name, category, price) VALUES (?, ?, ?);", [
        ('Jumbo Caramel Popcorn', 'Popcorn', 260.00),
        ('Salted Butter Popcorn', 'Popcorn', 220.00),
        ('Loaded Cheese Nachos with Salsa', 'Snacks', 240.00),
        ('Fountain Cola 600ml', 'Beverages', 150.00),
        ('Iced Cold Coffee', 'Beverages', 180.00),
        ('Couple Movie Combo (Jumbo Popcorn + 2 Drinks)', 'Combos', 480.00)
    ])

    # Populate Realistic Seats
    # Screens 1, 2, 4, 5, 6, 7, 8: 60 seats (Row A: Recliner 1-10; Rows B-D: Prime Gold 1-10; Rows E-F: Classic Silver 1-10)
    # Screens 3, 9: 36 seats (VIP Gold Class: Rows A-C, 1-12)
    seats_to_insert = []
    for s_id in range(1, 10):
        if s_id in (3, 9):
            for row in ('A', 'B', 'C'):
                for num in range(1, 13):
                    seats_to_insert.append((s_id, 1, row, num))
        else:
            # Row A: Recliner (cat 1)
            for num in range(1, 11):
                seats_to_insert.append((s_id, 1, 'A', num))
            # Rows B, C, D: Prime Gold (cat 2)
            for row in ('B', 'C', 'D'):
                for num in range(1, 11):
                    seats_to_insert.append((s_id, 2, row, num))
            # Rows E, F: Classic Silver (cat 3)
            for row in ('E', 'F'):
                for num in range(1, 11):
                    seats_to_insert.append((s_id, 3, row, num))

    cur.executemany("INSERT INTO seat (screen_id, category_id, row_label, seat_number) VALUES (?, ?, ?, ?);", seats_to_insert)

    # Users
    demo_pw = generate_password_hash('Demo@123')
    mgr_pw = generate_password_hash('Manager@123')
    cur.executemany("INSERT INTO customer (full_name, email, phone, password_hash, role) VALUES (?, ?, ?, ?, ?);", [
        ('Vikram Malhotra (Operations Manager)', 'manager@cinesphere.com', '9876543210', mgr_pw, 'MANAGER'),
        ('Arjun Kumar', 'arjun@example.com', '9000000001', demo_pw, 'CUSTOMER'),
        ('Priya Sharma', 'priya@example.com', '9000000002', demo_pw, 'CUSTOMER'),
        ('Rahul Verma', 'rahul@example.com', '9000000003', demo_pw, 'CUSTOMER'),
        ('Sneha Reddy', 'sneha@example.com', '9000000004', demo_pw, 'CUSTOMER')
    ])

    # Screenings across multiple dates and theaters
    today = date.today().isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    day_after = (date.today() + timedelta(days=2)).isoformat()

    screenings = [
        # The Martian (Today)
        (1, 1, 1, today, 250.00, 'SCHEDULED'),
        (1, 1, 3, today, 320.00, 'SCHEDULED'),
        (1, 1, 4, today, 350.00, 'SCHEDULED'),
        (1, 2, 2, today, 220.00, 'SCHEDULED'),
        # Project Hail Mary (Today)
        (2, 1, 2, today, 300.00, 'SCHEDULED'),
        (2, 4, 3, today, 320.00, 'SCHEDULED'),
        (2, 6, 4, today, 280.00, 'SCHEDULED'),
        # Gran Turismo (Today)
        (3, 5, 2, today, 260.00, 'SCHEDULED'),
        (3, 2, 4, today, 240.00, 'SCHEDULED'),
        # Spider-Man: Brand New Day (Today)
        (4, 1, 5, today, 380.00, 'SCHEDULED'),
        (4, 4, 4, today, 360.00, 'SCHEDULED'),
        (4, 7, 3, today, 320.00, 'SCHEDULED'),
        # Interstellar (Today)
        (5, 4, 1, today, 300.00, 'SCHEDULED'),
        (5, 7, 4, today, 340.00, 'SCHEDULED'),
        # Dune: Part Two (Tomorrow)
        (6, 1, 3, tomorrow, 350.00, 'SCHEDULED'),
        (6, 4, 3, tomorrow, 350.00, 'SCHEDULED'),
        (6, 8, 4, tomorrow, 320.00, 'SCHEDULED'),
        # Project Hail Mary (Day after)
        (2, 1, 4, day_after, 350.00, 'SCHEDULED'),
        (4, 2, 3, day_after, 280.00, 'SCHEDULED')
    ]
    cur.executemany("INSERT INTO screening (movie_id, screen_id, slot_id, screening_date, base_price, status) VALUES (?, ?, ?, ?, ?, ?);", screenings)

    # Initial Bookings for Manager Audit Log
    now_ts = datetime.now()
    t1 = (now_ts - timedelta(hours=4)).strftime('%Y-%m-%d %H:%M:%S')
    t2 = (now_ts - timedelta(hours=2)).strftime('%Y-%m-%d %H:%M:%S')
    t3 = (now_ts - timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')

    # Booking 1: Arjun Kumar booked seats 15 & 16 on screening 2
    cur.execute("""
    INSERT INTO booking (booking_reference, customer_id, screening_id, booking_date, total_amount, booking_status)
    VALUES (?, ?, ?, ?, ?, ?);
    """, ('CS-2026-9081', 2, 2, t1, 768.00, 'CONFIRMED'))
    b1_id = cur.lastrowid

    cur.execute("INSERT INTO booking_seat (booking_id, seat_id, ticket_price, seat_status) VALUES (?, ?, ?, ?);", (b1_id, 15, 384.00, 'BOOKED'))
    bs1_id = cur.lastrowid
    cur.execute("INSERT INTO booking_seat (booking_id, seat_id, ticket_price, seat_status) VALUES (?, ?, ?, ?);", (b1_id, 16, 384.00, 'BOOKED'))
    bs2_id = cur.lastrowid

    cur.execute("INSERT INTO ticket (booking_seat_id, ticket_code, issued_at, ticket_status) VALUES (?, ?, ?, ?);", (bs1_id, 'TCK-HYD-9081-01', t1, 'ACTIVE'))
    cur.execute("INSERT INTO ticket (booking_seat_id, ticket_code, issued_at, ticket_status) VALUES (?, ?, ?, ?);", (bs2_id, 'TCK-HYD-9081-02', t1, 'ACTIVE'))

    cur.execute("INSERT INTO payment (booking_id, payment_time, amount, payment_method, payment_status, transaction_reference) VALUES (?, ?, ?, ?, ?, ?);",
                (b1_id, t1, 768.00, 'UPI', 'SUCCESS', 'TXN-UPI-9823419081'))

    # Booking 2: Priya Sharma booked seat 5 on screening 5
    cur.execute("""
    INSERT INTO booking (booking_reference, customer_id, screening_id, booking_date, total_amount, booking_status)
    VALUES (?, ?, ?, ?, ?, ?);
    """, ('CS-2026-9142', 3, 5, t2, 450.00, 'CONFIRMED'))
    b2_id = cur.lastrowid

    cur.execute("INSERT INTO booking_seat (booking_id, seat_id, ticket_price, seat_status) VALUES (?, ?, ?, ?);", (b2_id, 5, 450.00, 'BOOKED'))
    bs3_id = cur.lastrowid

    cur.execute("INSERT INTO ticket (booking_seat_id, ticket_code, issued_at, ticket_status) VALUES (?, ?, ?, ?);", (bs3_id, 'TCK-HYD-9142-01', t2, 'ACTIVE'))
    cur.execute("INSERT INTO payment (booking_id, payment_time, amount, payment_method, payment_status, transaction_reference) VALUES (?, ?, ?, ?, ?, ?);",
                (b2_id, t2, 450.00, 'CARD', 'SUCCESS', 'TXN-CARD-8839109142'))

    # Booking 3: Rahul Verma booked & cancelled
    cur.execute("""
    INSERT INTO booking (booking_reference, customer_id, screening_id, booking_date, total_amount, booking_status)
    VALUES (?, ?, ?, ?, ?, ?);
    """, ('CS-2026-8803', 4, 1, t3, 250.00, 'CANCELLED'))
    b3_id = cur.lastrowid

    cur.execute("INSERT INTO booking_seat (booking_id, seat_id, ticket_price, seat_status) VALUES (?, ?, ?, ?);", (b3_id, 22, 250.00, 'CANCELLED'))
    bs4_id = cur.lastrowid

    cur.execute("INSERT INTO ticket (booking_seat_id, ticket_code, issued_at, ticket_status) VALUES (?, ?, ?, ?);", (bs4_id, 'TCK-HYD-8803-01', t3, 'CANCELLED'))
    cur.execute("INSERT INTO payment (booking_id, payment_time, amount, payment_method, payment_status, transaction_reference) VALUES (?, ?, ?, ?, ?, ?);",
                (b3_id, t3, 250.00, 'UPI', 'REFUNDED', 'TXN-UPI-7718298803'))

    # Install all views and triggers after the seed data is in place
    _install_sqlite_db_objects(cur)

    conn.commit()
    conn.close()
    print("SQLite database successfully initialized with full BookMyShow schema and seed data!")
    try:
        import json_sync
        json_sync.sync_all("INITIALIZE_DATABASE", "system", "Database initialized with full 17-table schema and BookMyShow seed data", user="System Initializer")
    except Exception as e:
        print(f"Notice: JSON sync on init: {e}")

if __name__ == '__main__':
    print(f"Active Engine: {ACTIVE_ENGINE}")
    init_sqlite_db()
