#!/usr/bin/env python3
"""独立调试脚本。

脱离 Home Assistant 直接验证 api.py 的登录与状态接口，便于在集成里
出问题时快速定位是「设备/凭证问题」还是「HA 集成层问题」。

用法：
cd {project_path}
python scripts/test_kunpeng_api.py --host 192.168.66.1 --username root --password admin -v
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from importlib.util import module_from_spec, spec_from_file_location

# 加载api.py文件，以便在脚本里直接使用
filepath = Path(__file__).resolve().parent.parent / "custom_components" / "kunpeng_cpe" / "api.py"
if not filepath.is_file():
    raise SystemExit(f"找不到文件：{filepath}")

_spec = spec_from_file_location("kunpeng_cpe_api", filepath)
if _spec is None or _spec.loader is None:
    raise SystemExit(f"无法创建模块规范：{filepath}")

_api = module_from_spec(_spec)
sys.modules["kunpeng_cpe_api"] = _api
try:
    _spec.loader.exec_module(_api)
except Exception:
    sys.modules.pop("kunpeng_cpe_api", None)
    raise

KunpengCpeApi = _api.KunpengCpeApi
KunpengCpeApiError = _api.KunpengCpeApiError
create_cpe_session = _api.create_cpe_session


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="调试鲲鹏 5G CPE 的 LuCI API",
    )
    parser.add_argument(
        "--host",
        default='192.168.66.1',
        help="设备IP",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=80,
        help="设备HTTP端口",
    )
    parser.add_argument(
        "--username",
        default='root',
        help="登录用户名",
    )
    parser.add_argument(
        "--password",
        default='admin',
        help="登录密码",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="输出 DEBUG 日志（含 api.py 内部的调试信息）",
    )
    return parser.parse_args()


async def main(args: argparse.Namespace) -> int:
    """执行一次登录 + 一次状态拉取，返回进程退出码。"""
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    session = create_cpe_session()
    api = KunpengCpeApi(
        host=args.host,
        port=args.port,
        username=args.username,
        password=args.password,
        session=session,
    )

    try:
        print(f"[1/2] 登录 {args.host}:{args.port} ...")
        await api.login()
        print("      登录成功，已获得 sysauth cookie")

        print("[2/2] 拉取状态 ...")
        data = await api.fetch_status()

        print("\n===== 状态数据 =====")
        print(json.dumps(data, ensure_ascii=False, indent=2))

        return 0

    except KunpengCpeApiError as err:
        print(f"\n[错误] {err}", file=sys.stderr)
        return 1
    finally:
        await api.close()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(args))