import pandas as pd
import json
import os
import datetime
from portfolio_manager import load_experience_log # Import the new function

def get_market_state_snapshot(history_df, symbol):
    """
    Creates a snapshot of the current market state using key indicators.
    This is what we'll use to compare for 'similarity'.
    """
    if history_df.empty:
        return {}

    # Ensure indicators are calculated
    # Assuming history_df already has indicators from the 'indicators.py' step
    # If not, you'd call calculate_indicators(history_df) here.

    latest_data = history_df.iloc[-1] # Get the very last row (most recent data)

    # Extract key indicators. You can customize which ones are most relevant.
    # For simplicity, we'll use RSI and MACD signal.
    # You might also want to include recent price change (e.g., 1-day, 5-day % change)
    
    # Check if MACD columns exist before accessing
    macd_line = latest_data.get('MACD')
    signal_line = latest_data.get('MACD_Signal')
    
    macd_signal = "neutral"
    if macd_line is not None and signal_line is not None:
        if macd_line > signal_line and history_df['MACD'].iloc[-2] <= history_df['MACD_Signal'].iloc[-2]:
            macd_signal = "bullish_cross" # MACD line just crossed above signal line
        elif macd_line < signal_line and history_df['MACD'].iloc[-2] >= history_df['MACD_Signal'].iloc[-2]:
            macd_signal = "bearish_cross" # MACD line just crossed below signal line
        elif macd_line > signal_line:
            macd_signal = "bullish"
        elif macd_line < signal_line:
            macd_signal = "bearish"

    # Calculate recent price change
    if len(history_df) >= 5:
        price_change_5d = (latest_data['Close'] - history_df['Close'].iloc[-5]) / history_df['Close'].iloc[-5]
    else:
        price_change_5d = 0.0

    snapshot = {
        "symbol": symbol,
        "current_price": latest_data['Close'],
        "RSI": latest_data.get('RSI'),
        "MACD_signal": macd_signal,
        "price_change_5d": price_change_5d, # Percentage change over 5 days
        # Add other indicators you deem important for defining 'similarity'
        # e.g., 'SMA_20_cross_SMA_50': 'bullish_cross' / 'bearish_cross' / 'no_cross'
    }
    return snapshot

def find_similar_experiences(current_market_state, tolerance=0.15, max_results=5):
    """
    Finds past experience records that match similar market conditions.
    Similarity is based on a few key indicators within a 'tolerance' percentage.
    """
    experience_log = load_experience_log()
    similar_records = []

    if not current_market_state or not experience_log:
        return []

    current_rsi = current_market_state.get('RSI')
    current_macd_signal = current_market_state.get('MACD_signal')
    current_price_change_5d = current_market_state.get('price_change_5d')
    current_symbol = current_market_state.get('symbol')

    if current_rsi is None or current_macd_signal is None or current_price_change_5d is None:
        print("Warning: Current market state is incomplete for similarity search.")
        return []

    for record in experience_log:
        past_state = record.get('market_state', {})
        past_rsi = past_state.get('RSI')
        past_macd_signal = past_state.get('MACD_signal')
        past_price_change_5d = past_state.get('price_change_5d')
        past_symbol = record.get('symbol')

        if past_rsi is None or past_macd_signal is None or past_price_change_5d is None:
            continue # Skip incomplete past records

        # Check for similar RSI (within tolerance percentage)
        rsi_diff = abs(current_rsi - past_rsi) / max(current_rsi, past_rsi, 1e-6) # Avoid division by zero
        is_rsi_similar = rsi_diff <= tolerance

        # Check for similar MACD signal (exact match for simplicity)
        is_macd_similar = (current_macd_signal == past_macd_signal)

        # Check for similar 5-day price change (within tolerance percentage)
        price_change_diff = abs(current_price_change_5d - past_price_change_5d) / max(abs(current_price_change_5d), abs(past_price_change_5d), 1e-6)
        is_price_change_similar = price_change_diff <= tolerance

        # Combine similarity checks. You can adjust the weighting or add more checks.
        if is_rsi_similar and is_macd_similar and is_price_change_similar and past_symbol == current_symbol:
            similar_records.append(record)
            if len(similar_records) >= max_results:
                break # Stop if we found enough similar records

    print(f"Found {len(similar_records)} similar past experiences for {current_market_state['symbol']}.")
    return similar_records

