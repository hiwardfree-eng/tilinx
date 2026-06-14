import sys, os, time, json, unittest, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestWebhooks(unittest.TestCase):
    def setUp(self):
        import webhooks
        self.tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump({}, self.tmp)
        self.tmp.close()
        webhooks.WEBHOOKS_PATH = self.tmp.name
        webhooks._wh_cache = {"data": {}, "ts": 0.0}

    def test_register_and_list(self):
        import webhooks
        wid = webhooks.register("https://example.com/hook")
        self.assertIsNotNone(wid)
        hooks = webhooks.list_webhooks()
        self.assertEqual(len(hooks), 1)
        self.assertEqual(hooks[0]["url"], "https://example.com/hook")

    def test_remove(self):
        import webhooks
        wid = webhooks.register("https://example.com/hook")
        self.assertTrue(webhooks.remove(wid))
        self.assertFalse(webhooks.remove("nonexistent"))

    def test_list_empty(self):
        import webhooks
        self.assertEqual(len(webhooks.list_webhooks()), 0)

    def test_dispatch_no_crash(self):
        import webhooks
        webhooks.register("https://example.com/hook", events=["test.event"])
        webhooks.dispatch("test.event", {"msg": "hello"})
        webhooks.dispatch("unregistered.event", {"msg": "ignored"})


class TestBulkOps(unittest.TestCase):
    def setUp(self):
        import database
        self.tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump({}, self.tmp)
        self.tmp.close()
        database.DB_PATH = self.tmp.name

    def test_export_ips_empty(self):
        import bulk_ops
        csv_content = bulk_ops.export_ips_csv()
        self.assertIn("ip,status", csv_content)
        self.assertEqual(len(csv_content.splitlines()), 1)

    def test_export_keys_empty(self):
        import bulk_ops
        csv_content = bulk_ops.export_keys_csv()
        self.assertIn("code,label", csv_content)

    def test_bulk_add_and_export(self):
        import bulk_ops
        result = bulk_ops.bulk_add_ips(["1.1.1.1", "2.2.2.2"], duration=3600)
        self.assertEqual(result["added"], 2)
        csv_content = bulk_ops.export_ips_csv()
        self.assertIn("1.1.1.1", csv_content)
        self.assertIn("2.2.2.2", csv_content)

    def test_bulk_remove(self):
        import bulk_ops
        bulk_ops.bulk_add_ips(["1.1.1.1"])
        result = bulk_ops.bulk_remove_ips(["1.1.1.1", "9.9.9.9"])
        self.assertEqual(result["removed"], 1)
        self.assertEqual(result["not_found"], 1)

    def test_bulk_set_status(self):
        import bulk_ops
        bulk_ops.bulk_add_ips(["1.1.1.1"])
        result = bulk_ops.bulk_set_status(["1.1.1.1"], "blocked")
        self.assertEqual(result["updated"], 1)
        result = bulk_ops.bulk_set_status(["9.9.9.9"], "active")
        self.assertEqual(result["not_found"], 1)


class TestFilterRules(unittest.TestCase):
    def setUp(self):
        import filter_rules
        self.tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump({"url_blacklist": [], "url_whitelist": [], "header_rules": [], "geoip_blocked_countries": [], "enabled": True}, self.tmp)
        self.tmp.close()
        filter_rules.FILTERS_PATH = self.tmp.name
        filter_rules._f_cache = {"data": {}, "ts": 0.0}

    def test_url_blacklist(self):
        import filter_rules
        filter_rules.add_url_blacklist("bad.example.com")
        blocked, reason = filter_rules.check_url_blocked("http://bad.example.com/page")
        self.assertTrue(blocked)
        self.assertIn("bad.example.com", reason)

    def test_url_whitelist_bypass(self):
        import filter_rules
        filter_rules.add_url_blacklist("bad.example.com")
        filter_rules.add_url_whitelist("good.example.com")
        blocked, _ = filter_rules.check_url_blocked("http://good.example.com/bad")
        self.assertFalse(blocked)

    def test_header_rules(self):
        import filter_rules
        filter_rules.add_header_rule("set", "X-Custom", "test123")
        headers = filter_rules.apply_header_rules("http://example.com", {"Host": "example.com"})
        self.assertEqual(headers.get("X-Custom"), "test123")

    def test_header_rule_remove(self):
        import filter_rules
        filter_rules.add_header_rule("remove", "X-Unwanted")
        headers = filter_rules.apply_header_rules("http://example.com", {"X-Unwanted": "remove_me", "Host": "example.com"})
        self.assertNotIn("X-Unwanted", headers)

    def test_geoip_countries(self):
        import filter_rules
        filter_rules.add_geoip_blocked_country("CN")
        filter_rules.add_geoip_blocked_country("RU")
        countries = filter_rules.get_geoip_blocked_countries()
        self.assertIn("CN", countries)
        self.assertIn("RU", countries)

    def test_remove_url_blacklist(self):
        import filter_rules
        filter_rules.add_url_blacklist("test.com")
        self.assertTrue(filter_rules.remove_url_blacklist("test.com"))
        self.assertFalse(filter_rules.remove_url_blacklist("nonexistent.com"))


