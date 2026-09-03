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
