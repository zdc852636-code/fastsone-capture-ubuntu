# fastsone capture-LW-ubuntu

一款面向 Ubuntu 24.04 X11 桌面的独立截图工具，采用经典悬浮工具栏和多标签编辑器。支持区域截图、滚动长截图、图片标注、屏幕录像和本地中英文 OCR。界面和图标由本项目实现，与 FastStone 官方无关联。

## 安装与启动

在 Ubuntu on Xorg 会话中安装依赖，再在本项目目录运行个人安装程序。

```sh
sudo apt install python3-gi python3-gi-cairo python3-cairo python3-pil gir1.2-gtk-3.0 libxtst6 \
  gir1.2-gstreamer-1.0 gstreamer1.0-x gstreamer1.0-plugins-good gstreamer1.0-plugins-base \
  gstreamer1.0-pulseaudio tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-eng
/usr/bin/python3 install.py
```

首次安装会创建应用菜单入口并启用登录自启。也可以直接在源码目录运行 `/usr/bin/python3 capture.py`。系统运行依赖由 Ubuntu 软件源提供。

## 使用

- 按 **F3** 框选截图，按 **F4** 框选文字。识别结果自动复制到剪贴板，按 Esc 取消框选。
- 在编辑器画布上按 **Ctrl＋滚轮** 缩放图片，每个标签保留自己的缩放比例。右上角可切换到“适合窗口”。
- 打开 **设置 → 快捷键**，输入新组合，例如 `Ctrl+Alt+K` 或 `F8`。留空可停用，点击“应用”后生效。
- 打开 **设置 → 图标布局**，选择悬浮工具栏或编辑器工具栏。拖动条目或用上下按钮排序，勾选要显示的工具。
- 可选的高精度 OCR 模型通过 `/usr/bin/python3 tools/install_ocr_models.py` 安装。日常识别全部在本机运行。

完整操作及卸载步骤见 [使用说明](README.txt)。测试方法见 [测试说明](tests/README.txt)。

## 许可

项目源码使用 [MIT 许可](LICENSE)。个人离线安装包可附带 Ubuntu 的 Cairo 适配组件，许可见 [第三方组件声明](vendor/COPYRIGHT-gi-cairo)。单独安装的官方 OCR 模型使用 Apache-2.0 许可，模型目录中附有完整许可和来源清单。
