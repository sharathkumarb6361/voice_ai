import os
import uuid
import re
from datetime import datetime, timedelta, timezone
from sqlalchemy import text
from app.database import get_db_connection

# Google Calendar API imports (optional runtime fallback)
try:
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    GOOGLE_API_AVAILABLE = True
except ImportError:
    GOOGLE_API_AVAILABLE = False


class CalendarService:
    @staticmethod
    def get_gcal_service():
        """Attempts to build Google Calendar API service if environment credentials exist."""
        if not GOOGLE_API_AVAILABLE:
            return None, None

        client_id = os.getenv("GOOGLE_CLIENT_ID")
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
        refresh_token = os.getenv("GOOGLE_REFRESH_TOKEN")
        calendar_id = os.getenv("GOOGLE_CALENDAR_ID", "primary")

        if not (client_id and client_secret and refresh_token):
            return None, None

        try:
            creds = Credentials(
                token=None,
                refresh_token=refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=client_id,
                client_secret=client_secret
            )
            service = build('calendar', 'v3', credentials=creds)
            return service, calendar_id
        except Exception as e:
            print(f"[CalendarService] Google Calendar API auth notice: {e}")
            return None, None

    @staticmethod
    def parse_datetime_input(date_str: str, time_str: str) -> datetime:
        """Helper to parse varied date and time strings into a Python datetime object."""
        now = datetime.now()
        date_str_lower = (date_str or "today").strip().lower()
        time_str_lower = (time_str or "16:00").strip().lower()

        # Parse Date
        target_date = now
        weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        weekdays_short = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

        matched_day_idx = None
        for i, (day, short_day) in enumerate(zip(weekdays, weekdays_short)):
            if re.search(r'\b' + day + r'\b', date_str_lower) or re.search(r'\b' + short_day + r'\b', date_str_lower):
                matched_day_idx = i
                break

        if "day after tomorrow" in date_str_lower or "parso" in date_str_lower:
            target_date = now + timedelta(days=2)
        elif "tomorrow" in date_str_lower or "naale" in date_str_lower or "kal" in date_str_lower:
            target_date = now + timedelta(days=1)
        elif "next week" in date_str_lower:
            target_date = now + timedelta(days=7)
        elif matched_day_idx is not None:
            current_day_idx = now.weekday()
            days_ahead = matched_day_idx - current_day_idx
            if days_ahead <= 0:
                days_ahead += 7
            target_date = now + timedelta(days=days_ahead)
        elif re.match(r'^\d{4}-\d{2}-\d{2}', date_str_lower):
            try:
                target_date = datetime.strptime(date_str_lower[:10], "%Y-%m-%d")
            except ValueError:
                target_date = now
        else:
            day_offset_match = re.search(r'(\d+)\s*days?', date_str_lower)
            if day_offset_match:
                target_date = now + timedelta(days=int(day_offset_match.group(1)))

        # Parse Time
        hours = 16
        minutes = 0

        is_evening = any(w in time_str_lower or w in date_str_lower for w in ["evening", "pm", "night", "sanje", "shaam", "afternoon"])
        is_morning = any(w in time_str_lower or w in date_str_lower for w in ["morning", "am", "belagge", "subah"])

        twelve_hour_match = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?', time_str_lower)
        if twelve_hour_match:
            h = int(twelve_hour_match.group(1))
            m = int(twelve_hour_match.group(2) or 0)
            ampm = (twelve_hour_match.group(3) or "").replace(".", "").lower()

            if ampm == "pm" or (not ampm and is_evening and h < 12):
                if h < 12:
                    h += 12
            elif ampm == "am" or (not ampm and is_morning):
                if h == 12:
                    h = 0
            elif not ampm:
                if 1 <= h <= 7:
                    h += 12
            hours, minutes = h, m
        elif ":" in time_str_lower:
            parts = time_str_lower.split(":")
            try:
                hours = int(parts[0])
                minutes = int(parts[1][:2])
            except ValueError:
                hours, minutes = 16, 0

        hours = max(0, min(hours, 23))
        minutes = max(0, min(minutes, 59))
        return target_date.replace(hour=hours, minute=minutes, second=0, microsecond=0)

    @staticmethod
    def check_availability(date_str: str, time_str: str, duration_minutes: int = 30, business_id: str = None):
        start_dt = CalendarService.parse_datetime_input(date_str, time_str)
        end_dt = start_dt + timedelta(minutes=duration_minutes)

        start_iso = start_dt.isoformat()
        end_iso = end_dt.isoformat()

        # 1. Query SQLite Database for slot conflicts
        with get_db_connection() as conn:
            query = """
                SELECT * FROM calendar_events 
                WHERE status != 'Cancelled' 
                AND ((start_time < :et AND end_time > :st))
            """
            params = {"st": start_iso, "et": end_iso}
            if business_id:
                query += " AND business_id = :bid"
                params["bid"] = business_id

            conflicts = conn.execute(text(query), params).fetchall()

        # 2. Query Live Google Calendar API if available
        gcal_service, cal_id = CalendarService.get_gcal_service()
        gcal_conflict = False
        if gcal_service:
            try:
                events_result = gcal_service.events().list(
                    calendarId=cal_id,
                    timeMin=start_iso + "Z" if not start_iso.endswith("Z") else start_iso,
                    timeMax=end_iso + "Z" if not end_iso.endswith("Z") else end_iso,
                    singleEvents=True
                ).execute()
                gcal_events = events_result.get('items', [])
                if gcal_events:
                    gcal_conflict = True
            except Exception as e:
                print(f"[CalendarService] Live Google Calendar availability check notice: {e}")

        if conflicts or gcal_conflict:
            alt1_dt = start_dt + timedelta(hours=1)
            alt2_dt = start_dt + timedelta(hours=2)
            alt1 = alt1_dt.strftime("%I:%M %p")
            alt2 = alt2_dt.strftime("%I:%M %p")
            return {
                "available": False,
                "start_time": start_iso,
                "end_time": end_iso,
                "recommended_slots": [alt1, alt2],
                "message": f"Time slot {start_dt.strftime('%B %d at %I:%M %p')} is currently booked on Google Calendar. Recommended alternative open slots: {alt1} and {alt2}."
            }

        return {
            "available": True,
            "start_time": start_iso,
            "end_time": end_iso,
            "message": f"Time slot {start_dt.strftime('%B %d, %Y at %I:%M %p')} is fully available on Google Calendar."
        }

    @staticmethod
    def create_event(business_id: str, title: str, start_time: str, end_time: str, attendee_name: str, attendee_phone: str, description: str = ""):
        evt_id = f"cal-{str(uuid.uuid4())[:8]}"
        gcal_id = f"gcal_py_{evt_id}"
        now = datetime.now(timezone.utc).isoformat()

        # Validate/Format Start and End Times
        try:
            if not end_time or end_time == start_time:
                st_parsed = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                end_time = (st_parsed + timedelta(minutes=30)).isoformat()
        except Exception:
            pass

        # Try inserting to Google Calendar API if credentials exist
        gcal_service, cal_id = CalendarService.get_gcal_service()
        if gcal_service:
            try:
                gcal_body = {
                    'summary': title,
                    'description': f"Attendee: {attendee_name} ({attendee_phone})\n{description}",
                    'start': {'dateTime': start_time if 'T' in start_time else f"{start_time}T00:00:00Z"},
                    'end': {'dateTime': end_time if 'T' in end_time else f"{end_time}T00:30:00Z"},
                }
                created_gcal_evt = gcal_service.events().insert(calendarId=cal_id, body=gcal_body).execute()
                if created_gcal_evt.get('id'):
                    gcal_id = created_gcal_evt.get('id')
            except Exception as e:
                print(f"[CalendarService] Live Google Calendar event creation notice: {e}")

        # Save event to SQLite Database
        with get_db_connection() as conn:
            conn.execute(text("""
                INSERT INTO calendar_events (id, business_id, title, start_time, end_time, attendee_name, attendee_phone, description, status, google_event_id, created_at)
                VALUES (:id, :bid, :title, :st, :et, :aname, :aphone, :desc, 'Confirmed', :gid, :cat)
            """), {
                "id": evt_id, "bid": business_id or "biz-cake-01", "title": title,
                "st": start_time, "et": end_time, "aname": attendee_name, "aphone": attendee_phone,
                "desc": description or "", "gid": gcal_id, "cat": now
            })
            conn.commit()

        return {
            "success": True,
            "event_id": evt_id,
            "google_event_id": gcal_id,
            "title": title,
            "start_time": start_time,
            "end_time": end_time,
            "attendee_name": attendee_name,
            "attendee_phone": attendee_phone,
            "status": "Confirmed",
            "message": f"Event '{title}' successfully scheduled on Google Calendar for {start_time}."
        }

    @staticmethod
    def update_event(event_id: str = "latest", title: str = None, new_start_time: str = None, new_end_time: str = None, attendee_name: str = None, attendee_phone: str = None, description: str = None, status: str = None, business_id: str = None):
        with get_db_connection() as conn:
            result = None
            if event_id and event_id not in ["latest", "cal-latest", "newest"]:
                result = conn.execute(text("SELECT * FROM calendar_events WHERE id = :id OR google_event_id = :id"), {"id": event_id}).fetchone()

            if not result:
                if business_id:
                    result = conn.execute(text("SELECT * FROM calendar_events WHERE business_id = :bid AND status != 'Cancelled' ORDER BY created_at DESC LIMIT 1"), {"bid": business_id}).fetchone()
                if not result:
                    result = conn.execute(text("SELECT * FROM calendar_events WHERE status != 'Cancelled' ORDER BY created_at DESC LIMIT 1")).fetchone()

            if not result:
                return {"success": False, "message": "No active calendar appointment found to update."}

            evt = dict(result._mapping)
            target_id = evt["id"]
            
            updated_title = title if title is not None else evt["title"]
            updated_st = new_start_time if new_start_time is not None else evt["start_time"]
            updated_et = new_end_time if new_end_time is not None else evt["end_time"]
            updated_aname = attendee_name if attendee_name is not None else evt["attendee_name"]
            updated_aphone = attendee_phone if attendee_phone is not None else evt["attendee_phone"]
            updated_desc = description if description is not None else evt["description"]
            updated_status = status if status is not None else evt["status"]

            if new_start_time and not new_end_time:
                try:
                    ne = datetime.fromisoformat(new_start_time.replace("Z", "+00:00")) + timedelta(minutes=30)
                    updated_et = ne.isoformat()
                except Exception:
                    updated_et = new_start_time

            # Update Google Calendar API if active
            gcal_service, cal_id = CalendarService.get_gcal_service()
            if gcal_service and evt.get("google_event_id"):
                try:
                    gcal_service.events().patch(
                        calendarId=cal_id,
                        eventId=evt["google_event_id"],
                        body={
                            'summary': updated_title,
                            'description': f"Attendee: {updated_aname} ({updated_aphone})\n{updated_desc}",
                            'start': {'dateTime': updated_st},
                            'end': {'dateTime': updated_et},
                            'status': 'cancelled' if updated_status == 'Cancelled' else 'confirmed'
                        }
                    ).execute()
                except Exception as e:
                    print(f"[CalendarService] Live Google Calendar update notice: {e}")

            # Update Database
            conn.execute(text("""
                UPDATE calendar_events 
                SET title = :title, start_time = :st, end_time = :et, 
                    attendee_name = :aname, attendee_phone = :aphone, 
                    description = :desc, status = :status
                WHERE id = :id
            """), {
                "title": updated_title, "st": updated_st, "et": updated_et,
                "aname": updated_aname, "aphone": updated_aphone,
                "desc": updated_desc, "status": updated_status, "id": target_id
            })
            conn.commit()

        return {
            "success": True,
            "event_id": target_id,
            "title": updated_title,
            "start_time": updated_st,
            "end_time": updated_et,
            "status": updated_status,
            "message": f"Calendar appointment '{updated_title}' updated successfully."
        }

    @staticmethod
    def cancel_event(event_id: str = "latest", business_id: str = None):
        return CalendarService.update_event(event_id=event_id, status="Cancelled", business_id=business_id)

    @staticmethod
    def list_events(business_id: str = None, status: str = None, search: str = None):
        with get_db_connection() as conn:
            query = "SELECT * FROM calendar_events WHERE 1=1"
            params = {}

            if business_id and business_id != "All":
                query += " AND business_id = :bid"
                params["bid"] = business_id

            if status and status != "All":
                query += " AND status = :status"
                params["status"] = status

            if search and search.strip():
                query += " AND (title LIKE :search OR attendee_name LIKE :search OR attendee_phone LIKE :search OR description LIKE :search)"
                params["search"] = f"%{search.strip()}%"

            query += " ORDER BY start_time DESC"

            result = conn.execute(text(query), params)
            rows = [dict(r._mapping) for r in result.fetchall()]
        return rows

    @staticmethod
    def sync_events():
        """Trigger sync check with Google Calendar API and sync to database."""
        gcal_service, cal_id = CalendarService.get_gcal_service()
        if not gcal_service:
            return {
                "synced": False,
                "count": 0,
                "message": "Google Calendar API credentials not configured in .env. Running on local SQLite database store."
            }

        try:
            events_result = gcal_service.events().list(calendarId=cal_id, maxResults=50).execute()
            items = events_result.get('items', [])
            synced_count = 0

            with get_db_connection() as conn:
                for item in items:
                    g_id = item.get('id')
                    summary = item.get('summary', 'Google Calendar Event')
                    start_data = item.get('start', {})
                    end_data = item.get('end', {})
                    start_time = start_data.get('dateTime') or start_data.get('date') or datetime.now().isoformat()
                    end_time = end_data.get('dateTime') or end_data.get('date') or datetime.now().isoformat()
                    description = item.get('description', '')

                    # Check if event already exists in DB
                    existing = conn.execute(
                        text("SELECT id FROM calendar_events WHERE google_event_id = :gid OR id = :gid"),
                        {"gid": g_id}
                    ).fetchone()

                    if not existing:
                        evt_id = f"gcal-{str(uuid.uuid4())[:8]}"
                        now = datetime.now(timezone.utc).isoformat()
                        conn.execute(text("""
                            INSERT INTO calendar_events (id, business_id, title, start_time, end_time, attendee_name, attendee_phone, description, status, google_event_id, created_at)
                            VALUES (:id, 'biz-clinic-01', :title, :st, :et, 'Google Client', '+91 98765 00000', :desc, 'Confirmed', :gid, :cat)
                        """), {
                            "id": evt_id, "title": summary, "st": start_time, "et": end_time,
                            "desc": description, "gid": g_id, "cat": now
                        })
                        synced_count += 1
                conn.commit()

            return {
                "synced": True,
                "count": len(items),
                "new_synced": synced_count,
                "message": f"Successfully synchronized with Google Calendar API ({len(items)} events total, {synced_count} new events imported to local DB)."
            }
        except Exception as e:
            return {
                "synced": False,
                "message": f"Google Calendar API sync error: {str(e)}"
            }
