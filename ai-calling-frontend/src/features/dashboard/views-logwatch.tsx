'use client';
import { useCallback, useEffect, useState } from 'react';
import {
  fetchAdminAppointments,
  fetchAdminHealthDetails,
  fetchAdminMonitoring,
  fetchAdminToolCalls,
  fetchAdminWebhookEvent,
  fetchAdminWebhookEvents,
} from './api';
import { useDash } from './store';
import { Dialog, Meter, PageHead, Status } from './ui';
import type {
  AdminAppointment,
  AdminHealthDetails,
  AdminMonitoringRow,
  AdminPage,
  AdminToolCall,
} from './types';

function usePaged<T>(load: () => Promise<AdminPage<T>>, enabled = true) {
  const [result, setResult] = useState<AdminPage<T> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    let active = true;
    setLoading(true);
    setError('');
    load().then((data) => {
      if (active) setResult(data);
    }).catch((cause: unknown) => {
      if (active) setError(cause instanceof Error ? cause.message : 'Unable to load records.');
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [enabled, load, retry]);

  return { result, loading, error, retry: () => setRetry((value) => value + 1) };
}

function useAdminGuard() {
  const { isSA } = useDash();
  return isSA;
}

function AccessDenied() {
  return <section className="card">Super Admin access is required to view this page.</section>;
}

function ErrorState({ error, retry }: { error: string; retry: () => void }) {
  return <div className="card" role="alert"><p>{error}</p><button onClick={retry}>Retry</button></div>;
}

function LoadingState() {
  return <div className="card" role="status">Loading…</div>;
}

function EmptyState({ children }: { children: string }) {
  return <div className="card">{children}</div>;
}

function DateLabel({ value }: { value: string | null }) {
  return <span>{value ? new Date(value).toLocaleString() : '—'}</span>;
}

function ClientFilter({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return (
    <input type="number" min="1" aria-label="Filter by client ID" placeholder="Client ID (all)" value={value} onChange={(event) => onChange(event.target.value)} />
  );
}

function Pager({ result, page, onPage }: { result: AdminPage<unknown>; page: number; onPage: (page: number) => void }) {
  const pages = Math.max(1, Math.ceil(result.total / result.limit));
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, marginTop: 12 }}>
      <span>{result.total} total · Page {page} of {pages}</span>
      <div style={{ display: 'flex', gap: 8 }}>
        <button disabled={page <= 1} onClick={() => onPage(page - 1)}>Previous</button>
        <button disabled={page >= pages} onClick={() => onPage(page + 1)}>Next</button>
      </div>
    </div>
  );
}

function JsonDetail({ id, onClose }: { id: number; onClose: () => void }) {
  const { isSA } = useDash();
  const [data, setData] = useState<Awaited<ReturnType<typeof fetchAdminWebhookEvent>> | null>(null);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    if (!isSA) return;
    let active = true;
    fetchAdminWebhookEvent(id).then((value) => { if (active) setData(value); })
      .catch((cause: unknown) => { if (active) setError(cause instanceof Error ? cause.message : 'Unable to load event.'); });
    return () => { active = false; };
  }, [id, isSA, retry]);
  return (
    <Dialog title="Webhook event details" actions={<button onClick={onClose}>Close</button>}>
      {error ? <div role="alert"><p>{error}</p><button onClick={() => { setError(''); setRetry((value) => value + 1); }}>Retry</button></div> : null}
      {!data && !error ? <p role="status">Loading event…</p> : null}
      {data && <>
        <dl className="lw-details">
          <dt>Record ID</dt><dd>{data.id}</dd><dt>Event ID</dt><dd>{data.event_id}</dd><dt>Provider / type</dt><dd>{data.provider} · {data.event_type}</dd>
          <dt>Client</dt><dd>{data.business_name ?? 'Unresolved client'}{data.client_id !== null ? ` (ID ${data.client_id})` : ''}</dd><dt>Status</dt><dd>{data.status}</dd>
          <dt>Error</dt><dd>{data.error_message ?? '—'}</dd><dt>Created / processed</dt><dd><DateLabel value={data.created_at} /> / <DateLabel value={data.processed_at} /></dd>
        </dl>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <strong>Sanitized payload</strong>
          <button onClick={() => void navigator.clipboard.writeText(JSON.stringify(data.payload, null, 2))}>Copy</button>
        </div>
        <pre className="lw-json">{JSON.stringify(data.payload, null, 2)}</pre>
      </>}
    </Dialog>
  );
}

