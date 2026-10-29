-- CineSphere DBMS Schema (BookMyShow Architecture)
-- Compatible with MySQL 8.x

DROP DATABASE IF EXISTS cinesphere;
CREATE DATABASE cinesphere CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE cinesphere;

-- 1. City / Location Table
CREATE TABLE city (
    city_id INT AUTO_INCREMENT PRIMARY KEY,
    city_name VARCHAR(100) NOT NULL UNIQUE,
    state VARCHAR(100) NOT NULL
);

-- 2. Theater Table
CREATE TABLE theater (
    theater_id INT AUTO_INCREMENT PRIMARY KEY,
    city_id INT NOT NULL,
    theater_name VARCHAR(150) NOT NULL,
    address VARCHAR(255) NOT NULL,
    location_area VARCHAR(100) NOT NULL,
    FOREIGN KEY (city_id) REFERENCES city(city_id) ON DELETE CASCADE
);

-- 3. Screen / Auditorium Table
CREATE TABLE screen (
    screen_id INT AUTO_INCREMENT PRIMARY KEY,
    theater_id INT NOT NULL,
    screen_name VARCHAR(60) NOT NULL,
    screen_type VARCHAR(60) DEFAULT 'Standard 2D',
    total_seats INT DEFAULT 0,
    FOREIGN KEY (theater_id) REFERENCES theater(theater_id) ON DELETE CASCADE
);

-- 4. Seat Category / Tier Table
CREATE TABLE seat_category (
    category_id INT AUTO_INCREMENT PRIMARY KEY,
    category_name VARCHAR(60) NOT NULL UNIQUE,
    price_multiplier DECIMAL(4,2) NOT NULL DEFAULT 1.00,
    description VARCHAR(150)
);

-- 5. Seat Table
CREATE TABLE seat (
    seat_id INT AUTO_INCREMENT PRIMARY KEY,
    screen_id INT NOT NULL,
    category_id INT NOT NULL,
    row_label VARCHAR(5) NOT NULL,
    seat_number INT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    UNIQUE (screen_id, row_label, seat_number),
    FOREIGN KEY (screen_id) REFERENCES screen(screen_id) ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES seat_category(category_id)
);

-- 6. Genre Table
CREATE TABLE genre (
    genre_id INT AUTO_INCREMENT PRIMARY KEY,
    genre_name VARCHAR(60) NOT NULL UNIQUE
);

-- 7. Movie Table
CREATE TABLE movie (
    movie_id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(180) NOT NULL,
    synopsis TEXT,
    language VARCHAR(60) DEFAULT 'English',
    duration_minutes INT NOT NULL,
    release_date DATE,
    rating VARCHAR(10) DEFAULT 'UA',
    dimension VARCHAR(30) DEFAULT '2D'
);

-- 8. Movie Genre Mapping
CREATE TABLE movie_genre (
    movie_id INT NOT NULL,
    genre_id INT NOT NULL,
    PRIMARY KEY (movie_id, genre_id),
    FOREIGN KEY (movie_id) REFERENCES movie(movie_id) ON DELETE CASCADE,
    FOREIGN KEY (genre_id) REFERENCES genre(genre_id) ON DELETE CASCADE
);

-- 9. Slot / Time Slots Table
CREATE TABLE slot (
    slot_id INT AUTO_INCREMENT PRIMARY KEY,
    slot_name VARCHAR(60) NOT NULL,
    start_time TIME NOT NULL
);

-- 10. Screening / Showtimes Table
CREATE TABLE screening (
    screening_id INT AUTO_INCREMENT PRIMARY KEY,
    movie_id INT NOT NULL,
    screen_id INT NOT NULL,
    slot_id INT NOT NULL,
    screening_date DATE NOT NULL,
    base_price DECIMAL(10,2) NOT NULL,
    status ENUM('SCHEDULED', 'CANCELLED', 'COMPLETED') DEFAULT 'SCHEDULED',
    FOREIGN KEY (movie_id) REFERENCES movie(movie_id) ON DELETE CASCADE,
    FOREIGN KEY (screen_id) REFERENCES screen(screen_id) ON DELETE CASCADE,
    FOREIGN KEY (slot_id) REFERENCES slot(slot_id)
);

