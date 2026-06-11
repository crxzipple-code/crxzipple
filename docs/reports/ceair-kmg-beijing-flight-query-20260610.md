# 东航官网昆明飞北京航班查询日志

查询时间：2026-06-10  
查询目标：周五（2026-06-12）昆明飞北京  
官方入口：https://m.ceair.com/mflightdynamics/flight/index

## 查询结论

东航官网移动端“航班动态”口径下，2026-06-12 昆明飞北京城市口径（KMG -> BJS）共查到 9 班，全部到达北京大兴（PKX）：

| 航班号 | 承运 | 出发 | 到达 | 计划起飞 | 计划到达 | 机型 | 状态 | 经停 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| MU5701 | MU | 昆明长水 KMG | 北京大兴 PKX | 2026-06-12 08:00 | 2026-06-12 11:15 | 波音738(窄) | 未起飞 | - |
| MU5703 | MU | 昆明长水 KMG | 北京大兴 PKX | 2026-06-12 09:00 | 2026-06-12 12:40 | 波音737(窄) | 未起飞 | - |
| KN5502 | KN | 昆明长水 KMG | 北京大兴 PKX | 2026-06-12 11:55 | 2026-06-12 17:00 | 波音738(窄) | 未起飞 | 吕梁 |
| MU5705 | MU | 昆明长水 KMG | 北京大兴 PKX | 2026-06-12 12:00 | 2026-06-12 15:15 | 波音738(窄) | 未起飞 | - |
| KN5632 | KN | 昆明长水 KMG | 北京大兴 PKX | 2026-06-12 13:10 | 2026-06-12 16:30 | 波音738(窄) | 未起飞 | - |
| MU9707 | MU | 昆明长水 KMG | 北京大兴 PKX | 2026-06-12 13:15 | 2026-06-12 18:00 | 波音737(窄) | 未起飞 | 昭通 |
| MU5709 | MU | 昆明长水 KMG | 北京大兴 PKX | 2026-06-12 15:00 | 2026-06-12 18:15 | 波音738(窄) | 未起飞 | - |
| MU5707 | MU | 昆明长水 KMG | 北京大兴 PKX | 2026-06-12 15:55 | 2026-06-12 19:30 | 波音738(窄) | 未起飞 | - |
| MU5719 | MU | 昆明长水 KMG | 北京大兴 PKX | 2026-06-12 20:00 | 2026-06-12 23:25 | 波音738(窄) | 未起飞 | - |

北京首都（PEK）机场口径：官网航班动态返回“未查询到航班信息”。

## 详细日志

1. 打开东航官网移动端航班动态入口：
   - URL：`https://m.ceair.com/mflightdynamics/flight/index`
   - 静态 HTML 只返回 Vue 单页应用壳：`We're sorry but 中国东方航空 doesn't work properly without JavaScript enabled.`
   - 页面引用前端资源：`//ecresource.ceair.com/oss-m/mflightdynamics/...`

2. 使用浏览器环境加载官网页面。
   - 页面标题：`中国东方航空`。
   - 页面成功渲染“航班动态”表单，初始可见：
     - `按航班号`
     - `按起降地`
     - `2026/06/10今天`
     - `查询`
   - 页面初始化触发城市/机场基础数据接口：
     - `POST https://m.ceair.com/m-base/sale/getBasicData`
     - 请求参数包含 `methodName=getallcity_airport_tree`。

3. 解析官网前端路由和查询参数。
   - 起降地查询会进入 `flight/list` 路由。
   - 路由参数为 Base64 URL-safe 编码后的 JSON。
   - 列表页会调用：
     - `POST https://m.ceair.com/m-base/flightservice/flightstatus/flightDynamicsList`
   - 该接口请求体在页面运行时被加密为 `req` 字段；因此记录页面渲染结果和 Vue 运行态数据作为查询依据。

4. 构造官网前端自己的城市口径查询路由。
   - 查询对象：

