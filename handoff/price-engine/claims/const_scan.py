"""Every number literal and every UPPER_CASE name in the price-engine package, with its line."""
import ast
from pathlib import Path

D = Path("/Users/maxzipperman/code/value-finder/.claude/worktrees/wf_4496c14b-845-1/sharp-markets/src/markets/research/"
         "price_engine")
for p in sorted(D.glob("*.py")):
    src = p.read_text().splitlines()
    tree = ast.parse(p.read_text())
    seen = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool):
            if (n.lineno, n.value) in seen:
                continue
            seen.add((n.lineno, n.value))
            line = src[n.lineno - 1].strip()
            if line.startswith(("#", '"', "'")) or '"""' in line:
                continue
            print(f"{p.name}:{n.lineno}\t{n.value!r}\t{line[:150]}")
