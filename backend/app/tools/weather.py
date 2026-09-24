from __future__ import annotations

import json

from pydantic import Field

from app.core.context import RequestContext
from app.services import weather
from app.tools.base import Tool, ToolOutput, ToolParams


class WeatherParams(ToolParams):
    location: str | None = Field(default=None, max_length=120,
                                 description="City name. Omit to use the user's saved location.")
    days: int = Field(default=3, ge=1, le=10, description="Number of forecast days (1 = today, 2 includes tomorrow)")


class WeatherTool(Tool):
    name = "get_weather"
    description = ("Get current weather and a daily forecast (temperature, rain probability, `rain_expected` flag) "
                   "from Open-Meteo. Uses the user's saved location when no location is given.")
    Params = WeatherParams
    category = "research"

    def describe_call(self, params: WeatherParams) -> str:
        return f"Checking the weather{(' for ' + params.location) if params.location else ''}"

    async def run(self, params: WeatherParams, ctx: RequestContext) -> ToolOutput:
        units = (ctx.preferences.get("regional") or {}).get("units", "metric")
        place = await weather.resolve_place(params.location, ctx.preferences)
        data = await weather.forecast(place, params.days, units)
        ctx.add_source(f"Open-Meteo forecast for {data['place']}", "https://open-meteo.com/", "api")
        return ToolOutput(
            summary=f"Weather for {data['place']}: {data['current']['summary']}",
            content=json.dumps(data, indent=1),
            data={"place": data["place"], "days": [
                {k: d[k] for k in ("date", "summary", "temp_max", "temp_min", "precipitation_probability", "rain_expected")}
                for d in data["days"]
            ]},
        )
