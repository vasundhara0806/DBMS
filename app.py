'''
Testing Data
User1:
    Name: Sreya Kalyan
    Email: sreyakalyan@icloud.com
    Phone Number: 9100097570
    Password: 'sreyakalyan'
'''

import os
from functools import wraps
from datetime import date
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
import mysql.connector

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'change-this-development-key')

def db():
    return mysql.connector.connect(host=os.getenv('DB_HOST','127.0.0.1'), port=int(os.getenv('DB_PORT','3306')), user=os.getenv('DB_USER','root'), password=os.getenv('DB_PASSWORD',''), database=os.getenv('DB_NAME','cinesphere'))

def query(sql, params=(), one=False):
    conn=db(); cur=conn.cursor(dictionary=True)
    try:
        cur.execute(sql, params); result=cur.fetchone() if one else cur.fetchall(); return result
    finally: cur.close(); conn.close()

def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if 'customer_id' not in session:
            flash('Please log in to continue.'); return redirect(url_for('login', next=request.path))
        return fn(*args, **kwargs)
    return wrapped

def safe_next(value):
    return value if value and value.startswith('/') and not value.startswith('//') else url_for('index')

@app.route('/')
def index():
    movies=query("SELECT m.*, GROUP_CONCAT(g.genre_name ORDER BY g.genre_name SEPARATOR ', ') AS genres FROM movie m LEFT JOIN movie_genre mg ON mg.movie_id=m.movie_id LEFT JOIN genre g ON g.genre_id=mg.genre_id GROUP BY m.movie_id ORDER BY m.title")
    return render_template('index.html', movies=movies)

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method=='POST':
        name=request.form.get('name','').strip(); email=request.form.get('email','').strip().lower(); phone=request.form.get('phone','').strip(); password=request.form.get('password','')
        if not name or not email or len(password)<6: flash('Enter your name, email, and a password of at least 6 characters.'); return render_template('register.html')
        conn=db(); cur=conn.cursor()
        try:
            cur.execute('SELECT customer_id FROM customer WHERE email=%s OR phone=%s',(email,phone))
            if cur.fetchone(): flash('That email or phone number is already registered.'); return render_template('register.html')
            cur.execute('INSERT INTO customer (full_name,email,phone,password_hash) VALUES (%s,%s,%s,%s)',(name,email,phone,generate_password_hash(password))); conn.commit(); session['customer_id']=cur.lastrowid; session['customer_name']=name; flash('Account created successfully.'); return redirect(url_for('index'))
        finally: cur.close(); conn.close()
    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method=='POST':
        email=request.form.get('email','').strip().lower(); password=request.form.get('password','')
        user=query('SELECT customer_id,full_name,password_hash FROM customer WHERE email=%s',(email,),one=True)
        if not user or not check_password_hash(user['password_hash'],password): flash('Invalid email or password.'); return render_template('login.html')
        session.clear(); session['customer_id']=user['customer_id']; session['customer_name']=user['full_name']; return redirect(safe_next(request.form.get('next')))
    return render_template('login.html', next=request.args.get('next',''))

@app.route('/logout')
def logout(): session.clear(); flash('You have been logged out.'); return redirect(url_for('index'))

@app.route('/movie/<int:movie_id>')
def movie_details(movie_id):
    movie=query('SELECT * FROM movie WHERE movie_id=%s',(movie_id,),one=True)
    if not movie: abort(404)
    movie['genres']=query('SELECT g.genre_name FROM genre g JOIN movie_genre mg ON mg.genre_id=g.genre_id WHERE mg.movie_id=%s',(movie_id,))
    return render_template('movie_details.html',movie=movie)

@app.route('/movie/<int:movie_id>/showtimes')
def showtimes(movie_id):
    movie=query('SELECT * FROM movie WHERE movie_id=%s',(movie_id,),one=True)
    if not movie: abort(404)
    shows=query("SELECT s.screening_id,s.screening_date,s.base_price,s.status,sl.slot_name,sl.start_time,t.theater_name,t.city,sc.screen_name,sc.screen_type FROM screening s JOIN slot sl ON sl.slot_id=s.slot_id JOIN screen sc ON sc.screen_id=s.screen_id JOIN theater t ON t.theater_id=sc.theater_id WHERE s.movie_id=%s AND s.screening_date>=CURDATE() AND s.status='SCHEDULED' ORDER BY s.screening_date,sl.start_time",(movie_id,))
    return render_template('showtimes.html',movie=movie,showtimes=shows)

