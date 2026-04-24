"""
Gemini AI Service for NyayaVoice.
Uses google-genai SDK (v1 API) for better rate limits.
"""
import os
import re
import logging
from typing import Dict, List, Any

from backend.config import SUPPORTED_LANGUAGES

logger = logging.getLogger(__name__)

# ── Emergency keywords — only genuine physical danger ────────────────────────
EMERGENCY_KEYWORDS = [
    "hitting me", "beating me", "i am in danger", "someone is hurting",
    "please save me", "bachao", "maaro", "maar raha hai", "maar rahi hai",
    "jaan ka khatra", "meri jaan", "attack kar raha", "assault",
]

# ── Language names ────────────────────────────────────────────────────────────
LANG_NAMES = {
    "hi": "Hindi", "en": "English", "ta": "Tamil", "bn": "Bengali",
    "mr": "Marathi", "te": "Telugu", "gu": "Gujarati", "kn": "Kannada",
    "pa": "Punjabi", "ur": "Urdu",
}

# ── Initialise Gemini ─────────────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_AVAILABLE = False
_client = None

if GEMINI_API_KEY:
    try:
        from google import genai as _genai_module
        _client = _genai_module.Client(api_key=GEMINI_API_KEY)
        # Auto-discover the first working model
        GEMINI_MODEL = None
        _preferred = [
            "gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.0-flash-lite",
            "gemini-2.0-flash-001", "gemini-1.5-flash", "gemini-1.5-pro",
        ]
        for _m in _preferred:
            try:
                _client.models.generate_content(model=_m, contents="hi")
                GEMINI_MODEL = _m
                GEMINI_AVAILABLE = True
                logger.info(f"Gemini API ready — using model: {_m}")
                break
            except Exception as _e:
                err_str = str(_e)
                if "503" in err_str or "UNAVAILABLE" in err_str:
                    # Model exists but overloaded — still use it
                    GEMINI_MODEL = _m
                    GEMINI_AVAILABLE = True
                    logger.info(f"Gemini API ready — using model: {_m} (high demand, will retry)")
                    break
                logger.debug(f"Model {_m} not available: {err_str[:60]}")
        if not GEMINI_AVAILABLE:
            logger.warning("No Gemini model available — using smart fallback.")
    except Exception as e:
        logger.warning(f"Gemini init failed: {e}")
else:
    logger.warning("GEMINI_API_KEY not set — using smart fallback responses.")


# ── Language detection ────────────────────────────────────────────────────────
def detect_language(text: str, fallback: str = "en") -> str:
    if any("\u0900" <= c <= "\u097F" for c in text):
        return "hi"
    return fallback if fallback in SUPPORTED_LANGUAGES else "en"


# ── Emergency detection ───────────────────────────────────────────────────────
def is_emergency(text: str) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in EMERGENCY_KEYWORDS)


# ── Intent detection ──────────────────────────────────────────────────────────
INTENT_PATTERNS = {
    "theft_complaint": r"chori|theft|stolen|phone|mobile|snatch|rob|loot|missing|lost.*phone|wallet|purse|pickpocket|lost.*bag|bag.*stolen",
    "domestic_violence": r"violen|hinsa|domestic|abuse|beat|dv|498|husband.*hit|hit.*wife|husband.*beating|wife.*beaten",
    "harassment": r"harass|posh|stalking|molestation|follow|threaten|eve.?teas",
    "wage_theft": r"wage|salary|pay|labour|labor|not paid|unpaid|employer|boss.*salary",
    "land_dispute": r"land|bhumi|zameen|property|plot|encroach|boundary",
    "cyber_crime": r"cyber|hack|online|fraud|scam|phishing|otp|upi|bank.*fraud|account.*hacked",
    "consumer_rights": r"consumer|refund|product|defect|warranty|cheated|overcharged",
    "rti": r"rti|right to info|information act",
    "fir_process": r"fir|first information|zero fir|police station|file.*complaint|draft.*fir|help.*fir",
    "legal_aid": r"free legal|legal aid|nalsa|dlsa|free lawyer|afford.*lawyer",
    "child_rights": r"child|pocso|juvenile|minor|kid",
    "post_fir": r"after.*fir|next step|fir.*registered|fir.*filed|what.*after|follow.*up|track.*case",
}

