"""Builds the generations guide (docs/generations/ on the report site) from hand-written generation
notes plus current matches and NHTSA data in finder.db.

  scripts/generations.py OUT.html      write the page only
  scripts/generations.py --publish     write it into the Pages checkout, push, and send an ntfy push
"""
import datetime as dt
import html
import json
import sqlite3
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from finder.config import general, load_config  # noqa: E402
from finder.guide_notes import BOTTOM, GENS  # noqa: E402
from finder.models import BY_KEY, autojunket_url, enabled  # noqa: E402
from finder.reliability import Reliability  # noqa: E402

PUBLISH = "--publish" in sys.argv

db = sqlite3.connect(ROOT / "data/finder.db")
rel = Reliability(db)
rows = [json.loads(r[0]) for r in db.execute("SELECT data FROM listings WHERE gone_on IS NULL")]
matches = [x for x in rows if x["tier"] == "match" and x.get("year")
           and (x.get("deal") or {}).get("label") != "suspect"]
cfg = load_config()
REPORT = cfg["publish"].get("page_url", "")
TITLE = general(cfg)["title"]
SHOW_CARGO = bool(general(cfg)["show_cargo"])
MIN_YEAR = cfg["search"]["min_year"]
_s = cfg["search"]
CRITERIA = (f'${_s["price_min"] / 1000:g}–{_s["price_max"] / 1000:g}k, {_s["min_year"]}+, '
            f'under {_s["max_mileage"] / 1000:g}k miles, within {_s["radius_miles"]} miles of {_s["origin_name"]}')


def e(s):
    return html.escape(str(s), quote=True)


def money(n):
    return f"${n:,.0f}"


def stars(n):
    return f'<span class="st{" low" if n <= 2 else ""}" aria-label="{n} of 5 stars">{"★" * n}{"☆" * (5 - n)}</span>'