export function MonitoringView() {
  const allowed = useAdminGuard();
  const [page, setPage] = useState(1);
  const [rows, setRows] = useState<AdminPage<AdminMonitoringRow> | null>(null);
  const [health, setHealth] = useState<AdminHealthDetails | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    if (!allowed) return;
    let active = true;
    setLoading(true);
    setError('');
    Promise.all([fetchAdminMonitoring({ page, limit: 10 }), fetchAdminHealthDetails()])
      .then(([monitoring, details]) => {
        if (active) { setRows(monitoring); setHealth(details); }
      })
      .catch((cause: unknown) => { if (active) setError(cause instanceof Error ? cause.message : 'Unable to load monitoring data.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [allowed, page, retry]);
  if (!allowed) return <AccessDenied />;
  return <>
    <PageHead title="Monitoring" sub="Cross-client usage, webhook and booking-tool health." />
    {loading ? <LoadingState /> : error ? <ErrorState error={error} retry={() => setRetry((value) => value + 1)} /> : <>
      {health && <section className="card lw-health">
        <h3>System health</h3>
        <div className="lw-health-grid">
          <span>Database <Status value={health.database_ok ? 'ok' : 'error'} label={health.database_ok ? 'OK' : 'Unavailable'} /></span>
          <span>Last webhook <DateLabel value={health.last_webhook_received_at} /></span>
          <span>Sarvam API key <Status value={health.sarvam_api_key_set ? 'ok' : 'error'} label={health.sarvam_api_key_set ? 'Set' : 'Not set'} /></span>
          <span>Sarvam base URL <Status value={health.sarvam_base_url_set ? 'ok' : 'error'} label={health.sarvam_base_url_set ? 'Set' : 'Not set'} /></span>
          <span>Webhook secret <Status value={health.sarvam_webhook_secret_set ? 'ok' : 'error'} label={health.sarvam_webhook_secret_set ? 'Set' : 'Not set'} /></span>
          <span>Email backend: {health.email_backend}</span>
          <span>Resend key <Status value={health.resend_api_key_set ? 'ok' : 'error'} label={health.resend_api_key_set ? 'Set' : 'Not set'} /></span>
          <span>Production mode <Status value={health.app_env_production ? 'ok' : 'info'} label={health.app_env_production ? 'Yes' : 'No'} /></span>
        </div>
      </section>}
      {!rows?.items.length ? <EmptyState>No clients to monitor.</EmptyState> : <>
        <div className="lw-scroll"><table><thead><tr><th>Business</th><th>Access / agent</th><th>Provider linked</th><th>Last call</th><th>Minutes / alert</th><th>Failed webhooks (24h)</th><th>Last webhook</th><th>Last tool call / error</th></tr></thead>
          <tbody>{rows.items.map((row) => {
            const needsAttention = row.alert === 'limit' || row.failed_webhook_events_24h > 0 ||
              !row.provider_agent_id_present || !row.agent_status || row.agent_status === 'inactive' ||
              !row.last_webhook_received_at;
            return <tr key={row.client_id} className={needsAttention ? 'lw-attention' : ''}>
              <td>{row.business_name}</td><td><Status value={row.access_status} /> <Status value={row.agent_status ?? 'unknown'} /></td>
              <td>{row.provider_agent_id_present ? 'Yes' : 'No'}</td><td><DateLabel value={row.last_call_time} /></td>
              <td>{row.minutes_used} / {row.minutes_limit} min <Meter used={row.minutes_used} limit={row.minutes_limit} /><Status value={row.alert} /></td>
              <td><Status value={row.failed_webhook_events_24h ? 'error' : 'ok'} label={String(row.failed_webhook_events_24h)} /></td>
              <td><DateLabel value={row.last_webhook_received_at} /></td><td><DateLabel value={row.last_tool_call_at} />{row.last_tool_call_error && <div>{row.last_tool_call_error}</div>}</td>
            </tr>;
          })}</tbody></table></div>
        <Pager result={rows} page={page} onPage={setPage} />
      </>}
    </>}
  </>;
}

export function WebhookEventsView() {
  const allowed = useAdminGuard();
  const { openModal, closeModal } = useDash();
  const [filters, setFilters] = useState({ status: '', client_id: '', event_type: '', date_from: '', date_to: '' });
  const [page, setPage] = useState(1);
  const update = (key: keyof typeof filters, value: string) => { setFilters((prev) => ({ ...prev, [key]: value })); setPage(1); };
  const load = useCallback(() => fetchAdminWebhookEvents({
    page, limit: 10, status: filters.status || undefined, client_id: filters.client_id ? Number(filters.client_id) : undefined,
    event_type: filters.event_type || undefined, date_from: filters.date_from || undefined, date_to: filters.date_to || undefined,
  }), [page, filters]);
  const state = usePaged(load, allowed);
  if (!allowed) return <AccessDenied />;
  return <>
    <PageHead title="Webhook events" sub="Inspect sanitized Sarvam event outcomes." />
    <div className="card lw-filters">
      <select aria-label="Filter by status" value={filters.status} onChange={(event) => update('status', event.target.value)}><option value="">All statuses</option>{['received', 'processed', 'failed', 'ignored', 'duplicate'].map((value) => <option key={value}>{value}</option>)}</select>
      <ClientFilter value={filters.client_id} onChange={(value) => update('client_id', value)} />
      <input aria-label="Filter by event type" placeholder="Event type (all)" value={filters.event_type} onChange={(event) => update('event_type', event.target.value)} />
      <label>From <input type="date" value={filters.date_from} onChange={(event) => update('date_from', event.target.value)} /></label>
      <label>To <input type="date" value={filters.date_to} onChange={(event) => update('date_to', event.target.value)} /></label>
    </div>
    {state.loading ? <LoadingState /> : state.error ? <ErrorState error={state.error} retry={state.retry} /> : !state.result?.items.length ? <EmptyState>No events match these filters</EmptyState> : <>
      <div className="lw-scroll"><table><thead><tr><th>ID</th><th>Provider</th><th>Event ID</th><th>Type</th><th>Client</th><th>Status</th><th>Error</th><th>Created</th><th>Processed</th></tr></thead><tbody>
        {state.result.items.map((row) => <tr key={row.id} onClick={() => openModal(<JsonDetail id={row.id} onClose={closeModal} />)} className="lw-clickable">
          <td>{row.id}</td><td>{row.provider}</td><td className="mono">{row.event_id}</td><td>{row.event_type}</td><td>{row.business_name ?? 'Unresolved client'}{row.client_id !== null ? ` (${row.client_id})` : ''}</td><td><Status value={row.status} /></td><td>{row.error_message ?? '—'}</td><td><DateLabel value={row.created_at} /></td><td><DateLabel value={row.processed_at} /></td>
        </tr>)}
      </tbody></table></div>
      <Pager result={state.result} page={page} onPage={setPage} />
    </>}
  </>;
}

export function ToolCallsView() {
  const allowed = useAdminGuard();
  const [filters, setFilters] = useState({ client_id: '', tool: '', success: '', date_from: '', date_to: '' });
  const [page, setPage] = useState(1);
  const update = (key: keyof typeof filters, value: string) => { setFilters((prev) => ({ ...prev, [key]: value })); setPage(1); };
  const load = useCallback(() => fetchAdminToolCalls({
    page, limit: 10, client_id: filters.client_id ? Number(filters.client_id) : undefined, tool: filters.tool || undefined,
    success: filters.success === '' ? undefined : filters.success === 'true',
    date_from: filters.date_from || undefined, date_to: filters.date_to || undefined,
  }), [page, filters]);
  const state = usePaged(load, allowed);
  if (!allowed) return <AccessDenied />;
  return <>
    <PageHead title="Tool calls" sub="Booking-tool outcomes and request correlation." />
    <div className="card lw-filters">
      <ClientFilter value={filters.client_id} onChange={(value) => update('client_id', value)} />
      <select aria-label="Filter by tool" value={filters.tool} onChange={(event) => update('tool', event.target.value)}><option value="">All tools</option>{['check-slot', 'book', 'reschedule', 'cancel'].map((value) => <option key={value}>{value}</option>)}</select>
      <select aria-label="Filter by outcome" value={filters.success} onChange={(event) => update('success', event.target.value)}><option value="">All outcomes</option><option value="true">Success</option><option value="false">Failure</option></select>
      <label>From <input type="date" value={filters.date_from} onChange={(event) => update('date_from', event.target.value)} /></label>
      <label>To <input type="date" value={filters.date_to} onChange={(event) => update('date_to', event.target.value)} /></label>
    </div>
    {state.loading ? <LoadingState /> : state.error ? <ErrorState error={state.error} retry={state.retry} /> : !state.result?.items.length ? <EmptyState>No tool calls match these filters</EmptyState> : <>
      <div className="lw-scroll"><table><thead><tr><th>Client</th><th>Tool / action</th><th>Outcome</th><th>Error</th><th>Appointment</th><th>Duration</th><th>Request ID</th><th>Created</th></tr></thead><tbody>
        {state.result.items.map((row) => <ToolCallRow key={row.id} row={row} />)}
      </tbody></table></div>
      <Pager result={state.result} page={page} onPage={setPage} />
    </>}
  </>;
}

function ToolCallRow({ row }: { row: AdminToolCall }) {
  return <tr>
    <td>{row.business_name ?? 'Unresolved client'}{!row.client_id && <div className="lw-note">Client could not be resolved</div>}</td>
    <td>{row.tool}<div className="lw-note">{row.action}</div></td><td><Status value={row.success ? 'success' : 'failed'} label={row.success ? 'Success' : 'Failure'} /></td>
    <td>{row.error_code ?? '—'}{row.message && <div>{row.message}</div>}</td><td>{row.appointment_id ?? '—'}</td><td>{row.duration_ms} ms</td>
    <td>{row.request_id ? <button className="lw-copy" onClick={() => void navigator.clipboard.writeText(row.request_id!)}>Copy ID</button> : '—'}{row.request_id && <div className="mono">{row.request_id}</div>}</td><td><DateLabel value={row.created_at} /></td>
  </tr>;
}

export function AdminAppointmentsView() {
  const allowed = useAdminGuard();
  const [filters, setFilters] = useState({ client_id: '', status: '', source: '', date_from: '', date_to: '' });
  const [page, setPage] = useState(1);
  const update = (key: keyof typeof filters, value: string) => { setFilters((prev) => ({ ...prev, [key]: value })); setPage(1); };
  const load = useCallback(() => fetchAdminAppointments({
    page, limit: 10, client_id: filters.client_id ? Number(filters.client_id) : undefined, status: filters.status || undefined,
    source: filters.source || undefined, date_from: filters.date_from || undefined, date_to: filters.date_to || undefined,
  }), [page, filters]);
  const state = usePaged(load, allowed);
  if (!allowed) return <AccessDenied />;
  return <>
    <PageHead title="All appointments" sub="Read-only appointments across all clients, newest created first." />
    <div className="card lw-filters">
      <ClientFilter value={filters.client_id} onChange={(value) => update('client_id', value)} />
      <select aria-label="Filter by status" value={filters.status} onChange={(event) => update('status', event.target.value)}><option value="">All statuses</option>{['scheduled', 'confirmed', 'completed', 'cancelled', 'rescheduled'].map((value) => <option key={value}>{value}</option>)}</select>
      <select aria-label="Filter by source" value={filters.source} onChange={(event) => update('source', event.target.value)}><option value="">All sources</option><option value="ai_agent">AI agent</option><option value="manual">Manual</option></select>
      <label>From <input type="date" value={filters.date_from} onChange={(event) => update('date_from', event.target.value)} /></label>
      <label>To <input type="date" value={filters.date_to} onChange={(event) => update('date_to', event.target.value)} /></label>
    </div>
    {state.loading ? <LoadingState /> : state.error ? <ErrorState error={state.error} retry={state.retry} /> : !state.result?.items.length ? <EmptyState>No appointments match these filters</EmptyState> : <>
      <div className="lw-scroll"><table><thead><tr><th>Client</th><th>Customer</th><th>Appointment date</th><th>Time</th><th>Status</th><th>Source</th><th>Created</th></tr></thead><tbody>
        {state.result.items.map((row) => <AppointmentRow key={row.id} row={row} />)}
      </tbody></table></div>
      <Pager result={state.result} page={page} onPage={setPage} />
    </>}
  </>;
}

function AppointmentRow({ row }: { row: AdminAppointment }) {
  return <tr><td>{row.business_name}</td><td>{row.customer_name}</td><td>{row.date}</td><td>{row.time}</td><td><Status value={row.status} /></td>
    <td><Status value={row.source} label={row.source === 'ai_agent' ? 'AI agent' : 'Manual'} /></td><td><DateLabel value={row.created_at} /></td></tr>;
}
