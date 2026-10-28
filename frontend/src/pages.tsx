import {
  ShieldCheck,
  KeyRound,
  BarChart3,
  CheckCheck,
  GitPullRequest,
  Activity,
  RefreshCw,
  Check,
  ArrowUpRight,
} from 'lucide-react';
import type { Session } from './types';
import { Metric } from './components';
import evaluation from '../../evaluation/results.json';
import reliability from '../../evaluation/reliability-results.json';
import verification from '../../evaluation/verification.json';
export function PolicyPage({
  session,
  onConnect,
}: {
  session: Session | null;
  onConnect: () => void;
}) {
  if (!session)
    return (
      <div className="standalone-empty">
        <ShieldCheck size={32} />
        <h2>Connect to inspect your policy.</h2>
        <button className="button primary" onClick={onConnect}>
          Connect workspace
        </button>
      </div>
    );
  return (
    <div className="policy-page">
      <section className="info-card">
        <div className="card-title">
          <span className="large-icon purple">
            <ShieldCheck size={24} />
          </span>
          <div>
            <h2>Trusted review policy</h2>
            <p>Version {session.policy.version} · Loaded by the service</p>
          </div>
          <span className="subtle-chip">Read-only</span>
        </div>
        <p className="body-copy">
          The policy lives on the server, outside pull request content. Repository instructions
          cannot change the rules that evaluate them.
        </p>
        <div className="policy-grid">
          <div>
            <small>Changed-line limit</small>
            <strong>
              {session.policy.max_lines}
              <span>lines</span>
            </strong>
            <p>Larger changes need human inspection.</p>
          </div>
          <div>
            <small>Changed-file limit</small>
            <strong>
              {session.policy.max_files}
              <span>files</span>
            </strong>
            <p>Broader changes receive closer review.</p>
          </div>
          <div>
            <small>Evidence freshness</small>
            <strong>
              1<span>hour</span>
            </strong>
            <p>Older recommendations must be refreshed.</p>
          </div>
        </div>
      </section>
      <section className="info-card">
        <div className="content-heading">
          <h2>Required CI checks</h2>
          <span>Exact commit + trusted producer</span>
        </div>
        <div className="check-list">
          {session.policy.required_checks.map((c) => (
            <div className="check-row" key={`${c.name}-${c.app_id}`}>
              <ShieldCheck size={20} className="purple-text" />
              <div>
                <strong>{c.name}</strong>
                <small>Trusted GitHub app ID: {c.app_id}</small>
              </div>
              <span className="required-chip">Must pass</span>
            </div>
          ))}
        </div>
      </section>
      <section className="info-card">
        <div className="content-heading">
          <h2>Sensitive change patterns</h2>
          <span>Always routed to a reviewer</span>
        </div>
        <p className="pane-caption">
          Authentication, payments, data migrations, infrastructure, CI, and dependency changes
          deserve human judgment.
        </p>
        <div className="pattern-grid">
          {session.policy.sensitive_patterns.map((p) => (
            <code key={p}>{p}</code>
          ))}
        </div>
      </section>
      <div className="policy-note">
        <KeyRound size={17} />
        <span>
          Policy edits require updating the trusted configuration and restarting the service and
          worker. This console does not modify policy.
        </span>
      </div>
    </div>
  );
}
export function EvidencePage() {
  const sqliteTests = verification.suites.sqlite.tests;
  return (
    <div className="evidence-page">
      <div className="evidence-disclosure">
        <BarChart3 size={20} />
        <div>
          <strong>Measured locally. Scoped honestly.</strong>
          <p>
            These are synthetic regression and contention experiments from this project. They do not
            measure production safety, real team time savings, or hiring outcomes.
          </p>
        </div>
        <span className="subtle-chip">28 OCT 2026</span>
      </div>
      <section className="metrics evidence-metrics">
        <Metric
          label="Labeled review scenarios"
          value={`${evaluation.matching_expected}/${evaluation.cases}`}
          caption="Matched their expected policy outcome"
          icon={<ShieldCheck size={18} />}
          color="purple"
        />
        <Metric
          label="Database verification"
          value={sqliteTests}
          caption="Tests passed on SQLite and PostgreSQL"
          icon={<CheckCheck size={18} />}
          color="green"
        />
        <Metric
          label="Conflicting approvals"
          value="0"
          caption={`${reliability.approval_races} races · ${reliability.reviewers_per_race} simultaneous attempts each`}
          icon={<GitPullRequest size={18} />}
          color="amber"
        />
      </section>
      <div className="evidence-columns">
        <section className="info-card">
          <div className="card-title">
            <span className="large-icon purple">
              <ShieldCheck size={23} />
            </span>
            <div>
              <h2>Does CI passing mean a change is ready?</h2>
              <p>40 hand-authored synthetic scenarios</p>
            </div>
          </div>
          <p className="body-copy">
            Compare a simple “test check passed” baseline with the agent’s combined risk checks.
          </p>
          <div className="bar-comparison">
            <div>
              <span>CI-only baseline</span>
              <strong>
                {evaluation.baseline_unsafe_ready}
                <small>unsafe ready recommendations</small>
              </strong>
              <div className="bar-track">
                <div
                  className="baseline-bar"
                  style={{
                    width: `${(evaluation.baseline_unsafe_ready / evaluation.unsafe_cases) * 100}%`,
                  }}
                />
              </div>
            </div>
            <div>
              <span>ApprovalFlow</span>
              <strong className="green-text">
                {evaluation.agent_unsafe_ready}
                <small>unsafe ready recommendations</small>
              </strong>
              <div className="bar-track">
                <div className="agent-zero" />
              </div>
            </div>
          </div>
          <p className="experiment-limit">
            31 cases were labeled as requiring review or blocking. The fixtures were authored with
            the implementation; this is a regression check, not an independent safety benchmark.
          </p>
        </section>
        <section className="info-card">
          <div className="card-title">
            <span className="large-icon green">
              <Activity size={23} />
            </span>
            <div>
              <h2>Reliable when work repeats</h2>
              <p>PostgreSQL {reliability.database_version.join('.')} · Synthetic experiments</p>
            </div>
          </div>
          <div className="reliability-rows">
            <div>
              <span>
                <RefreshCw size={17} />
                Repeated webhook deliveries
              </span>
              <strong>
                {reliability.duplicate_delivery_attempts.toLocaleString()} →{' '}
                {reliability.jobs_created} job
              </strong>
            </div>
            <div>
              <span>
                <CheckCheck size={17} />
                Resolution races
              </span>
              <strong>
                {reliability.successful_resolutions}/{reliability.approval_races} single winners
              </strong>
            </div>
            <div>
              <span>
                <Activity size={17} />
                Jobs recovered after restart
              </span>
              <strong>
                {reliability.jobs_recovered}/{reliability.simulated_restarts}
              </strong>
            </div>
          </div>
          <p className="experiment-limit">
            Restarts dispose and reopen database connections after an expired worker lease. These
            are not operating-system crash, power-loss, or network-partition tests.
          </p>
        </section>
      </div>
      <section className="info-card">
        <div className="content-heading">
          <h2>What this version proves — and what comes next</h2>
          <span>Evidence over claims</span>
        </div>
        <div className="next-evidence">
          <div>
            <span className="large-icon green">
              <Check size={20} />
            </span>
            <div>
              <h3>Repeatable behavior</h3>
              <p>
                Policy cases, signed webhooks, stale evidence, database races, and simulated GitHub
                publication are covered by automated checks.
              </p>
            </div>
          </div>
          <div>
            <span className="large-icon purple">
              <ArrowUpRight size={20} />
            </span>
            <div>
              <h3>Independent real-world evaluation</h3>
              <p>
                Next: have another reviewer label real sandbox pull requests, then measure
                disagreements, unnecessary escalations, and actual review time.
              </p>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
