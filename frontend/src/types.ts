export type Outcome = 'READY' | 'REVIEW' | 'BLOCKED';
export type Finding = {
  code: string;
  message: string;
  severity: 'block' | 'review' | 'info';
  paths: string[];
};
export type Evidence = {
  title?: string;
  author: string;
  draft: boolean;
  mergeable: boolean | null;
  files: {
    filename: string;
    previous_filename?: string;
    status: string;
    additions: number;
    deletions: number;
  }[];
  checks: {
    name: string;
    app_id: number;
    status: string;
    conclusion: string | null;
    head_sha: string;
  }[];
};
export type AuditEvent = {
  id: string;
  decision_id: string;
  at: number;
  actor: string;
  action: string;
  reason: string;
};
export type Decision = {
  is_current?: boolean;
  id: string;
  repository: string;
  number: number;
  head_sha: string;
  base_sha: string;
  author: string;
  evidence: Evidence;
  created_at: number;
  revision: number;
  resolution: 'approve' | 'reject' | null;
  recommendation: {
    outcome: Outcome;
    policy_version: string;
    findings: Finding[];
    changed_lines: number;
    changed_files: number;
  };
  audit?: AuditEvent[];
  publication?: {
    state: 'sending' | 'uncertain' | 'published';
    review_id?: string;
    url?: string;
  } | null;
};
export type Policy = {
  version: string;
  max_lines: number;
  max_files: number;
  required_checks: { name: string; app_id: number }[];
  sensitive_patterns: string[];
};
export type Session = {
  actor: string;
  role: 'operator' | 'reviewer';
  repositories: string[];
  publication_enabled: boolean;
  demo: boolean;
  policy: Policy;
};
export type AppConfig = { demo: boolean; demo_tokens?: { reviewer: string; operator: string } };

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}
export async function api<T>(path: string, token = '', options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok)
    throw new ApiError(
      response.status,
      typeof data.detail === 'string' ? data.detail : 'The request could not be completed.',
    );
  return data as T;
}
export function latestDecisions(decisions: Decision[]) {
  const seen = new Set<string>();
  return decisions.filter((d) => {
    const key = `${d.repository.toLowerCase()}#${d.number}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}
export function relativeTime(seconds: number) {
  const minutes = Math.max(0, Math.floor((Date.now() / 1000 - seconds) / 60));
  return minutes < 1
    ? 'just now'
    : minutes < 60
      ? `${minutes}m ago`
      : minutes < 1440
        ? `${Math.floor(minutes / 60)}h ago`
        : `${Math.floor(minutes / 1440)}d ago`;
}
