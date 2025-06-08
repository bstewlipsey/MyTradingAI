import yfinance as yf
import pandas as pd
import os
import sys
import asyncio
import websockets
import json

from alpaca.trading.client import TradingClient
from config import PAPER_TRADING, ALPACA_API_KEY, ALPACA_SECRET_KEY, LOOKBACK_PERIOD_HISTORY, BAR_GRANULARITY, BASE_URL

NEWS_JSON_PATH = os.path.join("data", "alpaca_realtime_news.json")
PORTFOLIO_PATH = os.path.join("data", "portfolio.json")

def safe_symbol(symbol):
    """Convert any symbol to a safe filename format (slashes to dashes)."""
    return symbol.replace("/", "-")

def get_historical_trade_data(symbol, period=LOOKBACK_PERIOD_HISTORY, save_json=False, min_rows=None):
    """Fetches historical data using Alpaca API for intraday bars, or yfinance for stocks if Alpaca not available. Ensures at least min_rows of real data if specified."""
    try:
        api = tradeapi.REST(ALPACA_API_KEY, ALPACA_SECRET_KEY, base_url=BASE_URL, api_version='v2')
        is_crypto = "/" in symbol or "-" in symbol
        alpaca_symbol = symbol.replace("-", "/").upper()
        file_symbol = safe_symbol(alpaca_symbol)
        # Try to fetch enough bars for min_rows, if specified
        bars = None
        df = pd.DataFrame()
        if is_crypto:
            # For crypto, Alpaca supports up to 10000 bars per call
            limit = min_rows if min_rows is not None else None
            if limit is not None and limit < 10000:
                bars = api.get_crypto_bars(alpaca_symbol, BAR_GRANULARITY, limit=limit)
            else:
                bars = api.get_crypto_bars(alpaca_symbol, BAR_GRANULARITY, limit=10000)
            df = bars.df
            while min_rows is not None and len(df) < min_rows:
                # Try to fetch more by extending the time window backwards
                earliest = df.index.min() if not df.empty else None
                if earliest is None:
                    break
                # Subtract more days to get more data
                new_bars = api.get_crypto_bars(
                    alpaca_symbol, BAR_GRANULARITY, limit=10000, end=earliest
                )
                new_df = new_bars.df
                if new_df.empty:
                    break
                df = pd.concat([new_df, df]).drop_duplicates()
        else:
            # For stocks, yfinance fallback is more robust for history
            # Alpaca get_bars has limited history for free accounts
            try:
                bars = api.get_bars(symbol, BAR_GRANULARITY, limit=min_rows if min_rows is not None else None)
                df = bars.df
            except Exception:
                df = pd.DataFrame()
        if df.empty or (min_rows is not None and len(df) < min_rows):
            # Fallback to yfinance for stocks or if not enough data
            try:
                yf_periods = ["1y", "6mo", "3mo", "1mo", "14d", "7d"]
                for yf_period in yf_periods:
                    stock = yf.Ticker(symbol)
                    data = stock.history(period=yf_period)
                    if not data.empty and (min_rows is None or len(data) >= min_rows):
                        df = data
                        break
                # If still not enough, try to fetch max available
                if (min_rows is not None and len(df) < min_rows) or df.empty:
                    stock = yf.Ticker(symbol)
                    data = stock.history(period="max")
                    if not data.empty:
                        df = data
            except Exception as e2:
                print(f"Error fetching data for {symbol} from yfinance: {e2}")
                return pd.DataFrame()
        if not df.empty:
            # Normalize symbol column for crypto (Alpaca returns 'symbol' as 'BTC/USD')
            df['symbol'] = alpaca_symbol
            df = df.copy()
            df.index = pd.to_datetime(df.index)
            df.sort_index(inplace=True)
            if 'close' in df.columns and 'Close' not in df.columns:
                df.rename(columns={'close': 'Close'}, inplace=True)
            if 'Close' not in df.columns:
                print("Warning: 'Close' column not found for indicator calculation.")
            # Always reset index so 'Date' is a column for CSV, regardless of original index name (including 'timestamp')
            df_reset = df.reset_index()
            df_reset.rename(columns={df_reset.columns[0]: 'Date'}, inplace=True)
            output_csv = os.path.join("data", f"{file_symbol}_history.csv")
            os.makedirs("data", exist_ok=True)
            df_reset.to_csv(output_csv, index=False, header=True)
            if save_json:
                json_path = os.path.join("data", f"{file_symbol}_history.json")
                df_reset_dict = df_reset.to_dict(orient="records")
                with open(json_path, "w") as f:
                    json.dump(df_reset_dict, f, indent=2, default=str)
            # Only return the last min_rows rows if more were fetched
            if min_rows is not None and len(df) > min_rows:
                df = df.iloc[-min_rows:]
            return df
        else:
            print(f"No intraday data found for {symbol} using Alpaca or yfinance.")
            return pd.DataFrame()
    except Exception as e:
        print(f"Error fetching intraday data for {symbol} from Alpaca: {e}")
        return pd.DataFrame()

