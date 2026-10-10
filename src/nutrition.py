#!/usr/bin/env python3
"""麦当劳 MCP 客户端 + 营养数据解析 + 个性化餐品推荐。

数据源：麦当劳官方 MCP 工具 `list-nutrition-foods`（无需门店上下文，直接返回
全部餐品的营养成分）。本模块负责：
  1. 通过 Streamable HTTP (JSON-RPC) 调用麦当劳 MCP；
  2. 解析其特有的 "[n]{fields}:\\n csv" 文本结构；
  3. 结合 body_profile 给出的营养目标，做单品推荐与「主餐+饮品」组合推荐。

Token 读取优先级：环境变量 MCD_MCP_TOKEN > ~/.config/mcd/mcp_token。
绝不在日志/输出中回显 Token。
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import List, Optional

import requests

MCD_MCP_URL = "https://mcp.mcd.cn/mcp-servers/mcd-mcp"
NUTRITION_FIELDS = [
    "productName", "nutritionDescription", "energyKj", "energyKcal",
    "protein", "fat", "carbohydrate", "sodium", "calcium",
]
NUMERIC_FIELDS = {"energyKj", "energyKcal", "protein", "fat", "carbohydrate", "sodium", "calcium"}

# 饮品类关键词（用于把饮品从主餐/小食里分出来）
DRINK_KEYWORDS = [
    "可乐", "雪碧", "咖啡", "红茶", "牛奶", "果汁", "纯悦", "豆浆",
    "雪冰", "麦旋酷", "柠檬", "阳光", "鲜萃", "浓缩", "热朱古力", "热牛奶",
    "苹果汁", "美汁源", "美式",
]
# 甜品/小食（不作为主餐，也不作为主要饮品）
DESSERT_KEYWORDS = ["新地", "派", "麦旋风", "奶冻", "爆珠", "拉明顿", "雪冰"]


# ---------------------------------------------------------------------------
# MCP 客户端
# ---------------------------------------------------------------------------
class McdMcpClient:
    def __init__(self, token: Optional[str] = None, url: str = MCD_MCP_URL):
        self.token = token or os.environ.get("MCD_MCP_TOKEN")
        if not self.token:
            p = os.path.expanduser("~/.config/mcd/mcp_token")
            if os.path.exists(p):
                self.token = open(p).read().strip()
        if not self.token:
            raise RuntimeError(
                "未找到 MCP Token：请设置环境变量 MCD_MCP_TOKEN 或写入 ~/.config/mcd/mcp_token"
            )
        self.url = url
        self.session: Optional[str] = None

    def _headers(self) -> dict:
        h = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {self.token}",
        }
        if self.session:
            h["Mcp-Session-Id"] = self.session
        return h

    @staticmethod
    def _parse_response(r: requests.Response):
        ct = r.headers.get("Content-Type", "")
        if "text/event-stream" in ct:
            out = None
            for line in r.text.splitlines():
                line = line.strip()
                if line.startswith("data:"):
                    try:
                        out = json.loads(line[5:].strip())
                    except Exception:
                        pass
            return out
        try:
            return r.json()
        except Exception:
            return {}

    def _rpc(self, method: str, params=None, _id: int = 1, notify: bool = False):
        body = {"jsonrpc": "2.0", "method": method}
        if not notify:
            body["id"] = _id
        if params is not None:
            body["params"] = params
        r = requests.post(self.url, headers=self._headers(), json=body, timeout=30)
        sid = r.headers.get("Mcp-Session-Id") or r.headers.get("mcp-session-id")
        if sid:
            self.session = sid
        return self._parse_response(r)

    def connect(self) -> dict:
        self._rpc("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "mcd-bodywise", "version": "0.1"},
        })
        self._rpc("notifications/initialized", notify=True)
        return {"status": "connected"}

    def call_tool(self, name: str, arguments: Optional[dict] = None) -> dict:
        return self._rpc("tools/call", {"name": name, "arguments": arguments or {}}, _id=2)

    def fetch_nutrition_items(self) -> List[dict]:
        """调用 list-nutrition-foods 并解析为餐品列表。"""
        res = self.call_tool("list-nutrition-foods", {})
        result = res.get("result", res) if isinstance(res, dict) else {}
        data_str = None
        sc = result.get("structuredContent")
        if isinstance(sc, dict) and "data" in sc:
            data_str = sc.get("data")
        if not data_str:
            content = result.get("content")
            if isinstance(content, list):
                for c in content:
                    if isinstance(c, dict) and c.get("type") == "text":
                        m = re.search(r'"data"\s*:\s*"(.*?)"\s*}', c.get("text", ""), re.S)
                        if m:
                            data_str = m.group(1).encode().decode("unicode_escape")
                        break
        return parse_nutrition_data(data_str) if data_str else []


# ---------------------------------------------------------------------------
# 数据解析
# ---------------------------------------------------------------------------
def parse_nutrition_data(data_str: str) -> List[dict]:
    """解析麦当劳 MCP 返回的营养文本。

    格式示例:
        [160]{productName,nutritionDescription,energyKj,energyKcal,protein,fat,carbohydrate,sodium,calcium}:
          猪柳麦满分,null,1288,308,16,16,24,781,213
    """
    if not data_str:
        return []
    lines = data_str.strip().split("\n")
    fields = None
    start = 0
    for i, line in enumerate(lines):
        m = re.search(r"\{([^}]+)\}", line)
        if m:
            fields = [f.strip() for f in m.group(1).split(",")]
            start = i + 1
            break
    if not fields:
        fields = NUTRITION_FIELDS

    items: List[dict] = []
    for line in lines[start:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split(",")
        if len(parts) < len(fields):
            continue
        vals = parts[: len(fields)]
        rec: dict = {}
        for idx, f in enumerate(fields):
            v = vals[idx].strip()
            if v == "null" or v == "":
                v = None
            elif f in NUMERIC_FIELDS:
                try:
                    v = float(v)
                except Exception:
                    pass
            rec[f] = v
        if rec.get("productName"):
            items.append(rec)
    return items


# ---------------------------------------------------------------------------
# 分类与推荐
# ---------------------------------------------------------------------------
def _classify(items: List[dict]):
    mains, drinks, sides = [], [], []
    for it in items:
        name = (it.get("productName") or "")
        kcal = it.get("energyKcal") or 0
        is_drink = any(k in name for k in DRINK_KEYWORDS)
        is_dessert = any(k in name for k in DESSERT_KEYWORDS)
        if is_drink and not is_dessert:
            drinks.append(it)
        elif is_dessert:
            sides.append(it)
        elif kcal >= 200:
            mains.append(it)
        else:
            sides.append(it)
    return mains, drinks, sides


def _combo_score(totals: dict, target: dict, side_is_cold: bool = False) -> float:
    k = totals["energyKcal"]
    p = totals["protein"]
    s = totals["sodium"]
    mid = (target["calorie_floor"] + target["calorie_cap"]) / 2 or 1
    kcal_dev = abs(k - mid) / mid
    protein_ok = 1.0 if p >= target["protein_min"] else max(0.0, p / max(1, target["protein_min"]))
    sodium_pen = max(0.0, s - target["sodium_warn"]) / max(1, target["sodium_warn"])
    cold_pen = 1.5 if (target.get("avoid_cold") and side_is_cold) else 0.0
    return kcal_dev * 1.0 + sodium_pen * 0.8 + (1 - protein_ok) * 2.0 + cold_pen


def build_recommendations(target: dict, items: List[dict],
                          prefer_names: Optional[set] = None) -> dict:
    """根据 NutritionTarget.to_constraints() 的结果生成推荐。

    target 字段: calorie_cap, calorie_floor, protein_min, fat_cap,
                 prefer_tags, sodium_warn
    """
    mains, drinks, sides = _classify(items)

    # ---- 单品推荐：热量不超、蛋白达标、蛋白密度优先 ----
    single = []
    for it in items:
        kcal = it.get("energyKcal") or 0
        pro = it.get("protein") or 0
        fat = it.get("fat") or 0
        if kcal <= target["calorie_cap"] and pro >= target["protein_min"] and fat <= target["fat_cap"]:
            density = pro / kcal if kcal else 0
            single.append((density, it))
    single.sort(key=lambda x: -x[0])
    single_top = [it for _, it in single[:5]]

    # ---- 组合推荐：主餐 + (饮品/小食)，总热量落在目标区间，去重 + 补位 ----
    lo, hi = target["calorie_floor"] * 0.85, target["calorie_cap"] * 1.05

    def _gen(main_list, side_list, side_label):
        out = []
        seen = set()
        for m in main_list:
            mk = m.get("energyKcal") or 0
            mp = m.get("protein") or 0
            mf = m.get("fat") or 0
            ms = m.get("sodium") or 0
            for s in side_list:
                sk = s.get("energyKcal") or 0
                sp = s.get("protein") or 0
                sf = s.get("fat") or 0
                ss = s.get("sodium") or 0
                tk = mk + sk
                tp = mp + sp
                tf = mf + sf
                ts = ms + ss
                if lo <= tk <= hi and tp >= target["protein_min"] * 0.9 and tf <= target["fat_cap"] * 1.2:
                    key = (m.get("productName"), s.get("productName"))
                    if key in seen:
                        continue
                    seen.add(key)
                    totals = {"energyKcal": tk, "protein": tp, "fat": tf, "sodium": ts}
                    side_is_cold = "冰" in (s.get("productName") or "")
                    score = _combo_score(totals, target, side_is_cold)
                    if prefer_names:
                        # 与 match_meal_code 一致：去除温度字，处理 冰美式/热美式 等
                        mn = normalize_name(m.get("productName") or "").replace("冰", "").replace("热", "")
                        sn = normalize_name(s.get("productName") or "").replace("冰", "").replace("热", "")
                        if mn in prefer_names or sn in prefer_names:
                            score -= 0.12  # 轻微优先：该门店有可用券可叠加
                    out.append({"main": m, "side": s, "side_label": side_label,
                                "totals": totals, "score": score})
        out.sort(key=lambda x: x["score"])
        return out

    def _pick_diverse(scored, n=3):
        """贪心挑选：优先主餐各异，不足再补任意。"""
        picked, seen = [], set()
        for c in scored:
            if len(picked) >= n:
                break
            m = c["main"].get("productName")
            if m not in seen:
                picked.append(c)
                seen.add(m)
        if len(picked) < n:
            for c in scored:
                if len(picked) >= n:
                    break
                if c not in picked:
                    picked.append(c)
        return picked

    combos = _pick_diverse(_gen(mains, drinks, "饮品"), 3)
    # 不足 3 套时用 主餐+小食 补位（主餐不重复）
    if len(combos) < 3:
        existing = {c["main"].get("productName") for c in combos}
        for c in _pick_diverse(_gen(mains, sides, "小食"), 3):
            if len(combos) >= 3:
                break
            if c["main"].get("productName") in existing:
                continue
            existing.add(c["main"].get("productName"))
            combos.append(c)

    return {
        "target": target,
        "counts": {"mains": len(mains), "drinks": len(drinks), "sides": len(sides), "total": len(items)},
        "single_top": single_top,
        "combos": combos,
    }


# ---------------------------------------------------------------------------
# 价格 / 门店（需门店上下文，调用 query-meals / calculate-price）
# ---------------------------------------------------------------------------
MEAL_COMBO_KW = ["套餐", "三件套", "随心配", "四件套", "双拼", "双全", "分享餐",
                "双人", "乐园餐", "周边", "按摩", "棒球帽", "百宝袋", "如意", "精选", "任选"]

def normalize_name(s: str) -> str:
    """规范化餐品名：统一括号、去空格/品牌前缀/规格词，便于跨源匹配。"""
    s = (s or "").replace("（", "(").replace("）", ")").replace(" ", "")
    for w in ["小杯", "中杯", "大杯", "迷你", "5块", "盒装", "(盒装)", "超值",
              "麦咖啡", "™", "®", "(", ")"]:
        s = s.replace(w, "")
    return s.strip()


def fetch_meals(client, store_code: str, order_type: int = 1, be_type: int = 1) -> dict:
    """调用 query-meals，返回 {productCode: {'name': str, 'price': float}}。"""
    res = client.call_tool("query-meals", {
        "storeCode": store_code, "orderType": order_type, "beType": be_type,
    })
    result = (res.get("result", res) if isinstance(res, dict) else {})
    sc = result.get("structuredContent") if isinstance(result, dict) else None
    out = {}
    if isinstance(sc, dict):
        meals = sc.get("data", {}).get("meals", {})
        if isinstance(meals, dict):
            for code, info in meals.items():
                if isinstance(info, dict):
                    price = 0.0
                    try:
                        price = float(info.get("currentPrice") or 0)
                    except Exception:
                        pass
                    out[code] = {"name": info.get("name", ""), "price": price}
    return out


def find_store(client, city: str, area: str, be_type: int = 1) -> Optional[str]:
    """按城市+区域搜索到店自取门店，返回第一个 storeCode。"""
    res = client.call_tool("query-nearby-stores", {
        "beType": be_type, "searchType": 2, "city": city, "keyword": area,
    })
    result = (res.get("result", res) if isinstance(res, dict) else {})
    sc = result.get("structuredContent") if isinstance(result, dict) else None
    if isinstance(sc, dict):
        data = sc.get("data")
        if isinstance(data, list) and data:
            return data[0].get("storeCode")
    return None


def match_meal_code(nutri_name: str, meals: dict) -> Optional[str]:
    """把营养成分里的餐品名匹配到 query-meals 的 productCode。
    优先非套餐、名称最贴近者；对咖啡/美式等温度杯型无关名称做宽松匹配。"""
    n = normalize_name(nutri_name)
    if not n:
        return None
    n_t = n.replace("冰", "").replace("热", "")  # 去温度，处理「冰美式/热美式」等
    cands = []
    for code, info in meals.items():
        raw = info.get("name", "")
        m = normalize_name(raw)
        m_t = m.replace("冰", "").replace("热", "")
        is_combo = any(k in raw for k in MEAL_COMBO_KW)
        # 精确/包含 或 去温度后相等（如 冰美式中杯 ↔ 麦咖啡™美式）
        temp_match = (n_t == m_t and n_t != "" and n_t != n)
        if n == m or n in m or m in n or temp_match:
            cands.append((code, raw, is_combo, temp_match))
    if not cands:
        return None
    # 非套餐优先；精确匹配优先于温度宽松匹配；同档取名称长度更接近者
    cands.sort(key=lambda x: (x[2], not x[3], abs(len(x[1]) - len(nutri_name))))
    return cands[0][0]


def calculate_price(client, store_code: str, codes, be_type: int = 1,
                    order_type: int = 1, coupon_map: Optional[dict] = None) -> Optional[dict]:
    """调用 calculate-price，返回 {price, original_price, discount, product_list}（元）。

    coupon_map: {productCode: {"couponCode":..., "couponId":...}}。
    注意：麦当劳 MCP 必须同时传 couponCode + couponId 才能正确应用券，
    只传其一会返回全 0 的异常结果。
    """
    items = []
    for c in codes:
        it = {"productCode": str(c), "quantity": 1}
        cm = coupon_map.get(str(c)) if coupon_map else None
        if cm:
            it["couponCode"] = cm.get("couponCode")
            it["couponId"] = cm.get("couponId")
        items.append(it)
    res = client.call_tool("calculate-price", {
        "storeCode": store_code, "orderType": order_type, "beType": be_type,
        "items": items, "needTableware": False,
    })
    result = (res.get("result", res) if isinstance(res, dict) else {})
    sc = result.get("structuredContent") if isinstance(result, dict) else None
    if not isinstance(sc, dict) or "data" not in sc:
        return None
    d = sc["data"]
    if (d.get("price") in (0, None)) and d.get("originalPrice") in (0, None):
        # 异常（如券参数不全），视为算价失败
        return None
    fen = lambda k: (d.get(k, 0) or 0) / 100.0
    return {
        "price": fen("price"),
        "original_price": fen("originalPrice"),
        "discount": fen("discount"),
        "product_list": d.get("productList", []),
        "store_code": store_code,
    }


def fetch_store_coupons(client, store_code: str, be_type: int = 1,
                        order_type: int = 1) -> List[dict]:
    """调用 query-store-coupons，返回门店可用券列表。

    每项: {couponId, couponCode, title, product_codes:set(str)}。
    product_codes 是该券适用的商品 code 集合，用于挂券算价。
    """
    res = client.call_tool("query-store-coupons", {
        "storeCode": store_code, "beType": be_type, "orderType": order_type,
    })
    result = (res.get("result", res) if isinstance(res, dict) else {})
    sc = result.get("structuredContent") if isinstance(result, dict) else None
    out = []
    if not isinstance(sc, dict):
        return out
    data = sc.get("data")
    coupons = data if isinstance(data, list) else (data.get("list") or data.get("coupons") or [])
    for cp in coupons:
        if not isinstance(cp, dict):
            continue
        prods = set()
        for p in (cp.get("products") or []):
            if isinstance(p, dict) and p.get("productCode"):
                prods.add(str(p["productCode"]))
        out.append({
            "couponId": cp.get("couponId"),
            "couponCode": cp.get("couponCode"),
            "title": cp.get("title"),
            "product_codes": prods,
        })
    return out


def build_coupon_map(coupons: List[dict]) -> dict:
    """将门店券列表转为 {productCode: {couponCode, couponId, title}}。
    一个商品若命中多张券，取第一张（可在调用处按优惠力度择优）。"""
    m = {}
    for cp in coupons:
        for pcode in cp.get("product_codes", set()):
            if pcode not in m:
                m[pcode] = {
                    "couponCode": cp.get("couponCode"),
                    "couponId": cp.get("couponId"),
                    "title": cp.get("title"),
                }
    return m


if __name__ == "__main__":
    client = McdMcpClient()
    client.connect()
    items = client.fetch_nutrition_items()
    print(f"拉取餐品数: {len(items)}")
    print("示例:", json.dumps(items[0], ensure_ascii=False))
    # 用演示目标跑一遍推荐
    demo_target = {
        "calorie_cap": 596, "calorie_floor": 487,
        "protein_min": 31, "fat_cap": 17,
        "prefer_tags": ["高蛋白", "控热量"], "sodium_warn": 1800,
    }
    rec = build_recommendations(demo_target, items)
    print("组合推荐数:", len(rec["combos"]))
    for c in rec["combos"]:
        print(f"  {c['main']['productName']} + {c['side']['productName']}（{c.get('side_label')}）"
              f" => {c['totals']['energyKcal']:.0f}kcal / 蛋白{c['totals']['protein']:.0f}g / 钠{c['totals']['sodium']:.0f}mg")
