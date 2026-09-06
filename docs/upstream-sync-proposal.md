# 同步工作流改进草案（待远端自动化授权）

状态：本地脚本和未应用补丁已完成；现有 .github/workflows/sync-upstreams.yml 和 GitHub 远端尚未修改。

## 改进内容

- Alpha 保持发布版 Smart/eBPF 策略；codex/ebpf-next 单独跟踪新版 eBPF 分支。
- 三方快照合并并保留上下游独立修改，Go 格式冲突可自动消解；真正冲突不猜测处理。
- 新版 eBPF 自动映射 common/ebpf、listener/sing_ebpf、listener/config/ebpf.go；其他代码变化如未被本地覆盖则报告人工处理。
- 每个上游独立成功/失败，只有成功集成的快照才推进状态。
- 候选提交先通过测试、vet、特权测试编译、BPF 生成检查和 Android 构建，之后才推进未发生变化的目标分支。
- dry_run 不推送分支、不维护 Issue、不触发发布；普通模式复用分支级失败 Issue，保留失败候选和补丁诊断。
- Alpha 成功后显式触发现有发布流程；实验分支不作为 Alpha 发布。

## 验证

- 14 项本地测试通过，使用临时 Git 仓库和本地 bare remote，没有 GitHub 写入。
- 工作流草案 YAML 解析和全部内联 Shell 的 bash -n 检查通过。
- 两份补丁分别对当前 Alpha 和 codex/ebpf-next 通过 git apply --check；未实际应用。
- 用之前的实际上游提交离线回放：Smart 的 10 个文件自动合并；eBPF 的 28 个文件可合并，但初始化代码存在一处真实冲突，因此整组 eBPF 变更未写入，原 UDP 超时修复得到保留。
- 尚未运行新版 GitHub 工作流，因为安装被自动审批阻止。

## 可审阅文件

- 工作流草案：../output/sync-upstreams-proposed.yml
- 实验分支完整补丁：../output/sync-workflow-next.patch
- Alpha 完整补丁：../output/sync-workflow-alpha.patch
- 操作说明草案：../output/upstream-sync-proposed.md
- 验证结果：../output/sync-workflow-validation.json

Alpha 补丁保留其原有发布基线，并包含已确认的旧特权测试 API 修正。实验分支补丁新增 ebpf_next=e88bb8c6 基线。不能把实验分支的整个状态文件覆盖到 Alpha。

## 部署前需要确认

自动审批拒绝了安装新版持续自动化，要求明确授权：定期自动推送/更新 Alpha 和 codex/ebpf-next、创建和清理候选分支、维护同步 Issue，并在 Alpha 验证成功后触发现有构建发布流程。部署前只保留可审阅草案，不绕过此阻止。
