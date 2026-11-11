# 数字配色与字体记录

[English](THEME_REVIEW.en.md) · [许可范围](LEGAL.zh-CN.md)

## 配色决定：保留

| 内部兼容键 | 中文显示名 | 数字 / 颜色标签 |
| :--- | :--- | :--- |
| unit01 | 初·绿紫 | 01 · Green/Purple |
| unit00 | 零·蓝银 | 00 · Blue/Silver |
| unit02 | 二·赤橙 | 02 · Red/Orange |
| unit08 | 八·桃绿 | 08 · Pink/Green |
| mark06 | 六·蓝金 | 06 · Blue/Gold |
| mono | 素·黑白 | Mono |

保留普通配色、几何线条和仪表排版，默认素·黑白。旧内部键用于兼容已有配置，界面显示使用数字和颜色名称。公开包未附官方徽标、角色图、动画画面、音效或官方主题字库；名称不表示联名或认证。

[6 种配色的实际主界面截图](../README.md#themes)

## 字体决定：保留当前开放字体

Noto Serif SC、Roboto Condensed、Share Tech Mono 已与官方文件逐字节核对，字体文件与版权/许可一起保留。公开版不附 Matisse 商业字体，也不优先调用本机 Matisse。

这三款内置字体的开放许可允许本项目的非商业学习使用，不需要另行取得此用途授权；其原有许可同时允许的其他用途也继续保留。字体未改字形、未做子集，CSS 别名不改字体内部保留名称。Roboto 的历史内嵌 Apache 声明另有保留。[OFL 官方 FAQ](https://openfontlicense.org/ofl-faq/)

Matisse 的 EVA 相关产品另有商业条款，本候选不使用它；无需为当前包安排此字体的授权。[产品来源](https://mojimo.jp/eva/)

以后新增字体或素材时，更新 `third_party/provenance.json` 和对应许可文件即可；现有配色无需反复列为发布待选项。
