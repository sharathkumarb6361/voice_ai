import React, { useState, useEffect, useMemo } from 'react';
import { CalendarEvent, Business } from '../types';
import { checkCalendarAvailability, syncGoogleCalendar } from '../lib/api';

interface CalendarMonitorProps {
  events: CalendarEvent[];
  businesses?: Business[];
  defaultBusinessFilter?: string;
  initialTargetDate?: string | null;
  onTargetDateConsumed?: () => void;
  onCancelEvent?: (eventId: string) => Promise<void>;
  onDeleteEvent?: (eventId: string) => Promise<void>;
  onDeleteAllEvents?: () => Promise<void>;
  onCreateEvent?: (data: Partial<CalendarEvent>) => Promise<void>;
  onUpdateEvent?: (eventId: string, data: Partial<CalendarEvent>) => Promise<void>;
  onSyncCalendar?: () => Promise<any>;
  onRefresh?: () => void;
}

export const CalendarMonitor: React.FC<CalendarMonitorProps> = ({
  events,
  businesses = [],
  defaultBusinessFilter = 'All',
  initialTargetDate,
  onTargetDateConsumed,
  onCancelEvent,
  onDeleteEvent,
  onDeleteAllEvents,
  onCreateEvent,
  onUpdateEvent,
  onSyncCalendar,
  onRefresh
}) => {
  const today = new Date();
  
  // View Month State for navigation
  const [viewDate, setViewDate] = useState<Date>(() => {
    if (initialTargetDate) {
      const d = new Date(initialTargetDate);
      if (!isNaN(d.getTime())) return d;
    }
    return new Date();
  });

  const [selectedDate, setSelectedDate] = useState<number | null>(() => {
    if (initialTargetDate) {
      const d = new Date(initialTargetDate);
      if (!isNaN(d.getTime())) return d.getDate();
    }
    return today.getDate();
  });

  const [businessFilter, setBusinessFilter] = useState(defaultBusinessFilter || 'All');
  const [statusFilter, setStatusFilter] = useState('All');
  const [searchQuery, setSearchQuery] = useState('');
  const [cancellingId, setCancellingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [isClearing, setIsClearing] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [syncStatusMsg, setSyncStatusMsg] = useState<string | null>(null);

  // Availability Checker Widget State
  const [checkDate, setCheckDate] = useState<string>(today.toISOString().split('T')[0]);
  const [checkTime, setCheckTime] = useState<string>('16:00');
  const [checkResult, setCheckResult] = useState<any | null>(null);
  const [isCheckingSlot, setIsCheckingSlot] = useState(false);

  // Schedule Modal State
  const [isScheduleModalOpen, setIsScheduleModalOpen] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [newBusinessId, setNewBusinessId] = useState(businesses[0]?.id || 'biz-cake-01');
  const [newDate, setNewDate] = useState(today.toISOString().split('T')[0]);
  const [newTime, setNewTime] = useState('14:00');
  const [newDuration, setNewDuration] = useState('30');
  const [newAttendeeName, setNewAttendeeName] = useState('');
  const [newAttendeePhone, setNewAttendeePhone] = useState('');
  const [newDescription, setNewDescription] = useState('');
  const [isSubmittingNew, setIsSubmittingNew] = useState(false);

  // Reschedule / Edit Modal State
  const [editingEvent, setEditingEvent] = useState<CalendarEvent | null>(null);
  const [editTitle, setEditTitle] = useState('');
  const [editDate, setEditDate] = useState('');
  const [editTime, setEditTime] = useState('');
  const [editAttendeeName, setEditAttendeeName] = useState('');
  const [editAttendeePhone, setEditAttendeePhone] = useState('');
  const [editDescription, setEditDescription] = useState('');
  const [editStatus, setEditStatus] = useState('Confirmed');
  const [isSubmittingEdit, setIsSubmittingEdit] = useState(false);

  // Month navigation calculations
  const currentMonthName = viewDate.toLocaleString('default', { month: 'long', year: 'numeric' });
  const currentYear = viewDate.getFullYear();
  const currentMonth = viewDate.getMonth();
  const daysInMonth = new Date(currentYear, currentMonth + 1, 0).getDate();
  const firstDayIndex = new Date(currentYear, currentMonth, 1).getDay();

  // Calendar events are already preloaded by App on tab navigation

  // Jump to target date if supplied externally (e.g. from Phone Simulator)
  useEffect(() => {
    if (initialTargetDate) {
      const d = new Date(initialTargetDate);
      if (!isNaN(d.getTime())) {
        setViewDate(d);
        setSelectedDate(d.getDate());
        if (onTargetDateConsumed) onTargetDateConsumed();
      }
    }
  }, [initialTargetDate]);

  // Update default business filter if parent changes authenticated owner
  useEffect(() => {
    if (defaultBusinessFilter && defaultBusinessFilter !== 'All') {
      setBusinessFilter(defaultBusinessFilter);
    }
  }, [defaultBusinessFilter]);

  // Month Navigation Handlers
  const handlePrevMonth = () => {
    setViewDate(prev => new Date(prev.getFullYear(), prev.getMonth() - 1, 1));
    setSelectedDate(null);
  };

  const handleNextMonth = () => {
    setViewDate(prev => new Date(prev.getFullYear(), prev.getMonth() + 1, 1));
    setSelectedDate(null);
  };

  const handleGoToToday = () => {
    const t = new Date();
    setViewDate(t);
    setSelectedDate(t.getDate());
  };

  // Filter events
  const filteredEvents = useMemo(() => {
    return events.filter(evt => {
      const matchesBiz = businessFilter === 'All' || evt.business_id === businessFilter;
      const matchesStatus = statusFilter === 'All' || evt.status === statusFilter;
      const searchLower = searchQuery.toLowerCase().trim();
      const matchesSearch = !searchLower || (
        evt.title.toLowerCase().includes(searchLower) ||
        evt.attendee_name.toLowerCase().includes(searchLower) ||
        evt.attendee_phone.toLowerCase().includes(searchLower) ||
        (evt.description || '').toLowerCase().includes(searchLower)
      );
      return matchesBiz && matchesStatus && matchesSearch;
    });
  }, [events, businessFilter, statusFilter, searchQuery]);

  // Upcoming confirmed events list sorted chronologically
  const upcomingEvents = useMemo(() => {
    const nowMs = Date.now() - 3600000;
    return [...filteredEvents]
      .filter(evt => {
        const d = new Date(evt.start_time).getTime();
        return !isNaN(d) && d >= nowMs && evt.status !== 'Cancelled';
      })
      .sort((a, b) => new Date(a.start_time).getTime() - new Date(b.start_time).getTime());
  }, [filteredEvents]);

  // Auto-select date with events if current selected date has no events on initial load
  useEffect(() => {
    if (selectedDate === today.getDate() && filteredEvents.length > 0) {
      const todayEvents = filteredEvents.filter(evt => {
        const d = new Date(evt.start_time);
        return !isNaN(d.getTime()) && d.getDate() === today.getDate() && d.getMonth() === today.getMonth() && d.getFullYear() === today.getFullYear();
      });
      if (todayEvents.length === 0 && upcomingEvents.length > 0) {
        const firstUpcoming = new Date(upcomingEvents[0].start_time);
        if (firstUpcoming.getMonth() === currentMonth && firstUpcoming.getFullYear() === currentYear) {
          setSelectedDate(firstUpcoming.getDate());
        }
      }
    }
  }, [filteredEvents, upcomingEvents]);

  const getEventsForDay = (day: number) => {
    return filteredEvents.filter(evt => {
      const evtDate = new Date(evt.start_time);
      if (isNaN(evtDate.getTime())) return false;
      return (
        evtDate.getDate() === day &&
        evtDate.getMonth() === currentMonth &&
        evtDate.getFullYear() === currentYear
      );
    });
  };

  const handleRefreshClick = async () => {
    setIsRefreshing(true);
    try {
      if (onSyncCalendar) {
        const res = await onSyncCalendar();
        if (res?.message) setSyncStatusMsg(res.message);
      } else {
        const res = await syncGoogleCalendar();
        if (res?.message) setSyncStatusMsg(res.message);
      }
      if (onRefresh) await onRefresh();
    } catch (err: any) {
      console.error(err);
    } finally {
      setTimeout(() => setIsRefreshing(false), 500);
      setTimeout(() => setSyncStatusMsg(null), 5000);
    }
  };

  const handleCancel = async (eventId: string) => {
    if (!onCancelEvent) return;
    setCancellingId(eventId);
    try {
      await onCancelEvent(eventId);
    } catch (err: any) {
      alert(`Cancellation failed: ${err.message}`);
    } finally {
      setCancellingId(null);
    }
  };

  const handleDelete = async (eventId: string, title: string) => {
    if (!window.confirm(`Are you sure you want to permanently delete the calendar appointment "${title}"?`)) {
      return;
    }
    setDeletingId(eventId);
    try {
      if (onDeleteEvent) {
        await onDeleteEvent(eventId);
      }
      if (editingEvent?.id === eventId) {
        setEditingEvent(null);
      }
      setSyncStatusMsg(`Appointment "${title}" was permanently deleted.`);
      setTimeout(() => setSyncStatusMsg(null), 4000);
    } catch (err: any) {
      alert(`Delete failed: ${err.message}`);
    } finally {
      setDeletingId(null);
    }
  };

  const handleClearAll = async () => {
    if (events.length === 0) return;
    if (!window.confirm(`Are you sure you want to permanently delete ALL ${events.length} calendar appointment(s)? This action cannot be undone.`)) {
      return;
    }
    setIsClearing(true);
    try {
      if (onDeleteAllEvents) {
        await onDeleteAllEvents();
      }
      setEditingEvent(null);
      setSyncStatusMsg(`Successfully removed all ${events.length} calendar appointments.`);
      setTimeout(() => setSyncStatusMsg(null), 4000);
    } catch (err: any) {
      alert(`Clear all failed: ${err.message}`);
    } finally {
      setIsClearing(false);
    }
  };

  const handleRunSlotCheck = async () => {
    setIsCheckingSlot(true);
    setCheckResult(null);
    try {
      const res = await checkCalendarAvailability(checkDate, checkTime, businessFilter !== 'All' ? businessFilter : undefined);
      setCheckResult(res);
    } catch (err: any) {
      setCheckResult({ available: false, message: `Error checking availability: ${err.message}` });
    } finally {
      setIsCheckingSlot(false);
    }
  };

  const openScheduleModalForDate = (day: number) => {
    const formattedDate = `${viewDate.getFullYear()}-${String(viewDate.getMonth() + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
    setNewDate(formattedDate);
    setIsScheduleModalOpen(true);
  };

  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle || !newAttendeeName || !newAttendeePhone) {
      alert('Please fill out event title, attendee name, and attendee phone number.');
      return;
    }

    setIsSubmittingNew(true);
    try {
      const startIso = new Date(`${newDate}T${newTime}:00`).toISOString();
      const durMinutes = parseInt(newDuration, 10) || 30;
      const endIso = new Date(new Date(`${newDate}T${newTime}:00`).getTime() + durMinutes * 60000).toISOString();

      const payload: Partial<CalendarEvent> = {
        business_id: newBusinessId,
        title: newTitle,
        start_time: startIso,
        end_time: endIso,
        attendee_name: newAttendeeName,
        attendee_phone: newAttendeePhone,
        description: newDescription
      };

      if (onCreateEvent) {
        await onCreateEvent(payload);
      } else {
        alert('Appointment successfully created.');
      }

      // Automatically focus on the newly scheduled date
      const scheduledD = new Date(`${newDate}T00:00:00`);
      if (!isNaN(scheduledD.getTime())) {
        setViewDate(scheduledD);
        setSelectedDate(scheduledD.getDate());
      }

      setIsScheduleModalOpen(false);
      setNewTitle('');
      setNewAttendeeName('');
      setNewAttendeePhone('');
      setNewDescription('');
      if (onRefresh) onRefresh();
    } catch (err: any) {
      alert(`Error creating event: ${err.message}`);
    } finally {
      setIsSubmittingNew(false);
    }
  };

  const openEditModal = (evt: CalendarEvent) => {
    setEditingEvent(evt);
    setEditTitle(evt.title);
    setEditAttendeeName(evt.attendee_name);
    setEditAttendeePhone(evt.attendee_phone);
    setEditDescription(evt.description || '');
    setEditStatus(evt.status || 'Confirmed');

    try {
      const d = new Date(evt.start_time);
      setEditDate(d.toISOString().split('T')[0]);
      setEditTime(d.toTimeString().substring(0, 5));
    } catch {
      setEditDate(today.toISOString().split('T')[0]);
      setEditTime('14:00');
    }
  };

  const handleEditSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingEvent || !onUpdateEvent) return;

    setIsSubmittingEdit(true);
    try {
      const startIso = new Date(`${editDate}T${editTime}:00`).toISOString();
      const endIso = new Date(new Date(`${editDate}T${editTime}:00`).getTime() + 30 * 60000).toISOString();

      await onUpdateEvent(editingEvent.id, {
        title: editTitle,
        start_time: startIso,
        end_time: endIso,
        attendee_name: editAttendeeName,
        attendee_phone: editAttendeePhone,
        description: editDescription,
        status: editStatus
      });

      setEditingEvent(null);
      if (onRefresh) onRefresh();
    } catch (err: any) {
      alert(`Error updating event: ${err.message}`);
    } finally {
      setIsSubmittingEdit(false);
    }
  };

  return (
    <div className="space-y-6 sm:space-y-8">
      {/* Header Bar */}
      <div className="glass-panel p-4 sm:p-5 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <h2 className="text-lg sm:text-xl font-bold text-white flex items-center gap-2">
            <i className="fa-solid fa-calendar-days text-purple-400" />
            Google Calendar Tool Calling & Visual Scheduling Hub
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">Live events scheduled, updated, or cancelled by the AI Voice Assistant via tool calling & direct owner scheduling</p>
        </div>

        <div className="flex flex-wrap items-center gap-2 sm:gap-3 w-full md:w-auto">
          <button
            onClick={() => setIsScheduleModalOpen(true)}
            className="flex-1 md:flex-initial flex items-center justify-center gap-2 px-3.5 py-2 rounded-xl bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white text-xs font-bold shadow-lg shadow-purple-600/30 transition-all"
          >
            <i className="fa-solid fa-plus" />
            Schedule Appointment
          </button>

          <button
            onClick={handleRefreshClick}
            disabled={isRefreshing}
            className="flex items-center justify-center gap-2 px-3 py-2 rounded-xl bg-purple-900/40 hover:bg-purple-900/60 text-purple-200 border border-purple-500/30 text-xs font-bold transition-all"
          >
            <i className={`fa-solid fa-arrows-rotate ${isRefreshing ? 'animate-spin' : ''}`} />
            {isRefreshing ? 'Syncing...' : 'Sync Calendar'}
          </button>

          <div className="hidden sm:flex items-center gap-2 bg-purple-950/60 border border-purple-500/30 px-3 py-2 rounded-xl text-xs">
            <i className="fa-solid fa-shield-heart text-emerald-400 text-sm" />
            <span className="text-purple-200 font-semibold">API:</span>
            <span className="text-emerald-400 font-bold">Active</span>
          </div>
        </div>
      </div>

      {syncStatusMsg && (
        <div className="p-3 bg-emerald-950/60 border border-emerald-500/40 rounded-xl text-xs text-emerald-200 flex items-center justify-between animate-fade-in">
          <span><i className="fa-solid fa-circle-check text-emerald-400 mr-2" />{syncStatusMsg}</span>
          <button onClick={() => setSyncStatusMsg(null)} className="text-slate-400 hover:text-white">✕</button>
        </div>
      )}

      {/* Filter and Search Bar */}
      <div className="glass-panel p-4 flex flex-col md:flex-row items-center justify-between gap-3 text-xs">
        <div className="grid grid-cols-2 sm:flex sm:flex-wrap items-center gap-2.5 w-full md:w-auto">
          {/* Business Profile Filter */}
          <div className="flex items-center gap-1.5 bg-slate-900/80 border border-white/10 px-3 py-2 rounded-xl">
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

          {/* Status Filter */}
          <div className="flex items-center gap-1.5 bg-slate-900/80 border border-white/10 px-3 py-2 rounded-xl">
            <i className="fa-solid fa-filter text-purple-400" />
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="bg-transparent text-slate-200 font-semibold focus:outline-none cursor-pointer text-xs w-full"
            >
              <option value="All" className="bg-slate-900">All Statuses</option>
              <option value="Confirmed" className="bg-slate-900">Confirmed</option>
              <option value="Cancelled" className="bg-slate-900">Cancelled</option>
            </select>
          </div>
        </div>

        {/* Search Box */}
        <div className="relative w-full md:w-64">
          <i className="fa-solid fa-magnifying-glass absolute left-3 top-2.5 text-slate-400" />
          <input
            type="text"
            placeholder="Search attendee, phone, title..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-slate-900/80 border border-white/10 pl-9 pr-3 py-1.5 rounded-xl text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500 text-xs"
          />
        </div>
      </div>

      {/* Visual Interactive Monthly Calendar Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 sm:gap-8">
        {/* Left Column: Monthly Calendar Visual Grid */}
        <div className="lg:col-span-8 glass-panel p-4 sm:p-6 space-y-4">
          <div className="flex flex-wrap items-center justify-between border-b border-white/10 pb-3 gap-2">
            <div className="flex items-center gap-2">
              <h3 className="text-base font-bold text-white flex items-center gap-2">
                <i className="fa-solid fa-calendar text-indigo-400" /> {currentMonthName}
              </h3>
              <div className="flex items-center gap-1 bg-slate-900 border border-white/10 rounded-xl p-0.5 ml-2">
                <button
                  onClick={handlePrevMonth}
                  className="p-1.5 hover:bg-slate-800 text-slate-400 hover:text-white rounded-lg text-xs transition-colors cursor-pointer"
                  title="Previous Month"
                >
                  <i className="fa-solid fa-chevron-left" />
                </button>
                <button
                  onClick={handleGoToToday}
                  className="px-2.5 py-1 hover:bg-slate-800 text-slate-300 hover:text-white rounded-lg text-[11px] font-bold transition-colors cursor-pointer"
                  title="Go to Current Month & Today"
                >
                  Today
                </button>
                <button
                  onClick={handleNextMonth}
                  className="p-1.5 hover:bg-slate-800 text-slate-400 hover:text-white rounded-lg text-xs transition-colors cursor-pointer"
                  title="Next Month"
                >
                  <i className="fa-solid fa-chevron-right" />
                </button>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-purple-300 bg-purple-950/50 px-3 py-1 rounded-full border border-purple-500/20">
                {filteredEvents.length} Total Events
              </span>
            </div>
          </div>

          {/* Days of Week Header */}
          <div className="grid grid-cols-7 text-center text-[10px] sm:text-xs font-bold text-slate-400 py-1 border-b border-white/5">
            <div><span className="sm:hidden">Su</span><span className="hidden sm:inline">Sun</span></div>
            <div><span className="sm:hidden">Mo</span><span className="hidden sm:inline">Mon</span></div>
            <div><span className="sm:hidden">Tu</span><span className="hidden sm:inline">Tue</span></div>
            <div><span className="sm:hidden">We</span><span className="hidden sm:inline">Wed</span></div>
            <div><span className="sm:hidden">Th</span><span className="hidden sm:inline">Thu</span></div>
            <div><span className="sm:hidden">Fr</span><span className="hidden sm:inline">Fri</span></div>
            <div><span className="sm:hidden">Sa</span><span className="hidden sm:inline">Sat</span></div>
          </div>

          {/* Days Cells Grid */}
          <div className="grid grid-cols-7 gap-1 sm:gap-2">
            {/* Empty padding cells for first day offset */}
            {Array.from({ length: firstDayIndex }).map((_, i) => (
              <div key={`empty-${i}`} className="h-12 sm:h-22 bg-slate-950/20 rounded-xl border border-white/[0.02]" />
            ))}

            {/* Calendar Days */}
            {Array.from({ length: daysInMonth }).map((_, i) => {
              const day = i + 1;
              const isToday = day === today.getDate() && currentMonth === today.getMonth() && currentYear === today.getFullYear();
              const isSelected = selectedDate === day;
              const dayEvents = getEventsForDay(day);
              const hasEvents = dayEvents.length > 0;

              return (
                <div
                  key={day}
                  onClick={() => setSelectedDate(day)}
                  className={`h-12 sm:h-22 p-1 sm:p-2 rounded-xl border transition-all cursor-pointer flex flex-col justify-between relative group ${
                    isSelected
                      ? 'bg-indigo-950/90 border-indigo-400 shadow-lg shadow-indigo-500/30 ring-2 ring-indigo-500/40'
                      : isToday
                      ? 'bg-purple-950/50 border-purple-400/80 shadow-md shadow-purple-500/20'
                      : hasEvents
                      ? 'bg-slate-900/90 border-indigo-500/40 hover:border-indigo-400 shadow-sm'
                      : 'bg-slate-900/40 border-white/5 hover:border-white/20'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1">
                      <span className={`text-[10px] sm:text-xs font-bold ${
                        isToday
                          ? 'text-purple-200 bg-purple-600 px-1 sm:px-1.5 py-0.5 rounded-md shadow'
                          : isSelected
                          ? 'text-white font-extrabold'
                          : 'text-slate-300'
                      }`}>
                        {day}
                      </span>
                      {hasEvents && (
                        <span className="hidden sm:flex items-center justify-center min-w-[16px] h-4 px-1 rounded-full text-[9px] font-extrabold bg-gradient-to-r from-purple-500 to-indigo-500 text-white shadow">
                          {dayEvents.length}
                        </span>
                      )}
                    </div>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        openScheduleModalForDate(day);
                      }}
                      className="hidden sm:block opacity-0 group-hover:opacity-100 text-[10px] text-slate-300 hover:text-indigo-300 transition-all p-0.5 rounded hover:bg-white/10"
                      title="Schedule on this day"
                    >
                      <i className="fa-solid fa-plus" />
                    </button>
                  </div>

                  {/* Mobile Event Dots Indicator */}
                  {hasEvents && (
                    <div className="flex sm:hidden items-center justify-center gap-1 mt-0.5 flex-wrap">
                      {dayEvents.slice(0, 3).map((evt, idx) => (
                        <span
                          key={idx}
                          className={`w-1.5 h-1.5 rounded-full ${
                            evt.status === 'Cancelled'
                              ? 'bg-rose-400'
                              : evt.business_id === 'biz-cake-01' || evt.title.toLowerCase().includes('cake')
                              ? 'bg-pink-400'
                              : 'bg-indigo-400'
                          }`}
                        />
                      ))}
                    </div>
                  )}

                  {/* Desktop Day Event Pills */}
                  <div className="hidden sm:block space-y-1 overflow-hidden mt-1">
                    {dayEvents.slice(0, 2).map(evt => (
                      <div
                        key={evt.id}
                        onClick={(e) => {
                          e.stopPropagation();
                          openEditModal(evt);
                        }}
                        className={`text-[8px] sm:text-[9px] font-semibold truncate px-1.5 py-0.5 rounded border transition-transform hover:scale-[1.02] ${
                          evt.status === 'Cancelled'
                            ? 'bg-rose-950/50 text-rose-300 border-rose-500/30 line-through'
                            : evt.business_id === 'biz-cake-01' || evt.title.toLowerCase().includes('cake')
                            ? 'bg-pink-950/60 text-pink-200 border-pink-500/40'
                            : 'bg-indigo-950/60 text-indigo-200 border-indigo-500/40'
                        }`}
                        title={`${evt.title} (${evt.status}) - Click to edit/reschedule`}
                      >
                        {evt.title}
                      </div>
                    ))}
                    {dayEvents.length > 2 && (
                      <div className="text-[7px] sm:text-[8px] text-indigo-300 font-bold px-0.5">
                        +{dayEvents.length - 2} more
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Right Column: Selected Day Appointments & Availability Checker */}
        <div className="lg:col-span-4 space-y-6">
          {/* Selected Day Events */}
          <div className="glass-panel p-4 sm:p-5 space-y-4">
            <div className="border-b border-white/10 pb-3 flex items-center justify-between">
              <div>
                <h3 className="text-xs sm:text-sm font-bold text-indigo-300 uppercase tracking-wider flex items-center gap-1.5">
                  <i className="fa-solid fa-calendar-day text-indigo-400" />
                  <span>
                    {selectedDate !== null
                      ? new Date(currentYear, currentMonth, selectedDate).toLocaleDateString('default', {
                          weekday: 'short',
                          month: 'short',
                          day: 'numeric'
                        })
                      : 'Selected Day'}
                  </span>
                </h3>
                <p className="text-[11px] text-slate-400 mt-0.5">
                  {selectedDate !== null && getEventsForDay(selectedDate).length} appointment(s) scheduled
                </p>
              </div>

              {selectedDate !== null && (
                <button
                  onClick={() => openScheduleModalForDate(selectedDate)}
                  className="px-2.5 py-1 rounded-lg bg-indigo-600/30 hover:bg-indigo-600/50 text-indigo-200 border border-indigo-500/30 text-[11px] font-bold transition-all flex items-center gap-1"
                  title="Schedule on selected date"
                >
                  <i className="fa-solid fa-plus text-[10px]" />
                  Add
                </button>
              )}
            </div>

            <div className="space-y-3 max-h-72 overflow-y-auto pr-1">
              {selectedDate === null || getEventsForDay(selectedDate).length === 0 ? (
                <div className="p-4 rounded-xl bg-slate-900/40 text-center space-y-2 border border-white/5">
                  <p className="text-slate-400 text-xs">No appointments scheduled for this date.</p>
                  {selectedDate !== null && (
                    <button
                      onClick={() => openScheduleModalForDate(selectedDate)}
                      className="px-3 py-1.5 rounded-xl bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white text-xs font-bold transition-all shadow-md inline-flex items-center gap-1.5"
                    >
                      <i className="fa-solid fa-calendar-plus text-xs" />
                      Schedule on Day {selectedDate}
                    </button>
                  )}
                </div>
              ) : (
                getEventsForDay(selectedDate).map(evt => (
                  <div
                    key={evt.id}
                    className="p-3 rounded-xl bg-purple-950/40 border border-purple-500/30 hover:border-purple-400 transition-all space-y-2 text-xs"
                  >
                    <div className="font-bold text-slate-100 flex items-center justify-between">
                      <span className="truncate pr-2">{evt.title}</span>
                      <span className={`text-[10px] font-mono ${evt.status === 'Confirmed' ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {evt.status === 'Confirmed' ? '✓ Confirmed' : '✕ Cancelled'}
                      </span>
                    </div>
                    <div className="text-[11px] text-purple-300 flex items-center justify-between">
                      <span className="flex items-center gap-1">
                        <i className="fa-solid fa-clock text-xs" />
                        {new Date(evt.start_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </span>

                      <div className="flex items-center gap-1.5">
                        <button
                          onClick={() => openEditModal(evt)}
                          className="px-2 py-0.5 rounded text-[10px] bg-indigo-600/30 hover:bg-indigo-600/50 text-indigo-200 border border-indigo-500/30 transition-all cursor-pointer"
                        >
                          Edit
                        </button>
                        {evt.status !== 'Cancelled' && onCancelEvent && (
                          <button
                            onClick={() => handleCancel(evt.id)}
                            disabled={cancellingId === evt.id}
                            className="px-2 py-0.5 rounded text-[10px] bg-rose-600/30 hover:bg-rose-600/50 text-rose-200 border border-rose-500/30 transition-all cursor-pointer"
                          >
                            {cancellingId === evt.id ? '...' : 'Cancel'}
                          </button>
                        )}
                      </div>
                    </div>
                    <div className="text-[11px] text-slate-400">
                      Attendee: <strong className="text-slate-200">{evt.attendee_name}</strong> ({evt.attendee_phone})
                    </div>
                  </div>
                ))
              )}
            </div>

            {/* Quick-Jump to Upcoming Appointments */}
            {upcomingEvents.length > 0 && (
              <div className="pt-3 border-t border-white/10 space-y-2">
                <div className="text-[11px] font-bold text-slate-300 flex items-center justify-between">
                  <span className="flex items-center gap-1.5">
                    <i className="fa-solid fa-clock-rotate-left text-purple-400" />
                    Upcoming Bookings ({upcomingEvents.length})
                  </span>
                  <span className="text-[10px] text-slate-500">Jump to date:</span>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {upcomingEvents.slice(0, 4).map(evt => {
                    const evtD = new Date(evt.start_time);
                    const dayNum = evtD.getDate();
                    const isSelected = selectedDate === dayNum && currentMonth === evtD.getMonth() && currentYear === evtD.getFullYear();
                    return (
                      <button
                        key={evt.id}
                        onClick={() => {
                          setViewDate(evtD);
                          setSelectedDate(dayNum);
                        }}
                        className={`px-2 py-1 rounded-lg text-[10px] font-semibold flex items-center gap-1 transition-all border cursor-pointer ${
                          isSelected
                            ? 'bg-indigo-600 text-white border-indigo-400 shadow-md'
                            : 'bg-slate-900/80 hover:bg-slate-800 text-purple-200 border-purple-500/30 hover:border-purple-400'
                        }`}
                        title={`${evt.title} - ${evtD.toLocaleDateString()}`}
                      >
                        <span>{evtD.toLocaleDateString('default', { month: 'short', day: 'numeric' })}</span>
                        <span className="opacity-60">&bull;</span>
                        <span className="truncate max-w-[90px]">{evt.attendee_name || evt.title}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
          </div>

          {/* Slot Availability Checker Widget */}
          <div className="glass-panel p-4 sm:p-5 space-y-3">
            <h3 className="text-xs font-bold text-purple-300 uppercase tracking-wider flex items-center gap-1.5">
              <i className="fa-solid fa-clock text-purple-400" /> Slot Availability Checker
            </h3>
            <div className="space-y-3 text-xs">
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-[10px] text-slate-400 font-semibold block mb-1">Date</label>
                  <input
                    type="date"
                    value={checkDate}
                    onChange={(e) => setCheckDate(e.target.value)}
                    className="w-full bg-slate-900 border border-white/10 p-2 rounded-lg text-slate-200 text-xs focus:outline-none focus:border-purple-500"
                  />
                </div>
                <div>
                  <label className="text-[10px] text-slate-400 font-semibold block mb-1">Time</label>
                  <input
                    type="time"
                    value={checkTime}
                    onChange={(e) => setCheckTime(e.target.value)}
                    className="w-full bg-slate-900 border border-white/10 p-2 rounded-lg text-slate-200 text-xs focus:outline-none focus:border-purple-500"
                  />
                </div>
              </div>

              <button
                onClick={handleRunSlotCheck}
                disabled={isCheckingSlot}
                className="w-full py-2 bg-indigo-900/50 hover:bg-indigo-900/80 text-indigo-200 border border-indigo-500/30 rounded-lg font-bold transition-all text-xs flex items-center justify-center gap-1.5"
              >
                {isCheckingSlot ? <i className="fa-solid fa-spinner animate-spin" /> : <i className="fa-solid fa-magnifying-glass-chart" />}
                {isCheckingSlot ? 'Checking...' : 'Check Availability'}
              </button>

              {checkResult && (
                <div className={`p-3 rounded-lg border text-[11px] space-y-1 ${
                  checkResult.available
                    ? 'bg-emerald-950/40 border-emerald-500/40 text-emerald-200'
                    : 'bg-rose-950/40 border-rose-500/40 text-rose-200'
                }`}>
                  <div className="font-bold flex items-center gap-1.5">
                    {checkResult.available ? (
                      <><i className="fa-solid fa-circle-check text-emerald-400" /> Slot Available!</>
                    ) : (
                      <><i className="fa-solid fa-circle-exclamation text-rose-400" /> Slot Conflict Detected</>
                    )}
                  </div>
                  <p className="text-[10px] opacity-90">{checkResult.message}</p>
                  {checkResult.recommended_slots && (
                    <div className="text-[10px] text-purple-300 font-semibold pt-1">
                      Alternatives: {checkResult.recommended_slots.join(', ')}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Desktop Calendar Events List Table (Visible on md+) */}
      <div className="hidden md:block glass-panel overflow-hidden border border-white/10">
        <div className="px-6 py-4 border-b border-white/10 flex items-center justify-between">
          <h3 className="text-base font-bold text-white flex items-center gap-2">
            <i className="fa-solid fa-wand-magic-sparkles text-purple-400" />
            All Calendar Appointments ({filteredEvents.length})
          </h3>
          {onDeleteAllEvents && events.length > 0 && (
            <button
              onClick={handleClearAll}
              disabled={isClearing}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-rose-500/15 hover:bg-rose-500/25 text-rose-300 border border-rose-500/30 text-xs font-semibold transition-all disabled:opacity-50"
              title="Delete all calendar appointments"
            >
              <i className={`fa-solid ${isClearing ? 'fa-spinner fa-spin' : 'fa-trash-can'}`} />
              {isClearing ? 'Clearing...' : 'Clear All Appointments'}
            </button>
          )}
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-900/80 text-slate-400 uppercase tracking-wider text-[11px] border-b border-white/10">
              <tr>
                <th className="px-6 py-3.5">Event Title</th>
                <th className="px-6 py-3.5">Date & Time</th>
                <th className="px-6 py-3.5">Customer Contact</th>
                <th className="px-6 py-3.5">Google Event ID</th>
                <th className="px-6 py-3.5">Status</th>
                <th className="px-6 py-3.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {filteredEvents.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-6 py-12 text-center text-slate-500">
                    No Google Calendar events found matching current criteria.
                  </td>
                </tr>
              ) : (
                filteredEvents.map((evt) => (
                  <tr key={evt.id} className="hover:bg-white/[0.02] transition-colors">
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-slate-100 text-sm">{evt.title}</span>
                        {evt.business_id === 'biz-cake-01' || evt.title.toLowerCase().includes('cake') ? (
                          <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-pink-500/20 text-pink-300 border border-pink-500/30">
                            🎂 Cake Order
                          </span>
                        ) : (
                          <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30">
                            📦 Logistics Pickup
                          </span>
                        )}
                      </div>
                      <div className="text-slate-400 text-[11px] mt-1 bg-slate-900/50 p-1.5 rounded-lg border border-white/5 font-sans leading-relaxed">
                        {evt.description || 'Scheduled via AI Assistant'}
                      </div>
                    </td>

                    <td className="px-6 py-4">
                      <div className="font-semibold text-purple-300 flex items-center gap-1.5">
                        <i className="fa-solid fa-clock text-purple-400 text-xs" />
                        {new Date(evt.start_time).toLocaleString()}
                      </div>
                    </td>

                    <td className="px-6 py-4">
                      <div className="font-semibold text-slate-200">{evt.attendee_name}</div>
                      <div className="text-slate-400 font-mono text-[11px]">{evt.attendee_phone}</div>
                    </td>

                    <td className="px-6 py-4">
                      <span className="font-mono text-[11px] text-indigo-300 bg-indigo-950/50 px-2 py-1 rounded border border-indigo-500/20">
                        {evt.google_event_id || evt.id}
                      </span>
                    </td>

                    <td className="px-6 py-4">
                      <span className={`px-2.5 py-1 rounded-full text-xs font-bold ${
                        evt.status === 'Confirmed'
                          ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                          : 'bg-rose-500/20 text-rose-300 border border-rose-500/30 line-through'
                      }`}>
                        {evt.status}
                      </span>
                    </td>

                    <td className="px-6 py-4 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={() => openEditModal(evt)}
                          className="px-3 py-1.5 rounded-lg bg-indigo-600/30 hover:bg-indigo-600/50 text-indigo-200 border border-indigo-500/30 text-xs font-bold transition-all"
                        >
                          Edit
                        </button>

                        {evt.status !== 'Cancelled' && onCancelEvent ? (
                          <button
                            onClick={() => handleCancel(evt.id)}
                            disabled={cancellingId === evt.id}
                            className="px-3 py-1.5 rounded-lg bg-amber-600/20 hover:bg-amber-600/40 text-amber-200 border border-amber-500/30 text-xs font-bold transition-all"
                            title="Cancel appointment"
                          >
                            {cancellingId === evt.id ? 'Cancelling...' : 'Cancel'}
                          </button>
                        ) : (
                          <span className="text-[11px] text-slate-500 italic px-1">Cancelled</span>
                        )}

                        <button
                          onClick={() => handleDelete(evt.id, evt.title)}
                          disabled={deletingId === evt.id}
                          className="flex items-center justify-center p-2 rounded-lg bg-rose-500/10 hover:bg-rose-500/30 text-rose-400 hover:text-rose-200 border border-rose-500/20 hover:border-rose-500/40 text-xs transition-all disabled:opacity-50"
                          title="Permanently delete appointment"
                        >
                          {deletingId === evt.id ? (
                            <i className="fa-solid fa-spinner animate-spin text-xs" />
                          ) : (
                            <i className="fa-solid fa-trash-can text-xs" />
                          )}
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

      {/* Mobile Calendar Events Card List (Visible on mobile < md) */}
      <div className="block md:hidden space-y-3">
        <div className="px-1 flex items-center justify-between">
          <h3 className="text-sm font-bold text-white">All Appointments ({filteredEvents.length})</h3>
          {onDeleteAllEvents && events.length > 0 && (
            <button
              onClick={handleClearAll}
              disabled={isClearing}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-rose-500/15 hover:bg-rose-500/25 text-rose-300 border border-rose-500/30 text-xs font-semibold"
            >
              <i className={`fa-solid ${isClearing ? 'fa-spinner fa-spin' : 'fa-trash-can'}`} />
              {isClearing ? 'Clearing...' : 'Clear All'}
            </button>
          )}
        </div>

        {filteredEvents.length === 0 ? (
          <div className="glass-panel p-6 text-center text-slate-500 text-xs">
            No calendar appointments found.
          </div>
        ) : (
          filteredEvents.map((evt) => (
            <div
              key={evt.id}
              className="glass-panel p-4 space-y-3 border border-white/10 hover:border-purple-500/40 transition-all text-xs"
            >
              <div className="flex items-start justify-between">
                <div>
                  <div className="font-bold text-slate-100 text-sm">{evt.title}</div>
                  <div className="text-purple-300 text-[11px] font-semibold flex items-center gap-1 mt-0.5">
                    <i className="fa-solid fa-clock text-xs" />
                    {new Date(evt.start_time).toLocaleString()}
                  </div>
                </div>
                <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                  evt.status === 'Confirmed' ? 'bg-emerald-500/20 text-emerald-300' : 'bg-rose-500/20 text-rose-300 line-through'
                }`}>
                  {evt.status}
                </span>
              </div>

              <div className="text-slate-400 text-[11px]">
                Attendee: <strong className="text-slate-200">{evt.attendee_name}</strong> ({evt.attendee_phone})
              </div>

              <div className="flex items-center justify-end gap-2 pt-2 border-t border-white/5">
                <button
                  onClick={() => openEditModal(evt)}
                  className="px-3 py-1 rounded-lg bg-indigo-600/30 text-indigo-200 border border-indigo-500/30 text-xs font-semibold"
                >
                  Edit
                </button>
                {evt.status !== 'Cancelled' && onCancelEvent && (
                  <button
                    onClick={() => handleCancel(evt.id)}
                    disabled={cancellingId === evt.id}
                    className="px-3 py-1 rounded-lg bg-amber-600/20 text-amber-200 border border-amber-500/30 text-xs font-semibold"
                  >
                    {cancellingId === evt.id ? '...' : 'Cancel'}
                  </button>
                )}
                <button
                  onClick={() => handleDelete(evt.id, evt.title)}
                  disabled={deletingId === evt.id}
                  className="p-1.5 rounded-lg bg-rose-500/10 text-rose-400 border border-rose-500/20 text-xs"
                  title="Delete"
                >
                  {deletingId === evt.id ? (
                    <i className="fa-solid fa-spinner animate-spin" />
                  ) : (
                    <i className="fa-solid fa-trash-can" />
                  )}
                </button>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Schedule New Appointment Modal */}
      {isScheduleModalOpen && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center p-3 sm:p-4 z-50 animate-fade-in">
          <div className="glass-panel max-w-lg w-full max-h-[92vh] overflow-y-auto p-4 sm:p-6 space-y-4 border border-purple-500/30 shadow-2xl">
            <div className="flex items-center justify-between border-b border-white/10 pb-3">
              <h3 className="text-base sm:text-lg font-bold text-white flex items-center gap-2">
                <i className="fa-solid fa-calendar-plus text-purple-400" />
                Schedule New Appointment
              </h3>
              <button
                onClick={() => setIsScheduleModalOpen(false)}
                className="text-slate-400 hover:text-white transition-colors text-sm font-bold"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleCreateSubmit} className="space-y-3.5 text-xs">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="text-slate-300 font-semibold block mb-1">Business Profile</label>
                  <select
                    value={newBusinessId}
                    onChange={(e) => setNewBusinessId(e.target.value)}
                    className="w-full bg-slate-900 border border-white/10 p-2.5 rounded-xl text-slate-200 font-semibold focus:outline-none focus:border-purple-500"
                  >
                    {businesses.map(b => (
                      <option key={b.id} value={b.id} className="bg-slate-900">{b.name}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="text-slate-300 font-semibold block mb-1">Appointment Title *</label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. Clinic Doctor Visit"
                    value={newTitle}
                    onChange={(e) => setNewTitle(e.target.value)}
                    className="w-full bg-slate-900 border border-white/10 p-2 rounded-xl text-slate-200 focus:outline-none focus:border-purple-500"
                  />
                </div>
              </div>

              <div className="grid grid-cols-3 gap-2 sm:gap-3">
                <div>
                  <label className="text-slate-300 font-semibold block mb-1">Date *</label>
                  <input
                    type="date"
                    required
                    value={newDate}
                    onChange={(e) => setNewDate(e.target.value)}
                    className="w-full bg-slate-900 border border-white/10 p-2 rounded-xl text-slate-200 focus:outline-none focus:border-purple-500 text-xs"
                  />
                </div>
                <div>
                  <label className="text-slate-300 font-semibold block mb-1">Start Time *</label>
                  <input
                    type="time"
                    required
                    value={newTime}
                    onChange={(e) => setNewTime(e.target.value)}
                    className="w-full bg-slate-900 border border-white/10 p-2 rounded-xl text-slate-200 focus:outline-none focus:border-purple-500 text-xs"
                  />
                </div>
                <div>
                  <label className="text-slate-300 font-semibold block mb-1">Duration</label>
                  <select
                    value={newDuration}
                    onChange={(e) => setNewDuration(e.target.value)}
                    className="w-full bg-slate-900 border border-white/10 p-2 rounded-xl text-slate-200 focus:outline-none focus:border-purple-500 text-xs"
                  >
                    <option value="15">15m</option>
                    <option value="30">30m</option>
                    <option value="45">45m</option>
                    <option value="60">60m</option>
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="text-slate-300 font-semibold block mb-1">Attendee Name *</label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. Sameer Malhotra"
                    value={newAttendeeName}
                    onChange={(e) => setNewAttendeeName(e.target.value)}
                    className="w-full bg-slate-900 border border-white/10 p-2 rounded-xl text-slate-200 focus:outline-none focus:border-purple-500"
                  />
                </div>
                <div>
                  <label className="text-slate-300 font-semibold block mb-1">Attendee Phone *</label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. +91 98765 43210"
                    value={newAttendeePhone}
                    onChange={(e) => setNewAttendeePhone(e.target.value)}
                    className="w-full bg-slate-900 border border-white/10 p-2 rounded-xl text-slate-200 focus:outline-none focus:border-purple-500"
                  />
                </div>
              </div>

              <div>
                <label className="text-slate-300 font-semibold block mb-1">Description / Notes</label>
                <textarea
                  rows={2}
                  placeholder="e.g. Consultation notes"
                  value={newDescription}
                  onChange={(e) => setNewDescription(e.target.value)}
                  className="w-full bg-slate-900 border border-white/10 p-2 rounded-xl text-slate-200 focus:outline-none focus:border-purple-500"
                />
              </div>

              <div className="pt-2 flex items-center justify-end gap-3 border-t border-white/10">
                <button
                  type="button"
                  onClick={() => setIsScheduleModalOpen(false)}
                  className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 font-bold"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmittingNew}
                  className="px-5 py-2 rounded-xl bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white font-bold transition-all shadow-lg shadow-purple-600/30 flex items-center gap-2"
                >
                  {isSubmittingNew ? <i className="fa-solid fa-spinner animate-spin" /> : <i className="fa-solid fa-check" />}
                  {isSubmittingNew ? 'Scheduling...' : 'Confirm Appointment'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Edit / Reschedule Appointment Modal */}
      {editingEvent && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center p-3 sm:p-4 z-50 animate-fade-in">
          <div className="glass-panel max-w-lg w-full max-h-[92vh] overflow-y-auto p-4 sm:p-6 space-y-4 border border-indigo-500/30 shadow-2xl">
            <div className="flex items-center justify-between border-b border-white/10 pb-3">
              <h3 className="text-base sm:text-lg font-bold text-white flex items-center gap-2">
                <i className="fa-solid fa-pen-to-square text-indigo-400" />
                Reschedule / Edit Appointment
              </h3>
              <button
                onClick={() => setEditingEvent(null)}
                className="text-slate-400 hover:text-white transition-colors text-sm font-bold"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleEditSubmit} className="space-y-3.5 text-xs">
              <div>
                <label className="text-slate-300 font-semibold block mb-1">Appointment Title</label>
                <input
                  type="text"
                  required
                  value={editTitle}
                  onChange={(e) => setEditTitle(e.target.value)}
                  className="w-full bg-slate-900 border border-white/10 p-2 rounded-xl text-slate-200 focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-slate-300 font-semibold block mb-1">Date</label>
                  <input
                    type="date"
                    required
                    value={editDate}
                    onChange={(e) => setEditDate(e.target.value)}
                    className="w-full bg-slate-900 border border-white/10 p-2 rounded-xl text-slate-200 focus:outline-none focus:border-indigo-500"
                  />
                </div>
                <div>
                  <label className="text-slate-300 font-semibold block mb-1">Start Time</label>
                  <input
                    type="time"
                    required
                    value={editTime}
                    onChange={(e) => setEditTime(e.target.value)}
                    className="w-full bg-slate-900 border border-white/10 p-2 rounded-xl text-slate-200 focus:outline-none focus:border-indigo-500"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-slate-300 font-semibold block mb-1">Attendee Name</label>
                  <input
                    type="text"
                    required
                    value={editAttendeeName}
                    onChange={(e) => setEditAttendeeName(e.target.value)}
                    className="w-full bg-slate-900 border border-white/10 p-2 rounded-xl text-slate-200 focus:outline-none focus:border-indigo-500"
                  />
                </div>
                <div>
                  <label className="text-slate-300 font-semibold block mb-1">Attendee Phone</label>
                  <input
                    type="text"
                    required
                    value={editAttendeePhone}
                    onChange={(e) => setEditAttendeePhone(e.target.value)}
                    className="w-full bg-slate-900 border border-white/10 p-2 rounded-xl text-slate-200 focus:outline-none focus:border-indigo-500"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-slate-300 font-semibold block mb-1">Status</label>
                  <select
                    value={editStatus}
                    onChange={(e) => setEditStatus(e.target.value)}
                    className="w-full bg-slate-900 border border-white/10 p-2.5 rounded-xl text-slate-200 focus:outline-none focus:border-indigo-500 font-semibold"
                  >
                    <option value="Confirmed">Confirmed</option>
                    <option value="Cancelled">Cancelled</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="text-slate-300 font-semibold block mb-1">Description / Notes</label>
                <textarea
                  rows={2}
                  value={editDescription}
                  onChange={(e) => setEditDescription(e.target.value)}
                  className="w-full bg-slate-900 border border-white/10 p-2 rounded-xl text-slate-200 focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div className="pt-2 flex items-center justify-between gap-3 border-t border-white/10">
                <button
                  type="button"
                  onClick={() => {
                    const id = editingEvent.id;
                    const t = editingEvent.title;
                    handleDelete(id, t);
                  }}
                  disabled={deletingId === editingEvent.id}
                  className="px-3.5 py-2 rounded-xl bg-rose-500/15 hover:bg-rose-500/25 text-rose-300 border border-rose-500/30 text-xs font-semibold flex items-center gap-1.5 transition-all"
                >
                  <i className={`fa-solid ${deletingId === editingEvent.id ? 'fa-spinner fa-spin' : 'fa-trash-can'}`} />
                  Delete Appointment
                </button>

                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setEditingEvent(null)}
                    className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 font-bold"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={isSubmittingEdit}
                    className="px-5 py-2 rounded-xl bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white font-bold transition-all shadow-lg shadow-indigo-600/30 flex items-center gap-2"
                  >
                    {isSubmittingEdit ? <i className="fa-solid fa-spinner animate-spin" /> : <i className="fa-solid fa-floppy-disk" />}
                    {isSubmittingEdit ? 'Saving...' : 'Save Changes'}
                  </button>
                </div>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
