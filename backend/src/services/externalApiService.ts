export interface DeliveryStatusResponse {
  tracking_number: string;
  status: 'In Transit' | 'Out for Delivery' | 'Delivered' | 'Pending Pickup' | 'NotFound';
  current_location: string;
  driver_name?: string;
  driver_phone?: string;
  estimated_delivery?: string;
  last_updated: string;
}

export interface CrmCustomerRecord {
  phone_number: string;
  name: string;
  customer_tier: 'VIP Gold' | 'Regular' | 'New';
  previous_orders_count: number;
  last_interaction: string;
  notes: string;
}

export class ExternalApiService {
  // Simulated or external REST API endpoint caller
  static async trackDeliveryStatus(trackingNumber: string): Promise<DeliveryStatusResponse> {
    console.log(`[Tool Call: track_delivery_status] Executing REST API call for tracking: ${trackingNumber}`);
    
    const cleanNumber = trackingNumber.trim().toUpperCase();
    
    // Check known mock patterns or return dynamic response
    if (cleanNumber.includes('9821') || cleanNumber.includes('EXPRESS')) {
      return {
        tracking_number: cleanNumber,
        status: 'Out for Delivery',
        current_location: 'Indiranagar Hub, Bengaluru',
        driver_name: 'Rohan Sharma',
        driver_phone: '+91 98888 77777',
        estimated_delivery: 'Today by 5:30 PM',
        last_updated: new Date().toISOString()
      };
    } else if (cleanNumber.includes('100') || cleanNumber.includes('DELIVERED')) {
      return {
        tracking_number: cleanNumber,
        status: 'Delivered',
        current_location: 'Customer Address',
        driver_name: 'Vikram Singh',
        last_updated: new Date(Date.now() - 3600000).toISOString()
      };
    } else {
      return {
        tracking_number: cleanNumber,
        status: 'In Transit',
        current_location: 'Central Logistics Hub, Bengaluru',
        estimated_delivery: 'Tomorrow morning',
        last_updated: new Date().toISOString()
      };
    }
  }

  static async lookupCrmCustomer(phoneNumber: string): Promise<CrmCustomerRecord> {
    console.log(`[Tool Call: lookup_crm_customer] Executing CRM lookup for phone: ${phoneNumber}`);

    const cleanPhone = phoneNumber.replace(/[^0-9]/g, '');

    if (cleanPhone.includes('98765') || cleanPhone.includes('98112')) {
      return {
        phone_number: phoneNumber,
        name: 'Rahul Kapur',
        customer_tier: 'VIP Gold',
        previous_orders_count: 8,
        last_interaction: 'Cake order placed 2 weeks ago',
        notes: 'Prefers eggless options and evening delivery.'
      };
    }

    return {
      phone_number: phoneNumber,
      name: 'Valued Customer',
      customer_tier: 'New',
      previous_orders_count: 1,
      last_interaction: 'First call today',
      notes: 'New prospective lead.'
    };
  }

  static async checkInventoryStock(itemName: string): Promise<{ item_name: string; available: boolean; quantity_in_stock: number; unit_price_inr: number }> {
    console.log(`[Tool Call: check_inventory_stock] Executing inventory API call for: ${itemName}`);
    const name = itemName.toLowerCase();

    if (name.includes('chocolate') || name.includes('velvet') || name.includes('mango')) {
      return { item_name: itemName, available: true, quantity_in_stock: 12, unit_price_inr: 1200 };
    }

    return { item_name: itemName, available: true, quantity_in_stock: 5, unit_price_inr: 950 };
  }
}
