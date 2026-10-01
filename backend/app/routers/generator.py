"""发电机接口：维护发电机，覆盖提交检测、判定绝缘异常、更换发电机等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import (
    ActionResult,
    BatchInspectionPayload,
    BatchInspectionResult,
    EntryPayload,
    PageResult,
)
from app.services.generator import CONCLUSION_RULES, GeneratorService

router = APIRouter(prefix="/api/generator", tags=["发电机"])

service = GeneratorService()

LIST_FIELDS = ["发电机编号", "所属机组", "额定电压", "绝缘电阻", "轴承温度", "上次检测日", "检测结论", "发电机状态"]
STATUSES = ["待检测", "检测合格", "绝缘偏低", "已更换"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按发电机编号检索"),
    status: str | None = Query(default=None, description="待检测、检测合格、绝缘偏低、已更换"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按发电机编号与状态过滤发电机列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/stats")
def get_stats() -> dict[str, int]:
    """发电机台账统计：待检测、检测合格、绝缘偏低、已更换各多少台。"""
    return service.stats()


@router.post("/batch-inspection", response_model=BatchInspectionResult)
def batch_inspection(payload: BatchInspectionPayload) -> BatchInspectionResult:
    """批量提交检测结论：整批判定合格或整批退回复检，逐台返回结果。

    单台不满足条件（缺绝缘电阻/轴承温度、发电机已更换）时只拦这一台，
    其余发电机照常生效。
    """
    if not payload.ids:
        raise HTTPException(status_code=400, detail="请至少勾选一台发电机")
    if payload.conclusion not in CONCLUSION_RULES:
        raise HTTPException(
            status_code=400,
            detail=f"检测结论仅支持：{'、'.join(CONCLUSION_RULES)}",
        )
    results, message = service.batch_inspect(payload.ids, payload.conclusion)
    return BatchInspectionResult(
        ok=any(item["ok"] for item in results),
        conclusion=payload.conclusion,
        message=message,
        results=results,
    )


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出发电机清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "generator", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条发电机明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"发电机 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条发电机，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="发电机已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条发电机执行提交检测、判定绝缘异常、更换发电机；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
