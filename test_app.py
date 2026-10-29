import unittest
import re
from app import app
import database

class CineSphereTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        database.init_sqlite_db()

    def setUp(self):
        self.app = app
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

    def test_01_index_and_cities(self):
        res = self.client.get('/')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        self.assertIn('CineSphere', html)
        self.assertIn('Now Showing', html)
        self.assertIn('The Martian', html)
        self.assertIn('Project Hail Mary', html)
        # Check no emojis
        self.assertIsNone(re.search(r'[\U00010000-\U0010ffff]', html), "Found emoji in index.html!")

    def test_02_theaters_list(self):
        res = self.client.get('/theaters?city=Hyderabad')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        self.assertIn('CineSphere Luxe Banjara', html)
        self.assertIn('CineSphere IMAX Forum Mall', html)
        self.assertIsNone(re.search(r'[\U00010000-\U0010ffff]', html), "Found emoji in theaters.html!")

    def test_03_movie_details(self):
        res = self.client.get('/movie/1')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        self.assertIn('The Martian', html)
        self.assertIn('Select Theater & Showtimes', html)
        self.assertIsNone(re.search(r'[\U00010000-\U0010ffff]', html), "Found emoji in movie_details.html!")

    def test_04_bookmyshow_showtimes(self):
        res = self.client.get('/movie/1/showtimes?city=Hyderabad')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        self.assertIn('The Martian', html)
        self.assertIn('Select Date', html)
        self.assertIn('CineSphere Luxe Banjara', html)
        self.assertIsNone(re.search(r'[\U00010000-\U0010ffff]', html), "Found emoji in showtimes.html!")

    def test_05_customer_login_and_seats(self):
        # Login as customer Arjun
        res = self.client.post('/login', data={'email': 'arjun@example.com', 'password': 'Demo@123'}, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        # Access seats for screening 1
        res = self.client.get('/show/1/seats')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        self.assertIn('Choose Seats', html)
        self.assertIn('VIP Recliner', html)
        self.assertIn('Prime Gold', html)
        self.assertIn('Classic Silver', html)
        self.assertIn('seat-tier-section', html)
        self.assertIsNone(re.search(r'[\U00010000-\U0010ffff]', html), "Found emoji in seats.html!")

    def test_06_booking_flow_and_confirmation(self):
        # Login
        self.client.post('/login', data={'email': 'arjun@example.com', 'password': 'Demo@123'}, follow_redirects=True)

        # Review booking for screening 1, seats 31 and 32 (Row D)
        res = self.client.post('/show/1/booking', data={'seat_ids': [31, 32]})
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        self.assertIn('Selected Seats', html)
        self.assertIn('Add Food & Beverages', html)
        self.assertIn('Jumbo Caramel Popcorn', html)

        # Confirm booking with 1 Popcorn
        res = self.client.post('/create-booking', data={
            'screening_id': '1',
            'seat_ids': ['31', '32'],
            'payment_method': 'UPI',
            'qty_1': '1'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        self.assertIn('Booking Confirmed', html)
        self.assertIn('CS-2026-', html)
        self.assertIn('TCK-', html)
        self.assertIn('Jumbo Caramel Popcorn', html)
        self.assertIsNone(re.search(r'[\U00010000-\U0010ffff]', html), "Found emoji in confirmation.html!")

    def test_07_manager_portal_access_and_audit(self):
        # Login as Manager Vikram
        res = self.client.post('/login', data={'email': 'manager@cinesphere.com', 'password': 'Manager@123'}, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        # Access /admin
        res = self.client.get('/admin')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        self.assertIn('Operations & Booking Audit Portal', html)
        self.assertIn('Comprehensive Booking Records & Customer Audit', html)
        self.assertIn('When Booked', html)
        self.assertIn('Who Booked (Customer)', html)
        self.assertIn('Arjun Kumar', html)
        self.assertIn('Auditorium Seat Occupancy Inspector', html)
        self.assertIn('Schedule New Showtime', html)
        self.assertIn('Financial Analytics', html)
        self.assertIsNone(re.search(r'[\U00010000-\U0010ffff]', html), "Found emoji in admin.html!")

        # API Occupancy test
        api_res = self.client.get('/admin/screening-occupancy/1')
        self.assertEqual(api_res.status_code, 200)
        json_data = api_res.get_json()
        self.assertIn('total_seats', json_data)
        self.assertIn('occupied_count', json_data)
        self.assertGreater(json_data['total_seats'], 50)

    def test_08_customer_cannot_access_manager_portal(self):
        # Switch to customer
        self.client.get('/switch-role?to=customer')
        res = self.client.get('/admin', follow_redirects=True)
        html = res.data.decode('utf-8')
        self.assertIn('Access restricted', html)

if __name__ == '__main__':
    unittest.main()
