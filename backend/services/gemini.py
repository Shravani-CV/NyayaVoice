"""
Gemini AI Service — Powers the entire NyayaVoice intelligence layer.

Flow:
  User speaks → Vapi STT → text → Gemini detects intent + language
  → Qdrant retrieves legal context → Gemini generates simple advice
  → Vapi TTS speaks response

Gemini handles:
  1. Intent detection (what legal problem is this?)
  2. Language detection (English / Hindi)
  3. Response generation (simple, empathetic, actionable advice)
  4. Document content generation (FIR, complaints)
  5. Vapi system prompt (voice call personality)
"""

import os
import logging
import json
from typing import Dict, List, Any, Optional

import google.generativeai as genai

import os
import logging
import re
from typing import Dict, List, Any, Optional

import google.generativeai as genai

from backend.config import SUPPORTED_LANGUAGES

logger = logging.getLogger(__name__)

# ── Tightly scoped emergency keywords — only real physical danger ────────────
EMERGENCY_KEYWORDS = [
    "hitting me", "beating me", "i am in danger", "someone is hurting",
    "please save me", "bachao", "maaro", "maar raha hai", "maar rahi hai",
    "jaan ka khatra", "meri jaan", "attack kar raha", "assault",
]

logger = logging.getLogger(__name__)

# ── Initialise Gemini ────────────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    _model = genai.GenerativeModel(
        model_name="gemini-1.5-flash",
        generation_config=genai.GenerationConfig(
            temperature=0.4,
            max_output_tokens=1024,
        ),
    )
    GEMINI_AVAILABLE = True
    logger.info("Gemini API initialised successfully.")
else:
    _model = None
    GEMINI_AVAILABLE = False
    logger.warning("GEMINI_API_KEY not set — falling back to template responses.")


# ── Language names for prompts ───────────────────────────────────────────────
LANG_NAMES = {
    "hi": "Hindi",
    "en": "English",
    "ta": "Tamil",
    "bn": "Bengali",
    "mr": "Marathi",
    "te": "Telugu",
    "gu": "Gujarati",
    "kn": "Kannada",
    "pa": "Punjabi",
    "ur": "Urdu",
}

# ── Emergency detection — only real physical danger ─────────────────────────
def is_emergency(text: str) -> bool:
    """
    Only trigger emergency for genuine physical danger.
    Requires a strong signal — not just words like 'help' or 'danger'.
    """
    lower = text.lower()
    # Must match a specific emergency phrase
    return any(kw in lower for kw in EMERGENCY_KEYWORDS)


# ── Detect language from text ────────────────────────────────────────────────
def detect_language(text: str, fallback: str = "en") -> str:
    """Detect language from script — Devanagari = Hindi, else use fallback."""
    if any("\u0900" <= c <= "\u097F" for c in text):
        return "hi"
    return fallback if fallback in SUPPORTED_LANGUAGES else "en"


