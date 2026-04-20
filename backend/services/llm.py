"""
Response engine — works without any external LLM API.
Uses Qdrant semantic search + keyword intent detection + template formatting.
Voice calls go through Vapi (which handles LLM on its own credits).
"""
import re
import logging
from typing import Dict, List, Any, Optional

from backend.config import SUPPORTED_LANGUAGES, EMERGENCY_KEYWORDS
from backend.services.qdrant import search_legal_knowledge, get_user_memory

logger = logging.getLogger(__name__)

INTENT_PATTERNS: Dict[str, str] = {
    "theft_complaint": r"chori|theft|stolen|चोरी|phone|फ़ोन|snatch|rob|loot|लूट|missing|lost.*phone|phone.*lost|phone.*stolen|mobile|wallet|purse|bag.*stolen|stolen.*bag|pickpocket|गुम|खो गया|चोरी हो",
    "domestic_violence": r"violen|hinsa|हिंसा|मार|domestic|abuse|beat|पीट|dv|498|husband|wife.*hit|hit.*wife|घरेलू|पति|पत्नी",
    "harassment": r"harass|posh|उत्पीड़|stalking|eve.?teas|molestation|छेड़|follow|threaten|bother",
    "wage_theft": r"wage|vetan|वेतन|salary|pay|भुगतान|mazduri|मज़दूरी|labour|labor|not paid|unpaid|employer|boss.*salary|salary.*not",
    "land_dispute": r"land|bhumi|भूमि|ज़मीन|zameen|property|सम्पत्ति|plot|encroach|boundary|neighbour.*land|land.*dispute",
    "cyber_crime": r"cyber|hack|online|fraud|धोखा|ऑनलाइन|scam|phishing|sextort|otp|upi|bank.*fraud|fraud.*bank|account.*hacked",
    "consumer_rights": r"consumer|उपभोक्ता|refund|product|defect|warranty|खराब|cheated|overcharged|not delivered|fake product",
    "rti": r"rti|सूचना|right to info|आरटीआई|information act|government.*info|info.*government",
    "fir_process": r"fir|एफ़आईआर|first information|zero fir|police station|थाना|file.*complaint|complaint.*file|register.*complaint",
    "legal_aid": r"free legal|legal aid|nalsa|नालसा|dlsa|free lawyer|15100|afford.*lawyer|no money.*lawyer",
    "child_rights": r"child|बच्च|pocso|juvenile|1098|minor|kid|son.*abuse|daughter.*abuse",
    "emergency": r"emergency|help me|bachao|बचाओ|danger|khatra|खतरा|jaan|kill|मार|attack|assault|threat",
}

EMERGENCY_RESPONSE: Dict[str, str] = {
    "en": (
        "**EMERGENCY — Call for help immediately:**\n\n"
        "- Police: **100**\n"
        "- Women Helpline: **181** (24/7)\n"
        "- Emergency (all services): **112**\n"
        "- Child Helpline: **1098**\n"
        "- Cyber Crime: **1930**\n\n"
        "You are not alone. Help is available right now. If you are in physical danger, call 112 immediately."
    ),
    "hi": (
        "**आपातकाल — तुरन्त सहायता के लिए कॉल करें:**\n\n"
        "- पुलिस: **100**\n"
        "- महिला हेल्पलाइन: **181** (24/7)\n"
        "- आपातकाल (सभी सेवाएँ): **112**\n"
        "- बाल हेल्पलाइन: **1098**\n"
        "- साइबर अपराध: **1930**\n\n"
        "आप अकेले नहीं हैं। सहायता अभी उपलब्ध है। यदि आप शारीरिक खतरे में हैं, तो तुरन्त 112 पर कॉल करें।"
    ),
}


