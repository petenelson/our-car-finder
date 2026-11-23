# Minivan Finder

Daily search for used Toyota, Honda, Lexus, Acura and Nissan cars and SUVs ($6–10k, 2011+, under 150k miles, within 250 driving
miles of McNeil Dr & US-183 in Austin). New matches and price drops go to your phone through ntfy, and a
report page is published to GitHub Pages.

## What it checks

| Site | How | Notes |
| --- | --- | --- |
| Cars.com | HTTP with Chrome TLS fingerprint | Covers most local dealer inventory. Out-of-area "ships to you" cars are dropped by distance. Each in-range listing page is opened once (with the search page as Referer, which it requires) for AutoCheck owners, accidents and title. |
| Craigslist | Craigslist's JSON search API | All TX areas within the radius (Austin, San Antonio, Houston, Dallas, Killeen, …). |
| Autotrader | HTTP with Chrome or Safari TLS fingerprint, falling back to KBB.com (same listings, same page format) | Dealer coordinates and KBB fair price come with the listing. |
| CarMax | Camoufox, then CarMax's search API from inside the page | CarMax rarely has anything under $10k. |
| Facebook Marketplace | Camoufox, logged out | First page of results per city and model only. Mileage, VIN and title status come from opening each new listing once. |

CarGurus is not included: it blocked every automated browser tried.

Listings seen on more than one site (same VIN, or same model, year and exact odometer) are merged into one card with a link to each site.

## Setup

```sh
uv venv .venv && uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python -m camoufox fetch          # downloads the stealth Firefox build
printf '[ntfy]\ntopic = "carfinder-%s"\n' "$(openssl rand -hex 6)" > config.local.toml
crontab -e   # add:  0 * * * * /path/to/run_daily.sh
```

`run_daily.sh` exits unless the hour is one of `[general] run_hours` (7 AM and 4 PM) in `[general] timezone`
(America/Chicago), so the hourly cron entry follows daylight saving.

## Files

- `config.toml`: name, maintainer, time zone and run hours, search terms, models, sources, deal scoring, where to publish
- `finder/config.py`: loads `config.toml` with `config.local.toml` merged over it
- `config.local.toml` (not committed): the ntfy topic and any other local overrides
- `finder/models.py`: model list, per-site URL slugs and cargo specs by generation
- `finder/sources.py`: one scraper per site
- `finder/deals.py`: deal scoring (price model per model, private-seller adjustment, KBB from Autotrader)
- `finder/report_template.html`: the report page (data is injected as JSON)
- `run.py`: the pipeline (scrape → filter → dedupe → distance → photos → notify → report → publish)
- `data/finder.db`: sqlite history (listings, first/last seen, price history, site health, geocode cache)
- `out/site/`: the generated report (`index.html` + `thumbs/`)
- `logs/`: one log per day

## Commands

```sh
./run_daily.sh                          # what cron runs
.venv/bin/python run.py --no-publish    # scrape + notify, skip the GitHub Pages push
.venv/bin/python run.py --report-only --no-publish   # rebuild the page from the database
.venv/bin/python run.py --sources carscom,craigslist --no-notify --no-publish -v
```

## Notifications

Install the ntfy app (iOS/Android) and subscribe on server `ntfy.sh`. Both topics are set in
`config.local.toml` (not committed; anyone who knows a topic name can read it).

`topic`, for whoever is car shopping:

- one push per new listing (photo attached, tap opens the listing; matches are higher priority than near misses)
- price drops of $300 or more, or drops into the budget

`ops_topic`, for whoever maintains this (falls back to `topic` if unset):

- a warning when a site fails 3 runs in a row (usually means its markup or bot protection changed), and a note when it recovers
- a crashed run (with the end of the traceback) or a failed GitHub Pages push

`ask_topic`, for asking questions about the cars:

- post a question (or a listing link) to the topic and an answer comes back on the same topic in under a minute.
  `scripts/ask.py` listens and runs `claude -p` with the current listings, reliability notes and generation notes in
  the prompt. Links to car sites are opened in the stealth browser and VINs are decoded with NHTSA recalls.
- Claude runs with no tools, MCP servers or skills, so a question can't read files, run commands or change the
  report; changes still go through the maintainer.
- each question and answer is copied to `ops_topic` (low priority) so the maintainer can see how it's used.
- `[ask] daily_limit` questions a day (in `[general] timezone`); past that it replies with a limit notice and warns `ops_topic`
  once. Failed answers are reported to `ops_topic` too.
- cron restarts the listener if it stops:
  `*/5 * * * * cd /path/to/our-car-finder && flock -n logs/.ask.lock .venv/bin/python scripts/ask.py >> logs/ask.log 2>&1`
- `scripts/ask.py --once "question"` prints an answer without touching ntfy.

## Publishing

This repo is private. The report goes to `docs/` in the public repo
[our-car-finder-report](https://github.com/petenelson/our-car-finder-report), which GitHub Pages serves at
https://petenelson.github.io/our-car-finder-report/ (marked noindex). `finder/publish.py` keeps a clone of that
repo in `pages/`, copies in `index.html` and the photos, commits and pushes over SSH.
