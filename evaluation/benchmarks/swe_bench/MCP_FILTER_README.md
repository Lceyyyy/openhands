# SWE-Bench MCP过滤功能使用说明

## 功能概述

本功能用于在SWE-Bench评估过程中，自动屏蔽当前任务对应的GitHub issue，防止agent通过搜索获取到原始issue信息，确保评估的公平性和准确性。

## 工作原理

1. **任务识别**: 在处理每个SWE-Bench任务时，系统会解析`instance_id`（格式：`{org}__{repo}-{number}`）来获取对应的GitHub仓库和issue编号
2. **自动过滤**: 当agent使用MCP工具搜索GitHub issues时，系统会自动过滤掉与当前任务匹配的issue
3. **精确匹配**: 只屏蔽完全匹配的issue（相同的仓库和issue编号），不影响其他相关issue的搜索

## 修改的文件

### 1. `openhands/mcp/utils.py`
- 添加了全局变量来存储当前SWE-Bench任务信息
- 实现了`set_current_swe_bench_task()`函数来设置当前任务
- 实现了`get_current_swe_bench_task()`函数来获取当前任务信息
- 实现了`should_block_swe_bench_issue()`函数来检查是否应该屏蔽特定issue
- 修改了`filter_swe_bench_issues()`函数来过滤当前任务对应的issue
- 修改了`call_search_issues_with_filter()`函数来处理过滤逻辑

### 2. `evaluation/benchmarks/swe_bench/run_infer.py`
- 在`process_instance()`函数中添加了设置当前任务的代码

### 3. `evaluation/benchmarks/swe_bench/scripts/run_infer.sh`
- 添加了环境变量设置来启用过滤功能

## 使用方法

### 1. 启用过滤功能
在运行SWE-Bench评估时，设置环境变量：
```bash
export SWE_BENCH_MCP_FILTER=true
export SWE_BENCH_EVAL_MODE=true
```

### 2. 运行评估
使用现有的评估脚本，过滤功能会自动生效：
```bash
./evaluation/benchmarks/swe_bench/scripts/run_infer.sh <model_config> <commit_hash> <agent> <eval_limit> <max_iter> <num_workers> <dataset> <split> <n_runs> <mode>
```

## 功能特性

### 1. 精确过滤
- 只屏蔽与当前任务完全匹配的GitHub issue
- 不影响其他相关issue的搜索和获取
- 支持所有SWE-Bench数据集（SWE-bench、SWE-Gym、SWT-bench等）

### 2. 自动识别
- 自动解析SWE-Bench的instance_id格式
- 无需手动配置每个任务的过滤规则
- 支持各种格式的instance_id

### 3. 日志记录
- 详细记录过滤操作
- 显示被屏蔽的issue信息
- 便于调试和监控

### 4. 错误处理
- 优雅处理无效的instance_id格式
- 不影响正常的MCP工具功能
- 提供详细的错误信息

## 示例

### 任务设置
```python
# 设置当前任务
set_current_swe_bench_task("django__django-11099")
# 解析结果: repo="django/django", issue_number=11099
```

### 过滤效果
当agent搜索GitHub issues时：
- **搜索前**: 返回包含`django/django#11099`的搜索结果
- **搜索后**: 自动过滤掉`django/django#11099`，保留其他相关issue

### 日志输出
```
Set current SWE-Bench task: repo=django/django, issue_number=11099
Filtering GitHub issues for SWE-Bench task: django__django-11099 (django/django#11099)
Blocking SWE-Bench issue: django/django#11099
Filtered 1 SWE-Bench task issue(s) from search results
```

## 测试

运行测试脚本来验证功能：
```bash
python3 evaluation/benchmarks/swe_bench/simple_test.py
```

测试内容包括：
- instance_id解析功能
- issue过滤逻辑
- 各种边界情况处理

## 注意事项

1. **环境变量**: 必须设置`SWE_BENCH_MCP_FILTER=true`才能启用过滤功能
2. **MCP工具**: 只影响`search_issues`工具，不影响其他MCP功能
3. **性能影响**: 过滤操作对性能影响极小，几乎无感知
4. **兼容性**: 与现有的SWE-Bench评估流程完全兼容

## 故障排除

### 1. 过滤功能未生效
- 检查环境变量`SWE_BENCH_MCP_FILTER`是否设置为`true`
- 确认MCP工具已正确配置
- 查看日志中是否有过滤相关的信息

### 2. 解析错误
- 检查instance_id格式是否正确
- 查看日志中的解析警告信息
- 确认SWE-Bench数据集格式

### 3. 性能问题
- 过滤操作通常很快，如果遇到性能问题，检查MCP服务器连接
- 确认网络连接正常

## 技术细节

### instance_id格式
```
{org}__{repo}-{number}
```
- `org`: GitHub组织名
- `repo`: 仓库名
- `number`: GitHub issue编号

### 过滤逻辑
```python
def should_block_swe_bench_issue(issue):
    if current_repo == issue.repo and current_issue_number == issue.number:
        return True
    return False
```

### 全局状态管理
使用全局变量来存储当前任务信息，确保在整个评估过程中保持一致的状态。 