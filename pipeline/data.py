"""Free data collection. Every fetch returns None/[] on failure; the caller logs a gap (never interpolates)."""
import csv, io, json, os, time, urllib.request
def _get(url, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": "epq-research/0.1", **(headers or {})})
    return urllib.request.urlopen(req, timeout=30).read().decode()
def fx_usd_gbp():
    for u in ("https://api.frankfurter.dev/v1/latest?base=USD&symbols=GBP", "https://api.frankfurter.app/latest?from=USD&to=GBP"):
        try: j = json.loads(_get(u)); return j["rates"]["GBP"], j["date"]
        except Exception: pass
    return None, None
def equity_history(t):  # ascending [(date, close, volume)]
    try:
        rows = list(csv.DictReader(io.StringIO(_get(f"https://stooq.com/q/d/l/?s={t.lower()}.us&i=d"))))
        out = [(r["Date"], float(r["Close"]), float(r.get("Volume") or 0)) for r in rows if r.get("Close")]
        if out: return out
    except Exception: pass
    try:
        import yfinance as yf
        h = yf.Ticker(t).history(period="2y")
        return [(i.strftime("%Y-%m-%d"), float(r.Close), float(r.Volume)) for i, r in h.iterrows()]
    except Exception: return []
LAST_ERROR = ""
def card_price(cid):  # TCGplayer market price via pokemontcg.io = GUIDE (not a completed sale)
    global LAST_ERROR
    key = os.environ.get("POKEMONTCG_API_KEY", ""); hdr = {"X-Api-Key": key} if key else {}
    for attempt in range(3):
        try:
            d = json.loads(_get(f"https://api.pokemontcg.io/v2/cards/{cid}", hdr))["data"]
            for v, p in (d.get("tcgplayer", {}).get("prices") or {}).items():
                if p.get("market"): return {"price_usd": p["market"], "variant": v, "price_type": "GUIDE", "source": "pokemontcg.io/tcgplayer", "as_of": d["tcgplayer"].get("updatedAt")}
            LAST_ERROR = "card found but no TCGplayer market price"; return None
        except Exception as e:
            LAST_ERROR = f"{type(e).__name__} {str(e)[:50]}"; time.sleep(2)
    return None
