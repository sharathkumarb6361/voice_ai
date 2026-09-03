import React, { useState } from 'react';
import { MissedCallRecord, Business } from '../types';

interface DashboardProps {
  records: MissedCallRecord[];
  businesses?: Business[];
  onStatusChange: (id: string, newStatus: string) => void;
  onLaunchSimulator: (businessId: string, workflowId: string) => void;
  onRefresh?: () => void;
}

export const Dashboard: React.FC<DashboardProps> = ({
  records,
  businesses = [],
  onStatusChange,
  onLaunchSimulator,
  onRefresh
}) => {
  const [selectedRecord, setSelectedRecord] = useState<MissedCallRecord | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [businessFilter, setBusinessFilter] = useState('All');
  const [statusFilter, setStatusFilter] = useState('All');
  const [urgencyFilter, setUrgencyFilter] = useState('All');
  const [isRefreshing, setIsRefreshing] = useState(false);

  const handleRefreshClick = async () => {
    if (!onRefresh) return;
    setIsRefreshing(true);
    await onRefresh();
    setTimeout(() => setIsRefreshing(false), 500);
  };

  // Computed stats
  const totalCalls = records.length;
  const urgentCount = records.filter(r => r.urgency === 'Urgent' || r.urgency === 'Critical').length;
  const pendingCount = records.filter(r => r.followup_status === 'Pending').length;
  const calendarToolsCount = records.filter(r => r.tools_executed?.some(t => t.tool.includes('calendar'))).length;

  const filteredRecords = records.filter(r => {
    const matchesSearch =
      r.caller_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      r.caller_phone.includes(searchQuery) ||
      (r.business_name || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
      r.intent.toLowerCase().includes(searchQuery.toLowerCase());

    const matchesBusiness = businessFilter === 'All' || r.business_id === businessFilter || r.business_name === businessFilter;
    const matchesStatus = statusFilter === 'All' || r.followup_status === statusFilter;
    const matchesUrgency = urgencyFilter === 'All' || r.urgency === urgencyFilter;

    return matchesSearch && matchesBusiness && matchesStatus && matchesUrgency;
  });

  const getUrgencyBadge = (urgency: string) => {
    switch (urgency) {
      case 'Critical':
        return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] sm:text-xs font-bold bg-rose-500/20 text-rose-400 border border-rose-500/30 animate-pulse"><i className="fa-solid fa-shield-halved" /> CRITICAL</span>;
      case 'Urgent':
        return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] sm:text-xs font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30"><i className="fa-solid fa-triangle-exclamation" /> URGENT (24h)</span>;
      default:
        return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] sm:text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">Normal</span>;
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'Pending':
        return <span className="px-2 py-0.5 rounded-lg text-[10px] sm:text-xs font-semibold bg-amber-500/20 text-amber-300 border border-amber-500/30">Pending</span>;
      case 'Contacted':
        return <span className="px-2 py-0.5 rounded-lg text-[10px] sm:text-xs font-semibold bg-blue-500/20 text-blue-300 border border-blue-500/30">Contacted</span>;
      case 'Completed':
        return <span className="px-2 py-0.5 rounded-lg text-[10px] sm:text-xs font-semibold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">Completed</span>;
      case 'Closed':
        return <span className="px-2 py-0.5 rounded-lg text-[10px] sm:text-xs font-semibold bg-slate-700/50 text-slate-400 border border-slate-600/30">Closed</span>;
      default:
        return null;
    }
  };

  return (
    <div className="space-y-6 sm:space-y-8">
      {/* Top Header & Sync Bar */}
      <div className="glass-panel p-4 sm:p-5 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <h2 className="text-lg sm:text-xl font-bold text-white flex items-center gap-2">
            <i className="fa-solid fa-chart-line text-indigo-400" />
            Voice AI Customer Call Operations Dashboard
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">Captured customer details, AI summaries, tool execution logs, and priority follow-ups</p>
        </div>

        {onRefresh && (
          <button
            onClick={handleRefreshClick}
            disabled={isRefreshing}
            className="w-full md:w-auto flex items-center justify-center gap-2 px-4 py-2 rounded-xl bg-indigo-600/20 hover:bg-indigo-600/40 text-indigo-200 border border-indigo-500/30 text-xs font-bold transition-all"
          >
            <i className={`fa-solid fa-arrows-rotate ${isRefreshing ? 'animate-spin' : ''}`} />
            {isRefreshing ? 'Syncing...' : 'Sync Live Records'}
          </button>
        )}
      </div>

      {/* Top Stat Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5 sm:gap-5">
        <div className="glass-panel p-4 sm:p-5 relative overflow-hidden glass-card-hover border-t-2 border-t-indigo-500">
          <div className="absolute -right-4 -bottom-4 w-24 h-24 bg-indigo-500/15 rounded-full blur-2xl pointer-events-none" />
          <div className="flex items-center justify-between mb-2">
            <span className="text-[11px] sm:text-xs font-bold uppercase tracking-wider text-slate-400">Total Calls</span>
            <div className="w-8 h-8 rounded-xl bg-indigo-500/20 border border-indigo-500/30 flex items-center justify-center">
              <i className="fa-solid fa-phone-slash text-indigo-400 text-sm" />
            </div>
          </div>
          <div className="text-2xl sm:text-3xl font-black text-white tracking-tight">{totalCalls}</div>
          <p className="text-[10px] sm:text-xs text-indigo-300/90 font-medium mt-1 flex items-center gap-1">
            <i className="fa-solid fa-arrow-trend-up text-indigo-400" /> Processed multi-tenant calls
          </p>
        </div>

        <div className="glass-panel p-4 sm:p-5 relative overflow-hidden glass-card-hover border-t-2 border-t-amber-500">
          <div className="absolute -right-4 -bottom-4 w-24 h-24 bg-amber-500/15 rounded-full blur-2xl pointer-events-none" />
          <div className="flex items-center justify-between mb-2">
            <span className="text-[11px] sm:text-xs font-bold uppercase tracking-wider text-slate-400">Urgent Flags</span>
            <div className="w-8 h-8 rounded-xl bg-amber-500/20 border border-amber-500/30 flex items-center justify-center">
              <i className="fa-solid fa-triangle-exclamation text-amber-400 text-sm" />
            </div>
          </div>
          <div className="text-2xl sm:text-3xl font-black text-amber-300 tracking-tight">{urgentCount}</div>
          <p className="text-[10px] sm:text-xs text-amber-300/80 font-medium mt-1 flex items-center gap-1">
            <i className="fa-solid fa-bolt text-amber-400" /> Rule engine flagged
          </p>
        </div>

        <div className="glass-panel p-4 sm:p-5 relative overflow-hidden glass-card-hover border-t-2 border-t-emerald-500">
          <div className="absolute -right-4 -bottom-4 w-24 h-24 bg-emerald-500/15 rounded-full blur-2xl pointer-events-none" />
          <div className="flex items-center justify-between mb-2">
            <span className="text-[11px] sm:text-xs font-bold uppercase tracking-wider text-slate-400">Pending Action</span>
            <div className="w-8 h-8 rounded-xl bg-emerald-500/20 border border-emerald-500/30 flex items-center justify-center">
              <i className="fa-solid fa-clock text-emerald-400 text-sm animate-pulse" />
            </div>
          </div>
          <div className="text-2xl sm:text-3xl font-black text-emerald-400 tracking-tight">{pendingCount}</div>
          <p className="text-[10px] sm:text-xs text-emerald-300/80 font-medium mt-1 flex items-center gap-1">
            <i className="fa-solid fa-user-clock text-emerald-400" /> Requires owner follow-up
          </p>
        </div>

        <div className="glass-panel p-4 sm:p-5 relative overflow-hidden glass-card-hover border-t-2 border-t-blue-500">
          <div className="absolute -right-4 -bottom-4 w-24 h-24 bg-blue-500/15 rounded-full blur-2xl pointer-events-none" />
          <div className="flex items-center justify-between mb-2">
            <span className="text-[11px] sm:text-xs font-bold uppercase tracking-wider text-slate-400">Calendar Tools</span>
            <div className="w-8 h-8 rounded-xl bg-blue-500/20 border border-blue-500/30 flex items-center justify-center">
              <i className="fa-solid fa-calendar-check text-blue-400 text-sm" />
            </div>
          </div>
          <div className="text-2xl sm:text-3xl font-black text-blue-300 tracking-tight">{calendarToolsCount}</div>
          <p className="text-[10px] sm:text-xs text-blue-300/80 font-medium mt-1 flex items-center gap-1">
            <i className="fa-solid fa-circle-check text-blue-400" /> Synced to Google Calendar
          </p>
        </div>
      </div>

      {/* Filter and Search Toolbar */}
      <div className="glass-panel p-4 flex flex-col md:flex-row items-center justify-between gap-3 text-xs">
        <div className="relative w-full md:w-80">
          <i className="fa-solid fa-magnifying-glass text-slate-400 text-xs absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            placeholder="Search by caller, phone, business..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-slate-900/80 border border-white/10 rounded-xl pl-9 pr-4 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
          />
        </div>

        <div className="grid grid-cols-2 sm:flex sm:flex-wrap items-center gap-2.5 w-full md:w-auto">
          {/* Business Profile Selector */}
          <div className="flex items-center gap-1.5 bg-slate-900/80 border border-white/10 px-2.5 py-1.5 rounded-xl">
            <i className="fa-solid fa-building-user text-indigo-400" />
            <select
              value={businessFilter}
              onChange={(e) => setBusinessFilter(e.target.value)}
              className="bg-transparent text-slate-200 font-semibold focus:outline-none cursor-pointer text-xs w-full"
            >
              <option value="All" className="bg-slate-900">All Businesses</option>
              {businesses.map(b => (
                <option key={b.id} value={b.id} className="bg-slate-900">{b.name}</option>
              ))}
            </select>
          </div>

          <div className="flex items-center gap-1.5 bg-slate-900/80 border border-white/10 px-2.5 py-1.5 rounded-xl">
            <i className="fa-solid fa-filter text-indigo-400" />
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="bg-transparent text-slate-200 font-semibold focus:outline-none cursor-pointer text-xs w-full"
            >
              <option value="All" className="bg-slate-900">All Statuses</option>
              <option value="Pending" className="bg-slate-900">Pending</option>
              <option value="Contacted" className="bg-slate-900">Contacted</option>
              <option value="Completed" className="bg-slate-900">Completed</option>
              <option value="Closed" className="bg-slate-900">Closed</option>
            </select>
          </div>

          <div className="flex items-center gap-1.5 bg-slate-900/80 border border-white/10 px-2.5 py-1.5 rounded-xl col-span-2 sm:col-auto">
            <i className="fa-solid fa-flag text-amber-400" />
            <select
              value={urgencyFilter}
              onChange={(e) => setUrgencyFilter(e.target.value)}
              className="bg-transparent text-slate-200 font-semibold focus:outline-none cursor-pointer text-xs w-full"
            >
              <option value="All" className="bg-slate-900">All Priorities</option>
              <option value="Normal" className="bg-slate-900">Normal</option>
              <option value="Urgent" className="bg-slate-900">Urgent</option>
              <option value="Critical" className="bg-slate-900">Critical</option>
            </select>
          </div>
        </div>
      </div>

      {/* Desktop Records Table (Visible on md+) */}
      <div className="hidden md:block glass-panel overflow-hidden border border-white/10">
        <div className="px-6 py-4 border-b border-white/10 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-bold text-white flex items-center gap-2">
              <i className="fa-solid fa-phone-slash text-indigo-400" />
              Customer Missed Call & Follow-up Log ({filteredRecords.length})
            </h2>
            <p className="text-xs text-slate-400">Real-time captured details, AI summaries, and tool calling results</p>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-900/80 text-slate-400 uppercase tracking-wider text-[11px] border-b border-white/10">
              <tr>
                <th className="px-6 py-3.5">Caller & Contact</th>
                <th className="px-6 py-3.5">Business & Workflow</th>
                <th className="px-6 py-3.5">Intent / Request</th>
                <th className="px-6 py-3.5">Urgency</th>
                <th className="px-6 py-3.5">Tools Executed</th>
                <th className="px-6 py-3.5">Follow-up Status</th>
                <th className="px-6 py-3.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {filteredRecords.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-6 py-12 text-center text-slate-500">
                    No customer call records found for this filter. Run a test call in the Phone Simulator!
                  </td>
                </tr>
              ) : (
                filteredRecords.map((record) => (
                  <tr key={record.id} className="hover:bg-white/[0.02] transition-colors">
                    {/* Caller Info */}
                    <td className="px-6 py-4">
                      <div className="font-semibold text-slate-100 text-sm">{record.caller_name}</div>
                      <div className="text-slate-400 font-mono text-[11px]">{record.caller_phone}</div>
                      <div className="text-[10px] text-slate-500 mt-1">{new Date(record.created_at).toLocaleString()}</div>
                    </td>

                    {/* Business Info */}
                    <td className="px-6 py-4">
                      <div className="font-medium text-indigo-300">{record.business_name || 'Business'}</div>
                      <div className="text-slate-400 text-[11px]">{record.workflow_name}</div>
                    </td>

                    {/* Intent & Summary */}
                    <td className="px-6 py-4 max-w-xs">
                      <div className="font-semibold text-slate-200 truncate">{record.intent}</div>
                      <div className="text-slate-400 text-[11px] line-clamp-2 mt-0.5">{record.ai_summary}</div>
                    </td>

                    {/* Urgency */}
                    <td className="px-6 py-4">
                      {getUrgencyBadge(record.urgency)}
                    </td>

                    {/* Executed Tools Badges */}
                    <td className="px-6 py-4">
                      <div className="flex flex-wrap gap-1">
                        {record.tools_executed && record.tools_executed.length > 0 ? (
                          record.tools_executed.map((tool, i) => (
                            <span
                              key={i}
                              className={`px-2 py-0.5 rounded text-[10px] font-mono border ${
                                tool.tool.includes('calendar')
                                  ? 'bg-purple-500/20 text-purple-300 border-purple-500/30'
                                  : tool.tool.includes('delivery') || tool.tool.includes('crm')
                                  ? 'bg-cyan-500/20 text-cyan-300 border-cyan-500/30'
                                  : 'bg-indigo-500/20 text-indigo-300 border-indigo-500/30'
                              }`}
                            >
                              <i className="fa-solid fa-bolt mr-1" /> {tool.tool}
                            </span>
                          ))
                        ) : (
                          <span className="text-slate-500 text-[11px]">No tools called</span>
                        )}
                      </div>
                    </td>

                    {/* Followup Status Selector */}
                    <td className="px-6 py-4">
                      <select
                        value={record.followup_status}
                        onChange={(e) => onStatusChange(record.id, e.target.value)}
                        className="bg-slate-900 border border-white/10 text-xs font-semibold rounded-lg px-2.5 py-1.5 text-slate-200 focus:outline-none focus:border-indigo-500 cursor-pointer"
                      >
                        <option value="Pending">Pending</option>
                        <option value="Contacted">Contacted</option>
                        <option value="Completed">Completed</option>
                        <option value="Closed">Closed</option>
                      </select>
                    </td>

                    {/* Actions */}
                    <td className="px-6 py-4 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={() => setSelectedRecord(record)}
                          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600/30 hover:bg-indigo-600/50 text-indigo-200 border border-indigo-500/30 font-semibold transition-all"
                        >
                          Details <i className="fa-solid fa-chevron-right text-[10px]" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Mobile Records Card List View (Visible on mobile < md) */}
      <div className="block md:hidden space-y-3">
        <h3 className="text-sm font-bold text-white px-1 flex items-center justify-between">
          <span>Call Records ({filteredRecords.length})</span>
        </h3>

        {filteredRecords.length === 0 ? (
          <div className="glass-panel p-6 text-center text-slate-500 text-xs">
            No customer call records found matching filter.
          </div>
        ) : (
          filteredRecords.map((record) => (
            <div
              key={record.id}
              className="glass-panel p-4 space-y-3 border border-white/10 hover:border-indigo-500/40 transition-all text-xs"
            >
              <div className="flex items-start justify-between">
                <div>
                  <div className="font-bold text-slate-100 text-sm">{record.caller_name}</div>
                  <div className="text-slate-400 font-mono text-[11px]">{record.caller_phone}</div>
                </div>
                <div>{getUrgencyBadge(record.urgency)}</div>
              </div>

              <div className="text-slate-300">
                <div className="font-semibold text-indigo-300">{record.intent}</div>
                <div className="text-slate-400 text-[11px] line-clamp-2 mt-0.5">{record.ai_summary}</div>
              </div>

              <div className="flex items-center justify-between pt-2 border-t border-white/5">
                <select
                  value={record.followup_status}
                  onChange={(e) => onStatusChange(record.id, e.target.value)}
                  className="bg-slate-900 border border-white/10 text-xs font-semibold rounded-lg px-2 py-1 text-slate-200 focus:outline-none"
                >
                  <option value="Pending">Pending</option>
                  <option value="Contacted">Contacted</option>
                  <option value="Completed">Completed</option>
                  <option value="Closed">Closed</option>
                </select>

                <button
                  onClick={() => setSelectedRecord(record)}
                  className="px-3 py-1 rounded-lg bg-indigo-600/30 text-indigo-200 border border-indigo-500/30 font-semibold text-xs"
                >
                  View Details ➔
                </button>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Record Details Modal */}
      {selectedRecord && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-center justify-center p-3 sm:p-4">
          <div className="glass-panel w-full max-w-3xl max-h-[90vh] overflow-y-auto p-4 sm:p-6 space-y-5 border border-indigo-500/30 shadow-2xl relative">
            <button
              onClick={() => setSelectedRecord(null)}
              className="absolute top-4 right-4 text-slate-400 hover:text-white text-lg font-bold"
            >
              ✕
            </button>

            {/* Modal Header */}
            <div className="flex items-start justify-between border-b border-white/10 pb-4 pr-6">
              <div>
                <h3 className="text-lg sm:text-xl font-bold text-white flex items-center gap-2">
                  <i className="fa-solid fa-phone-slash text-indigo-400" />
                  {selectedRecord.caller_name}
                </h3>
                <p className="text-xs text-indigo-300 mt-0.5">
                  {selectedRecord.caller_phone} • {selectedRecord.business_name}
                </p>
              </div>
              <div className="flex flex-col sm:flex-row items-end gap-1.5">
                {getUrgencyBadge(selectedRecord.urgency)}
                {getStatusBadge(selectedRecord.followup_status)}
              </div>
            </div>

            {/* AI Summary */}
            <div className="bg-indigo-950/40 p-3.5 rounded-xl border border-indigo-500/20">
              <h4 className="text-[11px] font-bold text-indigo-300 uppercase tracking-wider flex items-center gap-1.5 mb-1">
                <i className="fa-solid fa-wand-magic-sparkles text-indigo-400" /> AI Call Summary & Key Findings
              </h4>
              <p className="text-xs text-slate-200 leading-relaxed">{selectedRecord.ai_summary}</p>
            </div>

            {/* Structured Captured Data Fields */}
            <div>
              <h4 className="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-2">Collected Data Fields</h4>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {Object.entries(selectedRecord.collected_data || {}).map(([key, val]) => (
                  <div key={key} className="bg-slate-900/60 p-2.5 rounded-lg border border-white/5">
                    <div className="text-[10px] font-semibold text-indigo-300 uppercase">{key.replace(/_/g, ' ')}</div>
                    <div className="text-xs text-slate-100 font-medium mt-0.5">{String(val)}</div>
                  </div>
                ))}
              </div>
            </div>

            {/* Executed Tools Details */}
            {selectedRecord.tools_executed && selectedRecord.tools_executed.length > 0 && (
              <div>
                <h4 className="text-[11px] font-bold text-purple-400 uppercase tracking-wider mb-2">Tools & Integrations Called</h4>
                <div className="space-y-2">
                  {selectedRecord.tools_executed.map((tool, idx) => (
                    <div key={idx} className="bg-purple-950/30 border border-purple-500/20 p-3 rounded-lg text-xs font-mono">
                      <div className="font-bold text-purple-300"><i className="fa-solid fa-bolt text-purple-400 mr-1" /> Tool: {tool.tool}</div>
                      <div className="text-slate-400 text-[11px] mt-1 truncate">Args: {JSON.stringify(tool.args)}</div>
                      <div className="text-emerald-400 text-[11px] mt-0.5 truncate">Result: {JSON.stringify(tool.result)}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Transcript Log */}
            <div>
              <h4 className="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                <i className="fa-solid fa-comments text-indigo-400" /> Full Voice Conversation Transcript
              </h4>
              <div className="space-y-2 max-h-60 overflow-y-auto bg-slate-900/80 p-3.5 rounded-xl border border-white/5 text-xs">
                {selectedRecord.transcript && selectedRecord.transcript.length > 0 ? (
                  selectedRecord.transcript.map((msg, i) => (
                    <div
                      key={i}
                      className={`p-2.5 rounded-lg max-w-[90%] sm:max-w-[85%] ${
                        msg.role === 'user'
                          ? 'bg-indigo-600/30 text-indigo-100 ml-auto border border-indigo-500/30'
                          : 'bg-slate-800/80 text-slate-200 mr-auto border border-white/5'
                      }`}
                    >
                      <div className="text-[10px] font-bold text-slate-400 mb-0.5 uppercase">
                        {msg.role === 'user' ? '👤 Caller' : '🤖 AI Assistant'}
                      </div>
                      <div>{msg.content}</div>
                    </div>
                  ))
                ) : (
                  <p className="text-slate-500">No transcript available.</p>
                )}
              </div>
            </div>

            <div className="flex justify-end pt-2">
              <button
                onClick={() => setSelectedRecord(null)}
                className="w-full sm:w-auto px-5 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-bold text-xs"
              >
                Close Details
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