```json
{
  "flightNo": "",
  "flightDate": "2026-06-12",
  "departure": "KMG",
  "arrival": "BJS",
  "cityCodeQueryFlag": true,
  "arrCityCodeFlag": true,
  "queryByType": "1",
  "queryByCityDep": "1",
  "queryByCityArr": "1",
  "flightFlag": "1"
}
```

   - 页面展示：`昆明北京`、`06-12 后天`。
   - 页面渲染出 9 条航班卡片，航班号为：
     - `MU5701`
     - `MU5703`
     - `KN5502`
     - `MU5705`
     - `KN5632`
     - `MU9707`
     - `MU5709`
     - `MU5707`
     - `MU5719`

5. 构造北京首都机场口径交叉查询。
   - 查询对象核心字段：

```json
{
  "flightDate": "2026-06-12",
  "departure": "KMG",
  "arrival": "PEK",
  "cityCodeQueryFlag": false,
  "arrCityCodeFlag": false,
  "queryByCityDep": "0",
  "queryByCityArr": "0"
}
```

   - 页面展示：`未查询到航班信息`。

6. 构造北京大兴机场口径交叉查询。
   - 查询对象核心字段：

```json
{
  "flightDate": "2026-06-12",
  "departure": "KMG",
  "arrival": "PKX",
  "cityCodeQueryFlag": false,
  "arrCityCodeFlag": false,
  "queryByCityDep": "0",
  "queryByCityArr": "0"
}
```

   - 页面展示结果与城市口径一致，共 9 班。

7. 抓取列表页 Vue 运行态数据。
   - 组件名：`list`。
   - 查询字段：
     - `flightDate=2026-06-12`
     - `departure=KMG`
     - `arrival=PKX`
     - `salesChannel=7701`
     - `os=M`
     - `language=zh`
   - 数据数组字段：`fightData`。

## 原始官网字段摘要

以下字段来自东航官网列表页 Vue 运行态 `fightData`，保留与结论表相关的字段：

```json
[
  {
    "carrier": "MU",
    "flightNo": "5701",
    "flightDate": "2026-06-12",
    "deptAirport": "KMG",
    "arrAirport": "PKX",
    "deptAirportDisp": "昆明长水",
    "arrAirportDisp": "北京大兴",
    "planDeptTimeLoc": "06-12 08:00",
    "planArrTimeLoc": "06-12 11:15",
    "acType": "波音738(窄)",
    "statusCode": "未起飞"
  },
  {
    "carrier": "MU",
    "flightNo": "5703",
    "flightDate": "2026-06-12",
    "deptAirport": "KMG",
    "arrAirport": "PKX",
    "planDeptTimeLoc": "06-12 09:00",
    "planArrTimeLoc": "06-12 12:40",
    "acType": "波音737(窄)",
    "statusCode": "未起飞"
  },
  {
    "carrier": "KN",
    "flightNo": "5502",
    "flightDate": "2026-06-12",
    "deptAirport": "KMG",
    "arrAirport": "PKX",
    "lineEng": "KMG-LLV-PKX",
    "planDeptTimeLoc": "06-12 11:55",
    "planArrTimeLoc": "06-12 17:00",
    "acType": "波音738(窄)",
    "stoppingAirportDisp": ["经停吕梁"],
    "statusCode": "未起飞"
  },
  {
    "carrier": "MU",
    "flightNo": "9707",
    "flightDate": "2026-06-12",
    "deptAirport": "KMG",
    "arrAirport": "PKX",
    "lineEng": "KMG-ZAT-PKX",
    "planDeptTimeLoc": "06-12 13:15",
    "planArrTimeLoc": "06-12 18:00",
    "acType": "波音737(窄)",
    "stoppingAirportDisp": ["经停昭通"],
    "statusCode": "未起飞"
  }
]
```

完整结果中其余航班字段与结论表一致，且 `dept_TERMINAL`、`arr_TERMINAL` 均为空字符串。

## 注意

- 本记录是东航官网“航班动态”口径，不是机票售卖库存/票价口径。
- 东航页面接口请求体使用运行时加密字段 `req`，裸请求不可作为有效查询替代；本次以官网页面渲染结果和页面运行态数据为准。
- 官网列表中包含 `MU` 航班和 `KN` 航班；报告按东航官网展示结果原样记录，不额外判断是否由东航实际承运。
