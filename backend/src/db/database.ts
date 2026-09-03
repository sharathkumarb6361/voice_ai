import sqlite3 from 'better-sqlite3';
import path from 'path';
import fs from 'fs';
import { v4 as uuidv4 } from 'uuid';

const dbDir = path.join(__dirname, '../../data');
if (!fs.existsSync(dbDir)) {
  fs.mkdirSync(dbDir, { recursive: true });
}

const dbPath = path.join(dbDir, 'assistant.db');
const db = sqlite3(dbPath);

// Enable WAL mode for high performance
db.pragma('journal_mode = WAL');

export function initDatabase() {
  db.exec(`
    CREATE TABLE IF NOT EXISTS businesses (
      id TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      industry TEXT NOT NULL,
      owner_name TEXT NOT NULL,
      phone TEXT NOT NULL,
      email TEXT NOT NULL,
      address TEXT,
      created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS workflows (
      id TEXT PRIMARY KEY,
      business_id TEXT NOT NULL,
      name TEXT NOT NULL,
      industry TEXT NOT NULL,
      trigger_event TEXT NOT NULL,
      greeting TEXT NOT NULL,
      fields TEXT NOT NULL, -- JSON string
      conditions TEXT NOT NULL, -- JSON string
      actions TEXT NOT NULL, -- JSON string
      closing_message TEXT NOT NULL,
      language TEXT NOT NULL DEFAULT 'en',
      is_active INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL,
      FOREIGN KEY (business_id) REFERENCES businesses(id)
    );

    CREATE TABLE IF NOT EXISTS records (
      id TEXT PRIMARY KEY,
      business_id TEXT NOT NULL,
      workflow_id TEXT NOT NULL,
      caller_name TEXT NOT NULL,
      caller_phone TEXT NOT NULL,
      intent TEXT NOT NULL,
      collected_data TEXT NOT NULL, -- JSON string
      ai_summary TEXT NOT NULL,
      urgency TEXT NOT NULL DEFAULT 'Normal', -- Normal, Urgent, Critical
      followup_status TEXT NOT NULL DEFAULT 'Pending', -- Pending, Contacted, Completed, Closed
      transcript TEXT NOT NULL, -- JSON string
      tools_executed TEXT NOT NULL, -- JSON string
      created_at TEXT NOT NULL,
      FOREIGN KEY (business_id) REFERENCES businesses(id),
      FOREIGN KEY (workflow_id) REFERENCES workflows(id)
    );

    CREATE TABLE IF NOT EXISTS calendar_events (
      id TEXT PRIMARY KEY,
      business_id TEXT NOT NULL,
      title TEXT NOT NULL,
      start_time TEXT NOT NULL,
      end_time TEXT NOT NULL,
      attendee_name TEXT NOT NULL,
      attendee_phone TEXT NOT NULL,
      description TEXT,
      status TEXT NOT NULL DEFAULT 'Confirmed',
      google_event_id TEXT,
      created_at TEXT NOT NULL
    );
  `);

  seedDefaultData();
}

