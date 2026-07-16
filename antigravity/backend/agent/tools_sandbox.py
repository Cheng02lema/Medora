"""病例整理沙箱工具：路径 jail + 白名单 shell + 文件布局。"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from antigravity.backend.patient import IMAGE_EXTS

# 允许的 shell 可执行名（第一个 token）
SHELL_ALLOW = frozenset({
    "ls", "find", "mkdir", "cp", "mv", "file", "pwd", "echo", "cat", "head", "tail",
    "wc", "sort", "uniq", "basename", "dirname", "stat", "du", "tree",
    "unzip", "tar", "python3", "rsync",
})

SHELL_DENY_PATTERNS = [
    r"\brm\b", r"\bsudo\b", r"\bchmod\b", r"\bchown\b", r"\bcurl\b", r"\bwget\b",
    r"\bssh\b", r"\bscp\b", r">\s*/", r"\|\s*sh\b", r"\|\s*bash\b", r"`",
    r"\$\(", r"\beval\b", r"\bexport\b", r"\bpython\b(?!3)",
]

_SAFE_NAME = re.compile(r"[^\w\u4e00-\u9fff\-_.（）()]+", re.UNICODE)


class SandboxError(Exception):
    pass


class PathJail:
    def __init__(self, roots: List[Path]):
        self.roots = [r.resolve() for r in roots if r]

    def ensure_inside(self, path: Path) -> Path:
        p = path.expanduser().resolve()
        for root in self.roots:
            try:
                p.relative_to(root)
                return p
            except ValueError:
                continue
        raise SandboxError(f"路径越界，禁止访问: {p}")

    def ensure_parent_inside(self, path: Path) -> Path:
        p = path.expanduser().resolve()
        return self.ensure_inside(p if p.exists() else p.parent)


def safe_patient_name(name: str, fallback: str = "未知病人") -> str:
    raw = (name or "").strip() or fallback
    cleaned = _SAFE_NAME.sub("_", raw).strip("._ ") or fallback
    return cleaned[:80]


def list_dir(jail: PathJail, path: str, max_entries: int = 200) -> Dict[str, Any]:
    p = jail.ensure_inside(Path(path))
    if not p.is_dir():
        raise SandboxError(f"不是目录: {p}")
    entries = []
    for child in sorted(p.iterdir())[:max_entries]:
        try:
            st = child.stat()
            entries.append({
                "name": child.name,
                "path": str(child),
                "is_dir": child.is_dir(),
                "size": st.st_size if child.is_file() else None,
            })
        except OSError:
            continue
    return {"path": str(p), "count": len(entries), "entries": entries}


def scan_images(jail: PathJail, path: str, max_files: int = 2000) -> Dict[str, Any]:
    p = jail.ensure_inside(Path(path))
    if not p.exists():
        raise SandboxError(f"路径不存在: {p}")
    files = []
    root = p if p.is_dir() else p.parent
    for f in sorted(root.rglob("*")):
        if not f.is_file():
            continue
        if f.suffix.lower() not in IMAGE_EXTS:
            continue
        # 跳过 agent 元数据目录
        if "_agent" in f.parts:
            continue
        try:
            rel = str(f.relative_to(p if p.is_dir() else root))
        except ValueError:
            rel = f.name
        parent_rel = str(Path(rel).parent) if Path(rel).parent != Path(".") else ""
        files.append({
            "path": str(f),
            "name": f.name,
            "relative": rel.replace("\\", "/"),
            "parent": parent_rel.replace("\\", "/") if parent_rel else "",
            "size": f.stat().st_size,
        })
        if len(files) >= max_files:
            break
    # 按一级子目录汇总
    by_folder: Dict[str, int] = {}
    for f in files:
        top = f["parent"].split("/")[0] if f["parent"] else "(根目录)"
        by_folder[top] = by_folder.get(top, 0) + 1
    return {
        "root": str(p if p.is_dir() else root),
        "image_count": len(files),
        "by_folder": by_folder,
        "files": files[:500],  # 响应截断
        "truncated": len(files) > 500,
    }


def read_text(jail: PathJail, path: str, max_chars: int = 8000) -> Dict[str, Any]:
    p = jail.ensure_inside(Path(path))
    if not p.is_file():
        raise SandboxError(f"不是文件: {p}")
    if p.suffix.lower() not in {".txt", ".md", ".csv", ".json", ".log"}:
        raise SandboxError("仅允许读取 txt/md/csv/json/log")
    text = p.read_text(encoding="utf-8", errors="replace")
    return {"path": str(p), "text": text[:max_chars], "truncated": len(text) > max_chars}


def run_shell(jail: PathJail, command: str, cwd: str, timeout: int = 30) -> Dict[str, Any]:
    """白名单 shell，cwd 必须在 jail 内。"""
    cmd = (command or "").strip()
    if not cmd:
        raise SandboxError("空命令")
    for pat in SHELL_DENY_PATTERNS:
        if re.search(pat, cmd, re.I):
            raise SandboxError(f"命令被拒绝（匹配危险模式）: {pat}")
    try:
        tokens = shlex.split(cmd)
    except ValueError as exc:
        raise SandboxError(f"命令解析失败: {exc}") from exc
    if not tokens:
        raise SandboxError("空命令")
    exe = Path(tokens[0]).name
    if exe not in SHELL_ALLOW:
        raise SandboxError(f"命令不在白名单: {exe}")

    work = jail.ensure_inside(Path(cwd))
    if not work.is_dir():
        raise SandboxError(f"cwd 不是目录: {work}")

    # 简单路径参数检查：含 / 的参数若是绝对路径必须在 jail
    for tok in tokens[1:]:
        if tok.startswith("-"):
            continue
        if tok.startswith("/") or tok.startswith("~"):
            try:
                jail.ensure_inside(Path(tok))
            except SandboxError:
                raise SandboxError(f"参数路径越界: {tok}")

    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            tokens,
            cwd=str(work),
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "PATH": os.environ.get("PATH", "/usr/bin:/bin:/usr/local/bin")},
        )
    except subprocess.TimeoutExpired as exc:
        raise SandboxError(f"命令超时({timeout}s)") from exc
    except FileNotFoundError as exc:
        raise SandboxError(f"找不到命令: {exe}") from exc

    out = (proc.stdout or "")[:12000]
    err = (proc.stderr or "")[:4000]
    return {
        "command": cmd,
        "cwd": str(work),
        "returncode": proc.returncode,
        "stdout": out,
        "stderr": err,
        "ms": round((time.perf_counter() - t0) * 1000, 1),
    }


def web_search(query: str, max_results: int = 5) -> Dict[str, Any]:
    """轻量搜索（DuckDuckGo HTML 简易解析）。失败则返回空并说明。"""
    q = (query or "").strip()
    if not q:
        raise SandboxError("空查询")
    # 隐私：拒绝过长查询（可能含病历全文）
    if len(q) > 200:
        raise SandboxError("查询过长，请只用关键词（勿粘贴病历全文）")
    try:
        import urllib.parse
        import urllib.request
        url = "https://api.duckduckgo.com/?" + urllib.parse.urlencode({
            "q": q,
            "format": "json",
            "no_html": 1,
            "skip_disambig": 1,
        })
        req = urllib.request.Request(url, headers={"User-Agent": "MedoraOrganizeAgent/1.0"})
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
        results = []
        if data.get("AbstractText"):
            results.append({
                "title": data.get("Heading") or "摘要",
                "snippet": data.get("AbstractText"),
                "url": data.get("AbstractURL") or "",
            })
        for item in (data.get("RelatedTopics") or [])[:max_results]:
            if isinstance(item, dict) and item.get("Text"):
                results.append({
                    "title": (item.get("Text") or "")[:80],
                    "snippet": item.get("Text") or "",
                    "url": item.get("FirstURL") or "",
                })
        return {"query": q, "results": results[:max_results], "provider": "duckduckgo"}
    except Exception as exc:
        return {
            "query": q,
            "results": [],
            "provider": "none",
            "error": f"搜索不可用: {exc}",
            "hint": "可继续用本地规则整理，无需搜索",
        }


def propose_layout(jail: PathJail, work_path: str, out_path: str) -> Dict[str, Any]:
    """启发式：已有「一人一夹」则映射；扁平图片则按文件名聚类到待确认。"""
    work = jail.ensure_inside(Path(work_path))
    out = jail.ensure_inside(Path(out_path)) if Path(out_path).exists() else Path(out_path).expanduser().resolve()
    # out 允许尚未创建，但父目录须在 jail
    jail.ensure_parent_inside(out)

    scan = scan_images(jail, str(work))
    files = scan["files"]
    if scan.get("truncated"):
        # 重新完整扫（内部已截断 files；这里用 by_folder 够用）
        pass

    # 完整路径列表再扫一次（不截断到 500 用于 plan）
    all_files = []
    root = work if work.is_dir() else work.parent
    for f in sorted(root.rglob("*")):
        if f.is_file() and f.suffix.lower() in IMAGE_EXTS and "_agent" not in f.parts:
            all_files.append(f)

    mappings: List[Dict[str, Any]] = []
    # 情况1：work 下一级子目录含图 → 每夹一病人
    subdirs = [d for d in sorted(work.iterdir()) if d.is_dir() and d.name != "_agent"] if work.is_dir() else []
    patient_dirs = []
    for d in subdirs:
        imgs = [f for f in d.rglob("*") if f.is_file() and f.suffix.lower() in IMAGE_EXTS]
        if imgs:
            patient_dirs.append((d, imgs))

    covered: set = set()
    if patient_dirs:
        for d, imgs in patient_dirs:
            pname = safe_patient_name(d.name)
            for i, f in enumerate(sorted(imgs), 1):
                ext = f.suffix.lower()
                dest_rel = f"{pname}/{i:02d}{ext}"
                mappings.append({
                    "src": str(f),
                    "dest_rel": dest_rel,
                    "patient": pname,
                    "confidence": "high",
                    "reason": "已有病人子文件夹",
                })
                covered.add(str(f.resolve()))

    # 根目录散图 / 未被覆盖的图：按文件名启发式分组
    leftover = [f for f in all_files if str(f.resolve()) not in covered]
    if leftover:
        groups: Dict[str, List[Path]] = {}
        for f in leftover:
            m = re.search(r"[\u4e00-\u9fff]{2,4}", f.stem)
            key = m.group(0) if m else "待确认_未命名"
            groups.setdefault(key, []).append(f)
        for key, imgs in sorted(groups.items()):
            pname = safe_patient_name(key)
            conf = "medium" if key != "待确认_未命名" else "low"
            for i, f in enumerate(sorted(imgs), 1):
                mappings.append({
                    "src": str(f),
                    "dest_rel": f"{pname}/{i:02d}{f.suffix.lower()}",
                    "patient": pname,
                    "confidence": conf,
                    "reason": "文件名启发式分组" if conf == "medium" else "无法识别姓名",
                })

    patients = sorted({m["patient"] for m in mappings})
    return {
        "work_path": str(work),
        "out_path": str(out),
        "patient_count": len(patients),
        "file_count": len(mappings),
        "patients": patients,
        "mappings": mappings,
        "needs_confirm": any(m["confidence"] != "high" for m in mappings),
        "mode": "copy",
    }


def apply_layout(
    jail: PathJail,
    plan: Dict[str, Any],
    mode: str = "copy",
) -> Dict[str, Any]:
    mode = mode if mode in ("copy", "move") else "copy"
    out = Path(plan["out_path"]).expanduser()
    jail.ensure_parent_inside(out)
    out.mkdir(parents=True, exist_ok=True)
    jail.ensure_inside(out)

    done = 0
    errors = []
    for m in plan.get("mappings") or []:
        src = Path(m["src"])
        dest_rel = m["dest_rel"]
        try:
            src = jail.ensure_inside(src)
            dest = (out / dest_rel).resolve()
            jail.ensure_inside(dest.parent if not dest.exists() else dest)
            # dest 必须在 out 下
            dest.relative_to(out.resolve())
            dest.parent.mkdir(parents=True, exist_ok=True)
            if mode == "move":
                shutil.move(str(src), str(dest))
            else:
                shutil.copy2(str(src), str(dest))
            done += 1
        except Exception as exc:
            errors.append({"src": str(src), "error": str(exc)})

    return {
        "out_path": str(out),
        "mode": mode,
        "copied_or_moved": done,
        "error_count": len(errors),
        "errors": errors[:50],
    }


def validate_layout(jail: PathJail, out_path: str) -> Dict[str, Any]:
    out = jail.ensure_inside(Path(out_path))
    if not out.is_dir():
        return {"ok": False, "error": f"输出目录不存在: {out}", "patients": []}
    patients = []
    for d in sorted(out.iterdir()):
        if not d.is_dir() or d.name.startswith("_"):
            continue
        imgs = [f for f in d.rglob("*") if f.is_file() and f.suffix.lower() in IMAGE_EXTS]
        patients.append({
            "name": d.name,
            "path": str(d),
            "image_count": len(imgs),
            "ok": len(imgs) > 0,
        })
    ok = len(patients) > 0 and all(p["ok"] for p in patients)
    return {
        "ok": ok,
        "patient_count": len(patients),
        "image_total": sum(p["image_count"] for p in patients),
        "patients": patients,
        "import_ready": ok,
        "message": f"可导入 {len(patients)} 位病人，共 {sum(p['image_count'] for p in patients)} 张图" if ok else "结构不完整",
    }


def preview_tree(jail: PathJail, path: str, max_depth: int = 3) -> Dict[str, Any]:
    root = jail.ensure_inside(Path(path))
    lines: List[str] = []

    def walk(d: Path, prefix: str, depth: int):
        if depth > max_depth:
            return
        try:
            children = sorted(d.iterdir(), key=lambda x: (not x.is_dir(), x.name))
        except OSError:
            return
        for i, c in enumerate(children):
            if c.name.startswith(".") or c.name == "_agent":
                continue
            last = i == len(children) - 1
            branch = "└── " if last else "├── "
            if c.is_dir():
                n_img = sum(1 for f in c.rglob("*") if f.is_file() and f.suffix.lower() in IMAGE_EXTS)
                lines.append(f"{prefix}{branch}{c.name}/  ({n_img} 图)")
                extension = "    " if last else "│   "
                walk(c, prefix + extension, depth + 1)
            else:
                if c.suffix.lower() in IMAGE_EXTS or depth <= 1:
                    lines.append(f"{prefix}{branch}{c.name}")

    lines.append(str(root) + "/")
    if root.is_dir():
        walk(root, "", 1)
    return {"path": str(root), "tree": "\n".join(lines[:400])}


def scan_materials(jail: PathJail, path: str) -> Dict[str, Any]:
    """扫描图片 + PDF。"""
    p = jail.ensure_inside(Path(path))
    img = scan_images(jail, str(p))
    pdfs = []
    root = p if p.is_dir() else p.parent
    for f in sorted(root.rglob("*.pdf")):
        if "_agent" in f.parts or "/_pages/" in str(f).replace("\\", "/"):
            continue
        try:
            info = pdf_info(jail, str(f))
            pdfs.append(info)
        except Exception as exc:
            pdfs.append({"path": str(f), "name": f.name, "error": str(exc)})
    return {
        "root": str(root),
        "image_count": img["image_count"],
        "by_folder": img["by_folder"],
        "pdf_count": len(pdfs),
        "pdfs": pdfs,
        "files_sample": img.get("files") or [],
    }


def pdf_info(jail: PathJail, path: str) -> Dict[str, Any]:
    import fitz
    p = jail.ensure_inside(Path(path))
    if not p.is_file() or p.suffix.lower() != ".pdf":
        raise SandboxError(f"不是 PDF 文件: {p}")
    doc = fitz.open(str(p))
    try:
        return {
            "path": str(p),
            "name": p.name,
            "page_count": doc.page_count,
            "encrypted": bool(doc.is_encrypted),
        }
    finally:
        doc.close()


def pdf_to_images(
    jail: PathJail,
    path: str,
    out_dir: str,
    dpi: int = 150,
    max_pages: int = 500,
) -> Dict[str, Any]:
    """将 PDF 每页渲染为 jpg，输出到 out_dir。"""
    import fitz
    src = jail.ensure_inside(Path(path))
    if not src.is_file() or src.suffix.lower() != ".pdf":
        raise SandboxError(f"不是 PDF: {src}")
    out = Path(out_dir).expanduser()
    jail.ensure_parent_inside(out)
    out.mkdir(parents=True, exist_ok=True)
    out = jail.ensure_inside(out)

    doc = fitz.open(str(src))
    try:
        if doc.is_encrypted:
            raise SandboxError("PDF 已加密，无法渲染")
        n = min(doc.page_count, max_pages)
        zoom = max(0.5, min(3.0, float(dpi) / 72.0))
        mat = fitz.Matrix(zoom, zoom)
        pages = []
        for i in range(n):
            page = doc.load_page(i)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            name = f"p{i + 1:03d}.jpg"
            dest = out / name
            pix.save(str(dest))
            pages.append({"page": i + 1, "path": str(dest), "name": name})
        return {
            "pdf": str(src),
            "out_dir": str(out),
            "page_count": doc.page_count,
            "rendered": len(pages),
            "dpi": dpi,
            "pages": pages,
        }
    finally:
        doc.close()


def split_by_page_count(
    jail: PathJail,
    pages_dir: str,
    out_path: str,
    pages_per_patient: int = 2,
    name_prefix: str = "病人",
    mode: str = "copy",
) -> Dict[str, Any]:
    """将已渲染的页图按每 N 页一组写入 out_path/病人_xxx/。"""
    pages_per_patient = int(pages_per_patient or 2)
    if pages_per_patient < 1:
        raise SandboxError("pages_per_patient 必须 >= 1")
    src_dir = jail.ensure_inside(Path(pages_dir))
    if not src_dir.is_dir():
        raise SandboxError(f"页图目录不存在: {src_dir}")
    out = Path(out_path).expanduser()
    jail.ensure_parent_inside(out)
    out.mkdir(parents=True, exist_ok=True)
    out = jail.ensure_inside(out)

    images = sorted(
        f for f in src_dir.iterdir()
        if f.is_file() and f.suffix.lower() in IMAGE_EXTS
    )
    if not images:
        # 也支持子目录里的页图
        images = sorted(
            f for f in src_dir.rglob("*")
            if f.is_file() and f.suffix.lower() in IMAGE_EXTS
        )
    if not images:
        raise SandboxError(f"页图目录无图片: {src_dir}")

    mode = mode if mode in ("copy", "move") else "copy"
    groups = []
    prefix = safe_patient_name(name_prefix, "病人")
    for gi, start in enumerate(range(0, len(images), pages_per_patient), 1):
        chunk = images[start:start + pages_per_patient]
        patient = f"{prefix}_{gi:03d}"
        dest_dir = out / patient
        dest_dir.mkdir(parents=True, exist_ok=True)
        files = []
        for i, f in enumerate(chunk, 1):
            dest = dest_dir / f"{i:02d}{f.suffix.lower()}"
            if mode == "move":
                shutil.move(str(f), str(dest))
            else:
                shutil.copy2(str(f), str(dest))
            files.append(str(dest))
        groups.append({"patient": patient, "pages": len(chunk), "files": files})

    return {
        "out_path": str(out),
        "pages_per_patient": pages_per_patient,
        "source_pages": len(images),
        "patient_count": len(groups),
        "patients": [g["patient"] for g in groups],
        "groups": groups,
        "mode": mode,
        "import_ready": len(groups) > 0,
    }


def group_images_by_count(
    jail: PathJail,
    path: str,
    out_path: str,
    pages_per_patient: int = 2,
    name_prefix: str = "病人",
    mode: str = "copy",
) -> Dict[str, Any]:
    """扁平图片目录按每 N 张分组（不经过 PDF）。"""
    return split_by_page_count(
        jail,
        pages_dir=path,
        out_path=out_path,
        pages_per_patient=pages_per_patient,
        name_prefix=name_prefix,
        mode=mode,
    )


# OpenAI / DeepSeek function-calling 格式
OPENAI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "列出目录内容",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scan_images",
            "description": "扫描目录下图片并按文件夹汇总",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scan_materials",
            "description": "扫描目录中的图片和 PDF（含 PDF 页数）",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pdf_info",
            "description": "获取 PDF 页数等信息",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pdf_to_images",
            "description": "将 PDF 每一页渲染为 jpg 图片到 out_dir",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "PDF 路径"},
                    "out_dir": {"type": "string", "description": "页图输出目录"},
                    "dpi": {"type": "integer", "description": "默认 150"},
                },
                "required": ["path", "out_dir"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "split_by_page_count",
            "description": "将页图目录按每 N 页分成多个病人文件夹（如每 2 页一个病人）",
            "parameters": {
                "type": "object",
                "properties": {
                    "pages_dir": {"type": "string", "description": "pdf_to_images 输出的页图目录"},
                    "out_path": {"type": "string", "description": "最终一人一夹输出目录"},
                    "pages_per_patient": {"type": "integer", "description": "每个病人页数，例如 2"},
                    "name_prefix": {"type": "string", "description": "文件夹前缀，默认 病人"},
                    "mode": {"type": "string", "enum": ["copy", "move"]},
                },
                "required": ["pages_dir", "out_path", "pages_per_patient"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "group_images_by_count",
            "description": "扁平图片按每 N 张分成病人文件夹",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "out_path": {"type": "string"},
                    "pages_per_patient": {"type": "integer"},
                    "name_prefix": {"type": "string"},
                    "mode": {"type": "string", "enum": ["copy", "move"]},
                },
                "required": ["path", "out_path", "pages_per_patient"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_layout",
            "description": "对已有一人一夹或散图生成整理计划",
            "parameters": {
                "type": "object",
                "properties": {
                    "work_path": {"type": "string"},
                    "out_path": {"type": "string"},
                },
                "required": ["work_path", "out_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "apply_layout",
            "description": "执行 propose_layout 的计划（默认 copy）",
            "parameters": {
                "type": "object",
                "properties": {
                    "plan": {"type": "object"},
                    "mode": {"type": "string", "enum": ["copy", "move"]},
                },
                "required": ["plan"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "validate_layout",
            "description": "校验输出目录是否可 import-folder",
            "parameters": {
                "type": "object",
                "properties": {"out_path": {"type": "string"}},
                "required": ["out_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "preview_tree",
            "description": "预览目录树",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "短关键词网络搜索，禁止传病历全文",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
]

TOOL_SPECS = [
    {"name": t["function"]["name"], "description": t["function"]["description"], "params": list(t["function"]["parameters"].get("properties") or {})}
    for t in OPENAI_TOOLS
]


def execute_tool(name: str, args: Dict[str, Any], jail: PathJail, default_cwd: str) -> Dict[str, Any]:
    name = (name or "").strip()
    args = args or {}
    if name == "list_dir":
        return list_dir(jail, args.get("path") or default_cwd)
    if name == "scan_images":
        return scan_images(jail, args.get("path") or default_cwd)
    if name == "scan_materials":
        return scan_materials(jail, args.get("path") or default_cwd)
    if name == "pdf_info":
        return pdf_info(jail, args["path"])
    if name == "pdf_to_images":
        return pdf_to_images(
            jail,
            args["path"],
            args.get("out_dir") or str(Path(default_cwd) / "_pages"),
            dpi=int(args.get("dpi") or 150),
        )
    if name == "split_by_page_count":
        return split_by_page_count(
            jail,
            pages_dir=args.get("pages_dir") or args.get("path") or default_cwd,
            out_path=args.get("out_path") or default_cwd,
            pages_per_patient=int(args.get("pages_per_patient") or 2),
            name_prefix=args.get("name_prefix") or "病人",
            mode=args.get("mode") or "copy",
        )
    if name == "group_images_by_count":
        return group_images_by_count(
            jail,
            path=args.get("path") or default_cwd,
            out_path=args.get("out_path") or default_cwd,
            pages_per_patient=int(args.get("pages_per_patient") or 2),
            name_prefix=args.get("name_prefix") or "病人",
            mode=args.get("mode") or "copy",
        )
    if name == "read_text":
        return read_text(jail, args["path"])
    if name == "run_shell":
        return run_shell(jail, args.get("command", ""), args.get("cwd") or default_cwd)
    if name == "web_search":
        return web_search(args.get("query", ""))
    if name == "propose_layout":
        return propose_layout(jail, args.get("work_path") or default_cwd, args.get("out_path") or default_cwd)
    if name == "apply_layout":
        plan = args.get("plan")
        if isinstance(plan, str):
            plan = json.loads(plan)
        if not isinstance(plan, dict):
            raise SandboxError("apply_layout 需要 plan 对象")
        return apply_layout(jail, plan, mode=args.get("mode") or "copy")
    if name == "validate_layout":
        return validate_layout(jail, args.get("out_path") or default_cwd)
    if name == "preview_tree":
        return preview_tree(jail, args.get("path") or default_cwd)
    raise SandboxError(f"未知工具: {name}")
