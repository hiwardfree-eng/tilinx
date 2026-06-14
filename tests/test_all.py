import sys, os, json, time, tempfile, unittest, re, secrets
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database import load, save, get_stats, get_user_status_label, get_auth_status
from cache import get, set, delete, clear, stats
from utils import format_date, parse_duration
from adminx import create_user, remove_user, set_active, get_user, find_by_key, list_users

IP_RE = re.compile(r"^(?:(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)$")

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

    def test_save_with_integrity(self):
        save({"test_ip": {"status": "active"}})
        db = load()
        self.assertIn("test_ip", db)
        self.assertEqual(db["test_ip"]["status"], "active")

    def test_load_missing_file(self):
        import database
        old = database.DB_PATH
        database.DB_PATH = "/nonexistent/path.json"
        self.assertEqual(load(), {})
        database.DB_PATH = old


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

    def test_stats(self):
        set("x", 100)
        s = stats()
        self.assertEqual(s["entries"], 1)
        self.assertIn("x", s["keys"])

    def test_get_nonexistent(self):
        self.assertIsNone(get("nonexistent"))

    def test_overwrite(self):
        set("k", "old")
        set("k", "new")
        self.assertEqual(get("k"), "new")


class TestUtils(unittest.TestCase):
    def test_format_date(self):
        self.assertEqual(format_date(0), "\u2014")
        self.assertEqual(format_date(None), "\u2014")

    def test_format_date_valid(self):
        ts = 1700000000
        result = format_date(ts)
        self.assertIsInstance(result, str)
        self.assertNotEqual(result, "\u2014")

    def test_parse_duration_minutes(self):
        self.assertEqual(parse_duration("30m"), 1800)

    def test_parse_duration_hours(self):
        self.assertEqual(parse_duration("6h"), 21600)

    def test_parse_duration_days(self):
        self.assertEqual(parse_duration("14d"), 1209600)

    def test_parse_duration_hours_default(self):
        self.assertEqual(parse_duration("2"), 7200)

    def test_parse_duration_invalid(self):
        with self.assertRaises(ValueError):
            parse_duration("abc")


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
        self.assertEqual(len(code), 19)

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
        self.assertEqual(result, "IP_LOCKED")
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

    def test_get_key_info(self):
        code = self.keys.generate_key(7200, label="test")
        info = self.keys.get_key_info(code)
        self.assertIsNotNone(info)
        self.assertEqual(info["label"], "test")
        self.assertEqual(info["duration"], 7200)

    def test_refresh_key(self):
        code = self.keys.generate_key(3600)
        self.assertTrue(self.keys.refresh_key(code))
        info = self.keys.get_key_info(code)
        self.assertFalse(info["used"])

    def test_modify_key_duration(self):
        code = self.keys.generate_key(3600)
        self.assertTrue(self.keys.modify_key_duration(code, 3600))
        info = self.keys.get_key_info(code)
        self.assertEqual(info["duration"], 7200)

    def test_multi_device_key(self):
        code = self.keys.generate_key(86400, max_devices=3)
        self.tmp_db = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump({}, self.tmp_db)
        self.tmp_db.close()
        import database
        database.DB_PATH = self.tmp_db.name
        r1 = self.keys.redeem_key(code, "1.1.1.1")
        self.assertEqual(r1, "OK")
        r2 = self.keys.redeem_key(code, "2.2.2.2")
        self.assertEqual(r2, "OK")
        info = self.keys.get_key_info(code)
        self.assertEqual(len(info["active_ips"]), 2)
        os.unlink(self.tmp_db.name)


class TestAdminX(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump({}, self.tmp)
        self.tmp.close()
        import adminx
        adminx.ADMINX_PATH = self.tmp.name
        self.adminx = adminx

    def tearDown(self):
        os.unlink(self.tmp.name)

    def test_create_user(self):
        key, result = create_user("testuser", 12345, 30)
        self.assertEqual(result, "OK")
        self.assertTrue(key.startswith("ADMINX-"))

    def test_create_duplicate(self):
        create_user("dupuser", 12345)
        key, result = create_user("dupuser", 12345)
        self.assertIsNone(key)
        self.assertEqual(result, "USERNAME_EXISTS")

    def test_remove_user(self):
        create_user("toremove", 12345)
        self.assertTrue(remove_user("toremove"))
        self.assertFalse(remove_user("nonexistent"))

    def test_set_active(self):
        create_user("toggleuser", 12345)
        self.assertTrue(set_active("toggleuser", False))
        info = get_user("toggleuser")
        self.assertFalse(info["active"])

    def test_find_by_key(self):
        key, _ = create_user("findme", 12345)
        username, info = find_by_key(key)
        self.assertEqual(username, "findme")

    def test_list_users(self):
        create_user("user_a", 12345)
        create_user("user_b", 12345)
        users = list_users()
        self.assertEqual(len(users), 2)

    def test_get_user_nonexistent(self):
        self.assertIsNone(get_user("ghost"))


if __name__ == "__main__":
    unittest.main()
