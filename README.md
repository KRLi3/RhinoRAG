# RhinoRAG

RhinoRAG 是一个面向 Rhino / Grasshopper 开发的本地 API 知识库。它把官方文档
（RhinoCommon、Grasshopper SDK、GH_IO、Eto.Forms、RhinoScriptSyntax）做成可检索索引，
再通过 **MCP server** 接入 AI 客户端。

RhinoRAG is a local, versioned API knowledge base for Rhino / Grasshopper development. It indexes
the official docs (RhinoCommon, Grasshopper SDK, GH_IO, Eto.Forms, RhinoScriptSyntax) and exposes
them as an **MCP server** to MCP-capable AI clients.

它源于 Grasshopper 插件 **Medusa** 开发过程中反复出现的一个难题：当代码复杂到需要借助 AI
排查时，AI 给出的修改往往似是而非——方法名张冠李戴、凭空捏造并不存在的 API、把 C# 与 Python
的写法搅在一起、重载签名也时常出错。问题的根源在于，大模型对 Rhino 这类长尾 API 的记忆并不可靠。
RhinoRAG 的思路很简单：与其让模型凭记忆猜，不如让它在落笔前先查证——确认名称、签名、参数、
返回值与重载，再动手写代码。

It was born from a recurring frustration during the development of the Grasshopper plugin
**Medusa**: once the code grew complex enough to lean on AI for help, the AI's edits were
plausible-looking but wrong — methods misremembered, non-existent APIs invented, C# and Python
idioms tangled together, overload signatures mixed up. The root cause is that large models' recall
of Rhino's long-tail APIs is fundamentally unreliable. RhinoRAG takes a simple stance: rather than
let the model guess from memory, have it verify first — confirming the exact name, signature,
parameters, return type and overloads before writing a line of code.

