import unittest
import uuid
import json
from datetime import datetime, timedelta
from app.services.ai_service import AiService
from app.services.langchain_service import LangChainService
from app.services.delivery_workflow_service import DeliveryWorkflowService
from app.database import get_db_connection
from sqlalchemy import text


class LangChainCorrectionTests(unittest.TestCase):
    def setUp(self):
        self.phone = "+91 98765 12345"
        self.name = "LangChain Test Caller"

    def test_01_langchain_service_direct_flavor_correction(self):
        """LangChain directly detects flavor correction, updates value, and asks next missing field without repeating flavor."""
        analysis = LangChainService.analyze_and_correct_turn(
            workflow={"name": "Cake Shop Order", "industry": "Bakery"},
            business={"name": "Sweet Treats Bakery"},
            fields=[
                {"key": "cake_flavor", "label": "Cake Flavor", "required": True},
                {"key": "weight_kg", "label": "Weight in kg", "required": True},
                {"key": "custom_message", "label": "Message on Cake", "required": True}
            ],
            collected_data={"cake_flavor": "Belgian Dark Chocolate", "weight_kg": "1"},
            current_question_field="custom_message",
            messages=[
                {"role": "assistant", "content": "What custom message would you like written on the cake?"},
                {"role": "user", "content": "Wait, actually change the flavor to Vanilla."}
            ],
            language="en"
        )
        self.assertTrue(analysis.is_correction)
        corrections = {c.field_key: c.new_value for c in analysis.corrections}
        self.assertEqual(corrections.get("cake_flavor"), "Vanilla")
        # Must not re-ask cake_flavor!
        self.assertNotEqual(analysis.next_field_to_ask, "cake_flavor")
        self.assertEqual(analysis.next_field_to_ask, "custom_message")
        reply_lower = analysis.natural_spoken_reply.lower()
        self.assertNotIn("what flavor", reply_lower)
        self.assertNotIn("which cake flavor", reply_lower)
        self.assertTrue("vanilla" in reply_lower or "update" in reply_lower)

    def test_02_langchain_conversation_flow_cake_flavor_update(self):
        """End-to-end conversation turn: user corrects flavor, database updates, question not repeated."""
        target_dt = (datetime.now() + timedelta(days=1)).isoformat()
        rec_id = f"rec-lc-{uuid.uuid4().hex[:6]}"
        fields_data = {
            "order_type": "New Cake Order",
            "cake_flavor": "Belgian Dark Chocolate",
            "weight_kg": "1",
            "required_date": target_dt,
            "custom_message": "Happy Birthday Rahul",
            "delivery_preference": "Home Delivery",
            "budget_inr": "2000"
        }

        with get_db_connection() as conn:
            conn.execute(text("""
                INSERT INTO records (id, business_id, workflow_id, caller_name, caller_phone, intent, collected_data, ai_summary, urgency, followup_status, transcript, tools_executed, created_at)
                VALUES (:id, 'biz-cake-01', 'wf-cake-01', :name, :phone, 'Cake Order', :data, 'Test Summary', 'Normal', 'Pending', '[]', '[]', :cat)
            """), {
                "id": rec_id, "name": self.name, "phone": self.phone,
                "data": json.dumps(fields_data), "cat": datetime.now().isoformat()
            })
            conn.commit()

        request_data = {
            "business_id": "biz-cake-01",
            "workflow_id": "wf-cake-01",
            "caller_name": self.name,
            "caller_phone": self.phone,
            "messages": [
                {"role": "assistant", "content": "Your 1kg Chocolate cake is all set. Anything else you need?"},
                {"role": "user", "content": "Actually, change the flavor to Vanilla."}
            ],
            "record_id": rec_id
        }

        response = AiService.process_conversation(request_data)
        collected = response["collected_data"]

        # 1. Existing value updated
        self.assertEqual(collected["cake_flavor"], "Vanilla")
        # 2. Existing values preserved
        self.assertEqual(collected["weight_kg"], "1")
        self.assertEqual(collected["custom_message"], "Happy Birthday Rahul")
        self.assertEqual(collected["delivery_preference"], "Home Delivery")

        # 3. Does NOT ask the flavor question again
        reply = response["assistant_reply"].lower()
        self.assertNotIn("what cake flavor", reply)
        self.assertNotIn("what flavor cake", reply)

        # 4. Tools recorded
        tools = [t["tool"] for t in response["executed_tools"]]
        self.assertTrue("update_database_field" in tools or "langchain_conversational_correction" in tools)

    def test_03_weight_correction_mid_stream(self):
        """User corrects weight to 2kg while assistant is asking for custom message."""
        rec_id = f"rec-lc-{uuid.uuid4().hex[:6]}"
        fields_data = {
            "order_type": "New Cake Order",
            "cake_flavor": "Red Velvet",
            "weight_kg": "1"
        }

        with get_db_connection() as conn:
            conn.execute(text("""
                INSERT INTO records (id, business_id, workflow_id, caller_name, caller_phone, intent, collected_data, ai_summary, urgency, followup_status, transcript, tools_executed, created_at)
                VALUES (:id, 'biz-cake-01', 'wf-cake-01', :name, :phone, 'Cake Order', :data, 'Test Summary', 'Normal', 'Pending', '[]', '[]', :cat)
            """), {
                "id": rec_id, "name": self.name, "phone": self.phone,
                "data": json.dumps(fields_data), "cat": datetime.now().isoformat()
            })
            conn.commit()

        request_data = {
            "business_id": "biz-cake-01",
            "workflow_id": "wf-cake-01",
            "caller_name": self.name,
            "caller_phone": self.phone,
            "messages": [
                {"role": "assistant", "content": "What date and time would you like the cake ready?"},
                {"role": "user", "content": "Actually make it 2kg, not 1kg"}
            ],
            "record_id": rec_id
        }

        response = AiService.process_conversation(request_data)
        collected = response["collected_data"]

        # Weight updated to 2
        self.assertEqual(str(collected["weight_kg"]), "2")
        # Flavor preserved
        self.assertEqual(collected["cake_flavor"], "Red Velvet")
        # Does NOT ask for weight again
        reply = response["assistant_reply"].lower()
        self.assertNotIn("how many kilograms", reply)
        self.assertNotIn("what weight", reply)

    def test_04_delivery_preference_correction(self):
        """User corrects from Home Delivery to Store Pickup using 'instead of'."""
        analysis = LangChainService.analyze_and_correct_turn(
            workflow={"name": "Cake Shop Order", "industry": "Bakery"},
            business={"name": "Sweet Treats Bakery"},
            fields=[
                {"key": "cake_flavor", "label": "Cake Flavor", "required": True},
                {"key": "delivery_preference", "label": "Delivery Preference", "required": True}
            ],
            collected_data={"cake_flavor": "Chocolate", "delivery_preference": "Home Delivery"},
            current_question_field="budget_inr",
            messages=[
                {"role": "assistant", "content": "What is your approximate budget in rupees?"},
                {"role": "user", "content": "Actually, I'll do store pickup instead of home delivery."}
            ],
            language="en"
        )
        self.assertTrue(analysis.is_correction)
        corrections = {c.field_key: c.new_value for c in analysis.corrections}
        self.assertEqual(corrections.get("delivery_preference"), "Store Pickup")
        self.assertNotEqual(analysis.next_field_to_ask, "delivery_preference")

    def test_05_logistics_delivery_address_correction(self):
        """User corrects delivery location in logistics workflow from Whitefield to Indiranagar."""
        state = DeliveryWorkflowService.initial_state("test-lc-call", self.phone)
        state["intent"] = DeliveryWorkflowService.NEW_DELIVERY
        state["status"] = DeliveryWorkflowService.COMPLETED
        state["collected_fields"] = {
            "pickup_location": "MG Road",
            "delivery_location": "Whitefield",
            "package_type": "documents",
            "preferred_time": "tomorrow 10 AM",
            "contact_details": self.phone,
            "tracking_number": "TRK-123456",
            "issue_description": "Standard Delivery"
        }

        new_state, reply, _ = DeliveryWorkflowService.advance_state(
            state, "Wait, deliver it to Indiranagar instead", self.name, self.phone
        )
        self.assertEqual(new_state["collected_fields"]["delivery_location"], "Indiranagar")
        self.assertEqual(new_state["collected_fields"]["pickup_location"], "MG Road")
        self.assertIn("indiranagar", reply.lower())

    def test_06_hindi_weight_correction(self):
        """Multi-lingual Hindi: 'Arey nahi, ek kilo nahi, do kilo kardo' updates weight to 2."""
        analysis = LangChainService.analyze_and_correct_turn(
            workflow={"name": "Cake Shop Order", "industry": "Bakery"},
            business={"name": "Sweet Treats Bakery"},
            fields=[
                {"key": "cake_flavor", "label": "Cake Flavor", "required": True},
                {"key": "weight_kg", "label": "Weight in kg", "required": True}
            ],
            collected_data={"cake_flavor": "Chocolate", "weight_kg": "1"},
            current_question_field="required_date",
            messages=[
                {"role": "assistant", "content": "Aapko cake kis taareekh ko chahiye?"},
                {"role": "user", "content": "Arey nahi, ek kilo nahi, do kilo kardo"}
            ],
            language="hi"
        )
        self.assertTrue(analysis.is_correction)
        corrections = {c.field_key: c.new_value for c in analysis.corrections}
        self.assertEqual(str(corrections.get("weight_kg")), "2")
        self.assertNotEqual(analysis.next_field_to_ask, "weight_kg")


if __name__ == "__main__":
    unittest.main()
