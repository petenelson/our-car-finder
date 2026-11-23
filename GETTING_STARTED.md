# Getting Started

This guide is for someone setting up their own copy of this used-car finder. It's written to be read by you
**and** by your Claude (Claude Code or similar). Hand it this file and say something like:

> Read GETTING_STARTED.md and README.md, then help me set this up to search for my car.

Claude can then walk you through setup and make the config and code changes described below.

---

## What it does

Twice a day it searches Cars.com, Autotrader (or KBB), CarMax, Craigslist and Facebook Marketplace for the car
models you pick, within a price range, model year, mileage limit and driving distance of a starting point. Then it:

- drops junk (salvage/export/"no title" listings, cars too far away, wrong models)
- merges the same car listed on several sites into one entry
- scores each car against what similar cars sell for (great / good / fair / suspect)
- adds reliability stars from NHTSA complaint and recall data, plus known issues per generation
- sends a phone notification for each new listing and each price drop (through the free ntfy app)
- builds a report web page you can filter and sort, and can publish it to GitHub Pages

The original copy searches for family-hauler Toyotas, Hondas, Lexus and Acuras around Austin, TX, so a few things
are set up for that. The sections below say what to change.

---

## 1. What you need

- A Mac or Linux machine that stays on (or at least awake) at the times you want it to run. A spare Linux box or a
  cheap VPS works best; a laptop works if it isn't asleep at run time.
