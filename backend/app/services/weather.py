"""Weather via Open-Meteo (free, no API key required)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from app.core.errors import NotFoundError, ToolExecutionError

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

WMO_CODES = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast", 45: "fog", 48: "freezing fog",
    51: "light drizzle", 53: "drizzle", 55: "dense drizzle", 56: "freezing drizzle", 57: "freezing drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain", 66: "freezing rain", 67: "heavy freezing rain",
    71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow grains", 80: "light rain showers",
    81: "rain showers", 82: "violent rain showers", 85: "snow showers", 86: "heavy snow showers",
    95: "thunderstorm", 96: "thunderstorm with hail", 99: "thunderstorm with heavy hail",
}
RAIN_CODES = {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 99}


def _why(exc: Exception) -> str:
    if isinstance(exc, httpx.ProxyError):
        return f"A network proxy refused the connection to Open-Meteo ({exc})."
    if isinstance(exc, httpx.TimeoutException):
        return "Open-Meteo did not respond in time."
    return f"{exc.__class__.__name__}: {str(exc)[:150]}"


@dataclass
class Place:
    name: str
    latitude: float
    longitude: float
    country: str | None = None
    admin: str | None = None
    timezone: str | None = None

    @property
    def label(self) -> str:
        return ", ".join(p for p in (self.name, self.admin, self.country) if p)


async def geocode(name: str) -> Place:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(GEOCODE_URL, params={"name": name, "count": 1, "language": "en", "format": "json"})
    except httpx.HTTPError as exc:
        raise ToolExecutionError("Could not reach the weather service.", code="weather_unreachable",
                                 reason=_why(exc), next_step="Check your internet connection.") from exc
    results = (resp.json() or {}).get("results") or []
    if not results:
        raise NotFoundError(f"I couldn't find a place called '{name}'.", code="place_not_found",
                            next_step="Try a nearby city name, optionally with the country.")
    r = results[0]
    return Place(r["name"], r["latitude"], r["longitude"], r.get("country"), r.get("admin1"), r.get("timezone"))


async def forecast(place: Place, days: int = 3, units: str = "metric") -> dict[str, Any]:
    params: dict[str, Any] = {
        "latitude": place.latitude,
        "longitude": place.longitude,
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m,precipitation",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum,wind_speed_10m_max",
        "timezone": "auto",
        "forecast_days": max(1, min(days, 16)),
    }
    if units == "imperial":
        params.update({"temperature_unit": "fahrenheit", "wind_speed_unit": "mph", "precipitation_unit": "inch"})
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(FORECAST_URL, params=params)
    except httpx.HTTPError as exc:
        raise ToolExecutionError("Could not reach the weather service.", code="weather_unreachable",
                                 reason=_why(exc), next_step="Check your internet connection.") from exc
    if resp.status_code >= 400:
        raise ToolExecutionError(f"The weather service returned HTTP {resp.status_code}.", code="weather_failed")
    data = resp.json()
    daily = data.get("daily") or {}
    out_days = []
    for i, date in enumerate(daily.get("time", [])):
        code = (daily.get("weather_code") or [None])[i]
        prob = (daily.get("precipitation_probability_max") or [None])[i]
        amount = (daily.get("precipitation_sum") or [None])[i]
        rain_expected = bool((prob is not None and prob >= 50) or (amount is not None and amount >= 1.0)
                             or code in RAIN_CODES)
        out_days.append({
            "date": date,
            "summary": WMO_CODES.get(code, "unknown"),
            "temp_max": (daily.get("temperature_2m_max") or [None])[i],
            "temp_min": (daily.get("temperature_2m_min") or [None])[i],
            "precipitation_probability": prob,
            "precipitation_sum": amount,
            "wind_max": (daily.get("wind_speed_10m_max") or [None])[i],
            "rain_expected": rain_expected,
        })
    cur = data.get("current") or {}
    return {
        "place": place.label,
        "timezone": data.get("timezone"),
        "units": data.get("daily_units") or {},
        "current": {
            "temperature": cur.get("temperature_2m"),
            "feels_like": cur.get("apparent_temperature"),
            "humidity": cur.get("relative_humidity_2m"),
            "wind": cur.get("wind_speed_10m"),
            "summary": WMO_CODES.get(cur.get("weather_code"), "unknown"),
        },
        "days": out_days,
        "source": "Open-Meteo",
    }


async def resolve_place(location: str | None, prefs: dict[str, Any]) -> Place:
    if location:
        return await geocode(location)
    loc = prefs.get("location") or {}
    if loc.get("latitude") is not None and loc.get("longitude") is not None:
        return Place(loc.get("city") or "your location", float(loc["latitude"]), float(loc["longitude"]),
                     loc.get("country"))
    if loc.get("city"):
        return await geocode(loc["city"])
    raise NotFoundError(
        "I don't know your location yet.",
        code="location_unknown",
        next_step="Tell me your city (e.g. 'weather in Pune'), or set it in Settings → Location.",
    )
