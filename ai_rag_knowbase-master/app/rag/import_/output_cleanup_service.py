"""Import 输出目录清理。"""
import os
import shutil
import time
from pathlib import Path

from app.shared.runtime.logger import PROJECT_ROOT, logger

OUTPUT_RETENTION_DAYS: int = int(os.getenv("OUTPUT_RETENTION_DAYS", "7"))


def cleanup_old_output(retention_days: int | None = None) -> int:
    """删除 output/ 下超过 retention_days 的任务目录，返回删除数量。"""
    days = retention_days if retention_days is not None else OUTPUT_RETENTION_DAYS
    if days <= 0:
        return 0

    output_root = PROJECT_ROOT / "output"
    if not output_root.exists():
        return 0

    cutoff = time.time() - days * 86400
    removed = 0
    for date_dir in output_root.iterdir():
        if not date_dir.is_dir():
            continue
        for task_dir in date_dir.iterdir():
            if not task_dir.is_dir():
                continue
            try:
                if task_dir.stat().st_mtime < cutoff:
                    shutil.rmtree(task_dir, ignore_errors=True)
                    removed += 1
            except OSError as exc:
                logger.warning(f"清理目录失败 {task_dir}: {exc}")
    if removed:
        logger.info(f"已清理 {removed} 个过期 output 任务目录（>{days} 天）")
    return removed
