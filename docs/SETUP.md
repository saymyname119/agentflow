# Start ApprovalFlow

You need Python 3.11+ and Node.js 22.12+ installed. Open a terminal in the downloaded/cloned repository. The first launch needs internet access to install dependencies; subsequent unchanged launches reuse them.

## Local demo: one command

```powershell
python start.py
```

Open http://127.0.0.1:8000 and enter the review workspace. It signs in automatically and includes sample PRs. Try approving a ready change, rejecting a blocked change, and inspecting its activity. No accounts, credentials or external database are needed. It never calls GitHub or a model.

If port 8000 is already occupied, stop that server or use `python start.py --port 8001`. Press Ctrl+C in the launch terminal to stop.

## Real GitHub sandbox: guided setup

Prepare a disposable repository with an existing pull request and at least one CI check. Use a repository-scoped read token with access to its pull requests, contents and checks. Do not paste tokens into chat or commit them.

```powershell
python start.py --sandbox
```

The wizard asks for:

1. Your GitHub read token (hidden; used in memory, not saved).
2. The repository URL and an existing PR number.
3. Which observed check(s) and producer(s) you trust and require.
4. The named reviewer's GitHub login. Reviewing your own PR remains prohibited.
5. A Smee channel URL, or Enter to skip webhook setup for now.

It generates the other credentials automatically, saves them in ignored `.local/sandbox.json`, queues your chosen PR, and starts the API and worker together. This sandbox mode always disables GitHub publication and external LLM calls. It does not change your tracked policy or existing demo database.

Open the printed workspace URL. In the connect dialog, paste `reviewer_token` from `.local/sandbox.json` to inspect and decide on changes, or `operator_token` to queue another real PR through **New review**. Protect this file: it contains local access tokens and the webhook secret. The local SQLite database holds your sandbox history in `.local/sandbox.db`.

To stop, press Ctrl+C in the terminal. To restart, use the same command and enter your GitHub token again; the other settings are reused. To change the repository, trusted checks or forwarding URL, use `python start.py --sandbox --reset`. Reset changes configuration without deleting review history.

## Add automatic webhooks once

Open https://smee.io and select **Start a new channel**. Paste that channel's URL into the wizard. The launcher downloads a pinned Smee client and starts forwarding automatically; no extra terminal command is needed. Only use disposable sandbox data with a webhook proxy.

In the sandbox repository, choose **Settings → Webhooks → Add webhook**:

| Field | Value |
| --- | --- |
| Payload URL | The Smee channel URL you gave the wizard |
| Content type | `application/json` |
| Secret | `webhook_secret` from `.local/sandbox.json` |
| Individual events | Pull requests, Check runs, Check suites |
| Active | Enabled |

Now open a new PR or push a commit to an existing PR. Recent webhook deliveries should show **202**, and the dashboard should receive a recommendation. GitHub's initial ping is intentionally ignored. Check completion can create a newer recommendation; older recommendations remain in history and cannot be approved.

If you skipped Smee, you can still test real PR evidence by connecting as operator and selecting **New review**. Add the forwarding URL later with `--reset`.

## If something fails

| Symptom | Next step |
| --- | --- |
| Python or npm not found | Install Python/Node, then reopen the terminal. |
| First dependency install fails | Check internet access and rerun the same command. |
| Port already in use | Stop the previous server or pass `--port 8001`. |
| GitHub 401/403/404 | Check token expiry, repository selection and read permissions. |
| No checks found | Run CI on the chosen PR, then repeat setup. |
| Required CI blocked | Wait for CI; confirm the configured name and producer are correct. |
| Author cannot approve | Use a collaborator-authored PR and an appropriate named reviewer. |
| Webhook 401 | Match GitHub's secret to the generated `webhook_secret`. |
| Webhook not arriving | Keep the launcher running, check forwarding output and GitHub delivery details. |
| UI appears outdated | Run `python start.py --rebuild`. |

Advanced independently managed deployment and optional LLM configuration remain documented in README.md and LLM_AUDIT.md. Those are separate from this simplified sandbox mode.

References: [GitHub local webhook testing](https://docs.github.com/en/webhooks/testing-and-troubleshooting-webhooks/testing-webhooks), [creating webhooks](https://docs.github.com/en/webhooks/using-webhooks/creating-webhooks).
