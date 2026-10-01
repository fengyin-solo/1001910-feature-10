"""内存数据仓库：给每个业务模块准备一份可筛选、可流转的示例数据。

真实项目里这里会换成数据库访问层；当前实现只依赖标准库，保证克隆下来就能起。
"""
from __future__ import annotations

from typing import Any

from app.seed import SEED_ROWS

# 各模块“合格/正常”状态：台账与概览的合格数统一按此口径统计。
QUALIFIED_STATUSES: dict[str, frozenset[str]] = {
    "windfarm": frozenset({"运行中"}),
    "turbine": frozenset({"运行中"}),
    "blade": frozenset({"完好"}),
    "gearbox": frozenset({"运行正常"}),
    "generator": frozenset({"检测合格"}),
    "pitch": frozenset({"调试正常"}),
    "yaw": frozenset({"运行正常"}),
    "metmast": frozenset({"数据正常"}),
    "collector": frozenset({"运行正常"}),
    "substation": frozenset({"运行正常"}),
    "forecast": frozenset({"已生成"}),
    "vibration": frozenset({"数据正常"}),
    "defect": frozenset(),
    "maintjob": frozenset({"运行正常"}),
    "spare": frozenset({"已批准", "已领用"}),
    "patrol": frozenset({"已提交"}),
    "accept": frozenset({"已通过"}),
    "settle": frozenset({"已核算"}),
}


class Store:
    def __init__(self) -> None:
        self._tables: dict[str, list[dict[str, Any]]] = {
            name: [dict(row) for row in rows] for name, rows in SEED_ROWS.items()
        }

    def module_names(self) -> list[str]:
        return sorted(self._tables)

    def rows(self, module: str) -> list[dict[str, Any]]:
        return self._tables.setdefault(module, [])

    def find(self, module: str, entry_id: int) -> dict[str, Any] | None:
        for row in self.rows(module):
            if int(row.get("id", 0)) == entry_id:
                return row
        return None

    def qualified_count(self, module: str) -> int:
        """某模块的合格数：台账页与概览页都走这里，保证两边数字一致。"""
        statuses = QUALIFIED_STATUSES.get(module, frozenset())
        return sum(1 for row in self.rows(module) if row.get("status") in statuses)

    def overview(self) -> dict[str, object]:
        modules: list[dict[str, object]] = []
        for name in self.module_names():
            rows = self.rows(name)
            modules.append({
                "name": name,
                "created": len(rows),
                "pending": sum(1 for row in rows if row.get("pending")),
                "abnormal": sum(1 for row in rows if row.get("abnormal")),
                "qualified": self.qualified_count(name),
            })
        cards = [
            {"label": "业务模块", "value": len(modules)},
            {"label": "今日新增", "value": sum(int(item["created"]) for item in modules)},
            {"label": "待处理", "value": sum(int(item["pending"]) for item in modules)},
            {"label": "异常量", "value": sum(int(item["abnormal"]) for item in modules)},
            {"label": "合格数", "value": sum(int(item["qualified"]) for item in modules)},
        ]
        return {"cards": cards, "modules": modules}


store = Store()
