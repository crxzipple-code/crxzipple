# 昆航官网昆明飞北京航班查询日志

查询时间：2026-06-10  
查询目标：周五（2026-06-12）昆明飞北京  
官方入口：https://www.airkunming.com/

## 查询结论

昆航官网“航班动态”口径下，2026-06-12 昆明飞北京共查到 1 班：

| 航班号 | 出发 | 到达 | 计划起飞 | 计划到达 | 机型 | 状态 | 值机柜台 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| KY8269 | 昆明长水 KMG | 北京首都 PEK | 2026-06-12 08:20 | 2026-06-12 12:15 | 738 | 计划 | E03-E05 |

北京大兴（PKX）方向：官网航班动态返回空列表。

## 详细日志

1. 打开昆明航空官网 `https://www.airkunming.com/`。
   - 静态 HTML 只返回 React 单页应用壳：`You need to enable JavaScript to run this app.`
   - 页面引用前端包：`/static/js/main-fc816815.js`。

2. 解析官网前端包。
   - 发现官网 API base 为同域相对路径：`/search`、`/member`、`/order`、`/sso`。
   - 发现机票查询接口：`POST /search/flight`。
   - 发现航班动态按城市查询接口：`GET /search/flight/dynamic/city`。

3. 直接调用公开初始化接口。
   - `GET /search/token/time` 在纯静态请求下先返回风控 bootstrap 页。
   - `GET /search/city` 在纯静态请求下返回 `code=999`。
   - 结论：机票查询需要官网前端 JS 和风控脚本参与，不能用裸请求当作有效官网查询。

4. 使用浏览器环境打开官网机票页面：
   - URL：`https://www.airkunming.com/#/ticket/index/1/1`
   - 页面成功初始化，触发：
     - `GET /search/token/time`
     - `GET /search/token/mlogin`
     - `GET /search/city?type=0`
     - `GET /search/city?type=1`

5. 在官网表单中填写第一轮：昆明长水 -> 北京大兴。
   - 出发城市输入：`昆明`。
   - 官网候选选择：`昆明(昆明长水)`，机场码 `KMG`。
   - 到达城市输入：`北京`。
   - 官网候选选择：`北京大兴(北京大兴)`，机场码 `PKX`。
   - 日期控件选择：`2026-06-12`。
   - 点击：`立即查询`。
   - 官网前端发出：
     - `POST /search/flight`
     - 请求参数包含 `depAirportCode=KMG`、`arrAirportCode=PKX`、`depDate=2026-06-12`。
   - 返回 HTTP `418`，响应体为空；页面未渲染机票列表。

6. 在官网表单中填写第二轮：昆明长水 -> 北京首都。
   - 出发城市输入：`昆明`。
   - 官网候选选择：`昆明(昆明长水)`，机场码 `KMG`。
   - 到达城市输入：`北京`。
   - 官网候选选择：`北京首都(北京首都)`，机场码 `PEK`。
   - 日期控件选择：`2026-06-12`。
   - 点击：`立即查询`。
   - 官网前端发出：
     - `POST /search/flight`
     - 请求参数包含 `depAirportCode=KMG`、`arrAirportCode=PEK`、`depDate=2026-06-12`。
   - 返回 HTTP `418`，响应体为空；页面显示：`该日期暂无航班信息，请重新选择`。

7. 为避免把机票查询风控响应误判为无航班，改用官网公开的“航班动态”接口交叉确认。
   - 查询北京首都：
     - `GET /search/flight/dynamic/city?depCity=KMG&arrCity=PEK&flightDate=2026-06-12`
     - 返回 `code=200`，`message=操作成功`，`flights` 含 1 条。
   - 查询北京大兴：
     - `GET /search/flight/dynamic/city?depCity=KMG&arrCity=PKX&flightDate=2026-06-12`
     - 返回 `code=200`，`message=操作成功`，`flights=[]`。

## 原始官网返回摘要

北京首都（PEK）：

```json
{
  "flightNO": "KY8269",
  "flightDep": "昆明",
  "flightArr": "北京首都",
  "flightDepAirport": "昆明长水",
  "flightArrAirport": "北京首都",
  "flightDepcode": "KMG",
  "flightArrcode": "PEK",
  "flightDeptimePlanDate": "2026-06-12 08:20:00",
  "flightArrtimePlanDate": "2026-06-12 12:15:00",
  "acType": "738",
  "flightState": "计划",
  "checkInTable": "E03-E05",
  "ontimeRate": "90.00%"
}
```

北京大兴（PKX）：

```json
{
  "depCity": "KMG",
  "arrCity": "PKX",
  "flightDate2": "2026-06-12",
  "flights": []
}
```

## 注意

- 机票售卖列表接口 `/search/flight` 在自动化浏览器里返回 HTTP `418`，因此本记录不声称拿到了官网可售票价/舱位。
- 上表航班来自昆航官网“航班动态”接口，适合用于确认航班计划、机场、时间、状态和值机柜台。
