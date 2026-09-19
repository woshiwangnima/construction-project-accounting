# 命令行接口说明书（cpa）

施工项目记账程序的命令行接口。**不启动 GUI**，不依赖 Qt，可在无显示器环境、
CI、脚本和其他程序中作为子进程调用。

## 为什么要有 CLI

GUI 负责交互，CLI 负责"被程序调用"。二者共用同一套领域逻辑
（`src/project_manager.py`、`src/bill_recompute.py`、`src/calculator.py` 等），
因此**金额口径、算式规则、孤儿账单判定与 GUI 完全一致**，不存在两套实现。

CLI 层（`src/cli/`）不 import `PySide6` / `qfluentwidgets` / `src.gui`，
这条约束由 `tests/test_cli_no_qt.py` 守住。

## 快速开始

```bash
python cli.py --help
python cli.py calc "3*4+5" --json
python cli.py project.list --json
```

## 响应契约（程序调用必读）

**所有**命令都支持 `--json`。程序调用请始终加上它。

成功（退出码 `0`）：

```json
{ "ok": true, "data": { } }
```

失败（退出码 `1`）——**失败时响应体同样是 JSON**，不会只往 stderr 打印文本：

```json
{
  "ok": false,
  "error": {
    "code": "PROJECT_NOT_FOUND",
    "message": "项目 UUID 格式非法: does-not-exist",
    "details": { "uuid": "does-not-exist" }
  }
}
```

退出码约定：

| 退出码 | 含义 |
| --- | --- |
| `0` | 成功 |
| `1` | 业务错误（响应体仍是 JSON，**务必读 `error.code`**） |
| `2` | 参数错误（argparse，响应体不是 JSON） |

稳定错误码：

| `error.code` | 触发场景 |
| --- | --- |
| `PROJECT_NOT_FOUND` | 项目不存在，或 UUID 格式非法 |
| `GUI_RUNNING` | 桌面程序正在运行，写入被拒绝（只读命令不受影响） |
| `INVALID_ARGUMENT` | 参数语义非法（如导入文件不存在） |
| `FORMULA_ERROR` | 算式无法求值 |
| `EXPORT_FAILED` | 导出失败（含目标文件已存在） |
| `ERROR` | 兜底（不应出现，出现即为 bug） |

## 自动发现能力（推荐做法）

不要依赖本文件手工维护命令清单——请读取 `schema`：

```bash
python cli.py schema --json
```

它由命令注册表（`src/cli/registry.py`）自动生成，包含每个命令的参数、
是否只读、以及上面的响应契约。**这份 schema 不可能与实现漂移**，
因为 argparse 子命令和它来自同一个注册表。

## 命令清单

### 只读命令

```bash
# 项目
python cli.py project.list --json                          # 全部项目
python cli.py project.list --status 进行中 --json           # 按状态筛选
python cli.py project.list --name-contains 小区 --json      # 按名称筛选
python cli.py project.show <uuid> --json                   # 含账单/工种明细
python cli.py project.show <uuid> --summary-only --json    # 仅摘要

# 账单
python cli.py bill.list <uuid> --json                      # 每行合计（含公式错误标记）
python cli.py bill.list <uuid> --orphan-only --json        # 仅孤儿账单
python cli.py bill.summary <uuid> --json                   # 按分类/工作类型汇总

# 存档
python cli.py backup.list <uuid> --json
python cli.py backup.list <uuid> --valid-only --json
python cli.py backup.inspect <备份文件路径> --json

# 算式（不读写任何文件）
python cli.py calc "3*4+5" --json
python cli.py calc "（2+3）×4" --json                       # 全角符号自动归一化
```

### 写入命令

> ⚠️ **桌面程序运行时，写入命令会被拒绝**（错误码 `GUI_RUNNING`）。
> 这是刻意的保护：GUI 与 CLI 同时写同一批 JSON 会互相覆盖，导致你在界面上
> 正在编辑的内容丢失。请先保存并关闭程序再执行写入。
> 只读命令不受影响，GUI 开着也能正常查询。

