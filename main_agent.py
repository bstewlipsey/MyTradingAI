import time
import os
import pandas as pd
from datetime import datetime
import asyncio
import sys  # Moved from __main__ block as per TODO
import signal  # Moved from __main__ block as per TODO

# Import functions from your other modules
from data_collector import get_historical_trade_data, start_alpaca_news_ws_background, load_news_from_json
from indicators import calculate_indicators
from ai_brain import get_llm_analysis, model, reflect_and_learn # Import reflect_and_learn from ai_brain
from decision_maker import make_trading_decision
from trade_executor import get_open_positions, get_account_info, execute_trade, BASE_URL, place_stop_loss_order
from portfolio_manager import load_portfolio_state, save_portfolio_state, add_trade_log, add_llm_reflection_log, update_portfolio_from_alpaca, add_experience_record, add_decision_to_history, update_trade_outcomes_on_close
from experience_learner import get_market_state_snapshot, find_similar_experiences, analyze_similar_outcomes # NEW IMPORT
from config import TRADING_SYMBOLS, CYCLE_INTERVAL_SECONDS, LOOKBACK_PERIOD_HISTORY, NEWS_QUERY_LIMIT_PER_SYMBOL, LLM_REFLECTION_INTERVAL_CYCLES, NEWS_FETCH_INTERVAL_CYCLES, RISK_SETTINGS, SIMILARITY_TOLERANCE, MAX_SIMILAR_RECORDS
from learning_agent import analyze_llm_reflections

# (Remove all variable definitions for config values, keep only logic)



