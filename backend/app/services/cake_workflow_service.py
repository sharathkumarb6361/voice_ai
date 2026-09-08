"""Deterministic missed-call and order workflow for the Cake Shop & Bakery business.

Speech/LLM layers can supply a customer utterance, but this module owns intent,
state, validation, next-question selection, and the side effects (enquiry creation,
calendar booking, and owner alerts).
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy import text

from app.database import get_db_connection
from app.services.calendar_service import CalendarService
from app.services.external_api_service import ExternalApiService
from app.services.summary_service import SummaryService


class CakeWorkflowService:
    WORKFLOW_ID = "wf-cake-01"
    BUSINESS_ID = "biz-cake-01"

    IN_PROGRESS = "IN_PROGRESS"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    COMPLETED = "COMPLETED"
    CALLBACK_REQUIRED = "CALLBACK_REQUIRED"

    MISSED_CALL_GREETING = (
        "Namaste! Welcome to Sweet Treats Bakery. We missed your call. "
        "How can we help you today with your cake order or bakery enquiry?"
    )

    REQUIRED_FIELDS = [
        "cake_flavor",
        "weight_kg",
        "required_date",
        "custom_message",
        "delivery_preference",
        "budget_inr",
    ]

    FIELD_QUESTIONS = {
        "cake_flavor": "What cake flavor would you like (e.g. Belgian Dark Chocolate, Red Velvet, Vanilla Mango, Black Forest)?",
        "weight_kg": "What weight or size would you like for the cake in kilograms (e.g. 1 kg, 2 kg)?",
        "required_date": "For which date and time do you need the cake ready (e.g. tomorrow at 4 PM)?",
        "custom_message": "What message or name would you like written on the cake? (Say 'no message' if none)",
        "delivery_preference": "Would you prefer home delivery to your address or store pickup from our bakery?",
        "budget_inr": "What is your approximate budget for the cake in rupees (e.g. Rs. 1500)?",
    }

    FIELD_QUESTIONS_KN = {
        "cake_flavor": "ನೀವು ಯಾವ ಫ್ಲೇವರ್ ಕೇಕ್ ಬಯಸುತ್ತೀರಿ (ಉದಾ: ಚಾಕೊಲೇಟ್, ರೆಡ್ ವೆಲ್ವೆಟ್, ವೆನಿಲ್ಲಾ, ಬ್ಲಾಕ್ ಫಾರೆಸ್ಟ್)?",
        "weight_kg": "ಕೇಕ್ ತೂಕ ಎಷ್ಟು ಇರಬೇಕು (ಉದಾ: 1 ಕೆಜಿ, 2 ಕೆಜಿ)?",
        "required_date": "ಕೇಕ್ ಯಾವ ದಿನಾಂಕ ಮತ್ತು ಸಮಯಕ್ಕೆ ಬೇಕು (ಉದಾ: ನಾಳೆ ಸಂಜೆ 4 ಗಂಟೆಗೆ)?",
        "custom_message": "ಕೇಕ್ ಮೇಲೆ ಏನು ಸಂದೇಶ ಬರೆಯಬೇಕು? (ಸಂದೇಶ ಬೇಡವಾದರೆ 'ಸಂದೇಶ ಬೇಡ' ಎಂದು ಹೇಳಿ)",
        "delivery_preference": "ಮನೆಗೆ ಡೆಲಿವರಿ ಬೇಕೇ ಅಥವಾ ಬೇಕರಿಯಿಂದ ಸ್ಟೋರ್ ಪಿಕಪ್ ಮಾಡಿಕೊಳ್ಳುತ್ತೀರಾ?",
        "budget_inr": "ನಿಮ್ಮ ಅಂದಾಜು ಬಜೆಟ್ ಎಷ್ಟು ರೂಪಾಯಿ (ಉದಾ: 1500)?",
    }

    FIELD_QUESTIONS_HI = {
        "cake_flavor": "आप कौन सा फ्लेवर पसंद करेंगे (जैसे बेल्जियन डार्क चॉकलेट, रेड वेलवेट, वैनिला, ब्लैक फॉरेस्ट)?",
        "weight_kg": "केक का वजन कितना होना चाहिए (जैसे 1 किलो, 2 किलो)?",
        "required_date": "केक किस तारीख और समय तक तैयार चाहिए (जैसे कल शाम 4 बजे)?",
        "custom_message": "केक पर क्या संदेश या नाम लिखवाना चाहते हैं? (यदि कोई संदेश नहीं है तो 'कोई संदेश नहीं' कहें)",
        "delivery_preference": "होम डिलीवरी चाहिए या बेकरी से स्टोर पिकअप?",
        "budget_inr": "आपका अनुमानित बजट कितना है (जैसे 1500 रुपये)?",
    }

    INVALID_FLAVOR_WORDS = {
        "sorry", "no", "nope", "not", "nah", "nahi", "illa", "wait", "cake", "sweet", "flavor",
        "flavour", "yes", "yeah", "yep", "okay", "ok", "fine", "sure", "none", "unknown", "na",
        "n/a", "nil", "cancel", "correct", "wrong", "change", "update", "nothing", "details",
        "contact", "time", "date", "morning", "afternoon", "evening", "night", "tomorrow", "today",
        "pickup", "delivery", "home", "store", "order", "kg", "kilo"
    }

    @classmethod
    def handles(cls, workflow_id: str | None) -> bool:
        return workflow_id == cls.WORKFLOW_ID

    @staticmethod
    def _detect_language(message: str, selected_language: str | None) -> str:
        if selected_language in {"en", "hi", "kn"}:
            return selected_language
        if re.search(r"[\u0C80-\u0CFF]", message or ""):
            return "kn"
        if re.search(r"[\u0900-\u097F]", message or ""):
            return "hi"
        return "en"

    @classmethod
    def initial_state(cls, call_id: str, customer_phone: str) -> dict[str, Any]:
        return {
            "call_id": call_id,
            "customer_phone": customer_phone,
            "order_type": "New Cake Order",
            "status": cls.IN_PROGRESS,
            "collected_fields": {
                "order_type": "New Cake Order",
                "cake_type": "Birthday Cake",
                "cake_flavor": None,
                "weight_kg": None,
                "required_date": None,
                "custom_message": None,
                "delivery_preference": None,
                "budget_inr": None,
            },
            "missing_fields": list(cls.REQUIRED_FIELDS),
            "last_asked_field": None,
            "completed_fields": ["order_type", "cake_type"],
            "order_enquiry_created": False,
            "calendar_event_created": False,
            "confirmation_pending": False,
        }

    @classmethod
    def get_missing_fields(cls, state: dict[str, Any]) -> list[str]:
        fields = state["collected_fields"]
        missing: list[str] = []
        for field in cls.REQUIRED_FIELDS:
            if not cls._is_valid_field(field, fields.get(field)):
                missing.append(field)
        return missing

    @classmethod
    def extract_fields(cls, message: str, state: dict[str, Any]) -> dict[str, Any]:
        source = (message or "").strip()
        lower = source.lower()
        extracted: dict[str, Any] = {}
        last_field = state.get("last_asked_field")

        # 1. Weight Extraction (handles digits, English words, fractions, Kannada ondu/eradu, Hindi ek/do, bare kilo/kg/kilograms)
        # A. Pre-check compound fractional expressions
        if any(re.search(p, lower) for p in [
            r"\b(?:one\s+and\s+(?:a\s+)?half|1\s+and\s+(?:a\s+)?half|1\.5|dedh|ಒಂದುವರೆ)\s*(?:kg|kilo|kilos|kilogram|kilograms|ಕೆಜಿ|ಕೇಜಿ|ಕಿಲೊ|किलो)?\b"
        ]):
            extracted["weight_kg"] = "1.5"
        elif any(re.search(p, lower) for p in [
            r"\b(?:two\s+and\s+(?:a\s+)?half|2\s+and\s+(?:a\s+)?half|2\.5|dhai)\s*(?:kg|kilo|kilos|kilogram|kilograms|ಕೆಜಿ|ಕೇಜಿ|ಕಿಲೊ|किलो)?\b"
        ]):
            extracted["weight_kg"] = "2.5"
        elif any(re.search(p, lower) for p in [
            r"\b(?:half\s+(?:a\s+)?(?:kg|kilo|kilogram|kilos|kilograms)|half\s*kg|half\s*kilo|1/2\s*kg|0\.5\s*kg|ardha\s*kg|aadha\s*kilo|aadha\s*kg|ಅರ್ಧ\s*ಕೆಜಿ|ಆಧಾ\s*ಕಿಲೊ)\b"
        ]):
            extracted["weight_kg"] = "0.5"

        en_num_words = {
            "quarter": "0.25", "half": "0.5", "one": "1", "two": "2", "three": "3",
            "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10"
        }
        kn_num_map = {
            "ಅರ್ಧ": "0.5", "ಒಂದುವರೆ": "1.5", "ಒಂದು": "1", "ಎರಡು": "2", "ಮೂರು": "3", "ನಾಲ್ಕು": "4", "ಐದು": "5",
            "ondu": "1", "eradu": "2", "mooru": "3", "naalku": "4", "aidu": "5", "ardha": "0.5"
        }
        hi_num_map = {
            "आधा": "0.5", "डेढ़": "1.5", "ढाई": "2.5", "एक": "1", "दो": "2", "तीन": "3", "चार": "4", "पांच": "5",
            "aadha": "0.5", "dedh": "1.5", "dhai": "2.5", "ek": "1", "do": "2", "teen": "3", "char": "4", "paanch": "5"
        }

        # Check Kannada number words
        if "weight_kg" not in extracted:
            for w_kn, num_kn in kn_num_map.items():
                if re.search(rf"\b{re.escape(w_kn)}\b", lower) and (any(u in lower for u in ["ಕೆಜಿ", "ಕೇಜಿ", "ಕಿಲೊ", "kg", "kilo"]) or last_field == "weight_kg"):
                    extracted["weight_kg"] = num_kn
                    break

        # Check Hindi number words
        if "weight_kg" not in extracted:
            for w_hi, num_hi in hi_num_map.items():
                if re.search(rf"\b{re.escape(w_hi)}\b", lower) and (any(u in lower for u in ["किलो", "kg", "kilo"]) or last_field == "weight_kg"):
                    extracted["weight_kg"] = num_hi
                    break

        # Check numeric digits with units or standalone
        if "weight_kg" not in extracted:
            m_weight = re.search(r"(?:make\s+it\s+|change(?:\s+(?:the\s+)?weight)?\s+to\s+|weight\s+(?:is|to)\s*)?(\d+(?:\.\d+)?)\s*(?:kg|kilo|kilos|kilogram|kilograms|pound|pounds|lb|lbs|gm|gram|grams|g|ಕೆಜಿ|ಕೇಜಿ|ಕಿಲೊ|किलो)\b", lower)
            if not m_weight and last_field == "weight_kg":
                m_weight = re.search(r"\b(\d+(?:\.\d+)?)\b", lower)
            if m_weight:
                val_str = m_weight.group(1)
                if any(g in lower for g in ["gm", "gram", "grams"]) and not any(k in lower for k in ["kg", "kilo", "kilogram"]):
                    try:
                        val_f = float(val_str)
                        if val_f >= 100:
                            val_str = str(val_f / 1000.0)
                    except Exception:
                        pass
                extracted["weight_kg"] = val_str

        # Check English number words with units or when directly answering weight question
        if "weight_kg" not in extracted:
            for w_en, num_en in en_num_words.items():
                if re.search(rf"\b{w_en}\s*(?:kg|kilo|kilos|kilogram|kilograms|pound|pounds|lb|lbs)\b", lower):
                    extracted["weight_kg"] = num_en
                    break
                elif last_field == "weight_kg" and re.search(rf"^\s*(?:just\s+|about\s+|around\s+)?{w_en}(?:\s+(?:please|only))?\s*[.!]?$", lower):
                    extracted["weight_kg"] = num_en
                    break

        # Check bare units (e.g. 'Kilogram.', 'One kilograms', 'a kilo', 'a kilogram', 'kilo', 'kg') only when no number was matched
        if "weight_kg" not in extracted:
            if re.search(r"\b(?:just\s+)?(?:a\s+|an\s+)?(?:kilo|kilogram|kg|kilos|kilograms)\b", lower):
                if last_field == "weight_kg" or re.search(r"\b(?:a\s+|an\s+)(?:kilo|kilogram|kg)\b", lower):
                    extracted["weight_kg"] = "1"

        # 2. Cake Flavor Extraction
        known_flavors = (
            "belgian dark chocolate", "dark chocolate", "chocolate truffle", "chocolate", "red velvet",
            "vanilla mango", "vanilla", "black forest", "white forest", "pineapple", "butterscotch",
            "strawberry cheesecake", "strawberry", "choco chip", "fresh fruit", "fruit", "truffle",
            "blueberry", "lotus biscoff", "mango", "ferrero rocher", "caramel", "rasmalai", "gulab jamun"
        )
        for flv in known_flavors:
            if re.search(rf"\b{re.escape(flv)}\b", lower):
                extracted["cake_flavor"] = flv.title()
                break

        if "cake_flavor" not in extracted:
            m_flav_corr = re.search(r"(?:change\s+(?:the\s+)?flavor\s+to|flavor\s+(?:is|to|as)|switch\s+flavor\s+to|make\s+it\s+flavor)\s+([a-zA-Z\s]+?)(?=\s+instead|\s+and|\s*[,.]|$)", lower)
            if m_flav_corr and len(m_flav_corr.group(1).strip()) >= 3:
                clean_f = m_flav_corr.group(1).strip().title()
                if clean_f.lower() not in cls.INVALID_FLAVOR_WORDS:
                    extracted["cake_flavor"] = clean_f

        if "cake_flavor" not in extracted and last_field == "cake_flavor":
            cleaned_flavor = re.sub(r"^(?:i\s+want\s+|i\s+would\s+like\s+|make\s+it\s+|can\s+i\s+have\s+|give\s+me\s+|flavor\s+is\s+|a\s+|an\s+)", "", source.strip(), flags=re.IGNORECASE)
            cleaned_flavor = re.sub(r"\s+(?:cake|flavor|please)$", "", cleaned_flavor.strip(), flags=re.IGNORECASE).strip(" .,:;!?")
            if len(cleaned_flavor) >= 3 and cleaned_flavor.lower() not in cls.INVALID_FLAVOR_WORDS and not cls._is_yes(cleaned_flavor) and not cls._is_no(cleaned_flavor):
                extracted["cake_flavor"] = cleaned_flavor.title()

        # 3. Delivery Preference Extraction
        has_delivery = bool(re.search(r"\b(home delivery|delivery|deliver(?:ed|y)? to (?:my )?(?:home|house|address)|deliver it|delivery please|home please|send to home|deliver|swiggy|zomato|dunzo|ಮನೆಗೆ|ಡೆಲಿವರಿ|होम डिलीवरी|घर पर)\b", lower))
        has_pickup = bool(re.search(r"\b(store pickup|pickup|pick up|takeaway|collect|from (?:the )?store|pick it up|baker|shop|ಬಂದು ತಗೊಳ್ತೀನಿ|ಪಿಕಪ್|दुकान से|पिकअप)\b", lower))
        if re.search(r"\b(?:store pickup|pickup|pick up)\s+instead(?:\s+of\s+delivery)?\b", lower) or re.search(r"\b(?:change|switch|prefer)\s+(?:it\s+)?to\s+(?:store\s+)?pickup\b", lower):
            extracted["delivery_preference"] = "Store Pickup"
        elif re.search(r"\b(?:home delivery|delivery|deliver)\s+instead(?:\s+of\s+pickup)?\b", lower) or re.search(r"\b(?:change|switch|prefer)\s+(?:it\s+)?to\s+(?:home\s+)?delivery\b", lower):
            extracted["delivery_preference"] = "Home Delivery"
        elif has_delivery and not has_pickup:
            extracted["delivery_preference"] = "Home Delivery"
        elif has_pickup and not has_delivery:
            extracted["delivery_preference"] = "Store Pickup"
        elif last_field == "delivery_preference":
            if any(w in lower for w in ["store", "pick", "pickup", "takeaway", "collect", "shop"]):
                extracted["delivery_preference"] = "Store Pickup"
            elif any(w in lower for w in ["home", "deliver", "delivery", "address", "doorstep"]):
                extracted["delivery_preference"] = "Home Delivery"

        # 4. Required Date & Time Extraction
        # Precise keyword matching (prevents substring triggers e.g. "am" in "kilogram")
        has_explicit_date = bool(re.search(
            r"\b(?:today|tomorrow|day after tomorrow|naale|kal|parso|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
            lower
        ))
        has_explicit_time = bool(re.search(
            r"\b\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)\b|\b(?:morning|afternoon|evening|night|sanje|belagge)\b",
            lower
        ))
        is_date_field_active = (last_field == "required_date")

        if (has_explicit_date or has_explicit_time or is_date_field_active) and not any(w in lower for w in ["anytime", "any time", "later", "whenever"]):
            # Ignore false-positive time matches if user is answering weight or price (e.g. "500 grams", "Rs 500")
            is_weight_or_price_context = bool(re.search(r"\b(?:\d+\s*(?:kg|kilo|kilogram|gm|gram|grams|rs|rupees|inr))\b", lower))
            if is_date_field_active or has_explicit_date or (has_explicit_time and not is_weight_or_price_context):
                if "day after" in lower or "parso" in lower:
                    d_str = "day after tomorrow"
                elif "tomorrow" in lower or "naale" in lower or "kal" in lower:
                    d_str = "tomorrow"
                elif "today" in lower or "aaj" in lower or "ivattu" in lower:
                    d_str = "today"
                else:
                    d_str = "tomorrow" if is_date_field_active else "today"
                    for d_name in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]:
                        if re.search(rf"\b{d_name}\b", lower):
                            d_str = d_name
                            break
                t_str = "17:00"
                for tm in re.finditer(r"(\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)?)", lower, re.I):
                    after_str = lower[tm.end():tm.end()+6]
                    if not re.match(r"^\s*(?:kg|kilo|kilogram|pound|lb|rs|rupees|inr|gm|gram)", after_str):
                        t_str = tm.group(1)
                        break
                target_dt = CalendarService.parse_datetime_input(d_str, t_str)
                extracted["required_date"] = target_dt.isoformat()

        # 5. Custom Message on Cake Extraction
        no_msg_patterns = [
            r"\b(?:no\s+message|no\s+text|nothing\s+on\s+cake|no\s+name|without\s+message|no\s+writing|don't\s+write|dont\s+write|keep\s+it\s+plain|leave\s+it\s+blank|without\s+any\s+message)\b"
        ]
        if any(re.search(p, lower) for p in no_msg_patterns):
            extracted["custom_message"] = "None"
        elif last_field == "custom_message" and any(w == lower.strip(" .,:;!?") for w in ["no", "none", "nothing", "na", "n/a", "nil", "no need"]):
            extracted["custom_message"] = "None"
        else:
            m_msg = re.search(r'''(?:change\s+(?:the\s+)?(?:message|text|note|writing)\s+to|write|message|text|says|name on cake|note)\s*['"]?([^'"]+?)['"]?(?=\s+on|\s+for|\s+instead|\s*$)''', source, re.IGNORECASE)
            if not m_msg:
                m_msg = re.search(r"write\s+([a-zA-Z0-9\s!'-]+?)\s+on\s+(?:the\s+)?cake", source, re.IGNORECASE)
            if m_msg:
                clean_m = m_msg.group(1).strip()
                if clean_m.lower() in ["none", "nothing", "no message", "no"]:
                    extracted["custom_message"] = "None"
                elif len(clean_m) >= 2:
                    extracted["custom_message"] = clean_m.title()
            elif last_field == "custom_message":
                clean_m = re.sub(r"^(?:write\s+|put\s+|text\s+|it\s+should\s+say\s+|says\s+)", "", source.strip(), flags=re.IGNORECASE).strip(" .,:;!?'\"")
                if len(clean_m) >= 2 and not cls._is_yes(clean_m) and not cls._is_no(clean_m):
                    extracted["custom_message"] = clean_m.title()

        # 6. Budget INR Extraction (handles commas e.g. 1,500 and English words)
        clean_budget_lower = lower.replace(",", "")
        budget_words_map = {
            "one thousand": "1000", "two thousand": "2000", "three thousand": "3000",
            "fifteen hundred": "1500", "twelve hundred": "1200", "thousand": "1000",
            "five hundred": "500", "eight hundred": "800"
        }
        for bw, bval in budget_words_map.items():
            if bw in clean_budget_lower:
                extracted["budget_inr"] = bval
                break

        if "budget_inr" not in extracted:
            m_budget = re.search(r"(?:budget|price|cost)?\s*(?:to|is|of)?\s*(?:rs\.?|rupees|inr)\s*(\d+)", clean_budget_lower) or re.search(r"(\d+)\s*(?:rs\.?|rupees|inr)", clean_budget_lower)
            if not m_budget and last_field == "budget_inr":
                m_budget = re.search(r"\b(\d+)\b", clean_budget_lower)
            if m_budget:
                extracted["budget_inr"] = m_budget.group(1)
            elif last_field == "budget_inr" and any(w in lower for w in ["any", "standard", "normal", "flexible", "regular", "whatever", "reasonable"]):
                extracted["budget_inr"] = "1500"

        # 7. Cake Type / Occasion
        if any(w in lower for w in ["birthday cake", "birthday", "bday"]):
            extracted["cake_type"] = "Birthday Cake"
        elif any(w in lower for w in ["anniversary cake", "anniversary"]):
            extracted["cake_type"] = "Anniversary Cake"
        elif any(w in lower for w in ["wedding cake", "tier wedding", "tiered cake"]):
            extracted["cake_type"] = "Tier Wedding Cake"
        elif any(w in lower for w in ["pastry box", "pastries", "cupcake"]):
            extracted["cake_type"] = "Pastry Box"
        elif any(w in lower for w in ["theme cake", "custom cake", "photo cake"]):
            extracted["cake_type"] = "Theme Custom Cake"

        # 8. Order Type
        if any(w in lower for w in ["custom design", "custom cake", "photo cake", "theme cake", "tiered", "wedding cake"]):
            extracted["order_type"] = "Custom Design"
        elif any(w in lower for w in ["enquiry", "inquiry", "rate card", "price list", "menu"]):
            extracted["order_type"] = "General Enquiry"
        elif any(w in lower for w in ["order", "cake", "buy", "place"]):
            extracted["order_type"] = "New Cake Order"

        return extracted

    @classmethod
    def _is_valid_field(cls, field: str, value: Any) -> bool:
        if value is None or value == "":
            return False
        val_str = str(value).strip()
        val_lower = val_str.lower()

        if val_lower in ["none", "null", "n/a", "undefined", "unknown"]:
            if field == "custom_message" and val_lower in ["none", "no", "no message", "nothing"]:
                return True
            return False

        if field == "cake_flavor":
            if val_lower in cls.INVALID_FLAVOR_WORDS:
                return False
            return len(val_str) >= 3

        if field == "weight_kg":
            try:
                m = re.search(r"(\d+(?:\.\d+)?)", val_str)
                if m and float(m.group(1)) > 0:
                    return True
            except Exception:
                pass
            return False

        if field == "required_date":
            if val_lower in ["anytime", "any time", "later", "whenever", "soon"]:
                return False
            return len(val_str) >= 4

        if field == "custom_message":
            return len(val_str) >= 2 or val_lower in ["none", "n/a", "no", "no message", "nothing"]

        if field == "delivery_preference":
            return val_str in ["Home Delivery", "Store Pickup"]

        if field == "budget_inr":
            try:
                clean_b = val_str.replace(",", "")
                m = re.search(r"(\d+)", clean_b)
                if m and int(m.group(1)) > 0:
                    return True
            except Exception:
                pass
            return val_lower in ["standard", "normal", "regular", "flexible", "any", "1500"]

        if field in ["order_type", "cake_type"]:
            return len(val_str) >= 3

        return len(val_str) >= 2

    @classmethod
    def advance_state(cls, state: dict[str, Any], message: str, caller_name: str, caller_phone: str, language: str = "en") -> tuple[dict[str, Any], str, list[dict[str, Any]]]:
        tools: list[dict[str, Any]] = []
        msg_clean = (message or "").strip()
        msg_lower = msg_clean.lower()
        fields = state["collected_fields"]

        # 1. Voice Calendar Cancellation
        if any(w in msg_lower for w in ["cancel my cake", "cancel the cake", "cancel my order", "cancel order"]):
            cancel_res = CalendarService.cancel_event(business_id=cls.BUSINESS_ID)
            tools.append({
                "tool": "cancel_calendar_event",
                "args": {"business_id": cls.BUSINESS_ID},
                "result": cancel_res
            })
            state["status"] = cls.COMPLETED
            state["calendar_cancellation"] = cancel_res
            return state, "Your cake order and calendar appointment have been cancelled as requested. Thank you!", tools

        # 2. Reschedule Appointment
        if any(k in msg_lower for k in ["reschedule cake", "reschedule my cake", "reschedule order", "reschedule my order", "change cake time", "postpone cake", "change pickup time", "change delivery time"]):
            target_dt = CalendarService.parse_datetime_input(message, "17:00")
            update_res = CalendarService.update_event(
                business_id=cls.BUSINESS_ID,
                new_start_time=target_dt.isoformat()
            )
            tools.append({"tool": "update_calendar_event", "args": {"new_start_time": target_dt.isoformat(), "business_id": cls.BUSINESS_ID}, "result": update_res})
            state["status"] = cls.COMPLETED
            state["last_asked_field"] = None
            fields["required_date"] = target_dt.isoformat()
            return state, f"Your cake order has been rescheduled on our bakery calendar to {target_dt.strftime('%B %d at %I:%M %p')}. We will have it ready for you then. Thank you and goodbye!", tools

        # 3. Caller Negation of Existing Field
        for f_key in ["cake_flavor", "weight_kg", "required_date", "custom_message", "delivery_preference", "budget_inr"]:
            curr_val = fields.get(f_key)
            if curr_val and isinstance(curr_val, str) and len(curr_val) >= 2:
                curr_lower = curr_val.lower()
                neg_pattern = r"\b(?:not|isn't|is not|sorry,?\s+(?:it'?s\s+)?not|wrong)\s+" + re.escape(curr_lower) + r"\b"
                if re.search(neg_pattern, msg_lower) or re.search(re.escape(curr_lower) + r"\s+(?:is\s+)?(?:wrong|not correct)", msg_lower):
                    fields[f_key] = None
                    state["status"] = cls.IN_PROGRESS
                    state["confirmation_pending"] = False
                    state["last_asked_field"] = f_key
                    state["missing_fields"] = cls.get_missing_fields(state)
                    q = cls.FIELD_QUESTIONS.get(f_key, f"What would you like for {f_key.replace('_', ' ')} instead?")
                    return state, f"No problem! {q}", tools

        # 4. Caller Answering "Which cake detail would you like to update?"
        if state.get("last_asked_field") == "field_selection_for_correction":
            if any(w in msg_lower for w in ["flavor", "flavour", "taste"]):
                fields["cake_flavor"] = None
                state["status"] = cls.IN_PROGRESS
                state["confirmation_pending"] = False
                state["last_asked_field"] = "cake_flavor"
                state["missing_fields"] = cls.get_missing_fields(state)
                return state, "Sure! What cake flavor would you like instead?", tools
            elif any(w in msg_lower for w in ["weight", "size", "kg", "kilo"]):
                fields["weight_kg"] = None
                state["status"] = cls.IN_PROGRESS
                state["confirmation_pending"] = False
                state["last_asked_field"] = "weight_kg"
                state["missing_fields"] = cls.get_missing_fields(state)
                return state, "Sure! What weight or size would you like for the cake in kilograms instead?", tools
            elif any(w in msg_lower for w in ["date", "time", "day", "timing", "when"]):
                fields["required_date"] = None
                state["status"] = cls.IN_PROGRESS
                state["confirmation_pending"] = False
                state["last_asked_field"] = "required_date"
                state["missing_fields"] = cls.get_missing_fields(state)
                return state, "Sure! For which date and time do you need the cake ready instead?", tools
            elif any(w in msg_lower for w in ["message", "writing", "name", "inscription", "text"]):
                fields["custom_message"] = None
                state["status"] = cls.IN_PROGRESS
                state["confirmation_pending"] = False
                state["last_asked_field"] = "custom_message"
                state["missing_fields"] = cls.get_missing_fields(state)
                return state, "Sure! What message or name would you like written on the cake instead?", tools
            elif any(w in msg_lower for w in ["delivery", "pickup", "pick up", "address"]):
                fields["delivery_preference"] = None
                state["status"] = cls.IN_PROGRESS
                state["confirmation_pending"] = False
                state["last_asked_field"] = "delivery_preference"
                state["missing_fields"] = cls.get_missing_fields(state)
                return state, "Sure! Would you prefer home delivery to your address or store pickup from our bakery?", tools
            elif any(w in msg_lower for w in ["budget", "price", "cost", "rupees"]):
                fields["budget_inr"] = None
                state["status"] = cls.IN_PROGRESS
                state["confirmation_pending"] = False
                state["last_asked_field"] = "budget_inr"
                state["missing_fields"] = cls.get_missing_fields(state)
                return state, "Sure! What is your updated approximate budget in rupees?", tools

        has_change_cue = bool(re.search(r"\b(change|correct|update|switch|different|instead|modify|wrong|another|replace|mistake)\b", msg_lower))

        user_wants_to_confirm = any(phrase in msg_lower for phrase in [
            "confirm", "confirm order", "confirm my order", "please confirm", "confirm it",
            "confirm in calendar", "book it", "book order", "schedule it", "schedule in calendar",
            "yes confirm", "place order", "finalize", "theek hai confirm", "haan confirm", "confirm madi"
        ])

        user_wants_to_end = any(phrase in msg_lower for phrase in [
            "bye", "goodbye", "good bye", "that's all", "thats all", "that is all",
            "nothing else", "no that's all", "no thats all", "end call", "hang up",
            "thank you bye", "thanks bye", "dhanyawad", "shukriya", "alvida",
            "bas itna hi", "saku", "mugithu"
        ])

        # If user signals ending call
        if user_wants_to_end:
            if state.get("status") == cls.COMPLETED:
                return state, "Thank you for contacting Sweet Treats Bakery! Have a wonderful day, goodbye!", tools
            return cls._create_callback_for_incomplete_request(state, caller_name, caller_phone, tools, "Customer ended call before completing order")

        # Confirmation while awaiting confirmation
        if state.get("status") == cls.AWAITING_CONFIRMATION:
            if cls._is_yes(msg_clean) or user_wants_to_confirm:
                return cls._complete_cake_order(state, caller_name, caller_phone, tools)

            if cls._is_no(msg_clean) and not has_change_cue:
                state["status"] = cls.IN_PROGRESS
                state["confirmation_pending"] = False
                state["last_asked_field"] = "field_selection_for_correction"
                return state, "No problem. Which cake detail would you like to update — flavor, weight, date, message, delivery preference, or budget?", tools

        extracted = cls.extract_fields(msg_clean, state)
        updated_fields_log: dict[str, dict[str, Any]] = {}

        for field, value in extracted.items():
            if cls._is_valid_field(field, value):
                old_val = fields.get(field)
                if old_val is not None and old_val != value:
                    updated_fields_log[field] = {"old": old_val, "new": value}
                    tools.append({
                        "tool": "update_database_field",
                        "args": {"field": field, "old_value": old_val, "new_value": value},
                        "result": f"Field '{field}' updated from '{old_val}' to '{value}'."
                    })
                fields[field] = value

        state["completed_fields"] = [
            field for field, value in fields.items() if cls._is_valid_field(field, value)
        ]
        state["missing_fields"] = cls.get_missing_fields(state)

        # If all fields are already present and caller explicitly confirms
        if not state["missing_fields"] and (user_wants_to_confirm or cls._is_yes(msg_clean)):
            return cls._complete_cake_order(state, caller_name, caller_phone, tools)

        # Handle post-completion edits
        if state.get("status") == cls.COMPLETED:
            if updated_fields_log:
                flavor = fields.get("cake_flavor", "Chocolate")
                weight = str(fields.get("weight_kg", "1"))
                req_date = fields.get("required_date") or (datetime.now() + timedelta(days=1)).replace(hour=17, minute=0, second=0).isoformat()
                delivery_pref = fields.get("delivery_preference", "Store Pickup")
                custom_msg = fields.get("custom_message") or "None"
                budget = str(fields.get("budget_inr", "1500"))

                # Update calendar event
                target_dt = CalendarService.parse_datetime_input(req_date, "17:00")
                start_iso = target_dt.isoformat()
                end_iso = (target_dt + timedelta(minutes=30)).isoformat()
                cake_cal_title = f"Cake Order ({flavor} - {weight}kg) - {caller_name}"
                cal_evt_id = fields.get("calendar_event", {}).get("event_id") if isinstance(fields.get("calendar_event"), dict) else None
                cake_cal_res = CalendarService.update_event(
                    event_id=cal_evt_id or "latest",
                    business_id=cls.BUSINESS_ID,
                    title=cake_cal_title,
                    new_start_time=start_iso,
                    new_end_time=end_iso,
                    attendee_name=caller_name,
                    attendee_phone=caller_phone,
                    description=f"Sweet Treats Bakery: Cake ({flavor}, {weight}kg). {delivery_pref} at Rs. {budget}. Message: '{custom_msg}'. Caller: {caller_name} ({caller_phone})"
                )
                tools.append({
                    "tool": "update_calendar_event",
                    "args": {"title": cake_cal_title, "start_time": start_iso, "delivery_preference": delivery_pref},
                    "result": cake_cal_res
                })
                fields["calendar_event"] = cake_cal_res

                ack_items = [f"{k.replace('_', ' ')} to {v['new']}" for k, v in updated_fields_log.items()]
                return state, (
                    f"Got it, I have updated your order and calendar booking ({', '.join(ack_items)}). "
                    f"Your {weight}kg {flavor} cake is all set for {cls._format_date(req_date)}. Is there anything else you need?"
                ), tools
            elif has_change_cue:
                return state, "Sure! Which cake detail would you like to update — flavor, weight, date, message, delivery, or budget?", tools
            return state, "Your cake order is already confirmed! Is there anything else our bakery can help you with?", tools

        # If user corrected fields while awaiting confirmation, ask for reconfirmation
        if state.get("status") == cls.AWAITING_CONFIRMATION and updated_fields_log:
            ack_items = [f"{k.replace('_', ' ')} to {v['new']}" for k, v in updated_fields_log.items()]
            return state, (
                f"Got it, I have updated the {', '.join(ack_items)}. Let me reconfirm: "
                f"A {fields['weight_kg']}kg {fields['cake_flavor']} cake for {fields['delivery_preference']} on {cls._format_date(fields['required_date'])}, "
                f"message '{fields['custom_message']}', budget Rs. {fields['budget_inr']}. Is that correct?"
            ), tools

        if state["missing_fields"]:
            state["status"] = cls.IN_PROGRESS
            prefix = ""
            if updated_fields_log:
                ack_items = [f"{k.replace('_', ' ')} to {v['new']}" for k, v in updated_fields_log.items()]
                prefix = f"Got it, I have updated the {', '.join(ack_items)}."
            elif extracted and state.get("last_asked_field") in extracted:
                ans_field = state["last_asked_field"]
                ans_val = extracted[ans_field]
                if ans_field == "cake_flavor":
                    prefix = f"Got it, {ans_val} sounds delicious!"
                elif ans_field == "weight_kg":
                    prefix = f"Got it, {ans_val} kg!"
                elif ans_field == "required_date":
                    prefix = f"Got it, {cls._format_date(ans_val)}!"
                elif ans_field == "custom_message":
                    prefix = f"Got it, message noted as '{ans_val}'."
                elif ans_field == "delivery_preference":
                    prefix = f"Got it, {ans_val}!"
                elif ans_field == "budget_inr":
                    prefix = f"Got it, budget of Rs. {ans_val} noted."
            elif state.get("last_asked_field") and state.get("last_asked_field") in state["missing_fields"] and msg_clean:
                last_f = state["last_asked_field"]
                if language == "kn":
                    clarifications = {
                        "cake_flavor": "ಕ್ಷಮಿಸಿ, ಫ್ಲೇವರ್ ಸರಿಯಾಗಿ ತಿಳಿಯಲಿಲ್ಲ. ಚಾಕೊಲೇಟ್, ವೆನಿಲ್ಲಾ ಅಥವಾ ರೆಡ್ ವೆಲ್ವೆಟ್ ಇವುಗಳಲ್ಲಿ ಯಾವ ಫ್ಲೇವರ್ ಬಯಸುತ್ತೀರಿ?",
                        "weight_kg": "ಕ್ಷಮಿಸಿ, ತೂಕ ಸರಿಯಾಗಿ ತಿಳಿಯಲಿಲ್ಲ. ದಯವಿಟ್ಟು 1 ಕೆಜಿ ಅಥವಾ 2 ಕೆಜಿ ಎಂದು ತಿಳಿಸುವಿರಾ?",
                        "required_date": "ಕೇಕ್ ಯಾವ ದಿನಾಂಕ ಮತ್ತು ಸಮಯಕ್ಕೆ ಬೇಕು ಎಂದು ಸ್ಪಷ್ಟವಾಗಿ ತಿಳಿಸುವಿರಾ (ಉದಾ: ನಾಳೆ ಸಂಜೆ 4 ಗಂಟೆಗೆ)?",
                        "custom_message": "ಕೇಕ್ ಮೇಲೆ ಬರೆಯಬೇಕಾದ ಸಂದೇಶ ತಿಳಿಸುವಿರಾ ಅಥವಾ 'ಸಂದೇಶ ಬೇಡ' ಎನ್ನಿ?",
                        "delivery_preference": "ಮನೆಗೆ ಡೆಲಿವರಿ ಬೇಕೇ ಅಥವಾ ಬೇಕರಿಯಿಂದ ಸ್ಟೋರ್ ಪಿಕಪ್ ಮಾಡಿಕೊಳ್ಳುತ್ತೀರಾ?",
                        "budget_inr": "ಕೇಕ್‌ಗೆ ನಿಮ್ಮ ಅಂದಾಜು ಬಜೆಟ್ ಎಷ್ಟು ರೂಪಾಯಿ ಎಂದು ತಿಳಿಸುವಿರಾ (ಉದಾ: 1500)?"
                    }
                elif language == "hi":
                    clarifications = {
                        "cake_flavor": "माफ़ कीजिए, मैं फ्लेवर समझ नहीं पाया। आप बेल्जियन चॉकलेट, रेड वेलवेट या वैनिला में से कौन सा पसंद करेंगे?",
                        "weight_kg": "माफ़ कीजिए, वजन समझ नहीं पाया। क्या आप 1 किलो या 2 किलो जैसा वजन बता सकते हैं?",
                        "required_date": "केक किस तारीख और समय तक तैयार चाहिए, कृपया स्पष्ट बताएं (जैसे कल शाम 4 बजे)?",
                        "custom_message": "केक पर क्या संदेश लिखवाना चाहते हैं, या कहिए 'कोई संदेश नहीं'?",
                        "delivery_preference": "होम डिलीवरी चाहिए या बेकरी से स्टोर पिकअप?",
                        "budget_inr": "केक के लिए आपका अनुमानित बजट कितने रुपये का है (जैसे 1500 रुपये)?"
                    }
                else:
                    clarifications = {
                        "cake_flavor": "I didn't quite catch the flavor. Which cake flavor would you like (e.g. Belgian Dark Chocolate, Red Velvet, Vanilla)?",
                        "weight_kg": "I didn't quite catch the weight. Could you please specify the weight in kilograms (e.g. 1 kg or 2 kg)?",
                        "required_date": "Could you please clarify what date and time you need the cake ready (e.g. tomorrow at 4 PM)?",
                        "custom_message": "What message would you like written on the cake, or say 'no message' if none?",
                        "delivery_preference": "Would you like home delivery to your address, or store pickup from our bakery?",
                        "budget_inr": "What approximate budget in rupees do you have in mind for the cake (e.g. Rs. 1500)?"
                    }
                return state, clarifications.get(last_f, cls.FIELD_QUESTIONS.get(last_f, "")), tools

            return cls._ask_next_missing_field(state, tools, prefix=prefix, language=language)

        state["status"] = cls.AWAITING_CONFIRMATION
        state["confirmation_pending"] = True
        state["last_asked_field"] = None

        try:
            req_d = str(fields.get("required_date"))
            avail = CalendarService.check_availability(req_d, "17:00", duration_minutes=30, business_id=cls.BUSINESS_ID)
            tools.append({
                "tool": "check_calendar_availability",
                "args": {"requested_time": req_d, "business_id": cls.BUSINESS_ID},
                "result": avail
            })
        except Exception:
            pass

        formatted_date = cls._format_date(fields.get("required_date"))
        return state, (
            f"Let me confirm your cake order: A {fields['weight_kg']}kg {fields['cake_flavor']} cake for "
            f"{fields['delivery_preference']} on {formatted_date}, with message '{fields['custom_message']}', "
            f"approximate budget Rs. {fields['budget_inr']}. Is that correct?"
        ), tools

    @classmethod
    def _create_callback_for_incomplete_request(cls, state: dict[str, Any], caller_name: str, caller_phone: str, tools: list[dict[str, Any]], reason: str = "Customer needs assistance") -> tuple[dict[str, Any], str, list[dict[str, Any]]]:
        missing_str = ", ".join(state.get("missing_fields", [])) or "none"
        summary = f"{reason}. Missing cake order details: {missing_str}."
        callback = ExternalApiService.create_callback_task(summary, caller_name=caller_name, caller_phone=caller_phone)
        tools.append({"tool": "create_callback_task", "args": {"issue_description": summary}, "result": callback})
        if callback.get("success"):
            state["callback_task_created"] = True
            state["callback_task"] = callback
            state["status"] = cls.CALLBACK_REQUIRED
            state["last_asked_field"] = None
            return state, "No problem! I've created a callback request so our head baker Ananya can follow up with you. Thank you and have a wonderful day, goodbye!", tools
        return state, "I'm sorry, but I couldn't complete that request right now. Please call our bakery again shortly.", tools

    @classmethod
    def start_missed_call(cls, caller_name: str, caller_phone: str, language: str = "auto") -> dict[str, Any]:
        record_id = f"rec-cake-{uuid.uuid4().hex[:12]}"
        state = cls.initial_state(record_id, caller_phone)
        lang = cls._detect_language("", language)
        if lang == "kn":
            greeting = "ನಮಸ್ಕಾರ! ಸ್ವೀಟ್ ಟ್ರೀಟ್ಸ್ ಬೇಕರಿಗೆ ಸುಸ್ವಾಗತ. ನಿಮ್ಮ ಮಿಸ್ಡ್ ಕಾಲ್ ನೋಡಿದೆವು. ನೀವು ಕೇಕ್ ಆರ್ಡರ್ ಮಾಡಲು ಬಯಸುತ್ತೀರಾ ಅಥವಾ ಯಾವುದೇ ವಿಚಾರಣೆ ಇದೆಯೇ?"
        elif lang == "hi":
            greeting = "नमस्ते! स्वीट ट्रीट्स बेकरी में आपका स्वागत है। हमें आपका मिस्ड कॉल मिला। क्या आप केक ऑर्डर करना चाहते हैं या कोई सामान्य पूछताछ है?"
        else:
            greeting = cls.MISSED_CALL_GREETING

        callback = ExternalApiService.create_callback_task(
            issue_summary="Automated callback after missed cake-order call",
            caller_name=caller_name,
            caller_phone=caller_phone,
        )
        state["missed_call_callback_task"] = callback
        tools = [{
            "tool": "create_callback_task",
            "args": {"type": "MISSED_CALL_CALLBACK", "customer_phone": caller_phone},
            "result": callback,
        }]
        cls._save_record(
            record_id=record_id,
            business_id=cls.BUSINESS_ID,
            workflow_id=cls.WORKFLOW_ID,
            caller_name=caller_name,
            caller_phone=caller_phone,
            state=state,
            transcript=[{"role": "assistant", "content": greeting}],
            tools=tools,
        )
        return {
            "record_id": record_id,
            "assistant_reply": greeting,
            "language": lang,
            "executed_tools": tools,
            "conversation_state": state,
            "missing_fields": state["missing_fields"],
            "is_complete": False,
        }

    @classmethod
    def _complete_cake_order(cls, state: dict[str, Any], caller_name: str, caller_phone: str, tools: list[dict[str, Any]]) -> tuple[dict[str, Any], str, list[dict[str, Any]]]:
        fields = state["collected_fields"]
        enq_id = f"ENQ-{uuid.uuid4().hex[:6].upper()}"

        flavor = fields.get("cake_flavor", "Chocolate")
        weight = str(fields.get("weight_kg", "1"))
        order_type = fields.get("order_type", "New Cake Order")
        cake_type = fields.get("cake_type") or "Birthday Cake"
        req_date = fields.get("required_date") or (datetime.now() + timedelta(days=1)).replace(hour=17, minute=0, second=0).isoformat()
        delivery_pref = fields.get("delivery_preference", "Store Pickup")
        custom_msg = fields.get("custom_message") or "None"
        budget = str(fields.get("budget_inr", "1500"))

        if "anniversary" in (custom_msg + flavor + order_type).lower():
            cake_type = "Anniversary Cake"
        elif "wedding" in (custom_msg + flavor + order_type).lower():
            cake_type = "Tier Wedding Cake"

        enquiry_tool_res = {
            "success": True,
            "enquiry_id": enq_id,
            "order_type": order_type,
            "cake_type": cake_type,
            "flavor": flavor,
            "weight_kg": weight,
            "delivery_preference": delivery_pref,
            "budget": f"Rs. {budget}",
            "custom_message": custom_msg,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        tools.append({
            "tool": "create_order_enquiry",
            "args": {"enquiry_id": enq_id, "cake_type": cake_type, "flavor": flavor, "weight": f"{weight}kg"},
            "result": enquiry_tool_res
        })
        state["order_enquiry_created"] = True
        state["enquiry"] = enquiry_tool_res

        alert_res = ExternalApiService.send_owner_summary_alert(
            business_name="Sweet Treats Bakery & Confectionery",
            owner_phone="+91 98765 43210",
            caller_name=caller_name,
            caller_phone=caller_phone,
            order_type=order_type,
            cake_type=cake_type,
            details={
                "flavor": flavor,
                "weight": f"{weight} kg",
                "date_time": req_date,
                "delivery": delivery_pref,
                "message_on_cake": custom_msg,
                "budget": f"Rs. {budget}"
            }
        )
        tools.append({
            "tool": "send_owner_summary_alert",
            "args": {"recipient": "Ananya Sharma (Owner)", "phone": "+91 98765 43210", "enquiry_id": enq_id},
            "result": alert_res
        })

        try:
            target_dt = CalendarService.parse_datetime_input(req_date, "17:00")
            start_iso = target_dt.isoformat()
            end_iso = (target_dt + timedelta(minutes=30)).isoformat()
            cake_title = f"Cake Order: {cake_type} ({flavor}, {weight}kg) - {caller_name}"
            cal_res = CalendarService.create_event(
                business_id=cls.BUSINESS_ID,
                title=cake_title,
                start_time=start_iso,
                end_time=end_iso,
                attendee_name=caller_name,
                attendee_phone=caller_phone,
                description=f"Sweet Treats Bakery [{enq_id}]: {cake_type} ({flavor}, {weight}kg). {delivery_pref} at Rs. {budget}. Message: '{custom_msg}'. Caller: {caller_name} ({caller_phone})"
            )
            tools.append({
                "tool": "create_calendar_event",
                "args": {"title": cake_title, "start_time": start_iso, "enquiry_id": enq_id},
                "result": cal_res
            })
            state["calendar_event_created"] = True
            state["calendar_event"] = cal_res
        except Exception as e:
            print(f"[Calendar Event Notice] {e}")

        state["status"] = cls.COMPLETED
        state["last_asked_field"] = None

        formatted_date = cls._format_date(req_date)
        return state, (
            f"Thank you for choosing Sweet Treats Bakery! Your cake order ({enq_id}) for a {weight}kg {flavor} cake "
            f"({delivery_pref}) on {formatted_date} has been confirmed and scheduled on our bakery calendar. "
            f"We have alerted our baker Ananya Sharma and will have it freshly prepared for you. "
            f"Thank you and have a wonderful day, goodbye!"
        ), tools

    @classmethod
    def _ask_next_missing_field(cls, state: dict[str, Any], tools: list[dict[str, Any]], prefix: str = "", language: str = "en") -> tuple[dict[str, Any], str, list[dict[str, Any]]]:
        next_field = state["missing_fields"][0]
        state["last_asked_field"] = next_field
        if language == "kn":
            question = cls.FIELD_QUESTIONS_KN.get(next_field, cls.FIELD_QUESTIONS.get(next_field, ""))
        elif language == "hi":
            question = cls.FIELD_QUESTIONS_HI.get(next_field, cls.FIELD_QUESTIONS.get(next_field, ""))
        else:
            question = cls.FIELD_QUESTIONS.get(next_field, f"Could you please share your preference for {next_field.replace('_', ' ')}?")
        return state, f"{prefix} {question}".strip(), tools

    @staticmethod
    def _format_date(iso_or_str: Any) -> str:
        if not iso_or_str:
            return "Tomorrow at 5:00 PM"
        try:
            dt = datetime.fromisoformat(str(iso_or_str).replace("Z", "+00:00"))
            return dt.strftime("%B %d at %I:%M %p")
        except Exception:
            return str(iso_or_str)

    @staticmethod
    def _is_yes(message: str) -> bool:
        value = (message or "").strip().lower()
        if re.search(r"\b(?:yes|yep|yeah|correct|confirm|confirmed|proceed|haan|ha|ಹೌದು)\b", value) and not re.search(r"\b(?:no|don't|dont|not|cancel|wrong)\b", value):
            return True
        return bool(re.fullmatch(r"(?:yes|yep|yeah|correct|right|confirm|that's correct|that is correct|haan|ha|ಹೌದು)[.!]?", value) or re.match(r"(?:yes|yep|yeah)\b.*\bcorrect\b", value))

    @staticmethod
    def _is_no(message: str) -> bool:
        value = (message or "").strip().lower()
        return bool(
            re.fullmatch(r"\s*(?:no|nope|not correct|change it|nah|nahi|ಇಲ್ಲ|wrong|incorrect|not right)\s*[.!]?\s*", value, re.IGNORECASE)
            or re.search(r"\b(?:not correct|incorrect|wrong detail|that's wrong|thats wrong)\b", value)
        )

    @classmethod
    def _load_state(cls, record_id: str, caller_phone: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        state = cls.initial_state(record_id, caller_phone)
        tools = []
        with get_db_connection() as conn:
            row = conn.execute(text("SELECT collected_data, tools_executed FROM records WHERE id = :id"), {"id": record_id}).fetchone()
        if not row:
            return state, tools
        try:
            payload = json.loads(row[0] or "{}")
            if isinstance(payload, dict):
                loaded_state = payload.get("cake_workflow_state")
                if isinstance(loaded_state, dict):
                    state = loaded_state
                else:
                    for k, v in payload.items():
                        if k in state["collected_fields"] and v is not None:
                            state["collected_fields"][k] = v
                state["missing_fields"] = cls.get_missing_fields(state)
            if row[1]:
                tools = json.loads(row[1] or "[]")
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
        return state, tools

    @classmethod
    def _save_record(cls, record_id: str, business_id: str, workflow_id: str, caller_name: str, caller_phone: str, state: dict[str, Any], transcript: list[dict[str, Any]], tools: list[dict[str, Any]]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        flattened = dict(state.get("collected_fields", {}))
        flattened["cake_workflow_state"] = state
        summary = SummaryService.generate_clear_summary({
            "caller_name": caller_name,
            "caller_phone": caller_phone,
            "business_id": business_id,
            "intent": "Cake Order",
            "followup_status": "Completed" if state.get("status") == cls.COMPLETED else "Pending",
            "collected_data": flattened
        })
        payload = json.dumps(flattened)
        with get_db_connection() as conn:
            existing = conn.execute(text("SELECT id FROM records WHERE id = :id"), {"id": record_id}).fetchone()
            if existing:
                conn.execute(text("""
                    UPDATE records SET intent = :intent, collected_data = :collected_data, ai_summary = :summary,
                    followup_status = :followup_status, transcript = :transcript, tools_executed = :tools
                    WHERE id = :id
                """), {
                    "id": record_id,
                    "intent": "Cake Order",
                    "collected_data": payload,
                    "summary": summary,
                    "followup_status": "Completed" if state.get("status") == cls.COMPLETED else "Pending",
                    "transcript": json.dumps(transcript),
                    "tools": json.dumps(tools),
                })
            else:
                conn.execute(text("""
                    INSERT INTO records (id, business_id, workflow_id, caller_name, caller_phone, intent, collected_data, ai_summary, urgency, followup_status, transcript, tools_executed, created_at)
                    VALUES (:id, :business_id, :workflow_id, :caller_name, :caller_phone, 'Cake Order', :collected_data, :summary, 'Normal', :followup_status, :transcript, :tools, :created_at)
                """), {
                    "id": record_id,
                    "business_id": business_id,
                    "workflow_id": workflow_id,
                    "caller_name": caller_name,
                    "caller_phone": caller_phone,
                    "collected_data": payload,
                    "summary": summary,
                    "followup_status": "Completed" if state.get("status") == cls.COMPLETED else "Pending",
                    "transcript": json.dumps(transcript),
                    "tools": json.dumps(tools),
                    "created_at": now,
                })
            conn.commit()

    @classmethod
    def process_conversation(cls, request_data: dict[str, Any]) -> dict[str, Any]:
        business_id = request_data.get("business_id") or cls.BUSINESS_ID
        workflow_id = request_data.get("workflow_id") or cls.WORKFLOW_ID
        caller_name = request_data.get("caller_name") or "Customer"
        caller_phone = request_data.get("caller_phone") or "+91 98765 43210"
        record_id = request_data.get("record_id") or f"rec-cake-{uuid.uuid4().hex[:12]}"
        messages = request_data.get("messages") or []

        user_messages = [item.get("content", "") for item in messages if item.get("role") == "user"]
        customer_message = user_messages[-1] if user_messages else ""

        detected_lang = cls._detect_language(customer_message, request_data.get("language"))

        state, historical_tools = cls._load_state(record_id, caller_phone)
        state["customer_phone"] = caller_phone
        state["call_id"] = record_id

        # If state has no collected fields yet and client passed a multi-turn transcript, replay prior turns
        if not any(state["collected_fields"].get(k) for k in ["cake_flavor", "weight_kg", "required_date", "custom_message"]) and len(user_messages) > 1:
            for prior_msg in user_messages[:-1]:
                state, _, prior_turn_tools = cls.advance_state(state, prior_msg, caller_name, caller_phone)
                historical_tools.extend(prior_turn_tools)

        state, reply, turn_tools = cls.advance_state(state, customer_message, caller_name, caller_phone, language=detected_lang)
        all_tools = historical_tools + turn_tools
        state["missing_fields"] = cls.get_missing_fields(state)

        full_transcript = messages + [{"role": "assistant", "content": reply}]
        cls._save_record(
            record_id=record_id,
            business_id=business_id,
            workflow_id=workflow_id,
            caller_name=caller_name,
            caller_phone=caller_phone,
            state=state,
            transcript=full_transcript,
            tools=all_tools,
        )

        flattened = dict(state.get("collected_fields", {}))
        flattened["cake_workflow_state"] = state
        flattened["intent"] = "Cake Order"
        flattened["status"] = state.get("status")
        flattened["field_status"] = {
            k: {
                "value": v,
                "status": "answered" if cls._is_valid_field(k, v) else "missing",
                "attempts": 0
            }
            for k, v in state["collected_fields"].items()
        }
        flattened["current_question_field"] = state.get("last_asked_field")
        flattened["_last_asked_field"] = state.get("last_asked_field")

        return {
            "record_id": record_id,
            "assistant_reply": reply,
            "language": detected_lang,
            "language_switched": False,
            "urgency": "Normal",
            "executed_tools": turn_tools,
            "collected_data": flattened,
            "conversation_state": state,
            "missing_fields": state["missing_fields"],
            "is_complete": state["status"] in {cls.COMPLETED, cls.CALLBACK_REQUIRED},
        }
