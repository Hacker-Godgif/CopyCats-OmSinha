import unittest

from date_parser import parse_indian_date, extract_dates_from_text


class TestDateParser(unittest.TestCase):
    def test_parse_written_month_date(self):
        self.assertEqual(parse_indian_date("August 15, 2026"), "2026-08-15")

    def test_extract_dates_from_text_handles_written_month_dates(self):
        matches = extract_dates_from_text("The deadline is August 15, 2026")
        self.assertEqual(matches, [("August 15, 2026", "2026-08-15")])


if __name__ == "__main__":
    unittest.main()
