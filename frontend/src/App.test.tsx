import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from './App';
import { latestDecisions, type Decision, type Session } from './types';

function decision(id: string, number: number, outcome: 'READY' | 'REVIEW' | 'BLOCKED'): Decision {
  return {
    id,
    number,
    repository: 'team/service',
    head_sha: 'a'.repeat(40),
    base_sha: 'b'.repeat(40),
    author: 'maya',
    created_at: Date.now() / 1000 - 60,
    revision: 1,
    resolution: null,
    evidence: {
      title:
        outcome === 'BLOCKED'
          ? 'Fix broken catalog tests'
          : outcome === 'READY'
            ? 'Improve setup guide'
            : 'Update payment limits',
      author: 'maya',
      draft: false,
      mergeable: true,
      files: [{ filename: 'README.md', status: 'modified', additions: 2, deletions: 1 }],
      checks: [
        {
          name: 'test',
          app_id: 15368,
          status: 'completed',
          conclusion: outcome === 'BLOCKED' ? 'failure' : 'success',
          head_sha: 'a'.repeat(40),
        },
      ],
    },
    recommendation: {
      outcome,
      policy_version: 'v1',
      changed_lines: 3,
      changed_files: 1,
      findings: [
        {
          code:
            outcome === 'BLOCKED'
              ? 'required_ci'
              : outcome === 'READY'
                ? 'low_risk'
                : 'sensitive_paths',
          message: 'Inspect the supporting evidence.',
          severity: outcome === 'BLOCKED' ? 'block' : outcome === 'READY' ? 'info' : 'review',
          paths: [],
        },
      ],
    },
    audit: [
      {
        id: 'e1',
        decision_id: id,
        at: Date.now() / 1000 - 60,
        actor: 'policy',
        action: 'evaluated',
        reason: 'v1',
      },
    ],
    publication: null,
  };
}
function server(
  options: { live?: boolean; stale?: boolean; llm?: boolean; llmFailure?: boolean } = {},
) {
  const rows = [
    decision('review', 142, 'REVIEW'),
    decision('ready', 143, 'READY'),
    decision('blocked', 144, 'BLOCKED'),
  ];
  const session: Session = {
    llm_audit_enabled: options.llm,
    actor: 'reviewer',
    role: 'reviewer',
    repositories: ['team/service'],
    publication_enabled: false,
    demo: !options.live,
    policy: {
      version: 'v1',
      max_lines: 300,
      max_files: 15,
      required_checks: [{ name: 'test', app_id: 15368 }],
      sensitive_patterns: ['**/auth/**'],
    },
  };
  const calls: { path: string; body?: any; token: string }[] = [];
  const fetch = vi.fn(async (path: string, init: RequestInit = {}) => {
    const token = (init.headers as Record<string, string>)?.Authorization || '';
    calls.push({ path, body: init.body ? JSON.parse(String(init.body)) : undefined, token });
    const respond = (data: unknown, status = 200) =>
      ({ ok: status < 400, status, json: async () => data }) as Response;
    if (path === '/app-config')
      return respond({
        demo: !options.live,
        ...(!options.live
          ? { demo_tokens: { reviewer: 'review-token', operator: 'operator-token' } }
          : {}),
      });
    if (options.live && token !== 'Bearer valid-token')
      return respond({ detail: 'Valid bearer token required' }, 401);
    if (path === '/session')
      return respond({
        ...session,
        ...(token === 'Bearer operator-token' ? { actor: 'operator', role: 'operator' } : {}),
      });
    if (path === '/decisions') return respond(structuredClone(rows));
    if (path === '/reviews') return respond({ job_id: 'job1' }, 202);
    if (path === '/jobs/job1') return respond({ status: 'done', decision_id: 'review' });
    const row = rows.find((d) => path.startsWith(`/decisions/${d.id}`));
    if (row && path.endsWith('/llm-audit')) {
      if (options.llmFailure) {
        row.llm_audit = { id: 'audit1', state: 'unavailable', report: null };
        return respond({ detail: 'Audit unavailable; request a fresh review' }, 503);
      }
      row.llm_audit = { id: 'audit1', state: 'completed', report: { findings: [] } };
      return respond(structuredClone(row.llm_audit));
    }
    if (row && path.endsWith('/resolve')) {
      if (options.stale)
        return respond({ detail: 'Evidence or policy changed; request a fresh review' }, 409);
      const body = JSON.parse(String(init.body));
      row.resolution = body.action;
      row.revision++;
      row.audit!.push({
        id: 'e2',
        decision_id: row.id,
        at: Date.now() / 1000,
        actor: 'reviewer',
        action: body.action,
        reason: body.reason,
      });
      return respond({ resolution: body.action, revision: row.revision });
    }
    return row ? respond(structuredClone(row)) : respond({ detail: 'Not found' }, 404);
  });
  vi.stubGlobal('fetch', fetch);
  return { rows, calls, fetch };
}
async function boot() {
  render(<App />);
  await screen.findByRole('heading', { name: 'Why this recommendation?' });
}

