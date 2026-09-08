import React, { useState, useEffect } from 'react';
import { Navbar } from './components/Navbar';
import { Dashboard } from './components/Dashboard';
import { WorkflowBuilder } from './components/WorkflowBuilder';
import { PhoneSimulator } from './components/PhoneSimulator';
import { BusinessProfiles } from './components/BusinessProfiles';
import { CalendarMonitor } from './components/CalendarMonitor';
import { LoginPage } from './components/LoginPage';
import { Business, Workflow, MissedCallRecord, CalendarEvent } from './types';
import {
  fetchBusinesses,
  createBusiness,
  fetchWorkflows,
  createWorkflow,
  updateWorkflow,
  fetchRecords,
  updateRecordStatus,
  deleteRecord,
  deleteAllRecords,
  fetchCalendarEvents,
  createCalendarEvent,
  updateCalendarEvent,
  cancelCalendarEvent,
  deleteCalendarEvent,
  deleteAllCalendarEvents,
  syncGoogleCalendar
} from './lib/api';

export default function App() {
  const [activeTab, setActiveTab] = useState<string>('dashboard');
  const [selectedLanguage, setSelectedLanguage] = useState<string>('auto');

  // Business Owner Authentication & Session State
  const [isLoggedIn, setIsLoggedIn] = useState<boolean>(() => {
    return localStorage.getItem('isLoggedIn') === 'true';
  });
  const [authenticatedBusinessId, setAuthenticatedBusinessId] = useState<string | null>(() => {
    return localStorage.getItem('authenticatedBusinessId');
  });

  // App State
  const [businesses, setBusinesses] = useState<Business[]>([]);
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [records, setRecords] = useState<MissedCallRecord[]>([]);
  const [calendarEvents, setCalendarEvents] = useState<CalendarEvent[]>([]);
  const [simulatorWorkflowId, setSimulatorWorkflowId] = useState<string | undefined>(undefined);
  const [calendarTargetDate, setCalendarTargetDate] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // Load initial data from Python FastAPI backend
  const loadData = async (silent: boolean = false) => {
    try {
      if (!silent) setLoading(true);
      const [bizData, wfData, recData, calData] = await Promise.all([
        fetchBusinesses(),
        fetchWorkflows(),
        fetchRecords(),
        fetchCalendarEvents()
      ]);

      setBusinesses(bizData);
      setWorkflows(wfData);
      setRecords(recData);
      setCalendarEvents(calData);
    } catch (err: any) {
      console.error('FastAPI data loading error:', err);
    } finally {
      if (!silent) setLoading(false);
    }
  };

  useEffect(() => {
    loadData(activeTab !== 'dashboard');
  }, [activeTab]);

  // Filtered state per authenticated business owner profile
  const displayedRecords = authenticatedBusinessId
    ? records.filter(r => r.business_id === authenticatedBusinessId)
    : records;

  const displayedWorkflows = authenticatedBusinessId
    ? workflows.filter(w => w.business_id === authenticatedBusinessId)
    : workflows;

  const displayedCalendarEvents = authenticatedBusinessId
    ? calendarEvents.filter(e => e.business_id === authenticatedBusinessId)
    : calendarEvents;

  // Authentication Handlers
  const handleLogin = (businessId: string | null) => {
    setAuthenticatedBusinessId(businessId);
    setIsLoggedIn(true);
    localStorage.setItem('isLoggedIn', 'true');
    if (businessId) {
      localStorage.setItem('authenticatedBusinessId', businessId);
    } else {
      localStorage.removeItem('authenticatedBusinessId');
    }
    setActiveTab('dashboard');
  };

  const handleLogout = () => {
    setIsLoggedIn(false);
    setAuthenticatedBusinessId(null);
    localStorage.removeItem('isLoggedIn');
    localStorage.removeItem('authenticatedBusinessId');
  };

  // Handlers
  const handleCreateBusiness = async (data: Partial<Business>) => {
    const newBiz = await createBusiness(data);
    await loadData();
    if (newBiz?.id) {
      handleLogin(newBiz.id);
    }
  };

  const handleSaveWorkflow = async (data: Partial<Workflow>) => {
    if (data.id) {
      await updateWorkflow(data.id, data);
    } else {
      await createWorkflow(data);
    }
    await loadData();
  };

  const handleStatusChange = async (id: string, newStatus: string) => {
    await updateRecordStatus(id, newStatus);
    await loadData();
  };

  const handleDeleteRecord = async (id: string) => {
    await deleteRecord(id);
    await loadData();
  };

  const handleDeleteAllRecords = async () => {
    await deleteAllRecords(authenticatedBusinessId || undefined);
    await loadData();
  };

  const handleCreateCalendarEvent = async (data: Partial<CalendarEvent>) => {
    await createCalendarEvent(data);
    await loadData(true);
  };

  const handleUpdateCalendarEvent = async (eventId: string, data: Partial<CalendarEvent>) => {
    await updateCalendarEvent(eventId, data);
    await loadData(true);
  };

  const handleCancelCalendarEvent = async (eventId: string) => {
    await cancelCalendarEvent(eventId);
    await loadData(true);
  };

  const handleDeleteCalendarEvent = async (eventId: string) => {
    await deleteCalendarEvent(eventId);
    await loadData(true);
  };

  const handleDeleteAllCalendarEvents = async () => {
    await deleteAllCalendarEvents(authenticatedBusinessId || undefined);
    await loadData(true);
  };

  const handleSyncCalendar = async () => {
    const res = await syncGoogleCalendar();
    await loadData(true);
    return res;
  };

  const handleLaunchSimulator = (businessId: string, workflowId: string) => {
    setSimulatorWorkflowId(workflowId);
    setActiveTab('simulator');
  };

  // Render Dedicated Sign In Page if not logged in
  if (!isLoggedIn) {
    return (
      <div className="min-h-screen text-slate-100 flex flex-col justify-center relative z-10">
        <LoginPage
          businesses={businesses}
          onLogin={handleLogin}
          onCreateBusiness={handleCreateBusiness}
        />
      </div>
    );
  }

  return (
    <div className="min-h-screen pb-24 lg:pb-16 text-slate-100 relative z-10">
      {/* Top Glass Navigation Bar */}
      <Navbar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        selectedLanguage={selectedLanguage}
        setSelectedLanguage={setSelectedLanguage}
        businesses={businesses}
        authenticatedBusinessId={authenticatedBusinessId}
        onSelectOwner={setAuthenticatedBusinessId}
        onLogout={handleLogout}
      />

      {/* Main Container */}
      <main className="max-w-7xl mx-auto px-2.5 sm:px-6 lg:px-8">
        {loading ? (
          <div className="flex flex-col items-center justify-center min-h-[60vh] space-y-4">
            <div className="w-12 h-12 rounded-full border-4 border-indigo-500 border-t-transparent animate-spin" />
            <p className="text-xs text-indigo-300 font-semibold animate-pulse">
              Connecting to Python FastAPI Assistant Backend...
            </p>
          </div>
        ) : (
          <>
            {activeTab === 'dashboard' && (
              <Dashboard
                records={displayedRecords}
                businesses={businesses}
                onStatusChange={handleStatusChange}
                onDeleteRecord={handleDeleteRecord}
                onDeleteAllRecords={handleDeleteAllRecords}
                onLaunchSimulator={handleLaunchSimulator}
                onRefresh={loadData}
              />
            )}

            {activeTab === 'builder' && (
              <WorkflowBuilder
                businesses={businesses}
                workflows={displayedWorkflows}
                onSaveWorkflow={handleSaveWorkflow}
                onTestWorkflow={(wfId) => {
                  setSimulatorWorkflowId(wfId);
                  setActiveTab('simulator');
                }}
              />
            )}

            {activeTab === 'simulator' && (
              <PhoneSimulator
                businesses={businesses}
                workflows={workflows}
                selectedLanguage={selectedLanguage}
                initialWorkflowId={simulatorWorkflowId}
                onDataChanged={() => loadData(true)}
                onNavigateToCalendar={(targetDate?: string) => {
                  if (targetDate) setCalendarTargetDate(targetDate);
                  setActiveTab('calendar');
                }}
              />
            )}

            {activeTab === 'profiles' && (
              <BusinessProfiles
                businesses={businesses}
                onCreateBusiness={handleCreateBusiness}
              />
            )}

            {activeTab === 'calendar' && (
              <CalendarMonitor
                events={calendarEvents}
                businesses={businesses}
                defaultBusinessFilter={authenticatedBusinessId || 'All'}
                initialTargetDate={calendarTargetDate}
                onTargetDateConsumed={() => setCalendarTargetDate(null)}
                onCreateEvent={handleCreateCalendarEvent}
                onUpdateEvent={handleUpdateCalendarEvent}
                onCancelEvent={handleCancelCalendarEvent}
                onDeleteEvent={handleDeleteCalendarEvent}
                onDeleteAllEvents={handleDeleteAllCalendarEvents}
                onSyncCalendar={handleSyncCalendar}
                onRefresh={() => loadData(true)}
              />
            )}
          </>
        )}
      </main>
    </div>
  );
}
