import os
from dotenv import load_dotenv

load_dotenv() # This loads variables from .env

ALPACA_API_KEY = os.getenv("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
NEWS_API_KEY = os.getenv("NEWS_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

PAPER_TRADING = True  # Set to False for live trading

# --- User Configuration ---
TRADING_SYMBOLS = ["NKE", "PFE", "NVDA", "TSLA", "META", "BTC/USD", "ETH/USD", "AMZN", "AAPL", "GOOGL"]
CYCLE_INTERVAL_SECONDS = 60 * 30  # Run every 30 minutes (user preference)
LOOKBACK_PERIOD_HISTORY = "14D" # Use 14 days of history for 30-min cycles (enough for indicators)
BAR_GRANULARITY = '30Min'  # 30-minute bars for intraday trading
NEWS_QUERY_LIMIT_PER_SYMBOL = 3 # Max 3 relevant news articles for LLM per symbol
LLM_REFLECTION_INTERVAL_CYCLES = 6 # Reflect every 6 cycles 
NEWS_FETCH_INTERVAL_CYCLES = 1  # Fetch/process news every cycle (30 min)

RISK_SETTINGS = {
    "max_risk_per_trade_percent": 0.05,  # 5% of portfolio value per trade
    "min_sentiment_for_buy": 40,         # LLM sentiment > 40 to consider buying
    "min_sentiment_for_sell": -40,       # LLM sentiment < -40 to consider selling
    "max_position_per_asset_percent": 0.05, # Max 5% of portfolio in any single asset
    "min_sentiment_for_size_increase": 50,  # Sentiment needs to be above 50 to boost size
    "sentiment_sizing_factor": 0.005,       # Each point above min_sentiment_for_size_increase adds 0.005% of risk_per_trade_percent
    "atr_stop_multiplier": 2.0,             # How many ATRs away to place a stop loss (if not explicit)
    "fallback_size_if_no_risk_defined": 1    # Fallback trade size if no stop loss or ATR is provided
}

# --- Risk Management Variables (centralized for LLM and code) ---
RISK_MANAGEMENT_VARS = {
    'max_risk_per_trade_percent': {'range': (0.01, 0.10), 'use_in_llm': True},
    'min_sentiment_for_buy': {'range': (0, 100), 'use_in_llm': True},
    'min_sentiment_for_sell': {'range': (-100, 0), 'use_in_llm': True},
    'atr_stop_multiplier': {'range': (1.0, 5.0), 'use_in_llm': True},
    'fallback_size_if_no_risk_defined': {'range': (0, 10), 'use_in_llm': True},
    'max_position_per_asset_percent': {'range': (0.01, 0.20), 'use_in_llm': False},
    'min_sentiment_for_size_increase': {'range': (0, 100), 'use_in_llm': False},
    'sentiment_sizing_factor': {'range': (0.001, 0.01), 'use_in_llm': False}
}

SIMILARITY_TOLERANCE = 0.10 # 10% tolerance for numerical indicators to be considered "similar"
MAX_SIMILAR_RECORDS = 5 # Max number of similar past experiences to consider

# LLM prompt template for all LLM-based analysis (single source of truth)
TRADING_GOAL_DESCRIPTION = "The bot's weekly performance goal is to achieve the highest possible Sharpe Ratio, consistently above 1.5, while strictly adhering to a maximum weekly drawdown of 15% and ensuring a positive overall profit factor above 1.2 across all trades."

CYCLE_INTERVAL_SECONDS = 1800  # Example: 30 minutes
LLM_PROMPT_TEMPLATE = (
    f"{TRADING_GOAL_DESCRIPTION}\n\n"
    f"The current trading cycle is {CYCLE_INTERVAL_SECONDS // 60} minutes.\n\n"
    "You are an expert financial analyst. Analyze the following information for {symbol}:\n\n"
    "Current Price: ${current_price}\n\n"
    "Recent Price History & Technical Indicators (last few days/weeks, simplified):\n{history_str}\n\n"
    "Recent News Headlines (from real-time Alpaca WebSocket, most relevant to this cycle):\n{news_str}\n\n"
    "Past Trading Performance/Reflections (my AI's previous actions/outcomes for this asset):\n{past_trades_summary}\n\n"
    "---\n"
    "You have access to the following technical indicators: SMA_20, RSI, MACD, Bollinger Bands, OBV, ATR, and others. "
    "Use them in your analysis and explain how they influence your recommendation. If news headlines are present, consider their immediate impact for this cycle.\n\n"
    "Based on this data, provide your response in the following strict JSON format (do not include any explanation, ```json, or text outside the JSON):\n"
    "{\n  \"sentiment\": <integer from -100 to 100>,\n  \"action\": \"BUY\" | \"SELL\" | \"HOLD\",\n  \"reasoning\": <string>,\n  \"risks\": <string>\n}\n"
)