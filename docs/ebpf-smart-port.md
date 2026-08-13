# eBPF inbound port for the Smart branch

This branch combines the Smart policy-group implementation from
`vernesong/mihomo` with the cgroup eBPF inbound from `TanakaLun/mihomo`.
The maintained combined source is published at
`https://github.com/mingxitang/mihomo_epbf_smart` on the `Alpha` branch.

## Pinned baselines

- Smart target: `vernesong/mihomo` `Alpha` at `2e80ed75`.
- eBPF comparison base: `TanakaLun/mihomo` `Alpha` at `e183c580`.
- eBPF feature snapshot: `TanakaLun/mihomo` `ebpf-inbound` at `19c7a3be`.

The port uses the final tree difference between the two eBPF commits instead
of replaying the feature branch commit history. That history contains duplicate
equivalent commits introduced by earlier merges.

## Deliberate exclusions

The standalone Android workflow and the automatic upstream-sync workflow from
the source fork are not included. They contain source-fork branch, version, and
updater assumptions that do not belong in the Smart branch. The reusable
eBPF build workflow remains, with its branch filters targeting `Alpha` and the
local port branch.

## Smart compatibility resolution

The Smart implementation restores `metadata.Host` into `dialMetadata` before
creating TCP and UDP statistic trackers. The eBPF DNS relay must avoid wrapping
its internal `C.Dns` connection in those trackers. The merged implementation
does both: it restores the host first, then creates a tracker only when the
selected proxy type is not `C.Dns`.

The Smart version format in the root `Makefile` is retained. The source fork's
`TanakaLun-` version prefix is intentionally omitted.

## Validation

Run ordinary regression checks first:

```sh
git diff --check
go vet ./...
go test ./...
```

On Linux, install Clang and the Linux UAPI headers before generating the BPF
objects and running the tagged tests:

```sh
make ebpf_generate
CGO_ENABLED=1 go test -count=1 -tags "with_gvisor with_ebpf" \
  ./common/ebpf/... ./listener/sing_ebpf/...
make linux-amd64-ebpf
```

Before a privileged runtime test, verify the target kernel and cgroup v2
environment:

```sh
bash common/ebpf/check-kernel.sh --mode all
```

See `docs/ebpf-inbound.md` for configuration, required capabilities, Android
notes, and privileged integration-test commands.

## Port validation status

The initial port was validated on 2026-08-13 with Go 1.26.0:

- `CGO_ENABLED=0 go test ./...` passed.
- `CGO_ENABLED=0 go vet ./...` passed.
- Linux AMD64 cross-compilation with `with_gvisor with_ebpf` and cgo disabled
  passed, exercising the unsupported-build stub and all integration points.
- The Linux/Android cgo backend, BPF object generation, kernel verifier, and
  privileged traffic tests remain the responsibility of the Linux CI workflow;
  they cannot run in the Windows development environment used for this port.

The combined repository was then validated by GitHub Actions run
[`31680555204`](https://github.com/mingxitang/mihomo_epbf_smart/actions/runs/31680555204)
on 2026-08-13. The full test suite, `go vet`, BPF object generation/checks,
tagged eBPF package tests, and cross-platform compile checks passed. The run
also produced verified eBPF binaries for Linux AMD64 v3, Linux ARM64, and
Android ARM64. The hosted-runner capability probe passed, but the privileged
traffic test itself was skipped because the runner did not expose the required
kernel/cgroup capabilities.

Downloaded artifacts are stored under the ignored local directory
`output/github-actions-31680555204/`; their SHA-256 digests match the checksum
files emitted by the workflow.

## UDP DNS binding lifetime fix

The combined branch fixes two races that could make `dns-mode: hijack` fail
while `dns-mode: off` continued to work:

- cached UDP packets now refresh the client activity timestamp, and the idle
  sweeper rechecks it under the table lock before deleting the client;
- the cgroup socket-release hook no longer deletes a connected port-53
  original-destination entry before the queued DNS response reaches userspace.
  Userspace retains that DNS entry and releases it through the configured
  `udp-timeout`. Connected non-DNS UDP entries keep the original immediate
  kernel cleanup behavior.

Regression tests cover activity refresh, the sweep recheck, ordinary idle
cleanup, connected DNS cleanup, and unchanged connected non-DNS cleanup. After
installing a fixed binary, restart mihomo and restore `dns-mode: hijack`; no
other configuration change is required.

## Automatic upstream synchronization

`.github/workflows/sync-upstreams.yml` checks both source forks every six
hours and can also be run manually. It uses `.github/upstream-state.json` as
the last successfully integrated baseline.

An upstream is synchronized only after both its source and its release output
show a material update:

- Smart: `vernesong/mihomo` `Alpha` must advance, the rolling
  `Prerelease-Alpha` release must change, and at least one asset name must
  contain the new `Alpha` commit's seven-character hash. This handles Smart's
  practice of replacing files in one long-lived release.
- eBPF: the latest `TanakaLun/mihomo` release must change and its tag must point
  to a newer commit in `ebpf-inbound`. Unreleased commits are not integrated.

Ready changes are merged into `Alpha`, the state file is committed, and the
`Build eBPF branch` workflow is dispatched. A clean scheduled check makes no
commit and starts no build. If histories diverge or a merge conflicts, the
workflow does not push a partial result and creates or updates an issue named
`[automation] Smart/eBPF upstream synchronization failed`.

The eBPF feature was originally tree-ported, so its initial state commit is
not an ancestor of this repository. On the first future eBPF release, the
workflow records that already-integrated snapshot with an `ours` merge before
merging only the newer released commits. Subsequent updates use ordinary
ancestry-based merges.

The installed workflow was manually validated by GitHub Actions run
[`31684389383`](https://github.com/mingxitang/mihomo_epbf_smart/actions/runs/31684389383).
With both recorded baselines current, detection succeeded while merge, push,
and build dispatch were correctly skipped.
