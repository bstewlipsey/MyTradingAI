
import datetime
import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
# Ensure you have your API keys set up, e.g., in a .env file
# Or replace os.getenv with your actual keys for this test
# from dotenv import load_dotenv
# load_dotenv()
# ALPACA_API_KEY = os.getenv("ALPACA_API_KEY")
# ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")

# --- REPLACE WITH YOUR ACTUAL ALPACA API KEYS ---
# For a quick test, you can hardcode them here, but for your bot,
# always load from environment variables or a config file.
# ------------------------------------------------

def run_news_api_test():
    # Get current time in UTC
    current_time_utc = datetime.datetime.now(datetime.timezone.utc)
    # Set start time to 30 minutes ago
    start_time_utc = current_time_utc - datetime.timedelta(minutes=30)

    # Format to RFC-3339 (e.g., '2025-06-06T00:00:00Z')
    start_str = start_time_utc.isoformat(timespec='seconds').replace('+00:00', 'Z')
    end_str = current_time_utc.isoformat(timespec='seconds').replace('+00:00', 'Z')

    # Use active symbols that are likely to have recent news
    # BTCUSD and ETHUSD are 24/7; AAPL and NVDA are typically active during market hours
    test_symbols = "AAPL,NVDA,BTCUSD,ETHUSD"
    limit = 5 # Request up to 5 articles

    url = (f"https://data.alpaca.markets/v1beta1/news?"
           f"start={start_str}&end={end_str}&sort=desc&symbols={test_symbols}&limit={limit}")

    headers = {
        "accept": "application/json",
        "APCA-API-KEY-ID": ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY
    }

    print(f"--- Running Alpaca News API Test ---")
    print(f"Querying for news from {start_str} to {end_str} for symbols: {test_symbols}")

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
        news_data = response.json()

        print(f"\nAPI Response Status: {response.status_code} OK")

        if news_data and 'news' in news_data and len(news_data['news']) > 0:
            print(f"Found {len(news_data['news'])} news articles:")
            print("-" * 40)
            for article in news_data['news']:
                print(f"  Headline: {article.get('headline', 'N/A')}")
                print(f"  Created At: {article.get('created_at', 'N/A')}")
                print(f"  Symbols: {', '.join(article.get('symbols', ['N/A']))}")
                print(f"  Source: {article.get('source', 'N/A')}")
                print("-" * 40)
        else:
            print("No news articles found for the specified period and symbols. This might mean:")
            print("  - Genuinely no news for these symbols in the last 30 minutes.")
            print("  - Your Alpaca plan does not provide real-time news.")
            print("  - The news coverage for these symbols is sparse.")
            print("Consider extending the time window (e.g., 1 hour) or trying during active market hours.")

    except requests.exceptions.HTTPError as e:
        print(f"HTTP Error: {e.response.status_code} - {e.response.text}")
        if e.response.status_code == 429:
            print("You hit the rate limit. Check Alpaca API documentation for rate limits.")
        elif e.response.status_code == 403:
            print("Authentication failed. Check your API Key and Secret Key.")
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")
    except json.JSONDecodeError:
        print(f"Failed to decode JSON response: {response.text}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

# Run the test
if __name__ == "__main__":
    run_news_api_test()