'use client';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { useDash } from './store';
import { Chips, CopyButton, Dialog, Meter, PageHead, Toggle } from './ui';
import { PLAN_PRICE, inr } from './util';
import type { AdminClientIntegration, AdminClientToolToken, Agent, ContactMessage } from './types';
import {
  adminAgentErrorMessage,
  approveAccess,
  createClientToolToken,
  declineAccess,
  fetchAdminAgentLinks,
  fetchAdminIntegration,
  updateBusinessStatus,
  addMinutePack,
  viewBusinessPin,
  linkAdminAgent,
  unlinkAdminAgent,
  updateAdminAgent,
  resetBusinessPin,
  toggleAgentPower,
  updateContactMessage,
  type AdminAgentInput,
} from './api';

const near = (u: number, l: number) => u / l >= 0.9;

export function PlatformOverview() {
  const { s } = useDash();
  const act = s.businesses.filter((b) => b.status === 'Active');
  const mrr = act.reduce((t, b) => t + PLAN_PRICE[b.plan], 0);
  const M = [8.2, 9.6, 11.1, 12.4, 14, mrr / 1000], mx = Math.max(...M);
  const kp = [
    { t: 'Active businesses', v: String(act.length), n: `${s.businesses.length - act.length} suspended`, k: 'k2' },
    { t: 'Monthly revenue', v: inr(mrr), n: 'Active plans only', k: 'k1' },
    { t: 'Minutes used', v: String(s.businesses.reduce((t, b) => t + b.minutes_used, 0)), n: `of ${s.businesses.reduce((t, b) => t + b.minutes_limit, 0)} across plans`, k: 'k3' },
    { t: 'Pending access', v: String(s.requests.length), n: '', k: 'k4' },
  ];
  return (
    <>
      <PageHead title="Platform overview" sub="Revenue, usage and health across every business." />
      <div className="grid4">{kp.map((k) => <div key={k.t} className={`card kpi ${k.k}`}><small>{k.t}</small><b>{k.v}</b>{k.t === 'Pending access' ? <small><Link href="/dashboard/platform/access">Review requests</Link></small> : <small>{k.n}</small>}</div>)}</div>
      <div className="cols" style={{ marginTop: 14 }}>
        <div className="card" style={{ overflow: 'auto' }}>
          <h3>Businesses</h3>
          <table><thead><tr><th>Business</th><th>Plan</th><th>Minutes</th><th>Status</th></tr></thead>
            <tbody>{s.businesses.map((b) => (
              <tr key={b.id}><td>{b.name}</td><td>{b.plan}</td>
                <td style={{ minWidth: 140 }}><Meter used={b.minutes_used} limit={b.minutes_limit} /><small className="mono">{b.minutes_used}/{b.minutes_limit}</small>{near(b.minutes_used, b.minutes_limit) && <> <span className="st rescheduled">Near limit</span></>}</td>
                <td><span className={`st ${b.status === 'Active' ? 'completed' : 'cancelled'}`}>{b.status}</span></td></tr>
            ))}</tbody></table>
        </div>
        <div className="card"><h3>Revenue, 6 months (₹ thousand)</h3>
          <div className="bars">{M.map((v, i) => <div key={i} style={{ flexDirection: 'column', alignItems: 'stretch' }}><div style={{ flex: 1 }}><i style={{ height: `${(v / mx) * 100}%`, background: '#F26B2A' }} /></div><span>{['May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct'][i]}</span></div>)}</div>
        </div>
      </div>
    </>
  );
}

