import {
  Activity,
  ArrowUpRight,
  Check,
  CheckCheck,
  CheckCircle2,
  Code2,
  ExternalLink,
  FileCode2,
  GitBranch,
  GitCommitHorizontal,
  GitPullRequest,
  Loader2,
  ShieldCheck,
  TriangleAlert,
  X,
  XCircle,
} from 'lucide-react';
import { useState } from 'react';
import { Badge } from './components';
import LLMAuditPanel from './LLMAuditPanel';
import { relativeTime, type Decision, type Session } from './types';
const findingLabels: Record<string, string> = {
  sensitive_paths: 'Sensitive files changed',
  test_gap: 'Test updates need a closer look',
  test_removal: 'Tests were removed',
  source_rename: 'Source files were renamed',
  required_ci: 'Required checks have not passed',
  secret_material: 'Possible credentials detected',
  risky_operation: 'Potentially risky operation',
  large_change: 'Large change set',
  missing_patch: 'Some changes could not be inspected',
  mergeability: 'Mergeability is not confirmed',
  not_ready: 'Pull request is not ready',
  incomplete_files: 'Incomplete change evidence',
  low_risk: 'No configured risk signals found',
};

type Props = {
  token: string;
  onAuditComplete: () => void;
  active: Decision | null;
  selectedRow?: Decision;
  session: Session | null;
  tab: string;
  setTab: (tab: string) => void;
  busy: boolean;
  expired: boolean;
  canResolve: boolean;
  canPublish: boolean;
  navigate: (view: 'policy') => void;
  onDecision: (action: 'approve' | 'reject' | 'publish') => void;
};
export default function ReviewPanel({
  token,
  onAuditComplete,
  active,
  selectedRow,
  session,
  tab,
  setTab,
  busy,
  expired,
  canResolve,
  canPublish,
  navigate,
  onDecision,
}: Props) {
  const [acknowledgedAudit, setAcknowledgedAudit] = useState('');
  const auditReady =
    !session?.llm_audit_enabled ||
    (active?.llm_audit?.state === 'completed' && acknowledgedAudit === active.llm_audit.id);
  return (
    <div className="review-detail">
      {active ? (
        <>
          {active.is_current === false && (
            <div className="policy-note" role="status">
              Historical recommendation: a newer review owns the current decision. This record
              remains available for audit.
            </div>
          )}
          <div className="detail-heading">
            <div className="detail-repo">
              <GitPullRequest size={15} />
              {active.repository}
              <span>/</span>
              <strong>#{active.number}</strong>
            </div>
            <div className="detail-title-line">
              <h2>{active.evidence.title || `Pull request #${active.number}`}</h2>
              <Badge outcome={active.recommendation.outcome} resolved={active.resolution} />
            </div>
            <div className="detail-meta">
              <span className={`mini-avatar avatar-${active.author.length % 4}`}>
                {active.author.slice(0, 1).toUpperCase()}
              </span>
              <strong>{active.author}</strong>
              <span>requested a review</span>
              <span className="meta-dot">·</span>
              <span>{relativeTime(active.created_at)}</span>
            </div>
            <div className="commit-strip">
              <GitBranch size={13} />
              <span>{active.repository.split('/').at(-1)}</span>
              <span className="commit-divider" />
              <GitCommitHorizontal size={15} />
              <code>{active.head_sha.slice(0, 7)}</code>
              <span className="commit-pin">
                <ShieldCheck size={12} />
                Commit-pinned evidence
              </span>
            </div>
          </div>
          <div className="detail-tabs" role="tablist" aria-label="Review evidence">
            {[
              ['overview', 'Overview'],
              ['files', `Files changed (${active.evidence.files.length})`],
              ['checks', `Checks (${active.evidence.checks.length})`],
              ['llm', 'LLM audit'],
              ['activity', 'Activity'],
            ].map(([key, label]) => (
              <button
                role="tab"
                aria-selected={tab === key}
                id={`tab-${key}`}
                aria-controls="evidence-panel"
                key={key}
                className={tab === key ? 'active' : ''}
                onClick={() => setTab(key)}
              >
                {label}
              </button>
            ))}
          </div>
          <div
            className="detail-content"
            role="tabpanel"
            id="evidence-panel"
            aria-labelledby={`tab-${tab}`}
          >
            {tab === 'llm' && (
              <LLMAuditPanel
                key={`${active.id}-${token}`}
                decision={active}
                enabled={!!session?.llm_audit_enabled}
                token={token}
                canRun={!!canResolve && !expired && active.recommendation.outcome !== 'BLOCKED'}
                onComplete={onAuditComplete}
                acknowledged={acknowledgedAudit === active.llm_audit?.id}
                onAcknowledge={(checked) =>
                  setAcknowledgedAudit(checked ? active.llm_audit?.id || '' : '')
                }
              />
            )}
            {tab === 'overview' && (
              <>
                <div className={`recommendation ${active.recommendation.outcome.toLowerCase()}`}>
                  <div className="recommendation-symbol">
                    {active.recommendation.outcome === 'READY' ? (
                      <CheckCircle2 size={22} />
                    ) : active.recommendation.outcome === 'BLOCKED' ? (
                      <XCircle size={22} />
                    ) : (
                      <ShieldCheck size={22} />
                    )}
                  </div>
                  <div>
                    <div className="tiny-label">AGENT RECOMMENDATION</div>
                    <h3>
                      {active.recommendation.outcome === 'REVIEW'
                        ? 'A human review makes the difference.'
                        : active.recommendation.outcome === 'READY'
                          ? 'Ready for your final sign-off.'
                          : 'Let’s resolve the blockers first.'}
                    </h3>
                    <p>
                      {active.recommendation.outcome === 'REVIEW'
                        ? 'The required checks passed, but this change touches areas that deserve a closer look.'
                        : active.recommendation.outcome === 'READY'
                          ? 'This change meets the configured policy. A named reviewer still owns the final decision.'
                          : 'Required conditions have not been met. Approval stays unavailable until the evidence is refreshed.'}
                    </p>
                  </div>
                </div>
                <div className="evidence-summary">
                  <span>
                    <CheckCircle2 size={14} />
                    <strong>
                      {
                        active.evidence.checks.filter(
                          (c) => c.conclusion === 'success' && c.head_sha === active.head_sha,
                        ).length
                      }
                      /{active.evidence.checks.length}
                    </strong>{' '}
                    checks passed
                  </span>
                  <span>
                    <FileCode2 size={14} />
                    <strong>{active.recommendation.changed_files}</strong> changed files
                  </span>
                  <span>
                    <Code2 size={14} />
                    <strong>{active.recommendation.changed_lines}</strong> changed lines
                  </span>
                </div>
                <div className="content-heading">
                  <h3>Why this recommendation?</h3>
                  <span>
                    {active.recommendation.findings.length}{' '}
                    {active.recommendation.findings.length === 1 ? 'finding' : 'findings'}
                  </span>
                </div>
                <div className="findings">
                  {active.recommendation.findings.map((f, index) => (
                    <div key={`${f.code}-${index}`} className={`finding ${f.severity}`}>
                      <span className="finding-icon">
                        {f.severity === 'info' ? (
                          <Check size={15} />
                        ) : f.severity === 'block' ? (
                          <XCircle size={15} />
                        ) : (
                          <TriangleAlert size={15} />
                        )}
                      </span>
                      <div>
                        <h4>{findingLabels[f.code] || f.code.replaceAll('_', ' ')}</h4>
                        <p>{f.message}</p>
                        {f.paths.length > 0 && (
                          <div className="file-chips">
                            {f.paths.map((path) => (
                              <button key={path} onClick={() => setTab('files')}>
                                <FileCode2 size={11} />
                                {path}
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                      <span className={`severity-label ${f.severity}`}>
                        {f.severity === 'block'
                          ? 'Blocker'
                          : f.severity === 'review'
                            ? 'Review'
                            : 'Passed'}
                      </span>
                    </div>
                  ))}
                </div>
                <div className="policy-note">
                  <ShieldCheck size={15} />
                  <span>
                    Evaluated with policy <code>{active.recommendation.policy_version}</code>.
                    Evidence is refreshed before approval.
                  </span>
                  <button aria-label="View review policy" onClick={() => navigate('policy')}>
                    <ArrowUpRight size={15} />
                  </button>
                </div>
              </>
            )}
            {tab === 'files' && (
              <>
                <div className="content-heading">
                  <h3>Changed files</h3>
                  <span>Metadata from the inspected commit</span>
                </div>
                <p className="pane-caption">
                  Source patches are inspected during evaluation and are not saved to the review
                  record.
                </p>
                <div className="file-list">
                  {active.evidence.files.map((f) => (
                    <div className="file-row" key={f.filename}>
                      <FileCode2 size={18} />
                      <div>
                        <code>{f.filename}</code>
                        <small>
                          {f.previous_filename ? `Renamed from ${f.previous_filename}` : f.status}
                        </small>
                      </div>
                      <span className="additions">+{f.additions}</span>
                      <span className="deletions">−{f.deletions}</span>
                    </div>
                  ))}
                </div>
              </>
            )}
            {tab === 'checks' && (
              <>
                <div className="content-heading">
                  <h3>CI evidence</h3>
                  <span>Bound to {active.head_sha.slice(0, 7)}</span>
                </div>
                <p className="pane-caption">
                  Required checks must succeed on this commit and come from their configured GitHub
                  app.
                </p>
                <div className="check-list">
                  {active.evidence.checks.length ? (
                    active.evidence.checks.map((c, i) => {
                      const sameCommit = c.head_sha === active.head_sha;
                      const passed = c.conclusion === 'success' && sameCommit;
                      const required = session?.policy.required_checks.some(
                        (r) => r.name === c.name && r.app_id === c.app_id,
                      );
                      return (
                        <div className="check-row" key={`${c.name}-${i}`}>
                          <span className={passed ? 'green-text' : 'rose-text'}>
                            {passed ? <CheckCircle2 size={20} /> : <XCircle size={20} />}
                          </span>
                          <div>
                            <strong>
                              {c.name}
                              {required && <span className="required-chip">Required</span>}
                            </strong>
                            <small>
                              GitHub app {c.app_id} ·{' '}
                              {sameCommit
                                ? 'Matches inspected commit'
                                : 'Different commit — not valid evidence'}
                            </small>
                          </div>
                          <span className={`check-result ${passed ? 'success' : 'failure'}`}>
                            {!sameCommit ? 'Stale' : c.conclusion || c.status}
                          </span>
                        </div>
                      );
                    })
                  ) : (
                    <div className="empty-pane">
                      No CI evidence was available for this recommendation.
                    </div>
                  )}
                </div>
              </>
            )}
            {tab === 'activity' && (
              <>
                <div className="content-heading">
                  <h3>Decision timeline</h3>
                  <span>{active.audit?.length || 0} events</span>
                </div>
                <div className="timeline">
                  {active.audit?.map((event) => (
                    <div className="timeline-event" key={event.id}>
                      <span
                        className={`timeline-icon ${event.action === 'approve' ? 'green-text' : ''}`}
                      >
                        {event.action === 'evaluated' ? (
                          <ShieldCheck size={15} />
                        ) : event.action === 'approve' ? (
                          <Check size={15} />
                        ) : (
                          <Activity size={15} />
                        )}
                      </span>
                      <div>
                        <strong>
                          {event.action === 'evaluated'
                            ? 'Agent evaluated the change'
                            : event.action === 'approve'
                              ? 'Review approved'
                              : event.action === 'reject'
                                ? 'Review rejected'
                                : event.action.replaceAll('_', ' ')}
                        </strong>
                        <small>
                          {event.actor} · {new Date(event.at * 1000).toLocaleString()}
                        </small>
                        <p>
                          {event.action === 'evaluated'
                            ? `Applied trusted policy ${event.reason}.`
                            : event.reason}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
          <div className="decision-footer">
            {active.resolution ? (
              <>
                <div className="resolved-summary">
                  <span className={`resolved-icon ${active.resolution}`}>
                    <CheckCheck size={19} />
                  </span>
                  <div>
                    <strong>
                      {active.resolution === 'approve'
                        ? 'Approved and recorded'
                        : 'Rejected and recorded'}
                    </strong>
                    <small>
                      {active.publication?.state === 'published'
                        ? 'Published to GitHub'
                        : 'Saved with the reviewer’s reason and audit history.'}
                    </small>
                  </div>
                </div>
                {canPublish && active.publication?.state !== 'published' && (
                  <button
                    className="button primary"
                    disabled={busy || !!active.publication}
                    onClick={() => onDecision('publish')}
                  >
                    Publish to GitHub
                    <ExternalLink size={14} />
                  </button>
                )}
                <button className="button secondary" onClick={() => setTab('activity')}>
                  View activity
                  <ArrowUpRight size={13} />
                </button>
              </>
            ) : (
              <>
                <div className="footer-guidance">
                  <ShieldCheck size={18} />
                  <div>
                    <strong>Your judgment. Your sign-off.</strong>
                    <small>
                      {active.is_current === false
                        ? 'A newer review supersedes this recommendation.'
                        : !canResolve
                          ? session?.role === 'operator'
                            ? 'Connect as a named reviewer to make a decision.'
                            : 'Authors cannot review their own changes.'
                          : active.recommendation.outcome === 'BLOCKED'
                            ? 'Resolve the blockers and request fresh evidence.'
                            : expired
                              ? 'This recommendation expired. Queue a fresh review.'
                              : !auditReady
                                ? 'Inspect and acknowledge the LLM audit before approval.'
                                : 'Add a reason to keep the decision accountable.'}
                    </small>
                  </div>
                </div>
                <div className="decision-buttons">
                  <button
                    className="button secondary reject-button"
                    disabled={!canResolve || busy}
                    onClick={() => {
                      onDecision('reject');
                    }}
                  >
                    <X size={14} />
                    Reject
                  </button>
                  <button
                    className="button primary"
                    disabled={
                      !canResolve ||
                      busy ||
                      active.recommendation.outcome === 'BLOCKED' ||
                      expired ||
                      !auditReady
                    }
                    onClick={() => {
                      onDecision('approve');
                    }}
                  >
                    <Check size={15} />
                    Approve review
                  </button>
                </div>
              </>
            )}
          </div>
        </>
      ) : (
        <div className="detail-empty">
          {selectedRow ? (
            <>
              <Loader2 size={27} className="spin" />
              <h3>Gathering the evidence</h3>
              <p>Loading this recommendation and its decision history.</p>
            </>
          ) : (
            <>
              <GitPullRequest size={34} />
              <h3>A little context goes a long way.</h3>
              <p>Select a pull request to inspect its evidence and recommendation.</p>
            </>
          )}
        </div>
      )}
    </div>
  );
}
