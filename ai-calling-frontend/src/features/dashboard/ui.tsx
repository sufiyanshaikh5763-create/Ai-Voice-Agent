'use client';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { useDash } from './store';
import { fmtDur, statusClass } from './util';

export function ModalHost() {
  const { modal, closeModal, toasts } = useDash();
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!modal) return;
    ref.current?.focus();
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape') closeModal(); };
    window.addEventListener('keydown', h); return () => window.removeEventListener('keydown', h);
  }, [modal, closeModal]);
  return (
    <>
      {modal && (
        <div className="ov" onMouseDown={(e) => { if (e.target === e.currentTarget) closeModal(); }}>
          <div className="md" role="dialog" aria-modal="true" tabIndex={-1} ref={ref}>{modal}</div>
        </div>
      )}
      {toasts.map((t) => <div key={t.id} className="toast" role="status">{t.text}</div>)}
    </>
  );
}
export const Status = ({ value, label }: { value: string; label?: string }) => <span className={`st ${statusClass(value)}`}>{label ?? value.replace('_', ' ')}</span>;
export const PageHead = ({ title, sub, right }: { title: string; sub?: string; right?: ReactNode }) => (
  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap', margin: '6px 0 14px' }}>
    <div><h2>{title}</h2>{sub && <p className="mut" style={{ margin: '4px 0 0' }}>{sub}</p>}</div>{right}
  </div>
);
export function Chips<T extends string>({ options, value, onChange }: { options: readonly T[]; value: T; onChange: (v: T) => void }) {
  return <div className="seg" style={{ marginBottom: 12, flexWrap: 'wrap' }}>{options.map((o) => <button key={o} className={value === o ? 'on' : ''} onClick={() => onChange(o)}>{o.replace('_', ' ')}</button>)}</div>;
}
export const Toggle = ({ on, onClick, label, disabled }: { on: boolean; onClick: () => void; label: string; disabled?: boolean }) => (
  <button className={`tog ${on ? 'on' : ''}`} role="switch" aria-checked={on} aria-label={label} disabled={disabled} onClick={onClick}><i /></button>
);
export const Meter = ({ used, limit, percent, color }: { used: number; limit: number; percent?: number; color?: string }) => (
  <div className="meter"><i style={{ width: `${Math.min(100, Math.max(0, Math.round(percent ?? (used / limit) * 100)))}%`, background: color }} /></div>
);
export function CopyButton({ value, label = 'Copy' }: { value: string; label?: string }) {
  const { toast } = useDash();
  return (
    <button
      type="button"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(value);
          toast('Copied to clipboard');
        } catch {
          toast('Unable to copy to clipboard');
        }
      }}
    >
      {label}
    </button>
  );
}
export function Dialog({ title, children, actions }: { title: string; children?: ReactNode; actions?: ReactNode }) {
  return <><h3>{title}</h3>{children}<div className="acts">{actions}</div></>;
}
// Real audio player using HTML <audio>
export function Player({ duration, url }: { duration: number; url?: string }) {
  const { toast } = useDash();
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const [curTime, setCurTime] = useState(0);
  const audioSrc = url || 'https://actions.google.com/sounds/v1/ambiences/coffee_shop.ogg';

  const toggle = () => {
    if (!audioRef.current) return;
    if (playing) {
      audioRef.current.pause();
      setPlaying(false);
    } else {
      audioRef.current.play().catch(() => toast('Playback error'));
      setPlaying(true);
    }
  };

  const onTimeUpdate = () => {
    if (audioRef.current) {
      setCurTime(audioRef.current.currentTime);
    }
  };

  const onSeek = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = Number(e.target.value);
    setCurTime(val);
    if (audioRef.current) {
      audioRef.current.currentTime = val;
    }
  };

  const onEnded = () => {
    setPlaying(false);
    setCurTime(0);
  };

  const total = duration || (audioRef.current?.duration ? Math.round(audioRef.current.duration) : 60);

  return (
    <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
      <audio
        ref={audioRef}
        src={audioSrc}
        onTimeUpdate={onTimeUpdate}
        onEnded={onEnded}
        preload="metadata"
      />
      <button onClick={toggle} aria-label={playing ? 'Pause audio' : 'Play audio'}>
        {playing ? 'Pause' : 'Play'}
      </button>
      <input
        type="range"
        min={0}
        max={total}
        step={0.5}
        value={curTime}
        onChange={onSeek}
        style={{ flex: 1 }}
        aria-label="Seek recording"
      />
      <span className="mono">
        {fmtDur(Math.round(curTime))} / {fmtDur(total)}
      </span>
      <a
        href={audioSrc}
        download="call-recording.ogg"
        target="_blank"
        rel="noreferrer"
        className="button"
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          padding: '8px 14px',
          borderRadius: 10,
          background: 'var(--surf)',
          color: 'var(--navy)',
          border: '1px solid var(--line)',
          fontSize: 13,
          textDecoration: 'none',
        }}
      >
        Download
      </a>
    </div>
  );
}
