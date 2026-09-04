import React, { useState } from 'react';
import { Business, Workflow, WorkflowField, WorkflowCondition, BusinessHours } from '../types';

interface WorkflowBuilderProps {
  businesses: Business[];
  workflows: Workflow[];
  onSaveWorkflow: (workflowData: Partial<Workflow>) => Promise<void>;
  onTestWorkflow: (workflowId: string) => void;
}

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
    'We are currently closed for the day. Our business operating hours are Mon-Sat 9 AM to 6 PM. We have logged your request and will follow up first thing tomorrow.'
  );

  // Fields State
  const [fields, setFields] = useState<WorkflowField[]>([
    { key: 'order_type', label: 'Order Type', type: 'select', options: ['New Order', 'Enquiry'], required: true },
    { key: 'details', label: 'Order Details', type: 'text', required: true }
  ]);

  // Conditions State
  const [conditions, setConditions] = useState<WorkflowCondition[]>([
    { field: 'required_date', operator: 'within_hours', value: 24, action_override: 'mark_urgent', note: 'If required within 24 hours -> Mark urgent' }
  ]);

  // Actions State
  const [actions, setActions] = useState<string[]>(['create_order_enquiry', 'send_sms_alert']);

  const [saving, setSaving] = useState(false);
  const [successMsg, setSuccessMsg] = useState('');

  const allWeekDays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

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

  // Handle selecting existing workflow to edit
  const handleSelectWorkflow = (id: string) => {
    setSelectedWorkflowId(id);
    setSuccessMsg('');

    if (id === 'new') {
      setName('');
      setIndustry('Custom Business');
      setGreeting('Hello! Thank you for calling. We missed your call. How can we assist you?');
      setClosingMessage('Thank you! Your information is recorded. We will follow up shortly.');
      setBhEnabled(true);
      setBhDays(['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']);
      setBhStartTime('09:00');
      setBhEndTime('18:00');
      setBhAfterHoursGreeting('We are currently closed for the day. Our business operating hours are Mon-Sat 9 AM to 6 PM. We have logged your request.');
      setFields([
        { key: 'service_needed', label: 'Service Needed', type: 'text', required: true },
        { key: 'preferred_date', label: 'Preferred Date', type: 'datetime', required: true }
      ]);
      setConditions([]);
      setActions(['create_enquiry']);
      return;
    }

    const wf = workflows.find(w => w.id === id);
    if (wf) {
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
    }
  };

  const addField = () => {
    setFields([...fields, { key: `field_${Date.now().toString().slice(-4)}`, label: 'New Field', type: 'text', required: false }]);
  };

  const updateField = (index: number, updated: Partial<WorkflowField>) => {
    const copy = [...fields];
    copy[index] = { ...copy[index], ...updated };
    setFields(copy);
  };

  const removeField = (index: number) => {
    setFields(fields.filter((_, i) => i !== index));
  };

  const addCondition = () => {
    setConditions([
      ...conditions,
      { field: 'required_date', operator: 'within_hours', value: 24, action_override: 'mark_urgent', note: 'Mark urgent if under 24 hours' }
    ]);
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
          <p className="text-xs text-slate-400 mt-0.5">Configure missed-call logic, service availability timings, collected fields, & conditional rules</p>
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
                placeholder="e.g. Missed Call Appointment Booking"
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

        {/* Step 4: Captured Form Fields */}
        <div className="glass-panel p-5 sm:p-6 space-y-4 border border-slate-800">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <h3 className="text-sm font-bold text-indigo-300 uppercase tracking-wider flex items-center gap-2">
              <span className="w-6 h-6 rounded-full bg-indigo-500/20 text-indigo-300 flex items-center justify-center text-xs font-bold">4</span>
              Collected Customer Information Fields ({fields.length})
            </h3>

            <button
              type="button"
              onClick={addField}
              className="px-3 py-1.5 rounded-lg bg-indigo-600/20 hover:bg-indigo-600/40 text-indigo-200 border border-indigo-500/30 text-xs font-bold transition-all flex items-center gap-1"
            >
              <i className="fa-solid fa-plus text-[10px]" /> Add Field
            </button>
          </div>

          <div className="space-y-3">
            {fields.map((field, idx) => (
              <div key={idx} className="p-3.5 rounded-xl bg-slate-900/80 border border-slate-800 grid grid-cols-1 sm:grid-cols-12 gap-3 items-center text-xs">
                <div className="sm:col-span-3">
                  <label className="text-[10px] text-slate-400 font-semibold block mb-1">Field Label</label>
                  <input
                    type="text"
                    value={field.label}
                    onChange={(e) => updateField(idx, { label: e.target.value, key: e.target.value.toLowerCase().replace(/\s+/g, '_') })}
                    className="w-full bg-slate-950 border border-slate-700 p-2 rounded-lg text-slate-200 focus:outline-none"
                  />
                </div>

                <div className="sm:col-span-3">
                  <label className="text-[10px] text-slate-400 font-semibold block mb-1">Data Type</label>
                  <select
                    value={field.type}
                    onChange={(e) => updateField(idx, { type: e.target.value as any })}
                    className="w-full bg-slate-950 border border-slate-700 p-2 rounded-lg text-slate-200 focus:outline-none"
                  >
                    <option value="text">Text / String</option>
                    <option value="select">Dropdown Options</option>
                    <option value="number">Numeric Value</option>
                    <option value="datetime">Date & Time</option>
                  </select>
                </div>

                <div className="sm:col-span-4 flex items-center gap-3 pt-4 sm:pt-0">
                  <label className="flex items-center gap-1.5 text-slate-300 font-medium cursor-pointer">
                    <input
                      type="checkbox"
                      checked={field.required}
                      onChange={(e) => updateField(idx, { required: e.target.checked })}
                      className="rounded bg-slate-950 border-slate-700 text-indigo-600 focus:ring-0"
                    />
                    Required Field
                  </label>
                </div>

                <div className="sm:col-span-2 text-right">
                  <button
                    type="button"
                    onClick={() => removeField(idx)}
                    className="p-2 rounded-lg bg-rose-600/20 text-rose-300 hover:bg-rose-600/40 border border-rose-500/30 transition-colors"
                  >
                    <i className="fa-solid fa-trash-can" />
                  </button>
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
              <div key={idx} className="p-3.5 rounded-xl bg-slate-900/80 border border-slate-800 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 text-xs">
                <div className="space-y-1 flex-1">
                  <div className="font-bold text-amber-300 flex items-center gap-1.5">
                    <i className="fa-solid fa-bolt text-amber-400" />
                    If field <strong className="text-white">'{cond.field}'</strong> matches <span className="text-indigo-300">{cond.operator}</span>
                  </div>
                  <input
                    type="text"
                    value={cond.note || ''}
                    onChange={(e) => {
                      const copy = [...conditions];
                      copy[idx].note = e.target.value;
                      setConditions(copy);
                    }}
                    placeholder="Rule description e.g. Required under 24h -> Mark Urgent"
                    className="w-full bg-slate-950 border border-slate-700 p-1.5 rounded-lg text-slate-200 text-xs"
                  />
                </div>

                <button
                  type="button"
                  onClick={() => removeCondition(idx)}
                  className="p-2 rounded-lg bg-rose-600/20 text-rose-300 hover:bg-rose-600/40 border border-rose-500/30 transition-colors"
                >
                  <i className="fa-solid fa-trash-can" />
                </button>
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
