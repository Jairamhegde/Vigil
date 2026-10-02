import React from 'react';
import { Server, Activity, Calendar } from 'lucide-react';

export default function Header({ pageTitle, pageSubtitle }) {
  const currentDate = new Date().toLocaleDateString('en-US', {
    day: 'numeric',
    month: 'short',
    year: 'numeric'
  });

  return (
    <header style={{
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'flex-start',
      flexWrap: 'wrap',
      gap: '1rem',
      paddingBottom: '1.25rem',
      marginBottom: '1.75rem',
      borderBottom: '1px solid #e6ded6'
    }}>
      <div>
        <h1 style={{ fontSize: '1.75rem', fontWeight: 800, color: '#29181d', letterSpacing: '-0.02em' }} className="title-font">
          {pageTitle}
        </h1>
        <p style={{ fontSize: '0.875rem', color: '#6b5860', marginTop: '0.2rem' }}>
          {pageSubtitle}
        </p>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.5rem',
          background: '#ffffff',
          padding: '0.4rem 0.85rem',
          borderRadius: '20px',
          border: '1px solid #e6ded6',
          fontSize: '0.78rem',
          color: '#6b5860',
          boxShadow: '0 1px 3px rgba(41,24,29,0.04)'
        }}>
          <Server size={14} color="#9f1239" />
          <span>Platforms: <strong style={{ color: '#29181d' }}>AD · AWS · Okta</strong></span>
        </div>

        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.5rem',
          background: '#ffffff',
          padding: '0.4rem 0.85rem',
          borderRadius: '20px',
          border: '1px solid #e6ded6',
          fontSize: '0.78rem',
          color: '#6b5860',
          boxShadow: '0 1px 3px rgba(41,24,29,0.04)'
        }}>
          <span style={{
            width: '8px',
            height: '8px',
            borderRadius: '50%',
            background: '#0f766e',
            boxShadow: '0 0 8px rgba(15, 118, 110, 0.6)',
            display: 'inline-block'
          }}></span>
          <Activity size={14} color="#0f766e" />
          <span>Status: <strong style={{ color: '#0f766e' }}>Live Watchlist</strong></span>
        </div>

        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.4rem',
          fontSize: '0.78rem',
          color: '#9e8a92'
        }}>
          <Calendar size={14} color="#9e8a92" />
          <span>{currentDate}</span>
        </div>
      </div>
    </header>
  );
}
