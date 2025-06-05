import pandas as pd
import pandas_ta as ta
from data_collector import get_historical_trade_data

def calculate_indicators(data):
    """Calculates common technical indicators using pandas_ta."""
    if data.empty:
        print("Error: DataFrame is empty. Cannot calculate indicators.")
        return data

    # Ensure 'Close' column exists and is numeric
    if 'Close' not in data.columns:
        print("Warning: 'Close' column not found for indicator calculation.")
        return data
    data['Close'] = pd.to_numeric(data['Close'], errors='coerce')
    data.dropna(subset=['Close'], inplace=True)
    if data['Close'].isnull().any() or len(data) < 5:
        print("Error: 'Close' column contains NaN values or not enough data after cleaning.")
        print(data['Close'].tail(10))
        return data

    # --- Robust index and data checks for pandas_ta compatibility ---
    # Ensure index is DatetimeIndex, monotonic, unique, and sorted
    if not isinstance(data.index, pd.DatetimeIndex):
        try:
            data.index = pd.to_datetime(data.index)
        except Exception as e:
            print(f"Index conversion to DatetimeIndex failed: {e}")
            return data
    if not data.index.is_monotonic_increasing:
        data = data.sort_index()
    if not data.index.is_unique:
        data = data[~data.index.duplicated(keep='first')]

    # Print debug info for index and Close column
    print(f"Index type: {type(data.index)} | Monotonic: {data.index.is_monotonic_increasing} | Unique: {data.index.is_unique}")
    print(f"Close dtype: {data['Close'].dtype} | NaNs: {data['Close'].isnull().sum()} | Rows: {len(data)}")

    # Add Moving Averages
    try:
        data['SMA_20'] = ta.sma(data['Close'], length=20)
    except Exception as e:
        print(f"SMA_20 calculation failed: {e}")
    try:
        data['SMA_50'] = ta.sma(data['Close'], length=50)
    except Exception as e:
        print(f"SMA_50 calculation failed: {e}")

    # Add Relative Strength Index (RSI)
    try:
        data['RSI'] = ta.rsi(data['Close'], length=14)
    except Exception as e:
        print(f"RSI calculation failed: {e}")

    # Add Moving Average Convergence Divergence (MACD)
    try:
        macd = ta.macd(data['Close'])
        if macd is not None and not macd.empty:
            data = pd.concat([data, macd], axis=1)
    except Exception as e:
        print(f"MACD calculation failed: {e}")

    # Add Bollinger Bands
    try:
        bbands = ta.bbands(data['Close'])
        if bbands is not None and not bbands.empty:
            data = pd.concat([data, bbands], axis=1)
    except Exception as e:
        print(f"Bollinger Bands calculation failed: {e}")

    print(f"Calculated indicators for {len(data)} rows.")
    return data

if __name__ == "__main__":
    # Example usage: Load historical data and calculate indicators
    # Assume 'data/AAPL_history.csv' exists from Step 2
    try:
        symbols = ["AAPL", "BTC-USD"]
        for symbol in symbols:
            trade_history = get_historical_trade_data(symbol)
            trade_history_with_indicators = calculate_indicators(trade_history)
            
            print(f"\nTrade history indicators for: {symbol}") 
            print(trade_history.head())  # Debug: show first few rows
            print(trade_history.dtypes)  # Debug: show column types
            print(trade_history_with_indicators.tail())
    
    except FileNotFoundError:
        print("Run data_collector.py first to generate history CSV files")
    except Exception as e:
        print(f"Error calculating indicators: {e}")