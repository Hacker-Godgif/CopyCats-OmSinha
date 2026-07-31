"""
Indian Date Parsing Utility for StudyOS-India.
Handles DD/MM/YYYY, DD-MM-YYYY, written month dates (e.g. 15th Aug 2026, 15-August-2026), and ISO dates.
"""

import re
from datetime import datetime, date
from typing import Optional, Tuple

MONTH_MAP = {
    'jan': 1, 'january': 1,
    'feb': 2, 'february': 2,
    'mar': 3, 'march': 3,
    'apr': 4, 'april': 4,
    'may': 5,
    'jun': 6, 'june': 6,
    'jul': 7, 'july': 7,
    'aug': 8, 'august': 8,
    'sep': 9, 'september': 9, 'sept': 9,
    'oct': 10, 'october': 10,
    'nov': 11, 'november': 11,
    'dec': 12, 'december': 12
}


def parse_indian_date(date_str: str) -> Optional[str]:
    """
    Parses a date string into standard ISO format (YYYY-MM-DD).
    Returns None if parsing fails.
    """
    if not date_str or not isinstance(date_str, str):
        return None

    cleaned = date_str.strip()

    # 1. Check ISO YYYY-MM-DD
    iso_match = re.search(r'(\b\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b', cleaned)
    if iso_match:
        y, m, d = int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3))
        try:
            return date(y, m, d).isoformat()
        except ValueError:
            pass

    # 2. Check DD/MM/YYYY or DD-MM-YYYY or DD.MM.YYYY
    dd_mm_yyyy = re.search(r'(\b\d{1,2})[-/.](\d{1,2})[-/.](20\d{2}|\d{2})\b', cleaned)
    if dd_mm_yyyy:
        d, m, y_raw = int(dd_mm_yyyy.group(1)), int(dd_mm_yyyy.group(2)), dd_mm_yyyy.group(3)
        y = int(y_raw) if len(y_raw) == 4 else 2000 + int(y_raw)
        try:
            return date(y, m, d).isoformat()
        except ValueError:
            pass

    # 3. Check Written Month: e.g. "15th August 2026", "15 Aug 2026", "15-Aug-2026", "August 15, 2026"
    # Match day + ordinal + month + year
    written_1 = re.search(r'(\b\d{1,2})(?:st|nd|rd|th)?[\s\.\-]+([A-Za-z]+)[\s\.\-,]+(20\d{2})\b', cleaned, re.IGNORECASE)
    if written_1:
        d = int(written_1.group(1))
        m_str = written_1.group(2).lower()
        y = int(written_1.group(3))
        if m_str in MONTH_MAP:
            m = MONTH_MAP[m_str]
            try:
                return date(y, m, d).isoformat()
            except ValueError:
                pass

    # Match month + day + year: e.g. "August 15, 2026"
    written_2 = re.search(r'(\b[A-Za-z]+)[\s\.\-]+(\d{1,2})(?:st|nd|rd|th)?[\s\.\-,]+(20\d{2})\b', cleaned, re.IGNORECASE)
    if written_2:
        m_str = written_2.group(1).lower()
        d = int(written_2.group(2))
        y = int(written_2.group(3))
        if m_str in MONTH_MAP:
            m = MONTH_MAP[m_str]
            try:
                return date(y, m, d).isoformat()
            except ValueError:
                pass

    return None


def extract_dates_from_text(text: str) -> list[Tuple[str, str]]:
    """
    Extracts all candidate date strings and their parsed YYYY-MM-DD values from a line of text.
    Returns list of tuples: (matched_substring, YYYY-MM-DD_str).
    """
    results = []
    # Find numeric DD/MM/YYYY patterns
    numeric_matches = re.finditer(r'\b\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}\b', text)
    for m in numeric_matches:
        raw = m.group(0)
        parsed = parse_indian_date(raw)
        if parsed:
            results.append((raw, parsed))

    # Find written month patterns
    written_matches = re.finditer(r'\b\d{1,2}(?:st|nd|rd|th)?[\s\.\-]+[A-Za-z]+[\s\.\-,]+20\d{2}\b', text, re.IGNORECASE)
    for m in written_matches:
        raw = m.group(0)
        parsed = parse_indian_date(raw)
        if parsed:
            results.append((raw, parsed))

    written_matches_2 = re.finditer(r'\b[A-Za-z]+[\s\.\-]+\d{1,2}(?:st|nd|rd|th)?[\s\.\-,]+20\d{2}\b', text, re.IGNORECASE)
    for m in written_matches_2:
        raw = m.group(0)
        parsed = parse_indian_date(raw)
        if parsed:
            results.append((raw, parsed))

    return results
