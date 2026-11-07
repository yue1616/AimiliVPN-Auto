# AimiliVPN-Auto（Hybrid）

独立开发的个人节点采集与验证项目，不修改 `jiakuan` 或 `jiakuan1`，不复制 AimiliVPN 闭源模块。

## 架构
- GitHub-hosted Actions：每 6 小时采集 VPN Gate CSV，解析 OpenVPN 配置并做 TCP 端口检测。
- 可选自有 Linux VPS runner：仅在手动运行工作流并将 `run_vps_tests` 设为 `true` 时，进行有限数量的 OpenVPN 会话建立测试。
- 默认不发布 Pages；结果仅保存在私有仓库的 Actions Artifact（默认 7 天）。

没有 VPS 时，GitHub 采集流程仍可独立运行。接入 VPS 见 `VPS_RUNNER.md`。

## 当前范围
| 功能 | 状态 |
|---|---|
| VPN Gate CSV 采集 | 已实现 |
| OpenVPN 配置提取 | 已实现 |
| TCP 连通性检测 | 已实现 |
| VPS OpenVPN 实际会话建立验证 | 已加入验证器，需自有 VPS runner |
| SSTP / L2TP-IPsec / SoftEther | 尚未实现 |
| 自动切换、代理、管理后台 | 尚未实现 |

TCP 可连接不等于 VPN 隧道可用。VPS 验证成功以 OpenVPN 输出 `Initialization Sequence Completed` 为准，只表示隧道会话已初始化，不代表已验证互联网出口、DNS 或吞吐量。

## 使用
1. 在 GitHub 新建私有仓库 `AimiliVPN-Auto`。
2. 上传本项目全部文件到仓库根目录。
3. 在 Actions 中启用工作流。
4. `Update VPN data` 每 6 小时运行，也可手动运行。
5. 从运行记录下载 `aimili-collector-data` Artifact。

## 安全边界
- 不执行节点配置中的脚本、插件、up/down 命令。
- 验证器过滤未知指令，并加入 `route-nopull`，避免节点推送路由接管 VPS 默认路由。
- 建议只在专用、可重装的 VPS 上测试未知公开节点。
- 不要通过公开节点传输敏感业务。
- 不会自动创建仓库、推送代码或公开节点数据。

## 许可证
本项目独立实现，不包含 AimiliVPN 的闭源模块。使用公开数据源仍须遵守其服务条款及适用法律。
