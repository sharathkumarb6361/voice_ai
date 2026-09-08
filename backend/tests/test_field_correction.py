import unittest
import uuid
import json
from datetime import datetime, timedelta
from app.services.ai_service import AiService
from app.services.delivery_workflow_service import DeliveryWorkflowService
from app.database import get_db_connection
from sqlalchemy import text


class FieldCorrectionTests(unittest.TestCase):
    def setUp(self):
        self.phone = "+91 98765 12345"
        self.name = "Test Caller"

    def test_01_cake_flavor_correction_updates_value_and_preserves_other_fields(self):
        """When user corrects cake flavor from Chocolate to Vanilla, it updates flavor and preserves weight and date."""
        target_dt = (datetime.now() + timedelta(days=1)).isoformat()
        rec_id = f"rec-test-{uuid.uuid4().hex[:6]}"
        fields_data = {
            "order_type": "New Cake Order",
            "cake_flavor": "Belgian Dark Chocolate",
            "weight_kg": "1",
            "required_date": target_dt,
            "custom_message": "Happy Birthday",
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
                {"role": "assistant", "content": "Your 1kg Belgian Dark Chocolate cake is confirmed. Anything else?"},
                {"role": "user", "content": "Actually, change the flavor to Vanilla."}
            ],
            "record_id": rec_id
        }

        response = AiService.process_conversation(request_data)
        collected = response["collected_data"]

        # 1. Field updated with latest valid value
        self.assertEqual(collected["cake_flavor"], "Vanilla")
        # 2. Previously collected fields preserved
        self.assertEqual(collected["weight_kg"], "1")
        self.assertEqual(collected["required_date"], target_dt)
        self.assertEqual(collected["delivery_preference"], "Home Delivery")
        self.assertEqual(collected["custom_message"], "Happy Birthday")
        self.assertEqual(collected["budget_inr"], "2000")

        # 3. Does NOT ask the flavor question again
        reply = response["assistant_reply"].lower()
        self.assertNotIn("what cake flavor", reply)
        self.assertNotIn("which cake flavor would you like", reply)

        # 4. update_database_field tool was recorded
        tools = [t["tool"] for t in response["executed_tools"]]
        self.assertIn("update_database_field", tools)

    def test_02_weight_correction_updates_value(self):
        """User corrects weight from 1kg to 2kg."""
        rec_id = f"rec-test-{uuid.uuid4().hex[:6]}"
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
                {"role": "assistant", "content": "What date and time do you need the cake ready?"},
                {"role": "user", "content": "Actually make it 2kg, and I need it tomorrow at 6 PM"}
            ],
            "record_id": rec_id
        }

        response = AiService.process_conversation(request_data)
        collected = response["collected_data"]

        # Weight updated to 2
        self.assertEqual(str(collected["weight_kg"]), "2")
        # Flavor preserved
        self.assertEqual(collected["cake_flavor"], "Red Velvet")
        # Required date added
        self.assertTrue(bool(collected.get("required_date")))
        # Never ask for weight or flavor again
        reply = response["assistant_reply"].lower()
        self.assertNotIn("how many kilograms", reply)
        self.assertNotIn("what weight", reply)

    def test_03_delivery_preference_correction(self):
        """User changes from Home Delivery to Store Pickup using 'instead of' phrase."""
        fields_data = {
            "cake_flavor": "Chocolate",
            "weight_kg": "1",
            "delivery_preference": "Home Delivery"
        }
        fields = [{"key": "delivery_preference", "label": "Delivery Preference", "required": True}]
        extracted = AiService.extract_workflow_fields(
            fields=fields,
            messages=[{"role": "user", "content": "Store pickup instead of delivery please"}],
            collected_data=fields_data
        )
        self.assertEqual(extracted.get("delivery_preference"), "Store Pickup")

    def test_04_ambiguous_flavor_correction_requests_clarification(self):
        """When user says 'Can I change the flavor?' without naming a flavor, ask for clarification."""
        fields_data = {
            "cake_flavor": "Chocolate",
            "weight_kg": "1"
        }
        fields = [{"key": "cake_flavor", "label": "Cake Flavor", "required": True}]
        extracted = AiService.extract_workflow_fields(
            fields=fields,
            messages=[{"role": "user", "content": "Can I change the flavor?"}],
            collected_data=fields_data
        )
        self.assertNotIn("cake_flavor", extracted)

        is_ambig, target_field, clarif_q = AiService.detect_ambiguous_correction(
            "Can I change the flavor?", fields, fields_data, extracted
        )
        self.assertTrue(is_ambig)
        self.assertEqual(target_field, "cake_flavor")
        self.assertIn("Which cake flavor would you like instead", clarif_q)

    def test_05_ambiguous_delivery_correction_requests_clarification(self):
        """When user says 'I want to change the delivery option', ask for clarification."""
        fields_data = {
            "cake_flavor": "Chocolate",
            "delivery_preference": "Home Delivery"
        }
        fields = [{"key": "delivery_preference", "label": "Delivery Preference", "required": True}]
        extracted = AiService.extract_workflow_fields(
            fields=fields,
            messages=[{"role": "user", "content": "I want to change the delivery preference"}],
            collected_data=fields_data
        )
        self.assertNotIn("delivery_preference", extracted)

        is_ambig, target_field, clarif_q = AiService.detect_ambiguous_correction(
            "I want to change the delivery preference", fields, fields_data, extracted
        )
        self.assertTrue(is_ambig)
        self.assertEqual(target_field, "delivery_preference")
        self.assertIn("Home Delivery", clarif_q)
        self.assertIn("Store Pickup", clarif_q)

    def test_06_unambiguous_correction_does_not_ask_clarification(self):
        """When user says 'Change flavor to Vanilla', detect_ambiguous_correction returns False because value is present."""
        fields_data = {"cake_flavor": "Chocolate"}
        fields = [{"key": "cake_flavor", "label": "Cake Flavor", "required": True}]
        extracted = AiService.extract_workflow_fields(
            fields=fields,
            messages=[{"role": "user", "content": "Change flavor to Vanilla"}],
            collected_data=fields_data
        )
        self.assertEqual(extracted.get("cake_flavor"), "Vanilla")

        is_ambig, target_field, clarif_q = AiService.detect_ambiguous_correction(
            "Change flavor to Vanilla", fields, fields_data, extracted
        )
        self.assertFalse(is_ambig)

    def test_07_general_ambiguous_correction_asks_which_detail(self):
        """When user says 'Wait, I want to change something', ask which detail they want to update."""
        fields_data = {"cake_flavor": "Chocolate", "weight_kg": "1"}
        fields = [{"key": "cake_flavor", "label": "Cake Flavor", "required": True}]
        is_ambig, target_field, clarif_q = AiService.detect_ambiguous_correction(
            "Wait, I made a mistake, can I change something?", fields, fields_data, {}
        )
        self.assertTrue(is_ambig)
        self.assertIsNone(target_field)
        self.assertIn("Which detail would you like to update", clarif_q)

    def test_08_logistics_correction_after_completed_updates_field(self):
        """In Logistics workflow, user corrects delivery location after completion."""
        state = DeliveryWorkflowService.initial_state("test-call", self.phone)
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
            state, "Actually, deliver it to Indiranagar instead", self.name, self.phone
        )
        # Field updated
        self.assertEqual(new_state["collected_fields"]["delivery_location"], "Indiranagar")
        # Other fields preserved
        self.assertEqual(new_state["collected_fields"]["pickup_location"], "MG Road")
        self.assertEqual(new_state["collected_fields"]["package_type"], "documents")
        # State back to awaiting confirmation with updated details
        self.assertEqual(new_state["status"], DeliveryWorkflowService.AWAITING_CONFIRMATION)
        self.assertIn("indiranagar", reply.lower())

    def test_09_logistics_ambiguous_correction_requests_clarification(self):
        """In Logistics workflow, user says 'Can I change the pickup location?' without giving location."""
        state = DeliveryWorkflowService.initial_state("test-call", self.phone)
        state["intent"] = DeliveryWorkflowService.NEW_DELIVERY
        state["status"] = DeliveryWorkflowService.AWAITING_CONFIRMATION
        state["collected_fields"] = {
            "pickup_location": "MG Road",
            "delivery_location": "Whitefield",
            "package_type": "documents",
            "preferred_time": "tomorrow 10 AM",
            "contact_details": self.phone,
        }

        new_state, reply, _ = DeliveryWorkflowService.advance_state(
            state, "Can I change the pickup location?", self.name, self.phone
        )
        self.assertIn("where should we pick up", reply.lower())
        self.assertEqual(new_state["last_asked_field"], "pickup_location")
        # Previous fields still preserved
        self.assertEqual(new_state["collected_fields"]["delivery_location"], "Whitefield")


if __name__ == "__main__":
    unittest.main()