def detect_intent(user_message: str, language_code: str = "en") -> Dict[str, Any]:
    """
    Detect the intent and language of the user's message.
    Language is determined by:
    1. Devanagari characters in the message (definitive Hindi)
    2. The language_code passed from the frontend (user's selected language)
    3. Default to English
    """
    if not user_message or not isinstance(user_message, str):
        return {
            "intent": "general_legal_query",
            "language": language_code or "en",
            "urgency": False,
            "summary": "",
        }

    lower = user_message.lower()
    urgency = any(kw in lower for kw in EMERGENCY_KEYWORDS)

    detected_intent = "general_legal_query"
    for intent, pattern in INTENT_PATTERNS.items():
        if re.search(pattern, lower, re.IGNORECASE):
            detected_intent = intent
            break

    # Detect language: Devanagari script → definitive Hindi
    # Otherwise trust the language_code sent from the frontend (user's selected language)
    has_devanagari = any("\u0900" <= c <= "\u097F" for c in user_message)
    if has_devanagari:
        detected_lang = "hi"
    elif language_code in ("hi", "en"):
        detected_lang = language_code
    else:
        detected_lang = "en"

    return {
        "intent": detected_intent,
        "language": detected_lang,
        "urgency": urgency,
        "summary": user_message[:100],
    }


def generate_response(
    user_id: str,
    user_message: str,
    conversation: List[Dict[str, Any]],
    language_code: str = "en",
) -> Dict[str, Any]:
    """
    Generate a response using Qdrant RAG search (no LLM API needed).
    For voice calls, Vapi handles the LLM on its own credits.
    """
    try:
        # Pass language_code so detect_intent respects the user's selected language
        intent_data = detect_intent(user_message, language_code=language_code)
        intent = intent_data.get("intent", "general_legal_query")
        detected_lang = intent_data.get("language", language_code)
        urgency = intent_data.get("urgency", False)

        if urgency or intent == "emergency":
            emergency_text = EMERGENCY_RESPONSE.get(detected_lang, EMERGENCY_RESPONSE["en"])
            legal_results = search_legal_knowledge(user_message, top_k=2)
            if legal_results:
                emergency_text += "\n\n---\n\n" + _format_legal_results(legal_results, detected_lang)
            return {
                "response": emergency_text,
                "intent": "emergency",
                "language": detected_lang,
                "follow_up": False,
                "urgency": True,
            }

        legal_results = search_legal_knowledge(user_message, top_k=4)
        memories = get_user_memory(user_id, top_k=2)

        if legal_results and legal_results[0]["score"] > 0.1:
            reply = _format_legal_results(legal_results, detected_lang)
        else:
            # Score too low — use intent-based direct response instead
            reply = _intent_based_response(intent, detected_lang)

        if memories:
            memory_note = _format_memory_note(memories, detected_lang)
            reply = memory_note + "\n\n" + reply

        reply += "\n\n" + _disclaimer(detected_lang)

        store_turn(user_id, user_message, reply, intent)

        return {
            "response": reply,
            "intent": intent,
            "language": detected_lang,
            "follow_up": True,
            "urgency": False,
        }
    except Exception as e:
        logger.error(f"Error generating response for user {user_id}: {str(e)}", exc_info=True)
        return {
            "response": (
                "मुझे खेद है, अभी आपके अनुरोध को संसाधित करने में समस्या हो रही है।"
                if language_code == "hi"
                else "I apologize, but I'm having trouble processing your request right now. Please try again."
            ),
            "intent": "error",
            "language": language_code,
            "follow_up": False,
            "urgency": False,
        }


def store_turn(user_id, user_message, reply, intent):
    """Store the conversation turn for memory."""
    from backend.services.qdrant import store_conversation
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
        logger.warning(f"Failed to store turn: {e}")


def _format_legal_results(results: list, lang: str) -> str:
    lines = []
    for r in results:
        content = r["content"]
        category = r["category"].replace("_", " ").title()
        score = r["score"]
        if score < 0.25:
            continue
        lines.append(f"**[{category}]** {content}")

    if not lines:
        return _generic_guidance(lang)

    if lang == "hi":
        header = "**आपके प्रश्न से सम्बन्धित कानूनी जानकारी:**"
        footer = "\n\nक्या आप इनमें से किसी विषय पर और विस्तार से जानना चाहते हैं?"
    else:
        header = "**Legal information relevant to your query:**"
        footer = "\n\nWould you like to know more about any of these topics?"

    return header + "\n\n" + "\n\n".join(lines) + footer