@app.route('/show/<int:screening_id>/seats')
@login_required
def seats(screening_id):
    screening=query("SELECT s.*,m.title,t.theater_name,sc.screen_name,sc.screen_type,sl.slot_name FROM screening s JOIN movie m ON m.movie_id=s.movie_id JOIN screen sc ON sc.screen_id=s.screen_id JOIN theater t ON t.theater_id=sc.theater_id JOIN slot sl ON sl.slot_id=s.slot_id WHERE s.screening_id=%s AND s.status='SCHEDULED'",(screening_id,),one=True)
    if not screening: abort(404)
    screening['show_date']=screening['screening_date']
    seats=query('SELECT * FROM seat WHERE screen_id=%s ORDER BY row_label,seat_number',(screening['screen_id'],))
    booked=query("SELECT bs.seat_id FROM booking_seat bs JOIN booking b ON b.booking_id=bs.booking_id WHERE b.screening_id=%s AND b.booking_status='CONFIRMED' AND bs.seat_status='BOOKED'",(screening_id,))
    return render_template('seats.html',screening=screening,seats=seats,booked_seat_ids=[x['seat_id'] for x in booked])

@app.route('/show/<int:screening_id>/booking',methods=['GET','POST'])
@login_required
def booking_review(screening_id):
    ids=request.form.getlist('seat_ids') if request.method=='POST' else request.args.getlist('seat_ids')
    try: ids=list(dict.fromkeys(int(x) for x in ids))
    except ValueError: ids=[]
    if not ids: flash('Choose at least one seat.'); return redirect(url_for('seats',screening_id=screening_id))
    screening=query("SELECT s.*,m.title,t.theater_name,sc.screen_name,sc.screen_type,sl.slot_name FROM screening s JOIN movie m ON m.movie_id=s.movie_id JOIN screen sc ON sc.screen_id=s.screen_id JOIN theater t ON t.theater_id=sc.theater_id JOIN slot sl ON sl.slot_id=s.slot_id WHERE s.screening_id=%s AND s.status='SCHEDULED'",(screening_id,),one=True)
    if not screening: abort(404)
    marks=','.join(['%s']*len(ids)); selected=query(f'SELECT * FROM seat WHERE screen_id=%s AND seat_id IN ({marks})',(screening['screen_id'],*ids))
    if len(selected)!=len(ids): flash('One or more selected seats are invalid.'); return redirect(url_for('seats',screening_id=screening_id))
    occupied=query(f"SELECT bs.seat_id FROM booking_seat bs JOIN booking b ON b.booking_id=bs.booking_id WHERE b.screening_id=%s AND b.booking_status='CONFIRMED' AND bs.seat_status='BOOKED' AND bs.seat_id IN ({marks})",(screening_id,*ids))
    if occupied: flash('A selected seat is no longer available. Please choose again.'); return redirect(url_for('seats',screening_id=screening_id))
    return render_template('booking.html',screening=screening,seats=selected,selected_seat_ids=ids,total_amount=float(screening['base_price'])*len(ids))

@app.route('/create-booking',methods=['POST'])
@login_required
def create_booking():
    try: screening_id=int(request.form.get('screening_id','')); ids=list(dict.fromkeys(int(x) for x in request.form.getlist('seat_ids')))
    except ValueError: abort(400)
    method=request.form.get('payment_method','UPI')
    if not ids or method not in ('UPI','CARD','CASH'): flash('Invalid booking details.'); return redirect(url_for('index'))
    conn=db(); cur=conn.cursor(dictionary=True)
    try:
        conn.start_transaction()
        cur.execute("SELECT s.*,sc.screen_id FROM screening s JOIN screen sc ON sc.screen_id=s.screen_id WHERE s.screening_id=%s AND s.status='SCHEDULED' FOR UPDATE",(screening_id,)); show=cur.fetchone()
        if not show: conn.rollback(); flash('Showtime is unavailable.'); return redirect(url_for('index'))
        marks=','.join(['%s']*len(ids)); cur.execute(f'SELECT seat_id FROM seat WHERE screen_id=%s AND seat_id IN ({marks})',(show['screen_id'],*ids)); valid=cur.fetchall()
        if len(valid)!=len(ids): conn.rollback(); flash('Invalid seat selection.'); return redirect(url_for('seats',screening_id=screening_id))
        cur.execute(f"SELECT bs.seat_id FROM booking_seat bs JOIN booking b ON b.booking_id=bs.booking_id WHERE b.screening_id=%s AND b.booking_status='CONFIRMED' AND bs.seat_status='BOOKED' AND bs.seat_id IN ({marks}) FOR UPDATE",(screening_id,*ids))
        if cur.fetchall(): conn.rollback(); flash('A seat has just been booked by someone else.'); return redirect(url_for('seats',screening_id=screening_id))
        total=float(show['base_price'])*len(ids)
        cur.execute("INSERT INTO booking (customer_id,screening_id,booking_date,total_amount,booking_status) VALUES (%s,%s,NOW(),%s,'CONFIRMED')",(session['customer_id'],screening_id,total)); bid=cur.lastrowid
        for sid in ids:
            cur.execute(
                """
                INSERT INTO booking_seat
                    (booking_id, seat_id, ticket_price, seat_status)
                VALUES (%s, %s, %s, 'BOOKED')
                """,
                (bid, sid, show['base_price'])
            )
            booking_seat_id = cur.lastrowid
            cur.execute(
                """
                INSERT INTO ticket (booking_seat_id, ticket_status)
                VALUES (%s, 'ACTIVE')
                """,
                (booking_seat_id,)
            )
        cur.execute("""
        INSERT INTO payment
        (booking_id, amount, payment_method, payment_status, transaction_reference)
        VALUES (%s, %s, %s, 'SUCCESS', %s)
        """,
    (bid, total, method, f'DEMO-{bid}-{os.urandom(4).hex()}'))
        conn.commit(); return redirect(url_for('confirmation',booking_id=bid))
    except Exception:
        conn.rollback(); raise
    finally: cur.close(); conn.close()

