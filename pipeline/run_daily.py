"""Daily run: collect -> validate -> indicators -> score -> execute YESTERDAY's orders at today's price -> new orders for tomorrow -> snapshot -> export."""
import datetime as dt, hashlib, json, math, os, sys
import yaml
from pipeline import data as live, store, strategy
from pipeline.portfolio import Portfolio

NAMES = {"pokemon": "Pokémon algo (raw)", "equity": "Equity algo", "bh_card": "Pokémon buy & hold", "bh_equity": "Equity buy & hold"}
tax_year = lambda d: int(d[:4]) - (d[5:] < "04-06")

def main(root=".", src=live, today=None):
    raw = open(f"{root}/config.yaml", "rb").read(); cfg = yaml.safe_load(raw); h = hashlib.sha256(raw).hexdigest()
    D = f"{root}/{'data' if cfg['frozen'] else 'data_dev'}"; os.makedirs(D, exist_ok=True); os.makedirs(f"{root}/docs", exist_ok=True)
    ex = f"{D}/experiment.json"
    if cfg["frozen"] and os.path.exists(ex) and json.load(open(ex))["config_hash"] != h: sys.exit("config changed after freeze: refusing to run")
    if not os.path.exists(ex) or not cfg["frozen"]: json.dump({"config_hash": h}, open(ex, "w"))
    now = dt.datetime.now(dt.timezone.utc); today = today or now.strftime("%Y-%m-%d"); P = lambda n: f"{D}/{n}"
    if any(r["date"] == today for r in store.read(P("snapshots.jsonl"))): return print("already ran today")
    fx, fxd = src.fx_usd_gbp()
    if not fx: sys.exit("no FX rate: aborting run (nothing recorded)")
    gaps, hist, px, cap, R = [], {}, {}, cfg["capital_gbp"], cfg["rules"]
    for s in cfg["equities"] + list(cfg["benchmarks"].values()):
        hh = src.equity_history(s)
        if hh:
            hist[s] = hh; px[s] = hh[-1][1] * fx
            store.append(P("prices.jsonl"), {"date": today, "asset": s, "market": "equity", "price": hh[-1][1], "ccy": "USD", "price_type": "CLOSE", "as_of": hh[-1][0], "source": "stooq/yfinance", "retrieved_at": now.isoformat()})
        else: gaps.append(f"no data: {s}")
    for cid in cfg["cards"]:
        c = src.card_price(cid)
        if c:
            px[cid] = c["price_usd"] * fx
            store.append(P("prices.jsonl"), {"date": today, "asset": cid, "market": "card", "price": c["price_usd"], "ccy": "USD", "price_type": c["price_type"], "variant": c["variant"], "source": c["source"], "as_of": c["as_of"], "retrieved_at": now.isoformat()})
        else: gaps.append(f"no data: {cid} ({getattr(src, 'LAST_ERROR', '')})")
    sp = P("state.json")
    if os.path.exists(sp): st = json.load(open(sp))
    else: st = {"pf": {}, "pending": [], "bench0": {}, "last_px": {}, "start": today}
    st["last_px"].update(px); lp = st["last_px"]
    pf = {k: Portfolio(cfg, **st["pf"][k]) if k in st["pf"] else Portfolio(cfg, cash=cap) for k in NAMES}
    if not st["pf"]:  # first run: buy-and-hold benchmarks buy the whole universe equally; index start levels recorded
        for k, m, assets in (("bh_card", "card", cfg["cards"]), ("bh_equity", "equity", cfg["equities"])):
            for a in assets:
                if a in px: pf[k].buy(a, m, (cap / sum(x in px for x in assets) - cfg["costs"][m]["fixed_gbp"]) / (px[a] * (1 + pf[k].rate(m, "buy"))), px[a], today)
        st["bench0"] = {s: px[s] for s in cfg["benchmarks"].values() if s in px}
    # 1) execute orders decided on a previous day, at today's price (no look-ahead)
    for o in st["pending"]:
        p, a = pf[o["pf"]], o["asset"]
        if a not in px: gaps.append(f"order not executed, no price: {o['action']} {a}"); continue
        r, qty, t0 = None, 0, p.tax_due()
        if o["action"] == "BUY":
            c = cfg["costs"][o["mkt"]]; qty = (o["alloc"] - c["fixed_gbp"]) / (px[a] * (1 + p.rate(o["mkt"], "buy")))
            qty = math.floor(qty) if o["mkt"] == "card" else qty; r = p.buy(a, o["mkt"], qty, px[a], today)
        elif a in p.pos: qty = p.pos[a]["qty"]; r = p.sell(a, px[a], today, tax_year(today))
        store.append(P("decisions.jsonl"), {"date": today, "decided_on": o["decided_on"], "portfolio": NAMES[o["pf"]], "asset": a, "market": o["mkt"], "price_at_decision_gbp": o["px"],
            "exec_price_gbp": px[a], "score": o["score"], "action": o["action"] if r else "SKIPPED", "qty": qty, "gross": r and r["gross"], "costs": r and r["costs"],
            "tax": p.tax_due() - t0, "net": r and r["net"], "cash_after": p.cash, "reason": o["reason"] if r else "insufficient cash or quantity < 1", "indicators": o["ind"]})
    # 2) score with information available today; orders execute at the next run
    st["pending"] = []; regime = 0.5
    if "SPY" in hist and (f := strategy.features(hist["SPY"], cfg["lookbacks"]["equity"])): regime = 1.0 if f["trend"] > 0 else 0.0
    for k, m, assets in (("pokemon", "card", cfg["cards"]), ("equity", "equity", cfg["equities"])):
        p, F = pf[k], {}; c = cfg["costs"][m]; rt = p.rate(m, "buy") + p.rate(m, "sell") + 2 * c["fixed_gbp"] / (cap * R["max_position_pct"])
        for a in assets:
            if m == "card": d = {r["date"]: r["price"] for r in store.read(P("prices.jsonl")) if r["asset"] == a}; hh = [(x, v, 0.0) for x, v in sorted(d.items())]
            else: hh = hist.get(a)
            f = hh and strategy.features(hh, cfg["lookbacks"][m])
            if f: F[a] = f
            elif hh: store.append(P("signals.jsonl"), {"date": today, "portfolio": NAMES[k], "asset": a, "score": None, "reason": f"warm-up: {len(hh)}/{cfg['lookbacks'][m][1] + 1} observations"})
        S = strategy.score(F, cfg["weights"], rt, 0.5 if m == "card" else regime) if F else {}
        g = p.gross(lp); avail = p.cash - R["min_cash_pct"] * g; slots = R["max_positions"] - len(p.pos)
        for a, (sc, comp) in sorted(S.items(), key=lambda kv: -kv[1][0]):
            store.append(P("signals.jsonl"), {"date": today, "portfolio": NAMES[k], "asset": a, "score": sc, "components": comp, "features": F[a]})
            o = {"pf": k, "asset": a, "mkt": m, "decided_on": today, "px": lp[a], "score": sc, "ind": {**F[a], "round_trip_cost": rt}}
            if a in p.pos:
                held = (dt.date.fromisoformat(today) - dt.date.fromisoformat(p.pos[a]["date"])).days
                if sc <= R["sell_score"] and held >= R["min_hold_days"][m]: st["pending"].append({**o, "action": "SELL", "reason": f"score {sc} <= {R['sell_score']}, held {held}d"})
            elif sc >= R["buy_score"] and F[a]["mom_l"] > R["edge_multiple"] * rt and slots > 0:
                alloc = min(R["max_position_pct"] * g, avail)
                if alloc > 2 * c["fixed_gbp"] + 1: avail -= alloc; slots -= 1; st["pending"].append({**o, "action": "BUY", "alloc": alloc, "reason": f"score {sc} >= {R['buy_score']}; momentum {F[a]['mom_l']:.1%} > {R['edge_multiple']}x round-trip cost {rt:.1%}"})
    # 3) snapshots (append-only)
    for k, n in NAMES.items():
        v = pf[k].values(lp); store.append(P("snapshots.jsonl"), {"date": today, "portfolio": n, **v, "cash": pf[k].cash, "costs": pf[k].costs, "tax_due": pf[k].tax_due(), "n_pos": len(pf[k].pos)})
    for n, s in cfg["benchmarks"].items():
        if s in lp and s in st["bench0"]: v = cap * lp[s] / st["bench0"][s]; store.append(P("snapshots.jsonl"), {"date": today, "portfolio": n, "gross": v, "net": v, "post_tax": v, "cash": 0, "costs": 0, "tax_due": 0, "n_pos": 0})
    for g_ in gaps: store.append(P("gaps.jsonl"), {"date": today, "msg": g_})
    st["pf"] = {k: p.dump() for k, p in pf.items()}; json.dump(st, open(sp, "w"))
    # 4) export for the website
    snaps, decs = store.read(P("snapshots.jsonl")), store.read(P("decisions.jsonl")); series = {}
    for r in snaps: series.setdefault(r["portfolio"], []).append({k: r[k] for k in ("date", "gross", "net", "post_tax")})
    stats = {r["portfolio"]: {"costs": r["costs"], "tax": r["tax_due"], "trades": sum(d["portfolio"] == r["portfolio"] and d["action"] in ("BUY", "SELL") for d in decs)} for r in snaps if r["date"] == today}
    hold = {NAMES[k]: [{"asset": a, "market": q["mkt"], "qty": q["qty"], "cost": q["cost"], "value": q["qty"] * lp[a], "alloc": q["qty"] * lp[a] / pf[k].gross(lp)} for a, q in pf[k].pos.items()] for k in ("pokemon", "equity")}
    files = [P(f) for f in ("prices", "signals", "decisions", "snapshots", "gaps")]
    json.dump({"meta": {"last_refresh": now.isoformat(), "date": today, "fx_usd_gbp": fx, "fx_date": fxd, "frozen": cfg["frozen"], "config_hash": h[:12], "chain_ok": all(store.verify(f + ".jsonl") for f in files), "start": st["start"], "capital": cap},
               "series": series, "stats": stats, "holdings": hold, "signals": [r for r in store.read(P("signals.jsonl")) if r["date"] == today], "orders": st["pending"], "executed": [d for d in decs if d["date"] == today], "gaps": gaps},
              open(f"{root}/docs/data.json", "w"))
    print("done", today, "gaps:", len(gaps))

if __name__ == "__main__": main()
