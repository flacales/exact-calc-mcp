# -*- coding: utf-8 -*-
"""server.py —— MCP 服务器

把精确计算能力暴露成 MCP 工具，任何支持 MCP 的客户端都能直接接入：
Claude Desktop、Cursor、Cline、Continue、WorkBuddy，以及自己写的 agent。

为什么工具描述（docstring）用英文、其余注释用中文：
  docstring 是给**模型**读的，它相当于一段 prompt —— 英文的兼容性和
  触发率都更稳；注释是给人读的，用中文更省事。这两者受众不同，不该统一。
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from . import __version__, engine_cpp, engine_py

mcp = FastMCP(
    "exact-calc",
    instructions=(
        "Exact arithmetic for AI agents. Language models do not actually compute; "
        "they emit tokens that look like answers. Whenever an answer depends on a "
        "calculation, call these tools instead of doing the arithmetic yourself. "
        "Every result is cross-checked by two independently written engines "
        "(exact Python rational/decimal arithmetic, and a separate C++ evaluator) "
        "before it is returned."
    ),
)


@mcp.tool()
def calculate(expression: str, precision: int = 50) -> dict:
    """Evaluate an arithmetic expression exactly, with cross-validation.

    Use this instead of computing in your head. Never state a numeric result
    that did not come from a tool call.

    Supports: + - * / // % ** and parentheses; functions sqrt, abs, round
    (rounds half away from zero, NOT Python's banker's rounding), min, max,
    factorial, gcd, lcm, ln, log (natural log; log(x, base) for a custom
    base), log10, exp, pow; constants pi, e.

    Precision: values are computed as exact rationals when possible, so
    "0.1 + 0.2" returns exactly 3/10 -- not the 0.30000000000000004 that
    binary floating point produces.

    Args:
        expression: The expression to evaluate, e.g. "0.1 + 0.2",
            "(1/3) + 1/6", "2 ** 100", "sqrt(2)", "factorial(20)".
        precision: Decimal digits of working precision for irrational results.
            Default 50. Raise it for high-precision work.

    Returns:
        A dict with:
          value        -- the result, as a string ("3/10", "1267650600228229401496703205376")
          domain       -- "fraction" (exact rational) or "decimal" (exact decimal)
          exact        -- whether the result is lossless
          cross_check  -- result of the Fraction-vs-Decimal self-check
          cpp_check    -- result of the independent C++ implementation check
          note         -- extra explanation, if any
    """
    try:
        结果 = engine_py.计算(expression, 精度=precision)
    except engine_py.计算错误 as e:
        return {"error": str(e), "expression": expression}
    return 结果.as_dict()


@mcp.tool()
def verify(expression: str, precision: int = 50) -> dict:
    """Compute an expression and report how confident the result is.

    Same computation as `calculate`, but returns a plain-language verdict
    first. Call this when a wrong number would be costly and you want to
    know whether the answer was independently confirmed.

    Args:
        expression: The expression to evaluate.
        precision: Decimal digits of working precision. Default 50.

    Returns:
        A dict with `trusted` (bool), `verdict` (one-line summary),
        and the full result detail.
    """
    try:
        结果 = engine_py.计算(expression, 精度=precision)
    except engine_py.计算错误 as e:
        return {"trusted": False, "verdict": f"expression rejected: {e}"}

    通过 = 结果.可信
    if 通过:
        判定 = f"{结果.表达式} = {结果.值}（两路独立验证一致）"
    else:
        判定 = f"{结果.表达式} = {结果.值}，但验证未全部通过，请人工复核"
    明细 = 结果.as_dict()
    明细["trusted"] = 通过
    明细["verdict"] = 判定
    return 明细


@mcp.tool()
def are_equal(left: str, right: str, precision: int = 50) -> dict:
    """Test whether two expressions are mathematically equal.

    Unlike `left == right` in floating point, this compares exact values.
    For example "0.1 + 0.2" and "0.3" ARE equal here, even though
    `0.1 + 0.2 == 0.3` evaluates to False in binary floating point.

    Args:
        left: First expression, e.g. "0.1 + 0.2".
        right: Second expression, e.g. "0.3".
        precision: Decimal digits of working precision. Default 50.

    Returns:
        A dict with `equal` (bool) and `detail` (how the comparison was made).
    """
    try:
        相等, 说明 = engine_py.精确比较(left, right, 精度=precision)
    except engine_py.计算错误 as e:
        return {"error": str(e)}
    return {"equal": 相等, "detail": 说明, "left": left, "right": right}


@mcp.tool()
def to_fraction(decimal_string: str) -> dict:
    """Convert a decimal string to its exact fraction.

    Useful for showing why a decimal cannot be represented in binary floating
    point. For example "0.375" is exactly 3/8, but "0.1" is
    1/10 as a decimal while its nearest binary float is
    3602879701896397/36028797018963968.

    Args:
        decimal_string: A decimal number as text, e.g. "0.375" or "-2.5".

    Returns:
        A dict with `fraction` as a string.
    """
    try:
        return {"fraction": engine_py.转分数(decimal_string)}
    except engine_py.计算错误 as e:
        return {"error": str(e)}


@mcp.tool()
def engine_status() -> dict:
    """Report which calculation engines are available.

    The Python engine (exact rational and decimal arithmetic) is always
    available. The C++ engine is an optional second opinion; it is built
    on first use and skipped silently if no C++ compiler is installed.

    Returns:
        A dict describing the compiler, the built binary, and any reason
        the C++ engine is unavailable.
    """
    报告 = engine_cpp.环境报告()
    报告["version"] = __version__
    报告["python_engine"] = "ready"
    return 报告


def main() -> int:
    mcp.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
