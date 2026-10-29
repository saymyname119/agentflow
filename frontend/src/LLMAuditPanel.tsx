import { useState } from 'react';
import { api, type Decision } from './types';

export default function LLMAuditPanel({
  decision,
  enabled,
  token,
  canRun,
  onComplete,
  acknowledged,
  onAcknowledge,
}: {
  decision: Decision;
  enabled: boolean;
  token: string;
  canRun: boolean;
  onComplete: () => void;
  acknowledged: boolean;
  onAcknowledge: (checked: boolean) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const report = decision.llm_audit;
  async function run() {
    setBusy(true);
    setError('');
    try {
      await api(`/decisions/${decision.id}/llm-audit`, token, { method: 'POST' });
      onComplete();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Audit unavailable');
      onComplete();
    } finally {
      setBusy(false);
    }
  }
  return (
    <section aria-label="LLM audit" className="llm-audit">
      <h3>Advisory code audit</h3>
      <p>
        The model looks for issues in the diff. It cannot approve changes or remove policy blockers.
        Findings may be incorrect; verify them before deciding.
      </p>
      {!enabled ? (
        <div className="policy-note">
          External LLM audit is disabled. The demo uses deterministic rules and never sends code to
          a model.
        </div>
      ) : (
        <>
          <p>
            Running an audit sends this PR’s diff to OpenAI. One request is allowed per
            recommendation and audit configuration.
          </p>
          {!report && (
            <button
              className="button primary"
              disabled={!canRun || busy}
              onClick={() => void run()}
            >
              {busy ? 'Auditing…' : 'Run LLM audit'}
            </button>
          )}
          {report?.state === 'running' && (
            <p role="status">
              Audit reserved or running. Refresh to check its status. If interrupted, queue a fresh
              review; it will not be resubmitted automatically.
            </p>
          )}
          {report?.state === 'unavailable' && (
            <p role="alert">
              Audit unavailable. Approval remains blocked. Request a fresh review before retrying.
            </p>
          )}
          {report?.state === 'completed' && (
            <>
              <p>
                Audit completed for commit <code>{decision.head_sha.slice(0, 7)}</code>.{' '}
                {report.report?.findings.length || 0} findings. No findings is not proof of safety.
              </p>
              <div className="findings">
                {report.report?.findings.map((f, i) => (
                  <article className="finding review" key={i}>
                    <div>
                      <h4>{f.title}</h4>
                      <p>
                        <strong>{f.severity}</strong> ·{' '}
                        <code>
                          {f.path}:{f.line}
                        </code>
                      </p>
                      <p>{f.explanation}</p>
                      <p>Suggested fix: {f.suggestion}</p>
                    </div>
                  </article>
                ))}
              </div>
              <label>
                <input
                  type="checkbox"
                  checked={acknowledged}
                  onChange={(e) => onAcknowledge(e.target.checked)}
                />{' '}
                I inspected this audit and will account for its findings in my decision.
              </label>
            </>
          )}
        </>
      )}
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
