import os
import random
import string
from functools import wraps
from datetime import date, datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort, jsonify, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

import database
import json_sync

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'cinesphere-dev-secret-key-2026')

# Check and initialize database if using SQLite and empty
if database.ACTIVE_ENGINE == 'sqlite':
    if not os.path.exists(database.SQLITE_DB_PATH) or os.path.getsize(database.SQLITE_DB_PATH) == 0:
        database.init_sqlite_db()
    else:
        # Check if table exists
        try:
            cnt = database.query("SELECT COUNT(*) as c FROM sqlite_master WHERE type='table' AND name='screening'", one=True)
            if not cnt or cnt['c'] == 0:
                database.init_sqlite_db()
        except Exception:
            database.init_sqlite_db()

def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if 'customer_id' not in session:
            flash('Please log in to continue.')
            return redirect(url_for('login', next=request.path))
        return fn(*args, **kwargs)
    return wrapped

def manager_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if 'customer_id' not in session:
            flash('Manager access required. Please log in with a manager account.')
            return redirect(url_for('login', next=request.path))
        if session.get('role') not in ('MANAGER', 'ADMIN'):
            flash('Access restricted to Cinema Managers and Administrators.')
            return redirect(url_for('index'))
        return fn(*args, **kwargs)
    return wrapped

def safe_next(value):
    return value if value and value.startswith('/') and not value.startswith('//') else url_for('index')

def generate_booking_ref():
    chars = string.ascii_uppercase + string.digits
    suffix = ''.join(random.choices(chars, k=6))
    return f"CS-{date.today().year}-{suffix}"

def generate_ticket_code(theater_city, booking_id, seat_num):
    city_code = theater_city[:3].upper() if theater_city else 'CIN'
    return f"TCK-{city_code}-{booking_id:04d}-{seat_num:02d}"

@app.context_processor
def inject_global_data():
    cities = database.query("SELECT * FROM city ORDER BY city_name")
    selected_city = request.args.get('city') or session.get('selected_city') or 'Hyderabad'
    session['selected_city'] = selected_city
    return {
        'all_cities': cities,
        'current_city': selected_city,
        'user_role': session.get('role', 'GUEST'),
        'user_name': session.get('customer_name', ''),
        'active_engine': database.ACTIVE_ENGINE
    }

# ==========================================
# PUBLIC / CUSTOMER ROUTES
# ==========================================

@app.route('/')
def index():
    city_filter = request.args.get('city') or session.get('selected_city') or 'Hyderabad'
    genre_filter = request.args.get('genre')
    search_query = request.args.get('q', '').strip()

    sql = """
        SELECT m.*, GROUP_CONCAT(g.genre_name ORDER BY g.genre_name SEPARATOR ', ') AS genres
        FROM movie m
        LEFT JOIN movie_genre mg ON mg.movie_id = m.movie_id
        LEFT JOIN genre g ON g.genre_id = mg.genre_id
        GROUP BY m.movie_id
        ORDER BY m.title
    """
    movies = database.query(sql)

    # Filter by genre or search query if provided
    if genre_filter:
        movies = [m for m in movies if m.get('genres') and genre_filter.lower() in m['genres'].lower()]
    if search_query:
        movies = [m for m in movies if search_query.lower() in m['title'].lower() or (m.get('genres') and search_query.lower() in m['genres'].lower())]

    genres = database.query("SELECT * FROM genre ORDER BY genre_name")
    theaters = database.query(
        "SELECT t.*, c.city_name FROM theater t JOIN city c ON c.city_id = t.city_id WHERE c.city_name = %s ORDER BY t.theater_name",
        (city_filter,)
    )

    return render_template('index.html', movies=movies, genres=genres, theaters=theaters, selected_genre=genre_filter, search_query=search_query)

@app.route('/theaters')
def theaters_list():
    city_filter = request.args.get('city') or session.get('selected_city') or 'Hyderabad'
    theaters = database.query(
        """
        SELECT t.*, c.city_name, COUNT(DISTINCT sc.screen_id) AS screen_count
        FROM theater t
        JOIN city c ON c.city_id = t.city_id
        LEFT JOIN screen sc ON sc.theater_id = t.theater_id
        WHERE c.city_name = %s
        GROUP BY t.theater_id
        ORDER BY t.theater_name
        """,
        (city_filter,)
    )

    # Attach active screenings for each theater
    for t in theaters:
        t['screens'] = database.query("SELECT * FROM screen WHERE theater_id = %s ORDER BY screen_name", (t['theater_id'],))
        t['today_screenings'] = database.query(
            """
            SELECT s.screening_id, s.screening_date, s.base_price, m.title, m.movie_id, m.duration_minutes,
                   sl.slot_name, sl.start_time, sc.screen_name, sc.screen_type
            FROM screening s
            JOIN movie m ON m.movie_id = s.movie_id
            JOIN screen sc ON sc.screen_id = s.screen_id
            JOIN slot sl ON sl.slot_id = s.slot_id
            WHERE sc.theater_id = %s AND s.screening_date >= CURDATE() AND s.status = 'SCHEDULED'
            ORDER BY s.screening_date, sl.start_time
            LIMIT 8
            """,
            (t['theater_id'],)
        )

    return render_template('theaters.html', theaters=theaters, city=city_filter)

@app.route('/movie/<int:movie_id>')
def movie_details(movie_id):
    movie = database.query('SELECT * FROM movie WHERE movie_id = %s', (movie_id,), one=True)
    if not movie:
        abort(404)
    movie['genres'] = database.query(
        'SELECT g.genre_name FROM genre g JOIN movie_genre mg ON mg.genre_id = g.genre_id WHERE mg.movie_id = %s',
        (movie_id,)
    )
    # Available formats & cities
    cities_showing = database.query(
        """
        SELECT DISTINCT c.city_name
        FROM screening s
        JOIN screen sc ON sc.screen_id = s.screen_id
        JOIN theater t ON t.theater_id = sc.theater_id
        JOIN city c ON c.city_id = t.city_id
        WHERE s.movie_id = %s AND s.screening_date >= CURDATE() AND s.status = 'SCHEDULED'
        """,
        (movie_id,)
    )
    return render_template('movie_details.html', movie=movie, cities_showing=cities_showing)

@app.route('/movie/<int:movie_id>/showtimes')
def showtimes(movie_id):
    movie = database.query('SELECT * FROM movie WHERE movie_id = %s', (movie_id,), one=True)
    if not movie:
        abort(404)

    city_filter = request.args.get('city') or session.get('selected_city') or 'Hyderabad'
    date_filter = request.args.get('date') or date.today().isoformat()

    # Generate 4 selectable dates (Today, Tomorrow, Day+2, Day+3)
    date_options = []
    base_d = date.today()
    for i in range(4):
        d = base_d + timedelta(days=i)
        iso = d.isoformat()
        date_options.append({
            'date_str': iso,
            'day_name': 'Today' if i == 0 else ('Tomorrow' if i == 1 else d.strftime('%a')),
            'display_date': d.strftime('%d %b'),
            'is_selected': (iso == date_filter)
        })

    # Fetch showtimes grouped by Theater
    sql = """
        SELECT s.screening_id, s.screening_date, s.base_price, s.status,
               sl.slot_id, sl.slot_name, sl.start_time,
               t.theater_id, t.theater_name, t.address, t.location_area, c.city_name,
               sc.screen_id, sc.screen_name, sc.screen_type
        FROM screening s
        JOIN slot sl ON sl.slot_id = s.slot_id
        JOIN screen sc ON sc.screen_id = s.screen_id
        JOIN theater t ON t.theater_id = sc.theater_id
        JOIN city c ON c.city_id = t.city_id
        WHERE s.movie_id = %s AND s.screening_date = %s AND c.city_name = %s AND s.status = 'SCHEDULED'
        ORDER BY t.theater_name, sc.screen_name, sl.start_time
    """
    raw_shows = database.query(sql, (movie_id, date_filter, city_filter))

    # Group by Theater
    theater_map = {}
    for show in raw_shows:
        tid = show['theater_id']
        if tid not in theater_map:
            theater_map[tid] = {
                'theater_name': show['theater_name'],
                'address': show['address'],
                'location_area': show['location_area'],
                'city_name': show['city_name'],
                'shows': []
            }
        theater_map[tid]['shows'].append(show)

    theaters_list = list(theater_map.values())

    return render_template(
        'showtimes.html',
        movie=movie,
        theaters_list=theaters_list,
        date_options=date_options,
        current_date=date_filter,
        current_city=city_filter
    )

