'use client';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { useDash } from './store';
import { BotMark, Icon } from './icons';
import { CalendarCard, DayRoster } from './calendar';
import { ApptForm } from './appointments';
import { Chips, CopyButton, Dialog, Meter, PageHead, Player, Status, Toggle } from './ui';
import { ACTIVE_STATUSES, DAYS, TENANT_ID, TODAY, WEEKLY, fmtDur, initials } from './util';
import type { Call } from './types';
import { fetchBillingMe, toggleAgentPower, updateBusinessSettings, fetchCallDetails } from './api';

export function ConfirmLogoutDialog() {
  const { closeModal, logout } = useDash();

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Enter') {
        event.preventDefault();
        void logout();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [logout]);

  return (
    <Dialog
      title="Log out of TalkAor?"
      actions={
        <>
          <button onClick={closeModal}>Stay signed in</button>
          <button className="dng" onClick={() => void logout()}>Log out</button>
        </>
      }
    >
      <p className="mut">You will need to sign in again. Any admin session will end.</p>
    </Dialog>
  );
}

export function PinDialog() {
  const { tryPin, closeModal, toast } = useDash();
  const [v, setV] = useState('');
  const [msg, setMsg] = useState('');
  const [busy, setBusy] = useState(false);

  const go = async () => {
    if (busy) return;
    setBusy(true);
    setMsg('');
    try {
      const r = await tryPin(v);
      if (r.ok) {
        closeModal();
        toast('Admin session started');
      } else {
        setMsg(r.msg ?? 'Incorrect PIN');
        setV('');
      }
    } catch (err: any) {
      setMsg(err.message || 'Error verifying PIN');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      title="Enter admin PIN"
      actions={
        <>
          <button onClick={closeModal}>Cancel</button>
          <button className="pri" disabled={busy || v.length < 4} onClick={go}>
            {busy ? 'Verifying…' : 'Unlock'}
          </button>
        </>
      }
    >
      <p className="mut" style={{ margin: 0 }}>Ask your business owner for the 4-digit PIN.</p>
      <input
        className="mono"
        type="password"
        inputMode="numeric"
        maxLength={4}
        autoComplete="off"
        aria-label="4-digit PIN"
        value={v}
        autoFocus
        onChange={(e) => setV(e.target.value.replace(/\D/g, ''))}
        onKeyDown={(e) => {
          if (e.key === 'Enter') go();
        }}
        style={{ fontSize: 26, letterSpacing: 12, textAlign: 'center' }}
      />
      <small role="alert" style={{ color: 'var(--bad)', minHeight: 18, display: 'block' }}>{msg}</small>
    </Dialog>
  );
}

export function PlanCard() {
  const [billing, setBilling] = useState<Awaited<ReturnType<typeof fetchBillingMe>> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError('');
    fetchBillingMe()
      .then((result) => { if (active) setBilling(result); })
      .catch((cause: unknown) => { if (active) setError(cause instanceof Error ? cause.message : 'Unable to load billing details.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [retry]);

  if (loading) return <div className="card" role="status">Loading plan and minutes…</div>;
  if (error || !billing) {
    return <div className="card" role="alert"><h3>Your plan</h3><p>{error || 'Billing details are unavailable.'}</p><button onClick={() => setRetry((value) => value + 1)}>Retry</button></div>;
  }

  const atLimit = billing.alert === 'limit' || billing.usage_percent >= 100;
  const warning = !atLimit && (billing.alert === 'warning' || billing.usage_percent >= 80);
  const color = atLimit ? 'var(--bad)' : warning ? 'var(--warn)' : 'var(--blue)';
  const renewalDate = billing.renews_on.slice(0, 10);
  return (
    <div className="card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h3>Your plan</h3>
        <span className="st">{billing.plan}</span>
      </div>
      <p className="mut" style={{ margin: '4px 0' }}>{billing.plan} plan, billed {billing.billing_cycle}</p>
      <Meter used={billing.minutes_used} limit={billing.minutes_limit} percent={billing.usage_percent} color={color} />
      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
        <span className="mono">{billing.minutes_remaining} of {billing.minutes_limit} minutes left</span>
        <span className="mono">{billing.usage_percent}% used</span>
      </div>
      {atLimit && <p role="status" style={{ color: 'var(--bad)', margin: '8px 0 0' }}>Usage limit reached.</p>}
      {warning && <p role="status" style={{ color: 'var(--warn)', margin: '8px 0 0' }}>Usage is at the warning level.</p>}
      <p style={{ margin: '10px 0 6px' }}><b>Next renewal:</b> <span className="mono">{renewalDate}</span></p>
      <p className="mut" style={{ margin: 0 }}>Each call is rounded up to a whole minute.</p>
    </div>
  );
}

export function DashboardHome() {
  const { s, can, openModal } = useDash();
  const A = s.appts, tod = A.filter((a) => a.date === TODAY), done = tod.filter((a) => a.status === 'completed').length;
  const active = A.filter((a) => ACTIVE_STATUSES.includes(a.status)).length;
  const agents = s.agents.filter((a) => a.business_id === TENANT_ID), on = agents.filter((a) => a.online).length;
  const first = s.calls.find((c) => c.has_recording);

  const name = s.user?.name || (s.role === 'admin' ? 'Dr. Anil Rao' : s.role === 'staff' ? 'Meera Kulkarni' : 'Platform Owner');
  const title = s.role === 'admin' ? 'Business owner' : s.role === 'staff' ? 'Staff member' : 'Super admin';

  const kpis = [
    { t: "Today's appointments", v: String(tod.length), i: 'cal', n: `${done} completed · ${tod.length - done} pending`, k: 'k1' },
    { t: 'Total calls handled', v: '342', i: 'phone', n: `${s.calls.length} today · all-time total`, k: 'k2' },
    { t: 'Active AI agents', v: `${on} / ${agents.length || 1}`, i: 'bot', n: `${Math.round((on / (agents.length || 1)) * 100)}% availability`, k: 'k3' },
    { t: 'Customer records', v: '128', i: 'users', n: '+8 new this month', k: 'k4' },
  ];
  const strip = [['Total bookings', A.length, '#285CCC'], ['Completed', A.filter((a) => a.status === 'completed').length, '#2f9e75'], ['Scheduled active', active, '#F5A04A'], ['Cancelled', A.filter((a) => a.status === 'cancelled').length, '#d6486b']] as const;
  return (
    <>
      {s.role === 'staff' && !s.elevated && (
        <div className="vo" style={{ marginBottom: 16 }}><span>You have view-only access. Enter the admin PIN to make changes.</span><button className="pri" onClick={() => openModal(<PinDialog />)}>Enter admin PIN</button></div>
      )}
      <div className="dg">
        <div className="lc">
          <div className="hero">
            <div><span className="tag"><i className="pd" />AI voice concierge live</span><h1>TalkAor Operations Pulse</h1><p style={{ margin: 0 }}>Automating customer calls, calendar bookings and client enquiries 24/7.</p></div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {can && <Link className="pri" href="/dashboard/appointments" style={{ padding: '8px 14px', borderRadius: 10, fontWeight: 700 }}>Manage appointments</Link>}
              <Link className="gh" href="/dashboard/calls" style={{ padding: '8px 14px', borderRadius: 10, border: '1px solid rgba(255,255,255,.3)' }}>Recent calls</Link>
            </div>
          </div>
          <div className="k22">{kpis.map((k) => <div key={k.t} className={`card kp ${k.k}`}><span className="ic"><Icon name={k.i} /></span><small className="mut">{k.t}</small><b>{k.v}</b><small>{k.n}</small></div>)}</div>
          <div className="card strip">{strip.map((x) => <div key={x[0]} style={{ boxShadow: `inset 0 4px ${x[2]}` }}><small className="mut">{x[0]}</small><br /><b>{x[1]}</b></div>)}</div>
          <div className="card">
            <h3>Call and booking volume</h3><small className="mut">Past 7 days. Blue: calls handled. Orange: appointments booked.</small>
            <div className="bars">{WEEKLY.map((b, i) => <div key={i} style={{ flexDirection: 'column', alignItems: 'stretch', gap: 4 }}><div style={{ flex: 1 }}><i style={{ height: `${(b[0] / 9) * 100}%` }} /><i style={{ height: `${(b[1] / 9) * 100}%` }} /></div><span>{DAYS[i]}</span></div>)}</div>
          </div>
          {first && <div className="card"><h3>Latest recording</h3><p style={{ margin: '6px 0' }}><b>{first.customer_name}</b> with {first.agent_name} <span className="st">{first.outcome}</span></p><p className="mut" style={{ margin: '0 0 8px' }}>{first.summary}</p><button onClick={() => openModal(<CallDetails c={first} />)}>Open call details</button></div>}
        </div>
        <div className="rc">
          <div className="card">
            <div style={{ display: 'flex', gap: 14, alignItems: 'center', justifyContent: 'space-between' }}>
              <div style={{ display: 'flex', gap: 14, alignItems: 'center' }}><span className="av">{initials(name)}</span><div><b>{name}</b><br /><span className="st">{title}{s.elevated ? ' · admin session' : ''}</span></div></div>
              <button onClick={() => openModal(<ConfirmLogoutDialog />)} style={{ padding: '5px 9px', fontSize: 12 }}>Log out</button>
            </div>
            <div className="mini" style={{ marginTop: 14 }}><div><b>{active}</b><small>Booked</small></div><div><b>{on}</b><small>Agents</small></div><div><b>{s.calls.length}</b><small>Calls</small></div></div>
          </div>
          <CalendarCard /><DayRoster />
        </div>
      </div>
    </>
  );
}

export function CustomersView() {
  const { s, can, openModal, toast } = useDash();
  const [q, setQ] = useState('');
  const list = Array.from(new Map(s.appts.map((a) => [a.customer_id, a])).values()).filter((c) => (c.customer_name + c.customer_phone).toLowerCase().includes(q.toLowerCase()));
  return (
    <>
      <PageHead title="Customers" right={<input placeholder="Search name or phone" style={{ width: 240 }} value={q} onChange={(e) => setQ(e.target.value)} />} />
      <div className="card" style={{ overflow: 'auto' }}>
        <table><thead><tr><th>Name</th><th>Phone</th><th>Email</th><th>Visits</th><th>Last service</th><th /></tr></thead>
          <tbody>{list.map((c) => (
            <tr key={c.customer_id}><td><b>{c.customer_name}</b></td><td className="mono">{c.customer_phone}</td><td>{c.customer_email}</td>
              <td>{s.appts.filter((a) => a.customer_id === c.customer_id).length}</td><td>{c.service}</td>
              <td style={{ whiteSpace: 'nowrap' }}><button onClick={() => toast(`Calling ${c.customer_name} (demo)`)}>Call</button> <button onClick={() => toast('Opening WhatsApp (demo)')}>WhatsApp</button> {can && <button onClick={() => openModal(<ApptForm />)}>Book</button>}</td></tr>
          ))}</tbody></table>
      </div>
    </>
  );
}

function CallDetails({ c }: { c: Call }) {
  const { closeModal } = useDash();
  const [details, setDetails] = useState<Call>();
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    fetchCallDetails(c.id).then((result) => {
      if (active) setDetails(result);
    }).catch((err: unknown) => {
      if (active) setError(err instanceof Error ? err.message : 'Could not load call details.');
    });
    return () => { active = false; };
  }, [c.id]);

  return (
    <Dialog title={`Call details: ${c.customer_name}`} actions={<button onClick={closeModal}>Close</button>}>
      {!details && !error && <p className="mut">Loading call details…</p>}
      {error && <p role="alert">{error}</p>}
      {details && (
        <div style={{ display: 'grid', gap: 12 }}>
          <div className="note">
            <Status value={details.status} /> {fmtDur(details.duration_seconds)}
            {details.summary && <p>{details.summary}</p>}
          </div>
          {details.recording_url
            ? <Player duration={details.duration_seconds} url={details.recording_url} />
            : <p className="mut">{details.has_recording ? 'Recording link is unavailable.' : 'No recording is available.'}</p>}
          <div style={{ display: 'grid', gap: 8 }}>
            {(details.transcript ?? []).map((line, i) => (
              <div key={i} className="note"><b>{line.speaker}</b> <span className="mono mut">{line.time}</span><br />{line.text}</div>
            ))}
            {!details.transcript?.length && <p className="mut">No transcript is available.</p>}
          </div>
        </div>
      )}
    </Dialog>
  );
}
export function CallsView() {
  const { s, openModal } = useDash();
  const F = ['All', 'completed', 'in_progress', 'missed'] as const;
  const [f, setF] = useState<(typeof F)[number]>('All');
  const list = s.calls.filter((c) => f === 'All' || c.status === f);
  return (
    <>
      <PageHead title="Voice calls" />
      <Chips options={F} value={f} onChange={setF} />
      <div style={{ display: 'grid', gap: 12 }}>
        {list.map((c) => (
          <div className="card" key={c.id}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
              <div><b>{c.status === 'in_progress' ? 'Live: ' : ''}{c.customer_name}</b> · handled by {c.agent_name}</div>
              <div><Status value={c.status} /> {c.outcome && <span className="st">{c.outcome}</span>} <span className="mono">{fmtDur(c.duration_seconds)}</span></div>
            </div>
            <p className="mut" style={{ margin: '6px 0' }}>{c.summary}</p>
            <button style={{ marginTop: 8 }} onClick={() => openModal(<CallDetails c={c} />)}>Open call details</button>
          </div>
        ))}
        {list.length === 0 && <div className="card">No calls match this filter.</div>}
      </div>
    </>
  );
}

export function CancellationsView() {
  const { s } = useDash();
  const F = ['All', 'AI Agent', 'Human User'] as const;
  const [f, setF] = useState<(typeof F)[number]>('All');
  const src = (c?: string) => (c === 'ai_agent' ? 'AI Agent' : 'Human User');
  const list = s.appts.filter((a) => a.status === 'cancelled' && (f === 'All' || src(a.cancelled_by) === f));
  return (
    <>
      <PageHead title="Cancellations" />
      <Chips options={F} value={f} onChange={setF} />
      <div className="card" style={{ overflow: 'auto' }}>
        {list.length ? (
          <table><thead><tr><th>Customer</th><th>Slot</th><th>Service</th><th>Cancelled by</th><th>Reason</th></tr></thead>
            <tbody>{list.map((a) => <tr key={a.id}><td>{a.customer_name}</td><td className="mono">{a.date} {a.time.slice(0, 5)}</td><td>{a.service}</td><td><span className={`st ${a.cancelled_by === 'ai_agent' ? '' : 'rescheduled'}`}>{src(a.cancelled_by)}</span></td><td>{a.cancel_reason}</td></tr>)}</tbody></table>
        ) : <p>Nothing here. Cancel an appointment from the card stack and it appears in this log.</p>}
      </div>
    </>
  );
}

export function AgentsView() {
  const { s, can, openModal, closeModal, toast, actor, reload } = useDash();
  const list = s.agents.filter((a) => a.business_id === TENANT_ID);

  const click = async (id: string) => {
    if (!can) { toast('View only. Enter the admin PIN to change agents.'); return; }
    const a = list.find((x) => x.id === id)!;
    if (!a.online) {
      try {
        await toggleAgentPower(id, true, actor);
        await reload();
        toast(`Turned ${a.name} on`);
      } catch (err: any) {
        toast(err.message || 'Error toggling agent');
      }
      return;
    }
    openModal(
      <Dialog
        title={`Turn off ${a.name}?`}
        actions={
          <>
            <button className="pri" onClick={closeModal}>Keep online</button>
            <button
              className="dng"
              onClick={async () => {
                try {
                  await toggleAgentPower(id, false, actor);
                  await reload();
                  closeModal();
                  toast(`Turned ${a.name} off`);
                } catch (err: any) {
                  toast(err.message || 'Error toggling agent');
                }
              }}
            >
              Yes, turn off
            </button>
          </>
        }
      >
        <p style={{ margin: 0 }}>Calls to {a.phone} will go unanswered while {a.name} is offline.</p>
      </Dialog>
    );
  };

  return (
    <>
      <PageHead title="AI voice agents" sub="Your assigned phone number and agent availability." />
      <div className="grid4">
        {list.map((a) => (
          <div className="card" key={a.id}>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}><h3>{a.name}</h3><span className={`st ${a.online ? 'completed' : 'cancelled'}`}>{a.online ? 'Active' : 'Inactive'}</span></div>
            <p className="mut" style={{ margin: '4px 0' }}>{a.languages}</p>
            {a.phone
              ? <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', margin: '8px 0' }}><b className="mono" style={{ fontSize: 18 }}>{a.phone}</b><CopyButton value={a.phone} label="Copy number" /></div>
              : <p className="mut" style={{ margin: '8px 0' }}>Your number will be assigned by Talkaor. Contact support if this takes long.</p>}
            {a.phone && <p className="mut" style={{ margin: '0 0 8px' }}>This is the number your customers call.</p>}
            <p className="mut" style={{ margin: '0 0 12px' }}>{a.calls_today} calls today</p>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <Toggle on={a.online} label={`Power ${a.name}`} onClick={() => click(a.id)} />
            </div>
          </div>
        ))}
        {list.length === 0 && <div className="card">Your number will be assigned by Talkaor. Contact support if this takes long.</div>}
      </div>
    </>
  );
}

export function BusinessView() {
  const { s, set, can, toast, reload } = useDash();
  const [svc, setSvc] = useState('');

  const saveBiz = async () => {
    try {
      await updateBusinessSettings({ hours: s.hours, services: s.services, staff: s.staff });
      await reload();
      toast('Business profile saved');
    } catch (err: any) {
      toast(err.message || 'Error saving profile');
    }
  };

  return (
    <>
      <PageHead title="Business profile" right={can ? <button className="pri" onClick={saveBiz}>Save changes</button> : <span className="st">View only</span>} />
      <div className="cols">
        <div style={{ display: 'grid', gap: 14 }}>
          <div className="card" style={{ display: 'grid', gap: 10 }}>
            <label>Business name<input disabled={!can} defaultValue="Sunrise Dental Care" /></label>
            <label>Business type<select disabled={!can}><option>Healthcare clinic</option><option>Education</option><option>Salon or spa</option></select></label>
            <label>Timezone<select disabled={!can}><option>Asia/Kolkata (IST)</option><option>Asia/Dubai (GST)</option></select></label>
          </div>
          <div className="card">
            <h3>Services catalog</h3>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', margin: '10px 0' }}>
              {s.services.map((x) => <span key={x} className="st" style={{ padding: '6px 12px' }}>{x} <button disabled={!can} aria-label={`Remove ${x}`} style={{ padding: '0 6px', border: 0, background: 'none' }} onClick={() => set((p) => ({ ...p, services: p.services.filter((y) => y !== x) }))}>×</button></span>)}
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <input disabled={!can} placeholder="Add a service" style={{ flex: 1 }} value={svc} onChange={(e) => setSvc(e.target.value)} />
              <button disabled={!can} onClick={() => { if (svc.trim()) { set((p) => ({ ...p, services: [...p.services, svc.trim()] })); setSvc(''); } }}>Add</button>
            </div>
          </div>
        </div>
        <div className="card">
          <h3>Business hours</h3>
          <div style={{ display: 'grid', gap: 8, marginTop: 10 }}>
            {DAYS.map((d, i) => (
              <div key={d} style={{ display: 'grid', gridTemplateColumns: '44px 1fr 1fr 70px', gap: 6, alignItems: 'center' }}>
                <b>{d}</b>
                <input type="time" disabled={!can || s.hours[i].closed} value={s.hours[i].open} aria-label={`${d} opens`} onChange={(e) => set((p) => ({ ...p, hours: p.hours.map((h, j) => j === i ? { ...h, open: e.target.value } : h) }))} />
                <input type="time" disabled={!can || s.hours[i].closed} value={s.hours[i].close} aria-label={`${d} closes`} onChange={(e) => set((p) => ({ ...p, hours: p.hours.map((h, j) => j === i ? { ...h, close: e.target.value } : h) }))} />
                <button disabled={!can} onClick={() => set((p) => ({ ...p, hours: p.hours.map((h, j) => j === i ? { ...h, closed: !h.closed } : h) }))}>{s.hours[i].closed ? 'Closed' : 'Open'}</button>
              </div>
            ))}
          </div>
        </div>
      </div>
      <div className="card" style={{ marginTop: 14 }}>
        <h3>Staff availability</h3>{!can && <p className="mut" style={{ margin: '4px 0' }}>View only.</p>}
        <div style={{ overflow: 'auto' }}>
          <table><thead><tr><th />{DAYS.map((d) => <th key={d}>{d}</th>)}</tr></thead>
            <tbody>{s.staff.map((m) => (
              <tr key={m.id}><td><b>{m.name}</b><br /><small className="mut">{m.title}</small></td>
                {m.days.map((v, j) => <td key={j}><Toggle on={v} disabled={!can} label={`${m.name} ${DAYS[j]}`} onClick={() => set((p) => ({ ...p, staff: p.staff.map((x) => x.id === m.id ? { ...x, days: x.days.map((y, k) => k === j ? !y : y) } : x) }))} /></td>)}</tr>
            ))}</tbody></table>
        </div>
      </div>
    </>
  );
}

export function AdminView() {
  const { s, can, openModal, changePin, toast, set } = useDash();
  const [cur, setCur] = useState(''); const [nx, setNx] = useState(''); const [cf, setCf] = useState('');
  if (!can) {
    return (
      <div className="card" style={{ maxWidth: 440, margin: '30px auto', textAlign: 'center' }}>
        <BotMark /><h2>Admin control is locked</h2>
        <p className="mut">Staff can get admin powers with the 4-digit PIN set by the business owner.</p>
        <button className="pri" onClick={() => openModal(<PinDialog />)}>Enter admin PIN</button>
      </div>
    );
  }
  const owner = s.role === 'admin';
  const update = async () => {
    const err = await changePin(cur, nx, cf);
    if (err) toast(err);
    else {
      toast('PIN updated');
      setCur('');
      setNx('');
      setCf('');
    }
  };
  return (
    <>
      <PageHead title="Admin control" right={s.role === 'staff' ? <button onClick={() => set((p) => ({ ...p, elevated: false }))}>End admin session</button> : undefined} />
      <div className="cols">
        <div style={{ display: 'grid', gap: 14 }}>
          <div className="card" style={{ display: 'grid', gap: 10 }}>
            <h3>Staff admin PIN</h3>
            <p className="mut" style={{ margin: 0 }}>Last changed {s.pinChangedAt}. {owner ? 'Staff use this PIN to get admin powers.' : 'Only the business owner can change the PIN.'}</p>
            {owner && <>
              <label>Current PIN<input type="password" inputMode="numeric" maxLength={4} value={cur} onChange={(e) => setCur(e.target.value)} /></label>
              <label>New 4-digit PIN<input type="password" inputMode="numeric" maxLength={4} value={nx} onChange={(e) => setNx(e.target.value)} /></label>
              <label>Confirm new PIN<input type="password" inputMode="numeric" maxLength={4} value={cf} onChange={(e) => setCf(e.target.value)} /></label>
              <div><button className="pri" onClick={update}>Update PIN</button></div>
            </>}
          </div>
          <div className="card"><h3>Audit log</h3><div className="tl" style={{ marginTop: 10 }}>{s.logs.slice(0, 5).map((l, i) => <div key={i}>{l.text}<br /><small className="mut">{l.at}</small></div>)}</div></div>
        </div>
        <div style={{ display: 'grid', gap: 14, alignContent: 'start' }}>
          <PlanCard />
        </div>
      </div>
    </>
  );
}
