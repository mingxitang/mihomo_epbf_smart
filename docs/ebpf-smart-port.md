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
