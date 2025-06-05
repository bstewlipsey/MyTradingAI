import alpaca_trade_api as tradeapi
import os
from dotenv import load_dotenv

load_dotenv()
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")

# Use Alpaca's paper trading URL for testing!
# Base URL for paper trading: https://paper-api.alpaca.markets
# Base URL for live trading: https://api.alpaca.markets
BASE_URL = "https://paper-api.alpaca.markets" # <<< IMPORTANT! START WITH PAPER TRADING!

api = tradeapi.REST(ALPACA_API_KEY, ALPACA_SECRET_KEY, base_url=BASE_URL, api_version='v2')

def execute_trade(symbol, action, qty):
    """Executes a trade using Alpaca API. Supports fractional shares if enabled on your account."""
    if qty <= 0:
        print(f"Cannot execute trade for {symbol}: Quantity is zero or negative.")
        return {"status": "skipped", "message": "Zero quantity"}

    try:
        # Determine if this is a fractional stock order (not crypto)
        is_fractional = isinstance(qty, float) and not symbol.upper().endswith('USD')
        tif = 'day' if is_fractional else 'gtc'
        order = api.submit_order(
            symbol=symbol,
            qty=qty,  # float allowed for fractional trading
            side=action.lower(), # 'buy' or 'sell'
            type='market',
            time_in_force=tif # 'day' for fractional stocks, 'gtc' otherwise
        )
        print(f"Submitted {action} order for {qty} shares of {symbol}. Order ID: {order.id}")
        return {"status": "success", "order_id": order.id, "order_details": order._raw}
    except Exception as e:
        print(f"Error submitting order for {symbol} ({action} {qty}): {e}")
        return {"status": "failed", "message": str(e)}

def get_account_info():
    """Fetches account information from Alpaca."""
    try:
        account = api.get_account()
        print("\n--- Alpaca Account Info ---")
        print(f"Account Status: {account.status}")
        print(f"Cash: ${account.cash}")
        print(f"Portfolio Value: ${account.portfolio_value}")
        return {
            "status": account.status,
            "cash": float(account.cash),
            "portfolio_value": float(account.portfolio_value),
            "long_market_value": float(account.long_market_value),
            "short_market_value": float(account.short_market_value)
        }
    except Exception as e:
        print(f"Error fetching account info: {e}")
        return None

def get_open_positions():
    """Fetches all open positions."""
    try:
        positions = api.list_positions()
        holdings = {}
        for p in positions:
            holdings[p.symbol] = {
                "qty": float(p.qty),
                "avg_entry_price": float(p.avg_entry_price),
                "current_price": float(p.current_price),
                "market_value": float(p.market_value),
                "unrealized_pl": float(p.unrealized_pl)
            }
        print(f"Open Positions: {holdings}")
        return holdings
    except Exception as e:
        print(f"Error fetching open positions: {e}")
        return {}

if __name__ == "__main__":
    # Test Alpaca connection
    account_info = get_account_info()
    if account_info:
        print("Successfully connected to Alpaca Paper Trading account.")
        get_open_positions()

        # Example: Attempt to buy a fractional share of AAPL
        trade_result_aapl = execute_trade("AAPL", "BUY", 0.25)  # Fractional share example
        print(f"Trade Result for AAPL: {trade_result_aapl}")

        # Example: Attempt to buy a fractional share of BTC-USD (if supported)
        trade_result_btc = execute_trade("BTC-USD", "BUY", 0.01)  # Fractional crypto example
        print(f"Trade Result for BTC-USD: {trade_result_btc}")
    else:
        print("Failed to connect to Alpaca.")