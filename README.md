# CineSphere — Movie Ticket Booking Mini Project

A Flask + MySQL DBMS mini-project with account registration/login, movie listings, showtimes, seat selection, booking confirmation, booking history, and cancellation. Payments are simulated for demonstration only.

## Requirements
- Python 3.10+
- MySQL 8.x

## Setup
1. **Initialize the database.** Open MySQL as an administrator and run `init_schema.sql`. It begins by dropping and recreating the `cinesphere` database, so do not run it if you need to preserve an existing database.
2. Create and activate a virtual environment in this folder:
   - Windows: `python -m venv .venv` then `.venv\\Scripts\\activate`
   - macOS/Linux: `python3 -m venv .venv` then `source .venv/bin/activate`
3. Install dependencies: `pip install -r requirements.txt`
4. (Negligible) Copy `.env.example` to `.env` and set your MySQL credentials and a strong `SECRET_KEY`.
5. Start the app: `python app.py`
6. Visit http://127.0.0.1:5000

## Demo accounts
- `arjun@example.com`
- `priya@example.com`
- `rahul@example.com`

Password for each: `Demo@123`

You can also register a new account. Bookings use a demo payment status; no real payment provider is connected.

## Main routes
`/`, `/register`, `/login`, `/logout`, `/movie/<id>`, `/movie/<id>/showtimes`, `/show/<id>/seats`, `/show/<id>/booking`, `/create-booking`, `/booking/<id>/confirmation`, `/my-bookings`, `/cancel-booking/<id>`.

## Notes
- This is an educational prototype, not a production ticketing/payment service.
- The booking flow validates seat ownership and rechecks availability inside a transaction. Test it against your MySQL version and environment before your presentation.
