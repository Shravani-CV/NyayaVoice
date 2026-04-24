
"""
Gemini AI Service for NyayaVoice.
Handles ALL legal cases: theft, land dispute, rape, dowry, corruption,
cyber fraud, domestic violence, harassment, and more.
Uses Gemini to generate accurate, context-aware responses.
"""
import os
import re
import logging
from typing import Dict, List, Any

from backend.config import SUPPORTED_LANGUAGES

logger = logging.getLogger(__name__)

LANG_NAMES = {
    "hi": "Hindi", "en": "English", "ta": "Tamil", "bn": "Bengali",
    "mr": "Marathi", "te": "Telugu", "gu": "Gujarati", "kn": "Kannada",
    "pa": "Punjabi", "ur": "Urdu",
}

EMERGENCY_KEYWORDS = [
    "hitting me", "beating me", "i am in danger", "someone is hurting me",
    "please save me", "bachao", "maaro", "maar raha hai", "maar rahi hai",
    "jaan ka khatra", "meri jaan", "attack kar raha", "rape ho raha",
]

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_AVAILABLE = False
GEMINI_MODEL = None
_client = None

if GEMINI_API_KEY:
    try:
        from google import genai as _genai_module
        _client = _genai_module.Client(api_key=GEMINI_API_KEY)
        _preferred = [
            "gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.0-flash-lite",
            "gemini-2.0-flash-001", "gemini-1.5-flash",
        ]
        for _m in _preferred:
            try:
                _client.models.generate_content(model=_m, contents="hi")
                GEMINI_MODEL = _m
                GEMINI_AVAILABLE = True
                logger.info(f"Gemini ready: {_m}")
                break
            except Exception as _e:
                if "503" in str(_e) or "UNAVAILABLE" in str(_e):
                    GEMINI_MODEL = _m
                    GEMINI_AVAILABLE = True
                    logger.info(f"Gemini ready (high demand): {_m}")
                    break
                logger.debug(f"Model {_m} skip: {str(_e)[:60]}")
        if not GEMINI_AVAILABLE:
            logger.warning("No Gemini model available.")
    except Exception as e:
        logger.warning(f"Gemini init failed: {e}")
else:
    logger.warning("GEMINI_API_KEY not set.")


def detect_language(text: str, fallback: str = "en") -> str:
    if any("\u0900" <= c <= "\u097F" for c in text):
        return "hi"
    return fallback if fallback in SUPPORTED_LANGUAGES else "en"


def is_emergency(text: str) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in EMERGENCY_KEYWORDS)


INTENT_PATTERNS = {
    "theft": r"stolen|theft|chori|snatch|rob|loot|pickpocket|missing.*phone|lost.*phone|phone.*stolen|wallet.*stolen|bag.*stolen",
    "land_dispute": r"land|bhumi|zameen|property|plot|encroach|boundary|occupy|construction.*land|land.*construction|illegal.*build|build.*illegal",
    "domestic_violence": r"domestic.*violen|husband.*beat|wife.*beat|husband.*hit|hit.*wife|498|dv act|gharelu hinsa|pati.*maar|maar.*pati",
    "rape_sexual_assault": r"\brape\b|sexual assault|molestation|pocso|youn.*shos|balaatkar|chhed.*khani|sexual.*abuse|forced.*sex",
    "dowry": r"dowry|dahej|dowry.*harass|dahej.*utpeed",
    "corruption": r"bribe|corruption|bhrashtachar|rishwat|government.*money|officer.*demand|demand.*money.*officer",
    "cyber_crime": r"cyber|hack|online.*fraud|scam|phishing|otp.*fraud|upi.*fraud|bank.*fraud|account.*hacked|sextort|blackmail.*photo",
    "harassment": r"harass|posh|stalking|eve.*teas|follow.*me|threaten|workplace.*harass",
    "wage_theft": r"salary.*not|not.*paid|wage|vetan|unpaid|employer.*money|labour.*right",
    "consumer": r"consumer|refund|defect|warranty|cheated.*product|overcharged|fake.*product",
    "rti": r"\brti\b|right to information|information act",
    "legal_aid": r"free.*lawyer|legal aid|nalsa|dlsa|afford.*lawyer|no money.*lawyer",
    "murder_attempt": r"murder|attempt.*murder|jaan.*lena|khoon|hatya",
    "kidnapping": r"kidnap|abduct|missing.*child|child.*missing|apaharan",
    "accident": r"accident|road.*accident|hit.*run|vehicle.*accident|motor.*accident",
    "cheating_fraud": r"cheated|fraud|420|dhoka|fake.*document|forged|forgery",
    "post_fir": r"after.*fir|next.*step|fir.*register|fir.*filed|what.*after.*fir|follow.*up.*fir|track.*case",
    "draft_fir": r"draft.*fir|help.*fir|write.*fir|file.*fir|fir.*draft|prepare.*fir",
}

