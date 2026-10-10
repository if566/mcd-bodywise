# 🚀 参赛提交指南 · MCD Bodywise

本项目为 **2026 麦当劳程序员创意开发大赛** 参赛作品（基于麦当劳中国官方 MCP + WorkBuddy 开发）。
本文档帮助你把仓库推上 GitHub 并按官方 Issue 模板完成报名。

---

## 一、报名前置（一次性）

1. **GitHub 公开仓库**：仓库名建议 `mcd-bodywise`，公开（Public）。
2. **麦当劳 MCP Token**：仅本地使用，绝不进仓库（已被 `.gitignore` 屏蔽）。
3. **WorkBuddy 开发证明**：本项目全程由 WorkBuddy（Agent 模式）辅助开发，可在报名时申请 **+3000 积分**专项奖励。

---

## 二、推送方案 A（你给 PAT，我直接推）

如果你愿意提供 **GitHub Personal Access Token**（只需 `repo` 权限，推完可在 GitHub → Settings → Developer settings 吊销）：

```bash
# 1) 用 PAT 在 GitHub 创建公开仓库（脚本用 API 建）
curl -s -X POST https://api.github.com/user/repos \
  -H "Authorization: Bearer <你的PAT>" \
  -d '{"name":"mcd-bodywise","description":"麦当劳·身体情况定制营养推荐 Skill（基于官方 MCP）","public":true,"auto_init":false}'

# 2) 在本仓库目录关联远程并推送
git remote add origin https://github.com/if566/mcd-bodywise.git
git branch -M main
git push -u origin main
```

> 把 Token 发给小龙虾后，我可直接在上述步骤里补上远程地址并执行推送，你无需自己敲命令。

---

## 三、推送方案 B（你自己在本机推）

仓库已经 `git init` 并 `commit` 好，你只需：

```bash
cd mcd-bodywise-skill
git remote add origin https://github.com/if566/mcd-bodywise.git
git branch -M main
git push -u origin main
```

（若本机已配 SSH，可改用 `git@github.com:if566/mcd-bodywise.git`）

---

## 四、报名 Issue 文案（复制到官方活动仓库提交）

> 在 **M-China** 官方账号下的活动仓库按 Issue 模板提交；如官方模板字段不同，按以下要点对应填写即可。

```markdown
# [参赛] MCD Bodywise · 身体情况定制营养推荐 Skill

## 项目简介
MCD Bodywise 是一个根据「用户今日身体情况」推荐合适热量与营养餐品的 Skill。
它先用 Mifflin-St Jeor 公式估算基础代谢与每日消耗，再结合「今日运动量」与
「身体状态」（减脂 / 增肌 / 感冒 / 熬夜 / 生理期 / 大消耗）算出单餐热量与蛋白目标，
最后调用麦当劳官方 MCP 实时营养数据，筛出匹配目标的餐品组合，并可叠加实时价格与门店券。

## 作者 / GitHub
- 作者：if566
- 仓库：https://github.com/if566/mcd-bodywise

## 基于麦当劳官方 MCP 的能力
- list-nutrition-foods：拉取全部餐品营养成分（能量/蛋白/脂肪/碳水/钠/钙）
- query-nearby-stores / query-meals / calculate-price：实时门店、餐品与含优惠实付价
- query-store-coupons：门店可用券自动叠加，展示「无券价 → 用券价 → 再省 ¥X」

## 使用方式
python src/recommend.py --sex f --age 22 --height 165 --weight 55 \
    --activity moderate --state fat_loss --meal-count 3 --with-price

## 开发工具
本项目使用 WorkBuddy（Agent 模式）辅助开发，申请「用 WorkBuddy 开发」专项 +3000 积分。

## 参赛声明
- 代码以 MIT 协议开源，非商业用途。
- 营养数据版权归麦当劳中国所有；MCP Token 与下单能力由用户自行申请并承担风险。
- 遵守《麦当劳 MCP 服务规则》及《使用条款》，未将任何内容用于商业售卖或误导公众。
```

---

## 五、提交后
- 确认 Issue 已按模板提交，留存链接。
- 检查仓库 Public、README 渲染正常、`.gitignore` 未泄露 Token。
- 关注官方评审与积分发放通知。
