import json
import os
from datetime import datetime
import pandas as pd # Import pandas for data handling

# Define the path for the portfolio state file
PORTFOLIO_STATE_FILE = "portfolio_state.json"
EXPERIENCE_LOG_FILE = "experience_log.json" # New file for detailed experiences

def load_portfolio_state():
    """Loads the last saved portfolio state."""
    if os.path.exists(PORTFOLIO_STATE_FILE):
        with open(PORTFOLIO_STATE_FILE, "r") as f:
            return json.load(f)
    # Initial state if file doesn't exist
    return {
        "cash": 10000.0,
        "holdings": {},
        "trade_log": [],
        "llm_reflection_log": [],
        "current_prices": {},
        "cycle_count": 0 # Initialize cycle count
    }

def save_portfolio_state(state):
    """Saves the current portfolio state."""
    with open(PORTFOLIO_STATE_FILE, "w") as f:
        json.dump(state, f, indent=4)
    print("Portfolio state saved.")

def add_trade_log(state, trade_details):
    """Adds a trade entry to the log."""
    trade_details['timestamp'] = datetime.now().isoformat()
    state['trade_log'].append(trade_details)
    print(f"Logged trade: {trade_details['symbol']} {trade_details['action']} {trade_details['size']}")

def add_llm_reflection_log(state, reflection_details):
    """Adds an LLM reflection entry to the log."""
    reflection_details['timestamp'] = datetime.now().isoformat()
    state['llm_reflection_log'].append(reflection_details)
    print("Logged LLM reflection.")

def update_portfolio_from_alpaca(state, alpaca_account, alpaca_positions, current_prices):
    """Updates portfolio state from Alpaca API info."""
    state['cash'] = alpaca_account['cash']
    state['portfolio_value'] = alpaca_account['portfolio_value']
    state['holdings'] = alpaca_positions
    state['current_prices'] = current_prices # Pass latest prices from data collector
    print("Portfolio state updated from Alpaca.")
    return state

# --- NEW FUNCTION FOR EXPERIENCE LOGGING ---
def load_experience_log():
    """Loads the detailed experience log."""
    if os.path.exists(EXPERIENCE_LOG_FILE):
        with open(EXPERIENCE_LOG_FILE, "r") as f:
            return json.load(f)
    return [] # Return empty list if no log exists

def save_experience_log(log):
    """Saves the detailed experience log."""
    with open(EXPERIENCE_LOG_FILE, "w") as f:
        json.dump(log, f, indent=4)
    print("Experience log saved.")

def add_experience_record(
    symbol,
    market_state, # This will be a dictionary of key indicators
    llm_input_prompt,
    llm_output_analysis,
    action_taken,
    trade_size,
    decision_reason,
    trade_outcome_pl, # Actual Profit/Loss from the trade
    timestamp=None
):
    """
    Adds a detailed experience record for learning from past decisions.
    """
    if timestamp is None:
        timestamp = datetime.now().isoformat()

    record = {
        "timestamp": timestamp,
        "symbol": symbol,
        "market_state": market_state, # e.g., {'RSI': 55, 'SMA_20_cross_SMA_50': 'bullish_cross'}
        "llm_input_prompt": llm_input_prompt,
        "llm_output_analysis": llm_output_analysis, # Full LLM analysis dict
        "action_taken": action_taken, # BUY/SELL/HOLD
        "trade_size": trade_size,
        "decision_reason": decision_reason,
        "trade_outcome_pl": trade_outcome_pl # The P&L for this specific action
    }
    
    # Load, append, and save
    experience_log = load_experience_log()
    experience_log.append(record)
    save_experience_log(experience_log)
    print(f"Added experience record for {symbol} with P&L: {trade_outcome_pl:.2f}")

# Utility function to log experience to experience_log.json
def add_experience_record_util(symbol, market_state, llm_input_prompt, llm_output_analysis, action_taken, trade_size, decision_reason, trade_outcome_pl):
    experience = {
        "timestamp": datetime.now().isoformat(),
        "symbol": symbol,
        "market_state": market_state,
        "llm_input_prompt": llm_input_prompt,
        "llm_output_analysis": llm_output_analysis,
        "action_taken": action_taken,
        "trade_size": trade_size,
        "decision_reason": decision_reason,
        "trade_outcome_pl": trade_outcome_pl
    }
    try:
        with open("experience_log.json", "r", encoding="utf-8") as f:
            log = json.load(f)
    except Exception:
        log = []
    log.append(experience)
    with open("experience_log.json", "w", encoding="utf-8") as f:
        json.dump(log, f, indent=4)
    print(f"Experience record logged to file for {symbol}.")


if __name__ == "__main__":
    # Example usage for new functions
    print("--- Testing new experience log functions ---")
    
    # Clear existing logs for a clean test
    if os.path.exists(PORTFOLIO_STATE_FILE):
        os.remove(PORTFOLIO_STATE_FILE)
    if os.path.exists(EXPERIENCE_LOG_FILE):
        os.remove(EXPERIENCE_LOG_FILE)

    current_state = load_portfolio_state()
    print("Initial portfolio state:", current_state)

    # Mock market state for an experience record
    mock_market_state = {
        "current_price": 180.0,
        "RSI": 65.0,
        "MACD_signal": "bullish_cross",
        "recent_trend": "up"
    }
    mock_llm_input = "Prompt text for LLM."
    mock_llm_output = {"sentiment": 70, "action": "BUY", "reasoning": "Good news", "risks": "None"}
    
    # Add a mock experience record
    add_experience_record(
        symbol="AAPL",
        market_state=mock_market_state,
        llm_input_prompt=mock_llm_input,
        llm_output_analysis=mock_llm_output,
        action_taken="BUY",
        trade_size=10,
        decision_reason="LLM recommended buy",
        trade_outcome_pl=50.0 # Example: $50 profit
    )

    add_experience_record(
        symbol="MSFT",
        market_state={
            "current_price": 400.0,
            "RSI": 30.0,
            "MACD_signal": "bearish_cross",
            "recent_trend": "down"
        },
        llm_input_prompt="Prompt for MSFT",
        llm_output_analysis={"sentiment": -60, "action": "SELL", "reasoning": "Bad news", "risks": "High"},
        action_taken="SELL",
        trade_size=5,
        decision_reason="LLM recommended sell",
        trade_outcome_pl=-25.0 # Example: $25 loss
    )
    
    # Verify the experience log
    loaded_exp_log = load_experience_log()
    print("\nLoaded Experience Log:")
    for record in loaded_exp_log:
        print(f"  {record['symbol']} - Action: {record['action_taken']}, P&L: {record['trade_outcome_pl']}")

    print("\n--- Experience log test complete ---")