import os
import json
import uuid
import re
import httpx
from typing import Optional, Any, Tuple, Dict, List
from datetime import datetime, timedelta, timezone
from sqlalchemy import text
from app.database import get_db_connection
from app.services.calendar_service import CalendarService
from app.services.delivery_workflow_service import DeliveryWorkflowService
from app.services.cake_workflow_service import CakeWorkflowService
from app.services.external_api_service import ExternalApiService
from app.services.summary_service import SummaryService
from app.services.langchain_service import LangChainService, TurnCorrectionAnalysis, SlotCorrection

class AiService:
    @staticmethod
    def detect_language(text_msg: str) -> str:
        if not text_msg:
            return 'en'

        # Check Kannada script range (\u0C80-\u0CFF)
        if re.search(r'[\u0C80-\u0CFF]', text_msg):
            return 'kn'

        # Check Devanagari script range (\u0900-\u097F)
        if re.search(r'[\u0900-\u097F]', text_msg):
            return 'hi'

        lower = text_msg.lower()
        tokens = set(re.findall(r'[a-zA-Z]+', lower))

        # Check Kanglish keywords (whole words only)
        kanglish_words = {
            'namaskara', 'kannada', 'beku', 'beki', 'yaavaga', 'samaya', 'yaake', 
            'hege', 'elli', 'nanna', 'nimma', 'houdu', 'illa', 'dhanyavada', 
            'madabeka', 'madi', 'naale', 'sanje', 'belagge', 'eshtu', 'gante', 
            'gantege', 'ide', 'aguthe', 'kano', 'hogi', 'sahaya', 'turtu'
        }
        if kanglish_words & tokens:
            return 'kn'

        # Check Hinglish keywords (whole words only)
        hinglish_words = {
            'namaste', 'namaskar', 'shukriya', 'dhanyawad', 'dhanyabad', 'kya', 
            'hai', 'hain', 'karna', 'karo', 'chahiye', 'kaise', 'bhai', 'haan', 
            'nahi', 'kal', 'aaj', 'shaam', 'samay', 'mujhe', 'aap', 'kitna', 
            'kitne', 'paisa', 'daam', 'kab', 'kaha', 'bhejo', 'bhej', 'batao', 
            'sunao', 'swagat', 'par', 'mein', 'madad'
        }
        if hinglish_words & tokens:
            return 'hi'

        return 'en'

    CAKE_REQUIRED_FIELDS = [
        "order_type",
        "cake_flavor",
        "weight_kg",
        "required_date",
        "custom_message",
        "delivery_preference",
        "budget_inr"
    ]

    AMBIGUOUS_WORDS = {
        "yes", "yeah", "yep", "sure", "that's fine", "thats fine", "fine",
        "ok", "okay", "whatever", "either", "both", "any", "anything", "no",
        "all good", "sounds good", "alright", "right", "maybe", "idk",
        "i don't know", "i dont know", "you decide", "any is fine"
    }

    @staticmethod
    def is_valid_field_value(field_key: str, value: any) -> bool:
        if value is None or value == "":
            return False

        val_clean = str(value).strip().lower()
        if val_clean in ["none", "null", "n/a", "undefined", "unknown"]:
            if field_key == "custom_message" and val_clean in ["none", "no", "no message", "nothing"]:
                return True
            return False

        if val_clean in AiService.AMBIGUOUS_WORDS:
            return False

        if field_key == "custom_message":
            return len(val_clean) >= 2 or val_clean in ["none", "n/a", "no", "no message", "nothing"]

        if field_key == "delivery_preference":
            has_delivery = any(w in val_clean for w in ["delivery", "deliver", "home", "doorstep", "address"])
            has_pickup = any(w in val_clean for w in ["pickup", "pick up", "takeaway", "store", "collect", "baker", "shop"])
            if has_delivery and has_pickup:
                return False
            return has_delivery or has_pickup

        if field_key == "weight_kg":
            try:
                m = re.search(r'(\d+(?:\.\d+)?)', str(value))
                if m and float(m.group(1)) > 0:
                    return True
            except Exception:
                pass
            return False

        if field_key == "budget_inr":
            try:
                m = re.search(r'(\d+)', str(value))
                if m and int(m.group(1)) > 0:
                    return True
            except Exception:
                pass
            return val_clean in ["standard", "normal", "regular", "flexible", "any", "1500"]

        if field_key == "order_type":
            return len(str(value).strip()) >= 3

        if field_key == "cake_flavor":
            if val_clean in ["cake", "sweet", "good", "normal", "best", "regular"]:
                return False
            return len(val_clean) >= 3

        if field_key == "required_date":
            if val_clean in ["anytime", "any time", "later", "whenever", "soon"]:
                return False
            return len(val_clean) >= 4

        return len(val_clean) >= 2

    @staticmethod
    def get_missing_required_fields(workflow: dict, fields: list, collected_data: dict) -> list:
        industry = (workflow.get("industry") or "").lower()
        is_cake_shop = ("cake" in industry or "bakery" in industry or workflow.get("id") == "wf-cake-01")

        req_keys = [f["key"] for f in fields if f.get("required")]
        if not req_keys and is_cake_shop:
            req_keys = AiService.CAKE_REQUIRED_FIELDS

        missing = []
        for key in req_keys:
            val = collected_data.get(key)
            if not AiService.is_valid_field_value(key, val):
                missing.append(key)
        return missing

    @staticmethod
    def extract_workflow_fields(fields: list, messages: list, collected_data: dict, groq_api_key: str = None, current_question_field: str = None) -> dict:
        user_texts = [m["content"] for m in messages if m.get("role") == "user"]
        if not user_texts:
            return {}

        latest_user = user_texts[-1]
        latest_user_lower = latest_user.lower()
        full_user = " ".join(user_texts[-4:])
        full_user_lower = full_user.lower()

        extracted = {}

        # 1. Groq LLM extraction (JSON Mode)
        if groq_api_key:
            try:
                extraction_prompt = (
                    f"You are a structured entity extraction engine for a customer service voice AI.\n"
                    f"Target Workflow Database Fields to extract:\n{json.dumps(fields, indent=2)}\n\n"
                    f"Already Extracted Fields:\n{json.dumps({k: v for k, v in collected_data.items() if not k.startswith('_')}, indent=2)}\n\n"
                    f"Currently Asking For Field: '{current_question_field or 'any'}'\n\n"
                    f"Caller Just Said: '{latest_user}' (Recent Context: '{full_user}')\n\n"
                    f"TASK & CRITICAL RULES:\n"
                    f"- Extract any values matching the target database fields that the caller mentioned.\n"
                    f"- CRITICAL UPDATE RULE: NEVER permanently lock an extracted field! If the caller corrects, changes, or says they meant something else (e.g. 'Actually make it 2kg', 'Change flavor to Vanilla', 'I meant Red Velvet', 'Store pickup instead of delivery'), ALWAYS extract the new updated value so the existing field can be updated.\n"
                    f"- If the customer gives an AMBIGUOUS response (such as 'yes', 'that\\'s fine', 'sure', 'fine', 'okay', 'whatever', 'either'), DO NOT extract delivery_preference or any field. Leave it empty.\n"
                    f"- If the caller asks to write text on the cake (e.g. 'write Happy Birthday on it'), extract it as 'message_on_cake' and 'custom_message'.\n"
                    f"- Map delivery_preference ONLY if explicitly stated: 'Home Delivery' or 'Store Pickup'. Do NOT guess.\n"
                    f"- Return ONLY a JSON object containing the newly detected key-value pairs (empty {{}} if none)."
                )
                candidate_models = [os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"), "openai/gpt-oss-20b", "qwen/qwen3.6-27b"]
                for mdl in candidate_models:
                    try:
                        with httpx.Client(timeout=5.0) as client:
                            resp = client.post(
                                "https://api.groq.com/openai/v1/chat/completions",
                                headers={"Authorization": f"Bearer {groq_api_key}", "Content-Type": "application/json"},
                                json={
                                    "model": mdl,
                                    "messages": [{"role": "system", "content": extraction_prompt}],
                                    "response_format": {"type": "json_object"},
                                    "temperature": 0.1
                                }
                            )
                            if resp.status_code == 200:
                                data = resp.json()["choices"][0]["message"]["content"]
                                parsed = json.loads(data)
                                if isinstance(parsed, dict):
                                    for k, v in parsed.items():
                                        if v not in [None, "", "null", "None"] and AiService.is_valid_field_value(k, v):
                                            extracted[k] = v
                                break
                    except Exception:
                        continue
            except Exception as e:
                print(f"[Entity Extraction Notice] Groq extraction skipped: {e}")

        # 2. Rule & Regex Heuristic Fill (latest user statement always takes priority for new answers or corrections)
        field_keys = [f["key"] for f in fields]

        # Weight extraction (supports English, Kannada ಒಂದು/ಎರಡು/ಅರ್ಧ, Hindi ek/do/aadha, and numeric kg/kilo/grams)
        if ("weight_kg" in field_keys or not field_keys) and "weight_kg" not in extracted:
            # Map Kannada number words to numeric strings
            kn_num_map = {
                "ಅರ್ಧ": "0.5", "ಒಂದುವರೆ": "1.5", "ಒಂದು": "1", "ಎರಡು": "2", "ಮೂರು": "3", "ನಾಲ್ಕು": "4", "ಐದು": "5",
                "ondu": "1", "eradu": "2", "mooru": "3", "naalku": "4", "aidu": "5", "ardha": "0.5"
            }
            # Map Hindi number words to numeric strings
            hi_num_map = {
                "आधा": "0.5", "एक": "1", "दो": "2", "तीन": "3", "चार": "4", "पांच": "5", "डेढ़": "1.5", "ढाई": "2.5",
                "aadha": "0.5", "ek": "1", "do": "2", "teen": "3", "char": "4", "paanch": "5", "dedh": "1.5", "dhai": "2.5"
            }

            en_num_map = {
                "quarter": "0.25", "half": "0.5", "one": "1", "two": "2", "three": "3",
                "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10"
            }

            def parse_weight_from_text(text_val: str) -> Optional[str]:
                if not text_val:
                    return None
                tv_lower = text_val.lower()

                # Compound expressions
                if re.search(r"\b(?:one\s+and\s+(?:a\s+)?half|1\s+and\s+(?:a\s+)?half|1\.5|dedh|ಒಂದುವರೆ)\b", tv_lower):
                    return "1.5"
                if re.search(r"\b(?:two\s+and\s+(?:a\s+)?half|2\s+and\s+(?:a\s+)?half|2\.5|dhai)\b", tv_lower):
                    return "2.5"
                if re.search(r"\b(?:half\s+(?:a\s+)?(?:kg|kilo|kilogram)|half\s*kg|half\s*kilo|1/2\s*kg|0\.5\s*kg|ardha\s*kg|aadha\s*kilo|aadha\s*kg|ಅರ್ಧ\s*ಕೆಜಿ)\b", tv_lower):
                    return "0.5"

                # Check Kannada words
                for w_kn, num_kn in kn_num_map.items():
                    if re.search(rf"\b{re.escape(w_kn)}\b", tv_lower) and ("ಕೆಜಿ" in tv_lower or "kg" in tv_lower or "kilo" in tv_lower or "ಕೇಜಿ" in tv_lower or current_question_field == "weight_kg"):
                        return num_kn
                # Check Hindi words
                for w_hi, num_hi in hi_num_map.items():
                    if re.search(rf"\b{re.escape(w_hi)}\b", tv_lower) and ("kilo" in tv_lower or "kg" in tv_lower or "किलो" in tv_lower or current_question_field == "weight_kg"):
                        return num_hi
                # Check English number words
                for w_en, num_en in en_num_map.items():
                    if re.search(rf"\b{w_en}\s*(?:kg|kilo|kilos|kilogram|kilograms|pound|pounds|lb|lbs)\b", tv_lower):
                        return num_en
                    elif current_question_field == "weight_kg" and re.search(rf"^\s*(?:just\s+|about\s+|around\s+)?{w_en}(?:\s+(?:please|only))?\s*[.!]?$", tv_lower):
                        return num_en
                # Bare unit words
                if re.search(r"\b(?:just\s+)?(?:a\s+|an\s+)?(?:kilo|kilogram|kg|kilos|kilograms)\b", tv_lower):
                    if current_question_field == "weight_kg" or re.search(r"\b(?:a\s+|an\s+)(?:kilo|kilogram|kg)\b", tv_lower):
                        return "1"

                # Standard digits with kg/kilo/pound/gm/gram
                m_dig = re.search(r'(?:weight|size|portion)?\s*(?:to|is|as)?\s*(\d+(?:\.\d+)?)\s*(?:kg|kilo|kilos|kilogram|kilograms|pound|pounds|lb|lbs|gm|gram|grams|g|ಕೆಜಿ|ಕೇಜಿ|ಕಿಲೊ|किलो)\b', tv_lower)
                if not m_dig:
                    m_dig = re.search(r'\b(?:make it|change(?:\s+the\s+weight|\s+it)?\s+to|set\s+to|weight\s+(?:is|to))\s*(\d+(?:\.\d+)?)\b', tv_lower)
                if not m_dig and current_question_field == "weight_kg":
                    m_dig = re.search(r'\b(\d+(?:\.\d+)?)\b', tv_lower)
                if m_dig:
                    val_str = m_dig.group(1)
                    if any(g in tv_lower for g in ["gm", "gram", "grams"]) and not any(k in tv_lower for k in ["kg", "kilo", "kilogram"]):
                        try:
                            val_f = float(val_str)
                            if val_f >= 100:
                                return str(val_f / 1000.0)
                        except Exception:
                            pass
                    return val_str
                return None

            w_found = parse_weight_from_text(latest_user)
            if w_found:
                extracted["weight_kg"] = w_found
            elif not AiService.is_valid_field_value("weight_kg", collected_data.get("weight_kg")):
                w_found_full = parse_weight_from_text(full_user)
                if w_found_full:
                    extracted["weight_kg"] = w_found_full

        # Cake flavor extraction (detects latest flavor or user correction)
        if ("cake_flavor" in field_keys or not field_keys) and "cake_flavor" not in extracted:
            flav_match_latest = re.search(r'\b(dark chocolate|chocolate|red velvet|vanilla|mango|black forest|pineapple|butterscotch|strawberry|choco chip|fruit|truffle|blueberry|butter scotch)\b', latest_user_lower)
            if not flav_match_latest:
                flav_match_latest = re.search(r'\b(?:change\s+(?:the\s+)?flavor\s+to|flavor\s+(?:is|to|as)|switch\s+flavor\s+to|make\s+it\s+flavor)\s+([a-zA-Z\s]+?)(?=\s+instead|\s+and|\s*[,.]|$)', latest_user_lower)
            if flav_match_latest:
                extracted["cake_flavor"] = flav_match_latest.group(1).strip().title()
            elif not AiService.is_valid_field_value("cake_flavor", collected_data.get("cake_flavor")):
                flav_match_full = re.search(r'\b(dark chocolate|chocolate|red velvet|vanilla|mango|black forest|pineapple|butterscotch|strawberry|choco chip|fruit|truffle|blueberry|butter scotch)\b', full_user_lower)
                if flav_match_full:
                    extracted["cake_flavor"] = flav_match_full.group(1).title()

        # Order type
        if ("order_type" in field_keys or not field_keys) and "order_type" not in extracted:
            if any(w in latest_user_lower for w in ["custom", "design", "photo cake", "theme"]):
                extracted["order_type"] = "Custom Design"
            elif any(w in latest_user_lower for w in ["enquiry", "inquiry", "rate", "price", "menu", "cost"]):
                extracted["order_type"] = "General Enquiry"
            elif any(w in latest_user_lower for w in ["new cake", "order", "cake", "buy", "place", "birthday", "anniversary"]):
                extracted["order_type"] = "New Cake Order"
            elif not collected_data.get("order_type"):
                if any(w in full_user_lower for w in ["custom", "design", "photo cake", "theme"]):
                    extracted["order_type"] = "Custom Design"
                elif any(w in full_user_lower for w in ["order", "cake", "buy", "place", "birthday", "anniversary", "pastry"]):
                    extracted["order_type"] = "New Cake Order"
                elif any(w in full_user_lower for w in ["enquiry", "inquiry", "rate", "price", "menu", "cost"]):
                    extracted["order_type"] = "General Enquiry"

        # Delivery preference (strictly require explicit delivery or pickup keyword; handles user corrections like "store pickup instead of delivery")
        if ("delivery_preference" in field_keys or not field_keys) and "delivery_preference" not in extracted:
            # Check if this is an ambiguous change phrase without an explicit choice (e.g. "change delivery preference", "change the delivery option")
            is_ambig_delivery_phrase = bool(re.search(
                r'\b(?:change|switch|modify|update|different)\s+(?:the\s+)?(?:delivery|pickup)(?:\s+(?:preference|option|method|type))?\b|\b(?:delivery|pickup)\s+(?:preference|option|method|type)\b',
                latest_user_lower
            ))
            if not is_ambig_delivery_phrase:
                if re.search(r'\b(?:store pickup|pickup|pick up)\s+instead(?:\s+of\s+delivery)?\b', latest_user_lower) or re.search(r'\b(?:change|switch|prefer)\s+(?:it\s+)?to\s+(?:store\s+)?pickup\b', latest_user_lower):
                    extracted["delivery_preference"] = "Store Pickup"
                elif re.search(r'\b(?:home delivery|delivery|deliver)\s+instead(?:\s+of\s+pickup)?\b', latest_user_lower) or re.search(r'\b(?:change|switch|prefer)\s+(?:it\s+)?to\s+(?:home\s+)?delivery\b', latest_user_lower):
                    extracted["delivery_preference"] = "Home Delivery"
                else:
                    has_del = bool(re.search(r'\b(home delivery|delivery|deliver(?:ed|y)? to (?:my )?(?:home|house|address)|deliver it|delivery please|home please|send to home|deliver)\b', latest_user_lower))
                    has_pick = bool(re.search(r'\b(store pickup|pickup|pick up|takeaway|collect|from (?:the )?store|pick it up|baker|shop)\b', latest_user_lower))
                    if has_del and not has_pick:
                        extracted["delivery_preference"] = "Home Delivery"
                    elif has_pick and not has_del:
                        extracted["delivery_preference"] = "Store Pickup"
                    elif not AiService.is_valid_field_value("delivery_preference", collected_data.get("delivery_preference")):
                        has_del_f = bool(re.search(r'\b(home delivery|delivery|deliver(?:ed|y)? to (?:my )?(?:home|house|address)|deliver it|delivery please|home please|send to home|deliver)\b', full_user_lower))
                        has_pick_f = bool(re.search(r'\b(store pickup|pickup|pick up|takeaway|collect|from (?:the )?store|pick it up|baker|shop)\b', full_user_lower))
                        if has_del_f and not has_pick_f:
                            extracted["delivery_preference"] = "Home Delivery"
                        elif has_pick_f and not has_del_f:
                            extracted["delivery_preference"] = "Store Pickup"

        # Tracking number
        if "tracking_number" in field_keys and "tracking_number" not in extracted:
            match_trk_latest = re.search(r'TRK-[A-Z0-9-]+', latest_user, re.IGNORECASE)
            if match_trk_latest:
                extracted["tracking_number"] = match_trk_latest.group(0).upper()
            elif not AiService.is_valid_field_value("tracking_number", collected_data.get("tracking_number")):
                match_trk_full = re.search(r'TRK-[A-Z0-9-]+', full_user, re.IGNORECASE)
                if match_trk_full:
                    extracted["tracking_number"] = match_trk_full.group(0).upper()

        # Logistics inquiry type
        if "inquiry_type" in field_keys and "inquiry_type" not in extracted:
            if any(w in latest_user_lower for w in ["delay", "late", "delayed", "not reached", "stuck"]):
                extracted["inquiry_type"] = "Delivery Delay"
            elif any(w in latest_user_lower for w in ["address", "location", "change address", "redirect"]):
                extracted["inquiry_type"] = "Address Change"
            elif any(w in latest_user_lower for w in ["status", "where is", "track", "tracking", "parcel", "package"]):
                extracted["inquiry_type"] = "Package Status"
            elif not AiService.is_valid_field_value("inquiry_type", collected_data.get("inquiry_type")):
                if any(w in full_user_lower for w in ["delay", "late", "delayed", "not reached", "stuck"]):
                    extracted["inquiry_type"] = "Delivery Delay"
                elif any(w in full_user_lower for w in ["address", "location", "change address", "redirect"]):
                    extracted["inquiry_type"] = "Address Change"
                elif any(w in full_user_lower for w in ["status", "where is", "track", "tracking", "parcel", "package"]):
                    extracted["inquiry_type"] = "Package Status"

        # Required Date & Time (handles user rescheduling or time changes)
        if "required_date" not in extracted:
            has_date_latest = bool(re.search(
                r"\b(?:today|tomorrow|day after tomorrow|naale|kal|parso|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
                latest_user_lower
            ))
            has_time_latest = bool(re.search(
                r"\b\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)\b|\b(?:morning|afternoon|evening|night|sanje|belagge)\b",
                latest_user_lower
            ))
            is_date_question = (current_question_field == "required_date")
            is_weight_or_price = bool(re.search(r"\b(?:\d+\s*(?:kg|kilo|kilogram|gm|gram|grams|rs|rupees|inr))\b", latest_user_lower))

            if (is_date_question or has_date_latest or (has_time_latest and not is_weight_or_price)) and not any(w in latest_user_lower for w in ["anytime", "any time", "later", "whenever"]):
                if "day after" in latest_user_lower or "parso" in latest_user_lower:
                    d_str = "day after tomorrow"
                elif "tomorrow" in latest_user_lower or "naale" in latest_user_lower or "kal" in latest_user_lower:
                    d_str = "tomorrow"
                elif "today" in latest_user_lower or "aaj" in latest_user_lower or "ivattu" in latest_user_lower:
                    d_str = "today"
                else:
                    d_str = "tomorrow" if is_date_question else "today"
                    for d_name in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]:
                        if re.search(rf"\b{d_name}\b", latest_user_lower):
                            d_str = d_name
                            break
                t_str = "18:00"
                for tm in re.finditer(r'(\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)?)', latest_user_lower, re.I):
                    after_str = latest_user_lower[tm.end():tm.end()+6]
                    if not re.match(r'^\s*(?:kg|kilo|kilogram|pound|lb|rs|rupees|gm|gram)', after_str):
                        t_str = tm.group(1)
                        break
                target_dt = CalendarService.parse_datetime_input(d_str, t_str)
                extracted["required_date"] = target_dt.isoformat()
            elif not AiService.is_valid_field_value("required_date", collected_data.get("required_date")):
                has_date_full = bool(re.search(
                    r"\b(?:today|tomorrow|day after tomorrow|naale|kal|parso|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
                    full_user_lower
                ))
                has_time_full = bool(re.search(
                    r"\b\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)\b|\b(?:morning|afternoon|evening|night|sanje|belagge)\b",
                    full_user_lower
                ))
                if (has_date_full or has_time_full) and not any(w in full_user_lower for w in ["anytime", "any time", "later", "whenever"]):
                    if "day after" in full_user_lower or "parso" in full_user_lower:
                        d_str = "day after tomorrow"
                    elif "tomorrow" in full_user_lower or "naale" in full_user_lower or "kal" in full_user_lower:
                        d_str = "tomorrow"
                    elif "today" in full_user_lower or "aaj" in full_user_lower or "ivattu" in full_user_lower:
                        d_str = "today"
                    else:
                        d_str = "today"
                        for d_name in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]:
                            if re.search(rf"\b{d_name}\b", full_user_lower):
                                d_str = d_name
                                break
                    t_str = "18:00"
                    for tm in re.finditer(r'(\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)?)', full_user_lower, re.I):
                        after_str = full_user_lower[tm.end():tm.end()+6]
                        if not re.match(r'^\s*(?:kg|kilo|pound|lb)', after_str):
                            t_str = tm.group(1)
                            break
                    target_dt = CalendarService.parse_datetime_input(d_str, t_str)
                    extracted["required_date"] = target_dt.isoformat()

        # Custom message / Message on cake
        if any(w in latest_user_lower for w in ["no message", "no text", "nothing on cake", "no name", "without message", "no writing"]) or (current_question_field == "custom_message" and latest_user_lower in ["no", "none", "nothing", "na", "n/a"]):
            extracted["custom_message"] = "None"
            extracted["message_on_cake"] = "None"
        else:
            msg_match = re.search(r'\b(?:change\s+(?:the\s+)?(?:message|text|note|writing)\s+to|write|message|text|says|name on cake|note)\s*[\'"]?([^\'"]+?)[\'"]?(?=\s+on|\s+for|\s+instead|\s*$)', latest_user_lower)
            if not msg_match:
                msg_match = re.search(r'write\s+([a-zA-Z0-9\s]+?)\s+on\s+(?:the\s+)?cake', latest_user_lower)
            if msg_match:
                clean_msg = msg_match.group(1).strip()
                if clean_msg.lower() in ["none", "nothing", "no message", "no"]:
                    extracted["custom_message"] = "None"
                    extracted["message_on_cake"] = "None"
                elif clean_msg:
                    extracted["custom_message"] = clean_msg.title()
                    extracted["message_on_cake"] = clean_msg.title()
            elif current_question_field in ["custom_message", "message_on_cake"] and len(latest_user.strip()) >= 2 and latest_user_lower not in AiService.AMBIGUOUS_WORDS:
                extracted["custom_message"] = latest_user.strip().title()
                extracted["message_on_cake"] = latest_user.strip().title()

        # Budget
        if "budget_inr" in field_keys and "budget_inr" not in extracted:
            b_match_latest = re.search(r'\b(?:change\s+(?:the\s+)?budget\s+to|budget|price|cost)?\s*(?:to|is|of)?\s*(?:rs|rupees|inr|₹)\s*(\d+)', latest_user_lower) or re.search(r'(\d+)\s*(?:rs|rupees|inr)', latest_user_lower)
            if not b_match_latest and current_question_field == "budget_inr":
                b_match_latest = re.search(r'\b(\d+)\b', latest_user_lower)
            if b_match_latest:
                extracted["budget_inr"] = b_match_latest.group(1)
            elif current_question_field == "budget_inr" and any(w in latest_user_lower for w in ["any", "standard", "normal", "flexible", "regular"]):
                extracted["budget_inr"] = "1500"
            elif not collected_data.get("budget_inr"):
                b_match_full = re.search(r'(?:rs|rupees|inr|budget|₹)\s*(\d+)', full_user_lower) or re.search(r'(\d+)\s*(?:rs|rupees|inr)', full_user_lower)
                if b_match_full:
                    extracted["budget_inr"] = b_match_full.group(1)

        return extracted

    @staticmethod
    def detect_ambiguous_correction(latest_user: str, fields: list, collected_data: dict, extracted: dict) -> tuple[bool, Optional[str], Optional[str]]:
        """
        Detects if the caller indicates they want to correct, change, or update a field,
        but did NOT provide a valid specific value (ambiguous correction).
        Returns: (is_ambiguous, target_field, clarification_question)
        """
        user_lower = (latest_user or "").strip().lower()
        if not user_lower:
            return False, None, None

        change_cue = bool(re.search(r'\b(change|correct|update|switch|different|instead|modify|reschedule|meant|mean|wrong|another|replace|mistake)\b', user_lower))
        if not change_cue:
            return False, None, None

        # 1. Flavor
        if any(w in user_lower for w in ["flavor", "flavour", "taste"]):
            if "cake_flavor" not in extracted or not AiService.is_valid_field_value("cake_flavor", extracted.get("cake_flavor")):
                return True, "cake_flavor", "Sure! Which cake flavor would you like instead? We offer Belgian Dark Chocolate, Red Velvet, Vanilla Mango, and more."

        # 2. Delivery / Pickup
        if any(w in user_lower for w in ["delivery", "pickup", "pick up", "deliver", "address"]):
            if "delivery_preference" not in extracted or not AiService.is_valid_field_value("delivery_preference", extracted.get("delivery_preference")):
                return True, "delivery_preference", "Sure! Would you prefer Home Delivery to your address, or Store Pickup from our bakery?"

        # 3. Weight / Size
        if any(w in user_lower for w in ["weight", "size", "kilo", "kg", "portion"]):
            if "weight_kg" not in extracted or not AiService.is_valid_field_value("weight_kg", extracted.get("weight_kg")):
                return True, "weight_kg", "Sure! How many kilograms would you like to change the cake weight to?"

        # 4. Date / Time / Reschedule
        if any(w in user_lower for w in ["date", "time", "timing", "day", "slot", "reschedule"]):
            if "required_date" not in extracted or not AiService.is_valid_field_value("required_date", extracted.get("required_date")):
                return True, "required_date", "Sure! What date and time would you like to set instead?"

        # 5. Message on cake
        if any(w in user_lower for w in ["message", "text", "name on cake", "writing", "note"]):
            if "custom_message" not in extracted or not AiService.is_valid_field_value("custom_message", extracted.get("custom_message")):
                return True, "custom_message", "Sure! What new message or name would you like written on the cake?"

        # 6. Budget
        if any(w in user_lower for w in ["budget", "price", "cost", "inr", "rupees"]):
            if "budget_inr" not in extracted or not AiService.is_valid_field_value("budget_inr", extracted.get("budget_inr")):
                return True, "budget_inr", "Sure! What is your updated budget in rupees?"

        # 7. General ambiguous change without naming a specific field (e.g. "I want to change something", "Can I change that?")
        # Only triggers if no valid field was extracted in this turn
        if not extracted:
            return True, None, "Of course! Which detail would you like to update — the flavor, weight, date, or delivery preference?"

        return False, None, None

    @staticmethod
    def handle_missing_field_response(
        field: str,
        customer_response: str,
        conversation_state: dict
    ) -> dict:
        """
        Handles the customer response to a requested missing field.
        1. Understands the field being asked.
        2. Analyzes the customer's response.
        3. Extracts a valid value if present.
        4. Detects ambiguity.
        5. Tracks attempts.
        6. Rephrases question with explicit options instead of repeating.
        7. Escalates after maximum attempts (offers human/team assistance).
        8. Preserves all previously collected information.
        """
        MAX_FIELD_ATTEMPTS = 3
        text_clean = (customer_response or "").strip().lower()

        # Retrieve or initialize field_status structure
        field_status = conversation_state.setdefault("field_status", {})
        f_info = field_status.setdefault(field, {
            "value": None,
            "status": "missing",
            "attempts": 0
        })

        # Check for newly provided cake message / custom request
        msg_on_cake = None
        cake_msg_match = re.search(r'(?:write|message|text|says|name on cake|note)\s*[\'"]?([^\'"]+?)[\'"]?(?=\s+on|\s+for|\s+$)', text_clean)
        if not cake_msg_match:
            cake_msg_match = re.search(r'write\s+([a-zA-Z0-9\s]+?)\s+on\s+(?:the\s+)?cake', text_clean)
        if cake_msg_match:
            msg_on_cake = cake_msg_match.group(1).strip().title()
            conversation_state["message_on_cake"] = msg_on_cake
            conversation_state["custom_message"] = msg_on_cake

        # 1. Attempt extracting valid value for target field
        extracted_val = None
        if field == "delivery_preference":
            has_del = bool(re.search(r'\b(home delivery|delivery|deliver(?:ed|y)? to (?:my )?(?:home|house|address)|deliver it|delivery please|home please|send to home|deliver)\b', text_clean))
            has_pick = bool(re.search(r'\b(store pickup|pickup|pick up|takeaway|collect|from (?:the )?store|pick it up|baker|shop)\b', text_clean))
            if has_del and not has_pick:
                extracted_val = "Home Delivery"
            elif has_pick and not has_del:
                extracted_val = "Store Pickup"

        elif field == "weight_kg":
            kn_w_map = {"ಅರ್ಧ": "0.5", "ಒಂದುವರೆ": "1.5", "ಒಂದು": "1", "ಎರಡು": "2", "ಮೂರು": "3", "ನಾಲ್ಕು": "4", "ಐದು": "5", "ondu": "1", "eradu": "2", "mooru": "3", "naalku": "4", "aidu": "5", "ardha": "0.5"}
            hi_w_map = {"आधा": "0.5", "एक": "1", "दो": "2", "तीन": "3", "चार": "4", "पांच": "5", "डेढ़": "1.5", "ढाई": "2.5", "aadha": "0.5", "ek": "1", "do": "2", "teen": "3", "char": "4", "paanch": "5", "dedh": "1.5", "dhai": "2.5"}
            for k_w, k_n in kn_w_map.items():
                if k_w in text_clean:
                    extracted_val = k_n
                    break
            if not extracted_val:
                for h_w, h_n in hi_w_map.items():
                    if h_w in text_clean:
                        extracted_val = h_n
                        break
            if not extracted_val:
                w_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:kg|kilo|kilos|pound|lb|gm|gram|grams|ಕೆಜಿ|ಕೇಜಿ|किलो)?', text_clean)
                if w_match:
                    try:
                        v_num = float(w_match.group(1))
                        if v_num > 0:
                            if "gm" in text_clean or "gram" in text_clean:
                                extracted_val = str(v_num / 1000.0) if v_num >= 100 else str(v_num)
                            else:
                                extracted_val = str(w_match.group(1))
                    except Exception:
                        pass

        elif field == "cake_flavor":
            f_match = re.search(r'\b(dark chocolate|chocolate|red velvet|vanilla|mango|black forest|pineapple|butterscotch|strawberry|choco chip|fruit|truffle|blueberry|butter scotch)\b', text_clean)
            if f_match:
                extracted_val = f_match.group(1).title()
            elif len(text_clean) >= 3 and text_clean not in AiService.AMBIGUOUS_WORDS and text_clean not in ["cake", "sweet", "good", "normal", "best", "regular"]:
                extracted_val = customer_response.strip().title()

        elif field == "required_date":
            has_date = any(w in text_clean for w in ["today", "tomorrow", "day after", "naale", "kal", "parso", "sanje", "evening", "morning", "pm", "am"])
            if has_date and not any(w in text_clean for w in ["anytime", "any time", "later", "whenever", "soon"]):
                d_str = "tomorrow" if ("tomorrow" in text_clean or "naale" in text_clean or "kal" in text_clean) else ("day after tomorrow" if ("day after" in text_clean or "parso" in text_clean) else "today")
                t_str = "18:00"
                for tm in re.finditer(r'(\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)?)', text_clean, re.I):
                    after_str = text_clean[tm.end():tm.end()+6]
                    if not re.match(r'^\s*(?:kg|kilo|pound|lb)', after_str):
                        t_str = tm.group(1)
                        break
                target_dt = CalendarService.parse_datetime_input(d_str, t_str)
                extracted_val = target_dt.isoformat()

        elif field == "custom_message":
            if any(w in text_clean for w in ["no message", "no text", "no writing", "no name", "nothing", "none", "no", "na", "n/a", "not required", "without message"]):
                extracted_val = "None"
            elif cake_msg_match:
                extracted_val = cake_msg_match.group(1).strip().title()
            elif len(customer_response.strip()) >= 2 and text_clean not in AiService.AMBIGUOUS_WORDS:
                extracted_val = customer_response.strip().title()

        elif field == "budget_inr":
            b_dig = re.search(r'(\d+)', text_clean)
            if b_dig:
                extracted_val = b_dig.group(1)
            elif any(w in text_clean for w in ["any", "standard", "normal", "flexible", "regular", "whatever"]):
                extracted_val = "1500"

        elif field == "order_type":
            if any(w in text_clean for w in ["custom", "design"]):
                extracted_val = "Custom Design"
            elif any(w in text_clean for w in ["enquiry", "inquiry"]):
                extracted_val = "General Enquiry"
            else:
                extracted_val = "New Cake Order"

        # 2. Check if extracted value is valid
        if extracted_val and AiService.is_valid_field_value(field, extracted_val):
            f_info["value"] = extracted_val
            f_info["status"] = "answered"
            conversation_state[field] = extracted_val
            return {
                "field": field,
                "status": "answered",
                "value": extracted_val,
                "next_question": None,
                "field_status": field_status
            }

        # 3. Value is NOT valid; check for ambiguity vs completely missing
        is_ambiguous = (
            text_clean in AiService.AMBIGUOUS_WORDS or
            bool(re.search(r"^(?:yes|yeah|yep|sure|fine|ok|okay|that'?s fine|thats fine|all good|sounds good|no problem|alright|right|yes please|please|either|both)\.?$", text_clean)) or
            ("fine" in text_clean and not extracted_val)
        )

        f_info["attempts"] += 1
        attempt = f_info["attempts"]

        if is_ambiguous:
            f_info["status"] = "ambiguous"
        else:
            f_info["status"] = "missing"

        # 4. Generate progressive, non-repeating question based on attempts
        prefix = f"Absolutely, I'll note '{msg_on_cake}' on the cake. " if msg_on_cake else ""

        if attempt >= MAX_FIELD_ATTEMPTS:
            # Escalate after MAX attempts: Offer human assistance
            if field == "delivery_preference":
                q = f"{prefix}I understand! Would you prefer our bakery team to call you back to confirm delivery or pickup, or would you like to choose between Home Delivery or Store Pickup now?"
            elif field == "cake_flavor":
                q = f"{prefix}No problem! Would you like our head baker to call you with flavor recommendations, or would you like to pick a flavor now?"
            elif field == "weight_kg":
                q = f"{prefix}Would you like our bakery team to give you a quick callback to assist with portion sizes and weight, or should we set a specific weight now?"
            elif field == "required_date":
                q = f"{prefix}Would you like our team to check our baking schedule and give you a call to confirm the timing, or do you have a specific date and time in mind?"
            elif field == "custom_message":
                q = f"{prefix}Would you like us to note that no custom message is needed, or should our team confirm this on a callback?"
            elif field == "budget_inr":
                q = f"{prefix}Would you like our team to call you back with our pricing tiers and budget options?"
            else:
                q = f"{prefix}Would you like a member of our team to call you back to help finalize this detail?"
        elif is_ambiguous:
            # Ambiguous: give explicit choice
            if field == "delivery_preference":
                q = f"{prefix}Sure! Please choose one: **home delivery or pickup**?"
            elif field == "cake_flavor":
                q = f"{prefix}Sure! Just to confirm, which cake flavor would you prefer?"
            elif field == "weight_kg":
                q = f"{prefix}Sure! Just to confirm, how many kilograms would you like the cake to be?"
            elif field == "required_date":
                q = f"{prefix}Sure! Just to confirm, what exact date and time would you like the cake?"
            elif field == "custom_message":
                q = f"{prefix}Could you please clarify what specific text or name you would like inscribed on the cake?"
            elif field == "budget_inr":
                q = f"{prefix}Could you please share your approximate budget in rupees, for example 1500 or 2500?"
            else:
                q = f"{prefix}Could you please clarify your preference for this detail?"
        elif attempt == 2:
            # Rephrase clearly
            if field == "delivery_preference":
                q = f"{prefix}To make sure your cake reaches you smoothly, please let me know whether you'd prefer home delivery to your address, or store pickup from our bakery?"
            elif field == "cake_flavor":
                q = f"{prefix}We offer popular flavors including Belgian Dark Chocolate, Red Velvet, Vanilla Mango, and Black Forest. Which flavor would you like?"
            elif field == "weight_kg":
                q = f"{prefix}Could you please specify the cake weight in kilograms, for example 1 kg, 1.5 kg, or 2 kg?"
            elif field == "required_date":
                q = f"{prefix}Could you please provide the exact date and time you need the cake, for example tomorrow at 5 PM?"
            elif field == "custom_message":
                q = f"{prefix}What inscription or greeting would you like written on top of the cake?"
            elif field == "budget_inr":
                q = f"{prefix}What budget range in INR are you planning for this cake?"
            else:
                q = f"{prefix}Could you please clarify your preference for {field}?"
        else:
            # Normal question
            if field == "delivery_preference":
                q = f"{prefix}Would you like the cake delivered to your home or would you prefer to pick it up?"
            elif field == "cake_flavor":
                q = f"{prefix}What cake flavor are you thinking of?"
            elif field == "weight_kg":
                q = f"{prefix}What weight or size would you like for the cake in kilograms?"
            elif field == "required_date":
                q = f"{prefix}For which date and time do you need the cake ready?"
            elif field == "custom_message":
                q = f"{prefix}What message or name would you like written on the cake?"
            elif field == "budget_inr":
                q = f"{prefix}What is your approximate budget for the cake in rupees?"
            else:
                q = f"{prefix}Could you please share your preference for {field}?"

        return {
            "field": field,
            "status": f_info["status"],
            "value": None,
            "attempts": attempt,
            "next_question": q,
            "field_status": field_status
        }

    @staticmethod
    def process_conversation(request_data: dict):
        business_id = request_data.get("business_id")
        workflow_id = request_data.get("workflow_id")

        caller_name = request_data.get("caller_name") or "Customer"
        caller_phone = request_data.get("caller_phone") or "+91 98765 43210"
        messages = request_data.get("messages", [])
        language_option = request_data.get("language", "auto")

        with get_db_connection() as conn:
            biz_row = conn.execute(text("SELECT * FROM businesses WHERE id = :id"), {"id": business_id}).fetchone()
            wf_row = conn.execute(text("SELECT * FROM workflows WHERE id = :id"), {"id": workflow_id}).fetchone()

        if not biz_row or not wf_row:
            raise ValueError(f"Business ({business_id}) or Workflow ({workflow_id}) not found.")

        business = dict(biz_row._mapping)
        workflow = dict(wf_row._mapping)
        industry = (workflow.get("industry") or business.get("industry") or "").lower()
        is_cake_shop = ("cake" in industry or "bakery" in industry or workflow.get("id") == "wf-cake-01")
        is_logistics = ("logistics" in industry or "delivery" in industry or workflow.get("id") == "wf-logistics-01")

        if DeliveryWorkflowService.handles(workflow_id) or "logistics" in industry or "delivery" in industry:
            return DeliveryWorkflowService.process_conversation(request_data)

        if CakeWorkflowService.handles(workflow_id) or is_cake_shop:
            return CakeWorkflowService.process_conversation(request_data)

        fields = json.loads(workflow["fields"] or "[]")
        conditions = json.loads(workflow["conditions"] or "[]")

        # Extract current and previous user messages for language detection & dynamic switching
        user_messages = [m["content"] for m in messages if m.get("role") == "user"]
        last_user_msg = user_messages[-1] if user_messages else ""
        prev_user_msg = user_messages[-2] if len(user_messages) >= 2 else ""

        current_detected = AiService.detect_language(last_user_msg)
        prev_detected = AiService.detect_language(prev_user_msg) if prev_user_msg else "en"

        # Determine target language
        detected_lang = language_option if language_option != "auto" else current_detected

        executed_tools = []
        user_lower = last_user_msg.lower()

        # Check for Natural Language Switching (Bonus Requirement)
        language_switched = False
        if language_option == "auto" and prev_user_msg and current_detected != prev_detected:
            language_switched = True
            executed_tools.append({
                "tool": "language_switch_detected",
                "args": {"from": prev_detected.upper(), "to": current_detected.upper()},
                "result": f"Natural language switch detected: {prev_detected.upper()} -> {current_detected.upper()}"
            })

        # Check Business Hours & Service Availability Timings
        b_hours = None
        if workflow.get("business_hours"):
            try:
                b_hours = json.loads(workflow["business_hours"]) if isinstance(workflow["business_hours"], str) else workflow["business_hours"]
            except Exception:
                b_hours = None

        is_after_hours = False
        if b_hours and b_hours.get("enabled"):
            # Calculate current time in IST (UTC+5:30) or system timezone
            now_utc = datetime.now(timezone.utc)
            ist_tz = timezone(timedelta(hours=5, minutes=30))
            now_local = now_utc.astimezone(ist_tz)

            current_day = now_local.strftime("%a") # e.g. "Fri"
            current_day_full = now_local.strftime("%A") # e.g. "Friday"
            current_minutes = now_local.hour * 60 + now_local.minute

            days_open_raw = b_hours.get("days", ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"])
            days_open = [d[:3].capitalize() for d in days_open_raw] + [d.capitalize() for d in days_open_raw]

            def time_to_mins(t_str: str) -> int:
                if not t_str:
                    return 9 * 60
                t_str = str(t_str).strip().lower()
                m12 = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)?', t_str)
                if m12:
                    h = int(m12.group(1))
                    m = int(m12.group(2) or 0)
                    ampm = m12.group(3)
                    if ampm == "pm" and h < 12:
                        h += 12
                    elif ampm == "am" and h == 12:
                        h = 0
                    return h * 60 + m
                if ":" in t_str:
                    parts = t_str.split(":")
                    try:
                        return int(parts[0]) * 60 + int(parts[1][:2])
                    except ValueError:
                        pass
                return 9 * 60

            start_t_str = b_hours.get("start_time", "09:00")
            end_t_str = b_hours.get("end_time", "18:00")

            start_mins = time_to_mins(start_t_str)
            end_mins = time_to_mins(end_t_str)

            is_open_day = (current_day in days_open or current_day_full in days_open)
            is_open_time = (start_mins <= current_minutes <= end_mins)

            if not is_open_day or not is_open_time:
                is_after_hours = True
                curr_display = now_local.strftime("%a %I:%M %p")
                executed_tools.append({
                    "tool": "evaluate_business_hours",
                    "args": {"current_time": curr_display, "schedule": f"{','.join(days_open_raw)} {start_t_str}-{end_t_str}"},
                    "result": f"Notice: Call received OUTSIDE business hours ({curr_display}). After-hours service response triggered."
                })

        rec_id = request_data.get("record_id") or f"rec-{str(uuid.uuid4())[:8]}"
        collected_data_dict = {}

        # 1. Load any previously collected fields for this call record
        if request_data.get("record_id"):
            try:
                with get_db_connection() as conn:
                    existing_rec = conn.execute(
                        text("SELECT collected_data FROM records WHERE id = :id"),
                        {"id": request_data["record_id"]}
                    ).fetchone()
                    if existing_rec and existing_rec[0]:
                        loaded = json.loads(existing_rec[0]) if isinstance(existing_rec[0], str) else existing_rec[0]
                        if isinstance(loaded, dict):
                            collected_data_dict = loaded
            except Exception as e:
                print(f"[Record Load Notice] {e}")

        # 2. Extract newly mentioned fields and analyze corrections using LangChain
        current_question_field = collected_data_dict.get("current_question_field") or collected_data_dict.get("_last_asked_field")
        groq_api_key = os.getenv("GROQ_API_KEY")

        lc_analysis = LangChainService.analyze_and_correct_turn(
            workflow=workflow,
            business=business,
            fields=fields,
            collected_data=collected_data_dict,
            current_question_field=current_question_field,
            messages=messages,
            language=detected_lang,
            caller_name=caller_name,
            caller_phone=caller_phone,
            is_after_hours=is_after_hours
        )

        extracted_new = AiService.extract_workflow_fields(fields, messages, collected_data_dict, groq_api_key, current_question_field=current_question_field)

        # Merge LangChain corrections into database fields
        updated_fields = {}
        if lc_analysis and lc_analysis.corrections:
            for corr in lc_analysis.corrections:
                k = corr.field_key
                v = corr.new_value
                old_v = corr.old_value or collected_data_dict.get(k)
                if old_v != v:
                    updated_fields[k] = {"old": old_v, "new": v}
                collected_data_dict[k] = v
                extracted_new[k] = v

        if lc_analysis and lc_analysis.new_extracted_fields:
            for k, v in lc_analysis.new_extracted_fields.items():
                if k not in extracted_new:
                    extracted_new[k] = v

        user_texts = [m["content"] for m in messages if m.get("role") == "user"]
        last_user_raw = user_texts[-1] if user_texts else ""

        # Check for ambiguous correction when caller signals intent to change/correct without a valid new value
        is_ambig_corr, ambig_target_field, ambig_clarif_q = AiService.detect_ambiguous_correction(
            last_user_raw, fields, collected_data_dict, extracted_new
        )

        for k, v in extracted_new.items():
            if AiService.is_valid_field_value(k, v) or k in ["custom_message", "message_on_cake", "order_type", "budget_inr"]:
                # If field already exists with a different value, track as an update/correction
                if k in collected_data_dict and collected_data_dict[k] != v and k not in updated_fields:
                    updated_fields[k] = {"old": collected_data_dict[k], "new": v}
                collected_data_dict[k] = v

        # Maintain field_status structure for all workflow fields
        field_status = collected_data_dict.setdefault("field_status", {})
        for f in fields:
            f_k = f["key"]
            if f_k not in field_status:
                field_status[f_k] = {
                    "value": collected_data_dict.get(f_k),
                    "status": "answered" if AiService.is_valid_field_value(f_k, collected_data_dict.get(f_k)) else "missing",
                    "attempts": 0
                }
            else:
                if AiService.is_valid_field_value(f_k, collected_data_dict.get(f_k)):
                    field_status[f_k]["value"] = collected_data_dict.get(f_k)
                    field_status[f_k]["status"] = "answered"
                    if f_k in updated_fields:
                        field_status[f_k]["attempts"] = 0

        next_guided_question = None

        if is_ambig_corr:
            # Ambiguous correction: ask for clarification only! Preserve all valid fields.
            executed_tools.append({
                "tool": "request_correction_clarification",
                "args": {"target_field": ambig_target_field, "caller_statement": last_user_raw},
                "result": f"Ambiguous correction detected. Asking clarification: {ambig_clarif_q}"
            })
            if ambig_target_field and ambig_target_field in field_status:
                field_status[ambig_target_field]["status"] = "ambiguous"
                collected_data_dict["current_question_field"] = ambig_target_field
                collected_data_dict["_last_asked_field"] = ambig_target_field
            next_guided_question = ambig_clarif_q

        elif updated_fields:
            for u_k, u_v in updated_fields.items():
                executed_tools.append({
                    "tool": "update_database_field",
                    "args": {"field": u_k, "old_value": u_v["old"], "new_value": u_v["new"]},
                    "result": f"Field '{u_k}' updated from '{u_v['old']}' to '{u_v['new']}'. All other collected fields preserved."
                })

        elif extracted_new:
            executed_tools.append({
                "tool": "extract_database_fields",
                "args": {"extracted_count": len(extracted_new), "fields": list(extracted_new.keys())},
                "result": f"Extracted database fields from caller: {json.dumps(extracted_new)}"
            })

        # If previous turn asked a field, and current turn was NOT an ambiguous correction or correction of another field
        if not is_ambig_corr and not updated_fields and current_question_field and current_question_field in field_status:
            handler_res = AiService.handle_missing_field_response(
                field=current_question_field,
                customer_response=last_user_raw,
                conversation_state=collected_data_dict
            )
            field_status = handler_res.get("field_status", field_status)
            if handler_res.get("status") != "answered":
                next_guided_question = handler_res.get("next_question")

        # 3. Determine missing required fields using the reusable missing fields handler
        missing_keys = AiService.get_missing_required_fields(workflow, fields, collected_data_dict)
        # Find matching field dicts for labels
        field_dict_by_key = {f["key"]: f for f in fields}
        missing_required = [field_dict_by_key[k] for k in missing_keys if k in field_dict_by_key]
        is_complete = (len(missing_keys) == 0)

        # Check if caller explicitly signals that they want to confirm the order or conclude the call
        last_user_lower = last_user_raw.lower().strip()
        user_wants_to_confirm = any(phrase in last_user_lower for phrase in [
            "confirm", "confirm order", "confirm my order", "please confirm", "confirm it",
            "confirm in calendar", "book it", "book order", "schedule it", "schedule in calendar",
            "yes confirm", "place order", "finalize", "book appointment", "book the slot",
            "kharcha chalega", "theek hai confirm", "haan confirm", "confirm madi", "calender", "calendar"
        ])
        user_wants_to_end = any(phrase in last_user_lower for phrase in [
            "bye", "goodbye", "good bye", "that's all", "thats all", "that is all",
            "nothing else", "no that's all", "no thats all", "end call", "hang up",
            "thank you bye", "thanks bye", "dhanyawad", "shukriya", "alvida",
            "bas itna hi", "saku", "mugithu"
        ])
        if user_wants_to_confirm or (user_wants_to_end and not is_complete):
            if is_cake_shop or "cake" in (workflow.get("industry") or "").lower() or workflow.get("id") == "wf-cake-01":
                collected_data_dict["order_type"] = "New Cake Order"
            if not collected_data_dict.get("custom_message"):
                collected_data_dict["custom_message"] = "None"
            if not collected_data_dict.get("budget_inr"):
                collected_data_dict["budget_inr"] = "1500"
            if not collected_data_dict.get("delivery_preference"):
                collected_data_dict["delivery_preference"] = "Store Pickup"
            if not collected_data_dict.get("cake_flavor"):
                collected_data_dict["cake_flavor"] = "Belgian Dark Chocolate"
            if not collected_data_dict.get("weight_kg"):
                collected_data_dict["weight_kg"] = "1"
            if not collected_data_dict.get("required_date"):
                target_default_dt = (datetime.now() + timedelta(days=1)).replace(hour=17, minute=0, second=0, microsecond=0)
                collected_data_dict["required_date"] = target_default_dt.isoformat()

            missing_keys = []
            missing_required = []
            is_complete = True
            next_guided_question = None

        # Determine next field to ask
        next_field_to_ask = missing_keys[0] if missing_keys else None
        if not is_ambig_corr:
            collected_data_dict["current_question_field"] = next_field_to_ask
            collected_data_dict["_last_asked_field"] = next_field_to_ask

        # If the newly chosen next_field_to_ask hasn't been handled this turn, get its question
        if not is_complete and not next_guided_question and next_field_to_ask:
            target_f_info = field_status.setdefault(next_field_to_ask, {
                "value": None,
                "status": "missing",
                "attempts": 0
            })
            if target_f_info["status"] == "missing" and target_f_info["attempts"] == 0:
                target_f_info["status"] = "asked"
            # Generate appropriate question for this field
            handler_init = AiService.handle_missing_field_response(
                field=next_field_to_ask,
                customer_response="",
                conversation_state=collected_data_dict
            )
            next_guided_question = handler_init.get("next_question")

        if missing_required:
            executed_tools.append({
                "tool": "check_database_required_fields",
                "args": {
                    "collected_fields": [k for k in collected_data_dict.keys() if not k.startswith("_")],
                    "missing_required_fields": [f["label"] for f in missing_required]
                },
                "result": f"Awaiting {len(missing_required)} required field(s): {', '.join(f['label'] for f in missing_required)}"
            })

        # 4. Evaluate conditional rules & urgency
        urgency = "Normal"
        full_user_text = " ".join([m["content"] for m in messages if m.get("role") == "user"])
        full_user_lower = full_user_text.lower()
        for cond in conditions:
            if cond.get("field") in ["required_date", "preferred_time"] and cond.get("operator") in ["within_hours", "exists"]:
                req_d = str(collected_data_dict.get("required_date") or "").lower()
                if any(k in req_d or k in full_user_lower for k in ["tomorrow", "today", "24 hour", "urgent", "naale", "kal", "jaldi"]):
                    urgency = "Urgent"
                    executed_tools.append({
                        "tool": "evaluate_conditional_rule",
                        "args": {"condition": cond.get("note", "Target date within 24 hours")},
                        "result": "Rule Triggered: Flagged as URGENT"
                    })
            if cond.get("field") == "urgency_level" and ("emergency" in full_user_lower or "turtu" in full_user_lower or "zaruri" in full_user_lower):
                urgency = "Critical"
                executed_tools.append({
                    "tool": "evaluate_conditional_rule",
                    "args": {"condition": "Immediate Emergency"},
                    "result": "Rule Triggered: Flagged as CRITICAL"
                })

        # Calendar AI Agent: Real-time availability check for Cake Shop when required_date is known
        if is_cake_shop and collected_data_dict.get("required_date") and not collected_data_dict.get("_calendar_checked"):
            req_d = str(collected_data_dict.get("required_date"))
            avail = CalendarService.check_availability(req_d, "17:00", duration_minutes=30, business_id=business_id)
            executed_tools.append({
                "tool": "check_calendar_availability",
                "args": {"requested_time": req_d, "business_id": business_id},
                "result": avail
            })
            collected_data_dict["_calendar_checked"] = True

        # Calendar AI Agent: Voice-driven reschedule / cancellation for Cake Shop
        if is_cake_shop:
            if any(w in full_user_lower for w in ["cancel my cake", "cancel the cake", "cancel my order", "cancel order"]):
                cancel_res = CalendarService.cancel_event(business_id=business_id)
                executed_tools.append({
                    "tool": "cancel_calendar_event",
                    "args": {"business_id": business_id},
                    "result": cancel_res
                })
                collected_data_dict["calendar_cancellation"] = cancel_res
            elif any(w in full_user_lower for w in ["reschedule my cake", "reschedule the cake", "postpone cake", "change cake time", "postpone delivery", "reschedule order"]):
                target_dt = CalendarService.parse_datetime_input(full_user_lower, "17:00")
                update_res = CalendarService.update_event(
                    business_id=business_id,
                    new_start_time=target_dt.isoformat()
                )
                executed_tools.append({
                    "tool": "update_calendar_event",
                    "args": {"new_start_time": target_dt.isoformat(), "business_id": business_id},
                    "result": update_res
                })
                collected_data_dict["calendar_reschedule"] = update_res

        # 5. Domain Completion Actions (Triggered when all required fields have been collected, and synced when fields are updated)
        if is_complete:
            if is_cake_shop:
                flavor = collected_data_dict.get("cake_flavor", "Belgian Dark Chocolate")
                weight = str(collected_data_dict.get("weight_kg", "1"))
                order_type = collected_data_dict.get("order_type", "New Cake Order")
                req_date = collected_data_dict.get("required_date") or (datetime.now() + timedelta(days=1)).replace(hour=17, minute=0, second=0).isoformat()
                delivery_pref = collected_data_dict.get("delivery_preference", "Store Pickup")
                custom_msg = collected_data_dict.get("custom_message") or collected_data_dict.get("message_on_cake") or "None"
                budget = str(collected_data_dict.get("budget_inr", "1500"))
                cake_type = "Theme Custom Cake"
                if "birthday" in full_user_lower:
                    cake_type = "Birthday Cake"
                elif "anniversary" in full_user_lower:
                    cake_type = "Anniversary Cake"

                enq_id = collected_data_dict.get("order_enquiry", {}).get("enquiry_id") if isinstance(collected_data_dict.get("order_enquiry"), dict) else None
                if not enq_id:
                    enq_id = f"ENQ-{str(uuid.uuid4())[:6].upper()}"

                if not collected_data_dict.get("_order_enquiry_triggered"):
                    enquiry_tool_res = {
                        "success": True,
                        "enquiry_id": enq_id,
                        "order_type": order_type,
                        "cake_type": cake_type,
                        "flavor": flavor,
                        "weight_kg": weight,
                        "required_date": req_date,
                        "custom_message": custom_msg or "None",
                        "delivery_preference": delivery_pref,
                        "budget_inr": budget
                    }
                    executed_tools.append({
                        "tool": "create_order_enquiry",
                        "args": {"enquiry_id": enq_id, "cake_type": cake_type, "flavor": flavor, "weight": f"{weight}kg"},
                        "result": enquiry_tool_res
                    })
                    collected_data_dict["order_enquiry"] = enquiry_tool_res
                    collected_data_dict["_order_enquiry_triggered"] = True

                    owner_summary = ExternalApiService.send_owner_summary_alert(
                        business_name=business['name'],
                        owner_name=business.get('owner_name', 'Ananya Sharma'),
                        caller_name=caller_name,
                        caller_phone=caller_phone,
                        order_type=order_type,
                        cake_type=cake_type,
                        flavor=flavor,
                        weight=weight,
                        required_date=req_date,
                        custom_message=custom_msg,
                        delivery_pref=delivery_pref,
                        budget_inr=budget
                    )
                    executed_tools.append({
                        "tool": "send_owner_summary_alert",
                        "args": {"recipient": business.get('owner_name', 'Ananya Sharma'), "alert_id": owner_summary.get("alert_id")},
                        "result": owner_summary
                    })
                    collected_data_dict["owner_structured_summary"] = owner_summary.get("formatted_summary")

                    # Calendar AI Agent: Automatically schedule cake baking & delivery/pickup slot
                    target_dt = CalendarService.parse_datetime_input(req_date, "17:00")
                    start_iso = target_dt.isoformat()
                    end_iso = (target_dt + timedelta(minutes=30)).isoformat()
                    cake_cal_title = f"Cake Order ({flavor} - {weight}kg) - {caller_name}"
                    cake_cal_res = CalendarService.create_event(
                        business_id=business_id,
                        title=cake_cal_title,
                        start_time=start_iso,
                        end_time=end_iso,
                        attendee_name=caller_name,
                        attendee_phone=caller_phone,
                        description=f"Sweet Treats Bakery [{enq_id}]: {cake_type} ({flavor}, {weight}kg). {delivery_pref} at ₹{budget}. Message: '{custom_msg or 'None'}'. Caller: {caller_name} ({caller_phone})"
                    )
                    executed_tools.append({
                        "tool": "create_calendar_event",
                        "args": {"title": cake_cal_title, "start_time": start_iso, "delivery_preference": delivery_pref},
                        "result": cake_cal_res
                    })
                    collected_data_dict["calendar_event"] = cake_cal_res

                elif updated_fields:
                    # Dynamically update order enquiry and alerts with corrected values - never lock!
                    enq = collected_data_dict.get("order_enquiry") or {}
                    enq["flavor"] = flavor
                    enq["weight_kg"] = weight
                    enq["required_date"] = req_date
                    enq["custom_message"] = custom_msg or "None"
                    enq["delivery_preference"] = delivery_pref
                    enq["budget_inr"] = budget
                    collected_data_dict["order_enquiry"] = enq
                    executed_tools.append({
                        "tool": "update_order_enquiry",
                        "args": {"enquiry_id": enq.get("enquiry_id"), "updated_fields": list(updated_fields.keys())},
                        "result": enq
                    })
                    owner_summary = ExternalApiService.send_owner_summary_alert(
                        business_name=business['name'],
                        owner_name=business.get('owner_name', 'Ananya Sharma'),
                        caller_name=caller_name,
                        caller_phone=caller_phone,
                        order_type=order_type,
                        cake_type=cake_type,
                        flavor=flavor,
                        weight=weight,
                        required_date=req_date,
                        custom_message=custom_msg,
                        delivery_pref=delivery_pref,
                        budget_inr=budget
                    )
                    collected_data_dict["owner_structured_summary"] = owner_summary.get("formatted_summary")

                    # Update existing calendar event
                    target_dt = CalendarService.parse_datetime_input(req_date, "17:00")
                    start_iso = target_dt.isoformat()
                    end_iso = (target_dt + timedelta(minutes=30)).isoformat()
                    cake_cal_title = f"Cake Order ({flavor} - {weight}kg) - {caller_name}"
                    cal_evt_id = collected_data_dict.get("calendar_event", {}).get("event_id") if isinstance(collected_data_dict.get("calendar_event"), dict) else None
                    cake_cal_res = CalendarService.update_event(
                        event_id=cal_evt_id or "latest",
                        business_id=business_id,
                        title=cake_cal_title,
                        new_start_time=start_iso,
                        new_end_time=end_iso,
                        attendee_name=caller_name,
                        attendee_phone=caller_phone,
                        description=f"Sweet Treats Bakery [{enq_id}]: {cake_type} ({flavor}, {weight}kg). {delivery_pref} at ₹{budget}. Message: '{custom_msg or 'None'}'. Caller: {caller_name} ({caller_phone})"
                    )
                    executed_tools.append({
                        "tool": "update_calendar_event",
                        "args": {"title": cake_cal_title, "start_time": start_iso, "delivery_preference": delivery_pref},
                        "result": cake_cal_res
                    })
                    collected_data_dict["calendar_event"] = cake_cal_res

            elif is_logistics:
                trk_no = collected_data_dict.get("tracking_number") or "TRK-9821-IN"
                inq_type = collected_data_dict.get("inquiry_type", "Package Status")

                if any(k in full_user_lower for k in ["help", "support", "issue", "callback", "delayed", "complaint", "agent"]):
                    cb_res = ExternalApiService.create_callback_task(
                        issue_summary=f"Customer requested agent callback/support (Tracking #{trk_no})",
                        tracking_number=trk_no,
                        caller_name=caller_name,
                        caller_phone=caller_phone
                    )
                    executed_tools.append({
                        "tool": "create_callback_task",
                        "args": {"issue": "Delivery Support Callback", "tracking_number": trk_no},
                        "result": cb_res
                    })
                    collected_data_dict["service_option"] = "Help with Existing Delivery"
                    collected_data_dict["callback_task"] = cb_res
                else:
                    tracking_res = ExternalApiService.track_delivery_status(trk_no)
                    executed_tools.append({
                        "tool": "track_delivery_status",
                        "args": {"tracking_number": trk_no},
                        "result": tracking_res
                    })
                    collected_data_dict["service_option"] = "Package Status Update"
                    collected_data_dict["delivery_status"] = tracking_res.get("status")
                    collected_data_dict["current_location"] = tracking_res.get("current_location")

            else:
                # Calendar Appointment Workflow
                date_match = "tomorrow" if ("tomorrow" in user_lower or "naale" in user_lower or "kal" in user_lower) else ("day after tomorrow" if ("day after" in user_lower or "parso" in user_lower) else "today")
                time_match = "16:00"
                for m in re.finditer(r'(\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)?)', user_lower, re.IGNORECASE):
                    time_match = m.group(1)
                    break
                target_dt = CalendarService.parse_datetime_input(date_match, time_match)
                start_iso = target_dt.isoformat()
                end_iso = (target_dt + timedelta(minutes=30)).isoformat()
                evt_title = f"{workflow['industry']} Appointment - {caller_name}"
                create_res = CalendarService.create_event(
                    business_id=business_id,
                    title=evt_title,
                    start_time=start_iso,
                    end_time=end_iso,
                    attendee_name=caller_name,
                    attendee_phone=caller_phone,
                    description=f"Scheduled via Voice AI ({workflow['name']})"
                )
                executed_tools.append({
                    "tool": "create_calendar_event",
                    "args": {"title": evt_title, "start_time": start_iso},
                    "result": create_res
                })
                collected_data_dict["appointment"] = {
                    "event_id": create_res.get("event_id"),
                    "title": evt_title,
                    "start_time": start_iso,
                    "status": "Confirmed"
                }

        # 6. Response Generation (Progressive Question Asking vs Completion Confirmation)
        reply = None
        switch_prefix = ""
        if language_switched:
            lang_names = {"en": "English", "hi": "Hindi (हिन्दी)", "kn": "Kannada (ಕನ್ನಡ)"}
            switch_prefix = f"*(Language switched to {lang_names.get(detected_lang, 'English')})* "

        # LangChain Correction Response: When caller corrected a field, use LangChain's natural response that updates state and never repeats the question
        if lc_analysis and lc_analysis.natural_spoken_reply and (updated_fields or lc_analysis.is_correction) and not is_ambig_corr:
            reply = f"{switch_prefix}{lc_analysis.natural_spoken_reply}"
            executed_tools.append({
                "tool": "langchain_conversational_correction",
                "args": {"updated_fields": list(updated_fields.keys()), "next_field": lc_analysis.next_field_to_ask},
                "result": f"LangChain synthesized natural correction response without repeating question: '{reply}'"
            })

        if not reply and groq_api_key:
            try:
                tools_summary = json.dumps(executed_tools) if executed_tools else "None"
                after_hours_note = f"CLOSED (After-Hours). Call received outside business hours ({b_hours.get('after_hours_greeting', '')}). Process caller request accurately while politely reminding them of operating hours." if (is_after_hours and b_hours) else "OPEN"
                model_name = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

                if not is_complete:
                    # PROGRESSIVE QUESTION PROMPT: Ask for missing required fields (1-2 at a time)
                    next_needed = [f["label"] for f in missing_required[:2]]
                    sys_prompt = (
                        f"You are a warm, polite, and helpful human telephone representative for '{business['name']}' ({workflow['industry']}). "
                        f"Workflow: '{workflow['name']}'. Default Greeting: '{workflow['greeting']}'. "
                        f"Operating Hours Status: {after_hours_note}. "
                        f"Caller Name: '{caller_name}', Phone: '{caller_phone}'. "
                        f"Fields already collected: {json.dumps(collected_data_dict)}. "
                        f"Missing REQUIRED fields to collect: {[f['label'] for f in missing_required]}. "
                        f"Fields recently updated: {json.dumps(updated_fields)}. "
                        f"CRITICAL SPOKEN INSTRUCTIONS: "
                        f"- DYNAMIC CORRECTION: If caller corrected/changed any fields ({json.dumps(updated_fields)}), acknowledge warmly (e.g. 'I have updated the flavor to Vanilla.'). Never permanently lock an extracted field! Never re-ask an already answered field ({json.dumps({k: v for k, v in collected_data_dict.items() if not k.startswith('_')})}). "
                        f"- Preserve all previously collected valid fields. "
                        f"- Acknowledge warmly what the caller just said. "
                        f"- Ask conversationally for the next 1 or 2 missing fields ({next_needed}). Do NOT ask for more than 2 at once. "
                        f"- Speak like a real, caring person on a live telephone call, NEVER sound robotic. "
                        f"- Keep response to 1 or 2 short, natural spoken sentences. "
                        f"- NO markdown symbols, bullet points, asterisks, or robotic phrases. "
                        f"- MUST respond in target language code '{detected_lang.upper()}' (en=English, hi=Hindi/Hinglish, kn=Kannada/Kanglish)."
                    )
                else:
                    # COMPLETION CONFIRMATION PROMPT: Confirm collected details and deliver closing message
                    sys_prompt = (
                        f"You are a warm, friendly human phone representative for '{business['name']}' ({workflow['industry']}). "
                        f"Workflow: '{workflow['name']}'. Closing Message: '{workflow['closing_message']}'. "
                        f"Operating Hours Status: {after_hours_note}. "
                        f"Caller Name: '{caller_name}', Phone: '{caller_phone}'. "
                        f"All required fields successfully collected: {json.dumps(collected_data_dict)}. "
                        f"Executed Tools Data: {tools_summary}. Urgency Level: {urgency}. "
                        f"Fields recently updated: {json.dumps(updated_fields)}. "
                        f"CRITICAL SPOKEN INSTRUCTIONS: "
                        f"- DYNAMIC CORRECTION: If the caller just corrected a field ({json.dumps(updated_fields)}), warmly acknowledge the update (e.g. 'I have updated your cake flavor to Vanilla.'). Never lock fields! "
                        f"- Confirm the customer's request has been successfully registered with their exact choices. "
                        f"- Conclude with a warm goodbye and ask if they need anything else updated. "
                        f"- Speak naturally in 1 to 2 spoken sentences. NO bullet points, NO markdown, NO asterisks. "
                        f"- MUST respond in target language code '{detected_lang.upper()}' (en=English, hi=Hindi/Hinglish, kn=Kannada/Kanglish)."
                    )

                groq_messages = [{"role": "system", "content": sys_prompt}]
                for m in messages[-4:]:
                    groq_messages.append({"role": m.get("role", "user"), "content": m.get("content", "")})

                with httpx.Client(timeout=10.0) as client:
                    resp = client.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers={"Authorization": f"Bearer {groq_api_key}", "Content-Type": "application/json"},
                        json={
                            "model": model_name,
                            "messages": groq_messages,
                            "temperature": 0.3,
                            "max_tokens": 250
                        }
                    )
                    if resp.status_code == 200:
                        groq_data = resp.json()
                        raw_reply = groq_data["choices"][0]["message"]["content"]
                        reply = f"{switch_prefix}{raw_reply}"
                        executed_tools.append({
                            "tool": "groq_llm_inference",
                            "args": {"model": model_name, "mode": "slot_question" if not is_complete else "order_completion"},
                            "result": f"Generated dynamic response in {detected_lang.upper()}"
                        })
            except Exception as e:
                print(f"[Groq LLM Notice] {e}, continuing with local rule engine...")

        # 7. Fallback Response Generator (Multilingual, Progressive Question Asking & Confirmation)
        if not reply:
            if is_ambig_corr and ambig_clarif_q:
                reply = f"{switch_prefix}{ambig_clarif_q}"
            elif updated_fields:
                ack_items = [f"{k.replace('_', ' ')} to {v['new']}" for k, v in updated_fields.items()]
                if detected_lang == 'kn':
                    ack_str = f"Kanditha, naanu {', '.join(ack_items)} update madiddene."
                elif detected_lang == 'hi':
                    ack_str = f"Zaroor, maine {', '.join(ack_items)} update kar diya hai."
                else:
                    ack_str = f"Got it, I have updated the {', '.join(ack_items)}."

                if not is_complete:
                    reply = f"{switch_prefix}{ack_str} {next_guided_question or ''}".strip()
                else:
                    flv = collected_data_dict.get('cake_flavor', 'cake')
                    wt = collected_data_dict.get('weight_kg', '1')
                    dp = collected_data_dict.get('delivery_preference', 'Home Delivery')
                    if detected_lang == 'kn':
                        reply = f"{switch_prefix}{ack_str} Nimma {wt}kg {flv} cake ({dp}) confirm agide. Berenu badalavane madabeka?"
                    elif detected_lang == 'hi':
                        reply = f"{switch_prefix}{ack_str} Aapka {wt}kg {flv} cake ({dp}) confirm ho gaya hai. Kya aap kuch aur badalna chahenge?"
                    else:
                        reply = f"{switch_prefix}{ack_str} Your order for a {wt}kg {flv} cake with {dp} is updated and confirmed. Would you like to make any other changes?"
            elif not is_complete:
                # Progressive Question Asking Fallback
                next_keys = [f["key"] for f in missing_required[:2]]
                if "order_type" in next_keys and len(messages) <= 2:
                    if detected_lang == 'kn':
                        reply = f"{switch_prefix}Namaskara! {business['name']} ge swagatha. Naavu nimma call miss madidve. Yavudhu cake order athava enquiry beku?"
                    elif detected_lang == 'hi':
                        reply = f"{switch_prefix}Namaste! {business['name']} mein aapka swagat hai. Humne aapka missed call dekha. Aapko kis type ka cake order ya enquiry karni hai?"
                    else:
                        reply = f"{switch_prefix}Hello {caller_name}! Thank you for calling {business['name']}. We missed your call. What kind of cake order or enquiry can I help you with today?"
                elif "cake_flavor" in next_keys or "weight_kg" in next_keys:
                    if detected_lang == 'kn':
                        reply = f"{switch_prefix}Kanditha! Nimge yavudhu flavor cake beku, mathu eshtu kg banisabeku?"
                    elif detected_lang == 'hi':
                        reply = f"{switch_prefix}Zaroor! Aapko cake ka kaun sa flavor pasand hai, aur kitne kilo ka banwana chahenge?"
                    else:
                        reply = f"{switch_prefix}I would love to help you with that! What cake flavor are you thinking of, and what weight or size would you like?"
                elif "required_date" in next_keys or "delivery_preference" in next_keys:
                    flv = collected_data_dict.get('cake_flavor', 'cake')
                    if detected_lang == 'kn':
                        reply = f"{switch_prefix}Thumba chennagide! Nimge ee {flv} yavaththu mathu yav samayakke beku, mathu home delivery beka athava store pickup a?"
                    elif detected_lang == 'hi':
                        reply = f"{switch_prefix}Badiya! Yeh {flv} aapko kis din aur samay par chahiye, aur kya aap home delivery chahenge ya store pickup?"
                    else:
                        reply = f"{switch_prefix}{flv.title()} sounds wonderful! For which date and time do you need it, and would you prefer home delivery or store pickup?"
                elif "tracking_number" in next_keys:
                    if detected_lang == 'kn':
                        reply = f"{switch_prefix}Naanu nimma package status eega check madthene. Dayavittu nimma tracking athava waybill number heli?"
                    elif detected_lang == 'hi':
                        reply = f"{switch_prefix}Main abhi aapka package status check kar deta hoon. Kripya apna tracking ya waybill number bataiye?"
                    else:
                        reply = f"{switch_prefix}I would be happy to look that up for you! Could you please share your tracking or waybill number?"
                elif "inquiry_type" in next_keys:
                    if detected_lang == 'kn':
                        reply = f"{switch_prefix}Nimma delivery bagge nimge yavudhu sahaya beku? Package status, delivery delay, athava address change a?"
                    elif detected_lang == 'hi':
                        reply = f"{switch_prefix}Aapko apni delivery ke baare mein kya jankari chahiye? Package status, delivery delay, ya address change?"
                    else:
                        reply = f"{switch_prefix}How can I assist with your delivery today? Are you looking for package status, reporting a delay, or requesting a callback?"
                else:
                    first_label = missing_required[0]['label']
                    if detected_lang == 'kn':
                        reply = f"{switch_prefix}Dayavittu nimma {first_label} bagge details thilisi?"
                    elif detected_lang == 'hi':
                        reply = f"{switch_prefix}Kripya apna {first_label} bata dijiye?"
                    else:
                        reply = f"{switch_prefix}Could you please share your {first_label} so I can record that for you?"
            else:
                # Completion Confirmation Fallback
                enquiry_tool = next((t for t in executed_tools if t["tool"] == "create_order_enquiry"), None)
                delivery_tool = next((t for t in executed_tools if t["tool"] == "create_delivery_request"), None)
                tracking_tool = next((t for t in executed_tools if t["tool"] == "track_delivery_status"), None)
                callback_tool = next((t for t in executed_tools if t["tool"] == "create_callback_task"), None)
                create_tool = next((t for t in executed_tools if t["tool"] == "create_calendar_event"), None)

                if enquiry_tool and enquiry_tool.get("result", {}).get("success"):
                    e_res = enquiry_tool["result"]
                    owner_n = business.get('owner_name', 'Ananya Sharma')
                    if detected_lang == 'kn':
                        reply = f"{switch_prefix}Thumba dhanyavadagalu! Nimma cake order ({e_res.get('enquiry_id')}) calendar nalli confirm madalaagide ({e_res.get('weight_kg')}kg {e_res.get('flavor')}, {e_res.get('delivery_preference')}). {workflow['closing_message']} Call madidakke dhanyavadagalu, shubhadina!"
                    elif detected_lang == 'hi':
                        reply = f"{switch_prefix}Aapka bahut-bahut dhanyawad! Aapka cake order ({e_res.get('enquiry_id')}) calendar mein confirm kar diya gaya hai ({e_res.get('weight_kg')}kg {e_res.get('flavor')}, {e_res.get('delivery_preference')}). {workflow['closing_message']} Call karne ke liye shukriya, alvida!"
                    else:
                        reply = f"{switch_prefix}Thank you so much! Your cake order ({e_res.get('enquiry_id')}) for a {e_res.get('weight_kg')}kg {e_res.get('flavor')} ({e_res.get('delivery_preference')}) has been confirmed and scheduled in the calendar! {workflow['closing_message']} Thank you for calling {business['name']}, goodbye!"

                elif tracking_tool and tracking_tool.get("result"):
                    t_res = tracking_tool["result"]
                    if detected_lang == 'kn':
                        reply = f"{switch_prefix}Thumba dhanyavadagalu! Tracking #{t_res.get('tracking_number')} status: '{t_res.get('status')}' at {t_res.get('current_location')}. {workflow['closing_message']} Call madidakke dhanyavadagalu, shubhadina!"
                    elif detected_lang == 'hi':
                        reply = f"{switch_prefix}Dhanyawad! Tracking #{t_res.get('tracking_number')} status: '{t_res.get('status')}' at {t_res.get('current_location')}. {workflow['closing_message']} Call karne ke liye shukriya, alvida!"
                    else:
                        reply = f"{switch_prefix}Thank you! Tracking #{t_res.get('tracking_number')} is '{t_res.get('status')}' at {t_res.get('current_location')}. {workflow['closing_message']} Thank you for calling {business['name']}, have a great day!"

                elif callback_tool and callback_tool.get("result", {}).get("success"):
                    cb_res = callback_tool["result"]
                    if detected_lang == 'kn':
                        reply = f"{switch_prefix}Thumba dhanyavadagalu! Nimma callback task ({cb_res.get('task_id')}) note madalaagide. {workflow['closing_message']} Call madidakke dhanyavadagalu, shubhadina!"
                    elif detected_lang == 'hi':
                        reply = f"{switch_prefix}Aapka bahut dhanyawad! Aapka callback task ({cb_res.get('task_id')}) register kar diya gaya hai. {workflow['closing_message']} Call karne ke liye shukriya, alvida!"
                    else:
                        reply = f"{switch_prefix}Thank you! A customer support callback task ({cb_res.get('task_id')}) has been registered for {caller_phone}. {workflow['closing_message']} Thank you for calling {business['name']}, goodbye!"

                elif create_tool and create_tool.get("result", {}).get("success"):
                    c_res = create_tool["result"]
                    if detected_lang == 'kn':
                        reply = f"{switch_prefix}Thumba dhanyavadagalu! Nimma appointment confirm agide ({c_res.get('start_time')}). {workflow['closing_message']} Call madidakke dhanyavadagalu, shubhadina!"
                    elif detected_lang == 'hi':
                        reply = f"{switch_prefix}Bahut dhanyawad! Aapka appointment confirm ho gaya hai ({c_res.get('start_time')})! {workflow['closing_message']} Call karne ke liye shukriya, alvida!"
                    else:
                        reply = f"{switch_prefix}Thank you so much! Your appointment has been successfully scheduled for {c_res.get('start_time')}! {workflow['closing_message']} Thank you for calling {business['name']}, have a wonderful day!"

                else:
                    if detected_lang == 'kn':
                        reply = f"{switch_prefix}Thumba dhanyavadagalu! {business['name']} ge nimma ella details note madikollalaagide. {workflow['closing_message']} Call madidakke dhanyavadagalu, shubhadina!"
                    elif detected_lang == 'hi':
                        reply = f"{switch_prefix}Bahut dhanyawad! Maine aapke sabhi details ({business['name']}) note kar liye hain. {workflow['closing_message']} Call karne ke liye shukriya, alvida!"
                    else:
                        reply = f"{switch_prefix}Thank you so much! I have captured all the necessary information for {business['name']}. {workflow['closing_message']} Thank you for calling, have a wonderful day, goodbye!"

        # Guarantee that if is_complete is True, the response always includes a clear thank you message
        if is_complete and reply:
            reply_lower = reply.lower()
            if not any(w in reply_lower for w in ["thank you", "thanks", "dhanyawad", "dhanyavad", "shukriya"]):
                if detected_lang == 'kn':
                    reply = f"{reply} {business['name']} ge call madidakke thumba dhanyavadagalu! Shubhadina!"
                elif detected_lang == 'hi':
                    reply = f"{reply} {business['name']} mein call karne ke liye aapka bahut-bahut dhanyawad! Alvida!"
                else:
                    reply = f"{reply} Thank you for contacting {business['name']}! Have a wonderful day, goodbye!"

        # 8. DB Persistence & Automatic Follow-Up Tagging
        followup_status = "Completed" if is_complete else "Pending"
        if is_after_hours or urgency in ["Urgent", "Critical"]:
            followup_status = "Follow Up Needed"
            collected_data_dict["lead_status"] = "Follow Up Needed"
            collected_data_dict["urgency_tag"] = urgency

        now_str = datetime.now(timezone.utc).isoformat()
        full_transcript = messages + [{"role": "assistant", "content": reply}]
        tools_str = ", ".join(t["tool"] for t in executed_tools) or "None"
        summary = SummaryService.generate_clear_summary({
            "caller_name": caller_name,
            "caller_phone": caller_phone,
            "business_id": business_id,
            "intent": workflow['name'],
            "followup_status": followup_status,
            "urgency": urgency,
            "collected_data": collected_data_dict
        })

        with get_db_connection() as conn:
            existing = conn.execute(text("SELECT id FROM records WHERE id = :id"), {"id": rec_id}).fetchone()
            if existing:
                conn.execute(text("""
                    UPDATE records 
                    SET collected_data = :cd, ai_summary = :sum, urgency = :urg, followup_status = :fs, transcript = :tr, tools_executed = :te
                    WHERE id = :id
                """), {
                    "cd": json.dumps(collected_data_dict), "sum": summary, "urg": urgency, "fs": followup_status,
                    "tr": json.dumps(full_transcript), "te": json.dumps(executed_tools), "id": rec_id
                })
            else:
                conn.execute(text("""
                    INSERT INTO records (id, business_id, workflow_id, caller_name, caller_phone, intent, collected_data, ai_summary, urgency, followup_status, transcript, tools_executed, created_at)
                    VALUES (:id, :bid, :wfid, :cname, :cphone, :intent, :cd, :sum, :urg, :fs, :tr, :te, :cat)
                """), {
                    "id": rec_id, "bid": business_id, "wfid": workflow_id,
                    "cname": caller_name, "cphone": caller_phone, "intent": workflow['name'],
                    "cd": json.dumps(collected_data_dict), "sum": summary, "urg": urgency, "fs": followup_status,
                    "tr": json.dumps(full_transcript), "te": json.dumps(executed_tools), "cat": now_str
                })
            conn.commit()

        return {
            "record_id": rec_id,
            "assistant_reply": reply,
            "language": detected_lang,
            "language_switched": language_switched,
            "urgency": urgency,
            "executed_tools": executed_tools,
            "collected_data": collected_data_dict,
            "missing_fields": [f["key"] for f in missing_required],
            "is_complete": is_complete
        }
