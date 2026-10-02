import React, { useState } from 'react';
import StatCard from './StatCard';
import { ShieldAlert, AlertTriangle, Shield, KeyRound, Search, Filter, RefreshCw, Lock, Trash2 } from 'lucide-react';

export default function RemediationView({
  remediationData,
  selectedSeverity,
  setSelectedSeverity,
  searchQuery,
  setSearchQuery,
  onRemediate
}) {
  const [selectedPlatform, setSelectedPlatform] = useState('All');

  const metrics = remediationData?.metrics || {
    total_incidents: 0,
    critical: 0,
    high: 0,
    medium: 0
  };

  const incidents = remediationData?.incidents || [];

  const platforms = ['All', 'AWS', 'Okta', 'AD'];

  const filteredIncidents = incidents.filter(item => {
    if (selectedPlatform !== 'All' && item.platform?.toUpperCase() !== selectedPlatform.toUpperCase()) {
      return false;
    }
    return true;
  });

  return (
    <div>
      {/* Metric Cards Grid */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
        gap: '1.25rem',
        marginBottom: '2rem'
      }}>
        <StatCard
          label="Total Open Incidents"
          value={metrics.total_incidents}
          subtitle="Active policy violations"
          icon={ShieldAlert}
          accent="red"
        />
        <StatCard
          label="Critical Violations"
          value={metrics.critical}
          subtitle="Ghost accounts"
          icon={AlertTriangle}
          accent="orange"
        />
        <StatCard
          label="High Violations"
          value={metrics.high}
          subtitle="Privilege creep"
          icon={Shield}
          accent="yellow"
        />
        <StatCard
          label="Medium Violations"
          value={metrics.medium}
          subtitle="Stale tokens"
          icon={KeyRound}
          accent="rose"
        />
      </div>

      {/* Control Panel: Filters & Search */}
      <div className="glass-panel" style={{ padding: '1.25rem 1.5rem', marginBottom: '2rem' }}>
        <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', alignItems: 'center' }}>
          {/* Severity Filter */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Filter size={16} color="#6b5860" />
            <span style={{ fontSize: '0.82rem', color: '#6b5860', fontWeight: 600 }}>Severity:</span>
            <select
              value={selectedSeverity}
              onChange={(e) => setSelectedSeverity(e.target.value)}
              style={{
                background: '#ffffff',
                color: '#29181d',
                border: '1px solid #d8ccc2',
                borderRadius: '6px',
                padding: '0.45rem 0.8rem',
                fontSize: '0.82rem',
                outline: 'none',
                cursor: 'pointer'
              }}
            >
              <option value="All">All Severities</option>
              <option value="Critical">Critical</option>
              <option value="High">High</option>
              <option value="Medium">Medium</option>
            </select>
          </div>

          {/* Search Input */}
          <div style={{ position: 'relative', flex: 1, minWidth: '220px' }}>
            <Search size={15} color="#9e8a92" style={{ position: 'absolute', left: '0.75rem', top: '50%', transform: 'translateY(-50%)' }} />
            <input
              type="text"
              placeholder="Search by rule type or description..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{
                width: '100%',
                background: '#ffffff',
                color: '#29181d',
                border: '1px solid #d8ccc2',
                borderRadius: '6px',
                padding: '0.45rem 0.8rem 0.45rem 2.2rem',
                fontSize: '0.82rem',
                outline: 'none'
              }}
            />
          </div>

          {/* Platform Tabs */}
          <div style={{ display: 'flex', background: '#faf6f1', padding: '0.2rem', borderRadius: '8px', border: '1px solid #e6ded6' }}>
            {platforms.map(p => (
              <button
                key={p}
                onClick={() => setSelectedPlatform(p)}
                style={{
                  padding: '0.35rem 0.75rem',
                  fontSize: '0.78rem',
                  fontWeight: 700,
                  borderRadius: '6px',
                  border: 'none',
                  background: selectedPlatform === p ? '#ffffff' : 'transparent',
                  color: selectedPlatform === p ? '#9f1239' : '#6b5860',
                  boxShadow: selectedPlatform === p ? '0 1px 3px rgba(41,24,29,0.08)' : 'none',
                  cursor: 'pointer'
                }}
              >
                {p}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Policy Incidents Table */}
      <div className="glass-panel" style={{ padding: '1.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1.25rem', flexWrap: 'wrap' }}>
          <div style={{ width: '4px', height: '1.2rem', background: '#9f1239', borderRadius: '2px' }} />
          <h3 style={{ fontSize: '1.15rem', fontWeight: 700, color: '#29181d' }} className="title-font">
            Policy Incidents & Action Backlog
          </h3>
          <span style={{ fontSize: '0.78rem', color: '#6b5860', marginLeft: 'auto' }}>
            Showing {filteredIncidents.length} active violations
          </span>
        </div>

        {filteredIncidents.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '3rem', color: '#6b5860' }}>
            <p>No security policy incidents match your search filters.</p>
          </div>
        ) : (
          <div className="custom-table-container">
            <table className="custom-table">
              <thead>
                <tr>
                  <th>Rule Type</th>
                  <th>Identity ID</th>
                  <th>Severity</th>
                  <th>Platform</th>
                  <th>Violation Details</th>
                  <th style={{ textAlign: 'right' }}>Remediation Action</th>
                </tr>
              </thead>
              <tbody>
                {filteredIncidents.map((item, idx) => {
                  const sev = item.severity?.toUpperCase() || 'MEDIUM';
                  let btnLabel = 'Remediate';
                  let BtnIcon = Lock;
                  let btnClass = 'btn-danger';

                  if (sev === 'CRITICAL') {
                    btnLabel = 'Disable Account';
                    BtnIcon = Trash2;
                    btnClass = 'btn-danger';
                  } else if (sev === 'HIGH') {
                    btnLabel = 'Revoke Access';
                    BtnIcon = Lock;
                    btnClass = 'btn-warning';
                  } else if (sev === 'MEDIUM') {
                    btnLabel = 'Rotate Token';
                    BtnIcon = RefreshCw;
                    btnClass = 'btn-primary';
                  }

                  return (
                    <tr key={idx}>
                      <td style={{ fontWeight: 700, color: '#29181d' }}>
                        {item.rule_type}
                      </td>
                      <td style={{ color: '#6b5860' }}>
                        #{item.identity_id}
                      </td>
                      <td>
                        <span className={`pill-badge ${sev === 'CRITICAL' ? 'pill-crit' : sev === 'HIGH' ? 'pill-high' : 'pill-medium'}`}>
                          {item.severity}
                        </span>
                      </td>
                      <td style={{ fontWeight: 700, color: '#9f1239' }}>
                        {item.platform || 'N/A'}
                      </td>
                      <td style={{ fontSize: '0.82rem', color: '#6b5860', maxWidth: '380px' }}>
                        {item.description}
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        <button
                          onClick={() => onRemediate(item)}
                          className={btnClass}
                          style={{ display: 'inline-flex', alignItems: 'center', gap: '0.35rem' }}
                        >
                          <BtnIcon size={13} />
                          <span>{btnLabel}</span>
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
