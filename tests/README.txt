回归测试（Ubuntu 24.04 / 系统 Python 3.12）

依赖：本程序的 GTK3、Pillow、Cairo、GStreamer，以及 Xvfb、Openbox。
缺少测试桌面组件时，可执行：sudo apt install xvfb openbox

在软件目录运行：
  /usr/bin/python3 tests/run.py

测试不连接正在使用的桌面。运行器创建独立的 X11 显示、临时设置目录，
每组测试在独立进程中运行；结束后关闭测试桌面并清除测试图片和录像。
OCR 测试还需已安装 Tesseract 及 chi_sim、eng 模型。
无需修改 HOME，也不修改用户的自动启动、截图目录和全局快捷键设置。
不要直接在当前 DISPLAY 下运行单个测试文件。

八组回归：
test_storage.py：写入失败、已有文件保护、透明背景、损坏设置、缓存及录像错误。
test_edges.py：关闭/取消保存、输入框快捷键、绘制边界、滚动及设置异常。
test_workflows.py：编辑导出、六种截图、滚动拼接、真实录屏和视频解码。
test_toolbar.py：6px红条、位置恢复、悬停展开、F3、输出目标和自动保存。
test_input.py：九种选区取消、鼠标释放、连续截图、异常恢复和下一次点击。

test_ocr.py：真实 F4 → 框选中英文样例 → 自动复制；取消、空图和失败保留剪贴板。

单独运行某组：
  /usr/bin/python3 tests/run.py test_storage.py

保存使用合成样例生成的界面预览：
  /usr/bin/python3 tests/run.py --previews /tmp/lw-previews

测试不包含真实麦克风、系统声音、多屏/高DPI组合和实物打印机。
滚动拼接对动态网页、固定标题、虚拟列表不保证成功；Wayland 当前不支持。

OCR质量回归：test_ocr_quality.py 验证双栏顺序、空图及复查失败保护。
固定质量样例：ocr_fixtures.py，27张开发图与27张保留验证图，均为合成图。
指标：Unicode NFC后去除空白，保留标点/大小写，使用字符编辑距离；不是OCR引擎置信度。
复现2.4对照：
  /usr/bin/python3 tests/ocr_benchmark.py --module tests/ocr_baseline.py --split holdout --out /tmp/lw-ocr-before
复现当前版本：
  /usr/bin/python3 tests/ocr_benchmark.py --split holdout --out /tmp/lw-ocr-after
先安装可选高精度模型才能复现本机的完整复查配置。
样例使用系统字体 Noto Sans CJK SC、Noto Serif CJK SC、DejaVu Sans。
基准程序只生成合成图，不连接或截取用户桌面；输出逐图结果JSON、CSV和样例PNG。

个性化设置回归 test_customization.py 验证实际 Ctrl＋滚轮缩放、设置界面的快捷键和图标排序、隐藏、冲突及保存失败恢复。
