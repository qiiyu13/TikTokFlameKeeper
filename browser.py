import asyncio
import random
import logging
from pathlib import Path
from playwright.async_api import async_playwright, Page

log = logging.getLogger(__name__)

PROFILE_DIR = Path.home() / ".tiktok-flamekeeper" / "profile"

# ponytail: manual stealth patch, swap to playwright-stealth pkg if detection tightens
STEALTH_INIT = """
(() => {
    Object.defineProperty(navigator, 'webdriver', { get: () => false });
    Object.defineProperty(navigator, 'plugins', {
        get: () => {
            const p = [
                {name:'Chrome PDF Plugin', filename:'internal-pdf-viewer'},
                {name:'Chrome PDF Viewer', filename:'mhjfbmdgcfjbbpaeojofohoefgiehjai'},
                {name:'Native Client', filename:'internal-nacl-plugin'}
            ];
            p.item = i => p[i];
            p.namedItem = n => p.find(x => x.name === n);
            p.refresh = () => {};
            Object.setPrototypeOf(p, PluginArray.prototype);
            return p;
        }
    });
    Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en', 'zh-CN'] });
    Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 4 });
    Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
    window.chrome = { runtime: {}, loadTimes: () => {}, csi: () => {}, app: {} };
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (params) =>
        params.name === 'notifications'
            ? Promise.resolve({state: Notification.permission})
            : originalQuery(params);
    Object.defineProperty(Notification, 'permission', {
        get: () => navigator.permissions ? 'granted' : 'denied'
    });
    
})()
"""

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


