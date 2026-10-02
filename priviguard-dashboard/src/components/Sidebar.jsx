import React from 'react';
import { 
  ShieldAlert, 
  Clock, 
  Flame, 
  CheckSquare, 
  Users, 
  RefreshCw,
  ShieldCheck,
  Network
} from 'lucide-react';

export default function Sidebar({ activeTab, setActiveTab, onRefresh, isRefreshing }) {
  const navItems = [
    { id: 'overview', label: 'Overall Threat Posture', icon: ShieldAlert },
    { id: 'graph', label: 'Access Relationship Graph', icon: Network },
    { id: 'dormancy', label: 'Dormancy Analysis', icon: Clock },
    { id: 'damage', label: 'Damage Score', icon: Flame },
    { id: 'remediation', label: 'Remediation Backlog', icon: CheckSquare },
    { id: 'identities', label: 'Identities Directory', icon: Users },
  ];


  return (
    <aside style={{
      width: '260px',
      minWidth: '260px',
      flexShrink: 0,
      height: '100vh',
      background: 'linear-gradient(180deg, #2a141c 0%, #1d0c14 100%)',
      borderRight: '1px solid #3d1f2b',
      display: 'flex',
      flexDirection: 'column',
      padding: '1.5rem 1rem',
      boxShadow: '4px 0 20px rgba(0,0,0,0.15)',
      overflowY: 'auto',
      zIndex: 20
    }}>
      {/* Brand Logo */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '2rem', padding: '0 0.5rem' }}>
        <div style={{
          width: '36px',
          height: '36px',
          borderRadius: '8px',
          background: 'linear-gradient(135deg, #9f1239 0%, #be123c 100%)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          boxShadow: '0 0 15px rgba(225, 29, 72, 0.4)'
        }}>
          <ShieldCheck size={22} color="#ffffff" />
        </div>
        <div>
          <h2 style={{ fontSize: '1.15rem', fontWeight: 800, color: '#f8fafc', letterSpacing: '-0.02em' }} className="title-font">
            HybridGuard
          </h2>
          <p style={{ fontSize: '0.7rem', color: '#fb7185', fontWeight: 700, letterSpacing: '0.05em' }}>
            ISPM CONSOLE
          </p>
        </div>
      </div>

      {/* Navigation Links */}
      <div style={{ flex: 1 }}>
        <p style={{ fontSize: '0.68rem', fontWeight: 700, color: '#886d77', letterSpacing: '0.08em', marginBottom: '0.75rem', padding: '0 0.5rem' }}>
          NAVIGATION
        </p>

        <nav style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setActiveTab(item.id)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.75rem',
                  padding: '0.65rem 0.85rem',
                  borderRadius: '8px',
                  fontSize: '0.85rem',
                  fontWeight: isActive ? 700 : 500,
                  color: isActive ? '#fecdd3' : '#a8929b',
                  background: isActive ? 'rgba(225, 29, 72, 0.2)' : 'transparent',
                  border: isActive ? '1px solid rgba(225, 29, 72, 0.4)' : '1px solid transparent',
                  cursor: 'pointer',
                  textAlign: 'left',
                  transition: 'all 0.2s ease',
                  width: '100%'
                }}
              >
                <Icon size={18} color={isActive ? '#fb7185' : '#886d77'} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>
      </div>

      {/* Refresh Data Footer */}
      <div style={{ paddingTop: '1.5rem', borderTop: '1px solid #3d1f2b' }}>
        <button
          onClick={onRefresh}
          disabled={isRefreshing}
          style={{
            width: '100%',
            justifyContent: 'center',
            opacity: isRefreshing ? 0.7 : 1,
            background: 'rgba(61, 31, 43, 0.6)',
            color: '#f8fafc',
            border: '1px solid #542b3b',
            padding: '0.55rem 0.9rem',
            borderRadius: '6px',
            fontSize: '0.85rem',
            fontWeight: 600,
            cursor: 'pointer',
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.4rem',
            transition: 'all 0.2s ease'
          }}
        >
          <RefreshCw size={15} style={{ animation: isRefreshing ? 'spin 1s linear infinite' : 'none' }} />
          <span>{isRefreshing ? 'Refreshing Cache...' : 'Refresh Data Cache'}</span>
        </button>
      </div>
    </aside>
  );
}