def _detect_intent(text: str) -> str:
    lower = text.lower()
    for intent, pattern in INTENT_PATTERNS.items():
        if re.search(pattern, lower, re.IGNORECASE):
            return intent
    return "general"


# ── Master Gemini prompt — handles ALL cases ──────────────────────────────────
_MASTER_PROMPT = """You are NyayaVoice, an expert legal aid assistant for people in India with deep knowledge of all Indian laws.

You handle ALL types of legal cases including:
- Theft, robbery, snatching, pickpocketing
- Land encroachment, illegal construction, property disputes
- Rape, sexual assault, POCSO cases
- Domestic violence, dowry harassment
- Corruption, bribery by government officials
- Cyber crime, online fraud, UPI scam, sextortion
- Workplace harassment (POSH Act)
- Murder, attempt to murder
- Kidnapping, missing persons
- Road accidents, hit and run
- Cheating, forgery, fraud (IPC 420)
- Consumer complaints
- Labour rights, wage theft
- RTI applications
- Any other legal matter

LEGAL KNOWLEDGE BASE (use this):
{legal_context}

CONVERSATION HISTORY:
{history}

USER'S MESSAGE: {user_message}

INSTRUCTIONS:
1. READ the user's message carefully. Identify EXACTLY what legal problem they have.
2. Do NOT assume — if they say "land encroachment" give land encroachment steps, NOT phone theft steps.
3. Give numbered steps (Step 1, Step 2...) specific to THEIR exact situation.
4. Mention the CORRECT Indian law section for their specific case.
5. If they mention a specific location, use it in your response.
6. For railway incidents — mention Railway Police (GRP), not regular police.
7. For land encroachment — mention Revenue Court, Tehsildar, Civil Court.
8. For rape/sexual assault — mention special procedures, one-stop centres, 164 CrPC statement.
9. For corruption — mention Anti-Corruption Bureau, Lokayukta, CVC.
10. For cyber crime — mention cybercrime.gov.in, 1930 helpline.
11. If this is a follow-up question, use the conversation history to understand context.
12. End with: "Would you like me to help you draft a complaint document?" if relevant.
13. Plain text only — no markdown symbols like ** or ##.
14. Respond ONLY in {lang_name}.
15. Do NOT give emergency helpline numbers unless user is in immediate physical danger.

Respond now in {lang_name}:"""


def gemini_generate(
    user_message: str,
    legal_context: str,
    language_code: str,
    conversation_history: List[Dict[str, str]],
    user_id: str,
) -> Dict[str, Any]:
    lang = detect_language(user_message, fallback=language_code)
    lang_name = LANG_NAMES.get(lang, "English")
    intent = _detect_intent(user_message)

    if is_emergency(user_message):
        return _emergency_response(lang)

    if not GEMINI_AVAILABLE or _client is None:
        return _universal_fallback(user_message, lang, legal_context, conversation_history, intent)

    history_str = ""
    if conversation_history:
        recent = [m for m in conversation_history if m.get("role") != "system"][-8:]
        history_str = "\n".join(f"{m['role'].upper()}: {m.get('text','')}" for m in recent)

    prompt = _MASTER_PROMPT.format(
        legal_context=legal_context or "Use your knowledge of Indian law.",
        history=history_str or "This is the first message.",
        user_message=user_message,
        lang_name=lang_name,
    )

    try:
        from google import genai as gm
        response = _client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=gm.types.GenerateContentConfig(temperature=0.3, max_output_tokens=1200),
        )
        return {
            "response": response.text.strip(),
            "intent": intent,
            "language": lang,
            "urgency": False,
            "follow_up": True,
        }
    except Exception as e:
        logger.error(f"Gemini error: {e}")
        return _universal_fallback(user_message, lang, legal_context, conversation_history, intent)


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
Complainant: {complainant}
Incident: {incident}
Date/Time: {date_time}
Location: {location}
Suspect: {suspect}
Witnesses: {witness}

