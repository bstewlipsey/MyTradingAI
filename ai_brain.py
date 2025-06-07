import google.generativeai as genai
import os
import pandas as pd
from dotenv import load_dotenv
import re
import json as _json
from indicators import calculate_indicators
from portfolio_manager import add_llm_reflection_log, load_portfolio_state, save_portfolio_state
from config import LLM_PROMPT_TEMPLATE, RISK_MANAGEMENT_VARS
from datetime import datetime

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)

# Initialize the Gemini model
model = genai.GenerativeModel('models/gemini-1.5-flash-latest')

def get_llm_analysis(symbol, current_price, recent_history_df, news_df, past_trades_summary=""):
    """
    Gets Gemini's analysis, sentiment, and suggested action for a given asset.
    """
    # Always use the latest prompt template from state
    state = load_portfolio_state()
    prompt_template = state.get("llm_prompt_template", LLM_PROMPT_TEMPLATE)

    # Prepare recent history string
    history_str = ""
    if not recent_history_df.empty:
        # Add more indicators for LLM prompt
        indicator_cols = [col for col in recent_history_df.columns if col not in ["Date"]]
        history_str = recent_history_df[indicator_cols].to_string(index=True)

    # Dynamically use all indicator columns (exclude 'Date' and non-numeric columns)
    if not recent_history_df.empty:
        indicator_cols = [col for col in recent_history_df.columns if col not in ["Date"] and pd.api.types.is_numeric_dtype(recent_history_df[col])]
        # Add summary of most recent values for all indicators
        last_row = recent_history_df.iloc[-1]
        indicator_summary = [f"{ind}: {last_row[ind]:.2f}" for ind in indicator_cols if ind in last_row and pd.notnull(last_row[ind])]
        if indicator_summary:
            history_str += "\n\nLatest Indicator Values: " + ", ".join(indicator_summary)
        # Add trend lines for all indicators
        trend_lines = []
        for ind in indicator_cols:
            if ind in recent_history_df.columns:
                last_vals = recent_history_df[ind].tail(5).tolist()
                if len(last_vals) == 5 and all(pd.notnull(last_vals)):
                    if last_vals[-1] > last_vals[0]:
                        trend = "rising"
                    elif last_vals[-1] < last_vals[0]:
                        trend = "falling"
                    else:
                        trend = "flat"
                    trend_lines.append(f"{ind} trend over last 5 bars: {trend}")
        if trend_lines:
            history_str += "\n" + "\n".join(trend_lines)

    # Prepare news headlines string
    news_str = ""
    if not news_df.empty:
        news_str = "\n".join([f"- {row['title']} (Source: {row.get('source','N/A')})" for index, row in news_df.iterrows()])

    # Add a summary of the most recent news headline for LLM prompt clarity
    if not news_df.empty:
        latest_news = news_df.iloc[0]
        news_str += f"\n\nMost recent headline: {latest_news['title']} (Published: {latest_news.get('created_at', 'N/A')})"

    # --- LLM Prompt Improvements ---
    prompt = prompt_template.format(
        symbol=symbol,
        current_price=current_price,
        history_str=history_str,
        news_str=news_str,
        past_trades_summary=past_trades_summary if past_trades_summary else "No specific past performance to reflect on yet."
    )

    try:
        response = model.generate_content(prompt)
        analysis_text = response.text.strip()
        print(f"\n--- Gemini Analysis for {symbol} ---")
        print(analysis_text)
        print("--------------------------------------")

        # Parse the JSON response
        try:
            # Try to extract the first JSON object if Gemini returns extra text or markdown
            json_match = re.search(r'\{[\s\S]*?\}', analysis_text)
            if json_match:
                json_str = json_match.group(0)
            else:
                json_str = analysis_text
            result = _json.loads(json_str)
            result['raw_prompt_sent'] = prompt
            return result
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
            "raw_response": analysis_text,
            "raw_prompt_sent": prompt
        }

    except Exception as e:
        print(f"Error querying Gemini for {symbol}: {e}")
        return {"sentiment": 0, "action": "HOLD", "reasoning": f"Error: {e}", "risks": "API Call Failed", "raw_prompt_sent": prompt}

# (Assuming LLM analysis, portfolio manager functions are available)

