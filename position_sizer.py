# position_sizer.py
# Utility functions for position sizing and risk management

# Add your position sizing logic here.
import math

def calculate_position_size(
    portfolio_value: float,
    cash_available: float,
    asset_price: float,
    trade_type: str, # "BUY" or "SELL" (for shorting)
    risk_settings: dict,
    llm_sentiment_score: int, # From -100 to 100
    stop_loss_price: float = None, # Optional: explicit stop loss price
    atr: float = None # Optional: Average True Range for volatility
) -> int:
    """
    Calculates the number of shares/units for a trade based on risk management principles,
    cash availability, and LLM sentiment/confidence.

    Args:
        portfolio_value: Total value of the trading portfolio (cash + holdings).
        cash_available: Current available cash for buying.
        asset_price: Current price of the asset.
        trade_type: "BUY" or "SELL" (for shorting).
        risk_settings: Dictionary containing risk parameters.
                       Expected keys: 'max_risk_per_trade_percent', 'max_position_per_asset_percent',
                                     'min_sentiment_for_size_increase', 'sentiment_sizing_factor'
        llm_sentiment_score: Sentiment score from the LLM (-100 to 100).
        stop_loss_price: The price at which a stop loss would be placed.
                         Crucial for calculating dollar risk per share.
        atr: Average True Range for the asset, can be used for dynamic stop loss or sizing.

    Returns:
        The calculated number of shares/units to trade (integer), rounded down.
        Returns 0 if no trade should be made or calculation results in non-positive shares.
    """

    if asset_price <= 0:
        print("Error: Asset price must be positive for position sizing.")
        return 0

    # --- 1. Determine Effective Risk Per Trade based on LLM Sentiment ---
    # The higher the sentiment (above a threshold), the higher the effective risk percentage,
    # up to the max_risk_per_trade_percent.
    
    max_risk_per_trade_percent = risk_settings.get('max_risk_per_trade_percent', 0.01) # Default 1%
    min_sentiment_for_size_increase = risk_settings.get('min_sentiment_for_size_increase', 50) # e.g., 50
    sentiment_sizing_factor = risk_settings.get('sentiment_sizing_factor', 0.005) # e.g., 0.005 means 1 point of sentiment adds 0.5% of risk_per_trade_percent

    effective_risk_per_trade_percent = max_risk_per_trade_percent

    if llm_sentiment_score > min_sentiment_for_size_increase:
        # Increase risk slightly based on high sentiment
        sentiment_boost = (llm_sentiment_score - min_sentiment_for_size_increase) * sentiment_sizing_factor / 100
        effective_risk_per_trade_percent = min(
            max_risk_per_trade_percent * (1 + sentiment_boost),
            max_risk_per_trade_percent * 1.5 # Cap the sentiment boost at 1.5x max_risk_per_trade_percent
        )
        print(f"LLM sentiment {llm_sentiment_score} boosted effective risk to {effective_risk_per_trade_percent:.2%}")
    elif llm_sentiment_score < -min_sentiment_for_size_increase: # Apply for negative sentiment on sells too
        # Similar logic for shorting with strong negative sentiment
        sentiment_boost = (abs(llm_sentiment_score) - min_sentiment_for_size_increase) * sentiment_sizing_factor / 100
        effective_risk_per_trade_percent = min(
            max_risk_per_trade_percent * (1 + sentiment_boost),
            max_risk_per_trade_percent * 1.5 # Cap the sentiment boost
        )
        print(f"LLM sentiment {llm_sentiment_score} boosted effective risk (for shorting) to {effective_risk_per_trade_percent:.2%}")
    else:
        # For neutral or low sentiment, stick to base max_risk_per_trade_percent
        print(f"LLM sentiment {llm_sentiment_score} within neutral range, using base risk {effective_risk_per_trade_percent:.2%}")


    # Dollar amount of capital to risk on this specific trade
    dollar_risk_per_trade = portfolio_value * effective_risk_per_trade_percent
    print(f"Calculated dollar risk per trade: ${dollar_risk_per_trade:.2f}")

    # --- 2. Determine Dollar Risk Per Share ---
    dollar_risk_per_share = 0
    if stop_loss_price is not None and stop_loss_price > 0:
        if trade_type == "BUY":
            dollar_risk_per_share = asset_price - stop_loss_price
        elif trade_type == "SELL": # For shorting
            dollar_risk_per_share = stop_loss_price - asset_price
        
        # Ensure risk per share is positive and meaningful
        if dollar_risk_per_share <= 0:
            print(f"Warning: Stop loss price ({stop_loss_price}) implies no risk or invalid for {trade_type} at {asset_price}. Cannot size position based on stop loss. Returning 0.")
            return 0
        print(f"Calculated dollar risk per share: ${dollar_risk_per_share:.2f} (based on stop loss)")
    elif atr is not None and atr > 0:
        # If no explicit stop loss, use a multiple of ATR for an implicit stop
        # Common practice: 2 * ATR below/above entry
        atr_stop_multiplier = risk_settings.get('atr_stop_multiplier', 2.0)
        dollar_risk_per_share = atr * atr_stop_multiplier
        if dollar_risk_per_share <= 0: # Should not happen if ATR > 0
            print("Warning: ATR-based risk per share is zero or negative. Returning 0.")
            return 0
        print(f"Calculated dollar risk per share: ${dollar_risk_per_share:.2f} (based on {atr_stop_multiplier}x ATR)")
    else:
        # Fallback: If no stop loss or ATR, cannot use risk-based sizing.
        # This is generally NOT recommended for robust risk management.
        # For now, we'll return 0, forcing you to define risk.
        print("Warning: Cannot calculate risk per share (no stop loss or ATR provided). Returning 0 shares.")
        return 0


    # --- 3. Calculate Raw Shares based on Risk ---
    if dollar_risk_per_share > 0:
        shares_from_risk = math.floor(dollar_risk_per_trade / dollar_risk_per_share)
    else:
        shares_from_risk = 0 # Should be caught by earlier checks

    print(f"Shares based on risk management: {shares_from_risk} shares")

    # --- 4. Limit by Available Cash ---
    # For buying: ensure we have enough cash
    max_shares_from_cash = math.floor(cash_available / asset_price)
    print(f"Max shares from cash: {max_shares_from_cash} shares (Cash: ${cash_available:.2f})")

    # Final shares to buy, considering both risk and cash
    shares_to_trade = min(shares_from_risk, max_shares_from_cash)
    
    # --- 5. Limit by Max Position Per Asset (% of Portfolio Value) ---
    max_position_per_asset_percent = risk_settings.get('max_position_per_asset_percent', 0.05) # Default 5%
    max_dollar_position_per_asset = portfolio_value * max_position_per_asset_percent
    
    # Calculate current dollar value of holding for this symbol (if any)
    # This assumes 'current_portfolio' passed from decision_maker can get holdings.
    # For now, we'll assume the decision_maker handles this or we pass it explicitly.
    # A simplified check: if the *new* trade itself would exceed this limit.
    # A more robust check would involve `current_portfolio['holdings'].get(symbol, {}).get('qty', 0)`.
    
    # For simplicity, let's just ensure the *new* trade value doesn't exceed the max per asset.
    # This is a simplification; a full check would need to know current holdings.
    max_shares_from_asset_limit = math.floor(max_dollar_position_per_asset / asset_price)
    shares_to_trade = min(shares_to_trade, max_shares_from_asset_limit)
    print(f"Max shares from asset limit ({max_position_per_asset_percent:.2%}): {max_shares_from_asset_limit} shares")

    # Ensure quantity is positive
    shares_to_trade = max(0, shares_to_trade)
    
    print(f"Final calculated shares to trade: {shares_to_trade}")
    return int(shares_to_trade) # Return as integer