def _intent_based_response(intent: str, lang: str) -> str:
    """Return a direct, intent-specific response when Qdrant scores are too low."""
    responses = {
        "theft_complaint": {
            "en": (
                "**Theft / Lost Property — Your Legal Rights:**\n\n"
                "**[Theft]** If your phone, wallet, or any belonging was stolen or lost due to theft, "
                "you have the right to file a **First Information Report (FIR)** at the nearest police station — completely **free**.\n\n"
                "**Steps to take:**\n"
                "- Go to the nearest police station and file an FIR under **IPC Section 379** (theft)\n"
                "- You can file a **Zero FIR** at ANY police station — jurisdiction doesn't matter\n"
                "- Police MUST register your FIR. Refusal is punishable under **Section 166A IPC**\n"
                "- Get a free copy of your FIR — you are legally entitled to it\n"
                "- For mobile theft, also report to your telecom provider to block the SIM/IMEI\n\n"
                "Would you like to use the **FIR Wizard** to draft your complaint?"
            ),
            "hi": (
                "**चोरी / गुम सामान — आपके कानूनी अधिकार:**\n\n"
                "**[चोरी]** यदि आपका फ़ोन, बटुआ या कोई सामान चोरी हुआ है या गुम हो गया है, "
                "तो आप निकटतम थाने में **प्रथम सूचना रिपोर्ट (एफ़आईआर)** दर्ज करा सकते हैं — पूरी तरह **निःशुल्क**।\n\n"
                "**क्या करें:**\n"
                "- निकटतम थाने में जाएँ और **भारतीय दण्ड संहिता धारा 379** के तहत एफ़आईआर दर्ज कराएँ\n"
                "- किसी भी थाने में **ज़ीरो एफ़आईआर** दर्ज करा सकते हैं — क्षेत्राधिकार की चिंता नहीं\n"
                "- पुलिस को एफ़आईआर दर्ज करनी ही होगी। मना करना **धारा 166अ** के तहत दण्डनीय है\n"
                "- एफ़आईआर की निःशुल्क प्रति लें — यह आपका कानूनी अधिकार है\n"
                "- मोबाइल चोरी पर अपने टेलीकॉम प्रदाता को भी सूचित करें\n\n"
                "क्या आप **एफ़आईआर विज़ार्ड** से अपनी शिकायत तैयार करना चाहते हैं?"
            ),
        },
        "domestic_violence": {
            "en": (
                "**Domestic Violence — Your Legal Protection:**\n\n"
                "**[Domestic Violence]** Under the **Protection of Women from Domestic Violence Act 2005**, "
                "any woman facing physical, emotional, sexual, or economic abuse can file a complaint.\n\n"
                "**Immediate steps:**\n"
                "- Call **Women Helpline: 181** (24/7, free)\n"
                "- Call **Police: 100** if in immediate danger\n"
                "- Approach a **Protection Officer** in your district\n"
                "- You can get a **Protection Order** to stop the abuser\n"
                "- You have the right to stay in your home (Residence Order)\n\n"
                "You are not alone. Help is available right now."
            ),
            "hi": (
                "**घरेलू हिंसा — आपकी कानूनी सुरक्षा:**\n\n"
                "**[घरेलू हिंसा]** **घरेलू हिंसा से महिलाओं की सुरक्षा अधिनियम 2005** के तहत "
                "शारीरिक, मानसिक, यौन या आर्थिक शोषण की शिकार कोई भी महिला शिकायत दर्ज करा सकती है।\n\n"
                "**तुरन्त करें:**\n"
                "- **महिला हेल्पलाइन: 181** पर कॉल करें (24/7, निःशुल्क)\n"
                "- तत्काल खतरे में हों तो **पुलिस: 100** पर कॉल करें\n"
                "- अपने जिले के **संरक्षण अधिकारी** से सम्पर्क करें\n"
                "- **संरक्षण आदेश** प्राप्त करें जो आरोपी को आपसे दूर रखेगा\n"
                "- आपको अपने घर में रहने का अधिकार है (निवास आदेश)\n\n"
                "आप अकेले नहीं हैं। सहायता अभी उपलब्ध है।"
            ),
        },
        "wage_theft": {
            "en": (
                "**Wage Theft / Unpaid Salary — Your Rights:**\n\n"
                "**[Labour Rights]** Every worker has the right to receive full wages on time under the **Payment of Wages Act**.\n\n"
                "**Steps to take:**\n"
                "- File a complaint with the **Labour Commissioner** in your district — free, no lawyer needed\n"
                "- Contact **NALSA Helpline: 15100** for free legal advice\n"
                "- Migrant workers have the same rights as local workers\n"
                "- You can also approach the **Labour Court** for unpaid wages"
            ),
            "hi": (
                "**वेतन चोरी / वेतन न मिलना — आपके अधिकार:**\n\n"
                "**[श्रम अधिकार]** **वेतन भुगतान अधिनियम** के तहत हर कर्मचारी को समय पर पूरा वेतन पाने का अधिकार है।\n\n"
                "**क्या करें:**\n"
                "- अपने जिले के **श्रम आयुक्त** के पास शिकायत दर्ज करें — निःशुल्क, वकील की ज़रूरत नहीं\n"
                "- निःशुल्क कानूनी सलाह के लिए **नालसा हेल्पलाइन: 15100** पर कॉल करें\n"
                "- प्रवासी मज़दूरों को भी स्थानीय कर्मचारियों जैसे अधिकार हैं\n"
                "- **श्रम न्यायालय** में भी जा सकते हैं"
            ),
        },
        "harassment": {
            "en": (
                "**Harassment — Your Legal Rights:**\n\n"
                "**[Harassment]** You have strong legal protection against harassment.\n\n"
                "- **Workplace harassment:** File complaint under **POSH Act 2013** with your company's ICC within 3 months\n"
                "- **Street harassment:** File FIR under **IPC Section 354**\n"
                "- **Online harassment/stalking:** Report at **cybercrime.gov.in** or call **1930**\n"
                "- Call **Police: 100** or **Women Helpline: 181** for immediate help"
            ),
            "hi": (
                "**उत्पीड़न — आपके कानूनी अधिकार:**\n\n"
                "**[उत्पीड़न]** उत्पीड़न के विरुद्ध आपको कानूनी सुरक्षा प्राप्त है।\n\n"
                "- **कार्यस्थल उत्पीड़न:** **पॉश अधिनियम 2013** के तहत 3 माह में ICC में शिकायत करें\n"
                "- **सार्वजनिक उत्पीड़न:** **भारतीय दण्ड संहिता धारा 354** के तहत एफ़आईआर दर्ज करें\n"
                "- **ऑनलाइन उत्पीड़न:** **cybercrime.gov.in** पर या **1930** पर रिपोर्ट करें\n"
                "- तुरन्त सहायता के लिए **पुलिस: 100** या **महिला हेल्पलाइन: 181** पर कॉल करें"
            ),
        },
        "cyber_crime": {
            "en": (
                "**Cyber Crime — How to Report:**\n\n"
                "**[Cyber Crime]** If you are a victim of online fraud, UPI scam, OTP theft, or hacking:\n\n"
                "- Report immediately at **cybercrime.gov.in** or call **1930** (Cyber Crime Helpline)\n"
                "- File an FIR at your local police station under the **IT Act 2000**\n"
                "- For bank fraud, also call your bank immediately to block transactions\n"
                "- Save all evidence: screenshots, transaction IDs, emails, chat history"
            ),
            "hi": (
                "**साइबर अपराध — कैसे रिपोर्ट करें:**\n\n"
                "**[साइबर अपराध]** यदि आप ऑनलाइन धोखाधड़ी, UPI स्कैम, OTP चोरी या हैकिंग के शिकार हैं:\n\n"
                "- तुरन्त **cybercrime.gov.in** पर या **1930** (साइबर क्राइम हेल्पलाइन) पर रिपोर्ट करें\n"
                "- **सूचना प्रौद्योगिकी अधिनियम 2000** के तहत थाने में एफ़आईआर दर्ज करें\n"
                "- बैंक धोखाधड़ी पर तुरन्त अपने बैंक को भी सूचित करें\n"
                "- सभी साक्ष्य सुरक्षित रखें: स्क्रीनशॉट, लेनदेन आईडी, ईमेल"
            ),
        },
        "fir_process": {
            "en": (
                "**How to File an FIR:**\n\n"
                "**[FIR Process]** An FIR is the first step in reporting any crime to the police.\n\n"
                "- Go to the nearest police station — filing is **completely free**\n"
                "- You can file at **ANY** police station (Zero FIR) — jurisdiction doesn't matter\n"
                "- Police MUST register your FIR under **Section 154 CrPC**\n"
                "- If refused, complain to the **Superintendent of Police** or file in court under **Section 156(3) CrPC**\n"
                "- You are entitled to a **free copy** of your FIR\n\n"
                "Use the **FIR Wizard** in the sidebar to draft your FIR step by step."
            ),
            "hi": (
                "**एफ़आईआर कैसे दर्ज करें:**\n\n"
                "**[एफ़आईआर प्रक्रिया]** एफ़आईआर किसी भी अपराध की रिपोर्ट करने का पहला कदम है।\n\n"
                "- निकटतम थाने में जाएँ — दर्ज करना पूरी तरह **निःशुल्क** है\n"
                "- किसी भी थाने में **ज़ीरो एफ़आईआर** दर्ज करा सकते हैं\n"
                "- **दण्ड प्रक्रिया संहिता धारा 154** के तहत पुलिस को एफ़आईआर दर्ज करनी ही होगी\n"
                "- मना करने पर **पुलिस अधीक्षक** को शिकायत करें या **धारा 156(3)** के तहत न्यायालय जाएँ\n"
                "- एफ़आईआर की **निःशुल्क प्रति** पाने का आपको अधिकार है\n\n"
                "साइडबार में **एफ़आईआर विज़ार्ड** से चरण-दर-चरण एफ़आईआर तैयार करें।"
            ),
        },
        "legal_aid": {
            "en": (
                "**Free Legal Aid — Available to Everyone:**\n\n"
                "**[Legal Aid]** You have the right to free legal help if you cannot afford a lawyer.\n\n"
                "- Call **NALSA Helpline: 15100** for free legal advice (National Legal Services Authority)\n"
                "- Visit your **District Legal Services Authority (DLSA)** office\n"
                "- Women, children, SC/ST, disabled persons, and BPL families get free legal aid under the **Legal Services Authorities Act 1987**\n"
                "- **Lok Adalats** provide free and fast dispute resolution"
            ),
            "hi": (
                "**निःशुल्क कानूनी सहायता — सभी के लिए उपलब्ध:**\n\n"
                "**[कानूनी सहायता]** यदि आप वकील का खर्च नहीं उठा सकते, तो आपको निःशुल्क कानूनी सहायता का अधिकार है।\n\n"
                "- निःशुल्क कानूनी सलाह के लिए **नालसा हेल्पलाइन: 15100** पर कॉल करें\n"
                "- अपने जिले के **जिला विधिक सेवा प्राधिकरण (DLSA)** कार्यालय जाएँ\n"
                "- महिलाएँ, बच्चे, SC/ST, दिव्यांग और BPL परिवार **विधिक सेवा प्राधिकरण अधिनियम 1987** के तहत निःशुल्क सहायता पाने के हकदार हैं\n"
                "- **लोक अदालत** में निःशुल्क और त्वरित विवाद समाधान होता है"
            ),
        },
        "land_dispute": {
            "en": (
                "**Land / Property Dispute — Your Rights:**\n\n"
                "**[Land Dispute]** If someone has illegally occupied your land or property:\n\n"
                "- File a complaint at the local **police station** or approach the **Revenue Court (Tehsildar)**\n"
                "- Keep all documents: sale deed, property tax receipts, Aadhaar-linked land records\n"
                "- You can file a **civil suit for possession** in court\n"
                "- Contact **NALSA Helpline: 15100** for free legal advice"
            ),
            "hi": (
                "**भूमि / सम्पत्ति विवाद — आपके अधिकार:**\n\n"
                "**[भूमि विवाद]** यदि किसी ने आपकी ज़मीन या सम्पत्ति पर अवैध कब्ज़ा किया है:\n\n"
                "- स्थानीय **थाने** में शिकायत दर्ज करें या **राजस्व न्यायालय (तहसीलदार)** से सम्पर्क करें\n"
                "- सभी दस्तावेज़ सुरक्षित रखें: बिक्री विलेख, सम्पत्ति कर रसीदें, आधार-लिंक्ड भूमि अभिलेख\n"
                "- न्यायालय में **कब्ज़े के लिए दीवानी मुकदमा** दायर कर सकते हैं\n"
                "- निःशुल्क कानूनी सलाह के लिए **नालसा हेल्पलाइन: 15100** पर कॉल करें"
            ),
        },
        "consumer_rights": {
            "en": (
                "**Consumer Rights — How to Complain:**\n\n"
                "**[Consumer Rights]** Under the **Consumer Protection Act 2019**, you can file a complaint for defective goods, poor service, or overcharging.\n\n"
                "- File online at **edaakhil.nic.in** (free, no lawyer needed)\n"
                "- Visit the **District Consumer Forum** in your city\n"
                "- Claims up to ₹50 lakh → District Forum | Up to ₹2 crore → State Commission"
            ),
            "hi": (
                "**उपभोक्ता अधिकार — शिकायत कैसे करें:**\n\n"
                "**[उपभोक्ता अधिकार]** **उपभोक्ता संरक्षण अधिनियम 2019** के तहत खराब सामान, खराब सेवा या अधिक शुल्क के लिए शिकायत करें।\n\n"
                "- **edaakhil.nic.in** पर ऑनलाइन शिकायत करें (निःशुल्क, वकील की ज़रूरत नहीं)\n"
                "- अपने शहर के **जिला उपभोक्ता मंच** में जाएँ\n"
                "- ₹50 लाख तक → जिला मंच | ₹2 करोड़ तक → राज्य आयोग"
            ),
        },
        "child_rights": {
            "en": (
                "**Child Rights & Protection:**\n\n"
                "**[Child Rights]** Every child in India has strong legal protection.\n\n"
                "- Child labour (below 14 years) is illegal — report to **Child Helpline: 1098**\n"
                "- Sexual offences against children must be reported under **POCSO Act 2012**\n"
                "- Every child has the right to free education up to age 14 under **RTE Act 2009**\n"
                "- Call **1098** (Child Helpline) — available 24/7, free"
            ),
            "hi": (
                "**बाल अधिकार और सुरक्षा:**\n\n"
                "**[बाल अधिकार]** भारत में हर बच्चे को कानूनी सुरक्षा प्राप्त है।\n\n"
                "- 14 वर्ष से कम आयु के बच्चों से बाल श्रम कराना अवैध है — **बाल हेल्पलाइन: 1098** पर रिपोर्ट करें\n"
                "- बच्चों के विरुद्ध यौन अपराध **पॉक्सो अधिनियम 2012** के तहत रिपोर्ट करें\n"
                "- **शिक्षा का अधिकार अधिनियम 2009** के तहत 14 वर्ष तक निःशुल्क शिक्षा का अधिकार है\n"
                "- **1098** (बाल हेल्पलाइन) — 24/7 उपलब्ध, निःशुल्क"
            ),
        },
        "rti": {
            "en": (
                "**Right to Information (RTI):**\n\n"
                "**[RTI]** Under the **RTI Act 2005**, every citizen can request information from any government office.\n\n"
                "- File an RTI application with a fee of just **₹10**\n"
                "- Government must respond within **30 days**\n"
                "- If denied, appeal to the **First Appellate Authority**, then to the **Information Commission**\n"
                "- RTI can be filed online at **rtionline.gov.in**"
            ),
            "hi": (
                "**सूचना का अधिकार (आरटीआई):**\n\n"
                "**[आरटीआई]** **सूचना का अधिकार अधिनियम 2005** के तहत कोई भी नागरिक किसी भी सरकारी कार्यालय से जानकारी माँग सकता है।\n\n"
                "- मात्र **₹10** शुल्क पर आरटीआई आवेदन दाखिल करें\n"
                "- सरकार को **30 दिन** के भीतर उत्तर देना होगा\n"
                "- अस्वीकृति पर **प्रथम अपीलीय प्राधिकरण** और फिर **सूचना आयोग** में अपील करें\n"
                "- **rtionline.gov.in** पर ऑनलाइन आरटीआई दाखिल करें"
            ),
        },
    }

    if intent in responses:
        return responses[intent].get(lang, responses[intent]["en"])
    return _generic_guidance(lang)


