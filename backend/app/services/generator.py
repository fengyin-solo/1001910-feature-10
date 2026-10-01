"""发电机业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

MODULE = "generator"
REQUIRED_FIELDS = ["发电机编号", "所属机组", "额定电压"]
MEASURE_FIELDS = ["绝缘电阻", "轴承温度"]
STATUS_ORDER = ["待检测", "检测合格", "绝缘偏低", "已更换"]
ACTION_RULES = {"提交检测": "检测合格", "判定绝缘异常": "绝缘偏低", "更换发电机": "已更换"}
NEGATIVE_ACTIONS = []

# 批量检测结论：整批判定合格 / 整批退回复检
BATCH_VERDICTS = {"合格": "检测合格", "退回复检": "待检测"}


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

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        self._sync_display(entry)
        rows.append(entry)
        return entry, []

    def stats(self) -> dict[str, int]:
        """台账统计：合格数与概览共用 store.counts 的口径，避免两边对不上。"""
        rows = store.rows(MODULE)
        today = date.today().isoformat()
        month_prefix = today[:7]
        return {
            "pending": sum(1 for row in rows if row.get("status") == "待检测"),
            "qualified": sum(1 for row in rows if row.get("status") == "检测合格"),
            "abnormal": sum(1 for row in rows if row.get("status") == "绝缘偏低"),
            "month_checked": sum(
                1 for row in rows if str(row.get("上次检测日") or "").startswith(month_prefix)
            ),
        }

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
        # 已更换的发电机归档退出待办；其余状态都还需要继续跟踪
        entry["pending"] = target != "已更换"
        entry["abnormal"] = action in NEGATIVE_ACTIONS or target == "绝缘偏低"
        if action == "提交检测":
            self._sync_display(entry, check_date=date.today().isoformat(), conclusion="合格")
        elif action == "判定绝缘异常":
            self._sync_display(entry, conclusion="绝缘异常")
        else:
            self._sync_display(entry)
        return entry, f"发电机已{action}"

    def batch_inspect(
        self, entry_ids: list[int], verdict: str
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
        """批量提交检测结论，逐台给出结果，某一台被拦不影响其余发电机生效。

        - 合格：绝缘电阻或轴承温度缺失的发电机只拦它自己，并说明卡在哪一项
        - 退回复检：已经更换过的发电机不允许再被批量退回（已更换为终态，批量结论一律不再改动）
        - 同一台发电机重复提交：结论直接覆盖，只留最新一次
        """
        target = BATCH_VERDICTS.get(verdict)
        succeeded: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []
        # 同一台发电机在一次请求里重复出现时，只按最后一次处理
        for entry_id in dict.fromkeys(entry_ids):
            entry = store.find(MODULE, entry_id)
            if entry is None:
                failed.append({"id": entry_id, "message": f"发电机 {entry_id} 不存在或已归档"})
                continue
            code = str(entry.get("发电机编号") or entry_id)

            if entry.get("status") == "已更换":
                hint = "退回复检" if verdict == "退回复检" else "重新判定"
                failed.append({"id": entry_id, "code": code, "message": f"{code} 已更换，不能再批量{hint}"})
                continue

            missing = [
                field for field in MEASURE_FIELDS if not str(entry.get(field) or "").strip()
            ]
            if missing:
                failed.append({
                    "id": entry_id,
                    "code": code,
                    "message": f"{code} 缺少{'、'.join(missing)}，检测数据不完整，未提交结论",
                })
                continue

            entry["status"] = target
            entry["pending"] = True
            entry["abnormal"] = False
            today = date.today().isoformat()
            self._sync_display(entry, check_date=today, conclusion=verdict)
            succeeded.append({
                "id": entry_id,
                "code": code,
                "message": f"{code} 已判定{verdict}",
                "entry": entry,
            })
        return succeeded, failed, len(dict.fromkeys(entry_ids))

    @staticmethod
    def _sync_display(
        entry: dict[str, Any], *, check_date: str | None = None, conclusion: str | None = None
    ) -> None:
        """把内部状态同步到列表展示列，保证台账与状态字段始终一致。"""
        entry["发电机状态"] = entry.get("status")
        if check_date:
            entry["上次检测日"] = check_date
        if conclusion:
            entry["检测结论"] = conclusion
