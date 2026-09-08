import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, text

from app.services.delivery_workflow_service import DeliveryWorkflowService as Workflow


class DeliveryWorkflowAcceptanceTests(unittest.TestCase):
    PHONE = "+91 98765 12345"

    def new_state(self):
        return Workflow.initial_state("test-call", self.PHONE)

    def turn(self, state, message):
        return Workflow.advance_state(state, message, "Test Customer", self.PHONE)

    def test_01_basic_new_delivery_detects_intent_and_asks_first_missing_field(self):
        state, reply, _ = self.turn(self.new_state(), "I want to send a package.")
        self.assertEqual(state["intent"], Workflow.NEW_DELIVERY)
        self.assertEqual(state["last_asked_field"], "pickup_location")
        self.assertIn("pick up", reply.lower())
        self.assertEqual(state["collected_fields"]["contact_details"], self.PHONE)

    def test_02_extracts_multiple_delivery_fields_in_one_turn(self):
        state = self.new_state()
        state["intent"] = Workflow.NEW_DELIVERY
        state, reply, _ = self.turn(
            state,
            "Pickup is MG Road, delivery is Whitefield, documents, tomorrow morning, tracking TRK-1234, handle with care.",
        )
        self.assertEqual(state["collected_fields"]["pickup_location"], "MG Road")
        self.assertEqual(state["collected_fields"]["delivery_location"], "Whitefield")
        self.assertEqual(state["collected_fields"]["package_type"], "documents")
        self.assertEqual(state["collected_fields"]["preferred_time"].lower(), "tomorrow morning")
        self.assertEqual(state["collected_fields"]["tracking_number"], "TRK-1234")
        self.assertEqual(state["missing_fields"], [])
        self.assertNotIn("where should we pick up", reply.lower())
        self.assertNotIn("where should we deliver", reply.lower())

    def test_03_repeated_information_only_fills_the_new_field(self):
        state = self.new_state()
        state, _, _ = self.turn(state, "I want to send a package.")
        state, reply, _ = self.turn(state, "Pickup is MG Road.")
        self.assertEqual(state["collected_fields"]["pickup_location"], "MG Road")
        self.assertEqual(state["last_asked_field"], "delivery_location")

        state, reply, _ = self.turn(state, "It's from MG Road and going to Whitefield.")
        self.assertEqual(state["collected_fields"]["pickup_location"], "MG Road")
        self.assertEqual(state["collected_fields"]["delivery_location"], "Whitefield")
        self.assertNotIn("pick up the package", reply.lower())

    def test_04_latest_explicit_correction_replaces_delivery_location(self):
        state = self.new_state()
        state, _, _ = self.turn(
            state,
            "I need a new delivery. Pickup is MG Road, delivery is Whitefield, documents, tomorrow morning, tracking TRK-1234, handle with care.",
        )
        self.assertEqual(state["status"], Workflow.AWAITING_CONFIRMATION)

        state, reply, _ = self.turn(state, "Actually, deliver it to Marathahalli.")
        self.assertEqual(state["collected_fields"]["delivery_location"], "Marathahalli")
        self.assertEqual(state["status"], Workflow.AWAITING_CONFIRMATION)
        self.assertIn("marathahalli", reply.lower())

    def test_05_status_looks_up_identifier_without_delivery_questions(self):
        state = self.new_state()
        state, reply, _ = self.turn(state, "I want to check my delivery. Tracking number is ABC123.")
        self.assertEqual(state["intent"], Workflow.STATUS_UPDATE)
        self.assertEqual(state["collected_fields"]["tracking_number"], "ABC123")
        state, _, _ = self.turn(state, "No special instructions")
        state, _, _ = self.turn(state, "Indiranagar")
        state, _, _ = self.turn(state, "Whitefield")
        state, _, _ = self.turn(state, "documents")
        state, reply, tools = self.turn(state, "tomorrow")
        self.assertEqual(state["status"], Workflow.COMPLETED)
        self.assertEqual(tools[0]["tool"], "track_delivery_status")

    def test_06_existing_delivery_help_creates_callback_task(self):
        state = self.new_state()
        state, reply, _ = self.turn(state, "My delivery hasn't arrived. Order number is ORD123.")
        self.assertEqual(state["intent"], Workflow.EXISTING_DELIVERY_HELP)
        self.assertEqual(state["collected_fields"]["order_number"], "ORD123")
        self.assertEqual(state["collected_fields"]["issue_description"], "delivery not received")
        state, _, _ = self.turn(state, "Indiranagar")
        state, _, _ = self.turn(state, "Whitefield")
        state, _, _ = self.turn(state, "documents")
        state, reply, tools = self.turn(state, "tomorrow morning")
        self.assertEqual(state["status"], Workflow.CALLBACK_REQUIRED)
        self.assertTrue(state["callback_task_created"])
        self.assertEqual([tool["tool"] for tool in tools], ["track_delivery_status", "create_callback_task"])
        self.assertIn("callback request", reply.lower())

    def test_07_ten_turn_anti_repetition(self):
        state = self.new_state()
        turns = [
            "I want to send a package.",
            "Pickup is MG Road.",
            "It is from MG Road and going to Whitefield.",
            "It contains documents.",
            "Tomorrow morning.",
            "Please assign a new tracking ID.",
            "No special instructions, standard delivery.",
            "Yes, that's correct.",
            "Thanks.",
            "Goodbye.",
        ]
        for message in turns:
            state, _, _ = self.turn(state, message)
            asked = state.get("last_asked_field")
            if asked and asked != "tracking_or_order_number":
                self.assertFalse(
                    Workflow._is_valid_field(asked, state["collected_fields"].get(asked)),
                    f"Asked for an already collected field: {asked}",
                )
        self.assertEqual(state["status"], Workflow.COMPLETED)
        self.assertTrue(state["delivery_request_created"])

    def test_08_state_persists_between_separate_api_turns(self):
        engine = create_engine("sqlite://")
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE records (
                    id VARCHAR(64) PRIMARY KEY, business_id VARCHAR(64), workflow_id VARCHAR(64),
                    caller_name VARCHAR(255), caller_phone VARCHAR(64), intent VARCHAR(255),
                    collected_data TEXT, ai_summary TEXT, urgency VARCHAR(32), followup_status VARCHAR(32),
                    transcript TEXT, tools_executed TEXT, created_at VARCHAR(64)
                )
            """))

        with patch("app.services.delivery_workflow_service.get_db_connection", side_effect=engine.connect):
            first = Workflow.process_conversation({
                "business_id": Workflow.BUSINESS_ID,
                "workflow_id": Workflow.WORKFLOW_ID,
                "caller_name": "Test Customer",
                "caller_phone": self.PHONE,
                "messages": [{"role": "user", "content": "I want to send a package."}],
            })
            second = Workflow.process_conversation({
                "business_id": Workflow.BUSINESS_ID,
                "workflow_id": Workflow.WORKFLOW_ID,
                "caller_name": "Test Customer",
                "caller_phone": self.PHONE,
                "record_id": first["record_id"],
                "messages": [{"role": "user", "content": "Pickup is MG Road, delivery is Whitefield."}],
            })

        state = second["conversation_state"]
        self.assertEqual(state["call_id"], first["record_id"])
        self.assertEqual(state["collected_fields"]["pickup_location"], "MG Road")
        self.assertEqual(state["collected_fields"]["delivery_location"], "Whitefield")
        self.assertEqual(state["last_asked_field"], "package_type")

    def test_09_missed_call_creates_callback_before_ai_callback(self):
        with patch.object(Workflow, "_save_record") as save_record:
            result = Workflow.start_missed_call("Test Customer", self.PHONE)
        self.assertTrue(save_record.called)
        self.assertEqual(result["executed_tools"][0]["tool"], "create_callback_task")
        self.assertIn("calling you back", result["assistant_reply"].lower())

    def test_10_new_delivery_flow_creates_delivery_request_and_ends_with_thank_you(self):
        state = self.new_state()
        state, _, _ = self.turn(state, "I want to book a new delivery")
        self.assertEqual(state["intent"], Workflow.NEW_DELIVERY)
        state, _, _ = self.turn(state, "Indiranagar")
        self.assertEqual(state["collected_fields"]["pickup_location"], "Indiranagar")
        state, _, _ = self.turn(state, "Whitefield")
        self.assertEqual(state["collected_fields"]["delivery_location"], "Whitefield")
        state, _, _ = self.turn(state, "electronics")
        self.assertEqual(state["collected_fields"]["package_type"], "electronics")
        state, _, _ = self.turn(state, "tomorrow morning at 10 AM")
        state, _, _ = self.turn(state, "assign new tracking ID")
        self.assertTrue(state["collected_fields"]["tracking_number"])
        state, reply, _ = self.turn(state, "Handle with care, fragile items")
        self.assertIn("confirm", reply.lower())
        state, reply, tools = self.turn(state, "Yes, that is correct.")
        self.assertEqual(state["status"], Workflow.COMPLETED)
        self.assertTrue(state["delivery_request_created"])
        self.assertEqual(tools[0]["tool"], "create_delivery_request")
        self.assertIn("del-", reply.lower())
        self.assertIn("thank you", reply.lower())

    def test_11_status_update_validates_order_and_ends_with_thank_you(self):
        state = self.new_state()
        state, _, _ = self.turn(state, "I need a status update")
        self.assertEqual(state["intent"], Workflow.STATUS_UPDATE)
        state, _, _ = self.turn(state, "My tracking number is TRK-9821-IN")
        self.assertEqual(state["collected_fields"]["tracking_number"], "TRK-9821-IN")
        state, _, _ = self.turn(state, "No special instructions")
        state, _, _ = self.turn(state, "Indiranagar")
        state, _, _ = self.turn(state, "Whitefield")
        state, _, _ = self.turn(state, "documents")
        state, reply, tools = self.turn(state, "tomorrow")
        self.assertEqual(state["status"], Workflow.COMPLETED)
        self.assertEqual(state["collected_fields"]["tracking_number"], "TRK-9821-IN")
        self.assertEqual(tools[0]["tool"], "track_delivery_status")
        self.assertIn("out for delivery", reply.lower())
        self.assertIn("thank you", reply.lower())

    def test_12_existing_delivery_help_creates_callback_task_and_ends_with_thank_you(self):
        state = self.new_state()
        state, _, _ = self.turn(state, "I need help with an existing delivery")
        self.assertEqual(state["intent"], Workflow.EXISTING_DELIVERY_HELP)
        state, _, _ = self.turn(state, "Order is ORD-9988")
        self.assertEqual(state["collected_fields"]["order_number"], "ORD-9988")
        state, _, _ = self.turn(state, "The package is delayed and driver is unreachable")
        self.assertEqual(state["collected_fields"]["issue_description"], "delivery delayed")
        state, _, _ = self.turn(state, "Indiranagar")
        state, _, _ = self.turn(state, "Whitefield")
        state, _, _ = self.turn(state, "electronics")
        state, reply, tools = self.turn(state, "tomorrow")
        self.assertEqual(state["status"], Workflow.CALLBACK_REQUIRED)
        self.assertTrue(state["callback_task_created"])
        self.assertEqual([t["tool"] for t in tools], ["track_delivery_status", "create_callback_task"])
        self.assertIn("callback request", reply.lower())
        self.assertIn("thank you", reply.lower())

    def test_13_collected_data_flattened_for_ui(self):
        engine = create_engine("sqlite://")
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE records (
                    id VARCHAR(64) PRIMARY KEY, business_id VARCHAR(64), workflow_id VARCHAR(64),
                    caller_name VARCHAR(255), caller_phone VARCHAR(64), intent VARCHAR(255),
                    collected_data TEXT, ai_summary TEXT, urgency VARCHAR(32), followup_status VARCHAR(32),
                    transcript TEXT, tools_executed TEXT, created_at VARCHAR(64)
                )
            """))

        with patch("app.services.delivery_workflow_service.get_db_connection", side_effect=engine.connect):
            res = Workflow.process_conversation({
                "business_id": Workflow.BUSINESS_ID,
                "workflow_id": Workflow.WORKFLOW_ID,
                "caller_name": "Test Customer",
                "caller_phone": self.PHONE,
                "messages": [{"role": "user", "content": "I want a new delivery. Pickup is MG Road, delivery is Whitefield."}],
            })
            self.assertIn("pickup_location", res["collected_data"])
            self.assertEqual(res["collected_data"]["pickup_location"], "MG Road")
    def test_14_user_logistics_correction_scenario(self):
        state = self.new_state()

        # Turn 1: Intent
        state, reply, _ = self.turn(state, "Create a new delivery.")
        self.assertEqual(state["intent"], Workflow.NEW_DELIVERY)
        self.assertIn("pick up", reply.lower())

        # Turn 2: Pickup location provided
        state, reply, _ = self.turn(state, "Marathahalli.")
        self.assertEqual(state["collected_fields"]["pickup_location"], "Marathahalli")
        self.assertIn("deliver the package", reply.lower())

        # Turn 3: User realizes pickup was wrong and says "Sorry, it's not Marathahalli."
        state, reply, _ = self.turn(state, "Sorry, it's not Marathahalli.")
        self.assertIsNone(state["collected_fields"]["pickup_location"])
        self.assertNotEqual(state["collected_fields"]["delivery_location"], "Sorry")
        self.assertIsNone(state["collected_fields"]["delivery_location"])
        self.assertIn("where should we pick up", reply.lower())

        # Turn 4: User gives correct pickup
        state, reply, _ = self.turn(state, "MG Road.")
        self.assertEqual(state["collected_fields"]["pickup_location"], "MG Road")
        self.assertIn("deliver the package", reply.lower())

        # Turn 5: User gives delivery location
        state, reply, _ = self.turn(state, "Whitefield.")
        self.assertEqual(state["collected_fields"]["delivery_location"], "Whitefield")
        self.assertIn("package", reply.lower())

        # Turn 6: Mid-turn change request: "Could you please change delivery location?"
        state, reply, _ = self.turn(state, "Could you please change delivery location?")
        self.assertIsNone(state["collected_fields"]["delivery_location"])
        self.assertEqual(state["last_asked_field"], "delivery_location")
        self.assertIn("where should we deliver", reply.lower())
        self.assertNotIn("what type of package", reply.lower())

        # Turn 7: User provides new delivery location
        state, reply, _ = self.turn(state, "Indiranagar.")
        self.assertEqual(state["collected_fields"]["delivery_location"], "Indiranagar")
        self.assertIn("package", reply.lower())

        # Turn 8: Package type
        state, reply, _ = self.turn(state, "Electronic.")
        self.assertEqual(state["collected_fields"]["package_type"], "electronics")
        self.assertIn("prefer", reply.lower())

        # Turn 9: Preferred time
        state, reply, _ = self.turn(state, "Tomorrow, 10:00 AM.")
        self.assertIn("tomorrow", state["collected_fields"]["preferred_time"].lower())

        # Turn 10: Tracking ID prompt
        state, reply, _ = self.turn(state, "Assign a new ID.")
        self.assertTrue(state["collected_fields"]["tracking_number"].startswith("TRK-"))

        # Turn 11: Special instructions prompt
        state, reply, _ = self.turn(state, "No.")
        self.assertEqual(state["status"], Workflow.AWAITING_CONFIRMATION)
        self.assertIn("indiranagar", reply.lower())
        self.assertIn("mg road", reply.lower())
        self.assertNotIn("sorry", reply.lower())

        # Turn 12: Confirmation rejection: "No."
        state, reply, _ = self.turn(state, "No.")
        self.assertEqual(state["status"], Workflow.IN_PROGRESS)
        self.assertEqual(state["last_asked_field"], "field_selection_for_correction")
        self.assertIn("which delivery detail would you like to correct", reply.lower())

        # Turn 13: User picks slot: "location"
        state, reply, _ = self.turn(state, "location")
        self.assertEqual(state["status"], Workflow.IN_PROGRESS)
        self.assertIsNone(state["collected_fields"]["delivery_location"])
        self.assertEqual(state["last_asked_field"], "delivery_location")
        self.assertIn("where should we deliver the package instead", reply.lower())

        # Turn 14: User provides updated delivery location
        state, reply, _ = self.turn(state, "Koramangala.")
        self.assertEqual(state["collected_fields"]["delivery_location"], "Koramangala")
        self.assertEqual(state["status"], Workflow.AWAITING_CONFIRMATION)
        self.assertIn("koramangala", reply.lower())

        # Turn 15: Final confirmation: "Yes, that's correct."
        state, reply, tools = self.turn(state, "Yes, that's correct.")
        self.assertEqual(state["status"], Workflow.COMPLETED)
        self.assertIn("created successfully", reply.lower())
        self.assertTrue(state["delivery_request_created"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
