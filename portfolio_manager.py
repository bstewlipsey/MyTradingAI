import json
import os
import sys
from datetime import datetime
import pandas as pd # Import pandas for data handling
from config import LLM_PROMPT_TEMPLATE

# Define the path for the portfolio state file
PORTFOLIO_STATE_FILE = "portfolio_state.json"
PORTFOLIO_STATE_BACKUP_FILE = "portfolio_state_backup.json"
EXPERIENCE_LOG_FILE = "experience_log.json" # New file for detailed experiences

def load_portfolio_state():
    """Loads the last saved portfolio state."""
    if os.path.exists(PORTFOLIO_STATE_FILE):
        with open(PORTFOLIO_STATE_FILE, "r") as f:
            state = json.load(f)
            # Ensure decision_history key exists
            if "decision_history" not in state:
                state["decision_history"] = []
            # Ensure llm_prompt_template exists
            if "llm_prompt_template" not in state:
                state["llm_prompt_template"] = LLM_PROMPT_TEMPLATE
            # Ensure adaptation_log exists
            if "adaptation_log" not in state:
                state["adaptation_log"] = []
            # Ensure anomaly_log exists
            if "anomaly_log" not in state:
                state["anomaly_log"] = []
            return state
    # Initial state if file doesn't exist
    return {
        "cash": 10000.0,
        "holdings": {},
        "trade_log": [],
        "llm_reflection_log": [],
        "current_prices": {},
        "cycle_count": 0, # Initialize cycle count
        "decision_history": [],
        "llm_prompt_template": LLM_PROMPT_TEMPLATE,
        "adaptation_log": [],
        "anomaly_log": []
    }

def save_portfolio_state(state):
    """Saves the current portfolio state and creates a backup."""
    with open(PORTFOLIO_STATE_FILE, "w") as f:
        json.dump(state, f, indent=4)
    # Backup
    with open(PORTFOLIO_STATE_BACKUP_FILE, "w") as f:
        json.dump(state, f, indent=4)
    print("Portfolio state saved and backup created.")

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
    """Updates portfolio state from Alpaca API info. This function is called at the start of every trading cycle to ensure the local state is always synchronized with Alpaca, treating Alpaca as the source of truth."""
    state['cash'] = alpaca_account['cash']
    state['portfolio_value'] = alpaca_account['portfolio_value']
    state['holdings'] = alpaca_positions
    state['current_prices'] = current_prices # Pass latest prices from data collector
    print("Portfolio state updated from Alpaca (source of truth). All local portfolio values are now overwritten.")
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

def add_decision_to_history(state, symbol, decision_type, llm_sentiment, llm_reasoning, llm_risks):
    """
    Appends a decision record to the decision_history in the portfolio state and saves it.
    """
    record = {
        "timestamp": datetime.now().isoformat(),
        "symbol": symbol,
        "decision_type": decision_type,
        "llm_sentiment": llm_sentiment,
        "llm_reasoning": llm_reasoning,
        "llm_risks": llm_risks
    }
    if "decision_history" not in state:
        state["decision_history"] = []
    state["decision_history"].append(record)
    save_portfolio_state(state)
    print(f"Logged decision for {symbol}: {decision_type} (Sentiment: {llm_sentiment})")


def update_trade_outcomes_on_close(prev_holdings, curr_holdings, trade_log, latest_prices=None):
    """
    Detects closed positions and updates trade_log and experience_log.json with realized P&L.
    prev_holdings: dict of symbol -> holding info before trade
    curr_holdings: dict of symbol -> holding info after trade
    trade_log: list of trade dicts (from portfolio_state)
    latest_prices: dict of symbol -> price at close (optional, fallback to current_price in prev_holdings)
    """
    if latest_prices is None:
        latest_prices = {}
    closed_symbols = []
    for symbol, prev in prev_holdings.items():
        prev_qty = prev.get('qty', 0)
        curr_qty = curr_holdings.get(symbol, {}).get('qty', 0)
        if prev_qty > 0 and curr_qty == 0:
            # Position closed
            closed_symbols.append(symbol)
            avg_entry = prev.get('avg_entry_price', 0)
            close_price = latest_prices.get(symbol, prev.get('current_price', 0))
            realized_pl = (close_price - avg_entry) * prev_qty
            # Find the most recent open trade for this symbol in trade_log
            for trade in reversed(trade_log):
                if trade.get('symbol') == symbol and trade.get('action') == 'BUY' and trade.get('trade_outcome_pl', 0.0) == 0.0:
                    trade['trade_outcome_pl'] = realized_pl
                    break
            # Update experience_log.json as well
            exp_log = load_experience_log()
            for exp in reversed(exp_log):
                if exp.get('symbol') == symbol and exp.get('action_taken') == 'BUY' and exp.get('trade_outcome_pl', 0.0) == 0.0:
                    exp['trade_outcome_pl'] = realized_pl
                    break
            save_experience_log(exp_log)
            print(f"Updated realized P&L for closed {symbol}: {realized_pl:.2f}")
    return closed_symbols

def restore_portfolio_state_from_backup():
    """Restores portfolio state from backup file."""
    if os.path.exists(PORTFOLIO_STATE_BACKUP_FILE):
        with open(PORTFOLIO_STATE_BACKUP_FILE, "r") as f:
            backup_state = json.load(f)
        with open(PORTFOLIO_STATE_FILE, "w") as f:
            json.dump(backup_state, f, indent=4)
        print("Portfolio state restored from backup.")
    else:
        print("No backup file found.")

# Utility to log anomalies
def log_anomaly(state, anomaly_type, details):
    entry = {
        "timestamp": datetime.now().isoformat(),
        "anomaly_type": anomaly_type,
        "details": details
    }
    if "anomaly_log" not in state:
        state["anomaly_log"] = []
    state["anomaly_log"].append(entry)
    save_portfolio_state(state)
    print(f"Anomaly logged: {anomaly_type} - {details}")

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