# ── Core: Gemini intent + response generation ────────────────────────────────
def gemini_generate(
    user_message: str,
    legal_context: str,
    language_code: str,
    conversation_history: List[Dict[str, str]],
    user_id: str,
) -> Dict[str, Any]:
    """
    Main Gemini call — context-aware, handles follow-ups intelligently.
    """
    lang = detect_language(user_message, fallback=language_code)
    lang_name = LANG_NAMES.get(lang, "English")

    if is_emergency(user_message):
        return _emergency_response(lang)

    if not GEMINI_AVAILABLE:
        return _fallback_response(user_message, lang, legal_context)

    # Build conversation history string for context
    history_str = ""
    if conversation_history:
        recent = [m for m in conversation_history if m.get("role") != "system"][-8:]
        history_str = "\n".join(
            f"{m['role'].upper()}: {m.get('text', '')}" for m in recent
        )

    # Detect if this is a follow-up question
    is_followup = bool(history_str)
    intent = _detect_intent_from_message(user_message)

    prompt = f"""You are NyayaVoice, an expert legal aid assistant for people in India.
You have deep knowledge of Indian law — IPC, CrPC, DV Act, POSH Act, IT Act, Consumer Protection Act, RTI Act, and more.
Your users may be from rural areas, low-literacy backgrounds, or in distress. Be warm, clear, and empathetic.
Always respond in {lang_name} only.

LEGAL KNOWLEDGE BASE:
{legal_context if legal_context else "Use your knowledge of Indian law."}

CONVERSATION SO FAR:
{history_str if history_str else "This is the first message."}

USER'S CURRENT MESSAGE: {user_message}

TASK:
{"This is a FOLLOW-UP question. Use the conversation history above to understand the full context. Answer specifically what the user is asking now." if is_followup else "This is a NEW query. Understand the full situation and give comprehensive guidance."}

RESPONSE RULES:
1. Read the full conversation history carefully before answering.
2. If the user asks to "draft FIR", "help with FIR", or "file a complaint" — give them the exact steps to file it, NOT emergency numbers.
3. If the user asks "what to do after FIR" or "next steps" — explain the post-FIR process clearly.
4. Give numbered step-by-step guidance (Step 1, Step 2, etc.) — this is most helpful.
5. Always mention the specific Indian law section that applies (e.g., IPC 379, CrPC 154).
6. Include the correct police station or authority to approach (e.g., KR Puram Railway Police Station for railway incidents).
7. If the user mentioned a specific location (like KR Puram, Bangalore), use it in your response.
8. End with: "Would you like me to help you draft the FIR document?" if relevant.
9. Use plain text — no markdown symbols like ** or ##.
10. Be specific and practical — not generic.

IMPORTANT: Do NOT give emergency helpline numbers unless the user is in immediate physical danger.
Do NOT say "consult a lawyer" as the main advice — give direct actionable steps first.

Respond now in {lang_name}:"""

    try:
        result = _model.generate_content(prompt)
        response_text = result.text.strip()

        return {
            "response": response_text,
            "intent": intent,
            "language": lang,
            "urgency": False,
            "follow_up": True,
        }

    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        return _fallback_response(user_message, lang, legal_context)


# ── Gemini document content generation ──────────────────────────────────────
def gemini_generate_document(doc_type: str, details: dict, language_code: str = "en") -> str:
    """
    Use Gemini to generate professional legal document content.
    Falls back to templates if Gemini unavailable.
    """
    if not GEMINI_AVAILABLE:
        return _template_document(doc_type, details)

    complainant = details.get("complainant_name", details.get("complainant_id", "The Complainant"))
    incident = details.get("incident_description", "As described")
    date_time = details.get("date_time", "Date not specified")
    location = details.get("location", "Location not specified")
    suspect = details.get("suspect_description", "Unknown")
    witness = details.get("witness", "None")

    prompt = f"""You are a legal document drafting assistant for India.
Draft a formal {doc_type} in English for submission to Indian authorities.

DETAILS:
- Complainant: {complainant}
- Incident: {incident}
- Date/Time: {date_time}
- Location: {location}
- Suspect/Accused: {suspect}
- Witnesses: {witness}

REQUIREMENTS:
1. Use formal legal language appropriate for Indian courts/police
2. Reference the correct Indian law sections (IPC, CrPC, DV Act, etc.)
3. Structure: Salutation → Subject → Body → Relief Sought → Declaration → Signature
4. Keep it professional and factual
5. Include a note about the complainant's legal rights

Draft the complete {doc_type} now:"""

    try:
        result = _model.generate_content(prompt)
        return result.text.strip()
    except Exception as e:
        logger.error(f"Gemini document generation error: {e}")
        return _template_document(doc_type, details)


