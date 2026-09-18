import ast, sys, json
from pathlib import Path
from collections import defaultdict, deque

ROOT = Path("/Users/abab/Documents/ChatGPT/autoresearch/AutoResearch")
SRC = ROOT / "src"
PKG = SRC / "autoresearch"

files = sorted(PKG.rglob("*.py"))
def modname(p):
    parts = list(p.relative_to(SRC).with_suffix("").parts)
    if parts[-1] == "__init__": parts = parts[:-1]
    return ".".join(parts)

def imports_of(p):
    """return set of autoresearch.* modules imported by p (static, incl. function-local)"""
    out = set()
    t = p.read_text(encoding="utf-8", errors="replace")
    try: tree = ast.parse(t)
    except Exception: return out
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.startswith("autoresearch"): out.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                base = modname(p).split(".")
                base = base[: len(base) - node.level]
                if node.module: base += node.module.split(".")
                out.add(".".join(base))
            elif node.module and node.module.startswith("autoresearch"):
                out.add(node.module)
                for a in node.names: out.add(f"{node.module}.{a.name}")
    return out

def resolve(m, known):
    """map a dotted name to the deepest known module"""
    if m in known: return m
    parts = m.split(".")
    while parts:
        cand = ".".join(parts)
        if cand in known: return cand
        parts.pop()
    return None

known = {modname(p) for p in files}
graph = {m: set() for m in known}
for p in files:
    m = modname(p)
    for imp in imports_of(p):
        r = resolve(imp, known)
        if r and r != m: graph[m].add(r)

# entry points: real production entries
ENTRIES = ["autoresearch.cli", "autoresearch.__main__", "autoresearch.api", "autoresearch.application", "autoresearch.graph"]
# also dev/tool entries outside the package
TOOL_ENTRIES = []
for d in [ROOT/"web"/"dev", ROOT/"scripts"]:
    if d.exists():
        for p in sorted(d.rglob("*.py")):
            for imp in imports_of(p):
                r = resolve(imp, known)
                if r: TOOL_ENTRIES.append(r)
TOOL_ENTRIES = sorted(set(TOOL_ENTRIES))

def bfs(entries):
    seen = set(); q = deque(e for e in entries if e in known)
    while q:
        m = q.popleft()
        if m in seen: continue
        seen.add(m)
        for n in graph.get(m, ()): 
            if n not in seen: q.append(n)
    return seen

prod = bfs(ENTRIES)
withtools = bfs(ENTRIES + TOOL_ENTRIES)
unreachable_prod = sorted(known - prod)
unreachable_all  = sorted(known - withtools)

print("="*100)
print("从生产入口 BFS（cli/__main__/api/application/graph）")
print("入口集合 =", [e for e in ENTRIES if e in known])
print("可达模块数 =", len(prod), "/", len(known))
print("="*100)
print("\n### A. 生产入口不可达（= 孤岛），但被 web/dev 或 scripts 工具引用（工具可达）：")
only_tools = sorted(set(unreachable_prod) - set(unreachable_all))
for m in only_tools:
    p = [f for f in files if modname(f)==m][0]
    print(f"  · {m:<48} {len(p.read_text().splitlines()):>5} 行")
print(f"  小计 {len(only_tools)} 个")

print("\n### B. 生产入口和工具入口都不可达（= 完全孤岛，只有测试/文档引用）：")
for m in unreachable_all:
    p = [f for f in files if modname(f)==m][0]
    print(f"  · {m:<48} {len(p.read_text().splitlines()):>5} 行")
print(f"  小计 {len(unreachable_all)} 个")

print("\n### C. 上游可达但下游无人（可达但出度为 0 的叶子，供参考）：")
leaves = sorted([m for m in prod if not graph.get(m)])
print("  ", ", ".join(leaves) if leaves else "(none)")

json.dump({"prod_reachable": sorted(prod), "island_tools_only": only_tools, "island_fully": unreachable_all,
           "entries": ENTRIES, "tool_entries": TOOL_ENTRIES, "graph": {k: sorted(v) for k,v in graph.items()}},
          open("/tmp/island-scan/reach.json","w"), ensure_ascii=False, indent=1)
