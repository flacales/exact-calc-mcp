# -*- coding: utf-8 -*-
"""test_mcp_protocol.py —— MCP 协议层的冒烟测试

前面的 ``test_engine.py`` 测的是计算本身。这个文件测的是**协议那一段**：
真的起一个子进程、走一遍 stdio 上的 JSON-RPC 握手，确认

  1. ``initialize`` 能返回，且 ``serverInfo.version`` 是**本项目的版本**
     （不是 mcp SDK 的版本 —— 这个坑踩过一次）
  2. ``tools/list`` 列出预期的 5 个工具
  3. ``tools/call`` 能真的算出 ``0.1 + 0.2 = 3/10``
  4. 注入表达式被拒绝，而不是被执行

不依赖 mcp 客户端 SDK，直接手写 JSON-RPC —— 少一层依赖，坏起来也好定位。
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
import unittest

from exact_calc_mcp import __version__

# MCP stdio 传输：一行一个 JSON-RPC 对象
启动超时 = 20.0


class MCP协议测试(unittest.TestCase):
    """整个类共用一个服务器子进程——启动一次就够了，没必要每个用例起一个。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.proc = subprocess.Popen(
            [sys.executable, "-m", "exact_calc_mcp", "--serve"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        cls._响应: dict[int, dict] = {}
        cls._读线程 = threading.Thread(target=cls._读循环, daemon=True)
        cls._读线程.start()

        # 握手
        cls._发送({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "unittest", "version": "1.0"},
            },
        })
        cls.握手结果 = cls._等待(1)
        cls._发送({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

    @classmethod
    def tearDownClass(cls) -> None:
        try:
            cls.proc.kill()
        except Exception:
            pass

    # ── 读写管道 ──────────────────────────────────────────────

    @classmethod
    def _读循环(cls) -> None:
        assert cls.proc.stdout is not None
        for 行 in cls.proc.stdout:
            行 = 行.strip()
            if not 行:
                continue
            try:
                消息 = json.loads(行)
            except json.JSONDecodeError:
                continue  # 服务器偶尔会往 stdout 写非 JSON 的东西，跳过
            if "id" in 消息:
                cls._响应[消息["id"]] = 消息

    @classmethod
    def _发送(cls, 对象: dict) -> None:
        assert cls.proc.stdin is not None
        cls.proc.stdin.write(json.dumps(对象) + "\n")
        cls.proc.stdin.flush()

    @classmethod
    def _等待(cls, 编号: int, 超时: float = 启动超时):
        起点 = time.time()
        while time.time() - 起点 < 超时:
            if 编号 in cls._响应:
                return cls._响应[编号]
            time.sleep(0.02)
        return None

    def _调用(self, 编号: int, 方法: str, 参数: dict):
        self._发送({"jsonrpc": "2.0", "id": 编号, "method": 方法, "params": 参数})
        回应 = self._等待(编号)
        self.assertIsNotNone(回应, f"{方法} 在 {启动超时}s 内没有响应")
        return 回应

    # ── 用例 ──────────────────────────────────────────────────

    def test_01_服务器能启动并完成握手(self):
        self.assertIsNotNone(self.握手结果, "initialize 没有响应")
        结果 = self.握手结果.get("result", {})
        self.assertIn("serverInfo", 结果)
        self.assertIn("capabilities", 结果)

    def test_02_serverInfo_version_是项目版本而不是SDK版本(self):
        """曾经的 bug：FastMCP 不传 version，导致回落到 mcp SDK 的版本号。"""
        信息 = self.握手结果["result"]["serverInfo"]
        self.assertEqual(信息["name"], "exact-calc")
        self.assertEqual(
            信息["version"], __version__,
            f"serverInfo.version 应为项目版本 {__version__}，实际是 {信息['version']}"
            "（若为形如 1.x 的数字，说明又回落到 mcp SDK 版本了）",
        )

    def test_03_tools_list_列出5个工具(self):
        回应 = self._调用(2, "tools/list", {})
        工具 = 回应["result"]["tools"]
        名字 = sorted(t["name"] for t in 工具)
        self.assertEqual(
            名字,
            ["are_equal", "calculate", "engine_status", "to_fraction", "verify"],
        )
        # 每个工具都要有描述——描述是给模型读的 prompt，缺了模型就不会用
        for t in 工具:
            self.assertTrue(t.get("description", "").strip(), f"{t['name']} 没有描述")

    def test_04_calculate_真的算得对(self):
        回应 = self._调用(3, "tools/call", {
            "name": "calculate", "arguments": {"expression": "0.1 + 0.2"},
        })
        内容 = json.loads(回应["result"]["content"][0]["text"])
        self.assertEqual(内容["value"], "3/10")
        self.assertTrue(内容["exact"])
        self.assertEqual(内容["domain"], "fraction")

    def test_05_注入表达式被拒绝而不是被执行(self):
        恶意 = "__import__('os').system('echo pwned')"
        回应 = self._调用(4, "tools/call", {
            "name": "calculate", "arguments": {"expression": 恶意},
        })
        文本 = json.dumps(回应, ensure_ascii=False)
        self.assertIn("error", 文本.lower())
        for 不该出现 in ("uid=", "pwned\n", "Traceback"):
            self.assertNotIn(不该出现, 文本, f"响应里出现了 {不该出现!r}，注入可能成功了")

    def test_06_比较工具返回布尔(self):
        回应 = self._调用(5, "tools/call", {
            "name": "are_equal",
            "arguments": {"left": "0.1 + 0.2", "right": "0.3"},
        })
        文本 = 回应["result"]["content"][0]["text"]
        内容 = json.loads(文本)
        self.assertIn("equal", 内容)
        self.assertTrue(内容["equal"])


if __name__ == "__main__":
    unittest.main()
