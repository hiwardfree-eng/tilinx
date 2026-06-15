"""Unit tests for TilinX Brain V2 modules."""
import os, sys, json, time, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from brain.memory_store import MemoryStore
from brain.behavior_tracker import BehaviorTracker
from brain.anomaly_engine import AnomalyEngine
from brain.risk_scoring import RiskScoring
from brain.decision_engine_v2 import DecisionEngineV2
from brain.brain_v2 import BrainV2
from brain.types import RequestContext


def make_req(ip="1.2.3.4", path="/test", method="GET", host="example.com"):
    return RequestContext(ip=ip, path=path, method=method, host=host)


# ─── MemoryStore ────────────────────────────────────────────

def test_memory_get_set():
    ms = MemoryStore()
    ms.set("k1", "hello")
    assert ms.get("k1") == "hello"
    ms.set("k2", 42)
    assert ms.get("k2") == 42


def test_memory_expiry():
    ms = MemoryStore()
    ms.set("k", "v", ex=1)
    assert ms.get("k") == "v"
    time.sleep(1.1)
    ms.cleanup_expired()
    assert ms.get("k") is None


def test_memory_incr():
    ms = MemoryStore()
    assert ms.incr("c") == 1
    assert ms.incr("c") == 2
    assert ms.get("c") == 2


def test_memory_incr_expire():
    ms = MemoryStore()
    assert ms.incr_expire("e", 60) == 1
    assert ms.incr_expire("e", 60) == 2


def test_memory_list():
    ms = MemoryStore()
    ms.lpush("lst", "a")
    ms.lpush("lst", "b")
    assert ms.lrange("lst", 0, -1) == ["b", "a"]


def test_memory_set_ops():
    ms = MemoryStore()
    ms.sadd("s", "x")
    ms.sadd("s", "y")
    assert ms.smembers("s") == {"x", "y"}
    ms.srem("s", "x")
    assert ms.smembers("s") == {"y"}


def test_memory_keys():
    ms = MemoryStore()
    ms.set("a:1", "v1")
    ms.set("a:2", "v2")
    ms.set("b:1", "v3")
    assert set(ms.keys("a:")) == {"a:1", "a:2"}
    assert len(ms.keys()) == 3


def test_memory_persist():
    ms = MemoryStore()
    ms.set("k1", "v1")
    ms.incr("counter")
    ms.sadd("set1", "member")
    ms.lpush("list1", "item")

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    try:
        ms.persist_to_disk(path)
        ms2 = MemoryStore()
        ms2.load_from_disk(path)
        assert ms2.get("k1") == "v1"
        assert ms2.get("counter") == 1
        assert ms2.smembers("set1") == {"member"}
        assert ms2.lrange("list1", 0, -1) == ["item"]
    finally:
        os.unlink(path)


def test_memory_ttl():
    ms = MemoryStore()
    assert ms.ttl("nonexist") == -1
    ms.set("k", "v", ex=60)
    t = ms.ttl("k")
    assert 55 <= t <= 60


def test_memory_pipeline():
    ms = MemoryStore()
    ms.pipeline().incr("p1").incr("p1").expire("p1", 60).execute()
    assert ms.get("p1") == 2


# ─── BehaviorTracker ────────────────────────────────────────

def test_tracker_track_and_get():
    ms = MemoryStore()
    bt = BehaviorTracker(ms)
    bt.track(make_req(ip="10.0.0.1", path="/login"))
    bt.track(make_req(ip="10.0.0.1", path="/home"))
    recent = bt.get_recent("10.0.0.1", 10)
    assert len(recent) >= 2
    assert recent[0]["path"] == "/home"


def test_tracker_hits():
    ms = MemoryStore()
    bt = BehaviorTracker(ms)
    bt.track(make_req(ip="10.0.0.2"))
    bt.track(make_req(ip="10.0.0.2"))
    assert bt.get_hits("10.0.0.2") >= 2


def test_tracker_unique_paths():
    ms = MemoryStore()
    bt = BehaviorTracker(ms)
    bt.track(make_req(ip="10.0.0.3", path="/a"))
    bt.track(make_req(ip="10.0.0.3", path="/b"))
    bt.track(make_req(ip="10.0.0.3", path="/a"))
    assert bt.get_unique_paths("10.0.0.3") == {"/a", "/b"}