test('required LLM audit gates approval until the reviewer acknowledges its report', async () => {
  const backend = server({ llm: true });
  await boot();
  const user = userEvent.setup();
  expect(screen.getByRole('button', { name: 'Approve review' })).toBeDisabled();
  await user.click(screen.getByRole('tab', { name: 'LLM audit' }));
  await user.click(screen.getByRole('button', { name: 'Run LLM audit' }));
  const checkbox = await screen.findByRole('checkbox', { name: /I inspected this audit/ });
  expect(screen.getByRole('button', { name: 'Approve review' })).toBeDisabled();
  await user.click(checkbox);
  expect(screen.getByRole('button', { name: 'Approve review' })).toBeEnabled();
  await user.click(screen.getByRole('button', { name: 'Approve review' }));
  const dialog = screen.getByRole('dialog');
  fireEvent.change(within(dialog).getByRole('textbox'), {
    target: { value: 'Inspected model findings and verified changes' },
  });
  await user.click(within(dialog).getByRole('button', { name: 'Confirm approval' }));
  await waitFor(() =>
    expect(backend.calls.find((c) => c.path.endsWith('/resolve'))?.body.expected_audit_id).toBe(
      'audit1',
    ),
  );
});

test('unavailable LLM audit remains visible and does not enable approval', async () => {
  server({ llm: true, llmFailure: true });
  await boot();
  const user = userEvent.setup();
  await user.click(screen.getByRole('tab', { name: 'LLM audit' }));
  await user.click(screen.getByRole('button', { name: 'Run LLM audit' }));
  await screen.findByText(/Audit unavailable. Approval remains blocked/);
  expect(screen.getByRole('button', { name: 'Approve review' })).toBeDisabled();
});

test('disabled audit states its scope without offering an external request', async () => {
  server();
  await boot();
  await userEvent.setup().click(screen.getByRole('tab', { name: 'LLM audit' }));
  expect(screen.getByText(/External LLM audit is disabled/)).toBeVisible();
  expect(screen.queryByRole('button', { name: 'Run LLM audit' })).not.toBeInTheDocument();
});

test('demo loads real-shaped evidence and distinguishes required human review', async () => {
  server();
  await boot();
  expect(
    screen.getByRole('heading', { name: 'A human review makes the difference.' }),
  ).toBeVisible();
  expect(screen.getByRole('button', { name: 'Approve review' })).toBeEnabled();
  expect(screen.queryByRole('button', { name: 'Publish to GitHub' })).not.toBeInTheDocument();
  expect(localStorage.setItem).not.toHaveBeenCalled();
  expect(sessionStorage.setItem).not.toHaveBeenCalled();
});

