# Zotero MCP Connector

把本机的 Zotero 文献库安全地接到 **claude.ai / Claude 手机 App / Claude for PowerPoint·Word** 的自定义连接器。

打包内容：
- [zotero-mcp-lite](https://github.com/xmruuu/zotero-mcp-lite) 0.2.0（MIT）—— MCP 服务器本体，内置 OAuth 2.1
- 管理程序（本仓库）：首次设置向导、启动/停止、自检与自动重启、托盘/菜单栏图标、本地控制面板、授权模式、开机自启、加密导出/导入
- ngrok：首次启动时从 ngrok 官方下载，不随安装包分发

## 安全模型
| 层 | 措施 |
|---|---|
| 本机 | MCP 服务器只监听 `127.0.0.1` |
| 通道 | ngrok 出站 TLS 隧道，无需路由器端口映射 |
| 边缘 | IP 白名单只放行 Anthropic 出站段 `160.79.104.0/21`；授权模式临时放行本机 IP，到时自动收回 |
| 登录页 | ngrok Basic Auth（第一道）+ zotero-mcp-lite 管理员密码（第二道） |
| 访问令牌 | OAuth 2.1，令牌只在 claude.ai 与你的电脑之间 |

## 安装
从 Releases 下载：
- **Windows**：`ZoteroMCP-Setup-x.y.z.exe`，按用户安装，无需管理员。SmartScreen 提示时选「更多信息 → 仍要运行」。
- **macOS（Apple Silicon）**：`ZoteroMCP-x.y.z-arm64.dmg`，拖入「应用程序」。首次打开：右键 → 打开（应用未经 Apple 公证）。

前提：Zotero 7 已安装，并在 设置 → 高级 中勾选「允许此计算机上的其他应用程序与 Zotero 通信」。

## 首次设置
1. 打开 Zotero MCP，浏览器会弹出控制面板。
2. 填写 ngrok Authtoken 和固定域名（dashboard.ngrok.com）。
3. 点「保存并启动」：自动下载 ngrok、生成密码、启动并进入 30 分钟授权模式。
4. claude.ai → 设置 → 连接器 → 添加自定义连接器，URL 填面板上的地址；按提示输入两道凭证（面板「设置 → 查看登录凭证」）。

## AI4Paper（可选，v1.1.0 起）
AI4Paper 的 MCP 只监听本机，且使用自己的 Token，claude.ai 连接器无法直接使用。本软件可把它**挂载进同一个连接器**：
工具以 `ai4paper_` 前缀出现，复用同一个 URL、同一套 IP 白名单与 OAuth；AI4Paper Token 只在本机转发时使用。

1. Zotero → 设置 → AI4Paper → 工具与连接 → 外部 AI 工具连接：开启「启用认证」，复制 Token；如需写入，打开写入类工具。
2. 控制面板 →「AI4Paper」：粘贴 Token →「测试连接」→ 勾选启用 →「保存并重启服务」。
3. claude.ai 连接器的工具权限里，把 `ai4paper_` 开头的写入类工具（标 ✎）设为「需要批准」。

默认只开放读取类与导入/整理类工具（白名单）；全库删除标签、整理/重命名 PDF 等批量操作默认关闭，AI4Paper 新增的工具也默认隐藏。
AI4Paper 不在线（Zotero 未打开）时，zotero-mcp-lite 原有工具不受影响。

## 换电脑
旧电脑：面板 → 设置 → 导出配置包（设口令）。新电脑：安装后在首次设置页选择「从配置包导入」。连接器 URL 与授权记录一并迁移，**无需在 claude.ai 重新授权**。同一时间只能在一台电脑上运行（同一 ngrok 域名）。

## 从旧版脚本迁移（E:\zotero_mcp）
1. 在 `E:\zotero_mcp` 运行 `remove-autostart.cmd`，再运行 `stop.ps1`，右键托盘图标退出旧面板。
2. 安装本软件，在首次设置页展开「从旧版脚本迁移」读取旧配置，填入 ngrok Authtoken 后启动。
3. 因为 OAuth 授权记录在同一位置，通常无需重新授权。

## 数据位置
- Windows：`%APPDATA%\ZoteroMCP`；macOS：`~/Library/Application Support/ZoteroMCP`（配置、日志、ngrok）
- OAuth 授权记录：zotero-mcp-lite 默认位置（platformdirs `zotero-mcp/oauth.sqlite`）

## 开发
```
pip install -r requirements.txt pytest
python -m pytest tests
python -m app            # 运行管理程序
```
修改 `app/__init__.py` 中的版本号并推送到 main，GitHub Actions 自动构建 Windows 安装包与 Apple Silicon dmg，并以 `v版本号` 发布到 Releases。