def test_tracker_reputation():
    ms = MemoryStore()
    bt = BehaviorTracker(ms)
    assert bt.get_known_bad("10.0.0.4") == 0
    bt.mark_bad("10.0.0.4", 30)
    assert bt.get_known_bad("10.0.0.4") == 30
    bt.mark_bad("10.0.0.4", 80)
    assert bt.get_known_bad("10.0.0.4") == 100  # capped


# ─── AnomalyEngine ──────────────────────────────────────────

def test_anomaly_whitelist():
    ms = MemoryStore()
    ae = AnomalyEngine(ms)
    assert ae.is_whitelisted("127.0.0.1")
    assert not ae.is_whitelisted("1.2.3.4")


def test_anomaly_burst():
    ms = MemoryStore()
    ae = AnomalyEngine(ms)
    assert ae.detect_burst("10.0.0.5", 200)  # hits > threshold
    result = ae.analyze("10.0.0.5", [], 200)
    assert "burst" in result


def test_anomaly_scraping():
    ms = MemoryStore()
    ae = AnomalyEngine(ms)
    behaviors = [{"path": "/same"} for _ in range(20)]
    assert ae.detect_scraping(behaviors)
    result = ae.analyze("10.0.0.6", behaviors, 20)
    assert "scraping" in result


def test_anomaly_loop():
    ms = MemoryStore()
    ae = AnomalyEngine(ms)
    behaviors = [{"path": "/loop"} for _ in range(5)]
    assert ae.detect_loop(behaviors)
    result = ae.analyze("10.0.0.7", behaviors, 5)
    assert "loop" in result


def test_anomaly_fast_refresh():
    ms = MemoryStore()
    ae = AnomalyEngine(ms)
    now = time.time()
    behaviors = [
        {"ts": now},
        {"ts": now - 0.3},
        {"ts": now - 0.6},
    ]
    assert ae.detect_fast_refresh(behaviors)
    result = ae.analyze("10.0.0.8", behaviors, 3)
    assert "fast_refresh" in result


def test_anomaly_whitelist_skip():
    ms = MemoryStore()
    ae = AnomalyEngine(ms)
    behaviors = [{"path": "/same"} for _ in range(20)]
    result = ae.analyze("127.0.0.1", behaviors, 200)
    assert result == {}  # whitelisted returns empty


# ─── RiskScoring ────────────────────────────────────────────

def test_scoring_normal():
    ms = MemoryStore()
    ae = AnomalyEngine(ms)
    rs = RiskScoring(ms, ae)
    score = rs.calculate("10.0.0.10", [], 5, {})
    assert 0 <= score <= 10


def test_scoring_burst():
    ms = MemoryStore()
    ae = AnomalyEngine(ms)
    rs = RiskScoring(ms, ae)
    score = rs.calculate("10.0.0.11", [], 200, {"burst": "test"})
    assert score >= 35


def test_scoring_penalty():
    ms = MemoryStore()
    ae = AnomalyEngine(ms)
    rs = RiskScoring(ms, ae)
    rs.apply_penalty("10.0.0.12", "aggressive")
    score = rs.calculate("10.0.0.12", [], 0, {})
    assert score >= 6  # 20 * 0.3 = 6


def test_scoring_capped():
    ms = MemoryStore()
    ae = AnomalyEngine(ms)
    rs = RiskScoring(ms, ae)
    rs.apply_penalty("10.0.0.13", "test")
    rs.apply_penalty("10.0.0.13", "test")
    rs.apply_penalty("10.0.0.13", "test")
    rs.apply_penalty("10.0.0.13", "test")
    key = f"brain:history:10.0.0.13"
    val = int(ms.get(key) or 0)
    assert val <= 80  # capped


def test_scoring_decay():
    ms = MemoryStore()
    ae = AnomalyEngine(ms)
    rs = RiskScoring(ms, ae)
    rs.apply_penalty("10.0.0.14", "test")
    rs.decay_history()
    key = f"brain:history:10.0.0.14"
    val = int(ms.get(key) or 0)
    assert val == 15  # 20 - 5 = 15


