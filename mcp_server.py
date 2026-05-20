"""
RhinoRAG MCP server — exposes the Rhino/Grasshopper API knowledge base as tools.

Run (stdio transport):
    python mcp_server.py

Configure in an MCP client (Claude Desktop / Cherry Studio / Cline), replacing
<RHINORAG_DIR> with the absolute path to this repo:
    {
      "mcpServers": {
        "rhino-rag": {
          "command": "<RHINORAG_DIR>/.venv/Scripts/python.exe",
          "args": ["<RHINORAG_DIR>/mcp_server.py"]
        }
      }
    }
"""

from mcp.server.fastmcp import FastMCP

import rag_core


INSTRUCTIONS = """
You can search a local knowledge base of Rhino / Grasshopper developer APIs
(RhinoCommon, Grasshopper SDK, GH_IO, Eto.Forms, RhinoScriptSyntax).

HOW TO USE THESE TOOLS — read carefully:

You are an experienced Rhino/Grasshopper developer. You already know many common
patterns (how to subclass GH_Component, the shape of SolveInstance, how parameters
are registered, basic geometry calls, etc.). For things you are confident about,
JUST WRITE THE CODE. Do not look them up.

Only call the search tools when you are genuinely uncertain about a SPECIFIC point:
- You don't remember the exact method name (is it CreateBooleanDifference or BooleanDifference?)
- You don't remember the parameter order, types, or how many overloads exist
- You don't remember the return type (Brep[]? bool? could it be null?)
- You suspect an API might not exist (avoid hallucinating)
- The user wants a long-tail / version-specific feature you're unsure of

Do NOT:
- Look up template/boilerplate code you already know
- Dump a whole multi-feature request into one query
- Mechanically "search for every step"

Good workflow:
- Sketch the code in your head, write the parts you're confident about.
- Identify the few specific points you're unsure of (usually a couple of API calls).
- Search each uncertain point with a precise query (one point per query).
- Fill in, continue. Correct yourself if the search shows you misremembered.

Self-check before final output: even if you think you remember an API, if it is a
Create*/factory method or has multiple overloads, confirm its signature once with
get_member — a few tokens is cheaper than uncompilable code.

CHOOSING THE 'task' PARAMETER (controls which libraries are searched):
- rhino_python   — Python script in Rhino's Script Editor
- gh_python      — Python 3 component inside Grasshopper
- gh_csharp      — C# Script component inside Grasshopper
- gha_dev        — developing a compiled .gha component in Visual Studio (C#)
- plugin_csharp  — a Rhino C# plugin
- ui             — building a dialog/panel UI (Eto.Forms)
- auto           — unsure / search everything

LANGUAGE RULES:
- In Python tasks, prefer rhinoscriptsyntax (rs.*) for simple operations — it takes
  Python-friendly inputs like [x,y,z]. Drop to RhinoCommon when you need fine control
  (tolerances, batch processing, low-level geometry).
- In C# tasks, never use rhinoscriptsyntax — it's a Python-only library.
- Many out/ref parameters in RhinoCommon (marked @) become extra tuple return values
  in Python, not arguments. The tool output notes this where relevant.

If unsure what's available, call list_libraries first.
""".strip()


mcp = FastMCP("RhinoRAG", instructions=INSTRUCTIONS)


def _fmt_hit(r):
    lib = r.get("library", "")
    via = r.get("via", "")
    return f"[{lib}] {r['compact']}  (via {via})"


@mcp.tool()
def list_libraries() -> str:
    """List the available API libraries and which task each is for.

    Call this when you're unsure what can be searched or which 'task' to pass.
    """
    lines = ["Available libraries:"]
    for name in rag_core.available_libraries():
        cfg = rag_core.LIBRARIES[name]
        langs = "/".join(cfg.get("languages", []))
        lines.append(f"- {name} ({langs}): {cfg['description']}")

    lines.append("")
    lines.append("task -> libraries searched:")
    for task, scope in rag_core.TASK_SCOPE.items():
        scope_str = "all" if scope is None else ", ".join(scope)
        lines.append(f"- {task}: {scope_str}")
    return "\n".join(lines)


@mcp.tool()
def search_api(query: str, task: str = "auto", n: int = 5) -> str:
    """Search the Rhino/Grasshopper API docs for ONE specific thing you're unsure of.

    Use this to find an API when you don't know its exact name, aren't sure it
    exists, or want to discover what API performs some operation. Search one
    concrete uncertain point at a time — do NOT pass a whole multi-feature request.

    Good queries:
        "brep boolean difference"            (a specific operation)
        "register Brep input parameter"      (a specific concept)
        "SolveInstance DataAccess GetData"   (a specific concept)
    Bad query:
        "write a GH component that subtracts breps with a red rounded UI"
        (too broad — write what you know, then search the few specific gaps)

    task: rhino_python | gh_python | gh_csharp | gha_dev | plugin_csharp | ui | auto
          (controls which libraries are searched; default auto = search everything)
    n:    number of results (default 5)
    """
    try:
        results = rag_core.hybrid_search(query, n_results=n, task=task)
    except ValueError as e:
        return f"Error: {e}"

    if not results:
        return "No results. Try a different query or task=auto."

    return "\n".join(_fmt_hit(r) for r in results)


@mcp.tool()
def get_member(name: str, owner: str = "", task: str = "auto") -> str:
    """Get the full details of a KNOWN API member (all overloads, params, returns).

    Use this when you know the method/property/type name but need to confirm the
    exact signature, how many overloads exist, parameter order/types, or the
    return type. This is the right tool to verify an API before writing code.

    name:  the member name, e.g. "CreateBooleanDifference"
    owner: the declaring class/module, e.g. "Brep" (optional but recommended;
           for rhinoscriptsyntax this is the module like "surface")
    task:  restricts which libraries are searched (default auto)

    If you don't know the owner, use search_api first to find it.
    """
    if not owner:
        # Fall back to a search so the model still gets something useful.
        results = rag_core.hybrid_search(name, n_results=5, task=task)
        if not results:
            return f"No member found for '{name}'. Try search_api with a descriptive query."
        out = ["owner not given — closest matches (call get_member again with the right owner):"]
        out += [_fmt_hit(r) for r in results]
        return "\n".join(out)

    try:
        details = rag_core.get_member_detail(owner, name, task=task)
    except ValueError as e:
        return f"Error: {e}"

    if not details:
        return f"No member '{owner}.{name}' found. Check the name/owner, or use search_api."

    blocks = []
    for d in details:
        blocks.append(f"[{d['library']}]\n{d['text']}")
    return "\n\n---\n\n".join(blocks)


@mcp.tool()
def list_class(owner: str, kind: str = "", task: str = "auto") -> str:
    """List the members (methods/properties/...) of a class or module.

    Use this to discover what a type offers — e.g. "what methods can I override on
    GH_Component" or "what does the Brep class expose".

    owner: class name (e.g. "GH_Component", "Brep") or rhinoscriptsyntax module
           (e.g. "surface")
    kind:  optional filter — "method" | "property" | "field" | "event" | "type" |
           "function" (rhinoscriptsyntax). Empty = all kinds.
    task:  restricts which libraries are searched (default auto)
    """
    try:
        members = rag_core.list_class_members(
            owner, kind=kind or None, task=task, limit=200
        )
    except ValueError as e:
        return f"Error: {e}"

    if not members:
        return f"No members found for '{owner}'. Check the name or use search_api."

    return rag_core.format_method_list(members)


if __name__ == "__main__":
    mcp.run()
