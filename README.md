# CineSphere — Advanced Movie Ticket Booking System (BookMyShow Architecture)

A full-stack DBMS application built with **Flask**, **MySQL 8.x** (with automatic zero-config **SQLite fallback**), and modern vanilla CSS. Features complete BookMyShow-style multi-city, multi-theater discovery, screen formats, multi-tier auditorium seat maps, concession snacks, customer e-tickets, and a dedicated **Manager / Admin Portal** with comprehensive booking audit logs ("who booked when"), live screen occupancy visualizer, and financial analytics.

---

## Key Features

1. **BookMyShow Multi-Theater & Multi-City Discovery**:
   - Filter screenings across **Hyderabad, Bengaluru, and Mumbai**.
   - Browse by **Movies** or browse by **Theaters & Multiplexes**.
   - Date navigation pills (Today, Tomorrow, Day+2, Day+3).
   - Multiplex groupings with format tags: **IMAX 3D, 4DX Motion, Dolby Atmos, and Gold Class Luxe**.
   - Interactive show timing chips (Morning, Matinee, Evening Prime, Night, Late Night).

2. **Expanded Multi-Tier Auditorium Seating (490+ Total Seats)**:
   - Realistic 60-seat screens with aisle walkways (left wing, aisle, right wing).
   - Multi-tier seat categories with relational multipliers:
     - **VIP Recliner** (Row A, plush leather motor-recliners)
     - **Prime Gold** (Rows B, C, D, premium club seats)
     - **Classic Silver** (Rows E, F, standard cinema seating)
   - Real-time client-side price computation and live legend.

3. **Concessions & Food Add-ons**:
   - Optional snack add-ons (Jumbo Caramel Popcorn, Cheese Nachos, Cold Coffee, Couple Combos) with itemized billing.

4. **Dedicated Manager / Admin Portal (`/admin` or `/manager`)**:
   - **Comprehensive Customer Booking Audit Trail**:
     - Inspect **who booked when**: Customer full name, email, phone number, exact timestamp down to the second.
     - View exact movie, theater, screen, format, date, and showtime.
     - View individual seats booked with tier categories and unique ticket verification codes.
     - Payment details: simulated mode (UPI, Card, Net Banking, Cash), transaction reference ID, and status.
   - **Auditorium Seat Occupancy Inspector**:
     - Select any scheduled screening from a dropdown to inspect live seat layout.
     - Occupancy percentage bar and occupied count.
     - Hover or click any occupied seat to see customer name, contact info, booking time, and reference ID.
   - **Showtime Scheduler**:
     - Add new movie screenings to any screen and slot with conflict prevention.
   - **Financial Analytics**:
     - Gross revenue and ticket counts broken down by movie and theater.
   - **Manager Override**:
     - Direct booking cancellation and payment refund issuance from the portal.

5. **Design Aesthetics**:
   - Sleek dark purple/violet cinematic theme (`#100d20`, `#1c1732`, `#b69cff`).
   - Clean SVG icons and typography. **Strictly no emojis.**
   - Print-ready e-ticket receipt with barcode graphics.

---

## Relational Database Architecture (17 Tables)

1. `city` — Metro hubs (Hyderabad, Bengaluru, Mumbai)
2. `theater` — Cinemas and multiplexes linked to cities
3. `screen` — Auditoriums linked to theaters (IMAX, 4DX, Atmos, Luxe)
4. `seat_category` — Pricing tiers (VIP Recliner, Prime Gold, Classic Silver)
5. `seat` — Individual auditorium seats with row labels, numbers, and categories
6. `genre` — Movie genres
7. `movie` — Film details, certificates, formats, and synopses
8. `movie_genre` — Many-to-many relationship mapping movies to genres
9. `slot` — Show time slots (Morning, Matinee, Evening, Night, Late Night)
10. `screening` — Scheduled shows linking movie, screen, slot, date, and base price
11. `customer` — User accounts with role distinction (`CUSTOMER`, `MANAGER`, `ADMIN`)
12. `concession_item` — Food and beverage menu items with pricing
13. `booking` — Primary booking transactions with unique reference codes
14. `booking_seat` — Itemized seats reserved per booking with seat status
15. `ticket` — Unique e-ticket codes issued per booked seat
16. `payment` — Payment transaction records and refund tracking
17. `booking_concession` — Food & beverage add-on orders linked to bookings

---

## Getting Started

### 1. Requirements
- Python 3.10+
- (Optional) MySQL 8.x. *Note: If MySQL is not running on your machine, CineSphere automatically falls back to an embedded SQLite database (`cinesphere.db`) with zero configuration required!*

### 2. Setup
Clone or navigate to the project directory:
```bash
cd c:\dbmsVas\DBMS_Mini-Project_Batch6
```

Install requirements:
```bash
pip install -r requirements.txt
```

### 3. Run the Application
```bash
python app.py
```
Visit **http://127.0.0.1:5000** in your browser.

---

## Demo Accounts & Evaluation Credentials

| Role | Name | Email | Password |
|---|---|---|---|
| **Manager / Admin** | Vikram Malhotra | `manager@cinesphere.com` | `Manager@123` |
| **Customer 1** | Arjun Kumar | `arjun@example.com` | `Demo@123` |
| **Customer 2** | Priya Sharma | `priya@example.com` | `Demo@123` |
| **Customer 3** | Rahul Verma | `rahul@example.com` | `Demo@123` |

> **Pro-Tip for Live Demos**: Use the fast demo switcher bar at the top of every page (`Switch to Manager View` / `Switch to Customer View`) or the 1-click credential buttons on the login page to transition between roles seamlessly!

---

## Initializing MySQL (For Presentation / Submission)
If you wish to run on a local MySQL server:
1. Open MySQL Workbench or MySQL CLI:
   ```bash
   mysql -u root -p < init_schema.sql
   ```
2. Copy `.env.example` to `.env` and set your MySQL password:
   ```ini
   DB_HOST=127.0.0.1
   DB_PORT=3306
   DB_USER=root
   DB_PASSWORD=your_password
   DB_NAME=cinesphere
   ```
3. Run `python app.py`. CineSphere will automatically connect to your MySQL database!
