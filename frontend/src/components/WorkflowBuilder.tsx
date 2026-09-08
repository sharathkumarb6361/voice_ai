import React, { useState, useEffect } from 'react';
import { Business, Workflow, WorkflowField, WorkflowCondition, BusinessHours } from '../types';

interface WorkflowBuilderProps {
  businesses: Business[];
  workflows: Workflow[];
  onSaveWorkflow: (workflowData: Partial<Workflow>) => Promise<void>;
  onTestWorkflow: (workflowId: string) => void;
}

const CAKE_SHOP_PRESETS: WorkflowField[] = [
  { key: 'order_type', label: 'Order Type', type: 'select', options: ['New Cake Order', 'General Enquiry', 'Custom Design'], required: true, description: 'Order or general enquiry classification' },
  { key: 'cake_type', label: 'Cake Type / Occasion', type: 'select', options: ['Birthday Cake', 'Anniversary Cake', 'Tier Wedding Cake', 'Theme Custom Cake', 'Pastry Box'], required: false, description: 'Type or occasion for the cake' },
  { key: 'cake_flavor', label: 'Cake Flavor', type: 'text', required: true, description: 'e.g. Belgian Dark Chocolate, Red Velvet, Vanilla Mango' },
  { key: 'weight_kg', label: 'Weight (in kg)', type: 'number', required: true, description: 'e.g. 1, 2, 5' },
  { key: 'required_date', label: 'Required Date & Time', type: 'datetime', required: true, description: 'Pickup or delivery target datetime' },
  { key: 'custom_message', label: 'Message on Cake', type: 'text', required: true, description: 'e.g. Happy Birthday Rahul!' },
  { key: 'delivery_preference', label: 'Delivery or Pickup', type: 'select', options: ['Home Delivery', 'Store Pickup'], required: true, description: 'Customer preference for fulfillment' },
  { key: 'budget_inr', label: 'Budget (INR)', type: 'number', required: true, description: 'e.g. 1500' }
];

const LOGISTICS_PRESETS: WorkflowField[] = [
  { key: 'service_option', label: 'Service Option', type: 'select', options: ['New Delivery Request', 'Package Status Update', 'Help with Existing Delivery'], required: true, description: 'Logistics service request type' },
  { key: 'pickup_location', label: 'Pickup Location', type: 'text', required: true, description: 'e.g. Indiranagar, Bengaluru' },
  { key: 'delivery_location', label: 'Delivery Location', type: 'text', required: true, description: 'e.g. Whitefield, Bengaluru' },
  { key: 'package_type', label: 'Package Type', type: 'select', options: ['Documents & Files', 'Electronics', 'Parcels & Boxes', 'Furniture & Heavy', 'Fragile Item'], required: true, description: 'Type of cargo parcel' },
  { key: 'preferred_time', label: 'Preferred Pickup Time', type: 'datetime', required: true, description: 'Requested pickup time slot' },
  { key: 'tracking_number', label: 'Waybill / Tracking Number', type: 'text', required: true, description: 'e.g. TRK-9821-IN' }
];

