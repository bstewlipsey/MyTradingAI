import yfinance as yf
import pandas as pd
import os
import asyncio
import websockets
import json
import alpaca_trade_api as tradeapi
from config import ALPACA_API_KEY, ALPACA_SECRET_KEY, LOOKBACK_PERIOD_HISTORY, BAR_GRANULARITY, BASE_URL

NEWS_JSON_PATH = os.path.join("data", "alpaca_realtime_news.json")

def get_historical_trade_data(symbol, period=LOOKBACK_PERIOD_HISTORY, save_json=False):
    """Fetches historical data using Alpaca API for intraday bars, or yfinance for stocks if Alpaca not available."""
    try:
        api = tradeapi.REST(ALPACA_API_KEY, ALPACA_SECRET_KEY, base_url=BASE_URL, api_version='v2')
        # Use Alpaca for both stocks and crypto if possible
        bars = api.get_bars(symbol, BAR_GRANULARITY, limit=None, start=None, end=None, adjustment=None, feed='iex')
        df = bars.df
        if not df.empty:
            df = df[df['symbol'] == symbol]
            df = df.copy()
            df.index = pd.to_datetime(df.index)
            df.sort_index(inplace=True)
            df.to_csv(f"data/{symbol}_history.csv")
            if save_json:
                json_path = f"data/{symbol}_history.json"
                df.reset_index(inplace=True)
                df_dict = df.to_dict(orient="records")
                with open(json_path, "w") as f:
                    json.dump(df_dict, f, indent=2, default=str)
            return df
        else:
            print(f"No intraday data found for {symbol} using Alpaca.")
            return pd.DataFrame()
    except Exception as e:
        print(f"Error fetching intraday data for {symbol} from Alpaca: {e}")
        # Fallback to yfinance (daily bars only)
        try:
            stock = yf.Ticker(symbol)
            data = stock.history(period=period)
            if not data.empty:
                print(f"Fetched {len(data)} rows for {symbol} over {period} (daily bars, fallback).")
                data.to_csv(f"data/{symbol}_history.csv")
                if save_json:
                    json_path = f"data/{symbol}_history.json"
                    data.reset_index(inplace=True)
                    data_dict = data.to_dict(orient="records")
                    with open(json_path, "w") as f:
                        json.dump(data_dict, f, indent=2, default=str)
                return data
            else:
                print(f"No data found for {symbol} over {period}.")
                return pd.DataFrame()
        except Exception as e2:
            print(f"Error fetching data for {symbol} from yfinance: {e2}")
            return pd.DataFrame()

class AlpacaNewsWebSocket:
    def __init__(self, url="wss://stream.data.alpaca.markets/v1beta1/news"):
        self.api_key = ALPACA_API_KEY
        self.secret_key = ALPACA_SECRET_KEY
        self.url = url
        self.news_buffer = []
        self.ws = None
        self.connected = False

    async def connect(self):
        async with websockets.connect(self.url) as websocket:
            self.ws = websocket
            await self.authenticate()
            await self.subscribe_news()
            self.connected = True
            await self.listen()

    async def authenticate(self):
        auth_msg = {
            "action": "auth",
            "key": self.api_key,
            "secret": self.secret_key
        }
        await self.ws.send(json.dumps(auth_msg))
        response = await self.ws.recv()
        print(f"Alpaca News WebSocket Auth Response: {response}")

    async def subscribe_news(self):
        sub_msg = {"action": "subscribe", "news": ["*"]}
        await self.ws.send(json.dumps(sub_msg))
        response = await self.ws.recv()
        print(f"Alpaca News WebSocket Subscribe Response: {response}")

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
            print(f"Error saving news to JSON: {e}")

    async def listen(self):
        print("Listening for real-time Alpaca news...")
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
                        self.news_buffer.append(news_item)
                        self.save_news_to_json(news_item)
                        print(f"[NEWS] {news_item['created_at']} {news_item['headline']}")
            except Exception as e:
                print(f"WebSocket error: {e}")
                break

    def get_latest_news(self, limit=10):
        return self.news_buffer[-limit:]

    
alpaca_news_ws = AlpacaNewsWebSocket()
def start_alpaca_news_ws_background(loop):
    """Starts the Alpaca news websocket in the background. Returns the task."""
    return loop.create_task(alpaca_news_ws.connect())

def get_latest_alpaca_news(limit=10):
    return alpaca_news_ws.get_latest_news(limit=limit)

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

if __name__ == "__main__":
    # Create a directory to save data
    os.makedirs("data", exist_ok=True)

    # Test with a few symbols
    symbols = ["BTC-USD"]  # Add more as needed

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