#!/usr/bin/env python3
"""開發模式啟動腳本"""

import sys
from pathlib import Path

# 將 src 加入 Python path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

if __name__ == "__main__":
    import uvicorn
    from line_gateway.config import get_settings

    settings = get_settings()

    print("=" * 50)
    print("LINE Webhook Gateway - 開發模式")
    print("=" * 50)
    print(f"伺服器: http://{settings.host}:{settings.port}")
    print(f"Webhook URL: http://{settings.host}:{settings.port}/webhook")
    print("=" * 50)

    uvicorn.run(
        "line_gateway.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,  # 開發模式啟用熱重載
    )
