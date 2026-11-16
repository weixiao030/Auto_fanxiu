# 第三方资源与许可

本项目原创源码使用根目录的 Apache-2.0 许可。第三方组件和资源保留各自权利。

## 赞赏码与界面参考

按项目维护者要求，`web/appreciation-code.webp` 沿用 [Auto_Dps](https://github.com/weixiao030/Auto_Dps) 的作者赞赏码。来源为该仓库 `web/public/appreciation-code.webp`，600×600、35,700 字节，SHA-256：`0edee853c64f2aee537ffeade7f479483eb0de9567394cd363d09f8d64fe4f39`。

Auto_Dps 的第三方说明记载，赞赏码资源最初来自 [IdleLegions-AutoAbyss](https://github.com/weixiao030/IdleLegions-AutoAbyss)，参考提交 `46573b15f8b95383ce8ddc162638568ab54c0305`。对应许可保留于 `licenses/IdleLegions-AutoAbyss-Apache-2.0.txt`。图片未更改收款内容；赞赏完全自愿，不解锁功能。资源来源与许可在本文及 licenses/ 中保留。

声明交互及项目支持区参考 Auto_Dps 的产品形式；本项目以原生 HTML/CSS/JavaScript 独立实现，没有复制其 React 实现代码。Auto_Dps 自有代码的使用许可不被本项目 Apache-2.0 许可替代。

## Windows 发行包

- Python 3.10 运行时与标准库：Python Software Foundation 及其许可，见 `licenses/Python.txt`。
- Tcl/Tk：用于本机目录选择窗口，相关许可见 `licenses/Tk.txt`；Python 许可中保留相关历史许可说明。
- PyInstaller 6.15.0：用于封装独立 EXE，许可及 bootloader 例外见 `licenses/pyinstaller-COPYING.txt`。hooks-contrib 许可见同目录对应文件。

Pillow、Playwright、Node.js 和独立 Godot 测试引擎只用于开发检查，不随本项目 Windows 包分发。前端不使用外部框架或远程字体。

## 游戏资源

游戏程序、恢复源码、提取的图标与美术、存档、用户策略、配对密钥和会话资料不随仓库及发行包分发。背包图标仅在用户本机从其已安装游戏读取，保存在本地私有目录。
