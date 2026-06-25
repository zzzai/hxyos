from __future__ import annotations

from typing import Any


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _ratio(value: float, target: float) -> float:
    if target <= 0:
        return 1.0
    return value / target


def _percent(value: float) -> str:
    return f"{round(value * 100)}%"


def _add_anomaly(
    anomalies: list[dict[str, Any]],
    *,
    key: str,
    title: str,
    severity: str,
    current: Any,
    target: Any,
    detail: str,
    action_hint: str,
) -> None:
    anomalies.append(
        {
            "key": key,
            "title": title,
            "severity": severity,
            "current": current,
            "target": target,
            "detail": detail,
            "action_hint": action_hint,
        }
    )


def diagnose_store_daily_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    store_id = str(metrics.get("store_id") or "").strip() or "unknown-store"
    store_name = str(metrics.get("store_name") or "").strip() or store_id
    business_date = str(metrics.get("business_date") or "").strip()
    revenue = _number(metrics.get("revenue"))
    target_revenue = _number(metrics.get("target_revenue"))
    orders = int(_number(metrics.get("orders")))
    average_ticket = _number(metrics.get("average_ticket"))
    target_average_ticket = _number(metrics.get("target_average_ticket"))
    repeat_rate = _number(metrics.get("repeat_rate"))
    target_repeat_rate = _number(metrics.get("target_repeat_rate"))
    product_mix = metrics.get("product_mix") if isinstance(metrics.get("product_mix"), dict) else {}
    clear_mix = _number(product_mix.get("清泡"))
    upgrade_mix = sum(_number(product_mix.get(name)) for name in ["调泡", "补泡", "养泡"])
    training_retrain_count = int(_number(metrics.get("training_retrain_count")))
    customer_complaints = int(_number(metrics.get("customer_complaints")))

    anomalies: list[dict[str, Any]] = []
    if target_revenue > 0 and _ratio(revenue, target_revenue) < 0.9:
        _add_anomaly(
            anomalies,
            key="revenue_gap",
            title="营业额未达目标",
            severity="high" if _ratio(revenue, target_revenue) < 0.75 else "medium",
            current=round(revenue, 2),
            target=round(target_revenue, 2),
            detail=f"当前营业额只完成目标的 {_percent(_ratio(revenue, target_revenue))}。",
            action_hint="先拆订单数和客单价，确认是客流不足还是升级转化不足。",
        )
    if target_average_ticket > 0 and _ratio(average_ticket, target_average_ticket) < 0.9:
        _add_anomaly(
            anomalies,
            key="average_ticket_gap",
            title="客单价低于目标",
            severity="high" if _ratio(average_ticket, target_average_ticket) < 0.75 else "medium",
            current=round(average_ticket, 2),
            target=round(target_average_ticket, 2),
            detail=f"当前客单价只达到目标的 {_percent(_ratio(average_ticket, target_average_ticket))}。",
            action_hint="重点检查清泡调补养升级话术和员工是否会按顾客状态推荐。",
        )
    if target_repeat_rate > 0 and _ratio(repeat_rate, target_repeat_rate) < 0.9:
        _add_anomaly(
            anomalies,
            key="repeat_rate_gap",
            title="复购率低于目标",
            severity="high" if _ratio(repeat_rate, target_repeat_rate) < 0.7 else "medium",
            current=round(repeat_rate, 4),
            target=round(target_repeat_rate, 4),
            detail=f"当前复购率为 {_percent(repeat_rate)}，目标为 {_percent(target_repeat_rate)}。",
            action_hint="复盘首次顾客服务后是否有复访理由、复访提醒和顾客状态记录。",
        )
    if clear_mix > 0.6 or upgrade_mix < 0.4:
        _add_anomaly(
            anomalies,
            key="product_mix_upgrade_gap",
            title="产品升级占比不足",
            severity="high" if clear_mix > 0.65 else "medium",
            current={"清泡": round(clear_mix, 4), "升级项目": round(upgrade_mix, 4)},
            target={"清泡": "<=0.60", "升级项目": ">=0.40"},
            detail=f"清泡占比 {_percent(clear_mix)}，调泡/补泡/养泡合计 {_percent(upgrade_mix)}。",
            action_hint="把顾客状态询问、对应泡脚方推荐、禁用夸大表达放到班前会演练。",
        )
    if training_retrain_count >= 2:
        _add_anomaly(
            anomalies,
            key="training_risk",
            title="员工话术复训风险",
            severity="high",
            current=training_retrain_count,
            target="<2",
            detail=f"今日/近期有 {training_retrain_count} 次话术需要复训。",
            action_hint="店长必须抽查员工能否讲清清泡调补养差异和禁用表达。",
        )
    if customer_complaints >= 2:
        _add_anomaly(
            anomalies,
            key="complaint_risk",
            title="顾客投诉风险",
            severity="medium",
            current=customer_complaints,
            target="<2",
            detail=f"今日/近期有 {customer_complaints} 条顾客投诉信号。",
            action_hint="优先回看服务流程、等待时间、推荐话术是否造成过度承诺。",
        )

    anomaly_keys = {item["key"] for item in anomalies}
    today_actions = [
        "班前会用 10 分钟只练一件事：顾客问“有什么区别”时，员工必须先问睡眠、疲劳、手脚凉、压力，再推荐调泡/补泡/养泡。",
        "店长今天抽查至少 5 单低客单订单，记录员工是否只推荐清泡、是否讲清产品升级价值。",
        "把今日清泡占比、升级项目占比、客单价贴到店长复盘表，晚班前复盘一次。",
    ]
    if "repeat_rate_gap" in anomaly_keys:
        today_actions.append("筛出 45-60 天未到访顾客，按上次服务状态生成召回话术，今天完成第一轮触达。")
    if "complaint_risk" in anomaly_keys:
        today_actions.append("店长当天回访投诉顾客，先确认体验问题，不做疗效或结果承诺。")
    if "training_risk" in anomaly_keys:
        today_actions.append("对复训员工做一对一纠偏，未通过前不允许独立讲升级项目。")

    high_count = sum(1 for item in anomalies if item["severity"] == "high")
    if len(anomalies) >= 3 or high_count >= 2:
        priority = "high"
    elif anomalies:
        priority = "medium"
    else:
        priority = "low"

    if {"average_ticket_gap", "product_mix_upgrade_gap"} <= anomaly_keys:
        main_conflict = "主要矛盾是客单价偏低，背后是员工没有把清泡顾客有效转化到调泡、补泡、养泡等产品升级。"
    elif "repeat_rate_gap" in anomaly_keys:
        main_conflict = "主要矛盾是复购不足，顾客服务记录、复访理由和召回动作没有形成闭环。"
    elif "revenue_gap" in anomaly_keys:
        main_conflict = "主要矛盾是营业额未达目标，需要先拆解客流、客单价和复购哪个环节拖累结果。"
    elif "training_risk" in anomaly_keys:
        main_conflict = "主要矛盾是员工话术不稳定，标准口径没有转化成可执行动作。"
    else:
        main_conflict = "今日经营指标未触发明显异常，重点保持训练和复盘节奏。"

    should_create_issue = priority == "high" or len(anomalies) >= 3
    return {
        "version": "hxy-store-daily-diagnosis.v1",
        "store_id": store_id,
        "store_name": store_name,
        "business_date": business_date,
        "summary": f"{store_name} {business_date} 识别到 {len(anomalies)} 个经营异常，优先级 {priority}。",
        "metrics": {
            "revenue": revenue,
            "target_revenue": target_revenue,
            "orders": orders,
            "average_ticket": average_ticket,
            "target_average_ticket": target_average_ticket,
            "repeat_rate": repeat_rate,
            "target_repeat_rate": target_repeat_rate,
            "product_mix": product_mix,
        },
        "anomalies": anomalies,
        "main_conflict": main_conflict,
        "priority": priority,
        "owner": "店长",
        "today_actions": today_actions,
        "should_create_issue": should_create_issue,
        "issue_candidate": {
            "title": f"{store_name} 日经营异常复盘",
            "priority": priority,
            "owner": "店长",
            "reason": main_conflict,
            "recommended_action": today_actions[0],
        }
        if should_create_issue
        else None,
    }