def main_trading_cycle():
    # STEP 1: Start Trading Cycle
    print(f"\n--- Starting Trading Cycle: {datetime.now().isoformat()} ---")
    
    # STEP 2: Load Portfolio State
    portfolio_state = load_portfolio_state()
    
    # STEP 3: Anomaly Alert? (Print any new anomalies this cycle)
    last_alerted_cycle = portfolio_state.get('last_anomaly_alert_cycle', 0)
    new_anomalies = [a for a in portfolio_state.get('anomaly_log', []) if a.get('cycle', 0) > last_alerted_cycle]
    if new_anomalies:
        print("\n!!! ANOMALY ALERT !!!")
        for anomaly in new_anomalies:
            print(f"[{anomaly['timestamp']}] {anomaly['anomaly_type']}: {anomaly['details']}")
        portfolio_state['last_anomaly_alert_cycle'] = portfolio_state.get('cycle_count', 0)
        save_portfolio_state(portfolio_state)

    # STEP 4: Increment Cycle Count
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

    # STEP 5: Update Portfolio from Alpaca (account, positions, prices)
    alpaca_account = get_account_info()
    if alpaca_account:
        alpaca_positions = get_open_positions()
        current_prices_from_alpaca_holdings = {p: alpaca_positions[p]['current_price'] for p in alpaca_positions}
        portfolio_state = update_portfolio_from_alpaca(portfolio_state, alpaca_account, alpaca_positions, current_prices_from_alpaca_holdings)
    else:
        print("WARNING: Could not connect to Alpaca or fetch account info. Using cached portfolio state.")
        sys.exit(1)  # Exit if we can't get account info, as we need it for trading decisions

    # STEP 6: Data Collection (historical, indicators, news)
    os.makedirs("data", exist_ok=True)
    all_news_data = pd.DataFrame()
    latest_prices = {}
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
            latest_prices[symbol] = 0
            continue

    # STEP 7: Fetch News (periodic, from Alpaca WSS buffer)
    if fetch_news_this_cycle:
        news_json = load_news_from_json(limit=100)  # Load last 100 news items
        if news_json:
            all_news_data = pd.DataFrame(news_json)
        else:
            all_news_data = pd.DataFrame()
    else:
        all_news_data = pd.DataFrame()

    # STEP 8: Update current prices in portfolio state
    portfolio_state['current_prices'].update(latest_prices)
    save_portfolio_state(portfolio_state)

    # STEP 9: For each symbol: LLM/AI Analysis & Decision Making
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
            # Extract ATR if available for position sizing
            atr_value = None
            if 'ATR' in history_df.columns:
                atr_value = history_df['ATR'].iloc[-1]
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
            # Use actual P&L if available
            trade_outcome = last_trade.get('trade_outcome_pl')

            if trade_outcome is not None:
                outcome_str = f"Realized P&L: ${trade_outcome:.2f}"
            else:
                outcome_str = "Outcome: [P&L not available]"

            past_trades_summary = f"My last action for {symbol} was a {last_trade['action']} of {last_trade['size']} shares at ${last_trade['price']:.2f}. " \
                                  f"My reasoning then was: '{last_trade.get('llm_reasoning', 'N/A')}'. {outcome_str}."
            
            if last_trade.get('status') == 'success':
                past_trades_summary += " The trade was submitted successfully."
            else:
                past_trades_summary += " The trade encountered an issue."

        # Add the learning insight to the LLM's prompt
        try:
            llm_analysis = get_llm_analysis(
                symbol=symbol,
                current_price=current_price,
                recent_history_df=recent_history_for_llm,
                news_df=relevant_news_for_llm,
                past_trades_summary=past_trades_summary + "\n\nAlso, consider the following insights from similar past market conditions:\n" + learning_insight
            )
            if isinstance(llm_analysis, dict):
                llm_analysis['raw_prompt_sent'] = llm_analysis.get('raw_prompt_sent', '') or locals().get('prompt', '')
            # Check for LLM failure by action/risks (covers both exception and error dict cases)
            if (
                llm_analysis.get('action') == 'HOLD' and (
                    'API Call Failed' in llm_analysis.get('risks', '') or
                    'JSON Parse Failed' in llm_analysis.get('risks', '')
                )
            ):
                raise RuntimeError('LLM unavailable or failed, using fallback.')
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
                # Let the LLM (if available) suggest a fallback size, else use default logic
                suggested_size = None
                if 'fallback_size' in llm_analysis and isinstance(llm_analysis['fallback_size'], (int, float)):
                    suggested_size = llm_analysis['fallback_size']
                if sma20 and current_price > sma20 and rsi and rsi < 70:
                    fallback_decision = "BUY"
                    fallback_sentiment = 50
                    fallback_size = suggested_size if suggested_size is not None else 1
                    fallback_reason = "Price above SMA20 and RSI < 70."
                elif sma20 and current_price < sma20 and rsi and rsi > 30:
                    fallback_decision = "SELL"
                    fallback_sentiment = -50
                    fallback_size = suggested_size if suggested_size is not None else 1
                    fallback_reason = "Price below SMA20 and RSI > 30."
            llm_analysis = {
                'sentiment': fallback_sentiment,
                'action': fallback_decision,
                'reasoning': fallback_reason,
                'risks': 'LLM unavailable. Used fallback technicals.',
                'raw_prompt_sent': '',
                'size': fallback_size  # Pass fallback_size for downstream use
            }

        # --- USE make_trading_decision for risk-managed, position-sized trade decision ---
        trade_decision = make_trading_decision(
            symbol=symbol,
            llm_analysis_result=llm_analysis,
            current_portfolio=portfolio_state,
            risk_settings=portfolio_state.get('RISK_SETTINGS', RISK_SETTINGS),
            atr_value=atr_value
        )

        # STEP 10: Trade Execution (Simulated or Real)
        trade_outcome_pl = 0.0  # Default for HOLD
        prev_holdings = portfolio_state.get('holdings', {}).copy()  # Capture before trade
        if trade_decision['decision'] in ["BUY", "SELL"] and trade_decision['size'] > 0:
            print(f"Executing trade for {symbol}: {trade_decision['decision']} {trade_decision['size']}")
            trade_result = execute_trade(alpaca_symbol(symbol), trade_decision['decision'], trade_decision['size'])

            # After executing a new trade (buy/sell), place a stop-loss order
            if trade_result.get('status') == 'success':
                # Determine stop-loss percent from risk settings
                stop_loss_pct = portfolio_state.get('RISK_SETTINGS', RISK_SETTINGS).get('max_risk_per_trade_percent', 0.01)
                stop_loss_pct = stop_loss_pct / 100.0
                # Get entry price and qty from trade details
                entry_price = trade_result.get('filled_avg_price', current_price)  # Fallback to current_price if missing
                qty = trade_decision['size']
                side = trade_decision['decision'].lower()
                # Use Alpaca symbol format for stop-loss order
                place_stop_loss_order(alpaca_symbol(symbol), qty, side, entry_price, stop_loss_pct)

            # STEP 11: Portfolio & State Update (after trade)
            updated_alpaca_account = get_account_info()
            updated_alpaca_positions = get_open_positions()
            if updated_alpaca_account:
                updated_prices = {symbol: pos['current_price'] for symbol, pos in updated_alpaca_positions.items()}
                updated_prices.update(latest_prices)
                portfolio_state = update_portfolio_from_alpaca(portfolio_state, updated_alpaca_account, updated_alpaca_positions, updated_prices)
            else:
                print("Warning: Could not fetch updated Alpaca info after trade. Portfolio state might be stale.")
                sys.exit(1)  # Exit if we can't get account info, as we need it for trading decisions

            # --- Update trade outcomes for closed positions ---
            update_trade_outcomes_on_close(prev_holdings, portfolio_state.get('holdings', {}), portfolio_state['trade_log'], latest_prices=portfolio_state.get('current_prices', {}))

            # --- Real P&L Calculation ---
            # If the position was closed (i.e., a SELL and we had a previous BUY), calculate realized P&L
            # If the position is still open, calculate unrealized P&L
            # We'll use the last two trades for this symbol to estimate realized P&L for a round-trip
            ticker_trade_log = [t for t in portfolio_state['trade_log'] if t.get('symbol') == symbol]
            if len(ticker_trade_log) >= 2:
                prev_trade = ticker_trade_log[-2]
                if prev_trade['action'] == 'BUY' and trade_decision['decision'] == 'SELL':
                    # Realized P&L for a round-trip (BUY then SELL)
                    buy_price = prev_trade['price']
                    sell_price = current_price
                    qty = min(prev_trade['size'], trade_decision['size'])
                    trade_outcome_pl = (sell_price - buy_price) * qty
                elif prev_trade['action'] == 'SELL' and trade_decision['decision'] == 'BUY':
                    # Realized P&L for a round-trip (SELL then BUY, e.g., short covering)
                    sell_price = prev_trade['price']
                    buy_price = current_price
                    qty = min(prev_trade['size'], trade_decision['size'])
                    trade_outcome_pl = (sell_price - buy_price) * qty
                else:
                    # Otherwise, unrealized P&L for open position
                    avg_entry_price = trade_result.get('filled_avg_price', current_price)
                    trade_outcome_pl = (current_price - avg_entry_price) * trade_decision['size']
            else:
                # Only one trade for this symbol, so unrealized P&L
                avg_entry_price = trade_result.get('filled_avg_price', current_price)
                trade_outcome_pl = (current_price - avg_entry_price) * trade_decision['size']

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

        else:
            print(f"No trade executed for {symbol}. Reason: {trade_decision['reason']}")
            # trade_outcome_pl remains 0.0 for HOLD

        # Log the experience for both executed trades and holds
        add_experience_record(
            symbol=symbol,
            market_state=current_market_state_snapshot,
            llm_input_prompt=llm_analysis.get('raw_prompt_sent', ''),
            llm_output_analysis=llm_analysis,
            action_taken=trade_decision['decision'],
            trade_size=trade_decision.get('size', 0),
            decision_reason=trade_decision['reason'],
            trade_outcome_pl=trade_outcome_pl
        )

        # STEP 12: Log every decision with add_decision_to_history
        add_decision_to_history(
            portfolio_state,
            symbol,
            trade_decision['decision'],
            trade_decision.get('llm_sentiment', 0),
            llm_analysis.get('reasoning', ''),
            llm_analysis.get('risks', '')
        )

        # Save state after each symbol's decision/execution
        save_portfolio_state(portfolio_state)

    # STEP 13: Reflection & Learning (Periodically)
    if portfolio_state['cycle_count'] % LLM_REFLECTION_INTERVAL_CYCLES == 0:
        print(f"\n--- Performing LLM Reflection (Cycle {portfolio_state['cycle_count']}) ---")
        # The reflect_and_learn function from ai_brain.py
        # will now potentially use the updated trade log which includes P&L,
        # or you could modify it to directly summarize the experience_log.
        reflect_and_learn(model, portfolio_state)
        add_llm_reflection_log(portfolio_state, {"cycle": portfolio_state['cycle_count'], "reflection_performed": True}) # Log that reflection occurred
        save_portfolio_state(portfolio_state)
        # --- Adaptive Learning: Call learning_agent after reflection ---
        analyze_llm_reflections()
        # --- Apply adaptive parameters (stop-loss, cooldown, position sizing) ---
        # These will be used in the next cycle automatically as they are loaded from state

    # STEP 14: Adaptive Cooldown (if set, skip trading for that many cycles after a loss)
    cooldown_cycles = portfolio_state.get('RISK_SETTINGS', {}).get('cooldown_cycles', 0)
    last_loss_cycle = portfolio_state.get('RISK_SETTINGS', {}).get('last_loss_cycle', -1000)
    if cooldown_cycles > 0 and (portfolio_state['cycle_count'] - last_loss_cycle) < cooldown_cycles:
        print(f"Cooldown active. Skipping trading for {cooldown_cycles - (portfolio_state['cycle_count'] - last_loss_cycle)} more cycles.")
        return

    # STEP 15: Print cycle complete
    print(f"--- Trading Cycle Complete: {datetime.now().isoformat()} ---")


def alpaca_symbol(symbol):
    """Convert crypto symbols from '-' to '/' for Alpaca, leave stocks unchanged."""
    if symbol.endswith("-USD"):
        return symbol.replace("-", "/")
    return symbol


def main():
    loop = asyncio.get_event_loop()
    news_task = start_alpaca_news_ws_background(loop)
    try:
        print(f"Running trading bot in {'PAPER TRADING' if BASE_URL == 'https://paper-api.alpaca.markets' else 'LIVE TRADING'} mode.") 
        while True:
            main_trading_cycle()

            print(f"Waiting for {CYCLE_INTERVAL_SECONDS} seconds until next cycle...")
            time.sleep(CYCLE_INTERVAL_SECONDS)
            
    except KeyboardInterrupt:
        print("\nShutting down Alpaca News WebSocket...")
        news_task.cancel()
        try:
            loop.run_until_complete(news_task)
        except:
            pass
        loop.close()
    except Exception as e:
        print(f"Fatal error: {e}")
        safe_shutdown()


if __name__ == "__main__":
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
    
    main()