# --- Test Cases ---
if __name__ == "__main__":
    print("--- Position Sizer Test Cases ---")

    # Common Risk Settings
    common_risk_settings = {
        "max_risk_per_trade_percent": 0.01,  # 1% of portfolio value per trade
        "max_position_per_asset_percent": 0.05, # Max 5% of portfolio in any single asset
        "min_sentiment_for_size_increase": 50, # Sentiment above 50 starts increasing size
        "sentiment_sizing_factor": 0.005,      # 1 point of sentiment adds 0.5% to risk_per_trade_percent
        "atr_stop_multiplier": 2.0             # For ATR-based stop loss
    }

    # Test Case 1: Standard Buy, with explicit stop loss, high sentiment
    print("\n--- Test Case 1: Standard Buy, high sentiment ---")
    pv = 100000 # Portfolio Value
    cash = 50000 # Cash available
    price = 100  # Asset price
    stop_loss = 98   # Stop loss price (2$ risk per share)
    sentiment = 80   # Strong positive sentiment

    shares = calculate_position_size(
        portfolio_value=pv,
        cash_available=cash,
        asset_price=price,
        trade_type="BUY",
        risk_settings=common_risk_settings,
        llm_sentiment_score=sentiment,
        stop_loss_price=stop_loss
    )
    print(f"Resulting shares to BUY: {shares}")
    # Expected: dollar_risk_per_trade = 100000 * (0.01 * (1 + (80-50)*0.005)) = 100000 * (0.01 * 1.15) = 1150
    # dollar_risk_per_share = 100 - 98 = 2
    # shares_from_risk = 1150 / 2 = 575
    # max_shares_from_cash = 50000 / 100 = 500
    # max_shares_from_asset_limit = (100000 * 0.05) / 100 = 5000 / 100 = 500
    # Final shares should be min(575, 500, 500) = 500

    # Test Case 2: Buy, but not enough cash
    print("\n--- Test Case 2: Buy, not enough cash ---")
    cash = 1000 # Only 1000 cash
    shares = calculate_position_size(
        portfolio_value=pv,
        cash_available=cash,
        asset_price=price,
        trade_type="BUY",
        risk_settings=common_risk_settings,
        llm_sentiment_score=sentiment,
        stop_loss_price=stop_loss
    )
    print(f"Resulting shares to BUY (not enough cash): {shares}")
    # Expected: max_shares_from_cash = 1000 / 100 = 10
    # Final shares should be 10

    # Test Case 3: Buy, low sentiment (no boost)
    print("\n--- Test Case 3: Buy, low sentiment ---")
    cash = 50000
    sentiment = 20 # Low sentiment
    shares = calculate_position_size(
        portfolio_value=pv,
        cash_available=cash,
        asset_price=price,
        trade_type="BUY",
        risk_settings=common_risk_settings,
        llm_sentiment_score=sentiment,
        stop_loss_price=stop_loss
    )
    print(f"Resulting shares to BUY (low sentiment): {shares}")
    # Expected: dollar_risk_per_trade = 100000 * 0.01 = 1000
    # shares_from_risk = 1000 / 2 = 500
    # max_shares_from_cash = 500
    # max_shares_from_asset_limit = 500
    # Final shares should be 500

    # Test Case 4: Buy, using ATR for implicit stop loss
    print("\n--- Test Case 4: Buy, using ATR ---")
    cash = 50000
    sentiment = 70
    atr_val = 1.5 # ATR is $1.5
    shares = calculate_position_size(
        portfolio_value=pv,
        cash_available=cash,
        asset_price=price,
        trade_type="BUY",
        risk_settings=common_risk_settings,
        llm_sentiment_score=sentiment,
        atr=atr_val # No stop_loss_price
    )
    print(f"Resulting shares to BUY (using ATR): {shares}")
    # Expected: dollar_risk_per_share = 1.5 * 2 = 3
    # effective_risk_per_trade_percent = 0.01 * (1 + (70-50)*0.005) = 0.01 * 1.1 = 0.011
    # dollar_risk_per_trade = 100000 * 0.011 = 1100
    # shares_from_risk = 1100 / 3 = 366.66 -> 366
    # max_shares_from_cash = 500
    # max_shares_from_asset_limit = 500
    # Final shares should be 366

    # Test Case 5: Sell (short), explicit stop loss, strong negative sentiment
    print("\n--- Test Case 5: Sell (short), strong negative sentiment ---")
    cash = 50000
    price = 100
    stop_loss_short = 102 # Stop loss above entry for short
    sentiment = -90 # Strong negative sentiment
    shares = calculate_position_size(
        portfolio_value=pv,
        cash_available=cash, # Cash available is still relevant for margin/collateral
        asset_price=price,
        trade_type="SELL", # Short sell
        risk_settings=common_risk_settings,
        llm_sentiment_score=sentiment,
        stop_loss_price=stop_loss_short
    )
    print(f"Resulting shares to SELL (short): {shares}")
    # Expected: dollar_risk_per_trade = 100000 * (0.01 * (1 + (abs(-90)-50)*0.005)) = 100000 * (0.01 * 1.2) = 1200
    # dollar_risk_per_share = 102 - 100 = 2
    # shares_from_risk = 1200 / 2 = 600
    # max_shares_from_cash (assuming short selling doesn't directly consume cash for shares)
    # This part needs careful consideration for short selling, as it's margin-based.
    # For now, max_shares_from_cash would be limited by margin buying power or simply if you have enough collateral.
    # For a direct buy/sell, cash_available makes sense. For short selling, it's more complex.
    # For simplicity, we'll keep max_shares_from_cash as a general limit, but it's not truly for cash in hand for shorting.
    # Max shares from asset limit = 500
    # Final shares should be 500

    print("\n--- Position Sizer Test Cases Complete ---")