import time
import os
import pandas as pd
from datetime import datetime

# Import functions from your other modules
from data_collector import get_historical_trade_data, get_financial_news
from indicators import calculate_indicators
from ai_brain import get_llm_analysis, model, reflect_and_learn # Import reflect_and_learn from ai_brain
from decision_maker import make_trading_decision # NEW: Import from your new decision maker file
from trade_executor import execute_trade, get_account_info, get_open_positions, BASE_URL
from portfolio_manager import load_portfolio_state, save_portfolio_state, add_trade_log, add_llm_reflection_log, update_portfolio_from_alpaca, add_experience_record
from experience_learner import get_market_state_snapshot, find_similar_experiences, analyze_similar_outcomes # NEW IMPORT
from config import TRADING_SYMBOLS, CYCLE_INTERVAL_SECONDS, LOOKBACK_PERIOD_HISTORY, NEWS_QUERY_LIMIT_PER_SYMBOL, NEWS_QUERY_GLOBAL_LIMIT, LLM_REFLECTION_INTERVAL_CYCLES, NEWS_FETCH_INTERVAL_CYCLES, RISK_SETTINGS, SIMILARITY_TOLERANCE, MAX_SIMILAR_RECORDS

# (Remove all variable definitions for config values, keep only logic)

def main_trading_cycle():
    print(f"\n--- Starting Trading Cycle: {datetime.now().isoformat()} ---")

    # 0. Load Portfolio State
    portfolio_state = load_portfolio_state()
    portfolio_state['cycle_count'] = portfolio_state.get('cycle_count', 0) + 1
    cycle_count = portfolio_state['cycle_count']
    cash_val = portfolio_state.get('cash', 'N/A')
    port_val = portfolio_state.get('portfolio_value', 'N/A')
    try:
        cash_str = f"${float(cash_val):.2f}" if isinstance(cash_val, (int, float)) or (isinstance(cash_val, str) and cash_val.replace('.', '', 1).isdigit()) else str(cash_val)
    except Exception:
        cash_str = str(cash_val)
    try:
        port_str = f"${float(port_val):.2f}" if isinstance(port_val, (int, float)) or (isinstance(port_val, str) and port_val.replace('.', '', 1).isdigit()) else str(port_val)
    except Exception:
        port_str = str(port_val)
    print(f"Current Cash: {cash_str}, Portfolio Value: {port_str}")

    # 1. Update Portfolio from Alpaca (get latest cash/holdings)
    alpaca_account = get_account_info()
    if alpaca_account:
        alpaca_positions = get_open_positions()
        # Create a dictionary of current prices from Alpaca positions for held assets
        current_prices_from_alpaca_holdings = {p: alpaca_positions[p]['current_price'] for p in alpaca_positions}
        portfolio_state = update_portfolio_from_alpaca(portfolio_state, alpaca_account, alpaca_positions, current_prices_from_alpaca_holdings)
    else:
        print("WARNING: Could not connect to Alpaca or fetch account info. Using cached portfolio state.")

    # 2. Data Collection (Quota-Aware)
    os.makedirs("data", exist_ok=True)
    all_news_data = pd.DataFrame()
    latest_prices = {} # Store latest prices for passing to decision maker

    fetch_news_this_cycle = (cycle_count % NEWS_FETCH_INTERVAL_CYCLES == 1)

    for symbol in TRADING_SYMBOLS:
        print(f"\n--- Collecting data for {symbol} ---")
        history_df = get_historical_trade_data(symbol, period=LOOKBACK_PERIOD_HISTORY)
        if not history_df.empty:
            history_df_with_indicators = calculate_indicators(history_df)
            history_df_with_indicators.to_csv(f"data/{symbol}_processed_history.csv")
            latest_prices[symbol] = history_df_with_indicators['Close'].iloc[-1]
        else:
            print(f"Could not get historical data for {symbol}. Skipping.")
            latest_prices[symbol] = 0 # Indicate no valid price
            continue # Skip to next symbol if no history

        if fetch_news_this_cycle:
            ticker_news_df = get_financial_news(query=f"{symbol} stock", page_size=NEWS_QUERY_LIMIT_PER_SYMBOL)
            if not ticker_news_df.empty:
                all_news_data = pd.concat([all_news_data, ticker_news_df], ignore_index=True)
                ticker_news_df.to_csv(f"data/{symbol}_news.csv", index=False)
            else:
                print(f"No specific news for {symbol}.")
        else:
            # Load cached news if not fetching this cycle
            news_path = f"data/{symbol}_news.csv"
            if os.path.exists(news_path):
                ticker_news_df = pd.read_csv(news_path)
                all_news_data = pd.concat([all_news_data, ticker_news_df], ignore_index=True)
            else:
                print(f"No cached news for {symbol}.")

    if fetch_news_this_cycle:
        general_market_news_df = get_financial_news(query="stock market OR economy", page_size=NEWS_QUERY_GLOBAL_LIMIT)
        if not general_market_news_df.empty:
            all_news_data = pd.concat([all_news_data, general_market_news_df], ignore_index=True)
            general_market_news_df.to_csv("data/general_market_news.csv", index=False)
    else:
        # Load cached general news if not fetching this cycle
        news_path = "data/general_market_news.csv"
        if os.path.exists(news_path):
            general_market_news_df = pd.read_csv(news_path)
            all_news_data = pd.concat([all_news_data, general_market_news_df], ignore_index=True)
        else:
            print("No cached general market news.")

    # Update portfolio state with latest prices for accurate calculations
    # This combines prices from Alpaca holdings with newly fetched prices for non-held assets
    portfolio_state['current_prices'].update(latest_prices)
    save_portfolio_state(portfolio_state)

    # 3. LLM/AI Analysis & Decision Making (for each asset)
    print("\n--- Performing LLM Analysis and Decision Making ---")
    for symbol in TRADING_SYMBOLS:
        current_price = portfolio_state['current_prices'].get(symbol, 0)
        if current_price == 0:
            print(f"Skipping {symbol} due to no valid current price.")
            continue

        # Load processed data for LLM and Experience Learner
        try:
            history_df = pd.read_csv(f"data/{symbol}_processed_history.csv", index_col="Date", parse_dates=True)
            recent_history_for_llm = history_df.tail(10) # Last 10 rows for LLM

            # Get market state snapshot for experience learner
            current_market_state_snapshot = get_market_state_snapshot(history_df, symbol)

        except FileNotFoundError:
            print(f"Processed history not found for {symbol}. Skipping LLM analysis.")
            continue
        except Exception as e:
            print(f"Error preparing data for {symbol}: {e}. Skipping.")
            continue

        relevant_news_for_llm = all_news_data[all_news_data['title'].str.contains(symbol, case=False, na=False) |
                                              all_news_data['description'].str.contains(symbol, case=False, na=False)].head(NEWS_QUERY_LIMIT_PER_SYMBOL)

        # --- Consult Experience Learner ---
        learning_insight = ""
        try:
            similar_experiences = find_similar_experiences(current_market_state_snapshot, tolerance=SIMILARITY_TOLERANCE, max_results=MAX_SIMILAR_RECORDS)
            learning_insight = analyze_similar_outcomes(similar_experiences)
            print(f"\nLearning Insight for {symbol}:\n{learning_insight}")
        except Exception as e:
            print(f"Error getting learning insight for {symbol}: {e}")
            learning_insight = "Could not retrieve past learning insights."

        # Construct past trades summary for LLM reflection (combining with new learning insight)
        past_trades_summary = ""
        ticker_trade_log = [t for t in portfolio_state['trade_log'] if t.get('symbol') == symbol]
        if ticker_trade_log:
            last_trade = ticker_trade_log[-1]
            past_trades_summary = f"My last action for {symbol} was a {last_trade['action']} of {last_trade['size']} shares at ${last_trade['price']:.2f}. " \
                                  f"My reasoning then was: '{last_trade.get('llm_reasoning', 'N/A')}'. Outcome: [You need to manually calculate P&L or fetch from Alpaca settlement for accuracy]."
            if last_trade.get('status') == 'success':
                past_trades_summary += "The trade was submitted successfully."
            else:
                past_trades_summary += "The trade encountered an issue."

        # Add the learning insight to the LLM's prompt

        try:
            llm_analysis = get_llm_analysis(
                symbol=symbol,
                current_price=current_price,
                recent_history_df=recent_history_for_llm,
                news_df=relevant_news_for_llm,
                past_trades_summary=past_trades_summary + "\n\nAlso, consider the following insights from similar past market conditions:\n" + learning_insight
            )
            trade_decision = make_trading_decision(
                symbol=symbol,
                llm_analysis_result=llm_analysis,
                current_portfolio=portfolio_state,
                risk_settings=RISK_SETTINGS
            )
        except Exception as e:
            print(f"LLM analysis failed for {symbol}: {e}. Using fallback technical strategy.")
            # Fallback: simple technical-based decision
            last_row = recent_history_for_llm.iloc[-1] if not recent_history_for_llm.empty else None
            fallback_decision = "HOLD"
            fallback_reason = "LLM unavailable. Fallback to technicals."
            fallback_sentiment = 0
            fallback_size = 0
            if last_row is not None:
                sma20 = last_row['SMA_20'] if 'SMA_20' in last_row else None
                rsi = last_row['RSI'] if 'RSI' in last_row else None
                if sma20 and current_price > sma20 and rsi and rsi < 70:
                    fallback_decision = "BUY"
                    fallback_sentiment = 50
                    fallback_size = 1  # Or use your sizing logic
                    fallback_reason = "Price above SMA20 and RSI < 70."
                elif sma20 and current_price < sma20 and rsi and rsi > 30:
                    fallback_decision = "SELL"
                    fallback_sentiment = -50
                    fallback_size = 1
                    fallback_reason = "Price below SMA20 and RSI > 30."
            trade_decision = {
                'decision': fallback_decision,
                'size': fallback_size,
                'reason': fallback_reason,
                'llm_sentiment': fallback_sentiment
            }
            llm_analysis = {
                'sentiment': fallback_sentiment,
                'reasoning': fallback_reason,
                'risks': 'LLM unavailable. Used fallback technicals.',
                'raw_prompt_sent': '',
            }

        # 4. Trade Execution (Simulated or Real)
        trade_outcome_pl = 0.0 # Initialize P&L for this specific trade
        if trade_decision['decision'] in ["BUY", "SELL"] and trade_decision['size'] > 0:
            print(f"Executing trade for {symbol}: {trade_decision['decision']} {trade_decision['size']}")
            trade_result = execute_trade(alpaca_symbol(symbol), trade_decision['decision'], trade_decision['size'])

            # 5. Portfolio & State Update (after trade)
            updated_alpaca_account = get_account_info()
            updated_alpaca_positions = get_open_positions()
            if updated_alpaca_account:
                updated_prices = {symbol: pos['current_price'] for symbol, pos in updated_alpaca_positions.items()}
                updated_prices.update(latest_prices)
                portfolio_state = update_portfolio_from_alpaca(portfolio_state, updated_alpaca_account, updated_alpaca_positions, updated_prices)
            else:
                print("Warning: Could not fetch updated Alpaca info after trade. Portfolio state might be stale.")

            # --- Placeholder for Actual P&L Calculation (Implement this carefully!) ---
            # This is a critical point for your AI to learn from its actual performance.
            # For open positions, you could use (current_price - avg_entry_price) * qty as unrealized_pl
            # For closed positions, it's (sell_price - buy_price) * qty
            trade_outcome_pl = 0.0 # <--- REPLACE WITH ACTUAL P&L CALCULATION LATER

            # Log the trade details with LLM reasoning
            logged_trade = {
                "symbol": symbol,
                "action": trade_decision['decision'],
                "size": trade_decision['size'],
                "price": current_price, # Price at time of decision/execution
                "status": trade_result['status'],
                "order_id": trade_result.get('order_id'),
                "llm_sentiment": llm_analysis['sentiment'],
                "llm_reasoning": llm_analysis['reasoning'],
                "llm_risks": llm_analysis['risks'],
                "trade_outcome_pl": trade_outcome_pl # Log the P&L for this trade
            }
            add_trade_log(portfolio_state, logged_trade)

            # --- Add to Experience Log ---
            add_experience_record(
                symbol=symbol,
                market_state=current_market_state_snapshot,
                llm_input_prompt=llm_analysis.get('raw_prompt_sent', ''), # Use the saved prompt
                llm_output_analysis=llm_analysis,
                action_taken=trade_decision['decision'],
                trade_size=trade_decision['size'],
                decision_reason=trade_decision['reason'],
                trade_outcome_pl=trade_outcome_pl # This is the crucial part for learning!
            )

        else:
            print(f"No trade executed for {symbol}. Reason: {trade_decision['reason']}")
            # Optional: You could still log the LLM's analysis and the 'HOLD' decision
            # as an experience if you want the AI to learn from "correct holds" too.
            # For now, we only log executed trades.

        # Save state after each symbol's decision/execution
        save_portfolio_state(portfolio_state)

    # 6. Reflection & Learning (Periodically)
    portfolio_state['cycle_count'] = portfolio_state.get('cycle_count', 0) + 1
    if portfolio_state['cycle_count'] % LLM_REFLECTION_INTERVAL_CYCLES == 0:
        print(f"\n--- Performing LLM Reflection (Cycle {portfolio_state['cycle_count']}) ---")
        # The reflect_and_learn function from ai_brain.py
        # will now potentially use the updated trade log which includes P&L,
        # or you could modify it to directly summarize the experience_log.
        reflect_and_learn(model, portfolio_state)
        add_llm_reflection_log(portfolio_state, {"cycle": portfolio_state['cycle_count'], "reflection_performed": True}) # Log that reflection occurred
        save_portfolio_state(portfolio_state)

    print(f"--- Trading Cycle Complete: {datetime.now().isoformat()} ---")


def alpaca_symbol(symbol):
    """Convert crypto symbols from '-' to '/' for Alpaca, leave stocks unchanged."""
    if symbol.endswith("-USD"):
        return symbol.replace("-", "/")
    return symbol


if __name__ == "__main__":
    import sys
    import signal

    def safe_shutdown(*args):
        print(f"\n[{datetime.now().isoformat()}] Trading agent stopped safely. Saving state...")
        try:
            # Save portfolio state and any other critical info
            save_portfolio_state(load_portfolio_state())
        except Exception as e:
            print(f"Error during shutdown save: {e}")
        sys.exit(0)
    signal.signal(signal.SIGINT, safe_shutdown)
    signal.signal(signal.SIGTERM, safe_shutdown)
    
    
    print(f"Running trading bot in {'PAPER TRADING' if BASE_URL == 'https://paper-api.alpaca.markets' else 'LIVE TRADING'} mode.")
    while True:
        try:
            main_trading_cycle()
            print(f"Waiting for {CYCLE_INTERVAL_SECONDS} seconds until next cycle...")
            time.sleep(CYCLE_INTERVAL_SECONDS)
        except KeyboardInterrupt:
            safe_shutdown()
        except Exception as e:
            print(f"Fatal error: {e}")
            safe_shutdown()