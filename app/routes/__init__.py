from typing import Annotated

from fastapi import Path

# 主键从 1 开始；范围外的 id 会触发校验错误，由 main.py 转成 404，也避免 SQLite 整数溢出
DbId = Annotated[int, Path(ge=1, le=2**63 - 1)]
