"""Builds the static report page (index.html + thumbs/) from the database."""
import datetime as dt
import json
import shutil
from html import escape
from pathlib import Path

from .config import general
from .models import autojunket_url

TEMPLATE = Path(__file__).with_name("report_template.html")
ALERTS_TEMPLATE = Path(__file__).with_name("alerts_template.html")
# Report-page distance filter: [miles, place name shown in brackets]. Override with [search] distance_filters.
DEFAULT_DISTANCES = [[30, ""], [90, "San Antonio"], [180, "Houston"], [220, "DFW"]]
GONE_DAYS = 14
NEW_HOURS = 24


def build_report(db, cfg, models, site_dir, thumbs_dir, now):
    site_dir.mkdir(parents=True, exist_ok=True)
    (site_dir / "thumbs").mkdir(exist_ok=True)
    cutoff = (now.date() - dt.timedelta(days=GONE_DAYS)).isoformat()
    rows = db.execute(
        "SELECT data, first_seen, last_seen, gone_on FROM listings WHERE gone_on IS NULL OR gone_on >= ?",
        (cutoff,)).fetchall()

    items = []
    for data, first_seen, last_seen, gone_on in rows:
        d = json.loads(data)
        fs = dt.datetime.fromisoformat(first_seen)
        thumb = d.get("thumb")
        if thumb and (thumbs_dir / thumb).exists():
            dst = site_dir / "thumbs" / thumb
            if not dst.exists():
                shutil.copy2(thumbs_dir / thumb, dst)
            thumb = f"thumbs/{thumb}"
        else:
            thumb = None
        hist = d.get("price_history") or []
        items.append({
            "key": d["key"], "year": d.get("year"), "make": d["make"], "model": d["model"],
            "modelKey": d["model_key"], "trim": d.get("trim"), "title": d.get("title"),
            "price": d["price"], "firstPrice": hist[0][1] if hist else d["price"],
            "mileage": d.get("mileage"), "tier": d["tier"], "seller": d.get("seller"),
            "private": d.get("private"), "city": d.get("city"), "driveMi": d.get("drive_mi"),
            "driveMin": d.get("drive_min"), "cargo": d.get("cargo"), "body": d.get("body"),
            "seats": d.get("seats"), "links": d.get("links", {}), "flags": d.get("flags", []),
            "thumb": thumb, "firstSeen": fs.date().isoformat(), "deal": d.get("deal"), "rel": d.get("reliability"),
            "aj": autojunket_url(d["model_key"], d.get("year")), "owners": d.get("owners"),
            "accidents": d.get("accidents"), "titleStatus": d.get("title_status"), "history": d.get("history_source"),
            "isNew": gone_on is None and (now - fs).total_seconds() < NEW_HOURS * 3600,
            "gone": gone_on,
        })

    health = [
        {"name": n, "ok": f == 0, "failures": f, "lastOk": lo, "error": e, "count": c}
        for n, f, lo, e, c in db.execute(
            "SELECT source, failures, last_ok, last_error, last_count FROM source_health ORDER BY source")
    ]
    s = cfg["search"]
    meta = {
        "generated": now.isoformat(timespec="minutes"),
        "origin": s["origin_name"], "radius": s["radius_miles"], "minYear": s["min_year"],
        "maxMileage": s["max_mileage"], "priceMin": s["price_min"], "priceMax": s["price_max"],
        "margin": s["near_miss_margin"], "goneDays": GONE_DAYS,
        "models": [{"key": m.key, "name": f"{m.make} {m.model}", "short": m.model, "body": m.body,
                    "seats": m.seats, "cargo": m.cargo} for m in models],
        "health": health,
        "showCargo": bool(general(cfg)["show_cargo"]),
        "distances": s.get("distance_filters", DEFAULT_DISTANCES),
        "marketMin": cfg["deals"]["market_price_min"], "marketMax": cfg["deals"]["market_price_max"],
    }
    payload = json.dumps({"meta": meta, "items": items}, separators=(",", ":")).replace("</", "<\\/")
    title = escape(general(cfg)["title"])
    html = TEMPLATE.read_text().replace("__TITLE__", title).replace("__DATA__", payload)
    out = site_dir / "index.html"
    out.write_text(html)
    build_alerts_page(cfg, site_dir)

    # Drop thumbnails no longer referenced so the publish set stays small.
    used = {Path(i["thumb"]).name for i in items if i["thumb"]}
    for p in (site_dir / "thumbs").glob("*.jpg"):
        if p.name not in used:
            p.unlink()
    return site_dir


def build_alerts_page(cfg, site_dir):
    """alerts.html: how to get notifications in the ntfy app. Never includes topic names, since anyone who
    knows one can read it; the page tells people to ask the maintainer instead."""
    g, n = general(cfg), cfg.get("ntfy", {})
    server = (n.get("server") or "https://ntfy.sh").rstrip("/")
    host = server.split("://", 1)[-1]
    ask = ""
    if n.get("ask_topic"):
        ask = ("<h2>Ask questions from your phone</h2><p>There is also a second topic for questions. Subscribe to it "
               "the same way, then tap it and type a question at the bottom, like <i>which of these is the best deal "
               "under 100k miles?</i> or paste a listing link. An answer comes back in the same topic within a minute "
               f"or two. Ask {escape(g['maintainer'])} for that topic name too.</p>")
    html = (ALERTS_TEMPLATE.read_text().replace("__TITLE__", escape(g["title"]))
            .replace("__MAINTAINER__", escape(g["maintainer"])).replace("__SERVER__", escape(host))
            .replace("__CUSTOM_SERVER__", "" if host == "ntfy.sh" else
                     f"<li>Turn on <b>Use another server</b> and enter <code>{escape(server)}</code>.</li>")
            .replace("__ASK__", ask)
            .replace("__NEAR__", "Near misses (a little over budget) come through too, at a lower priority."
                     if n.get("notify_near_misses", True) else ""))
    (site_dir / "alerts.html").write_text(html)
