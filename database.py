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

def init_sqlite_db():
    """Initializes the complete 17-table schema and seeds realistic BookMyShow data in SQLite."""
    conn = sqlite3.connect(SQLITE_DB_PATH)
    cur = conn.cursor()
    cur.execute('PRAGMA foreign_keys = OFF;')

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
