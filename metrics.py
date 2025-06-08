import warnings
warnings.filterwarnings("ignore", category=FutureWarning, module="pandas_ta")

import pandas as pd
import pandas_ta as ta
from data_collector import get_historical_trade_data
import os

def calculate_indicators(data):
    """Calculates common technical indicators using pandas_ta."""
    if data.empty:
        print("Error: DataFrame is empty. Cannot calculate indicators.")
        return data

    # Standardize column names to title case for consistency
    data.columns = [col.title() for col in data.columns]

    # Ensure required columns exist
    required_cols = ['Close', 'High', 'Low', 'Volume']
    missing_cols = [col for col in required_cols if col not in data.columns]
    if missing_cols:
        print(f"Error: Missing required columns for indicator calculation: {missing_cols}")
        return data

    # Ensure 'Close' column is numeric
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
        if data['Close'].isnull().any():
            raise ValueError("MACD calculation failed: 'Close' column contains missing values. Please check your data source.")
        macd = ta.macd(data['Close'])
        if macd is None or macd.isnull().any().any():
            raise ValueError("MACD calculation failed: pandas_ta returned None or NaN values. This indicates a bug or insufficient data.")
        data = pd.concat([data, macd], axis=1)
    except Exception as e:
        print(e)

    # Add Bollinger Bands
    try:
        bbands = ta.bbands(data['Close'])
        if bbands is not None and not bbands.empty:
            data = pd.concat([data, bbands], axis=1)
    except Exception as e:
        print(f"Bollinger Bands calculation failed: {e}")

    # Add Stochastic Oscillator
    try:
        stoch = ta.stoch(data['High'], data['Low'], data['Close'])
        if stoch is not None and not stoch.empty:
            data = pd.concat([data, stoch], axis=1)
    except Exception as e:
        print(f"Stochastic Oscillator calculation failed: {e}")

    # Add Average True Range (ATR)
    try:
        data['ATR'] = ta.atr(data['High'], data['Low'], data['Close'], length=14)
    except Exception as e:
        print(f"ATR calculation failed: {e}")

    # Add Commodity Channel Index (CCI)
    try:
        data['CCI'] = ta.cci(data['High'], data['Low'], data['Close'], length=20)
    except Exception as e:
        print(f"CCI calculation failed: {e}")

    # Add Williams %R
    try:
        data['WILLR'] = ta.willr(data['High'], data['Low'], data['Close'], length=14)
    except Exception as e:
        print(f"Williams %R calculation failed: {e}")

    # Add Money Flow Index (MFI)
    try:
        mfi = ta.mfi(data['High'], data['Low'], data['Close'], data['Volume'], length=14)
        if 'MFI' in data.columns:
            data = data.drop(columns=['MFI'])
        if mfi is not None:
            mfi = pd.Series(mfi, dtype=float, index=data.index)
            if mfi.isnull().any():
                mfi = mfi.interpolate(method='linear', limit_direction='both')
            if mfi.isnull().any():
                raise ValueError("MFI calculation failed: pandas_ta returned None or NaN values even after interpolation. This indicates a bug or insufficient data.")
            data['MFI'] = mfi
    except Exception as e:
        print(e)

    # Add Rate of Change (ROC)
    try:
        data['ROC'] = ta.roc(data['Close'], length=10)
    except Exception as e:
        print(f"ROC calculation failed: {e}")

    # Add Parabolic SAR
    try:
        data['PSAR'] = ta.psar(data['High'], data['Low'], data['Close'])['PSARl_0.02_0.2']
    except Exception as e:
        print(f"Parabolic SAR calculation failed: {e}")

    # Add On-Balance Volume (OBV)
    try:
        data['OBV'] = ta.obv(data['Close'], data['Volume'])
    except Exception as e:
        print(f"OBV calculation failed: {e}")

    # Add Chaikin Money Flow (CMF)
    try:
        data['CMF'] = ta.cmf(data['High'], data['Low'], data['Close'], data['Volume'], length=20)
    except Exception as e:
        print(f"CMF calculation failed: {e}")

    # Add Ease of Movement (EOM)
    try:
        eom = ta.eom(data['High'], data['Low'], data['Close'], data['Volume'])
        if eom is not None and not eom.empty:
            data = pd.concat([data, eom], axis=1)
    except Exception as e:
        print(f"EOM calculation failed: {e}")

    # Add Accumulation/Distribution Line (ADL)
    try:
        data['ADL'] = ta.ad(data['High'], data['Low'], data['Close'], data['Volume'])
    except Exception as e:
        print(f"ADL calculation failed: {e}")

    # Add Ultimate Oscillator (UO)
    try:
        data['UO'] = ta.uo(data['High'], data['Low'], data['Close'], length=7)
    except Exception as e:
        print(f"Ultimate Oscillator calculation failed: {e}")

    print(f"Calculated additional indicators for {len(data)} rows.")
    return data

