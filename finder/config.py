"""Loads config.toml with config.local.toml merged over it. Only uses the standard library, so
run_daily.sh can read the schedule without loading the scraper's dependencies."""
import tomllib
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent


def load_config():
    """config.toml, with config.local.toml (not committed: holds the ntfy topic) merged over it."""
    cfg = tomllib.load(open(ROOT / "config.toml", "rb"))
    local = ROOT / "config.local.toml"
    if local.exists():
        for section, values in tomllib.load(open(local, "rb")).items():
            if isinstance(values, dict):
                cfg.setdefault(section, {}).update(values)
            else:
                cfg[section] = values
    return cfg


def general(cfg):
    """The [general] section with defaults filled in."""
    return {"title": "Car Finder", "maintainer": "the person who runs it", "home_area": "",
            "timezone": "America/Chicago", "run_hours": [7, 16], "show_cargo": True, **cfg.get("general", {})}


def timezone(cfg):
    return ZoneInfo(general(cfg)["timezone"])


if __name__ == "__main__":
    # run_daily.sh reads the schedule from this:  <timezone> <HH> <HH> ...
    g = general(load_config())
    print(g["timezone"], *(f"{int(h):02d}" for h in g["run_hours"]))
