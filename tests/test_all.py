import sys, os, json, time, tempfile, unittest, re, secrets
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database import load, save, get_stats, get_user_status_label, get_auth_status
from cache import get, set, delete, clear
from utils import format_date, parse_duration

IP_RE = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")

class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump({}, self.tmp)
        self.tmp.close()
        import config
        import database
        database.DB_PATH = self.tmp.name

    def tearDown(self):
        os.unlink(self.tmp.name)

    def test_save_and_load(self):
        save({"192.168.1.1": {"status": "active", "expires_at": time.time() + 3600}})
        db = load()
        self.assertIn("192.168.1.1", db)
        self.assertEqual(db["192.168.1.1"]["status"], "active")

    def test_get_stats_empty(self):
        t, a, e, b = get_stats({})
        self.assertEqual(t, 0)
        self.assertEqual(a, 0)

    def test_get_stats_active(self):
        db = {"10.0.0.1": {"status": "active", "expires_at": time.time() + 3600}}
        t, a, e, b = get_stats(db)
        self.assertEqual(a, 1)

    def test_get_stats_expired(self):
        db = {"10.0.0.1": {"status": "active", "expires_at": time.time() - 10}}
        t, a, e, b = get_stats(db)
        self.assertEqual(e, 1)

    def test_get_stats_blocked(self):
        db = {"10.0.0.1": {"status": "blocked", "expires_at": 0}}
        t, a, e, b = get_stats(db)
        self.assertEqual(b, 1)

    def test_user_status_active(self):
        label = get_user_status_label({"status": "active", "expires_at": time.time() + 3600})
        self.assertIn("Active", label)

    def test_user_status_expired(self):
        label = get_user_status_label({"status": "active", "expires_at": time.time() - 10})
        self.assertIn("Expired", label)

    def test_user_status_blocked(self):
        label = get_user_status_label({"status": "blocked"})
        self.assertIn("Banned", label)

    def test_auth_status_active(self):
        save({"192.168.1.1": {"status": "active", "expires_at": time.time() + 3600}})
        self.assertEqual(get_auth_status("192.168.1.1"), "ACTIVE")

    def test_auth_status_banned(self):
        save({"192.168.1.1": {"status": "blocked", "expires_at": 0}})
        self.assertEqual(get_auth_status("192.168.1.1"), "BANNED")

    def test_auth_status_not_found(self):
        self.assertEqual(get_auth_status("999.999.999.999"), "NOT_FOUND")

    def test_is_valid_ip(self):
        self.assertTrue(IP_RE.match("192.168.1.1"))
        self.assertTrue(IP_RE.match("10.0.0.255"))
        self.assertFalse(IP_RE.match("256.1.1.1"))
        self.assertFalse(IP_RE.match("abc"))
        self.assertFalse(IP_RE.match("12345"))

class TestCache(unittest.TestCase):
    def setUp(self):
        clear()

    def test_set_and_get(self):
        set("key1", "value1")
        self.assertEqual(get("key1"), "value1")

    def test_expiry(self):
        set("key2", "value2", ttl=0)
        import time
        time.sleep(0.1)
        self.assertIsNone(get("key2"))

    def test_delete(self):
        set("key3", "value3")
        delete("key3")
        self.assertIsNone(get("key3"))

    def test_clear(self):
        set("a", 1)
        set("b", 2)
        clear()
        self.assertIsNone(get("a"))
        self.assertIsNone(get("b"))

class TestUtils(unittest.TestCase):
    def test_format_date(self):
        self.assertEqual(format_date(0), "—")
        self.assertEqual(format_date(None), "—")

    def test_parse_duration_minutes(self):
        self.assertEqual(parse_duration("30m"), 1800)

    def test_parse_duration_hours(self):
        self.assertEqual(parse_duration("6h"), 21600)

    def test_parse_duration_days(self):
        self.assertEqual(parse_duration("14d"), 1209600)

    def test_parse_duration_hours_default(self):
        self.assertEqual(parse_duration("2"), 7200)

class TestKeys(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump({}, self.tmp)
        self.tmp.close()
        import config
        import keys
        keys.KEYS_PATH = self.tmp.name
        self.keys = keys

    def tearDown(self):
        os.unlink(self.tmp.name)

    def test_generate_key(self):
        code = self.keys.generate_key(86400)
        self.assertTrue(code.startswith("TILINX-"))
        self.assertEqual(len(code), 19)  # TILINX- + 12 hex chars

    def test_redeem_valid(self):
        code = self.keys.generate_key(3600)
        self.tmp_db = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump({}, self.tmp_db)
        self.tmp_db.close()
        import database
        database.DB_PATH = self.tmp_db.name
        result = self.keys.redeem_key(code, "192.168.1.1")
        self.assertEqual(result, "OK")
        db = database.load()
        self.assertIn("192.168.1.1", db)
        self.assertEqual(db["192.168.1.1"]["status"], "active")
        os.unlink(self.tmp_db.name)

    def test_redeem_invalid(self):
        result = self.keys.redeem_key("FAKE", "1.1.1.1")
        self.assertEqual(result, "INVALID")

    def test_redeem_twice(self):
        code = self.keys.generate_key(3600)
        self.tmp_db = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump({}, self.tmp_db)
        self.tmp_db.close()
        import database
        database.DB_PATH = self.tmp_db.name
        self.keys.redeem_key(code, "1.1.1.1")
        result = self.keys.redeem_key(code, "2.2.2.2")
        self.assertEqual(result, "ALREADY_USED")
        os.unlink(self.tmp_db.name)

    def test_list_keys(self):
        self.keys.generate_key(3600)
        self.keys.generate_key(86400)
        k = self.keys.list_keys()
        self.assertEqual(len(k), 2)

    def test_delete_key(self):
        code = self.keys.generate_key(3600)
        self.assertTrue(self.keys.delete_key(code))
        self.assertFalse(self.keys.delete_key("NONEXISTENT"))

if __name__ == "__main__":
    unittest.main()
