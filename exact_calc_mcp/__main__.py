# -*- coding: utf-8 -*-
"""`python -m exact_calc_mcp` 的入口。

    python -m exact_calc_mcp "0.1 + 0.2"
    python -m exact_calc_mcp --compare "0.1+0.2" "0.3"
    python -m exact_calc_mcp --doctor
    python -m exact_calc_mcp --serve      # 以 MCP 服务器方式启动
"""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
