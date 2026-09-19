# 开发与测试规范

本文档定义本地开发、编码、测试和提交工作流。根目录 `AGENTS.md` 提供必须执行的摘要。

## 1. 环境要求

- Python 3.10+
- Windows 为主要桌面目标平台
- 从仓库根目录执行命令，确保相对配置和资源路径正确

创建环境并安装依赖：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

启动桌面程序：

```powershell
.\.venv\Scripts\python.exe main.py
```

查看 CLI：

```powershell
.\.venv\Scripts\python.exe cli.py --help
```

## 2. 编码规范

- 使用四空格缩进和标准库风格导入。
- 模块、函数、变量使用 `snake_case`。
- 类使用 `PascalCase`。
- 常量使用 `UPPER_SNAKE_CASE`。
- 类型提示用于澄清数据流和公共接口，不为形式而增加复杂度。
- 保持修改范围小，不在功能变更中夹带无关重构。
- 领域和持久化逻辑放在 `src/`，Qt 代码放在 `src/gui/qt/`。
- 保持 JSON schema、原子写入及旧数据兼容。

架构边界见 `docs/architecture.md`，UI 规则见 `docs/ui-guidelines.md`，数据安全见 `docs/data-and-persistence.md`。

## 3. 基础验证

所有 Python 代码变更至少运行：

```powershell
.\.venv\Scripts\python.exe -m compileall -q main.py cli.py src
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

也可以使用 pytest 运行测试，但提交前应确保项目规定的 `unittest discover` 入口通过。

## 4. 按改动类型验证

| 改动类型 | 最低验证要求 |
| --- | --- |
| 仅文档 | 检查路径、链接、命令和描述是否与实现一致 |
| 领域逻辑 | 相关单元测试、完整测试套件 |
| 配置 | 默认配置、用户自定义值、旧配置修复、完整测试 |
| 持久化 | 保存、重新加载、原子写入、备份、失败场景、迁移 |
| CLI | JSON 契约、退出码、只读/写入保护、CLI 专项测试 |
| GUI | 编译、完整测试、启动、缩放、持久化、相关对话框 |
| 主题/UI | 默认及放大字号、对比度、Tooltip、焦点、截图 |
| 打包 | 执行构建并启动打包产物，检查资源和 Qt 依赖 |

测试应覆盖行为而不是实现细节。修复回归问题时，应优先增加能够复现问题的测试。

## 5. GUI 手工检查

GUI 改动至少检查：

- 应用正常启动和关闭；
- 窗口缩放后没有遮挡或截断；
- 默认字号和较大字号均可使用；
- 表格滚动、悬停和行级按钮一致；
- 对话框未被狭窄 parent 裁切；
- Tooltip 清晰可读；
- 数据保存并重新打开后保持一致；
- 快速关闭时后台保存线程正常结束。

完整清单见 `docs/ui-guidelines.md`。

## 6. 测试隔离与数据安全

- 测试运行时优先通过 `CPA_DATA_DIR` 或专项目录变量指向临时目录。
- 不得使用真实用户项目作为测试 fixture。
- 不得将测试生成的项目、备份、日志或用户配置提交到仓库。
- 涉及并发和异步保存时，应验证 teardown，不要只验证正常路径。

## 7. 已知回归重点

### 保存桥 teardown

历史上 `ProjectSaveBridge` 后台线程曾在宿主 QObject 销毁后发射信号，导致 Qt 冒烟测试不稳定。若再次出现 teardown 或 drain loop 失败，应优先检查后台线程与对象生命周期。

### PySide6 枚举

PySide6 6.11 不再支持部分实例级枚举访问。delegate 绘制相关崩溃应检查是否错误使用了 `painter.Antialiasing` 等实例属性。

### 旧配置兼容

列表配置由 `_deep_merge` 整体替换。新增列配置后，应检查旧用户配置是否经过按名称修复。

## 8. 提交规范

提交说明保持简洁并聚焦一个主题，可使用中文摘要或 Conventional Commit 风格，例如：

```text
feat: add project summary filter
fix: 修复大字号下标签截断
chore: 更新打包清单
```

避免将功能、格式化和无关重构混在同一提交中。

## 9. Pull Request 要求

PR 应说明：

- 改动目的和用户可见行为；
- 主要实现方式；
- 执行过的验证命令；
- 数据 schema、配置或迁移变化；
- 已知限制和后续工作；
- UI 修改前后的截图。

如果无法完成规定验证，应明确说明未执行的项目和原因，不能默认视为已通过。
