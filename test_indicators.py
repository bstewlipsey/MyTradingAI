import unittest
import pandas as pd
from indicators import calculate_indicators

class TestIndicators(unittest.TestCase):
    def setUp(self):
        # Create a longer DataFrame to ensure MACD columns are generated
        data = {
            'Open': [100 + i for i in range(40)],
            'High': [101 + i for i in range(40)],
            'Low': [99 + i for i in range(40)],
            'Close': [100 + i for i in range(40)],
            'Volume': [1000 + 10 * i for i in range(40)]
        }
        self.df = pd.DataFrame(data)
        self.df.index = pd.date_range(start='2024-01-01', periods=40, freq='D')

    def test_calculate_indicators(self):
        result = calculate_indicators(self.df.copy())
        print("Columns after indicator calculation:", result.columns.tolist())
        print(result.head())
        # Check that key indicators are present (except MACD, which is checked below)
        for col in ['SMA_20', 'RSI', 'BBL_5_2.0', 'BBU_5_2.0', 'OBV', 'ATR']:
            self.assertIn(col, result.columns)
        # MACD: check for any column that starts with 'MACD'
        macd_cols = [c for c in result.columns if c.startswith('MACD')]
        self.assertTrue(len(macd_cols) > 0, "No MACD columns found")
        # Check that the output DataFrame is not empty
        self.assertFalse(result.empty)

if __name__ == '__main__':
    unittest.main()
