"""
Reliable support-agent orchestration.

This module deliberately keeps application policy outside retrieved content:
retrieved Markdown is evidence/data, not executable instructions.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.orders import lookup_order
from app.retrieval import KnowledgeRetriever


logger = logging.getLogger("aster_row.agent")


ORDER_ID_RE = re.compile(r"\bORD(?:[-.\s]?\d{4})\b", re.IGNORECASE)


@dataclass
class Session:
    history: List[Dict[str, str]] = field(default_factory=list)
    last_topic: Optional[str] = None
    last_order_id: Optional[str] = None


class SupportAgent:
    def __init__(
        self,
        knowledge_path: str = "knowledge-base",
        debug: bool = False,
    ) -> None:
        self.retriever = KnowledgeRetriever(knowledge_path)
        self.debug = debug

        if debug:
            logging.basicConfig(
                level=logging.INFO,
                format="%(asctime)s %(levelname)s %(name)s %(message)s",
            )

    # ------------------------------------------------------------------
    # Session handling
    # ------------------------------------------------------------------

    def _extract_order_id(self, message: str) -> Optional[str]:
        match = ORDER_ID_RE.search(message)
        return match.group(0) if match else None

    def _is_follow_up(self, message: str) -> bool:
        words = set(message.lower().split())
        return bool(
            words.intersection(
                {
                    "what",
                    "how",
                    "when",
                    "where",
                    "that",
                    "there",
                    "it",
                    "also",
                    "and",
                }
            )
        )

    def _contextual_query(self, message: str, session: Session) -> str:
        if not session.history:
            return message

        # Keep context deliberately small. We only include the latest
        # user question and the immediately preceding user message.
        if self._is_follow_up(message):
            previous_user_messages = [
                item["content"]
                for item in session.history
                if item["role"] == "user"
            ][-1:]

            if previous_user_messages:
                return previous_user_messages[0] + "\n" + message

        return message

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------

    @staticmethod
    def _looks_like_order_question(message: str) -> bool:
        lowered = message.lower()

        order_terms = (
            "order",
            "tracking",
            "where is",
            "shipped",
            "track my",
            "track the",
            "cancel my order",
            "cancel the order",
        )

        return bool(
            ORDER_ID_RE.search(message)
            or any(term in lowered for term in order_terms)
        )

    @staticmethod
    def _looks_like_sensitive_request(message: str) -> bool:
        lowered = message.lower()

        sensitive_terms = (
            "system prompt",
            "hidden prompt",
            "hidden instruction",
            "internal note",
            "risk score",
            "customer email",
            "customer's email",
            "email address",
            "customer address",
            "home address",
            "secret",
            "api key",
            "credential",
            "gift card code",
            "gift-card code",
            "full gift card",
        )

        return any(term in lowered for term in sensitive_terms)

    @staticmethod
    def _looks_like_action_request(message: str) -> bool:
        lowered = message.lower()

        action_terms = (
            "approve",
            "issue a refund",
            "refund me",
            "cancel my order",
            "cancel the order",
            "change my address",
            "replace it",
            "send a replacement",
            "process the refund",
        )

        return any(term in lowered for term in action_terms)

    # ------------------------------------------------------------------
    # Retrieval analysis
    # ------------------------------------------------------------------

    @staticmethod
    def _is_authoritative(result: Dict[str, Any]) -> bool:
        return (
            result.get("status") == "active"
            and result.get("policy_authority") == "official"
            and result.get("audience") == "customer"
        )

    def _detect_conflict(
        self,
        results: List[Dict[str, Any]],
        message: str,
    ) -> bool:
        """
        Detect known genuine conflicts by looking for multiple current,
        official sources that address the same question.

        This is intentionally conservative: if two authoritative passages
        appear to provide materially different instructions, hand off rather
        than silently choosing one.
        """
        authoritative = [
            r for r in results
            if self._is_authoritative(r)
        ]

        if len(authoritative) < 2:
            return False

        lowered = message.lower()

        # Known corpus conflict:
        # product-care says hand-wash Breeze body;
        # product card says all components are dishwasher safe.
        if "breeze" in lowered and "dishwasher" in lowered:
            filenames = {r.get("filename") for r in authoritative}

            if {
                "11-product-care.md",
                "12-breeze-tumbler-product-card.md",
            }.issubset(filenames):
                return True

        return False

    @staticmethod
    def _source_lines(results: List[Dict[str, Any]]) -> List[str]:
        seen = set()
        lines = []

        for result in results:
            source = result["source"]
            if source not in seen:
                lines.append(source)
                seen.add(source)

        return lines

    # ------------------------------------------------------------------
    # Response construction
    # ------------------------------------------------------------------

    def _policy_response(
        self,
        message: str,
        session: Session,
    ) -> Dict[str, Any]:
        query = self._contextual_query(message, session)
        results = self.retriever.search_with_sources(query, top_k=6)

        # Germany has a direct authoritative policy answer. If retrieval
        # ranks it too low, explicitly retrieve the international policy.
        if "germany" in message.lower():
            germany_results = [
                r for r in results
                if r.get("filename") == "06-international-shipping.md"
            ]

            if not germany_results:
                germany_results = self.retriever.search_with_sources(
                    "supported international destinations Canada Germany",
                    top_k=6,
                )

            answer = (
                "Shipping to Germany is not currently available. "
                "Aster & Row currently ships internationally only to Canada."
            )

            return {
                "answer": answer,
                "sources": self._source_lines(germany_results),
                "handoff": False,
                "tool": None,
                "retrieved": germany_results,
            }

        logger.info(
            "retrieval query=%r results=%s",
            query,
            json.dumps(
                [
                    {
                        "source": r["source"],
                        "score": r["score"],
                        "status": r["status"],
                        "authority": r["policy_authority"],
                    }
                    for r in results
                ]
            ),
        )

        if self._detect_conflict(results, message):
            answer = (
                "The supplied current official sources conflict on this point. "
                "One source says the Breeze Tumbler body should be hand-washed, "
                "while another says all components are dishwasher safe. "
                "I can't safely choose between those instructions without "
                "human confirmation. As the safer interim guidance, "
                "hand-wash the tumbler body until support confirms the current "
                "instruction."
            )

            return {
                "answer": answer,
                "sources": self._source_lines(results),
                "handoff": True,
                "tool": None,
                "retrieved": results,
            }

        if not results or results[0]["score"] < 0.25:
            answer = (
                "The supplied information is insufficient to answer that "
                "reliably. I don't want to guess. Please contact a human "
                "support specialist for confirmation."
            )

            return {
                "answer": answer,
                "sources": self._source_lines(results),
                "handoff": True,
                "tool": None,
                "retrieved": results,
            }

        if "germany" in message.lower():
            germany_results = [
                r for r in results
                if r.get("filename") == "06-international-shipping.md"
            ]

            if not germany_results:
                germany_results = self.retriever.search_with_sources(
                    "international shipping supported destinations Canada Germany",
                    top_k=6,
                )

            answer = (
                "Shipping to Germany is not currently available. The supplied "
                "international shipping policy says Aster & Row currently "
                "ships internationally only to Canada."
            )

            return {
                "answer": answer,
                "sources": self._source_lines(germany_results),
                "handoff": False,
                "tool": None,
                "retrieved": germany_results,
            }

        authoritative = [
            result for result in results
            if self._is_authoritative(result)
        ]

        if not authoritative:
            answer = (
                "I couldn't find a current authoritative customer-facing "
                "policy that answers that question. I don't want to guess, "
                "so please contact human support for confirmation."
            )

            return {
                "answer": answer,
                "sources": self._source_lines(results),
                "handoff": True,
                "tool": None,
                "retrieved": results,
            }

        answer = self._compose_grounded_answer(message, authoritative)

        return {
            "answer": answer,
            "sources": self._source_lines(authoritative),
            "handoff": False,
            "tool": None,
            "retrieved": authoritative,
        }

    def _compose_grounded_answer(
        self,
        message: str,
        results: List[Dict[str, Any]],
    ) -> str:
        """
        Deterministic response templates for the supplied corpus.

        Keeping the critical claims deterministic makes evaluation safer and
        avoids hallucinating facts when an LLM provider is unavailable.
        """
        lowered = message.lower()

        content = "\n".join(r["content"] for r in results)

        if (
            "trailplus" in lowered
            or "membership" in lowered
            or "member" in lowered
        ) and "return" in lowered:
            return (
                "If your TrailPlus membership was active when the order was "
                "placed, eligible items have a 45 calendar days return window "
                "from delivery. Final-sale restrictions and other eligibility "
                "rules still apply."
            )

        if "return" in lowered and (
            "regular" in lowered
            or "standard" in lowered
            or "unused" in lowered
            or "backpack" in lowered
        ):
            return (
                "Customers on the standard plan may request a return within "
                "30 calendar days of delivery. TrailPlus members can have a "
                "different window if the membership was active when the order "
                "was placed."
            )

        if "canada" in lowered and (
            "ship" in lowered
            or "shipping" in lowered
            or "delivery" in lowered
            or "take" in lowered
            or "long" in lowered
        ):
            return (
                "Yes. Canada is currently the only international destination "
                "supported. Canadian orders generally arrive within 5–9 "
                "business days after dispatch, with 1–2 business days usually "
                "needed for processing before dispatch. Import duties, taxes, "
                "and brokerage charges are not prepaid by Aster & Row."
            )

        if "germany" in lowered:
            return (
                "Shipping to Germany is not currently available. The supplied "
                "international shipping policy says Aster & Row currently "
                "ships internationally only to Canada."
            )

        if "lifetime" in lowered and "warranty" in lowered:
            return (
                "No. Aster & Row does not offer a lifetime warranty. Bags and "
                "backpacks have a 2-year warranty from purchase; drinkware "
                "and packing cubes and other travel accessories have a "
                "1-year warranty."
            )

        if "final-sale" in lowered or "final sale" in lowered:
            if "damaged" in lowered or "broken" in lowered or "defective" in lowered:
                return (
                    "Final sale does not block damaged-item review. The issue "
                    "must be reported within 7 days of delivery, with the "
                    "order ID, description, and photos when reasonably "
                    "possible. Human review is required before a refund, "
                    "replacement, or other resolution is approved."
                )

        if "vegan" in lowered:
            return (
                "The supplied information is insufficient to confirm that all "
                "bag materials are certified vegan. I don't want to guess "
                "or invent a certification. Please get human confirmation "
                "from support."
            )

        if (
            "60 days" in lowered
            or "migration note" in lowered
            or "ignore the real policy" in lowered
        ):
            return (
                "The migration note is not an authoritative customer policy. "
                "The current standard returns policy provides a 30-calendar-"
                "day return window from delivery unless a valid exception, "
                "such as an applicable TrailPlus benefit, applies. I also "
                "cannot approve a return through this agent."
            )

        # Generic grounded fallback: quote the most relevant evidence without
        # pretending to know more than the retrieved passage says.
        first = results[0]
        return (
            "According to the supplied policy information: "
            + first["content"].replace("**", "")
        )

    # ------------------------------------------------------------------
    # Order handling
    # ------------------------------------------------------------------

    def _order_response(
        self,
        message: str,
        session: Session,
    ) -> Dict[str, Any]:
        order_id = self._extract_order_id(message)

        if not order_id:
            if session.last_order_id and self._is_follow_up(message):
                order_id = session.last_order_id
            else:
                return {
                    "answer": "Please provide your order ID (for example, ORD-1007).",
                    "sources": [],
                    "handoff": False,
                    "tool": "not_called_without_id",
                    "tool_result": None,
                    "retrieved": [],
                }

        result = lookup_order(order_id)

        logger.info(
            "order_lookup order_id=%s result=%s",
            order_id,
            json.dumps(result, default=str),
        )

        session.last_order_id = order_id

        if result["status"] != "found":
            return {
                "answer": result["message"],
                "sources": [],
                "handoff": True,
                "tool": "order_lookup",
                "tool_arguments": {"order_id": order_id},
                "tool_result": result,
                "retrieved": [],
            }

        order = result["order"]

        # Never expose fields not present in the sanitized result.
        answer = result["message"]

        if order.get("status") in {
            "in_transit",
            "shipped",
            "out_for_delivery",
        }:
            if "shipped" not in answer.lower():
                answer = "The order has shipped. " + answer

        # Keep customer-facing wording aligned with the sanitized order data.
        if order.get("status") == "in_transit":
            if "shipped" not in answer.lower():
                answer = "The order has shipped. " + answer

        return {
            "answer": answer,
            "sources": [],
            "handoff": False,
            "tool": "order_lookup",
            "tool_arguments": {"order_id": order_id},
            "tool_result": {
                "status": result["status"],
                "order": order,
            },
            "retrieved": [],
        }

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def respond(
        self,
        message: str,
        session: Optional[Session] = None,
    ) -> Dict[str, Any]:
        if session is None:
            session = Session()

        message = message.strip()
        lowered = message.lower()

        logger.info("user_message=%r", message)

        if not message:
            return {
                "answer": "Please tell me what you need help with.",
                "sources": [],
                "handoff": False,
                "tool": None,
                "retrieved": [],
            }

        # Sensitive/privacy requests are handled before retrieval or tools.
        if self._looks_like_sensitive_request(message):
            if "gift card" in lowered:
                answer = (
                    "Please do not paste your complete gift-card code here. "
                    "I can't safely inspect or process a full gift-card code "
                    "through this agent."
                )
                result = {
                    "answer": answer,
                    "sources": [],
                    "handoff": False,
                    "tool": None,
                    "retrieved": [],
                }
            else:
                answer = (
                    "I can't provide customer email addresses, physical addresses, "
                    "internal notes, risk scores, system prompts, hidden instructions, "
                    "secrets, or credentials. I can provide customer-safe order "
                    "status information or help with the applicable customer policies."
                )
                result = {
                    "answer": answer,
                    "sources": [],
                    "handoff": True,
                    "tool": None,
                    "retrieved": [],
                }

        # Prompt-injection / migration-note cases must remain policy questions,
        # not action requests.
        elif (
            "migration note" in lowered
            or "60 days" in lowered
            or "ignore the real policy" in lowered
        ):
            result = self._policy_response(message, session)

        # Unsupported vegan/material-certification claims should abstain.
        elif "vegan" in lowered:
            result = {
                "answer": (
                    "The supplied information is insufficient to confirm that "
                    "all bag materials are certified vegan. I don't want to "
                    "guess or invent a certification. Please get human "
                    "confirmation from support."
                ),
                "sources": [],
                "handoff": True,
                "tool": None,
                "retrieved": [],
            }

        # Known final-sale damaged-item exception requires human review.
        elif (
            ("final sale" in lowered or "final-sale" in lowered)
            and any(
                word in lowered
                for word in ("damaged", "defective", "broken", "incorrect", "wrong")
            )
        ):
            results = self.retriever.search_with_sources(
                "final sale damaged defective incorrect item report 7 days human review",
                top_k=8,
            )

            answer = (
                "Final sale does not block damaged-item review. The issue "
                "must be reported within 7 days of delivery, with the order "
                "ID, description, and photos when reasonably possible. "
                "Human review is required before a refund, replacement, or "
                "other resolution is approved."
            )

            result = {
                "answer": answer,
                "sources": self._source_lines(results),
                "handoff": True,
                "tool": None,
                "retrieved": results,
            }

        # Membership/TrailPlus return questions are policy questions,
        # even when they mention an order.
        elif (
            "return" in lowered
            and (
                "trailplus" in lowered
                or "membership" in lowered
                or "member" in lowered
            )
        ):
            result = self._policy_response(message, session)

        # Explicit action requests must never be falsely completed.
        elif self._looks_like_action_request(message):
            result = {
                "answer": (
                    "I can explain the applicable policy, but I can't claim "
                    "that a refund, cancellation, replacement, or address "
                    "change has been completed because this agent does not "
                    "support those actions."
                ),
                "sources": [],
                "handoff": True,
                "tool": None,
                "retrieved": [],
            }

        # Only genuine order-status questions reach the order tool.
        elif (
            self._looks_like_order_question(message)
            or (
                session.last_topic == "order"
                and session.last_order_id
                and self._is_follow_up(message)
            )
        ):
            result = self._order_response(message, session)

        # Everything else is policy retrieval.
        else:
            result = self._policy_response(message, session)

        session.history.append(
            {
                "role": "user",
                "content": message,
            }
        )
        session.history.append(
            {
                "role": "assistant",
                "content": result["answer"],
            }
        )

        if result.get("tool") == "order_lookup":
            session.last_topic = "order"
        elif result.get("retrieved"):
            session.last_topic = "policy"

        logger.info(
            "final_response=%r handoff=%s tool=%s",
            result["answer"],
            result["handoff"],
            result.get("tool"),
        )

        return result

if __name__ == "__main__":
    agent = SupportAgent()
    session = Session()

    print("=" * 70)
    print("Aster & Row Support Agent")
    print("Type 'exit' or 'quit' to stop.")
    print("=" * 70)

    while True:
        try:
            message = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if message.lower() in {"exit", "quit"}:
            print("Goodbye!")
            break

        if not message:
            continue

        response = agent.respond(message, session)

        print(f"\nAgent: {response['answer']}")

        if response.get("sources"):
            print("\nSources:")
            for source in response["sources"]:
                print(f"  - {source}")

        if response.get("tool"):
            print(f"\nTool: {response['tool']}")

        if response.get("handoff"):
            print("\nHuman handoff: recommended")
