# Changelog

## 1.2.0 — 2026-11-03
### 新增
- **PDF 原文高亮**：MCP 工具 `zotero_highlight_quote(item_key, quote, comment="", color="#ffd400")`。
  用 PyMuPDF 在 PDF 中定位原句（先精确匹配，再做空白 / 连字符 / 跨行跨页规范化匹配），
  换算为 PDF 坐标后写入 Zotero 高亮批注；返回页码、匹配方式、批注 key。找不到时只返回最接近的候选句，不写入。
- **查找可用 PDF**：MCP 工具 `zotero_find_pdf(item_key)`，调用 Zotero 的「查找可用 PDF」。
- **Zotero 桥接插件** `zotero-plugin/`（Zotero 7，无界面）：在 Zotero 本机服务器上注册
  `GET /zmc/ping`、`POST /zmc/annotate`、`POST /zmc/find-pdf`，每个请求校验 `X-ZMC-Token`。
  Releases 附带 `ZoteroMCP-Bridge-x.y.z.xpi` 与自动更新用的 `updates.json`。
- 配置新增 `zmc_bridge_token`（自动生成；旧版本升级后首次启动时生成）。
- 控制面板：「Zotero 桥接插件」状态行（已连接 / 未安装 / Token 不匹配 / Zotero 未运行）、安装步骤、Token 复制按钮。
- `skills/ppt-evidence-to-zotero`：PPT 论点 → 文献原句 → 高亮 + 子笔记的工作流。

### 修复
- 测试在 Windows 上会读写真实的 `%APPDATA%\ZoteroMCP` 配置和 OAuth 数据库（platformdirs 在 Windows 上不读环境变量）。
  现在所有测试通过 `tests/conftest.py` 强制隔离，路径越界时直接失败。

## 1.1.0 — 2026-11-02
### 新增
- AI4Paper 代理：把 AI4Paper 的本机 MCP（`127.0.0.1:23119/ai4paper/mcp`）以 `ai4paper_` 前缀挂载进同一个受 OAuth 保护的连接器。
- 工具白名单（默认读取 + 导入/整理），Token 本地保存，认证方式自动探测；控制面板新增 AI4Paper 卡片。
- AI4Paper 离线时 zotero-mcp-lite 原有工具不受影响。

## 1.0.0 — 2026-10-29
### 首个版本
- 打包 zotero-mcp-lite 0.2.0（内置 OAuth 2.1）+ ngrok 管理程序，提供 Windows 安装包与 Apple Silicon dmg。
- 首次设置向导、启动 / 停止、自检与自动重启、托盘 / 菜单栏图标、本地控制面板。
- ngrok IP 白名单（仅 Anthropic）+ Basic Auth + 管理员密码；授权模式临时放行本机 IP。
- 开机自启、加密导出 / 导入配置包、从旧版脚本迁移。
- GitHub Actions：推送到 main 自动构建并按版本号发布 Release。
