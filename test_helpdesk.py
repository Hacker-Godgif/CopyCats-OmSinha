"""
Unit Test Suite for Grounded Helpdesk Agent.
Verifies all 4 Definition of Done requirements:
1. Covered question returns cited answer with confidence >= 0.60.
2. Uncovered question returns escalated: true and a ticket stub.
3. Numeric claim check: no fee, %, or date in answer is missing from source text.
4. Output validates against SCHEMA.md HelpdeskAnswer shape.
"""

import unittest
from schema import HelpdeskAnswer, SchemaValidator
from helpdesk_agent import GroundedHelpdeskAgent, CONFIDENCE_THRESHOLD


class TestGroundedHelpdeskAgent(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.agent = GroundedHelpdeskAgent()

    # -------------------------------------------------------------
    # 1. COVERED QUESTION WITH CITATION & HIGH CONFIDENCE
    # -------------------------------------------------------------
    def test_covered_question_returns_cited_answer(self):
        query = "What is the fee for revaluation per subject?"
        res = self.agent.answer_query(query)

        self.assertFalse(res["escalated"])
        self.assertIsNone(res["ticket"])
        
        answer_data = res["answer"]
        self.assertGreaterEqual(answer_data["confidence"], CONFIDENCE_THRESHOLD)
        self.assertGreater(len(answer_data["sources"]), 0)
        self.assertIn("350", answer_data["answer"])
        self.assertIn("DOC-EXM-REV-2026", answer_data["sources"][0])

    # -------------------------------------------------------------
    # 2. UNCOVERED QUESTION RETURNS ESCALATED: TRUE & TICKET STUB
    # -------------------------------------------------------------
    def test_uncovered_question_escalates_and_generates_ticket(self):
        query = "What is the wifi password for the cafeteria server?"
        res = self.agent.answer_query(query)

        self.assertTrue(res["escalated"])
        self.assertIsNotNone(res["ticket"])
        
        ticket = res["ticket"]
        self.assertTrue(ticket["ticket_id"].startswith("TICKET-"))
        self.assertIn("cafeteria", ticket["question_summary"])

        answer_data = res["answer"]
        self.assertTrue(answer_data["needs_manual_review"])

    # -------------------------------------------------------------
    # 3. NUMERIC CLAIM SOURCE VERIFICATION
    # -------------------------------------------------------------
    def test_numeric_claims_present_in_source(self):
        query = "What is the fine for attendance condonation?"
        res = self.agent.answer_query(query)

        answer_data = res["answer"]
        answer_text = answer_data["answer"]

        full_source_doc = "UGC/AICTE Attendance & Condonation Regulations 2026 (DOC-ATT-2026), Section 4: Attendance & Condonation Under UGC/AICTE guidelines, 75% attendance is mandatory to appear in end-term examinations. Students with attendance between 65% and 75% are eligible for condonation upon payment of a fine of Rs 500 and submission of a valid medical certificate before 20/10/2026. Students below 65% are detained and not eligible for condonation."

        valid_numerics = GroundedHelpdeskAgent.verify_numeric_claims(answer_text, full_source_doc)
        self.assertTrue(valid_numerics, f"Numeric claim verification failed for answer: {answer_text}")

    # -------------------------------------------------------------
    # 4. SCHEMA CONFORMANCE FOR HELPDESKANSWER
    # -------------------------------------------------------------
    def test_helpdesk_schema_conformance(self):
        query = "What is the attendance requirement under UGC guidelines?"
        res = self.agent.answer_query(query)

        val_res = SchemaValidator.validate_helpdesk_answer(res["answer"])
        self.assertTrue(val_res["valid"], f"HelpdeskAnswer failed schema validation: {val_res['errors']}")


if __name__ == "__main__":
    unittest.main()