# ── Gemini Vapi system prompt ────────────────────────────────────────────────
def get_vapi_system_prompt(language: str) -> str:
    """Generate a Gemini-powered system prompt for Vapi voice calls."""
    lang_name = LANG_NAMES.get(language, "English")
    return (
        f"You are NyayaVoice, a kind and knowledgeable legal aid assistant for people in India. "
        f"You are powered by Gemini AI and have deep knowledge of Indian law. "
        f"ALWAYS respond in {lang_name}. Use simple, everyday language that anyone can understand. "
        f"Be warm, patient, and empathetic — your users may be in distress. "
        f"If the user is in danger, IMMEDIATELY give emergency numbers: Police 100, Women Helpline 181, Emergency 112. "
        f"Ask one question at a time to understand the user's problem fully. "
        f"Identify the legal issue (theft, domestic violence, wage theft, harassment, land dispute, cyber crime, consumer rights, FIR process). "
        f"Give clear step-by-step guidance on what the user can do. "
        f"Mention relevant Indian laws (IPC sections, CrPC, DV Act 2005, POSH Act 2013, etc.). "
        f"When you have enough details, offer to generate a legal document (FIR, complaint letter). "
        f"Keep responses SHORT and CLEAR — this is a voice call, not a text chat. "
        f"Never give medical, financial, or personal advice outside of legal matters."
    )


# ── Intent detection (fast regex, no API call) ───────────────────────────────

INTENT_PATTERNS = {
    "theft_complaint": r"chori|theft|stolen|चोरी|phone|mobile|snatch|rob|loot|लूट|missing|lost.*phone|wallet|purse|pickpocket|गुम|खो गया",
    "domestic_violence": r"violen|hinsa|हिंसा|domestic|abuse|beat|पीट|dv|498|husband.*hit|hit.*wife|घरेलू|पति|पत्नी",
    "harassment": r"harass|posh|उत्पीड़|stalking|molestation|छेड़|follow|threaten",
    "wage_theft": r"wage|वेतन|salary|pay|भुगतान|mazduri|मज़दूरी|labour|labor|not paid|unpaid|employer",
    "land_dispute": r"land|bhumi|भूमि|ज़मीन|zameen|property|सम्पत्ति|plot|encroach|boundary",
    "cyber_crime": r"cyber|hack|online|fraud|धोखा|scam|phishing|otp|upi|bank.*fraud|account.*hacked",
    "consumer_rights": r"consumer|उपभोक्ता|refund|product|defect|warranty|खराब|cheated|overcharged",
    "rti": r"rti|सूचना|right to info|आरटीआई|information act",
    "fir_process": r"fir|एफ़आईआर|first information|zero fir|police station|थाना|file.*complaint",
    "legal_aid": r"free legal|legal aid|nalsa|नालसा|dlsa|free lawyer|15100|afford.*lawyer",
    "child_rights": r"child|बच्च|pocso|juvenile|1098|minor|kid",
    "emergency": r"emergency|help me|bachao|बचाओ|danger|khatra|खतरा|kill|मार|attack|assault|threat",
}

def _detect_intent_from_message(text: str) -> str:
    lower = text.lower()
    for intent, pattern in INTENT_PATTERNS.items():
        if re.search(pattern, lower, re.IGNORECASE):
            return intent
    return "general_legal_query"


# ── Emergency response (no API call) ────────────────────────────────────────
EMERGENCY_RESPONSES = {
    "en": (
        "EMERGENCY — Please call for help immediately.\n\n"
        "Police: 100\n"
        "Women Helpline: 181 (24/7)\n"
        "Emergency (all services): 112\n"
        "Child Helpline: 1098\n"
        "Cyber Crime: 1930\n\n"
        "You are not alone. Help is available right now. "
        "If you are in physical danger, call 112 immediately."
    ),
    "hi": (
        "आपातकाल — तुरन्त सहायता के लिए कॉल करें।\n\n"
        "पुलिस: 100\n"
        "महिला हेल्पलाइन: 181 (24/7)\n"
        "आपातकाल (सभी सेवाएँ): 112\n"
        "बाल हेल्पलाइन: 1098\n"
        "साइबर अपराध: 1930\n\n"
        "आप अकेले नहीं हैं। सहायता अभी उपलब्ध है। "
        "यदि आप शारीरिक खतरे में हैं, तो तुरन्त 112 पर कॉल करें।"
    ),
}

def _emergency_response(lang: str) -> Dict[str, Any]:
    return {
        "response": EMERGENCY_RESPONSES.get(lang, EMERGENCY_RESPONSES["en"]),
        "intent": "emergency",
        "language": lang,
        "urgency": True,
        "follow_up": False,
    }


