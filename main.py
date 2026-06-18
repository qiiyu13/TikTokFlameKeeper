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
        browser = StealthBrowser(headless=False)
        try:
            await browser.start()
            log.info("Browser opened. Log into TikTok manually in the browser window.")
            log.info("After login, press Enter here to save and exit...")
            await asyncio.get_event_loop().run_in_executor(None, input)
            log.info("Profile saved to %s", "/home/$USER/.tiktok-flamekeeper/profile")
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


def cmd_test(_args):
    """Quick smoke test: check login state only."""
    from browser import StealthBrowser

    async def _test():
        browser = StealthBrowser(headless=False)
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

    args = parser.parse_args()

    if args.command == "setup":
        cmd_setup(args)
    elif args.command == "run":
        cmd_run(args)
    elif args.command == "log":
        cmd_log(args)
    elif args.command == "test":
        cmd_test(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