普通用户请看 [快速安装](#快速安装)，开发者请看 [从源码构建](#从源码构建)。

For end users, jump to [Quick install](#quick-install). For developers, see
[Building from source](#building-from-source).

---

## 收录内容

| Library | Source | Chunks | 适合场景 |
|---|---:|---:|---|
| `rhinocommon` | RhinoCommon.xml (Rhino 8.31) | 16,260 | RhinoCommon / .NET API，C# 与 Python 都会用到 |
| `grasshopper` | Grasshopper.xml | 7,974 | Grasshopper 组件、参数、数据访问、SDK |
| `gh_io` | GH_IO.xml | 495 | Grasshopper 序列化与持久化，主要面向 C# |
| `eto` | Eto.xml | 5,958 | Rhino 插件界面、对话框、面板 |
| `rhinoscriptsyntax` | mcneel/rhinoscriptsyntax | 920 | Rhino Python 脚本里的 `rs.*` 函数 |

检索方式是混合检索：`bge-small-en-v1.5` 语义向量 + BM25 关键词检索，并使用 RRF 融合结果。
每个库独立建索引，避免 Python-only 的 `rhinoscriptsyntax` 混进 C# 任务里。

## What's indexed

| Library | Source | Chunks | Use for |
|---|---:|---:|---|
| `rhinocommon` | RhinoCommon.xml (Rhino 8.31) | 16,260 | RhinoCommon / .NET API, used from both C# and Python |
| `grasshopper` | Grasshopper.xml | 7,974 | Grasshopper components, params, data access, SDK |
| `gh_io` | GH_IO.xml | 495 | Grasshopper serialization / persistence, mainly C# |
| `eto` | Eto.xml | 5,958 | Rhino plugin UI, dialogs, panels |
| `rhinoscriptsyntax` | mcneel/rhinoscriptsyntax | 920 | The `rs.*` functions in Rhino Python scripts |

Retrieval is hybrid: semantic vectors (`bge-small-en-v1.5`) plus BM25 keyword search, fused with
RRF. Each library is indexed separately so the Python-only `rhinoscriptsyntax` never leaks into
C# tasks.

---

## 快速安装

面向不想手动配 Python 环境、也不想自己构建索引的 Rhino / Grasshopper 用户。

**1. 下载并安装**

1. 从 GitHub Releases 下载最新的 release 压缩包，解压到任意文件夹。
   建议路径不要包含中文或空格，例如 `C:/Tools/RhinoRAG`。
2. 确认电脑已安装 **Python 3.10+**。安装 Python 时请勾选 **Add Python to PATH**。
   没装的话先到 <https://www.python.org/downloads/> 安装。
3. 双击 `install.bat`。它会自动创建 `.venv`、安装依赖，并下载预构建的索引和模型数据。
4. 看到“安装完成”后，窗口里会显示 `python.exe` 和 `mcp_server.py` 两个路径，配置 MCP 时会用到。

**2. 配置 MCP 客户端**

MCP 配置里的 Windows 路径建议直接写成正斜杠 `/`，例如：

```json
{
  "mcpServers": {
    "rhino-rag": {
      "command": "C:/Tools/RhinoRAG/.venv/Scripts/python.exe",
      "args": ["C:/Tools/RhinoRAG/mcp_server.py"]
    }
  }
}
```

如果使用反斜杠 `\`，JSON 里要写成双反斜杠 `\\`。常见客户端：

- **Claude Desktop**：Settings → Developer → Edit Config，加入上面的 `mcpServers` 配置后重启。
- **VS Code + Cline / Roo Code**：在插件的 MCP 设置里新增 server，填写同样的 `command` 和 `args`。
- **Cherry Studio / Continue 等**：找到 MCP server 配置入口，填入相同路径即可。

**3. 配置大语言模型**

RhinoRAG 只是一个 MCP 工具，不包含 LLM，真正写代码的是你在客户端里配置的模型。
Claude Desktop 可直接使用 Claude 模型；VS Code 插件可接 OpenRouter、Anthropic、OpenAI、
智谱 GLM、Qwen 等服务；想低成本试用，可选支持 tool calling / MCP 的免费或低价模型。

**4. 开始使用**

直接向 AI 描述你的 Rhino / Grasshopper 需求即可，模型会在不确定 API 时调用 RhinoRAG 查询。例如：

```text
在 Grasshopper 里写一个 C# 组件，输入两个 Brep，输出布尔差集结果。
用 Rhino Python 画一个球，并把它放到指定图层。
给一个 compiled .gha 组件自定义 Attributes，让组件背景变成白色，C#。
```

## Quick install

For Rhino / Grasshopper users who don't want to set up Python or build the index by hand.

**1. Download & install**

1. Download the latest release zip from GitHub Releases and unzip it anywhere
   (avoid spaces / non-ASCII in the path, e.g. `C:/Tools/RhinoRAG`).
2. Make sure **Python 3.10+** is installed, with **Add Python to PATH** checked.
   Get it at <https://www.python.org/downloads/> if needed.
3. Double-click `install.bat`. It creates `.venv`, installs dependencies, and downloads the
   prebuilt index + model data.
4. When it finishes, it prints the `python.exe` and `mcp_server.py` paths — you'll need them next.

**2. Configure your MCP client**

Use forward slashes in Windows paths inside JSON, e.g.:

```json
{
  "mcpServers": {
    "rhino-rag": {
      "command": "C:/Tools/RhinoRAG/.venv/Scripts/python.exe",
      "args": ["C:/Tools/RhinoRAG/mcp_server.py"]
    }
  }
}
```

If you use backslashes, double them (`\\`) in JSON. Common clients:

- **Claude Desktop**: Settings → Developer → Edit Config, add the `mcpServers` block, restart.
- **VS Code + Cline / Roo Code**: add a server in the extension's MCP settings with the same
  `command` and `args`.
- **Cherry Studio / Continue, etc.**: point them at the same two paths.

**3. Configure an LLM**

RhinoRAG is only the MCP tool — it ships no LLM. The model that writes code is the one you
configure in your client. Claude Desktop uses Claude directly; VS Code extensions can use
OpenRouter, Anthropic, OpenAI, Zhipu GLM, Qwen, etc. For cheap testing, pick a free or low-cost
model that supports tool calling / MCP.

**4. Start using**

Just describe your Rhino / Grasshopper task to the AI; it calls RhinoRAG whenever it's unsure
about an API. For example:

```text
Write a C# Grasshopper component that takes two Breps and outputs their boolean difference.
Draw a sphere in Rhino Python and move it to a specific layer.
Customise a compiled .gha component's Attributes so its background turns white, in C#.
```

---

## MCP 工具

RhinoRAG 暴露 4 个工具：

| Tool | 用途 |
|---|---|
| `list_libraries()` | 查看可用库，以及不同 `task` 会检索哪些库 |
| `search_api(query, task, n)` | 查找一个不确定的 API 或概念，一次只查一个具体问题 |
| `get_member(name, owner, task)` | 确认已知成员的完整签名、参数、返回值和重载 |
| `list_class(owner, kind, task)` | 浏览某个类或模块的成员列表 |

`task` 用来限制检索范围：

| task | 检索范围 |
|---|---|
| `rhino_python` | `rhinoscriptsyntax` + `rhinocommon` |
| `gh_python` | `rhinoscriptsyntax` + `rhinocommon` + `grasshopper` |
| `gh_csharp` | `rhinocommon` + `grasshopper` |
| `gha_dev` | `rhinocommon` + `grasshopper` + `gh_io` |
| `plugin_csharp` | `rhinocommon` |
| `ui` | `eto` + `rhinocommon` |
| `auto` | 全部库 |

C# 任务不会返回 `rhinoscriptsyntax`，避免把 Python-only API 混进 C# 代码。

## MCP tools

RhinoRAG exposes four tools:

| Tool | Purpose |
|---|---|
| `list_libraries()` | List the libraries, and what each `task` searches |
| `search_api(query, task, n)` | Find one uncertain API or concept — one question at a time |
| `get_member(name, owner, task)` | Confirm a known member's signature, params, return type, overloads |
| `list_class(owner, kind, task)` | Browse the members of a class or module |

The `task` parameter routes the search:

| task | searches |
|---|---|
| `rhino_python` | `rhinoscriptsyntax` + `rhinocommon` |
| `gh_python` | `rhinoscriptsyntax` + `rhinocommon` + `grasshopper` |
| `gh_csharp` | `rhinocommon` + `grasshopper` |
| `gha_dev` | `rhinocommon` + `grasshopper` + `gh_io` |
| `plugin_csharp` | `rhinocommon` |
| `ui` | `eto` + `rhinocommon` |
| `auto` | everything |

C# tasks never return `rhinoscriptsyntax`, so Python-only APIs never leak into C# code.

---

## 常见问题

**双击 `install.bat` 后窗口闪退** — 通常是没装 Python，或安装时没勾选 **Add Python to PATH**。
重新安装 Python 3.10+ 后再运行。

**提示找不到 `db/` 或模型** — 数据包没下载或解压成功。重新运行 `install.bat`，或手动从 Releases
下载 `rhino-rag-data.zip` 解压到 RhinoRAG 根目录（解压后应能看到 `db/` 和 `models/`）。

**AI 没有调用 RhinoRAG** — 先确认客户端里 `rhino-rag` server 已连接；提问时可明确场景，
例如“这是 Grasshopper C# Script 组件”。

**换了新版 Rhino** — 当前索引基于 **Rhino 8.31**。需要匹配更新版本时，等待新的 release 数据包，
或按下面的步骤自行重建索引。

## FAQ

**`install.bat` flashes and closes** — Python probably isn't installed, or wasn't added to PATH.
Reinstall Python 3.10+ with “Add to PATH” checked.

**`db/` or model not found** — The data package didn't download/extract. Re-run `install.bat`, or
manually download `rhino-rag-data.zip` from Releases and unzip it into the RhinoRAG root (you
should see `db/` and `models/`).

**The AI doesn't call RhinoRAG** — Check that the `rhino-rag` server is connected in your client,
and state the context in your prompt (e.g. “this is a Grasshopper C# Script component”).

**New Rhino version** — The index is built from **Rhino 8.31**. For a newer Rhino, wait for an
updated release package, or rebuild it yourself (below).

---

## 从源码构建

仓库主要包含代码。官方 API 文档、预构建索引和模型缓存不放进 git（第三方内容、体积较大）。

**1. 准备 API 文档** — 把 Rhino 安装目录里的这些文件复制到 `docs/`：

- `System/RhinoCommon.xml`
- `System/Eto.xml`
- `Plug-ins/Grasshopper/Grasshopper.xml`
- `Plug-ins/Grasshopper/GH_IO.XML`

再从 [mcneel/rhinoscriptsyntax](https://github.com/mcneel/rhinoscriptsyntax) 复制
`Scripts/rhinoscript/*.py` 到 `docs/rhinoscriptsyntax/`。

**2. 安装依赖并构建索引**

```bat
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python ingest.py
```

只重建某一个库：`.venv\Scripts\python ingest.py grasshopper`

**3. 运行 MCP server**

```bat
.venv\Scripts\python mcp_server.py
```

MCP 配置示例（macOS / Linux 的 Python 路径为 `<RHINORAG_DIR>/.venv/bin/python`）：

```json
{
  "mcpServers": {
    "rhino-rag": {
      "command": "<RHINORAG_DIR>/.venv/Scripts/python.exe",
      "args": ["<RHINORAG_DIR>/mcp_server.py"]
    }
  }
}
```

## Building from source

The repo ships code only. The official API docs, the prebuilt index, and the model cache are not
in git (third-party content / large binaries).

**1. Provide the source docs** — copy these from your Rhino install into `docs/`:

- `System/RhinoCommon.xml`
- `System/Eto.xml`
- `Plug-ins/Grasshopper/Grasshopper.xml`
- `Plug-ins/Grasshopper/GH_IO.XML`

And copy `Scripts/rhinoscript/*.py` from
[mcneel/rhinoscriptsyntax](https://github.com/mcneel/rhinoscriptsyntax) into
`docs/rhinoscriptsyntax/`.

**2. Install & build the index**

```bat
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python ingest.py
```

Rebuild a single library: `.venv\Scripts\python ingest.py grasshopper`

**3. Run the MCP server**

```bat
.venv\Scripts\python mcp_server.py
```

MCP config (on macOS/Linux the Python path is `<RHINORAG_DIR>/.venv/bin/python`):

```json
{
  "mcpServers": {
    "rhino-rag": {
      "command": "<RHINORAG_DIR>/.venv/Scripts/python.exe",
      "args": ["<RHINORAG_DIR>/mcp_server.py"]
    }
  }
}
```

---

## 发布数据包 / Cutting a release

维护者发布 release 时运行：

```bat
.venv\Scripts\python ingest.py
.venv\Scripts\python build_release.py
```

脚本会生成 `dist/rhino-rag-data.zip`。把它上传到 GitHub Release，并在 `install.bat` 中设置
对应的 `DATA_URL`。用户运行 `install.bat` 时会自动下载并把 `db/` 与 `models/` 解压到项目根目录。

As the maintainer, the two commands above build the index and produce `dist/rhino-rag-data.zip`.
Upload it to a GitHub Release and set the matching `DATA_URL` in `install.bat`. Users' `install.bat`
then downloads it and unpacks `db/` + `models/` next to the code.

---

## Notes

Embedding 模型和 `db/` 索引独立于 LLM；LLM 由你的 MCP 客户端决定。只有运行 `mcp_server.py`
的机器需要 embedding 模型，用来把查询编码成向量。首次安装完成后，本地检索可离线运行。
当前索引版本：**Rhino 8.31**。

The embedding model and `db/` are independent of the LLM (whatever your client uses). Only the
machine running `mcp_server.py` needs the embedding model, to encode queries. After first setup,
local retrieval runs offline. Current index: **Rhino 8.31**.
