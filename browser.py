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
    Object.defineProperty(HTMLCanvasElement.prototype, 'toDataURL', {
        value: function() {
            const ctx = this.getContext('2d');
            if (ctx) ctx.fillStyle = 'rgba(255,255,255,0.01)';
            return 'data:image/png;base64,';
        }
    });
})()
"""

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


class StealthBrowser:
    def __init__(self, headless: bool = True):
        self.headless = headless
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
        await self.context.add_init_script(STEALTH_INIT)

        pages = self.context.pages
        self.page = pages[0] if pages else await self.context.new_page()
        # ponytail: extra_http_headers, can remove if no benefit
        await self.page.set_extra_http_headers({
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        })

    async def check_login(self) -> bool:
        """True if logged in (profile icon present, no login modal)."""
        await self.page.goto("https://www.tiktok.com", wait_until="domcontentloaded")
        await asyncio.sleep(2)

        login_button = await self.page.query_selector(
            'button:has-text("Log in"), div:has-text("Log in") >> visible=true'
        )
        if login_button:
            return False

        profile_icon = await self.page.query_selector(
            '[data-e2e="top-login-container"] img, [aria-label="Profile"]'
        )
        return profile_icon is not None

    async def goto_messages(self):
        await self.page.goto("https://www.tiktok.com/messages", wait_until="domcontentloaded")
        await asyncio.sleep(random.uniform(2, 4))
        log.info("On messages page: %s", self.page.url)

    async def search_dm(self, username: str):
        """Search for user in DM sidebar and open conversation."""
        username = username.lstrip("@")

        search_input = await self._find_element([
            'input[placeholder*="Search" i]',
            'input[placeholder*="search" i]',
            'input[type="search"]',
            '[data-e2e="message-search-input"] input',
        ], timeout=10000)

        if not search_input:
            log.warning("DM search input not found for %s", username)
            return False

        await search_input.click()
        await self._human_delay(0.3, 0.8)
        await self._human_clear(search_input)
        await self._human_type(search_input, username)
        await self._human_delay(1.5, 3)

        user_item = await self._find_element([
            f'text="{username}"',
            f'[data-e2e="chat-list-item"]:has-text("{username}")',
            f'div:has-text("{username}") >> visible=true',
        ], timeout=5000)

        if user_item:
            await user_item.click()
            await self._human_delay(1, 2)
            log.info("Opened DM with %s", username)
            return True

        log.warning("User %s not found in DM list", username)
        return False

    async def send_message(self, text: str) -> bool:
        """Type message into DM input and send."""
        input_box = await self._find_element([
            'div[contenteditable="true"]',
            '[data-e2e="message-input"]',
            'div[role="textbox"]',
            '.public-DraftEditor-content',
        ], timeout=10000)

        if not input_box:
            log.error("Message input not found")
            return False

        await input_box.click()
        await self._human_delay(0.3, 0.8)
        await self._human_type(input_box, text)
        await self._human_delay(0.5, 2.0)

        await self.page.keyboard.press("Enter")
        await self._human_delay(0.5, 1.5)
        log.info("Sent: %s", text)
        return True

    async def close(self):
        if self.context:
            await self.context.close()
        if self.playwright:
            await self.playwright.stop()

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
        await element.evaluate("el => { el.textContent = ''; el.focus(); }")
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

            found = await browser.search_dm(target)
            if not found:
                results[target] = False
                continue

            sent = await browser.send_message(msg)
            if sent:
                log_sent(target, msg)
                results[target] = True
            else:
                results[target] = False

            check_page(browser.page)

            if i < len(targets) - 1:
                pause = random.uniform(30, 120)
                log.info("Pausing %.0fs before next target", pause)
                await asyncio.sleep(pause)

    except Exception as e:
        log.exception("Fatal error during DM flow: %s", e)
    finally:
        await browser.close()

    return results
