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
