import { useState } from 'react';
import {
  ArrowDown,
  ArrowRight,
  ArrowUpRight,
  Check,
  CheckCircle2,
  ChevronRight,
  FileCode2,
  GitBranch,
  GitPullRequest,
  ShieldCheck,
  Terminal,
  XCircle,
} from 'lucide-react';
import { Mark } from './components';
import type { Decision } from './types';
import verification from '../../evaluation/verification.json';
import results from '../../evaluation/results.json';
import reliability from '../../evaluation/reliability-results.json';

type Props = {
  records: Decision[];
  demo: boolean;
  loading: boolean;
  onOpenWorkspace: (view?: 'inbox' | 'evidence' | 'policy', decisionId?: string) => void;
};

export default function ProductPage({ records, demo, loading, onOpenWorkspace }: Props) {
  const [previewTab, setPreviewTab] = useState('review');
  const sample = records.find((r) => r.number === 142) || records[0];
  return (
    <div className="product-site">
      <header className="product-header">
        <a href="#overview" className="product-brand" aria-label="ApprovalFlow home">
          <Mark />
          <strong>ApprovalFlow</strong>
        </a>
        <nav aria-label="Product navigation">
          <a href="#workflow">Workflow</a>
          <a href="#results">Results</a>
          <button onClick={() => onOpenWorkspace('policy')}>
            Review policy
            <ArrowUpRight size={13} />
          </button>
        </nav>
        <button className="product-button nav-cta" onClick={() => onOpenWorkspace()}>
          Open workspace
          <ArrowUpRight size={16} />
        </button>
      </header>
      <main className="product-main">
        <section className="product-hero" id="overview">
          <div className="hero-grid" aria-hidden="true" />
          <div className="hero-art" aria-hidden="true">
            <div className="ribbon ribbon-one" />
            <div className="ribbon ribbon-two" />
            <div className="ribbon ribbon-three" />
            <span className="art-cross cross-one">+</span>
            <span className="art-cross cross-two">+</span>
            <div className="orbit-label">
              <GitPullRequest size={15} />
              change → evidence → decision
            </div>
          </div>
          <div className="hero-copy">
            <div className="product-kicker">
              <span />
              GITHUB REVIEW AGENT <span className="kicker-version">/ v0.3</span>
            </div>
            <h1>
              Your next merge.
              <br />
              <span>A clearer decision.</span>
            </h1>
            <p>
              All the context behind a code change.
              <br />
              One workspace to make the call.
            </p>
            <div className="hero-buttons">
              <button className="product-button white" onClick={() => onOpenWorkspace()}>
                Open review workspace
                <ArrowUpRight size={20} />
              </button>
              <a className="product-button outline" href="#workflow">
                See how it works
                <ArrowDown size={18} />
              </a>
            </div>
            <div className="hero-footnote">
              <span className="status-light" />
              <span>
                {loading
                  ? 'Connecting to the review service…'
                  : demo
                    ? 'Local demo. No GitHub account required.'
                    : 'Connect your team’s review service.'}
              </span>
              <span className="footnote-divider" />
              <span>Human-controlled approvals.</span>
            </div>
          </div>
          <div className="hero-caption">
            <span>BUILT FOR DEVELOPERS.</span>
            <span>DESIGNED FOR JUDGMENT.</span>
          </div>
        </section>

        <section className="product-preview-section" aria-label="Workspace preview">
          <div className="preview-intro">
            <span className="mono-label">01 / THE WORKSPACE</span>
            <p>The change. The checks. The reason.</p>
            <button onClick={() => onOpenWorkspace()}>
              Explore the interactive workspace
              <ArrowUpRight size={16} />
            </button>
          </div>
          <div className="product-preview">
            <div className="preview-chrome">
              <div className="window-dots">
                <i />
                <i />
                <i />
              </div>
              <span>
                <Mark small />
                ApprovalFlow <ChevronRight size={12} /> Review workspace
              </span>
              <span className="preview-demo-label">
                {demo ? 'FIXTURE-BACKED DEMO' : 'WORKSPACE PREVIEW'}
              </span>
            </div>
            <div className="preview-app">
              <aside className="preview-sidebar">
                <GitPullRequest size={20} />
                <ShieldCheck size={20} />
                <Terminal size={20} />
                <GitBranch size={20} />
              </aside>
              <div className="preview-queue">
                <div className="preview-queue-heading">
                  Pull requests<span>{records.length || '—'}</span>
                </div>
                {(records.length ? records.slice(0, 3) : []).map((r) => (
                  <button
                    className={r.id === sample?.id ? 'active' : ''}
                    key={r.id}
                    onClick={() => onOpenWorkspace('inbox', r.id)}
                  >
                    <span>
                      <GitPullRequest size={14} />#{r.number}
                      <small>
                        {r.resolution
                          ? 'Resolved'
                          : r.recommendation.outcome === 'READY'
                            ? 'Ready'
                            : r.recommendation.outcome === 'BLOCKED'
                              ? 'Blocked'
                              : 'Needs review'}
                      </small>
                    </span>
                    <strong>{r.evidence.title || `Review pull request #${r.number}`}</strong>
                    <span className="preview-author">
                      {r.author} · {r.recommendation.changed_files}{' '}
                      {r.recommendation.changed_files === 1 ? 'file' : 'files'}
                    </span>
                  </button>
                ))}
                {!records.length && (
                  <div className="preview-unconnected">
                    <ShieldCheck size={23} />
                    <p>
                      Your team’s changes.
                      <br />
                      Their supporting evidence.
                    </p>
                    <button onClick={() => onOpenWorkspace()}>
                      Connect workspace
                      <ArrowUpRight size={14} />
                    </button>
                  </div>
                )}
              </div>
              <div className="preview-editor">
                <div className="preview-editor-heading">
                  <div>
                    <span>{sample?.repository || 'YOUR REPOSITORY'}</span>
                    <h2>{sample?.evidence.title || 'A clear path from change to sign-off.'}</h2>
                  </div>
                  <span className="preview-commit">
                    <GitBranch size={13} />
                    {sample?.head_sha.slice(0, 7) || 'commit-pinned'}
                  </span>
                </div>
                <div className="preview-tabs" role="tablist" aria-label="Product preview">
                  <button
                    role="tab"
                    aria-selected={previewTab === 'review'}
                    onClick={() => setPreviewTab('review')}
                  >
                    Recommendation
                  </button>
                  <button
                    role="tab"
                    aria-selected={previewTab === 'checks'}
                    onClick={() => setPreviewTab('checks')}
                  >
                    CI evidence
                  </button>
                  <span>Read-only preview</span>
                </div>
                <div
                  className="preview-code"
                  role="tabpanel"
                  aria-label={
                    previewTab === 'review' ? 'Recommendation preview' : 'CI evidence preview'
                  }
                >
                  {previewTab === 'review' ? (
                    <>
                      <div className="preview-line">
                        <span>01</span>
                        <code>
                          <b>review</b> = gather_evidence(pull_request)
                        </code>
                      </div>
                      <div className="preview-line">
                        <span>02</span>
                        <code>
                          verify_checks(<em>commit</em>=head_sha)
                        </code>
                      </div>
                      <div className="preview-line">
                        <span>03</span>
                        <code>
                          inspect_changes(<em>policy</em>=trusted_policy)
                        </code>
                      </div>
                      <div className="preview-recommendation">
                        <ShieldCheck size={23} />
                        <div>
                          <small>
                            {sample?.recommendation.outcome === 'BLOCKED'
                              ? 'REQUIRED CONDITIONS NOT MET'
                              : sample?.recommendation.outcome === 'READY'
                                ? 'READY FOR HUMAN SIGN-OFF'
                                : 'HUMAN REVIEW RECOMMENDED'}
                          </small>
                          <h3>
                            {sample?.recommendation.outcome === 'BLOCKED'
                              ? 'Resolve the blockers before approval.'
                              : sample?.recommendation.outcome === 'READY'
                                ? 'The evidence meets the configured policy.'
                                : 'Green checks are part of the picture.'}
                          </h3>
                          <p>
                            {sample?.recommendation.findings[0]?.message ||
                              'Combine CI evidence, change risk and human judgment before signing off.'}
                          </p>
                          {sample?.recommendation.findings[0]?.paths[0] && (
                            <code>
                              <FileCode2 size={12} />
                              {sample.recommendation.findings[0].paths[0]}
                            </code>
                          )}
                        </div>
                      </div>
                      <div className="preview-line last">
                        <span>04</span>
                        <code>
                          <span className="code-comment">
                            # The reviewer owns the final decision.
                          </span>
                        </code>
                      </div>
                    </>
                  ) : (
                    <div className="preview-checks">
                      {sample?.evidence.checks.length ? (
                        sample.evidence.checks.map((c, i) => (
                          <div key={`${c.name}-${i}`}>
                            {c.conclusion === 'success' ? (
                              <CheckCircle2 size={18} />
                            ) : (
                              <XCircle size={18} />
                            )}
                            <span>
                              {c.name}
                              <small>
                                GitHub app {c.app_id} · commit {c.head_sha.slice(0, 7)}
                              </small>
                            </span>
                            <code>{c.conclusion || c.status}</code>
                          </div>
                        ))
                      ) : (
                        <p>Connect a workspace to inspect its check evidence.</p>
                      )}
                    </div>
                  )}
                </div>
                <div className="preview-bottom">
                  <span>
                    <ShieldCheck size={14} />
                    Evidence is refreshed before approval.
                  </span>
                  <button onClick={() => onOpenWorkspace('inbox', sample?.id)}>
                    Review the change
                    <ArrowRight size={15} />
                  </button>
                </div>
              </div>
            </div>
          </div>
          <p className="preview-disclosure">
            {demo
              ? 'Sample pull requests. Real policy and database code. Demo mode never contacts GitHub.'
              : 'The preview uses your connected review data. Decisions are made inside the workspace.'}
          </p>
        </section>

        <section className="product-workflow" id="workflow">
          <div className="workflow-heading">
            <span className="mono-label">02 / HOW IT WORKS</span>
            <h2>
              The evidence,
              <br />
              before the approval.
            </h2>
            <p>
              Less hunting for context.
              <br />
              More room for a thoughtful review.
            </p>
          </div>
          <div className="workflow-cards">
            <article>
              <div className="workflow-card-top">
                <span>01</span>
                <GitPullRequest size={27} />
              </div>
              <h3>
                See the whole <br />
                change.
              </h3>
              <p>
                Gather the pull request, changed files, and CI results. Keep the evidence tied to
                the exact commit you’re inspecting.
              </p>
              <div className="workflow-code">
                <GitBranch size={14} />
                <code>head_sha → evidence</code>
              </div>
            </article>
            <article>
              <div className="workflow-card-top">
                <span>02</span>
                <ShieldCheck size={27} />
              </div>
              <h3>
                Know what needs <br />a closer look.
              </h3>
              <p>
                Flag sensitive paths, missing test updates, suspicious operations, and failed
                checks. Get a reason for every recommendation.
              </p>
              <div className="workflow-code">
                <span className="workflow-signal" />
                <code>payments/* → review</code>
              </div>
            </article>
            <article>
              <div className="workflow-card-top">
                <span>03</span>
                <CheckCircle2 size={27} />
              </div>
              <h3>
                Make the call. <br />
                Keep the record.
              </h3>
              <p>
                A named reviewer signs off with a reason. Fresh evidence, version checks, and an
                audit history keep the decision accountable.
              </p>
              <div className="workflow-code">
                <Check size={15} />
                <code>reviewer + reason + revision</code>
              </div>
            </article>
          </div>
        </section>

        <section className="product-results" id="results">
          <div className="results-heading">
            <span className="mono-label">03 / MEASURED, NOT ASSUMED</span>
            <h2>
              Built to be
              <br />
              <span>put to the test.</span>
            </h2>
            <p>
              Reproducible local experiments.
              <br />
              Clear limits behind every number.
            </p>
          </div>
          <div className="product-stat-grid">
            <article>
              <strong>
                {verification.suites.sqlite.tests}
                <span>× 2</span>
              </strong>
              <h3>Backend tests passed</h3>
              <p>Verified against SQLite and PostgreSQL.</p>
            </article>
            <article>
              <strong>
                {results.matching_expected}
                <span>/{results.cases}</span>
              </strong>
              <h3>Expected policy outcomes</h3>
              <p>Hand-authored synthetic review scenarios.</p>
            </article>
            <article>
              <strong>
                {reliability.approval_races}
                <span>× {reliability.reviewers_per_race}</span>
              </strong>
              <h3>Approval race attempts</h3>
              <p>Exactly one decision recorded per race.</p>
            </article>
          </div>
          <div className="results-bottom">
            <p>
              Regression and contention experiments, not production impact or an independent safety
              benchmark. Live GitHub publication remains unverified.
            </p>
            <button className="product-button outline" onClick={() => onOpenWorkspace('evidence')}>
              Inspect the full results
              <ArrowUpRight size={18} />
            </button>
          </div>
        </section>

        <section className="product-final">
          <div className="final-accent" aria-hidden="true" />
          <span className="mono-label">YOUR WORKFLOW. YOUR JUDGMENT.</span>
          <h2>
            Keep the human
            <br />
            in the loop.
          </h2>
          <button className="product-button white" onClick={() => onOpenWorkspace()}>
            Try the review workspace
            <ArrowUpRight size={21} />
          </button>
          <p>
            {demo
              ? 'Runs locally. Uses sample data. No credentials needed.'
              : 'Connect with your configured reviewer or operator token.'}
          </p>
        </section>
      </main>
      <footer className="product-footer">
        <div>
          <Mark />
          <strong>ApprovalFlow</strong>
          <span>Evidence first. Human in control.</span>
        </div>
        <span>Python · FastAPI · PostgreSQL · React · TypeScript</span>
        <a href="#overview">Back to top ↑</a>
      </footer>
    </div>
  );
}
