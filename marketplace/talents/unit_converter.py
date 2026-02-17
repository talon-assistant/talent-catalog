"""UnitConverterTalent — convert between units of measurement and currencies.

Supports length, weight, temperature, volume, speed, data size, time,
and live currency exchange rates via a free API.

Examples:
    "convert 100 miles to kilometers"
    "convert 72 fahrenheit to celsius"
    "convert 5 pounds to kilograms"
    "how many liters in a gallon"
    "convert 50 usd to eur"
    "convert 1 TB to GB"
"""

import re
import requests
from talents.base import BaseTalent


class UnitConverterTalent(BaseTalent):
    name = "unit_converter"
    description = "Convert between units of measurement and currencies"
    keywords = [
        "convert", "conversion", "how many", "how much is",
        "celsius", "fahrenheit", "miles", "kilometers",
        "pounds", "kilograms", "liters", "gallons",
        "inches", "centimeters", "feet", "meters",
        "exchange rate", "currency",
    ]
    priority = 39

    _EXCLUSIONS = [
        "remind", "timer", "email", "note", "weather", "hue",
        "light", "search", "news", "todo", "task", "pomodoro",
        "docker", "github", "regex", "json", "snippet",
        "stock", "crypto", "bitcoin",
    ]

    # Unit definitions: {alias: (canonical_name, category)}
    _UNIT_ALIASES = {}
    _CONVERSIONS = {}

    def __init__(self):
        super().__init__()
        self._build_conversion_tables()

    def get_config_schema(self) -> dict:
        return {}

    def can_handle(self, command: str) -> bool:
        cmd = command.lower()
        if any(ex in cmd for ex in self._EXCLUSIONS):
            return False
        return any(kw in cmd for kw in self.keywords)

    def execute(self, command: str, context: dict) -> dict:
        cmd = command.lower().strip()

        # Parse: "convert X UNIT to UNIT"
        # or: "how many UNIT in X UNIT"
        parsed = self._parse_conversion(cmd)
        if not parsed:
            return self._fail(
                "Please use format: 'convert 100 miles to kilometers'\n"
                "Supported: length, weight, temperature, volume, speed, data, time, currency.")

        value, from_unit, to_unit = parsed

        # Check if it's a currency conversion
        currencies = self._get_currency_codes()
        from_upper = from_unit.upper()
        to_upper = to_unit.upper()

        if from_upper in currencies and to_upper in currencies:
            return self._convert_currency(value, from_upper, to_upper)

        # Unit conversion
        return self._convert_unit(value, from_unit, to_unit)

    # ── Unit conversion ──────────────────────────────────────────

    def _convert_unit(self, value, from_unit, to_unit):
        from_canonical = self._UNIT_ALIASES.get(from_unit)
        to_canonical = self._UNIT_ALIASES.get(to_unit)

        if not from_canonical:
            return self._fail(f"Unknown unit: '{from_unit}'")
        if not to_canonical:
            return self._fail(f"Unknown unit: '{to_unit}'")

        from_name, from_cat = from_canonical
        to_name, to_cat = to_canonical

        if from_cat != to_cat:
            return self._fail(
                f"Cannot convert {from_name} ({from_cat}) to {to_name} ({to_cat}). "
                f"Units must be in the same category.")

        # Temperature is special
        if from_cat == "temperature":
            result = self._convert_temperature(value, from_name, to_name)
            if result is None:
                return self._fail(f"Cannot convert {from_name} to {to_name}.")
            return self._ok(f"{value:g} {from_name} = {result:g} {to_name}")

        # Standard conversion via base unit
        from_to_base = self._CONVERSIONS.get(from_name)
        to_to_base = self._CONVERSIONS.get(to_name)

        if from_to_base is None or to_to_base is None:
            return self._fail(f"Conversion not available for {from_name} to {to_name}.")

        # Convert: value * from_to_base / to_to_base
        base_value = value * from_to_base
        result = base_value / to_to_base

        # Format nicely
        if abs(result) >= 0.01:
            result_str = f"{result:,.4f}".rstrip('0').rstrip('.')
        else:
            result_str = f"{result:.8g}"

        return self._ok(f"{value:g} {from_name} = {result_str} {to_name}")

    def _convert_temperature(self, value, from_name, to_name):
        # Convert everything to Celsius first, then to target
        if from_name == "celsius":
            c = value
        elif from_name == "fahrenheit":
            c = (value - 32) * 5 / 9
        elif from_name == "kelvin":
            c = value - 273.15
        else:
            return None

        if to_name == "celsius":
            return round(c, 2)
        elif to_name == "fahrenheit":
            return round(c * 9 / 5 + 32, 2)
        elif to_name == "kelvin":
            return round(c + 273.15, 2)
        return None

    # ── Currency conversion ──────────────────────────────────────

    def _convert_currency(self, value, from_code, to_code):
        try:
            # Use free exchangerate.host or open.er-api.com
            url = f"https://open.er-api.com/v6/latest/{from_code}"
            resp = requests.get(url, timeout=10)
            if resp.status_code != 200:
                return self._fail("Currency API unavailable.")

            data = resp.json()
            rates = data.get("rates", {})
            rate = rates.get(to_code)

            if rate is None:
                return self._fail(f"Exchange rate not found for {from_code} to {to_code}.")

            result = value * rate
            return self._ok(
                f"{value:,.2f} {from_code} = {result:,.2f} {to_code}\n"
                f"  Rate: 1 {from_code} = {rate:.4f} {to_code}")

        except requests.RequestException as e:
            return self._fail(f"Currency API error: {e}")

    # ── Parsing ──────────────────────────────────────────────────

    def _parse_conversion(self, cmd):
        """Extract (value, from_unit, to_unit) from the command."""

        # "convert X UNIT to UNIT"
        match = re.search(
            r'convert\s+([\d,.]+)\s+(\w+)\s+(?:to|into|in)\s+(\w+)', cmd)
        if match:
            return float(match.group(1).replace(",", "")), match.group(2), match.group(3)

        # "X UNIT to UNIT"
        match = re.search(
            r'([\d,.]+)\s+(\w+)\s+(?:to|into|in)\s+(\w+)', cmd)
        if match:
            return float(match.group(1).replace(",", "")), match.group(2), match.group(3)

        # "how many UNIT in X UNIT"
        match = re.search(
            r'how\s+many\s+(\w+)\s+in\s+([\d,.]+)\s+(\w+)', cmd)
        if match:
            return float(match.group(2).replace(",", "")), match.group(3), match.group(1)

        # "how many UNIT in a UNIT"
        match = re.search(
            r'how\s+many\s+(\w+)\s+in\s+(?:a|an|one)\s+(\w+)', cmd)
        if match:
            return 1.0, match.group(2), match.group(1)

        return None

    def _get_currency_codes(self):
        return {
            "USD", "EUR", "GBP", "JPY", "CAD", "AUD", "CHF", "CNY",
            "INR", "BRL", "KRW", "MXN", "NZD", "SGD", "HKD", "NOK",
            "SEK", "DKK", "PLN", "ZAR", "RUB", "TRY", "THB", "IDR",
        }

    # ── Conversion tables ────────────────────────────────────────

    def _build_conversion_tables(self):
        """Build unit alias and conversion tables."""
        # Each entry: alias -> (canonical_name, category)
        # Conversion factors are relative to a base unit per category

        # Length (base: meter)
        length = {
            "meter": 1, "meters": 1, "m": 1,
            "kilometer": 1000, "kilometers": 1000, "km": 1000,
            "centimeter": 0.01, "centimeters": 0.01, "cm": 0.01,
            "millimeter": 0.001, "millimeters": 0.001, "mm": 0.001,
            "mile": 1609.344, "miles": 1609.344, "mi": 1609.344,
            "yard": 0.9144, "yards": 0.9144, "yd": 0.9144,
            "foot": 0.3048, "feet": 0.3048, "ft": 0.3048,
            "inch": 0.0254, "inches": 0.0254, "in": 0.0254,
            "nautical_mile": 1852, "nautical_miles": 1852, "nmi": 1852,
        }

        # Weight (base: kilogram)
        weight = {
            "kilogram": 1, "kilograms": 1, "kg": 1,
            "gram": 0.001, "grams": 0.001, "g": 0.001,
            "milligram": 0.000001, "milligrams": 0.000001, "mg": 0.000001,
            "pound": 0.453592, "pounds": 0.453592, "lb": 0.453592, "lbs": 0.453592,
            "ounce": 0.0283495, "ounces": 0.0283495, "oz": 0.0283495,
            "ton": 907.185, "tons": 907.185,
            "metric_ton": 1000, "tonne": 1000, "tonnes": 1000,
            "stone": 6.35029, "stones": 6.35029, "st": 6.35029,
        }

        # Volume (base: liter)
        volume = {
            "liter": 1, "liters": 1, "l": 1, "litre": 1, "litres": 1,
            "milliliter": 0.001, "milliliters": 0.001, "ml": 0.001,
            "gallon": 3.78541, "gallons": 3.78541, "gal": 3.78541,
            "quart": 0.946353, "quarts": 0.946353, "qt": 0.946353,
            "pint": 0.473176, "pints": 0.473176, "pt": 0.473176,
            "cup": 0.236588, "cups": 0.236588,
            "fluid_ounce": 0.0295735, "fluid_ounces": 0.0295735, "floz": 0.0295735,
            "tablespoon": 0.0147868, "tablespoons": 0.0147868, "tbsp": 0.0147868,
            "teaspoon": 0.00492892, "teaspoons": 0.00492892, "tsp": 0.00492892,
        }

        # Speed (base: m/s)
        speed = {
            "mps": 1, "m/s": 1,
            "kph": 0.277778, "km/h": 0.277778, "kmh": 0.277778,
            "mph": 0.44704,
            "knot": 0.514444, "knots": 0.514444, "kn": 0.514444,
        }

        # Data (base: byte)
        data = {
            "byte": 1, "bytes": 1, "b": 1,
            "kilobyte": 1024, "kilobytes": 1024, "kb": 1024,
            "megabyte": 1048576, "megabytes": 1048576, "mb": 1048576,
            "gigabyte": 1073741824, "gigabytes": 1073741824, "gb": 1073741824,
            "terabyte": 1099511627776, "terabytes": 1099511627776, "tb": 1099511627776,
        }

        # Time (base: second)
        time_units = {
            "second": 1, "seconds": 1, "sec": 1,
            "minute": 60, "minutes": 60, "min": 60,
            "hour": 3600, "hours": 3600, "hr": 3600,
            "day": 86400, "days": 86400,
            "week": 604800, "weeks": 604800,
            "month": 2592000, "months": 2592000,
            "year": 31536000, "years": 31536000,
        }

        # Temperature (special handling — no base unit multiplication)
        temp = {
            "celsius": None, "c": None,
            "fahrenheit": None, "f": None,
            "kelvin": None, "k": None,
        }

        categories = [
            ("length", length), ("weight", weight), ("volume", volume),
            ("speed", speed), ("data", data), ("time", time_units),
            ("temperature", temp),
        ]

        for cat_name, units in categories:
            for alias, factor in units.items():
                # For canonical name, use the longest alias that matches this factor
                # (simplification: the first entry for each factor is canonical)
                canonical = alias
                self._UNIT_ALIASES[alias] = (canonical, cat_name)
                if factor is not None:
                    self._CONVERSIONS[canonical] = factor

    # ── Helpers ──────────────────────────────────────────────────

    def _ok(self, msg):
        return {"success": True, "response": msg,
                "actions_taken": [{"action": "unit_converter"}], "spoken": False}

    def _fail(self, msg):
        return {"success": False, "response": msg,
                "actions_taken": [], "spoken": False}
