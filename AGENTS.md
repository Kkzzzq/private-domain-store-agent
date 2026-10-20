# Working on this repository

## Automatic GitHub sync

The user authorizes automatic commit and push after each completed code task in this repository.

- Finish the requested change and run the relevant checks before committing.
- Review the diff and stage explicit paths belonging to the current task only. Do not include another ongoing task's changes, credentials, `.env`, database files, uploaded user files, or temporary outputs.
- Commit with a meaningful message. This checkout uses `.githooks/post-commit` to push the committed HEAD to the current branch's existing upstream. Confirm the remote branch contains the commit afterward.
- If the hook is not installed in a new checkout, run `git config core.hooksPath .githooks` after checking for existing custom hooks. Never overwrite an existing hook setup without preserving it.
- Do not force push, reset others' work, or resolve remote conflicts by overwriting changes. If a push fails, keep the local commit and report the cause.
- Pushing `main` starts the existing GitHub Actions test-and-deploy workflow. Report commit/push status accurately; do not call deployment successful until its workflow is confirmed successful.
- This is task-completion sync, not a file watcher. Never auto-commit unfinished edits merely because a file was saved.
- A later explicit user instruction not to commit or push takes precedence.
