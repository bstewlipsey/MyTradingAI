# MyTradingAI

A fully automated trading bot for stocks and crypto using Alpaca, yFinance, NewsAPI, and LLM-based decision making.

## Features
- Automated data collection (price, news)
- Technical indicator calculation
- LLM-powered trade analysis and decision making
- Risk management and position sizing
- Experience logging and learning
- Supports both stocks and crypto (BTC, ETH)

## Setup
1. **Clone the repository**
2. **Install dependencies**
   ```sh
   pip install -r requirements.txt
   ```
3. **Configure environment variables**
   - Copy `.env.example` to `.env` and fill in your API keys:
     - `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `NEWS_API_KEY`, `GEMINI_API_KEY`
4. **Configure trading parameters**
   - Edit `config.py` to set trading symbols, intervals, risk settings, etc.
5. **Run the bot**
   ```sh
   python main_agent.py
   ```

## Configuration
All user-editable variables are now in `config.py`, including:
- Trading symbols
- Cycle intervals
- Lookback periods
- News and LLM settings
- Risk management parameters

## File Structure
- `main_agent.py` - Main trading loop
- `config.py` - All configuration variables
- `data_collector.py` - Data and news fetching
- `metrics.py` - Technical metrics
- `ai_brain.py` - LLM analysis and learning
- `decision_maker.py` - Trade decision logic
- `trade_executor.py` - Alpaca trade execution
- `portfolio_manager.py` - Portfolio and log management
- `experience_learner.py` - Experience-based learning

## Notes
- All data, logs, and sensitive files are excluded from git via `.gitignore`.
- For crypto, use symbols like `BTC-USD` in config; the bot will convert to `BTC/USD` for Alpaca.

## Disclaimer
This project is for educational purposes only. Use at your own risk. Trading involves risk of loss.
