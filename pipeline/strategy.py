"""Indicators + 0-100 score. Pure functions of history up to 'now': no future data can enter."""
import statistics as st
def features(hist, lb):  # hist ascending [(date, price, volume)]
    s, l = lb
    if len(hist) < l + 1: return None
    p = [h[1] for h in hist]; r = [p[i] / p[i - 1] - 1 for i in range(len(p) - l, len(p))]
    return {"mom_s": p[-1] / p[-1 - s] - 1, "mom_l": p[-1] / p[-1 - l] - 1, "trend": p[-1] / (sum(p[-l:]) / l) - 1,
            "vol": st.pstdev(r), "dollar_vol": st.mean(h[1] * h[2] for h in hist[-s:])}
def _pct(v, hi=True):
    n = len(v)
    if n < 2 or len(set(v)) == 1: return [0.5] * n
    r = [sum(y < x for y in v) / (n - 1) for x in v]
    return r if hi else [1 - x for x in r]
def score(F, w, rt, regime):
    a = list(F); n = len(a); cost = 1 - min(1, rt / 0.3)
    c = {"momentum": _pct([(F[x]["mom_s"] + F[x]["mom_l"]) / 2 for x in a]), "trend": _pct([F[x]["trend"] for x in a]),
         "volatility": _pct([F[x]["vol"] for x in a], False),
         "liquidity_cost": [(d + cost) / 2 for d in _pct([F[x]["dollar_vol"] for x in a])], "regime": [regime] * n}
    return {x: (round(100 * sum(w[k] * c[k][i] for k in w), 1), {k: round(c[k][i], 3) for k in w}) for i, x in enumerate(a)}