def _detect_intent_from_message(text: str) -> str:
    lower = text.lower()
    for intent, pattern in INTENT_PATTERNS.items():
        if re.search(pattern, lower, re.IGNORECASE):
            return intent
    return "general_legal_query"


# ── Core Gemini call ──────────────────────────────────────────────────────────
def gemini_generate(
    user_message: str,
    legal_context: str,
    language_code: str,
    conversation_history: List[Dict[str, str]],
    user_id: str,
) -> Dict[str, Any]:
    lang = detect_language(user_message, fallback=language_code)
    lang_name = LANG_NAMES.get(lang, "English")

    if is_emergency(user_message):
        return _emergency_response(lang)

    if not GEMINI_AVAILABLE or _client is None:
        return _smart_fallback(user_message, lang, legal_context, conversation_history)

    # Build conversation history string
    history_str = ""
    if conversation_history:
        recent = [m for m in conversation_history if m.get("role") != "system"][-8:]
        history_str = "\n".join(
            f"{m['role'].upper()}: {m.get('text', '')}" for m in recent
        )

    is_followup = bool(history_str)
    intent = _detect_intent_from_message(user_message)

    prompt = f"""You are NyayaVoice, an expert legal aid assistant for people in India.
You have deep knowledge of Indian law — IPC, CrPC, DV Act, POSH Act, IT Act, Consumer Protection Act, RTI Act.
Always respond in {lang_name} only. Be warm, clear, and empathetic.

LEGAL KNOWLEDGE BASE:
{legal_context if legal_context else "Use your knowledge of Indian law."}

CONVERSATION SO FAR:
{history_str if history_str else "This is the first message."}

USER'S CURRENT MESSAGE: {user_message}

TASK: {"This is a FOLLOW-UP. Use conversation history to understand full context." if is_followup else "This is a NEW query."}

RULES:
1. Read conversation history carefully before answering.
2. If user asks to draft FIR or file complaint — give exact numbered steps, NOT emergency numbers.
3. If user asks what to do after FIR — explain post-FIR process step by step.
4. Give numbered steps: Step 1, Step 2, Step 3...
5. Mention specific Indian law section (IPC 379, CrPC 154, etc.).
6. If user mentioned a specific location (like KR Puram, Bangalore) — use it in your response.
7. For phone theft at railway station — mention Railway Police / GRP specifically.
8. End with: "Would you like me to help you draft the FIR document?" if relevant.
9. Plain text only — no markdown symbols.
10. Do NOT give emergency helpline numbers unless user is in immediate physical danger.
11. Do NOT say "consult a lawyer" as main advice — give direct steps first.

Respond in {lang_name}:"""

    try:
        from google import genai as genai_module
        response = _client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=genai_module.types.GenerateContentConfig(
                temperature=0.4,
                max_output_tokens=1024,
            ),
        )
        return {
            "response": response.text.strip(),
            "intent": intent,
            "language": lang,
            "urgency": False,
            "follow_up": True,
        }
    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        return _smart_fallback(user_message, lang, legal_context, conversation_history)


# ── Gemini document generation ────────────────────────────────────────────────
def gemini_generate_document(doc_type: str, details: dict, language_code: str = "en") -> str:
    if not GEMINI_AVAILABLE or _client is None:
        return _template_document(doc_type, details)

    complainant = details.get("complainant_name", details.get("complainant_id", "The Complainant"))
    incident = details.get("incident_description", "As described")
    date_time = details.get("date_time", "Date not specified")
    location = details.get("location", "Location not specified")
    suspect = details.get("suspect_description", "Unknown")
    witness = details.get("witness", "None")

    prompt = f"""Draft a formal {doc_type} for submission to Indian authorities.

DETAILS:
- Complainant: {complainant}
- Incident: {incident}
- Date/Time: {date_time}
- Location: {location}
- Suspect/Accused: {suspect}
- Witnesses: {witness}

Requirements:
1. Formal legal language for Indian courts/police
2. Correct Indian law sections (IPC, CrPC, DV Act, etc.)
3. Structure: Salutation, Subject, Body, Relief Sought, Declaration, Signature
4. Include complainant's legal rights

Draft the complete {doc_type}:"""

    try:
        from google import genai as genai_module
        response = _client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )
        return response.text.strip()
    except Exception as e:
        logger.error(f"Gemini document error: {e}")
        return _template_document(doc_type, details)


