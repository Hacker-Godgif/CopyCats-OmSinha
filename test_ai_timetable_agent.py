import os
import unittest
from unittest.mock import patch

from ai_timetable_agent import TimetableVisionAgent


class TestTimetableVisionAgentConfiguration(unittest.TestCase):
    @patch("ai_timetable_agent.TimetableVisionAgent._load_local_env", return_value=None)
    def test_openai_compatible_env_aliases_are_used(self, mock_load):
        with patch.dict(os.environ, {
            "OPENAI_API_KEY": "sk-test",
            "OPENAI_BASE_URL": "https://api.openai.com/v1",
            "OPENAI_MODEL": "gpt-4o-mini",
        }, clear=True):
            agent = TimetableVisionAgent()
            self.assertTrue(agent.configured)
            self.assertEqual(agent.api_key, "sk-test")
            self.assertEqual(agent.base_url, "https://api.openai.com/v1")
            self.assertEqual(agent.model, "gpt-4o-mini")


if __name__ == "__main__":
    unittest.main()
