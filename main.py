#!/usr/bin/env python3
import argparse
import asyncio
import json
import logging
import random
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("flamekeeper")

CONFIG_PATH = Path.home() / ".tiktok-flamekeeper" / "config.json"


def load_config(path: str | None = None) -> dict:
    path = Path(path) if path else CONFIG_PATH
    if not path.exists():
        log.error("Config not found at %s. Copy config.json.example and edit it.", path)
        sys.exit(1)
    return json.loads(path.read_text())


def cmd_setup(_args):
    """Interactive setup: open browser for manual login, create config."""
    from browser import StealthBrowser

    config_dest = Path(_args.config) if _args.config else CONFIG_PATH
    config_dest.parent.mkdir(parents=True, exist_ok=True)

    if not config_dest.exists():
        example = Path(__file__).parent / "config.json.example"
        config_dest.write_text(example.read_text())
        log.info("Config created at %s — edit targets and messages", config_dest)

    async def _setup():
        browser = StealthBrowser(headless=False, stealth=False)
        try:
            await browser.start()
            await browser.page.goto("https://www.tiktok.com/login", wait_until="domcontentloaded")
            log.info("Browser opened. Log into TikTok in the browser window.")
            log.info("Close the browser tab/window when done logging in.")
            await browser.wait_for_close()
            log.info("Profile saved to ~/.tiktok-flamekeeper/profile")
        finally:
            await browser.close()

    asyncio.run(_setup())


def cmd_run(args):
    """Run the DM streak flow."""
    config = load_config(args.config)
    from browser import run_dm_flow

    results = asyncio.run(run_dm_flow(
        targets=config["targets"],
        messages=config["messages"],
        headless=not args.debug,
    ))

    succeeded = sum(1 for v in results.values() if v)
    failed = len(results) - succeeded
    log.info("Done. %d sent, %d failed.", succeeded, failed)

    if failed > 0 and config.get("webhook_url"):
        from sentinel import notify
        notify(f"{failed}/{len(results)} targets failed.", config["webhook_url"])


def cmd_log(args):
    """Show recent streak log."""
    config = load_config(args.config)
    from db import get_streak_log

    target = args.target or config["targets"][0] if config["targets"] else None
    rows = get_streak_log(target, limit=args.n)
    for target_name, msg, ts in rows:
        print(f"{ts}  {target_name:20s}  {msg}")


def cmd_import_cookies(args):
    """Import cookies from real browser login."""
    import json as _json
    from browser import StealthBrowser

    cookie_file = Path(args.file)
    if not cookie_file.exists():
        log.error("Cookie file not found: %s", cookie_file)
        sys.exit(1)

    raw = _json.loads(cookie_file.read_text())

    if isinstance(raw, list):
        cookies = raw
    elif isinstance(raw, dict):
        cookies = [
            {"name": k, "value": v, "domain": ".tiktok.com", "path": "/"}
            for k, v in raw.items()
        ]
    else:
        log.error("Invalid cookie format. Use JSON array or {name: value} object.")
        sys.exit(1)

    async def _import():
        browser = StealthBrowser(headless=not args.show, stealth=False)
        try:
            await browser.start()
            await browser.page.goto("https://www.tiktok.com", wait_until="domcontentloaded")
            await browser.context.add_cookies(cookies)
            await browser.page.reload()
            logged_in = await browser.check_login()
            log.info("Cookies imported. Login: %s", "OK" if logged_in else "FAILED")
        finally:
            await browser.close()

    asyncio.run(_import())


def cmd_test(_args):
    """Quick smoke test: check login state only."""
    from browser import StealthBrowser

    async def _test():
        browser = StealthBrowser(headless=not _args.show, stealth=True)
        try:
            await browser.start()
            logged_in = await browser.check_login()
            log.info("Login status: %s", "OK" if logged_in else "NOT LOGGED IN")
        finally:
            await browser.close()

    asyncio.run(_test())


def main():
    parser = argparse.ArgumentParser(description="TikTok FlameKeeper — auto DM streaks")
    sub = parser.add_subparsers(dest="command")

    run_p = sub.add_parser("run", help="Run automated DM streak flow")
    run_p.add_argument("--config", "-c", help="Config file path")
    run_p.add_argument("--debug", action="store_true", help="Show browser window")

    setup_p = sub.add_parser("setup", help="First-time setup: login and create config")
    setup_p.add_argument("--config", "-c", help="Config file path")

    log_p = sub.add_parser("log", help="Show recent streak history")
    log_p.add_argument("--config", "-c", help="Config file path")
    log_p.add_argument("--target", "-t", help="Filter by target username")
    log_p.add_argument("--n", type=int, default=30, help="Number of entries")

    test_p = sub.add_parser("test", help="Test login state only")
    test_p.add_argument("--show", action="store_true", help="Show browser (needs display)")

    import_p = sub.add_parser("import-cookies", help="Import cookies from real browser")
    import_p.add_argument("file", help="Path to cookies.json")
    import_p.add_argument("--show", action="store_true", help="Show browser (needs display; omit on headless server)")

    args = parser.parse_args()

    if args.command == "setup":
        cmd_setup(args)
    elif args.command == "run":
        cmd_run(args)
    elif args.command == "log":
        cmd_log(args)
    elif args.command == "test":
        cmd_test(args)
    elif args.command == "import-cookies":
        cmd_import_cookies(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