def _generic_guidance(lang: str) -> str:
    if lang == "hi":
        return (
            "मैं आपकी कानूनी समस्या समझने में मदद कर सकता हूँ। कृपया अपनी समस्या विस्तार से बताएँ:\n\n"
            "- **चोरी / एफ़आईआर** — चोरी, डकैती, एफ़आईआर प्रक्रिया\n"
            "- **घरेलू हिंसा** — शारीरिक, मानसिक, आर्थिक शोषण\n"
            "- **वेतन चोरी** — वेतन न मिलना, न्यूनतम वेतन\n"
            "- **भूमि विवाद** — सम्पत्ति, ज़मीन, अतिक्रमण\n"
            "- **साइबर अपराध** — ऑनलाइन धोखाधड़ी, हैकिंग\n"
            "- **उपभोक्ता अधिकार** — खराब उत्पाद, रिफ़ंड\n\n"
            "आपातकाल में: पुलिस **100** | महिला **181** | आपातकाल **112**"
        )
    return (
        "I can help you understand your legal rights. Please describe your issue in detail:\n\n"
        "- **Theft / FIR** — stolen property, robbery, FIR process\n"
        "- **Domestic Violence** — physical, emotional, economic abuse\n"
        "- **Wage Theft** — unpaid wages, minimum wage violations\n"
        "- **Land Dispute** — property, encroachment, ownership\n"
        "- **Cyber Crime** — online fraud, hacking, identity theft\n"
        "- **Consumer Rights** — defective products, refunds\n\n"
        "Emergency: Police **100** | Women **181** | Emergency **112**"
    )


