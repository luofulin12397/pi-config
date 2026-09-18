#!/usr/bin/env python3
"""从 uv.lock 生成「部署瘦依赖清单」（deploy/requirements.deploy.txt）。

为什么需要它：
    项目 pyproject 声明了 torch / flagembedding / magic-pdf / unstructured /
    transformers / datasets / modelscope 等重依赖，但 app/ 对它们的导入数均为 0
    （向量化与重排已 API 化，MinerU 走 HTTP）。
    直接 `uv sync` 会把这些包及其传递依赖（含数 GB 的 nvidia-cu12 系列 CUDA 包）
    全部装进镜像。uv 的 `--no-install-package` 只剔除指定包、**不剔除其传递依赖**，
    所以按名字逐个排除不可靠；本脚本改为做依赖图可达性分析：
        从「保留的根依赖」出发做闭包，锁文件里不可达的包一律删除。

用法：
    uv run python scripts/gen_deploy_requirements.py          # 生成
    uv run python scripts/gen_deploy_requirements.py --check  # 只校验是否最新（CI 用）
"""
from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCK = ROOT / "uv.lock"
OUT = ROOT / "deploy" / "requirements.deploy.txt"

# 明确剔除的重依赖：均为 app/ 零导入
DROP_ROOTS = {
    "torch",
    "torchaudio",
    "torchvision",
    "flagembedding",
    "magic-pdf",
    "unstructured",
    "datasets",
    "transformers",
    "modelscope",
    "pymilvus-model",  # 仅被 pymilvus[model] extra 需要，同样零导入
}
# 保留但需要去掉 extras 的包：extras 会拖入 onnxruntime 等无用重依赖
STRIP_EXTRAS = {"pymilvus"}


def load_lock() -> dict[str, dict]:
    with LOCK.open("rb") as fh:
        data = tomllib.load(fh)
    return {pkg["name"]: pkg for pkg in data.get("package", [])}


def resolve_project(pkgs: dict[str, dict]) -> dict:
    for pkg in pkgs.values():
        if pkg.get("source", {}).get("virtual") == ".":
            return pkg
    raise SystemExit("uv.lock 中未找到项目自身条目（source.virtual = '.'）")


def collect(pkgs: dict[str, dict], roots: list[dict]) -> tuple[set[str], list[str]]:
    """从根依赖做闭包；返回（可达包名集合，缺失包名列表）"""
    reachable: set[str] = set()
    missing: list[str] = []
    stack = [dict(dep) for dep in roots]

    def push(entry: dict) -> None:
        stack.append(dict(entry))

    while stack:
        dep = stack.pop()
        name = dep["name"]
        if dep["name"] in STRIP_EXTRAS:
            dep.pop("extra", None)
        if name in reachable:
            continue
        reachable.add(name)
        pkg = pkgs.get(name)
        if pkg is None:
            missing.append(name)
            continue
        for child in pkg.get("dependencies", []):
            push(child)
        for extra in dep.get("extra", []) or []:
            for child in (pkg.get("optional-dependencies", {}) or {}).get(extra, []):
                push(child)
    return reachable, missing


def render(pkgs: dict[str, dict], keep: set[str]) -> str:
    """用 `uv export` 拿带平台标记的锁定版本，再按可达性分析做减法。

    为何不自己拼 `name==version`：uv.lock 可能是在 Windows 上生成的，
    含 pywin32 等平台专属包——必须保留 PEP 508 环境标记，
    否则在 Linux 上安装会直接报 “no wheels with a matching platform tag”。
    """
    import subprocess

    exported = subprocess.run(
        [
            "uv", "export", "--frozen", "--no-dev", "--no-emit-project",
            "--format", "requirements-txt", "--no-hashes",
        ],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout

    def norm(name: str) -> str:
        return name.strip().lower().replace("_", "-")

    kept_norm = {norm(n) for n in keep}
    lines: list[str] = []
    dropped_lines = 0
    for raw in exported.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        name = line.split("==")[0].split("[")[0].strip()
        if norm(name) not in kept_norm:
            dropped_lines += 1
            continue
        lines.append(line)

    header = [
        "# ⚠️ 自动生成，请勿手改 —— 由 scripts/gen_deploy_requirements.py 生成",
        "# 来源：uv export（锁定版本 + PEP 508 平台标记）再做重依赖减法",
        "# 用途：Dockerfile 的 SLIM 构建路径（uv pip install -r 本文件）",
        "# 剔除：torch/CUDA、flagembedding、magic-pdf、unstructured、transformers、",
        "#       datasets、modelscope、pymilvus-model（app/ 对它们的导入数均为 0）",
        f"# 包数：{len(lines)}（锁文件共 {len(pkgs)} 个包，本次跳过 {dropped_lines} 行）",
        "",
    ]
    return "\n".join(header + sorted(lines)) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="只校验清单是否最新")
    args = parser.parse_args()

    pkgs = load_lock()
    project = resolve_project(pkgs)

    # 根依赖 = 项目直接依赖 - 明确剔除项
    roots = [d for d in project.get("dependencies", []) if d["name"] not in DROP_ROOTS]
    dropped_roots = sorted(d["name"] for d in project.get("dependencies", []) if d["name"] in DROP_ROOTS)

    keep, missing = collect(pkgs, roots)
    dropped_transitive = sorted(set(pkgs) - keep - {"ai-0119-rag"})
    content = render(pkgs, keep)

    if args.check:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != content:
            print("[check] ✗ deploy/requirements.deploy.txt 已过期，请重新生成", file=sys.stderr)
            return 1
        print("[check] ✓ 部署依赖清单是最新的")
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(content, encoding="utf-8")
    print(f"[生成] {OUT.relative_to(ROOT)}")
    print(f"       保留 {len(keep)} 个包；剔除直接重依赖 {len(dropped_roots)} 个：{', '.join(dropped_roots)}")
    print(f"       连带剔除不可达的传递依赖 {len(dropped_transitive)} 个")
    if missing:
        print(f"       ! 锁中缺失（请检查）：{', '.join(sorted(missing))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
