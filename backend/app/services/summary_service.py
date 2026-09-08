import json
from datetime import datetime


class SummaryService:
    @staticmethod
    def generate_clear_summary(record: dict) -> str:
        caller_name = record.get('caller_name') or 'Customer'
        caller_phone = record.get('caller_phone') or 'Unknown Phone'
        business_id = record.get('business_id') or ''
        intent = record.get('intent') or ''
        status = record.get('followup_status') or 'Pending'
        urgency = record.get('urgency') or 'Normal'

        raw_data = record.get('collected_data')
        data = {}
        if isinstance(raw_data, str):
            try:
                data = json.loads(raw_data)
            except Exception:
                data = {}
        elif isinstance(raw_data, dict):
            data = raw_data

        # 1. Check if Logistics workflow
        if business_id == 'biz-logistics-01' or 'logistics' in intent.lower() or 'delivery' in intent.lower() or 'delivery_workflow_state' in data:
            state = data.get('delivery_workflow_state') or data
            fields = state.get('collected_fields') or data
            sub_intent = state.get('intent') or intent
            pickup = fields.get('pickup_location')
            delivery = fields.get('delivery_location')
            pkg = fields.get('package_type')
            time_val = fields.get('preferred_time')
            trk = fields.get('tracking_number') or fields.get('order_number')
            issue = fields.get('issue_description')

            if sub_intent == 'NEW_DELIVERY':
                if status == 'COMPLETED' or state.get('delivery_request_created'):
                    return (
                        f"📦 New Delivery Booked: {caller_name} ({fields.get('contact_details') or caller_phone}) scheduled a courier pickup of {pkg or 'parcel'} "
                        f"from {pickup or 'Hub'} to {delivery or 'Destination'}. Preferred time: {time_val or 'Scheduled'}. "
                        f"Dispatch request created and courier pickup slot logged on calendar."
                    )
                elif status == 'AWAITING_CONFIRMATION':
                    return (
                        f"📦 Delivery Awaiting Confirmation: {caller_name} requested {pkg or 'parcel'} pickup from {pickup} to {delivery} for {time_val}. "
                        f"Ready for customer final confirmation."
                    )
                else:
                    gathered = [f"{k.replace('_', ' ').title()}: {v}" for k, v in fields.items() if v and not k.startswith('_')]
                    gathered_str = ', '.join(gathered) if gathered else 'Customer requested new pickup'
                    return f"📦 In-Progress Delivery Request: {caller_name} ({caller_phone}). Captured: {gathered_str}."

            elif sub_intent == 'STATUS_UPDATE':
                lookup = state.get('delivery_lookup', {})
                trk_status = lookup.get('status') or 'In Transit'
                loc = lookup.get('current_location') or 'Logistics Network'
                return f"🔍 Tracking Status Query: {caller_name} checked status for shipment #{trk or 'N/A'}. Live Status: {trk_status} at {loc}."

            elif sub_intent == 'EXISTING_DELIVERY_HELP':
                cb = state.get('callback_task', {})
                task_id = cb.get('task_id') or 'TASK-PENDING'
                return (
                    f"⚠️ Delivery Support Request: {caller_name} ({caller_phone}) requested support for #{trk or 'N/A'}. "
                    f"Reason: {issue or 'Delivery help'}. Callback task #{task_id} generated for dispatch team."
                )

            return f"🚚 SwiftMove Logistics: {caller_name} ({caller_phone}) contacted regarding delivery operations. Status: {status}."

        # 2. Cake Shop workflow
        flavor = data.get('cake_flavor')
        weight = data.get('weight_kg')
        req_date = data.get('required_date')
        order_type = data.get('order_type') or 'Cake Order'
        deliv_pref = data.get('delivery_preference')
        msg = data.get('custom_message') or data.get('message_on_cake')
        budget = data.get('budget_inr')

        date_str = ''
        if req_date:
            try:
                dt = datetime.fromisoformat(str(req_date).replace('Z', '+00:00'))
                date_str = dt.strftime('%B %d, %Y at %I:%M %p')
            except Exception:
                date_str = str(req_date)

        is_cake_completed = (status == 'Completed' or bool(data.get('_order_enquiry_triggered') or data.get('order_enquiry')))
        if is_cake_completed and flavor:
            parts = [f"🎂 Cake Order Confirmed: {caller_name} ({caller_phone}) placed a {order_type} for a {weight or '1'}kg {flavor} cake."]
            if date_str:
                parts.append(f"Required for: {date_str} via {deliv_pref or 'Home Delivery'}.")
            if msg and msg.lower() not in ['none', 'no', 'n/a']:
                parts.append(f"Message on cake: \"{msg}\".")
            if budget:
                parts.append(f"Budget: ₹{budget}.")
            parts.append("Order recorded, owner alerted, and calendar appointment scheduled.")
            return " ".join(parts)
        elif flavor or weight:
            known = []
            if flavor: known.append(f"Flavor: {flavor}")
            if weight: known.append(f"Weight: {weight}kg")
            if date_str: known.append(f"Timing: {date_str}")
            if deliv_pref: known.append(f"Preference: {deliv_pref}")
            return f"🎂 In-Progress Cake Order: {caller_name} ({caller_phone}). Details gathered: {', '.join(known)}. Awaiting remaining details."

        return f"📞 Customer Call: {caller_name} ({caller_phone}) contacted for {intent or 'assistance'}. Status: {status}. Urgency: {urgency}."
