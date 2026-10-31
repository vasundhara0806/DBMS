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

    def test_09_json_synchronization_and_endpoints(self):
        import json_sync
        import json
        import os

        # 1. Verify files exist on disk
        db_json_path = json_sync.get_database_state_path()
        act_json_path = json_sync.get_activity_log_path()
        self.assertTrue(os.path.exists(db_json_path), "database_state.json should exist on disk")
        self.assertTrue(os.path.exists(act_json_path), "activity_log.json should exist on disk")

        # 2. Verify file content structure
        with open(db_json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        self.assertIn('_metadata', data)
        self.assertIn('movies', data)
        self.assertIn('screenings', data)
        self.assertIn('theaters', data)
        self.assertIn('concession_items', data)
        self.assertIn('seat_categories', data)
        self.assertIn('bookings', data)

        # 3. Test API JSON endpoints
        res1 = self.client.get('/api/json/database')
        self.assertEqual(res1.status_code, 200)
        self.assertIn('application/json', res1.content_type)
        json1 = res1.get_json()
        self.assertIn('movies', json1)

        res2 = self.client.get('/api/json/activity')
        self.assertEqual(res2.status_code, 200)
        self.assertIn('application/json', res2.content_type)

        res3 = self.client.get('/api/json/table/movies')
        self.assertEqual(res3.status_code, 200)
        json3 = res3.get_json()
        self.assertEqual(json3['table'], 'movies')
        self.assertGreater(json3['count'], 0)

        # 4. Test view_json template
        res4 = self.client.get('/view-json')
        self.assertEqual(res4.status_code, 200)
        html4 = res4.data.decode('utf-8')
        self.assertIn('database_state.json', html4)
        self.assertIsNone(re.search(r'[\U00010000-\U0010ffff]', html4), "Found emoji in view_json.html!")

    def test_10_admin_editing_every_feature(self):
        import json_sync
        # Login as manager
        self.client.post('/login', data={'email': 'manager@cinesphere.com', 'password': 'Manager@123'}, follow_redirects=True)

        # 1. Edit movie
        res = self.client.post('/admin/movie/edit/1', data={
            'title': 'The Martian Extended Edition',
            'language': 'English',
            'duration_minutes': '155',
            'rating': 'UA',
            'dimension': 'IMAX 3D',
            'release_date': '2015-10-02',
            'synopsis': 'Updated synopsis for the test suite.',
            'genre_ids': ['2', '4']
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        # Verify DB updated
        m = database.query("SELECT * FROM movie WHERE movie_id = 1", one=True)
        self.assertEqual(m['title'], 'The Martian Extended Edition')

        # Verify JSON state updated
        state = json_sync.get_database_state()
        m_json = next(item for item in state['movies'] if item['movie_id'] == 1)
        self.assertEqual(m_json['title'], 'The Martian Extended Edition')

        # 2. Edit screening base price and status
        res_sc = self.client.post('/admin/screening/edit/1', data={
            'movie_id': '1',
            'screen_id': '1',
            'slot_id': '1',
            'screening_date': '2026-11-01',
            'base_price': '290.00',
            'status': 'SCHEDULED'
        }, follow_redirects=True)
        self.assertEqual(res_sc.status_code, 200)
        sc = database.query("SELECT * FROM screening WHERE screening_id = 1", one=True)
        self.assertEqual(float(sc['base_price']), 290.0)

        # 3. Edit theater
        res_th = self.client.post('/admin/theater/edit/1', data={
            'city_id': '1',
            'theater_name': 'CineSphere Luxe Banjara Hills Premium',
            'location_area': 'Banjara Hills Rd 2',
            'address': 'Banjara Hills Road No 2 Hyderabad'
        }, follow_redirects=True)
        self.assertEqual(res_th.status_code, 200)
        th = database.query("SELECT * FROM theater WHERE theater_id = 1", one=True)
        self.assertEqual(th['theater_name'], 'CineSphere Luxe Banjara Hills Premium')

        # 4. Edit screen
        res_scr = self.client.post('/admin/screen/edit/1', data={
            'screen_name': 'Screen 1 (IMAX Laser Dual 4K)',
            'screen_type': 'IMAX Laser'
        }, follow_redirects=True)
        self.assertEqual(res_scr.status_code, 200)
        scr = database.query("SELECT * FROM screen WHERE screen_id = 1", one=True)
        self.assertEqual(scr['screen_name'], 'Screen 1 (IMAX Laser Dual 4K)')

        # 5. Edit concession item price
        res_ci = self.client.post('/admin/concession/edit/1', data={
            'item_name': 'Jumbo Caramel Gourmet Popcorn',
            'category': 'Popcorn',
            'price': '280.00'
        }, follow_redirects=True)
        self.assertEqual(res_ci.status_code, 200)
        ci = database.query("SELECT * FROM concession_item WHERE item_id = 1", one=True)
        self.assertEqual(float(ci['price']), 280.0)

        # 6. Edit seat category multiplier
        res_cat = self.client.post('/admin/seat-category/edit/1', data={
            'category_name': 'VIP Recliner Supreme',
            'price_multiplier': '1.75',
            'description': 'Luxury leather motor recliners'
        }, follow_redirects=True)
        self.assertEqual(res_cat.status_code, 200)
        cat = database.query("SELECT * FROM seat_category WHERE category_id = 1", one=True)
        self.assertEqual(float(cat['price_multiplier']), 1.75)

        # 7. Edit booking status override
        res_b = self.client.post('/admin/booking/edit-status/2', data={
            'booking_status': 'CANCELLED'
        }, follow_redirects=True)
        self.assertEqual(res_b.status_code, 200)
        b = database.query("SELECT * FROM booking WHERE booking_id = 2", one=True)
        self.assertEqual(b['booking_status'], 'CANCELLED')

        # 8. Check activity log has entries for each action
        logs = json_sync.get_activity_log(limit=10)
        actions = [item['action'] for item in logs]
        self.assertIn('UPDATE_BOOKING_STATUS', actions)
        self.assertIn('UPDATE_SEAT_CATEGORY', actions)
        self.assertIn('UPDATE_CONCESSION', actions)
        self.assertIn('UPDATE_THEATER', actions)
        self.assertIn('UPDATE_SCREENING', actions)
        self.assertIn('UPDATE_MOVIE', actions)

if __name__ == '__main__':
    unittest.main()
