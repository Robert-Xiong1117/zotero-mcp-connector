---
name: ppt-evidence-to-zotero
description: When revising an argument on a PowerPoint slide, back it with a verbatim quote from a paper in the user's Zotero library — search the library (or import the paper), get the PDF, pull the exact sentence with its page number, rewrite the slide and cite it in the speaker notes, highlight the sentence in the PDF, and leave a child note linking quote, page, slide and claim. Use for 改 PPT 论点 / 给幻灯片找文献支撑 / 补引用 / 原文高亮.
---

# PPT 论点 → Zotero 原文证据

用 Zotero MCP 连接器（v1.2.0+，带 Zotero 桥接插件）把幻灯片上的一个论点落到一篇文献的**逐字原句**上，
并在 PPT 和 Zotero 两边都留下可追溯的记录。

## 用到的工具
| 步骤 | 工具 |
|---|---|
| 库内检索 | `zotero_search_items`（`qmode="everything"` 可搜全文）；有 AI4Paper 时可用 `ai4paper_zotero_semantic_search` |
| 外部检索 / 导入 | `ai4paper_zotero_search_literature` → `ai4paper_zotero_import_papers`（写入，需用户批准） |
| 补 PDF | `zotero_find_pdf`（写入，需用户批准） |
| 读全文 | `zotero_get_item_fulltext`；需要页码时优先 `ai4paper_zotero_get_pdf_text`（如有分页信息） |
| 高亮原句 | `zotero_highlight_quote`（写入，需用户批准） |
| 子笔记 | `zotero_create_note(content, parent_key, tags)`（写入，需用户批准） |

任何写入工具调用前，先用一句话告诉用户要写什么，再调用（claude.ai 中这些工具应设为「需要批准」）。

## 流程

### 1. 明确要改的论点
读当前幻灯片（标题、正文、备注），用一句话写出**要支撑的论点**（claim）。论点含糊时先和用户确认，不要自己扩大或改变论点。
记下幻灯片编号和标题，后面每一步都用到。

### 2. 找文献
1. 先在库内找：用论点中的 2–4 个关键词 `zotero_search_items`，必要时 `qmode="everything"`。列出最相关的 3–5 篇（作者、年份、标题、item key）。
2. 库内没有合适的：用外部检索找候选，**列给用户选**，用户确认后再导入。不要未经确认批量导入。
3. 选定一篇（或几篇）后继续。

### 3. 确保有 PDF
`zotero_get_item_children` 查看附件。没有 PDF 时调用 `zotero_find_pdf(item_key)`：
- `found: true` → 继续；
- `found: false` → 告诉用户找不到开放获取版本，请其手动下载拖入 Zotero，或换一篇文献。

### 4. 读全文，摘原句
1. 读全文，找出**直接支撑论点**的句子。优先选结果、结论或数据句，避免引用作者对他人研究的转述。
2. 原句必须**逐字**照抄（保留原文语言、标点和数字），不得改写、拼接或省略中间内容；需要两处证据就摘两句。
3. 记录页码：能从分页文本中确定就记下；否则以第 6 步高亮返回的 `page` 为准，届时回头更新备注。
4. 给用户看：原句、页码、它为什么支撑论点。若证据只能部分支撑，如实说明，并建议收窄论点措辞。

### 5. 改幻灯片 + 备注引用
- **正文**：按证据改写论点，措辞不得强于原文（原文说 "associated with" 就不要写成「导致」）。保持原幻灯片的版式和长度。
- **备注**（speaker notes）末尾追加：
  ```
  证据：作者 (年份). 标题. p. 页码
  原句："……逐字原句……"
  Zotero: item_key
  ```

### 6. 高亮原句
`zotero_highlight_quote(item_key, quote=原句, comment="支撑：<论点>（幻灯片 N）")`
- `ok: true` → 记下返回的 `page`、`match`、`annotation_key`。`page` 与第 4 步不同时，以它为准并更新备注。
- `ok: false` 且带 `candidates` → **不要自行挑选**。把候选句和得分给用户看；确认后用候选的原文逐字重试，并同步改正备注里的原句。
- 提示插件未安装 / Token 不匹配 / Zotero 未运行 → 把错误原文告诉用户，按控制面板提示处理；其余步骤照常完成，报告中注明未高亮。

### 7. 写子笔记
`zotero_create_note(parent_key=item_key, tags=["ppt-evidence"], content=…)`，内容：
```
## PPT 证据：<论点>
- 原句："……逐字原句……"
- 页码：p. <page>
- 对应幻灯片：<演示文稿名> · 第 N 张「<标题>」
- 支撑的论点：<论点>
- 支撑程度：直接支撑 / 部分支撑（说明）
- 高亮批注：<annotation_key>
```

### 8. 汇报
用简短列表告诉用户：改了哪张幻灯片、用了哪篇文献哪一页的哪句话、高亮和笔记是否写入成功；有未完成的步骤要明确列出。

## 规则
- 只用文献里真实存在的句子；高亮工具找不到就是找不到，不要硬凑。
- 一条论点对应的每一句证据都要走完 4–7 步。
- 不删除、不修改库里已有的条目、批注和笔记。
