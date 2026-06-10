# 施工项目记账程序

一款专为建筑施工场景打造的可视化记账、算账、项目管理工具，支持语音播报、自动备份、存档回滚、跨项目复制粘贴、自动更新，无需专业财务知识即可快速完成工程收支核算。

## 功能特性

### 单窗口设计
- 左侧边栏显示项目列表，点击切换
- 右侧内容区显示项目详情（账单管理 / 工作类型）
- 支持搜索过滤项目
- 项目名就地编辑

### 项目管理
- 创建、编辑、删除施工项目
- 项目状态管理：编辑中 / 进行中 / 已结账
- 项目列表支持搜索
- 项目数据自动备份（智能比较，仅内容变化时备份）
- 项目导入 / 导出（JSON 文件）
- 项目右键菜单：打开文件位置、回滚存档、删除
- 存档回滚：支持选择历史版本预览并恢复，附带孤儿账单检测
- 窗口尺寸和位置持久化

### 工作类型管理（分类 + 工种）
- 预置常见工作类型（泥瓦工程、水电工程等），按分类组织
- 自定义工作项目、单价和单位
- 支持"按单价"或"无单价"两种计费方式
- 支持分类的添加、删除、排序（上移/下移）
- 工作类型支持添加、编辑、删除、排序
- 支持恢复默认工作类型
- 删除工作类型时关联账单自动转为孤儿（保留最后已知金额快照）

### 账单管理
- 记录各工作项目的账单
- 每条记录包含日期（支持无时间 / 单个时间 / 起止时间三模态）
- 支持数学算式计算（如：3×4+5），支持 × ÷ 符号和括号
- 自动计算金额总计
- 双击记录可编辑
- 支持批量选中 / 删除
- 拖动行手柄排序 / 上移下移按钮
- 列宽可拖拽调节，自动持久化

### 账单审核
- 逐条账单审核标记（未审核 / 已审核）
- 表头一键全选 / 全取消审核
- 已审核行视觉区分（绿色背景）

### 跨项目复制粘贴
- 复制账单或工作类型到应用内剪贴板
- 切换到其他项目粘贴
- 自动处理名称去重（X → X 副本 → X 副本 2）
- 孤儿账单自动生成 frozen_snapshot

### 图片导出
- 将账单记录导出为 PNG 图片
- 包含工作类型价目表 + 账单明细
- 自定义导出设置（字体颜色、背景色、列对齐等）
- 支持隐藏无单价项 / 空分类
- 孤儿账单阻止导出，确保数据完整

### 语音播报
- 计算器按键预录音频播放（winsound / playsound）
- 整段公式 TTS 朗读（pyttsx3，中文语音）
- 可调节音量、语速
- 按需加载，缺失依赖自动降级

### 设置面板
- **基本设置**：导出颜色设置（文字颜色、背景色）
- **语音设置**：启用/禁用语音、音量、语速
- **导出设置**：价目表显示、列对齐、宽度的配置
- **关于**：版本信息、许可证

### 自动更新
- 启动后 3 秒后台检查 GitHub Releases
- 语义化版本对比
- 下载 zip + SHA256 manifest 校验
- 拉起 apply_update.bat 自动替换文件并重启（绕过 Windows exe 占用）

### 数据安全
- 所有写入使用原子写入（临时文件 → os.replace）
- 项目文件名使用 UUID，防路径遍历
- 修改前自动备份，保留最近 10 个
- 备份存档可查看有效性、孤儿账单数
- 数据迁移框架：自动升级旧版本数据到最新 schema
- 配置文件错误后自动恢复为默认值

## 界面预览

