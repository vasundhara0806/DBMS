-- This will drop and recreate the Cinesphere database
DROP DATABASE IF EXISTS cinesphere;
CREATE DATABASE cinesphere CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE cinesphere;
CREATE TABLE customer(customer_id INT AUTO_INCREMENT PRIMARY KEY,full_name VARCHAR(120) NOT NULL,email VARCHAR(190) NOT NULL UNIQUE,phone VARCHAR(30) NOT NULL UNIQUE,password_hash VARCHAR(255) NOT NULL,created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE movie(movie_id INT AUTO_INCREMENT PRIMARY KEY,title VARCHAR(180) NOT NULL,synopsis TEXT,language VARCHAR(60) DEFAULT 'English',duration_minutes INT NOT NULL,release_date DATE,rating VARCHAR(10));
CREATE TABLE genre(genre_id INT AUTO_INCREMENT PRIMARY KEY,genre_name VARCHAR(60) NOT NULL UNIQUE);
CREATE TABLE theater(theater_id INT AUTO_INCREMENT PRIMARY KEY,theater_name VARCHAR(120) NOT NULL,city VARCHAR(100) NOT NULL);
CREATE TABLE slot(slot_id INT AUTO_INCREMENT PRIMARY KEY,slot_name VARCHAR(60) NOT NULL,start_time TIME NOT NULL);
CREATE TABLE screen(screen_id INT AUTO_INCREMENT PRIMARY KEY,theater_id INT NOT NULL,screen_name VARCHAR(60) NOT NULL,screen_type VARCHAR(60) DEFAULT 'Standard',FOREIGN KEY(theater_id) REFERENCES theater(theater_id));
CREATE TABLE seat(seat_id INT AUTO_INCREMENT PRIMARY KEY,screen_id INT NOT NULL,row_label VARCHAR(5) NOT NULL,seat_number INT NOT NULL,UNIQUE(screen_id,row_label,seat_number),FOREIGN KEY(screen_id) REFERENCES screen(screen_id));
CREATE TABLE movie_genre(movie_id INT NOT NULL,genre_id INT NOT NULL,PRIMARY KEY(movie_id,genre_id),FOREIGN KEY(movie_id) REFERENCES movie(movie_id),FOREIGN KEY(genre_id) REFERENCES genre(genre_id));
CREATE TABLE screening(screening_id INT AUTO_INCREMENT PRIMARY KEY,movie_id INT NOT NULL,screen_id INT NOT NULL,slot_id INT NOT NULL,screening_date DATE NOT NULL,base_price DECIMAL(10,2) NOT NULL,status ENUM('SCHEDULED','CANCELLED','COMPLETED') DEFAULT 'SCHEDULED',FOREIGN KEY(movie_id) REFERENCES movie(movie_id),FOREIGN KEY(screen_id) REFERENCES screen(screen_id),FOREIGN KEY(slot_id) REFERENCES slot(slot_id));
CREATE TABLE booking(booking_id INT AUTO_INCREMENT PRIMARY KEY,customer_id INT NOT NULL,screening_id INT NOT NULL,booking_date DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,total_amount DECIMAL(10,2) NOT NULL,booking_status ENUM('CONFIRMED','CANCELLED') DEFAULT 'CONFIRMED',FOREIGN KEY(customer_id) REFERENCES customer(customer_id),FOREIGN KEY(screening_id) REFERENCES screening(screening_id));
CREATE TABLE booking_seat(booking_seat_id INT AUTO_INCREMENT PRIMARY KEY,
    booking_id INT NOT NULL,
    seat_id INT NOT NULL,
    ticket_price DECIMAL(10,2) NOT NULL,
    seat_status ENUM('BOOKED','CANCELLED') DEFAULT 'BOOKED',
    UNIQUE (booking_id, seat_id),
    FOREIGN KEY (booking_id) REFERENCES booking(booking_id),
    FOREIGN KEY (seat_id) REFERENCES seat(seat_id));
CREATE TABLE ticket(ticket_id INT AUTO_INCREMENT PRIMARY KEY,
    booking_seat_id INT NOT NULL UNIQUE,
    issued_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    qr_code VARCHAR(255) UNIQUE,
    ticket_status ENUM('ACTIVE','CANCELLED') NOT NULL DEFAULT 'ACTIVE',
    FOREIGN KEY (booking_seat_id)
        REFERENCES booking_seat(booking_seat_id));
CREATE TABLE payment(payment_id INT AUTO_INCREMENT PRIMARY KEY,
    booking_id INT NOT NULL,
    payment_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    amount DECIMAL(10,2) NOT NULL,
    payment_method ENUM('UPI','CARD','CASH') NOT NULL,
    payment_status ENUM('SUCCESS','FAILED','REFUNDED') DEFAULT 'SUCCESS',
    transaction_reference VARCHAR(100) UNIQUE,
    FOREIGN KEY (booking_id) REFERENCES booking(booking_id));
INSERT INTO genre(genre_name) VALUES ('Action'),('Drama'),('Science Fiction'),('Comedy');
INSERT INTO movie(title,synopsis,language,duration_minutes,release_date,rating) VALUES
('The Martian','An astronaut stranded on Mars uses his scientific knowledge and determination to survive and find a way back home.','English',144,'2015-10-02','UA'),
('Project Hail Mary','A lone astronaut awakens on a desperate mission to save Earth and uncover the mystery threatening humanity.','English',150,'2026-03-20','UA'),
('Gran Turismo','A skilled gamer gets the opportunity to turn his virtual racing abilities into a real-world motorsport career.','English',134,'2023-08-25','UA'),
('Spider-Man: Brand New Day','Spider-Man faces a new chapter of challenges and adventures as he protects his city from new threats.','English',140,'2026-07-31','UA');
INSERT INTO movie_genre VALUES (1,1),(1,3),(2,2),(3,4),(4,1);
INSERT INTO theater(theater_name,city) VALUES ('CineSphere Central','Hyderabad'),('CineSphere Riverside','Hyderabad');
INSERT INTO screen(theater_id,screen_name,screen_type) VALUES (1,'Screen 1','IMAX'),(1,'Screen 2','Standard'),(2,'Screen 1','Dolby Atmos');
INSERT INTO slot(slot_name,start_time) VALUES ('Morning','10:00:00'),('Matinee','13:30:00'),('Evening','17:30:00'),('Night','20:45:00');
-- 12 seats per screen; add more seats here if desired.
INSERT INTO seat(screen_id,row_label,seat_number) VALUES
(1,'A',1),(1,'A',2),(1,'A',3),(1,'A',4),(1,'B',1),(1,'B',2),(1,'B',3),(1,'B',4),(1,'C',1),(1,'C',2),(1,'C',3),(1,'C',4),
(2,'A',1),(2,'A',2),(2,'A',3),(2,'A',4),(2,'B',1),(2,'B',2),(2,'B',3),(2,'B',4),(2,'C',1),(2,'C',2),(2,'C',3),(2,'C',4),
(3,'A',1),(3,'A',2),(3,'A',3),(3,'A',4),(3,'B',1),(3,'B',2),(3,'B',3),(3,'B',4),(3,'C',1),(3,'C',2),(3,'C',3),(3,'C',4);
INSERT INTO screening(movie_id, screen_id, slot_id, screening_date, base_price, status) VALUES
    (1, 1, 3, '2026-12-10', 300, 'SCHEDULED'),
    (2, 2, 2, '2026-12-10', 220, 'SCHEDULED'),
    (3, 3, 1, '2026-12-10', 200, 'SCHEDULED'),
    (4, 1, 4, '2026-12-10', 250, 'SCHEDULED');
-- Demo password for all seeded accounts: Demo@123
INSERT INTO customer(full_name,email,phone,password_hash) VALUES
('Arjun Kumar','arjun@example.com','9000000001','pbkdf2:sha256:600000$d13b68f68257a4f2$550380eac96b9472085fa342fd23cc3e6cc319f5f0a7605d118bca3162626a26'),
('Priya Sharma','priya@example.com','9000000002','pbkdf2:sha256:600000$d13b68f68257a4f2$550380eac96b9472085fa342fd23cc3e6cc319f5f0a7605d118bca3162626a26'),
('Rahul Verma','rahul@example.com','9000000003','pbkdf2:sha256:600000$d13b68f68257a4f2$550380eac96b9472085fa342fd23cc3e6cc319f5f0a7605d118bca3162626a26');
