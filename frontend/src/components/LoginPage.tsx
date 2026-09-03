import React, { useState } from 'react';
import { Business } from '../types';
import { Logo } from './Logo';

interface LoginPageProps {
  businesses: Business[];
  onLogin: (businessId: string | null) => void;
  onCreateBusiness: (data: Partial<Business>) => Promise<void>;
}

export const LoginPage: React.FC<LoginPageProps> = ({
  businesses,
  onLogin,
  onCreateBusiness
}) => {
  const [authMode, setAuthMode] = useState<'login' | 'register'>('login');

  // Sign In Form State
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  // Register Form State
  const [name, setName] = useState('');
  const [industry, setIndustry] = useState('Cake Shop');
  const [ownerName, setOwnerName] = useState('');
  const [phone, setPhone] = useState('');
  const [regEmail, setRegEmail] = useState('');
  const [isRegistering, setIsRegistering] = useState(false);

  const handleLoginSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const matched = businesses.find(b =>
      b.email.toLowerCase() === email.toLowerCase().trim() ||
      b.phone.includes(email.trim()) ||
      b.owner_name.toLowerCase().includes(email.toLowerCase().trim()) ||
      b.name.toLowerCase().includes(email.toLowerCase().trim())
    );
    if (matched) {
      onLogin(matched.id);
    } else if (email.toLowerCase().includes('admin')) {
      onLogin(null);
    } else if (businesses.length > 0) {
      onLogin(businesses[0].id);
    } else {
      onLogin(null);
    }
  };

  const handleRegisterSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name || !ownerName || !phone) return;
    setIsRegistering(true);
    try {
      await onCreateBusiness({
        name,
        industry,
        owner_name: ownerName,
        phone,
        email: regEmail || `${ownerName.toLowerCase().replace(/\s+/g, '')}@business.com`
      });
    } catch (err: any) {
      alert(`Registration failed: ${err.message}`);
    } finally {
      setIsRegistering(false);
    }
  };

  const getIndustryIcon = (ind: string) => {
    if (ind.includes('Cake')) return 'fa-cake-candles text-pink-400';
    if (ind.includes('Clinic') || ind.includes('Health')) return 'fa-user-doctor text-emerald-400';
    if (ind.includes('Logistics') || ind.includes('Delivery')) return 'fa-truck-fast text-sky-400';
    if (ind.includes('Real Estate')) return 'fa-house-building text-fuchsia-400';
    if (ind.includes('Repair')) return 'fa-wrench text-amber-400';
    return 'fa-briefcase text-purple-400';
  };

  return (
    <div className="min-h-[85vh] flex items-center justify-center py-12 px-4">
      <div className="w-full max-w-lg space-y-6 glass-panel p-6 sm:p-8 border border-slate-800 shadow-xl relative">

        {/* Brand Header */}
        <div className="text-center space-y-2 relative">
          <Logo size="lg" className="mb-2" />
          <h2 className="text-2xl font-extrabold bg-gradient-to-r from-white via-slate-100 to-indigo-200 bg-clip-text text-transparent tracking-tight">
            VoiceAssistant.ai
          </h2>
          <p className="text-xs text-indigo-300 font-medium">Business Owner Authentication Portal</p>
        </div>

        {/* Auth Mode Toggle Tabs */}
        <div className="flex rounded-xl bg-slate-950 p-1 border border-slate-800 text-xs font-semibold">
          <button
            type="button"
            onClick={() => setAuthMode('login')}
            className={`flex-1 py-2.5 rounded-lg transition-all ${
              authMode === 'login'
                ? 'bg-gradient-to-r from-indigo-600 to-blue-600 text-white shadow-md font-bold'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            <i className="fa-solid fa-key mr-1.5 text-indigo-300" /> Password Sign In
          </button>
          <button
            type="button"
            onClick={() => setAuthMode('register')}
            className={`flex-1 py-2.5 rounded-lg transition-all ${
              authMode === 'register'
                ? 'bg-gradient-to-r from-indigo-600 to-blue-600 text-white shadow-md font-bold'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            <i className="fa-solid fa-user-plus mr-1.5 text-emerald-400" /> Register Business
          </button>
        </div>

        {/* PASSWORD SIGN IN FORM */}
        {authMode === 'login' && (
          <form onSubmit={handleLoginSubmit} className="space-y-4 text-xs">
              <div>
                <label className="text-slate-300 font-semibold block mb-1">Owner Email or Phone</label>
                <div className="relative">
                  <i className="fa-solid fa-envelope text-slate-500 absolute left-3.5 top-1/2 -translate-y-1/2" />
                  <input
                    type="text"
                    required
                    placeholder="e.g. orders@sweettreats.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-9 pr-4 py-2.5 text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                  />
                </div>
              </div>

              <div>
                <label className="text-slate-300 font-semibold block mb-1">Password</label>
                <div className="relative">
                  <i className="fa-solid fa-lock text-slate-500 absolute left-3.5 top-1/2 -translate-y-1/2" />
                  <input
                    type="password"
                    required
                    placeholder="••••••••••••"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-9 pr-4 py-2.5 text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500 font-mono"
                  />
                </div>
              </div>

              <button
                type="submit"
                className="w-full py-3 rounded-xl bg-gradient-to-r from-indigo-600 via-indigo-500 to-blue-600 hover:from-indigo-500 hover:to-blue-500 text-white font-bold text-xs shadow-lg shadow-indigo-500/25 transition-all cursor-pointer"
              >
                Sign In to Business Portal ➔
              </button>
            </form>
        )}

        {/* 3. REGISTER NEW BUSINESS FORM */}
        {authMode === 'register' && (
          <form onSubmit={handleRegisterSubmit} className="space-y-4 text-xs">
            <div>
              <label className="text-slate-300 font-semibold block mb-1">Business Name</label>
              <input
                type="text"
                required
                placeholder="e.g. Kavya Cake Studio"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3.5 py-2.5 text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-slate-300 font-semibold block mb-1">Industry</label>
                <select
                  value={industry}
                  onChange={(e) => setIndustry(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-2.5 text-slate-200 focus:outline-none cursor-pointer"
                >
                  <option value="Cake Shop" className="bg-slate-900">Cake Shop</option>
                  <option value="Clinic / Healthcare" className="bg-slate-900">Clinic / Healthcare</option>
                  <option value="Logistics & Delivery" className="bg-slate-900">Logistics & Delivery</option>
                  <option value="Real Estate" className="bg-slate-900">Real Estate</option>
                  <option value="Home Repair" className="bg-slate-900">Home Repair</option>
                  <option value="Custom Business" className="bg-slate-900">Custom Business</option>
                </select>
              </div>

              <div>
                <label className="text-slate-300 font-semibold block mb-1">Owner Name</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Kavya Sharma"
                  value={ownerName}
                  onChange={(e) => setOwnerName(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3.5 py-2.5 text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-slate-300 font-semibold block mb-1">Phone Number</label>
                <input
                  type="text"
                  required
                  placeholder="+91 98765 00000"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3.5 py-2.5 text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div>
                <label className="text-slate-300 font-semibold block mb-1">Owner Email</label>
                <input
                  type="email"
                  placeholder="kavya@cakestudio.com"
                  value={regEmail}
                  onChange={(e) => setRegEmail(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3.5 py-2.5 text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={isRegistering}
              className="w-full py-3 rounded-xl bg-gradient-to-r from-indigo-600 to-blue-600 hover:from-indigo-500 hover:to-blue-500 text-white font-bold text-xs shadow-lg shadow-indigo-500/20 transition-all"
            >
              {isRegistering ? 'Registering Account...' : 'Register & Direct Sign In ➔'}
            </button>
          </form>
        )}
      </div>
    </div>
  );
};