def _format_memory_note(memories: list, lang: str) -> str:
    if lang == "hi":
        note = "*(पिछले सत्रों से:*"
    else:
        note = "*(From your previous sessions:*"
    for m in memories[:2]:
        case = m["case_type"].replace("_", " ").title()
        note += f" *{case}*,"
    note = note.rstrip(",") + "*)*"
    return note


def _disclaimer(lang: str) -> str:
    if lang == "hi":
        return "*कृपया ध्यान दें: यह केवल सामान्य कानूनी जानकारी है। विशिष्ट सलाह के लिए योग्य वकील से परामर्श करें।*"
    return "*Please note: This is general legal information only. For specific legal advice, please consult a qualified lawyer.*"


def generate_document_content(doc_type: str, details: dict) -> str:
    """Generate document text using templates (no LLM needed)."""
    complainant = details.get("complainant_name", details.get("complainant_id", "The Complainant"))
    incident = details.get("incident_description", "As described verbally")
    date_time = details.get("date_time", "Date not specified")
    location = details.get("location", "Location not specified")
    suspect = details.get("suspect_description", "Unknown")
    witness = details.get("witness", "None provided")

    if doc_type == "FIR":
        return _fir_template(complainant, incident, date_time, location, suspect, witness)
    elif "Domestic Violence" in doc_type:
        return _dv_template(complainant, incident, date_time, location, suspect)
    elif "Labour" in doc_type or "Wage" in doc_type:
        return _labour_template(complainant, incident, date_time, location, details)
    else:
        return _generic_complaint_template(doc_type, complainant, incident, date_time, location, suspect, details)