sections, overview = [], []
for key, gens in GENS.items():
    m = BY_KEY[key]
    mine = [x for x in matches if x["model_key"] == key]
    if not mine:
        continue
    gen_html = []
    for g in gens:
        lo, hi = g["years"]
        cars = [x for x in mine if lo <= x["year"] <= hi]
        if not cars:
            continue
        years = sorted({x["year"] for x in cars})
        prices = [x["price"] for x in cars]
        miles = [x["mileage"] for x in cars if x.get("mileage")]
        deals = [x for x in cars if (x.get("deal") or {}).get("label") in ("great", "good")]
        best = min(cars, key=lambda x: (-(x.get("deal") or {}).get("pct", 0) if x.get("deal") else 0, x["price"]))
        cargo = m.cargo_for(lo) if lo >= MIN_YEAR else m.cargo_for(years[0])
        # Per-year reliability across the matched years of this generation.
        yr_rows, star_vals = [], []
        for y in range(max(lo, MIN_YEAR), min(hi, dt.date.today().year) + 1):
            r = rel.rating(key, y)
            if not r or not r.get("stars"):
                continue
            n_y = sum(1 for x in cars if x["year"] == y)
            if y in years:
                star_vals.append(r["stars"])
            aj = autojunket_url(key, y)
            yr_rows.append(
                f'<tr class="{"" if n_y else "dim"}"><td>{y}</td><td>{stars(r["stars"])}</td>'
                f'<td>{r["per10k"]}</td><td>{r["recalls"]}</td><td>{e(", ".join(r["components"]).lower())}</td>'
                f'<td class="n">{n_y or "–"}</td><td>{f"<a href={chr(34)}{e(aj)}{chr(34)} target=_blank rel=noopener>↗</a>" if aj else ""}</td></tr>')
        issues = next((t for a, b, t in __import__("finder.reliability", fromlist=["KNOWN_ISSUES"]).KNOWN_ISSUES.get(key, [])
                       if a <= years[0] <= b), "")
        med_miles = statistics.median(miles) if miles else None
        avg_st = round(sum(star_vals) / len(star_vals), 1) if star_vals else None
        overview.append(dict(model=f"{m.make} {m.model}", key=key, gen=g["name"], years=f"{lo}–{hi}",
                             n=len(cars), lo=min(prices), hi=max(prices), med=statistics.median(prices),
                             miles=med_miles, cargo=cargo, stars=avg_st, deals=len(deals)))
        cargo_txt = (f'{cargo["max"]} cu ft max · {cargo["row2"]} behind 2nd row'
                     + (f' · {cargo["row3"]} behind 3rd row' if cargo.get("row3") else "")) if cargo else "—"
        best_link = next(iter(best["links"].values()), None)
        gen_html.append(f"""
      <div class="gen">
        <div class="gen-head">
          <h3>{e(g["name"])} <span>{lo}–{hi}</span></h3>
          <div class="pill">{len(cars)} match{"es" if len(cars) != 1 else ""} · {money(min(prices))}–{money(max(prices))}{f" · median {med_miles/1000:.0f}k mi" if med_miles else ""}{f" · {len(deals)} good/great deal{'s' if len(deals) != 1 else ''}" if deals else ""}</div>
        </div>
        <dl>
          <dt>Powertrain</dt><dd>{e(g["power"])}</dd>
          <dt>Drive</dt><dd>{e(g["drive"])}</dd>
          <dt>Features</dt><dd>{e(g["features"])}</dd>
          <dt>Updates</dt><dd>{e(g["changes"])}</dd>
          {f"<dt>Cargo</dt><dd>{e(cargo_txt)} · seats {e(m.seats)}</dd>" if SHOW_CARGO else f"<dt>Seats</dt><dd>{e(m.seats)}</dd>"}
          <dt>Known issues</dt><dd>{e(issues)}</dd>
          <dt>Before you buy</dt><dd>{e(g["check"])}</dd>
        </dl>
        <div class="tbl"><table>
          <thead><tr><th>Year</th><th>Reliability</th><th>Complaints / 10k sold</th><th>Recalls</th><th>Most complaints</th><th class="n">Listed now</th><th>Autojunket</th></tr></thead>
          <tbody>{"".join(yr_rows)}</tbody>
        </table></div>
        {f'<p class="best">Best deal listed now: <a href="{e(best_link)}" target="_blank" rel="noopener">{e(best["year"])} {e(m.model)} {e(best.get("trim") or "")} · {money(best["price"])} · {f"{best[chr(109)+chr(105)+chr(108)+chr(101)+chr(97)+chr(103)+chr(101)]/1000:.0f}k mi · " if best.get("mileage") else ""}{e(best.get("city") or "")}</a></p>' if best_link else ""}
      </div>""")
    sections.append(f"""
    <section class="model" id="{key}">
      <div class="model-head">
        <h2>{e(m.make)} {e(m.model)}</h2>
        <span class="body">{e(m.body)} · {len(mine)} current match{"es" if len(mine) != 1 else ""}</span>
      </div>
      <p class="bottom">{e(BOTTOM[key])}</p>
      {"".join(gen_html)}
    </section>""")

overview.sort(key=lambda o: -o["n"])
# Searched models left out of the guide, and why.
no_notes = [m.model for m in enabled(cfg) if m.key not in GENS]
no_matches = [m.model for m in enabled(cfg) if m.key in GENS and not any(x["model_key"] == m.key for x in matches)]
not_included = "".join(f'<p><b>{label}:</b> {e(", ".join(names))}.</p>' for label, names in
                       (("No current matches", no_matches), ("No generation notes yet", no_notes)) if names)