class TestConfigTemplates(unittest.TestCase):
    def setUp(self):
        import config_templates
        self.tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump({}, self.tmp)
        self.tmp.close()
        config_templates.TEMPLATES_PATH = self.tmp.name
        config_templates._t_cache = {"data": {}, "ts": 0.0}

    def test_list_builtin_templates(self):
        import config_templates
        templates = config_templates.list_templates()
        self.assertGreaterEqual(len(templates), 3)

    def test_get_builtin_template(self):
        import config_templates
        tmpl = config_templates.get_template("gaming_default")
        self.assertIsNotNone(tmpl)
        self.assertTrue(tmpl["builtin"])

    def test_get_nonexistent_template(self):
        import config_templates
        self.assertIsNone(config_templates.get_template("nonexistent"))

    def test_save_custom_template(self):
        import config_templates
        config_templates.save_custom_template("my_custom", "My Config", "Test", {"rate_limit": 50})
        tmpl = config_templates.get_template("my_custom")
        self.assertIsNotNone(tmpl)
        self.assertEqual(tmpl["config"]["rate_limit"], 50)

    def test_delete_custom_template(self):
        import config_templates
        config_templates.save_custom_template("to_delete", "Delete Me", "", {})
        self.assertTrue(config_templates.delete_custom_template("to_delete"))
        self.assertFalse(config_templates.delete_custom_template("nonexistent"))


class TestScheduler(unittest.TestCase):
    def setUp(self):
        import scheduler
        self.tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump({}, self.tmp)
        self.tmp.close()
        scheduler.SCHED_PATH = self.tmp.name
        scheduler._sched_cache = {"data": {}, "ts": 0.0}

    def test_register_and_list(self):
        import scheduler
        tid = scheduler.register_task("health_check", 3600)
        tasks = scheduler.list_tasks()
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["type"], "health_check")

    def test_remove_task(self):
        import scheduler
        tid = scheduler.register_task("cleanup_expired", 86400)
        self.assertTrue(scheduler.remove_task(tid))
        self.assertFalse(scheduler.remove_task("nonexistent"))

    def test_list_empty(self):
        import scheduler
        self.assertEqual(len(scheduler.list_tasks()), 0)


class TestAlerts(unittest.TestCase):
    def setUp(self):
        import alerts
        self.tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump({"configs": [], "recent": [], "max_recent": 100}, self.tmp)
        self.tmp.close()
        alerts.ALERTS_PATH = self.tmp.name
        alerts._a_cache = {"data": {}, "ts": 0.0}
        alerts._last_alert.clear()

    def test_list_configs(self):
        import alerts
        configs = alerts.list_alert_configs()
        self.assertGreaterEqual(len(configs), 0)

    def test_add_and_remove_config(self):
        import alerts
        aid = alerts.add_alert_config("system_error", threshold=1)
        configs = alerts.list_alert_configs()
        self.assertTrue(any(c["id"] == aid for c in configs))
        self.assertTrue(alerts.remove_alert_config(aid))
        self.assertFalse(alerts.remove_alert_config("nonexistent"))

    def test_trigger_no_crash(self):
        import alerts
        alerts.add_alert_config("system_error", threshold=1, channels=[])
        alerts.trigger("system_error", "Test alert", {"detail": "test"})
        recent = alerts.get_recent(5)
        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0]["type"], "system_error")


if __name__ == "__main__":
    unittest.main()
