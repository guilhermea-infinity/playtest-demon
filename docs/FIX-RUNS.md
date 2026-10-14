# From approved playtest to a verified fix

## Connect once per game

1. Clone your game repository on the Mac and sign in to the [GitHub CLI](https://cli.github.com/manual/gh_auth_login): `gh auth login`. Private HTTPS clones need Git credential access; use `gh auth setup-git` if Git does not already have it.
2. In Playtest Demon, select the game and click **Connect game repository**. Enter the local repository root, its GitHub base branch (blank uses `origin/HEAD`), and the command that verifies a fresh clone. Examples: `npm ci && npm test`, or `python3 -m pip install -r requirements.txt && python3 -m pytest`. The command runs on this Mac; it must install required dependencies and exit nonzero on failure.
3. Choose Codex CLI or Claude Code, a model/default and its supported reasoning effort. These fixing settings are separate from the video analyst. The desk verifies the local repository and GitHub access before saving.
4. Leave automatic merge off for the first batch. Enable it per game once the repository has required checks, branch protection and GitHub auto-merge configured. Never use automatic merge as a substitute for meaningful tests.

## The loop

Capture and describe a change → AI drafts a request → human checks/edits it → human approves → **Send batch to agent** → agent implements → verification command passes → branch and PR → merge → install/build the new game version → human playtests again.

The desk uses an existing authenticated local CLI. It starts a fresh task inside a new clone of the remote base branch, with the game’s repository instructions, approved ticket snapshot and evidence. It does not inject work into an unrelated open chat. Repo configuration is visible before submission; the fixing model is never silently substituted. [Codex non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode) and [Claude’s programmatic mode](https://code.claude.com/docs/en/headless) support this workflow.

Review requires a title, expected behavior and acceptance criteria. Copy prompt is an export: it leaves requests approved. **Send batch to agent** atomically reserves approved IDs so two clicks/tabs cannot launch duplicate batches. Submitted requests are frozen; later arrivals collect in a new batch. One open batch/PR per repository prevents fixes being based on an obsolete branch before the previous PR finishes. Resolve or return a failed/interrupted run before sending the next batch.

## Isolation and publication

- Every run lives in `QA-Inbox/AgentRuns/<RUN-ID>/`, with an immutable `batch.json`, prompt, clone, logs and PR body. The source checkout is never reset or switched, and its local changes are not copied.
- The fixing CLI receives copied video/screenshot evidence and approved observations, including linked duplicate evidence. Evidence and structured-result helper files are removed before the desk stages changes.
- Codex uses `workspace-write`. Claude uses editing tools and its Bash sandbox with strict failure/no unsandboxed fallback. Repository code, tools and instructions still need to be trusted. CLI authentication stays in the CLI’s own storage; credentials are not copied into the workspace. See [Claude sandbox boundaries](https://code.claude.com/docs/en/sandboxing).
- The agent accounts for every request. Any unaddressed item stops publication and keeps the work for clarification. It may not commit, publish or merge; the desk performs those operations after verification.
- The desk reruns your verification command, checks whitespace and unchanged branch/base history, commits on `playtest/run-…`, pushes that branch and opens a PR. It never pushes directly to the base branch. PR lookup by head branch protects publication recovery from duplicate PR creation.
- Logs are local and may contain private code or observations. They are visible from the run’s Details dialog, not published as release assets. Evidence is not attached to public GitHub PRs.

## Merge and retest

**Queue merge** delegates to GitHub’s auto-merge with `--match-head-commit`. The desk requires the PR’s original head, at least one reported check, no failing checks and required status checks configured on the base branch. GitHub then enforces required checks/reviews and repository rules. The desk does not use admin bypasses, weaken rules or merge changed commits automatically. [GitHub merge behavior](https://cli.github.com/manual/gh_pr_merge).

Automatic merge is opt-in per game. **Stop auto merge** disables the queued merge for the current open PR; use GitHub to review/merge it afterwards. If checks have not appeared yet, the desk retries the merge request as GitHub updates; errors are visible in Fix runs. Closing a PR without merge returns its requests to approval. Merging marks them **Fixed**, which means the code merged—not that the human has verified the game.

Build/install the new game build using that game’s normal workflow. The desk does not yet create game builds or install them. Mark each fix **Verified in game**, or **Still needs work** to reopen the request and add the remaining issue before approving another batch. The original evidence and prior run stay linked. Do not mark a request verified simply because the test command passed.

## Stop, failure and recovery

**Cancel run** terminates the active process and returns tickets to approval while preserving its folder. Publication cannot be cancelled while a push/PR is in flight. A possibly published commit requires a GitHub lookup before tickets can be returned. If a PR exists, finish/close it first.

After a desk restart, interrupted coding work is never automatically re-executed. Inspect its log and saved changes. If there is an unchanged verified commit, **Recover publication** pushes the same branch and reuses its existing PR. Otherwise, **Return tickets to batch**, clarify the request/check command and start a fresh run. No failed run is labeled fixed. Long agent runs time out after 30 minutes; verification after 15 minutes.

The batch runner and video analyst are independent single workers. Pausing video analysis does not pause a coding run; use Cancel run for that. Keeping Terminal open and the Mac awake is required. Logs and run folders remain in the inbox and need their own backup/disk management.
