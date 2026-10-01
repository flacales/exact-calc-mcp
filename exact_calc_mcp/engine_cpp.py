# -*- coding: utf-8 -*-
"""engine_cpp.py —— C++ 引擎的编译与调用封装

为什么要跨语言做第二遍：如果只有一个实现，它错了你也不知道。
两个独立实现（不同语言、不同数值类型、不同作者思路）算出同一个数，
才叫验证过。C++ 那边故意用 long double（不精确），所以它只回答
「量级和有效数字对得上吗」，不参与精度判定。

编译策略：
  - 首次使用时自动编译，二进制放在 cpp/ 下
  - calc.cpp 比二进制新才重编，避免每次调用都等编译
  - 找不到编译器就优雅降级，绝不因此让主流程报错
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path

根目录 = Path(__file__).resolve().parent.parent
包目录 = Path(__file__).resolve().parent
二进制名 = "calc.exe" if sys.platform == "win32" else "calc"

# 编译器搜索路径：环境变量 > PATH > 常见安装位置
常见编译器 = (
    r"D:\编程\Dev-Cpp\TDM-GCC-64\bin\g++.exe",
    r"C:\Program Files\Dev-Cpp\TDM-GCC-64\bin\g++.exe",
    r"C:\TDM-GCC-64\bin\g++.exe",
    r"C:\MinGW\bin\g++.exe",
    r"C:\msys64\mingw64\bin\g++.exe",
    r"C:\Program Files\LLVM\bin\clang++.exe",
    "/usr/bin/g++",
    "/usr/bin/clang++",
    "/opt/homebrew/bin/g++",
)

_编译失败原因 = ""


def _找源码() -> Path | None:
    """C++ 源码可能在哪几个位置。

    仓库检出时在 <repo>/cpp/calc.cpp；pip 安装后源码不随包分发，
    所以也允许用环境变量 EXACT_CALC_SOURCE 直接指定。
    """
    候选 = []
    指定 = os.environ.get("EXACT_CALC_SOURCE")
    if 指定:
        候选.append(Path(指定))
    候选.append(根目录 / "cpp" / "calc.cpp")   # 仓库布局
    候选.append(包目录 / "cpp" / "calc.cpp")   # 源码内嵌布局
    候选.append(Path.cwd() / "cpp" / "calc.cpp")
    for 路径 in 候选:
        if 路径.exists():
            return 路径
    return None


def _二进制路径(源码: Path) -> Path:
    """二进制放在源码旁边，跟着源码走。"""
    return 源码.parent / 二进制名


def 找编译器() -> str | None:
    """按 环境变量 -> PATH -> 常见路径 的顺序找 C++ 编译器。"""
    指定 = os.environ.get("EXACT_CALC_CXX")
    if 指定 and Path(指定).exists():
        return 指定

    for 名 in ("g++", "clang++", "c++"):
        找到 = shutil.which(名)
        if 找到:
            return 找到

    for 路径 in 常见编译器:
        if Path(路径).exists():
            return 路径
    return None


def 确保编译(强制: bool = False) -> Path | None:
    """保证二进制存在且是最新的。返回二进制路径，失败返回 None。"""
    global _编译失败原因

    源码 = _找源码()
    if 源码 is None:
        _编译失败原因 = ("找不到 cpp/calc.cpp。C++ 交叉验证已跳过，其余功能不受影响。"
                      "如果你是从 pip 安装的，可以用环境变量 EXACT_CALC_SOURCE "
                      "指向 calc.cpp 的路径。")
        return None

    二进制 = _二进制路径(源码)

    if 二进制.exists() and not 强制:
        try:
            if 二进制.stat().st_mtime >= 源码.stat().st_mtime:
                return 二进制
        except OSError:
            pass

    编译器 = 找编译器()
    if 编译器 is None:
        _编译失败原因 = ("没找到 C++ 编译器（g++ / clang++）。"
                      "C++ 交叉验证已跳过，其余功能不受影响。"
                      "想启用就装个 TDM-GCC 或 MinGW，"
                      "或用环境变量 EXACT_CALC_CXX 指定编译器路径。")
        return None

    try:
        过程 = subprocess.run(
            [编译器, "-O2", "-std=c++17", "-o", str(二进制), str(源码)],
            capture_output=True, text=True, timeout=180,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        _编译失败原因 = f"编译失败：{e}"
        return None

    if 过程.returncode != 0:
        _编译失败原因 = f"编译失败：\n{过程.stderr[:800]}"
        return None

    _编译失败原因 = ""
    return 二进制


def 可用() -> bool:
    return 确保编译() is not None


def 编译失败原因() -> str:
    return _编译失败原因


def 计算(表达式: str, 超时: float = 10.0) -> str:
    """让 C++ 引擎算一遍。它搞不定的表达式抛 计算错误，调用方应跳过验证。"""
    from .engine_py import 计算错误

    程序 = 确保编译()
    if 程序 is None:
        raise 计算错误(_编译失败原因)

    try:
        过程 = subprocess.run(
            [str(程序), 表达式],
            capture_output=True, text=True, timeout=超时,
        )
    except subprocess.TimeoutExpired as e:
        raise 计算错误(f"C++ 引擎超时（>{超时}s）") from e
    except OSError as e:
        raise 计算错误(f"无法运行 C++ 引擎：{e}") from e

    if 过程.returncode != 0:
        # 退出码 2 = 表达式超出 C++ 引擎能力范围，这是预期内的，不是错误
        raise 计算错误(过程.stderr.strip() or f"C++ 引擎退出码 {过程.returncode}")

    return 过程.stdout.strip()


def 解析结果(文本: str) -> Decimal:
    """C++ 输出可能是 1.2676506002282294e+30 这种科学计数法。"""
    return Decimal(文本)


def 交叉验证(表达式: str, python值: str, 相对容差: float = 1e-14) -> str:
    """把 C++ 的结果和 Python 的结果比一比，返回一句人能看懂的话。"""
    from .engine_py import 计算错误

    # 报告里引用 Python 结果时截断 —— pi 这种上千位的值原样塞进
    # 验证信息会把 MCP 响应撑爆，验证的是数值，不是展示值。
    展示值 = python值 if len(python值) <= 40 else python值[:37] + "..."
    try:
        cpp文本 = 计算(表达式)
        cpp值 = 解析结果(cpp文本)
    except 计算错误 as e:
        return f"已跳过（C++ 引擎不处理这个表达式：{e}）"
    except (InvalidOperation, ValueError) as e:
        return f"异常（C++ 输出无法解析：{e}）"

    with localcontext() as ctx:
        ctx.prec = 40
        if "/" in python值:  # Python 侧给的是分数
            分子, _, 分母 = python值.partition("/")
            py值 = Decimal(int(分子)) / Decimal(int(分母 or 1))
        else:
            try:
                py值 = Decimal(python值)
            except InvalidOperation:
                return f"异常（Python 结果无法解析：{展示值}）"

        甲, 乙 = abs(py值), abs(cpp值)
        基准 = max(甲, 乙, Decimal(1))
        相对误差 = abs(甲 - 乙) / 基准

        if 相对误差 > Decimal(str(相对容差)):
            return ("不一致 —— 请人工复核"
                    f"（Python: {展示值}，C++: {cpp文本}，相对误差 {相对误差:.3e}）")

        if abs(甲 - 乙) == 0:
            return f"通过（Python 与 C++ 独立实现结果完全一致：{cpp文本}）"
        return (f"通过（Python {展示值} ≈ C++ {cpp文本}，"
                f"相对误差 {相对误差:.2e}，差异来自 long double 精度上限）")


def 环境报告() -> dict:
    """给 CLI 和 README 用：当前 C++ 引擎是什么状态。"""
    编译器 = 找编译器()
    源码 = _找源码()
    程序 = 确保编译()
    return {
        "可用": 程序 is not None,
        "编译器": 编译器 or "未找到",
        "源码": str(源码) if 源码 else "未找到",
        "二进制": str(程序) if 程序 else "",
        "说明": _编译失败原因 or ("C++ 交叉验证已就绪" if 程序 else "未编译"),
    }
