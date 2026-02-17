"""StockTalent — look up stock prices and market data via Yahoo Finance.

Uses yfinance for real-time and historical stock data.

Examples:
    "stock price of AAPL"
    "how is TSLA doing"
    "check MSFT stock"
    "stock info for GOOGL"
    "compare AAPL and MSFT"
"""

import re
from talents.base import BaseTalent

try:
    import yfinance as yf
    _HAS_YFINANCE = True
except ImportError:
    _HAS_YFINANCE = False


class StockTalent(BaseTalent):
    name = "stock"
    description = "Look up stock prices, ticker info, and basic market data"
    keywords = [
        "stock", "stock price", "ticker", "shares", "market",
        "nasdaq", "nyse", "s&p", "dow jones",
    ]
    priority = 50

    _EXCLUSIONS = [
        "remind", "timer", "email", "note", "weather", "hue",
        "light", "search", "news", "todo", "task", "pomodoro",
        "docker", "github", "regex", "json", "snippet",
        "crypto", "bitcoin", "ethereum",
    ]

    def get_config_schema(self) -> dict:
        return {
            "fields": [
                {"key": "default_tickers", "label": "Watchlist (comma-separated tickers)",
                 "type": "string", "default": ""},
            ]
        }

    def can_handle(self, command: str) -> bool:
        cmd = command.lower()
        if any(ex in cmd for ex in self._EXCLUSIONS):
            return False
        if any(kw in cmd for kw in self.keywords):
            return True
        # Also match uppercase ticker patterns like "AAPL", "TSLA"
        if re.search(r'\b[A-Z]{1,5}\b', command) and ("price" in cmd or "how is" in cmd or "check" in cmd):
            return True
        return False

    def execute(self, command: str, context: dict) -> dict:
        if not _HAS_YFINANCE:
            return self._fail("yfinance is not installed. Run: pip install yfinance")

        cmd = command.lower().strip()
        tickers = self._extract_tickers(command)

        if not tickers:
            # Check watchlist
            watchlist = self._config.get("default_tickers", "")
            if watchlist:
                tickers = [t.strip().upper() for t in watchlist.split(",") if t.strip()]
            if not tickers:
                return self._fail(
                    "Which stock? Include a ticker symbol like AAPL, TSLA, MSFT.")

        # Compare multiple
        if len(tickers) > 1:
            return self._compare_stocks(tickers)

        # Single stock
        ticker = tickers[0]

        # Detailed info requested
        if any(p in cmd for p in ["info", "detail", "about", "tell me about"]):
            return self._stock_info(ticker)

        # Default: price
        return self._stock_price(ticker)

    # ── Price ────────────────────────────────────────────────────

    def _stock_price(self, ticker):
        try:
            stock = yf.Ticker(ticker)
            info = stock.info

            name = info.get("shortName", ticker)
            price = info.get("currentPrice") or info.get("regularMarketPrice")
            prev_close = info.get("previousClose") or info.get("regularMarketPreviousClose")
            currency = info.get("currency", "USD")

            if price is None:
                return self._fail(f"Could not fetch price for {ticker}. Is the ticker correct?")

            change = ""
            if prev_close and price:
                diff = price - prev_close
                pct = (diff / prev_close) * 100
                arrow = "\u2b06\ufe0f" if diff >= 0 else "\u2b07\ufe0f"
                sign = "+" if diff >= 0 else ""
                change = f"  {arrow} {sign}{diff:.2f} ({sign}{pct:.2f}%)"

            mkt_cap = info.get("marketCap")
            cap_str = ""
            if mkt_cap:
                if mkt_cap >= 1e12:
                    cap_str = f"  Market Cap: ${mkt_cap/1e12:.2f}T"
                elif mkt_cap >= 1e9:
                    cap_str = f"  Market Cap: ${mkt_cap/1e9:.2f}B"
                elif mkt_cap >= 1e6:
                    cap_str = f"  Market Cap: ${mkt_cap/1e6:.2f}M"

            high = info.get("dayHigh", info.get("regularMarketDayHigh"))
            low = info.get("dayLow", info.get("regularMarketDayLow"))
            range_str = ""
            if high and low:
                range_str = f"  Day Range: ${low:.2f} - ${high:.2f}"

            lines = [f"{name} ({ticker})"]
            lines.append(f"  Price: ${price:.2f} {currency}{change}")
            if range_str:
                lines.append(range_str)
            if cap_str:
                lines.append(cap_str)

            volume = info.get("volume", info.get("regularMarketVolume"))
            if volume:
                lines.append(f"  Volume: {volume:,.0f}")

            return self._ok("\n".join(lines))

        except Exception as e:
            return self._fail(f"Error fetching {ticker}: {e}")

    # ── Info ─────────────────────────────────────────────────────

    def _stock_info(self, ticker):
        try:
            stock = yf.Ticker(ticker)
            info = stock.info

            name = info.get("shortName", ticker)
            lines = [f"{name} ({ticker})\n"]

            fields = [
                ("Sector", "sector"),
                ("Industry", "industry"),
                ("Country", "country"),
                ("Employees", "fullTimeEmployees"),
                ("Website", "website"),
                ("P/E Ratio", "trailingPE"),
                ("EPS", "trailingEps"),
                ("Dividend Yield", "dividendYield"),
                ("52-Week High", "fiftyTwoWeekHigh"),
                ("52-Week Low", "fiftyTwoWeekLow"),
            ]

            for label, key in fields:
                val = info.get(key)
                if val is not None:
                    if key == "dividendYield" and val:
                        val = f"{val * 100:.2f}%"
                    elif key == "fullTimeEmployees":
                        val = f"{val:,}"
                    elif isinstance(val, float):
                        val = f"${val:.2f}" if "High" in label or "Low" in label else f"{val:.2f}"
                    lines.append(f"  {label}: {val}")

            summary = info.get("longBusinessSummary", "")
            if summary:
                lines.append(f"\n{summary[:200]}...")

            return self._ok("\n".join(lines))

        except Exception as e:
            return self._fail(f"Error fetching info for {ticker}: {e}")

    # ── Compare ──────────────────────────────────────────────────

    def _compare_stocks(self, tickers):
        lines = ["Stock Comparison:\n"]
        lines.append(f"  {'Ticker':<8} {'Price':>10} {'Change':>10} {'Mkt Cap':>12}")
        lines.append("  " + "-" * 44)

        for ticker in tickers[:5]:
            try:
                stock = yf.Ticker(ticker)
                info = stock.info
                price = info.get("currentPrice") or info.get("regularMarketPrice", 0)
                prev = info.get("previousClose") or info.get("regularMarketPreviousClose", 0)
                cap = info.get("marketCap", 0)

                if price and prev:
                    pct = ((price - prev) / prev) * 100
                    change_str = f"{pct:+.2f}%"
                else:
                    change_str = "N/A"

                if cap >= 1e12:
                    cap_str = f"${cap/1e12:.1f}T"
                elif cap >= 1e9:
                    cap_str = f"${cap/1e9:.1f}B"
                elif cap >= 1e6:
                    cap_str = f"${cap/1e6:.1f}M"
                else:
                    cap_str = "N/A"

                price_str = f"${price:.2f}" if price else "N/A"
                lines.append(f"  {ticker:<8} {price_str:>10} {change_str:>10} {cap_str:>12}")

            except Exception:
                lines.append(f"  {ticker:<8} {'Error':>10}")

        return self._ok("\n".join(lines))

    # ── Helpers ──────────────────────────────────────────────────

    def _extract_tickers(self, command):
        """Extract stock ticker symbols from the command."""
        # Find uppercase 1-5 letter words that look like tickers
        candidates = re.findall(r'\b([A-Z]{1,5})\b', command)
        # Filter out common words
        noise = {"I", "A", "AND", "OR", "THE", "FOR", "OF", "IN", "IS",
                 "IT", "TO", "MY", "HOW", "VS", "NYSE", "NASDAQ", "SP"}
        tickers = [t for t in candidates if t not in noise]
        return tickers[:5]

    def _ok(self, msg):
        return {"success": True, "response": msg,
                "actions_taken": [{"action": "stock"}], "spoken": False}

    def _fail(self, msg):
        return {"success": False, "response": msg,
                "actions_taken": [], "spoken": False}
