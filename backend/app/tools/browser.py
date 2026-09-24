"""Headless browser (Playwright) for JavaScript-heavy pages.

Every request the page makes - including redirects and sub-resources - is
checked by the SSRF guard, so a malicious page can't make the browser probe
the local network.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.core.context import RequestContext
from app.core.errors import NexusError, ToolExecutionError
from app.security.prompt_injection import wrap_untrusted
from app.security.url_guard import validate_url, validate_url_syntax
from app.tools.base import Tool, ToolOutput, ToolParams
from app.tools.web import html_to_text


def playwright_available() -> tuple[bool, str | None]:
    try:
        import playwright.async_api  # noqa: F401
    except ImportError:
        return False, "Browser automation is not installed (pip install playwright)."
    return True, None


class BrowseParams(ToolParams):
    url: str = Field(max_length=2048)
    screenshot: bool = Field(default=False, description="Also save a screenshot of the rendered page")
    max_chars: int = Field(default=12000, ge=500, le=40000)


class BrowsePageTool(Tool):
    name = "browse_page"
    description = ("Open a public web page in a headless browser (runs JavaScript), return its visible text and "
                   "optionally a screenshot. Use when fetch_webpage returns little content.")
    Params = BrowseParams
    category = "research"
    timeout_seconds = 60

    async def available(self, ctx: RequestContext) -> tuple[bool, str | None]:
        return playwright_available()

    def describe_call(self, params: BrowseParams) -> str:
        return f"Opening {params.url[:80]} in a headless browser"

    def assess(self, params: BrowseParams, ctx: RequestContext):  # type: ignore[override]
        validate_url_syntax(params.url)
        return super().assess(params, ctx)

    async def run(self, params: BrowseParams, ctx: RequestContext) -> ToolOutput:
        from playwright.async_api import Error as PlaywrightError
        from playwright.async_api import async_playwright

        await validate_url(params.url)
        blocked: list[str] = []

        async def guard(route, request):
            try:
                await validate_url(request.url)
            except NexusError:
                blocked.append(request.url[:120])
                await route.abort()
                return
            await route.continue_()

        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                try:
                    context = await browser.new_context(java_script_enabled=True, accept_downloads=False,
                                                        viewport={"width": 1366, "height": 900})
                    page = await context.new_page()
                    await page.route("**/*", guard)
                    await page.goto(params.url, wait_until="domcontentloaded", timeout=30000)
                    try:
                        await page.wait_for_load_state("networkidle", timeout=8000)
                    except PlaywrightError:
                        pass
                    html = await page.content()
                    final_url = page.url
                    shot = await page.screenshot(full_page=False, type="png") if params.screenshot else None
                finally:
                    await browser.close()
        except PlaywrightError as exc:
            raise ToolExecutionError("The headless browser could not load the page.", code="browser_failed",
                                     reason=str(exc).splitlines()[0][:200],
                                     next_step="Check the URL, or run `playwright install chromium`.") from exc

        title, text = html_to_text(html)
        ctx.add_source(title or final_url, final_url, "web", text[:200])
        data: dict = {"url": final_url, "title": title}
        extra = ""
        if shot:
            from app.services import files as file_service

            row = await file_service.store_upload(ctx.user.id, f"page-{datetime.now():%Y%m%d-%H%M%S}.png", shot)
            data["screenshot_file_id"] = str(row.id)
            extra = f"\nScreenshot saved as file id {row.id}."
        if blocked:
            extra += f"\nBlocked {len(blocked)} requests to internal addresses."
        return ToolOutput(
            summary=f"Browsed “{(title or final_url)[:70]}”",
            content=wrap_untrusted(f"Title: {title}\nURL: {final_url}\n\n{text[: params.max_chars]}", source=final_url,
                                   max_chars=params.max_chars + 500) + extra,
            data=data,
        )
