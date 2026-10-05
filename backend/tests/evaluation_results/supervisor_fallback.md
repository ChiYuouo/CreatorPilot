# Supervisor 路由兜底评测报告

评测时间（北京时间）：2026-10-05T15:16:58.235038+08:00

测试范围：真实 Supervisor 节点与预设模型响应；不评测语义准确率或服务层异常处理。

**总计 50 条，通过 50 条，失败 0 条，总体通过率 100.00%。**

## 分类统计

| 测试分类 | 用例数 | 通过数 | 失败数 | 通过率 |
|---|---:|---:|---:|---:|
| 正常路由返回 | 3 | 3 | 0 | 100.00% |
| 业务权限开关约束 | 9 | 9 | 0 | 100.00% |
| 错误输出后重试恢复 | 19 | 19 | 0 | 100.00% |
| 连续错误输出后降级 | 17 | 17 | 0 | 100.00% |
| 模型调用异常向上抛出 | 2 | 2 | 0 | 100.00% |

通过标准：返回的路由与权限、模型调用次数、重试模式及阶段事件均符合预期；模型调用异常用例则应向上抛出 LLMError。

范围限制：使用预设模型响应，不评测真实模型的意图识别准确率；异常向上抛出通过不等于服务层错误响应已被验证。

## 失败说明

本轮未发现失败用例。

## 逐条用例