export const WorkflowBuilder: React.FC<WorkflowBuilderProps> = ({
  businesses,
  workflows,
  onSaveWorkflow,
  onTestWorkflow
}) => {
  const [selectedWorkflowId, setSelectedWorkflowId] = useState<string>('new');

  // Form State
  const [businessId, setBusinessId] = useState<string>(businesses[0]?.id || 'biz-cake-01');
  const [name, setName] = useState<string>('');
  const [industry, setIndustry] = useState<string>('Cake Shop');
  const [greeting, setGreeting] = useState<string>('Namaste! We missed your call. How can we help you today?');
  const [closingMessage, setClosingMessage] = useState<string>('Thank you! Your enquiry has been recorded. We will contact you shortly.');
  const [language, setLanguage] = useState<string>('en-hi');

  // Business Hours & Service Availability Timings State
  const [bhEnabled, setBhEnabled] = useState<boolean>(true);
  const [bhDays, setBhDays] = useState<string[]>(['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']);
  const [bhStartTime, setBhStartTime] = useState<string>('09:00');
  const [bhEndTime, setBhEndTime] = useState<string>('18:00');
  const [bhAfterHoursGreeting, setBhAfterHoursGreeting] = useState<string>(
    'We are currently closed for the day. Our business operating hours are Mon-Sat 9 AM to 6 PM. We have logged your request and will follow up tomorrow morning.'
  );

  // Fields State
  const [fields, setFields] = useState<WorkflowField[]>(CAKE_SHOP_PRESETS);

  // Conditions State
  const [conditions, setConditions] = useState<WorkflowCondition[]>([
    { field: 'required_date', operator: 'within_hours', value: 24, action_override: 'mark_urgent', note: 'If required within 24 hours -> Mark urgent' }
  ]);

  // Actions State
  const [actions, setActions] = useState<string[]>(['create_order_enquiry', 'send_owner_summary_alert']);

  const [saving, setSaving] = useState(false);
  const [successMsg, setSuccessMsg] = useState('');

  const allWeekDays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

  // Sync selected workflow whenever workflows array or selectedWorkflowId changes
  useEffect(() => {
    if (workflows && workflows.length > 0) {
      if (selectedWorkflowId !== 'new') {
        const wf = workflows.find(w => w.id === selectedWorkflowId);
        if (wf) {
          loadWorkflowData(wf);
        } else if (workflows[0]) {
          setSelectedWorkflowId(workflows[0].id);
          loadWorkflowData(workflows[0]);
        }
      } else if (!name && workflows[0]) {
        setSelectedWorkflowId(workflows[0].id);
        loadWorkflowData(workflows[0]);
      }
    }
  }, [workflows, selectedWorkflowId]);

  const loadWorkflowData = (wf: Workflow) => {
    setBusinessId(wf.business_id);
    setName(wf.name);
    setIndustry(wf.industry);
    setGreeting(wf.greeting);
    setClosingMessage(wf.closing_message);
    setLanguage(wf.language || 'en-hi');
    setFields(wf.fields || []);
    setConditions(wf.conditions || []);
    setActions(wf.actions || []);

    if (wf.business_hours) {
      setBhEnabled(wf.business_hours.enabled ?? true);
      setBhDays(wf.business_hours.days || ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']);
      setBhStartTime(wf.business_hours.start_time || '09:00');
      setBhEndTime(wf.business_hours.end_time || '18:00');
      setBhAfterHoursGreeting(wf.business_hours.after_hours_greeting || 'We are currently closed for the day. Our operating hours are Mon-Sat 9 AM to 6 PM.');
    } else {
      setBhEnabled(true);
      setBhDays(['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']);
      setBhStartTime('09:00');
      setBhEndTime('18:00');
    }
  };

  const toggleDay = (day: string) => {
    if (bhDays.includes(day)) {
      setBhDays(bhDays.filter(d => d !== day));
    } else {
      setBhDays([...bhDays, day]);
    }
  };

  // Helper to calculate whether current local time is OPEN or CLOSED based on config
  const checkCurrentOpenStatus = () => {
    if (!bhEnabled) return { isOpen: true, label: '🟢 Always Open (24/7 Service)' };
    const now = new Date();
    const dayName = now.toLocaleString('en-US', { weekday: 'short' });
    const currentHhMm = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;

    if (bhDays.includes(dayName) && currentHhMm >= bhStartTime && currentHhMm <= bhEndTime) {
      return { isOpen: true, label: `🟢 Currently OPEN (${dayName} ${currentHhMm})` };
    }
    return { isOpen: false, label: `🌙 Currently CLOSED / After-Hours (${dayName} ${currentHhMm})` };
  };

  const currentStatus = checkCurrentOpenStatus();

  const handleSelectWorkflow = (id: string) => {
    setSelectedWorkflowId(id);
    setSuccessMsg('');

    if (id === 'new') {
      setName('');
      setIndustry('Cake Shop');
      setGreeting('Hello! Thank you for calling. We missed your call. How can we assist you?');
      setClosingMessage('Thank you! Your information is recorded. We will follow up shortly.');
      setBhEnabled(true);
      setBhDays(['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']);
      setBhStartTime('09:00');
      setBhEndTime('18:00');
      setBhAfterHoursGreeting('We are currently closed for the day. Our business operating hours are Mon-Sat 9 AM to 6 PM. We have logged your request.');
      setFields(CAKE_SHOP_PRESETS);
      setConditions([]);
      setActions(['create_order_enquiry']);
      return;
    }

    const wf = workflows.find(w => w.id === id);
    if (wf) {
      loadWorkflowData(wf);
    }
  };

  const addField = () => {
    const newIndex = fields.length + 1;
    setFields([
      ...fields,
      {
        key: `custom_field_${newIndex}`,
        label: `Custom Field ${newIndex}`,
        type: 'text',
        required: true,
        description: 'Customer input detail'
      }
    ]);
  };

  const loadCakePresets = () => {
    setFields(CAKE_SHOP_PRESETS);
    setIndustry('Cake Shop');
  };

  const loadLogisticsPresets = () => {
    setFields(LOGISTICS_PRESETS);
    setIndustry('Logistics & Delivery');
  };

  const updateField = (index: number, updated: Partial<WorkflowField>) => {
    const copy = [...fields];
    copy[index] = { ...copy[index], ...updated };
    setFields(copy);
  };

  const removeField = (index: number) => {
    setFields(fields.filter((_, i) => i !== index));
  };

  const moveField = (index: number, direction: 'up' | 'down') => {
    if (direction === 'up' && index === 0) return;
    if (direction === 'down' && index === fields.length - 1) return;
    const copy = [...fields];
    const targetIdx = direction === 'up' ? index - 1 : index + 1;
    const temp = copy[index];
    copy[index] = copy[targetIdx];
    copy[targetIdx] = temp;
    setFields(copy);
  };

  const addCondition = () => {
    setConditions([
      ...conditions,
      {
        field: fields[0]?.key || 'required_date',
        operator: 'within_hours',
        value: 24,
        action_override: 'mark_urgent',
        note: 'Mark urgent if required within 24 hours'
      }
    ]);
  };

  const updateCondition = (index: number, updated: Partial<WorkflowCondition>) => {
    const copy = [...conditions];
    copy[index] = { ...copy[index], ...updated };
    setConditions(copy);
  };

  const removeCondition = (index: number) => {
    setConditions(conditions.filter((_, i) => i !== index));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name || !greeting || !closingMessage) return;

    setSaving(true);
    try {
      const format24h = (t: string, fallback: string) => {
        if (!t) return fallback;
        const trimmed = t.trim();
        if (/^\d{1,2}:\d{2}$/.test(trimmed)) {
          const [h, m] = trimmed.split(':');
          return `${h.padStart(2, '0')}:${m}`;
        }
        return fallback;
      };

      const bhPayload: BusinessHours = {
        enabled: bhEnabled,
        days: bhDays,
        start_time: format24h(bhStartTime, '09:00'),
        end_time: format24h(bhEndTime, '18:00'),
        after_hours_greeting: bhAfterHoursGreeting,
        after_hours_action: 'flag_after_hours'
      };

      await onSaveWorkflow({
        id: selectedWorkflowId === 'new' ? undefined : selectedWorkflowId,
        business_id: businessId,
        name,
        industry,
        trigger_event: 'Missed Call',
        greeting,
        fields,
        conditions,
        actions,
        closing_message: closingMessage,
        language,
        business_hours: bhPayload
      });
      setSuccessMsg('Workflow & Business Hours schedule saved successfully!');
      setTimeout(() => setSuccessMsg(''), 4000);
    } catch (err: any) {
      alert(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6 sm:space-y-8">
      {/* Workflow Selector Bar */}
      <div className="glass-panel p-4 sm:p-5 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <h2 className="text-lg sm:text-xl font-bold text-white flex items-center gap-2">
            <i className="fa-solid fa-sliders text-indigo-400" />
            Custom Voice AI Workflow Builder
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Configure missed-call AI voice greeting, operating hours, all collected customer fields, & conditional rules
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3 w-full md:w-auto">
          <span className="text-xs text-slate-400 font-medium hidden sm:inline">Load Workflow:</span>
          <select
            value={selectedWorkflowId}
            onChange={(e) => handleSelectWorkflow(e.target.value)}
            className="w-full sm:w-auto bg-slate-900 border border-slate-700 text-xs font-semibold rounded-xl px-3 py-2 text-slate-200 focus:outline-none focus:border-indigo-500 cursor-pointer"
          >
            <option value="new" className="bg-slate-900">+ Create New Custom Workflow</option>
            {workflows.map(w => (
              <option key={w.id} value={w.id} className="bg-slate-900">{w.name} ({w.industry})</option>
            ))}
          </select>
        </div>
      </div>

      {successMsg && (
        <div className="p-4 bg-emerald-950/40 border border-emerald-500/40 rounded-xl text-xs text-emerald-200 font-bold flex items-center justify-between animate-fade-in">
          <span><i className="fa-solid fa-circle-check text-emerald-400 mr-2 text-sm" />{successMsg}</span>
          <button onClick={() => setSuccessMsg('')} className="text-slate-400 hover:text-white">✕</button>
        </div>
      )}

      {/* Main Workflow Form */}
      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Step 1: Basic Information & Business Profile */}
        <div className="glass-panel p-5 sm:p-6 space-y-4 border border-slate-800">
          <h3 className="text-sm font-bold text-indigo-300 uppercase tracking-wider flex items-center gap-2 border-b border-slate-800 pb-3">
            <span className="w-6 h-6 rounded-full bg-indigo-500/20 text-indigo-300 flex items-center justify-center text-xs font-bold">1</span>
            Basic Information & Industry Profile
          </h3>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs">
            <div>
              <label className="text-slate-300 font-semibold block mb-1">Target Business Profile *</label>
              <select
                value={businessId}
                onChange={(e) => setBusinessId(e.target.value)}
                className="w-full bg-slate-900 border border-slate-700 rounded-xl p-2.5 text-slate-200 font-semibold focus:outline-none focus:border-indigo-500"
              >
                {businesses.map(b => (
                  <option key={b.id} value={b.id} className="bg-slate-900">{b.name} ({b.industry})</option>
                ))}
              </select>
            </div>

            <div>
              <label className="text-slate-300 font-semibold block mb-1">Workflow Name *</label>
              <input
                type="text"
                required
                placeholder="e.g. Missed Call Cake Order & Enquiry"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full bg-slate-900 border border-slate-700 rounded-xl p-2.5 text-slate-200 focus:outline-none focus:border-indigo-500"
              />
            </div>

            <div>
              <label className="text-slate-300 font-semibold block mb-1">Industry Category</label>
              <select
                value={industry}
                onChange={(e) => setIndustry(e.target.value)}
                className="w-full bg-slate-900 border border-slate-700 rounded-xl p-2.5 text-slate-200 focus:outline-none focus:border-indigo-500"
              >
                <option value="Cake Shop" className="bg-slate-900">Cake Shop</option>
                <option value="Logistics & Delivery" className="bg-slate-900">Logistics & Delivery</option>
              </select>
            </div>
          </div>
        </div>

        {/* Step 2: Business Hours & Service Availability Timings Section */}
        <div className="glass-panel p-5 sm:p-6 space-y-4 border border-slate-800">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 border-b border-slate-800 pb-3">
            <h3 className="text-sm font-bold text-indigo-300 uppercase tracking-wider flex items-center gap-2">
              <span className="w-6 h-6 rounded-full bg-indigo-500/20 text-indigo-300 flex items-center justify-center text-xs font-bold">2</span>
              <i className="fa-solid fa-clock text-amber-400 mr-1" />
              Business Hours & Service Availability Timings
            </h3>
            <div className="flex items-center gap-2">
              <span className={`text-[11px] font-bold px-3 py-1 rounded-full border ${
                currentStatus.isOpen ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40' : 'bg-rose-500/20 text-rose-300 border-rose-500/40'
              }`}>
                {currentStatus.label}
              </span>
            </div>
          </div>

          <div className="space-y-4 text-xs">
            {/* Enable Schedule Toggle */}
            <div className="flex items-center justify-between bg-slate-900/80 p-3.5 rounded-xl border border-slate-800">
              <div>
                <div className="font-bold text-slate-100 flex items-center gap-2">
                  <i className="fa-solid fa-calendar-week text-indigo-400" />
                  Enable Operating Hours Schedule & Service Availability Rules
                </div>
                <p className="text-[11px] text-slate-400 mt-0.5">
                  When enabled, calls received outside operating hours will trigger the After-Hours message and flag after-hours follow-ups.
                </p>
              </div>
              <label className="relative inline-flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  checked={bhEnabled}
                  onChange={(e) => setBhEnabled(e.target.checked)}
                  className="sr-only peer"
                />
                <div className="w-11 h-6 bg-slate-800 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-indigo-600" />
              </label>
            </div>

            {bhEnabled && (
              <div className="space-y-4 pt-1 animate-fade-in">
                {/* Operating Days Selection */}
                <div>
                  <label className="text-slate-300 font-semibold block mb-2">Operating Service Days</label>
                  <div className="flex flex-wrap gap-2">
                    {allWeekDays.map(day => {
                      const isSelected = bhDays.includes(day);
                      return (
                        <button
                          key={day}
                          type="button"
                          onClick={() => toggleDay(day)}
                          className={`px-3.5 py-1.5 rounded-xl font-bold transition-all border ${
                            isSelected
                              ? 'bg-gradient-to-r from-indigo-600 to-blue-600 text-white border-indigo-400 shadow-md shadow-indigo-500/20'
                              : 'bg-slate-900 text-slate-400 border-slate-700 hover:border-indigo-500/30'
                          }`}
                        >
                          {isSelected ? '✓ ' : ''}{day}
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* Operating Hours Pickers */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="text-slate-300 font-semibold block mb-1">Service Start Time (Opening)</label>
                    <input
                      type="time"
                      value={bhStartTime}
                      onChange={(e) => setBhStartTime(e.target.value)}
                      className="w-full bg-slate-900 border border-slate-700 rounded-xl p-2.5 text-slate-200 font-semibold focus:outline-none focus:border-indigo-500"
                    />
                  </div>

                  <div>
                    <label className="text-slate-300 font-semibold block mb-1">Service End Time (Closing)</label>
                    <input
                      type="time"
                      value={bhEndTime}
                      onChange={(e) => setBhEndTime(e.target.value)}
                      className="w-full bg-slate-900 border border-slate-700 rounded-xl p-2.5 text-slate-200 font-semibold focus:outline-none focus:border-indigo-500"
                    />
                  </div>
                </div>

                {/* After Hours Message */}
                <div>
                  <label className="text-slate-300 font-semibold block mb-1">After-Hours / Service Unavailable Response Message</label>
                  <textarea
                    rows={2}
                    value={bhAfterHoursGreeting}
                    onChange={(e) => setBhAfterHoursGreeting(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-700 rounded-xl p-2.5 text-slate-200 focus:outline-none focus:border-indigo-500"
                    placeholder="Message spoken or returned to caller when calling outside business hours..."
                  />
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Step 3: Voice Greetings & Closing Message */}
        <div className="glass-panel p-5 sm:p-6 space-y-4 border border-slate-800">
          <h3 className="text-sm font-bold text-indigo-300 uppercase tracking-wider flex items-center gap-2 border-b border-slate-800 pb-3">
            <span className="w-6 h-6 rounded-full bg-indigo-500/20 text-indigo-300 flex items-center justify-center text-xs font-bold">3</span>
            Opening Greeting & Closing Voice Messages
          </h3>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
            <div>
              <label className="text-slate-300 font-semibold block mb-1">Opening Voice Greeting *</label>
              <textarea
                rows={3}
                required
                value={greeting}
                onChange={(e) => setGreeting(e.target.value)}
                className="w-full bg-slate-900 border border-slate-700 rounded-xl p-2.5 text-slate-200 focus:outline-none focus:border-indigo-500"
              />
            </div>

            <div>
              <label className="text-slate-300 font-semibold block mb-1">Closing Message *</label>
              <textarea
                rows={3}
                required
                value={closingMessage}
                onChange={(e) => setClosingMessage(e.target.value)}
                className="w-full bg-slate-900 border border-slate-700 rounded-xl p-2.5 text-slate-200 focus:outline-none focus:border-indigo-500"
              />
            </div>
          </div>
        </div>

        {/* Step 4: Captured Form Fields (Showing ALL Fields & Options) */}
        <div className="glass-panel p-5 sm:p-6 space-y-5 border border-slate-800">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 border-b border-slate-800 pb-4">
            <div>
              <h3 className="text-sm font-bold text-indigo-300 uppercase tracking-wider flex items-center gap-2">
                <span className="w-6 h-6 rounded-full bg-indigo-500/20 text-indigo-300 flex items-center justify-center text-xs font-bold">4</span>
                Collected Customer Information Fields ({fields.length} Active Fields)
              </h3>
              <p className="text-[11px] text-slate-400 mt-1">
                All data fields collected during missed call interactions. View, edit, or add dropdown options & descriptions.
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={loadCakePresets}
                className="px-3 py-1.5 rounded-lg bg-pink-600/20 hover:bg-pink-600/40 text-pink-300 border border-pink-500/30 text-xs font-bold transition-all flex items-center gap-1.5"
                title="Load standard 8 fields for Cake Shop"
              >
                <i className="fa-solid fa-cake-candles text-xs" /> Cake Shop Fields (8)
              </button>

              <button
                type="button"
                onClick={loadLogisticsPresets}
                className="px-3 py-1.5 rounded-lg bg-blue-600/20 hover:bg-blue-600/40 text-blue-300 border border-blue-500/30 text-xs font-bold transition-all flex items-center gap-1.5"
                title="Load standard 6 fields for Logistics & Delivery"
              >
                <i className="fa-solid fa-truck-fast text-xs" /> Logistics Fields (6)
              </button>

              <button
                type="button"
                onClick={addField}
                className="px-3.5 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-bold text-xs shadow-md shadow-indigo-500/20 transition-all flex items-center gap-1.5"
              >
                <i className="fa-solid fa-plus text-xs" /> Add Custom Field
              </button>
            </div>
          </div>

          {/* Active Fields Overview Badges Bar */}
          <div className="bg-slate-900/90 p-3.5 rounded-xl border border-slate-800 space-y-2">
            <div className="text-[11px] font-bold text-slate-400 uppercase tracking-wider flex items-center justify-between">
              <span><i className="fa-solid fa-list-check text-indigo-400 mr-1.5" /> All Configured Collected Fields Overview</span>
              <span className="text-[10px] text-indigo-300 font-mono">{fields.length} fields configured</span>
            </div>

            <div className="flex flex-wrap gap-2">
              {fields.map((f, i) => (
                <div key={i} className="px-3 py-1.5 rounded-lg bg-slate-950 border border-slate-700/80 text-xs text-slate-200 flex items-center gap-2 shadow-sm">
                  <span className="font-bold text-white">{i + 1}. {f.label}</span>
                  <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-md ${
                    f.type === 'select' ? 'bg-purple-500/20 text-purple-300 border border-purple-500/30' :
                    f.type === 'number' ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30' :
                    f.type === 'datetime' ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30' :
                    'bg-indigo-500/20 text-indigo-300 border border-indigo-500/30'
                  }`}>
                    {f.type}
                  </span>
                  {f.required && <span className="text-[10px] font-bold text-rose-400" title="Required Field">*Required</span>}
                </div>
              ))}
            </div>
          </div>

          {/* Detailed Fields Cards List */}
          <div className="space-y-4">
            {fields.map((field, idx) => (
              <div key={idx} className="p-4 rounded-xl bg-slate-900/90 border border-slate-800 space-y-3.5 text-xs hover:border-slate-700 transition-colors">
                <div className="grid grid-cols-1 sm:grid-cols-12 gap-3 items-center">
                  {/* Reorder and Index */}
                  <div className="sm:col-span-1 flex items-center gap-1">
                    <span className="w-6 h-6 rounded-lg bg-slate-800 text-slate-300 font-mono text-xs flex items-center justify-center font-bold">
                      {idx + 1}
                    </span>
                    <div className="flex flex-col gap-0.5">
                      <button
                        type="button"
                        onClick={() => moveField(idx, 'up')}
                        disabled={idx === 0}
                        className="text-[10px] text-slate-400 hover:text-indigo-400 disabled:opacity-30"
                        title="Move Up"
                      >
                        ▲
                      </button>
                      <button
                        type="button"
                        onClick={() => moveField(idx, 'down')}
                        disabled={idx === fields.length - 1}
                        className="text-[10px] text-slate-400 hover:text-indigo-400 disabled:opacity-30"
                        title="Move Down"
                      >
                        ▼
                      </button>
                    </div>
                  </div>

                  {/* Field Label */}
                  <div className="sm:col-span-3">
                    <label className="text-[10px] text-slate-400 font-semibold block mb-1">Field Display Name *</label>
                    <input
                      type="text"
                      required
                      value={field.label}
                      onChange={(e) => {
                        const newLabel = e.target.value;
                        const newKey = newLabel.toLowerCase().replace(/[^a-z0-9]/g, '_').replace(/_+/g, '_').replace(/^_+|_+$/g, '');
                        updateField(idx, { label: newLabel, key: field.key ? field.key : newKey });
                      }}
                      className="w-full bg-slate-950 border border-slate-700 p-2 rounded-lg text-slate-200 font-semibold focus:outline-none focus:border-indigo-500"
                    />
                  </div>

                  {/* Field Database System Key */}
                  <div className="sm:col-span-3">
                    <label className="text-[10px] text-slate-400 font-semibold block mb-1">Database System Key</label>
                    <input
                      type="text"
                      value={field.key}
                      onChange={(e) => updateField(idx, { key: e.target.value.toLowerCase().replace(/\s+/g, '_') })}
                      className="w-full bg-slate-950 border border-slate-700 p-2 rounded-lg text-indigo-300 font-mono text-xs focus:outline-none focus:border-indigo-500"
                    />
                  </div>

                  {/* Data Type Selection */}
                  <div className="sm:col-span-3">
                    <label className="text-[10px] text-slate-400 font-semibold block mb-1">Field Data Type</label>
                    <select
                      value={field.type}
                      onChange={(e) => {
                        const newType = e.target.value as any;
                        const defaultOpts = newType === 'select' ? (field.options && field.options.length > 0 ? field.options : ['Option 1', 'Option 2']) : undefined;
                        updateField(idx, { type: newType, options: defaultOpts });
                      }}
                      className="w-full bg-slate-950 border border-slate-700 p-2 rounded-lg text-slate-200 font-semibold focus:outline-none focus:border-indigo-500"
                    >
                      <option value="text">Text / String</option>
                      <option value="select">Dropdown Options (Select)</option>
                      <option value="number">Numeric Value</option>
                      <option value="datetime">Date & Time</option>
                    </select>
                  </div>

                  {/* Required Checkbox & Actions */}
                  <div className="sm:col-span-2 flex items-center justify-between sm:justify-end gap-3 pt-2 sm:pt-0">
                    <label className="flex items-center gap-1.5 text-slate-300 font-medium cursor-pointer">
                      <input
                        type="checkbox"
                        checked={field.required}
                        onChange={(e) => updateField(idx, { required: e.target.checked })}
                        className="rounded bg-slate-950 border-slate-700 text-indigo-600 focus:ring-0"
                      />
                      Required
                    </label>

                    <button
                      type="button"
                      onClick={() => removeField(idx)}
                      className="p-2 rounded-lg bg-rose-600/20 text-rose-300 hover:bg-rose-600/40 border border-rose-500/30 transition-colors"
                      title="Delete Field"
                    >
                      <i className="fa-solid fa-trash-can" />
                    </button>
                  </div>
                </div>

                {/* Sub-row for Select Dropdown Options */}
                {field.type === 'select' && (
                  <div className="bg-slate-950/80 p-3 rounded-lg border border-purple-500/20 space-y-1.5 animate-fade-in">
                    <div className="flex items-center justify-between">
                      <label className="text-[10px] font-bold text-purple-300 flex items-center gap-1">
                        <i className="fa-solid fa-list text-purple-400" />
                        Dropdown Options List (comma-separated):
                      </label>
                      <span className="text-[10px] text-slate-400 font-mono">
                        {field.options?.length || 0} options
                      </span>
                    </div>

                    <input
                      type="text"
                      value={field.options?.join(', ') || ''}
                      onChange={(e) => {
                        const parsedOpts = e.target.value.split(',').map(o => o.trim()).filter(Boolean);
                        updateField(idx, { options: parsedOpts });
                      }}
                      placeholder="e.g. Birthday Cake, Anniversary Cake, Tier Wedding Cake"
                      className="w-full bg-slate-900 border border-purple-500/40 p-2 rounded-lg text-slate-200 text-xs focus:outline-none focus:border-purple-400"
                    />

                    {field.options && field.options.length > 0 && (
                      <div className="flex flex-wrap gap-1.5 pt-1">
                        {field.options.map((opt, oIdx) => (
                          <span key={oIdx} className="bg-purple-900/40 border border-purple-500/30 text-purple-200 px-2 py-0.5 rounded-md text-[10px] font-medium">
                            ✓ {opt}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {/* Sub-row for Description / Examples */}
                <div className="grid grid-cols-1 sm:grid-cols-12 gap-3 items-center">
                  <div className="sm:col-span-12">
                    <input
                      type="text"
                      value={field.description || ''}
                      onChange={(e) => updateField(idx, { description: e.target.value })}
                      placeholder="Field description or voice prompt format hint (e.g. Belgian Dark Chocolate, Red Velvet / TRK-9821-IN)..."
                      className="w-full bg-slate-950/60 border border-slate-800 p-2 rounded-lg text-slate-400 text-[11px] focus:outline-none focus:border-slate-700"
                    />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Step 5: Conditional Rules & Priority Flags */}
        <div className="glass-panel p-5 sm:p-6 space-y-4 border border-slate-800">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <h3 className="text-sm font-bold text-indigo-300 uppercase tracking-wider flex items-center gap-2">
              <span className="w-6 h-6 rounded-full bg-indigo-500/20 text-indigo-300 flex items-center justify-center text-xs font-bold">5</span>
              Conditional Rules & Urgency Triggers ({conditions.length})
            </h3>

            <button
              type="button"
              onClick={addCondition}
              className="px-3 py-1.5 rounded-lg bg-amber-600/20 hover:bg-amber-600/40 text-amber-200 border border-amber-500/30 text-xs font-bold transition-all flex items-center gap-1"
            >
              <i className="fa-solid fa-plus text-[10px]" /> Add Rule
            </button>
          </div>

          <div className="space-y-3">
            {conditions.map((cond, idx) => (
              <div key={idx} className="p-3.5 rounded-xl bg-slate-900/90 border border-slate-800 space-y-2 text-xs">
                <div className="grid grid-cols-1 sm:grid-cols-12 gap-3 items-center">
                  <div className="sm:col-span-4">
                    <label className="text-[10px] text-amber-300 font-semibold block mb-1">Target Collected Field</label>
                    <select
                      value={cond.field}
                      onChange={(e) => updateCondition(idx, { field: e.target.value })}
                      className="w-full bg-slate-950 border border-slate-700 p-2 rounded-lg text-slate-200 font-semibold focus:outline-none"
                    >
                      {fields.map(f => (
                        <option key={f.key} value={f.key}>{f.label} ({f.key})</option>
                      ))}
                    </select>
                  </div>

                  <div className="sm:col-span-3">
                    <label className="text-[10px] text-slate-400 font-semibold block mb-1">Operator</label>
                    <select
                      value={cond.operator}
                      onChange={(e) => updateCondition(idx, { operator: e.target.value as any })}
                      className="w-full bg-slate-950 border border-slate-700 p-2 rounded-lg text-slate-200 focus:outline-none"
                    >
                      <option value="within_hours">within_hours (Under X hours)</option>
                      <option value="equals">equals (Matches text)</option>
                      <option value="exists">exists (Field provided)</option>
                    </select>
                  </div>

                  <div className="sm:col-span-3">
                    <label className="text-[10px] text-slate-400 font-semibold block mb-1">Value / Hours</label>
                    <input
                      type="text"
                      value={cond.value ?? ''}
                      onChange={(e) => updateCondition(idx, { value: e.target.value })}
                      placeholder="e.g. 24 or New Delivery Request"
                      className="w-full bg-slate-950 border border-slate-700 p-2 rounded-lg text-slate-200 focus:outline-none"
                    />
                  </div>

                  <div className="sm:col-span-2 text-right pt-2 sm:pt-0">
                    <button
                      type="button"
                      onClick={() => removeCondition(idx)}
                      className="p-2 rounded-lg bg-rose-600/20 text-rose-300 hover:bg-rose-600/40 border border-rose-500/30 transition-colors"
                      title="Remove Rule"
                    >
                      <i className="fa-solid fa-trash-can" />
                    </button>
                  </div>
                </div>

                <div>
                  <input
                    type="text"
                    value={cond.note || ''}
                    onChange={(e) => updateCondition(idx, { note: e.target.value })}
                    placeholder="Rule explanation (e.g. Required under 24 hours -> Flag Urgent Order)..."
                    className="w-full bg-slate-950/70 border border-slate-800 p-2 rounded-lg text-slate-300 text-xs focus:outline-none"
                  />
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Submit Actions */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-4 pt-2">
          <button
            type="button"
            onClick={() => onTestWorkflow(selectedWorkflowId === 'new' ? workflows[0]?.id || 'wf-cake-01' : selectedWorkflowId)}
            className="w-full sm:w-auto px-5 py-2.5 rounded-xl bg-slate-900 hover:bg-slate-800 text-slate-200 border border-slate-700 font-bold text-xs transition-all flex items-center justify-center gap-2"
          >
            <i className="fa-solid fa-circle-play text-indigo-400" /> Test in AI Phone Simulator
          </button>

          <button
            type="submit"
            disabled={saving}
            className="w-full sm:w-auto px-8 py-3 rounded-xl bg-gradient-to-r from-indigo-600 to-blue-600 hover:from-indigo-500 hover:to-blue-500 text-white font-bold text-xs shadow-lg shadow-indigo-500/20 transition-all flex items-center justify-center gap-2"
          >
            {saving ? <i className="fa-solid fa-spinner animate-spin" /> : <i className="fa-solid fa-floppy-disk" />}
            {saving ? 'Saving Workflow...' : 'Save Workflow & Operating Schedule'}
          </button>
        </div>
      </form>
    </div>
  );
};