- Python 3.11 or newer (the code uses `tomllib`).
- [`uv`](https://docs.astral.sh/uv/) for the Python environment (`brew install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh`).
- `git`.
- `flock`, used by `run_daily.sh` to stop two runs overlapping. It comes with Linux; on a Mac run `brew install flock`.
- The **ntfy** app on your phone (iOS or Android) for notifications. Free, no account needed.
- Optional: a GitHub account if you want the report on a web page you can open from your phone.
- Optional: the Claude Code CLI (`claude`) if you want the "ask a question from your phone" feature.

## 2. First-time setup

From the project folder:

```sh
uv venv .venv && uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python -m camoufox fetch     # downloads the stealth Firefox build used for CarMax and Facebook
```

Make your private settings file. It's git-ignored, because anyone who knows an ntfy topic name can read it:

```sh
printf '[ntfy]\ntopic = "carfinder-%s"\n' "$(openssl rand -hex 6)" > config.local.toml
cat config.local.toml
```

In the ntfy app, tap **+**, keep the server as `ntfy.sh`, and subscribe to the topic name it printed.

Then edit `config.toml` (next section) and do a test run that doesn't notify or publish:

```sh
.venv/bin/python run.py --no-notify --no-publish -v
open out/site/index.html        # Linux: xdg-open
```

The first real run (with notifications on) sends one "is running" notification with a count, not one per car.
After that you get a notification for each new listing.

## 3. Make it yours: `config.toml`

Most changes happen here. Every run reads the file fresh, so there's nothing to restart.

| Setting | What to change |
| --- | --- |
| `[general] title` | Name shown on the report page and in notifications. |
| `maintainer` | Who runs your copy. The ask feature tells people to ask this person for changes. |
| `home_area` | Where you live, e.g. `"Columbus, OH"`. Used in the ask feature's prompt. |
| `timezone` | Your time zone, e.g. `"America/New_York"`. Sets when runs happen and when the ask limit resets. |
| `run_hours` | Hours of the day (24-hour) to run, e.g. `[7, 16]` for 7 AM and 4 PM. |
| `show_cargo` | `false` to hide cargo space on the report and in notifications. |
| `[search] models` | Which vehicles to search for. Keys must exist in `finder/models.py` (see section 5 to add one). |
| `origin_name`, `origin_lat`, `origin_lon`, `origin_zip` | Your starting point. Lat/lon set driving distances; the ZIP is what the car sites search around. Get lat/lon by right-clicking a spot in Google Maps. |
| `radius_miles` | How far you're willing to drive. |
| `min_year`, `max_mileage` | Oldest model year and highest odometer reading. |
| `price_min`, `price_max` | Your budget. |
| `distance_filters` | The report's "Within N mi" choices, as `[miles, "place name"]` pairs. Pick towns near you. |
| `near_miss_margin` | Cars this many dollars outside the budget still appear, marked "near miss". |
| `[deals] market_price_min/max` | A wider price band searched on Cars.com only to learn what cars sell for. Set it to roughly budget minus $1k to budget plus $6k. |
| `[sources]` | Set any site to `false` to skip it. |
| `facebook_cities` | Facebook Marketplace city slugs near you. Find yours by opening Marketplace in a browser and choosing a location: the URL becomes `facebook.com/marketplace/<slug>/`. |
| `craigslist_site` | Your nearest Craigslist site, the `<site>` in `<site>.craigslist.org`. |
| `[ntfy] notify_near_misses` | `false` for notifications about in-budget cars only. |
| `[ask]` | Settings for the question-answering feature (section 6). |
| `[publish]` | Where the report gets pushed. Delete `repo` (or set it to `""`) to skip publishing and just use the local `out/site/index.html`. |

Keep private values in `config.local.toml` instead of `config.toml`. Any section there is merged over
`config.toml`, so you can override single keys, for example:

```toml
[ntfy]
topic = "carfinder-1a2b3c4d5e6f"
ops_topic = "carfinder-ops-9f8e7d6c5b4a"   # optional: errors go here instead of the main topic
ask_topic = "carfinder-ask-0a1b2c3d4e5f"   # optional: see section 6
```

## 4. Things specific to the original setup

Everything personal to the original Austin copy is in `config.toml`, so change these values there:

- `[general]` `title`, `maintainer`, `home_area`, `timezone`, `run_hours`
- `[search]` origin, radius, budget and models
- `[sources]` `facebook_cities` and `craigslist_site`
- `[publish]` `repo` and `page_url` (these point at the original owner's GitHub; change or remove them)

A few bits of content are still written for the original setup. They're harmless, but you may want to edit them:

- `finder/reliability.py`: the Lexus RX note mentions "Texas heat".
- `scripts/generations.py`: the "Not included" paragraph at the bottom of the guide and the notification text
  describe one particular day's listings. Rewrite them if you use the generations guide.
- `run.py` drops listings with Spanish "no title / export only" wording, common in Texas. It does no harm elsewhere.
- The `slides/` folder (narration for a talk about the project) isn't needed. Delete it or ignore it.

## 5. Adding or removing a car model

**Removing** a model: take its key out of `[search] models` in `config.toml`. Nothing else is needed.

**Adding** a model takes a few edits. Ask Claude to do it, and point it at this list:

1. **`finder/models.py` → `MODELS`**: add a `Model(...)` entry with:
   - `key` (short lowercase id), `make`, `model`, `body`, `seats`
   - the per-site URL slugs: `carscom` (e.g. `"mazda-cx_5"`), `autotrader` (e.g. `"mazda/cx-5"`), `carmax`
     (e.g. `"mazda/cx-5"`). Find them by searching that model on each site in a browser and reading the URL. A
     tuple of slugs searches several variants (see the Lexus RX entry).
   - `pattern`: a regex that matches the model name in listing titles. Make sure it can't match other models
     (see how `prius` excludes `prius v` and `prius c`).
   - `cargo`: `(first_year, last_year, max, row2, row3)` cargo space in cubic feet per generation (`row3` is
     `None` for two-row vehicles).
2. **`finder/models.py` → `AUTOJUNKET`**: the autojunket.com reliability page slug, if it has one.
3. **`finder/reliability.py`**:
   - `SALES`: approximate average US sales per year (used to turn complaint counts into a rate). Without it,
     the model gets no reliability stars.
   - `NHTSA_NAMES`: only if NHTSA's model name differs from the plain model name (e.g. `"CR-V"`, `"RX350"`).
   - `KNOWN_ISSUES`: a one-line note on common problems per generation.
4. **`finder/guide_notes.py`** → `GENS` and `BOTTOM`: generation notes used by the ask feature and the
   generations guide. Optional, but the ask feature answers better with them.
5. Add the key to `[search] models` in `config.toml`.
6. Test with one fast source: `.venv/bin/python run.py --sources carscom --no-notify --no-publish -v` and check
   the log shows listings for the new model.

Deal scores need at least 15 price observations per model over the last 45 days, so a new model shows no deal
label for its first run or two.

Nissan models (Rogue, Altima, Sentra, Murano, Pathfinder, Quest, Versa, Kicks) and sedans (Camry, Corolla, Avalon,
Accord, Civic, Lexus ES) are also defined; add their keys to `models` to search them. Other makes should work the same way, since every site is searched by make
and model.

## 6. Optional features

**Publishing the report to GitHub Pages.** Create a new **public** GitHub repo (the report shows listing data, not
your settings), turn on Pages for its `docs/` folder on `main`, make sure this machine can push to it over SSH, then
set `[publish] repo` and `page_url`. Each run clones it into `pages/`, copies in the report and photos, commits and
pushes. The report page is marked `noindex`, but anyone with the link can see it.

**Asking questions from your phone.** Set `ask_topic` in `config.local.toml`, subscribe to it in ntfy, and run
`scripts/ask.py`. Post a question like "which of these is the best deal
under 120k miles?" or paste a listing link, and an answer comes back on the same topic. It uses the `claude` CLI
with no tools, so a question can't change anything. Test it first with
`.venv/bin/python scripts/ask.py --once "what are the three best deals?"`. Keep it running with cron (see README).
`[ask] daily_limit` caps questions per day.

**Generations guide.** `scripts/generations.py OUT.html` builds a page explaining each model's generations, with
current matches. `--publish` pushes it next to the report. See section 4 for text to rewrite first.

**Phone alerts page.** Every report build also writes `alerts.html`, linked from the top of the report, with
ntfy setup steps for the people using the finder. It never shows the topic name; it tells them to ask the
`maintainer` for it.

**Error alerts.** Set `ops_topic` so warnings about a site failing 3 runs in a row, crashed runs and failed
publishes go somewhere separate from the car notifications.

## 7. Scheduling

`run_daily.sh` is meant to be run by cron **every hour**; it exits right away unless the hour in `[general]
timezone` is one of `[general] run_hours`. That way the schedule follows daylight saving.

```sh
crontab -e
# add (use your real path):
0 * * * * /full/path/to/our-car-finder/run_daily.sh
```

Run it right now, skipping the time check: `./run_daily.sh --now`. Logs go to `logs/run-YYYY-MM-DD.log` and are
kept for 30 days.

On a Mac, cron jobs don't run while the machine is asleep. Either keep it awake at those hours
(System Settings → Energy, or `pmset repeat wakeorpoweron`) or run this on an always-on machine.

## 8. Handy commands

```sh
./run_daily.sh --now                                    # full run, as cron would do it
.venv/bin/python run.py --no-publish                    # scrape + notify, don't push the page
.venv/bin/python run.py --no-notify --no-publish -v     # quiet test run with debug logging
.venv/bin/python run.py --report-only --no-publish      # rebuild the page from saved data, no scraping
.venv/bin/python run.py --sources carscom,craigslist --no-notify --no-publish -v   # only some sites
```

Start over with an empty history (all listings count as new again; the next run sends the first-run summary):
delete `data/finder.db`. Back it up first if you might want it.

## 9. When something breaks

- **A site returns 0 listings or fails.** Car sites change their pages and bot protection often. Run just that
  source with `-v`, read the log, and ask Claude to look at what the site now returns. The scrapers are all in
  `finder/sources.py`, one function per site. Turn a broken site off in `[sources]` in the meantime.
- **Autotrader blocked.** It already falls back to KBB.com automatically; if both fail for days, turn it off for
  a while.
- **Facebook shows few results.** It runs logged out and reads only the first page of results per city and model,
  by design.
- **CarGurus** isn't supported; it blocked every automated browser tried.
- **No notifications.** Check `topic` is set in `config.local.toml`, that you subscribed to the exact name in the
  app, and that you didn't pass `--no-notify`.
- **Distances missing or wrong.** Check `origin_lat` / `origin_lon` (latitude is the first number, and US
  longitudes are negative).

---

## Notes for Claude

If you're Claude helping someone with this project:

- Read `README.md` for the architecture and the file map. The pipeline is in `run.py`; scrapers are in
  `finder/sources.py`; model definitions are in `finder/models.py`.
- Before changing code, check whether the change is just a setting in `config.toml` or `config.local.toml`.
  Config is loaded by `finder/config.py`; `general(cfg)` returns the `[general]` section with defaults filled in.
  If you add something personal (a name, place, path or time zone), put it in config rather than in code.
  Put anything private (ntfy topic names) in `config.local.toml`, which is git-ignored.
- Test changes with `--no-notify --no-publish` so the user's phone doesn't get test notifications and nothing is
  pushed. Use `--sources <name>` to test one scraper, and `--report-only` to test report-page changes without
  scraping.
- The scrapers depend on how each site works today. If one breaks, fetch the page the same way the code does
  (`curl_cffi` with Chrome impersonation, or Camoufox for CarMax and Facebook) and look at the real response before
  changing selectors or parsing.
- Don't make many rapid requests to the car sites while debugging; the code already spaces requests out, and
  hammering a site gets the IP blocked.
- When adding a model, follow section 5; a missing `SALES` entry is the usual reason a new model has no
  reliability stars.
- The person you're helping may not be technical. Explain what you changed in plain words and tell them how to
  check it on their phone or in the report page.
