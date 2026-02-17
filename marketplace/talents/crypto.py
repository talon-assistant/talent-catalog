"""CryptoTalent — check cryptocurrency prices via the free CoinGecko API.

No API key required. Uses the public CoinGecko v3 API.

Examples:
    "bitcoin price"
    "check ethereum"
    "crypto price of solana"
    "how much is dogecoin"
    "top crypto prices"
"""

import re
import requests
from talents.base import BaseTalent


# Map common names/symbols to CoinGecko IDs
_COIN_ALIASES = {
    "bitcoin": "bitcoin", "btc": "bitcoin",
    "ethereum": "ethereum", "eth": "ethereum",
    "solana": "solana", "sol": "solana",
    "cardano": "cardano", "ada": "cardano",
    "dogecoin": "dogecoin", "doge": "dogecoin",
    "polkadot": "polkadot", "dot": "polkadot",
    "avalanche": "avalanche-2", "avax": "avalanche-2",
    "chainlink": "chainlink", "link": "chainlink",
    "polygon": "matic-network", "matic": "matic-network",
    "litecoin": "litecoin", "ltc": "litecoin",
    "xrp": "ripple", "ripple": "ripple",
    "bnb": "binancecoin", "binance": "binancecoin",
    "tron": "tron", "trx": "tron",
    "shiba": "shiba-inu", "shib": "shiba-inu",
}


