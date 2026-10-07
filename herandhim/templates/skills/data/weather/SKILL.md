---
name: weather
description: "Get current weather and forecasts via Open-Meteo and wttr.in. Use when: user asks about weather, temperature, rain, wind, or forecasts for any location. NOT for: historical weather data, severe weather alerts, or detailed meteorological analysis. No API key needed."
metadata:
  emoji: "🌤️"
---

# Weather Skill

Fetch current weather and forecasts via Open-Meteo (Python script) or wttr.in (curl).

## When to Use

✅ **USE this skill when:**
- "What's the weather in Tokyo?"
- "Will it rain in London today?"
- "5-day forecast for New York"
- "Temperature and wind in Paris"
- "Is it snowing in Boston?"
- User asks about temperature, humidity, wind, precipitation, or conditions for any place

## When NOT to Use

❌ **DON'T use this skill when:**
- Historical weather data → use specialized historical APIs
- Severe weather alerts or warnings → use official weather alert services
- Detailed meteorological analysis → use professional weather tools

## Usage/Commands

### Option A — Python script (Open-Meteo) via `run_skill_script`

```
run_skill_script(script="{skill_path}/weather.py", args=["City Name"])
run_skill_script(script="{skill_path}/weather.py", args=["City Name", "--forecast", "3", "--units", "imperial"])
```

The first positional arg is the city; every option is its own list item.
Options:
- `--forecast 3` — include N-day forecast (default: current only)
- `--format json` — output as JSON (default: human-readable text)
- `--units imperial` — use Fahrenheit/mph (default: metric)

### Option B — wttr.in (curl; only when the `run_command` shell tool is available)

```bash
# Current weather for a city
curl -s "wttr.in/CityName?format=%l%20%t%20%h%20%w%20%c"

# Human-readable output (default)
curl -s "wttr.in/CityName"

# JSON output
curl -s "wttr.in/CityName?format=j1"

# 3-day forecast
curl -s "wttr.in/CityName?2"
```

### Examples

- "What's the weather in Tokyo?" → `run_skill_script(script="{skill_path}/weather.py", args=["Tokyo"])` (or `curl -s wttr.in/Tokyo` if you have a shell)
- "5-day forecast for New York" → `run_skill_script(script="{skill_path}/weather.py", args=["New York", "--forecast", "5"])`
- "Weather in Paris in Fahrenheit" → `run_skill_script(script="{skill_path}/weather.py", args=["Paris", "--units", "imperial"])`

## Notes

- Open-Meteo geocodes city names and returns temperature, humidity, wind, condition, and precipitation
- wttr.in supports city names, airport codes, and lat/long in the URL path
- Both approaches are free and require no API key