# ── Fallback when Gemini unavailable ────────────────────────────────────────
FALLBACK_RESPONSES = {
    "theft_complaint": {
        "en": "Your phone or belongings were stolen. You have the right to file a free FIR at any police station under IPC Section 379. Police must register it. You can also file a Zero FIR at any station regardless of location. Would you like help drafting your FIR?",
        "hi": "आपका सामान चोरी हुआ है। आप किसी भी थाने में धारा 379 के तहत निःशुल्क एफ़आईआर दर्ज करा सकते हैं। पुलिस को दर्ज करना ही होगा। क्या आप एफ़आईआर तैयार करना चाहते हैं?",
    },
    "domestic_violence": {
        "en": "You are protected under the Domestic Violence Act 2005. Call Women Helpline 181 immediately for free help. You can get a Protection Order from court to stop the abuser. You are not alone.",
        "hi": "आप घरेलू हिंसा अधिनियम 2005 के तहत सुरक्षित हैं। तुरन्त महिला हेल्पलाइन 181 पर कॉल करें। आप अकेले नहीं हैं।",
    },
    "wage_theft": {
        "en": "Your employer must pay your full wages on time under the Payment of Wages Act. File a free complaint with the Labour Commissioner in your district. No lawyer needed. Call NALSA Helpline 15100 for free legal advice.",
        "hi": "आपके नियोक्ता को वेतन भुगतान अधिनियम के तहत समय पर वेतन देना होगा। जिले के श्रम आयुक्त के पास निःशुल्क शिकायत करें। नालसा हेल्पलाइन 15100 पर कॉल करें।",
    },
    "general_legal_query": {
        "en": "I can help you with theft, domestic violence, wage theft, harassment, land disputes, cyber crime, consumer rights, and FIR filing. Please describe your problem in detail and I will guide you step by step.",
        "hi": "मैं चोरी, घरेलू हिंसा, वेतन चोरी, उत्पीड़न, भूमि विवाद, साइबर अपराध, उपभोक्ता अधिकार और एफ़आईआर में मदद कर सकता हूँ। अपनी समस्या विस्तार से बताएँ।",
    },
}

def _fallback_response(user_message: str, lang: str, legal_context: str) -> Dict[str, Any]:
    intent = _detect_intent_from_message(user_message)
    responses = FALLBACK_RESPONSES.get(intent, FALLBACK_RESPONSES["general_legal_query"])
    response_text = responses.get(lang, responses["en"])

    # Append relevant legal context if available
    if legal_context and len(legal_context) > 20:
        if lang == "hi":
            response_text += f"\n\nकानूनी जानकारी: {legal_context[:300]}"
        else:
            response_text += f"\n\nLegal reference: {legal_context[:300]}"

    disclaimer = (
        "\n\nकृपया ध्यान दें: यह सामान्य कानूनी जानकारी है। विशिष्ट सलाह के लिए वकील से मिलें।"
        if lang == "hi"
        else "\n\nNote: This is general legal information. Please consult a qualified lawyer for specific advice."
    )

    return {
        "response": response_text + disclaimer,
        "intent": intent,
        "language": lang,
        "urgency": False,
        "follow_up": True,
    }


# ── Template document fallback ───────────────────────────────────────────────
def _template_document(doc_type: str, details: dict) -> str:
    complainant = details.get("complainant_name", details.get("complainant_id", "The Complainant"))
    incident = details.get("incident_description", "As described verbally")
    date_time = details.get("date_time", "Date not specified")
    location = details.get("location", "Location not specified")
    suspect = details.get("suspect_description", "Unknown")
    witness = details.get("witness", "None provided")

    return f"""{doc_type.upper()}

To,
The Appropriate Authority,

Subject: {doc_type}

Respected Sir/Madam,

I, {complainant}, hereby submit this {doc_type}.

INCIDENT DETAILS:
{incident}

DATE AND TIME: {date_time}
LOCATION: {location}
ACCUSED/SUSPECT: {suspect}
WITNESSES: {witness}

I request that appropriate action be taken as per the provisions of Indian law.

Yours faithfully,
{complainant}

Note: Under Section 154 CrPC, police are legally bound to register FIRs.
Refusal is punishable under Section 166A IPC.
"""