export function AccessControl() {
  const { s, toast, actor, reload } = useDash();

  const grant = async (id: string) => {
    const r = s.requests.find((x) => x.id === id);
    if (!r) return;
    try {
      await approveAccess(id, actor);
      await reload();
      toast(`Access granted to ${r.business}`);
    } catch (err: any) {
      toast(err.message || 'Error granting access');
    }
  };

  const decline = async (id: string) => {
    const r = s.requests.find((x) => x.id === id);
    if (!r) return;
    try {
      await declineAccess(id, actor);
      await reload();
      toast(`Access declined for ${r.business}`);
    } catch (err: any) {
      toast(err.message || 'Error declining access');
    }
  };

  const flip = async (id: string) => {
    const b = s.businesses.find((x) => x.id === id);
    if (!b) return;
    const st = b.status === 'Active' ? 'Suspended' : 'Active';
    try {
      await updateBusinessStatus(id, st, actor);
      await reload();
      toast(`${b.name} ${st === 'Active' ? 'reactivated' : 'suspended'}`);
    } catch (err: any) {
      toast(err.message || 'Error updating status');
    }
  };

  return (
    <>
      <PageHead title="Access control" sub="New signups wait on their status page until you approve them. After approval, monitor usage and last login." />
      <div className="card"><h3>Pending ({s.requests.length})</h3>
        <div style={{ display: 'grid', gap: 10, marginTop: 10 }}>
          {s.requests.map((r) => (
            <div key={r.id} className="ro" style={{ display: 'flex', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
              <div><b>{r.business}</b><br /><span className="mut">{r.plan}, {r.billing}</span> <span className="mono">{inr(r.amount)}</span> <span className="st">{r.status}</span></div>
              <div className="acts" style={{ margin: 0 }}><button onClick={() => toast('Opening payment proof (UPI verified)')}>View payment</button><button className="dng" onClick={() => decline(r.id)}>Decline</button><button className="pri" onClick={() => grant(r.id)}>Grant access</button></div>
            </div>
          ))}
          {s.requests.length === 0 && <p className="mut">All caught up. New signups will show up here.</p>}
        </div>
      </div>
      <div className="card" style={{ marginTop: 14, overflow: 'auto' }}><h3>Monitoring</h3>
        <table><thead><tr><th>Business</th><th>Last login</th><th>Minutes</th><th>Status</th><th /></tr></thead>
          <tbody>{s.businesses.map((b) => <tr key={b.id}><td>{b.name}</td><td>{b.last_login}</td><td className="mono">{b.minutes_used}/{b.minutes_limit}</td><td><span className={`st ${b.status === 'Active' ? 'completed' : 'cancelled'}`}>{b.status}</span></td><td><button onClick={() => flip(b.id)}>{b.status === 'Active' ? 'Suspend' : 'Resume'}</button></td></tr>)}</tbody></table>
      </div>
    </>
  );
}

function PinReveal({ id }: { id: string }) {
  const { s, closeModal, actor, toast } = useDash();
  const b = s.businesses.find((x) => x.id === id)!;
  const [pinVal, setPinVal] = useState('••••');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    viewBusinessPin(id, actor)
      .then((res) => {
        setPinVal(res.pin);
        setLoading(false);
      })
      .catch(() => {
        setPinVal('••••');
        setLoading(false);
        toast('Unable to load staff PIN');
      });
  }, [id, actor, toast]);

  return (
    <Dialog title={`Staff PIN: ${b.name}`} actions={<button onClick={closeModal}>Close</button>}>
      <p className="mono" style={{ fontSize: 32, letterSpacing: 10, margin: '6px 0' }}>
        {loading ? '...' : pinVal}
      </p>
      <p className="mut" style={{ margin: 0 }}>This view was logged to the platform audit trail.</p>
    </Dialog>
  );
}

