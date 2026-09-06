# 两个上游差异核查（2026-09-06）

> 本文表格为同步前快照。后续合并进展见文末，避免将历史缺口当作当前状态。

## 基线与方法

- 本地：`codex/ebpf-next`，`c28b1080`；核查前工作区干净。
- Smart：`vernesong/mihomo` 的 `Alpha`，在线 fetch 后为 `4bc3d49f`；本地已同步基线 `86ece769`。
- eBPF：`TanakaLun/mihomo` 的 `ebpf-inbound`，在线 fetch 后为 `e88bb8c6`。
- 旧 `type: ebpf` 为 `.3` 迁移路线，含下游修复；实验 `type: ebpf-next` 已搬入 `e3256f2f` 的统一后端。
- 结合提交差异、本地实现、实验目录映射和 CI 配置核查；不把提交祖先缺失直接等同于功能缺失。两个上游共同继承的核心修复只计一次。
- 本报告针对上述分支头，不表示这些变更均已有正式发布。未运行设备流量测试，也未更改功能代码。

## 确认缺失：Smart 与共同核心

| 项目 | 缺少的行为与影响 | 上游提交 |
| --- | --- | --- |
| 节点尝试顺序 | 前三个候选逐个尝试，再进入每批五个的并发拨号；重试上限由 3 变 5，避免过早竞速选中其他节点 | `69423f04` |
| 选路缓存稳定性 | 合并同一目标/ASN/协议的并发计算；缓存未过期时避免覆盖；非 CDN ASN 优先复用；成功切换时明确更新胜出节点，退化时删除缓存 | `69423f04` |
| 候选排序 | 去除候选过少时的随机打散，有权重时不再额外插入前置节点 | `69423f04` |
| 并发正确性 | 健康检查使用 CAS 防止重复启动，失败计数加锁，回调移出计数锁；hostFailLimit 原子访问，异步统计克隆 metadata | `69423f04` |
| 异常统计与封禁 | 洪泛抑制触发时清理待写入异常记录及相关缓存，抑制期间暂停稳定性检查；修正等级持续较差时反复封禁的条件 | `69423f04` |
| 切换关闭连接的范围 | 增加 ASN 匹配约束，降低关闭不相关连接的风险；取消后的拨号不再录入部分失败统计 | `69423f04` |
| Hysteria v1 UDP | DialUDP 请求仍错误设置 UDP=false；封包缓冲区仍以非零长度初始化，导致前置零字节 | `0159cf47` |
| Hysteria2 UDP | sing-quic 依赖尚未更新至连接关闭时清理 UDP 会话的版本 | `634b3199` |
| TrustTunnel 建连 | 当前提前返回连接；上游改为等待底层 TCP 建立，并传递建连错误及取消 | `fd74ecb6` |
| mipstack 背压 | 缺少设备背压处理改进的依赖更新：`dc187ebcbdc7` → `c7e60ae7a02a` | `2ecceb5b` |
| 发布流程 | update-tag action 仍为 v1，上游已升级 v3 | `810b014e` |

主要证据：`adapter/outboundgroup/{smart,groupbase}.go`、`component/smart/{common,memory}.go`、`transport/hysteria/core/{client,protocol}.go`、`transport/trusttunnel/client.go`、`go.mod`。

## 确认缺失：实验 ebpf-next

| 项目 | 本地情况与缺失内容 | 上游提交 |
| --- | --- | --- |
| cgroup 劫持 UDP DNS 回包 | relayUDPDNS 仍无条件使用 TC 透明回复 socket；缺少按客户端数据平面选择 cgroup 回写的 writeUDPReply。上游举例为绑定 `[fe80::1]:53` 失败导致 DNS 无应答 | `4b01610b` |
| bypass-rule-set 全后端下发 | refreshBypassCIDRsLocked 只更新 TC，TC 后端为空即返回；cgroup 和 shared packet_rewrite 缺少旁路 CIDR 写入及共享路径策略缓存 | `e88bb8c6` |
| 统一策略快照 | 缺少 CompilePolicy/CompiledPolicy、统一策略向量及各后端的对应 API 接入 | `77cad549`、`94bad6ea` |
| Fake-IP 策略集中实现 | 缺少新的共享内核策略头文件和统一编码；不是完全没有 Fake-IP 强制拦截功能 | `77cad549` |
| 共享流清理 | 缺少事件/压力驱动的有界孤立流扫描更新 | `77cad549` |
| TCX 与 sysctl 生命周期 | 缺少先挂新链路再拆旧链路的角色切换、保留外部修改的 sysctl 恢复、全局 rp_filter 与 delivery 接口策略协调和重建交接 | `94bad6ea` |