class CryptoTalent(BaseTalent):
    name = "crypto"
    description = "Check cryptocurrency prices, market cap, and 24h changes"
    keywords = [
        "crypto", "cryptocurrency", "bitcoin", "btc", "ethereum", "eth",
        "coin price", "token price", "dogecoin", "solana",
    ]
    priority = 50

    _EXCLUSIONS = [
        "remind", "timer", "email", "note", "weather", "hue",
        "light", "search", "news", "todo", "task", "pomodoro",
        "docker", "github", "regex", "json", "snippet",
        "stock", "ticker", "shares", "nasdaq",
    ]

    _API_BASE = "https://api.coingecko.com/api/v3"

    def get_config_schema(self) -> dict:
        return {
            "fields": [
                {"key": "currency", "label": "Display Currency",
                 "type": "choice", "default": "usd",
                 "choices": ["usd", "eur", "gbp", "jpy", "cad", "aud"]},
                {"key": "watchlist", "label": "Watchlist (comma-separated coins)",
                 "type": "string", "default": ""},
            ]
        }

    def can_handle(self, command: str) -> bool:
        cmd = command.lower()
        if any(ex in cmd for ex in self._EXCLUSIONS):
            return False
        return any(kw in cmd for kw in self.keywords)

    def execute(self, command: str, context: dict) -> dict:
        cmd = command.lower().strip()
        currency = self._config.get("currency", "usd")

        # Top coins
        if any(p in cmd for p in ["top crypto", "top coin", "market overview",
                                   "crypto market", "crypto prices"]):
            return self._top_coins(currency)

        # Extract coin name
        coin_id = self._extract_coin(cmd)

        if not coin_id:
            # Check watchlist
            watchlist = self._config.get("watchlist", "")
            if watchlist:
                coins = [self._resolve_coin(c.strip()) for c in watchlist.split(",")]
                coins = [c for c in coins if c]
                if coins:
                    return self._multi_price(coins, currency)
            return self._fail(
                "Which cryptocurrency? Try 'bitcoin price' or 'check ethereum'.")

        return self._coin_price(coin_id, currency)

    # ── Single coin price ────────────────────────────────────────

    def _coin_price(self, coin_id, currency):
        try:
            url = f"{self._API_BASE}/coins/{coin_id}"
            params = {"localization": "false", "tickers": "false",
                      "community_data": "false", "developer_data": "false"}
            resp = requests.get(url, params=params, timeout=10)

            if resp.status_code == 429:
                return self._fail("CoinGecko rate limit reached. Try again in a minute.")
            if resp.status_code != 200:
                return self._fail(f"Coin not found: {coin_id}")

            data = resp.json()
            market = data.get("market_data", {})
            name = data.get("name", coin_id)
            symbol = data.get("symbol", "").upper()

            price = market.get("current_price", {}).get(currency, 0)
            change_24h = market.get("price_change_percentage_24h", 0)
            change_7d = market.get("price_change_percentage_7d", 0)
            market_cap = market.get("market_cap", {}).get(currency, 0)
            volume = market.get("total_volume", {}).get(currency, 0)
            high_24h = market.get("high_24h", {}).get(currency, 0)
            low_24h = market.get("low_24h", {}).get(currency, 0)
            ath = market.get("ath", {}).get(currency, 0)

            cur = currency.upper()
            arrow = "\u2b06\ufe0f" if change_24h >= 0 else "\u2b07\ufe0f"

            lines = [f"{name} ({symbol})"]
            lines.append(f"  Price: {self._fmt_price(price)} {cur}")
            lines.append(f"  24h Change: {arrow} {change_24h:+.2f}%")
            lines.append(f"  7d Change: {change_7d:+.2f}%")
            lines.append(f"  24h Range: {self._fmt_price(low_24h)} - {self._fmt_price(high_24h)}")

            if market_cap:
                lines.append(f"  Market Cap: {self._fmt_large(market_cap)} {cur}")
            if volume:
                lines.append(f"  24h Volume: {self._fmt_large(volume)} {cur}")
            if ath:
                lines.append(f"  All-Time High: {self._fmt_price(ath)} {cur}")

            return self._ok("\n".join(lines))

        except requests.RequestException as e:
            return self._fail(f"Network error: {e}")

    # ── Multiple coins ───────────────────────────────────────────

    def _multi_price(self, coin_ids, currency):
        try:
            ids_str = ",".join(coin_ids)
            url = f"{self._API_BASE}/simple/price"
            params = {
                "ids": ids_str,
                "vs_currencies": currency,
                "include_24hr_change": "true",
                "include_market_cap": "true",
            }
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code != 200:
                return self._fail("Failed to fetch crypto prices.")

            data = resp.json()
            cur = currency.upper()

            lines = [f"Crypto Prices ({cur}):\n"]
            for coin_id in coin_ids:
                coin_data = data.get(coin_id, {})
                price = coin_data.get(currency, 0)
                change = coin_data.get(f"{currency}_24h_change", 0)
                arrow = "\u2b06" if change and change >= 0 else "\u2b07"
                name = coin_id.replace("-", " ").title()
                lines.append(f"  {name}: {self._fmt_price(price)} {arrow} {change:+.1f}%")

            return self._ok("\n".join(lines))

        except requests.RequestException as e:
            return self._fail(f"Network error: {e}")

    # ── Top coins ────────────────────────────────────────────────

    def _top_coins(self, currency):
        try:
            url = f"{self._API_BASE}/coins/markets"
            params = {
                "vs_currency": currency,
                "order": "market_cap_desc",
                "per_page": 10,
                "page": 1,
            }
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code != 200:
                return self._fail("Failed to fetch top coins.")

            coins = resp.json()
            cur = currency.upper()

            lines = [f"Top 10 Cryptocurrencies ({cur}):\n"]
            lines.append(f"  {'#':<3} {'Name':<15} {'Price':>12} {'24h':>8} {'Mkt Cap':>12}")
            lines.append("  " + "-" * 54)

            for coin in coins:
                rank = coin.get("market_cap_rank", "?")
                name = coin.get("name", "?")[:14]
                price = coin.get("current_price", 0)
                change = coin.get("price_change_percentage_24h", 0) or 0
                mcap = coin.get("market_cap", 0)

                lines.append(
                    f"  {rank:<3} {name:<15} {self._fmt_price(price):>12} "
                    f"{change:>+7.1f}% {self._fmt_large(mcap):>12}")

            return self._ok("\n".join(lines))

        except requests.RequestException as e:
            return self._fail(f"Network error: {e}")

    # ── Helpers ──────────────────────────────────────────────────

    def _extract_coin(self, cmd):
        """Extract a CoinGecko coin ID from the command."""
        # Check known aliases
        for alias, coin_id in _COIN_ALIASES.items():
            if alias in cmd:
                return coin_id

        # Try to extract a coin name after price-related words
        match = re.search(r'(?:price of|check|how much is|price for)\s+(\w+)', cmd)
        if match:
            name = match.group(1).lower()
            return self._resolve_coin(name)

        return ""

    def _resolve_coin(self, name):
        name = name.lower().strip()
        if name in _COIN_ALIASES:
            return _COIN_ALIASES[name]
        # Try as-is (might be a CoinGecko ID already)
        return name if len(name) > 1 else ""

    def _fmt_price(self, price):
        if price >= 1:
            return f"${price:,.2f}"
        elif price >= 0.01:
            return f"${price:.4f}"
        else:
            return f"${price:.8f}"

    def _fmt_large(self, value):
        if value >= 1e12:
            return f"${value/1e12:.1f}T"
        elif value >= 1e9:
            return f"${value/1e9:.1f}B"
        elif value >= 1e6:
            return f"${value/1e6:.1f}M"
        else:
            return f"${value:,.0f}"

    def _ok(self, msg):
        return {"success": True, "response": msg,
                "actions_taken": [{"action": "crypto"}], "spoken": False}

    def _fail(self, msg):
        return {"success": False, "response": msg,
                "actions_taken": [], "spoken": False}
