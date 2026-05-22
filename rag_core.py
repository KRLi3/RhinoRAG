import os

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _here(*parts):
    return os.path.join(_BASE_DIR, *parts)


os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
os.environ.setdefault("CHROMA_TELEMETRY_IMPL", "none")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

# If a packaged model cache ships alongside the code (release builds put it in
# ./models), point HuggingFace at it so the server runs fully offline without
# touching the user's global ~/.cache. Falls back to the default cache otherwise.
_LOCAL_MODEL_CACHE = _here("models")
if os.path.isdir(_LOCAL_MODEL_CACHE):
    os.environ.setdefault("HF_HOME", _LOCAL_MODEL_CACHE)

import re
import ast
import json
import hashlib
import chromadb
import bm25s
from bs4 import BeautifulSoup
from sentence_transformers import SentenceTransformer


DB_ROOT = _here("db")
EMBED_MODEL = "BAAI/bge-small-en-v1.5"
EMBED_DIM = 384
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

LIBRARIES = {
    "rhinocommon": {
        "display_name": "RhinoCommon",
        "source_file": _here("docs", "RhinoCommon.xml"),
        "chunker": "xml_dotnet",
        "languages": [".NET", "Python"],
        "description": "Rhino core .NET API — geometry, document, commands, plugin SDK. Usable from C# and Python.",
    },
    "grasshopper": {
        "display_name": "Grasshopper",
        "source_file": _here("docs", "Grasshopper.xml"),
        "chunker": "xml_dotnet",
        "languages": [".NET", "Python"],
        "description": "Grasshopper SDK — build custom GH components, params, data types.",
    },
    "gh_io": {
        "display_name": "GH_IO",
        "source_file": _here("docs", "GH_IO.xml"),
        "chunker": "xml_dotnet",
        "languages": [".NET"],
        "description": "Grasshopper I/O — serialization, archive read/write for GH components (C# only).",
    },
    "eto": {
        "display_name": "Eto.Forms",
        "source_file": _here("docs", "Eto.xml"),
        "chunker": "xml_dotnet",
        "languages": [".NET", "Python"],
        "description": "Eto.Forms — cross-platform UI framework used by Rhino/GH dialogs and panels.",
    },
    "rhinoscriptsyntax": {
        "display_name": "RhinoScriptSyntax",
        "source_file": _here("docs", "rhinoscriptsyntax"),
        "chunker": "python_rhinoscript",
        "languages": ["Python"],
        "description": "RhinoScriptSyntax — high-level Python wrappers over RhinoCommon. For simple Python scripts in Rhino/GH.",
    },
}

# Maps a high-level task to the libraries that should be searched for it.
# None means "search everything available". Used by MCP-facing helpers.
TASK_SCOPE = {
    "rhino_python": ["rhinoscriptsyntax", "rhinocommon"],
    "gh_python": ["rhinoscriptsyntax", "rhinocommon", "grasshopper"],
    "gh_csharp": ["rhinocommon", "grasshopper"],
    "gha_dev": ["rhinocommon", "grasshopper", "gh_io"],
    "plugin_csharp": ["rhinocommon"],
    "ui": ["eto", "rhinocommon"],
    "auto": None,
}

SUPPORTED_EXTS = (
    ".txt",
    ".md",
    ".cs",
    ".xml",
    ".html",
    ".htm",
)

_model = None
_chroma_clients = {}
_bm25_state = {}


def get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBED_MODEL)
    return _model


def library_dir(library: str) -> str:
    if library not in LIBRARIES:
        raise ValueError(f"Unknown library: {library}. Available: {list(LIBRARIES)}")
    return os.path.join(DB_ROOT, library)


def bm25_dir(library: str) -> str:
    return os.path.join(library_dir(library), "bm25")


def bm25_meta_path(library: str) -> str:
    return os.path.join(library_dir(library), "bm25_meta.json")


