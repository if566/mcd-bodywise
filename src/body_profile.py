#!/usr/bin/env python3
"""身体状态 -> 营养目标 评估引擎。

不依赖麦当劳 MCP，纯本地计算。输入用户的身体基本情况与今日状态，
输出单餐的目标热量区间、宏量营养素目标、营养侧重标签，
以及可直接用于麦当劳 MCP 菜单筛选的约束条件。

营养学依据：
- BMR 采用 Mifflin-St Jeor 公式（较 Harris-Benedict 更准）
- 活动系数参考通用 TDEE 系数（久坐1.2 / 轻度1.375 / 中度1.55 / 高强度1.725）
- 蛋白系数参考 ISSN / 运动营养共识（普通人1.2，增肌/减脂1.6-2.2 g/kg）
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import List


ACTIVITY_FACTORS = {
    "sedentary": 1.2,
    "light": 1.375,
    "moderate": 1.55,
    "high": 1.725,
}
ACTIVITY_LABELS = {
    "sedentary": "久坐（很少动）",
    "light": "轻度（日常走动/散步）",
    "moderate": "中度（运动30-60分钟）",
    "high": "高强度（运动>60分钟/重体力）",
}

# 身体状态规则表
# calorie_delta_pct = 相对 TDEE 的热量偏移；protein_g_per_kg = 每公斤体重蛋白目标
BODY_STATE_RULES = {
    "none": {
        "label": "无特殊",
        "calorie_delta_pct": 0.0,
        "protein_g_per_kg": 1.2,
        "tags": ["均衡"],
        "advice": "维持日常营养平衡即可，注意搭配蔬菜与无糖饮品。",
    },
    "fat_loss": {
        "label": "减脂期",
        "calorie_delta_pct": -0.20,
        "protein_g_per_kg": 2.0,
        "tags": ["高蛋白", "控热量", "高纤维"],
        "advice": "制造约20%热量缺口，提高蛋白以保留肌肉；多选蔬菜、无糖饮品，避开油炸。",
    },
    "muscle_gain": {
        "label": "健身增肌",
        "calorie_delta_pct": 0.12,
        "protein_g_per_kg": 1.8,
        "tags": ["高蛋白", "足量碳水"],
        "advice": "小幅热量盈余+高蛋白，训练后及时补充碳水与优质蛋白。",
    },
    "cold": {
        "label": "感冒/身体不适",
        "calorie_delta_pct": 0.05,
        "protein_g_per_kg": 1.5,
        "tags": ["高蛋白", "维C", "清淡", "避油腻"],
        "advice": "维持或略增热量，提高蛋白助组织修复；避免油炸油腻，多选温热、含维C的餐品。",
    },
    "fatigue": {
        "label": "熬夜/疲劳",
        "calorie_delta_pct": 0.0,
        "protein_g_per_kg": 1.3,
        "tags": ["稳血糖", "控糖", "B族"],
        "advice": "维持热量，选择低GI、稳血糖、少精制糖的食物，避免血糖骤升骤降加重疲惫。",
    },
    "period": {
        "label": "生理期",
        "calorie_delta_pct": 0.0,
        "protein_g_per_kg": 1.3,
        "tags": ["补铁", "温热", "优质蛋白"],
        "advice": "维持热量，侧重铁与优质蛋白，避免生冷，优先温热餐品。",
    },
    "training": {
        "label": "当日大消耗/运动",
        "calorie_delta_pct": 0.10,
        "protein_g_per_kg": 1.7,
        "tags": ["高蛋白", "补碳水"],
        "advice": "活动系数已较高，再补碳水与蛋白以支持恢复，训练后尽快进食。",
    },
}

# 单餐钠上限（麦当劳普遍高钠，给出提醒阈值，mg）
SODIUM_PER_MEAL_WARN = 1800


@dataclass
class BodyProfile:
    sex: str                 # "m" / "f"
    age: int
    height_cm: float
    weight_kg: float
    activity: str            # 见 ACTIVITY_FACTORS
    body_state: str = "none" # 见 BODY_STATE_RULES
    meal_count: int = 3      # 一日几餐（用于把日目标折算到单餐）

    def validate(self) -> List[str]:
        errs = []
        if self.sex not in ("m", "f"):
            errs.append("sex 须为 'm' 或 'f'")
        if not (10 <= self.age <= 120):
            errs.append("age 应在 10-120")
        if not (100 <= self.height_cm <= 250):
            errs.append("height_cm 应在 100-250")
        if not (30 <= self.weight_kg <= 300):
            errs.append("weight_kg 应在 30-300")
        if self.activity not in ACTIVITY_FACTORS:
            errs.append(f"activity 须为 {list(ACTIVITY_FACTORS)}")
        if self.body_state not in BODY_STATE_RULES:
            errs.append(f"body_state 须为 {list(BODY_STATE_RULES)}")
        if self.meal_count < 1:
            errs.append("meal_count >= 1")
        return errs


@dataclass
class NutritionTarget:
    bmr: float
    tdee: float
    target_calories_lo: float
    target_calories_hi: float
    protein_g_lo: float
    protein_g_hi: float
    fat_g_hi: float
    carb_g_est: float
    tags: List[str]
    advice: str
    state_label: str
    activity_label: str
    avoid_cold: bool = False

    def to_constraints(self) -> dict:
        """输出给 nutrition.py（麦当劳 MCP 筛选）用的约束。"""
        return {
            "calorie_cap": round(self.target_calories_hi),
            "calorie_floor": round(self.target_calories_lo),
            "protein_min": round(self.protein_g_lo),
            "fat_cap": round(self.fat_g_hi),
            "prefer_tags": self.tags,
            "sodium_warn": SODIUM_PER_MEAL_WARN,
            "avoid_cold": self.avoid_cold,
        }

    def summary(self) -> str:
        lines = [
            f"基础代谢 BMR: {self.bmr:.0f} kcal",
            f"每日总消耗 TDEE: {self.tdee:.0f} kcal",
            f"目标热量(单餐): {self.target_calories_lo:.0f}–{self.target_calories_hi:.0f} kcal",
            f"蛋白质目标(单餐): {self.protein_g_lo:.0f}–{self.protein_g_hi:.0f} g",
            f"脂肪上限(单餐): {self.fat_g_hi:.0f} g",
            f"碳水估算(单餐): ~{self.carb_g_est:.0f} g",
            f"营养侧重: {', '.join(self.tags)}",
            f"建议: {self.advice}",
        ]
        return "\n".join(lines)


def compute_bmr(sex: str, age: int, height_cm: float, weight_kg: float) -> float:
    base = 10 * weight_kg + 6.25 * height_cm - 5 * age
    return base + 5 if sex == "m" else base - 161


def evaluate(profile: BodyProfile) -> NutritionTarget:
    errs = profile.validate()
    if errs:
        raise ValueError("身体档案不合法: " + "; ".join(errs))
    bmr = compute_bmr(profile.sex, profile.age, profile.height_cm, profile.weight_kg)
    tdee = bmr * ACTIVITY_FACTORS[profile.activity]
    rule = BODY_STATE_RULES[profile.body_state]

    daily_target = tdee * (1 + rule["calorie_delta_pct"])
    per_meal = daily_target / max(1, profile.meal_count)
    lo = per_meal * 0.9
    hi = per_meal * 1.1

    daily_protein_g = profile.weight_kg * rule["protein_g_per_kg"]
    per_meal_protein = daily_protein_g / max(1, profile.meal_count)
    p_lo = per_meal_protein * 0.85
    p_hi = per_meal_protein * 1.15

    fat_g_hi = (hi * 0.30) / 9
    carb_cal = hi - (p_hi * 4 + fat_g_hi * 9)
    carb_g_est = max(0.0, carb_cal / 4)

    return NutritionTarget(
        bmr=bmr, tdee=tdee,
        target_calories_lo=lo, target_calories_hi=hi,
        protein_g_lo=p_lo, protein_g_hi=p_hi,
        fat_g_hi=fat_g_hi, carb_g_est=carb_g_est,
        tags=list(rule["tags"]), advice=rule["advice"],
        state_label=rule["label"], activity_label=ACTIVITY_LABELS[profile.activity],
        avoid_cold=profile.body_state in ("period", "cold"),
    )


if __name__ == "__main__":
    demo = BodyProfile(sex="f", age=22, height_cm=165, weight_kg=55,
                       activity="moderate", body_state="fat_loss", meal_count=3)
    t = evaluate(demo)
    print(f"场景: {ACTIVITY_LABELS[demo.activity]} / {t.state_label}")
    print(t.summary())
    print("\nMCP 筛选约束:")
    import json
    print(json.dumps(t.to_constraints(), ensure_ascii=False))
