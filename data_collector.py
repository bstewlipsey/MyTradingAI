import yfinance as yf
from newsapi import NewsApiClient
from config import NEWS_API_KEY  # Assuming you have a news API client set up
import pandas as pd # For data manipulation
import os



def get_historical_trade_data(symbol, period="1mo"):
    """Fetches historical stock data using yfinance."""
    try:
        stock = yf.Ticker(symbol)
        data = stock.history(period=period) # e.g., "1mo", "3mo", "1y"
        if not data.empty:
            print(f"Fetched {len(data)} rows for {symbol} over {period}.")
            # Save to a CSV for caching and future use
            data.to_csv(f"data/{symbol}_history.csv")
            return data
        else:
            print(f"No data found for {symbol} over {period}.")
            return pd.DataFrame() # Return empty DataFrame
    except Exception as e:
        print(f"Error fetching data for {symbol}: {e}")
        return pd.DataFrame()

def get_financial_news(query="stock market", language="en", sort_by="relevancy", page_size=3):
    """Fetches financial news headlines and summaries."""
    newsapi = NewsApiClient(api_key=NEWS_API_KEY)
    try:
        # Use 'everything' endpoint for more specific queries, 'top-headlines' for general
        articles = newsapi.get_everything(q=query,
                                          language=language,
                                          sort_by=sort_by,
                                          page_size=page_size) # Max 100 on free tier
        
        if articles['status'] == 'ok' and articles['articles']:
            print(f"Fetched {len(articles['articles'])} news articles for '{query}'.")
            # Store news for later use
            news_list = []
            for article in articles['articles']:
                news_list.append({
                    "title": article['title'],
                    "description": article['description'],
                    "url": article['url'],
                    "publishedAt": article['publishedAt'],
                    "source": article['source']['name']
                })
            news_df = pd.DataFrame(news_list)
            news_df.to_csv(f"data/{query.replace(' ', '_')}_news.csv", index=False)
            return news_df
        else:
            print(f"No news found for '{query}'.")
            return pd.DataFrame()
    except Exception as e:
        print(f"Error fetching news for '{query}': {e}")
        return pd.DataFrame()


if __name__ == "__main__":
    # Create a directory to save data
    os.makedirs("data", exist_ok=True)

    # Test with a few symbols
    symbols = ["BTC-USD"]  # Add more as needed

    for symbol in symbols:
        get_historical_trade_data(symbol, period="3mo") # Fetch 3 months of data
        get_financial_news(query=f"{symbol} stock", page_size=3)
    print(f"Historical trade data collection complete for {symbols}.")