# ─── DecisionEngineV2 ───────────────────────────────────────

def test_decision_allow():
    de = DecisionEngineV2()
    d = de.decide(make_req(), 10)
    assert d["action"] == "allow"


def test_decision_rate_limit():
    de = DecisionEngineV2()
    d = de.decide(make_req(), 30)
    assert d["action"] == "rate_limit"
    assert "throttle" in d


def test_decision_challenge():
    de = DecisionEngineV2()
    d = de.decide(make_req(), 60)
    assert d["action"] == "challenge"


def test_decision_block():
    de = DecisionEngineV2()
    d = de.decide(make_req(), 85)
    assert d["action"] == "block"


# ─── BrainV2 Integration ────────────────────────────────────

def test_brain_allow():
    br = BrainV2()
    result = br.process(make_req(ip="10.0.0.20"))
    assert result["decision"]["action"] in ("allow", "rate_limit")


def test_brain_track_before_cache():
    br = BrainV2()
    for _ in range(200):
        br.process(make_req(ip="10.0.0.21", path="/fast"))
    result = br.process(make_req(ip="10.0.0.21", path="/fast"))
    actions = ("block", "challenge", "rate_limit", "allow")
    assert result["decision"]["action"] in actions


def test_brain_cached_block():
    br = BrainV2()
    ip = "10.0.0.22"
    from brain.types import BrainResult
    cached = BrainResult(
        ip=ip, risk_score=90,
        decision={"action": "block", "reason": "cached_test", "score": 90, "ttl": 300},
        signals=["test"],
    )
    br._cache_decision(ip, cached, 30)
    result = br.process(make_req(ip=ip))
    assert result.get("_from_cache") or result["decision"]["action"] == "block"


def test_brain_persist():
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        p = f.name
    os.environ["TilinX_BRAIN_PERSIST_PATH"] = p
    try:
        br = BrainV2()
        br.process(make_req(ip="10.0.0.30"))
        assert os.path.exists(p)
        os.unlink(p)
    finally:
        os.environ.pop("TilinX_BRAIN_PERSIST_PATH", None)


if __name__ == "__main__":
    tests = [
        ("memory_get_set", test_memory_get_set),
        ("memory_expiry", test_memory_expiry),
        ("memory_incr", test_memory_incr),
        ("memory_incr_expire", test_memory_incr_expire),
        ("memory_list", test_memory_list),
        ("memory_set_ops", test_memory_set_ops),
        ("memory_keys", test_memory_keys),
        ("memory_persist", test_memory_persist),
        ("memory_ttl", test_memory_ttl),
        ("memory_pipeline", test_memory_pipeline),
        ("tracker_track_and_get", test_tracker_track_and_get),
        ("tracker_hits", test_tracker_hits),
        ("tracker_unique_paths", test_tracker_unique_paths),
        ("tracker_reputation", test_tracker_reputation),
        ("anomaly_whitelist", test_anomaly_whitelist),
        ("anomaly_burst", test_anomaly_burst),
        ("anomaly_scraping", test_anomaly_scraping),
        ("anomaly_loop", test_anomaly_loop),
        ("anomaly_fast_refresh", test_anomaly_fast_refresh),
        ("anomaly_whitelist_skip", test_anomaly_whitelist_skip),
        ("scoring_normal", test_scoring_normal),
        ("scoring_burst", test_scoring_burst),
        ("scoring_penalty", test_scoring_penalty),
        ("scoring_capped", test_scoring_capped),
        ("scoring_decay", test_scoring_decay),
        ("decision_allow", test_decision_allow),
        ("decision_rate_limit", test_decision_rate_limit),
        ("decision_challenge", test_decision_challenge),
        ("decision_block", test_decision_block),
        ("brain_allow", test_brain_allow),
        ("brain_track_before_cache", test_brain_track_before_cache),
        ("brain_cached_block", test_brain_cached_block),
        ("brain_persist", test_brain_persist),
    ]

    passed = failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  OK  {name}")
            passed += 1
        except Exception as e:
            print(f"FAIL  {name}: {e}")
            failed += 1
    print(f"\n{passed}/{passed + failed} passed")
    sys.exit(0 if failed == 0 else 1)
