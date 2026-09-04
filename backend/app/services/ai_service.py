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

        collected_data_dict = {}

        # 1. Google Calendar Tool Triggers
        calendar_keywords = [
            "schedule", "book", "appointment", "site visit", "tomorrow", "4 pm", "10 am",
            "reschedule", "cancel", "change", "time", "pm", "am", "p.m.", "a.m.", "slot",
            "move", "shift", "update", "set", "beku", "naale", "kal", "chahiye",
            "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
            "order", "cake", "bakery", "pastry", "delivery", "pickup", "flavor", "flavour", "kg", "sweet"
        ]
        if any(k in user_lower for k in calendar_keywords):
            if "cancel" in user_lower and ("event" in user_lower or "appointment" in user_lower or "order" in user_lower):
                res = CalendarService.cancel_event("latest", business_id=business_id)
                executed_tools.append({"tool": "cancel_calendar_event", "args": {"event_id": "latest"}, "result": res})
                if res.get("success"):
                    collected_data_dict["appointment_status"] = "Cancelled"
            elif any(w in user_lower for w in ["reschedule", "change", "move", "shift", "update", "set"]):
                time_match = "16:00"
                for m in re.finditer(r'(\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)?)', user_lower, re.IGNORECASE):
                    after_str = user_lower[m.end():m.end()+6]
                    if not re.match(r'^\s*(?:kg|kilo|pound|lb)', after_str):
                        time_match = m.group(1)
                        break
                date_match = "day after tomorrow" if ("day after" in user_lower or "parso" in user_lower) else ("tomorrow" if ("tomorrow" in user_lower or "kal" in user_lower or "naale" in user_lower) else "today")
                target_dt = CalendarService.parse_datetime_input(date_match, time_match)
                new_start = target_dt.isoformat()
                new_end = (target_dt + timedelta(minutes=30)).isoformat()
                res = CalendarService.update_event("latest", new_start_time=new_start, new_end_time=new_end, business_id=business_id)
                executed_tools.append({"tool": "update_calendar_event", "args": {"event_id": "latest", "start_time": new_start}, "result": res})
                if res.get("success"):
                    collected_data_dict["appointment"] = {
                        "event_id": res.get("event_id"),
                        "title": res.get("title"),
                        "start_time": new_start,
                        "status": "Rescheduled"
                    }
            else:
                date_match = "tomorrow" if ("tomorrow" in user_lower or "naale" in user_lower or "kal" in user_lower) else ("day after tomorrow" if ("day after" in user_lower or "parso" in user_lower) else "today")
                time_match = "16:00"
                
                # Find all potential time matches excluding weight suffixes (e.g. 2kg)
                for m in re.finditer(r'(\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)?)', user_lower, re.IGNORECASE):
                    after_str = user_lower[m.end():m.end()+6]
                    if not re.match(r'^\s*(?:kg|kilo|pound|lb)', after_str):
                        time_match = m.group(1)
                        break

                check_res = CalendarService.check_availability(date_match, time_match, 30, business_id=business_id)
                executed_tools.append({
                    "tool": "check_calendar_availability",
                    "args": {"date": date_match, "time": time_match, "business": business["name"]},
                    "result": check_res
                })

                if check_res.get("available") is True:
                    start_iso = check_res.get("start_time")
                    end_iso = check_res.get("end_time")

                    # Extract cake / order metadata if present
                    flavor = "Custom"
                    flav_match = re.search(r'(dark chocolate|chocolate|red velvet|vanilla|mango|black forest|pineapple|butterscotch|strawberry)', user_lower)
                    if flav_match:
                        flavor = flav_match.group(1).title()

                    weight = "1"
                    w_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:kg|kilo|pound|lb)', user_lower)
                    if w_match:
                        weight = w_match.group(1)

                    if workflow.get("industry") == "Cake Shop" or "cake" in user_lower or "order" in user_lower:
                        evt_title = f"Cake Order ({flavor} - {weight}kg) - {caller_name}"
                        evt_desc = f"Voice AI Cake Order: {flavor} ({weight}kg). Customer: {caller_name} ({caller_phone}). Business: {business['name']}"
                    else:
                        evt_title = f"{workflow['industry']} - {caller_name}"
                        evt_desc = f"Scheduled via Voice AI Assistant ({workflow['name']})"

                    create_res = CalendarService.create_event(
                        business_id=business_id,
                        title=evt_title,
                        start_time=start_iso,
                        end_time=end_iso,
                        attendee_name=caller_name,
                        attendee_phone=caller_phone,
                        description=evt_desc
                    )
                    executed_tools.append({
                        "tool": "create_calendar_event",
                        "args": {"title": evt_title, "start_time": start_iso},
                        "result": create_res
                    })
                    if create_res.get("success"):
                        collected_data_dict["appointment"] = {
                            "event_id": create_res.get("event_id"),
                            "google_event_id": create_res.get("google_event_id"),
                            "title": create_res.get("title"),
                            "start_time": start_iso,
                            "end_time": end_iso,
                            "flavor": flavor,
                            "weight_kg": weight,
                            "status": "Confirmed"
                        }

        # 2. External REST API & Logistics Tool Triggers
        if any(k in user_lower for k in ["new delivery", "schedule delivery", "send package", "ship parcel", "pickup location", "dispatch parcel"]):
            pickup = "Indiranagar, Bengaluru"
            p_match = re.search(r'from\s+([a-zA-Z0-9\s]+?)(?=\s+to|\s+at|\s+for|\s+$)', user_lower, re.IGNORECASE)
            if p_match:
                pickup = p_match.group(1).title()

            delivery = "Whitefield, Bengaluru"
            d_match = re.search(r'to\s+([a-zA-Z0-9\s]+?)(?=\s+tomorrow|\s+today|\s+at|\s+for|\s+on|\s+$)', user_lower, re.IGNORECASE)
            if d_match:
                delivery = d_match.group(1).strip().title()

            pkg_type = "Parcel / Box"
            if any(w in user_lower for w in ["document", "file", "paper"]):
                pkg_type = "Documents & Files"
            elif any(w in user_lower for w in ["electronic", "laptop", "phone"]):
                pkg_type = "Electronics"
            elif any(w in user_lower for w in ["fragile", "glass"]):
                pkg_type = "Fragile Item"

            pref_time = "Tomorrow 4:00 PM"
            if "today" in user_lower:
                pref_time = "Today 5:00 PM"

            del_res = ExternalApiService.create_delivery_request(
                pickup_location=pickup,
                delivery_location=delivery,
                package_type=pkg_type,
                preferred_time=pref_time,
                caller_name=caller_name,
                caller_phone=caller_phone
            )
            executed_tools.append({
                "tool": "create_delivery_request",
                "args": {"pickup": pickup, "delivery": delivery, "package_type": pkg_type},
                "result": del_res
            })
            collected_data_dict["new_delivery_request"] = del_res

        if any(k in user_lower for k in ["help", "support", "issue", "callback", "delayed", "complaint", "agent"]):
            match = re.search(r'TRK-[A-Z0-9-]+', last_user_msg, re.IGNORECASE)
            tracking_no = match.group(0).upper() if match else None

            cb_res = ExternalApiService.create_callback_task(
                issue_summary="Customer requested support / help with existing delivery",
                tracking_number=tracking_no,
                caller_name=caller_name,
                caller_phone=caller_phone
            )
            executed_tools.append({
                "tool": "create_callback_task",
                "args": {"issue": "Delivery Support Callback", "tracking_number": tracking_no},
                "result": cb_res
            })
            collected_data_dict["callback_task"] = cb_res

        if any(k in user_lower for k in ["trk-", "track", "package", "parcel", "where is", "status"]):
            match = re.search(r'TRK-[A-Z0-9-]+', last_user_msg, re.IGNORECASE)
            tracking_no = match.group(0).upper() if match else "TRK-9821-IN"

            tracking_res = ExternalApiService.track_delivery_status(tracking_no)
            executed_tools.append({
                "tool": "track_delivery_status",
                "args": {"tracking_number": tracking_no},
                "result": tracking_res
            })
            collected_data_dict["tracking_number"] = tracking_no
            collected_data_dict["delivery_status"] = tracking_res.get("status")

        if any(k in user_lower for k in ["crm", "customer profile", "history"]):
            crm_res = ExternalApiService.lookup_crm_customer(caller_phone)
            executed_tools.append({
                "tool": "lookup_crm_customer",
                "args": {"phone_number": caller_phone},
                "result": crm_res
            })
            collected_data_dict["crm_profile"] = crm_res

        # 3. Evaluate conditional rules
        urgency = "Normal"
        for cond in conditions:
            if cond.get("field") == "required_date" and cond.get("operator") == "within_hours":
                if any(k in user_lower for k in ["tomorrow", "today", "24 hour", "urgent", "naale", "kal", "jaldi"]):
                    urgency = "Urgent"
                    executed_tools.append({
                        "tool": "evaluate_conditional_rule",
                        "args": {"condition": cond.get("note", "Required within 24 hours")},
                        "result": "Rule Triggered: Flagged as URGENT"
                    })
            if cond.get("field") == "urgency_level" and ("emergency" in user_lower or "turtu" in user_lower or "zaruri" in user_lower):
                urgency = "Critical"
                executed_tools.append({
                    "tool": "evaluate_conditional_rule",
                    "args": {"condition": "Immediate Emergency"},
                    "result": "Rule Triggered: Flagged as CRITICAL"
                })

        # 4. Groq API Integration (If GROQ_API_KEY is configured in .env)
        groq_api_key = os.getenv("GROQ_API_KEY")
        reply = None

        switch_prefix = ""
        if language_switched:
            lang_names = {"en": "English", "hi": "Hindi (हिन्दी)", "kn": "Kannada (ಕನ್ನಡ)"}
            switch_prefix = f"*(Language switched to {lang_names.get(detected_lang, 'English')})* "

        if groq_api_key:
            try:
                print(f"[Groq LLM Engine] Processing request with Llama 3.3 on Groq LPUs...")
                tools_summary = json.dumps(executed_tools) if executed_tools else "None"
                after_hours_note = f"CLOSED (After-Hours). Call received outside business hours ({b_hours.get('after_hours_greeting', '')}). Process caller request accurately (e.g. rescheduling/booking) while politely reminding them of operating hours." if (is_after_hours and b_hours) else "OPEN"
                sys_prompt = (
                    f"You are a professional Voice AI Assistant for business '{business['name']}' ({workflow['industry']}). "
                    f"Workflow: '{workflow['name']}'. Default Greeting: '{workflow['greeting']}'. Closing Message: '{workflow['closing_message']}'. "
                    f"Operating Hours Status: {after_hours_note}. "
                    f"Caller Name: '{caller_name}', Phone: '{caller_phone}'. "
                    f"Executed Tools Data: {tools_summary}. Urgency Level: {urgency}. "
                    f"MUST respond in target language code '{detected_lang.upper()}' (en=English, hi=Hindi/Hinglish, kn=Kannada/Kanglish). "
                    f"Keep responses natural, helpful, polite, and concise (under 3 sentences) for speech playback."
                )
                groq_messages = [{"role": "system", "content": sys_prompt}]
                for m in messages[-4:]:
                    groq_messages.append({"role": m.get("role", "user"), "content": m.get("content", "")})

                with httpx.Client(timeout=10.0) as client:
                    resp = client.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers={"Authorization": f"Bearer {groq_api_key}", "Content-Type": "application/json"},
                        json={
                            "model": "llama-3.3-70b-versatile",
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
                            "args": {"model": "llama-3.3-70b-versatile", "latency": "ultra-fast LPU"},
                            "result": f"Generated dynamic response via Groq Cloud API in {detected_lang.upper()}"
                        })
            except Exception as e:
                print(f"Groq API call notice ({e}), continuing with local rule engine...")

        # Fallback response generation if Groq API key is not set or failed
        if not reply:
            switch_prefix = ""
            if language_switched:
                lang_names = {"en": "English", "hi": "Hindi (हिन्दी)", "kn": "Kannada (ಕನ್ನಡ)"}
                switch_prefix = f"*(Language switched to {lang_names.get(detected_lang, 'English')})* "

            # Check if creation succeeded
            create_tool = next((t for t in executed_tools if t["tool"] == "create_calendar_event"), None)
            check_tool = next((t for t in executed_tools if t["tool"] == "check_calendar_availability"), None)
            cancel_tool = next((t for t in executed_tools if t["tool"] == "cancel_calendar_event"), None)
            update_tool = next((t for t in executed_tools if t["tool"] == "update_calendar_event"), None)

            if create_tool and create_tool.get("result", {}).get("success"):
                c_res = create_tool["result"]
                st_formatted = c_res.get("start_time", "tomorrow")
                try:
                    dt = datetime.fromisoformat(st_formatted.replace("Z", "+00:00"))
                    st_formatted = dt.strftime("%B %d at %I:%M %p")
                except Exception:
                    pass

                if detected_lang == 'kn':
                    reply = f"{switch_prefix}Namaskara! Nimma appointment Google Calendar nalli confirm agide ({st_formatted}). {workflow['closing_message']}"
                elif detected_lang == 'hi':
                    reply = f"{switch_prefix}Aapka appointment Google Calendar par confirm ho gaya hai ({st_formatted})! {workflow['closing_message']}"
                else:
                    reply = f"{switch_prefix}Your appointment has been successfully scheduled on Google Calendar for {st_formatted}! {workflow['closing_message']}"
            elif check_tool and check_tool.get("result", {}).get("available") is False:
                chk_res = check_tool["result"]
                rec_slots = ", ".join(chk_res.get("recommended_slots", ["5:00 PM", "6:00 PM"]))
                if detected_lang == 'kn':
                    reply = f"{switch_prefix}Namaskara! Nimma requested time slot Google Calendar nalli already book agide. Alternative open slots: {rec_slots}. Eavudanna book madabeka?"
                elif detected_lang == 'hi':
                    reply = f"{switch_prefix}Namaste! Aapka maanga hua time slot Google Calendar par pehle se booked hai. Subah/shaam ke recommended open slots: {rec_slots} hain. Kya aap inme se koi slot book karna chahenge?"
                else:
                    reply = f"{switch_prefix}Your requested time slot is currently booked on Google Calendar. Recommended available open slots: {rec_slots}. Would you like me to book one of these for you?"
            elif cancel_tool:
                if detected_lang == 'kn':
                    reply = f"{switch_prefix}Nimma appointment cancel madalaagide. Dhanyavada!"
                elif detected_lang == 'hi':
                    reply = f"{switch_prefix}Aapka appointment cancel kar diya gaya hai. Dhanyawad!"
                else:
                    reply = f"{switch_prefix}Your appointment has been cancelled successfully. Thank you!"
            elif update_tool:
                if detected_lang == 'kn':
                    reply = f"{switch_prefix}Nimma appointment update madalaagide ({new_start if 'new_start' in locals() else 'new time'}). {workflow['closing_message']}"
                elif detected_lang == 'hi':
                    reply = f"{switch_prefix}Aapka appointment reschedule kar diya gaya hai. {workflow['closing_message']}"
                else:
                    reply = f"{switch_prefix}Your appointment has been rescheduled successfully! {workflow['closing_message']}"
            elif any(t["tool"] == "create_delivery_request" for t in executed_tools):
                d_res = next((t["result"] for t in executed_tools if t["tool"] == "create_delivery_request"), {})
                if detected_lang == 'kn':
                    reply = f"{switch_prefix}Namaskara! Nimma hosadhu delivery request {d_res.get('delivery_id')} confirm agide ({d_res.get('pickup_location')} -> {d_res.get('delivery_location')}). {workflow['closing_message']}"
                elif detected_lang == 'hi':
                    reply = f"{switch_prefix}Aapka naya delivery request {d_res.get('delivery_id')} register ho gaya hai ({d_res.get('pickup_location')} se {d_res.get('delivery_location')})! {workflow['closing_message']}"
                else:
                    reply = f"{switch_prefix}Your new delivery request ({d_res.get('delivery_id')}) from {d_res.get('pickup_location')} to {d_res.get('delivery_location')} has been successfully registered! {workflow['closing_message']}"
            elif any(t["tool"] == "create_callback_task" for t in executed_tools):
                cb_res = next((t["result"] for t in executed_tools if t["tool"] == "create_callback_task"), {})
                if detected_lang == 'kn':
                    reply = f"{switch_prefix}Nimma delivery support callback task ({cb_res.get('task_id')}) dispatch team ge assign agide. Agent nimge call madthare."
                elif detected_lang == 'hi':
                    reply = f"{switch_prefix}Aapka delivery support callback task ({cb_res.get('task_id')}) dispatch team ko assign kar diya gaya hai. Agent aapko call karega."
                else:
                    reply = f"{switch_prefix}A dispatch callback task ({cb_res.get('task_id')}) has been assigned to our customer support team regarding your delivery inquiry. Our agent will call you back shortly."
            elif any(t["tool"] == "track_delivery_status" for t in executed_tools):
                t_res = next((t["result"] for t in executed_tools if t["tool"] == "track_delivery_status"), {})
                if detected_lang == 'kn':
                    reply = f"{switch_prefix}Nimma package status check madalaagide. Tracking #{t_res.get('tracking_number')} '{t_res.get('status')}' nallide ({t_res.get('current_location')}). Delivery agent nimge contact madthare."
                elif detected_lang == 'hi':
                    reply = f"{switch_prefix}Maine aapka package status check kiya hai. Tracking #{t_res.get('tracking_number')} abhi '{t_res.get('status')}' mein hai ({t_res.get('current_location')}). Agent {t_res.get('driver_name', 'Rohan')} contact karega."
                else:
                    reply = f"{switch_prefix}I queried our delivery API. Tracking #{t_res.get('tracking_number')} is currently '{t_res.get('status')}' at {t_res.get('current_location')}."
            elif len(messages) <= 1 and is_after_hours and b_hours and b_hours.get("after_hours_greeting"):
                reply = f"{switch_prefix}{b_hours['after_hours_greeting']}"
            elif len(messages) <= 2:
                if detected_lang == 'kn':
                    reply = f"{switch_prefix}Namaskara! {business['name']} ge swagatha. Naavu nimma call miss madidve. Nimge hege sahaya madabeku?"
                elif detected_lang == 'hi':
                    reply = f"{switch_prefix}Namaste! {business['name']} mein aapka swagat hai. Humne aapka missed call dekha. Hum aapki kya madad kar sakte hain?"
                else:
                    reply = f"{switch_prefix}{workflow['greeting']}"
            else:
                if is_after_hours and b_hours and b_hours.get("after_hours_greeting"):
                    reply = f"{switch_prefix}Thank you! We have logged your request. Note that our operating hours are Mon-Sat 9 AM to 6 PM."
                elif detected_lang == 'kn':
                    reply = f"{switch_prefix}Thumba dhanyavadagalu! {business['name']} ge nimma mahithi note madikollalaagide. {workflow['closing_message']}"
                elif detected_lang == 'hi':
                    reply = f"{switch_prefix}Bahut dhanyawad! Maine aapke details ({business['name']}) note kar liye hain. {workflow['closing_message']}"
                else:
                    reply = f"{switch_prefix}Thank you! I have captured all the necessary information for {business['name']}. {workflow['closing_message']}"

        # 5. DB Persistence & Automatic Follow-Up Tagging
        followup_status = "Follow Up Needed" if (is_after_hours or urgency in ["Urgent", "Critical"]) else "Pending"
        if is_after_hours or urgency in ["Urgent", "Critical"]:
            collected_data_dict["lead_status"] = "Follow Up Needed"
            collected_data_dict["urgency_tag"] = urgency

        rec_id = request_data.get("record_id") or f"rec-{str(uuid.uuid4())[:8]}"
        now_str = datetime.now(timezone.utc).isoformat()
        full_transcript = messages + [{"role": "assistant", "content": reply}]
        tools_str = ", ".join(t["tool"] for t in executed_tools) or "None"
        summary = f"Caller ({caller_name}) contacted {business['name']} for {workflow['name']}. Tools executed: {tools_str}. Priority: {urgency}. Language: {detected_lang.upper()} (Switched: {language_switched})."

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
            "executed_tools": executed_tools
        }
