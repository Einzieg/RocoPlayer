# Windows 安装包

按首页准备环境并执行 `uv sync --locked` 后：

```powershell
$ErrorActionPreference = 'Stop'
.\Build-Installer.ps1
```

PyInstaller 打包 Python 引擎、模型及依赖，Tauri NSIS 生成 x64 安装器，输出在 `.build/installer-target/release/bundle/nsis/`。每次使用独立暂存目录，普通版不混入之前的 DD 文件。构建过程不安装驱动，也不覆盖正在运行的工作区播放器。

安装包运行不需要 Python/Node/Rust。系统需要 Windows 10/11 x64 和 WebView2；Tauri 安装器使用默认 WebView2 引导。per-machine 安装会请求管理员权限。升级、卸载前须先停止演奏并正常退出程序。

## 含 DD 的构建

仅当你已确认具备适用的再分发权时：

```powershell
$ErrorActionPreference = 'Stop'
.\Build-Installer.ps1 -DDPackagePath '.\2026.DD.EV.HVCI.63xxx\2.hid' -ConfirmDDRedistributionRights
```

必需文件：`ddhid.63340.dll`、`drv/ddc.exe`、`drv/ddhid63340.inf`、`drv/ddhid63340.sys`、`drv/ddhid63340.cat`。脚本校验文件及 DLL、安装器、CAT 的 Authenticode 状态，不修改签名文件。

构建时从打包引擎中提取 `msvcp140.dll`、`vcruntime140.dll`、`vcruntime140_1.dll`，验证 Microsoft 签名、AMD64 架构和复制哈希后，部署在 `ddc.exe` 同目录。Windows 10/11 提供系统 UCRT；不修改系统目录、PATH 或已有运行库。

安装器调用独立的 `--dd-setup` 分支，不启动播放器，不加载 DD DLL。先查询 `ddhid63340` 服务和当前存在的关联 PnP 设备；只有服务运行、设备已启动且查询成功/问题码为 0，才报告服务与设备就绪（不代表实际输入已验证）。已注册或已有设备但状态异常时跳过重装。仅完全未注册且无关联设备时启动厂商安装程序；返回 0 后最多轮询 10 秒确认状态，不再把注册表项存在当作安装成功。

3010 或 120 秒超时提示重启。超时不强杀厂商进程，写入 `dd-install-pending.json`，后续未就绪时阻止重复安装。支持人员须确认重启后无遗留安装进程并检查日志，再手工处理该标记；程序不会自动删除它。应用卸载不会移除共享驱动，不关闭内存完整性、安全启动、签名检查。

### 持久化日志

默认目录：`C:\ProgramData\RocoPlayer\logs`（实际使用 Windows 的公共应用数据目录）。

- `dd-bootstrap.log`：安装器调用路径和助手返回值，即使 Python 助手启动失败仍有记录。
- `dd-<UTC时间>-<随机编号>.jsonl`：服务安装前后状态、PnP 设备 ID/状态/问题码、文件哈希、厂商进程 PID/返回码、异常及最终结论；UTF-8。
- `dd-<同编号>-vendor.log`：厂商 stdout/stderr 原始字节，编码由厂商决定。弹出的原生对话框内容不在该文件内。
- 日志不随卸载清除。向他人提交前检查路径和设备 ID 等信息。

若无法建立日志，助手不会安装驱动。可在安装目录用 `engine/rock-music-engine.exe --dd-setup --inspect-only --driver-dir drivers/dd/drv --log-dir <可写目录>` 只读检查；退出 0 表示服务/设备状态正常，2 表示异常或未知。此模式绝不调用 `ddc.exe`。

当前官方仓库未附 MIT LICENSE；如果使用其他明确授权的版本，应随发布包保留许可与来源，详见 [第三方说明](../THIRD_PARTY_NOTICES.md)。

## 发布前验证

1. 运行 Python/前端测试及 Rust 检查。
2. 复制独立打包目录到不含源码、`.venv` 的路径，使用独立数据目录执行 `ROCK_MUSIC_SMOKE=1`；不调用真实播放。
3. 在干净 Windows 虚拟机测试安装、升级、卸载、WebView2、取消 UAC、DD 安装失败和重启场景。
4. 未做干净虚拟机测试前，不声称完整安装验收通过。未签名的应用安装器可能触发 SmartScreen；DD 厂商签名不能替代应用签名。
