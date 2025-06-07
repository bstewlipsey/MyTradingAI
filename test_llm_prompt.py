import unittest
import pandas as pd
from ai_brain import get_llm_analysis

class TestLLMPrompt(unittest.TestCase):
    def test_llm_prompt_structure(self):
        # Minimal DataFrame for indicators
        df = pd.DataFrame({
            'SMA_20': [150, 151, 152, 153, 154],
            'RSI': [60, 62, 65, 68, 70],
            'MACD_12_26_9': [1, 1.2, 1.3, 1.4, 1.5],
            'BBL_5_2.0': [140, 141, 142, 143, 144],
            'BBU_5_2.0': [160, 161, 162, 163, 164],
            'OBV': [1000, 1100, 1200, 1300, 1400],
            'ATR': [2, 2.1, 2.2, 2.3, 2.4]
        })
        news_df = pd.DataFrame({
            'title': ['Stock surges on earnings'],
            'source': ['Reuters'],
            'created_at': ['2024-01-01T10:00:00Z']
        })
        # Call get_llm_analysis and check prompt is present
        result = get_llm_analysis(
            symbol="AAPL",
            current_price=155.0,
            recent_history_df=df,
            news_df=news_df,
            past_trades_summary=""
        )
        self.assertIn('raw_prompt_sent', result)
        self.assertIn('Current Price', result['raw_prompt_sent'])
        self.assertIn('AAPL', result['raw_prompt_sent'])
        self.assertIn('Latest Indicator Values', result['raw_prompt_sent'])
        self.assertIn('Most recent headline', result['raw_prompt_sent'])

if __name__ == '__main__':
    unittest.main()
