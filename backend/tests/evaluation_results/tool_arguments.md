# 工具参数校验评测报告

评测时间（北京时间）：2026-10-05T15:15:20.455569+08:00

测试范围：发布工具参数校验；使用记录调用的模拟业务接口；不调用模型或执行真实业务。

**总计 50 条，通过 50 条，失败 0 条，总体通过率 100.00%。**

## 分类统计

| 测试分类 | 用例数 | 通过数 | 失败数 | 通过率 |
|---|---:|---:|---:|---:|
| 非法参数执行前拦截 | 40 | 40 | 0 | 100.00% |
| 合法参数通过并调用模拟接口 | 10 | 10 | 0 | 100.00% |

通过标准：非法参数必须返回失败且业务接口调用次数为 0；合法参数必须返回成功且调用次数为 1。

## 工具覆盖统计

| 工具 | 用例数 | 通过数 | 失败数 | 通过率 |
|---|---:|---:|---:|---:|
| 查询素材详情 | 9 | 9 | 0 | 100.00% |
| 查询发布状态 | 5 | 5 | 0 | 100.00% |
| 查询账号 | 4 | 4 | 0 | 100.00% |
| 查询素材列表 | 14 | 14 | 0 | 100.00% |
| 查询平台 | 2 | 2 | 0 | 100.00% |
| 查询发布任务 | 2 | 2 | 0 | 100.00% |
| 提交发布 | 14 | 14 | 0 | 100.00% |

范围限制：模拟业务接口只记录调用，不验证数据库、账号归属、平台发布或真实业务执行成功率。

## 失败说明

本轮未发现失败用例。

## 逐条用例

