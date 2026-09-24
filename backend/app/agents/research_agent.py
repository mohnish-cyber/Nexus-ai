from __future__ import annotations

import re

from app.agents.base import Agent, AgentResult, AgentTask
from app.core.context import RequestContext
from app.tools.executor import execute_tool

_WEATHER_RE = re.compile(r"\b(weather|forecast|temperature|rain|umbrella|snow|humid|sunny)\b", re.IGNORECASE)
_RESEARCHY_RE = re.compile(r"\b(search|news|compare|latest|price|buy|review|best|vs)\b", re.IGNORECASE)
_LOCATION_RE = re.compile(
    r"\b(?:in|for|at)\s+(?P<loc>[a-z][\w\s,.'-]{1,60}?)(?=\s+(?:today|tomorrow|tonight|this|next|on|and|if)\b|[?.!,]|$)",
    re.IGNORECASE,
)
_NOT_PLACES = {"today", "tomorrow", "tonight", "the morning", "the evening", "the afternoon", "my area", "my city",
               "here", "my location", "the week", "the weekend", "this week"}


def extract_location(text: str) -> str | None:
    for m in _LOCATION_RE.finditer(text):
        loc = m.group("loc").strip(" ,.")
        if loc.lower() not in _NOT_PLACES and not loc.lower().startswith(("the ", "my ")):
            return loc
    return None


class ResearchAgent(Agent):
    name = "research"
    title = "ResearchAgent"
    purpose = "Searches the internet, reads pages, compares sources and reports with citations. Also checks weather."
    allowed_tools = frozenset({"web_search", "fetch_webpage", "browse_page", "get_weather"})
    max_steps = 8
    instructions = """
You are ResearchAgent. Research the request using approved tools, then answer.

Method:
1. For time-sensitive topics (news, prices, releases, "latest", "current") use web_search with a freshness
   filter; otherwise a plain search.
2. Open the 2-4 most relevant results with fetch_webpage (or browse_page for JavaScript-heavy sites).
3. Compare sources. Prefer primary/official sources. Note disagreements and how recent each source is.
4. Answer concisely. Cite sources inline as [1], [2] matching a short "Sources" list (title + URL) at the end.
5. State uncertainty explicitly (e.g. prices change, stock varies by region, a source may be outdated).
For product comparisons, use a compact table (name, price, key specs, source). Currency: keep the user's
currency (e.g. ₹). For weather use get_weather - it needs no search. Never fabricate URLs, prices or specs.
If search is not configured, say so and answer only what you can verify with other tools.
"""

    async def prefer_fallback(self, task: AgentTask, ctx: RequestContext) -> bool:
        # Plain weather questions don't need a model round-trip.
        return bool(_WEATHER_RE.search(task.instruction + " " + task.user_message)) and not _RESEARCHY_RE.search(
            task.user_message)

    async def fallback(self, task: AgentTask, ctx: RequestContext) -> AgentResult | None:
        text = task.user_message
        if _WEATHER_RE.search(text):
            loc = extract_location(text)
            days = 2 if "tomorrow" in text.lower() else 3
            ex = await execute_tool(ctx, "get_weather", {"location": loc, "days": days}, agent=self.title,
                                    allowed_tools=set(self.allowed_tools))
            if not ex.ok and ex.error is not None:
                return AgentResult.failure(self.name, ex.error)
            d = ex.output.data if ex.output else {}
            lines = [f"**Weather for {d.get('place')}**"]
            for day in d.get("days", []):
                rain = " · rain expected" if day.get("rain_expected") else ""
                lines.append(f"- {day['date']}: {day['summary']}, {day.get('temp_min')}–{day.get('temp_max')}°, "
                             f"precipitation chance {day.get('precipitation_probability')}%{rain}")
            return AgentResult(agent=self.name, status="succeeded", answer="\n".join(lines), data=d)
        ex = await execute_tool(ctx, "web_search", {"query": text[:400], "max_results": 6}, agent=self.title,
                                allowed_tools=set(self.allowed_tools))
        if not ex.ok:
            return None
        results = [s for s in ctx.sources if s.get("kind") == "web"][:6]
        lines = ["Here are the top results (AI summarisation is unavailable without an AI key):"]
        for i, s in enumerate(results, 1):
            lines.append(f"{i}. [{s['title']}]({s['url']}) — {s.get('snippet', '')[:160]}")
        return AgentResult(agent=self.name, status="succeeded", answer="\n".join(lines))