# ── Vapi system prompt ────────────────────────────────────────────────────────
def get_vapi_system_prompt(language: str) -> str:
    lang_name = LANG_NAMES.get(language, "English")
    return (
        f"You are NyayaVoice, a kind and expert legal aid assistant for people in India. "
        f"ALWAYS respond in {lang_name}. Use simple everyday language. "
        f"Be warm, patient, and empathetic. "
        f"If the user is in danger, give emergency numbers: Police 100, Women Helpline 181, Emergency 112. "
        f"Ask one question at a time. Identify the legal issue and give step-by-step guidance. "
        f"Mention relevant Indian laws (IPC, CrPC, DV Act 2005, POSH Act 2013, etc.). "
        f"When you have enough details, offer to generate a legal document. "
        f"Keep responses SHORT and CLEAR for voice delivery."
    )


# ── Emergency response ────────────────────────────────────────────────────────
EMERGENCY_RESPONSES = {
    "en": (
        "EMERGENCY — Please call for help immediately.\n\n"
        "Police: 100\nWomen Helpline: 181 (24/7)\n"
        "Emergency (all services): 112\nChild Helpline: 1098\n\n"
        "You are not alone. Help is available right now."
    ),
    "hi": (
        "आपातकाल — तुरन्त सहायता के लिए कॉल करें।\n\n"
        "पुलिस: 100\nमहिला हेल्पलाइन: 181 (24/7)\n"
        "आपातकाल: 112\nबाल हेल्पलाइन: 1098\n\n"
        "आप अकेले नहीं हैं। सहायता अभी उपलब्ध है।"
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


# ── Smart fallback — context-aware, step-by-step ─────────────────────────────
def _smart_fallback(
    user_message: str,
    lang: str,
    legal_context: str,
    conversation_history: List[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Context-aware fallback that reads conversation history
    and gives step-by-step responses like Gemini would.
    """
    lower = user_message.lower()
    intent = _detect_intent_from_message(user_message)

    # Extract location from message if mentioned
    location_hint = ""
    location_keywords = {
        "kr puram": "KR Puram Railway Police Station (GRP)",
        "karpuram": "KR Puram Railway Police Station (GRP)",
        "bangalore": "Bangalore",
        "bengaluru": "Bengaluru",
        "railway station": "Railway Police Station (GRP)",
        "airport": "Airport Police Station",
    }
    for kw, loc in location_keywords.items():
        if kw in lower:
            location_hint = loc
            break

    # Check conversation history for context
    prev_context = ""
    if conversation_history:
        for m in reversed(conversation_history[-6:]):
            if m.get("role") == "user":
                prev_context = m.get("text", "")
                break

    # Detect follow-up patterns
    is_draft_fir = bool(re.search(r"draft|help.*fir|fir.*draft|file.*fir|write.*fir", lower))
    is_post_fir = bool(re.search(r"after.*fir|next step|fir.*registered|fir.*filed|what.*after|follow.*up|track", lower))
    is_theft = bool(re.search(r"phone|mobile|stolen|theft|lost|chori|wallet|purse", lower))
    is_theft_context = is_theft or bool(re.search(r"phone|mobile|stolen|theft|lost|chori|wallet|purse", prev_context.lower()))

    # ── Post-FIR steps ────────────────────────────────────────────────────────
    if is_post_fir:
        station = location_hint or "the police station"
        if lang == "hi":
            response = (
                f"एफ़आईआर दर्ज होने के बाद अगले कदम:\n\n"
                f"Step 1: एफ़आईआर की निःशुल्क प्रति लें — यह आपका कानूनी अधिकार है (धारा 154(2) CrPC)।\n"
                f"Step 2: एफ़आईआर नम्बर नोट करें — केस ट्रैक करने के लिए ज़रूरी है।\n"
                f"Step 3: हर 2-3 हफ़्ते में जाँच अधिकारी से मिलें और प्रगति पूछें।\n"
                f"Step 4: 30 दिन में कोई कार्यवाही न हो तो पुलिस अधीक्षक को शिकायत करें।\n"
                f"Step 5: मोबाइल चोरी हो तो IMEI नम्बर से ceir.gov.in पर ट्रैक करें।\n"
                f"Step 6: अपने टेलीकॉम प्रदाता को सूचित करें — SIM ब्लॉक करवाएँ।"
            )
        else:
            response = (
                f"After your FIR is registered at {station}, here are the next steps:\n\n"
                f"Step 1: Collect your FIR copy — you are legally entitled to it free of cost (Section 154(2) CrPC).\n"
                f"Step 2: Note your FIR number — use it to track your case status.\n"
                f"Step 3: Follow up with the investigating officer every 2-3 weeks.\n"
                f"Step 4: If no action in 30 days, file a complaint with the Superintendent of Police.\n"
                f"Step 5: For mobile theft, track your phone using IMEI at ceir.gov.in.\n"
                f"Step 6: Contact your telecom provider to block the SIM and IMEI number."
            )
        return {"response": response, "intent": "post_fir", "language": lang, "urgency": False, "follow_up": True}

    # ── Draft FIR request ─────────────────────────────────────────────────────
    if is_draft_fir or (intent == "fir_process" and is_theft_context):
        if lang == "hi":
            response = (
                "एफ़आईआर तैयार करने के लिए मुझे ये जानकारी चाहिए:\n\n"
                "1. आपका पूरा नाम\n"
                "2. घटना की तारीख़ और समय\n"
                "3. घटना का स्थान\n"
                "4. क्या खोया/चोरी हुआ (मोबाइल का IMEI नम्बर भी)\n"
                "5. आरोपी का विवरण (यदि ज्ञात हो)\n\n"
                "FIR Wizard में जाकर इन विवरणों को भरें और PDF तैयार करें।"
            )
        else:
            response = (
                "To draft your FIR, I need the following details:\n\n"
                "1. Your full name\n"
                "2. Date and time of the incident\n"
                "3. Exact location (e.g., KR Puram Railway Station, Platform 2)\n"
                "4. What was stolen/lost (include phone IMEI number if available)\n"
                "5. Suspect description (if known)\n\n"
                "Please go to the FIR Wizard section and fill in these details to generate your FIR PDF."
            )
        return {"response": response, "intent": "fir_process", "language": lang, "urgency": False, "follow_up": True}

    # ── Theft / lost phone ────────────────────────────────────────────────────
    if intent == "theft_complaint" or is_theft:
        station = location_hint or "the nearest police station"
        is_railway = "railway" in lower or "station" in lower or "train" in lower or "railway" in prev_context.lower()

        if lang == "hi":
            response = (
                f"आपका फ़ोन/सामान खोने पर ये कदम उठाएँ:\n\n"
                f"Step 1: {'रेलवे पुलिस (GRP) थाने' if is_railway else 'निकटतम थाने'} में जाएँ — रेलवे परिसर में हुई घटनाओं के लिए रेलवे पुलिस ज़िम्मेदार है।\n"
                f"Step 2: IPC धारा 379 के तहत निःशुल्क FIR दर्ज कराएँ।\n"
                f"Step 3: फ़ोन का IMEI नम्बर दें (*#06# डायल करके पता करें)।\n"
                f"Step 4: अपने टेलीकॉम प्रदाता को सूचित करें — SIM ब्लॉक करवाएँ।\n"
                f"Step 5: ceir.gov.in पर IMEI से फ़ोन ट्रैक/ब्लॉक करें।\n\n"
                f"क्या आप FIR का प्रारूप तैयार करना चाहते हैं?"
            )
        else:
            response = (
                f"Here are the steps to take for your lost/stolen phone:\n\n"
                f"Step 1: Go to {'KR Puram Railway Police Station (GRP)' if is_railway else station} — railway incidents are handled by Railway Police, not regular police.\n"
                f"Step 2: File an FIR under IPC Section 379 (theft) — completely free.\n"
                f"Step 3: Provide your phone's IMEI number (dial *#06# to find it).\n"
                f"Step 4: Report to your telecom provider to block the SIM immediately.\n"
                f"Step 5: Track or block your phone using IMEI at ceir.gov.in (Government of India portal).\n"
                f"Step 6: You can also file an e-FIR online at Karnataka Police website if you cannot visit in person.\n\n"
                f"Would you like me to help you draft the FIR document?"
            )
        return {"response": response, "intent": "theft_complaint", "language": lang, "urgency": False, "follow_up": True}

    # ── Generic fallback with legal context ───────────────────────────────────
    context_note = ""
    if legal_context:
        context_note = f"\n\nLegal reference: {legal_context[:200]}"

    GENERIC = {
        "domestic_violence": {
            "en": "You are protected under the Domestic Violence Act 2005.\n\nStep 1: Call Women Helpline 181 (24/7, free).\nStep 2: Approach a Protection Officer in your district.\nStep 3: File a complaint at the nearest police station.\nStep 4: You can get a Protection Order from court to stop the abuser.\n\nYou are not alone. Help is available right now.",
            "hi": "आप घरेलू हिंसा अधिनियम 2005 के तहत सुरक्षित हैं।\n\nStep 1: महिला हेल्पलाइन 181 पर कॉल करें (24/7, निःशुल्क)।\nStep 2: जिले के संरक्षण अधिकारी से मिलें।\nStep 3: थाने में शिकायत दर्ज करें।\nStep 4: न्यायालय से संरक्षण आदेश प्राप्त करें।",
        },
        "wage_theft": {
            "en": "Your employer must pay full wages on time under the Payment of Wages Act.\n\nStep 1: File a free complaint with the Labour Commissioner in your district.\nStep 2: No lawyer needed — it is completely free.\nStep 3: Call NALSA Helpline 15100 for free legal advice.\nStep 4: You can also approach the Labour Court.",
            "hi": "वेतन भुगतान अधिनियम के तहत नियोक्ता को समय पर वेतन देना होगा।\n\nStep 1: जिले के श्रम आयुक्त के पास निःशुल्क शिकायत करें।\nStep 2: वकील की ज़रूरत नहीं।\nStep 3: नालसा हेल्पलाइन 15100 पर कॉल करें।",
        },
        "general_legal_query": {
            "en": "I can help you with theft, domestic violence, wage theft, harassment, land disputes, cyber crime, consumer rights, and FIR filing.\n\nPlease describe your problem in detail and I will guide you step by step.",
            "hi": "मैं चोरी, घरेलू हिंसा, वेतन चोरी, उत्पीड़न, भूमि विवाद, साइबर अपराध, उपभोक्ता अधिकार और एफ़आईआर में मदद कर सकता हूँ।\n\nअपनी समस्या विस्तार से बताएँ।",
        },
    }

    responses = GENERIC.get(intent, GENERIC["general_legal_query"])
    response_text = responses.get(lang, responses["en"]) + context_note

    disclaimer = (
        "\n\nNote: This is general legal information. Please consult a qualified lawyer for specific advice."
        if lang == "en"
        else "\n\nकृपया ध्यान दें: यह सामान्य कानूनी जानकारी है। विशिष्ट सलाह के लिए वकील से मिलें।"
    )

    return {
        "response": response_text + disclaimer,
        "intent": intent,
        "language": lang,
        "urgency": False,
        "follow_up": True,
    }


# ── Template document fallback ────────────────────────────────────────────────
def _template_document(doc_type: str, details: dict) -> str:
    complainant = details.get("complainant_name", details.get("complainant_id", "The Complainant"))
    incident = details.get("incident_description", "As described verbally")
    date_time = details.get("date_time", "Date not specified")
    location = details.get("location", "Location not specified")
    suspect = details.get("suspect_description", "Unknown")
    witness = details.get("witness", "None provided")

    return f"""{doc_type.upper()}

To,
The Station House Officer / Appropriate Authority,

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