function seedDefaultData() {
  const checkBiz = db.prepare('SELECT COUNT(*) as count FROM businesses').get() as { count: number };
  if (checkBiz.count > 0) return;

  console.log('Seeding initial businesses and workflows...');

  const now = new Date().toISOString();

  // 1. Cake Shop Business
  const cakeBizId = 'biz-cake-01';
  db.prepare(`
    INSERT INTO businesses (id, name, industry, owner_name, phone, email, address, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
  `).run(cakeBizId, 'Sweet Treats Bakery & Confectionery', 'Cake Shop', 'Ananya Sharma', '+91 98765 43210', 'orders@sweettreats.com', 'MG Road, Indiranagar, Bengaluru', now);

  const cakeWorkflow = {
    id: 'wf-cake-01',
    business_id: cakeBizId,
    name: 'Missed Call Cake Order & Enquiry',
    industry: 'Cake Shop',
    trigger_event: 'Missed Call',
    greeting: 'Namaste! Thank you for calling Sweet Treats Bakery. We missed your call. Would you like to place a new cake order or ask a general enquiry?',
    fields: JSON.stringify([
      { key: 'order_type', label: 'Order Type', type: 'select', options: ['New Cake Order', 'General Enquiry', 'Custom Design'], required: true },
      { key: 'cake_flavor', label: 'Cake Flavor', type: 'text', required: true, description: 'e.g. Belgian Chocolate, Red Velvet, Vanilla Mango' },
      { key: 'weight_kg', label: 'Weight (in kg)', type: 'number', required: true, description: 'e.g. 1, 2, 5' },
      { key: 'required_date', label: 'Required Date & Time', type: 'datetime', required: true },
      { key: 'custom_message', label: 'Message on Cake', type: 'text', required: false },
      { key: 'delivery_preference', label: 'Delivery or Pickup', type: 'select', options: ['Home Delivery', 'Store Pickup'], required: true },
      { key: 'budget_inr', label: 'Budget (INR)', type: 'number', required: false }
    ]),
    conditions: JSON.stringify([
      { field: 'required_date', operator: 'within_hours', value: 24, action_override: 'mark_urgent', note: 'Mark urgent if required within 24 hours' }
    ]),
    actions: JSON.stringify(['create_order_enquiry', 'send_owner_sms_alert']),
    closing_message: 'Thank you! Your cake order details have been recorded. Our head baker will contact you shortly to confirm design and pricing.',
    language: 'en-hi',
    is_active: 1,
    created_at: now
  };

  db.prepare(`
    INSERT INTO workflows (id, business_id, name, industry, trigger_event, greeting, fields, conditions, actions, closing_message, language, is_active, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  `).run(
    cakeWorkflow.id, cakeWorkflow.business_id, cakeWorkflow.name, cakeWorkflow.industry,
    cakeWorkflow.trigger_event, cakeWorkflow.greeting, cakeWorkflow.fields,
    cakeWorkflow.conditions, cakeWorkflow.actions, cakeWorkflow.closing_message,
    cakeWorkflow.language, cakeWorkflow.is_active, cakeWorkflow.created_at
  );

  // 2. Clinic / Doctor Business
  const clinicBizId = 'biz-clinic-01';
  db.prepare(`
    INSERT INTO businesses (id, name, industry, owner_name, phone, email, address, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
  `).run(clinicBizId, 'Apex Health Care & Multi-Specialty Clinic', 'Clinic / Healthcare', 'Dr. Ramesh Kumar', '+91 91234 56789', 'contact@apexcare.com', 'Koramangala 5th Block, Bengaluru', now);

  const clinicWorkflow = {
    id: 'wf-clinic-01',
    business_id: clinicBizId,
    name: 'Patient Appointment Booking & Callback',
    industry: 'Clinic / Healthcare',
    trigger_event: 'Missed Call',
    greeting: 'Hello! You have reached Apex Health Clinic. We noticed we missed your call. Are you calling to book a doctor appointment, reschedule, or ask an enquiry?',
    fields: JSON.stringify([
      { key: 'request_type', label: 'Request Type', type: 'select', options: ['Book Appointment', 'Reschedule Appointment', 'Cancel Appointment', 'General Enquiry'], required: true },
      { key: 'patient_name', label: 'Patient Name', type: 'text', required: true },
      { key: 'specialty_or_doctor', label: 'Specialty / Doctor', type: 'select', options: ['General Physician', 'Dermatologist', 'Cardiologist', 'Pediatrician', 'Dentist'], required: true },
      { key: 'preferred_date_time', label: 'Preferred Date & Time', type: 'datetime', required: true },
      { key: 'symptoms_or_notes', label: 'Symptoms / Brief Note', type: 'text', required: false }
    ]),
    conditions: JSON.stringify([
      { field: 'request_type', operator: 'equals', value: 'Book Appointment', tool_action: 'check_and_create_google_calendar', note: 'Checks calendar availability and creates Google Calendar event' }
    ]),
    actions: JSON.stringify(['create_google_calendar_event', 'send_patient_confirmation_sms']),
    closing_message: 'Your appointment request has been scheduled on our calendar. Please do not take this as medical emergency advice. Our front desk will verify your details.',
    language: 'en-hi',
    is_active: 1,
    created_at: now
  };

  db.prepare(`
    INSERT INTO workflows (id, business_id, name, industry, trigger_event, greeting, fields, conditions, actions, closing_message, language, is_active, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  `).run(
    clinicWorkflow.id, clinicWorkflow.business_id, clinicWorkflow.name, clinicWorkflow.industry,
    clinicWorkflow.trigger_event, clinicWorkflow.greeting, clinicWorkflow.fields,
    clinicWorkflow.conditions, clinicWorkflow.actions, clinicWorkflow.closing_message,
    clinicWorkflow.language, clinicWorkflow.is_active, clinicWorkflow.created_at
  );

  // 3. Logistics Business
  const logisticsBizId = 'biz-logistics-01';
  db.prepare(`
    INSERT INTO businesses (id, name, industry, owner_name, phone, email, address, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
  `).run(logisticsBizId, 'SwiftMove Logistics & Parcel Express', 'Logistics & Delivery', 'Vikram Verma', '+91 99887 76655', 'support@swiftmove.in', 'Electronic City Phase 1, Bengaluru', now);

  const logisticsWorkflow = {
    id: 'wf-logistics-01',
    business_id: logisticsBizId,
    name: 'Delivery Request & Parcel Tracking Assistant',
    industry: 'Logistics & Delivery',
    trigger_event: 'Missed Call',
    greeting: 'Welcome to SwiftMove Express! Sorry we missed your call. Would you like to schedule a new package delivery or track an existing parcel?',
    fields: JSON.stringify([
      { key: 'service_type', label: 'Service Type', type: 'select', options: ['New Pickup & Delivery', 'Track Package Status', 'Support / Issue'], required: true },
      { key: 'tracking_number', label: 'Tracking Number (if existing)', type: 'text', required: false },
      { key: 'pickup_address', label: 'Pickup Location', type: 'text', required: false },
      { key: 'delivery_address', label: 'Delivery Location', type: 'text', required: false },
      { key: 'package_type', label: 'Package Type', type: 'select', options: ['Standard Documents', 'Electronics', 'Heavy Parcel', 'Perishable'], required: false }
    ]),
    conditions: JSON.stringify([
      { field: 'tracking_number', operator: 'exists', tool_action: 'call_external_delivery_api', note: 'Calls external Logistics API tool to fetch real-time package status' }
    ]),
    actions: JSON.stringify(['call_external_delivery_api', 'create_dispatch_task']),
    closing_message: 'Thank you. Your logistics request is logged, and our dispatch team has been notified.',
    language: 'en-hi',
    is_active: 1,
    created_at: now
  };

  db.prepare(`
    INSERT INTO workflows (id, business_id, name, industry, trigger_event, greeting, fields, conditions, actions, closing_message, language, is_active, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  `).run(
    logisticsWorkflow.id, logisticsWorkflow.business_id, logisticsWorkflow.name, logisticsWorkflow.industry,
    logisticsWorkflow.trigger_event, logisticsWorkflow.greeting, logisticsWorkflow.fields,
    logisticsWorkflow.conditions, logisticsWorkflow.actions, logisticsWorkflow.closing_message,
    logisticsWorkflow.language, logisticsWorkflow.is_active, logisticsWorkflow.created_at
  );

  // 4. Real Estate Business
  const realEstateBizId = 'biz-re-01';
  db.prepare(`
    INSERT INTO businesses (id, name, industry, owner_name, phone, email, address, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
  `).run(realEstateBizId, 'Prime Haven Realty & Properties', 'Real Estate', 'Priya Patel', '+91 97654 32109', 'info@primehavenrealty.com', 'HSR Layout, Bengaluru', now);

  const realEstateWorkflow = {
    id: 'wf-re-01',
    business_id: realEstateBizId,
    name: 'Lead Qualification & Property Visit Booking',
    industry: 'Real Estate',
    trigger_event: 'Missed Call',
    greeting: 'Hello! Thank you for contacting Prime Haven Realty. Are you looking to buy, rent, sell, or schedule a property site visit?',
    fields: JSON.stringify([
      { key: 'intent', label: 'Property Intent', type: 'select', options: ['Buy Property', 'Rent Property', 'Sell Property', 'Schedule Site Visit'], required: true },
      { key: 'property_type', label: 'Property Type', type: 'select', options: ['2BHK Apartment', '3BHK Apartment', 'Independent Villa', 'Commercial Plot'], required: true },
      { key: 'preferred_location', label: 'Preferred Location', type: 'text', required: true },
      { key: 'budget_range', label: 'Budget Range (Lakhs / Crores)', type: 'text', required: true },
      { key: 'site_visit_date', label: 'Preferred Visit Date', type: 'datetime', required: false }
    ]),
    conditions: JSON.stringify([
      { field: 'intent', operator: 'equals', value: 'Schedule Site Visit', tool_action: 'check_and_create_google_calendar', note: 'Schedule site visit appointment on agent Google Calendar' }
    ]),
    actions: JSON.stringify(['create_qualified_lead', 'schedule_google_calendar_visit']),
    closing_message: 'Your property inquiry has been registered. An expert real estate advisor will call you shortly with curated listings.',
    language: 'en-hi',
    is_active: 1,
    created_at: now
  };

  db.prepare(`
    INSERT INTO workflows (id, business_id, name, industry, trigger_event, greeting, fields, conditions, actions, closing_message, language, is_active, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  `).run(
    realEstateWorkflow.id, realEstateWorkflow.business_id, realEstateWorkflow.name, realEstateWorkflow.industry,
    realEstateWorkflow.trigger_event, realEstateWorkflow.greeting, realEstateWorkflow.fields,
    realEstateWorkflow.conditions, realEstateWorkflow.actions, realEstateWorkflow.closing_message,
    realEstateWorkflow.language, realEstateWorkflow.is_active, realEstateWorkflow.created_at
  );

  // 5. Home Repair Business
  const repairBizId = 'biz-repair-01';
  db.prepare(`
    INSERT INTO businesses (id, name, industry, owner_name, phone, email, address, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
  `).run(repairBizId, 'FixIt Pro Home Repair Services', 'Home & Repair Services', 'Rajesh Gupta', '+91 94567 89012', 'support@fixitpro.in', 'Whitefield, Bengaluru', now);

  const repairWorkflow = {
    id: 'wf-repair-01',
    business_id: repairBizId,
    name: 'Emergency Repair Dispatch & Maintenance Request',
    industry: 'Home & Repair Services',
    trigger_event: 'Missed Call',
    greeting: 'Hello! FixIt Pro Home Maintenance received your missed call. What repair or service do you require today?',
    fields: JSON.stringify([
      { key: 'service_category', label: 'Service Category', type: 'select', options: ['Plumbing', 'Electrical Repair', 'AC Repair & Service', 'Carpentry & Locksmith'], required: true },
      { key: 'issue_description', label: 'Issue Description', type: 'text', required: true },
      { key: 'address', label: 'Service Address', type: 'text', required: true },
      { key: 'urgency_level', label: 'Urgency', type: 'select', options: ['Immediate Emergency', 'Today', 'Schedule Later'], required: true }
    ]),
    conditions: JSON.stringify([
      { field: 'urgency_level', operator: 'equals', value: 'Immediate Emergency', action_override: 'mark_critical', note: 'Mark record as critical priority for immediate technician dispatch' }
    ]),
    actions: JSON.stringify(['create_service_ticket', 'dispatch_priority_technician']),
    closing_message: 'Your service request has been logged. For emergency tickets, our nearest technician has been alerted immediately.',
    language: 'en-hi',
    is_active: 1,
    created_at: now
  };

  db.prepare(`
    INSERT INTO workflows (id, business_id, name, industry, trigger_event, greeting, fields, conditions, actions, closing_message, language, is_active, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  `).run(
    repairWorkflow.id, repairWorkflow.business_id, repairWorkflow.name, repairWorkflow.industry,
    repairWorkflow.trigger_event, repairWorkflow.greeting, repairWorkflow.fields,
    repairWorkflow.conditions, repairWorkflow.actions, repairWorkflow.closing_message,
    repairWorkflow.language, repairWorkflow.is_active, repairWorkflow.created_at
  );

  // Seed sample customer call records so dashboard is instantly rich and visual!
  const sampleRecords = [
    {
      id: 'rec-cake-01',
      business_id: cakeBizId,
      workflow_id: cakeWorkflow.id,
      caller_name: 'Rahul Kapur',
      caller_phone: '+91 98112 33445',
      intent: 'New Cake Order - Birthday',
      collected_data: JSON.stringify({
        order_type: 'New Cake Order',
        cake_flavor: 'Belgian Dark Chocolate Fudge',
        weight_kg: 2,
        required_date: new Date(Date.now() + 18 * 3600 * 1000).toISOString(),
        custom_message: 'Happy 30th Birthday Sameer!',
        delivery_preference: 'Home Delivery',
        budget_inr: 2500
      }),
      ai_summary: 'Customer wants a 2kg Belgian Dark Chocolate Fudge cake delivered within 18 hours. Custom message requested. Marked URGENT as delivery is required under 24h.',
      urgency: 'Urgent',
      followup_status: 'Pending',
      transcript: JSON.stringify([
        { role: 'assistant', text: 'Namaste! Thank you for calling Sweet Treats Bakery. We missed your call. Would you like to place a new cake order or ask a general enquiry?' },
        { role: 'user', text: 'Hi! I want to order a birthday cake for tomorrow evening.' },
        { role: 'assistant', text: 'Great! What flavor and weight would you prefer?' },
        { role: 'user', text: 'Belgian Dark Chocolate Fudge, 2kg. Deliver to HSR layout by 6 PM tomorrow.' },
        { role: 'assistant', text: 'Got it! Any custom message on the cake?' },
        { role: 'user', text: 'Yes, write "Happy 30th Birthday Sameer!"' }
      ]),
      tools_executed: JSON.stringify([{ tool: 'evaluate_urgency_condition', result: 'Urgent flag set (delivery < 24h)' }]),
      created_at: new Date(Date.now() - 2 * 3600 * 1000).toISOString()
    },
    {
      id: 'rec-clinic-01',
      business_id: clinicBizId,
      workflow_id: clinicWorkflow.id,
      caller_name: 'Meera Nair',
      caller_phone: '+91 97441 22334',
      intent: 'Doctor Appointment Booking',
      collected_data: JSON.stringify({
        request_type: 'Book Appointment',
        patient_name: 'Meera Nair',
        specialty_or_doctor: 'Dermatologist',
        preferred_date_time: new Date(Date.now() + 24 * 3600 * 1000).toISOString(),
        symptoms_or_notes: 'Skin rash consultation'
      }),
      ai_summary: 'Patient booked consultation with Dermatologist for tomorrow at 4:00 PM. Checked Google Calendar availability and created appointment event.',
      urgency: 'Normal',
      followup_status: 'Contacted',
      transcript: JSON.stringify([
        { role: 'assistant', text: 'Hello! You have reached Apex Health Clinic. Are you calling to book a doctor appointment?' },
        { role: 'user', text: 'Yes, I need to see a Dermatologist tomorrow afternoon around 4 PM.' },
        { role: 'assistant', text: 'Let me check doctor availability on Google Calendar... Yes, 4:00 PM is available. May I confirm your name?' },
        { role: 'user', text: 'My name is Meera Nair.' },
        { role: 'assistant', text: 'Appointment created on Google Calendar for Meera Nair on tomorrow at 4:00 PM.' }
      ]),
      tools_executed: JSON.stringify([
        { tool: 'check_calendar_availability', args: { date: 'tomorrow', time: '16:00', doctor: 'Dermatologist' }, result: 'Available' },
        { tool: 'create_calendar_event', args: { title: 'Dermatology Consultation - Meera Nair', start_time: '2026-09-03T16:00:00Z' }, result: 'Created event gcal_evt_991823' }
      ]),
      created_at: new Date(Date.now() - 5 * 3600 * 1000).toISOString()
    },
    {
      id: 'rec-logistics-01',
      business_id: logisticsBizId,
      workflow_id: logisticsWorkflow.id,
      caller_name: 'Amitabh Sen',
      caller_phone: '+91 98990 11223',
      intent: 'Parcel Tracking',
      collected_data: JSON.stringify({
        service_type: 'Track Package Status',
        tracking_number: 'TRK-9821-IN'
      }),
      ai_summary: 'Customer enquired about package #TRK-9821-IN. AI called external Logistics REST API and provided live status: Out for Delivery in Indiranagar.',
      urgency: 'Normal',
      followup_status: 'Completed',
      transcript: JSON.stringify([
        { role: 'assistant', text: 'Welcome to SwiftMove Express! Would you like to schedule a new package delivery or track an existing parcel?' },
        { role: 'user', text: 'I want to check where my package TRK-9821-IN is right now.' },
        { role: 'assistant', text: 'Let me query our Logistics REST API... Tracking #TRK-9821-IN is currently Out for Delivery with courier agent Rohan (ETA 45 mins).' }
      ]),
      tools_executed: JSON.stringify([
        { tool: 'track_delivery_status', args: { tracking_number: 'TRK-9821-IN' }, result: { status: 'Out for Delivery', driver: 'Rohan', eta: '45 minutes' } }
      ]),
      created_at: new Date(Date.now() - 1 * 24 * 3600 * 1000).toISOString()
    }
  ];

  const stmtRecord = db.prepare(`
    INSERT INTO records (id, business_id, workflow_id, caller_name, caller_phone, intent, collected_data, ai_summary, urgency, followup_status, transcript, tools_executed, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  `);

  for (const rec of sampleRecords) {
    stmtRecord.run(
      rec.id, rec.business_id, rec.workflow_id, rec.caller_name, rec.caller_phone,
      rec.intent, rec.collected_data, rec.ai_summary, rec.urgency, rec.followup_status,
      rec.transcript, rec.tools_executed, rec.created_at
    );
  }

  console.log('Database successfully initialized and seeded!');
}

export { db };
