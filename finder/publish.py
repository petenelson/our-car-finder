"""Publishes the report to a GitHub Pages repo by committing the built site and pushing."""
import logging
import shutil
import subprocess

log = logging.getLogger("finder")


def git(repo, *args, check=True):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=180, check=check)


def publish(cfg, root, site):
    pub = cfg["publish"]
    repo = root / pub.get("checkout", "pages")
    try:
        if not (repo / ".git").exists():
            subprocess.run(["git", "clone", pub["repo"], str(repo)], capture_output=True, text=True,
                           timeout=180, check=True)
        branch = pub.get("branch", "main")
        if git(repo, "rev-parse", "--verify", "HEAD", check=False).returncode == 0:
            git(repo, "fetch", "origin")
            if git(repo, "ls-remote", "--exit-code", "--heads", "origin", branch, check=False).returncode == 0:
                git(repo, "reset", "--hard", f"origin/{branch}")
        else:
            git(repo, "checkout", "-B", branch)

        # Mirror the built site into the Pages folder: replace the page, sync thumbs.
        out = repo / pub.get("path", "docs")
        out.mkdir(exist_ok=True)
        shutil.copy2(site / "index.html", out / "index.html")
        if (site / "alerts.html").exists():
            shutil.copy2(site / "alerts.html", out / "alerts.html")
        dst = out / "thumbs"
        dst.mkdir(exist_ok=True)
        want = {p.name for p in (site / "thumbs").glob("*.jpg")}
        for p in dst.glob("*.jpg"):
            if p.name not in want:
                p.unlink()
        for name in want:
            if not (dst / name).exists():
                shutil.copy2(site / "thumbs" / name, dst / name)
        (out / ".nojekyll").touch()

        git(repo, "add", "-A")
        if git(repo, "diff", "--cached", "--quiet", check=False).returncode == 0:
            log.info("publish: nothing changed")
            return True
        stamp = subprocess.run(["date", "+%Y-%m-%d %H:%M %Z"], capture_output=True, text=True).stdout.strip()
        git(repo, "commit", "-m", f"Update listings {stamp}")
        git(repo, "push", "-u", "origin", branch)
        log.info("published to %s", pub["repo"])
        return True
    except subprocess.CalledProcessError as e:
        log.error("publish failed: %s %s", e.stderr, e.stdout)
    except Exception as e:
        log.error("publish failed: %s", e)
    return False