```
┌──────────────────────────────────────────────────┐
│  施工项目记账程序                                  │
├────────────┬─────────────────────────────────────┤
│            │                                     │
│ [+ 新建项目]│  XX小区装修  ● 进行中  [标记为已结账]│
│ [导入] [导出]│  创建：2024-03-15                  │
│ [搜索...]  │  ─────────────────────────────────  │
│            │  [账单管理]  [工作类型]               │
│ ● XX小区装修│                                     │
│ ● 商场改造  │  合计（3 条）：￥725.00              │
│ ○ 仓库维修  │  [+添加记录] [保存为图片]             │
│            │  ┌─────────┬──────┬──────┬──────┐   │
│  [设置]     │  │#│审核│工作内容│公式│单价│金额│...│   │
│  [检查更新]  │  │1│ ☑  │砌墙    │5  │45 │225 │   │   │
│            │  │2│ ☐  │贴砖    │8  │40 │320 │   │   │
│            │  └─────────┴──────┴──────┴──────┘   │
└────────────┴─────────────────────────────────────┘

● = 进行中 / 编辑中    ○ = 已结账
```

## 技术栈

- **Python 3.10+**
- **Tkinter** — GUI 界面框架
- **Pillow** — 图片处理与导出
- **pyttsx3** — TTS 语音播报（可选依赖）
- **PyInstaller** — 打包为 Windows 可执行文件
- **JSON** — 数据存储格式

## 项目结构

```
construction-project-accounting/
├── main.py                     # 应用程序入口
├── build.bat                   # PyInstaller 打包脚本
├── requirements.txt            # Python 依赖
├── LICENSE                     # MIT 许可证
├── config/                     # 配置文件目录
│   ├── app_config.json         # 应用配置（符号映射、默认工种等）
│   └── user_config.json        # 用户配置（导出颜色、语音偏好等）
├── src/                        # 源代码目录
│   ├── gui/                    # 图形界面
│   │   ├── __init__.py
│   │   ├── main_window.py      # 主窗口组装 + 快捷键 + 更新检查
│   │   ├── sidebar.py          # 侧边栏（项目列表 + 右键菜单）
│   │   ├── content.py          # 内容区（账单 + 工作类型 + 导出）
│   │   ├── theme.py            # 颜色/字体常量
│   │   ├── editability.py      # 编辑权限策略
│   │   ├── clipboard.py        # 应用内剪贴板
│   │   ├── widgets/            # 可复用组件
│   │   │   ├── bill_list_view.py    # 账单自定义列表
│   │   │   ├── worker_list_view.py  # 工种列表
│   │   │   ├── list_view_base.py    # 列表基类
│   │   │   ├── rollback_list_view.py# 回滚存档列表
│   │   │   ├── canvas_scroll.py     # Canvas 滚动工具
│   │   │   ├── scroll_anchor.py     # 滚动位置锚点
│   │   │   ├── column_layout.py     # 列宽布局
│   │   │   ├── reorder.py           # 拖动排序
│   │   │   ├── confirm_dialog.py    # 确认弹窗
│   │   │   ├── __init__.py          # 通用按钮/输入/日期选择器
│   │   │   └── ...
│   │   └── dialogs/            # 弹窗组件
│   │       ├── new_project.py       # 新建项目
│   │       ├── edit_trade.py        # 编辑工作项目
│   │       ├── edit_bill.py         # 编辑账单记录
│   │       ├── rollback.py          # 回滚存档
│   │       ├── update_dialog.py     # 更新提示
│   │       └── settings/            # 设置面板
│   │           ├── __init__.py           # 设置窗口框架
│   │           ├── base.py              # 面板基类 + 注册
│   │           ├── basic_panel.py       # 基本设置
│   │           ├── voice_panel.py       # 语音设置
│   │           ├── export_panel.py      # 导出设置
│   │           └── about_panel.py       # 关于
│   ├── project_manager.py     # 项目 CRUD + 备份 + 导入导出
│   ├── project.py             # Project 数据模型
│   ├── project_uuid.py        # UUID 生成/验证/文件路径
│   ├── project_status.py      # 项目状态枚举
│   ├── category.py            # 分类数据模型
│   ├── trade_item.py          # 工种数据模型
│   ├── trade_item_id.py       # 工种 ID / 账单 ID 生成
│   ├── bill.py                # 账单数据模型
│   ├── billing.py             # 计费方式模型
│   ├── billing_resolver.py    # 账单解析（名称、单价、孤儿检测）
│   ├── bill_recompute.py      # 账单金额重算
│   ├── bill_review.py         # 审核状态操作
│   ├── calculator.py          # 数学表达式解析（÷×→/*，括号）
│   ├── symbol_mapping.py      # 符号映射（语音用）
│   ├── image_output.py        # PIL 文本 → PNG 导出
│   ├── config_loader.py       # JSON 配置读写
│   ├── export_config.py       # 导出设置数据模型
│   ├── paste_actions.py       # 粘贴纯函数层
│   ├── voice.py               # 语音播报引擎
│   ├── updater.py             # GitHub Releases 自动更新
│   ├── versioning.py          # 版本号 + 数据迁移框架
│   ├── migrate_v3.py          # v3 → v4 数据迁移
│   ├── backup_policy.py       # 备份策略（指纹比对、序列化）
│   ├── backup_inspector.py    # 存档检视（孤儿检测）
│   ├── logger.py              # 日志模块
│   └── utils.py               # 工具函数（atomic_write_json）
├── assets/                    # 资源文件
│   └── audio/                 # 语音播报音频文件（数字 + 运算符 WAV）
├── projects/                  # 项目账本数据存储目录
├── backups/                   # 自动备份文件目录
├── logs/                      # 日志文件目录
└── scripts/                   # 构建工具脚本
    ├── generate_manifest.py   # 生成 SHA256 file_manifest.json
    └── ziprelease.bat         # 打包 release zip
```

