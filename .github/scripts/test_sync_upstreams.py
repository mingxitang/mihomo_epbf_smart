import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import sync_upstreams as sync


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / "work"
        self.repo.mkdir()
        sync.git(self.repo, "init", "-b", "local")
        sync.git(self.repo, "config", "user.name", "test")
        sync.git(self.repo, "config", "user.email", "test@example.invalid")
        sync.git(self.repo, "config", "core.autocrlf", "false")
        sync.git(self.repo, "config", "commit.gpgsign", "false")
        sync.git(self.repo, "commit", "--allow-empty", "-m", "initial")
        self.base = sync.text(self.repo, "rev-parse", "HEAD")

    def write(self, files):
        for name, data in files.items():
            file = self.repo / name
            if data is None:
                file.unlink()
            else:
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(data.encode() if isinstance(data, str) else data)

    def commit(self, files):
        self.write(files)
        sync.git(self.repo, "add", "-A")
        sync.git(self.repo, "commit", "--allow-empty", "-m", "fixture")
        return sync.text(self.repo, "rev-parse", "HEAD")

    def upstream(self, files, base=None):
        current = sync.text(self.repo, "rev-parse", "HEAD")
        sync.git(self.repo, "checkout", "--detach", base or self.base)
        sha = self.commit(files)
        sync.git(self.repo, "checkout", "local")
        self.assertEqual(current, sync.text(self.repo, "rev-parse", "HEAD"))
        return sha

    def state(self, smart=None, ebpf=None):
        data = {
            key: {"repository": sync.SOURCES[key][0], "branch": sync.SOURCES[key][1],
                  "commit": sha or self.base}
            for key, sha in (("smart", smart), ("ebpf_next", ebpf))
        }
        self.commit({sync.STATE: json.dumps(data)})
        return data

    def test_mapped_edits_preserve_local_fix_and_rewrite_imports(self):
        path = "common/ebpf/backend.txt"
        old = b'import "github.com/metacubex/mihomo/common/ebpf"\n\nupstream=old\n\nlocal=old\n'
        self.base = self.commit({path: old})
        self.commit({"experimental/tanaka/" + path: sync.remap(old).replace(b"local=old", b"local=fixed")})
        new = self.upstream({path: old.replace(b"upstream=old", b"upstream=new")})
        edits, conflicts = sync.plan_snapshot(self.repo, self.base, new, mapped=True)
        self.assertEqual([], conflicts)
        self.assertEqual(1, len(edits))
        self.assertEqual("experimental/tanaka/" + path, edits[0][0])
        self.assertIn(b"local=fixed", edits[0][2])
        self.assertIn(b"upstream=new", edits[0][2])
        self.assertIn(b"mihomo/experimental/tanaka/common/ebpf", edits[0][2])

    def test_overlapping_edit_is_reported_without_writing(self):
        self.base = self.commit({"file.txt": "base\n"})
        self.commit({"file.txt": "local fix\n"})
        new = self.upstream({"file.txt": "upstream change\n"})
        before = sync.text(self.repo, "rev-parse", "HEAD")
        edits, conflicts = sync.plan_snapshot(self.repo, self.base, new)
        self.assertFalse(edits)
        self.assertEqual("file.txt", conflicts[0]["path"])
        self.assertEqual(before, sync.text(self.repo, "rev-parse", "HEAD"))
        self.assertEqual("local fix\n", (self.repo / "file.txt").read_text())

    def test_binary_update_and_conflict(self):
        self.assertEqual(b"\0new", sync.merge_content("a.o", b"\0old", b"\0old", b"\0new"))
        with self.assertRaises(ValueError):
            sync.merge_content("a.o", b"\0old", b"\0local", b"\0new")

    def test_add_delete_conflict_and_duplicate_update(self):
        self.assertEqual(b"new", sync.merge_content("a", None, None, b"new"))
        self.assertIsNone(sync.merge_content("a", b"old", b"old", None))
        self.assertEqual(b"new", sync.merge_content("a", b"old", b"new", b"new"))
        with self.assertRaises(ValueError):
            sync.merge_content("a", b"old", b"local fix", None)
        with self.assertRaises(ValueError):
            sync.merge_content("a", None, b"local file", b"upstream file")

    @unittest.skipUnless(shutil.which("gofmt"), "gofmt required")
    def test_go_formatting_does_not_create_false_conflict(self):
        old = b"package x\nvar x=1\n"
        local = b"package x\n\nvar x = 1\n"
        new = b"package x\nvar x=2\n"
        self.assertEqual(b"package x\n\nvar x = 2\n", sync.merge_content("x.go", old, local, new))

    def test_python_whitespace_remains_significant(self):
        with self.assertRaises(ValueError):
            sync.merge_content("x.py", b"if a:\n x=1\n", b"if a:\n  x=1\n", b"if a:\n x=2\n")

    def test_ebpf_external_code_requires_manual_integration(self):
        self.base = self.commit({"listener/inbound/ebpf.go": "package x\n"})
        new = self.upstream({"listener/inbound/ebpf.go": "package x\nvar newOption = true\n"})
        edits, conflicts = sync.plan_snapshot(self.repo, self.base, new, mapped=True)
        self.assertFalse(edits)
        self.assertIn("outside mapped paths", conflicts[0]["reason"])

    def test_already_integrated_core_changes_are_not_ported_again(self):
        self.base = self.commit({"go.mod": "base\n"})
        new = self.upstream({"go.mod": "new dependency\n"})
        self.commit({"go.mod": "new dependency\n"})
        edits, conflicts = sync.plan_snapshot(self.repo, self.base, new, mapped=True)
        self.assertEqual(([], []), (edits, conflicts))

    def test_release_readiness(self):
        release = {"tag_name": "v1", "updated_at": "t1", "draft": False,
                   "assets": [{"name": "binary", "state": "uploaded", "updated_at": "t2"}]}
        self.assertEqual("v1|t1|t2|1", sync.release_marker(release))
        for incomplete in ({**release, "assets": []}, {**release, "draft": True},
                           {**release, "assets": [{"state": "new"}]}):
            with self.assertRaises(sync.NotReady):
                sync.release_marker(incomplete)

    def test_rewind_and_rewritten_history(self):
        forward = self.commit({"forward": "one"})
        rewritten = self.upstream({"rewritten": "two"})
        self.assertEqual("forward", sync.relation(self.repo, self.base, forward))
        self.assertEqual("rewind", sync.relation(self.repo, forward, self.base))
        self.assertEqual("rewritten", sync.relation(self.repo, forward, rewritten))

    def test_independent_source_progress_and_idempotency(self):
        self.base = self.commit({"smart.txt": "base\n", "common/ebpf/policy.txt": "base\n"})
        smart = self.upstream({"smart.txt": "upstream\n"})
        ebpf = self.upstream({"common/ebpf/policy.txt": "new policy\n"})
        self.commit({"smart.txt": "local fix\n", "experimental/tanaka/common/ebpf/policy.txt": "base\n"})
        state = self.state()
        candidates = {"smart": {"commit": smart}, "ebpf_next": {"commit": ebpf}}
        with patch.object(sync, "candidate", side_effect=lambda repo, key: candidates[key]):
            result = {"target": "codex/ebpf-next"}
            sync.prepare(self.repo, "codex/ebpf-next", result)
            self.assertEqual(["blocked", "integrated"], [x["status"] for x in result["sources"]])
            stored = json.loads((self.repo / sync.STATE).read_text())
            self.assertEqual(state["smart"], stored["smart"])
            self.assertEqual(ebpf, stored["ebpf_next"]["commit"])
            self.assertEqual("local fix\n", (self.repo / "smart.txt").read_text())
            self.assertEqual("new policy\n", (self.repo / "experimental/tanaka/common/ebpf/policy.txt").read_text())
            before = sync.text(self.repo, "rev-parse", "HEAD")
            again = {"target": "codex/ebpf-next"}
            sync.prepare(self.repo, "codex/ebpf-next", again)
            self.assertFalse(again["changed"])
            self.assertEqual(before, again["head"])
            directory = Path(self.temp.name) / "report"
            with patch.dict(os.environ, {k: v for k, v in os.environ.items() if k not in ("GITHUB_OUTPUT", "GITHUB_STEP_SUMMARY")}, clear=True):
                sync.save_report(self.repo, result, directory)
            self.assertTrue((directory / "smart-upstream.patch").exists())
            self.assertTrue((directory / "candidate.patch").exists())

    def test_smart_merge_records_upstream_parent(self):
        self.base = self.commit({"a.txt": "old"})
        new = self.upstream({"a.txt": "new"})
        state = self.state()
        edits, conflicts = sync.plan_snapshot(self.repo, self.base, new)
        self.assertFalse(conflicts)
        commit = sync.commit_snapshot(self.repo, state, "smart", {"commit": new}, edits)
        self.assertIn(new, sync.text(self.repo, "show", "-s", "--format=%P", commit).split())
        self.assertFalse(sync.text(self.repo, "status", "--porcelain"))

    def test_promotion_refuses_target_that_moved(self):
        remote = Path(self.temp.name) / "remote.git"
        sync.run("git", "init", "--bare", str(remote))
        sync.git(self.repo, "remote", "add", "origin", str(remote))
        sync.git(self.repo, "push", "origin", "HEAD:refs/heads/Alpha")
        base = sync.text(self.repo, "rev-parse", "HEAD")
        head = self.commit({"candidate": "validated"})
        result = {"target": "Alpha", "base": base, "head": head}
        # Simulate another writer updating the target while CI was running.
        other = self.upstream({"other": "user change"}, base=base)
        sync.git(self.repo, "push", "origin", other + ":refs/heads/Alpha")
        with self.assertRaisesRegex(ValueError, "moved"):
            sync.promote(self.repo, result)
        self.assertEqual(other, sync.text(self.repo, "ls-remote", "origin", "refs/heads/Alpha").split()[0])

    def test_promotion_fast_forwards_local_bare_remote(self):
        remote = Path(self.temp.name) / "remote.git"
        sync.run("git", "init", "--bare", str(remote))
        sync.git(self.repo, "remote", "add", "origin", str(remote))
        sync.git(self.repo, "push", "origin", "HEAD:refs/heads/Alpha")
        base = sync.text(self.repo, "rev-parse", "HEAD")
        head = self.commit({"candidate": "validated"})
        sync.promote(self.repo, {"target": "Alpha", "base": base, "head": head})
        self.assertEqual(head, sync.text(self.repo, "ls-remote", "origin", "refs/heads/Alpha").split()[0])


if __name__ == "__main__":
    unittest.main()
