"""
Response engine — powered by Gemini AI + Qdrant RAG.

Flow:
  user_message → Gemini detects intent + language
               → Qdrant retrieves relevant legal context
               → Gemini generates simple, empathetic advice
               → Response returned to frontend / Vapi TTS
"""
import logging
from typing import Dict, List, Any

from backend.services.qdrant import search_legal_knowledge, get_user_memory, store_conversation
from backend.services.gemini import (
    gemini_generate,
    gemini_generate_document,
    detect_language,
    is_emergency,
    _emergency_response,
    _detect_intent_from_message,
    GEMINI_AVAILABLE,
)

logger = logging.getLogger(__name__)


def generate_response(
    user_id: str,
    user_message: str,
    conversation: List[Dict[str, Any]],
    language_code: str = "en",
) -> Dict[str, Any]:
    """
    Main response pipeline:
    1. Detect language
    2. Check for emergency (fast path)
    3. Search Qdrant for relevant legal knowledge
    4. Pass context to Gemini for intelligent response
    5. Store conversation turn in memory
    """
    try:
        # Step 1: Detect language
        lang = detect_language(user_message, fallback=language_code)

        # Step 2: Fast emergency path
        if is_emergency(user_message):
            result = _emergency_response(lang)
            _store_turn(user_id, user_message, result["response"], "emergency")
            return result

        # Step 3: Retrieve legal context from Qdrant
        legal_results = search_legal_knowledge(user_message, top_k=4)
        legal_context = _format_legal_context(legal_results)

        # Step 4: Retrieve user memory for context
        memories = get_user_memory(user_id, top_k=2)
        memory_context = _format_memory_context(memories)

        # Merge memory into conversation history
        full_conversation = list(conversation or [])
        if memory_context:
            full_conversation = [{"role": "system", "text": memory_context}] + full_conversation

        # Step 5: Gemini generates the response
        result = gemini_generate(
            user_message=user_message,
            legal_context=legal_context,
            language_code=lang,
            conversation_history=full_conversation,
            user_id=user_id,
        )

        # Step 6: Store this turn in memory
        _store_turn(user_id, user_message, result["response"], result.get("intent", "general"))

        return result

    except Exception as e:
        logger.error(f"generate_response error for user {user_id}: {e}", exc_info=True)
        lang = detect_language(user_message, fallback=language_code)
        return {
            "response": (
                "मुझे खेद है, अभी आपके अनुरोध को संसाधित करने में समस्या हो रही है। कृपया पुनः प्रयास करें।"
                if lang == "hi"
                else "I'm sorry, I had trouble processing your request. Please try again."
            ),
            "intent": "error",
            "language": lang,
            "urgency": False,
            "follow_up": False,
        }


def generate_document_content(doc_type: str, details: dict) -> str:
    """
    Generate legal document content using Gemini AI.
    Falls back to templates if Gemini unavailable.
    """
    return gemini_generate_document(doc_type, details)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _format_legal_context(results: list) -> str:
    """Format Qdrant search results into a context string for Gemini."""
    if not results:
        return ""
    lines = []
    for r in results:
        if r.get("score", 0) > 0.05:
            category = r["category"].replace("_", " ").title()
            lines.append(f"[{category}]: {r['content']}")
    return "\n\n".join(lines[:3])  # Top 3 most relevant


def _format_memory_context(memories: list) -> str:
    """Format user memory into a context string."""
    if not memories:
        return ""
    parts = []
    for m in memories[:2]:
        case = m.get("case_type", "").replace("_", " ").title()
        summary = m.get("summary", "")[:150]
        if summary:
            parts.append(f"Previous case ({case}): {summary}")
    return " | ".join(parts)


def _store_turn(user_id: str, user_message: str, reply: str, intent: str):
    """Store conversation turn in Qdrant memory."""
    try:
        store_conversation(
            user_id=user_id,
            conversation=[
                {"role": "user", "text": user_message},
                {"role": "assistant", "text": reply[:300]},
            ],
            case_type=intent,
        )
    except Exception as e:
        logger.warning(f"Failed to store conversation turn: {e}")