## 安装与运行

### 环境要求
- Python 3.10 或更高版本
- pip 包管理器

### 安装步骤

1. 克隆或下载项目文件
2. 安装依赖包：
   ```bash
   pip install -r config/requirements.txt
   ```
3. 运行应用程序：
   ```bash
   python main.py
   ```

### 一键启动
Windows 用户可以直接双击 `start.bat` 文件启动应用程序。

### 打包为可执行文件
```bash
build.bat
```
输出：`dist/ConstructionAccounting/` 目录 + `dist/ConstructionAccounting-{版本号}.zip` 发布包。

## 使用说明

### 创建新项目
1. 点击左侧边栏的「+ 新建项目」按钮
2. 输入项目名称
3. 点击「创建」按钮

### 切换项目
直接点击左侧边栏中的项目名称即可切换。

### 项目状态管理
- 项目默认状态为「编辑中」
- 点击顶部状态标签可切换：编辑中 → 进行中 → 编辑中
- 已结账项目显示为灰色，数据只读

### 导入 / 导出项目
- **导出**：选中项目后点击「导出项目」按钮，保存为 JSON 文件
- **导入**：点击「导入项目」按钮，选择 JSON 文件导入

### 管理工作类型
1. 点击右侧的「工作类型」标签
2. 左侧分类列表：添加、排序、删除分类
3. 右侧工种表格：添加、编辑（双击）、删除工作项目
4. 支持恢复默认工作类型
5. 分类和工种均支持右键菜单（上移/下移/删除）

### 记录账单
1. 点击右侧的「账单管理」标签
2. 点击「+ 添加记录」按钮
3. 选择工作项目
4. 输入公式（支持算式如 3×4+5）
5. 选择日期类型：无时间 / 单个时间 / 起止时间
6. 填写备注（可选）
7. 点击「确定」保存

### 编辑/删除记录
- **编辑**：双击记录行
- **删除**：选中记录后点击行内删除按钮或 Delete 键
- **排序**：拖动行左侧手柄，或点击上移/下移按钮

### 审核账单
- 点击行内复选框逐条审核
- 点击表头全选/取消全选

### 跨项目复制粘贴
- **复制**：账单或工种行右键 → 复制
- **粘贴**：切换到目标项目，右键 → 粘贴
- 支持跨项目复制，自动处理孤儿账单和名称去重

### 导出图片
1. 点击「保存为图片」按钮
2. 选择保存位置
3. 图片自动生成（孤儿账单会阻止导出）

### 回滚存档
1. 项目右键菜单 → 「回滚存档」
2. 选择历史备份版本（显示时间和有效性）
3. 确认后自动备份当前状态并恢复所选版本

