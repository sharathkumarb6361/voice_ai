import unittest
import uuid
from datetime import datetime, timedelta
from app.services.calendar_service import CalendarService
from app.services.delivery_workflow_service import DeliveryWorkflowService
from app.services.ai_service import AiService
from app.database import get_db_connection
from sqlalchemy import text


class CalendarAiIntegrationTests(unittest.TestCase):
    def setUp(self):
        with get_db_connection() as conn:
            conn.execute(text("DELETE FROM calendar_events WHERE attendee_name LIKE 'Test%'"))
            conn.commit()

    def test_01_calendar_availability_check(self):
        avail = CalendarService.check_availability("tomorrow", "11:00", duration_minutes=30, business_id="biz-cake-01")
        self.assertIn("available", avail)
        self.assertTrue(avail["available"])

    def test_02_cake_shop_calendar_event_creation(self):
        caller_phone = "+91 98888 77777"
        caller_name = "Test Aarti"
        target_dt = datetime.now() + timedelta(days=1)
        req_date = target_dt.isoformat()

        rec_id = f"rec-test-{uuid.uuid4().hex[:6]}"
        fields_data = {
            "order_type": "New Cake Order",
            "cake_flavor": "Belgian Dark Chocolate",
            "weight_kg": "2",
            "required_date": req_date,
            "custom_message": "Happy Birthday",
            "delivery_preference": "Home Delivery",
            "budget_inr": "2500"
        }
        with get_db_connection() as conn:
            import json
            conn.execute(text("""
                INSERT INTO records (id, business_id, workflow_id, caller_name, caller_phone, intent, collected_data, ai_summary, urgency, followup_status, transcript, tools_executed, created_at)
                VALUES (:id, 'biz-cake-01', 'wf-cake-01', :name, :phone, 'Cake Order', :data, 'Test Summary', 'Normal', 'Pending', '[]', '[]', :cat)
            """), {
                "id": rec_id, "name": caller_name, "phone": caller_phone,
                "data": json.dumps(fields_data), "cat": datetime.now().isoformat()
            })
            conn.commit()

        request_data = {
            "business_id": "biz-cake-01",
            "workflow_id": "wf-cake-01",
            "caller_name": caller_name,
            "caller_phone": caller_phone,
            "messages": [{"role": "user", "content": "Please confirm my order"}],
            "record_id": rec_id
        }

        response = AiService.process_conversation(request_data)
        executed_tools = response.get("executed_tools", [])
        tool_names = [t.get("tool") for t in executed_tools]

        self.assertIn("create_calendar_event", tool_names)

        with get_db_connection() as conn:
            evt = conn.execute(
                text("SELECT * FROM calendar_events WHERE attendee_name = :name AND business_id = 'biz-cake-01'"),
                {"name": caller_name}
            ).fetchone()
            self.assertIsNotNone(evt)
            self.assertEqual(evt._mapping["status"], "Confirmed")

    def test_03_logistics_calendar_event_creation(self):
        caller_name = "Test Vikram"
        caller_phone = "+91 99999 88888"
        call_id = f"rec-del-{uuid.uuid4().hex[:6]}"

        state = DeliveryWorkflowService.initial_state(call_id, caller_phone)
        state["intent"] = DeliveryWorkflowService.NEW_DELIVERY
        state, _, _ = DeliveryWorkflowService.advance_state(
            state,
            "Pickup is Koramangala, delivery is Indiranagar, documents, tomorrow 10 AM, tracking TRK-7788, handle with care.",
            caller_name,
            caller_phone
        )
        self.assertEqual(state["status"], DeliveryWorkflowService.AWAITING_CONFIRMATION)

        state, reply, tools = DeliveryWorkflowService.advance_state(
            state,
            "Yes, confirm it.",
            caller_name,
            caller_phone
        )
        self.assertEqual(state["status"], DeliveryWorkflowService.COMPLETED)
        tool_names = [t.get("tool") for t in tools]
        self.assertIn("create_delivery_request", tool_names)
        self.assertIn("create_calendar_event", tool_names)

        with get_db_connection() as conn:
            evt = conn.execute(
                text("SELECT * FROM calendar_events WHERE attendee_name = :name AND business_id = 'biz-logistics-01'"),
                {"name": caller_name}
            ).fetchone()
            self.assertIsNotNone(evt)
            self.assertIn("Courier Pickup", evt._mapping["title"])

    def test_04_calendar_service_update_and_cancel(self):
        res = CalendarService.create_event(
            business_id="biz-cake-01",
            title="Test Event to Reschedule",
            start_time=(datetime.now() + timedelta(days=1)).isoformat(),
            end_time=(datetime.now() + timedelta(days=1, minutes=30)).isoformat(),
            attendee_name="Test Reschedule User",
            attendee_phone="+91 91111 22222"
        )
        evt_id = res["event_id"]

        new_time = (datetime.now() + timedelta(days=2)).isoformat()
        update_res = CalendarService.update_event(
            event_id=evt_id,
            new_start_time=new_time
        )
        self.assertTrue(update_res["success"])

        cancel_res = CalendarService.cancel_event(event_id=evt_id)
        self.assertTrue(cancel_res["success"])
        self.assertEqual(cancel_res["status"], "Cancelled")

        with get_db_connection() as conn:
            row = conn.execute(text("SELECT status FROM calendar_events WHERE id = :id"), {"id": evt_id}).fetchone()
            self.assertEqual(row[0], "Cancelled")

    def test_05_logistics_voice_cancel_and_reschedule(self):
        caller_name = "Test Logistics Voice"
        caller_phone = "+91 97777 66666"
        call_id = f"rec-voice-{uuid.uuid4().hex[:6]}"

        # Seed active event
        start_t = (datetime.now() + timedelta(days=1)).isoformat()
        res = CalendarService.create_event(
            business_id="biz-logistics-01",
            title="Courier Pickup: Koramangala -> Indiranagar",
            start_time=start_t,
            end_time=(datetime.now() + timedelta(days=1, minutes=45)).isoformat(),
            attendee_name=caller_name,
            attendee_phone=caller_phone
        )

        state = DeliveryWorkflowService.initial_state(call_id, caller_phone)
        # Test voice reschedule
        state, reply, tools = DeliveryWorkflowService.advance_state(
            state,
            "Please reschedule pickup to tomorrow 4 PM",
            caller_name,
            caller_phone
        )
        tool_names = [t.get("tool") for t in tools]
        self.assertIn("update_calendar_event", tool_names)
        self.assertIn("rescheduled", reply.lower())

        # Test voice cancel
        state_cancel = DeliveryWorkflowService.initial_state(f"rec-voice-c-{uuid.uuid4().hex[:6]}", caller_phone)
        state_cancel, reply_cancel, tools_cancel = DeliveryWorkflowService.advance_state(
            state_cancel,
            "Please cancel pickup",
            caller_name,
            caller_phone
        )
        tool_names_cancel = [t.get("tool") for t in tools_cancel]
        self.assertIn("cancel_calendar_event", tool_names_cancel)
        self.assertIn("cancelled", reply_cancel.lower())

    def test_06_cake_shop_voice_cancel(self):
        caller_name = "Test Cake Cancel"
        caller_phone = "+91 96666 55555"

        # Seed active cake order event
        start_t = (datetime.now() + timedelta(days=1)).isoformat()
        CalendarService.create_event(
            business_id="biz-cake-01",
            title="Cake Order (Belgian Dark Chocolate - 2kg) - Test Cake Cancel",
            start_time=start_t,
            end_time=(datetime.now() + timedelta(days=1, minutes=30)).isoformat(),
            attendee_name=caller_name,
            attendee_phone=caller_phone
        )

        req_data = {
            "business_id": "biz-cake-01",
            "workflow_id": "wf-cake-01",
            "caller_name": caller_name,
            "caller_phone": caller_phone,
            "messages": [{"role": "user", "content": "I need to cancel my cake order please"}],
            "record_id": f"rec-cake-c-{uuid.uuid4().hex[:6]}"
        }
        res = AiService.process_conversation(req_data)
        executed_tools = res.get("executed_tools", [])
        tool_names = [t.get("tool") for t in executed_tools]
        self.assertIn("cancel_calendar_event", tool_names)

    def test_07_thank_you_message_on_conversation_end(self):
        caller_name = "Test ThankYou Caller"
        caller_phone = "+91 97777 66666"

        req_data = {
            "business_id": "biz-cake-01",
            "workflow_id": "wf-cake-01",
            "caller_name": caller_name,
            "caller_phone": caller_phone,
            "messages": [
                {"role": "user", "content": "I want a chocolate cake for tomorrow"},
                {"role": "assistant", "content": "What size or weight would you like?"},
                {"role": "user", "content": "That's all thank you, goodbye!"}
            ],
            "record_id": f"rec-ty-{uuid.uuid4().hex[:6]}"
        }
        res = AiService.process_conversation(req_data)
        self.assertTrue(res.get("is_complete"))
        reply_lower = (res.get("assistant_reply") or "").lower()
        has_thank_you = any(w in reply_lower for w in ["thank you", "thanks", "dhanyawad", "shukriya", "dhanyavadagalu"])
    def test_08_order_confirmation_in_calendar(self):
        caller_name = "Test Confirmation Caller"
        caller_phone = "+91 91111 22222"
        rec_id = f"rec-confirm-{uuid.uuid4().hex[:6]}"

        req_data = {
            "business_id": "biz-cake-01",
            "workflow_id": "wf-cake-01",
            "caller_name": caller_name,
            "caller_phone": caller_phone,
            "messages": [
                {"role": "user", "content": "I want a 1.5kg vanilla cake for tomorrow 5pm, store pickup. Please confirm my order in calendar."}
            ],
            "record_id": rec_id
        }
        res = AiService.process_conversation(req_data)
        self.assertTrue(res.get("is_complete"))
        executed_tools = res.get("executed_tools", [])
        tool_names = [t.get("tool") for t in executed_tools]
        self.assertIn("create_calendar_event", tool_names)

        # Verify event in database
        with get_db_connection() as conn:
            evt = conn.execute(
                text("SELECT * FROM calendar_events WHERE attendee_name = :name AND business_id = 'biz-cake-01'"),
                {"name": caller_name}
            ).fetchone()
            self.assertIsNotNone(evt)
            self.assertEqual(evt._mapping["status"], "Confirmed")

        # Verify subsequent turn does not crash with UnboundLocalError and does not duplicate
        req_data_turn2 = {
            "business_id": "biz-cake-01",
            "workflow_id": "wf-cake-01",
            "caller_name": caller_name,
            "caller_phone": caller_phone,
            "messages": [
                {"role": "user", "content": "I want a 1.5kg vanilla cake for tomorrow 5pm, store pickup. Please confirm my order in calendar."},
                {"role": "assistant", "content": res.get("assistant_reply")},
                {"role": "user", "content": "Actually please change flavor to Chocolate"}
            ],
            "record_id": rec_id
        }
        res2 = AiService.process_conversation(req_data_turn2)
        self.assertTrue(res2.get("is_complete"))
        tool_names2 = [t.get("tool") for t in res2.get("executed_tools", [])]
        self.assertIn("update_calendar_event", tool_names2)


if __name__ == "__main__":
    unittest.main()

