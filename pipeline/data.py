"""Free data collection. Every fetch returns None/[] on failure; the caller logs a gap (never interpolates).
Every per-asset fetch is hard-bounded (see _bounded): no single flaky source can ever stack up and blow the job's overall time limit, however badly it's failing."""
import concurrent.futures as _cf, csv, io, json, math, os, time, urllib.request
_POOL = _cf.ThreadPoolExecutor(max_workers=8)
def _bounded(fn, seconds):  # runs fn with a hard wall-clock cutoff; a hung/slow source can't block the whole run
    try: return _POOL.submit(fn).result(timeout=seconds)
    except _cf.TimeoutError: raise TimeoutError(f"no response within {seconds}s")
def _get(url, headers=None, timeout=8):
    req = urllib.request.Request(url, headers={"User-Agent": "epq-research/0.1", **(headers or {})})
    return urllib.request.urlopen(req, timeout=timeout).read().decode()
def fx_usd_gbp():
    for u in ("https://api.frankfurter.dev/v1/latest?base=USD&symbols=GBP", "https://api.frankfurter.app/latest?from=USD&to=GBP"):
        try: j = json.loads(_get(u)); return j["rates"]["GBP"], j["date"]
        except Exception: pass
    return None, None
def _equity_history_inner(t):
    try:
        rows = list(csv.DictReader(io.StringIO(_get(f"https://stooq.com/q/d/l/?s={t.lower()}.us&i=d"))))
        out = []
        for r in rows:
            if not r.get("Close"): continue
            try: c = float(r["Close"])
            except ValueError: continue
            if math.isfinite(c): out.append((r["Date"], c, float(r.get("Volume") or 0)))  # drop a NaN/inf row (a source glitch) rather than let it poison every downstream calculation
        if out: return out
    except Exception: pass
    try:
        import yfinance as yf
        h = yf.Ticker(t).history(period="2y")
        return [(i.strftime("%Y-%m-%d"), float(r.Close), float(r.Volume)) for i, r in h.iterrows()]
    except Exception: return []
def equity_history(t):  # ascending [(date, close, volume)] -- hard-capped at 15s total, Stooq + yfinance fallback combined
    try: return _bounded(lambda: _equity_history_inner(t), 15)
    except Exception: return []
LAST_ERROR = ""
def _pokemontcg(cid):
    key = os.environ.get("POKEMONTCG_API_KEY", ""); hdr = {"X-Api-Key": key} if key else {}
    d = json.loads(_get(f"https://api.pokemontcg.io/v2/cards/{cid}", hdr))["data"]
    for v, p in (d.get("tcgplayer", {}).get("prices") or {}).items():
        if p.get("market"): return {"price_usd": p["market"], "variant": v, "price_type": "GUIDE", "source": "pokemontcg.io/tcgplayer", "as_of": d["tcgplayer"].get("updatedAt")}
    raise ValueError("card found but no TCGplayer market price")
def _tcgdex(cid):  # fallback: same "set-number" id scheme, free, no key
    d = json.loads(_get(f"https://api.tcgdex.net/v2/en/cards/{cid}"))
    for v, p in (d.get("pricing", {}).get("tcgplayer") or {}).items():
        if isinstance(p, dict) and p.get("marketPrice"): return {"price_usd": p["marketPrice"], "variant": v, "price_type": "GUIDE", "source": "tcgdex.net/tcgplayer", "as_of": d.get("updated")}
    raise ValueError("card found but no TCGplayer market price")
def _card_price_inner(cid):
    errs = []
    for name, fn in (("pokemontcg.io", _pokemontcg), ("tcgdex.net", _tcgdex)):  # one attempt each; two independent sources IS the retry
        try: return fn(cid), None
        except Exception as e: errs.append(f"{name}:{type(e).__name__} {str(e)[:40]}")
    return None, " | ".join(errs)
def card_price(cid):  # GUIDE prices only (TCGplayer market price), never a completed sale -- hard-capped at 12s total
    global LAST_ERROR
    try:
        result, err = _bounded(lambda: _card_price_inner(cid), 12)
        if result: return result
        LAST_ERROR = err or "unknown error"; return None
    except Exception as e:
        LAST_ERROR = f"timeout/error: {e}"; return None
