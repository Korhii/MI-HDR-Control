# 0.9.26-public-preview.1

- 修复 HDR 图样顶部参数文字：黑底提高亮度，亮底改用黑字；保留原有几何、PQ 输入和隐藏文字功能。
- 更新真实 ADB 在线主题图、便携数据目录及迁移说明；补充连接时的授权／管理员权限确认。
- 开放 Issues、Discussions 和 Pull Requests；不承诺回复、维护、修复、更新或合并。
- GitHub Latest 提供当前便携包下载，项目继续定位为实验预览。上一版附件与标签保留。

Fixed HDR annotation contrast on dark/full-white backgrounds without changing geometry, PQ input or hiding. Updated connected theme images, portable-data/relocation guidance and ADB permission prompts. Feedback and pull requests are open without a maintenance commitment. This experimental-preview revision is the Latest download; previous artifacts remain available.

# 0.9.26-public-preview

[中文说明](README.md) · [English](README.en.md)

- 以 0.9.26 为源包，保留竖向 A4 窗口与新版 ABL 关闭、循环/未收敛、透明时间切片及投影。
- 修正统一预算/ABL 快照耦合、迟到预测覆盖、离线 JSON 导入和 ADB 多入口识别问题。
- 中英文 README、首次使用/逐模块教程同步更新；补齐 Alpha 与信号层级解释。
- 21 张暗黑 MONO 教程图、6 张真实 ADB 在线的 APL/ABL 页首配色图；设备菜单图沿用同固件的真实裁切记录。
- 保留独立桥接与使用者本机准备组件、仅调光范围、分层许可及实验预览定位。

Experimental preview based on 0.9.26: current A4/ABL behaviour retained; coupled Apply, stale forecasts, offline file import and discovery corrected. Updated bilingual guides, signal glossary and actual captures. No second-device/LAN acceptance, thermal/electrical safety certification or completed uninterrupted reboot acceptance is claimed. Published downloads are listed in Releases.

## 界面与缓存修订 / UI and cache revision

启动弹窗集中风险与正常退出提示；完成提示仅确认；自动保存简化，JSON 支持原生另存；离开曲线节点即隐藏提示；ABL 开启整区灰化，修复导入后无拟合结果的刷新；响应冷缓存 35.05→4.59 秒，逐字节一致。中英文教程与截图同步。

Startup risks/normal exit, acknowledgement-only notices, autosave with native JSON Save As, node-only tooltips, ABL-disabled fitting and corrected no-fit import redraw. Parallel cold caching 35.05→4.59 s with byte-identical results. Paired guides and captures updated.

## GitHub 首发 / First public release

中英文 README、免责声明、启动提示及署名说明增加 AI 工具制作声明；提供明确便携包下载入口。建立只读公开检查与手动批准发布步骤，保留个人实验、无维护承诺及原有许可/硬件边界。

AI-assisted creation disclosed in paired READMEs, disclaimers, startup and attribution. Added portable download entry, read-only public checks and an explicit manual release-approval step. Personal-use scope, support policy, licenses and hardware limits remain unchanged.
