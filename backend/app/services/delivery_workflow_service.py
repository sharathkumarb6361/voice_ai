"""Deterministic missed-call workflow for the logistics business.

Speech/LLM layers can supply a customer utterance, but this module owns intent,
state, validation, next-question selection, and the side effects that follow.
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


class DeliveryWorkflowService:
    WORKFLOW_ID = "wf-logistics-01"
    BUSINESS_ID = "biz-logistics-01"

    NEW_DELIVERY = "NEW_DELIVERY"
    STATUS_UPDATE = "STATUS_UPDATE"
    EXISTING_DELIVERY_HELP = "EXISTING_DELIVERY_HELP"

    IN_PROGRESS = "IN_PROGRESS"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    COMPLETED = "COMPLETED"
    CALLBACK_REQUIRED = "CALLBACK_REQUIRED"

    MISSED_CALL_GREETING = (
        "Hi, this is the delivery assistant calling you back regarding your missed call. "
        "Are you looking to create a new delivery, check the status of an existing "
        "delivery, or get help with an existing delivery?"
    )

    REQUIRED_FIELDS = {
        NEW_DELIVERY: [
            "pickup_location",
            "delivery_location",
            "package_type",
            "preferred_time",
            "contact_details",
            "tracking_number",
            "issue_description",
        ],
        STATUS_UPDATE: [
            "tracking_number",
            "issue_description",
            "pickup_location",
            "delivery_location",
            "package_type",
            "preferred_time",
            "contact_details",
        ],
        EXISTING_DELIVERY_HELP: [
            "tracking_number",
            "issue_description",
            "pickup_location",
            "delivery_location",
            "package_type",
            "preferred_time",
            "contact_details",
        ],
    }

    FIELD_QUESTIONS = {
        "pickup_location": "Where should we pick up the package (pickup location)?",
        "delivery_location": "Where should we deliver the package (destination address)?",
        "package_type": "What type of package is it (e.g. documents, parcel, electronics)?",
        "preferred_time": "When is your preferred pickup or delivery time?",
        "contact_details": "What contact number should the delivery agent use?",
        "tracking_number": "Sure. Could you provide your order or tracking number?",
        "tracking_or_order_number": "Sure. Could you provide your order or tracking number?",
        "issue_description": "What help or instructions do you have for the delivery?",
    }

    INVALID_LOCATION_WORDS = {
        "sorry", "no", "nope", "not", "nah", "nahi", "illa", "wait", "location", "pickup",
        "delivery", "destination", "origin", "address", "yes", "yeah", "yep", "okay", "ok",
        "fine", "sure", "none", "unknown", "na", "n/a", "nil", "cancel", "correct", "wrong",
        "change", "update", "nothing", "details", "contact", "package", "parcel", "time",
        "date", "timing", "morning", "afternoon", "evening", "night", "tomorrow", "today",
        "asap", "electronic", "electronics", "document", "documents", "order", "tracking",
        "id", "number", "badal", "badli", "thappu", "galat"
    }

    @classmethod
    def handles(cls, workflow_id: str | None) -> bool:
        return workflow_id == cls.WORKFLOW_ID

    @classmethod
    def initial_state(cls, call_id: str, customer_phone: str) -> dict[str, Any]:
        contact = customer_phone if cls._is_valid_phone(customer_phone) else None
        completed = ["contact_details"] if contact else []
        return {
            "call_id": call_id,
            "customer_phone": customer_phone,
            "intent": None,
            "status": cls.IN_PROGRESS,
            "collected_fields": {
                "pickup_location": None,
                "delivery_location": None,
                "package_type": None,
                "preferred_time": None,
                "contact_details": contact,
                "tracking_number": None,
                "order_number": None,
                "issue_description": None,
            },
            "missing_fields": [],
            "last_asked_field": None,
            "completed_fields": completed,
            "callback_task_created": False,
            "delivery_request_created": False,
            "confirmation_pending": False,
        }

    @classmethod
    def get_missing_fields(cls, state: dict[str, Any]) -> list[str]:
        intent = state.get("intent")
        if intent not in cls.REQUIRED_FIELDS:
            return []

        fields = state["collected_fields"]
        missing: list[str] = []
        for field in cls.REQUIRED_FIELDS[intent]:
            if field in {"tracking_number", "tracking_or_order_number"}:
                if not (cls._is_valid_identifier(fields.get("tracking_number")) or cls._is_valid_identifier(fields.get("order_number"))):
                    missing.append("tracking_number")
            elif not cls._is_valid_field(field, fields.get(field)):
                missing.append(field)
        return missing

    @classmethod
    def detect_intent(cls, message: str) -> str | None:
        value = (message or "").lower().strip()
        if not value:
            return None

        # Direct option shortcuts
        if value in {"1", "one", "first", "first one", "option 1", "option one", "#1"}:
            return cls.NEW_DELIVERY
        if value in {"2", "two", "second", "second one", "option 2", "option two", "#2"}:
            return cls.STATUS_UPDATE
        if value in {"3", "three", "third", "third one", "option 3", "option three", "#3"}:
            return cls.EXISTING_DELIVERY_HELP

        help_terms = (
            "help with an existing delivery", "help with existing delivery", "existing delivery help",
            "existing delivery", "help with delivery", "help with", "need help", "problem", "issue",
            "hasn't arrived", "has not arrived", "not arrived", "not received", "late", "delay", "delayed",
            "change delivery", "change address", "change location", "contact driver", "contact agent",
            "unable to receive", "complaint", "support", "sahayata", "madad", "ಸಹಾಯ", "ತಲುಪಿಲ್ಲ",
        )
        status_terms = (
            "status update", "check status", "tracking update", "delivery update", "order update",
            "track order", "track package", "check tracking", "where is", "where's", "kahan",
            "status", "track", "tracking", "स्थिति", "ಸ್ಥಿತಿ", "ಟ್ರ್ಯಾಕ್",
        )
        new_terms = (
            "new delivery", "create a new delivery", "create new delivery", "create delivery",
            "book delivery", "book a delivery", "send a package", "send package", "send a parcel",
            "send parcel", "need a delivery", "pickup a package", "courier", "new", "parcel bhej",
            "delivery bhej", "deliver to", "delivery to", "pickup from", "pickup is", "send to",
            "courier to", "parcel to", "ಹೊಸ ಡೆಲಿವರಿ", "ಪಾರ್ಸೆಲ್ ಕಳುಹ",
        )
        if any(term in value for term in help_terms):
            return cls.EXISTING_DELIVERY_HELP
        if any(term in value for term in new_terms):
            return cls.NEW_DELIVERY
        if any(term in value for term in status_terms):
            return cls.STATUS_UPDATE
        return None

    @classmethod
    def extract_fields(cls, message: str, state: dict[str, Any]) -> dict[str, str]:
        """Extract every explicit value in a turn; never clear stored values."""
        source = (message or "").strip()
        lower = source.lower()
        extracted: dict[str, str] = {}
        last_field = state.get("last_asked_field")

        # 1. Identifiers (Tracking / Order numbers)
        tracking = re.search(r"\b(?:tracking|waybill)(?:\s*(?:number|no\.?))?\s*(?:is|:|#)?\s*([a-z0-9-]{4,})\b", source, re.IGNORECASE)
        order = re.search(r"\border(?:\s*(?:number|no\.?|id))?\s*(?:is|:|#)?\s*([a-z0-9-]{4,})\b", source, re.IGNORECASE)
        if tracking:
            extracted["tracking_number"] = tracking.group(1).upper()
            extracted["order_number"] = tracking.group(1).upper()
        if order:
            extracted["order_number"] = order.group(1).upper()
            if "tracking_number" not in extracted:
                extracted["tracking_number"] = order.group(1).upper()

        if not (tracking or order):
            # Formats like TRK-1234 or ORD-1234
            explicit_id = re.search(r"\b(TRK-[A-Z0-9-]+|ORD-[A-Z0-9-]+|DEL-[A-Z0-9-]+)\b", source, re.IGNORECASE)
            if explicit_id:
                extracted["tracking_number"] = explicit_id.group(1).upper()
                extracted["order_number"] = explicit_id.group(1).upper()
            elif last_field in {"tracking_or_order_number", "tracking_number"}:
                if any(w in lower for w in ["none", "no tracking", "no number", "don't have", "dont have", "not yet", "new parcel", "new delivery", "new", "assign", "generate", "na", "no"]):
                    gen_id = f"TRK-{uuid.uuid4().hex[:6].upper()}"
                    extracted["tracking_number"] = gen_id
                    extracted["order_number"] = gen_id
                else:
                    # Find any standalone alphanumeric token of 4+ chars that isn't a conversational stopword
                    candidates = re.findall(r"\b[A-Za-z0-9-]{4,}\b", source)
                    stopwords = {"this", "that", "with", "have", "here", "from", "number", "order", "tracking", "please", "help", "assign", "create", "generate", "give"}
                    for cand in candidates:
                        if cand.lower() not in stopwords:
                            extracted["tracking_number"] = cand.upper()
                            extracted["order_number"] = cand.upper()
                            break
                    if not extracted.get("tracking_number") and len(source.strip()) >= 3:
                        extracted["tracking_number"] = source.strip().upper()
                        extracted["order_number"] = source.strip().upper()

        # 2. Contact Phone Number
        phone = re.search(r"(?:\+?91[-\s]?)?\d(?:[-\s]?\d){9}\b", source)
        if phone:
            extracted["contact_details"] = phone.group(0).strip()
        elif last_field == "contact_details" and cls._is_valid_phone(source):
            extracted["contact_details"] = source.strip()

        # 3. Locations: Combined "from X to Y"
        from_to = re.search(
            r"\bfrom\s+(.+?)\s+(?:to|and\s+(?:going|deliver(?:ing)?)\s+to)\s+(.+?)(?=\s+(?:tomorrow|today|this|next|at|around|by|for|with)\b|[,.;]|$)",
            source,
            re.IGNORECASE,
        )
        if from_to:
            extracted["pickup_location"] = cls._clean_location(from_to.group(1))
            extracted["delivery_location"] = cls._clean_location(from_to.group(2))

        # Explicit Pickup Location (if not already extracted by from_to)
        if "pickup_location" not in extracted:
            pickup = re.search(r"\b(?:change\s+(?:the\s+)?pickup(?:\s+location)?\s+to|pickup(?:\s+location)?\s*(?:is|:|at|from|to))\s*([^,.;]+)", source, re.IGNORECASE)
            if pickup:
                value = cls._clean_location(pickup.group(1))
                if value:
                    extracted["pickup_location"] = value
            elif last_field == "pickup_location":
                clean_ans = cls._clean_location(source)
                if len(clean_ans) >= 2 and not cls.detect_intent(source):
                    extracted["pickup_location"] = clean_ans

        # Explicit Delivery Location (if not already extracted by from_to)
        if "delivery_location" not in extracted:
            delivery = re.search(r"\b(?:change\s+(?:the\s+)?delivery(?:\s+location)?\s+to|delivery(?:\s+location)?\s*(?:is|:|to|at)|deliver(?:\s+it)?\s+(?:to|at))\s*([^,.;]+)", source, re.IGNORECASE)
            if delivery:
                value = cls._clean_location(delivery.group(1))
                if value:
                    extracted["delivery_location"] = value
            elif last_field == "delivery_location":
                clean_ans = cls._clean_location(source)
                if len(clean_ans) >= 2 and not cls.detect_intent(source):
                    extracted["delivery_location"] = clean_ans

        # 4. Package Types
        package_types = (
            ("documents", ("document", "documents", "files", "file", "papers", "paper")),
            ("small package", ("small package", "small parcel")),
            ("electronics", ("electronics", "electronic", "laptop", "phone", "gadget")),
            ("fragile item", ("fragile", "glass")),
            ("furniture or heavy item", ("furniture", "heavy")),
            ("parcel", ("parcel", "box")),
        )
        for normalized, phrases in package_types:
            if any(phrase in lower for phrase in phrases):
                extracted["package_type"] = normalized
                break

        if "package_type" not in extracted and last_field == "package_type":
            cleaned_pkg = re.sub(r"^(?:it\s+is\s+|it\'?s\s+|a\s+|an\s+|some\s+)", "", source.strip(), flags=re.IGNORECASE).strip(" .,:;!?")
            if len(cleaned_pkg) >= 2 and not cls.detect_intent(source):
                extracted["package_type"] = cleaned_pkg

        # 5. Preferred Time
        time_match = re.search(
            r"\b(?:tomorrow|today|day after tomorrow)(?:\s+(?:morning|afternoon|evening|night|around\s+\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)?|at\s+\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)?|by\s+\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)?))?\b|\b(?:around|at|by)\s+\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)\b|\b\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)\b|\b(?:asap|as soon as possible|right now|immediately)\b",
            source,
            re.IGNORECASE,
        )
        if time_match:
            extracted["preferred_time"] = time_match.group(0).strip()
        elif last_field == "preferred_time" and "preferred_time" not in extracted:
            cleaned_time = re.sub(r"^(?:at\s+|around\s+|by\s+)", "", source.strip(), flags=re.IGNORECASE).strip(" .,:;!?")
            if len(cleaned_time) >= 3 and not cls.detect_intent(source):
                extracted["preferred_time"] = cleaned_time

        # 6. Issue Description / Special Instructions
        issue = cls._extract_issue(source)
        if issue:
            extracted["issue_description"] = issue
        elif last_field == "issue_description":
            clean_issue = source.strip(" .,:;!?")
            if any(w in lower for w in ["none", "no issue", "no problem", "all good", "standard", "normal", "no special", "nothing", "no notes", "no instructions"]):
                extracted["issue_description"] = "Standard Delivery - No Issues"
            elif len(clean_issue) >= 2 and not cls.detect_intent(source):
                extracted["issue_description"] = clean_issue

        # LangChain fallback / enhancement for natural language corrections
        has_change_cue = any(w in lower for w in ["actually", "change", "correct", "update", "switch", "wrong", "instead", "meant", "sorry", "not", "different", "modify", "badal", "badli", "galat", "thappu"])
        if has_change_cue or not extracted or (last_field and last_field not in extracted and last_field != "field_selection_for_correction"):
            try:
                from app.services.langchain_service import LangChainService
                lc_res = LangChainService.analyze_and_correct_turn(
                    workflow={"name": "Logistics & Delivery Assistant", "industry": "Logistics & Delivery"},
                    business={"name": "SwiftMove Express"},
                    fields=[
                        {"key": "pickup_location", "label": "Pickup Location", "required": True},
                        {"key": "delivery_location", "label": "Delivery Location", "required": True},
                        {"key": "package_type", "label": "Package Type", "required": True},
                        {"key": "preferred_time", "label": "Preferred Time", "required": True},
                        {"key": "tracking_number", "label": "Tracking Number", "required": False}
                    ],
                    collected_data=state.get("collected_fields", {}),
                    current_question_field=last_field,
                    messages=[{"role": "user", "content": source}],
                    language="en"
                )
                for c in lc_res.corrections:
                    if cls._is_valid_field(c.field_key, c.new_value):
                        extracted[c.field_key] = c.new_value
                for k, v in lc_res.new_extracted_fields.items():
                    if k not in extracted and cls._is_valid_field(k, v):
                        extracted[k] = v
            except Exception:
                pass

        return {key: value for key, value in extracted.items() if cls._is_valid_field(key, value)}

    @classmethod
    def advance_state(
        cls,
        state: dict[str, Any],
        customer_message: str,
        caller_name: str,
        caller_phone: str,
    ) -> tuple[dict[str, Any], str, list[dict[str, Any]]]:
        """Run one deterministic customer turn without persistence concerns."""
        tools: list[dict[str, Any]] = []
        message = (customer_message or "").strip()
        fields = state["collected_fields"]

        # Intent is established only once; later turns are field answers/corrections.
        msg_lower = message.lower()
        if any(k in msg_lower for k in ["cancel pickup", "cancel delivery", "cancel my pickup", "cancel my courier"]):
            cancel_res = CalendarService.cancel_event(business_id=cls.BUSINESS_ID)
            tools.append({"tool": "cancel_calendar_event", "args": {"business_id": cls.BUSINESS_ID}, "result": cancel_res})
            state["status"] = cls.COMPLETED
            state["last_asked_field"] = None
            return state, "Your courier pickup appointment has been successfully cancelled on our dispatch calendar. Thank you for notifying SwiftMove Express, goodbye!", tools

        if any(k in msg_lower for k in ["reschedule pickup", "reschedule delivery", "reschedule my pickup", "change pickup time", "postpone pickup"]):
            target_dt = CalendarService.parse_datetime_input(message, "10:00")
            update_res = CalendarService.update_event(
                business_id=cls.BUSINESS_ID,
                new_start_time=target_dt.isoformat()
            )
            tools.append({"tool": "update_calendar_event", "args": {"new_start_time": target_dt.isoformat(), "business_id": cls.BUSINESS_ID}, "result": update_res})
            state["status"] = cls.COMPLETED
            state["last_asked_field"] = None
            return state, f"Your courier pickup has been rescheduled on our dispatch calendar to {target_dt.strftime('%B %d at %I:%M %p')}. Our driver will arrive then. Thank you and goodbye!", tools

        # 1. Check if caller is negating an existing field (e.g. "Sorry, it's not Marathahalli", "not Marathahalli", "wrong pickup")
        for f_key in ["pickup_location", "delivery_location", "package_type", "preferred_time"]:
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
                    if f_key == "pickup_location":
                        return state, "No problem! Where should we pick up the package instead?", tools
                    elif f_key == "delivery_location":
                        return state, "No problem! Where should we deliver the package instead?", tools
                    elif f_key == "package_type":
                        return state, "No problem! What type of package is it instead?", tools
                    elif f_key == "preferred_time":
                        return state, "No problem! When would you prefer the pickup or delivery instead?", tools

        # 2. If caller is answering "Which delivery detail would you like to correct?"
        if state.get("last_asked_field") == "field_selection_for_correction":
            if any(w in msg_lower for w in ["delivery", "destination", "drop", "location", "address"]):
                if "pickup" in msg_lower or "origin" in msg_lower:
                    fields["pickup_location"] = None
                    state["status"] = cls.IN_PROGRESS
                    state["confirmation_pending"] = False
                    state["last_asked_field"] = "pickup_location"
                    state["missing_fields"] = cls.get_missing_fields(state)
                    return state, "Sure! Where should we pick up the package instead?", tools
                fields["delivery_location"] = None
                state["status"] = cls.IN_PROGRESS
                state["confirmation_pending"] = False
                state["last_asked_field"] = "delivery_location"
                state["missing_fields"] = cls.get_missing_fields(state)
                return state, "Sure! Where should we deliver the package instead?", tools
            elif any(w in msg_lower for w in ["pickup", "origin", "pick up"]):
                fields["pickup_location"] = None
                state["status"] = cls.IN_PROGRESS
                state["confirmation_pending"] = False
                state["last_asked_field"] = "pickup_location"
                state["missing_fields"] = cls.get_missing_fields(state)
                return state, "Sure! Where should we pick up the package instead?", tools
            elif any(w in msg_lower for w in ["package", "parcel", "type", "item"]):
                fields["package_type"] = None
                state["status"] = cls.IN_PROGRESS
                state["confirmation_pending"] = False
                state["last_asked_field"] = "package_type"
                state["missing_fields"] = cls.get_missing_fields(state)
                return state, "Sure! What type of package is it instead?", tools
            elif any(w in msg_lower for w in ["time", "timing", "date", "slot", "when", "day"]):
                fields["preferred_time"] = None
                state["status"] = cls.IN_PROGRESS
                state["confirmation_pending"] = False
                state["last_asked_field"] = "preferred_time"
                state["missing_fields"] = cls.get_missing_fields(state)
                return state, "Sure! When is your updated preferred pickup or delivery time?", tools
            elif any(w in msg_lower for w in ["contact", "phone", "number"]):
                fields["contact_details"] = None
                state["status"] = cls.IN_PROGRESS
                state["confirmation_pending"] = False
                state["last_asked_field"] = "contact_details"
                state["missing_fields"] = cls.get_missing_fields(state)
                return state, "Sure! What contact number should the delivery team use?", tools

        # 3. Check for mid-turn slot correction / change requests
        has_change_cue = any(w in msg_lower for w in ["change", "correct", "update", "switch", "wrong", "another", "modify", "mistake", "badal", "badli", "thappu", "galat"])
        if has_change_cue and state.get("intent") == cls.NEW_DELIVERY:
            if any(w in msg_lower for w in ["deliver", "delivery", "destination", "drop"]):
                del_match = re.search(r"(?:change\s+(?:the\s+)?delivery(?:\s+location)?\s+to|deliver(?:\s+it)?\s+to)\s+([a-zA-Z0-9\s]+)", msg_lower)
                if del_match and cls._is_valid_field("delivery_location", del_match.group(1)):
                    new_val = cls._clean_location(del_match.group(1)).title()
                    fields["delivery_location"] = new_val
                    state["last_asked_field"] = None
                    state["missing_fields"] = cls.get_missing_fields(state)
                    if not state["missing_fields"]:
                        state["status"] = cls.AWAITING_CONFIRMATION
                        state["confirmation_pending"] = True
                        return state, (
                            f"Got it, I have updated the delivery address to {new_val}. Let me reconfirm: "
                            f"The {fields['package_type']} will be picked up from {fields['pickup_location']} "
                            f"and delivered to {fields['delivery_location']} {fields['preferred_time']}. Is that correct?"
                        ), tools
                    return cls._ask_next_missing_field(state, tools, prefix=f"Got it, I have updated the delivery address to {new_val}.")
                else:
                    fields["delivery_location"] = None
                    state["status"] = cls.IN_PROGRESS
                    state["confirmation_pending"] = False
                    state["last_asked_field"] = "delivery_location"
                    state["missing_fields"] = cls.get_missing_fields(state)
                    return state, "Sure! Where should we deliver the package instead?", tools

            elif any(w in msg_lower for w in ["pickup", "pick up", "origin"]):
                pick_match = re.search(r"(?:change\s+(?:the\s+)?pickup(?:\s+location)?\s+to|pickup\s+from)\s+([a-zA-Z0-9\s]+)", msg_lower)
                if pick_match and cls._is_valid_field("pickup_location", pick_match.group(1)):
                    new_val = cls._clean_location(pick_match.group(1)).title()
                    fields["pickup_location"] = new_val
                    state["last_asked_field"] = None
                    state["missing_fields"] = cls.get_missing_fields(state)
                    if not state["missing_fields"]:
                        state["status"] = cls.AWAITING_CONFIRMATION
                        state["confirmation_pending"] = True
                        return state, (
                            f"Got it, I have updated the pickup location to {new_val}. Let me reconfirm: "
                            f"The {fields['package_type']} will be picked up from {fields['pickup_location']} "
                            f"and delivered to {fields['delivery_location']} {fields['preferred_time']}. Is that correct?"
                        ), tools
                    return cls._ask_next_missing_field(state, tools, prefix=f"Got it, I have updated the pickup location to {new_val}.")
                else:
                    fields["pickup_location"] = None
                    state["status"] = cls.IN_PROGRESS
                    state["confirmation_pending"] = False
                    state["last_asked_field"] = "pickup_location"
                    state["missing_fields"] = cls.get_missing_fields(state)
                    return state, "Sure! Where should we pick up the package instead?", tools

            elif any(w in msg_lower for w in ["package", "parcel", "type"]):
                pkg_match = re.search(r"(?:change\s+(?:the\s+)?package(?:\s+type)?\s+to)\s+([a-zA-Z0-9\s]+)", msg_lower)
                if pkg_match and cls._is_valid_field("package_type", pkg_match.group(1)):
                    new_val = pkg_match.group(1).strip().lower()
                    fields["package_type"] = new_val
                    state["last_asked_field"] = None
                    state["missing_fields"] = cls.get_missing_fields(state)
                    if not state["missing_fields"]:
                        state["status"] = cls.AWAITING_CONFIRMATION
                        state["confirmation_pending"] = True
                        return state, (
                            f"Got it, I have updated the package type to {new_val}. Let me reconfirm: "
                            f"The {fields['package_type']} will be picked up from {fields['pickup_location']} "
                            f"and delivered to {fields['delivery_location']} {fields['preferred_time']}. Is that correct?"
                        ), tools
                    return cls._ask_next_missing_field(state, tools, prefix=f"Got it, I have updated the package type to {new_val}.")
                else:
                    fields["package_type"] = None
                    state["status"] = cls.IN_PROGRESS
                    state["confirmation_pending"] = False
                    state["last_asked_field"] = "package_type"
                    state["missing_fields"] = cls.get_missing_fields(state)
                    return state, "Sure! What type of package is it instead?", tools

            elif any(w in msg_lower for w in ["time", "timing", "date", "slot", "when", "day"]):
                fields["preferred_time"] = None
                state["status"] = cls.IN_PROGRESS
                state["confirmation_pending"] = False
                state["last_asked_field"] = "preferred_time"
                state["missing_fields"] = cls.get_missing_fields(state)
                return state, "Sure! When is your updated preferred pickup or delivery time?", tools

        if not state.get("intent"):
            state["intent"] = cls.detect_intent(message)

        extracted = cls.extract_fields(message, state)
        for field, value in extracted.items():
            # A valid explicit correction wins. An absent/invalid extraction never erases data.
            if cls._is_valid_field(field, value):
                fields[field] = value

        if fields.get("contact_details") is None and cls._is_valid_phone(caller_phone):
            fields["contact_details"] = caller_phone

        # If intent was not explicitly detected by keywords, infer from extracted fields or greeting response
        if not state.get("intent") and message:
            if fields.get("pickup_location") or fields.get("delivery_location") or fields.get("package_type") or fields.get("preferred_time"):
                state["intent"] = cls.NEW_DELIVERY
            elif fields.get("order_number") or fields.get("tracking_number"):
                state["intent"] = cls.EXISTING_DELIVERY_HELP if fields.get("issue_description") else cls.STATUS_UPDATE
            elif not cls._is_no(message) and not cls._customer_refused(message):
                clean_ans = cls._clean_location(message).strip(" .,:;!?")
                if len(clean_ans) >= 2:
                    state["intent"] = cls.NEW_DELIVERY
                    if not fields.get("pickup_location"):
                        fields["pickup_location"] = clean_ans

        state["completed_fields"] = [
            field for field, value in fields.items() if cls._is_valid_field(field, value)
        ]
        state["missing_fields"] = cls.get_missing_fields(state)

        if state.get("status") in {cls.COMPLETED, cls.CALLBACK_REQUIRED}:
            if extracted:
                state["status"] = cls.AWAITING_CONFIRMATION
                state["confirmation_pending"] = True
                state["delivery_request_created"] = False
                updated_names = [f.replace('_', ' ') for f in extracted.keys()]
                return state, (
                    f"Got it, I have updated the {', '.join(updated_names)}. Let me reconfirm: "
                    f"The {fields['package_type']} will be picked up from {fields['pickup_location']} "
                    f"and delivered to {fields['delivery_location']} {fields['preferred_time']}. Is that correct?"
                ), tools
            elif any(w in msg_lower for w in ["change", "correct", "update", "switch", "wrong", "another", "modify", "mistake"]):
                if "pickup" in msg_lower:
                    state["status"] = cls.IN_PROGRESS
                    state["last_asked_field"] = "pickup_location"
                    return state, "Sure! Where should we pick up the package instead?", tools
                if "deliver" in msg_lower:
                    state["status"] = cls.IN_PROGRESS
                    state["last_asked_field"] = "delivery_location"
                    return state, "Sure! Where should we deliver the package instead?", tools
                if "package" in msg_lower or "type" in msg_lower:
                    state["status"] = cls.IN_PROGRESS
                    state["last_asked_field"] = "package_type"
                    return state, "Sure! What type of package is it instead?", tools
                if "time" in msg_lower or "timing" in msg_lower:
                    state["status"] = cls.IN_PROGRESS
                    state["last_asked_field"] = "preferred_time"
                    return state, "Sure! When is your updated preferred pickup or delivery time?", tools
                return state, "Sure! Which delivery detail would you like to update — pickup location, delivery address, package type, or preferred time?", tools
            return state, "This request is already complete. Is there anything else our delivery team can help you with?", tools

        if not state.get("intent"):
            state["last_asked_field"] = None
            return state, cls.MISSED_CALL_GREETING, tools

        if cls._customer_refused(message) and state["missing_fields"]:
            return cls._create_callback_for_incomplete_request(state, caller_name, caller_phone, tools)

        if state["intent"] == cls.NEW_DELIVERY:
            return cls._advance_new_delivery(state, message, caller_name, caller_phone, tools)
        if state["intent"] == cls.STATUS_UPDATE:
            return cls._advance_status_update(state, caller_name, caller_phone, tools)
        return cls._advance_existing_delivery_help(state, caller_name, caller_phone, tools)

    @classmethod
    def process_conversation(cls, request_data: dict[str, Any]) -> dict[str, Any]:
        business_id = request_data.get("business_id") or cls.BUSINESS_ID
        workflow_id = request_data.get("workflow_id") or cls.WORKFLOW_ID
        caller_name = request_data.get("caller_name") or "Customer"
        caller_phone = request_data.get("caller_phone") or "+91 98765 43210"
        record_id = request_data.get("record_id") or f"rec-delivery-{uuid.uuid4().hex[:12]}"
        messages = request_data.get("messages") or []
        user_messages = [item.get("content", "") for item in messages if item.get("role") == "user"]
        customer_message = user_messages[-1] if user_messages else ""

        state, historical_tools = cls._load_state(record_id, caller_phone)
        state["customer_phone"] = caller_phone
        state["call_id"] = record_id

        # If state in DB has no intent yet and client passed a multi-turn transcript,
        # replay prior turns so context is preserved across HTTP calls even if record was not cached.
        if not state.get("intent") and len(user_messages) > 1:
            for prior_msg in user_messages[:-1]:
                state, _, prior_turn_tools = cls.advance_state(state, prior_msg, caller_name, caller_phone)
                historical_tools.extend(prior_turn_tools)

        state, reply, turn_tools = cls.advance_state(state, customer_message, caller_name, caller_phone)
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
        flattened_collected = dict(state.get("collected_fields", {}))
        flattened_collected["intent"] = state.get("intent")
        flattened_collected["status"] = state.get("status")
        flattened_collected["delivery_workflow_state"] = state

        return {
            "record_id": record_id,
            "assistant_reply": reply,
            "language": cls._detect_language(customer_message, request_data.get("language")),
            "language_switched": False,
            "urgency": "Normal",
            "executed_tools": turn_tools,
            "collected_data": flattened_collected,
            "conversation_state": state,
            "missing_fields": state["missing_fields"],
            "is_complete": state["status"] in {cls.COMPLETED, cls.CALLBACK_REQUIRED},
        }

    @classmethod
    def start_missed_call(cls, caller_name: str, caller_phone: str, language: str = "auto") -> dict[str, Any]:
        record_id = f"rec-delivery-{uuid.uuid4().hex[:12]}"
        state = cls.initial_state(record_id, caller_phone)
        callback = ExternalApiService.create_callback_task(
            issue_summary="Automated callback after missed delivery-service call",
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
            transcript=[{"role": "assistant", "content": cls.MISSED_CALL_GREETING}],
            tools=tools,
        )
        return {
            "record_id": record_id,
            "assistant_reply": cls.MISSED_CALL_GREETING,
            "language": cls._detect_language("", language),
            "executed_tools": tools,
            "conversation_state": state,
            "missing_fields": [],
            "is_complete": False,
        }

    @classmethod
    def _advance_new_delivery(cls, state: dict[str, Any], message: str, caller_name: str, caller_phone: str, tools: list[dict[str, Any]]):
        if state["status"] == cls.AWAITING_CONFIRMATION:
            if cls._is_yes(message):
                result = ExternalApiService.create_delivery_request(
                    pickup_location=state["collected_fields"]["pickup_location"],
                    delivery_location=state["collected_fields"]["delivery_location"],
                    package_type=state["collected_fields"]["package_type"],
                    preferred_time=state["collected_fields"]["preferred_time"],
                    caller_name=caller_name,
                    caller_phone=state["collected_fields"]["contact_details"],
                )
                tools.append({"tool": "create_delivery_request", "args": dict(state["collected_fields"]), "result": result})
                if result.get("success"):
                    state["delivery_request_created"] = True
                    state["status"] = cls.COMPLETED
                    state["last_asked_field"] = None

                    # Calendar AI Agent: Automatically schedule courier pickup window on Google Calendar & DB
                    try:
                        pref_time = state["collected_fields"].get("preferred_time") or "tomorrow 10 AM"
                        target_dt = CalendarService.parse_datetime_input(pref_time, "10:00")
                        start_iso = target_dt.isoformat()
                        end_iso = (target_dt + timedelta(minutes=45)).isoformat()
                        cal_title = f"Courier Pickup: {state['collected_fields']['pickup_location']} -> {state['collected_fields']['delivery_location']} ({result['delivery_id']})"
                        cal_res = CalendarService.create_event(
                            business_id=cls.BUSINESS_ID,
                            title=cal_title,
                            start_time=start_iso,
                            end_time=end_iso,
                            attendee_name=caller_name,
                            attendee_phone=state["collected_fields"]["contact_details"],
                            description=(
                                f"SwiftMove Express [{result['delivery_id']}] Courier Pickup & Dispatch.\n"
                                f"Package: {state['collected_fields']['package_type']}\n"
                                f"From: {state['collected_fields']['pickup_location']}\n"
                                f"To: {state['collected_fields']['delivery_location']}\n"
                                f"Contact: {state['collected_fields']['contact_details']}"
                            )
                        )
                        tools.append({
                            "tool": "create_calendar_event",
                            "args": {"title": cal_title, "start_time": start_iso, "delivery_id": result["delivery_id"]},
                            "result": cal_res
                        })
                        state["calendar_event"] = cal_res
                    except Exception as cal_err:
                        print(f"[Logistics Calendar Notice] {cal_err}")

                    return state, (
                        f"Thank you for choosing SwiftMove Express! Your delivery request has been created successfully and scheduled on our dispatch calendar. "
                        f"Your request number is {result['delivery_id']}. Our pickup agent will collect the package from "
                        f"{state['collected_fields']['pickup_location']} {state['collected_fields']['preferred_time']}. "
                        f"Thank you and have a wonderful day, goodbye!"
                    ), tools
                return cls._create_callback_for_incomplete_request(state, caller_name, caller_phone, tools, "Delivery creation failed")
            if cls._is_no(message):
                state["status"] = cls.IN_PROGRESS
                state["confirmation_pending"] = False
                state["last_asked_field"] = "field_selection_for_correction"
                return state, "No problem. Which delivery detail would you like to correct?", tools
            # Check for ambiguous correction while awaiting confirmation
            if any(w in message.lower() for w in ["change", "correct", "update", "switch", "wrong", "modify", "mistake", "different"]):
                msg_l = message.lower()
                if "pickup" in msg_l:
                    state["status"] = cls.IN_PROGRESS
                    state["confirmation_pending"] = False
                    state["last_asked_field"] = "pickup_location"
                    return state, "Sure! Where should we pick up the package instead?", tools
                if "deliver" in msg_l:
                    state["status"] = cls.IN_PROGRESS
                    state["confirmation_pending"] = False
                    state["last_asked_field"] = "delivery_location"
                    return state, "Sure! Where should we deliver the package instead?", tools
                if "package" in msg_l or "type" in msg_l:
                    state["status"] = cls.IN_PROGRESS
                    state["confirmation_pending"] = False
                    state["last_asked_field"] = "package_type"
                    return state, "Sure! What type of package is it instead?", tools
                if "time" in msg_l or "timing" in msg_l:
                    state["status"] = cls.IN_PROGRESS
                    state["confirmation_pending"] = False
                    state["last_asked_field"] = "preferred_time"
                    return state, "Sure! When is your updated preferred pickup or delivery time?", tools
                state["status"] = cls.IN_PROGRESS
                state["confirmation_pending"] = False
                state["last_asked_field"] = "field_selection_for_correction"
                return state, "No problem. Which delivery detail would you like to update — pickup location, delivery address, package type, or time?", tools

        if state.get("last_asked_field") == "field_selection_for_correction":
            return state, "No problem. Which delivery detail would you like to update — pickup location, delivery address, package type, or time?", tools

        if state["missing_fields"]:
            return cls._ask_next_missing_field(state, tools)

        state["status"] = cls.AWAITING_CONFIRMATION
        state["confirmation_pending"] = True
        state["last_asked_field"] = None
        fields = state["collected_fields"]

        # Calendar AI: Check courier slot availability
        try:
            pref_time = fields.get("preferred_time") or "tomorrow 10 AM"
            avail = CalendarService.check_availability(pref_time, "10:00", duration_minutes=45, business_id=cls.BUSINESS_ID)
            tools.append({
                "tool": "check_calendar_availability",
                "args": {"preferred_time": pref_time, "business_id": cls.BUSINESS_ID},
                "result": avail
            })
        except Exception:
            pass

        return state, (
            f"Let me confirm. The {fields['package_type']} will be picked up from {fields['pickup_location']} "
            f"and delivered to {fields['delivery_location']} {fields['preferred_time']}. We'll use "
            f"{fields['contact_details']} for contact. Is that correct?"
        ), tools

    @classmethod
    def _advance_status_update(cls, state: dict[str, Any], caller_name: str, caller_phone: str, tools: list[dict[str, Any]]):
        if state["missing_fields"]:
            return cls._ask_next_missing_field(state, tools)
        identifier = state["collected_fields"].get("tracking_number") or state["collected_fields"].get("order_number")
        lookup = ExternalApiService.track_delivery_status(identifier)
        tools.append({"tool": "track_delivery_status", "args": {"identifier": identifier}, "result": lookup})
        if lookup.get("success") is False:
            state["collected_fields"]["tracking_number"] = None
            state["collected_fields"]["order_number"] = None
            state["missing_fields"] = cls.get_missing_fields(state)
            return cls._ask_next_missing_field(state, tools, "I couldn't find that delivery.")
        state["delivery_lookup"] = lookup
        state["status"] = cls.COMPLETED
        state["last_asked_field"] = None
        driver_str = f" Driver: {lookup['driver_name']} ({lookup.get('driver_phone', '')})." if lookup.get("driver_name") else ""
        return state, (
            f"Your delivery {identifier} is {lookup.get('status', 'being processed')} at "
            f"{lookup.get('current_location', 'our logistics network')}.{driver_str} "
            f"Estimated delivery: {lookup.get('estimated_delivery', 'not yet available')}. "
            f"Thank you for checking with SwiftMove Express! Have a great day, goodbye!"
        ), tools

    @classmethod
    def _advance_existing_delivery_help(cls, state: dict[str, Any], caller_name: str, caller_phone: str, tools: list[dict[str, Any]]):
        if state["missing_fields"]:
            return cls._ask_next_missing_field(state, tools)
        identifier = state["collected_fields"].get("tracking_number") or state["collected_fields"].get("order_number")
        lookup = ExternalApiService.track_delivery_status(identifier)
        tools.append({"tool": "track_delivery_status", "args": {"identifier": identifier}, "result": lookup})
        issue = state["collected_fields"]["issue_description"]
        summary = f"Delivery help requested for {identifier}: {issue}. Current status: {lookup.get('status', 'unknown')}."
        callback = ExternalApiService.create_callback_task(
            issue_summary=summary,
            tracking_number=identifier,
            caller_name=caller_name,
            caller_phone=caller_phone,
        )
        tools.append({
            "tool": "create_callback_task",
            "args": {
                "customer_phone": caller_phone,
                "order_number": state["collected_fields"].get("order_number"),
                "tracking_number": state["collected_fields"].get("tracking_number"),
                "issue_description": issue,
                "conversation_summary": summary,
                "priority": "NORMAL",
                "status": "PENDING",
            },
            "result": callback,
        })
        if callback.get("success"):
            state["callback_task_created"] = True
            state["callback_task"] = callback
            state["delivery_lookup"] = lookup
            state["status"] = cls.CALLBACK_REQUIRED
            state["last_asked_field"] = None
            return state, (
                f"Thank you for reaching out. I've created a callback request for our delivery team regarding {identifier}. "
                f"Your callback request task ID is {callback.get('task_id', '')}. A support representative will follow up with you "
                f"shortly on {caller_phone}. Thank you and have a wonderful day, goodbye!"
            ), tools
        return cls._create_callback_for_incomplete_request(state, caller_name, caller_phone, tools, "Callback creation failed")

    @classmethod
    def _create_callback_for_incomplete_request(cls, state: dict[str, Any], caller_name: str, caller_phone: str, tools: list[dict[str, Any]], reason: str = "Customer needs assistance"):
        summary = f"{reason}. Missing information: {', '.join(state.get('missing_fields', [])) or 'none'}."
        callback = ExternalApiService.create_callback_task(summary, caller_name=caller_name, caller_phone=caller_phone)
        tools.append({"tool": "create_callback_task", "args": {"issue_description": summary}, "result": callback})
        if callback.get("success"):
            state["callback_task_created"] = True
            state["callback_task"] = callback
            state["status"] = cls.CALLBACK_REQUIRED
            state["last_asked_field"] = None
            return state, "I'm having trouble completing that request right now. I've created a callback request so our team can assist you.", tools
        return state, "I'm sorry, but I couldn't complete that request right now. Please try again shortly.", tools

    @classmethod
    def _ask_next_missing_field(cls, state: dict[str, Any], tools: list[dict[str, Any]], prefix: str = ""):
        next_field = state["missing_fields"][0]
        state["last_asked_field"] = next_field
        intent = state.get("intent")

        if next_field in {"tracking_number", "tracking_or_order_number"}:
            if intent == cls.NEW_DELIVERY:
                question = "Do you have an existing tracking or reference number, or should we assign a new tracking ID?"
            else:
                question = "Sure! Could you please provide your order or tracking number (e.g. TRK-9821-IN)?"
        elif next_field == "issue_description":
            if intent == cls.NEW_DELIVERY:
                question = "Are there any special handling instructions or notes for this delivery?"
            elif intent == cls.STATUS_UPDATE:
                question = "Any specific query or status note regarding this delivery?"
            else:
                question = "What help do you need with this delivery or what issue occurred?"
        elif next_field == "pickup_location":
            if intent == cls.NEW_DELIVERY:
                question = "Where should we pick up the package?"
            else:
                question = "What was the pickup location for this package?"
        elif next_field == "delivery_location":
            if intent == cls.NEW_DELIVERY:
                question = "Where should we deliver the package?"
            else:
                question = "What is the destination delivery address?"
        elif next_field == "package_type":
            question = "What type of package is it (e.g. documents, small package, electronics, parcel)?"
        elif next_field == "preferred_time":
            if intent == cls.NEW_DELIVERY:
                question = "When would you prefer the pickup?"
            else:
                question = "What is your preferred delivery or callback time?"
        elif next_field == "contact_details":
            question = "What contact number should the delivery team use?"
        elif next_field in cls.FIELD_QUESTIONS:
            question = cls.FIELD_QUESTIONS[next_field]
        else:
            question = f"Could you please specify the {next_field.replace('_', ' ')}?"

        return state, f"{prefix} {question}".strip(), tools

    @classmethod
    def _clean_location(cls, value: str) -> str:
        value = re.split(r"\s+(?:and\s+)?(?:deliver(?:y)?|drop|package|tomorrow|today|at|around|by|instead|please)\b", value, maxsplit=1, flags=re.IGNORECASE)[0]
        value = re.sub(r"^(?:it\s+is\s+|it\'?s\s+|pickup\s+(?:is\s+|from\s+|at\s+)?|delivery\s+(?:is\s+|to\s+|at\s+)?|from\s+|to\s+|at\s+|near\s+)", "", value.strip(), flags=re.IGNORECASE)
        value = re.sub(r"\s+(?:instead|please)$", "", value.strip(), flags=re.IGNORECASE)
        cleaned = value.strip(" .,:;-")
        if cleaned.lower() in cls.INVALID_LOCATION_WORDS:
            return ""
        return cleaned

    @staticmethod
    def _extract_issue(message: str) -> str | None:
        lower = message.lower()
        issue_map = {
            "hasn't arrived": "delivery not received",
            "has not arrived": "delivery not received",
            "not arrived": "delivery not received",
            "not received": "delivery not received",
            "late": "delivery delayed",
            "delay": "delivery delayed",
            "delayed": "delivery delayed",
            "change delivery time": "change delivery time",
            "change address": "change delivery location",
            "change location": "change delivery location",
            "unable to receive": "unable to receive package",
            "contact driver": "contact delivery agent",
            "handle with care": "handle with care",
            "fragile": "fragile item - handle with care",
            "do not bend": "do not bend",
            "urgent": "urgent delivery",
        }
        for phrase, normalized in issue_map.items():
            if phrase in lower:
                return normalized
        if any(word in lower for word in ("problem", "issue", "complaint", "support")):
            cleaned = re.sub(r"\b(?:tracking|waybill|order)(?:\s*(?:number|no\.?|id))?\s*(?:is|:|#)?\s*[a-z0-9-]+", "", message, flags=re.IGNORECASE)
            return cleaned.strip(" .,:;")[:240] or None
        return None

    @staticmethod
    def _is_valid_phone(value: Any) -> bool:
        return len(re.sub(r"\D", "", str(value or ""))) >= 10

    @staticmethod
    def _is_valid_identifier(value: Any) -> bool:
        return bool(re.fullmatch(r"[A-Za-z0-9-]{4,}", str(value or "")))

    @classmethod
    def _is_valid_field(cls, field: str, value: Any) -> bool:
        if not value:
            return False
        val_str = str(value).strip()
        val_lower = val_str.lower()
        if field in {"tracking_number", "order_number"}:
            return cls._is_valid_identifier(val_str)
        if field == "contact_details":
            return cls._is_valid_phone(val_str)
        if field in {"pickup_location", "delivery_location"}:
            if val_lower in cls.INVALID_LOCATION_WORDS:
                return False
            if any(val_lower.startswith(prefix) for prefix in ["sorry", "not ", "it's not", "its not", "no ", "wrong", "change", "update", "galat", "thappu"]):
                return False
            if re.fullmatch(r"[\d\W_]+", val_str):
                return False
            return len(val_str) >= 3
        if field == "package_type":
            if val_lower in {"no", "none", "na", "n/a", "unknown", "sorry", "cancel", "not"}:
                return False
            return len(val_str) >= 2
        if field == "preferred_time":
            if val_lower in {"no", "none", "na", "n/a", "unknown", "sorry"}:
                return False
            return len(val_str) >= 3
        if field == "issue_description":
            return len(val_str) >= 2
        return len(val_str) >= 2

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

    @staticmethod
    def _customer_refused(message: str) -> bool:
        value = (message or "").lower()
        return any(phrase in value for phrase in ("don't want to provide", "do not want to provide", "won't provide", "will not provide", "refuse"))

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
    def _load_state(cls, record_id: str, caller_phone: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        with get_db_connection() as conn:
            row = conn.execute(text("SELECT collected_data, tools_executed FROM records WHERE id = :id"), {"id": record_id}).fetchone()
        if not row:
            return cls.initial_state(record_id, caller_phone), []
        try:
            payload = json.loads(row[0] or "{}")
            state = payload.get("delivery_workflow_state")
            if isinstance(state, dict):
                return state, json.loads(row[1] or "[]")
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
        return cls.initial_state(record_id, caller_phone), []

    @classmethod
    def _save_record(cls, record_id: str, business_id: str, workflow_id: str, caller_name: str, caller_phone: str, state: dict[str, Any], transcript: list[dict[str, Any]], tools: list[dict[str, Any]]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        summary = SummaryService.generate_clear_summary({
            "caller_name": caller_name,
            "caller_phone": caller_phone,
            "business_id": business_id,
            "intent": state.get("intent") or "NEW_DELIVERY",
            "followup_status": state.get("status"),
            "collected_data": {"delivery_workflow_state": state}
        })
        payload = json.dumps({"delivery_workflow_state": state})
        with get_db_connection() as conn:
            existing = conn.execute(text("SELECT id FROM records WHERE id = :id"), {"id": record_id}).fetchone()
            if existing:
                conn.execute(text("""
                    UPDATE records SET intent = :intent, collected_data = :collected_data, ai_summary = :summary,
                    followup_status = :followup_status, transcript = :transcript, tools_executed = :tools
                    WHERE id = :id
                """), {
                    "id": record_id,
                    "intent": state.get("intent") or "UNCLASSIFIED",
                    "collected_data": payload,
                    "summary": summary,
                    "followup_status": state.get("status"),
                    "transcript": json.dumps(transcript),
                    "tools": json.dumps(tools),
                })
            else:
                conn.execute(text("""
                    INSERT INTO records (id, business_id, workflow_id, caller_name, caller_phone, intent, collected_data, ai_summary, urgency, followup_status, transcript, tools_executed, created_at)
                    VALUES (:id, :business_id, :workflow_id, :caller_name, :caller_phone, :intent, :collected_data, :summary, 'Normal', :followup_status, :transcript, :tools, :created_at)
                """), {
                    "id": record_id,
                    "business_id": business_id,
                    "workflow_id": workflow_id,
                    "caller_name": caller_name,
                    "caller_phone": caller_phone,
                    "intent": state.get("intent") or "UNCLASSIFIED",
                    "collected_data": payload,
                    "summary": summary,
                    "followup_status": state.get("status"),
                    "transcript": json.dumps(transcript),
                    "tools": json.dumps(tools),
                    "created_at": now,
                })
            conn.commit()
