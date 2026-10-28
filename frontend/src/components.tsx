import { useEffect, useRef, type ReactNode } from 'react';
import { GitPullRequest, CheckCheck, X } from 'lucide-react';
import type { Decision, Outcome } from './types';
const outcomeLabels: Record<Outcome, string> = {
  READY: 'Ready for sign-off',
  REVIEW: 'Needs review',
  BLOCKED: 'Blocked',
};
export function Mark({ small = false }: { small?: boolean }) {
  return (
    <span className={`brand-mark ${small ? 'small' : ''}`}>
      <svg viewBox="0 0 32 32" fill="none" aria-hidden="true">
        <path
          d="M8 8v7a6 6 0 0 0 6 6h9M17 8h7v7M23 9 9 23"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </span>
  );
}
export function Badge({
  outcome,
  resolved,
}: {
  outcome: Outcome;
  resolved?: Decision['resolution'];
}) {
  if (resolved)
    return (
      <span className={`badge ${resolved === 'approve' ? 'approved' : 'rejected'}`}>
        {resolved === 'approve' ? <CheckCheck size={12} /> : <X size={12} />}{' '}
        {resolved === 'approve' ? 'Approved' : 'Rejected'}
      </span>
    );
  return (
    <span className={`badge ${outcome.toLowerCase()}`}>
      <span className="badge-dot" />
      {outcomeLabels[outcome]}
    </span>
  );
}
export function ModalFrame({
  title,
  subtitle,
  children,
  onClose,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const before = document.activeElement as HTMLElement | null;
    const panel = ref.current!;
    const focusable = () =>
      Array.from(
        panel.querySelectorAll<HTMLElement>(
          'button:not(:disabled), input, textarea, select, a[href]',
        ),
      );
    (panel.querySelector<HTMLElement>('input,textarea,select') || focusable()[0])?.focus();
    const key = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
      if (e.key === 'Tab') {
        const items = focusable(),
          first = items[0],
          last = items.at(-1);
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last?.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first?.focus();
        }
      }
    };
    document.addEventListener('keydown', key);
    return () => {
      document.removeEventListener('keydown', key);
      before?.focus();
    };
  }, [onClose]);
  return (
    <div
      className="modal-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title"
        ref={ref}
      >
        <button className="icon-button modal-close" aria-label="Close dialog" onClick={onClose}>
          <X size={19} />
        </button>
        <div className="modal-emblem">
          <GitPullRequest size={22} />
        </div>
        <h2 id="modal-title">{title}</h2>
        {subtitle && <p className="modal-subtitle">{subtitle}</p>}
        {children}
      </div>
    </div>
  );
}

export function Metric({
  label,
  value,
  caption,
  icon,
  color,
}: {
  label: string;
  value: number | string;
  caption: string;
  icon: ReactNode;
  color: string;
}) {
  return (
    <article className="metric">
      <div className="metric-top">
        <span>{label}</span>
        <span className={`metric-icon ${color}`}>{icon}</span>
      </div>
      <strong>{value}</strong>
      <p>{caption}</p>
    </article>
  );
}