@app.route('/show/<int:screening_id>/seats')
@login_required
def seats(screening_id):
    screening = database.query(
        """
        SELECT s.*, m.title, m.dimension, t.theater_name, t.address, t.location_area, c.city_name,
               sc.screen_name, sc.screen_type, sl.slot_name, sl.start_time
        FROM screening s
        JOIN movie m ON m.movie_id = s.movie_id
        JOIN screen sc ON sc.screen_id = s.screen_id
        JOIN theater t ON t.theater_id = sc.theater_id
        JOIN city c ON c.city_id = t.city_id
        JOIN slot sl ON sl.slot_id = s.slot_id
        WHERE s.screening_id = %s AND s.status = 'SCHEDULED'
        """,
        (screening_id,),
        one=True
    )
    if not screening:
        abort(404)

    # Fetch all seats for this screen with category multiplier & pricing
    seats = database.query(
        """
        SELECT s.*, c.category_name, c.price_multiplier,
               ROUND(%s * c.price_multiplier, 2) AS seat_price
        FROM seat s
        JOIN seat_category c ON c.category_id = s.category_id
        WHERE s.screen_id = %s AND s.is_active = 1
        ORDER BY s.row_label, s.seat_number
        """,
        (screening['base_price'], screening['screen_id'])
    )

    # Booked seat IDs for this screening
    booked = database.query(
        """
        SELECT bs.seat_id
        FROM booking_seat bs
        JOIN booking b ON b.booking_id = bs.booking_id
        WHERE b.screening_id = %s AND b.booking_status = 'CONFIRMED' AND bs.seat_status = 'BOOKED'
        """,
        (screening_id,)
    )
    booked_seat_ids = [x['seat_id'] for x in booked]

    # Categories present for legend
    categories = database.query(
        """
        SELECT DISTINCT c.category_name, c.price_multiplier,
               ROUND(%s * c.price_multiplier, 2) AS sample_price
        FROM seat s
        JOIN seat_category c ON c.category_id = s.category_id
        WHERE s.screen_id = %s
        ORDER BY c.price_multiplier DESC
        """,
        (screening['base_price'], screening['screen_id'])
    )

    return render_template(
        'seats.html',
        screening=screening,
        seats=seats,
        booked_seat_ids=booked_seat_ids,
        categories=categories
    )

@app.route('/show/<int:screening_id>/booking', methods=['GET', 'POST'])
@login_required
def booking_review(screening_id):
    ids = request.form.getlist('seat_ids') if request.method == 'POST' else request.args.getlist('seat_ids')
    try:
        ids = list(dict.fromkeys(int(x) for x in ids))
    except ValueError:
        ids = []

    if not ids:
        flash('Please choose at least one seat to proceed.')
        return redirect(url_for('seats', screening_id=screening_id))

    screening = database.query(
        """
        SELECT s.*, m.title, t.theater_name, t.address, c.city_name,
               sc.screen_name, sc.screen_type, sl.slot_name, sl.start_time
        FROM screening s
        JOIN movie m ON m.movie_id = s.movie_id
        JOIN screen sc ON sc.screen_id = s.screen_id
        JOIN theater t ON t.theater_id = sc.theater_id
        JOIN city c ON c.city_id = t.city_id
        JOIN slot sl ON sl.slot_id = s.slot_id
        WHERE s.screening_id = %s AND s.status = 'SCHEDULED'
        """,
        (screening_id,),
        one=True
    )
    if not screening:
        abort(404)

    marks = ','.join(['%s'] * len(ids))
    selected_seats = database.query(
        f"""
        SELECT s.*, c.category_name, c.price_multiplier,
               ROUND(%s * c.price_multiplier, 2) AS seat_price
        FROM seat s
        JOIN seat_category c ON c.category_id = s.category_id
        WHERE s.screen_id = %s AND s.seat_id IN ({marks})
        ORDER BY s.row_label, s.seat_number
        """,
        (screening['base_price'], screening['screen_id'], *ids)
    )

    if len(selected_seats) != len(ids):
        flash('One or more selected seats are invalid.')
        return redirect(url_for('seats', screening_id=screening_id))

    # Verify none are booked
    occupied = database.query(
        f"""
        SELECT bs.seat_id
        FROM booking_seat bs
        JOIN booking b ON b.booking_id = bs.booking_id
        WHERE b.screening_id = %s AND b.booking_status = 'CONFIRMED' AND bs.seat_status = 'BOOKED' AND bs.seat_id IN ({marks})
        """,
        (screening_id, *ids)
    )
    if occupied:
        flash('One or more selected seats were just booked by another user. Please re-select.')
        return redirect(url_for('seats', screening_id=screening_id))

    # Calculate total seat amount
    seats_subtotal = sum(float(s['seat_price']) for s in selected_seats)

    # Concession snacks
    concessions = database.query("SELECT * FROM concession_item ORDER BY category, price")

    return render_template(
        'booking.html',
        screening=screening,
        seats=selected_seats,
        selected_seat_ids=ids,
        seats_subtotal=seats_subtotal,
        concessions=concessions
    )

