---
name: mcd-bodywise
description: 根据用户的身体基本情况（性别/年龄/身高/体重/今日运动量）与今日身体状态（减脂/增肌/感冒/熬夜/生理期/大消耗等），调用麦当劳官方 MCP 拉取实时营养数据，推荐符合当日热量与营养目标的麦当劳餐品组合。当用户说"我今天想吃点麦当劳但要看身体情况"、"健身后吃点啥"、"感冒了吃麦当劳怎么点"、"减脂期麦当劳怎么点"、"帮我按今天的身体状态推荐麦当劳"等时使用。
---

# 麦当劳 · 身体情况定制营养推荐（MCD Bodywise）

一个把「用户今日身体情况」转化为「麦当劳当日点餐方案」的 Skill：用 Mifflin-St Jeor 公式
估算基础代谢与每日消耗，结合今日运动量/身体状态给出单餐热量与蛋白目标，再调用麦当劳
官方 MCP 的 `list-nutrition-foods` 拉取实时营养数据，筛选出匹配目标的餐品组合。

## 适用场景
- 用户想按身体状态点麦当劳：「减脂期怎么点」「健身后吃点啥」「感冒了吃啥」
- 用户给出身体数据后，希望得到热量/蛋白/脂肪都合适的餐品方案
- 需要结合优惠券/价格的进阶点餐（见下方扩展点）

## 工作流程
1. **收集身体情况**：若用户未给全，用简洁问题补齐：性别、年龄、身高(cm)、体重(kg)、
   今日运动量、今日身体状态。可用一条消息列出选项，避免来回追问。
2. **计算目标**：内部 `body_profile.py` 用 BMR×活动系数×状态修正，得到单餐热量区间、
   蛋白/脂肪目标、营养侧重标签。
3. **拉取营养数据**：调用麦当劳 MCP `list-nutrition-foods`（无需门店上下文）。
4. **筛选+组合**：`nutrition.py` 解析数据，生成「主餐+饮品」组合推荐与高蛋白单品 Top。
5. **输出报告**：给出 3 套方案（热量/蛋白/脂肪/钠）+ 个性化建议 + 钠提醒。
6. **（可选）叠加价格**：若用户要实付价，加 `--with-price`，内部经 `query-nearby-stores`
   → `query-meals` → `calculate-price` 自动定位门店并计算含优惠的实付价，标注到每套方案。

## 调用方式
```bash
# 参数方式
python src/recommend.py --sex f --age 22 --height 165 --weight 55 \
    --activity moderate --state fat_loss --meal-count 3

# JSON 方式（便于程序化调用）
python src/recommend.py --json-input '{"sex":"f","age":22,"height_cm":165,"weight_kg":55,"activity":"moderate","body_state":"fat_loss","meal_count":3}'

# 输出结构化 JSON（加 --json）
python src/recommend.py --json-input '...' --json
```
参数说明：
- `sex`: `m` / `f`
- `age`: 整数
- `height_cm`: 身高(cm)
- `weight_kg`: 体重(kg)
- `activity`: `sedentary`(久坐) / `light`(轻度) / `moderate`(中度) / `high`(高强度)
- `state`: `none`(无特殊) / `fat_loss`(减脂) / `muscle_gain`(增肌) / `cold`(感冒) /
  `fatigue`(熬夜) / `period`(生理期) / `training`(当日大消耗)
- `meal_count`: 一日几餐（默认 3）
- `--with-price`: 叠加实时价格（麦当劳官方 MCP，需联网查门店与餐品价）
- `--store-code`: 直接指定门店编码（优先于自动搜索）
- `--city` / `--area`: 自动搜门店的城市/区域（默认 广州 / 天河）

带价格的调用示例：
```bash
python src/recommend.py --sex f --age 22 --height 165 --weight 55 \
    --activity moderate --state fat_loss --meal-count 3 --with-price
```
价格链路：`query-nearby-stores`（定位门店）→ `query-meals`（餐品编码与价格）
→ 按名称匹配营养表中的主餐/饮品 → `calculate-price`（含优惠实付价）。
若组合中某餐品在门店无对应单品，会标注「未含」并只对可计价部分求和，避免不完整报价。

**优惠券叠加**：`--with-price` 默认同步尝试门店券（可用 `--no-coupon` 关闭）。内部调用
`query-store-coupons` 取得该门店可用券（含 `couponCode`/`couponId`/适用商品 `productCode`），
映射到命中商品后在 `calculate-price` 时**同时传 `couponCode` + `couponId`**（两者缺一不可，否则返异常价），
对比「无券实付」与「用券实付」展示「再省 ¥X」与所用券名；推荐排序亦轻微偏好有券商品。

## 前置依赖
- **麦当劳 MCP Token**：环境变量 `MCD_MCP_TOKEN` 或文件 `~/.config/mcd/mcp_token`
  （申请：https://open.mcd.cn/mcp ，手机号登录 → 控制台 → 激活 → 复制）
- Python 依赖：`pip install -r requirements.txt`（仅需 `requests`）
- 数据范围：麦当劳中国大陆官方营养数据

## 注意事项
- 营养数据为麦当劳官方标称值；过敏、孕期、慢病等特殊人群请遵医嘱，本 Skill 不替代专业建议。
- 本 Skill 默认**只做推荐、不直接下单**。若需下单，引导用户使用麦当劳官方 App，
  或扩展调用 MCP 的 `create-order`（需门店与订单参数，风险自负）。
- 麦当劳餐品钠普遍偏高，报告已标注超过单餐建议上限(1800mg)的提醒。

## 身体状态 → 营养目标 规则表
| 状态 | 热量偏移(相对TDEE) | 蛋白(g/kg体重) | 营养侧重 |
|---|---|---|---|
| none 无特殊 | 0% | 1.2 | 均衡 |
| fat_loss 减脂 | −20% | 2.0 | 高蛋白 / 控热量 / 高纤维 |
| muscle_gain 增肌 | +12% | 1.8 | 高蛋白 / 足量碳水 |
| cold 感冒 | +5% | 1.5 | 高蛋白 / 维C / 清淡 / 避油腻 |
| fatigue 熬夜 | 0% | 1.3 | 稳血糖 / 控糖 / B族 |
| period 生理期 | 0% | 1.3 | 补铁 / 温热 / 优质蛋白 |
| training 大消耗 | +10% | 1.7 | 高蛋白 / 补碳水 |

## 文件结构
```
mcd-bodywise/
├── SKILL.md
├── requirements.txt
├── src/
│   ├── body_profile.py   # 身体评估 → 营养目标
│   ├── nutrition.py      # 麦当劳 MCP 客户端 + 解析 + 推荐
│   └── recommend.py      # CLI 入口 + 报告
├── scripts/
│   └── install_skill.sh  # 一键安装到 WorkBuddy
└── README.md
```

## 扩展点
- **价格/优惠（已实现）**：`--with-price` 已接入 `query-nearby-stores` → `query-meals` → `calculate-price`，
  自动定位门店并计算含优惠的实付价；并叠加 `query-store-coupons` 门店券（`couponCode`+`couponId` 齐传），
  展示「无券实付 → 用券价 → 再省 ¥X」；餐品无法匹配时诚实标注「未含」，不给出不完整报价。
- **下单**：`create-order`（需确认门店、订单类型、商品 code，谨慎使用）。
- **多餐规划**：把 `meal_count` 摊到早/午/晚并分别推荐。
