import os
from dotenv import load_dotenv
import alpaca_trade_api as tradeapi
from config import ALPACA_API_KEY, ALPACA_SECRET_KEY, BASE_URL

# Load environment variables
load_dotenv()

# Initialize Alpaca API
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


def get_alpaca_active_positions():
    """
    Fetches all current open positions from Alpaca and returns them as a standardized dict: symbol -> holding info.
    """
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
        return holdings
    except Exception as e:
        print(f"Error fetching open positions from Alpaca: {e}")
        return {}


def place_stop_loss_order(symbol, qty, side, entry_price, stop_loss_pct):
    """
    Places a stop-loss order for the given symbol and position.
    Args:
        symbol: str, the ticker symbol
        qty: float, the number of shares/contracts
        side: str, 'buy' or 'sell' (direction of the original trade)
        entry_price: float, the price at which the position was entered
        stop_loss_pct: float, the stop loss percent (e.g., 0.02 for 2%)
    Returns:
        order_response: dict, the response from the broker API
    """
    if side.lower() == 'buy':
        stop_price = entry_price * (1 - stop_loss_pct)
        order_side = 'sell'
    else:
        stop_price = entry_price * (1 + stop_loss_pct)
        order_side = 'buy'
    stop_price = round(stop_price, 2)
    try:
        order = api.submit_order(
            symbol=symbol,
            qty=qty,
            side=order_side,
            type='stop',
            time_in_force='gtc',
            stop_price=stop_price
        )
        print(f"Stop-loss order placed for {symbol} at {stop_price}")
        return order._raw
    except Exception as e:
        print(f"Failed to place stop-loss order for {symbol}: {e}")
        return None


if __name__ == "__main__":
    # Test Alpaca connection
    account_info = get_account_info()
    if account_info:
        print("Successfully connected to Alpaca Paper Trading account.")
        get_open_positions()

        # Example: Attempt to buy a fractional share of AAPL
        trade_result_aapl = execute_trade("AAPL", "BUY", 0.25)  # Fractional share example
        print(f"Trade Result for AAPL: {trade_result_aapl}")

        # Place a stop-loss order for the AAPL trade
        if trade_result_aapl["status"] == "success":
            place_stop_loss_order("AAPL", 0.25, "buy", 150.00, 0.02)  # 2% stop loss

        # Example: Attempt to buy a fractional share of BTC-USD (if supported)
        trade_result_btc = execute_trade("BTC-USD", "BUY", 0.01)  # Fractional crypto example
        print(f"Trade Result for BTC-USD: {trade_result_btc}")

        # Place a stop-loss order for the BTC-USD trade
        if trade_result_btc["status"] == "success":
            place_stop_loss_order("BTC-USD", 0.01, "buy", 30000.00, 0.02)  # 2% stop loss
    else:
        print("Failed to connect to Alpaca.")