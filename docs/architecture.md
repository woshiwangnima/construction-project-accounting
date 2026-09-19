# 项目架构约束

本文档说明项目的模块职责、依赖方向和新增代码的放置原则。强制规则摘要见根目录 `AGENTS.md`；若两者冲突，以 `AGENTS.md` 为准。

## 1. 应用入口

- `main.py`：Windows 桌面应用入口，启动 PySide6/Qt 界面。
- `cli.py`：命令行入口，不启动 GUI。
- `src/`：领域逻辑、数据模型、配置、持久化及共享服务。

GUI 与 CLI 应复用同一套领域逻辑，不得分别实现金额计算、项目状态或数据保存规则。

## 2. 目录职责

| 路径 | 职责 |
| --- | --- |
| `src/` | 领域模型、业务计算、配置、持久化、备份等非界面逻辑 |
| `src/cli/` | 参数解析、命令注册、输出序列化和 CLI 写入保护 |
| `src/gui/` | 主题、字体、剪贴板、快捷键、编辑性等共享 GUI 能力 |
| `src/gui/common/` | 不依赖具体 GUI 框架的 UI 辅助逻辑 |
| `src/gui/qt/` | PySide6 窗口、对话框、控件、delegate 和 Qt 事件处理 |
| `config/` | 随程序发布的默认配置 |
| `assets/` | 音频、图标等静态资源 |
| `scripts/` | 版本、迁移、清单和发布辅助脚本 |
| `tests/` | `unittest`/pytest 自动化测试 |
| `packaging/` | PyInstaller 等打包配置 |

运行时用户数据属于 `projects/`、`backups/`、`logs/` 或环境变量指定的外部目录，不属于源码。

## 3. 依赖方向

推荐依赖方向：

```text
main.py / cli.py
        ↓
GUI / CLI adapters
        ↓
application services
        ↓
domain models and persistence
```

必须遵守：

1. 领域与持久化模块不得依赖 `PySide6`、`qfluentwidgets` 或 `src.gui`。
2. `src/cli/` 不得导入 Qt；该边界由 `tests/test_cli_no_qt.py` 保护。
3. GUI 和 CLI 不得复制业务计算，应调用 `src/` 中已有领域函数。
4. 框架无关逻辑优先放入 `src/gui/common/`，不要绑死在 QWidget 中。
5. 窗口和页面负责界面组合及事件协调，不应成为新的持久化实现。

## 4. Qt 界面组成

主要界面结构：

- `QtContentArea`：`src/gui/qt/content.py`
- `BillViewMixin`：`src/gui/qt/bill_view.py`
- `WorkerViewMixin`：`src/gui/qt/worker_view.py`
- 共享视图辅助：`src/gui/qt/view_common.py`
- 分类及列宽纯逻辑：`src/gui/qt/category_utils.py`
- 异步保存桥：`src/gui/qt/save_bridge.py`

新增较大功能时，优先形成独立组件或 mixin，而不是继续扩大单个窗口类。完整视觉和交互约束见 `docs/ui-guidelines.md`。

## 5. CLI 架构

CLI 只负责：

```text
参数解析 → 调用领域函数 → 序列化结果
```

新增命令通过 `src/cli/commands/` 与命令注册表实现。命令清单、参数和 schema 必须来自同一注册源，不能维护第二份静态实现。写入操作必须复用 `project_manager`，不能自行写 JSON。完整契约见 `docs/cli.md`。

## 6. 新代码放置判断

新增代码前依次判断：

1. 是否是纯业务规则？放在 `src/` 对应领域模块。
2. 是否是数据加载、保存或迁移？放在持久化或配置模块，并遵守 `docs/data-and-persistence.md`。
3. 是否不依赖 Qt、但服务于 UI？放在 `src/gui/common/` 或 `src/gui/`。
4. 是否直接操作 QWidget、信号、delegate 或 Qt 事件？放在 `src/gui/qt/`。
5. 是否只是 CLI 参数和输出适配？放在 `src/cli/`，业务本身仍留在领域层。
6. 是否仅用于构建、发布或一次性迁移？放在 `scripts/`。

## 7. 架构变更要求

涉及模块职责或依赖方向的变更应：

- 说明为什么现有模块无法承载；
- 避免形成 GUI/CLI 各自一套业务规则；
- 为关键边界增加测试；
- 更新本文档及受影响的专项文档；
- 保持公共数据格式向后兼容，或提供明确迁移方案。