| 用例 ID | 工具 | 参数 | 预期 | 实际成功标记 | 业务调用次数 | 结果 |
|---|---|---|---|---|---:|---|
| missing_asset_id | 查询素材详情 | {} | 执行前拦截 | 失败 | 0 | 通过 |
| zero_asset_id | 查询素材详情 | {"asset_id": 0} | 执行前拦截 | 失败 | 0 | 通过 |
| negative_asset_id | 查询素材详情 | {"asset_id": -1} | 执行前拦截 | 失败 | 0 | 通过 |
| string_asset_id | 查询素材详情 | {"asset_id": "1"} | 执行前拦截 | 失败 | 0 | 通过 |
| boolean_asset_id | 查询素材详情 | {"asset_id": true} | 执行前拦截 | 失败 | 0 | 通过 |
| null_asset_id | 查询素材详情 | {"asset_id": null} | 执行前拦截 | 失败 | 0 | 通过 |
| injected_user_id | 查询素材详情 | {"asset_id": 1, "user_id": 2} | 执行前拦截 | 失败 | 0 | 通过 |
| negative_offset | 查询素材列表 | {"offset": -1} | 执行前拦截 | 失败 | 0 | 通过 |
| zero_limit | 查询素材列表 | {"limit": 0} | 执行前拦截 | 失败 | 0 | 通过 |
| excessive_limit | 查询素材列表 | {"limit": 51} | 执行前拦截 | 失败 | 0 | 通过 |
| string_limit | 查询素材列表 | {"limit": "20"} | 执行前拦截 | 失败 | 0 | 通过 |
| unsupported_media_type | 查询素材列表 | {"media_type": "audio"} | 执行前拦截 | 失败 | 0 | 通过 |
| long_search | 查询素材列表 | {"search": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"} | 执行前拦截 | 失败 | 0 | 通过 |
| array_arguments | 查询素材列表 | [] | 执行前拦截 | 失败 | 0 | 通过 |
| malformed_json | 查询素材列表 | { | 执行前拦截 | 失败 | 0 | 通过 |
| missing_job_id | 查询发布状态 | {} | 执行前拦截 | 失败 | 0 | 通过 |
| zero_job_id | 查询发布状态 | {"job_id": 0} | 执行前拦截 | 失败 | 0 | 通过 |
| fractional_job_id | 查询发布状态 | {"job_id": 1.5} | 执行前拦截 | 失败 | 0 | 通过 |
| injected_path | 查询发布状态 | {"job_id": 1, "path": "/tmp/file"} | 执行前拦截 | 失败 | 0 | 通过 |
| boolean_jobs_limit | 查询发布任务 | {"limit": true} | 执行前拦截 | 失败 | 0 | 通过 |
| valid_asset | 查询素材详情 | {"asset_id": 1} | 允许执行 | 成功 | 1 | 通过 |
| default_asset_list | 查询素材列表 | {} | 允许执行 | 成功 | 1 | 通过 |
| asset_list_boundaries | 查询素材列表 | {"offset": 0, "limit": 50, "media_type": "image", "search": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"} | 允许执行 | 成功 | 1 | 通过 |
| valid_job_status | 查询发布状态 | {"job_id": 1} | 允许执行 | 成功 | 1 | 通过 |
| valid_jobs_limit | 查询发布任务 | {"limit": 1} | 允许执行 | 成功 | 1 | 通过 |
| long_account_platform | 查询账号 | {"platform": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"} | 执行前拦截 | 失败 | 0 | 通过 |
| numeric_account_platform | 查询账号 | {"platform": 123} | 执行前拦截 | 失败 | 0 | 通过 |
| extra_platform_argument | 查询平台 | {"user_id": 2} | 执行前拦截 | 失败 | 0 | 通过 |
| scalar_arguments | 查询素材列表 | 42 | 执行前拦截 | 失败 | 0 | 通过 |
| null_arguments | 查询素材列表 | null | 执行前拦截 | 失败 | 0 | 通过 |
| fractional_asset_id | 查询素材详情 | {"asset_id": 1.5} | 执行前拦截 | 失败 | 0 | 通过 |
| string_offset | 查询素材列表 | {"offset": "0"} | 执行前拦截 | 失败 | 0 | 通过 |
| boolean_offset | 查询素材列表 | {"offset": false} | 执行前拦截 | 失败 | 0 | 通过 |
| publish_missing_accounts | 提交发布 | {"asset_id": 1, "title": "test"} | 执行前拦截 | 失败 | 0 | 通过 |
| publish_empty_accounts | 提交发布 | {"account_ids": [], "asset_id": 1, "title": "test"} | 执行前拦截 | 失败 | 0 | 通过 |
| publish_excessive_accounts | 提交发布 | {"account_ids": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31], "asset_id": 1, "title": "test"} | 执行前拦截 | 失败 | 0 | 通过 |
| publish_zero_account | 提交发布 | {"account_ids": [0], "asset_id": 1, "title": "test"} | 执行前拦截 | 失败 | 0 | 通过 |
| publish_boolean_account | 提交发布 | {"account_ids": [true], "asset_id": 1, "title": "test"} | 执行前拦截 | 失败 | 0 | 通过 |
| publish_missing_asset | 提交发布 | {"account_ids": [1], "title": "test"} | 执行前拦截 | 失败 | 0 | 通过 |
| publish_missing_title | 提交发布 | {"account_ids": [1], "asset_id": 1} | 执行前拦截 | 失败 | 0 | 通过 |
| publish_empty_title | 提交发布 | {"account_ids": [1], "asset_id": 1, "title": ""} | 执行前拦截 | 失败 | 0 | 通过 |
| publish_long_title | 提交发布 | {"account_ids": [1], "asset_id": 1, "title": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx…（完整内容见原始记录） | 执行前拦截 | 失败 | 0 | 通过 |
| publish_excessive_images | 提交发布 | {"account_ids": [1], "asset_id": 1, "title": "test", "image_asset_ids": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]} | 执行前拦截 | 失败 | 0 | 通过 |
| publish_excessive_tags | 提交发布 | {"account_ids": [1], "asset_id": 1, "title": "test", "tags": ["tag", "tag", "tag", "tag", "tag", "tag", "tag", "tag", "tag", "tag", "tag", "tag", "tag", "tag", "tag", "tag", "tag",…（完整内容见原始记录） | 执行前拦截 | 失败 | 0 | 通过 |
| publish_invalid_datetime | 提交发布 | {"account_ids": [1], "asset_id": 1, "title": "test", "scheduled_at": "invalid-date"} | 执行前拦截 | 失败 | 0 | 通过 |
| default_accounts | 查询账号 | {} | 允许执行 | 成功 | 1 | 通过 |
| account_platform_boundary | 查询账号 | {"platform": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"} | 允许执行 | 成功 | 1 | 通过 |
| valid_platform_list | 查询平台 | {} | 允许执行 | 成功 | 1 | 通过 |
| valid_publish_minimum | 提交发布 | {"account_ids": [1], "asset_id": 1, "title": "x"} | 允许执行 | 成功 | 1 | 通过 |
| valid_publish_boundaries | 提交发布 | {"account_ids": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30], "asset_id": 1, "title": "xxxxxxxxxxxxxxxxxxxxxxxxxx…（完整内容见原始记录） | 允许执行 | 成功 | 1 | 通过 |

## 复现信息

- Python：3.12.10
- Git 提交：2d3503c04c9e721310c8116d46040b7b9cf0b619（被测文件内容哈希见原始记录）
- 在 backend 目录运行：`.venv/Scripts/python.exe tests/evaluate_tool_arguments.py`
- [完整原始记录](tool_arguments.json)
