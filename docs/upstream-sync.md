# Upstream synchronization

The scheduled workflow runs from the default branch (Alpha) at 00:23 UTC on
every third calendar day. It independently targets Alpha and codex/ebpf-next.

## Tracking policy

- Alpha: released Smart snapshots with matching uploaded assets, plus the
  latest eBPF release. Existing Android publication remains on Alpha.
- codex/ebpf-next: the same released Smart snapshots, plus the eBPF branch
  head mapped into experimental/tanaka. The legacy eBPF implementation is
  not replaced.
- .github/upstream-state.json holds separate smart, ebpf, and (on the next
  branch) ebpf_next commit markers. Failed sources never advance their marker.

## Merge and validation

Each source is merged against its recorded snapshot, rather than guessing
from possibly rewritten commit ancestry. Go text is formatted before retrying
a text conflict; indentation in other languages remains significant. Binary,
add/delete, and semantic conflicts require manual integration. Rewinds are
reported. Rewritten histories still undergo the full three-way comparison.

The mapped paths are common/ebpf, listener/sing_ebpf, and
listener/config/ebpf.go. Import paths are translated. Upstream CI, docs and
branding are not copied into the experimental tree. Other source changes
(such as new listener integration fields or dependencies) must already be
present locally or the eBPF source is blocked for manual integration.

A source snapshot is applied atomically. If Smart conflicts but eBPF does not,
the eBPF candidate can still be validated and integrated, and vice versa.
The workflow keeps its own scripts in a separate checkout while validating
candidate code.

Before advancing a target, the workflow runs vet, ordinary and eBPF package
tests, integration-test compilation, both applicable BPF generation checks,
and an Android ARM64 build. A failure leaves the target at its previous
commit. The candidate is saved in an automation/sync-* branch for recovery.
The final push requires the target to equal the recorded starting commit;
it never force-pushes a target branch. Concurrent changes cause a rerun request.

After an Alpha update the existing build-ebpf.yml pipeline is explicitly
dispatched for normal artifact publication. This deliberately preserves the
existing release pipeline, including its separate release build. Token-driven
pushes alone do not trigger GitHub push workflows. The next branch is validated
but not automatically published as an Alpha release.

## Manual controls

In Actions, choose Sync Smart and eBPF upstreams:

- target: both, Alpha, or codex/ebpf-next.
- dry_run: detect and trial-merge locally, then upload diagnostics. No remote
  branches, issues, releases or target updates are written. Candidate runtime
  validation is skipped in this mode.
- force_build: explicitly rerun the existing Alpha release pipeline even if
  no source changed; ignored for next-only or dry-run invocations.

Release assets that are not yet ready are a waiting condition, not a failure.
Network/API failures, source conflicts, and validation failures are actionable.

## Failure recovery

Download the upstream-sync-alpha-* or upstream-sync-next-* diagnostic artifact.
It contains result.json, summary.md, candidate.patch, and upstream patches for
blocked sources. Each target reuses one open synchronization issue instead of
creating one on every failed run. Successful candidate branches are removed;
failed/partial candidates are retained.

For a retained candidate, resolve the reported source conflicts there, preserve
downstream fixes, and rerun the normal build checks. Update only the source
snapshot actually integrated. A manually merged candidate must still incorporate
any newer target commits; rerun the workflow when its original target moved.
An all-unchanged successful run can close an issue after manual repair.

## Installation and testing

Install the workflow and scripts on Alpha, because GitHub schedules run only
from the default branch, and also keep the next branch's copy updated. Do not
copy the next branch's entire upstream-state.json over Alpha: its release
baselines are independent. Alpha also needs its stale integration-test calls
updated to the current backend API (included in the deployment patch).

Local tests use disposable Git repositories and local bare remotes only:

    python -m unittest discover -s .github/scripts -p 'test_*.py' -v

gofmt must be on PATH for the Go-formatting test. The workflow runs these tests
before synchronization and on pull requests changing the automation.

References:
- https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows
- https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow
