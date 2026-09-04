import httpx
from datetime import datetime, timezone

class ExternalApiService:
    @staticmethod
    def track_delivery_status(tracking_number: str):
        print(f"[Python Tool Call: track_delivery_status] Querying logistics REST API for: {tracking_number}")
        clean_num = tracking_number.strip().upper()

        if "9821" in clean_num or "EXPRESS" in clean_num:
            return {
                "tracking_number": clean_num,
                "status": "Out for Delivery",
                "current_location": "Indiranagar Hub, Bengaluru",
                "driver_name": "Rohan Sharma",
                "driver_phone": "+91 98888 77777",
                "estimated_delivery": "Today by 5:30 PM",
                "last_updated": datetime.now(timezone.utc).isoformat()
            }
        elif "100" in clean_num or "DELIVERED" in clean_num:
            return {
                "tracking_number": clean_num,
                "status": "Delivered",
                "current_location": "Customer Address",
                "driver_name": "Vikram Singh",
                "last_updated": datetime.now(timezone.utc).isoformat()
            }
        else:
            return {
                "tracking_number": clean_num,
                "status": "In Transit",
                "current_location": "Central Logistics Hub, Bengaluru",
                "estimated_delivery": "Tomorrow morning",
                "last_updated": datetime.now(timezone.utc).isoformat()
            }

    @staticmethod
    def lookup_crm_customer(phone_number: str):
        print(f"[Python Tool Call: lookup_crm_customer] Querying CRM API for phone: {phone_number}")
        clean_phone = "".join(filter(str.isdigit, phone_number))

        if "98765" in clean_phone or "98112" in clean_phone:
            return {
                "phone_number": phone_number,
                "name": "Rahul Kapur",
                "customer_tier": "VIP Gold",
                "previous_orders_count": 8,
                "last_interaction": "Cake order placed 2 weeks ago",
                "notes": "Prefers eggless options and evening delivery."
            }

        return {
            "phone_number": phone_number,
            "name": "Valued Customer",
            "customer_tier": "New",
            "previous_orders_count": 1,
            "last_interaction": "First call today",
            "notes": "New prospective lead."
        }

    @staticmethod
    def create_delivery_request(pickup_location: str, delivery_location: str, package_type: str = "Parcel", preferred_time: str = "Asap", caller_name: str = "Customer", caller_phone: str = "+91 98765 43210"):
        print(f"[Python Tool Call: create_delivery_request] Creating new delivery request: {pickup_location} -> {delivery_location}")
        req_id = f"DEL-{str(hash(pickup_location + delivery_location) % 9000 + 1000)}-IN"
        return {
            "success": True,
            "delivery_id": req_id,
            "status": "Scheduled / Pickup Pending",
            "pickup_location": pickup_location or "Indiranagar, Bengaluru",
            "delivery_location": delivery_location or "Whitefield, Bengaluru",
            "package_type": package_type or "Parcel / Box",
            "preferred_time": preferred_time or "Tomorrow 4:00 PM",
            "caller_name": caller_name,
            "caller_phone": caller_phone,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "message": f"New delivery request '{req_id}' registered successfully from {pickup_location} to {delivery_location}."
        }

    @staticmethod
    def create_callback_task(issue_summary: str, tracking_number: str = None, caller_name: str = "Customer", caller_phone: str = "+91 98765 43210"):
        print(f"[Python Tool Call: create_callback_task] Creating dispatch callback task for: {caller_name} ({caller_phone})")
        task_id = f"TSK-{str(hash(caller_phone + (issue_summary or '')) % 9000 + 1000)}-IN"
        return {
            "success": True,
            "task_id": task_id,
            "status": "Callback Task Assigned to Dispatch",
            "tracking_number": tracking_number or "TRK-9821-IN",
            "issue_summary": issue_summary or "Customer requested support with existing delivery",
            "caller_name": caller_name,
            "caller_phone": caller_phone,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "message": f"Callback task '{task_id}' assigned to dispatch team for {caller_name}."
        }
