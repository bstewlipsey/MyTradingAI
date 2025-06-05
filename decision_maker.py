# Import the new position_sizer module
from position_sizer import calculate_position_size
# Assuming you already import portfolio_manager if needed for portfolio_value/cash_available

def make_trading_decision(
    symbol: str,
    llm_analysis_result: dict,
    current_portfolio: dict, # Contains 'cash', 'portfolio_value', 'current_prices'
    risk_settings: dict,
    # You will need to pass ATR here if you want to use it for sizing
    # For now, let's assume you'll get ATR from your indicators for the stock
    # If ATR is not available, stop_loss_price must be provided or it will return 0
    atr_value: float = None # NEW PARAMETER
) -> dict:
    """
    Makes a final trading decision (BUY, SELL, HOLD) based on LLM analysis,
    portfolio status, risk settings, and calculates position size.
    """
    sentiment = llm_analysis_result.get('sentiment', 0)
    llm_action = llm_analysis_result.get('action', 'HOLD')
    reasoning = llm_analysis_result.get('reasoning', 'No specific reason provided by LLM.')
    
    current_price = current_portfolio['current_prices'].get(symbol, 0)
    portfolio_value = current_portfolio.get('portfolio_value', current_portfolio['cash']) # Use actual portfolio value
    cash_available = current_portfolio['cash']

    # Default to HOLD
    final_decision = "HOLD"
    trade_size = 0
    decision_reason = "No compelling reason to trade or outside risk parameters."

    # Get risk thresholds from settings
    min_sentiment_for_buy = risk_settings.get('min_sentiment_for_buy', 40)
    min_sentiment_for_sell = risk_settings.get('min_sentiment_for_sell', -40)
    max_risk_per_trade_percent = risk_settings.get('max_risk_per_trade_percent', 0.01) # Use the new name
    max_position_per_asset_percent = risk_settings.get('max_position_per_asset_percent', 0.05) # Use the new name

    # --- Decision Logic ---
    if llm_action == "BUY" and sentiment > min_sentiment_for_buy:
        current_holding_qty = current_portfolio['holdings'].get(symbol, {}).get('qty', 0)
        current_holding_value = current_holding_qty * current_price
        if current_holding_value / portfolio_value < max_position_per_asset_percent:
            # Use ATR if provided, else fallback to a default stop loss
            stop_loss_price = current_price * (1 - max_risk_per_trade_percent * 2)
            shares_to_buy = calculate_position_size(
                portfolio_value=portfolio_value,
                cash_available=cash_available,
                asset_price=current_price,
                trade_type="BUY",
                risk_settings=risk_settings,
                llm_sentiment_score=sentiment,
                stop_loss_price=stop_loss_price,
                atr=atr_value
            )
            if shares_to_buy > 0:
                final_decision = "BUY"
                trade_size = shares_to_buy
                decision_reason = f"LLM recommended BUY (Sentiment: {sentiment}). Risk-managed position size calculated."
            else:
                decision_reason = "LLM recommended BUY, but position sizing resulted in 0 shares (e.g., not enough cash, risk too high, or no valid stop/ATR)."
        else:
            decision_reason = f"LLM recommended BUY, but already at max position ({max_position_per_asset_percent:.2%}) for {symbol}."

    elif llm_action == "SELL" and sentiment < min_sentiment_for_sell:
        current_holding_qty = current_portfolio['holdings'].get(symbol, {}).get('qty', 0)
        if current_holding_qty > 0:
            final_decision = "SELL"
            trade_size = current_holding_qty
            decision_reason = f"LLM recommended SELL (Sentiment: {sentiment}). Closing existing position."
        elif llm_action == "SELL" and sentiment < min_sentiment_for_sell and current_holding_qty == 0:
            stop_loss_price = current_price * (1 + max_risk_per_trade_percent * 2)
            shares_to_short = calculate_position_size(
                portfolio_value=portfolio_value,
                cash_available=cash_available,
                asset_price=current_price,
                trade_type="SELL",
                risk_settings=risk_settings,
                llm_sentiment_score=sentiment,
                stop_loss_price=stop_loss_price,
                atr=atr_value
            )
            if shares_to_short > 0:
                final_decision = "SELL"
                trade_size = shares_to_short
                decision_reason = f"LLM recommended SELL (Sentiment: {sentiment}). Initiating short position with risk-managed size."
            else:
                decision_reason = "LLM recommended SELL/SHORT, but position sizing resulted in 0 shares for shorting."
    else:
        decision_reason = f"LLM action '{llm_action}' or sentiment '{sentiment}' not strong enough (min buy: {min_sentiment_for_buy}, min sell: {min_sentiment_for_sell})."

    return {
        "decision": final_decision,
        "size": int(trade_size),
        "reason": decision_reason,
        "llm_sentiment": sentiment,
        "llm_reasoning": reasoning
    }

if __name__ == "__main__":
    # Mock LLM analysis result for testing
    mock_llm_result_buy = {
        "sentiment": 75,
        "action": "BUY",
        "reasoning": "Strong news, positive indicators.",
        "risks": "Market downturn"
    }
    mock_llm_result_sell = {
        "sentiment": -60,
        "action": "SELL",
        "reasoning": "Negative earnings, bearish sentiment.",
        "risks": "Short squeeze"
    }
    mock_llm_result_hold = {
        "sentiment": 10,
        "action": "HOLD",
        "reasoning": "Mixed signals.",
        "risks": "Uncertainty"
    }

    # Mock current portfolio and prices
    mock_portfolio = {
        "cash": 10000,
        "holdings": {
            "AAPL": {"qty": 50, "avg_price": 170, "value": 50 * 170}, # Example holding
            "MSFT": {"qty": 0, "avg_price": 0, "value": 0}
        },
        "current_prices": {
            "AAPL": 180,
            "MSFT": 400
        }
    }
    mock_risk_settings = {
        "max_risk_per_trade_percent": 0.01, # 1%
        "min_sentiment_for_buy": 40,
        "min_sentiment_for_sell": -40,
        "max_position_per_asset_percent": 0.05 # 5%
    }

    print("\n--- Testing Decision Maker ---")
    # Test BUY scenario
    buy_decision = make_trading_decision(
        symbol="MSFT",
        llm_analysis_result=mock_llm_result_buy,
        current_portfolio=mock_portfolio,
        risk_settings=mock_risk_settings
    )
    print(f"MSFT Decision: {buy_decision}")

    # Test SELL scenario (for AAPL, assuming we hold it)
    sell_decision = make_trading_decision(
        symbol="AAPL",
        llm_analysis_result=mock_llm_result_sell,
        current_portfolio=mock_portfolio,
        risk_settings=mock_risk_settings
    )
    print(f"AAPL Decision: {sell_decision}")

    # Test HOLD scenario
    hold_decision = make_trading_decision(
        symbol="GOOGL",
        llm_analysis_result=mock_llm_result_hold,
        current_portfolio=mock_portfolio,
        risk_settings=mock_risk_settings
    )
    print(f"GOOGL Decision: {hold_decision}")