-- 11. Customer / User Account Table with Role Separation
CREATE TABLE customer (
    customer_id INT AUTO_INCREMENT PRIMARY KEY,
    full_name VARCHAR(120) NOT NULL,
    email VARCHAR(190) NOT NULL UNIQUE,
    phone VARCHAR(30) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('CUSTOMER', 'MANAGER', 'ADMIN') NOT NULL DEFAULT 'CUSTOMER',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 12. Concession Item (Food & Beverage) Table
CREATE TABLE concession_item (
    item_id INT AUTO_INCREMENT PRIMARY KEY,
    item_name VARCHAR(120) NOT NULL,
    category VARCHAR(60) NOT NULL,
    price DECIMAL(10,2) NOT NULL
);

-- 13. Booking Table
CREATE TABLE booking (
    booking_id INT AUTO_INCREMENT PRIMARY KEY,
    booking_reference VARCHAR(30) NOT NULL UNIQUE,
    customer_id INT NOT NULL,
    screening_id INT NOT NULL,
    booking_date DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    total_amount DECIMAL(10,2) NOT NULL,
    booking_status ENUM('CONFIRMED', 'CANCELLED') DEFAULT 'CONFIRMED',
    FOREIGN KEY (customer_id) REFERENCES customer(customer_id),
    FOREIGN KEY (screening_id) REFERENCES screening(screening_id)
);

-- 14. Booking Seat Table
CREATE TABLE booking_seat (
    booking_seat_id INT AUTO_INCREMENT PRIMARY KEY,
    booking_id INT NOT NULL,
    seat_id INT NOT NULL,
    ticket_price DECIMAL(10,2) NOT NULL,
    seat_status ENUM('BOOKED', 'CANCELLED') DEFAULT 'BOOKED',
    UNIQUE (booking_id, seat_id),
    FOREIGN KEY (booking_id) REFERENCES booking(booking_id) ON DELETE CASCADE,
    FOREIGN KEY (seat_id) REFERENCES seat(seat_id)
);

-- 15. Ticket Table
CREATE TABLE ticket (
    ticket_id INT AUTO_INCREMENT PRIMARY KEY,
    booking_seat_id INT NOT NULL UNIQUE,
    ticket_code VARCHAR(60) NOT NULL UNIQUE,
    issued_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ticket_status ENUM('ACTIVE', 'CANCELLED') NOT NULL DEFAULT 'ACTIVE',
    FOREIGN KEY (booking_seat_id) REFERENCES booking_seat(booking_seat_id) ON DELETE CASCADE
);

-- 16. Payment Table
CREATE TABLE payment (
    payment_id INT AUTO_INCREMENT PRIMARY KEY,
    booking_id INT NOT NULL,
    payment_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    amount DECIMAL(10,2) NOT NULL,
    payment_method ENUM('UPI', 'CARD', 'NET_BANKING', 'CASH') NOT NULL,
    payment_status ENUM('SUCCESS', 'FAILED', 'REFUNDED') DEFAULT 'SUCCESS',
    transaction_reference VARCHAR(100) UNIQUE,
    FOREIGN KEY (booking_id) REFERENCES booking(booking_id) ON DELETE CASCADE
);

-- 17. Booking Concessions (Add-on Food Orders)
CREATE TABLE booking_concession (
    booking_concession_id INT AUTO_INCREMENT PRIMARY KEY,
    booking_id INT NOT NULL,
    item_id INT NOT NULL,
    quantity INT NOT NULL DEFAULT 1,
    subtotal DECIMAL(10,2) NOT NULL,
    FOREIGN KEY (booking_id) REFERENCES booking(booking_id) ON DELETE CASCADE,
    FOREIGN KEY (item_id) REFERENCES concession_item(item_id)
);

-- =======================================================
-- SEED DATA
-- =======================================================

-- Cities
INSERT INTO city (city_name, state) VALUES
('Hyderabad', 'Telangana'),
('Bengaluru', 'Karnataka'),
('Mumbai', 'Maharashtra');

-- Theaters
INSERT INTO theater (city_id, theater_name, address, location_area) VALUES
(1, 'CineSphere Luxe Banjara', 'Road No. 2, Banjara Hills', 'Banjara Hills'),
(1, 'CineSphere IMAX Forum Mall', 'Kukatpally Housing Board Colony', 'Kukatpally'),
(1, 'CineSphere Riverside Gachibowli', 'Financial District, Nanakramguda', 'Gachibowli'),
(2, 'CineSphere Forum Koramangala', 'Hosur Road, 7th Block, Koramangala', 'Koramangala'),
(2, 'CineSphere Orion Mall', 'Dr Rajkumar Rd, Rajajinagar', 'Rajajinagar'),
(3, 'CineSphere Palladium Luxe', 'High Street Phoenix, Lower Parel', 'Lower Parel');

-- Screens
INSERT INTO screen (theater_id, screen_name, screen_type, total_seats) VALUES
(1, 'Screen 1 (IMAX 3D)', 'IMAX 3D', 60),
(1, 'Screen 2 (Dolby Atmos)', 'Dolby Atmos 2D', 60),
(1, 'Screen 3 (Gold Class)', 'VIP Gold Class', 36),
(2, 'IMAX Laser Experience', 'IMAX Laser', 60),
(2, 'Screen 2 (4DX)', '4DX Motion', 60),
(3, 'Screen 1 (Dolby Vision)', 'Dolby Vision 4K', 60),
(4, 'Screen 1 (IMAX)', 'IMAX 3D', 60),
(5, 'Screen 1 (PXL Atmos)', 'Dolby Atmos', 60),
(6, 'Screen 1 (Luxe Insignia)', 'VIP Gold Class', 36);

-- Seat Categories
INSERT INTO seat_category (category_name, price_multiplier, description) VALUES
('VIP Recliner', 1.50, 'Plush leather motor-recliners with extra legroom'),
('Prime Gold', 1.20, 'Premium viewing angle with cushioned club seats'),
('Classic Silver', 1.00, 'Standard comfortable cinema seating');

-- Genres
INSERT INTO genre (genre_name) VALUES
('Action'), ('Sci-Fi'), ('Drama'), ('Adventure'), ('Comedy'), ('Thriller');

-- Movies
INSERT INTO movie (title, synopsis, language, duration_minutes, release_date, rating, dimension) VALUES
('The Martian', 'An astronaut stranded on Mars uses his scientific knowledge and determination to survive and find a way back home.', 'English', 144, '2015-10-02', 'UA', '2D, 3D'),
('Project Hail Mary', 'A lone astronaut awakens on a desperate mission to save Earth and uncover the cosmic mystery threatening humanity.', 'English', 150, '2026-03-20', 'UA', 'IMAX 3D'),
('Gran Turismo', 'A skilled gamer gets the opportunity to turn his virtual racing abilities into a real-world motorsport career.', 'English', 134, '2023-08-25', 'UA', '4DX, 2D'),
('Spider-Man: Brand New Day', 'Spider-Man faces a new chapter of challenges and adventures as he protects his city from emerging high-tech threats.', 'English', 140, '2026-07-31', 'UA', 'IMAX 3D, 2D'),
('Interstellar', 'A team of explorers travel through a wormhole in space in an attempt to ensure humanity survival.', 'English', 169, '2014-11-07', 'UA', 'IMAX 70mm'),
('Dune: Part Two', 'Paul Atreides unites with Chani and the Fremen while seeking revenge against the conspirators who destroyed his family.', 'English', 166, '2024-03-01', 'UA', 'IMAX 3D');

-- Movie Genres
INSERT INTO movie_genre (movie_id, genre_id) VALUES
(1, 2), (1, 3),
(2, 2), (2, 4),
(3, 1), (3, 3),
(4, 1), (4, 2),
(5, 2), (5, 3),
(6, 1), (6, 2);

-- Time Slots
INSERT INTO slot (slot_name, start_time) VALUES
('Morning Show', '10:00:00'),
('Matinee Show', '13:30:00'),
('Evening Prime', '17:15:00'),
('Night Show', '20:45:00'),
('Late Night Show', '23:15:00');

-- Concessions / Food Items
INSERT INTO concession_item (item_name, category, price) VALUES
('Jumbo Caramel Popcorn', 'Popcorn', 260.00),
('Salted Butter Popcorn', 'Popcorn', 220.00),
('Loaded Cheese Nachos with Salsa', 'Snacks', 240.00),
('Fountain Cola 600ml', 'Beverages', 150.00),
('Iced Cold Coffee', 'Beverages', 180.00),
('Couple Movie Combo (Jumbo Popcorn + 2 Drinks)', 'Combos', 480.00);

-- Populate Realistic Seats for Screens 1 to 9
-- Screen 1 to 8: 60 seats (Row A: Recliner 1-10; Rows B-D: Prime Gold 1-10; Rows E-F: Classic Silver 1-10)
-- Screen 3 & 9: 36 seats (VIP Gold Class: Rows A-C, 1-12)

DELIMITER $$
CREATE PROCEDURE PopulateSeats()
BEGIN
    DECLARE s_id INT;
    DECLARE r CHAR(1);
    DECLARE num INT;
    DECLARE cat INT;
    
    -- Loop through standard screens 1, 2, 4, 5, 6, 7, 8
    SET s_id = 1;
    WHILE s_id <= 8 DO
        IF s_id != 3 THEN
            -- Row A: Recliner (cat = 1)
            SET num = 1;
            WHILE num <= 10 DO
                INSERT INTO seat (screen_id, category_id, row_label, seat_number) VALUES (s_id, 1, 'A', num);
                SET num = num + 1;
            END WHILE;
            
            -- Rows B, C, D: Prime Gold (cat = 2)
            SET num = 1;
            WHILE num <= 10 DO
                INSERT INTO seat (screen_id, category_id, row_label, seat_number) VALUES (s_id, 2, 'B', num);
                INSERT INTO seat (screen_id, category_id, row_label, seat_number) VALUES (s_id, 2, 'C', num);
                INSERT INTO seat (screen_id, category_id, row_label, seat_number) VALUES (s_id, 2, 'D', num);
                SET num = num + 1;
            END WHILE;
            
            -- Rows E, F: Classic Silver (cat = 3)
            SET num = 1;
            WHILE num <= 10 DO
                INSERT INTO seat (screen_id, category_id, row_label, seat_number) VALUES (s_id, 3, 'E', num);
                INSERT INTO seat (screen_id, category_id, row_label, seat_number) VALUES (s_id, 3, 'F', num);
                SET num = num + 1;
            END WHILE;
        ELSE
            -- Screen 3: All VIP Gold Class Recliners (Rows A, B, C, 12 seats each)
            SET num = 1;
            WHILE num <= 12 DO
                INSERT INTO seat (screen_id, category_id, row_label, seat_number) VALUES (3, 1, 'A', num);
                INSERT INTO seat (screen_id, category_id, row_label, seat_number) VALUES (3, 1, 'B', num);
                INSERT INTO seat (screen_id, category_id, row_label, seat_number) VALUES (3, 1, 'C', num);
                SET num = num + 1;
            END WHILE;
        END IF;
        SET s_id = s_id + 1;
    END WHILE;
    
    -- Screen 9: VIP Gold Class
    SET num = 1;
    WHILE num <= 12 DO
        INSERT INTO seat (screen_id, category_id, row_label, seat_number) VALUES (9, 1, 'A', num);
        INSERT INTO seat (screen_id, category_id, row_label, seat_number) VALUES (9, 1, 'B', num);
        INSERT INTO seat (screen_id, category_id, row_label, seat_number) VALUES (9, 1, 'C', num);
        SET num = num + 1;
    END WHILE;
END$$
DELIMITER ;

CALL PopulateSeats();
DROP PROCEDURE PopulateSeats;

-- Seed Users: 1 Manager/Admin + Customers
-- Passwords:
-- Manager: Manager@123
-- Customers: Demo@123
INSERT INTO customer (full_name, email, phone, password_hash, role) VALUES
('Vikram Malhotra (Operations Manager)', 'manager@cinesphere.com', '9876543210', 'pbkdf2:sha256:600000$d13b68f68257a4f2$550380eac96b9472085fa342fd23cc3e6cc319f5f0a7605d118bca3162626a26', 'MANAGER'),
('Arjun Kumar', 'arjun@example.com', '9000000001', 'pbkdf2:sha256:600000$d13b68f68257a4f2$550380eac96b9472085fa342fd23cc3e6cc319f5f0a7605d118bca3162626a26', 'CUSTOMER'),
('Priya Sharma', 'priya@example.com', '9000000002', 'pbkdf2:sha256:600000$d13b68f68257a4f2$550380eac96b9472085fa342fd23cc3e6cc319f5f0a7605d118bca3162626a26', 'CUSTOMER'),
('Rahul Verma', 'rahul@example.com', '9000000003', 'pbkdf2:sha256:600000$d13b68f68257a4f2$550380eac96b9472085fa342fd23cc3e6cc319f5f0a7605d118bca3162626a26', 'CUSTOMER'),
('Sneha Reddy', 'sneha@example.com', '9000000004', 'pbkdf2:sha256:600000$d13b68f68257a4f2$550380eac96b9472085fa342fd23cc3e6cc319f5f0a7605d118bca3162626a26', 'CUSTOMER');

-- Screenings across Multiple Theaters & Show Timings
INSERT INTO screening (movie_id, screen_id, slot_id, screening_date, base_price, status) VALUES
-- The Martian at CineSphere Luxe Banjara (Screen 1 IMAX & Screen 2 Atmos)
(1, 1, 1, CURDATE(), 250.00, 'SCHEDULED'),
(1, 1, 3, CURDATE(), 320.00, 'SCHEDULED'),
(1, 1, 4, CURDATE(), 350.00, 'SCHEDULED'),
(1, 2, 2, CURDATE(), 220.00, 'SCHEDULED'),
-- Project Hail Mary at multiple theaters
(2, 1, 2, CURDATE(), 300.00, 'SCHEDULED'),
(2, 4, 3, CURDATE(), 320.00, 'SCHEDULED'),
(2, 6, 4, CURDATE(), 280.00, 'SCHEDULED'),
-- Gran Turismo
(3, 5, 2, CURDATE(), 260.00, 'SCHEDULED'),
(3, 2, 4, CURDATE(), 240.00, 'SCHEDULED'),
-- Spider-Man: Brand New Day
(4, 1, 5, CURDATE(), 380.00, 'SCHEDULED'),
(4, 4, 4, CURDATE(), 360.00, 'SCHEDULED'),
(4, 7, 3, CURDATE(), 320.00, 'SCHEDULED'),
-- Interstellar
(5, 4, 1, CURDATE(), 300.00, 'SCHEDULED'),
(5, 7, 4, CURDATE(), 340.00, 'SCHEDULED'),
-- Dune: Part Two
(6, 1, 3, DATE_ADD(CURDATE(), INTERVAL 1 DAY), 350.00, 'SCHEDULED'),
(6, 4, 3, DATE_ADD(CURDATE(), INTERVAL 1 DAY), 350.00, 'SCHEDULED');

-- Pre-seed Real-world Sample Bookings for Manager Audit Details
-- Booking 1: Arjun Kumar books 2 Prime Gold seats for The Martian
INSERT INTO booking (booking_reference, customer_id, screening_id, booking_date, total_amount, booking_status)
VALUES ('CS-2026-9081', 2, 2, DATE_SUB(NOW(), INTERVAL 4 HOUR), 768.00, 'CONFIRMED');

INSERT INTO booking_seat (booking_id, seat_id, ticket_price, seat_status)
VALUES (1, 15, 384.00, 'BOOKED'), (1, 16, 384.00, 'BOOKED');

INSERT INTO ticket (booking_seat_id, ticket_code, ticket_status)
VALUES (1, 'TCK-HYD-9081-01', 'ACTIVE'), (2, 'TCK-HYD-9081-02', 'ACTIVE');

INSERT INTO payment (booking_id, amount, payment_method, payment_status, transaction_reference)
VALUES (1, 768.00, 'UPI', 'SUCCESS', 'TXN-UPI-9823419081');

-- Booking 2: Priya Sharma books 1 Recliner VIP seat for Project Hail Mary
INSERT INTO booking (booking_reference, customer_id, screening_id, booking_date, total_amount, booking_status)
VALUES ('CS-2026-9142', 3, 5, DATE_SUB(NOW(), INTERVAL 2 HOUR), 450.00, 'CONFIRMED');

INSERT INTO booking_seat (booking_id, seat_id, ticket_price, seat_status)
VALUES (2, 5, 450.00, 'BOOKED');

INSERT INTO ticket (booking_seat_id, ticket_code, ticket_status)
VALUES (3, 'TCK-HYD-9142-01', 'ACTIVE');

INSERT INTO payment (booking_id, amount, payment_method, payment_status, transaction_reference)
VALUES (2, 450.00, 'CARD', 'SUCCESS', 'TXN-CARD-8839109142');

-- Booking 3: Rahul Verma booked and later cancelled
INSERT INTO booking (booking_reference, customer_id, screening_id, booking_date, total_amount, booking_status)
VALUES ('CS-2026-8803', 4, 1, DATE_SUB(NOW(), INTERVAL 1 DAY), 250.00, 'CANCELLED');

INSERT INTO booking_seat (booking_id, seat_id, ticket_price, seat_status)
VALUES (3, 22, 250.00, 'CANCELLED');

INSERT INTO ticket (booking_seat_id, ticket_code, ticket_status)
VALUES (4, 'TCK-HYD-8803-01', 'CANCELLED');

INSERT INTO payment (booking_id, amount, payment_method, payment_status, transaction_reference)
VALUES (3, 250.00, 'UPI', 'REFUNDED', 'TXN-UPI-7718298803');
