import React, { useState } from 'react';
import { Business } from '../types';

interface BusinessProfilesProps {
  businesses: Business[];
  onCreateBusiness: (data: Partial<Business>) => Promise<void>;
}

export const BusinessProfiles: React.FC<BusinessProfilesProps> = ({ businesses, onCreateBusiness }) => {
  const [showModal, setShowModal] = useState(false);
  const [name, setName] = useState('');
  const [industry, setIndustry] = useState('Cake Shop');
  const [ownerName, setOwnerName] = useState('');
  const [phone, setPhone] = useState('');
  const [email, setEmail] = useState('');
  const [address, setAddress] = useState('');
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      await onCreateBusiness({ name, industry, owner_name: ownerName, phone, email, address });
      setShowModal(false);
      setName('');
      setOwnerName('');
      setPhone('');
      setEmail('');
      setAddress('');
    } catch (err: any) {
      alert(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-8">
      {/* Header Bar */}
      <div className="glass-panel p-5 flex flex-col md:flex-row items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-white flex items-center gap-2">
            <i className="fa-solid fa-building-user text-indigo-400" />
            Small Business Profiles Manager
          </h2>
          <p className="text-xs text-slate-400">Configure business identities across multiple industries (Cake Shop, Clinic, Logistics, Real Estate, Repair)</p>
        </div>

        <button
          onClick={() => setShowModal(true)}
          className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white font-bold text-xs shadow-lg shadow-indigo-500/25 transition-all"
        >
          <i className="fa-solid fa-plus text-xs" /> Create Business Profile
        </button>
      </div>

      {/* Business Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {businesses.map((b) => (
          <div key={b.id} className="glass-panel p-6 space-y-4 glass-card-hover border border-white/10 relative overflow-hidden">
            <div className="absolute top-0 right-0 w-24 h-24 bg-indigo-500/5 rounded-full blur-xl pointer-events-none" />

            <div className="flex items-start justify-between">
              <div>
                <span className="px-2.5 py-1 rounded-full text-[10px] font-bold bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                  {b.industry}
                </span>
                <h3 className="text-lg font-bold text-white mt-2">{b.name}</h3>
              </div>
            </div>

            <div className="space-y-2 text-xs text-slate-300 border-t border-white/10 pt-4">
              <div className="flex items-center gap-2">
                <i className="fa-solid fa-user-tie text-indigo-400 text-sm" />
                <span>Owner: <strong className="text-slate-100">{b.owner_name}</strong></span>
              </div>

              <div className="flex items-center gap-2">
                <i className="fa-solid fa-phone text-indigo-400 text-sm" />
                <span className="font-mono text-slate-200">{b.phone}</span>
              </div>

              <div className="flex items-center gap-2">
                <i className="fa-solid fa-envelope text-indigo-400 text-sm" />
                <span className="text-slate-300">{b.email}</span>
              </div>

              {b.address && (
                <div className="flex items-center gap-2">
                  <i className="fa-solid fa-location-dot text-indigo-400 text-sm" />
                  <span className="text-slate-400">{b.address}</span>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Create Business Profile Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-md flex items-center justify-center p-4">
          <div className="glass-panel w-full max-w-md p-6 space-y-6 border border-indigo-500/30 shadow-2xl relative">
            <button
              onClick={() => setShowModal(false)}
              className="absolute top-4 right-4 text-slate-400 hover:text-white"
            >
              ✕
            </button>

            <div className="border-b border-white/10 pb-3">
              <h3 className="text-lg font-bold text-white flex items-center gap-2">
                <i className="fa-solid fa-building-user text-indigo-400" /> Create Business Profile
              </h3>
              <p className="text-xs text-slate-400">Add a new business identity to the platform</p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="text-xs font-semibold text-slate-300 mb-1 block">Business Name</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Royal Bakes & Treats"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full bg-slate-900 border border-white/10 rounded-xl px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-300 mb-1 block">Industry / Category</label>
                <select
                  value={industry}
                  onChange={(e) => setIndustry(e.target.value)}
                  className="w-full bg-slate-900 border border-white/10 rounded-xl px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
                >
                  <option value="Cake Shop">Cake Shop & Bakery</option>
                  <option value="Clinic / Healthcare">Clinic / Doctor</option>
                  <option value="Logistics & Delivery">Logistics & Delivery</option>
                  <option value="Real Estate">Real Estate</option>
                  <option value="Home & Repair Services">Home & Repair Services</option>
                  <option value="Custom Business">Other Custom Business</option>
                </select>
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-300 mb-1 block">Owner / Contact Person</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Priya Sharma"
                  value={ownerName}
                  onChange={(e) => setOwnerName(e.target.value)}
                  className="w-full bg-slate-900 border border-white/10 rounded-xl px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-300 mb-1 block">Phone Number</label>
                <input
                  type="text"
                  required
                  placeholder="+91 98765 43210"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  className="w-full bg-slate-900 border border-white/10 rounded-xl px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-300 mb-1 block">Email Address</label>
                <input
                  type="email"
                  required
                  placeholder="contact@business.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full bg-slate-900 border border-white/10 rounded-xl px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-300 mb-1 block">Address</label>
                <input
                  type="text"
                  placeholder="Street, Area, City"
                  value={address}
                  onChange={(e) => setAddress(e.target.value)}
                  className="w-full bg-slate-900 border border-white/10 rounded-xl px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  className="px-4 py-2 rounded-xl bg-slate-800 text-slate-300 text-xs font-semibold"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={saving}
                  className="px-5 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-bold shadow-lg shadow-indigo-500/25"
                >
                  {saving ? 'Creating...' : 'Create Profile'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