def _fir_template(complainant, incident, date_time, location, suspect, witness):
    return f"""FIRST INFORMATION REPORT (FIR)

To,
The Station House Officer,
[Nearest Police Station]

Subject: Request for Registration of First Information Report

Respected Sir/Madam,

I, {complainant}, hereby wish to lodge a First Information Report regarding the following incident:

INCIDENT DETAILS:
{incident}

DATE AND TIME: {date_time}
PLACE OF OCCURRENCE: {location}

SUSPECT DESCRIPTION:
{suspect}

WITNESSES:
{witness}

I request that this FIR be registered under the appropriate sections of the Indian Penal Code and that necessary investigation be carried out at the earliest.

I declare that the facts stated above are true to the best of my knowledge and belief.

Yours faithfully,
{complainant}

Note: Under Section 154 of CrPC, the police are legally bound to register this FIR. Refusal to do so is punishable under Section 166A IPC with imprisonment up to 2 years.
"""


def _dv_template(complainant, incident, date_time, location, suspect):
    return f"""COMPLAINT UNDER THE PROTECTION OF WOMEN FROM DOMESTIC VIOLENCE ACT, 2005

To,
The Protection Officer / Magistrate,
[Jurisdiction]

Subject: Complaint of Domestic Violence

Respected Sir/Madam,

I, {complainant}, hereby submit this complaint under the Protection of Women from Domestic Violence Act, 2005.

DETAILS OF VIOLENCE:
{incident}

DATE: {date_time}
ADDRESS WHERE VIOLENCE OCCURRED: {location}
RESPONDENT (ACCUSED): {suspect}

RELIEF SOUGHT:
1. Protection Order under Section 18 of the DV Act
2. Residence Order under Section 19
3. Monetary Relief under Section 20
4. Any other relief the Hon'ble Court deems fit

I request immediate action and protection as per law.

{complainant}

Emergency Contacts: Women Helpline 181 | Police 100 | Emergency 112
"""


