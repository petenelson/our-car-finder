"""Push notifications through ntfy (https://ntfy.sh)."""
import base64
import logging

from curl_cffi import requests

from .config import general

log = logging.getLogger("finder")
MAX_INDIVIDUAL = 8


def fmt_money(n):
    return f"${n:,.0f}" if n else "?"


def describe(x, show_cargo=True):
    bits = [fmt_money(x["price"])]
    bits.append(f'{x["mileage"] / 1000:.0f}k mi' if x.get("mileage") else "miles unknown")
    where = x.get("city") or "location unknown"
    if x.get("drive_mi"):
        where += f' ({x["drive_mi"]} mi away)'
    bits.append(where)
    if x.get("owners"):
        bits.append(f'{x["owners"]} owner{"" if x["owners"] == "1" else "s"}')
    if x.get("accidents") is not None:
        bits.append("no accidents" if x["accidents"] == 0 else "accident reported" if x["accidents"] == "reported"
                    else f'{x["accidents"]} accident{"" if x["accidents"] == 1 else "s"}')
    if x.get("cargo") and show_cargo:
        bits.append(f'cargo {x["cargo"]["max"]:.0f} cu ft')
    r = x.get("reliability") or {}
    if r.get("stars"):
        bits.append(f'reliability {"★" * r["stars"]}{"☆" * (5 - r["stars"])}')
    line = " · ".join(bits)
    d = x.get("deal")
    if d and d.get("expected") and d["label"] in ("great", "good"):
        line += f'\n{d["label"].title()} deal: {fmt_money(d["delta"])} under {d["basis"]} ({fmt_money(d["expected"])})'

    extra = f'{x.get("seller") or ""} via {", ".join(x["links"])}'
    if x.get("flags"):
        extra += f' — mentions: {", ".join(x["flags"])}'
    return f"{line}\n{extra}"


def is_suspect(x):
    """Listings priced far below similar cars (usually down-payment ads or scams) aren't worth a push."""
    return (x.get("deal") or {}).get("label") == "suspect"


def headline(x):
    return " ".join(str(p) for p in (x.get("year") or "", x["make"], x["model"], x.get("trim") or "") if p).strip()


class Notifier:
    def __init__(self, cfg, enabled=True):
        n = cfg["ntfy"]
        self.url = f'{n["server"].rstrip("/")}/{n["topic"]}'
        # Errors and health alerts go to the maintainer's topic; car alerts to the main one.
        self.ops_url = f'{n["server"].rstrip("/")}/{n["ops_topic"]}' if n.get("ops_topic") else self.url
        self.report_url = cfg.get("publish", {}).get("page_url") or None
        self.title = general(cfg)["title"]
        self.show_cargo = bool(general(cfg)["show_cargo"])
        self.enabled = enabled and bool(n.get("topic"))
        self.http = requests.Session()

    def send(self, title, body, click=None, tags=None, attach=None, priority=None, report_button=True, ops=False):
        if not self.enabled:
            log.info("[notify disabled] %s | %s", title, body.replace("\n", " | "))
            return
        # Headers must be ASCII; ntfy decodes RFC 2047 encoded words for anything else (·, ✓, accents).
        headers = {"Title": title if title.isascii() else f"=?UTF-8?B?{base64.b64encode(title.encode()).decode()}?="}
        if not ops:
            click = click or self.report_url  # car summaries without a single listing open the report
        # Ops messages have no tap action, so tapping opens them in the ntfy app to read in full.
        if click:
            headers["Click"] = click
        if tags:
            headers["Tags"] = tags
        if attach:
            headers["Attach"] = attach
        if priority:
            headers["Priority"] = str(priority)
        if report_button and self.report_url:
            headers["Actions"] = f"view, Open report, {self.report_url}"
        try:
            r = self.http.post(self.ops_url if ops else self.url, data=body.encode("utf-8"), headers=headers, timeout=20)
            r.raise_for_status()
        except Exception as e:
            log.error("ntfy send failed: %s", e)

    def new_listings(self, items):
        items = [x for x in items if not is_suspect(x)]
        rank = {"great": 0, "good": 1}
        items = sorted(items, key=lambda x: (rank.get((x.get("deal") or {}).get("label"), 2),
                                             x["tier"] != "match", x.get("drive_mi") or 999))
        for x in items[:MAX_INDIVIDUAL]:
            great = (x.get("deal") or {}).get("label") == "great"
            if great:
                label, tag, prio = "Great deal", "fire", 5
            elif x["tier"] == "match":
                label, tag, prio = "New match", "red_car", 4
            else:
                label, tag, prio = "New near-miss", "small_orange_diamond", 3
            self.send(f"{label}: {headline(x)}", describe(x, self.show_cargo), click=next(iter(x["links"].values()), None),
                      tags=tag, attach=x.get("image_url"), priority=prio)
        rest = items[MAX_INDIVIDUAL:]
        if rest:
            lines = [f'{headline(x)} · {fmt_money(x["price"])} · {x.get("city") or "?"}' for x in rest[:20]]
            self.send(f"{len(rest)} more new listings", "\n".join(lines), tags="red_car")

    def price_drops(self, drops):
        drops = [(x, p) for x, p in drops if not is_suspect(x)]
        for x, old_price in drops[:MAX_INDIVIDUAL]:
            self.send(f"Price drop: {headline(x)}",
                      f'{fmt_money(old_price)} → {describe(x, self.show_cargo)}',
                      click=next(iter(x["links"].values()), None), tags="chart_with_downwards_trend",
                      attach=x.get("image_url"))

    def first_run(self, items):
        items = list(items)
        matches = sum(1 for x in items if x["tier"] == "match")
        self.send(f"{self.title} is running",
                  f"First scan found {matches} matches and {len(items) - matches} near misses. "
                  "From now on you'll get a notification for each new listing and price drop.",
                  tags="white_check_mark")

    def source_failures(self, rows):
        body = "\n".join(f"{src}: failed {n} runs in a row ({err})" for src, n, err in rows)
        self.send("Some car sites are failing", body, tags="warning", report_button=False, ops=True)

    def source_recovered(self, names):
        self.send("Car sites working again", ", ".join(names) + " returned listings again.",
                  tags="white_check_mark", report_button=False, ops=True)

    def run_summary(self, took, status, counts, raw, in_range, new, drops, gone, published):
        """A quiet end-of-run summary for the maintainer."""
        failed = [n for n, e in status.items() if e]
        mins = round(took.total_seconds() / 60)
        title = f"Car finder run OK · {mins} min" if not failed else f"Car finder run · {len(failed)} site{'s' if len(failed) > 1 else ''} failed"
        sites = "\n".join(f"{'✗' if status[n] else '✓'} {n}: " + (status[n][:120] if status[n] else f"{counts.get(n, 0)} listings")
                          for n in sorted(status))
        pub = {True: "Report published.", False: "Report NOT published.", None: "Publishing skipped."}[published]
        body = (f"{raw:,} listings scanned, {in_range} in range: {new} new, {drops} price drop{'' if drops == 1 else 's'}, {gone} gone.\n"
                f"{sites}\n{pub}")
        self.send(title, body, tags="warning" if failed else "white_check_mark",
                  priority=3 if failed else 2, report_button=bool(published), ops=True)

    def ops(self, title, body, priority=4):
        """An error for the maintainer: crashed runs, failed publishes."""
        self.send(title, body[:1500], tags="rotating_light", priority=priority, report_button=False, ops=True)
