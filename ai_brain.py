import google.generativeai as genai
import os
import pandas as pd
from dotenv import load_dotenv
import json
from indicators import calculate_indicators

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)

# Initialize the Gemini model
model = genai.GenerativeModel('models/gemini-1.5-flash-latest')

def get_llm_analysis(symbol, current_price, recent_history_df, news_df, past_trades_summary=""):
    """
    Gets Gemini's analysis, sentiment, and suggested action for a given asset.
    """
    # Prepare recent history string
    history_str = ""
    if not recent_history_df.empty:
        history_str = recent_history_df[['Close', 'SMA_20', 'RSI']].to_string(index=True)

    # Prepare news headlines string
    news_str = ""
    if not news_df.empty:
        news_str = "\n".join([f"- {row['title']} (Source: {row['source']})" for index, row in news_df.iterrows()])

    # Construct the prompt for Gemini
    prompt = f"""
    You are an expert financial analyst. Analyze the following information for {symbol}:

    Current Price: ${current_price:.2f}

    Recent Price History & Technical Indicators (last few days/weeks, simplified):
    {history_str}

    Recent News Headlines:
    {news_str}

    Past Trading Performance/Reflections (my AI's previous actions/outcomes for this asset):
    {past_trades_summary if past_trades_summary else "No specific past performance to reflect on yet."}

    Based on this data, provide your response in the following strict JSON format (do not include any explanation, ```json, or text outside the JSON):
    {{
      "sentiment": <integer from -100 to 100>,
      "action": "BUY" | "SELL" | "HOLD",
      "reasoning": <string>,
      "risks": <string>
    }}
    """

    try:
        response = model.generate_content(prompt)
        analysis_text = response.text.strip()
        print(f"\n--- Gemini Analysis for {symbol} ---")
        print(analysis_text)
        print("--------------------------------------")

        # Parse the JSON response
        try:
            # Try to extract the first JSON object if Gemini returns extra text or markdown
            import re
            json_match = re.search(r'\{[\s\S]*?\}', analysis_text)
            if json_match:
                json_str = json_match.group(0)
            else:
                json_str = analysis_text
            parsed = json.loads(json_str)
            sentiment = int(parsed.get("sentiment", 0))
            action = parsed.get("action", "HOLD").upper()
            if action not in ['BUY', 'SELL', 'HOLD']:
                action = 'HOLD'
            reasoning = parsed.get("reasoning", "")
            risks = parsed.get("risks", "")
        except Exception as e:
            print(f"Error parsing Gemini JSON: {e}")
            sentiment = 0
            action = "HOLD"
            reasoning = analysis_text
            risks = "JSON Parse Failed"

        return {
            "sentiment": sentiment,
            "action": action,
            "reasoning": reasoning,
            "risks": risks,
            "raw_response": analysis_text
        }

    except Exception as e:
        print(f"Error querying Gemini for {symbol}: {e}")
        return {"sentiment": 0, "action": "HOLD", "reasoning": f"Error: {e}", "risks": "API Call Failed"}

# (Assuming LLM analysis, portfolio manager functions are available)

def reflect_and_learn(llm_model, portfolio_state):
    """
    Feeds past trade outcomes to Gemini for reflection and learning.
    """
    trade_log = portfolio_state.get("trade_log", [])
    if not trade_log:
        print("No trades in log to reflect on.")
        return

    # Take a subset of recent trades for reflection to save on tokens/quota
    recent_trades_for_reflection = trade_log[-5:] # Reflect on last 5 trades

    reflection_prompt = f"""
    You are an expert trading AI. Review the following past trades and your previous reasoning.
    Analyze the outcomes and identify areas for improvement in your decision-making.

    --- My Recent Trades ---
    """
    for trade in recent_trades_for_reflection:
        reflection_prompt += f"Symbol: {trade.get('symbol')}, Action: {trade.get('action')}, " \
                             f"Size: {trade.get('size')}, Price: {trade.get('price')}, " \
                             f"Outcome: [Needs P&L here from actual trade settlement or close], " \
                             f"My Reasoning: {trade.get('llm_reasoning', 'N/A')}\n"

    reflection_prompt += """
    --- Reflection Questions ---
    1. What patterns or insights can you identify from these outcomes (successes or failures)?
    2. Where did your previous reasoning align with the outcome, and where did it diverge?
    3. What could be improved in your future analysis or risk assessment?
    4. Based on this, suggest any adjustments to the overall trading strategy or factors to prioritize.

    Provide a concise but insightful reflection.
    """

    try:
        response = llm_model.generate_content(reflection_prompt)
        reflection_text = response.text
        print("\n--- Gemini Reflection ---")
        print(reflection_text)
        print("-------------------------")

        # Save the reflection
        reflection_details = {
            "trades_reviewed": recent_trades_for_reflection,
            "llm_reflection": reflection_text
        }

        add_llm_reflection_log(portfolio_state, reflection_details)
    
    except Exception as e:
        print(f"Error during LLM reflection: {e}")
    
    def add_llm_reflection_log(portfolio_state, reflection_details):
        """
        Adds the LLM reflection details to the portfolio state's reflection log.
        """
        if "llm_reflection_log" not in portfolio_state:
            portfolio_state["llm_reflection_log"] = []
        portfolio_state["llm_reflection_log"].append(reflection_details)

# This reflection step would be called periodically in your main loop.
# For example:
# if __name__ == "__main__":
#    # Assuming you have a loaded portfolio_state and initialized model
#    current_state = load_portfolio_state()
#    # Need to update trade log with actual P&L before reflection for best results
#    reflect_and_learn(model, current_state)
#    save_portfolio_state(current_state)

if __name__ == "__main__":
    # List available Gemini models before running analysis
    print("Available Gemini models:")
    for m in genai.list_models():
        print(f"- {getattr(m, 'name', m)}")
    print("\n--- Running analysis with selected model ---\n")
    
    # Example usage for both AAPL and BTC-USD (or any available symbol)
    from data_collector import get_historical_trade_data, get_financial_news
    symbols = ["AAPL", "BTC-USD", "ETH-USD", "GOOGL", "AMZN"]  # Add more symbols as needed
    try:
        for symbol in symbols:
            try:
                # Use data_collector methods to fetch data
                data = get_historical_trade_data(symbol)
                data = calculate_indicators(data)
                news = get_financial_news(query=f"{symbol} stock", page_size=5)
            except Exception as e:
                print(f"Error fetching data for {symbol}: {e}. Skipping.")
                continue

            if data is None or data.empty:
                print(f"No historical data for {symbol}, skipping.")
                continue
            if news is None or news.empty:
                print(f"No news data for {symbol}, skipping.")
                continue

            current_price = data['Close'].iloc[-1]
            recent_history = data.tail(10)
            # Use only news related to the symbol (if possible)
            news_specific = news[news['title'].str.contains(symbol.split('-')[0], case=False, na=False)]
            news_for_llm = news_specific.head(5)

            gemini_result = get_llm_analysis(
                symbol=symbol,
                current_price=current_price,
                recent_history_df=recent_history,
                news_df=news_for_llm,
                past_trades_summary=""  # You can load or pass past trade summaries here
            )
            print(f"\nParsed Gemini Result for {symbol}:")
            print(f"Sentiment: {gemini_result['sentiment']}")
            print(f"Action: {gemini_result['action']}")
            print(f"Risks: {gemini_result['risks']}")

    except Exception as e:
        print(f"An error occurred during Gemini batch execution: {e}")