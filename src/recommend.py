#!/usr/bin/env python3
"""麦当劳·身体情况定制营养推荐 —— CLI 入口与报告生成。

整合 body_profile（身体评估）与 nutrition（MCP 拉取+筛选），输出可读推荐报告。
也可加 --json 输出结构化结果，便于被 WorkBuddy Skill 调用后二次处理。

示例:
  python recommend.py --sex f --age 22 --height 165 --weight 55 \
      --activity moderate --state fat_loss --meal-count 3
  python recommend.py --json-input '{"sex":"f","age":22,...}' --json
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from body_profile import (BodyProfile, evaluate, ACTIVITY_LABELS,
                          BODY_STATE_RULES)
from nutrition import (McdMcpClient, build_recommendations, fetch_meals,
                       find_store, match_meal_code, calculate_price,
                       fetch_store_coupons, build_coupon_map, normalize_name)


def fmt_item(it: dict) -> str:
    return (f"{it.get('productName','?')}: {it.get('energyKcal',0):.0f}kcal | "
            f"蛋白{it.get('protein',0):.0f}g | 脂肪{it.get('fat',0):.0f}g | "
            f"碳水{it.get('carbohydrate',0):.0f}g | 钠{it.get('sodium',0):.0f}mg")


def build_profile_from_args(args) -> BodyProfile:
    d = {
        "sex": args.sex, "age": args.age, "height_cm": args.height,
        "weight_kg": args.weight, "activity": args.activity,
        "body_state": args.state, "meal_count": args.meal_count,
    }
    missing = [k for k, v in d.items() if v is None]
    if missing:
        raise SystemExit(f"缺少必要参数: {missing}（或用 --json-input 提供完整 JSON）")
    return BodyProfile(**d)


def enrich_combos_with_price(client, combos, store_code, city, area,
                            with_coupon=True, coupon_map=None):
    """为每套组合注入实时价格与可选券叠加。返回 (combos, note)。

    券叠加逻辑：先算「无券实付」，再用门店可用券（query-store-coupons 返回
    couponCode+couponId+适用商品 code）挂到对应商品上重算「用券实付」，取较优者。
    """
    if not store_code:
        store_code = find_store(client, city, area)
    if not store_code:
        return combos, "未定位到门店（用 --store-code 指定，或检查 --city/--area）"
    meals = fetch_meals(client, store_code)
    if not meals:
        return combos, f"门店 {store_code} 餐品列表为空"
    if coupon_map is None and with_coupon:
        try:
            coupons = fetch_store_coupons(client, store_code)
            coupon_map = build_coupon_map(coupons)
        except Exception:
            coupon_map = None
    for combo in combos:
        names = [combo["main"].get("productName", ""),
                 combo["side"].get("productName", "")]
        codes, unmatched = [], []
        for nm in names:
            code = match_meal_code(nm, meals)
            if code:
                codes.append(code)
            else:
                unmatched.append(nm)
        if codes:
            if unmatched:
                # 部分餐品无法计价：只用已匹配项的菜单标价，并明确标注缺失项
                combo["price_info"] = {
                    "menu_total": sum(meals[c]["price"] for c in codes),
                    "unmatched": unmatched,
                }
                continue
            base = calculate_price(client, store_code, codes)
            if not base:
                combo["price_info"] = {
                    "menu_total": sum(meals[c]["price"] for c in codes),
                    "unmatched": [],
                }
                continue
            pi = dict(base)
            if coupon_map:
                used = [c for c in codes if str(c) in coupon_map]
                if used:
                    coupon_calc = calculate_price(
                        client, store_code, codes, coupon_map=coupon_map)
                    if coupon_calc and coupon_calc["price"] < base["price"]:
                        pi["coupon_price"] = coupon_calc["price"]
                        pi["coupon_save"] = round(base["price"] - coupon_calc["price"], 2)
                        pi["coupon_titles"] = [coupon_map[str(c)]["title"] for c in used]
            combo["price_info"] = pi
    note = f"门店 {store_code}（麦当劳官方 MCP 实时查询）"
    if coupon_map:
        note += " · 已尝试叠加门店可用券"
    return combos, note


def print_report(profile: BodyProfile, target, rec: dict) -> None:
    c = target.to_constraints()
    bar = "=" * 56
    print(bar)
    print("🍔 麦当劳 · 身体情况定制营养推荐")
    print(bar)
    print(f"场景: {ACTIVITY_LABELS[profile.activity]} / {BODY_STATE_RULES[profile.body_state]['label']}")
    print(target.summary())
    print(f"\n数据源: 麦当劳官方 MCP · 共 {rec['counts']['total']} 个餐品 "
          f"(主餐 {rec['counts']['mains']} / 饮品 {rec['counts']['drinks']} / 小食 {rec['counts']['sides']})")
    if rec.get("price_note"):
        print(f"💰 价格: {rec['price_note']}")

    print("\n【组合推荐】主餐 + 配餐（总热量落在目标区间）")
    if not rec["combos"]:
        print("  （当前目标较严格，未找到完全匹配的组合，可放宽热量区间或餐数）")
    for i, combo in enumerate(rec["combos"], 1):
        t = combo["totals"]
        side_label = combo.get("side_label", "配餐")
        combo_name = f"{combo['main']['productName']} + {combo['side']['productName']}（{side_label}）"
        print(f"\n  方案{i}: {combo_name}")
        line = (f"    总热量 {t['energyKcal']:.0f}kcal | 蛋白 {t['protein']:.0f}g | "
                f"脂肪 {t['fat']:.0f}g | 钠 {t['sodium']:.0f}mg")
        print(line)
        if t["sodium"] > c["sodium_warn"]:
            print(f"    ⚠️ 钠 {t['sodium']:.0f}mg 超过单餐建议上限 {c['sodium_warn']}mg，注意补水")
        pi = combo.get("price_info")
        if pi:
            base_names = [combo["main"].get("productName", ""),
                          combo["side"].get("productName", "")]
            if "price" in pi:
                disc = f" (已享活动优惠 -¥{pi['discount']:.2f})" if pi.get("discount") else ""
                print(f"    💴 无券实付 ¥{pi['price']:.2f}{disc}")
                if pi.get("coupon_price") is not None:
                    print(f"    🎟️ 叠加门店券后 ¥{pi['coupon_price']:.2f}"
                          f"（再省 ¥{pi['coupon_save']:.2f}）")
                    for t in pi.get("coupon_titles", []):
                        print(f"      · 已用券: {t}")
                for nm, it in zip(base_names, pi.get("product_list", [])):
                    sub = (it.get("subtotal") or 0) / 100.0
                    print(f"      · {nm}: ¥{sub:.2f}")
                if pi.get("unmatched"):
                    print(f"    * 以下餐品未匹配到价格: {', '.join(pi['unmatched'])}")
            elif "menu_total" in pi:
                note = f"（未含: {', '.join(pi['unmatched'])}）" if pi.get("unmatched") else ""
                print(f"    💴 菜单标价合计 ¥{pi['menu_total']:.2f}{note}")

    print("\n【高蛋白单品 Top】")
    if not rec["single_top"]:
        print("  （无单品同时满足热量/蛋白/脂肪约束）")
    for it in rec["single_top"]:
        print("  - " + fmt_item(it))

    print("\n💡 个性化建议: " + target.advice)
    print(bar)


def main() -> None:
    ap = argparse.ArgumentParser(description="麦当劳身体情况定制营养推荐")
    ap.add_argument("--sex", choices=["m", "f"])
    ap.add_argument("--age", type=int)
    ap.add_argument("--height", type=float, help="身高 cm")
    ap.add_argument("--weight", type=float, help="体重 kg")
    ap.add_argument("--activity", choices=list(ACTIVITY_LABELS.keys()))
    ap.add_argument("--state", choices=list(BODY_STATE_RULES.keys()), default="none")
    ap.add_argument("--meal-count", type=int, default=3)
    ap.add_argument("--json-input", help="完整身体档案 JSON 字符串")
    ap.add_argument("--json", action="store_true", help="输出结构化 JSON")
    ap.add_argument("--with-price", action="store_true", help="叠加实时价格（需联网查门店与餐品价）")
    ap.add_argument("--with-coupon", dest="with_coupon", action="store_true",
                    help="叠加门店可用优惠券（默认开启，随 --with-price）")
    ap.add_argument("--no-coupon", dest="with_coupon", action="store_false",
                    help="不叠加优惠券，仅显示无券实付价")
    ap.set_defaults(with_coupon=True)
    ap.add_argument("--store-code", help="门店编码（优先于 city/area 自动搜索）")
    ap.add_argument("--city", default="广州", help="自动搜门店时的城市")
    ap.add_argument("--area", default="天河", help="自动搜门店时的区域关键词")
    args = ap.parse_args()

    if args.json_input:
        d = json.loads(args.json_input)
        profile = BodyProfile(**d)
    else:
        profile = build_profile_from_args(args)

    target = evaluate(profile)
    constraints = target.to_constraints()

    client = McdMcpClient()
    client.connect()
    items = client.fetch_nutrition_items()

    # 若需要价格/优惠券，先定位门店并拉取可用券，构建「省钱偏好」注入推荐排序
    coupon_map = None
    prefer_names = None
    store_code = args.store_code
    if args.with_price or store_code:
        if not store_code:
            store_code = find_store(client, args.city, args.area)
        if store_code:
            meals = fetch_meals(client, store_code)
            if args.with_coupon and meals:
                try:
                    coupons = fetch_store_coupons(client, store_code)
                    coupon_map = build_coupon_map(coupons)
                    prefer_names = set()
                    for pcode in coupon_map:
                        nm = meals.get(pcode, {}).get("name")
                        if nm:
                            # 与 nutrition._gen 的偏好比较保持一致：去温度字
                            prefer_names.add(normalize_name(nm).replace("冰", "").replace("热", ""))
                except Exception:
                    coupon_map = None
                    prefer_names = None

    rec = build_recommendations(constraints, items, prefer_names=prefer_names)

    if store_code:
        rec["combos"], note = enrich_combos_with_price(
            client, rec["combos"], store_code, args.city, args.area,
            with_coupon=args.with_coupon, coupon_map=coupon_map)
        rec["price_note"] = note

    if args.json:
        print(json.dumps({
            "profile": {
                "sex": profile.sex, "age": profile.age,
                "height_cm": profile.height_cm, "weight_kg": profile.weight_kg,
                "activity": profile.activity, "body_state": profile.body_state,
                "meal_count": profile.meal_count,
            },
            "target": constraints,
            "recommendation": rec,
        }, ensure_ascii=False, indent=2))
    else:
        print_report(profile, target, rec)


if __name__ == "__main__":
    main()