@app.route('/booking/<int:booking_id>/confirmation')
@login_required
def confirmation(booking_id):
    b=query("SELECT b.*,m.title,t.theater_name,t.city,sc.screen_name,sc.screen_type,s.screening_date,sl.slot_name,sl.start_time,c.full_name FROM booking b JOIN screening s ON s.screening_id=b.screening_id JOIN movie m ON m.movie_id=s.movie_id JOIN screen sc ON sc.screen_id=s.screen_id JOIN theater t ON t.theater_id=sc.theater_id JOIN slot sl ON sl.slot_id=s.slot_id JOIN customer c ON c.customer_id=b.customer_id WHERE b.booking_id=%s AND b.customer_id=%s",(booking_id,session['customer_id']),one=True)
    if not b: abort(404)
    b['seats']=query("SELECT se.row_label,se.seat_number FROM booking_seat bs JOIN seat se ON se.seat_id=bs.seat_id WHERE bs.booking_id=%s AND bs.seat_status='BOOKED' ORDER BY se.row_label,se.seat_number",(booking_id,))
    b['payment']=query('SELECT payment_method,payment_status FROM payment WHERE booking_id=%s ORDER BY payment_id DESC LIMIT 1',(booking_id,),one=True)
    return render_template('confirmation.html',booking=b)

@app.route('/my-bookings')
@login_required
def my_bookings():
    bookings=query("SELECT b.*,m.title,t.theater_name,t.city,sc.screen_name,sc.screen_type,s.screening_date,sl.slot_name,sl.start_time FROM booking b JOIN screening s ON s.screening_id=b.screening_id JOIN movie m ON m.movie_id=s.movie_id JOIN screen sc ON sc.screen_id=s.screen_id JOIN theater t ON t.theater_id=sc.theater_id JOIN slot sl ON sl.slot_id=s.slot_id WHERE b.customer_id=%s ORDER BY b.booking_date DESC",(session['customer_id'],))
    for b in bookings: b['seats']=query("SELECT se.row_label,se.seat_number FROM booking_seat bs JOIN seat se ON se.seat_id=bs.seat_id WHERE bs.booking_id=%s AND bs.seat_status='BOOKED' ORDER BY se.row_label,se.seat_number",(b['booking_id'],))
    return render_template('my_bookings.html',bookings=bookings)

@app.route('/cancel-booking/<int:booking_id>', methods=['POST'])
@login_required
def cancel_booking(booking_id):
    conn = db()
    cur = conn.cursor()
    try:
        conn.start_transaction()
        cur.execute(
            """
            SELECT booking_status
            FROM booking
            WHERE booking_id = %s AND customer_id = %s
            FOR UPDATE
            """,
            (booking_id, session['customer_id'])
        )
        b = cur.fetchone()
        if not b or b[0] != 'CONFIRMED':
            conn.rollback()
            flash('This booking cannot be cancelled.')
            return redirect(url_for('my_bookings'))
        # Cancel the booking.
        cur.execute(
            """
            UPDATE booking
            SET booking_status = 'CANCELLED'
            WHERE booking_id = %s
            """,
            (booking_id,)
        )
        # Release the booked seats.
        cur.execute(
            """
            UPDATE booking_seat
            SET seat_status = 'CANCELLED'
            WHERE booking_id = %s
            """,
            (booking_id,)
        )
        # Cancel tickets through their booking-seat relationship.
        cur.execute(
            """
            UPDATE ticket t
            JOIN booking_seat bs
                ON t.booking_seat_id = bs.booking_seat_id
            SET t.ticket_status = 'CANCELLED'
            WHERE bs.booking_id = %s
            """,
            (booking_id,)
        )
        # Mark the successful demo payment as refunded.
        cur.execute(
            """
            UPDATE payment
            SET payment_status = 'REFUNDED'
            WHERE booking_id = %s
              AND payment_status = 'SUCCESS'
            """,
            (booking_id,)
        )
        conn.commit()
        flash('Booking cancelled. Demo payment marked refunded.')
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()
    return redirect(url_for('my_bookings'))

if __name__=='__main__': app.run(host=os.getenv('FLASK_HOST','127.0.0.1'),port=int(os.getenv('FLASK_PORT','5000')),debug=os.getenv('FLASK_DEBUG','1')=='1')