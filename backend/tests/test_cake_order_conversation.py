import unittest
import uuid
from app.services.cake_workflow_service import CakeWorkflowService


class CakeOrderConversationTests(unittest.TestCase):
    def setUp(self):
        self.phone = "+91 98765 43210"
        self.name = "Ankit Mehta"

    def test_01_user_saying_kilogram_extracts_weight_and_does_not_corrupt_date(self):
        """When caller answers 'Kilogram.' to the weight question, weight is 1 and date is NOT set."""
        rec_id = f"rec-cake-{uuid.uuid4().hex[:8]}"
        state = CakeWorkflowService.initial_state(rec_id, self.phone)
        state["collected_fields"]["cake_flavor"] = "Dark Chocolate"
        state["last_asked_field"] = "weight_kg"
        state["missing_fields"] = CakeWorkflowService.get_missing_fields(state)

        next_state, reply, tools = CakeWorkflowService.advance_state(state, "Kilogram.", self.name, self.phone)

        self.assertEqual(next_state["collected_fields"]["weight_kg"], "1")
        self.assertIsNone(next_state["collected_fields"]["required_date"])
        self.assertEqual(next_state["missing_fields"][0], "required_date")
        reply_lower = reply.lower()
        self.assertNotIn("what weight or size", reply_lower)
        self.assertIn("date and time", reply_lower)

    def test_02_user_saying_one_kilograms_extracts_weight(self):
        """When caller answers 'One kilograms.' to the weight question, weight is 1 and date is NOT set."""
        rec_id = f"rec-cake-{uuid.uuid4().hex[:8]}"
        state = CakeWorkflowService.initial_state(rec_id, self.phone)
        state["collected_fields"]["cake_flavor"] = "Dark Chocolate"
        state["last_asked_field"] = "weight_kg"
        state["missing_fields"] = CakeWorkflowService.get_missing_fields(state)

        next_state, reply, tools = CakeWorkflowService.advance_state(state, "One kilograms.", self.name, self.phone)

        self.assertEqual(next_state["collected_fields"]["weight_kg"], "1")
        self.assertIsNone(next_state["collected_fields"]["required_date"])
        self.assertEqual(next_state["missing_fields"][0], "required_date")
        reply_lower = reply.lower()
        self.assertNotIn("what weight or size", reply_lower)
        self.assertIn("date and time", reply_lower)

    def test_03_various_weight_expressions(self):
        """Check all natural variations of weight: two kilograms, half kg, 500 grams, a kilo."""
        test_inputs = [
            ("two kilograms", "2"),
            ("half a kilo", "0.5"),
            ("one and half kg", "1.5"),
            ("two and a half kg", "2.5"),
            ("500 grams", "0.5"),
            ("a kilo", "1"),
            ("Just 1 kg please", "1"),
            ("make it 3 kg", "3"),
        ]
        for user_text, expected_val in test_inputs:
            extracted = CakeWorkflowService.extract_fields(user_text, {"last_asked_field": "weight_kg"})
            self.assertEqual(
                extracted.get("weight_kg"), expected_val,
                f"Failed for input '{user_text}': got {extracted.get('weight_kg')} instead of {expected_val}"
            )
            self.assertNotIn("required_date", extracted, f"Date falsely extracted for '{user_text}'")

    def test_04_full_conversation_progression(self):
        """Walks through the entire cake order conversation from flavor to final confirmation."""
        rec_id = f"rec-cake-{uuid.uuid4().hex[:8]}"
        state = CakeWorkflowService.initial_state(rec_id, self.phone)

        state, reply, _ = CakeWorkflowService.advance_state(state, "Dark chocolate cake please", self.name, self.phone)
        self.assertEqual(state["collected_fields"]["cake_flavor"], "Dark Chocolate")
        self.assertEqual(state["last_asked_field"], "weight_kg")

        state, reply, _ = CakeWorkflowService.advance_state(state, "One kilograms.", self.name, self.phone)
        self.assertEqual(state["collected_fields"]["weight_kg"], "1")
        self.assertEqual(state["last_asked_field"], "required_date")

        state, reply, _ = CakeWorkflowService.advance_state(state, "Tomorrow at 4 PM", self.name, self.phone)
        self.assertTrue(bool(state["collected_fields"]["required_date"]))
        self.assertEqual(state["last_asked_field"], "custom_message")

        state, reply, _ = CakeWorkflowService.advance_state(state, "Happy Birthday Ankit", self.name, self.phone)
        self.assertEqual(state["collected_fields"]["custom_message"], "Happy Birthday Ankit")
        self.assertEqual(state["last_asked_field"], "delivery_preference")

        state, reply, _ = CakeWorkflowService.advance_state(state, "Home delivery please", self.name, self.phone)
        self.assertEqual(state["collected_fields"]["delivery_preference"], "Home Delivery")
        self.assertEqual(state["last_asked_field"], "budget_inr")

        state, reply, _ = CakeWorkflowService.advance_state(state, "1500 rupees", self.name, self.phone)
        self.assertEqual(state["collected_fields"]["budget_inr"], "1500")
        self.assertEqual(state["status"], CakeWorkflowService.AWAITING_CONFIRMATION)

        state, reply, tools = CakeWorkflowService.advance_state(state, "Yes confirm order", self.name, self.phone)
        self.assertEqual(state["status"], CakeWorkflowService.COMPLETED)
        tool_names = [t["tool"] for t in tools]
        self.assertIn("create_order_enquiry", tool_names)
        self.assertIn("send_owner_summary_alert", tool_names)
        self.assertIn("create_calendar_event", tool_names)


if __name__ == "__main__":
    unittest.main()