def safe_symbol(symbol):
    """Convert any symbol to a safe filename format (slashes to dashes)."""
    return symbol.replace("/", "-")

if __name__ == "__main__":
    # Example usage: Load historical data and calculate indicators
    # Load extra data to ensure all indicators have enough lookback
    try:
        symbols = ["AAPL", "BTC/USD", "BTC-USD"]
        for symbol in symbols:
            file_symbol = safe_symbol(symbol)
            input_path = f"data/{file_symbol}_history.csv"
            output_path = f"data/{file_symbol}_processed_history.csv"
            # Load more data: at least 100 rows for robust indicator calculation
            if os.path.exists(input_path):
                try:
                    trade_history = pd.read_csv(input_path, index_col="Date", parse_dates=True)
                except Exception as e:
                    print(f"CSV read with index_col='Date' failed: {e}")
                    trade_history = pd.read_csv(input_path)
                    print(f"Columns after fallback read: {trade_history.columns}")
                    # Handle 'Date', 'Timestamp', or 'timestamp' as possible date columns
                    date_col = None
                    for candidate in ['Date', 'Timestamp', 'timestamp']:
                        if candidate in trade_history.columns:
                            date_col = candidate
                            break
                    if date_col:
                        trade_history[date_col] = pd.to_datetime(trade_history[date_col])
                        trade_history.set_index(date_col, inplace=True)
                        trade_history.index.name = 'Date'  # Standardize index name
                    else:
                        print("Error: No date column ('Date', 'Timestamp', 'timestamp') found after fallback read. Columns are:", trade_history.columns)
                        raise
                print(f"Columns after reading {input_path}: {trade_history.columns}")
                # If less than 100 rows, try to fetch more (if possible)
                if len(trade_history) < 100:
                    print(f"Warning: Only {len(trade_history)} rows found for {symbol}. Attempting to fetch more data.")
                    # Fetch more data and append to existing
                    more_history = get_historical_trade_data(symbol, min_rows=100)
                    if more_history is not None and len(more_history) > len(trade_history):
                        trade_history = more_history
            else:
                trade_history = get_historical_trade_data(symbol, min_rows=100)
            trade_history_with_indicators = calculate_indicators(trade_history)
            # Drop all rows with any NaN after all indicators are calculated
            trade_history_with_indicators = trade_history_with_indicators.dropna()
            if len(trade_history_with_indicators) < 100:
                print(f"Warning: Only {len(trade_history_with_indicators)} valid rows after indicator calculation for {symbol}.")
            trade_history_with_indicators.to_csv(output_path)
            print(f"\nTrade history indicators for: {symbol}")
            print(trade_history.head())  # Debug: show first few rows
            print(trade_history.dtypes)  # Debug: show column types
            print(trade_history_with_indicators.tail())
    except FileNotFoundError:
        print("Run data_collector.py first to generate history CSV files")
    except Exception as e:
        print(f"Error calculating indicators: {e}")