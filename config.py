import os
from dotenv import load_dotenv

load_dotenv() # This loads variables from .env

ALPACA_API_KEY = os.getenv("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
NEWS_API_KEY = os.getenv("NEWS_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# --- User Configuration ---
TRADING_SYMBOLS = ["NKE", "PFE", "NVDA", "TSLA", "META", "BTC-USD", "ETH-USD", "AMZN", "AAPL", "GOOGL"]
CYCLE_INTERVAL_SECONDS = 60 * 30 # Run every 30 minutes
LOOKBACK_PERIOD_HISTORY = "60d" # Max 60 days of history for indicators etc. (quota friendly)
NEWS_QUERY_LIMIT_PER_SYMBOL = 3 # Max 3 relevant news articles for LLM per symbol
NEWS_QUERY_GLOBAL_LIMIT = 5 # Max 5 general market news articles
LLM_REFLECTION_INTERVAL_CYCLES = 7 # Reflect every 7 cycles (e.g., once a week)
NEWS_FETCH_INTERVAL_CYCLES = 6  # Fetch news every 3 hours (6 cycles of 30 min)

RISK_SETTINGS = {
    "max_risk_per_trade_percent": 0.05,  # 5% of portfolio value per trade
    "min_sentiment_for_buy": 40,         # LLM sentiment > 40 to consider buying
    "min_sentiment_for_sell": -40,       # LLM sentiment < -40 to consider selling
    "max_position_per_asset_percent": 0.05, # Max 5% of portfolio in any single asset
    "min_sentiment_for_size_increase": 50,  # Sentiment needs to be above 50 to boost size
    "sentiment_sizing_factor": 0.005,       # Each point above min_sentiment_for_size_increase adds 0.005% of risk_per_trade_percent
    "atr_stop_multiplier": 2.0              # How many ATRs away to place a stop loss (if not explicit)
}

SIMILARITY_TOLERANCE = 0.10 # 10% tolerance for numerical indicators to be considered "similar"
MAX_SIMILAR_RECORDS = 5 # Max number of similar past experiences to consider
