import unittest
import json
import os
from portfolio_manager import add_experience_record, load_experience_log
from datetime import datetime

class TestExperienceLog(unittest.TestCase):
    def setUp(self):
        # Remove the log if it exists for a clean test
        self.log_file = 'experience_log.json'
        if os.path.exists(self.log_file):
            os.remove(self.log_file)

    def test_add_and_load_experience_record(self):
        # Add a mock experience record
        add_experience_record(
            symbol="AAPL",
            market_state={"RSI": 55, "SMA_20": 150},
            llm_input_prompt="PROMPT TEXT",
            llm_output_analysis={"sentiment": 60, "action": "BUY", "reasoning": "Test", "risks": "None"},
            action_taken="BUY",
            trade_size=10,
            decision_reason="Test reason",
            trade_outcome_pl=100.0,
            timestamp=datetime.now().isoformat()
        )
        log = load_experience_log()
        self.assertEqual(len(log), 1)
        self.assertEqual(log[0]['symbol'], "AAPL")
        self.assertEqual(log[0]['action_taken'], "BUY")
        self.assertIn('llm_input_prompt', log[0])
        self.assertIn('llm_output_analysis', log[0])

if __name__ == '__main__':
    unittest.main()