function PinChange({ id }: { id: string }) {
  const { s, closeModal, toast, actor, reload } = useDash();
  const b = s.businesses.find((x) => x.id === id)!;
  const [v, setV] = useState('');
  const [busy, setBusy] = useState(false);

  const save = async () => {
    if (!/^\d{4}$/.test(v)) {
      toast('PIN must be 4 digits');
      return;
    }
    setBusy(true);
    try {
      await resetBusinessPin(id, actor, v);
      await reload();
      closeModal();
      toast('PIN changed and logged to audit trail');
    } catch (err: any) {
      toast(err.message || 'Error resetting PIN');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog title={`Change PIN: ${b.name}`} actions={<><button onClick={closeModal}>Cancel</button><button className="pri" disabled={busy || v.length < 4} onClick={save}>{busy ? 'Saving…' : 'Save PIN'}</button></>}>
      <label>New 4-digit PIN<input className="mono" inputMode="numeric" maxLength={4} value={v} onChange={(e) => setV(e.target.value.replace(/\D/g, ''))} /></label>
    </Dialog>
  );
}

export function BusinessesPlans() {
  const { s, toast, openModal, actor, reload } = useDash();

  const addPack = async (id: string, name: string) => {
    try {
      await addMinutePack(id, 100, actor);
      await reload();
      toast(`100-minute pack added for ${name}`);
    } catch (err: any) {
      toast(err.message || 'Error adding minute pack');
    }
  };

  return (
    <>
      <PageHead title="Businesses and plans" sub="Limits, packs, subscriptions and staff PINs." />
      <div className="card" style={{ overflow: 'auto' }}>
        <table><thead><tr><th>Business</th><th>Plan and limit</th><th>Renews</th><th>Revenue</th><th>Staff PIN</th><th /></tr></thead>
          <tbody>{s.businesses.map((b) => (
            <tr key={b.id}><td><b>{b.name}</b></td><td>{b.plan}<br /><span className="mono mut">{b.minutes_used}/{b.minutes_limit} min</span></td><td className="mono">{b.renews_on}</td><td className="mono">{inr(PLAN_PRICE[b.plan])}</td>
              <td className="mono">••••<br /><button onClick={() => openModal(<PinReveal id={b.id} />)}>View</button> <button onClick={() => openModal(<PinChange id={b.id} />)}>Change</button></td>
              <td><button onClick={() => addPack(b.id, b.name)}>Add 100 min</button></td></tr>
          ))}</tbody></table>
      </div>
    </>
  );
}

export function FleetView() {
  const { s, isSA, toast, actor, reload, openModal } = useDash();
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const [issuedToken, setIssuedToken] = useState<AdminClientToolToken | null>(null);
  const [issuedClientName, setIssuedClientName] = useState('');
  const name = (id: string) => s.businesses.find((b) => b.id === id)?.name ?? id;

  useEffect(() => {
    if (!isSA) return;
    let active = true;
    setLoading(true);
    setError('');
    fetchAdminAgentLinks()
      .then((result) => { if (active) setAgents(result); })
      .catch((cause: unknown) => { if (active) setError(cause instanceof Error ? cause.message : 'Unable to load agent links.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [isSA, retry]);

  const refreshAgents = async () => {
    await reload();
    setAgents(await fetchAdminAgentLinks());
  };

  const openIntegration = (clientId: string, clientName: string) => {
    openModal(
      <ClientIntegrationDialog
        clientId={clientId}
        clientName={clientName}
        onToken={(token) => {
          setIssuedClientName(clientName);
          setIssuedToken(token);
          setAgents((current) => current.map((agent) => agent.business_id === clientId
            ? { ...agent, tool_token_exists: true }
            : agent));
        }}
      />
    );
  };

  const flip = async (id: string) => {
    const a = agents.find((x) => x.id === id);
    if (!a) return;
    try {
      await toggleAgentPower(id, !a.online, actor);
      await refreshAgents();
      toast(`Turned ${a.name} ${!a.online ? 'on' : 'off'}`);
    } catch (err: any) {
      toast(err.message || 'Error toggling agent power');
    }
  };

  if (!isSA) return <AccessDenied />;

  return (
    <>
      <PageHead
        title="AI agents, all businesses"
        sub="Link Sarvam agents and phone numbers to clients, manage their tool credentials, and control agent status."
        right={<button className="pri" disabled={s.businesses.length === 0} onClick={() => openModal(<AgentLinkDialog businesses={s.businesses} onSaved={refreshAgents} />)}>Link agent</button>}
      />
      <div className="card" style={{ overflow: 'auto', marginBottom: 14 }}>
        <h3>Client integrations</h3>
        <table><thead><tr><th>Client</th><th>Client ID</th><th /></tr></thead>
          <tbody>{s.businesses.map((business) => (
            <tr key={business.id}>
              <td><b>{business.name}</b></td>
              <td className="mono">{business.id}</td>
              <td><button onClick={() => openIntegration(business.id, business.name)}>Integration</button></td>
            </tr>
          ))}</tbody></table>
        {s.businesses.length === 0 && <p className="mut">No clients are available.</p>}
      </div>
      <div className="card" style={{ overflow: 'auto' }}>
        <h3>Agent links</h3>
        {loading ? <p role="status">Loading linked agents…</p> : error
          ? <div role="alert"><p>{error}</p><button onClick={() => setRetry((value) => value + 1)}>Retry</button></div>
          : <table><thead><tr><th>Agent</th><th>Client</th><th>Provider agent ID</th><th>Phone number</th><th>Status</th><th>Tool token</th><th>Actions</th></tr></thead>
            <tbody>{agents.map((a) => (
              <tr key={a.id}>
                <td><b>{a.name}</b></td>
                <td>{name(a.business_id)}</td>
                <td className="mono">{a.provider_agent_id || '—'}</td>
                <td>{a.phone ? <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, whiteSpace: 'nowrap' }}><span className="mono">{a.phone}</span><CopyButton value={a.phone} label="Copy" /></span> : '—'}</td>
                <td><span className={`st ${a.online ? 'completed' : 'cancelled'}`}>{a.status ? `${a.status.charAt(0).toUpperCase()}${a.status.slice(1)}` : a.online ? 'Active' : 'Inactive'}</span></td>
                <td><span className={`st ${a.tool_token_exists ? 'completed' : 'rescheduled'}`}>{a.tool_token_exists ? 'Token set' : 'No token'}</span></td>
                <td><div className="acts" style={{ margin: 0 }}>
                  <button onClick={() => openModal(<AgentLinkDialog businesses={s.businesses} agent={a} onSaved={refreshAgents} />)}>Edit</button>
                  <button className="dng" onClick={() => openModal(<UnlinkAgentDialog agent={a} onUnlinked={refreshAgents} />)}>Unlink</button>
                  <Toggle on={a.online} label={`Power ${a.name}`} onClick={() => flip(a.id)} />
                </div></td>
              </tr>
            ))}</tbody></table>}
        {!loading && !error && agents.length === 0 && <p className="mut">No linked agents yet. Use Link agent to assign one to a client.</p>}
      </div>
      {issuedToken && <IssuedTokenDialog token={issuedToken} clientName={issuedClientName} onClose={() => setIssuedToken(null)} />}
    </>
  );
}

function AgentLinkDialog({ businesses, agent, onSaved }: { businesses: { id: string; name: string }[]; agent?: Agent; onSaved: () => Promise<void> }) {
  const { closeModal, toast } = useDash();
  const [clientId, setClientId] = useState(agent?.business_id ?? businesses[0]?.id ?? '');
  const [name, setName] = useState(agent?.name ?? '');
  const [providerAgentId, setProviderAgentId] = useState(agent?.provider_agent_id ?? '');
  const [phone, setPhone] = useState(agent?.phone.replace(/[^\d+]/g, '') ?? '');
  const [phoneTouched, setPhoneTouched] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const phoneValid = /^\+[1-9]\d{6,14}$/.test(phone);

  const save = async () => {
    setPhoneTouched(true);
    setError('');
    if (!clientId && !agent) {
      setError('Select a client.');
      return;
    }
    if (!name.trim() || !providerAgentId.trim() || !phoneValid) {
      setError('Enter an agent name, provider agent ID, and valid E.164 phone number.');
      return;
    }
    const input: AdminAgentInput = {
      name: name.trim(),
      provider: 'sarvam',
      provider_agent_id: providerAgentId.trim(),
      phone_number: phone,
    };
    setBusy(true);
    try {
      if (agent) await updateAdminAgent(agent.id, input);
      else await linkAdminAgent(clientId, input);
      await onSaved();
      closeModal();
      toast(agent ? 'Agent link updated' : 'Agent linked to client');
    } catch (cause: unknown) {
      setError(adminAgentErrorMessage(cause));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      title={agent ? `Edit ${agent.name}` : 'Link a Sarvam agent'}
      actions={<><button onClick={closeModal}>Cancel</button><button className="pri" disabled={busy} onClick={save}>{busy ? 'Saving…' : agent ? 'Save changes' : 'Link agent'}</button></>}
    >
      {!agent && <label>Client<select value={clientId} onChange={(event) => setClientId(event.target.value)} required>
        {businesses.map((business) => <option key={business.id} value={business.id}>{business.name}</option>)}
      </select></label>}
      <label>Agent name<input maxLength={150} value={name} onChange={(event) => setName(event.target.value)} required /></label>
      <label>Provider<input value="Sarvam" readOnly /></label>
      <label>Provider agent ID<input maxLength={255} value={providerAgentId} onChange={(event) => setProviderAgentId(event.target.value)} required /></label>
      <label>Phone number (E.164)
        <input
          type="tel"
          value={phone}
          onChange={(event) => setPhone(event.target.value)}
          onBlur={() => setPhoneTouched(true)}
          placeholder="+919876543210"
          aria-invalid={phoneTouched && !phoneValid}
          aria-describedby="agent-phone-hint"
          required
        />
      </label>
      <small id="agent-phone-hint" className="mut">Use + followed by the country code and number, for example +919876543210.</small>
      {phoneTouched && !phoneValid && <small role="alert" style={{ color: 'var(--bad)' }}>Enter a valid E.164 number such as +919876543210.</small>}
      {error && <p role="alert" style={{ color: 'var(--bad)' }}>{error}</p>}
    </Dialog>
  );
}

function UnlinkAgentDialog({ agent, onUnlinked }: { agent: Agent; onUnlinked: () => Promise<void> }) {
  const { closeModal, toast } = useDash();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const unlink = async () => {
    setBusy(true);
    setError('');
    try {
      await unlinkAdminAgent(agent.id);
      await onUnlinked();
      closeModal();
      toast(`${agent.name} deactivated`);
    } catch (cause: unknown) {
      setError(adminAgentErrorMessage(cause));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog title={`Unlink ${agent.name}?`} actions={<><button onClick={closeModal}>Cancel</button><button className="dng" disabled={busy} onClick={unlink}>{busy ? 'Unlinking…' : 'Unlink agent'}</button></>}>
      <p>This deactivates the agent; it does not delete the agent or its call history.</p>
      {error && <p role="alert" style={{ color: 'var(--bad)' }}>{error}</p>}
    </Dialog>
  );
}

function displayDate(value: string | null): string {
  return value ? new Date(value).toLocaleString() : '—';
}

function ClientIntegrationDialog({ clientId, clientName, onToken }: { clientId: string; clientName: string; onToken: (token: AdminClientToolToken) => void }) {
  const { closeModal, openModal } = useDash();
  const [integration, setIntegration] = useState<AdminClientIntegration | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError('');
    fetchAdminIntegration(clientId)
      .then((result) => { if (active) setIntegration(result); })
      .catch((cause: unknown) => { if (active) setError(cause instanceof Error ? cause.message : 'Unable to load integration details.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [clientId, retry]);

  const confirmToken = () => openModal(
    <TokenRotationDialog
      clientId={clientId}
      clientName={clientName}
      rotating={Boolean(integration?.credential_exists)}
      onToken={(token) => {
        onToken(token);
        closeModal();
      }}
    />
  );

  return (
    <Dialog title={`${clientName} integration`} actions={<><button onClick={closeModal}>Close</button>{integration && <button className="pri" onClick={confirmToken}>{integration.credential_exists ? 'Rotate token' : 'Generate token'}</button>}</>}>
      {loading && <p role="status">Loading integration details…</p>}
      {error && <div role="alert"><p>{error}</p><button onClick={() => setRetry((value) => value + 1)}>Retry</button></div>}
      {integration && <>
        {!integration.urls_are_absolute && <p role="note" className="vo">These URLs are relative. Set PUBLIC_API_BASE_URL on the server to provide absolute URLs.</p>}
        <p><b>Signed event webhook URL</b></p>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}><code className="mono" style={{ wordBreak: 'break-all' }}>{integration.signed_event_webhook_url}</code><CopyButton value={integration.signed_event_webhook_url} /></div>
        <h4>Tool URL patterns</h4>
        <div style={{ display: 'grid', gap: 8 }}>
          {Object.entries(integration.tool_url_patterns).map(([action, url]) => (
            <div key={action}>
              <small>{action}</small>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}><code className="mono" style={{ wordBreak: 'break-all' }}>{url}</code><CopyButton value={url} /></div>
            </div>
          ))}
        </div>
        <h4>Tool token</h4>
        <p><span className={`st ${integration.credential_exists ? 'completed' : 'rescheduled'}`}>{integration.credential_exists ? 'Token exists' : 'No token'}</span></p>
        <dl className="lw-details">
          <dt>Created</dt><dd>{displayDate(integration.credential_created_at)}</dd>
          <dt>Rotated</dt><dd>{displayDate(integration.credential_rotated_at)}</dd>
          <dt>Last used</dt><dd>{displayDate(integration.credential_last_used_at)}</dd>
        </dl>
        <h4>Linked agents</h4>
        {integration.agents.length ? <div style={{ display: 'grid', gap: 6 }}>
          {integration.agents.map((agent) => (
            <div key={agent.id} className="ro" style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
              <span>{agent.name} · ID <code className="mono">{agent.id}</code> · {agent.phone_number || 'No phone number'} · {agent.status}</span>
              <div style={{ display: 'flex', gap: 6 }}>{agent.phone_number && <CopyButton value={agent.phone_number} label="Copy phone" />}<CopyButton value={agent.id} label="Copy agent ID" /></div>
            </div>
          ))}
        </div> : <p className="mut">No agents are linked to this client.</p>}
        <p className="mut" style={{ marginTop: 14 }}>The legacy shared token is still accepted until it is disabled on the server.</p>
      </>}
    </Dialog>
  );
}

function TokenRotationDialog({ clientId, clientName, rotating, onToken }: { clientId: string; clientName: string; rotating: boolean; onToken: (token: AdminClientToolToken) => void }) {
  const { closeModal } = useDash();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const generate = async () => {
    setBusy(true);
    setError('');
    try {
      const token = await createClientToolToken(clientId);
      onToken(token);
    } catch {
      setError('Unable to generate the tool token. Check Super Admin access and try again.');
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog title={`${rotating ? 'Rotate' : 'Generate'} ${clientName} tool token?`} actions={<><button onClick={closeModal}>Cancel</button><button className="dng" disabled={busy} onClick={generate}>{busy ? 'Working…' : rotating ? 'Rotate token' : 'Generate token'}</button></>}>
      <p>The old token stops working immediately. Update the Sarvam tool URLs with the new token as soon as it is generated.</p>
      {error && <p role="alert" style={{ color: 'var(--bad)' }}>{error}</p>}
    </Dialog>
  );
}

function IssuedTokenDialog({ token, clientName, onClose }: { token: AdminClientToolToken; clientName: string; onClose: () => void }) {
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose(); };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);
  return (
    <div className="ov" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <div className="md" role="dialog" aria-modal="true">
        <h3>{clientName} tool token</h3>
        <p role="alert"><b>This will not be shown again.</b> Copy the token and URLs now.</p>
        {!token.urls_are_absolute && <p className="vo">These URLs are relative. Set PUBLIC_API_BASE_URL on the server to provide absolute URLs.</p>}
        <label>Raw token
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <code className="mono" style={{ wordBreak: 'break-all' }}>{token.token}</code>
            <CopyButton value={token.token} label="Copy token" />
          </div>
        </label>
        <h4>Ready-to-paste tool URLs</h4>
        <div style={{ display: 'grid', gap: 8 }}>
          {Object.entries(token.tool_urls).map(([action, url]) => (
            <div key={action}>
              <small>{action}</small>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}><code className="mono" style={{ wordBreak: 'break-all' }}>{url}</code><CopyButton value={url} /></div>
            </div>
          ))}
        </div>
        <div className="acts"><button onClick={onClose}>Close</button></div>
      </div>
    </div>
  );
}

function MessageDialog({ m }: { m: ContactMessage }) {
  const { closeModal, toast } = useDash();
  return (
    <Dialog title={m.name} actions={<><button onClick={closeModal}>Close</button><button className="pri" onClick={() => { closeModal(); toast('Reply sent to customer email'); }}>Send reply</button></>}>
      <p className="mut" style={{ margin: 0 }}>{m.email} · {m.phone} · {m.received_at}</p>
      <div className="note">{m.message}</div>
      <label>Reply<textarea placeholder="Write a reply" /></label>
    </Dialog>
  );
}

export function MessagesInbox() {
  const { s, openModal, toast, reload } = useDash();

  const mark = async (id: string, patch: Partial<ContactMessage>) => {
    try {
      await updateContactMessage(id, patch);
      await reload();
    } catch (err: any) {
      toast(err.message || 'Error updating message');
    }
  };

  return (
    <>
      <PageHead title="Messages" sub="Contact-form messages from the landing page. Only Super Admin can see these." />
      <div style={{ display: 'grid', gap: 12 }}>
        {s.messages.map((m) => (
          <div key={m.id} className="card" style={{ display: 'flex', gap: 12, justifyContent: 'space-between', flexWrap: 'wrap' }}>
            <div style={{ minWidth: 0, flex: 1 }}>
              <div>{!m.read && <i className="pd" style={{ background: '#F26B2A' }} />}<b>{m.name}</b> <span className="mono mut">{m.received_at}</span>{m.handled && <> <span className="st completed">handled</span></>}</div>
              <p style={{ margin: '6px 0' }}>{m.message}</p><small className="mut">{m.email} · {m.phone}</small>
            </div>
            <div className="acts" style={{ margin: 0 }}>
              <button onClick={() => { mark(m.id, { read: true }); openModal(<MessageDialog m={m} />); }}>{m.read ? 'View' : 'Open'}</button>
              <button disabled={m.handled} onClick={() => mark(m.id, { handled: true, read: true })}>Mark handled</button>
            </div>
          </div>
        ))}
        {s.messages.length === 0 && <p className="mut">No contact messages received yet.</p>}
      </div>
    </>
  );
}

const EP = [
  ['GET', '/api/v1/appointments', 'List appointments', '200 OK', 'Returns list of appointments with status, customer, date, time'],
  ['POST', '/api/v1/appointments', 'Create appointment', '201 Created', 'Creates appointment, records audit history'],
  ['PATCH', '/api/v1/appointments/{id}/reschedule', 'Reschedule appointment', '200 OK', 'Updates date/time and logs change reason'],
  ['POST', '/api/v1/appointments/{id}/cancel', 'Cancel appointment', '200 OK', 'Sets cancelled status, source (ai_agent/staff) & reason'],
  ['GET', '/api/v1/appointments/{id}/history', 'Appointment history', '200 OK', 'Audit trail of events for this appointment'],
  ['GET', '/api/v1/calls', 'List calls with recordings', '200 OK', 'Returns call logs with audio recording URLs and transcripts'],
  ['PATCH', '/api/v1/agents/{id}/power', 'Turn agent on/off', '200 OK', 'Toggles AI agent availability across phone numbers'],
  ['POST', '/api/v1/pin/verify', 'Verify staff admin PIN', '200 OK', 'Server-hashed PIN check, locked for 15m after 5 wrong tries'],
  ['POST', '/api/v1/pin/change', 'Change staff admin PIN', '200 OK', 'Requires current PIN, sets new 4-digit PIN, audited'],
  ['POST', '/api/v1/admin/access/{id}/approve', 'Approve dashboard access', '200 OK', 'Grants dashboard access to approved signup'],
  ['GET', '/api/v1/admin/messages', 'Landing page contact messages', '200 OK', 'Submissions from /contact form'],
] as const;

export function ApiDocs() {
  const { openModal, closeModal } = useDash();

  return (
    <>
      <PageHead
        title="API / Swagger Documentation"
        sub="TalkAor AI Voice Calling & Appointments Backend OpenAPI 3.0 Specification."
        right={
          <a
            href="/api/v1/openapi.json"
            target="_blank"
            rel="noreferrer"
            className="pri"
            style={{ padding: '8px 14px', borderRadius: 10, textDecoration: 'none', fontWeight: 700 }}
          >
            Open raw OpenAPI JSON
          </a>
        }
      />
      <div className="card">
        <div style={{ marginBottom: 16 }}>
          <p className="mut" style={{ margin: 0 }}>
            Base URL: <code className="mono">/api/v1</code> · Specification: <code className="mono">OpenAPI 3.0.3</code>
          </p>
        </div>
        <div style={{ display: 'grid', gap: 10 }}>
          {EP.map((e) => (
            <button
              key={e[0] + e[1]}
              style={{ display: 'flex', gap: 12, alignItems: 'center', textAlign: 'left', padding: '12px 16px' }}
              onClick={() =>
                openModal(
                  <Dialog title={e[2]} actions={<button onClick={closeModal}>Close</button>}>
                    <p className="mono" style={{ margin: 0, wordBreak: 'break-all' }}>
                      <span className={`meth ${e[0]}`}>{e[0]}</span> {e[1]}
                    </p>
                    <p className="mut" style={{ margin: '8px 0' }}>{e[4]}</p>
                    <div style={{ display: 'grid', gap: 4 }}>
                      <small className="mono">Expected Response: {e[3]}</small>
                      <pre className="mono note" style={{ margin: 0, overflowX: 'auto' }}>
                        {JSON.stringify({ ok: true, data: { status: 'success', timestamp: new Date().toISOString() } }, null, 2)}
                      </pre>
                    </div>
                  </Dialog>
                )
              }
            >
              <span className={`meth ${e[0]}`}>{e[0]}</span>
              <span className="mono" style={{ flex: 1, wordBreak: 'break-all' }}>{e[1]}</span>
              <span className="mut">{e[2]}</span>
            </button>
          ))}
        </div>
      </div>
    </>
  );
}

export function LogsView() {
  const { s } = useDash();
  const F = ['All', 'info', 'warn', 'error'] as const;
  const [f, setF] = useState<(typeof F)[number]>('All');
  const list = s.logs.filter((l) => f === 'All' || l.level === f);
  return (
    <>
      <PageHead title="Logs" sub="Platform events and audit trail." />
      <Chips options={F} value={f} onChange={setF} />
      <div className="card" style={{ overflow: 'auto' }}>
        <table>
          <tbody>
            {list.map((l, i) => (
              <tr key={i}>
                <td className="mono" style={{ whiteSpace: 'nowrap' }}>{l.at}</td>
                <td><span className={`st ${l.level === 'error' ? 'cancelled' : l.level === 'warn' ? 'rescheduled' : 'completed'}`}>{l.level}</span></td>
                <td>{l.text}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
