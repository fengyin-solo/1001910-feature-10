"""发电机业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "generator"
REQUIRED_FIELDS = ["发电机编号", "所属机组", "额定电压"]
INSPECTION_FIELDS = ["绝缘电阻", "轴承温度"]
STATUS_ORDER = ["待检测", "检测合格", "绝缘偏低", "已更换"]
ACTION_RULES = {"提交检测": "检测合格", "判定绝缘异常": "绝缘偏低", "更换发电机": "已更换"}
NEGATIVE_ACTIONS = []

# 批量检测结论 -> (目标状态, 检测结论字段值, 是否待处理)
CONCLUSION_RULES = {
    "合格": ("检测合格", "合格", False),
    "退回复检": ("待检测", "退回复检", True),
}
REPLACED_STATUS = "已更换"


def _is_blank(value: Any) -> bool:
    return value is None or not str(value).strip()


class GeneratorService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("发电机编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def stats(self) -> dict[str, int]:
        """发电机台账口径的统计数字；概览页的合格数必须与这里一致。"""
        rows = store.rows(MODULE)
        return {
            "total": len(rows),
            "pending": sum(1 for row in rows if row.get("status") == "待检测"),
            "qualified": sum(1 for row in rows if row.get("status") == "检测合格"),
            "abnormal": sum(1 for row in rows if row.get("status") == "绝缘偏低"),
            "replaced": sum(1 for row in rows if row.get("status") == REPLACED_STATUS),
        }

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if _is_blank(values.get(field))]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        for field in INSPECTION_FIELDS:
            entry[field] = values.get(field)
        entry["上次检测日"] = values.get("上次检测日")
        entry["检测结论"] = None
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"发电机 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于发电机可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target == "待检测"
        entry["abnormal"] = target == "绝缘偏低"
        if action == "提交检测":
            entry["检测结论"] = "合格"
        elif action == "判定绝缘异常":
            entry["检测结论"] = "绝缘偏低"
        elif action == "更换发电机":
            entry["检测结论"] = "已更换"
        return entry, f"发电机已{action}"

    def batch_inspect(
        self, ids: list[int], conclusion: str
    ) -> tuple[list[dict[str, Any]], str]:
        """批量提交检测结论，逐台校验、逐台返回结果。

        - 同一台发电机在一次请求里重复出现时只处理一次（以最新结论为准）；
        - 绝缘电阻或轴承温度缺失时只拦这一台，并说明卡在哪一项，其余照常生效；
        - 已更换的发电机不允许再被批量退回复检（已更换是终态，批量合格同样不能
          覆盖该状态，否则先判合格再退回就能绕过限制）。
        """
        rule = CONCLUSION_RULES[conclusion]
        target_status, conclusion_text, pending = rule
        results: list[dict[str, Any]] = []
        # dict 去重：重复 id 只保留最后一次，结论以本次提交为准（覆盖旧结论）。
        unique_ids: dict[int, None] = {}
        for entry_id in ids:
            unique_ids[entry_id] = None

        for entry_id in unique_ids:
            entry = store.find(MODULE, entry_id)
            name = entry.get("发电机编号") if entry else None
            if entry is None:
                results.append({
                    "id": entry_id,
                    "name": name,
                    "ok": False,
                    "message": "发电机不存在或已归档，未处理",
                    "entry": None,
                })
                continue

            if entry.get("status") == REPLACED_STATUS:
                hint = "，不允许再批量退回复检" if conclusion == "退回复检" else "，终态不能再被批量判定覆盖"
                results.append({
                    "id": entry_id,
                    "name": name,
                    "ok": False,
                    "message": f"该发电机已更换{hint}",
                    "entry": entry,
                })
                continue

            missing = [field for field in INSPECTION_FIELDS if _is_blank(entry.get(field))]
            if missing:
                results.append({
                    "id": entry_id,
                    "name": name,
                    "ok": False,
                    "message": f"缺少{'、'.join(missing)}，无法出具检测结论，已拦截",
                    "entry": entry,
                })
                continue

            entry["status"] = target_status
            entry["检测结论"] = conclusion_text
            entry["pending"] = pending
            entry["abnormal"] = False
            action_text = "判定合格" if conclusion == "合格" else "退回复检"
            results.append({
                "id": entry_id,
                "name": name,
                "ok": True,
                "message": f"已{action_text}",
                "entry": entry,
            })

        succeeded = sum(1 for item in results if item["ok"])
        failed = len(results) - succeeded
        summary = f"批量{('判定合格' if conclusion == '合格' else '退回复检')}完成：{succeeded} 台生效"
        if failed:
            summary += f"，{failed} 台被拦截"
        return results, summary