### 设置
点击侧边栏底部「设置」按钮，可配置：
- 导出文字颜色 / 背景色
- 语音播报开关
- 价目表显示选项
- 查看版本信息和许可证

## 术语说明

| 术语 | 含义 |
|------|------|
| 工作类型（分类） | 工人的工种类别，如泥瓦工程、水电工程 |
| 工作项目（工种） | 具体的工作内容，如砌墙、贴砖 |
| 按单价计费 | 需要"单价（浮点）"和"单位（文本）"，按 单价×公式结果 计算 |
| 无单价计费 | 不需要单价和单位，金额直接由公式得出（按次/一次性） |
| 孤儿账单 | 账单引用的工作项目已被删除时的状态，显示为红色"⚠ 已删除" |
| 编辑中 | 项目数据可自由编辑 |
| 进行中 | 项目正在施工，数据可编辑 |
| 已结账 | 钱已付清，项目关闭，数据只读 |

## 数据结构

### 项目数据
```json
{
  "name": "XX小区装修",
  "status": "active",
  "project_uuid": "p_xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "project_date_type": "无时间",
  "project_date_start": "",
  "project_date_end": "",
  "created_at": "2024-03-15",
  "last_modified": "2024-03-15 10:30:00",
  "schema_version": 1,
  "app_version": "1.0.0",
  "category_order": [
    {"id": "cat_xxx", "name": "泥瓦工程"}
  ],
  "trade_items": [...],
  "bills": [...],
  "view_state": {}
}
```

### 账单记录数据
```json
{
  "id": "bill_xxx",
  "trade_item_id": "ti_xxx",
  "content": "5",
  "work_date_type": "单个时间",
  "work_date_start": "2024-03-15",
  "work_date_end": "",
  "note": "加油",
  "record_time": "2024-03-15 10:30:00",
  "reviewed": false,
  "frozen_snapshot": null,
  "frozen_total": null,
  "_needs_attention": false
}
```

## 配置说明

### 应用配置 (app_config.json)
- `symbol_mapping`：操作符映射关系（×、÷等符号转换）
- `default_trade_items`：默认工作类型列表
- `default_categories`：默认分类列表
- `selection_highlight_color`：列表选中高亮色
- `bill_reviewed_row_color`：已审核行背景色
- `window_sizes`：窗口尺寸记忆
- `default_bill_column_widths`：账单列宽默认值
- `default_worker_column_widths`：工种列宽默认值

### 用户配置 (user_config.json)
- `export_defaults`：导出设置（颜色、价目表显示等）
- `voice`：语音设置（启用、音量、语速）
- `window_sizes`：弹窗尺寸记忆
- `recent_projects`：最近项目

### 环境变量
- `CPA_PROJECTS_DIR`：项目数据目录（默认：./projects）
- `CPA_BACKUPS_DIR`：备份文件目录（默认：./backups）
- `CPA_CONFIG_DIR`：配置文件目录（默认：./config）
- `CPA_LOG_LEVEL`：日志级别（DEBUG/INFO/WARNING/ERROR）

## 自动更新

项目内置 GitHub Releases 自动更新机制：
1. 启动 3 秒后后台检查最新版本
2. 语义化版本对比，仅新版本提示
3. 下载 zip + SHA256 manifest 完整性校验
4. 启动 apply_update.bat 完成替换和重启
5. 更新源配置在 `src/updater.py` 中 `GITHUB_OWNER` / `GITHUB_REPO`

## 数据备份

- 系统自动在 `backups/` 目录中创建项目备份
- 备份策略：智能指纹比对，仅内容变化时备份
- 序列化文件名：`p_{uuid}.{seq}.json`
- 保留最近 10 个备份
- 修改前自动备份当前状态
- 迁移前自动备份到 `migration_backups/`

## 日志文件

应用程序运行日志保存在 `logs/app.log` 文件中，包含调试信息和操作记录。

## 许可证

[MIT License](LICENSE)

Copyright (c) 2026 woshiwangnima