def analyze_similar_outcomes(similar_experiences):
    """
    Analyzes the outcomes of similar past experiences to provide learning insights.
    Identifies common successful actions and warns about past mistakes.
    """
    if not similar_experiences:
        return "No similar past experiences to learn from."

    successful_actions = {} # Count of actions that led to profit
    unsuccessful_actions = {} # Count of actions that led to loss
    total_pl = 0.0
    num_trades = 0

    for record in similar_experiences:
        action = record['action_taken']
        pl = record['trade_outcome_pl']
        
        if pl is None: # Skip records where P&L isn't available yet
            continue

        num_trades += 1
        total_pl += pl

        if pl > 0:
            successful_actions[action] = successful_actions.get(action, 0) + 1
        elif pl < 0:
            unsuccessful_actions[action] = unsuccessful_actions.get(action, 0) + 1

    insight = "Based on similar past market conditions:\n"
    if num_trades > 0:
        avg_pl = total_pl / num_trades
        insight += f"- Average P&L across {num_trades} similar trades: ${avg_pl:.2f}\n"

    if successful_actions:
        insight += "- Actions that have led to profit in similar situations:\n"
        for action, count in successful_actions.items():
            insight += f"  - {action} ({count} times)\n"
    
    if unsuccessful_actions:
        insight += "- Actions that have led to LOSSES in similar situations (exercise caution!):\n"
        for action, count in unsuccessful_actions.items():
            insight += f"  - {action} ({count} times)\n"
    else:
        insight += "- No recorded losses in similar situations (good sign!).\n"

    return insight

if __name__ == "__main__":
    # Example usage:
    # Ensure you've run portfolio_manager.py's test to populate experience_log.json
    print("--- Testing Experience Learner ---")

    # Mock a current market state (e.g., for AAPL)
    # This would normally come from your data_collector and indicators modules
    mock_current_aapl_state = {
        "symbol": "AAPL",
        "current_price": 181.0,
        "RSI": 66.0, # Slightly different from the mock record (65.0)
        "MACD_signal": "bullish_cross",
        "price_change_5d": 0.015 # 1.5% up (mock record was 0.0)
    }

    print(f"\nSearching for similar experiences for {mock_current_aapl_state['symbol']}...")
    similar_aapl_experiences = find_similar_experiences(mock_current_aapl_state, tolerance=0.10) # Adjust tolerance as needed

    if similar_aapl_experiences:
        print("\nAnalyzing similar outcomes for AAPL:")
        learning_insight = analyze_similar_outcomes(similar_aapl_experiences)
        print(learning_insight)
    else:
        print("No similar experiences found for AAPL to analyze.")

    # Mock a current market state for MSFT
    mock_current_msft_state = {
        "symbol": "MSFT",
        "current_price": 395.0,
        "RSI": 32.0,
        "MACD_signal": "bearish_cross",
        "price_change_5d": -0.01
    }
    print(f"\nSearching for similar experiences for {mock_current_msft_state['symbol']}...")
    similar_msft_experiences = find_similar_experiences(mock_current_msft_state, tolerance=0.10)

    if similar_msft_experiences:
        print("\nAnalyzing similar outcomes for MSFT:")
        learning_insight_msft = analyze_similar_outcomes(similar_msft_experiences)
        print(learning_insight_msft)
    else:
        print("No similar experiences found for MSFT to analyze.")

    print("\n--- Experience learner test complete ---")