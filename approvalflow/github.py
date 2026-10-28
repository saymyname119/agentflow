"""GitHub evidence adapter and explicit review publisher. Never executes PR code."""
import httpx

from .models import ChangedFile, Check, Snapshot
from .patches import patch_is_complete


class GitHub:
    def __init__(self, token: str = "", client: httpx.Client | None = None):
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2026-03-10"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.client = client or httpx.Client(base_url="https://api.github.com", headers=headers,
                                            timeout=15, follow_redirects=False)

    def get(self, path, **params):
        response = self.client.get(path, params=params)
        response.raise_for_status()
        return response.json()

    def pages(self, path, key=None, **params):
        items = []
        for page in range(1, 31):
            data = self.get(path, per_page=100, page=page, **params)
            batch = data[key] if key else data
            items.extend(batch)
            if len(batch) < 100:
                return items
        raise ValueError("GitHub pagination limit exceeded; manual review required")

    def snapshot(self, repository: str, number: int) -> Snapshot:
        path = f"/repos/{repository}/pulls/{number}"
        first = self.get(path)
        head, base = first["head"]["sha"], first["base"]["sha"]
        files = self.pages(path + "/files")
        checks = self.pages(f"/repos/{repository}/commits/{head}/check-runs", "check_runs", filter="latest")
        final = self.get(path)
        # Pull-request files are mutable. Reject torn reads, including a changed base.
        if (head, base, first["updated_at"]) != (final["head"]["sha"], final["base"]["sha"], final["updated_at"]):
            raise ValueError("Pull request changed while collecting evidence; retry")
        parsed_files = [ChangedFile.model_validate(f) for f in files]
        for file in parsed_files:
            file.patch_complete = patch_is_complete(file)
        return Snapshot(
            title=final.get("title", ""),
            repository=repository, number=number, head_sha=head, base_sha=base,
            author=final["user"]["login"], draft=final["draft"], state=final["state"],
            mergeable=final.get("mergeable"), files_complete=len(files) == final["changed_files"],
            files=parsed_files,
            checks=[Check(name=c["name"], app_id=c["app"]["id"], status=c["status"],
                          conclusion=c.get("conclusion"), head_sha=c["head_sha"]) for c in checks],
        )

    def publish_approval(self, snapshot, decision_id, reviewer, reason):
        response = self.client.post(f"/repos/{snapshot.repository}/pulls/{snapshot.number}/reviews", json={
            "commit_id": snapshot.head_sha, "event": "APPROVE",
            "body": f"ApprovalFlow: reviewed by {reviewer}.\n\n{reason}\n\n<!-- approvalflow:{decision_id} -->",
        })
        response.raise_for_status()
        data = response.json()
        return {"review_id": data["id"], "url": data["html_url"]}
