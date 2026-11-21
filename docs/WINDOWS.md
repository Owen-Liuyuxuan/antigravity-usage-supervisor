# Windows 托盘版

在项目根目录运行以下命令。需要 Windows x64 或 ARM64 和 Python 3.10+。安装脚本会补装缺失的 .NET 10 SDK 和官方 Antigravity CLI，并发布自带 .NET 运行时的应用。

```powershell
./packaging/windows/install.ps1
```

从桌面或开始菜单打开 **Antigravity Usage Supervisor**。首次使用时，从托盘右键菜单选择「打开 agy」，在终端完成 Google 登录，然后点「刷新」。浮窗显示账户提供的额度窗口、重置时间、今日活动和最近五个本机任务。活动时间和 token 数是本机日志估算值。

- 托盘优先显示 Argon 周额度的已用百分比，悬停可查看当前对应的额度窗口。绿、黄、红的分界是 70% 和 90%。灰色代表缓存，`?` 代表当前无数据。
- 左键点击托盘图标可打开或收起浮窗。右键菜单可以刷新、打开 agy、打开设置或退出。
- 设置里可以改变日志目录、刷新间隔和登录 Windows 后自动启动。自动启动默认关闭。

本机活动默认读取 `%USERPROFILE%\.gemini\antigravity-cli`。实时额度沿用当前 Windows 用户的 agy 登录会话，通过原项目的 Cloud Code Assist 查询实现。监控仅发出额度查询，不消耗模型生成额度。查询失败时使用最近一次成功的额度缓存。

安装位置为 `%LOCALAPPDATA%\Programs\AntigravityUsageSupervisor`。重新安装前从托盘菜单退出。运行 `./packaging/windows/uninstall.ps1` 可移除应用和快捷方式，个人设置和 CLI 登录会保留。

安装后可运行 `AntigravityUsageSupervisor.exe --smoke-test` 验证后端和浮窗渲染。应用会写入 `smoke-test.txt` 和 `smoke-test.png` 后退出。截图可能包含本机任务名。