主要证据位于 `experimental/tanaka/listener/sing_ebpf` 和 `experimental/tanaka/common/ebpf`。这些补丁针对新版架构，不能据此断言旧 `ebpf` 存在完全相同的故障，也不应直接覆盖旧目录。

`94bad6ea` 增加启用配置解码测试，但 `mode` 与 `local.enabled/shared.enabled` 字段及选择逻辑在本地实验版已经存在，不应误报为全新缺失功能。

## 已有，但只在实验入口

以下已在 `ebpf-next`，旧 `ebpf` 的配置与后端尚未具备同等接口：

- local 选择 cgroup 或 TC，shared 选择 packet_rewrite 或 socket_assign，统一接入监听与回包流程。
- local/shared 独立 enabled、DNS 模式、IPv6、私网旁路配置。
- local/shared 的 bypass-port、bypass-port-range。

所以使用旧 `type: ebpf` 时，不能认为这些功能已随实验目录加入而自动启用。实验说明见 `docs/ebpf-next.md`。

## 本地额外修复与同步边界

- 保留实验版 UDP 超时秒单位转换及范围校验；最新上游 inbound.go 仍直接把配置整数转为 time.Duration。
- 保留本地 Fake-IP 前缀同步存储、离开 Fake-IP 模式时清理旧值，以及 UDP 缓冲区回收修复。
- 保留旧实现的地址精确匹配、共享接口维护、ARP 恢复、LRU 回收等迁移后修复；细节见迁移文档。
- 不应用 Smart 的整个 go.mod 覆盖本地：本地 Go 1.25 与 eBPF 依赖、新版基础依赖属于集成需要，不是缺失项。
- 自动同步工作流 checkout 的是 Alpha，并按 release 资产检测更新；不会自动按实验目录映射维护 codex/ebpf-next。状态文件的 `.3` 记录与实验版 `e3256f2f` 记录代表不同路线，不宜简单改成同一提交。
- 普通带标签测试已覆盖实验目录；build-ebpf.yml 的特权集成命令只运行 `./common/ebpf/...`，实验后端缺少这条 CI 的设备级覆盖。已有文档亦将真实 Linux/Android 内核流量验证列为未完成。
- experimental 后端 README 仍含 sing-box 命令示例，不应当作本项目已提供的 CLI 能力；迁移时应清理文档适配。

## 建议顺序

1. 优先补实验 eBPF 的 DNS 回包与 CIDR 下发，以及 Hysteria v1/v2、TrustTunnel 修复。
2. 同步 Smart 的完整节点切换提交，连同其存储层和 GroupBase 并发修复一起评估，避免只改 smart.go。
3. 将统一策略和 TCX/sysctl 生命周期更新按实验目录映射接入，保留下游超时、Fake-IP 和缓冲区修复。
4. 补实验后端特权测试及目标设备流量验证，再决定是否将其提升为常规入口。

上述为代码静态核查的优先级，不代表已在目标设备复现全部问题。

## 同步处理记录

- 已按用户要求调用 GitHub merges API；Smart、eBPF 两路均返回 HTTP 409，随后转为手动处理。
- Smart 已合并至 4bc3d49f；smart.go 的冲突为本地格式化与上游改动重叠，保留上游行为并统一格式。
- eBPF 已将 e3256f2f..e88bb8c6 的增量映射至 experimental/tanaka；保留本地超时秒单位校验、Fake-IP 同步和 UDP 缓冲区管理。旧 ebpf 后端未被覆盖。
- 同步了 Smart 发布标记；实验 eBPF 基线单独记录在 docs/ebpf-next.md。
- 补齐实验后端生成检查和特权测试范围；特权测试仍受目标内核能力约束。
- 本地 Smart/Hysteria 回归测试、Linux 新旧后端特权测试编译、实验监听层测试编译、Android ARM64 构建通过；BPF manifest 校验通过。
- 首轮 CI 重新生成检查通过。特权日志暴露旧测试过期 API、实验测试 typed-nil 游标/遍历终止错误及未加载程序访问，已修正测试代码。特权测试编译现为独立必过步骤。
- 最终 GitHub Actions 验证进行中，完成后补充结果。
