# Zotero Cloud MCP 2.0.0rc1

这是独立的云端只读版本。部署在云服务器后，无需个人电脑开机，不启动 Zotero Desktop、ngrok 或 AI4Paper。现有桌面版继续保留，版本号和打包流程不变。

## 实际支持范围

14 个工具：cloud_status、search_items、get_recent、get_collections、get_collection_items、get_tags、get_saved_searches、get_trash、get_item_metadata、get_item_children、search_annotations、get_item_fulltext、read_pdf_pages、export_citations。

- 读取已同步文献全部元数据字段、笔记 HTML、分类、标签、标注、回收站和保存的搜索定义。
- 每次最多 100 条，并返回 next_start；不断翻页可遍历完整结果，不把第一页冒充全库。
- 从 Zotero Storage 下载 PDF，按页提取文本；保留附件 key、PDF 物理页码、标注页标签和 zotero:// 链接。
- 云端索引全文按字符分段，保留 indexedPages/totalPages 等完整性信息。
- BibTeX、RIS 和 CSL JSON 导出。
- 每个部署配置一个个人文库或群组文库。群组部署使用 group 类型和群组 ID。

**“全部云端”表示运行和数据来源均不依赖个人电脑，不代表所有桌面插件能力都已迁移。** 当前不提供写入/删除、OCR、音视频解析、AI4Paper 语义索引、选中文献、当前阅读器状态或插件本地数据库访问。保存的搜索仅返回定义，不能由 Web API 直接执行。新版工具参数可能与桌面版不同，客户端应重新发现工具。

## 部署前准备

1. Zotero 设置 → 同步：完成数据同步。文件同步选择 Zotero Storage，等待 PDF 上传完成。此版本**不读取坚果云 WebDAV**。
2. 本地链接附件不会因为切换存储服务而自动上传；需要先转换为存储附件并确认同步成功。
3. 在 https://www.zotero.org/settings/keys 创建独立的 API Key，允许读取所需文库、笔记及附件，记录数字 User ID。无需公开文库，不需要写权限。
4. 准备支持 Docker、HTTPS 和持久磁盘的云平台或 Linux 云服务器。GitHub 仓库不是常驻 MCP 服务器。

## 容器平台部署

在云平台连接本 GitHub 仓库，选择包含此改动的分支：

- Dockerfile：`Dockerfile.cloud`
- 构建上下文：仓库根目录
- 内部端口：`8000`（也支持平台提供的 PORT）
- 健康检查：`/healthz`，只检查进程存活，不检查 Zotero 同步状态
- 持久磁盘：挂载到 `/data`，确保容器用户 UID 10001 可写
- 实例数：1；OAuth SQLite 状态不适用于多个副本共同写入
- 建议至少 768 MiB 内存，设置平台资源限制；复杂 PDF 可能需要更多

在平台的秘密变量设置中填写：

| 变量 | 内容 |
|---|---|
| ZOTERO_LIBRARY_ID | 数字 User ID，不能填本地 0 |
| ZOTERO_LIBRARY_TYPE | user；群组则为 group |
| ZOTERO_API_KEY | Zotero 只读密钥 |
| ZOTERO_MCP_PUBLIC_URL | 服务的 HTTPS 根地址，不含 /mcp |
| ZOTERO_MCP_ADMIN_PASSWORD | 随机密码，至少 24 字符，用于授权远程 AI |
| ZOTERO_CIMD_URLS | 可选：客户端使用的、你已核实的准确 HTTPS 元数据 URL，逗号分隔 |

先由平台分配稳定域名，再设置 PUBLIC_URL 并启动。配置不完整时服务会拒绝启动。不要把秘密写进 GitHub、Docker 镜像、PR 或聊天。

如使用自己已有的云服务器：在**云服务器上**复制 `.env.cloud.example` 为 `.env.cloud` 并填写，然后运行：

```sh
docker compose -f compose.cloud.yaml up -d --build
```

Compose 只绑定服务器回环地址 8000；用你云服务器现有的 HTTPS 反向代理转发到 `127.0.0.1:8000`，保留所有路径、Authorization 请求头，并关闭 SSE 响应缓冲。不要只代理 /mcp，OAuth discovery、/register、/authorize、/token 等路径也需要到达服务。不要额外加不兼容的网页登录墙。为 OAuth 登录与注册端点在网关配置限流。

持久磁盘保存 OAuth 令牌；PDF 使用最多 64 MiB 的进程内缓存，重启后重新下载，不持久保存文库副本。重启或更换密码不是撤销全部旧令牌的机制；应使用 OAuth 撤销端点，或停止服务后清除云端 OAuth 数据库并重新授权所有客户端。

## 接入远程 AI

在支持远程 Streamable HTTP 和 OAuth 的客户端中添加：

`https://你的云服务域名/mcp`

浏览器授权时输入 MCP 管理密码，不是 Zotero 登录密码或 API Key。支持动态客户端注册（DCR）。若客户端使用 CIMD，管理员需把其官方提供的准确 metadata URL 加入 ZOTERO_CIMD_URLS；默认拒绝任意 URL 拉取，防止访问云服务器内部网络。不同客户端实际握手仍需部署后验证。

## 验收

1. 无授权访问 /mcp 应返回 401；/healthz 应返回 200。
2. 在 AI 客户端完成 OAuth 登录，调用 cloud_status，确认云端文库 ID、数量和版本。
3. 搜索一篇已同步论文，调用 get_item_children 获取附件 key；用 read_pdf_pages 读第一页。
4. 再对附件调用 get_item_children，核对一条原有标注的文本、评论、PDF 页码和页标签。
5. 关闭个人电脑，再从手机或另一设备重复步骤 2–4。这一步通过才算“关机后可用”。

## 限制和错误

- 未同步或只在 WebDAV 的 PDF 会报告云端不可用，不会回退到本机。
- 单 PDF 下载上限 32 MiB；一次提取 1–10 页，每页 30,000 字符，截断会明确标记。无文字页标记 needs_ocr，不会假装已完成 OCR。
- PDF 页码为从 1 开始的物理页，与论文印刷页码可能不同。标注的 page_label 单独保留。
- 429/Backoff 会暂停后续请求并告诉调用方等待多久，不自动重复高频请求。
- 64 MiB 缓存只是下载字节预算，不是整个 Python 进程的内存上限；云平台仍须限制资源。
- zotero:// 链接需要打开链接的设备安装并同步 Zotero；云端提取文本本身不需要桌面程序。
- 只读 API Key 是第二道限制：即使以后添加写工具，也必须另行授权。

## 开发与验证

```sh
pip install -r requirements-cloud.txt
python -m unittest discover -s cloud_tests -v
docker build -f Dockerfile.cloud -t zotero-cloud:test .
```

`.github/workflows/cloud.yml` 在云端分支与 PR 中运行完整依赖测试和镜像构建，不执行部署。依赖重用 zotero-mcp-lite 0.2.0 的 MIT 授权 OAuth 模块；云端模块不调用其本机数据层。FastMCP 限定 2.x，避免未经验证的主版本迁移。

参考：
- https://www.zotero.org/support/dev/web_api/v3/basics
- https://www.zotero.org/support/dev/web_api/v3/fulltext_content
- https://www.zotero.org/support/sync
- https://github.com/xmruuu/zotero-mcp-lite