@app.route('/create-booking', methods=['POST'])
@login_required
def create_booking():
    try:
        screening_id = int(request.form.get('screening_id', ''))
        ids = list(dict.fromkeys(int(x) for x in request.form.getlist('seat_ids')))
    except ValueError:
        abort(400)

    method = request.form.get('payment_method', 'UPI')
    if not ids or method not in ('UPI', 'CARD', 'NET_BANKING', 'CASH'):
        flash('Invalid booking parameters.')
        return redirect(url_for('index'))

    # Parse concessions if any
    concession_items = []
    concession_total = 0.0
    all_concessions = database.query("SELECT * FROM concession_item")
    concession_map = {c['item_id']: c for c in all_concessions}

    for item_id, item_info in concession_map.items():
        qty_str = request.form.get(f'qty_{item_id}', '0')
        try:
            qty = int(qty_str)
            if qty > 0:
                sub = float(item_info['price']) * qty
                concession_total += sub
                concession_items.append((item_id, qty, sub))
        except ValueError:
            pass

    conn = database.get_db()
    cur = conn.cursor()
    try:
        if database.ACTIVE_ENGINE == 'sqlite':
            cur.execute("BEGIN TRANSACTION")
        else:
            conn.start_transaction()

        # Lock/fetch screening info
        cur.execute(database.adapt_sql(
            """
            SELECT s.*, m.title, sc.screen_id, t.city_id, c.city_name
            FROM screening s
            JOIN movie m ON m.movie_id = s.movie_id
            JOIN screen sc ON sc.screen_id = s.screen_id
            JOIN theater t ON t.theater_id = sc.theater_id
            JOIN city c ON c.city_id = t.city_id
            WHERE s.screening_id = %s AND s.status = 'SCHEDULED'
            """
        ), (screening_id,))
        show = cur.fetchone()
        if not show:
            conn.rollback()
            flash('The selected screening is unavailable.')
            return redirect(url_for('index'))

        # Row mapping depending on engine
        show_dict = dict(show) if database.ACTIVE_ENGINE == 'sqlite' else show
        screen_id = show_dict['screen_id']
        base_price = float(show_dict['base_price'])
        city_name = show_dict['city_name']

        # Fetch seats with price multipliers
        marks = ','.join(['%s'] * len(ids))
        cur.execute(database.adapt_sql(
            f"""
            SELECT s.seat_id, s.row_label, s.seat_number, sc.price_multiplier
            FROM seat s
            JOIN seat_category sc ON sc.category_id = s.category_id
            WHERE s.screen_id = %s AND s.seat_id IN ({marks})
            """
        ), (screen_id, *ids))
        valid_seats = cur.fetchall()
        if len(valid_seats) != len(ids):
            conn.rollback()
            flash('Seat verification failed.')
            return redirect(url_for('seats', screening_id=screening_id))

        # Check occupancy
        cur.execute(database.adapt_sql(
            f"""
            SELECT bs.seat_id
            FROM booking_seat bs
            JOIN booking b ON b.booking_id = bs.booking_id
            WHERE b.screening_id = %s AND b.booking_status = 'CONFIRMED' AND bs.seat_status = 'BOOKED' AND bs.seat_id IN ({marks})
            """
        ), (screening_id, *ids))
        if cur.fetchall():
            conn.rollback()
            flash('One of your selected seats was just reserved by someone else.')
            return redirect(url_for('seats', screening_id=screening_id))

        # Calculate total
        total_seat_price = 0.0
        seat_prices = {}
        for s in valid_seats:
            s_dict = dict(s) if database.ACTIVE_ENGINE == 'sqlite' else s
            sid = s_dict['seat_id']
            mult = float(s_dict['price_multiplier'])
            price = round(base_price * mult, 2)
            seat_prices[sid] = price
            total_seat_price += price

        grand_total = total_seat_price + concession_total
        booking_ref = generate_booking_ref()

        # Insert booking
        cur.execute(database.adapt_sql(
            """
            INSERT INTO booking (booking_reference, customer_id, screening_id, booking_date, total_amount, booking_status)
            VALUES (%s, %s, %s, NOW(), %s, 'CONFIRMED')
            """
        ), (booking_ref, session['customer_id'], screening_id, grand_total))
        booking_id = cur.lastrowid

        # Insert seats & individual tickets
        idx = 1
        for sid in ids:
            price = seat_prices[sid]
            cur.execute(database.adapt_sql(
                """
                INSERT INTO booking_seat (booking_id, seat_id, ticket_price, seat_status)
                VALUES (%s, %s, %s, 'BOOKED')
                """
            ), (booking_id, sid, price))
            bs_id = cur.lastrowid

            t_code = generate_ticket_code(city_name, booking_id, idx)
            idx += 1
            cur.execute(database.adapt_sql(
                """
                INSERT INTO ticket (booking_seat_id, ticket_code, issued_at, ticket_status)
                VALUES (%s, %s, NOW(), 'ACTIVE')
                """
            ), (bs_id, t_code))

        # Insert concessions
        for item_id, qty, sub in concession_items:
            cur.execute(database.adapt_sql(
                """
                INSERT INTO booking_concession (booking_id, item_id, quantity, subtotal)
                VALUES (%s, %s, %s, %s)
                """
            ), (booking_id, item_id, qty, sub))

        # Insert payment record
        txn_ref = f"TXN-{method}-{booking_id}-{os.urandom(4).hex().upper()}"
        cur.execute(database.adapt_sql(
            """
            INSERT INTO payment (booking_id, payment_time, amount, payment_method, payment_status, transaction_reference)
            VALUES (%s, NOW(), %s, %s, 'SUCCESS', %s)
            """
        ), (booking_id, grand_total, method, txn_ref))

        conn.commit()

        # Synchronize change immediately into database_state.json and activity_log.json
        try:
            movie_name = show_dict.get('title', 'Movie')
            cust_name = session.get('customer_name', 'Customer')
            json_sync.sync_all(
                "CREATE_BOOKING",
                "booking",
                f"Booking {booking_ref} placed: {len(ids)} seat(s) for '{movie_name}' (Total: Rs. {grand_total:.2f})",
                details={
                    "booking_id": booking_id,
                    "booking_reference": booking_ref,
                    "customer_name": cust_name,
                    "movie": movie_name,
                    "seats_count": len(ids),
                    "total_amount": grand_total,
                    "payment_method": method,
                    "transaction_reference": txn_ref
                },
                user=cust_name
            )
        except Exception as e:
            print(f"Notice: JSON sync on create_booking: {e}")

        return redirect(url_for('confirmation', booking_id=booking_id))
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

@app.route('/booking/<int:booking_id>/confirmation')
@login_required
def confirmation(booking_id):
    sql = """
        SELECT b.*, m.title, m.dimension, m.language,
               t.theater_name, t.address, t.location_area, c.city_name,
               sc.screen_name, sc.screen_type,
               s.screening_date, sl.slot_name, sl.start_time,
               cust.full_name, cust.email, cust.phone
        FROM booking b
        JOIN screening s ON s.screening_id = b.screening_id
        JOIN movie m ON m.movie_id = s.movie_id
        JOIN screen sc ON sc.screen_id = s.screen_id
        JOIN theater t ON t.theater_id = sc.theater_id
        JOIN city c ON c.city_id = t.city_id
        JOIN slot sl ON sl.slot_id = s.slot_id
        JOIN customer cust ON cust.customer_id = b.customer_id
        WHERE b.booking_id = %s
    """
    params = (booking_id,)
    # If not manager, must match customer_id
    if session.get('role') not in ('MANAGER', 'ADMIN'):
        sql += " AND b.customer_id = %s"
        params = (booking_id, session['customer_id'])

    b = database.query(sql, params, one=True)
    if not b:
        abort(404)

    # Seats with tickets
    seats = database.query(
        """
        SELECT se.row_label, se.seat_number, cat.category_name, bs.ticket_price, t.ticket_code
        FROM booking_seat bs
        JOIN seat se ON se.seat_id = bs.seat_id
        JOIN seat_category cat ON cat.category_id = se.category_id
        LEFT JOIN ticket t ON t.booking_seat_id = bs.booking_seat_id
        WHERE bs.booking_id = %s
        ORDER BY se.row_label, se.seat_number
        """,
        (booking_id,)
    )
    b['seats'] = seats

    # Concessions
    b['concessions'] = database.query(
        """
        SELECT bc.quantity, bc.subtotal, ci.item_name, ci.category
        FROM booking_concession bc
        JOIN concession_item ci ON ci.item_id = bc.item_id
        WHERE bc.booking_id = %s
        """,
        (booking_id,)
    )

    # Payment
    b['payment'] = database.query(
        "SELECT * FROM payment WHERE booking_id = %s ORDER BY payment_id DESC LIMIT 1",
        (booking_id,),
        one=True
    )

    return render_template('confirmation.html', booking=b)

@app.route('/my-bookings')
@login_required
def my_bookings():
    bookings = database.query(
        """
        SELECT b.*, m.title, m.dimension,
               t.theater_name, t.location_area, c.city_name,
               sc.screen_name, sc.screen_type,
               s.screening_date, sl.slot_name, sl.start_time
        FROM booking b
        JOIN screening s ON s.screening_id = b.screening_id
        JOIN movie m ON m.movie_id = s.movie_id
        JOIN screen sc ON sc.screen_id = s.screen_id
        JOIN theater t ON t.theater_id = sc.theater_id
        JOIN city c ON c.city_id = t.city_id
        JOIN slot sl ON sl.slot_id = s.slot_id
        WHERE b.customer_id = %s
        ORDER BY b.booking_date DESC
        """,
        (session['customer_id'],)
    )
    for b in bookings:
        b['seats'] = database.query(
            """
            SELECT se.row_label, se.seat_number, cat.category_name
            FROM booking_seat bs
            JOIN seat se ON se.seat_id = bs.seat_id
            JOIN seat_category cat ON cat.category_id = se.category_id
            WHERE bs.booking_id = %s AND bs.seat_status = 'BOOKED'
            ORDER BY se.row_label, se.seat_number
            """,
            (b['booking_id'],)
        )
    return render_template('my_bookings.html', bookings=bookings)