Use formal legal language, correct Indian law sections (IPC, CrPC, etc.).
Structure: Salutation, Subject, Body, Relief Sought, Declaration, Signature."""

    try:
        from google import genai as gm
        r = _client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
        return r.text.strip()
    except Exception as e:
        logger.error(f"Gemini doc error: {e}")
        return _template_document(doc_type, details)


def get_vapi_system_prompt(language: str) -> str:
    lang_name = LANG_NAMES.get(language, "English")
    return (
        f"You are NyayaVoice, an expert legal aid assistant for India. "
        f"ALWAYS respond in {lang_name}. Be warm and empathetic. "
        f"Handle ALL legal cases: theft, land disputes, rape, dowry, corruption, cyber crime, domestic violence, etc. "
        f"Give step-by-step guidance with correct Indian law sections. "
        f"If user is in danger: Police 100, Women Helpline 181, Emergency 112. "
        f"Keep responses SHORT and CLEAR for voice delivery."
    )


EMERGENCY_RESPONSES = {
    "en": "EMERGENCY — Call for help immediately.\nPolice: 100\nWomen Helpline: 181 (24/7)\nEmergency: 112\nChild Helpline: 1098\nYou are not alone. Help is available right now.",
    "hi": "आपातकाल — तुरन्त सहायता के लिए कॉल करें।\nपुलिस: 100\nमहिला हेल्पलाइन: 181 (24/7)\nआपातकाल: 112\nआप अकेले नहीं हैं।",
}

def _emergency_response(lang: str) -> Dict[str, Any]:
    return {"response": EMERGENCY_RESPONSES.get(lang, EMERGENCY_RESPONSES["en"]),
            "intent": "emergency", "language": lang, "urgency": True, "follow_up": False}


# ── Universal fallback — accurate for ALL case types ─────────────────────────
_CASE_RESPONSES = {
    "land_dispute": {
        "en": (
            "Someone has illegally encroached on your land. Here are the steps:\n\n"
            "Step 1: File a complaint at the local police station under IPC Section 447 (criminal trespass) and Section 441.\n"
            "Step 2: Approach the Tehsildar (Revenue Officer) with your land documents — they can issue a stay order on construction.\n"
            "Step 3: File a civil suit for injunction in the Civil Court to stop the illegal construction immediately.\n"
            "Step 4: Gather all documents: sale deed, property tax receipts, Aadhaar-linked land records, survey records.\n"
            "Step 5: File a complaint with the local Municipal Corporation / Panchayat to stop the illegal building permit.\n"
            "Step 6: Contact NALSA Helpline 15100 for free legal aid if you cannot afford a lawyer.\n\n"
            "Would you like me to help you draft a complaint document?"
        ),
        "hi": (
            "किसी ने आपकी ज़मीन पर अवैध कब्ज़ा किया है। ये कदम उठाएँ:\n\n"
            "Step 1: थाने में IPC धारा 447 (आपराधिक अतिचार) और धारा 441 के तहत शिकायत दर्ज करें।\n"
            "Step 2: तहसीलदार (राजस्व अधिकारी) के पास अपने भूमि दस्तावेज़ लेकर जाएँ — वे निर्माण पर रोक लगा सकते हैं।\n"
            "Step 3: सिविल न्यायालय में निषेधाज्ञा (Injunction) के लिए दीवानी मुकदमा दायर करें।\n"
            "Step 4: सभी दस्तावेज़ एकत्र करें: बिक्री विलेख, सम्पत्ति कर रसीदें, भूमि अभिलेख।\n"
            "Step 5: स्थानीय नगर निगम/पंचायत में अवैध निर्माण की शिकायत करें।\n"
            "Step 6: निःशुल्क कानूनी सहायता के लिए नालसा हेल्पलाइन 15100 पर कॉल करें।\n\n"
            "क्या आप शिकायत पत्र तैयार करना चाहते हैं?"
        ),
    },
    "rape_sexual_assault": {
        "en": (
            "This is a serious crime. You have strong legal protection. Here are the steps:\n\n"
            "Step 1: Call Police 100 or Women Helpline 181 immediately — they must respond.\n"
            "Step 2: Go to the nearest government hospital for medical examination — this is free and confidential.\n"
            "Step 3: File an FIR at any police station under IPC Section 376 (rape) — police MUST register it.\n"
            "Step 4: Your statement will be recorded by a Magistrate under Section 164 CrPC — this is important evidence.\n"
            "Step 5: Your identity is protected by law — no media can reveal your name.\n"
            "Step 6: Contact One Stop Centre (Sakhi Centre) — call 181 for free medical, legal, and psychological support.\n"
            "Step 7: Contact NALSA Helpline 15100 for free legal representation.\n\n"
            "You are not alone. Help is available right now."
        ),
        "hi": (
            "यह एक गम्भीर अपराध है। आपको कानूनी सुरक्षा प्राप्त है। ये कदम उठाएँ:\n\n"
            "Step 1: तुरन्त पुलिस 100 या महिला हेल्पलाइन 181 पर कॉल करें।\n"
            "Step 2: निकटतम सरकारी अस्पताल में चिकित्सा जाँच कराएँ — यह निःशुल्क और गोपनीय है।\n"
            "Step 3: किसी भी थाने में IPC धारा 376 के तहत FIR दर्ज कराएँ — पुलिस को दर्ज करना ही होगा।\n"
            "Step 4: धारा 164 CrPC के तहत मजिस्ट्रेट के सामने बयान दर्ज होगा — यह महत्त्वपूर्ण साक्ष्य है।\n"
            "Step 5: आपकी पहचान कानून द्वारा सुरक्षित है — कोई मीडिया आपका नाम नहीं बता सकता।\n"
            "Step 6: वन स्टॉप सेंटर (सखी केंद्र) से सम्पर्क करें — 181 पर कॉल करें।\n"
            "Step 7: निःशुल्क कानूनी सहायता के लिए नालसा हेल्पलाइन 15100 पर कॉल करें।\n\n"
            "आप अकेले नहीं हैं। सहायता अभी उपलब्ध है।"
        ),
    },
    "dowry": {
        "en": (
            "Dowry harassment is a serious crime under Indian law. Here are the steps:\n\n"
            "Step 1: File an FIR under IPC Section 498A (cruelty for dowry) and Dowry Prohibition Act 1961.\n"
            "Step 2: Call Women Helpline 181 (24/7) for immediate support.\n"
            "Step 3: Approach the nearest police station — they must register your complaint.\n"
            "Step 4: File a complaint under the Domestic Violence Act 2005 for protection orders.\n"
            "Step 5: Contact One Stop Centre (Sakhi) — call 181 for free legal and psychological support.\n"
            "Step 6: Preserve all evidence — messages, photos, witnesses, medical reports.\n\n"
            "Would you like me to help you draft a complaint?"
        ),
        "hi": (
            "दहेज उत्पीड़न भारतीय कानून के तहत गम्भीर अपराध है। ये कदम उठाएँ:\n\n"
            "Step 1: IPC धारा 498अ (दहेज के लिए क्रूरता) और दहेज प्रतिषेध अधिनियम 1961 के तहत FIR दर्ज करें।\n"
            "Step 2: महिला हेल्पलाइन 181 पर कॉल करें (24/7)।\n"
            "Step 3: निकटतम थाने में शिकायत दर्ज करें।\n"
            "Step 4: घरेलू हिंसा अधिनियम 2005 के तहत संरक्षण आदेश के लिए आवेदन करें।\n"
            "Step 5: सखी वन स्टॉप सेंटर से सम्पर्क करें — 181 पर कॉल करें।\n"
            "Step 6: सभी साक्ष्य सुरक्षित रखें — संदेश, फ़ोटो, गवाह, चिकित्सा रिपोर्ट।"
        ),
    },
    "corruption": {
        "en": (
            "Corruption by a government official is a serious offence. Here are the steps:\n\n"
            "Step 1: File a complaint with the Anti-Corruption Bureau (ACB) in your state.\n"
            "Step 2: File a complaint with the Lokayukta (State Ombudsman) — they have strong powers.\n"
            "Step 3: File a complaint under Prevention of Corruption Act 1988 at the nearest police station.\n"
            "Step 4: You can also file a complaint with the Central Vigilance Commission (CVC) at cvc.gov.in.\n"
            "Step 5: File an RTI application to get information about the official's actions.\n"
            "Step 6: Preserve all evidence — record conversations if possible, keep receipts.\n\n"
            "Would you like me to help you draft a complaint?"
        ),
        "hi": (
            "सरकारी अधिकारी द्वारा भ्रष्टाचार गम्भीर अपराध है। ये कदम उठाएँ:\n\n"
            "Step 1: अपने राज्य के भ्रष्टाचार निरोधक ब्यूरो (ACB) में शिकायत दर्ज करें।\n"
            "Step 2: लोकायुक्त (राज्य लोकपाल) के पास शिकायत करें — उनके पास व्यापक अधिकार हैं।\n"
            "Step 3: भ्रष्टाचार निवारण अधिनियम 1988 के तहत थाने में शिकायत दर्ज करें।\n"
            "Step 4: केंद्रीय सतर्कता आयोग (CVC) को cvc.gov.in पर शिकायत करें।\n"
            "Step 5: अधिकारी की कार्यवाही की जानकारी के लिए RTI आवेदन दाखिल करें।\n"
            "Step 6: सभी साक्ष्य सुरक्षित रखें — बातचीत रिकॉर्ड करें, रसीदें रखें।"
        ),
    },
    "cyber_crime": {
        "en": (
            "You are a victim of cyber crime. Here are the steps:\n\n"
            "Step 1: Report immediately at cybercrime.gov.in or call 1930 (Cyber Crime Helpline).\n"
            "Step 2: File an FIR at your local police station under IT Act 2000 and IPC 420 (cheating).\n"
            "Step 3: For bank/UPI fraud — call your bank immediately to freeze the transaction.\n"
            "Step 4: For sextortion/blackmail — do NOT pay. Report to cybercrime.gov.in immediately.\n"
            "Step 5: Preserve all evidence — screenshots, transaction IDs, emails, chat history.\n"
            "Step 6: For social media hacking — report to the platform and change all passwords.\n\n"
            "Would you like me to help you draft a complaint?"
        ),
        "hi": (
            "आप साइबर अपराध के शिकार हैं। ये कदम उठाएँ:\n\n"
            "Step 1: तुरन्त cybercrime.gov.in पर या 1930 (साइबर क्राइम हेल्पलाइन) पर रिपोर्ट करें।\n"
            "Step 2: IT अधिनियम 2000 और IPC 420 के तहत थाने में FIR दर्ज करें।\n"
            "Step 3: बैंक/UPI धोखाधड़ी पर तुरन्त बैंक को कॉल करें — लेनदेन फ्रीज़ करवाएँ।\n"
            "Step 4: सेक्सटॉर्शन/ब्लैकमेल पर पैसे न दें। तुरन्त cybercrime.gov.in पर रिपोर्ट करें।\n"
            "Step 5: सभी साक्ष्य सुरक्षित रखें — स्क्रीनशॉट, लेनदेन आईडी, ईमेल।\n"
            "Step 6: सोशल मीडिया हैकिंग पर प्लेटफ़ॉर्म को रिपोर्ट करें और पासवर्ड बदलें।"
        ),
    },
    "theft": {
        "en": (
            "Here are the steps to take for theft/stolen property:\n\n"
            "Step 1: File an FIR at the nearest police station under IPC Section 379 (theft) — completely free.\n"
            "Step 2: For railway station theft — go to Railway Police (GRP), not regular police.\n"
            "Step 3: For phone theft — provide your IMEI number (dial *#06# to find it).\n"
            "Step 4: Report to your telecom provider to block the SIM immediately.\n"
            "Step 5: Track your phone using IMEI at ceir.gov.in.\n"
            "Step 6: You can file a Zero FIR at ANY police station — jurisdiction does not matter.\n\n"
            "Would you like me to help you draft the FIR document?"
        ),
        "hi": (
            "चोरी/सामान खोने पर ये कदम उठाएँ:\n\n"
            "Step 1: निकटतम थाने में IPC धारा 379 के तहत निःशुल्क FIR दर्ज कराएँ।\n"
            "Step 2: रेलवे स्टेशन पर चोरी हो तो रेलवे पुलिस (GRP) के पास जाएँ।\n"
            "Step 3: फ़ोन चोरी पर IMEI नम्बर दें (*#06# डायल करें)।\n"
            "Step 4: टेलीकॉम प्रदाता को सूचित करें — SIM ब्लॉक करवाएँ।\n"
            "Step 5: ceir.gov.in पर IMEI से फ़ोन ट्रैक करें।\n"
            "Step 6: किसी भी थाने में ज़ीरो FIR दर्ज करा सकते हैं।"
        ),
    },
    "murder_attempt": {
        "en": (
            "Attempt to murder is a serious cognizable offence. Here are the steps:\n\n"
            "Step 1: Call Police 100 immediately if you are in danger.\n"
            "Step 2: File an FIR under IPC Section 307 (attempt to murder) at the nearest police station.\n"
            "Step 3: Get a medical examination done immediately — this is crucial evidence.\n"
            "Step 4: Preserve all evidence — CCTV footage, witnesses, injury photos.\n"
            "Step 5: Apply for anticipatory bail protection if threatened.\n"
            "Step 6: Contact NALSA Helpline 15100 for free legal representation."
        ),
        "hi": (
            "हत्या का प्रयास गम्भीर संज्ञेय अपराध है। ये कदम उठाएँ:\n\n"
            "Step 1: खतरे में हों तो तुरन्त पुलिस 100 पर कॉल करें।\n"
            "Step 2: निकटतम थाने में IPC धारा 307 (हत्या का प्रयास) के तहत FIR दर्ज करें।\n"
            "Step 3: तुरन्त चिकित्सा जाँच कराएँ — यह महत्त्वपूर्ण साक्ष्य है।\n"
            "Step 4: सभी साक्ष्य सुरक्षित रखें — CCTV, गवाह, चोट की फ़ोटो।\n"
            "Step 5: धमकी मिल रही हो तो अग्रिम ज़मानत के लिए आवेदन करें।\n"
            "Step 6: निःशुल्क कानूनी सहायता के लिए नालसा हेल्पलाइन 15100 पर कॉल करें।"
        ),
    },
    "cheating_fraud": {
        "en": (
            "You have been cheated/defrauded. Here are the steps:\n\n"
            "Step 1: File an FIR under IPC Section 420 (cheating) at the nearest police station.\n"
            "Step 2: If fake documents were used — add IPC Section 468 (forgery) to the complaint.\n"
            "Step 3: Preserve all evidence — contracts, receipts, messages, emails.\n"
            "Step 4: For property fraud — approach the Sub-Registrar office and Revenue Court.\n"
            "Step 5: File a complaint with the Economic Offences Wing (EOW) of police for large frauds.\n"
            "Step 6: Contact NALSA Helpline 15100 for free legal advice.\n\n"
            "Would you like me to help you draft a complaint?"
        ),
        "hi": (
            "आपके साथ धोखाधड़ी हुई है। ये कदम उठाएँ:\n\n"
            "Step 1: निकटतम थाने में IPC धारा 420 (धोखाधड़ी) के तहत FIR दर्ज करें।\n"
            "Step 2: नकली दस्तावेज़ इस्तेमाल हुए हों तो IPC धारा 468 (जालसाज़ी) भी जोड़ें।\n"
            "Step 3: सभी साक्ष्य सुरक्षित रखें — अनुबंध, रसीदें, संदेश, ईमेल।\n"
            "Step 4: सम्पत्ति धोखाधड़ी पर उप-पंजीयक कार्यालय और राजस्व न्यायालय जाएँ।\n"
            "Step 5: बड़ी धोखाधड़ी पर पुलिस के आर्थिक अपराध प्रकोष्ठ (EOW) में शिकायत करें।\n"
            "Step 6: नालसा हेल्पलाइन 15100 पर निःशुल्क कानूनी सलाह लें।"
        ),
    },
    "post_fir": {
        "en": (
            "After your FIR is registered, here are the next steps:\n\n"
            "Step 1: Collect your FIR copy — you are legally entitled to it free of cost (Section 154(2) CrPC).\n"
            "Step 2: Note your FIR number — use it to track your case status.\n"
            "Step 3: Follow up with the investigating officer every 2-3 weeks.\n"
            "Step 4: If no action in 30 days, file a complaint with the Superintendent of Police.\n"
            "Step 5: If police are inactive, file a complaint in court under Section 156(3) CrPC.\n"
            "Step 6: Contact NALSA Helpline 15100 for free legal representation in court."
        ),
        "hi": (
            "FIR दर्ज होने के बाद अगले कदम:\n\n"
            "Step 1: FIR की निःशुल्क प्रति लें — यह आपका कानूनी अधिकार है (धारा 154(2) CrPC)।\n"
            "Step 2: FIR नम्बर नोट करें — केस ट्रैक करने के लिए ज़रूरी है।\n"
            "Step 3: हर 2-3 हफ़्ते में जाँच अधिकारी से मिलें।\n"
            "Step 4: 30 दिन में कोई कार्यवाही न हो तो पुलिस अधीक्षक को शिकायत करें।\n"
            "Step 5: पुलिस निष्क्रिय हो तो धारा 156(3) CrPC के तहत न्यायालय में शिकायत करें।\n"
            "Step 6: नालसा हेल्पलाइन 15100 पर निःशुल्क कानूनी सहायता लें।"
        ),
    },
    "general": {
        "en": (
            "I can help you with all types of legal cases in India including:\n\n"
            "- Theft, robbery, snatching\n"
            "- Land encroachment, property disputes\n"
            "- Rape, sexual assault\n"
            "- Domestic violence, dowry harassment\n"
            "- Corruption, bribery\n"
            "- Cyber crime, online fraud\n"
            "- Workplace harassment\n"
            "- Murder, kidnapping\n"
            "- Consumer complaints\n"
            "- Labour rights, wage theft\n\n"
            "Please describe your specific problem in detail and I will guide you step by step."
        ),
        "hi": (
            "मैं भारत में सभी प्रकार के कानूनी मामलों में मदद कर सकता हूँ:\n\n"
            "- चोरी, डकैती, छीनाझपटी\n"
            "- भूमि अतिक्रमण, सम्पत्ति विवाद\n"
            "- बलात्कार, यौन उत्पीड़न\n"
            "- घरेलू हिंसा, दहेज उत्पीड़न\n"
            "- भ्रष्टाचार, रिश्वत\n"
            "- साइबर अपराध, ऑनलाइन धोखाधड़ी\n"
            "- कार्यस्थल उत्पीड़न\n"
            "- हत्या, अपहरण\n"
            "- उपभोक्ता शिकायतें\n"
            "- श्रम अधिकार, वेतन चोरी\n\n"
            "अपनी समस्या विस्तार से बताएँ और मैं चरण-दर-चरण मार्गदर्शन करूँगा।"
        ),
    },
}


def _universal_fallback(
    user_message: str,
    lang: str,
    legal_context: str,
    conversation_history: List[Dict[str, str]] = None,
    intent: str = "general",
) -> Dict[str, Any]:
    """
    Universal fallback — picks the correct response based on detected intent.
    No hardcoded location or case-specific assumptions.
    """
    case_data = _CASE_RESPONSES.get(intent, _CASE_RESPONSES["general"])
    response_text = case_data.get(lang, case_data["en"])

    if legal_context and len(legal_context) > 30:
        snippet = legal_context[:250]
        if lang == "hi":
            response_text += f"\n\nकानूनी सन्दर्भ: {snippet}"
        else:
            response_text += f"\n\nLegal reference: {snippet}"

    return {
        "response": response_text,
        "intent": intent,
        "language": lang,
        "urgency": False,
        "follow_up": True,
    }


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

INCIDENT DETAILS: {incident}
DATE AND TIME: {date_time}
LOCATION: {location}
ACCUSED/SUSPECT: {suspect}
WITNESSES: {witness}

I request appropriate action as per Indian law.

Yours faithfully,
{complainant}

Note: Under Section 154 CrPC, police must register FIRs. Refusal is punishable under Section 166A IPC.
"""