def get_client(library: str):
    if library not in _chroma_clients:
        path = library_dir(library)
        os.makedirs(path, exist_ok=True)
        _chroma_clients[library] = chromadb.PersistentClient(path=path)
    return _chroma_clients[library]


def get_collection(library: str):
    client = get_client(library)
    return client.get_or_create_collection(
        library,
        metadata={"hnsw:space": "cosine"},
    )


def available_libraries():
    return list(LIBRARIES.keys())


def stable_id(key: str) -> str:
    return hashlib.md5(key.encode("utf-8", errors="ignore"), usedforsecurity=False).hexdigest()


def read_file(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        raw = f.read()

    if ext in (".html", ".htm"):
        soup = BeautifulSoup(raw, "html.parser")

        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        lines = [
            line.strip()
            for line in soup.get_text("\n").splitlines()
            if line.strip()
        ]
        return "\n".join(lines)

    return raw


def chunk_plain_text(text: str, size: int = 2000, overlap: int = 300):
    chunks = []
    start = 0

    while start < len(text):
        chunk = text[start:start + size].strip()
        if chunk:
            chunks.append({
                "text": chunk,
                "kind": "text",
                "owner": "",
                "name": "",
                "full_name": "",
                "signatures": "",
                "overload_count": 0,
            })
        start += size - overlap

    return chunks


_KIND_MAP = {"T": "type", "M": "method", "P": "property", "F": "field", "E": "event"}

_MEMBER_RE = re.compile(
    r"<member\s+name=\"([^\"]+)\"\s*>(.*?)</member>",
    flags=re.DOTALL | re.IGNORECASE,
)

_NAME_RE = re.compile(r"^([TMPFE]):([^(]+)(\([^)]*\))?$")


def _strip_ns(s: str) -> str:
    return (s.replace("Rhino.Geometry.Collections.", "")
             .replace("Rhino.Geometry.", "")
             .replace("Rhino.DocObjects.", "")
             .replace("Rhino.", "")
             .replace("System.Collections.Generic.", "")
             .replace("System.", ""))


def _split_camel(name: str):
    parts = re.findall(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+", name)
    return [p for p in parts if p]


def _out_param_hint(name: str, sigs):
    """If any overload has out/ref params (marked with @ in .NET XML), emit a
    Python-usage note: those become extra tuple return values, not arguments."""
    out_sigs = [s for s in sigs if "@" in s]
    if not out_sigs:
        return None

    sample = out_sigs[0]
    inner = sample.strip("()")
    parts = [p.strip() for p in inner.split(",") if p.strip()]
    in_args = [p for p in parts if not p.endswith("@")]
    out_args = [p.rstrip("@") for p in parts if p.endswith("@")]

    call_in = ", ".join(f"arg{i+1}" for i in range(len(in_args)))
    returns = ["result"] + [f"out_{i+1}" for i in range(len(out_args))]
    lhs = ", ".join(returns)

    note = (
        "Python note: this method has out/ref parameter(s) (marked @). "
        "In Python they are NOT passed as arguments — they come back as extra "
        f"return values in a tuple. Example: {lhs} = obj.{name}({call_in})"
    )
    return note


def _parse_member_xml(body_xml: str):
    soup = BeautifulSoup(body_xml, "xml")

    def grab(tag):
        node = soup.find(tag)
        return node.get_text(" ", strip=True) if node else ""

    summary = grab("summary")
    remarks = grab("remarks")
    returns = grab("returns")

    params = []
    for p in soup.find_all("param"):
        pname = p.get("name", "")
        ptext = p.get_text(" ", strip=True)
        if pname:
            params.append((pname, ptext))

    return {
        "summary": summary,
        "remarks": remarks,
        "returns": returns,
        "params": params,
    }


def _parse_member_name(raw_name: str):
    m = _NAME_RE.match(raw_name.strip())
    if not m:
        return None

    kind_code = m.group(1)
    full_name = m.group(2).strip()
    sig = (m.group(3) or "").strip()

    parts = full_name.rsplit(".", 1)
    if len(parts) == 2:
        owner_full, member = parts
    else:
        owner_full, member = "", full_name

    return {
        "kind": _KIND_MAP.get(kind_code, kind_code),
        "kind_code": kind_code,
        "owner_full": owner_full,
        "owner": owner_full.split(".")[-1] if owner_full else "",
        "name": member,
        "signature": _strip_ns(sig),
        "full_name": full_name,
    }


def _build_expanded_text(parsed_name, infos):
    owner = parsed_name["owner"]
    name = parsed_name["name"]
    kind = parsed_name["kind"]

    camel_words = _split_camel(name)
    camel_phrase = " ".join(camel_words)

    header_lines = [
        f"{owner}.{name}",
        f"{owner} {name}",
        camel_phrase,
        f"Class: {owner}",
        f"{kind.capitalize()}: {name}",
    ]

    summaries = []
    remarks_all = []
    returns_all = []
    params_all = []
    sigs = []

    for sig, info in infos:
        if sig:
            sigs.append(sig)
        if info["summary"]:
            summaries.append(info["summary"])
        if info["remarks"]:
            remarks_all.append(info["remarks"])
        if info["returns"]:
            returns_all.append(info["returns"])
        for pname, ptext in info["params"]:
            if ptext:
                params_all.append(f"{pname}: {ptext}")
            else:
                params_all.append(pname)

    uniq_summaries = list(dict.fromkeys(summaries))
    uniq_remarks = list(dict.fromkeys(remarks_all))
    uniq_returns = list(dict.fromkeys(returns_all))
    uniq_params = list(dict.fromkeys(params_all))
    uniq_sigs = list(dict.fromkeys(sigs))

    body = []
    if uniq_summaries:
        body.append("Summary: " + " | ".join(uniq_summaries))
    if uniq_remarks:
        body.append("Remarks: " + " ".join(uniq_remarks))
    if uniq_returns:
        body.append("Returns: " + " | ".join(uniq_returns))
    if uniq_params:
        body.append("Parameters: " + "; ".join(uniq_params))
    if uniq_sigs:
        if len(uniq_sigs) == 1:
            body.append(f"Signature: {name}{uniq_sigs[0]}")
        else:
            body.append("Overloads:")
            for s in uniq_sigs:
                body.append(f"  {name}{s}")

    hint = _out_param_hint(name, uniq_sigs)
    if hint:
        body.append(hint)

    text = "\n".join(header_lines + [""] + body).strip()
    return text, uniq_sigs


def chunk_xml_members(xml_text: str):
    chunks = []
    groups = {}
    order = []

    for raw_name, body in _MEMBER_RE.findall(xml_text):
        parsed = _parse_member_name(raw_name)
        if not parsed:
            continue

        info = _parse_member_xml(body)
        key = (parsed["kind_code"], parsed["owner_full"], parsed["name"])

        if key not in groups:
            groups[key] = {"parsed": parsed, "items": []}
            order.append(key)

        groups[key]["items"].append((parsed["signature"], info))

    for key in order:
        g = groups[key]
        parsed = g["parsed"]
        text, sigs = _build_expanded_text(parsed, g["items"])

        if not text:
            continue

        chunks.append({
            "text": text,
            "kind": parsed["kind"],
            "owner": parsed["owner"],
            "name": parsed["name"],
            "full_name": parsed["full_name"],
            "signatures": " | ".join(sigs),
            "overload_count": len(sigs) if sigs else (1 if parsed["kind"] != "type" else 0),
        })

    if not chunks:
        chunks = chunk_plain_text(xml_text)

    return chunks


def chunk_file(path: str, text: str):
    ext = os.path.splitext(path)[1].lower()

    if ext == ".xml":
        return chunk_xml_members(text)

    return chunk_plain_text(text)


_RS_HINT = (
    "[Library: rhinoscriptsyntax — high-level Python wrapper over RhinoCommon. "
    "Use in Python scripts inside Rhino/Grasshopper. Accepts Python-friendly "
    "inputs like [x,y,z] lists for points. For fine control (tolerances, batch "
    "operations) drop down to RhinoCommon instead.]"
)


def _format_py_signature(func_node):
    args = func_node.args
    parts = []

    pos = args.posonlyargs + args.args
    defaults = list(args.defaults)
    num_no_default = len(pos) - len(defaults)

    for i, a in enumerate(pos):
        if i >= num_no_default:
            d = defaults[i - num_no_default]
            parts.append(f"{a.arg}={_literal(d)}")
        else:
            parts.append(a.arg)

    if args.vararg:
        parts.append(f"*{args.vararg.arg}")

    for i, a in enumerate(args.kwonlyargs):
        d = args.kw_defaults[i]
        if d is None:
            parts.append(a.arg)
        else:
            parts.append(f"{a.arg}={_literal(d)}")

    if args.kwarg:
        parts.append(f"**{args.kwarg.arg}")

    return "(" + ", ".join(parts) + ")"


def _literal(node):
    try:
        return repr(ast.literal_eval(node))
    except Exception:
        try:
            return ast.unparse(node)
        except Exception:
            return "..."


def chunk_python_rhinoscript(doc_dir: str):
    chunks = []

    py_files = sorted(
        f for f in os.listdir(doc_dir)
        if f.endswith(".py") and not f.startswith("__") and f not in ("compat.py",)
    )

    for fname in py_files:
        module = os.path.splitext(fname)[0]
        path = os.path.join(doc_dir, fname)

        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            src = f.read()

        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue

        for node in tree.body:
            if not isinstance(node, ast.FunctionDef):
                continue
            if node.name.startswith("_"):
                continue

            sig = _format_py_signature(node)
            doc = ast.get_docstring(node) or ""

            summary = ""
            for line in doc.splitlines():
                s = line.strip()
                if s:
                    summary = s
                    break

            camel = " ".join(_split_camel(node.name))

            header = [
                f"rs.{node.name}",
                f"{module}.{node.name}",
                camel,
                f"Module: {module}",
                f"Function: rs.{node.name}{sig}",
                _RS_HINT,
            ]

            body_parts = []
            if summary:
                body_parts.append(f"Summary: {summary}")
            if doc.strip():
                body_parts.append(doc.strip())
            text = "\n".join(header + [""] + body_parts).strip()

            chunks.append({
                "text": text,
                "kind": "function",
                "owner": module,
                "name": node.name,
                "full_name": f"rhinoscriptsyntax.{module}.{node.name}",
                "signatures": sig,
                "overload_count": 1,
            })

    return chunks


def chunk_source(library: str):
    cfg = LIBRARIES[library]
    chunker = cfg.get("chunker", "xml_dotnet")
    source = cfg["source_file"]

    if chunker == "python_rhinoscript":
        return chunk_python_rhinoscript(source)

    text = read_file(source)
    if not text.strip():
        return []
    return chunk_xml_members(text)


def _bm25_tokenize(texts):
    return bm25s.tokenize(texts, stopwords="en", show_progress=False)


def ingest_library(library: str, reset: bool = True):
    if library not in LIBRARIES:
        raise ValueError(f"Unknown library: {library}. Available: {available_libraries()}")

    cfg = LIBRARIES[library]
    source_file = cfg["source_file"]

    if not os.path.exists(source_file):
        raise FileNotFoundError(f"Source file missing for {library}: {source_file}")

    client = get_client(library)

    if reset:
        try:
            client.delete_collection(library)
            print(f"[{library}] [RESET] Deleted old collection")
        except Exception:
            print(f"[{library}] [RESET] No old collection found")

    collection = client.get_or_create_collection(
        library,
        metadata={"hnsw:space": "cosine"},
    )

    model = get_model()

    print(f"[{library}] [INFO] Reading {source_file}")
    chunks = chunk_source(library)

    if not chunks:
        print(f"[{library}] [SKIP] No chunks produced")
        return 0, 1

    print(f"[{library}] [CHUNK] {len(chunks)} chunks produced")

    all_ids = []
    all_docs = []
    all_metas = []
    filename = os.path.basename(source_file.rstrip("/\\"))

    for idx, chunk in enumerate(chunks):
        key = f"{library}::{chunk.get('full_name') or idx}"
        chunk_id = stable_id(key)

        all_ids.append(chunk_id)
        all_docs.append(chunk["text"])
        all_metas.append({
            "library": library,
            "source": source_file,
            "filename": filename,
            "chunk_index": idx,
            "kind": chunk["kind"],
            "owner": chunk["owner"],
            "name": chunk["name"],
            "full_name": chunk["full_name"],
            "signatures": chunk["signatures"],
            "overload_count": chunk["overload_count"],
        })

    print(f"[{library}] [INFO] Embedding {len(all_docs)} chunks...")

    batch = 64
    for i in range(0, len(all_docs), batch):
        sub_docs = all_docs[i:i + batch]
        sub_ids = all_ids[i:i + batch]
        sub_metas = all_metas[i:i + batch]
        embs = model.encode(sub_docs, show_progress_bar=False, normalize_embeddings=True).tolist()
        collection.add(ids=sub_ids, documents=sub_docs, embeddings=embs, metadatas=sub_metas)
        if (i // batch) % 10 == 0:
            print(f"[{library}] [EMBED] {i + len(sub_docs)}/{len(all_docs)}")

    print(f"[{library}] [INFO] Building BM25 index...")
    bdir = bm25_dir(library)
    os.makedirs(bdir, exist_ok=True)

    retriever = bm25s.BM25()
    tokens = _bm25_tokenize(all_docs)
    retriever.index(tokens, show_progress=False)
    retriever.save(bdir, corpus=None)

    with open(bm25_meta_path(library), "w", encoding="utf-8") as f:
        json.dump({"ids": all_ids, "metas": all_metas}, f, ensure_ascii=False)

    _bm25_state.pop(library, None)

    print(f"[{library}] [DONE] Indexed {len(all_docs)} chunks")
    return len(all_docs), 0


def ingest_all(reset: bool = True):
    results = {}
    for lib in available_libraries():
        if not os.path.exists(LIBRARIES[lib]["source_file"]):
            print(f"[{lib}] [SKIP] Source file not found: {LIBRARIES[lib]['source_file']}")
            continue
        n, skipped = ingest_library(lib, reset=reset)
        results[lib] = (n, skipped)
    return results


def _load_bm25(library: str):
    if library in _bm25_state:
        return _bm25_state[library]

    meta_path = bm25_meta_path(library)
    if not os.path.exists(meta_path):
        return None

    retriever = bm25s.BM25.load(bm25_dir(library))
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    _bm25_state[library] = {
        "retriever": retriever,
        "ids": meta["ids"],
        "metas": meta["metas"],
    }
    return _bm25_state[library]


def _vec_search(library: str, query: str, n: int):
    collection = get_collection(library)
    model = get_model()
    emb = model.encode(QUERY_PREFIX + query, normalize_embeddings=True).tolist()

    res = collection.query(
        query_embeddings=[emb],
        n_results=n,
        include=["documents", "metadatas", "distances"],
    )

    ids = res.get("ids", [[]])[0]
    docs = res.get("documents", [[]])[0]
    metas = res.get("metadatas", [[]])[0]
    dists = res.get("distances", [[]])[0]

    out = []
    for cid, doc, meta, dist in zip(ids, docs, metas, dists):
        meta = dict(meta)
        meta.setdefault("library", library)
        out.append({
            "id": cid,
            "library": library,
            "text": doc,
            "metadata": meta,
            "distance": dist,
        })
    return out


def _bm25_search(library: str, query: str, n: int):
    state = _load_bm25(library)
    if state is None:
        return []

    tokens = _bm25_tokenize([query])
    k = min(n, len(state["ids"]))
    if k == 0:
        return []
    indices, scores = state["retriever"].retrieve(tokens, k=k, show_progress=False)

    out = []
    for idx, score in zip(indices[0], scores[0]):
        idx = int(idx)
        meta = dict(state["metas"][idx])
        meta.setdefault("library", library)
        out.append({
            "id": state["ids"][idx],
            "library": library,
            "metadata": meta,
            "score": float(score),
            "_idx": idx,
        })
    return out


def _rrf_fuse(hit_lists, k_rrf: int = 60):
    fused = {}

    for hits in hit_lists:
        for rank, h in enumerate(hits):
            cid = h["id"]
            channel = h.get("_channel", "unknown")
            entry = fused.setdefault(cid, {
                "id": cid,
                "library": h.get("library", ""),
                "score": 0.0,
                "channels": set(),
                "vec": None,
                "bm25": None,
            })
            entry["score"] += 1.0 / (k_rrf + rank + 1)
            entry["channels"].add(channel)
            if channel == "vec":
                entry["vec"] = h
            elif channel == "bm25":
                entry["bm25"] = h

    return sorted(fused.values(), key=lambda x: x["score"], reverse=True)


def _hydrate_document(library: str, cid: str, vec_hit, fallback_meta):
    if vec_hit is not None:
        return vec_hit["text"], vec_hit["metadata"]

    collection = get_collection(library)
    got = collection.get(ids=[cid], include=["documents", "metadatas"])
    if got["ids"]:
        meta = dict(got["metadatas"][0])
        meta.setdefault("library", library)
        return got["documents"][0], meta

    return "", fallback_meta or {}


def compact_chunk(text: str, meta: dict) -> str:
    owner = meta.get("owner", "")
    name = meta.get("name", "")
    kind = meta.get("kind", "")
    sigs = meta.get("signatures", "")

    if not owner and not name:
        return text.strip()

    summary = ""
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("Summary:"):
            summary = s[len("Summary:"):].strip()
            break

    head = f"{owner}.{name}".strip(".")
    if kind == "method" and sigs:
        sig_list = [s.strip() for s in sigs.split("|") if s.strip()]
        if len(sig_list) == 1:
            head = f"{head}{sig_list[0]}"
        else:
            head = f"{head}  [{len(sig_list)} overloads]"

    if summary:
        return f"{head} — {summary}"
    return head


def _resolve_scope(scope=None, task=None):
    if scope is None and task is not None:
        if task not in TASK_SCOPE:
            raise ValueError(f"Unknown task: {task}. Available: {list(TASK_SCOPE)}")
        scope = TASK_SCOPE[task]

    if scope is None:
        return [lib for lib in available_libraries() if os.path.exists(library_dir(lib))]

    if isinstance(scope, str):
        scope = [scope]

    bad = [s for s in scope if s not in LIBRARIES]
    if bad:
        raise ValueError(f"Unknown libraries in scope: {bad}. Available: {available_libraries()}")

    # Drop libraries that haven't been ingested yet (e.g. rhinoscriptsyntax placeholder).
    return [lib for lib in scope if os.path.exists(library_dir(lib))]


def hybrid_search(query: str, n_results: int = 5, fetch: int = 30, scope=None, task=None):
    libraries = _resolve_scope(scope, task)

    all_hit_lists = []
    for lib in libraries:
        vec_hits = _vec_search(lib, query, fetch)
        for h in vec_hits:
            h["_channel"] = "vec"
        bm25_hits = _bm25_search(lib, query, fetch)
        for h in bm25_hits:
            h["_channel"] = "bm25"
        all_hit_lists.append(vec_hits)
        all_hit_lists.append(bm25_hits)

    fused = _rrf_fuse(all_hit_lists)[:n_results]

    output = []
    for f in fused:
        lib = f["library"]
        meta_fallback = f["bm25"]["metadata"] if f["bm25"] else None
        text, meta = _hydrate_document(lib, f["id"], f["vec"], meta_fallback)
        channels = f["channels"]
        if "vec" in channels and "bm25" in channels:
            via = "vec+bm25"
        elif "vec" in channels:
            via = "vec"
        else:
            via = "bm25"

        output.append({
            "id": f["id"],
            "library": lib,
            "score": f["score"],
            "kind": meta.get("kind", ""),
            "owner": meta.get("owner", ""),
            "name": meta.get("name", ""),
            "signatures": meta.get("signatures", ""),
            "filename": meta.get("filename", ""),
            "text": text,
            "compact": compact_chunk(text, meta),
            "via": via,
        })
    return output


def search(query: str, n_results: int = 5, scope=None, task=None):
    return hybrid_search(query, n_results=n_results, scope=scope, task=task)


def search_methods(query: str, n_results: int = 8, scope=None, task=None):
    results = hybrid_search(query, n_results=n_results * 2, scope=scope, task=task)

    seen = set()
    out = []
    for r in results:
        if not r["name"]:
            continue
        key = (r["library"], r["owner"], r["name"])
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "library": r["library"],
            "kind": r["kind"],
            "owner": r["owner"],
            "name": r["name"],
            "signatures": r["signatures"],
            "via": r["via"],
        })
        if len(out) >= n_results:
            break
    return out


def get_member_detail(owner: str, name: str, scope=None, task=None):
    libraries = _resolve_scope(scope, task)

    out = []
    for lib in libraries:
        collection = get_collection(lib)
        try:
            res = collection.get(
                where={"$and": [{"owner": owner}, {"name": name}]},
                include=["documents", "metadatas"],
            )
        except Exception:
            continue

        for doc, meta in zip(res["documents"], res["metadatas"]):
            meta = dict(meta)
            meta.setdefault("library", lib)
            out.append({
                "library": lib,
                "kind": meta.get("kind", ""),
                "owner": meta.get("owner", ""),
                "name": meta.get("name", ""),
                "signatures": meta.get("signatures", ""),
                "full_name": meta.get("full_name", ""),
                "text": doc,
                "compact": compact_chunk(doc, meta),
            })
    return out


def list_class_members(owner: str, kind: str = None, limit: int = 200, scope=None, task=None):
    libraries = _resolve_scope(scope, task)

    out = []
    for lib in libraries:
        collection = get_collection(lib)

        where = {"owner": owner}
        if kind:
            where = {"$and": [{"owner": owner}, {"kind": kind}]}

        try:
            res = collection.get(where=where, include=["metadatas"], limit=limit)
        except Exception:
            continue

        for meta in res["metadatas"]:
            out.append({
                "library": lib,
                "kind": meta.get("kind", ""),
                "owner": meta.get("owner", ""),
                "name": meta.get("name", ""),
                "signatures": meta.get("signatures", ""),
                "overload_count": meta.get("overload_count", 0),
            })

    order = {"type": 0, "method": 1, "property": 2, "field": 3, "event": 4, "": 5}
    out.sort(key=lambda x: (x["library"], order.get(x["kind"], 9), x["name"]))
    return out


def format_results(results):
    blocks = []
    for r in results:
        lib = r.get("library", "")
        prefix = f"[{lib}] " if lib else ""
        blocks.append(f"{prefix}{r['compact']}")
    return "\n\n---\n\n".join(blocks)


def format_method_list(methods):
    lines = []
    for m in methods:
        sigs = m.get("signatures", "")
        sig_list = [s.strip() for s in sigs.split("|") if s.strip()] if sigs else []
        lib = m.get("library", "")
        lib_prefix = f"[{lib}] " if lib else ""
        kind_prefix = f"[{m['kind']}]"
        head = f"{lib_prefix}{kind_prefix} {m['owner']}.{m['name']}".strip()
        if m["kind"] == "method" and sig_list:
            if len(sig_list) == 1:
                lines.append(f"{head}{sig_list[0]}")
            else:
                lines.append(f"{head}  [{len(sig_list)} overloads]")
        else:
            lines.append(head)
    return "\n".join(lines)
