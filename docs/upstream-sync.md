# Upstream synchronization

The `sync-upstreams.yml` workflow tracks released Smart and eBPF snapshots in
`.github/upstream-state.json`. It merges a snapshot only after the matching
release assets are available, then dispatches `build-ebpf.yml`.

## Resolving an integration conflict

When the workflow reports a merge conflict, merge the reported Smart or eBPF
commit into `Alpha` locally, resolve the listed files, and run the same checks
as `build-ebpf.yml`. Keep both upstreams' behavior when their changes are
independent. For `go.mod` and `go.sum`, use the merged source tree as the source
of truth and run `go mod tidy` instead of hand-maintaining indirect modules.

After validation, update the corresponding commit and release marker in
`.github/upstream-state.json` before pushing `Alpha`. A successful push starts
the build workflow; the synchronization failure issue is closed by the next
successful synchronization run.

Keep validation and release workflows in separate concurrency groups so a
push-triggered validation run cannot cancel the release build.