class StealthBrowser:
    def __init__(self, headless: bool = True, stealth: bool = True):
        self.headless = headless
        self.stealth = stealth
        self.playwright = None
        self.context = None
        self.page = None

    async def start(self):
        self.playwright = await async_playwright().start()
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)

        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=self.headless,
            viewport={"width": 1280, "height": 800},
            user_agent=UA,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
            ],
            locale="en-US",
            timezone_id="America/Chicago",
            permissions=["notifications"],
            geolocation={"latitude": 41.8781, "longitude": -87.6298},
        )
        await self.context.add_init_script(STEALTH_INIT) if self.stealth else None

        pages = self.context.pages
        self.page = pages[0] if pages else await self.context.new_page()
        # ponytail: extra_http_headers, can remove if no benefit
        await self.page.set_extra_http_headers({
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        })

    async def check_login(self) -> bool:
        """True if logged in (page redirects away from login, user nav visible)."""
        await self.page.goto("https://www.tiktok.com", wait_until="domcontentloaded")
        # Logged-in nav renders after hydration; give it time and a stable hook.
        nav_sel = (
            '[data-e2e="profile-icon"], [data-e2e="nav-profile"], '
            '[data-e2e="nav-upload"], [data-e2e="upload-icon"]'
        )
        try:
            await self.page.wait_for_selector(nav_sel, timeout=10000)
        except Exception:
            pass
        await self._human_delay(1, 2)

        url = self.page.url
        if "login" in url.lower():
            return False

        login_button = await self.page.query_selector(
            '[data-e2e="top-login-button"], button:has-text("Log in")'
        )
        if login_button and await login_button.is_visible():
            return False

        nav_elements = await self.page.query_selector_all(nav_sel)
        return len(nav_elements) > 0

    async def goto_messages(self):
        await self.page.goto("https://www.tiktok.com/messages", wait_until="domcontentloaded")
        await asyncio.sleep(random.uniform(2, 4))
        log.info("On messages page: %s", self.page.url)

    CONV_ITEM = '[data-e2e="dm-new-conversation-item"]'
    CONV_NICK = '[data-e2e="dm-new-conversation-nickname"]'

    async def open_first_dm(self):
        """Click the first (pinned) conversation in DM sidebar."""
        await self.goto_messages()
        await self._human_delay(1, 3)

        first = await self._find_element([self.CONV_ITEM], timeout=8000)
        if first:
            await first.click()
            await self._human_delay(1, 3)
            log.info("Opened first/pinned DM conversation")
            return True

        log.warning("No conversations found in DM sidebar")
        return False

    async def goto_dm_with_user(self, username: str):
        """Open an existing DM, matched by the sidebar nickname.

        The sidebar shows display nicknames, never @handles, so `username`
        must be the nickname as shown in TikTok messages (e.g. "vall").
        """
        name = username.lstrip("@").strip().lower()
        await self.goto_messages()
        await self._human_delay(1, 3)

        try:
            await self.page.wait_for_selector(self.CONV_ITEM, timeout=8000)
        except Exception:
            log.warning("DM sidebar never rendered conversation items")
            return await self._search_dm_in_sidebar(username)

        items = self.page.locator(self.CONV_ITEM)
        count = await items.count()
        for i in range(count):
            item = items.nth(i)
            nick_el = item.locator(self.CONV_NICK).first
            try:
                nick = (await nick_el.text_content()) or ""
            except Exception:
                continue
            if name and name in nick.strip().lower():
                await item.click()
                await self._human_delay(1, 3)
                log.info("Opened DM with nickname %r (target %s)", nick.strip(), username)
                return True

        log.warning("No sidebar conversation nickname matches %r", username)
        return await self._search_dm_in_sidebar(username)

    async def _search_dm_in_sidebar(self, username: str):
        """Fallback: type into the top search box, click the first result."""
        name = username.lstrip("@")
        search_input = await self._find_element([
            'input[data-e2e="search-user-input"]',
            'input[placeholder*="Search" i]',
            'input[type="search"]',
        ], timeout=6000)

        if not search_input:
            log.warning("DM sidebar search not found")
            return False

        await search_input.click()
        await self._human_delay(0.3, 0.8)
        await self._human_clear(search_input)
        await self._human_type(search_input, name)
        await self._human_delay(1.5, 3)

        result = await self._find_element([self.CONV_ITEM], timeout=5000)
        if result:
            await result.click()
            await self._human_delay(1, 2)
            log.info("Opened first search result for %s", username)
            return True

        log.warning("User %s not found via search", username)
        return False

    async def send_message(self, text: str) -> bool:
        """Type message into DM and send."""
        await self._human_delay(0.5, 1.5)

        input_box = await self._find_element([
            'div[contenteditable="true"]',
            '[data-e2e="message-input"]',
            'div[role="textbox"]',
            '.public-DraftEditor-content',
            '[class*="DraftEditor"]',
            '[class*="ProseMirror"]',
            '[class*="msg-input" i]',
            '[class*="chat-input" i]',
            '[class*="message"] [contenteditable]',
            '[contenteditable="true"]',
        ], timeout=5000)

        if not input_box:
            log.error("Message input not found; nothing sent")
            return False

        await input_box.click()
        await self._human_delay(0.2, 0.5)

        await self._human_type_direct(text)
        await self._human_delay(0.5, 2.0)

        await self.page.keyboard.press("Enter")
        await self._human_delay(0.5, 1.5)
        log.info("Sent: %s", text)
        return True

    async def wait_for_close(self):
        """Wait until all browser pages are closed by the user."""
        while self.context and self.context.pages:
            await asyncio.sleep(1)

    async def close(self):
        if self.context:
            await self.context.close()
        if self.playwright:
            await self.playwright.stop()

    async def _dismiss_modals(self):
        """Close any overlay/modals intercepting clicks."""
        await self._human_delay(0.5, 1)
        await self.page.keyboard.press("Escape")
        await self._human_delay(0.5, 1)

        close_btns = await self.page.query_selector_all(
            '[aria-label="Close"], [data-e2e="modal-close"], '
            '.TUXModal-close, [class*="close" i] >> visible=true'
        )
        for btn in close_btns:
            try:
                await btn.click(timeout=2000)
                await self._human_delay(0.5, 1)
            except Exception:
                pass

    async def _human_type_direct(self, text: str):
        """Type directly via keyboard (no element required)."""
        for char in text:
            await self.page.keyboard.type(char, delay=random.randint(50, 200))

    async def _find_element(self, selectors: list[str], timeout: int = 5000):
        for sel in selectors:
            try:
                el = await self.page.wait_for_selector(sel, timeout=timeout)
                if el:
                    return el
            except Exception:
                continue
        return None

    @staticmethod
    async def _human_delay(min_s: float, max_s: float):
        await asyncio.sleep(random.uniform(min_s, max_s))

    @staticmethod
    async def _human_clear(element):
        await element.click()
        await asyncio.sleep(0.1)
        # <input>/<textarea> use .value; contenteditable uses .textContent. Clear both.
        await element.evaluate(
            "el => { el.focus(); if ('value' in el) el.value = ''; "
            "else el.textContent = ''; "
            "el.dispatchEvent(new Event('input', {bubbles: true})); }"
        )
        await asyncio.sleep(0.1)

    async def _human_type(self, element, text: str):
        """Type with random per-character delay (50-200ms)."""
        await element.focus()
        for char in text:
            await self.page.keyboard.type(char, delay=random.randint(50, 200))


async def run_dm_flow(targets: list[str], messages: list[str], headless: bool):
    """Send one DM to each target. Returns dict of {target: success}."""
    from db import pick_message, log_sent, init_db
    from sentinel import check_page, notify

    init_db()

    browser = StealthBrowser(headless=headless)
    results = {}

    try:
        await browser.start()
        log.info("Browser started (headless=%s)", headless)

        logged_in = await browser.check_login()
        if not logged_in:
            log.error("Not logged in. Run --setup first to save cookies.")
            return results

        await browser.goto_messages()

        for i, target in enumerate(targets):
            log.info("[%d/%d] Processing %s", i + 1, len(targets), target)

            msg = pick_message(target, messages)

            found = await browser.goto_dm_with_user(target)
            if not found:
                results[target] = False
                continue

            sent = await browser.send_message(msg)
            if sent:
                log_sent(target, msg)
                results[target] = True
            else:
                results[target] = False

            await check_page(browser.page)

            if i < len(targets) - 1:
                pause = random.uniform(30, 120)
                log.info("Pausing %.0fs before next target", pause)
                await asyncio.sleep(pause)

    except Exception as e:
        log.exception("Fatal error during DM flow: %s", e)
    finally:
        await browser.close()

    return results
