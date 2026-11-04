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

## Database Views, Stored Procedures & Triggers

The schema ships with real database objects that are demonstrated live in the Manager Portal
(**Views, Procedures & Triggers** tab, also at `/admin/db-objects`).

### 7 Views
| View | Purpose |
|---|---|
| `vw_booking_totals` | One row per booking with its seat count |
| `vw_booking_details` | Full audit join: customer, movie, theater, screen, slot and payment |
| `vw_movie_performance` | Bookings, tickets and gross revenue per movie |
| `vw_theater_performance` | Screens, bookings and gross revenue per theater |
| `vw_screening_occupancy` | Total vs booked seats and occupancy percentage per show |
| `vw_customer_spend` | Customer booking counts, tickets and total spend |
| `vw_concession_sales` | Food & beverage units sold and revenue |

### 6 Stored Procedures
| Procedure | Purpose |
|---|---|
| `sp_get_customer_bookings(customer_id)` | Full booking history for a customer |
| `sp_get_movie_revenue(movie_id)` | Revenue summary for one movie |
| `sp_get_available_seats(screening_id)` | Vacant seats with computed tier prices |
| `sp_revenue_report(start_date, end_date)` | Revenue by movie for a date range |
| `sp_schedule_screening(movie_id, screen_id, slot_id, date, price)` | Conflict-checked showtime insert |
| `sp_cancel_booking(booking_id)` | Cancels a confirmed booking and refunds its payment |

> MySQL uses native stored procedures (`CALL`). SQLite has no stored-procedure language, so the same
> procedures are emulated by the Python data layer; the admin console runs either version transparently.

### 9 Triggers
| Trigger | Rule enforced |
|---|---|
| `trg_booking_status_cascade` | Cancelling a booking cancels its seats/tickets and refunds payment |
| `trg_booking_restore_on_confirm` | Re-confirming a booking restores seats, tickets and payment |
| `trg_prevent_double_booking` | Blocks the same seat being booked twice for one screening |
| `trg_screening_conflict_insert` | Blocks duplicate screen/date/slot showtimes |
| `trg_screening_conflict_update` | Blocks conflicting showtime edits |
| `trg_screen_seat_count_insert` | Keeps `screen.total_seats` correct after seat inserts |
| `trg_screen_seat_count_update` | Keeps the count correct when seats are activated/deactivated |
| `trg_screen_seat_count_delete` | Keeps the count correct after seat deletes |
| `trg_booking_seat_ticket_sync` | Mirrors seat status changes onto the linked ticket |

The console includes a **Trigger Test Lab** that exercises each rule inside a transaction and rolls
it back, so live demo data is never modified. The Financial Analytics tab now reads directly from
`vw_movie_performance` and `vw_theater_performance`.

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

## Real-Time JSON Synchronization ("Sir's Inspection Engine")

Whenever **ANY** insertion, edit, delete, booking, or cancellation takes place anywhere in CineSphere, the system automatically mirrors and updates two JSON files in real time:

1. **`database_state.json`**:
   - Complete, structured snapshot of all 17 relational database tables (movies, screenings, theaters, screens, seat categories, concession items, customers, bookings, tickets, and payments).
   - Formatted with 2-space indentation for immediate inspection in VS Code or web browsers.
   - Includes metadata header: `last_synced_at`, `active_engine`, `last_action`, and record count totals.

2. **`activity_log.json`**:
   - Chronological audit log of every mutation / operation executed in the application.
   - Records: incremental ID, exact timestamp (`YYYY-MM-DD HH:MM:SS`), action type (`INSERT_SCREENING`, `CREATE_BOOKING`, `UPDATE_MOVIE`, `UPDATE_THEATER`, `UPDATE_SEAT_CATEGORY`, etc.), target table, initiating user, and payload details.

### How to Show the JSON File to Your Professor / Sir:
- **Direct in Project Root**: Open `database_state.json` or `activity_log.json` directly in VS Code or Notepad.
- **In the Admin Portal**: Navigate to `/admin` and click the **Live JSON File Inspector** tab. It includes live search, table filtering, 1-click clipboard copy, and a live refresh button.
- **Dedicated Full-Page Inspector**: Open **`http://127.0.0.1:5000/view-json`** (also accessible from the top navigation bar).
- **Download as JSON**: Click "Download JSON" in the Admin Portal or visit `/admin/download-json/database` / `/admin/download-json/activity`.
- **Raw API JSON Endpoints**:
  - `GET /api/json/database` — Returns full live database state as JSON.
  - `GET /api/json/activity` — Returns full activity log as JSON.
  - `GET /api/json/table/<table_name>` — Returns specific table records as JSON (e.g. `/api/json/table/movies`).

---

## Live System Date & Time Display

The Admin Portal now includes a live system date and time widget:
- **Real-Time Digital Clock**: Smooth 1-second pulse displaying `HH:MM:SS AM/PM` with a live green indicator.
- **Full Date Display**: Full weekday, day, month, and year (e.g. `Saturday, 31 October 2026`).
- **Last Sync Timestamp**: Shows the exact date & time when the database was last synchronized with `database_state.json`.
- **Audit Timestamps**: All screenings, bookings, and activity logs display full date and time timestamps down to the second.

---

## Full Feature Editing in Admin Portal

Every feature displayed across the customer website can now be directly modified from the Manager Admin Portal:

1. **Movies Catalog**:
   - **Edit Movie**: Update title, synopsis, language, duration (mins), censor certificate rating (U/UA/A), format (2D/3D/IMAX 3D/4DX), release date, and genre associations.
   - **Add Movie**: Create new film listings that immediately display on the home page.
   - **Delete Movie**: Safely remove movie records.
2. **Showtimes & Schedules**:
   - **Edit Showtime**: Modify screening dates, time slots, base ticket price (Rs.), and status (`SCHEDULED`, `CANCELLED`, `COMPLETED`).
   - **Schedule Showtime**: Add new showtimes with automatic conflict checking.
   - **Delete Showtime**: Cancel or remove showtimes from the public schedule.
3. **Theaters & Auditoriums**:
   - **Edit Theater**: Update multiplex venue name, metro city hub, location area, and address.
   - **Add Theater**: Add new cinema multiplexes with automatic default screen and 60 seats.
   - **Edit Screen**: Change screen label and audio-visual projection formats (IMAX 3D, Dolby Atmos, VIP Gold Class, etc.).
4. **Food & Concession Items**:
   - **Edit Concession**: Change snack item name, category (Popcorn, Snacks, Beverages, Combos), and price (Rs.).
   - **Add Concession**: Add new F&B items available during customer checkout.
   - **Delete Concession**: Remove items from the concession menu.
5. **Seat Tiers & Pricing Multipliers**:
   - **Edit Tier Multiplier**: Adjust pricing multipliers for VIP Recliners (e.g. 1.50x to 1.75x), Prime Gold (1.20x), and Classic Silver (1.00x) with immediate effect on ticket prices.
   - **Edit Description**: Update seating tier descriptions and luxury amenities.
6. **Booking Status & Overrides**:
   - **Update Status**: Manually toggle booking status between `CONFIRMED` and `CANCELLED`, with automatic cascade to ticket and payment statuses.

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

