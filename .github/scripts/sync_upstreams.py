"""Synchronize upstream snapshots in a disposable checkout; no third-party modules."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

STATE = ".github/upstream-state.json"
TARGETS = ("Alpha", "codex/ebpf-next")
SOURCES = {
    "smart": ("vernesong/mihomo", "Alpha"),
    "ebpf": ("TanakaLun/mihomo", "ebpf-inbound"),
    "ebpf_next": ("TanakaLun/mihomo", "ebpf-inbound"),
}
MAPPED = ("common/ebpf/", "listener/sing_ebpf/", "listener/config/ebpf.go")


def run(*args, cwd=None, data=None, check=True):
    result = subprocess.run(args, cwd=cwd, input=data, capture_output=True)
    if check and result.returncode:
        raise RuntimeError(result.stderr.decode(errors="replace") or result.stdout.decode(errors="replace"))
    return result


def git(repo, *args, data=None, check=True):
    return run("git", *args, cwd=repo, data=data, check=check)


def text(repo, *args):
    return git(repo, *args).stdout.decode().strip()


def blob(repo, ref, path):
    entry = git(repo, "ls-tree", "-z", ref, "--", path).stdout
    if not entry:
        return None, None
    meta, name = entry.rstrip(b"\0").split(b"\t", 1)
    mode, kind, sha = meta.decode().split()
    if name.decode() != path or kind != "blob" or mode not in ("100644", "100755"):
        raise ValueError("unsupported file type: " + path)
    return mode, git(repo, "cat-file", "blob", sha).stdout


def mapped_path(path):
    if path.startswith(MAPPED[:2]) or path == MAPPED[2]:
        return "experimental/tanaka/" + path
    return None


def remap(data):
    if data is None or b"\0" in data:
        return data
    for path in (b"common/ebpf", b"listener/config", b"listener/sing_ebpf"):
        data = data.replace(b"github.com/metacubex/mihomo/" + path,
                            b"github.com/metacubex/mihomo/experimental/tanaka/" + path)
    return data


def merge_value(old, local, new):
    if local == old or local == new:
        return new
    if new == old:
        return local
    raise ValueError("both upstream and downstream changed")


def merge_content(path, old, local, new):
    try:
        return merge_value(old, local, new)
    except ValueError:
        pass
    if None in (old, local, new) or any(b"\0" in value for value in (old, local, new)):
        raise ValueError("conflicting add/delete or binary change")
    # Go formatting is safe to normalize; never ignore whitespace in YAML/Python.
    if path.endswith(".go"):
        old, local, new = (run("gofmt", data=value).stdout for value in (old, local, new))
        try:
            return merge_value(old, local, new)
        except ValueError:
            pass
    with tempfile.TemporaryDirectory() as directory:
        files = [Path(directory) / name for name in ("local", "base", "upstream")]
        for file, data in zip(files, (local, old, new)):
            file.write_bytes(data)
        result = run("git", "merge-file", "-p", *map(str, files), check=False)
    if result.returncode:
        raise ValueError("overlapping text edits")
    return result.stdout


def plan_snapshot(repo, old, new, mapped=False):
    paths = git(repo, "diff", "--name-only", "--no-renames", "-z", old, new).stdout
    edits, conflicts = [], []
    for raw in filter(None, paths.split(b"\0")):
        source = raw.decode()
        destination = mapped_path(source) if mapped else source
        # Repository-specific CI, documentation and branding are not ported.
        if mapped and destination is None and (
            source.startswith((".github/", "docs/")) or
            source in ("README.md", "Meta.png", "LICENSE", ".gitignore")
        ):
            continue
        destination = destination or source
        try:
            old_mode, old_data = blob(repo, old, source)
            new_mode, new_data = blob(repo, new, source)
            local_mode, local_data = blob(repo, "HEAD", destination)
            if mapped_path(source) and mapped:
                old_data, new_data = remap(old_data), remap(new_data)
            mode = merge_value(old_mode, local_mode, new_mode)
            data = merge_content(destination, old_data, local_data, new_data)
            if mapped and mapped_path(source) is None:
                if (mode, data) != (local_mode, local_data):
                    raise ValueError("change outside mapped paths needs manual integration")
                continue
            if (mode, data) != (local_mode, local_data):
                # Reject symlink parents and file/directory collisions before writing.
                file = repo / destination
                if repo.resolve() not in file.resolve().parents or file.is_dir():
                    raise ValueError("unsafe destination")
                if any(parent.is_symlink() for parent in (file, *file.parents) if parent != repo.parent):
                    raise ValueError("symlink destination")
                edits.append((destination, mode, data))
        except (ValueError, RuntimeError) as error:
            conflicts.append({"path": destination, "reason": str(error)})
    return edits, conflicts


def commit_snapshot(repo, state, key, candidate, edits):
    for path, mode, data in edits:
        file = repo / path
        if data is None:
            file.unlink()
        else:
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(data)
            file.chmod(0o755 if mode == "100755" else 0o644)
    state[key].update(candidate)
    (repo / STATE).write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    git(repo, "add", "-A")
    # Explicitly preserve executable bits on Windows as well.
    for path, mode, data in edits:
        if data is not None:
            git(repo, "update-index", "--chmod=" + ("+x" if mode == "100755" else "-x"), "--", path)
    parent = text(repo, "rev-parse", "HEAD")
    args = ["commit-tree", text(repo, "write-tree"), "-p", parent]
    if key != "ebpf_next" and candidate["commit"] != parent:
        args += ["-p", candidate["commit"]]
    commit = text(repo, *args, "-m", "sync: integrate " + key + " " + candidate["commit"][:12])
    git(repo, "update-ref", "HEAD", commit, parent)
    return commit


def relation(repo, old, new):
    if old == new:
        return "unchanged"
    if git(repo, "merge-base", "--is-ancestor", old, new, check=False).returncode == 0:
        return "forward"
    if git(repo, "merge-base", "--is-ancestor", new, old, check=False).returncode == 0:
        return "rewind"
    return "rewritten"


class NotReady(ValueError):
    pass


def release_marker(release):
    assets = release.get("assets", [])
    if release.get("draft") or not assets or any(a.get("state") != "uploaded" for a in assets):
        raise NotReady("release assets are not ready")
    return "|".join((release["tag_name"], release["updated_at"],
                     max(a["updated_at"] for a in assets), str(len(assets))))


def candidate(repo, key):
    repository, branch = SOURCES[key]
    url = "https://github.com/" + repository + ".git"
    ref = "refs/remotes/sync-" + key
    git(repo, "fetch", "--no-tags", "--force", url, "refs/heads/" + branch + ":" + ref)
    sha = text(repo, "rev-parse", ref)
    if key == "ebpf_next":
        return {"commit": sha}
    endpoint = ("releases/tags/Prerelease-Alpha" if key == "smart" else "releases/latest")
    release = json.loads(run("gh", "api", "repos/" + repository + "/" + endpoint).stdout)
    marker = release_marker(release)
    if key == "smart":
        if not any(sha[:7] in asset["name"] for asset in release["assets"]):
            raise NotReady("Smart branch head does not yet have matching release assets")
    else:
        tag = release["tag_name"]
        git(repo, "check-ref-format", "refs/tags/" + tag)
        tag_ref = "refs/remotes/sync-ebpf-release"
        git(repo, "fetch", "--no-tags", "--force", url, "refs/tags/" + tag + ":" + tag_ref)
        released = text(repo, "rev-parse", tag_ref + "^{commit}")
        if git(repo, "merge-base", "--is-ancestor", released, sha, check=False).returncode:
            raise ValueError("eBPF release is outside the tracked branch")
        sha = released
    return {"commit": sha, "release_tag": release["tag_name"], "release_marker": marker}


def prepare(repo, target, report):
    if text(repo, "status", "--porcelain"):
        raise ValueError("prepare requires a clean disposable checkout")
    state = json.loads((repo / STATE).read_text(encoding="utf-8-sig"))
    keys = ("smart", "ebpf_next" if target == "codex/ebpf-next" else "ebpf")
    for key in keys:
        entry = state[key]
        if (entry["repository"], entry["branch"]) != SOURCES[key] or not re.fullmatch(r"[0-9a-f]{40}", entry["commit"]):
            raise ValueError("invalid upstream state: " + key)
    report.update(base=text(repo, "rev-parse", "HEAD"), sources=[], changed=False)
    git(repo, "config", "user.name", "github-actions[bot]")
    git(repo, "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    for key in keys:
        item = {"source": key, "old": state[key]["commit"]}
        report["sources"].append(item)
        try:
            selected = candidate(repo, key)
            item["candidate"] = selected["commit"]
            if git(repo, "cat-file", "-e", item["old"] + "^{commit}", check=False).returncode:
                git(repo, "fetch", "--no-tags", "https://github.com/" + SOURCES[key][0] + ".git", item["old"])
            item["relation"] = relation(repo, item["old"], selected["commit"])
            if item["relation"] == "unchanged":
                item["status"] = "unchanged"
                continue
            if item["relation"] == "rewind":
                raise ValueError("upstream rewind; baseline was not changed")
            edits, conflicts = plan_snapshot(repo, item["old"], selected["commit"], key == "ebpf_next")
            if conflicts:
                item.update(status="blocked", conflicts=conflicts)
                continue
        except NotReady as error:
            item.update(status="waiting", error=str(error))
            continue
        except ValueError as error:
            item.update(status="blocked", error=str(error))
            continue
        except RuntimeError as error:
            item.update(status="blocked", error=str(error))
            continue
        # Write only after the entire source snapshot has merged without conflicts.
        commit_snapshot(repo, state, key, selected, edits)
        item["status"] = "integrated"
        report["changed"] = True
    report["head"] = text(repo, "rev-parse", "HEAD")


def promote(repo, report):
    target, base, head = report["target"], report["base"], report["head"]
    if target not in TARGETS or not all(re.fullmatch(r"[0-9a-f]{40}", s) for s in (base, head)):
        raise ValueError("invalid promotion target")
    if text(repo, "rev-parse", "HEAD") != head or text(repo, "status", "--porcelain"):
        raise ValueError("validation changed the candidate checkout")
    remote = text(repo, "ls-remote", "origin", "refs/heads/" + target).split()
    if not remote or remote[0] != base:
        raise ValueError("target branch moved during validation; rerun synchronization")
    # A normal fast-forward push also protects against a race after ls-remote.
    git(repo, "push", "origin", head + ":refs/heads/" + target)


def save_report(repo, report, directory):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if "base" in report:
        (directory / "candidate.patch").write_bytes(git(repo, "diff", "--binary", report["base"], "HEAD").stdout)
    for item in report.get("sources", []):
        if item.get("status") == "blocked" and item.get("candidate"):
            patch = git(repo, "diff", "--binary", item["old"], item["candidate"], check=False)
            (directory / (item["source"] + "-upstream.patch")).write_bytes(patch.stdout)
    lines = ["# Upstream synchronization: " + report["target"], "",
             "| Source | Previous | Candidate | Result |", "| --- | --- | --- | --- |"]
    for item in report.get("sources", []):
        lines.append(f"| {item['source']} | {item['old']} | {item.get('candidate', '-')} | {item.get('status', 'failed')} |")
        if item.get("error"):
            lines += ["", item["source"] + ": " + item["error"]]
        for conflict in item.get("conflicts", []):
            lines += ["", "- " + conflict["path"] + ": " + conflict["reason"]]
    if report.get("error"):
        lines += ["", report["error"]]
    lines += ["", "Diagnostics and candidate.patch are attached to this workflow run.",
              "Failed sources retain their previous baseline; successful sources can proceed independently."]
    summary = "\n".join(lines) + "\n"
    (directory / "summary.md").write_text(summary, encoding="utf-8")
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as file:
            file.write(summary)
    if os.getenv("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as file:
            file.write("changed=" + str(report.get("changed", False)).lower() + "\n")
            file.write("waiting=" + str(any(s.get("status") == "waiting" for s in report.get("sources", []))).lower() + "\n")
            file.write("blocked=" + str(any(s.get("status") == "blocked" for s in report.get("sources", [])) or "error" in report).lower() + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "promote"))
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--target", choices=TARGETS, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = {"target": args.target}
    try:
        if args.action == "prepare":
            prepare(args.repo.resolve(), args.target, report)
        else:
            report = json.loads((args.report / "result.json").read_text(encoding="utf-8"))
            if report["target"] != args.target:
                raise ValueError("report target mismatch")
            promote(args.repo.resolve(), report)
    except (RuntimeError, ValueError, KeyError) as error:
        report["error"] = str(error)
        save_report(args.repo, report, args.report)
        raise SystemExit(str(error))
    save_report(args.repo, report, args.report)


if __name__ == "__main__":
    main()

