"""GBP accounting, costs, UK CGT (simplified: average cost per holding; realised gains only)."""
class Portfolio:
    def __init__(s, cfg, cash=0.0, pos=None, costs=0.0, realised=None):
        s.cfg, s.cash, s.pos, s.costs, s.realised = cfg, cash, pos or {}, costs, realised or {}
    def dump(s): return {"cash": s.cash, "pos": s.pos, "costs": s.costs, "realised": s.realised}
    def rate(s, m, side): c = s.cfg["costs"][m]; return c[side + "_fee"] + c["half_spread"] + c["fx_fee"]
    def buy(s, a, m, qty, px, date):
        gross = qty * px; cost = gross * s.rate(m, "buy") + s.cfg["costs"][m]["fixed_gbp"]
        if qty <= 0 or gross + cost > s.cash + 1e-9: return None
        s.cash -= gross + cost; s.costs += cost
        p = s.pos.setdefault(a, {"mkt": m, "qty": 0.0, "cost": 0.0, "date": date}); p["qty"] += qty; p["cost"] += gross + cost
        return {"gross": gross, "costs": cost, "net": -(gross + cost)}
    def sell(s, a, px, date, ty):
        p = s.pos.pop(a); gross = p["qty"] * px; cost = gross * s.rate(p["mkt"], "sell") + s.cfg["costs"][p["mkt"]]["fixed_gbp"]
        net = gross - cost; s.cash += net; s.costs += cost; gain = net - p["cost"]
        if not (p["mkt"] == "card" and s.cfg["tax"]["cards_tax_treatment"] == "chattel_exempt" and gross <= 6000):
            s.realised[str(ty)] = s.realised.get(str(ty), 0) + gain
        return {"gross": gross, "costs": cost, "net": net, "gain": gain}
    def tax_due(s):
        t = s.cfg["tax"]; return sum(max(0, g - t["cgt_exempt_gbp"]) * t["cgt_rate"] for g in s.realised.values())
    def gross(s, px): return s.cash + sum(p["qty"] * px[a] for a, p in s.pos.items())
    def liquidation(s, px):
        return sum(p["qty"] * px[a] * (1 - s.rate(p["mkt"], "sell")) - s.cfg["costs"][p["mkt"]]["fixed_gbp"] for a, p in s.pos.items())
    def values(s, px):
        net = s.cash + s.liquidation(px); return {"gross": s.gross(px), "net": net, "post_tax": net - s.tax_due()}