ov_rows = "".join(
    f'<tr><td><a href="#{o["key"]}">{e(o["model"])}</a><small>{e(o["gen"])} · {o["years"]}</small></td>'
    f'<td class="n">{o["n"]}</td><td class="n">{money(o["med"])}</td>'
    f'<td class="n">{f"{o[chr(109)+chr(105)+chr(108)+chr(101)+chr(115)]/1000:.0f}k" if o["miles"] else "—"}</td>'
    + (f'<td class="n">{o["cargo"]["max"] if o["cargo"] else "—"}</td>' if SHOW_CARGO else "") +
    f'<td>{stars(round(o["stars"])) if o["stars"] else "—"} <small>{o["stars"] or ""}</small></td>'
    f'<td class="n">{o["deals"] or "–"}</td></tr>'
    for o in overview)

today = dt.date.today().strftime("%b %-d, %Y")
page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Car Generations Guide</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700&family=Barlow:wght@400;500;600&display=swap">
<style>
:root {{ --bg:#f3f4f1; --paper:#fff; --ink:#15201b; --muted:#5d6a63; --line:#dde1db; --accent:#1b6a46; --soft:#e3efe8; --warn:#b5541f; --star:#b07d12;
  --head:"Barlow Condensed","Arial Narrow",system-ui,sans-serif; --body:"Barlow",system-ui,-apple-system,"Segoe UI",sans-serif; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#111814; --paper:#18221d; --ink:#e6eee9; --muted:#9db0a5; --line:#2a3a31; --accent:#6fcf9b; --soft:#1f3329; --warn:#f08a5d; --star:#e0b146; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--ink); font:16px/1.5 var(--body); -webkit-font-smoothing:antialiased; }}
.wrap {{ max-width:1040px; margin:0 auto; padding:28px 16px 60px; }}
a {{ color:var(--accent); text-underline-offset:3px; }}
.kicker {{ font:600 13px/1 var(--body); letter-spacing:.12em; text-transform:uppercase; color:var(--muted); margin:0 0 8px; }}
h1 {{ font:700 clamp(38px,7vw,56px)/1 var(--head); margin:0 0 10px; }}
.intro {{ color:var(--muted); max-width:760px; margin:0 0 22px; }}
nav.jump {{ display:flex; gap:8px; overflow-x:auto; padding-bottom:6px; margin-bottom:22px; }}
nav.jump a {{ flex:none; padding:6px 12px; border:1px solid var(--line); border-radius:999px; background:var(--paper); text-decoration:none; color:var(--ink); font-size:14px; }}
.tbl {{ overflow-x:auto; -webkit-overflow-scrolling:touch; }}
table {{ border-collapse:collapse; width:100%; min-width:680px; font-size:14.5px; }}
th {{ text-align:left; font:600 11.5px/1.2 var(--body); letter-spacing:.08em; text-transform:uppercase; color:var(--muted); padding:8px 10px; border-bottom:2px solid var(--ink); white-space:nowrap; }}
td {{ padding:8px 10px; border-bottom:1px solid var(--line); vertical-align:top; }}
td small {{ display:block; color:var(--muted); font-size:12.5px; }}
.n {{ text-align:right; font-variant-numeric:tabular-nums; }}
tr.dim td {{ color:var(--muted); opacity:.7; }}
.st {{ color:var(--star); letter-spacing:1px; white-space:nowrap; }}
.st.low {{ color:var(--warn); }}
.overview {{ background:var(--paper); border:1px solid var(--line); border-radius:12px; padding:14px 14px 6px; margin-bottom:34px; }}
.overview h2 {{ font:700 26px/1 var(--head); margin:2px 0 10px; }}
.model {{ margin-bottom:40px; scroll-margin-top:12px; }}
.model-head {{ display:flex; flex-wrap:wrap; align-items:baseline; gap:4px 14px; border-bottom:3px solid var(--ink); padding-bottom:6px; }}
.model-head h2 {{ font:700 36px/1 var(--head); margin:0; }}
.model-head .body {{ color:var(--muted); font-size:15px; }}
.bottom {{ font-size:17px; margin:10px 0 14px; }}
.gen {{ background:var(--paper); border:1px solid var(--line); border-radius:12px; padding:16px 18px; margin-bottom:14px; }}
.gen-head {{ display:flex; flex-wrap:wrap; justify-content:space-between; align-items:baseline; gap:6px 12px; margin-bottom:8px; }}
.gen-head h3 {{ font:700 24px/1.1 var(--head); margin:0; }}
.gen-head h3 span {{ color:var(--muted); font-weight:600; }}
.pill {{ background:var(--soft); color:var(--accent); font-weight:600; font-size:13.5px; padding:4px 10px; border-radius:999px; }}
dl {{ display:grid; grid-template-columns:130px 1fr; gap:6px 14px; margin:0 0 12px; font-size:15px; }}
dt {{ font:600 12px/1.6 var(--body); letter-spacing:.07em; text-transform:uppercase; color:var(--muted); }}
dd {{ margin:0; }}
.best {{ margin:10px 0 0; font-size:14.5px; }}
.notes {{ color:var(--muted); font-size:14px; border-top:1px solid var(--line); padding-top:14px; }}
@media (max-width:600px) {{ dl {{ grid-template-columns:1fr; gap:0 }} dd {{ margin-bottom:8px }} .gen {{ padding:14px }} }}
</style>
</head>
<body>
<div class="wrap">
  <p class="kicker">{e(TITLE)} · snapshot from {today}</p>
  <h1>Generations guide</h1>
  <p class="intro">Every model and generation that has listings matching our search right now ({e(CRITERIA)}): what changed between years, what to check, and how each model year rates for reliability. This is a one-time snapshot; the <a href="{REPORT}">live report</a> keeps updating.</p>
  <nav class="jump">{"".join(f'<a href="#{k}">{e(BY_KEY[k].model)}</a>' for k in GENS if any(x["model_key"] == k for x in matches))}</nav>

  <div class="overview">
    <h2>At a glance</h2>
    <div class="tbl"><table>
      <thead><tr><th>Model / generation</th><th class="n">Matches</th><th class="n">Median price</th><th class="n">Median miles</th>{'<th class="n">Max cargo (cu ft)</th>' if SHOW_CARGO else ""}<th>Avg reliability</th><th class="n">Good/great deals</th></tr></thead>
      <tbody>{ov_rows}</tbody>
    </table></div>
  </div>

  {"".join(sections)}

  <div class="notes">
    <p><b>Reliability:</b> stars come from NHTSA owner complaints per 10,000 vehicles sold for each model year, ranked against every model year in the search (airbag complaints excluded). Greyed rows are years with no current listings. Sales figures are approximate, so treat stars as a guide. The ↗ links open Autojunket's report for that year; its scores are its own estimates.</p>
    {not_included}
    <p>Specs are for the common U.S. versions and vary slightly by trim. Verify any specific car with a pre-purchase inspection and a VIN recall check at nhtsa.gov/recalls.</p>
  </div>
</div>
</body>
</html>"""
if not PUBLISH:
    out = Path(sys.argv[1])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page)
    print("wrote", out, len(page), "bytes;", len(sections), "models")
    sys.exit(0)

import subprocess  # noqa: E402

from finder.notify import Notifier  # noqa: E402

repo = ROOT / cfg["publish"].get("checkout", "pages")


def git(*args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


git("fetch", "origin")
git("reset", "--hard", f"origin/{cfg['publish'].get('branch', 'main')}")
out = repo / cfg["publish"].get("path", "docs") / "generations" / "index.html"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(page)
git("add", "-A")
if subprocess.run(["git", "-C", str(repo), "diff", "--cached", "--quiet"]).returncode:
    git("commit", "-m", f"Rebuild the generations guide {dt.date.today().isoformat()}")
    git("push", "origin", cfg["publish"].get("branch", "main"))
url = cfg["publish"]["page_url"].rstrip("/") + "/generations/"
Notifier(cfg).send("Generations guide updated",
                   f"Rebuilt with today's matches: {len(sections)} models, {len(matches)} listings.\n{url}",
                   tags="blue_book", report_button=False, ops=True)
print("published", url)