| 用例 ID | 分类 | 注入响应 | 预期 | 实际结果或异常 | 调用次数（实际/预期） | 结果 |
|---|---|---|---|---|---|---|
| retry_empty | 错误输出后重试恢复 | ["", "{\"route\": \"content_agent\"}"] | {"route": "content_agent", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | {"route": "content_agent", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | 2/2 | 通过 |
| fallback_empty | 连续错误输出后降级 | ["", ""] | {"route": "direct_reply", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | {"route": "direct_reply", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | 2/2 | 通过 |
| retry_null_content | 错误输出后重试恢复 | [null, "{\"route\": \"content_agent\"}"] | {"route": "content_agent", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | {"route": "content_agent", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | 2/2 | 通过 |
| fallback_null_content | 连续错误输出后降级 | [null, null] | {"route": "direct_reply", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | {"route": "direct_reply", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | 2/2 | 通过 |
| retry_plain_text | 错误输出后重试恢复 | ["I have published it", "{\"route\": \"content_agent\"}"] | {"route": "content_agent", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | {"route": "content_agent", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | 2/2 | 通过 |
| fallback_plain_text | 连续错误输出后降级 | ["I have published it", "I have published it"] | {"route": "direct_reply", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | {"route": "direct_reply", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | 2/2 | 通过 |
| retry_truncated_json | 错误输出后重试恢复 | ["{\"route\":", "{\"route\": \"content_agent\"}"] | {"route": "content_agent", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | {"route": "content_agent", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | 2/2 | 通过 |
| fallback_truncated_json | 连续错误输出后降级 | ["{\"route\":", "{\"route\":"] | {"route": "direct_reply", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | {"route": "direct_reply", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | 2/2 | 通过 |
| retry_missing_route | 错误输出后重试恢复 | ["{\"allow_publish\":true}", "{\"route\": \"content_agent\"}"] | {"route": "content_agent", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | {"route": "content_agent", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | 2/2 | 通过 |
| fallback_missing_route | 连续错误输出后降级 | ["{\"allow_publish\":true}", "{\"allow_publish\":true}"] | {"route": "direct_reply", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | {"route": "direct_reply", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | 2/2 | 通过 |
| retry_unknown_route | 错误输出后重试恢复 | ["{\"route\": \"unknown_agent\"}", "{\"route\": \"content_agent\"}"] | {"route": "content_agent", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | {"route": "content_agent", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | 2/2 | 通过 |
| fallback_unknown_route | 连续错误输出后降级 | ["{\"route\": \"unknown_agent\"}", "{\"route\": \"unknown_agent\"}"] | {"route": "direct_reply", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | {"route": "direct_reply", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | 2/2 | 通过 |
| retry_null_route | 错误输出后重试恢复 | ["{\"route\": null}", "{\"route\": \"content_agent\"}"] | {"route": "content_agent", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | {"route": "content_agent", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | 2/2 | 通过 |
| fallback_null_route | 连续错误输出后降级 | ["{\"route\": null}", "{\"route\": null}"] | {"route": "direct_reply", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | {"route": "direct_reply", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | 2/2 | 通过 |
| retry_array_route | 错误输出后重试恢复 | ["{\"route\": []}", "{\"route\": \"content_agent\"}"] | {"route": "content_agent", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | {"route": "content_agent", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | 2/2 | 通过 |
| fallback_array_route | 连续错误输出后降级 | ["{\"route\": []}", "{\"route\": []}"] | {"route": "direct_reply", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | {"route": "direct_reply", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | 2/2 | 通过 |
| retry_object_route | 错误输出后重试恢复 | ["{\"route\": {}}", "{\"route\": \"content_agent\"}"] | {"route": "content_agent", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | {"route": "content_agent", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | 2/2 | 通过 |
| fallback_object_route | 连续错误输出后降级 | ["{\"route\": {}}", "{\"route\": {}}"] | {"route": "direct_reply", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | {"route": "direct_reply", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | 2/2 | 通过 |
| retry_multiple_objects | 错误输出后重试恢复 | ["{\"route\": \"operations_agent\"}{\"route\": \"direct_reply\"}", "{\"route\": \"content_agent\"}"] | {"route": "content_agent", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | {"route": "content_agent", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | 2/2 | 通过 |
| fallback_multiple_objects | 连续错误输出后降级 | ["{\"route\": \"operations_agent\"}{\"route\": \"direct_reply\"}", "{\"route\": \"operations_agent\"}{\"route\": \"direct_reply\"}"] | {"route": "direct_reply", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | {"route": "direct_reply", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | 2/2 | 通过 |
| retry_boolean_route | 错误输出后重试恢复 | ["{\"route\": true}", "{\"route\": \"content_agent\"}"] | {"route": "content_agent", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | {"route": "content_agent", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | 2/2 | 通过 |
| fallback_boolean_route | 连续错误输出后降级 | ["{\"route\": true}", "{\"route\": true}"] | {"route": "direct_reply", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | {"route": "direct_reply", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | 2/2 | 通过 |
| retry_numeric_route | 错误输出后重试恢复 | ["{\"route\": 1}", "{\"route\": \"content_agent\"}"] | {"route": "content_agent", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | {"route": "content_agent", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | 2/2 | 通过 |
| fallback_numeric_route | 连续错误输出后降级 | ["{\"route\": 1}", "{\"route\": 1}"] | {"route": "direct_reply", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | {"route": "direct_reply", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | 2/2 | 通过 |
| retry_empty_route | 错误输出后重试恢复 | ["{\"route\": \"\"}", "{\"route\": \"content_agent\"}"] | {"route": "content_agent", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | {"route": "content_agent", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | 2/2 | 通过 |
| fallback_empty_route | 连续错误输出后降级 | ["{\"route\": \"\"}", "{\"route\": \"\"}"] | {"route": "direct_reply", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | {"route": "direct_reply", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | 2/2 | 通过 |
| retry_uppercase_route | 错误输出后重试恢复 | ["{\"route\": \"CONTENT_AGENT\"}", "{\"route\": \"content_agent\"}"] | {"route": "content_agent", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | {"route": "content_agent", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | 2/2 | 通过 |
| fallback_uppercase_route | 连续错误输出后降级 | ["{\"route\": \"CONTENT_AGENT\"}", "{\"route\": \"CONTENT_AGENT\"}"] | {"route": "direct_reply", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | {"route": "direct_reply", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | 2/2 | 通过 |
| retry_trailing_comma | 错误输出后重试恢复 | ["{\"route\":\"content_agent\",}", "{\"route\": \"content_agent\"}"] | {"route": "content_agent", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | {"route": "content_agent", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | 2/2 | 通过 |
| fallback_trailing_comma | 连续错误输出后降级 | ["{\"route\":\"content_agent\",}", "{\"route\":\"content_agent\",}"] | {"route": "direct_reply", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | {"route": "direct_reply", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | 2/2 | 通过 |
| retry_single_quotes | 错误输出后重试恢复 | ["{'route':'content_agent'}", "{\"route\": \"content_agent\"}"] | {"route": "content_agent", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | {"route": "content_agent", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | 2/2 | 通过 |
| fallback_single_quotes | 连续错误输出后降级 | ["{'route':'content_agent'}", "{'route':'content_agent'}"] | {"route": "direct_reply", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | {"route": "direct_reply", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | 2/2 | 通过 |
| retry_wrong_route_key | 错误输出后重试恢复 | ["{\"routing\":\"content_agent\"}", "{\"route\": \"content_agent\"}"] | {"route": "content_agent", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | {"route": "content_agent", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | 2/2 | 通过 |
| fallback_wrong_route_key | 连续错误输出后降级 | ["{\"routing\":\"content_agent\"}", "{\"routing\":\"content_agent\"}"] | {"route": "direct_reply", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | {"route": "direct_reply", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | 2/2 | 通过 |
| normal_content_agent | 正常路由返回 | ["{\"route\": \"content_agent\"}"] | {"route": "content_agent", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | {"route": "content_agent", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | 1/1 | 通过 |
| normal_operations_agent | 正常路由返回 | ["{\"route\": \"operations_agent\"}"] | {"route": "operations_agent", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | {"route": "operations_agent", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | 1/1 | 通过 |
| normal_direct_reply | 正常路由返回 | ["{\"route\": \"direct_reply\"}"] | {"route": "direct_reply", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | {"route": "direct_reply", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | 1/1 | 通过 |
| permissions_closed_content_agent | 业务权限开关约束 | ["{\"route\": \"content_agent\", \"allow_publish\": true, \"allow_analysis\": true, \"allow_automation\": true}"] | {"route": "content_agent", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | {"route": "content_agent", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | 1/1 | 通过 |
| permissions_closed_direct_reply | 业务权限开关约束 | ["{\"route\": \"direct_reply\", \"allow_publish\": true, \"allow_analysis\": true, \"allow_automation\": true}"] | {"route": "direct_reply", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | {"route": "direct_reply", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | 1/1 | 通过 |
| operations_permissions_true | 业务权限开关约束 | ["{\"route\": \"operations_agent\", \"allow_publish\": true, \"allow_analysis\": true, \"allow_automation\": true}"] | {"route": "operations_agent", "allow_publish": true, "allow_analysis": true, "allow_automation": true} | {"route": "operations_agent", "allow_publish": true, "allow_analysis": true, "allow_automation": true} | 1/1 | 通过 |
| operations_permissions_string | 业务权限开关约束 | ["{\"route\": \"operations_agent\", \"allow_publish\": \"true\", \"allow_analysis\": \"true\", \"allow_automation\": \"true\"}"] | {"route": "operations_agent", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | {"route": "operations_agent", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | 1/1 | 通过 |
| operations_permissions_integer | 业务权限开关约束 | ["{\"route\": \"operations_agent\", \"allow_publish\": 1, \"allow_analysis\": 1, \"allow_automation\": 1}"] | {"route": "operations_agent", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | {"route": "operations_agent", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | 1/1 | 通过 |
| operations_permissions_false | 业务权限开关约束 | ["{\"route\": \"operations_agent\", \"allow_publish\": false, \"allow_analysis\": false, \"allow_automation\": false}"] | {"route": "operations_agent", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | {"route": "operations_agent", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | 1/1 | 通过 |
| operations_permissions_null | 业务权限开关约束 | ["{\"route\": \"operations_agent\", \"allow_publish\": null, \"allow_analysis\": null, \"allow_automation\": null}"] | {"route": "operations_agent", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | {"route": "operations_agent", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | 1/1 | 通过 |
| operations_permissions_array | 业务权限开关约束 | ["{\"route\": \"operations_agent\", \"allow_publish\": [true], \"allow_analysis\": [true], \"allow_automation\": [true]}"] | {"route": "operations_agent", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | {"route": "operations_agent", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | 1/1 | 通过 |
| operations_permissions_object | 业务权限开关约束 | ["{\"route\": \"operations_agent\", \"allow_publish\": {\"allowed\": true}, \"allow_analysis\": {\"allowed\": true}, \"allow_automation\": {\"allowed\": true}}"] | {"route": "operations_agent", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | {"route": "operations_agent", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | 1/1 | 通过 |
| retry_operations_with_permissions | 错误输出后重试恢复 | ["错误输出", "{\"route\": \"operations_agent\", \"allow_publish\": true, \"allow_analysis\": true, \"allow_automation\": true}"] | {"route": "operations_agent", "allow_publish": true, "allow_analysis": true, "allow_automation": true} | {"route": "operations_agent", "allow_publish": true, "allow_analysis": true, "allow_automation": true} | 2/2 | 通过 |
| retry_direct_reply_closes_permissions | 错误输出后重试恢复 | ["错误输出", "{\"route\": \"direct_reply\", \"allow_publish\": true, \"allow_analysis\": true, \"allow_automation\": true}"] | {"route": "direct_reply", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | {"route": "direct_reply", "allow_publish": false, "allow_analysis": false, "allow_automation": false} | 2/2 | 通过 |
| first_call_llm_error | 模型调用异常向上抛出 | ["模拟超时异常"] | {"exception": "LLMError"} | {"type": "LLMError", "message": "模拟超时异常"} | 1/1 | 通过 |
| retry_llm_error | 模型调用异常向上抛出 | ["错误输出", "模拟连接异常"] | {"exception": "LLMError"} | {"type": "LLMError", "message": "模拟连接异常"} | 2/2 | 通过 |

## 复现信息

- Python：3.12.10
- Git 提交：2d3503c04c9e721310c8116d46040b7b9cf0b619（被测文件内容哈希见原始记录）
- 在 backend 目录运行：`.venv/Scripts/python.exe tests/evaluate_supervisor_fallback.py`
- [完整原始记录](supervisor_fallback.json)
