# From approved playtest to a verified fix

## Connect once per game

1. Sign in to the [GitHub CLI](https://cli.github.com/manual/gh_auth_login) once: `gh auth login`. Your account needs write access to the game repository.
2. In Playtest Demon, select the game and click **Connect GitHub repository** (or **Connect repository** on its approved batch). Paste the GitHub URL or `owner/repository`, then click **Check repository**. A local clone is optional; you can still paste an existing repository root.
3. Review the detected starting branch, suggested project checks and fixing agent. For npm projects, the desk reads `package.json` and the lockfile to suggest dependency setup, build and test/QA scripts. Playwright projects also get Chromium setup. Unknown project types open **Agent & advanced settings** so you can enter your own verification command. A build-only check is clearly labelled; it is not a gameplay test.
4. New connections start with your current analyst’s chosen CLI/model/effort. Change these under **Agent & advanced settings** if you want a separate fixing model. Saved explicit models/efforts are preserved when catalog discovery is unavailable. Automatic merge starts off; enable it only once required checks and branch protection are configured.
5. Click **Connect game**. This saves the setup only. Nothing is cloned, edited, executed or submitted during GitHub-link inspection/connection. The desk reads GitHub metadata/project files and verifies access. Existing local-folder inputs are read to identify their GitHub origin. The verification command executes later, after you send an approved batch.

The connection belongs to this game in your local inbox. Each tester configures their own repository access and AI CLI login. During a batch the desk uses its GitHub CLI credential helper per Git operation; it does not change global Git configuration or copy a token into the game checkout.

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

When an agent leaves requests unaddressed, the run pauses as **Your answers needed**. Open **Review agent notes** in Fix runs to see each pending request, its approved description/recording, and the agent’s question. Use Previous/Next or request IDs to move between them. Draft text stays in this browser as you type; **Save answers** stores partial answers with the run without invoking an agent. Closing/reopening the dialog or normal state polling does not discard your text.

Answer every pending request, then **Continue saved work** to explicitly start another pass with the same configured CLI/model, run ID, saved working tree, evidence and branch. The original ticket snapshot stays intact; owner answers and prior results are archived with the run. Already implemented work is included in the continuation context. No fresh clone or duplicate batch is created. Checks still have to pass before publication. This also works for older failed/cancelled runs with unanswered requests when their saved workspace is intact and their unchanged tickets remain approved and unclaimed. If tickets changed, another run/PR owns the repository, or the branch/history changed, continuation stops with an explanation.

If all requests are implemented but verification fails or is interrupted, **Retry checks on saved work** reruns the configured check command on the same working tree and branch without invoking the agent again. Reservations and Git-history checks remain mandatory; a previously verified commit uses Recover publication instead. Required browsers are still installed and all project checks still run. During desk verification, Playwright’s unrelated global browser-cache garbage collection is disabled so it does not traverse other projects or protected folders; no filesystem permission or sandbox setting is changed.

After a desk restart, interrupted coding work is never automatically re-executed. Inspect its log and saved changes. If there is an unchanged verified commit, **Recover publication** pushes the same branch and reuses its existing PR. For saved agent questions, use **Review agent notes → Continue saved work**. Otherwise, **Return tickets to batch** releases the reservation for a fresh run; it is not the continuation path. No failed run is labeled fixed. Long agent runs time out after 30 minutes; verification after 15 minutes.

The batch runner and video analyst are independent single workers. Pausing video analysis does not pause a coding run; use Cancel run for that. Keep Playtest Demon running and the Mac awake. Closing its Mac window keeps the service running; Cmd+Q stops it. For source launches, keep Terminal open. Logs and run folders remain in the inbox and need their own backup/disk management.