test('historical recommendations explain why decision actions are disabled', async () => {
  const backend = server();
  backend.rows[0].is_current = false;
  await boot();
  expect(screen.getByRole('button', { name: 'Approve review' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Reject' })).toBeDisabled();
  expect(screen.getByText(/Historical recommendation:/)).toBeVisible();
  expect(screen.getByText('A newer review supersedes this recommendation.')).toBeVisible();
});
test('search and filters select matching evidence and handle empty results', async () => {
  server();
  await boot();
  const user = userEvent.setup();
  await user.click(screen.getByRole('button', { name: 'Blocked' }));
  await screen.findByRole('heading', { name: 'Let’s resolve the blockers first.' });
  expect(screen.getByRole('button', { name: 'Approve review' })).toBeDisabled();
  await user.type(screen.getByRole('textbox', { name: 'Search pull requests' }), 'not-a-match');
  expect(await screen.findByRole('heading', { name: 'No matching reviews' })).toBeVisible();
  await user.click(screen.getByRole('button', { name: 'Clear filters' }));
  await screen.findByRole('heading', { name: 'Why this recommendation?' });
});
test('approval requires a meaningful reason and uses the displayed revision', async () => {
  const backend = server();
  await boot();
  const user = userEvent.setup();
  await user.click(screen.getByRole('button', { name: 'Approve review' }));
  const dialog = screen.getByRole('dialog');
  expect(within(dialog).getByRole('button', { name: 'Confirm approval' })).toBeDisabled();
  fireEvent.change(within(dialog).getByRole('textbox'), {
    target: { value: 'Reviewed sensitive paths and verified the test results.' },
  });
  await user.click(within(dialog).getByRole('button', { name: 'Confirm approval' }));
  expect(await screen.findByText('Approved and recorded')).toBeVisible();
  expect(backend.calls.find((c) => c.path === '/decisions/review/resolve')?.body).toEqual({
    action: 'approve',
    expected_revision: 1,
    reason: 'Reviewed sensitive paths and verified the test results.',
  });
  await user.click(screen.getByRole('button', { name: 'View activity' }));
  expect(
    await screen.findByText('Reviewed sensitive paths and verified the test results.'),
  ).toBeVisible();
});
test('stale evidence produces a visible conflict and never optimistic approval', async () => {
  server({ stale: true });
  await boot();
  const user = userEvent.setup();
  await user.click(screen.getByRole('button', { name: 'Approve review' }));
  fireEvent.change(screen.getByRole('dialog').querySelector('textarea')!, {
    target: { value: 'Checked the supporting evidence.' },
  });
  await user.click(screen.getByRole('button', { name: 'Confirm approval' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Evidence or policy changed');
  expect(screen.queryByText('Approved and recorded')).not.toBeInTheDocument();
});
test('blocked changes can be rejected with a recorded reason', async () => {
  const backend = server();
  await boot();
  const user = userEvent.setup();
  await user.click(screen.getByRole('button', { name: 'Blocked' }));
  await screen.findByRole('heading', { name: 'Let’s resolve the blockers first.' });
  await user.click(screen.getByRole('button', { name: 'Reject' }));
  fireEvent.change(screen.getByRole('dialog').querySelector('textarea')!, {
    target: { value: 'Please fix the failing catalog tests.' },
  });
  await user.click(screen.getByRole('button', { name: 'Reject review' }));
  await waitFor(() => expect(backend.rows[2].resolution).toBe('reject'));
});
test('operator access queues a request and polls it to a fresh recommendation', async () => {
  const backend = server();
  await boot();
  const user = userEvent.setup();
  await user.click(screen.getByRole('button', { name: 'Connection and account' }));
  await user.click(screen.getByRole('button', { name: 'Use operator access' }));
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  await user.click(screen.getByRole('button', { name: 'New review' }));
  await user.click(screen.getByRole('button', { name: 'Queue review' }));
  expect(
    await screen.findByText('Fresh evidence is ready. Open the recommendation below.'),
  ).toBeVisible();
  expect(backend.calls.find((c) => c.path === '/reviews')).toMatchObject({
    token: 'Bearer operator-token',
    body: { repository: 'team/service', number: 142 },
  });
});
test('live mode requires authentication and reports an invalid token', async () => {
  server({ live: true });
  render(<App />);
  const user = userEvent.setup();
  await screen.findByRole('dialog');
  await user.type(screen.getByLabelText('Access token'), 'invalid-token');
  await user.click(screen.getByRole('button', { name: 'Connect workspace' }));
  expect(await within(screen.getByRole('dialog')).findByRole('alert')).toHaveTextContent(
    'Valid bearer token required',
  );
  await user.clear(screen.getByLabelText('Access token'));
  await user.type(screen.getByLabelText('Access token'), 'valid-token');
  await user.click(screen.getByRole('button', { name: 'Connect workspace' }));
  await screen.findByRole('heading', { name: 'Why this recommendation?' });
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(localStorage.setItem).not.toHaveBeenCalled();
});
test('policy and measured-results pages expose scope rather than production claims', async () => {
  server();
  await boot();
  const user = userEvent.setup();
  await user.click(screen.getByRole('button', { name: 'Review policy' }));
  expect(await screen.findByRole('heading', { name: 'Required CI checks' })).toBeVisible();
  await user.click(screen.getByRole('button', { name: 'Measured results' }));
  expect(await screen.findByText('Measured locally. Scoped honestly.')).toBeVisible();
  expect(screen.getByText(/not an independent safety benchmark/)).toBeVisible();
});
test('repeated analysis keeps the newest snapshot in the inbox without discarding history', () => {
  const old = decision('old', 142, 'READY'),
    fresh = decision('fresh', 142, 'BLOCKED');
  expect(latestDecisions([fresh, old])).toEqual([fresh]);
});

test('product overview opens the functioning review workspace', async () => {
  server();
  window.history.replaceState(null, '', '/');
  render(<App />);
  const user = userEvent.setup();
  expect(screen.getByRole('heading', { name: /Your next merge/ })).toBeVisible();
  await user.click(screen.getByRole('button', { name: 'Open review workspace' }));
  await screen.findByRole('heading', { name: 'Why this recommendation?' });
  expect(window.location.hash).toBe('#/workspace');
});

test('product preview switches to actual check evidence and results link opens measurements', async () => {
  server();
  window.history.replaceState(null, '', '/');
  render(<App />);
  const user = userEvent.setup();
  await user.click(screen.getByRole('tab', { name: 'CI evidence' }));
  expect(await screen.findByRole('tabpanel', { name: 'CI evidence preview' })).toHaveTextContent(
    'GitHub app 15368',
  );
  await user.click(screen.getByRole('button', { name: 'Inspect the full results' }));
  expect(await screen.findByText('Measured locally. Scoped honestly.')).toBeVisible();
});

test('opening a pull request from the product preview selects that request', async () => {
  server();
  window.history.replaceState(null, '', '/');
  render(<App />);
  const user = userEvent.setup();
  const request = await screen.findByRole('button', { name: /#143 Ready Improve setup guide/ });
  await user.click(request);
  expect(
    await screen.findByRole('heading', { name: 'Ready for your final sign-off.' }),
  ).toBeVisible();
});