@app.route('/cancel-booking/<int:booking_id>', methods=['POST'])
@login_required
def cancel_booking(booking_id):
    conn = database.get_db()
    cur = conn.cursor()
    try:
        if database.ACTIVE_ENGINE == 'sqlite':
            cur.execute("BEGIN TRANSACTION")
        else:
            conn.start_transaction()

        # Check booking exists and ownership
        if session.get('role') in ('MANAGER', 'ADMIN'):
            cur.execute(database.adapt_sql("SELECT booking_reference, booking_status FROM booking WHERE booking_id = %s"), (booking_id,))
        else:
            cur.execute(database.adapt_sql(
                "SELECT booking_reference, booking_status FROM booking WHERE booking_id = %s AND customer_id = %s"
            ), (booking_id, session['customer_id']))

        b = cur.fetchone()
        b_dict = dict(b) if isinstance(b, dict) else ({'booking_reference': b[0], 'booking_status': b[1]} if b else {})
        status = b_dict.get('booking_status')
        if not b or status != 'CONFIRMED':
            conn.rollback()
            flash('This booking cannot be cancelled.')
            return redirect(url_for('my_bookings'))

        cur.execute(database.adapt_sql("UPDATE booking SET booking_status = 'CANCELLED' WHERE booking_id = %s"), (booking_id,))
        cur.execute(database.adapt_sql("UPDATE booking_seat SET seat_status = 'CANCELLED' WHERE booking_id = %s"), (booking_id,))
        cur.execute(database.adapt_sql(
            """
            UPDATE ticket
            SET ticket_status = 'CANCELLED'
            WHERE booking_seat_id IN (SELECT booking_seat_id FROM booking_seat WHERE booking_id = %s)
            """
        ), (booking_id,))
        cur.execute(database.adapt_sql(
            "UPDATE payment SET payment_status = 'REFUNDED' WHERE booking_id = %s AND payment_status = 'SUCCESS'"
        ), (booking_id,))

        conn.commit()

        # Synchronize cancellation to database_state.json and activity_log.json
        try:
            b_ref = b_dict.get('booking_reference', f'#{booking_id}')
            user_label = session.get('customer_name', 'User')
            json_sync.sync_all(
                "CANCEL_BOOKING",
                "booking",
                f"Booking {b_ref} cancelled and marked refunded",
                details={"booking_id": booking_id, "booking_reference": b_ref, "status": "CANCELLED"},
                user=user_label
            )
        except Exception as e:
            print(f"Notice: JSON sync on cancel_booking: {e}")

        flash('Booking cancelled successfully. Payment marked refunded.')
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

    if session.get('role') in ('MANAGER', 'ADMIN') and request.referrer and '/admin' in request.referrer:
        return redirect(url_for('admin_portal'))
    return redirect(url_for('my_bookings'))

# ==========================================
# AUTHENTICATION & ROLE SWITCHER
# ==========================================

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '')

        if not name or not email or len(password) < 6:
            flash('Enter your name, email, and a password of at least 6 characters.')
            return render_template('register.html')

        conn = database.get_db()
        cur = conn.cursor()
        try:
            cur.execute(database.adapt_sql('SELECT customer_id FROM customer WHERE email = %s OR phone = %s'), (email, phone))
            if cur.fetchone():
                flash('That email or phone number is already registered.')
                return render_template('register.html')

            pw_hash = generate_password_hash(password)
            cur.execute(database.adapt_sql(
                'INSERT INTO customer (full_name, email, phone, password_hash, role) VALUES (%s, %s, %s, %s, "CUSTOMER")'
            ), (name, email, phone, pw_hash))
            conn.commit()

            new_cust_id = cur.lastrowid
            session['customer_id'] = new_cust_id
            session['customer_name'] = name
            session['role'] = 'CUSTOMER'

            try:
                json_sync.sync_all(
                    "REGISTER_CUSTOMER",
                    "customer",
                    f"New customer registered: {name} ({email})",
                    details={"customer_id": new_cust_id, "full_name": name, "email": email, "phone": phone},
                    user=name
                )
            except Exception as e:
                print(f"Notice: JSON sync on register: {e}")

            flash('Account created successfully!')
            return redirect(url_for('index'))
        finally:
            cur.close()
            conn.close()
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        user = database.query('SELECT * FROM customer WHERE email = %s', (email,), one=True)
        if not user or not check_password_hash(user['password_hash'], password):
            flash('Invalid email or password.')
            return render_template('login.html')

        session.clear()
        session['customer_id'] = user['customer_id']
        session['customer_name'] = user['full_name']
        session['role'] = user.get('role', 'CUSTOMER')

        if session['role'] in ('MANAGER', 'ADMIN'):
            flash(f"Welcome to Manager Portal, {user['full_name']}!")
            return redirect(safe_next(request.form.get('next')) or url_for('admin_portal'))

        flash(f"Welcome back, {user['full_name']}!")
        return redirect(safe_next(request.form.get('next')))

    return render_template('login.html', next=request.args.get('next', ''))

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.')
    return redirect(url_for('index'))

@app.route('/switch-role')
def switch_role():
    """Demo Helper: Fast 1-click toggle between Manager Vikram and Customer Arjun for evaluation"""
    target = request.args.get('to', 'manager')
    session.clear()
    if target == 'manager':
        mgr = database.query("SELECT * FROM customer WHERE role = 'MANAGER' LIMIT 1", one=True)
        if mgr:
            session['customer_id'] = mgr['customer_id']
            session['customer_name'] = mgr['full_name']
            session['role'] = 'MANAGER'
            flash('Switched session to Manager: ' + mgr['full_name'])
            return redirect(url_for('admin_portal'))
    else:
        cust = database.query("SELECT * FROM customer WHERE role = 'CUSTOMER' LIMIT 1", one=True)
        if cust:
            session['customer_id'] = cust['customer_id']
            session['customer_name'] = cust['full_name']
            session['role'] = 'CUSTOMER'
            flash('Switched session to Customer: ' + cust['full_name'])
            return redirect(url_for('index'))

    return redirect(url_for('index'))

# ==========================================
# MANAGER / ADMIN PORTAL ("WHO BOOKED WHEN")
# ==========================================