def _labour_template(complainant, incident, date_time, location, details):
    employer = details.get("employer_name", "The Employer")
    amount = details.get("amount_due", "Amount not specified")
    return f"""COMPLAINT TO THE LABOUR COMMISSIONER

To,
The Labour Commissioner,
[District/State]

Subject: Complaint Regarding Non-Payment of Wages / Labour Dispute

Respected Sir/Madam,

I, {complainant}, hereby file this complaint under the Payment of Wages Act, 1936 and the Minimum Wages Act, 1948.

DETAILS:
{incident}

EMPLOYER: {employer}
AMOUNT DUE: {amount}
PERIOD: {date_time}
WORKPLACE ADDRESS: {location}

I request that appropriate action be taken against the employer as per the provisions of the law.

{complainant}

Note: Filing this complaint is free. No lawyer is required. Contact NALSA Helpline 15100 for free legal aid.
"""


def _generic_complaint_template(doc_type, complainant, incident, date_time, location, suspect, details):
    return f"""{doc_type.upper()}

To,
The Appropriate Authority,
[Jurisdiction]

Subject: {doc_type}

Respected Sir/Madam,

I, {complainant}, hereby submit this {doc_type} regarding the following matter:

DETAILS:
{incident}

DATE: {date_time}
LOCATION: {location}
ACCUSED / RESPONDENT: {suspect}

I request that appropriate action be taken as per the provisions of law.

{complainant}

Disclaimer: This document was generated by NyayaVoice AI assistant for informational purposes. Please review with a legal professional before submission.
"""