def reflect_and_learn(llm_model, portfolio_state):
    """
    Feeds past trade outcomes to Gemini for reflection and learning.
    After reflection, parses for prompt/parameter suggestions and updates state if needed.
    """
    trade_log = portfolio_state.get("trade_log", [])
    if not trade_log:
        print("No trades in log to reflect on.")
        return

    # Take a subset of recent trades for reflection to save on tokens/quota
    recent_trades_for_reflection = trade_log[-5:] # Reflect on last 5 trades

    # Build the allowed parameters section dynamically
    allowed_params = {k: v['range'] for k, v in RISK_MANAGEMENT_VARS.items() if v.get('use_in_llm')}
    allowed_params_str = '\n'.join([
        f"- {k} ({v[0]} to {v[1]})" for k, v in allowed_params.items()
    ])

    reflection_prompt = f"""
    You are an expert trading AI. Review the following past trades and your previous reasoning.
    Analyze the outcomes and identify areas for improvement in your decision-making.

    --- My Recent Trades ---
    """
    for trade in recent_trades_for_reflection:
        reflection_prompt += f"Symbol: {trade.get('symbol')}, Action: {trade.get('action')}, " \
                             f"Size: {trade.get('size')}, Price: {trade.get('price')}, " \
                             f"Outcome: Realized P&L: ${trade.get('trade_outcome_pl', 0):.2f}, " \
                             f"My Reasoning: {trade.get('llm_reasoning', 'N/A')}\n"

    reflection_prompt += f"""
    --- Reflection Questions ---
    1. What patterns or insights can you identify from these outcomes (successes or failures)?
    2. Where did your previous reasoning align with the outcome, and where did it diverge?
    3. What could be improved in your future analysis or risk assessment?
    4. Based on this, suggest any adjustments to the overall trading strategy or factors to prioritize.

    Provide a concise but insightful reflection.

    You may suggest changes to the following parameters only (with suggested value ranges):
{allowed_params_str}

    If you believe a new risk or strategy variable should be added to the system (for example, a new threshold, a new type of limit, or a new adaptive rule), suggest it in a field called "new_variable_suggestions" in your JSON output. For each, provide:
      - variable_name: a concise name for the new variable
      - description: what it controls and why it would help
      - suggested_range: a reasonable min/max or valid values
      - initial_value: a recommended starting value
      - example_usage: a one-sentence example of how it would be used in the system

    If you believe a new variable should be added to the LLM's own prompt, memory, or reasoning process (for example, a new context feature, a new type of input, or a new self-reflection metric), suggest it in a field called "llm_self_variable_suggestions" in your JSON output. For each, provide:
      - variable_name: a concise name for the new LLM self-variable
      - description: what it represents and how it could improve LLM performance
      - suggested_range: a reasonable min/max or valid values
      - initial_value: a recommended starting value
      - example_usage: a one-sentence example of how the LLM would use this variable in its own reasoning or prompt

    At the end, output a single JSON object with any suggested changes, for example:
    {{
      "prompt_suggestion": "...new prompt template...",
      "param_suggestions": {{
        "max_risk_per_trade_percent": 0.03,
        "min_sentiment_for_buy": 55
      }},
      "new_variable_suggestions": [
        {{
          "variable_name": "max_drawdown_per_week",
          "description": "Maximum portfolio drawdown allowed per week before pausing trading.",
          "suggested_range": [0.01, 0.10],
          "initial_value": 0.05,
          "example_usage": "If weekly drawdown exceeds max_drawdown_per_week, halt new trades until review."
        }}
      ],
      "llm_self_variable_suggestions": [
        {{
          "variable_name": "reflection_depth",
          "description": "How many past cycles the LLM should consider in its self-reflection.",
          "suggested_range": [1, 20],
          "initial_value": 5,
          "example_usage": "Set reflection_depth to 10 to consider a longer history in prompt construction."
        }}
      ]
    }}
    If you have no suggestions, output an empty JSON object: {{}}
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

        # --- Parse for JSON suggestions ---
        json_match = re.search(r'\{[\s\S]*\}', reflection_text)
        suggestions = {}
        if json_match:
            try:
                suggestions = _json.loads(json_match.group(0))
            except Exception as e:
                print(f"Error parsing LLM JSON suggestions: {e}")
        prompt_suggestion = suggestions.get('prompt_suggestion')
        param_suggestions = suggestions.get('param_suggestions', {})
        # --- New: Capture any new variable suggestions ---
        new_vars = suggestions.get('new_variable_suggestions', {})
        if new_vars:
            if 'llm_new_variable_suggestions' not in portfolio_state:
                portfolio_state['llm_new_variable_suggestions'] = []
            portfolio_state['llm_new_variable_suggestions'].append({
                'timestamp': datetime.now().isoformat(),
                'suggestions': new_vars,
                'reflection_excerpt': reflection_text[:200]
            })
        # --- New: Capture any LLM self-variable suggestions ---
        llm_self_vars = suggestions.get('llm_self_variable_suggestions', {})
        if llm_self_vars:
            if 'llm_self_variable_suggestions' not in portfolio_state:
                portfolio_state['llm_self_variable_suggestions'] = []
            portfolio_state['llm_self_variable_suggestions'].append({
                'timestamp': datetime.now().isoformat(),
                'suggestions': llm_self_vars,
                'reflection_excerpt': reflection_text[:200]
            })
        # Update prompt template if suggested
        if prompt_suggestion:
            portfolio_state['llm_prompt_template'] = prompt_suggestion
            if 'adaptation_log' not in portfolio_state:
                portfolio_state['adaptation_log'] = []
            portfolio_state['adaptation_log'].append({
                'timestamp': datetime.now().isoformat(),
                'type': 'prompt_update',
                'new_prompt': prompt_suggestion,
                'reason': 'LLM reflection suggestion',
                'reflection_excerpt': str(prompt_suggestion)
            })
        # Update parameters if suggested (with min/max safeguards)
        minmax = allowed_params
        for k, v in param_suggestions.items():
            if k in minmax:
                minv, maxv = minmax[k]
                try:
                    val = float(v)
                    val = max(minv, min(maxv, val))
                    if 'RISK_SETTINGS' not in portfolio_state:
                        portfolio_state['RISK_SETTINGS'] = {}
                    portfolio_state['RISK_SETTINGS'][k] = val
                    portfolio_state['adaptation_log'].append({
                        'timestamp': datetime.now().isoformat(),
                        'type': 'param_update',
                        'param': k,
                        'new_value': val,
                        'reason': 'LLM reflection suggestion',
                        'reflection_excerpt': f'{k}={v}'
                    })
                except Exception:
                    continue
        save_portfolio_state(portfolio_state)
    except Exception as e:
        print(f"Error during LLM reflection: {e}")

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