# 可选 VPS Runner 接入

这一步不是必需的。建议先让 GitHub 自动采集跑通。

## VPS 要求
- 自己管理的 Debian/Ubuntu x86_64 VPS。
- OpenVPN 已安装，`/dev/net/tun` 可用。
- runner 用户可通过 `sudo -n` 运行 OpenVPN。
- 建议使用专用测试机，不要在承载重要业务的 VPS 上运行。

## 注册 runner
仓库 → Settings → Actions → Runners → New self-hosted runner。按 GitHub 页面提示安装并注册。确保 runner 标签包含 `aimili-vpn`，同时有默认标签 `self-hosted`、`linux`、`x64`。不要把 runner 注册到不可信的公共仓库。

## 安装依赖（Debian/Ubuntu）
```bash
sudo apt-get update
sudo apt-get install -y openvpn
test -c /dev/net/tun && echo "TUN available"
```
如果 TUN 不存在，向 VPS 服务商确认支持情况，不要运行不明脚本绕过限制。

## 手动测试
1. 确认 runner 在线且 Idle。
2. Actions → Update VPN data → Run workflow。
3. 将 `run_vps_tests` 设为 `true`。
4. 流程会先采集候选，再在 VPS runner 上最多测试 5 个候选。
5. 下载 `aimili-vps-verification` Artifact 查看结果。

runner 不在线时不要启用该选项，否则作业会等待 runner。节点配置来自公开来源，仍有风险；过滤配置指令不能保证消除所有风险。测试结果仅表示 OpenVPN 会话建立，不代表完整网络可用。

## OpenVPN 实际隧道验证

手动运行工作流并将 `run_vps_tests` 设为 `true` 后，VPS Runner 最多验证 5 个候选节点。成功标准是 OpenVPN 输出 `Initialization Sequence Completed`，而不是仅仅 TCP 端口可达。结果写入 `out/vps_results.json` 并上传为 `aimili-vps-verification` 工件。

Runner 必须是专用 Linux VPS，安装 OpenVPN、启用 `/dev/net/tun`，并允许 runner 用户通过 `sudo -n openvpn` 启动客户端。不要在承载生产 VPN 或重要路由的主机上运行。验证器会丢弃配置内的远程地址、脚本、插件、管理接口和路由修改，只使用候选记录中的 host/port，并保留 `route-nopull`，避免接管 VPS 默认路由。

这是对公共 VPNGate 节点的实际连接测试。节点离线、限速、拒绝连接或认证失败，都可能导致未通过；未通过不必然表示解析器有错误。
