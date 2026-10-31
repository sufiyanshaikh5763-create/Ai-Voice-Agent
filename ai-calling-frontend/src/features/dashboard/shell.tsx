'use client';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useRef, type ReactNode } from 'react';
import { useDash } from './store';
import { Dialog, ModalHost } from './ui';
import { BotMark, Icon } from './icons';
import { ApptForm } from './appointments';
import { ConfirmLogoutDialog, PinDialog } from './views-tenant';
import { TENANT_ID } from './util';
import type { Role } from './types';

const IDLE_WARNING_MS = 28 * 60 * 1000;
const IDLE_LOGOUT_MS = 30 * 60 * 1000;
const STAFF_ADMIN_IDLE_MS = 15 * 60 * 1000;
const isDemoMode = process.env.NEXT_PUBLIC_API_MODE === 'mock';

function IdleLogoutDialog({ onStay }: { onStay: () => void }) {
  const { logout } = useDash();
  return (
    <Dialog
      title="Still there?"
      actions={
        <>
          <button onClick={onStay}>Stay signed in</button>
          <button className="dng" onClick={() => void logout()}>Log out</button>
        </>
      }
    >
      <p className="mut">You will be signed out in 2 minutes due to inactivity.</p>
    </Dialog>
  );
}

export function DashboardShell({ children }: { children: ReactNode }) {
  const { s, isSA, can, setRole, setTheme, openModal, closeModal, set, toast, logout } = useDash();
  const path = usePathname();
  const router = useRouter();
  const lastActivityRef = useRef(Date.now());
  const idleWarningOpenRef = useRef(false);
  const onPlatform = path.startsWith('/dashboard/platform');

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    const schedule = () => {
      clearTimeout(timer);
      const idleFor = Date.now() - lastActivityRef.current;
      if (idleFor >= IDLE_LOGOUT_MS) {
        void logout();
        return;
      }
      if (s.role === 'staff' && s.elevated && idleFor >= STAFF_ADMIN_IDLE_MS) {
        set((prev) => ({ ...prev, elevated: false }));
        toast('Admin session expired due to inactivity');
      }
      if (idleFor >= IDLE_WARNING_MS && !idleWarningOpenRef.current) {
        idleWarningOpenRef.current = true;
        openModal(<IdleLogoutDialog onStay={() => window.dispatchEvent(new Event('tk-activity'))} />);
      }
      const nextAt = Math.min(
        idleFor < IDLE_WARNING_MS ? IDLE_WARNING_MS : IDLE_LOGOUT_MS,
        s.role === 'staff' && s.elevated && idleFor < STAFF_ADMIN_IDLE_MS ? STAFF_ADMIN_IDLE_MS : IDLE_LOGOUT_MS
      );
      timer = setTimeout(schedule, Math.max(1, nextAt - idleFor));
    };
    const handleActivity = () => {
      lastActivityRef.current = Date.now();
      if (idleWarningOpenRef.current) {
        idleWarningOpenRef.current = false;
        closeModal();
      }
      schedule();
    };
    window.addEventListener('mousemove', handleActivity);
    window.addEventListener('pointerdown', handleActivity);
    window.addEventListener('keydown', handleActivity);
    window.addEventListener('tk-activity', handleActivity);
    schedule();
    return () => {
      clearTimeout(timer);
      window.removeEventListener('mousemove', handleActivity);
      window.removeEventListener('pointerdown', handleActivity);
      window.removeEventListener('keydown', handleActivity);
      window.removeEventListener('tk-activity', handleActivity);
    };
  }, [s.role, s.elevated, closeModal, openModal, set, toast, logout]);

  useEffect(() => {
    if (isSA && !onPlatform) router.replace('/dashboard/platform');
    if (!isSA && onPlatform) router.replace('/dashboard');
  }, [isSA, onPlatform, router]);

  const mine = s.agents.filter((a) => a.business_id === TENANT_ID);
  const tenant: [string, string, string, string][] = [
    ['/dashboard', 'Dashboard', 'grid', ''],
    ['/dashboard/appointments', 'Appointments', 'cal', String(s.appts.length)],
    ['/dashboard/customers', 'Customers', 'users', String(new Set(s.appts.map((a) => a.customer_id)).size)],
    ['/dashboard/calls', 'Voice Calls', 'phone', 'Live'],
    ['/dashboard/cancellations', 'Cancellations', 'x', String(s.appts.filter((a) => a.status === 'cancelled').length)],
    ['/dashboard/agents', 'AI Voice Agents', 'bot', `${mine.filter((a) => a.online).length} active`],
    ['/dashboard/business', 'Business Profile', 'biz', 'IST'],
    ['/dashboard/admin', 'Admin Control', 'lock', can ? 'ACTIVE' : 'PIN'],
  ];

  const platform: [string, string, string, string][] = [
    ['/dashboard/platform', 'Platform overview', 'pulse', ''],
    ['/dashboard/platform/access', 'Access control', 'shield', `${s.requests.length} pending`],
    ['/dashboard/platform/businesses', 'Businesses & plans', 'coin', String(s.businesses.length)],
    ['/dashboard/platform/agents', 'AI agents (all)', 'bot', `${s.agents.filter((a) => a.online).length} on`],
    ['/dashboard/platform/messages', 'Messages', 'mail', `${s.messages.filter((m) => !m.read).length} new`],
    ['/dashboard/platform/api', 'API / Swagger', 'code', ''],
    ['/dashboard/platform/logs', 'Logs', 'list', ''],
    ['/dashboard/platform/monitoring', 'Monitoring', 'pulse', ''],
    ['/dashboard/platform/webhook-events', 'Webhook events', 'list', ''],
    ['/dashboard/platform/tool-calls', 'Tool calls', 'code', ''],
    ['/dashboard/platform/appointments', 'All appointments', 'cal', ''],
  ];

  const items = isSA ? platform : tenant;
  const active = (h: string) => (h === '/dashboard' || h === '/dashboard/platform' ? path === h : path.startsWith(h));

  const pick = (r: Role) => {
    const userMap: Record<Role, { id: string; name: string; email: string; businessName: string }> = {
      staff: {
        id: 'u_staff',
        name: 'Meera Kulkarni',
        email: 'meera@sunrisedental.in',
        businessName: 'Sunrise Dental Care',
      },
      admin: {
        id: 'u_admin',
        name: 'Dr. Anil Rao',
        email: 'dr.anil@sunrisedental.in',
        businessName: 'Sunrise Dental Care',
      },
      super_admin: {
        id: 'u_superadmin',
        name: 'Platform Owner',
        email: 'superadmin@talkaor.com',
        businessName: 'All Businesses',
      },
    };
    const target = userMap[r];
    setRole(r);
    set((p) => ({
      ...p,
      role: r,
      elevated: false,
      user: {
        ...target,
        role: r,
      },
    }));
    document.cookie = `tk_role=${r}; path=/; max-age=86400`;
    document.cookie = `tk_session_user=${target.id}; path=/; max-age=86400`;
    toast(`Switched to ${r === 'staff' ? 'Staff View (read-only)' : r === 'admin' ? 'Admin View (business owner)' : 'Super Admin (platform owner)'}`);
    router.push(r === 'super_admin' ? '/dashboard/platform' : '/dashboard');
  };

  const ROLES: [Role, string][] = [
    ['staff', 'Staff View'],
    ['admin', 'Admin View'],
    ['super_admin', 'Super Admin'],
  ];

  if (!isSA && onPlatform) {
    return <div className="tk-dash" data-theme={s.theme}><section className="card">Super Admin access is required to view this page.</section></div>;
  }

  return (
    <div className="tk-dash" data-theme={s.theme}>
      <div className="app">
        <aside aria-label="Dashboard menu">
          <div className="logo">
            <BotMark size={34} />
            talkaor
          </div>
          <div className="sec">{isSA ? 'Platform super admin' : 'Tenant operations'}</div>

          {isDemoMode && <div style={{ padding: '0 8px 8px' }}>
            <div
              style={{
                display: 'flex',
                gap: 4,
                padding: 4,
                background: 'rgba(0,0,0,0.18)',
                borderRadius: 12,
                fontSize: 11,
              }}
            >
              <button
                type="button"
                onClick={() => pick('staff')}
                title="Staff View: Read-only access"
                style={{
                  flex: 1,
                  padding: '5px 2px',
                  borderRadius: 8,
                  fontSize: 11,
                  border: 0,
                  background: s.role === 'staff' ? 'var(--blue)' : 'transparent',
                  color: s.role === 'staff' ? '#fff' : 'inherit',
                  fontWeight: s.role === 'staff' ? 700 : 500,
                }}
              >
                Staff
              </button>
              <button
                type="button"
                onClick={() => pick('admin')}
                title="Admin View: Business owner full control"
                style={{
                  flex: 1,
                  padding: '5px 2px',
                  borderRadius: 8,
                  fontSize: 11,
                  border: 0,
                  background: s.role === 'admin' ? 'var(--blue)' : 'transparent',
                  color: s.role === 'admin' ? '#fff' : 'inherit',
                  fontWeight: s.role === 'admin' ? 700 : 500,
                }}
              >
                Admin
              </button>
              <button
                type="button"
                onClick={() => pick('super_admin')}
                title="Super Admin: Platform owner view"
                style={{
                  flex: 1,
                  padding: '5px 2px',
                  borderRadius: 8,
                  fontSize: 11,
                  border: 0,
                  background: s.role === 'super_admin' ? 'var(--blue)' : 'transparent',
                  color: s.role === 'super_admin' ? '#fff' : 'inherit',
                  fontWeight: s.role === 'super_admin' ? 700 : 500,
                }}
              >
                Super
              </button>
            </div>}
          </div>

          <nav style={{ display: 'grid', gap: 6 }}>
            {items.map(([href, label, icon, badge]) => (
              <Link
                key={href}
                href={href}
                className={`nav ${active(href) ? 'on' : ''}`}
                aria-current={active(href) ? 'page' : undefined}
              >
                <span className="nl">
                  <Icon name={icon} />
                  {label}
                </span>
                {badge && <span className="badge">{badge}</span>}
              </Link>
            ))}
          </nav>
          <button className="nav" onClick={() => openModal(<ConfirmLogoutDialog />)}>
            <span className="nl"><Icon name="logout" />Log out</span>
          </button>
          <div className="scope">
            <small>Current scope</small>
            <b>{isSA ? 'All businesses' : s.user?.businessName || 'Sunrise Dental Care'}</b>
            <small>Build v2.4</small>
          </div>
        </aside>
        <main>
          <div className="top">
            {isDemoMode && <div className="seg" role="group" aria-label="Demo role switcher">
              <span className="sim" style={{ fontWeight: 600, color: 'var(--blue)' }}>
                Demo Role:
              </span>
              {ROLES.map(([r, l]) => (
                <button
                  key={r}
                  type="button"
                  className={s.role === r ? 'on' : ''}
                  onClick={() => pick(r)}
                  style={{ fontWeight: s.role === r ? 700 : 500 }}
                >
                  {l}
                </button>
              ))}
            </div>}

            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              {s.role === 'staff' && s.elevated && (
                <>
                  <span className="st">Admin session</span>
                  <button type="button" onClick={() => set((p) => ({ ...p, elevated: false }))}>
                    End session
                  </button>
                </>
              )}
              {s.role === 'staff' && !s.elevated && (
                <button type="button" onClick={() => openModal(<PinDialog />)}>
                  Admin PIN
                </button>
              )}
              <div className="seg" role="group" aria-label="Theme">
                <button
                  type="button"
                  className={s.theme === 'dark' ? 'on' : ''}
                  onClick={() => setTheme('dark')}
                  aria-label="Dark mode"
                  title="Dark mode"
                >
                  <Icon name="moon" />
                </button>
                <button
                  type="button"
                  className={s.theme === 'light' ? 'on' : ''}
                  onClick={() => setTheme('light')}
                  aria-label="Light mode"
                  title="Light mode"
                >
                  <Icon name="sun" />
                </button>
              </div>
              {!isSA && can && (
                <button type="button" className="pri" onClick={() => openModal(<ApptForm />)}>
                  Book slot
                </button>
              )}
            </div>
          </div>
          {children}
        </main>
      </div>
      <ModalHost />
    </div>
  );
}
