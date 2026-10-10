# 🍔 麦当劳 · 身体情况定制营养推荐 Skill（MCD Bodywise）

> 根据你的**今日身体情况**，调用**麦当劳官方 MCP** 实时营养数据，推荐热量、蛋白、脂肪都合适的麦当劳餐品组合。

---

## 这是什么

传统点餐助手只会按预算/热量上限筛菜单。MCD Bodywise 多走了一步：先搞清楚**你今天身体需要什么**。

它用 Mifflin-St Jeor 公式估算你的基础代谢与每日消耗，再结合**今日运动量**与**身体状态**
（减脂 / 增肌 / 感冒 / 熬夜 / 生理期 / 大消耗），算出单餐该吃多少热量、多少蛋白，
最后调用麦当劳官方 MCP 的 `list-nutrition-foods` 拉取全部餐品营养数据，筛出匹配的组合方案。

**参赛作品**：2026 麦当劳程序员创意开发大赛 · 基于麦当劳中国官方 MCP + WorkBuddy 开发。

---

## 快速开始

### 1. 申请麦当劳 MCP Token
访问 https://open.mcd.cn/mcp ，手机号登录 → 控制台 → 激活 → 复制 Token。

### 2. 配置 Token（二选一，请勿提交进仓库）
```bash
# 方式A：环境变量
export MCD_MCP_TOKEN="你的Token"

# 方式B：本地文件（推荐，脚本自动读取）
mkdir -p ~/.config/mcd && umask 077 && printf '%s' '你的Token' > ~/.config/mcd/mcp_token
```

### 3. 安装依赖
```bash
pip install -r requirements.txt
```

### 4. 安装 Skill 到 WorkBuddy
```bash
bash scripts/install_skill.sh            # 用户级
# 或指定项目：bash scripts/install_skill.sh /path/to/project
```

### 5. 直接使用（命令行）
```bash
python src/recommend.py --sex f --age 22 --height 165 --weight 55 \
    --activity moderate --state fat_loss --meal-count 3
```

在 WorkBuddy 中只需说：「我今天减脂期，想吃点麦当劳，帮我按身体情况推荐」，
Skill 会自动收集信息并调用上述逻辑给出方案。

---

## 工作原理

```
用户输入身体情况
      │
      ▼
body_profile.py  ── BMR(Mifflin-St Jeor) × 活动系数 × 状态修正
      │           → 单餐热量区间 / 蛋白·脂肪目标 / 营养侧重标签
      ▼
nutrition.py  ── 调用麦当劳 MCP list-nutrition-foods（实时营养数据）
      │           → 解析 → 主餐/饮品分类 → 筛选 + 组合
      ▼
recommend.py ── 生成 3 套「主餐+饮品」组合 + 高蛋白单品 Top + 钠提醒
```

---

## 价格功能（实时实付价）

默认只展示营养推荐（无需门店上下文）。加 `--with-price` 可叠加**麦当劳官方 MCP 实时价格**：

```bash
python src/recommend.py --sex f --age 22 --height 165 --weight 55 \
    --activity moderate --state fat_loss --meal-count 3 --with-price
```

链路：`query-nearby-stores`（按城市/区域定位门店）→ `query-meals`（拉取该店餐品与编码）
→ 按餐品名匹配营养表中的主餐/饮品 → `calculate-price`（含优惠的实付价）。

- `--store-code`：直接指定门店编码（跳过自动搜索）
- `--city` / `--area`：自动搜门店的城市与区域（默认 广州 / 天河）
- 若组合中某餐品在门店菜单无对应单品（如部分麦满分仅以套餐形式售卖），会标注「未含」并仅对可计价部分求和，**不会给出不完整的「实付」价**，避免误导。

### 优惠券叠加（门店券自动应用）

加 `--with-price` 时**默认同步尝试门店可用券叠加**（可用 `--no-coupon` 关闭）：

1. 调用 `query-store-coupons` 获取该门店可用券（含 `couponCode`、`couponId` 及适用商品 `productCode`）；
2. 将券映射到推荐组合中命中的商品，在 `calculate-price` 时**同时传入 `couponCode` + `couponId`**——麦当劳 MCP 必须两者齐传，否则会返回异常的 0 元价；
3. 对比「无券实付」与「用券实付」，展示 **再省 ¥X** 及所用券名。

此外，推荐排序会**轻微偏好「该门店有可用券」的商品**（仍在热量/营养达标前提下），让更省钱的搭配更可能被推到前面。

> 说明：券是否可叠加取决于该门店实际发放的券及其适用商品；若某券适用商品不在麦当劳公开营养表中（如仅限套餐），则无法在推荐组合里自动命中，会如实显示无券价。

---

## 身体状态 → 营养目标 规则表

| 状态 | 热量偏移(相对TDEE) | 蛋白(g/kg体重) | 营养侧重 |
|---|---|---|---|
| 无特殊 none | 0% | 1.2 | 均衡 |
| 减脂 fat_loss | −20% | 2.0 | 高蛋白 / 控热量 / 高纤维 |
| 增肌 muscle_gain | +12% | 1.8 | 高蛋白 / 足量碳水 |
| 感冒 cold | +5% | 1.5 | 高蛋白 / 维C / 清淡 / 避油腻 |
| 熬夜 fatigue | 0% | 1.3 | 稳血糖 / 控糖 / B族 |
| 生理期 period | 0% | 1.3 | 补铁 / 温热 / 优质蛋白 |
| 大消耗 training | +10% | 1.7 | 高蛋白 / 补碳水 |

---

## 目录结构

```
mcd-bodywise/
├── SKILL.md
├── README.md
├── requirements.txt
├── src/
│   ├── body_profile.py   # 身体评估 → 营养目标
│   ├── nutrition.py      # 麦当劳 MCP 客户端 + 解析 + 推荐
│   └── recommend.py      # CLI 入口 + 报告
└── scripts/
    └── install_skill.sh  # 一键安装
```

---

## 免责声明

- 营养数据为麦当劳官方标称值，仅供参考，不构成医疗/营养诊断建议。
- 过敏、孕期、慢性病等特殊人群请遵医嘱。
- 本 Skill 默认只做推荐、不直接下单；如需下单请使用麦当劳官方渠道，或自行扩展 `create-order`（风险自负）。

---

## 参赛声明

本项目为 **2026 麦当劳程序员创意开发大赛** 参赛作品，基于 **麦当劳中国官方 MCP**
（https://open.mcd.cn/mcp）能力开发，使用 **WorkBuddy** 辅助开发。代码以 MIT 协议开源，
营养数据版权归麦当劳中国所有，Token 与下单能力由用户自行申请与承担风险。

按大赛要求，报名请在麦当劳 GitHub 官方账号（M-China）活动页按指定 Issue 模板提交，
并附：项目介绍、参赛声明、MCP 接入说明（见上文）。
