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

from backend.config import EMERGENCY_KEYWORDS, SUPPORTED_LANGUAGES

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

# ── Emergency detection (fast, no API call needed) ───────────────────────────
def is_emergency(text: str) -> bool:
    lower = text.lower()
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
    Main Gemini call — detects intent and generates a response.
    Returns dict with: response, intent, language, urgency, follow_up
    """
    lang = detect_language(user_message, fallback=language_code)
    lang_name = LANG_NAMES.get(lang, "English")

    # Fast emergency path — no API call needed
    if is_emergency(user_message):
        return _emergency_response(lang)

    if not GEMINI_AVAILABLE:
        return _fallback_response(user_message, lang, legal_context)

    # Build conversation context string
    history_str = ""
    if conversation_history:
        recent = conversation_history[-6:]
        history_str = "\n".join(
            f"{m['role'].upper()}: {m['text']}" for m in recent
        )

    # Build the prompt
    prompt = f"""You are NyayaVoice, a compassionate legal aid assistant for people in India.
Your users are often from rural areas, low-literacy backgrounds, or are migrant workers.
Always respond in {lang_name}. Use very simple, everyday language. Be warm and empathetic.
Keep your response concise — 3 to 5 sentences maximum for voice delivery.

LEGAL KNOWLEDGE BASE (use this to answer):
{legal_context if legal_context else "No specific legal data found. Use your general knowledge of Indian law."}

CONVERSATION HISTORY:
{history_str if history_str else "This is the start of the conversation."}

USER'S MESSAGE: {user_message}

INSTRUCTIONS:
1. Identify what legal problem the user has (theft, domestic violence, wage theft, harassment, land dispute, cyber crime, consumer rights, FIR process, legal aid, child rights, or general).
2. Give clear, actionable steps the user can take RIGHT NOW.
3. Mention the relevant Indian law section (IPC, CrPC, DV Act, etc.) briefly.
4. If urgent, give emergency numbers: Police 100, Women Helpline 181, Emergency 112.
5. End with one helpful next step (e.g., "Would you like me to help draft an FIR?").
6. Respond ONLY in {lang_name}. Do NOT mix languages.
7. Do NOT use markdown formatting — plain text only (this will be spoken aloud).

Respond now:"""

    try:
        result = _model.generate_content(prompt)
        response_text = result.text.strip()

        # Detect intent from the response context
        intent = _detect_intent_from_message(user_message)

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
import re

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
