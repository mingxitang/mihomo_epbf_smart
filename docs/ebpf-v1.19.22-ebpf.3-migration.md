# eBPF v1.19.22-ebpf.3 migration

## Post-migration correctness fixes

- Local interface addresses are stored only in the dedicated host-address
  maps as exact IPv4 `/32` or IPv6 `/128` entries.
- `bypass-rule-set` CIDRs are stored only in the bypass LPM maps. An interface
  such as `192.168.1.5/24` no longer bypasses the whole `192.168.1.0/24`
  subnet unless a rule set requests it.
- Shared-network attachments are reconciled per interface, verified against
  kernel TC state, and repaired without disabling healthy interfaces.
- Downstream `arp_announce` is raised while shared-network interception is
  active and restored on detach, preventing redirected `127.x` sources from
  poisoning ARP resolution.
- TCX cleanup retries are bounded to avoid an unbounded file-descriptor leak.
- TCP and UDP statistic tracker shutdown is idempotent.
- Cgroup TCP redirect, UDP redirect, UDP token, and UDP peer maps are bounded
  LRU maps. Independent eviction is validated before cached state is reused.
- The periodic inbound maintenance loop sweeps stale TCP and UDP redirects in
  bounded batches, preventing permanent exhaustion and later `EPERM` failures.
- Connected UDP recovery validates token/peer ownership, retains recoverable
  state across failed recovery writes, and bounds reverse token scans.

## Target

The migration branch `migration/ebpf-v1.19.22-ebpf.3` combines:

- Smart `Alpha` at `5664b1ba0943206e0fa140eb0f31f393688b0c2d`;
- eBPF release `v1.19.22-ebpf.3` at
  `0c8987595fa2d4466681353bc92111b1f1fa584c`;
- Go module baseline 1.25.0 and default CI/release toolchain Go 1.26.

## Architecture change

The eBPF runtime no longer uses the cgo/C loader boundary. Loading, maps,
cgroup attachment, kernel feature probes, runtime status, and TCX/clsact
selection now use `github.com/cilium/ebpf` from Go. Generated little- and
big-endian BPF bindings and objects live under `common/ebpf/internal/bpfgen`.
Shared-network attachment prefers TCX and falls back to clsact.

The listener configuration and lifecycle use the new nested local/shared
schema. The migration retains the combined repository's UDP timeout unit fix;
the new upstream UDP recovery map replaces the earlier DNS-only
socket-release workaround.

## Build and CI

- `go.mod` and `test/go.mod` require Go 1.25.0.
- General tests run on Go 1.25 and 1.26.
- General and eBPF release builds use Go 1.26.
- eBPF builds and tests run with `CGO_ENABLED=0`; old NDK/cross-C-compiler and
  sing-tun patch steps are no longer part of the eBPF build path.
- The obsolete `common/ebpf/check-kernel.sh` workflow call was removed. The
  privileged job now runs the new pure-Go integration suite directly. It uses
  the absolute `setup-go` binary path across `sudo`; hosted-runner capability
  failures are advisory and do not block the Android release.
- The automated build/release target is Android ARM64. Linux and other
  platforms remain test or compile checks, but are not published by this
  release pipeline. The artifact and released binary are both named `mihomo`;
  its checksum is `mihomo.sha256`.
- Upstreams are checked at 00:23 UTC every third calendar day. A released
  upstream change triggers the Android build and prerelease automatically;
  manual synchronization defaults to forcing the same pipeline even when the
  upstream state is unchanged.

## Synchronization baseline

`.github/upstream-state.json` records the Smart and eBPF commits and their
current release markers. Future automation must compare from this baseline;
it must not treat `.2` as still integrated.
Because the migration is a tree-port, its recorded Smart snapshot is initially
not a Git ancestor of the combined branch. The first released Smart update
records that snapshot with an `ours` merge before integrating later changes;
the marker changes commit topology only, not the migrated work tree.

## Alpha integration

Merged into the updated `Alpha` baseline on 2026-08-22. Conflict resolution
kept the migration branch's Smart `5664b1ba` and eBPF `.3` state, its newer
`mipstack` dependency, and the OpenVPN `IV_PROTO=22` capability advertisement
with the matching tests. The Smart constant conflict was formatting-only.

The first Alpha release run exposed that `gh run download --name mihomo`
extracts the named artifact contents directly into the requested directory.
The release workflow now downloads into `artifacts/mihomo`, matching its
`dist/mihomo` verification path and reporting the discovered files on failure.

## Validation status

Validated locally on 2026-08-20 with official Go 1.26.5:

- [x] `gofmt` on every changed Go source file;
- [x] `go vet` across all Git-tracked source package roots;
- [x] default unit tests across all Git-tracked source package roots;
- [x] Linux AMD64 tagged test binaries compile for `common/ebpf` and
  `listener/sing_ebpf`, including the integration-test build tag;
- [x] generated eBPF bindings and objects are byte-identical to the `.3` tag;
- [x] Linux AMD64 v3, Linux ARM64, and Android ARM64 eBPF builds;
- [x] release-shaped Android ARM64 build named `mihomo`, stripped to
  55,574,788 bytes (53.0 MiB);
- [x] non-eBPF Windows AMD64, macOS ARM64, and Linux AMD64 builds;
- [x] all seven GitHub workflow YAML files parse successfully;
- [ ] privileged Linux eBPF integration tests.

The local Windows host cannot execute the compiled Linux tests and access to
WSL is denied. GitHub-hosted runners also do not guarantee the required kernel
and cgroup capabilities, so the privileged suite remains a target-device gate
rather than an Android artifact publication gate.

The generated-object check uses stable Android NDK r29 (Clang 21), matching
the version guard in `common/ebpf/Makefile`. The older `r29-beta1` workflow
input is incompatible with that reproducible generation contract.

GitHub Actions run
[`32347359334`](https://github.com/mingxitang/mihomo_epbf_smart/actions/runs/32347359334)
validated the ordinary tests, tagged eBPF package tests, generated objects,
cross-platform compilation, and the Android ARM64 `mihomo` artifact. Its first
attempt also exposed that `sudo` selected the runner's Go 1.24.13 instead of
the configured Go 1.26; the workflow now passes the absolute configured Go
binary and treats host capability failures as advisory.