@app.route('/admin')
@app.route('/manager')
@manager_required
def admin_portal():
    tab = request.args.get('tab', 'bookings')
    theater_filter = request.args.get('theater')
    movie_filter = request.args.get('movie')
    status_filter = request.args.get('status')
    date_filter = request.args.get('date')
    search = request.args.get('q', '').strip()

    # KPI Metrics
    stats = {}
    stats['total_bookings'] = database.query("SELECT COUNT(*) AS c FROM booking", one=True)['c']
    stats['confirmed_bookings'] = database.query("SELECT COUNT(*) AS c FROM booking WHERE booking_status = 'CONFIRMED'", one=True)['c']
    rev = database.query("SELECT SUM(total_amount) AS s FROM booking WHERE booking_status = 'CONFIRMED'", one=True)['s']
    stats['total_revenue'] = rev if rev is not None else 0.0
    stats['tickets_sold'] = database.query("SELECT COUNT(*) AS c FROM ticket WHERE ticket_status = 'ACTIVE'", one=True)['c']
    stats['active_theaters'] = database.query("SELECT COUNT(*) AS c FROM theater", one=True)['c']
    stats['active_screenings'] = database.query("SELECT COUNT(*) AS c FROM screening WHERE status = 'SCHEDULED' AND screening_date >= CURDATE()", one=True)['c']
    stats['total_movies'] = database.query("SELECT COUNT(*) AS c FROM movie", one=True)['c']

    # Comprehensive Bookings Audit Query ("Who booked when, details n all that stuff")
    conditions = ["1=1"]
    params = []

    if theater_filter:
        conditions.append("t.theater_id = %s")
        params.append(theater_filter)
    if movie_filter:
        conditions.append("m.movie_id = %s")
        params.append(movie_filter)
    if status_filter:
        conditions.append("b.booking_status = %s")
        params.append(status_filter)
    if date_filter:
        conditions.append("s.screening_date = %s")
        params.append(date_filter)
    if search:
        conditions.append("(cust.full_name LIKE %s OR cust.email LIKE %s OR cust.phone LIKE %s OR b.booking_reference LIKE %s)")
        like_term = f"%{search}%"
        params.extend([like_term, like_term, like_term, like_term])

    where_clause = " AND ".join(conditions)

    bookings_sql = f"""
        SELECT b.booking_id, b.booking_reference, b.booking_date, b.total_amount, b.booking_status,
               cust.customer_id, cust.full_name, cust.email, cust.phone,
               m.movie_id, m.title, m.dimension,
               t.theater_id, t.theater_name, t.location_area, c.city_name,
               sc.screen_id, sc.screen_name, sc.screen_type,
               s.screening_id, s.screening_date, sl.slot_name, sl.start_time,
               p.payment_method, p.payment_status, p.transaction_reference, p.payment_time
        FROM booking b
        JOIN customer cust ON cust.customer_id = b.customer_id
        JOIN screening s ON s.screening_id = b.screening_id
        JOIN movie m ON m.movie_id = s.movie_id
        JOIN screen sc ON sc.screen_id = s.screen_id
        JOIN theater t ON t.theater_id = sc.theater_id
        JOIN city c ON c.city_id = t.city_id
        JOIN slot sl ON sl.slot_id = s.slot_id
        LEFT JOIN payment p ON p.booking_id = b.booking_id
        WHERE {where_clause}
        ORDER BY b.booking_date DESC
    """
    bookings = database.query(bookings_sql, params)

    # Attach seat breakdown & ticket codes for each booking
    for b in bookings:
        b['seat_list'] = database.query(
            """
            SELECT se.row_label, se.seat_number, cat.category_name, bs.ticket_price, t.ticket_code
            FROM booking_seat bs
            JOIN seat se ON se.seat_id = bs.seat_id
            JOIN seat_category cat ON cat.category_id = se.category_id
            LEFT JOIN ticket t ON t.booking_seat_id = bs.booking_seat_id
            WHERE bs.booking_id = %s
            ORDER BY se.row_label, se.seat_number
            """,
            (b['booking_id'],)
        )

    # Master lists for dropdown filters & comprehensive management
    theaters = database.query("""
        SELECT t.*, c.city_name, c.state,
               (SELECT COUNT(*) FROM screen sc WHERE sc.theater_id = t.theater_id) AS screen_count
        FROM theater t
        JOIN city c ON c.city_id = t.city_id
        ORDER BY t.theater_name
    """)
    movies = database.query("""
        SELECT m.*, GROUP_CONCAT(g.genre_name ORDER BY g.genre_name SEPARATOR ', ') AS genres
        FROM movie m
        LEFT JOIN movie_genre mg ON mg.movie_id = m.movie_id
        LEFT JOIN genre g ON g.genre_id = mg.genre_id
        GROUP BY m.movie_id
        ORDER BY m.title
    """)
    screenings = database.query(
        """
        SELECT s.screening_id, s.screening_date, m.title, t.theater_name, sc.screen_name, sl.slot_name, sl.start_time
        FROM screening s
        JOIN movie m ON m.movie_id = s.movie_id
        JOIN screen sc ON sc.screen_id = s.screen_id
        JOIN theater t ON t.theater_id = sc.theater_id
        JOIN slot sl ON sl.slot_id = s.slot_id
        WHERE s.screening_date >= CURDATE() AND s.status = 'SCHEDULED'
        ORDER BY s.screening_date, t.theater_name, sl.start_time
        """
    )
    all_screenings = database.query(
        """
        SELECT s.screening_id, s.screening_date, s.base_price, s.status,
               m.movie_id, m.title, m.dimension, m.language,
               t.theater_id, t.theater_name, t.location_area,
               sc.screen_id, sc.screen_name, sc.screen_type,
               sl.slot_id, sl.slot_name, sl.start_time
        FROM screening s
        JOIN movie m ON m.movie_id = s.movie_id
        JOIN screen sc ON sc.screen_id = s.screen_id
        JOIN theater t ON t.theater_id = sc.theater_id
        JOIN slot sl ON sl.slot_id = s.slot_id
        ORDER BY s.screening_date DESC, sl.start_time ASC
        """
    )
    slots = database.query("SELECT * FROM slot ORDER BY start_time")
    screens = database.query("SELECT sc.*, t.theater_name FROM screen sc JOIN theater t ON t.theater_id = sc.theater_id ORDER BY t.theater_name, sc.screen_name")
    concession_items = database.query("SELECT * FROM concession_item ORDER BY category, price")
    seat_categories = database.query("SELECT * FROM seat_category ORDER BY price_multiplier DESC")
    genres = database.query("SELECT * FROM genre ORDER BY genre_name")
    cities = database.query("SELECT * FROM city ORDER BY city_name")

    # Revenue by Movie breakdown
    revenue_by_movie = database.query(
        """
        SELECT m.title, COUNT(DISTINCT b.booking_id) AS total_bookings,
               COUNT(bs.booking_seat_id) AS total_tickets,
               COALESCE(SUM(b.total_amount), 0) AS gross_revenue
        FROM movie m
        LEFT JOIN screening s ON s.movie_id = m.movie_id
        LEFT JOIN booking b ON b.screening_id = s.screening_id AND b.booking_status = 'CONFIRMED'
        LEFT JOIN booking_seat bs ON bs.booking_id = b.booking_id AND bs.seat_status = 'BOOKED'
        GROUP BY m.movie_id
        ORDER BY gross_revenue DESC
        """
    )

    # Revenue by Theater breakdown
    revenue_by_theater = database.query(
        """
        SELECT t.theater_name, c.city_name,
               COUNT(DISTINCT b.booking_id) AS total_bookings,
               COALESCE(SUM(b.total_amount), 0) AS gross_revenue
        FROM theater t
        JOIN city c ON c.city_id = t.city_id
        LEFT JOIN screen sc ON sc.theater_id = t.theater_id
        LEFT JOIN screening s ON s.screen_id = sc.screen_id
        LEFT JOIN booking b ON b.screening_id = s.screening_id AND b.booking_status = 'CONFIRMED'
        GROUP BY t.theater_id
        ORDER BY gross_revenue DESC
        """
    )

    activity_log = json_sync.get_activity_log(limit=60)
    db_state = json_sync.get_database_state()
    last_sync_time = db_state.get('_metadata', {}).get('last_synced_at', datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    return render_template(
        'admin.html',
        stats=stats,
        bookings=bookings,
        theaters=theaters,
        movies=movies,
        screenings=screenings,
        all_screenings=all_screenings,
        concession_items=concession_items,
        seat_categories=seat_categories,
        genres=genres,
        cities=cities,
        slots=slots,
        screens=screens,
        revenue_by_movie=revenue_by_movie,
        revenue_by_theater=revenue_by_theater,
        activity_log=activity_log,
        last_sync_time=last_sync_time,
        active_tab=tab,
        selected_theater=theater_filter,
        selected_movie=movie_filter,
        selected_status=status_filter,
        selected_date=date_filter,
        search_query=search
    )

@app.route('/admin/screening-occupancy/<int:screening_id>')
@manager_required
def admin_screening_occupancy(screening_id):
    """API endpoint for manager to view real-time seat occupancy and customer details for any show."""
    screening = database.query(
        """
        SELECT s.*, m.title, t.theater_name, sc.screen_name, sc.screen_type, sl.slot_name, sl.start_time
        FROM screening s
        JOIN movie m ON m.movie_id = s.movie_id
        JOIN screen sc ON sc.screen_id = s.screen_id
        JOIN theater t ON t.theater_id = sc.theater_id
        JOIN slot sl ON sl.slot_id = s.slot_id
        WHERE s.screening_id = %s
        """,
        (screening_id,),
        one=True
    )
    if not screening:
        return jsonify({'error': 'Screening not found'}), 404

    seats = database.query(
        """
        SELECT s.seat_id, s.row_label, s.seat_number, cat.category_name,
               b.booking_id, b.booking_reference, b.booking_date, b.booking_status,
               cust.full_name AS booked_by, cust.email AS customer_email, cust.phone AS customer_phone
        FROM seat s
        JOIN seat_category cat ON cat.category_id = s.category_id
        LEFT JOIN booking_seat bs ON bs.seat_id = s.seat_id AND bs.seat_status = 'BOOKED'
        LEFT JOIN booking b ON b.booking_id = bs.booking_id AND b.screening_id = %s AND b.booking_status = 'CONFIRMED'
        LEFT JOIN customer cust ON cust.customer_id = b.customer_id
        WHERE s.screen_id = %s
        ORDER BY s.row_label, s.seat_number
        """,
        (screening_id, screening['screen_id'])
    )

    total_seats = len(seats)
    occupied_count = sum(1 for s in seats if s.get('booking_id'))
    rate = round((occupied_count / total_seats * 100), 1) if total_seats > 0 else 0

    return jsonify({
        'screening': dict(screening),
        'total_seats': total_seats,
        'occupied_count': occupied_count,
        'occupancy_rate': rate,
        'seats': [dict(s) for s in seats]
    })

# ==========================================
# SHOWTIME / SCREENING CRUD & EDITING
# ==========================================

@app.route('/admin/add-screening', methods=['POST'])
@manager_required
def admin_add_screening():
    movie_id = request.form.get('movie_id')
    screen_id = request.form.get('screen_id')
    slot_id = request.form.get('slot_id')
    screening_date = request.form.get('screening_date')
    base_price = request.form.get('base_price', '250.00')

    if not (movie_id and screen_id and slot_id and screening_date and base_price):
        flash('Please fill in all fields to schedule a new showtime.')
        return redirect(url_for('admin_portal', tab='screenings'))

    # Conflict check: is this screen already booked for this slot on this date?
    conflict = database.query(
        "SELECT screening_id FROM screening WHERE screen_id = %s AND slot_id = %s AND screening_date = %s AND status = 'SCHEDULED'",
        (screen_id, slot_id, screening_date),
        one=True
    )
    if conflict:
        flash('Conflict detected: This screen is already scheduled for that time slot on the selected date.')
        return redirect(url_for('admin_portal', tab='screenings'))

    conn = database.get_db()
    cur = conn.cursor()
    try:
        cur.execute(database.adapt_sql(
            """
            INSERT INTO screening (movie_id, screen_id, slot_id, screening_date, base_price, status)
            VALUES (%s, %s, %s, %s, %s, 'SCHEDULED')
            """
        ), (movie_id, screen_id, slot_id, screening_date, float(base_price)))
        sc_id = cur.lastrowid
        conn.commit()

        # Fetch movie and theater names for clear audit log
        sc_info = database.query("""
            SELECT m.title, t.theater_name, sc.screen_name, sl.slot_name
            FROM screening s
            JOIN movie m ON m.movie_id = s.movie_id
            JOIN screen sc ON sc.screen_id = s.screen_id
            JOIN theater t ON t.theater_id = sc.theater_id
            JOIN slot sl ON sl.slot_id = s.slot_id
            WHERE s.screening_id = %s
        """, (sc_id,), one=True)
        m_title = sc_info['title'] if sc_info else f"Movie #{movie_id}"
        t_name = sc_info['theater_name'] if sc_info else f"Screen #{screen_id}"

        json_sync.sync_all(
            "INSERT_SCREENING",
            "screening",
            f"Scheduled new showtime: '{m_title}' at {t_name} on {screening_date} (Rs. {float(base_price):.2f})",
            details={"screening_id": sc_id, "movie_id": movie_id, "screen_id": screen_id, "slot_id": slot_id, "date": screening_date, "base_price": base_price},
            user=session.get('customer_name', 'Manager')
        )
        flash('New showtime scheduled successfully and recorded in JSON file!')
    finally:
        cur.close()
        conn.close()

    return redirect(url_for('admin_portal', tab='screenings'))


@app.route('/admin/screening/edit/<int:screening_id>', methods=['POST'])
@manager_required
def admin_edit_screening(screening_id):
    movie_id = request.form.get('movie_id')
    screen_id = request.form.get('screen_id')
    slot_id = request.form.get('slot_id')
    screening_date = request.form.get('screening_date')
    base_price = request.form.get('base_price', '250.00')
    status = request.form.get('status', 'SCHEDULED')

    conn = database.get_db()
    cur = conn.cursor()
    try:
        cur.execute(database.adapt_sql(
            """
            UPDATE screening
            SET movie_id = %s, screen_id = %s, slot_id = %s, screening_date = %s,
                base_price = %s, status = %s
            WHERE screening_id = %s
            """
        ), (movie_id, screen_id, slot_id, screening_date, float(base_price), status, screening_id))
        conn.commit()

        json_sync.sync_all(
            "UPDATE_SCREENING",
            "screening",
            f"Updated showtime #{screening_id}: Date {screening_date}, Price Rs. {float(base_price):.2f}, Status {status}",
            details={"screening_id": screening_id, "movie_id": movie_id, "screen_id": screen_id, "slot_id": slot_id, "date": screening_date, "price": base_price, "status": status},
            user=session.get('customer_name', 'Manager')
        )
        flash(f"Showtime #{screening_id} updated successfully and mirrored to JSON file!")
    finally:
        cur.close()
        conn.close()

    return redirect(url_for('admin_portal', tab='screenings'))


@app.route('/admin/screening/delete/<int:screening_id>', methods=['POST'])
@manager_required
def admin_delete_screening(screening_id):
    conn = database.get_db()
    cur = conn.cursor()
    try:
        cur.execute(database.adapt_sql("DELETE FROM screening WHERE screening_id = %s"), (screening_id,))
        conn.commit()

        json_sync.sync_all(
            "DELETE_SCREENING",
            "screening",
            f"Deleted showtime #{screening_id} from schedule",
            details={"screening_id": screening_id},
            user=session.get('customer_name', 'Manager')
        )
        flash(f"Showtime #{screening_id} deleted successfully!")
    finally:
        cur.close()
        conn.close()

    return redirect(url_for('admin_portal', tab='screenings'))

# ==========================================
# MOVIE CRUD & EDITING
# ==========================================

@app.route('/admin/movie/add', methods=['POST'])
@manager_required
def admin_add_movie():
    title = request.form.get('title', '').strip()
    synopsis = request.form.get('synopsis', '').strip()
    language = request.form.get('language', 'English').strip()
    duration = int(request.form.get('duration_minutes', 120))
    release_date = request.form.get('release_date', date.today().isoformat())
    rating = request.form.get('rating', 'UA')
    dimension = request.form.get('dimension', '2D')
    genre_ids = request.form.getlist('genre_ids')

    if not title:
        flash('Movie title is required.')
        return redirect(url_for('admin_portal', tab='movies'))

    conn = database.get_db()
    cur = conn.cursor()
    try:
        cur.execute(database.adapt_sql(
            """
            INSERT INTO movie (title, synopsis, language, duration_minutes, release_date, rating, dimension)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
        ), (title, synopsis, language, duration, release_date, rating, dimension))
        movie_id = cur.lastrowid

        for gid in genre_ids:
            try:
                cur.execute(database.adapt_sql(
                    "INSERT INTO movie_genre (movie_id, genre_id) VALUES (%s, %s)"
                ), (movie_id, int(gid)))
            except Exception:
                pass

        conn.commit()

        json_sync.sync_all(
            "INSERT_MOVIE",
            "movie",
            f"Added movie '{title}' ({language}, {dimension}, {duration}m)",
            details={"movie_id": movie_id, "title": title, "duration": duration, "language": language, "rating": rating},
            user=session.get('customer_name', 'Manager')
        )
        flash(f"Movie '{title}' added successfully and recorded to JSON file!")
    finally:
        cur.close()
        conn.close()

    return redirect(url_for('admin_portal', tab='movies'))


@app.route('/admin/movie/edit/<int:movie_id>', methods=['POST'])
@manager_required
def admin_edit_movie(movie_id):
    title = request.form.get('title', '').strip()
    synopsis = request.form.get('synopsis', '').strip()
    language = request.form.get('language', 'English').strip()
    duration = int(request.form.get('duration_minutes', 120))
    release_date = request.form.get('release_date', date.today().isoformat())
    rating = request.form.get('rating', 'UA')
    dimension = request.form.get('dimension', '2D')
    genre_ids = request.form.getlist('genre_ids')

    if not title:
        flash('Movie title is required.')
        return redirect(url_for('admin_portal', tab='movies'))

    conn = database.get_db()
    cur = conn.cursor()
    try:
        cur.execute(database.adapt_sql(
            """
            UPDATE movie
            SET title = %s, synopsis = %s, language = %s, duration_minutes = %s,
                release_date = %s, rating = %s, dimension = %s
            WHERE movie_id = %s
            """
        ), (title, synopsis, language, duration, release_date, rating, dimension, movie_id))

        cur.execute(database.adapt_sql("DELETE FROM movie_genre WHERE movie_id = %s"), (movie_id,))
        for gid in genre_ids:
            try:
                cur.execute(database.adapt_sql(
                    "INSERT INTO movie_genre (movie_id, genre_id) VALUES (%s, %s)"
                ), (movie_id, int(gid)))
            except Exception:
                pass

        conn.commit()

        json_sync.sync_all(
            "UPDATE_MOVIE",
            "movie",
            f"Updated movie #{movie_id} '{title}' ({language}, {rating})",
            details={"movie_id": movie_id, "title": title, "duration": duration, "language": language},
            user=session.get('customer_name', 'Manager')
        )
        flash(f"Movie '{title}' updated successfully and mirrored in JSON file!")
    finally:
        cur.close()
        conn.close()

    return redirect(url_for('admin_portal', tab='movies'))


@app.route('/admin/movie/delete/<int:movie_id>', methods=['POST'])
@manager_required
def admin_delete_movie(movie_id):
    movie = database.query("SELECT title FROM movie WHERE movie_id = %s", (movie_id,), one=True)
    title = movie['title'] if movie else f"#{movie_id}"

    conn = database.get_db()
    cur = conn.cursor()
    try:
        cur.execute(database.adapt_sql("DELETE FROM movie WHERE movie_id = %s"), (movie_id,))
        conn.commit()

        json_sync.sync_all(
            "DELETE_MOVIE",
            "movie",
            f"Deleted movie '{title}' (ID #{movie_id})",
            details={"movie_id": movie_id, "title": title},
            user=session.get('customer_name', 'Manager')
        )
        flash(f"Movie '{title}' deleted successfully!")
    finally:
        cur.close()
        conn.close()

    return redirect(url_for('admin_portal', tab='movies'))

# ==========================================
# THEATER & SCREEN CRUD & EDITING
# ==========================================

@app.route('/admin/theater/add', methods=['POST'])
@manager_required
def admin_add_theater():
    city_id = request.form.get('city_id')
    name = request.form.get('theater_name', '').strip()
    address = request.form.get('address', '').strip()
    location_area = request.form.get('location_area', '').strip()

    if not name or not address:
        flash('Theater name and address are required.')
        return redirect(url_for('admin_portal', tab='theaters'))

    conn = database.get_db()
    cur = conn.cursor()
    try:
        cur.execute(database.adapt_sql(
            "INSERT INTO theater (city_id, theater_name, address, location_area) VALUES (%s, %s, %s, %s)"
        ), (city_id, name, address, location_area))
        theater_id = cur.lastrowid

        # Automatically create default Screen 1 with 60 seats for the new theater
        cur.execute(database.adapt_sql(
            "INSERT INTO screen (theater_id, screen_name, screen_type, total_seats) VALUES (%s, 'Screen 1 (Dolby 2D)', 'Dolby Atmos 2D', 60)"
        ), (theater_id,))
        screen_id = cur.lastrowid

        seats = []
        for num in range(1, 11):
            seats.append((screen_id, 1, 'A', num))
        for row in ('B', 'C', 'D'):
            for num in range(1, 11):
                seats.append((screen_id, 2, row, num))
        for row in ('E', 'F'):
            for num in range(1, 11):
                seats.append((screen_id, 3, row, num))

        if database.ACTIVE_ENGINE == 'sqlite':
            cur.executemany("INSERT INTO seat (screen_id, category_id, row_label, seat_number) VALUES (?, ?, ?, ?)", seats)
        else:
            cur.executemany("INSERT INTO seat (screen_id, category_id, row_label, seat_number) VALUES (%s, %s, %s, %s)", seats)

        conn.commit()

        json_sync.sync_all(
            "INSERT_THEATER",
            "theater",
            f"Added theater '{name}' in {location_area} with Screen 1 (60 seats)",
            details={"theater_id": theater_id, "theater_name": name, "city_id": city_id, "screen_id": screen_id},
            user=session.get('customer_name', 'Manager')
        )
        flash(f"Theater '{name}' and Screen 1 created successfully!")
    finally:
        cur.close()
        conn.close()

    return redirect(url_for('admin_portal', tab='theaters'))


@app.route('/admin/theater/edit/<int:theater_id>', methods=['POST'])
@manager_required
def admin_edit_theater(theater_id):
    city_id = request.form.get('city_id')
    name = request.form.get('theater_name', '').strip()
    address = request.form.get('address', '').strip()
    location_area = request.form.get('location_area', '').strip()

    conn = database.get_db()
    cur = conn.cursor()
    try:
        cur.execute(database.adapt_sql(
            """
            UPDATE theater
            SET city_id = %s, theater_name = %s, address = %s, location_area = %s
            WHERE theater_id = %s
            """
        ), (city_id, name, address, location_area, theater_id))
        conn.commit()

        json_sync.sync_all(
            "UPDATE_THEATER",
            "theater",
            f"Updated theater #{theater_id} '{name}' ({location_area})",
            details={"theater_id": theater_id, "theater_name": name, "location_area": location_area},
            user=session.get('customer_name', 'Manager')
        )
        flash(f"Theater '{name}' updated successfully and recorded to JSON file!")
    finally:
        cur.close()
        conn.close()

    return redirect(url_for('admin_portal', tab='theaters'))


@app.route('/admin/screen/edit/<int:screen_id>', methods=['POST'])
@manager_required
def admin_edit_screen(screen_id):
    screen_name = request.form.get('screen_name', '').strip()
    screen_type = request.form.get('screen_type', 'Standard 2D').strip()

    conn = database.get_db()
    cur = conn.cursor()
    try:
        cur.execute(database.adapt_sql(
            "UPDATE screen SET screen_name = %s, screen_type = %s WHERE screen_id = %s"
        ), (screen_name, screen_type, screen_id))
        conn.commit()

        json_sync.sync_all(
            "UPDATE_SCREEN",
            "screen",
            f"Updated screen #{screen_id} '{screen_name}' ({screen_type})",
            details={"screen_id": screen_id, "screen_name": screen_name, "screen_type": screen_type},
            user=session.get('customer_name', 'Manager')
        )
        flash(f"Screen '{screen_name}' updated successfully!")
    finally:
        cur.close()
        conn.close()

    return redirect(url_for('admin_portal', tab='theaters'))

# ==========================================
# CONCESSION / F&B CRUD & EDITING
# ==========================================

@app.route('/admin/concession/add', methods=['POST'])
@manager_required
def admin_add_concession():
    name = request.form.get('item_name', '').strip()
    category = request.form.get('category', 'Popcorn').strip()
    price = float(request.form.get('price', '150.00'))

    if not name:
        flash('Item name is required.')
        return redirect(url_for('admin_portal', tab='concessions'))

    conn = database.get_db()
    cur = conn.cursor()
    try:
        cur.execute(database.adapt_sql(
            "INSERT INTO concession_item (item_name, category, price) VALUES (%s, %s, %s)"
        ), (name, category, price))
        item_id = cur.lastrowid
        conn.commit()

        json_sync.sync_all(
            "INSERT_CONCESSION",
            "concession_item",
            f"Added concession snack '{name}' (Rs. {price:.2f})",
            details={"item_id": item_id, "item_name": name, "category": category, "price": price},
            user=session.get('customer_name', 'Manager')
        )
        flash(f"Item '{name}' added successfully and mirrored in JSON file!")
    finally:
        cur.close()
        conn.close()

    return redirect(url_for('admin_portal', tab='concessions'))


@app.route('/admin/concession/edit/<int:item_id>', methods=['POST'])
@manager_required
def admin_edit_concession(item_id):
    name = request.form.get('item_name', '').strip()
    category = request.form.get('category', 'Popcorn').strip()
    price = float(request.form.get('price', '150.00'))

    conn = database.get_db()
    cur = conn.cursor()
    try:
        cur.execute(database.adapt_sql(
            "UPDATE concession_item SET item_name = %s, category = %s, price = %s WHERE item_id = %s"
        ), (name, category, price, item_id))
        conn.commit()

        json_sync.sync_all(
            "UPDATE_CONCESSION",
            "concession_item",
            f"Updated concession snack #{item_id} '{name}' to Rs. {price:.2f}",
            details={"item_id": item_id, "item_name": name, "category": category, "price": price},
            user=session.get('customer_name', 'Manager')
        )
        flash(f"Concession item '{name}' updated successfully!")
    finally:
        cur.close()
        conn.close()

    return redirect(url_for('admin_portal', tab='concessions'))


@app.route('/admin/concession/delete/<int:item_id>', methods=['POST'])
@manager_required
def admin_delete_concession(item_id):
    conn = database.get_db()
    cur = conn.cursor()
    try:
        cur.execute(database.adapt_sql("DELETE FROM concession_item WHERE item_id = %s"), (item_id,))
        conn.commit()

        json_sync.sync_all(
            "DELETE_CONCESSION",
            "concession_item",
            f"Deleted concession snack item #{item_id}",
            details={"item_id": item_id},
            user=session.get('customer_name', 'Manager')
        )
        flash(f"Concession item #{item_id} deleted successfully!")
    finally:
        cur.close()
        conn.close()

    return redirect(url_for('admin_portal', tab='concessions'))

# ==========================================
# SEAT CATEGORY & MULTIPLIER EDITING
# ==========================================

@app.route('/admin/seat-category/edit/<int:category_id>', methods=['POST'])
@manager_required
def admin_edit_seat_category(category_id):
    name = request.form.get('category_name', '').strip()
    multiplier = float(request.form.get('price_multiplier', '1.00'))
    description = request.form.get('description', '').strip()

    conn = database.get_db()
    cur = conn.cursor()
    try:
        cur.execute(database.adapt_sql(
            "UPDATE seat_category SET category_name = %s, price_multiplier = %s, description = %s WHERE category_id = %s"
        ), (name, multiplier, description, category_id))
        conn.commit()

        json_sync.sync_all(
            "UPDATE_SEAT_CATEGORY",
            "seat_category",
            f"Updated seat category '{name}' pricing multiplier to {multiplier:.2f}x",
            details={"category_id": category_id, "category_name": name, "price_multiplier": multiplier},
            user=session.get('customer_name', 'Manager')
        )
        flash(f"Seat category '{name}' pricing multiplier updated to {multiplier:.2f}x and synced to JSON file!")
    finally:
        cur.close()
        conn.close()

    return redirect(url_for('admin_portal', tab='pricing'))

# ==========================================
# BOOKING STATUS OVERRIDE
# ==========================================

@app.route('/admin/booking/edit-status/<int:booking_id>', methods=['POST'])
@manager_required
def admin_edit_booking_status(booking_id):
    status = request.form.get('booking_status', 'CONFIRMED')

    conn = database.get_db()
    cur = conn.cursor()
    try:
        cur.execute(database.adapt_sql("UPDATE booking SET booking_status = %s WHERE booking_id = %s"), (status, booking_id))
        seat_status = 'BOOKED' if status == 'CONFIRMED' else 'CANCELLED'
        cur.execute(database.adapt_sql("UPDATE booking_seat SET seat_status = %s WHERE booking_id = %s"), (seat_status, booking_id))
        tck_status = 'ACTIVE' if status == 'CONFIRMED' else 'CANCELLED'
        cur.execute(database.adapt_sql(
            "UPDATE ticket SET ticket_status = %s WHERE booking_seat_id IN (SELECT booking_seat_id FROM booking_seat WHERE booking_id = %s)"
        ), (tck_status, booking_id))
        pay_status = 'SUCCESS' if status == 'CONFIRMED' else 'REFUNDED'
        cur.execute(database.adapt_sql("UPDATE payment SET payment_status = %s WHERE booking_id = %s"), (pay_status, booking_id))

        conn.commit()

        json_sync.sync_all(
            "UPDATE_BOOKING_STATUS",
            "booking",
            f"Admin updated Booking #{booking_id} status to '{status}'",
            details={"booking_id": booking_id, "status": status, "payment_status": pay_status},
            user=session.get('customer_name', 'Manager')
        )
        flash(f"Booking #{booking_id} status updated to '{status}'!")
    finally:
        cur.close()
        conn.close()

    return redirect(url_for('admin_portal', tab='bookings'))

# ==========================================
# JSON EXPORT, LIVE VIEW & DOWNLOAD ENDPOINTS
# ==========================================

@app.route('/api/json/database')
def api_json_database():
    return jsonify(json_sync.get_database_state())

@app.route('/api/json/activity')
def api_json_activity():
    return jsonify(json_sync.get_activity_log())

@app.route('/api/json/table/<table_name>')
def api_json_table(table_name):
    db = json_sync.get_database_state()
    if table_name in db:
        return jsonify({
            "table": table_name,
            "count": len(db[table_name]) if isinstance(db[table_name], list) else 1,
            "data": db[table_name]
        })
    return jsonify({"error": f"Table '{table_name}' not found in database export"}), 404

@app.route('/admin/download-json/<file_type>')
@manager_required
def admin_download_json(file_type):
    if file_type == 'activity':
        path = json_sync.get_activity_log_path()
        filename = 'cinesphere_activity_log.json'
    else:
        path = json_sync.get_database_state_path()
        filename = 'cinesphere_database_state.json'
    return send_file(path, as_attachment=True, download_name=filename, mimetype='application/json')

@app.route('/admin/sync-json-now', methods=['POST'])
@manager_required
def admin_sync_json_now():
    res = json_sync.sync_all("MANUAL_SYNC", "system", "Manual JSON synchronization triggered from Manager Portal", user=session.get('customer_name', 'Manager'))
    flash(f"Database successfully synchronized with JSON file at {res['timestamp']}!")
    return redirect(url_for('admin_portal', tab='json'))

@app.route('/view-json')
def view_json():
    file_type = request.args.get('file', 'database')
    if file_type == 'activity':
        raw_data = json_sync.get_activity_log()
        title = "Activity Mutation Log (activity_log.json)"
    else:
        raw_data = json_sync.get_database_state()
        title = "Live Database State Snapshot (database_state.json)"
    return render_template('view_json.html', raw_data=raw_data, file_type=file_type, title=title)

if __name__ == '__main__':
    host = os.getenv('FLASK_HOST', '127.0.0.1')
    port = int(os.getenv('FLASK_PORT', '5000'))
    debug = os.getenv('FLASK_DEBUG', '1') == '1'
    print(f"CineSphere running at http://{host}:{port}")
    app.run(host=host, port=port, debug=debug)