import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import {
  Activity,
  ArrowUpRight,
  BarChart3,
  BookOpen,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  GitPullRequest,
  HelpCircle,
  Inbox,
  KeyRound,
  Loader2,
  LogOut,
  Menu,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  TriangleAlert,
  X,
  XCircle,
} from 'lucide-react';
import {
  api,
  ApiError,
  latestDecisions,
  relativeTime,
  type AppConfig,
  type Decision,
  type Session,
} from './types';
import { Badge, Mark, Metric, ModalFrame } from './components';
import { PolicyPage, EvidencePage } from './pages';
import ReviewPanel from './ReviewPanel';
import ProductPage from './ProductPage';

type View = 'inbox' | 'history' | 'policy' | 'evidence';
type Modal = 'connect' | 'queue' | 'approve' | 'reject' | 'publish' | 'guide' | null;
export default function App() {
  const [productPage, setProductPage] = useState(!window.location.hash.startsWith('#/workspace'));
  useEffect(() => {
    document.title = productPage
      ? 'ApprovalFlow — Evidence-first code reviews'
      : 'ApprovalFlow — Review workspace';
  }, [productPage]);
  useEffect(() => {
    const updateRoute = () => setProductPage(!window.location.hash.startsWith('#/workspace'));
    window.addEventListener('hashchange', updateRoute);
    return () => window.removeEventListener('hashchange', updateRoute);
  }, []);
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [token, setToken] = useState('');
  const [records, setRecords] = useState<Decision[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<Decision | null>(null);
  const [epoch, setEpoch] = useState(0);
  const [view, setView] = useState<View>('inbox');
  const [filter, setFilter] = useState('all');
  const [query, setQuery] = useState('');
  const [repoFilter, setRepoFilter] = useState('all');
  const [tab, setTab] = useState('overview');
  const [modal, setModal] = useState<Modal>(null);
  const [menu, setMenu] = useState(false);
  const [busy, setBusy] = useState(false);
  const [booting, setBooting] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [credential, setCredential] = useState('');
  const [reason, setReason] = useState('');
  const [newRepo, setNewRepo] = useState('');
  const [prNumber, setPrNumber] = useState('142');
  const [job, setJob] = useState<{ id: string; status: string } | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);
  const closeModal = useCallback(() => {
    if (!busy) {
      setModal(null);
      setReason('');
    }
  }, [busy]);

  const connect = useCallback(async (newToken: string) => {
    setBusy(true);
    setError('');
    try {
      const [who, rows] = await Promise.all([
        api<Session>('/session', newToken),
        api<Decision[]>('/decisions', newToken),
      ]);
      setToken(newToken);
      setSession(who);
      setRecords(rows);
      setSelected(latestDecisions(rows).find((d) => !d.resolution)?.id || rows[0]?.id || null);
      setNewRepo(who.repositories[0] || '');
      setCredential('');
      setModal(null);
      setDetail(null);
      setEpoch((e) => e + 1);
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    (async () => {
      try {
        const cfg = await api<AppConfig>('/app-config', '', { signal: controller.signal });
        if (controller.signal.aborted) return;
        setConfig(cfg);
        if (cfg.demo_tokens) {
          const t = cfg.demo_tokens.reviewer;
          const [who, rows] = await Promise.all([
            api<Session>('/session', t, { signal: controller.signal }),
            api<Decision[]>('/decisions', t, { signal: controller.signal }),
          ]);
          if (controller.signal.aborted) return;
          setToken(t);
          setSession(who);
          setRecords(rows);
          setSelected(rows.find((d) => !d.resolution)?.id || rows[0]?.id || null);
          setNewRepo(who.repositories[0]);
        } else setModal('connect');
      } catch (e) {
        if (!controller.signal.aborted)
          setError(
            'Could not reach the service. Check that the ApprovalFlow API is running, then reload.',
          );
      } finally {
        if (!controller.signal.aborted) setBooting(false);
      }
    })();
    return () => controller.abort();
  }, []);

  const refresh = useCallback(async () => {
    if (!token) return;
    setRefreshing(true);
    setError('');
    try {
      const rows = await api<Decision[]>('/decisions', token);
      setRecords(rows);
      setSelected((prev) => (rows.some((d) => d.id === prev) ? prev : rows[0]?.id || null));
      setEpoch((e) => e + 1);
    } catch (e) {
      setError(message(e));
    } finally {
      setRefreshing(false);
    }
  }, [token]);

  useEffect(() => {
    setDetail(null);
    if (!selected || !token) return;
    const controller = new AbortController();
    api<Decision>(`/decisions/${selected}`, token, { signal: controller.signal })
      .then((d) => {
        if (!controller.signal.aborted) setDetail(d);
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(message(e));
      });
    return () => controller.abort();
  }, [selected, token, epoch]);

  useEffect(() => {
    if (!job?.id || !token) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    let polls = 0;
    const poll = async () => {
      try {
        const data = await api<{ status: string; decision_id: string | null; error?: string }>(
          `/jobs/${job.id}`,
          token,
          { signal: controller.signal },
        );
        if (controller.signal.aborted) return;
        if (data.status === 'done') {
          await refresh();
          if (!controller.signal.aborted && data.decision_id) {
            setSelected(data.decision_id);
            setView('inbox');
            setFilter('all');
            setQuery('');
            setNotice('Fresh evidence is ready. Open the recommendation below.');
            setJob(null);
          }
          return;
        }
        if (data.status === 'dead') {
          setJob(null);
          setError(
            'This review could not be completed after five attempts. Check the repository and connection, then queue it again.',
          );
          return;
        }
        setJob({ id: job.id, status: data.status });
        if (++polls >= 60) {
          setJob(null);
          setNotice(
            `Review ${job.id.slice(0, 8)} is still processing. Refresh the inbox to check for its recommendation.`,
          );
          return;
        }
        timer = setTimeout(poll, 1000);
      } catch (e) {
        if (!controller.signal.aborted) {
          setJob(null);
          setError(message(e));
        }
      }
    };
    void poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [job?.id, token, refresh]);

  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        setView('inbox');
        setTimeout(() => searchRef.current?.focus(), 0);
      }
    };
    window.addEventListener('keydown', key);
    return () => window.removeEventListener('keydown', key);
  }, []);

  const action = async (e: FormEvent) => {
    e.preventDefault();
    if (!detail || busy) return;
    setBusy(true);
    setError('');
    try {
      if (modal === 'publish')
        await api(`/decisions/${detail.id}/publish`, token, { method: 'POST' });
      else
        await api(`/decisions/${detail.id}/resolve`, token, {
          method: 'POST',
          body: JSON.stringify({
            action: modal,
            expected_revision: detail.revision,
            reason: reason.trim(),
          }),
        });
      setModal(null);
      setReason('');
      setNotice(
        modal === 'publish'
          ? 'The approved review was published to GitHub.'
          : `Review ${modal === 'approve' ? 'approved' : 'rejected'}. Your decision and reason are recorded.`,
      );
      await refresh();
    } catch (e) {
      setError(message(e));
      if (e instanceof ApiError && e.status === 409) {
        setModal(null);
        await refresh();
        setError(message(e));
      }
    } finally {
      setBusy(false);
    }
  };

  const enqueue = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      const result = await api<{ job_id: string }>('/reviews', token, {
        method: 'POST',
        body: JSON.stringify({ repository: newRepo, number: Number(prNumber) }),
      });
      setJob({ id: result.job_id, status: 'queued' });
      setModal(null);
      setNotice('Review queued. We’re gathering fresh evidence.');
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  };
  const disconnect = () => {
    setToken('');
    setSession(null);
    setRecords([]);
    setDetail(null);
    setSelected(null);
    setModal('connect');
    setMenu(false);
    setJob(null);
    setNotice('');
  };
  const choose = (d: Decision) => {
    if (!busy) {
      setSelected(d.id);
      setTab('overview');
    }
  };
  const navigate = (next: View) => {
    setView(next);
    setMenu(false);
    setFilter('all');
    setQuery('');
  };
  const latest = latestDecisions(records);
  const pending = latest.filter((d) => !d.resolution);
  const list = (view === 'history' ? records : latest).filter(
    (d) =>
      (filter === 'all' ||
        (filter === 'resolved'
          ? !!d.resolution
          : !d.resolution && d.recommendation.outcome === filter)) &&
      (repoFilter === 'all' || d.repository === repoFilter) &&
      `${d.evidence.title || ''} ${d.repository} ${d.number} ${d.author}`
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  const visibleIds = list.map((d) => d.id).join(',');
  useEffect(() => {
    if (!busy && (view === 'inbox' || view === 'history') && !list.some((d) => d.id === selected))
      setSelected(list[0]?.id || null);
  }, [visibleIds, selected, busy, view]);
  const selectedRow = records.find((d) => d.id === selected);
  const active = detail?.id === selected ? detail : null;
  const expired = active ? Date.now() / 1000 - active.created_at > 3600 : false;
  const canResolve =
    active &&
    session?.role === 'reviewer' &&
    session.actor.toLowerCase() !== active.author.toLowerCase() &&
    !active.resolution;
  const canPublish =
    active?.resolution === 'approve' &&
    session?.publication_enabled &&
    active.audit?.some((e) => e.action === 'approve' && e.actor === session.actor);

  if (productPage)
    return (
      <ProductPage
        records={latest}
        demo={!!config?.demo}
        loading={booting}
        onOpenWorkspace={(next = 'inbox', decisionId) => {
          navigate(next);
          if (decisionId) setSelected(decisionId);
          setProductPage(false);
          window.location.hash = '/workspace';
          window.scrollTo(0, 0);
        }}
      />
    );

  return (
    <div className="app-shell">
      {menu && <div className="sidebar-scrim" onClick={() => setMenu(false)} />}
      <aside className={`sidebar ${menu ? 'open' : ''}`}>
        <a
          className="brand"
          href="#overview"
          onClick={(e) => {
            e.preventDefault();
            setProductPage(true);
            window.location.hash = 'overview';
            window.scrollTo(0, 0);
          }}
        >
          <Mark />
          <span>
            Approval<span className="brand-light">Flow</span>
            <small>REVIEW WORKSPACE</small>
          </span>
        </a>
        <div className="workspace-label">
          <span className="workspace-avatar">T</span>
          <div>
            <strong>{session?.demo ? 'Tanay’s workspace' : 'Your workspace'}</strong>
            <small>
              {session?.demo ? 'Portfolio demo' : session ? 'Connected workspace' : 'Not connected'}
            </small>
          </div>
          <ChevronDown size={13} />
        </div>
        <p className="nav-label">WORKSPACE</p>
        <nav aria-label="Main navigation">
          <button className={view === 'inbox' ? 'active' : ''} onClick={() => navigate('inbox')}>
            <Inbox size={18} />
            Review inbox<span className="nav-count">{pending.length}</span>
          </button>
          <button
            className={view === 'history' ? 'active' : ''}
            onClick={() => navigate('history')}
          >
            <Activity size={18} />
            Decision history
          </button>
          <button className={view === 'policy' ? 'active' : ''} onClick={() => navigate('policy')}>
            <ShieldCheck size={18} />
            Review policy
          </button>
        </nav>
        <p className="nav-label secondary-label">PROJECT</p>
        <nav aria-label="Project navigation">
          <button
            className={view === 'evidence' ? 'active' : ''}
            onClick={() => navigate('evidence')}
          >
            <BarChart3 size={18} />
            Measured results
          </button>
          <button onClick={() => setModal('guide')}>
            <BookOpen size={18} />
            Workspace guide
            <ArrowUpRight size={14} className="nav-arrow" />
          </button>
        </nav>
        <div className="sidebar-bottom">
          <div className="human-card">
            <ShieldCheck size={21} />
            <strong>
              Evidence first.
              <br />
              Human in control.
            </strong>
            <p>Every recommendation has a reason. Every approval has an owner.</p>
            <button onClick={() => setModal('guide')}>
              How it works <ArrowUpRight size={13} />
            </button>
          </div>
          <button className="profile" onClick={() => setModal('connect')}>
            <span className="avatar purple">{session?.actor.slice(0, 1).toUpperCase() || 'T'}</span>
            <span>
              <strong>{session?.actor || 'Connect workspace'}</strong>
              <small>{session?.role === 'operator' ? 'Operator access' : 'Reviewer access'}</small>
            </span>
            <ChevronDown size={14} />
          </button>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumbs">
            <button
              className="icon-button mobile-menu"
              aria-label="Open navigation"
              onClick={() => setMenu(!menu)}
            >
              <Menu size={20} />
            </button>
            <span>Workspace</span>
            <ChevronRight size={13} />
            <strong>
              {
                {
                  inbox: 'Review inbox',
                  history: 'Decision history',
                  policy: 'Review policy',
                  evidence: 'Measured results',
                }[view]
              }
            </strong>
          </div>
          <div className="topbar-actions">
            <span className="connection">
              <i className={session ? 'connected' : ''} />
              {session ? 'Service connected' : 'Not connected'}
            </span>
            <span className={`mode-pill ${config?.demo ? '' : 'live'}`}>
              {config?.demo ? <Sparkles size={12} /> : <KeyRound size={12} />}{' '}
              {config?.demo ? 'Demo workspace' : 'Live workspace'}
            </span>
            <span className="topbar-divider" />
            <button
              className="icon-button"
              onClick={() => setModal('guide')}
              aria-label="Open workspace guide"
            >
              <HelpCircle size={18} />
            </button>
            <button
              className="avatar top-avatar"
              onClick={() => setModal('connect')}
              aria-label="Connection and account"
            >
              {session?.actor.slice(0, 1).toUpperCase() || 'T'}
            </button>
          </div>
        </header>
        <main>
          {config?.demo && (
            <div className="demo-banner">
              <span>
                <span className="demo-dot" />
                You’re exploring a working demo.
                <span className="banner-extra">
                  {' '}
                  Sample pull requests, real review logic. GitHub writes are disabled.
                </span>
              </span>
              <button onClick={() => setModal('guide')}>
                About this demo <ArrowUpRight size={12} />
              </button>
            </div>
          )}
          <div className="page-heading">
            <div>
              <div className="eyebrow">
                {view === 'evidence'
                  ? 'BUILT TO BE VERIFIED'
                  : view === 'policy'
                    ? 'YOUR REVIEW GUARDRAILS'
                    : 'YOUR REVIEW WORKSPACE'}
              </div>
              <h1>
                {
                  {
                    inbox: 'Good changes. Confident decisions.',
                    history: 'Every decision, accounted for.',
                    policy: 'Clear rules. Consistent reviews.',
                    evidence: 'Engineering you can measure.',
                  }[view]
                }
              </h1>
              <p>
                {
                  {
                    inbox: 'Know what changed, understand the risk, and keep work moving.',
                    history: 'Revisit recommendations, reviewer decisions, and their evidence.',
                    policy: 'The trusted policy behind every recommendation in this workspace.',
                    evidence: 'Reproducible experiments, with the scope behind every number.',
                  }[view]
                }
              </p>
            </div>
            <div className="heading-actions">
              {session && (
                <button
                  className="button secondary refresh-button"
                  onClick={refresh}
                  disabled={refreshing || busy}
                  aria-label="Refresh reviews"
                >
                  <RefreshCw size={15} className={refreshing ? 'spin' : ''} />
                  <span>Refresh</span>
                </button>
              )}
              <button
                className="button primary"
                onClick={() => {
                  setError('');
                  setModal(session ? 'queue' : 'connect');
                }}
              >
                <Plus size={16} />
                New review
              </button>
            </div>
          </div>
          {error && (
            <div className="alert error" role="alert">
              <TriangleAlert size={16} />
              <span>{error}</span>
              <button
                className="icon-button"
                aria-label="Dismiss error"
                onClick={() => setError('')}
              >
                <X size={15} />
              </button>
            </div>
          )}
          {notice && (
            <div className="alert notice" role="status">
              <CheckCircle2 size={16} />
              <span>{notice}</span>
              <button
                className="icon-button"
                aria-label="Dismiss notification"
                onClick={() => setNotice('')}
              >
                <X size={15} />
              </button>
            </div>
          )}
          {job && (
            <div className="job-progress" role="status">
              <Loader2 size={16} className="spin" />
              <strong>Review in progress</strong>
              <span>
                {job.status === 'retry'
                  ? 'Retrying evidence collection'
                  : 'Gathering pull request and CI evidence'}{' '}
                · {job.id.slice(0, 8)}
              </span>
            </div>
          )}
          {view === 'evidence' ? (
            <EvidencePage />
          ) : view === 'policy' ? (
            <PolicyPage session={session} onConnect={() => setModal('connect')} />
          ) : (
            <>
              <section className="metrics" aria-label="Review overview">
                <Metric
                  label="Open reviews"
                  value={pending.length}
                  caption="Awaiting a reviewer decision"
                  icon={<GitPullRequest size={18} />}
                  color="purple"
                />
                <Metric
                  label="Ready for sign-off"
                  value={pending.filter((d) => d.recommendation.outcome === 'READY').length}
                  caption="Required checks have passed"
                  icon={<CheckCircle2 size={18} />}
                  color="green"
                />
                <Metric
                  label="Needs a closer look"
                  value={pending.filter((d) => d.recommendation.outcome === 'REVIEW').length}
                  caption="Risk signals worth reviewing"
                  icon={<ShieldCheck size={18} />}
                  color="amber"
                />
                <Metric
                  label="Blocked by checks"
                  value={pending.filter((d) => d.recommendation.outcome === 'BLOCKED').length}
                  caption="Resolve issues before approval"
                  icon={<XCircle size={18} />}
                  color="rose"
                />
              </section>
              <section className="review-workspace">
                <div className="section-title">
                  <div>
                    <h2>
                      {view === 'history' ? 'Decision history' : 'Pull request reviews'}
                      <span className="count-pill">
                        {view === 'history' ? records.length : latest.length}
                      </span>
                    </h2>
                    <p>
                      {view === 'history'
                        ? 'All recorded recommendations, newest first.'
                        : 'A clear path from change to sign-off.'}
                    </p>
                  </div>
                  <select
                    aria-label="Filter by repository"
                    value={repoFilter}
                    onChange={(e) => setRepoFilter(e.target.value)}
                  >
                    <option value="all">All repositories</option>
                    {session?.repositories.map((r) => (
                      <option key={r} value={r}>
                        {r}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="inbox-toolbar">
                  <div className="filters" role="group" aria-label="Filter reviews">
                    {[
                      ['all', 'All reviews'],
                      ['REVIEW', 'Needs review'],
                      ['READY', 'Ready'],
                      ['BLOCKED', 'Blocked'],
                      ['resolved', 'Resolved'],
                    ].map(([key, label]) => (
                      <button
                        key={key}
                        className={filter === key ? 'selected' : ''}
                        onClick={() => setFilter(key)}
                      >
                        {label}
                        {key === 'all' && (
                          <span>{(view === 'history' ? records : latest).length}</span>
                        )}
                      </button>
                    ))}
                  </div>
                  <div className="search-box">
                    <Search size={15} />
                    <input
                      ref={searchRef}
                      aria-label="Search pull requests"
                      placeholder="Search pull requests..."
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                    />
                    {query ? (
                      <button
                        className="icon-button"
                        aria-label="Clear search"
                        onClick={() => setQuery('')}
                      >
                        <X size={13} />
                      </button>
                    ) : (
                      <kbd>⌘ K</kbd>
                    )}
                  </div>
                </div>
                <div className="review-split">
                  <div className="review-list" aria-label="Pull requests">
                    {booting ? (
                      <div className="list-state">
                        <Loader2 className="spin" size={24} />
                        <h3>Loading your workspace</h3>
                      </div>
                    ) : list.length ? (
                      list.map((d) => (
                        <button
                          className={`review-row ${d.id === selected ? 'selected' : ''}`}
                          key={d.id}
                          onClick={() => choose(d)}
                          disabled={busy}
                          aria-label={`Review pull request ${d.number}: ${d.evidence.title || d.repository}`}
                          aria-pressed={d.id === selected}
                        >
                          <div className="row-top">
                            <span
                              className={`pr-icon ${d.resolution ? 'closed' : d.recommendation.outcome.toLowerCase()}`}
                            >
                              <GitPullRequest size={17} />
                            </span>
                            <span className="pr-number">#{d.number}</span>
                            <span className="row-time">{relativeTime(d.created_at)}</span>
                          </div>
                          <h3>
                            {d.evidence.title || `Review changes in ${d.repository.split('/')[1]}`}
                          </h3>
                          <div className="row-meta">
                            <span className={`mini-avatar avatar-${d.author.length % 4}`}>
                              {d.author.slice(0, 1).toUpperCase()}
                            </span>
                            <span>{d.author}</span>
                            <span>·</span>
                            <span>
                              {d.recommendation.changed_files}{' '}
                              {d.recommendation.changed_files === 1 ? 'file' : 'files'}
                            </span>
                          </div>
                          <div className="row-bottom">
                            <Badge outcome={d.recommendation.outcome} resolved={d.resolution} />
                            <span className="repo-short">{d.repository.split('/').at(-1)}</span>
                            <ChevronRight size={13} />
                          </div>
                        </button>
                      ))
                    ) : (
                      <div className="list-state">
                        <Inbox size={27} />
                        <h3>
                          {!session
                            ? 'Connect your workspace'
                            : query || filter !== 'all'
                              ? 'No matching reviews'
                              : 'Your inbox is clear'}
                        </h3>
                        <p>
                          {!session
                            ? 'Use your access token to load review evidence.'
                            : query || filter !== 'all'
                              ? 'Try another search or clear the filters.'
                              : 'Queue a pull request to get an explainable recommendation.'}
                        </p>
                        <button
                          className="button secondary"
                          onClick={() => {
                            if (!session) setModal('connect');
                            else if (query || filter !== 'all') {
                              setQuery('');
                              setFilter('all');
                            } else setModal('queue');
                          }}
                        >
                          {!session
                            ? 'Connect'
                            : query || filter !== 'all'
                              ? 'Clear filters'
                              : 'New review'}
                        </button>
                      </div>
                    )}
                  </div>
                  <ReviewPanel
                    active={active}
                    selectedRow={selectedRow}
                    session={session}
                    tab={tab}
                    setTab={setTab}
                    busy={busy}
                    expired={expired}
                    canResolve={!!canResolve}
                    canPublish={!!canPublish}
                    navigate={navigate}
                    onDecision={(action) => {
                      setReason('');
                      setModal(action);
                    }}
                  />
                </div>
              </section>
            </>
          )}
          <footer className="page-footer">
            <span>
              <Mark small />
              Built for thoughtful reviews.
            </span>
            <span>
              Explainable recommendations<span>·</span>Human-owned decisions<span>·</span>
              ApprovalFlow <code>v0.2</code>
            </span>
          </footer>
        </main>
      </div>
      {modal === 'connect' && (
        <ModalFrame
          title={session ? 'Workspace connection' : 'Connect your workspace'}
          subtitle="Your token stays in memory for this tab. It is never saved to browser storage."
          onClose={closeModal}
        >
          {session && (
            <div className="connected-account">
              <span className="avatar purple">{session.actor.slice(0, 1).toUpperCase()}</span>
              <div>
                <strong>{session.actor}</strong>
                <small>
                  {session.role} · {session.demo ? 'Isolated demo' : 'Live service'}
                </small>
              </div>
              <button
                className="icon-button"
                aria-label="Disconnect workspace"
                onClick={disconnect}
              >
                <LogOut size={16} />
              </button>
            </div>
          )}
          {config?.demo_tokens && (
            <div className="demo-roles">
              <p className="field-label">EXPLORE THE DEMO</p>
              <button
                className="button secondary"
                disabled={busy}
                onClick={() => connect(config.demo_tokens!.reviewer)}
              >
                <ShieldCheck size={16} />
                Use reviewer access
              </button>
              <button
                className="button secondary"
                disabled={busy}
                onClick={() => connect(config.demo_tokens!.operator)}
              >
                <KeyRound size={16} />
                Use operator access
              </button>
              <small>
                Reviewers decide. Operators queue fresh evidence. Demo credentials cannot access
                GitHub.
              </small>
            </div>
          )}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void connect(credential.trim());
            }}
          >
            <label htmlFor="access-token">Access token</label>
            <input
              id="access-token"
              type="password"
              autoComplete="off"
              placeholder="Paste your workspace token"
              value={credential}
              onChange={(e) => setCredential(e.target.value)}
              required
            />
            <p className="form-help">
              Use the reviewer or operator token configured for this service.
            </p>
            {error && (
              <p className="form-error" role="alert">
                {error}
              </p>
            )}
            <button
              className="button primary full"
              type="submit"
              disabled={busy || !credential.trim()}
            >
              {busy ? <Loader2 size={15} className="spin" /> : <KeyRound size={15} />}Connect
              workspace
            </button>
          </form>
        </ModalFrame>
      )}
      {modal === 'queue' && (
        <ModalFrame
          title="Start a new review"
          subtitle="Gather fresh pull request evidence and apply your workspace’s review policy."
          onClose={closeModal}
        >
          {session?.role !== 'operator' ? (
            <>
              <div className="permission-note">
                <KeyRound size={20} />
                <div>
                  <strong>Operator access is required</strong>
                  <p>
                    Switch to an operator connection to queue a review. Named reviewers can sign off
                    on the results.
                  </p>
                </div>
              </div>
              {config?.demo_tokens ? (
                <button
                  className="button primary full"
                  onClick={() => connect(config.demo_tokens!.operator)}
                >
                  Switch to demo operator
                  <ArrowUpRight size={14} />
                </button>
              ) : (
                <button className="button primary full" onClick={() => setModal('connect')}>
                  Change connection
                </button>
              )}
            </>
          ) : (
            <form onSubmit={enqueue}>
              <label htmlFor="review-repo">Repository</label>
              <select
                id="review-repo"
                value={newRepo}
                onChange={(e) => setNewRepo(e.target.value)}
                required
              >
                {session.repositories.map((r) => (
                  <option key={r}>{r}</option>
                ))}
              </select>
              <label htmlFor="pr-number">Pull request number</label>
              <input
                id="pr-number"
                type="number"
                min="1"
                step="1"
                value={prNumber}
                onChange={(e) => setPrNumber(e.target.value)}
                required
              />
              {session.demo && (
                <p className="form-help">
                  The demo includes pull requests #142–#149. It uses sample data and never contacts
                  GitHub.
                </p>
              )}
              {error && (
                <p className="form-error" role="alert">
                  {error}
                </p>
              )}
              <button className="button primary full" type="submit" disabled={busy || !!job}>
                {busy ? <Loader2 className="spin" size={15} /> : <GitPullRequest size={15} />}Queue
                review
              </button>
            </form>
          )}
        </ModalFrame>
      )}
      {(modal === 'approve' || modal === 'reject' || modal === 'publish') && active && (
        <ModalFrame
          title={
            modal === 'publish'
              ? 'Publish this review to GitHub?'
              : modal === 'approve'
                ? 'Add your sign-off'
                : 'Record your concerns'
          }
          subtitle={`${active.repository} · #${active.number} · ${active.head_sha.slice(0, 7)}`}
          onClose={closeModal}
        >
          <form onSubmit={action}>
            {modal === 'publish' ? (
              <div className="permission-note">
                <ExternalLink size={20} />
                <p>
                  This sends an APPROVE review to GitHub using the service account. Your recorded
                  reason and reviewer name will be included. Evidence is refreshed before
                  submission.
                </p>
              </div>
            ) : (
              <>
                <label htmlFor="review-reason">
                  {modal === 'approve'
                    ? 'Why are you approving this change?'
                    : 'What needs to change?'}
                </label>
                <textarea
                  id="review-reason"
                  placeholder="Describe what you inspected and why you reached this decision…"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  minLength={10}
                  maxLength={2000}
                  required
                  rows={5}
                />
                <div className="form-help reason-count">
                  <span>At least 10 characters. Saved in the audit history.</span>
                  <span>{reason.trim().length}/2000</span>
                </div>
                <div className="safe-action-note">
                  <ShieldCheck size={15} />
                  {session?.demo
                    ? 'Demo decision only. Nothing will be posted to GitHub.'
                    : 'This records your decision locally. Publishing is a separate action.'}
                </div>
              </>
            )}
            {error && (
              <p className="form-error" role="alert">
                {error}
              </p>
            )}
            <div className="modal-actions">
              <button
                className="button secondary"
                type="button"
                onClick={closeModal}
                disabled={busy}
              >
                Cancel
              </button>
              <button
                className={`button ${modal === 'reject' ? 'danger' : 'primary'}`}
                type="submit"
                disabled={busy || (modal !== 'publish' && reason.trim().length < 10)}
              >
                {busy ? (
                  <Loader2 className="spin" size={15} />
                ) : modal === 'reject' ? (
                  <X size={15} />
                ) : (
                  <Check size={15} />
                )}{' '}
                {busy
                  ? 'Checking and saving…'
                  : modal === 'publish'
                    ? 'Publish approved review'
                    : modal === 'approve'
                      ? 'Confirm approval'
                      : 'Reject review'}
              </button>
            </div>
          </form>
        </ModalFrame>
      )}
      {modal === 'guide' && (
        <ModalFrame
          title="A clearer path to sign-off"
          subtitle="ApprovalFlow gathers the context. A reviewer makes the call."
          onClose={closeModal}
        >
          <div className="guide-steps">
            {[
              [
                '01',
                'Gather the evidence',
                'An operator queues a pull request, or a signed GitHub webhook starts a review.',
              ],
              [
                '02',
                'Understand the recommendation',
                'Inspect the exact commit’s CI checks, sensitive files, test signals, and policy findings.',
              ],
              [
                '03',
                'Make an accountable decision',
                'A named reviewer approves or rejects with a reason. Evidence is refreshed before approval.',
              ],
            ].map(([num, title, description]) => (
              <div key={num}>
                <span>{num}</span>
                <div>
                  <strong>{title}</strong>
                  <p>{description}</p>
                </div>
              </div>
            ))}
          </div>
          <div className="safe-action-note">
            <Sparkles size={17} />
            <span>
              {session?.demo
                ? 'This demo uses eight sample pull requests and the real policy and database code. Restarting it creates a fresh demo session. GitHub publication is disabled.'
                : 'Recommendations use explainable rules, not an LLM. Test naming is a signal, not proof of coverage. Human review and GitHub branch protection remain essential.'}
            </span>
          </div>
          <button className="button primary full" onClick={closeModal}>
            Back to the workspace
            <ArrowUpRight size={15} />
          </button>
        </ModalFrame>
      )}
    </div>
  );
}

function message(error: unknown) {
  return error instanceof Error ? error.message : 'Something went wrong. Please try again.';
}
