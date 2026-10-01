# -*- coding: utf-8 -*-
"""cli.py —— 命令行入口

为什么除了 MCP 还要有 CLI：
  MCP 需要客户端支持才能用。CLI 不需要 —— 任何能执行 shell 命令的 agent
  （包括只有 Bash 工具的）都能调 `exact-calc "0.1+0.2"` 拿到答案。
  两条路都留着，覆盖面才够。

给 agent 用的约定：
  --json 输出结构化结果，退出码 0 成功 / 1 失败，方便程序化解析。
"""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__, engine_cpp, engine_py


def _打印结果(结果: engine_py.计算结果, 用JSON: bool) -> None:
    if 用JSON:
        print(json.dumps(结果.as_dict(), ensure_ascii=False, indent=2))
        return

    print(f"{结果.表达式} = {结果.值}")
    print(f"  数值域    : {结果.数值域}"
          f"{'（无损）' if 结果.精确 else ''}")
    print(f"  Python 自检: {结果.交叉验证}")
    print(f"  C++ 独立复核: {结果.cpp验证}")
    if 结果.备注:
        print(f"  备注      : {结果.备注}")
    if not 结果.可信:
        print("  [警告] 有验证未通过，请不要直接采信这个结果")


def _命令计算(参数) -> int:
    try:
        结果 = engine_py.计算(参数.expression, 精度=参数.precision)
    except engine_py.计算错误 as e:
        print(f"错误：{e}", file=sys.stderr)
        return 1
    _打印结果(结果, 参数.json)
    return 0 if 结果.可信 else 1


def _命令比较(参数) -> int:
    try:
        相等, 说明 = engine_py.精确比较(参数.甲, 参数.乙, 精度=参数.precision)
    except engine_py.计算错误 as e:
        print(f"错误：{e}", file=sys.stderr)
        return 1
    if 参数.json:
        print(json.dumps({"equal": 相等, "detail": 说明}, ensure_ascii=False, indent=2))
    else:
        print(f"{'相等' if 相等 else '不相等'}：{说明}")
    return 0 if 相等 else 1


def _命令转分数(参数) -> int:
    try:
        结果 = engine_py.转分数(参数.value)
    except engine_py.计算错误 as e:
        print(f"错误：{e}", file=sys.stderr)
        return 1
    print(json.dumps({"value": 结果}, ensure_ascii=False) if 参数.json else 结果)
    return 0


def _命令体检(参数) -> int:
    报告 = engine_cpp.环境报告()
    if 参数.json:
        print(json.dumps(报告, ensure_ascii=False, indent=2))
        return 0
    print(f"exact-calc-mcp {__version__}")
    print(f"  Python 引擎 : 就绪（Fraction + Decimal，默认 {engine_py.默认精度} 位精度）")
    print(f"  C++ 引擎    : {'就绪' if 报告['可用'] else '未启用'}")
    print(f"  编译器      : {报告['编译器']}")
    if 报告["二进制"]:
        print(f"  二进制      : {报告['二进制']}")
    if not 报告["可用"]:
        print(f"  说明        : {报告['说明']}")
    return 0


def 造解析器() -> argparse.ArgumentParser:
    解析器 = argparse.ArgumentParser(
        prog="exact-calc",
        description="让 AI 用代码精确计算，而不是靠猜。",
        epilog='例：exact-calc "0.1 + 0.2"    exact-calc --compare "0.1+0.2" "0.3"',
    )
    解析器.add_argument("expression", nargs="?", help="要计算的表达式")
    解析器.add_argument("--precision", type=int, default=engine_py.默认精度,
                        help=f"工作精度，默认 {engine_py.默认精度} 位")
    解析器.add_argument("--json", action="store_true", help="输出 JSON（给程序用）")
    解析器.add_argument("--compare", nargs=2, metavar=("甲", "乙"),
                        help="判断两个表达式是否数学相等")
    解析器.add_argument("--fraction", metavar="小数",
                        help="把十进制小数还原成精确分数")
    解析器.add_argument("--doctor", action="store_true", help="检查两个引擎的状态")
    解析器.add_argument("--serve", action="store_true", help="以 MCP 服务器方式启动")
    解析器.add_argument("--version", action="version", version=f"exact-calc-mcp {__version__}")
    return 解析器


def main(argv=None) -> int:
    参数 = 造解析器().parse_args(argv)

    if 参数.serve:
        from .server import main as 起服务
        return 起服务()

    if 参数.doctor:
        return _命令体检(参数)
    if 参数.compare:
        参数.甲, 参数.乙 = 参数.compare
        return _命令比较(参数)
    if 参数.fraction is not None:
        参数.value = 参数.fraction
        return _命令转分数(参数)
    if 参数.expression:
        return _命令计算(参数)

    造解析器().print_help()
    return 1
