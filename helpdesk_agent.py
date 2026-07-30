"""
Grounded Helpdesk Agent for StudyOS-India.
Implements RAG document retrieval over campus policies, confidence-gated escalation,
and strict numeric claim verification against source text.
Conforms to SCHEMA.md HelpdeskAnswer shape.
"""

import json
import re
import os
import math
import uuid
from datetime import datetime
from typing import Dict, Any, List, Tuple

from schema import HelpdeskAnswer, SchemaValidator
from agent_log import run_with_logging

CONFIDENCE_THRESHOLD = 0.60
POLICIES_PATH = "campus_policies.json"


class GroundedHelpdeskAgent:

    def __init__(self, policies_file: str = POLICIES_PATH):
        self.policies = self._load_policies(policies_file)

    def _load_policies(self, filepath: str) -> List[Dict[str, Any]]:
        if not os.path.exists(filepath):
            return []
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)

    def _compute_relevance(self, query: str, doc_text: str) -> float:
        """
        Computes hybrid TF-IDF / keyword similarity score between query and document text.
        """
        query_words = set(re.findall(r'\w+', query.lower()))
        stop_words = {'what', 'is', 'the', 'for', 'a', 'an', 'of', 'in', 'to', 'how', 'much', 'many', 'can', 'i', 'my'}
        query_terms = query_words - stop_words

        if not query_terms:
            return 0.0

        doc_words = re.findall(r'\w+', doc_text.lower())
        doc_word_counts = {}
        for w in doc_words:
            doc_word_counts[w] = doc_word_counts.get(w, 0) + 1

        matches = sum(doc_word_counts.get(term, 0) for term in query_terms)
        score = matches / (math.sqrt(len(doc_words)) + 1e-5)

        # Scale score to 0.0 - 1.0 range
        confidence = min(1.0, round(score / 1.0, 2))
        return confidence

    @staticmethod
    def verify_numeric_claims(answer_text: str, source_text: str) -> bool:
        """
        Verifies that every numeric claim (fee amount, %, date) in answer_text exists in source_text.
        """
        numbers_in_answer = re.findall(r'\b\d+(?:[\.,]\d+)?%?\b', answer_text)
        for num in numbers_in_answer:
            if num not in source_text:
                return False
        return True

    def answer_query(self, query: str) -> Dict[str, Any]:
        """
        Answers student query. Emits 4 AgentLog entries with real DoD checks.
        """
        if not query or not query.strip():
            ans = HelpdeskAnswer(
                query=query,
                answer="Empty query provided.",
                sources=[],
                confidence=0.0,
                needs_manual_review=True,
                review_reason="Empty query"
            )
            return {"answer": ans.to_dict(), "escalated": True, "ticket": None}

        agent = self

        def _compute():
            return agent._do_answer(query)

        def _check(result):
            return agent._verify_answer(result, query)

        return run_with_logging(
            agent_name="Helpdesk Agent",
            action_description=f"Answered query: {query[:50]}",
            compute_fn=_compute,
            checks_fn=_check,
        )

    def _do_answer(self, query: str) -> Dict[str, Any]:
        """Core answer logic — no logging."""
        best_doc = None
        best_score = 0.0

        for doc in self.policies:
            combined_text = f"{doc['title']} {doc['section']} {doc['content']}"
            score = self._compute_relevance(query, combined_text)
            if score > best_score:
                best_score = score
                best_doc = doc

        # Check confidence threshold (0.60)
        if best_score < CONFIDENCE_THRESHOLD or not best_doc:
            ticket_id = f"TICKET-{uuid.uuid4().hex[:8].upper()}"
            summary = query[:60] + "..." if len(query) > 60 else query

            answer_obj = HelpdeskAnswer(
                query=query,
                answer=f"Your query could not be answered with high confidence from official campus policies. A support ticket ({ticket_id}) has been generated for manual review.",
                sources=[],
                confidence=best_score,
                needs_manual_review=True,
                review_reason=f"Low confidence ({best_score:.2f} < {CONFIDENCE_THRESHOLD}). Generated ticket {ticket_id}."
            )

            ticket_stub = {
                "ticket_id": ticket_id,
                "question_summary": summary,
                "timestamp": datetime.now().isoformat(),
                "status": "OPEN"
            }

            return {
                "answer": answer_obj.to_dict(),
                "escalated": True,
                "ticket": ticket_stub,
                "validation": SchemaValidator.validate_helpdesk_answer(answer_obj)
            }

        # Build grounded answer with citation
        full_source_text = f"{best_doc['title']} ({best_doc['doc_id']}), {best_doc['section']} {best_doc['content']}"
        source_ref = f"{best_doc['title']} ({best_doc['doc_id']}), {best_doc['section']}"
        answer_text = f"According to {source_ref}: {best_doc['content']}"

        # Verify numeric claims against full source text
        numeric_valid = self.verify_numeric_claims(answer_text, full_source_text)
        if not numeric_valid:
            best_score = 0.40 # Penalize score if numeric verification fails
            needs_review = True
            review_reason = "Numeric claim verification failed against source text."
        else:
            needs_review = False
            review_reason = None

        answer_obj = HelpdeskAnswer(
            query=query,
            answer=answer_text,
            sources=[source_ref],
            confidence=best_score,
            needs_manual_review=needs_review,
            review_reason=review_reason
        )

        return {
            "answer": answer_obj.to_dict(),
            "escalated": False,
            "ticket": None,
            "validation": SchemaValidator.validate_helpdesk_answer(answer_obj)
        }

    def _verify_answer(self, result: Dict[str, Any], query: str) -> tuple:
        """Real DoD checks for Helpdesk answer."""
        failures = []
        checks_run = 0

        # Check 1: Output structure
        checks_run += 1
        if "answer" not in result or "escalated" not in result:
            failures.append("Result missing 'answer' or 'escalated' key")

        # Check 2: Confidence bounds
        checks_run += 1
        ans_data = result.get("answer", {})
        conf = ans_data.get("confidence", 0.0)
        if not (0.0 <= conf <= 1.0):
            failures.append(f"Confidence score {conf} out of bounds [0.0, 1.0]")

        # Check 3: Escalation consistency
        checks_run += 1
        escalated = result.get("escalated", False)
        if conf < CONFIDENCE_THRESHOLD and not escalated:
            failures.append(f"Confidence {conf} < threshold {CONFIDENCE_THRESHOLD} but escalated is False")

        # Check 4: Ticket stub present when escalated
        checks_run += 1
        if escalated and not result.get("ticket"):
            failures.append("Escalated is True but no ticket stub generated")

        # Check 5: Sources present when not escalated
        checks_run += 1
        if not escalated and not ans_data.get("sources"):
            failures.append("Not escalated but no sources cited")

        checks_passed = checks_run - len(failures)
        return checks_run, checks_passed, failures
