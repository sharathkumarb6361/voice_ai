import React, { useState } from 'react';
import { Business } from '../types';
import { Logo } from './Logo';

interface NavbarProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
  selectedLanguage: string;
  setSelectedLanguage: (lang: string) => void;
  businesses?: Business[];
  authenticatedBusinessId: string | null;
  onSelectOwner: (businessId: string | null) => void;
  onLogout?: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({
  activeTab,
  setActiveTab,
  selectedLanguage,
  setSelectedLanguage,
  businesses = [],
  authenticatedBusinessId,
  onSelectOwner,
  onLogout
}) => {
  const [showLoginModal, setShowLoginModal] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const currentBusiness = businesses.find(b => b.id === authenticatedBusinessId);

  const tabs = [
    { id: 'dashboard', label: 'Dashboard & Records', iconClass: 'fa-solid fa-phone-slash' },
    { id: 'builder', label: 'Custom Workflow Builder', iconClass: 'fa-solid fa-sliders' },
    { id: 'simulator', label: 'AI Voice Call Simulator', iconClass: 'fa-solid fa-circle-play' },
    { id: 'profiles', label: 'Business Profiles', iconClass: 'fa-solid fa-building-user' },
    { id: 'calendar', label: 'Google Calendar & Tools', iconClass: 'fa-solid fa-calendar-days' },
  ];

  const handleOwnerLogin = (bizId: string | null) => {
    onSelectOwner(bizId);
    setShowLoginModal(false);
    setMobileMenuOpen(false);
  };

  const handleTabClick = (tabId: string) => {
    setActiveTab(tabId);
    setMobileMenuOpen(false);
  };

  return (
    <header className="sticky top-0 z-50 glass-panel border-b border-slate-800 px-4 sm:px-6 lg:px-8 py-3 mb-6 shadow-xl">
      <div className="max-w-7xl mx-auto flex items-center justify-between gap-4">
        {/* Brand Logo */}
        <div className="flex items-center gap-3 cursor-pointer group" onClick={() => handleTabClick('dashboard')}>
          <Logo size="md" />
          <div>
            <h1 className="text-lg sm:text-xl font-extrabold tracking-tight animate-shimmer-text">
              VoiceAssistant.ai
            </h1>
            <p className="text-[10px] sm:text-xs text-indigo-300 font-semibold tracking-wide hidden sm:flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              Automated Missed Call & AI Workflows
            </p>
          </div>
        </div>

        {/* Desktop Navigation Tabs */}
        <nav className="hidden lg:flex items-center gap-1 bg-slate-950 p-1 rounded-2xl border border-slate-800 shadow-inner flex-shrink">
          {tabs.map((tab) => {
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => handleTabClick(tab.id)}
                className={`relative flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-bold transition-all whitespace-nowrap flex-shrink-0 ${
                  isActive
                    ? 'bg-gradient-to-r from-indigo-600 via-indigo-500 to-blue-600 text-white shadow-md border border-indigo-400/40'
                    : 'text-slate-300 hover:text-white hover:bg-slate-900'
                }`}
              >
                <i className={`${tab.iconClass} ${isActive ? 'text-white' : 'text-indigo-400'}`} />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </nav>

        {/* Right Desktop Section */}
        <div className="hidden md:flex items-center gap-2 flex-shrink-0">
          {/* Business Owner Session Badge */}
          <button
            onClick={() => setShowLoginModal(true)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-bold border transition-all cursor-pointer whitespace-nowrap flex-shrink-0 ${
              currentBusiness
                ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40 hover:bg-emerald-500/25'
                : 'bg-slate-900 text-indigo-200 border-slate-800 hover:bg-slate-800'
            }`}
          >
            <i className={`fa-solid ${currentBusiness ? 'fa-user-check text-emerald-400' : 'fa-shield-halved text-indigo-400'}`} />
            <span className="truncate max-w-[120px]">
              {currentBusiness ? `${currentBusiness.owner_name}` : 'Admin Mode'}
            </span>
            <i className="fa-solid fa-chevron-down text-[9px] text-slate-400" />
          </button>

          {/* Language Selector */}
          <div className="flex items-center gap-1 bg-slate-950 px-2.5 py-1.5 rounded-xl border border-slate-800 text-xs shadow-inner flex-shrink-0">
            <i className="fa-solid fa-language text-indigo-400 text-xs" />
            <select
              value={selectedLanguage}
              onChange={(e) => setSelectedLanguage(e.target.value)}
              className="bg-transparent text-slate-100 font-semibold focus:outline-none cursor-pointer text-xs"
            >
              <option value="auto" className="bg-slate-900">✨ Auto</option>
              <option value="en" className="bg-slate-900">English (EN)</option>
              <option value="hi" className="bg-slate-900">Hindi (हिन्दी)</option>
              <option value="kn" className="bg-slate-900">Kannada (ಕನ್ನಡ)</option>
            </select>
          </div>

          {/* Sign Out Button */}
          {onLogout && (
            <button
              onClick={onLogout}
              className="flex-shrink-0 whitespace-nowrap flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-900 hover:bg-rose-950/60 text-slate-300 hover:text-rose-300 border border-slate-800 hover:border-rose-500/40 text-xs font-bold transition-all shadow-sm"
              title="Sign Out"
            >
              <i className="fa-solid fa-right-from-bracket text-rose-400 text-xs" />
              <span className="whitespace-nowrap">Sign Out</span>
            </button>
          )}
        </div>

        {/* Mobile Hamburger Toggle Button */}
        <div className="flex items-center gap-2 md:hidden">
          <button
            onClick={() => setShowLoginModal(true)}
            className="p-2 rounded-xl bg-slate-900 text-indigo-300 border border-slate-700 text-xs font-bold"
          >
            <i className="fa-solid fa-user-gear text-sm" />
          </button>

          <button
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="p-2 rounded-xl bg-slate-900 border border-slate-700 text-slate-200 hover:text-white text-lg focus:outline-none"
            aria-label="Toggle Navigation Menu"
          >
            <i className={`fa-solid ${mobileMenuOpen ? 'fa-xmark' : 'fa-bars'}`} />
          </button>
        </div>
      </div>

      {/* Mobile Slide-down Menu Drawer */}
      {mobileMenuOpen && (
        <div className="md:hidden mt-3 pt-3 border-t border-indigo-500/20 space-y-3 animate-fade-in max-h-[75vh] overflow-y-auto touch-scroll pr-1">
          <nav className="grid grid-cols-1 gap-2">
            {tabs.map((tab) => {
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  onClick={() => handleTabClick(tab.id)}
                  className={`flex items-center justify-between px-4 py-3 rounded-xl text-xs font-bold transition-all text-left ${
                    isActive
                      ? 'bg-gradient-to-r from-indigo-600 via-indigo-500 to-blue-600 text-white shadow-lg shadow-indigo-500/25 border border-indigo-400/40'
                      : 'bg-slate-950/80 text-slate-200 border border-slate-800 hover:bg-slate-900'
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <i className={`${tab.iconClass} ${isActive ? 'text-white' : 'text-indigo-400'} text-sm`} />
                    <span>{tab.label}</span>
                  </div>
                  {isActive && <i className="fa-solid fa-chevron-right text-[10px] text-white/80" />}
                </button>
              );
            })}
          </nav>

          <div className="pt-2 border-t border-indigo-500/20 flex flex-col gap-2">
            {/* Language Selector Mobile */}
            <div className="flex items-center justify-between bg-slate-950/90 px-3.5 py-2.5 rounded-xl border border-indigo-500/25 text-xs">
              <span className="text-slate-300 font-semibold flex items-center gap-2">
                <i className="fa-solid fa-language text-indigo-400 text-sm" /> AI Speech Language:
              </span>
              <select
                value={selectedLanguage}
                onChange={(e) => setSelectedLanguage(e.target.value)}
                className="bg-transparent text-slate-100 font-bold focus:outline-none cursor-pointer"
              >
                <option value="auto" className="bg-slate-900">✨ Auto-Detect</option>
                <option value="en" className="bg-slate-900">English (EN)</option>
                <option value="hi" className="bg-slate-900">Hindi (हिन्दी)</option>
                <option value="kn" className="bg-slate-900">Kannada (ಕನ್ನಡ)</option>
              </select>
            </div>

            {/* Business Owner Session Button Mobile */}
            <button
              onClick={() => {
                setMobileMenuOpen(false);
                setShowLoginModal(true);
              }}
              className="w-full py-2.5 rounded-xl bg-slate-950/90 text-indigo-200 border border-indigo-500/30 text-xs font-bold flex items-center justify-center gap-2"
            >
              <i className="fa-solid fa-user-check text-emerald-400" />
              <span>Session: {currentBusiness ? `${currentBusiness.owner_name}` : 'Admin View'}</span>
            </button>

            {onLogout && (
              <button
                onClick={() => {
                  setMobileMenuOpen(false);
                  onLogout();
                }}
                className="w-full py-2.5 rounded-xl bg-rose-950/40 text-rose-200 border border-rose-500/30 text-xs font-bold flex items-center justify-center gap-2"
              >
                <i className="fa-solid fa-right-from-bracket text-rose-400" /> Sign Out
              </button>
            )}
          </div>
        </div>
      )}

      {/* Business Owner Session Switcher Modal */}
      {showLoginModal && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-center justify-center p-4">
          <div className="glass-panel w-full max-w-md p-6 space-y-6 border border-slate-700 shadow-2xl relative">
            <button
              onClick={() => setShowLoginModal(false)}
              className="absolute top-4 right-4 text-slate-400 hover:text-white text-lg font-bold"
            >
              ✕
            </button>

            <div>
              <h3 className="text-lg font-bold text-white flex items-center gap-2">
                <i className="fa-solid fa-shield-halved text-indigo-400" />
                {authenticatedBusinessId ? 'Business Owner Account Session' : 'Master Admin Session Control'}
              </h3>
              <p className="text-xs text-slate-400 mt-1">
                {authenticatedBusinessId
                  ? 'Active business owner session profile details.'
                  : 'Switch business owner profile sessions or sign out.'}
              </p>
            </div>

            {/* IF MASTER ADMIN MODE: Allow switching across accounts */}
            {!authenticatedBusinessId ? (
              <div className="space-y-3">
                <div className="p-3 rounded-xl bg-purple-950/40 border border-purple-500/30 text-xs">
                  <div className="font-bold text-purple-300 flex items-center gap-1.5 mb-0.5">
                    <i className="fa-solid fa-crown text-amber-400" /> Master Admin Mode Active
                  </div>
                  <p className="text-[11px] text-slate-400">
                    You have administrative access to inspect and switch across all business owner profiles.
                  </p>
                </div>

                <div className="space-y-2">
                  <label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider block">
                    Select Business Profile Session
                  </label>
                  <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
                    {businesses.map((biz) => (
                      <button
                        key={biz.id}
                        onClick={() => handleOwnerLogin(biz.id)}
                        className="w-full text-left p-3 rounded-xl bg-slate-900 hover:bg-indigo-950/40 border border-slate-800 hover:border-indigo-500/40 text-xs transition-all flex items-center justify-between group"
                      >
                        <div>
                          <div className="font-bold text-slate-200 group-hover:text-indigo-300 flex items-center gap-2">
                            <i className="fa-solid fa-user-tie text-indigo-400" />
                            {biz.owner_name}
                          </div>
                          <div className="text-[11px] text-slate-400 mt-0.5">
                            {biz.name} • <span className="text-indigo-300">{biz.industry}</span>
                          </div>
                        </div>
                        <span className="text-xs text-indigo-400 font-semibold group-hover:translate-x-0.5 transition-transform">
                          Switch ➔
                        </span>
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              /* IF REGULAR BUSINESS OWNER: Show ONLY active business details (NO account switching) */
              <div className="space-y-4">
                {currentBusiness && (
                  <div className="p-4 rounded-xl bg-slate-900 border border-emerald-500/40 text-xs space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="px-2.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 text-[10px] font-bold border border-emerald-500/30">
                        ✓ Active Owner Session
                      </span>
                      <span className="text-indigo-300 text-[11px] font-semibold">{currentBusiness.industry}</span>
                    </div>
                    <div>
                      <div className="text-base font-extrabold text-white">{currentBusiness.owner_name}</div>
                      <div className="text-xs text-slate-300 font-semibold">{currentBusiness.name}</div>
                    </div>
                    <div className="pt-2 border-t border-slate-800 space-y-1 text-[11px] text-slate-400">
                      <div><i className="fa-solid fa-envelope mr-2 text-slate-500" /> {currentBusiness.email}</div>
                      <div><i className="fa-solid fa-phone mr-2 text-slate-500" /> {currentBusiness.phone}</div>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Actions */}
            <div className="pt-2 border-t border-slate-800 flex flex-col gap-2">
              {onLogout && (
                <button
                  onClick={() => {
                    setShowLoginModal(false);
                    onLogout();
                  }}
                  className="w-full py-2.5 rounded-xl bg-rose-950/40 hover:bg-rose-900/60 text-rose-200 border border-rose-500/30 text-xs font-bold transition-all flex items-center justify-center gap-2 cursor-pointer"
                >
                  <i className="fa-solid fa-right-from-bracket text-rose-400" />
                  Sign Out of Account
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </header>
  );
};