class AlpacaNewsWebSocket:
    def __init__(self, url="wss://stream.data.alpaca.markets/v1beta1/news"):
        self.api_key = ALPACA_API_KEY
        self.secret_key = ALPACA_SECRET_KEY
        self.url = url
        self.news_buffer = []
        self.ws = None
        self.connected = False
        self.loop = asyncio.get_event_loop() 
    
    
    #  [BL] Step 1.1 Start News Collector    
    
    def start_alpaca_news_ws_background(self):
        """Starts the Alpaca news websocket in the background. Returns the task."""
        return loop.create_task(self.connect()) # [BL] Step 1.1 Connect to Alpaca News WebSocket


    # [BL] Step 1.1 Connect to Alpaca News WebSocket  
    async def connect(self):
        async with websockets.connect(self.url) as websocket:
            self.ws = websocket
            await self.authenticate() #  [BL] Step 1.2 Authenticate   
            await self.subscribe_news() #  [BL] Step 1.3 Subscribe to News   
            self.connected = True
            await self.listen() #  [BL] Step 1.4 Listen loop for News

    #  [BL] Step 1.2 Authenticate   
    async def authenticate(self):
        auth_msg = {
            "action": "auth",
            "key": self.api_key,
            "secret": self.secret_key
        }

        await self.ws.send(json.dumps(auth_msg))
        response = await self.ws.recv()
        print(f"[ALPACA_NEWS] Alpaca News WebSocket Auth Response: {response}")

    #  [BL] Step 1.3 Subscribe to News
    async def subscribe_news(self):
        sub_msg = {"action": "subscribe", "news": ["*"]}

        await self.ws.send(json.dumps(sub_msg))
        response = await self.ws.recv()
        print(f"[ALPACA_NEWS]Alpaca News WebSocket Subscribe Response: {response}")

    #  [BL] Step 1.4.1 save to JSON
    def save_news_to_json(self, news_item):
        """Append a news item to the persistent JSON file."""
        try:
            if not os.path.exists(NEWS_JSON_PATH):
                with open(NEWS_JSON_PATH, "w") as f:
                    json.dump([], f)

            with open(NEWS_JSON_PATH, "r+") as f:
                try:
                    news_list = json.load(f)

                except json.JSONDecodeError:
                    news_list = []

                news_list.append(news_item)
                f.seek(0)
                json.dump(news_list, f, indent=2)
                f.truncate()

        except Exception as e:
            print(f"[ALPACA_NEWS] Error saving news to JSON: {e}")

    #  [BL] Step 1.4 Listen loop for News
    async def listen(self):
        print("[ALPACA_NEWS] Listening for real-time Alpaca news...")

        while True:
            try:
                message = await self.ws.recv()
                data = json.loads(message)

                for item in data:
                    if item.get("T") == "n":
                        news_item = {
                            "headline": item.get("headline"),
                            "summary": item.get("summary"),
                            "created_at": item.get("created_at"),
                            "symbols": item.get("symbols", []),
                            "id": item.get("id")
                        }

                        #  [BL] Step 1.4.1 save to buffer and JSON
                        self.news_buffer.append(news_item)
                        self.save_news_to_json(news_item)

                        print(f"[ALPACA_NEWS] {news_item['created_at']} {news_item['headline']}")
            
            except Exception as e:
                print(f"[ALPACA_NEWS]WebSocket error: {e}")
                break

    def get_latest_news(self, limit=10):
        return self.news_buffer[-limit:]

