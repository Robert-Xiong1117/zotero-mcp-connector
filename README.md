# Zotero MCP Connector

把本机的 Zotero 文献库安全地接到 **claude.ai / Claude 手机 App / Claude for PowerPoint·Word** 的自定义连接器。

打包内容：
- [zotero-mcp-lite](https://github.com/xmruuu/zotero-mcp-lite) 0.2.0（MIT）—— MCP 服务器本体，内置 OAuth 2.1
- 管理程序（本仓库）：首次设置向导、启动/停止、自检与自动重启、托盘/菜单栏图标、本地控制面板、授权模式、开机自启、加密导出/导入
- ngrok：首次启动时从 ngrok 官方下载，不随安装包分发
- Zotero 桥接插件（可选，`zotero-plugin/`）：PDF 高亮与查找 PDF，见下文

版本变化见 [CHANGELOG.md](CHANGELOG.md)。

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

## PDF 高亮与查找 PDF（v1.2.0 起）
Zotero 本地 API 只读，写批注必须在 Zotero 进程内完成，所以需要额外装一个很小的 **Zotero 桥接插件**（无界面）。
不装插件时这两个工具会返回清晰的错误，其他工具照常可用。

### 安装插件
1. 从 Releases 下载 `ZoteroMCP-Bridge-x.y.z.xpi`（版本与本软件一致）。
2. Zotero（7 – 10）→ 工具 → 插件 → 右上角齿轮 →「从文件安装附加组件…」，选择该 .xpi。
3. 控制面板 →「Zotero 桥接插件」→ 复制桥接 Token。
4. Zotero → 设置 → 高级 → 滚到底部「设置编辑器」（Config Editor，首次会提示风险，点 Accept the Risk and Continue），搜索 `extensions.zmc-bridge.token`，双击后粘贴 Token。
5. 控制面板状态行显示「已连接 vx.y.z」即完成。插件通过 `updates.json` 随 Releases 自动更新。

### 两个工具
| 工具 | 作用 |
|---|---|
| `zotero_highlight_quote(item_key, quote, comment="", color="#ffd400")` | 在条目的 PDF 中找到这句原文并写入高亮批注（可带评论、颜色）。先精确匹配；失败后忽略空白、大小写、连字符与换行，并支持跨行、跨页。**不会写入模糊匹配**：找不到时返回最接近的候选句，确认后用候选原文重试。返回页码、匹配方式（`exact` / `normalized`）、批注 key。 |
| `zotero_find_pdf(item_key)` | 运行 Zotero 的「查找可用 PDF」（按 DOI / URL 查找开放获取版本），找到后作为附件保存。条目已有 PDF 时直接返回。 |

扫描版 PDF 没有文本层，无法定位，请先 OCR。

### 在 claude.ai 中设为「需要批准」
claude.ai → 设置 → 连接器 → 本连接器 → 工具权限：把 `zotero_highlight_quote`、`zotero_find_pdf`
（以及 `zotero_create_note`）设为「需要批准」，每次写入前你都会看到参数并确认。

### 安全说明
- 插件端点挂在 Zotero 自带的本机服务器上，只监听 `127.0.0.1:23119`，不经过 ngrok，外网无法直接访问。
- 每个请求都必须带 `X-ZMC-Token`，与本软件配置里的 `zmc_bridge_token` 一致，否则返回 403；插件里的 Token 为空时拒绝一切请求。
  这能防止本机网页或其他程序借 Zotero 端口写入你的文献库。
- claude.ai 只能通过已有的 OAuth 连接器调用这两个工具，桥接 Token 不会离开你的电脑。
- 插件只能新建高亮批注和添加 PDF 附件，不能删除或修改已有条目。

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
插件测试需要 Node.js（没有时自动跳过）。发布时 `app/__init__.py`、`zotero-plugin/manifest.json` 与 spec 中的版本号须一致（测试与 CI 会检查前两者）。

修改 `app/__init__.py` 中的版本号并推送到 main，GitHub Actions 自动构建 Windows 安装包与 Apple Silicon dmg，并以 `v版本号` 发布到 Releases。
