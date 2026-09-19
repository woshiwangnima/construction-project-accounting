# 发布与打包规范

本文档说明 Windows 发布包、PyInstaller 配置、资源和发布验证要求。

## 1. 构建入口

从仓库根目录运行：

```powershell
build.bat
```

发布产物位于：

```text
dist/ConstructionAccounting
```

构建目录和发布产物属于生成内容，不应提交到仓库。

## 2. PyInstaller 配置

打包由以下文件驱动：

```text
packaging/ConstructionAccounting.spec
```

必须遵守：

1. spec 文件保留在 `packaging/`，不要移动到 `build/`。
2. `build.bat` 会在每次构建前删除 `build/`，放在其中的配置会丢失。
3. spec 内路径应从 `SPECPATH` 派生，不能依赖调用者当前目录或某台机器的绝对路径。
4. 新增资源、动态导入或第三方依赖时，应检查 PyInstaller 是否能够发现并收集它们。

## 3. Qt 模块和原生 DLL

PyInstaller 的 `excludes` 只排除 Python bindings，不会自动移除对应的 Qt6 原生 DLL。

新增依赖如果引入新的 Qt 模块，必须同时检查：

- `QT_EXCLUDES`
- `BIN_EXCLUDE_KEYWORDS`
- `a.binaries` 的过滤结果

不要只验证 Python 模块是否被排除，还要检查最终发布目录中的 Qt6 DLL。过度排除也可能导致程序只在开发环境可运行，因此必须启动干净构建产物进行验证。

## 4. 资源与运行时路径

- 随程序发布的资源放在 `assets/` 或明确的配置目录中。
- 代码不得依赖开发机器的绝对路径。
- 默认配置来自 `config/`，用户配置和项目数据应写入运行时数据目录。
- 发布包不得携带真实 `projects/`、`backups/`、`logs/` 或 `config/user_config.json`。
- 使用环境变量覆盖目录时，打包程序应与源码运行行为一致。

## 5. 版本与发布脚本

`scripts/` 包含版本、manifest 和压缩发布辅助工具，例如：

- `scripts/bump_app_version.py`
- `scripts/read_app_version.py`
- `scripts/generate_manifest.py`
- `scripts/zip_release.py`
- `scripts/ziprelease.bat`

发布前应确认应用显示版本、构建元数据、manifest 和压缩包名称保持一致。版本号应通过已有脚本或单一版本来源更新，避免在多个文件中手工维护不同值。

## 6. 构建前验证

打包前至少运行：

```powershell
.\.venv\Scripts\python.exe -m compileall -q main.py cli.py src
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

测试失败时不应继续制作正式发布包，除非已记录并批准明确例外。

## 7. 发布包冒烟测试

每次正式发布至少验证：

- [ ] 从全新构建目录完成打包。
- [ ] `dist/ConstructionAccounting` 中程序能够启动。
- [ ] 主窗口、项目列表和核心编辑页面可打开。
- [ ] 创建、保存、关闭和重新打开项目正常。
- [ ] 默认配置和资源能够加载。
- [ ] 图标、字体、音频及导出功能所需资源存在。
- [ ] 对话框和 Tooltip 正常显示。
- [ ] 应用退出后没有残留保存线程或异常日志。
- [ ] 数据写入 `%APPDATA%\ConstructionAccounting` 或指定目录，而非发布目录。
- [ ] 发布目录不包含不需要的 Qt 模块、测试数据或用户数据。

## 8. 新依赖检查清单

引入新依赖时应评估：

1. 是否确有必要，标准库或现有依赖能否满足需求；
2. 是否支持项目 Python 和 Windows 版本；
3. 是否引入新的 Qt bindings 或大型原生库；
4. 是否需要 hidden imports、数据文件或二进制收集；
5. 是否需要修改 `QT_EXCLUDES` 和二进制过滤规则；
6. 对发布包体积、启动速度和许可证的影响；
7. 在未安装开发工具的环境中能否运行。

## 9. 发布记录

正式发布应记录：

- 版本号；
- 用户可见变更；
- 数据或配置迁移；
- 已执行的测试和冒烟检查；
- 已知问题；
- 发布产物名称及生成方式。
