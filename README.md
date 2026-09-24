# Pokémon cards vs equities: hypothetical £10,000 experiment (EPQ)
Academic simulation, not investment advice. Free data only. All assumptions are in `config.yaml`.

## How it works
`pipeline/run_daily.py` runs daily: collect prices (Stooq/yfinance, pokemontcg.io, Frankfurter FX) → build features (`strategy.py`) → 0–100 score → **execute yesterday's orders at today's price** (no look-ahead) → queue tomorrow's orders → snapshot → write `docs/data.json`. `docs/index.html` is the dashboard.
Logs in `data/` (`data_dev/` while `frozen: false`) are append-only, hash-chained JSONL (`store.py`): prices, signals, decisions, snapshots, gaps. The site shows whether the chain verifies.

## Put the site online (free)
1. Create a GitHub repo, push this folder. 2. Repo → Settings → Secrets → Actions: add `POKEMONTCG_API_KEY` (free key from pokemontcg.io). 3. Settings → Pages → Deploy from branch → `main` `/docs`. 4. Actions → daily → Run workflow. Your site: `https://<user>.github.io/<repo>/`. Free Pages sites are public.

## Freeze procedure
Verify the placeholders in `config.yaml` (cost sources, card IDs, universe), let the dry run collect ≥30 days, set `frozen: true`, commit, tag `v1.0-frozen`. After that the runner refuses to start if `config.yaml` changes.

## Known limits (also on the site)
Card prices are GUIDE, not sold. Unknown card IDs/tickers are logged as gaps. UK tax is simplified (average cost, realised gains, no same-day/30-day matching yet). Not built yet: graded and sealed portfolios, composite portfolio, TCGIndex/TCGscreener/PriceCharting readers, costs and methodology pages, historical dry-run, bootstrap CIs. Data-source URLs were not tested against live services from the build environment. Run the first workflow and check the gaps list.