def load_news_from_json(limit=10):
    try:
        if not os.path.exists(NEWS_JSON_PATH):
            print(f"No news JSON file found at {NEWS_JSON_PATH}. Returning empty list.")
            return []
        with open(NEWS_JSON_PATH, "r") as f:
            news_list = json.load(f)
            return news_list[-limit:]
    except Exception as e:
        print(f"Error loading news from JSON: {e}")
        return []

# [BL] Step 2 Start Alpaca
class AlpacaPortfolio:
    def __init__(self, api_key=ALPACA_API_KEY, secret_key=ALPACA_SECRET_KEY, paper_trading=paper):
        self.alpaca = TradingClient(api_key, secret_key, paper=paper_trading)
        self.portfolio = self.get_current_portfolio() 

        # [BL] Step 2.0 initialize running portfolio
        save_portfolio_state({
            "last_updated": pd.Timestamp.now().isoformat(),
            "cash": self.alpaca.get_account().cash,
            "portfolio_value": self.alpaca.get_account().portfolio_value,
            "buying_power": self.alpaca.get_account().buying_power,
            "positions": self.portfolio,

            })


    # [BL] Step 2.1 get current portfolio and update json
    def get_current_portfolio(self):
        try:
            positions = self.alpaca.get_all_positions()
            portfolio = {
                pos.symbol: {
                    'qty': pos.qty,
                    'avg_entry_price': pos.avg_entry_price,
                    'side': pos.side,
                    'market_value': pos.market_value,
                    'cost_basis': pos.cost_basis,
                    'unrealized_pl': pos.unrealized_pl,
                    'unrealized_plpc': pos.unrealized_plpc,
                    'unrealized_intraday_pl': pos.unrealized_intraday_pl,
                    'unrealized_intraday_plpc': pos.unrealized_intraday_plpc,
                    'current_price': pos.current_price,
                    'lastday_price': pos.lastday_price,
                    'change_today': pos.change_today,
                    'qty_available': getattr(pos, 'qty_available', None),
                    'asset_class': pos.asset_class,
                    'exchange': pos.exchange,
                    'asset_marginable': getattr(pos, 'asset_marginable', None),
                    'asset_id': pos.asset_id
                }
                for pos in positions
            }
            return portfolio
        except Exception as e:
            print(f"[AlpacaPortfolio (get_current_portfolio)] Error fetching current portfolio: {e}")
            sys.exit(1)

def save_portfolio_state(portfolio):
    """Save the portfolio dictionary to portfolio_state.json."""
    os.makedirs(os.path.dirname(PORTFOLIO_PATH), exist_ok=True)
    with open(PORTFOLIO_PATH, "w") as f:
        json.dump(portfolio, f, indent=2)

def test_fetch_btcusd_intraday():
    from alpaca_trade_api.rest import REST, TimeFrame
    import os
    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")
    base_url = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
    api = REST(api_key, secret_key, base_url)
    try:
        # Use get_crypto_bars for crypto symbols
        bars = api.get_crypto_bars("BTC/USD", TimeFrame.Minute, limit=1)
        print("Bars fetched for BTC/USD:", bars)
    except Exception as e:
        print("Error fetching BTC/USD intraday bars:", e)

if __name__ == "__main__":
    # Create a directory to save data
    os.makedirs("data", exist_ok=True)

    # Test with a few symbols
    symbols = ["BTC/USD"]  # Use slash format for Alpaca

    for symbol in symbols:
        get_historical_trade_data(symbol, period="3mo") # Fetch 3 months of data
    print(f"Historical trade data collection complete for {symbols}.")

    # Start Alpaca News WebSocket in the background and keep running
    loop = asyncio.get_event_loop()
    news_task = start_alpaca_news_ws_background(loop)
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        print("\nShutting down Alpaca News WebSocket...")
        news_task.cancel()
        try:
            loop.run_until_complete(news_task)
        except:
            pass
        loop.close()

    test_fetch_btcusd_intraday()