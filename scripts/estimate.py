#!/usr/bin/env python3
"""pick-model 期望成本估算器。

读 references/models.yaml，为每个模型算出"做这个任务一次"的期望成本
（含重试风险与返工成本），并按档位排序。

无第三方依赖。价格换算：USD / 1M tokens。

用法：
    python3 scripts/estimate.py --in 20000 --out 3000
    python3 scripts/estimate.py --in 20000 --out 3000 --tier T2
    python3 scripts/estimate.py --in 200000 --out 8000 --rework 2.5
    python3 scripts/estimate.py --check
    python3 scripts/estimate.py --in 20000 --out 3000 --json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import unicodedata
from datetime import date, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG = os.path.join(HERE, "..", "references", "models.yaml")
REQUIRED = ("id", "tier", "price_in", "price_out")
STALE_DAYS = 90


class ConfigError(Exception):
    pass


def _strip_comment(line: str) -> str:
    out, prev = [], " "
    for ch in line:
        if ch == "#" and prev in " \t":
            break
        out.append(ch)
        prev = ch
    return "".join(out).rstrip()


def _parse_value(raw: str):
    v = raw.strip()
    if not v:
        return ""
    if v.startswith("[") and v.endswith("]"):
        return [p.strip().strip("\"'") for p in v[1:-1].split(",") if p.strip()]
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        pass
    return v.strip("\"'")


def load_config(path: str) -> dict:
    """解析 models.yaml 的受限子集：顶层标量 + models 列表（每项为扁平键值）。

    刻意只支持这个子集，并在遇到无法识别的结构时明确报错——
    宁可失败，也不要静默算出一个错的成本。
    """
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except FileNotFoundError:
        raise ConfigError(
            f"找不到价目表：{path}\n"
            "这个 skill 不接受记忆里的价格。请先确认 references/models.yaml 存在。"
        )

    cfg: dict = {}
    section = None
    cur = None

    for lineno, raw in enumerate(text.splitlines(), 1):
        line = _strip_comment(raw)
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()

        if indent == 0 and not stripped.startswith("- "):
            key, _, val = stripped.partition(":")
            key, val = key.strip(), val.strip()
            if not val:
                section, cur = key, None
                if key == "models":
                    cfg.setdefault("models", [])
                continue
            if section == "models":
                raise ConfigError(
                    f"第 {lineno} 行：models 列表已开始，却又出现顶层键 `{key}`。"
                )
            cfg[key] = _parse_value(val)
            section, cur = None, None
            continue

        if indent >= 2:
            if stripped.startswith("- "):
                if section != "models":
                    raise ConfigError(f"第 {lineno} 行：列表项出现在非 models 段落中。")
                cur = {}
                cfg.setdefault("models", []).append(cur)
                key, _, val = stripped[2:].partition(":")
                cur[key.strip()] = _parse_value(val)
            elif cur is not None:
                key, _, val = stripped.partition(":")
                cur[key.strip()] = _parse_value(val)
            else:
                raise ConfigError(f"第 {lineno} 行：缩进行不属于任何模型条目。")

    models = cfg.get("models") or []
    if not models:
        raise ConfigError(f"{path} 里没有解析到任何模型。检查 models: 段落格式。")

    for i, m in enumerate(models):
        missing = [k for k in REQUIRED if k not in m]
        if missing:
            raise ConfigError(f"第 {i + 1} 个模型缺少字段：{', '.join(missing)}")
        m.setdefault("fail_rate", 0.05)
        m.setdefault("name", m["id"])
        for k in ("price_in", "price_out", "fail_rate"):
            if not isinstance(m[k], (int, float)):
                raise ConfigError(f"模型 {m['id']} 的 {k} 必须是数字，当前为 {m[k]!r}")
        if not 0 <= m["fail_rate"] < 1:
            raise ConfigError(f"模型 {m['id']} 的 fail_rate 必须在 [0, 1) 内。")
    return cfg


def config_age_days(cfg: dict) -> int | None:
    raw = cfg.get("updated")
    if raw is None:
        return None
    try:
        if isinstance(raw, int):
            d = datetime.strptime(str(raw), "%Y%m%d").date()
        else:
            d = date.fromisoformat(str(raw))
    except ValueError:
        return None
    return (date.today() - d).days


def estimate(cfg: dict, tokens_in: int, tokens_out: int, rework: float) -> list[dict]:
    rows = []
    for m in cfg["models"]:
        unit = (tokens_in * m["price_in"] + tokens_out * m["price_out"]) / 1_000_000
        fr = m["fail_rate"]
        expected = unit / (1 - fr) + fr * rework
        rows.append(
            {
                "id": m["id"],
                "name": m.get("name", m["id"]),
                "vendor": m.get("vendor", ""),
                "tier": m["tier"],
                "unit_cost": round(unit, 6),
                "expected_cost": round(expected, 6),
                "fail_rate": fr,
                "note": m.get("note", ""),
            }
        )

    for tier in {r["tier"] for r in rows}:
        peers = [r for r in rows if r["tier"] == tier]
        floor = min(p["expected_cost"] for p in peers)
        for r in peers:
            r["vs_tier_floor"] = round(r["expected_cost"] / floor, 2) if floor else None
    rows.sort(key=lambda r: (r["tier"], r["expected_cost"]))
    return rows


def _width(text: str) -> int:
    """终端显示宽度：CJK 全角字符占 2 列。"""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


def _pad(text: str, width: int, right: bool = False) -> str:
    gap = " " * max(0, width - _width(text))
    return gap + text if right else text + gap


def render(rows, tokens_in, tokens_out, rework, cfg, age, tier_filter) -> str:
    lines = []
    updated = cfg.get("updated", "未知")
    meta = f"配置：{len(cfg['models'])} 个模型 · 价目更新于 {updated}"
    if age is not None:
        meta += f"（{age} 天前）"
    lines.append(meta)
    if age is not None and age > STALE_DAYS:
        lines.append(
            f"⚠ 价目表已 {age} 天未更新，超过 {STALE_DAYS} 天阈值——"
            "结论可能失真，先核对再采用。"
        )
    lines.append(
        f"估算：输入 {tokens_in:,} / 输出 {tokens_out:,} tokens · "
        f"返工成本 ${rework:.2f}/次"
    )
    lines.append("")
    head = (
        _pad("档位", 6)
        + _pad("模型", 24)
        + _pad("单次成本", 12, right=True)
        + _pad("期望成本", 13, right=True)
        + _pad("本档倍数", 11, right=True)
    )
    lines.append(head)
    lines.append("-" * _width(head))
    for r in rows:
        if tier_filter and r["tier"] != tier_filter:
            continue
        ratio = f"{r['vs_tier_floor']:.1f}x" if r["vs_tier_floor"] else "-"
        lines.append(
            _pad(r["tier"], 6)
            + _pad(r["id"], 24)
            + _pad(f"${r['unit_cost']:.4f}", 12, right=True)
            + _pad(f"${r['expected_cost']:.4f}", 13, right=True)
            + _pad(ratio, 11, right=True)
        )
    lines.append("")

    visible = [r for r in rows if not tier_filter or r["tier"] == tier_filter]
    if visible:
        best = min(visible, key=lambda r: r["expected_cost"])
        lines.append(
            f"最便宜：{best['id']}（{best['tier']}）≈ "
            f"${best['expected_cost']:.4f}/次 · 失败率假设 {best['fail_rate']:.0%}"
        )
        if best["note"]:
            lines.append(f"  注：{best['note']}")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="pick-model 期望成本估算器")
    ap.add_argument("--in", dest="tokens_in", type=int, default=None, help="单次输入 tokens")
    ap.add_argument("--out", dest="tokens_out", type=int, default=None, help="单次输出 tokens")
    ap.add_argument("--rework", type=float, default=0.0, help="每次失败的人工返工成本（USD）")
    ap.add_argument("--tier", choices=["T1", "T2", "T3"], help="只看某一档")
    ap.add_argument("--config", default=DEFAULT_CONFIG, help="价目表路径")
    ap.add_argument("--check", action="store_true", help="只校验价目表并打印元信息")
    ap.add_argument("--json", action="store_true", help="输出 JSON，供上层程序消费")
    args = ap.parse_args(argv)

    try:
        cfg = load_config(args.config)
    except ConfigError as exc:
        print(f"配置错误：{exc}", file=sys.stderr)
        return 2

    age = config_age_days(cfg)

    if args.check:
        if args.json:
            print(json.dumps({"models": len(cfg["models"]), "updated": cfg.get("updated"), "age_days": age}, ensure_ascii=False))
            return 0
        print(f"✓ 价目表可解析：{args.config}")
        print(f"  模型数：{len(cfg['models'])}")
        print(f"  更新时间：{cfg.get('updated', '未标注')}（{age} 天前）" if age is not None else "  更新时间：未标注")
        by_tier = {}
        for m in cfg["models"]:
            by_tier.setdefault(m["tier"], []).append(m["id"])
        for tier in sorted(by_tier):
            print(f"  {tier}: {', '.join(by_tier[tier])}")
        if age is not None and age > STALE_DAYS:
            print(f"⚠ 已超过 {STALE_DAYS} 天，建议核对价格。")
        return 0

    if args.tokens_in is None or args.tokens_out is None:
        ap.error("需要同时提供 --in 和 --out（或用 --check 只校验配置）")

    rows = estimate(cfg, args.tokens_in, args.tokens_out, args.rework)

    if args.json:
        print(
            json.dumps(
                {
                    "tokens_in": args.tokens_in,
                    "tokens_out": args.tokens_out,
                    "rework_cost": args.rework,
                    "updated": cfg.get("updated"),
                    "age_days": age,
                    "stale": bool(age is not None and age > STALE_DAYS),
                    "models": rows,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    print(render(rows, args.tokens_in, args.tokens_out, args.rework, cfg, age, args.tier))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
