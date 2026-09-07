import os
import json
import uuid
import re
import httpx
from datetime import datetime, timedelta, timezone
from sqlalchemy import text
from app.database import get_db_connection
from app.services.calendar_service import CalendarService
from app.services.external_api_service import ExternalApiService

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

        # Check Kanglish keywords
        kanglish_words = [
            'namaskara', 'kannada', 'beku', 'beki', 'yaavaga', 'samaya', 'yaake', 
            'hege', 'elli', 'nanna', 'nimma', 'houdu', 'illa', 'dhanyavada', 
            'madabeka', 'madi', 'naale', 'sanje', 'belagge', 'eshtu', 'gante', 
            'gantege', 'ide', 'aguthe', 'kano', 'hogi', 'sahaya', 'turtu'
        ]
        matches_kn = [w for w in kanglish_words if w in lower]
        if len(matches_kn) >= 1:
            return 'kn'

        # Check Hinglish keywords
        hinglish_words = [
            'namaste', 'namaskar', 'shukriya', 'dhanyawad', 'dhanyabad', 'kya', 
            'hai', 'hain', 'karna', 'karo', 'chahiye', 'kaise', 'bhai', 'haan', 
            'nahi', 'kal', 'aaj', 'shaam', 'samay', 'mujhe', 'aap', 'kitna', 
            'kitne', 'paisa', 'daam', 'kab', 'kaha', 'bhejo', 'bhej', 'batao', 
            'sunao', 'swagat', 'par', 'mein', 'madad'
        ]
        matches_hi = [w for w in hinglish_words if w in lower]
        if len(matches_hi) >= 1:
            return 'hi'

        return 'en'

    @staticmethod
    def extract_workflow_fields(fields: list, messages: list, collected_data: dict, groq_api_key: str = None) -> dict:
        user_texts = [m["content"] for m in messages if m.get("role") == "user"]
        if not user_texts:
            return {}

        latest_user = user_texts[-1]
        full_user = " ".join(user_texts[-4:])
        full_user_lower = full_user.lower()

        extracted = {}

        # 1. Groq LLM extraction (JSON Mode)
        if groq_api_key:
            try:
                extraction_prompt = (
                    f"You are a structured entity extraction engine for a customer service voice AI.\n"
                    f"Target Workflow Database Fields to extract:\n{json.dumps(fields, indent=2)}\n\n"
                    f"Already Extracted Fields:\n{json.dumps(collected_data, indent=2)}\n\n"
                    f"Caller Just Said: '{latest_user}' (Recent Context: '{full_user}')\n\n"
                    f"TASK:\n"
                    f"- Extract any values matching the target database fields that the caller mentioned.\n"
                    f"- If the caller speaks Hindi/Hinglish or Kannada/Kanglish, accurately map to the field values.\n"
                    f"- For select fields (e.g. order_type, delivery_preference, inquiry_type), map to the closest allowed option.\n"
                    f"- Do not hallucinate or make up values that the user has not mentioned.\n"
                    f"- Return ONLY a JSON object containing the newly detected key-value pairs (empty {{}} if none)."
                )
                with httpx.Client(timeout=6.0) as client:
                    resp = client.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers={"Authorization": f"Bearer {groq_api_key}", "Content-Type": "application/json"},
                        json={
                            "model": os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
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
                                if v not in [None, "", "null", "None"] and any(f["key"] == k for f in fields):
                                    extracted[k] = v
            except Exception as e:
                print(f"[Entity Extraction Notice] Groq extraction skipped: {e}")

        # 2. Rule & Regex Heuristic Fill (ensures zero failure even if Groq is slow or misses a field)
        field_keys = [f["key"] for f in fields]

        # Weight extraction (e.g. 1.5 kg, 2 kilo, 500g)
        if "weight_kg" in field_keys and "weight_kg" not in extracted and "weight_kg" not in collected_data:
            w_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:kg|kilo|kilos|pound|lb)', full_user_lower)
            if w_match:
                extracted["weight_kg"] = w_match.group(1)

        # Cake flavor extraction
        if "cake_flavor" in field_keys and "cake_flavor" not in extracted and "cake_flavor" not in collected_data:
            flav_match = re.search(r'(dark chocolate|chocolate|red velvet|vanilla|mango|black forest|pineapple|butterscotch|strawberry|choco chip|fruit|truffle|blueberry|butter scotch)', full_user_lower)
            if flav_match:
                extracted["cake_flavor"] = flav_match.group(1).title()

        # Order type
        if "order_type" in field_keys and "order_type" not in extracted and "order_type" not in collected_data:
            if any(w in full_user_lower for w in ["custom", "design", "photo cake", "theme"]):
                extracted["order_type"] = "Custom Design"
            elif any(w in full_user_lower for w in ["order", "cake", "buy", "place", "want", "need", "birthday", "anniversary", "pastry"]):
                extracted["order_type"] = "New Cake Order"
            elif any(w in full_user_lower for w in ["enquiry", "inquiry", "rate", "price", "menu", "cost"]):
                extracted["order_type"] = "General Enquiry"

        # Delivery preference
        if "delivery_preference" in field_keys and "delivery_preference" not in extracted and "delivery_preference" not in collected_data:
            if any(w in full_user_lower for w in ["delivery", "deliver", "home", "address", "send to", "drop"]):
                extracted["delivery_preference"] = "Home Delivery"
            elif any(w in full_user_lower for w in ["pickup", "pick up", "store", "takeaway", "collect", "baker"]):
                extracted["delivery_preference"] = "Store Pickup"

        # Tracking number
        if "tracking_number" in field_keys and "tracking_number" not in extracted and "tracking_number" not in collected_data:
            match_trk = re.search(r'TRK-[A-Z0-9-]+', full_user, re.IGNORECASE)
            if match_trk:
                extracted["tracking_number"] = match_trk.group(0).upper()

        # Logistics inquiry type
        if "inquiry_type" in field_keys and "inquiry_type" not in extracted and "inquiry_type" not in collected_data:
            if any(w in full_user_lower for w in ["delay", "late", "delayed", "not reached", "stuck"]):
                extracted["inquiry_type"] = "Delivery Delay"
            elif any(w in full_user_lower for w in ["address", "location", "change address", "redirect"]):
                extracted["inquiry_type"] = "Address Change"
            elif any(w in full_user_lower for w in ["status", "where is", "track", "tracking", "parcel", "package"]):
                extracted["inquiry_type"] = "Package Status"

        # Required Date & Time
        if "required_date" in field_keys and "required_date" not in extracted and "required_date" not in collected_data:
            has_date = any(w in full_user_lower for w in ["today", "tomorrow", "day after", "naale", "kal", "parso", "sanje", "evening", "morning", "pm", "am"])
            if has_date:
                d_str = "tomorrow" if ("tomorrow" in full_user_lower or "naale" in full_user_lower or "kal" in full_user_lower) else ("day after tomorrow" if ("day after" in full_user_lower or "parso" in full_user_lower) else "today")
                t_str = "18:00"
                for tm in re.finditer(r'(\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)?)', full_user_lower, re.I):
                    after_str = full_user_lower[tm.end():tm.end()+6]
                    if not re.match(r'^\s*(?:kg|kilo|pound|lb)', after_str):
                        t_str = tm.group(1)
                        break
                target_dt = CalendarService.parse_datetime_input(d_str, t_str)
                extracted["required_date"] = target_dt.isoformat()

        # Custom message
        if "custom_message" in field_keys and "custom_message" not in extracted and "custom_message" not in collected_data:
            msg_match = re.search(r'(?:write|message|text|says|name on cake)\s*[\'"]?([^\'"]+?)[\'"]?(?=\s+on|\s+for|\s+$)', full_user_lower)
            if msg_match:
                extracted["custom_message"] = msg_match.group(1).strip()

        # Budget
        if "budget_inr" in field_keys and "budget_inr" not in extracted and "budget_inr" not in collected_data:
            b_match = re.search(r'(?:rs|rupees|inr|budget|₹)\s*(\d+)', full_user_lower) or re.search(r'(\d+)\s*(?:rs|rupees|inr)', full_user_lower)
            if b_match:
                extracted["budget_inr"] = b_match.group(1)

        return extracted

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

        # 2. Extract newly mentioned fields from caller messages matching database fields
        groq_api_key = os.getenv("GROQ_API_KEY")
        extracted_new = AiService.extract_workflow_fields(fields, messages, collected_data_dict, groq_api_key)
        for k, v in extracted_new.items():
            collected_data_dict[k] = v

        if extracted_new:
            executed_tools.append({
                "tool": "extract_database_fields",
                "args": {"extracted_count": len(extracted_new), "fields": list(extracted_new.keys())},
                "result": f"Extracted database fields from caller: {json.dumps(extracted_new)}"
            })

        # 3. Determine missing required fields defined in workflow
        required_fields = [f for f in fields if f.get("required")]
        missing_required = [f for f in required_fields if f["key"] not in collected_data_dict or collected_data_dict[f["key"]] in [None, ""]]
        is_complete = (len(missing_required) == 0)

        if missing_required:
            executed_tools.append({
                "tool": "check_database_required_fields",
                "args": {
                    "collected_fields": list(collected_data_dict.keys()),
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

        industry = (workflow.get("industry") or business.get("industry") or "").lower()
        is_cake_shop = ("cake" in industry or "bakery" in industry or workflow.get("id") == "wf-cake-01")
        is_logistics = ("logistics" in industry or "delivery" in industry or workflow.get("id") == "wf-logistics-01")

        # 5. Domain Completion Actions (Triggered ONLY when all required fields have been collected!)
        if is_complete:
            if is_cake_shop:
                flavor = collected_data_dict.get("cake_flavor", "Belgian Dark Chocolate")
                weight = str(collected_data_dict.get("weight_kg", "1"))
                order_type = collected_data_dict.get("order_type", "New Cake Order")
                req_date = collected_data_dict.get("required_date") or datetime.now().isoformat()
                delivery_pref = collected_data_dict.get("delivery_preference", "Home Delivery")
                custom_msg = collected_data_dict.get("custom_message")
                budget = str(collected_data_dict.get("budget_inr", "2000"))
                cake_type = "Theme Custom Cake"
                if "birthday" in full_user_lower:
                    cake_type = "Birthday Cake"
                elif "anniversary" in full_user_lower:
                    cake_type = "Anniversary Cake"

                enq_id = f"ENQ-{str(uuid.uuid4())[:6].upper()}"
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

        if groq_api_key:
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
                        f"CRITICAL SPOKEN INSTRUCTIONS: "
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
                        f"CRITICAL SPOKEN INSTRUCTIONS: "
                        f"- Warmly confirm the customer's request has been successfully registered with their exact choices. "
                        f"- Naturally deliver or incorporate the closing message: '{workflow['closing_message']}'. "
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
            if not is_complete:
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
                        reply = f"{switch_prefix}Namaskara! Nimma cake order enquiry ({e_res.get('enquiry_id')}) submit agide ({e_res.get('weight_kg')}kg {e_res.get('flavor')} {e_res.get('cake_type')}, {e_res.get('delivery_preference')}). Shop owner {owner_n} ge alert kalisalaagide. {workflow['closing_message']}"
                    elif detected_lang == 'hi':
                        reply = f"{switch_prefix}Namaste! Aapka cake order enquiry ({e_res.get('enquiry_id')}) submit ho gaya hai ({e_res.get('weight_kg')}kg {e_res.get('flavor')} {e_res.get('cake_type')}, {e_res.get('delivery_preference')})! Shop owner {owner_n} ko summary bhej di gayi hai. {workflow['closing_message']}"
                    else:
                        reply = f"{switch_prefix}Thank you! Your cake order enquiry ({e_res.get('enquiry_id')}) for a {e_res.get('weight_kg')}kg {e_res.get('flavor')} ({e_res.get('delivery_preference')}) has been created! A summary has been sent to our shop owner {owner_n}. {workflow['closing_message']}"

                elif tracking_tool and tracking_tool.get("result"):
                    t_res = tracking_tool["result"]
                    if detected_lang == 'kn':
                        reply = f"{switch_prefix}Nimma package status check madalaagide. Tracking #{t_res.get('tracking_number')} '{t_res.get('status')}' nallide ({t_res.get('current_location')}). Delivery agent nimge contact madthare."
                    elif detected_lang == 'hi':
                        reply = f"{switch_prefix}Maine aapka package status check kiya hai. Tracking #{t_res.get('tracking_number')} abhi '{t_res.get('status')}' mein hai ({t_res.get('current_location')}). Driver contact karega."
                    else:
                        reply = f"{switch_prefix}I checked tracking number {t_res.get('tracking_number')}. It is currently '{t_res.get('status')}' at {t_res.get('current_location')}. Estimated delivery: {t_res.get('estimated_delivery', 'today')}."

                elif callback_tool and callback_tool.get("result", {}).get("success"):
                    cb_res = callback_tool["result"]
                    if detected_lang == 'kn':
                        reply = f"{switch_prefix}Nimma delivery support callback task ({cb_res.get('task_id')}) assign agide. Agent nimge {caller_phone} ge call madthare."
                    elif detected_lang == 'hi':
                        reply = f"{switch_prefix}Aapka delivery callback task ({cb_res.get('task_id')}) assign kar diya gaya hai. Agent aapko {caller_phone} par call karega."
                    else:
                        reply = f"{switch_prefix}A customer support callback task ({cb_res.get('task_id')}) has been registered. Our agent will call you back shortly at {caller_phone}."

                elif create_tool and create_tool.get("result", {}).get("success"):
                    c_res = create_tool["result"]
                    if detected_lang == 'kn':
                        reply = f"{switch_prefix}Namaskara! Nimma appointment confirm agide ({c_res.get('start_time')}). {workflow['closing_message']}"
                    elif detected_lang == 'hi':
                        reply = f"{switch_prefix}Aapka appointment confirm ho gaya hai ({c_res.get('start_time')})! {workflow['closing_message']}"
                    else:
                        reply = f"{switch_prefix}Your appointment has been successfully scheduled for {c_res.get('start_time')}! {workflow['closing_message']}"

                else:
                    if detected_lang == 'kn':
                        reply = f"{switch_prefix}Thumba dhanyavadagalu! {business['name']} ge nimma mahithi note madikollalaagide. {workflow['closing_message']}"
                    elif detected_lang == 'hi':
                        reply = f"{switch_prefix}Bahut dhanyawad! Maine aapke details ({business['name']}) note kar liye hain. {workflow['closing_message']}"
                    else:
                        reply = f"{switch_prefix}Thank you! I have captured all the necessary information for {business['name']}. {workflow['closing_message']}"

        # 8. DB Persistence & Automatic Follow-Up Tagging
        followup_status = "Completed" if is_complete else "Pending"
        if is_after_hours or urgency in ["Urgent", "Critical"]:
            followup_status = "Follow Up Needed"
            collected_data_dict["lead_status"] = "Follow Up Needed"
            collected_data_dict["urgency_tag"] = urgency

        now_str = datetime.now(timezone.utc).isoformat()
        full_transcript = messages + [{"role": "assistant", "content": reply}]
        tools_str = ", ".join(t["tool"] for t in executed_tools) or "None"
        summary = f"Caller ({caller_name}) contacted {business['name']} for {workflow['name']}. Status: {'Completed' if is_complete else 'Collecting Fields'}. Fields: {list(collected_data_dict.keys())}. Tools: {tools_str}. Urgency: {urgency}. Lang: {detected_lang.upper()}."

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