```bash
# 项目
python cli.py project.create 某某小区 --json                        # 创建
python cli.py project.create 某某小区 --description 备注 --json
python cli.py project.rename <uuid> 新名称 --json                   # 改名
python cli.py project.status <uuid> done --json                    # 改状态
python cli.py project.status <uuid> 已完成 --json                   # 也接受中文
python cli.py project.set-description <uuid> 备注 --json
python cli.py project.delete <uuid> --yes --json                   # 删除需 --yes

# 账单
python cli.py bill.add <uuid> '3*4+5' --trade-item ti_wall --json   # 添加
python cli.py bill.add <uuid> '2+1' --trade-item ti_wall --note '三份' --json
python cli.py bill.add <uuid> '1+1' --trade-item ti_wall \
    --work-date-type 起止时间 --date-start 2026-01-01 --date-end 2026-01-05 --json
python cli.py bill.update <uuid> <bill-id> --content '5*5' --json   # 修改（只改传入字段）
python cli.py bill.update <uuid> <bill-id> --reviewed --json        # 标记已审核
python cli.py bill.remove <uuid> <bill-id> --json                   # 删除

# 导入导出
python cli.py project.export <uuid> ./out.json --json               # 目标已存在则失败
python cli.py project.export <uuid> ./out.json --overwrite --json
python cli.py project.import ./project.json --json                  # 生成新 UUID，不覆盖原项目
```

写入保护的实现：所有写入命令先探测 GUI 的单实例锁（`src/cli/guard.py`），
再调用 `project_manager` 的既有 API（内部自带写锁 `_project_write_lock`
与备份策略）。CLI 不自行写 JSON 文件。

### 写入命令的安全约定

- `project.delete` 必须显式加 `--yes`，且删除前会**强制备份一次**。
- 项目状态为「已完成」时，`bill.add` / `bill.update` / `bill.remove` 会被拒绝
  （与 GUI 的冻结规则一致，见 `ProjectStatus.is_editable`）。
- `bill.add` 不传 `--trade-item` 会报错；确实要登记不关联工作类型的账单时，
  需显式加 `--allow-orphan`，避免静默产生孤儿数据。
- `bill.update` 只修改传入的字段，未传的字段保持不变；无实际改动时
  返回 `changed: false`。

## 金额口径说明

- `bill.list` / `bill.summary` 的合计**复用 GUI 同一函数**
  （`bill_recompute.summarize_bill_calculations`），已覆盖：
  按单价乘法、孤儿账单回退 `frozen_total`、每行四舍五入到分。
- `bill.list --orphan-only` 时，`total` 只统计**本次实际输出的行**；
  同时提供 `project_total` 表示项目整体金额，避免调用方误读。
- `formula_error_count` 沿用 GUI 口径：非空公式且合计为 0 即计一次告警。

## 环境变量

CLI 与 GUI 共用同一套数据目录变量：

| 变量 | 说明 |
| --- | --- |
| `CPA_PROJECTS_DIR` | 项目文件目录 |
| `CPA_BACKUPS_DIR` | 备份目录 |
| `CPA_CONFIG_DIR` | 配置目录（`symbol_mapping` 等由此读取） |

`symbol_mapping` 来自用户配置，因此用户改了算式符号后，CLI 与 GUI 的
求值结果依然一致。

## 设计约束（改动前请先读）

1. **CLI 不做业务计算。** 只做参数解析 → 调用 domain 函数 → 序列化。
   自行求和/自行解析公式必然与 GUI 口径分叉。
2. **写入必须复用 `project_manager`。** 不要自己 `json.dump` 到项目文件，
   否则会绕过 `atomic_write_json` 的原子写入与备份策略。
3. **命令清单只在注册表里写一份。** 新增命令 = 在 `src/cli/commands/` 下
   `register(CommandSpec(...))`；`schema` 与 help 会自动包含它。
   `tests/test_cli_contract.py` 会校验注册表与 schema 一致。
