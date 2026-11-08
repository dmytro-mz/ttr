"""Play a whole game through the real browser UI (clicks only) and fail on any page error.

    uv run python scripts/ui_check.py [--bots 2] [--seed 5] [--max-turns 80] [--headed] [--shots shots/ui]

The human seat picks tickets, claims routes (paying tunnels when it can), and otherwise draws from the deck,
while bots play on the server. Screenshots of interesting moments land in --shots.
"""

from __future__ import annotations

import argparse
import asyncio
import time
from pathlib import Path

from demo import prepare, serving
from playwright.async_api import Page, async_playwright

from ttr.web.server import create_app

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


class Checker:
    def __init__(self, page: Page, shots: Path) -> None:
        self.page = page
        self.shots = shots
        self.errors: list[str] = []
        self.taken: set[str] = set()
        self.claims = 0
        self.draws = 0
        page.on("pageerror", lambda e: self.errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: m.type == "error" and self.errors.append(f"console: {m.text}"))

    async def shot(self, name: str) -> None:
        if name not in self.taken:
            self.taken.add(name)
            await self.page.screenshot(path=str(self.shots / f"{name}.png"))

    async def visible(self, selector: str) -> bool:
        return await self.page.locator(selector).count() > 0

    async def click_box(self, selector: str) -> None:
        box = await self.page.locator(selector).first.bounding_box()
        assert box, selector
        await self.page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)

    async def settle(self) -> None:
        await self.page.wait_for_timeout(250)

    async def smoke_dialogs(self) -> None:
        page = self.page
        await page.get_by_title("How to play").click()
        await page.wait_for_selector(".backdrop")
        await self.shot("rules")
        await page.keyboard.press("Escape")
        await self.settle()
        await page.get_by_title("Scores").click()
        await self.settle()
        await self.shot("scores")
        await page.keyboard.press("Escape")
        await self.settle()

    async def my_turn(self) -> bool:
        page = self.page
        if await self.visible(".float-panel .offer"):
            await self.shot("tickets")
            await page.get_by_role("button", name="Select all").click()
            await page.locator(".float-panel .actions .btn.primary").click()
            return True
        if await self.visible(".tunnel-panel .actions"):
            await self.shot("tunnel")
            pay = page.locator(".tunnel-panel .actions .btn.primary")
            if await pay.count():
                await pay.first.click()
            else:
                await page.get_by_role("button", name="Give up the route").click()
            return True
        if not await self.visible(".status.mine"):
            return False
        claimable = page.locator(".route.claimable")
        if await claimable.count():
            rid = await claimable.first.get_attribute("data-route")
            await self.click_box(f'.route[data-route="{rid}"] .space-rect')
            await page.wait_for_selector(".popover .btn.pay", timeout=3000)
            await self.shot("claim-popover")
            await page.locator(".popover .btn.pay").first.click()
            self.claims += 1
            return True
        for selector in ['.pile.clickable[data-fly="deck"]', "#market .face-up .tcard.clickable"]:
            pile = page.locator(selector)
            if await pile.count():
                await pile.first.click()
                self.draws += 1
                return True
        tickets = page.locator('.pile.clickable[data-fly="tickets"]')
        if await tickets.count():
            await tickets.first.click()
            return True
        await page.get_by_role("button", name="Pass").click()
        return True


async def run(args: argparse.Namespace) -> int:
    shots = Path(args.shots)
    shots.mkdir(parents=True, exist_ok=True)
    room = prepare("tickets", bots=args.bots, seed=args.seed, delay_scale=0.02)
    room.settings.hints = True
    app = create_app(delay_scale=0.02)
    async with serving(app, room, port=args.port) as url, async_playwright() as pw:
        browser = await pw.chromium.launch(executable_path=CHROME, headless=not args.headed)
        page = await browser.new_page(viewport={"width": 1440, "height": 900}, reduced_motion="reduce")
        await page.add_init_script("localStorage.setItem('ttr.showClaimable', '1')")
        check = Checker(page, shots)
        await page.goto(url)
        await page.wait_for_selector(".board-svg")
        await check.smoke_dialogs()
        await page.get_by_role("button", name="Hint").click()
        await check.settle()
        await check.shot("hint")
        deadline = time.monotonic() + args.timeout
        while room.status == "playing" and time.monotonic() < deadline:
            if room.game and room.game.turn > args.max_turns:
                break
            acted = await check.my_turn()
            await page.wait_for_timeout(300 if acted else 120)
            if check.claims == 3:
                await check.shot("mid-game")
        await check.settle()
        await check.shot("end" if room.status != "playing" else "stopped")
        await browser.close()
    print(f"status={room.status} turn={room.game.turn if room.game else 0} claims={check.claims} draws={check.draws}")
    for err in check.errors:
        print(err)
    return 1 if check.errors else 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bots", type=int, default=2)
    ap.add_argument("--seed", type=int, default=5)
    ap.add_argument("--max-turns", type=int, default=400)
    ap.add_argument("--timeout", type=float, default=240)
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--port", type=int, default=8767)
    ap.add_argument("--shots", default="shots/ui")
    raise SystemExit(asyncio.run(run(ap.parse_args())))


if __name__ == "__main__":
    main()
