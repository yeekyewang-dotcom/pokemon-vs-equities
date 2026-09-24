import datetime as dt, json, random, yaml
from pipeline import store, run_daily
from pipeline.portfolio import Portfolio
CFG = yaml.safe_load(open("config.yaml"))

def test_hash_chain_detects_tampering(tmp_path):
    f = str(tmp_path / "x.jsonl")
    for i in range(3): store.append(f, {"i": i})
    assert store.verify(f)
    lines = open(f).read().replace('"i": 1', '"i": 9'); open(f, "w").write(lines)
    assert not store.verify(f)

def test_accounting_costs_and_tax():
    p = Portfolio(CFG, cash=10000.0)
    b = p.buy("X", "equity", 10, 100.0, "2026-10-01"); assert abs(p.cash - (10000 - 1000 - b["costs"])) < 1e-9
    s = p.sell("X", 500.0, "2026-10-20", 2026)  # gain far above the £3,000 allowance
    assert abs(p.cash - (10000 - b["costs"] + s["net"] - 1000)) < 1e-6
    assert abs(p.tax_due() - (s["gain"] - 3000) * 0.18) < 1e-6
    assert p.buy("Y", "equity", 1e9, 1.0, "d") is None  # cannot overspend

class Fake:  # deterministic synthetic market; NOT real data
    today = "2026-01-01"
    def fx_usd_gbp(s): return 0.75, s.today
    def equity_history(s, t):
        r = random.Random(t); end = dt.date.fromisoformat(s.today); px, out = 100.0, []
        for i in range(200, -1, -1):
            px *= 1 + r.gauss(0.001, 0.015); out.append(((end - dt.timedelta(days=i)).isoformat(), px, 1e6))
        return out
    def card_price(s, c):
        n = (dt.date.fromisoformat(s.today) - dt.date(2026, 1, 1)).days; r = random.Random(c)
        return {"price_usd": 50 * (1 + 0.02 * n) * (1 + r.random()), "variant": "holofoil", "price_type": "GUIDE", "source": "fake", "as_of": s.today}

def test_daily_loop_runs_and_is_idempotent(tmp_path):
    import shutil; shutil.copy("config.yaml", tmp_path / "config.yaml"); fk = Fake()
    for d in range(30):
        fk.today = (dt.date(2026, 1, 1) + dt.timedelta(days=d)).isoformat(); run_daily.main(str(tmp_path), fk, fk.today)
    run_daily.main(str(tmp_path), fk, fk.today)  # second run same day = no-op
    out = json.load(open(tmp_path / "docs" / "data.json"))
    assert out["meta"]["chain_ok"] and len(out["series"]["Equity algo"]) == 30 and abs(out["series"]["Equity algo"][0]["net"] - 10000) < 1
    assert all(abs(s[0]["net"] - 10000) < 1 for n, s in out["series"].items() if "algo" in n)
