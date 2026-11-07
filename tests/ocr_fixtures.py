"""Fixed synthetic OCR corpus: 27 development + 27 held-out cases, no user data."""
import io
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

SANS='/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
SERIF='/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc'
LATIN='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
TEXTS={
 'dev':{
  'normal':['屏幕截图支持中文识别。\n选择文字区域，结果自动复制。','今天下午三点开会。\n请带上项目说明和测试记录。','保存图片前，请检查文件名称。\n不要覆盖尚未备份的原始资料。'],
  'small':['文件名称：季度总结\n保存位置：文档目录','快速截图和文字识别\n按下快捷键即可开始','网络连接正常\n当前任务已经完成'],
  'dark':['深色界面也可以识别文字。\n识别结果保存在剪贴板中。','终端提示：操作成功\n请继续执行下一步任务','阅读模式采用浅色文字。\n截图后可以直接复制内容。'],
  'contrast':['灰色说明文字需要保持清晰。\n请避免选中阴影和装饰图案。','蓝色背景上的白色文字\n也需要正确判断明暗方向','彩色提示：连接已经恢复。\n请重新打开当前页面。'],
  'english':['Open the folder and select an image.\nCopy the recognized text to the clipboard.','Release notes: faster capture and safer saves.\nPlease check the output before sharing.','The quick brown fox jumps over the lazy dog.\nLocal recognition works without a cloud service.'],
  'mixed':['Ubuntu 24.04 截图工具\n按 F4 识别，按 Ctrl+V 粘贴。','项目名称：LW Capture\n版本 Version 2.4，状态 Ready。','Python 支持中文和 English。\n保存为 PNG、JPEG 或 PDF 文件。'],
  'numeric':['订单编号：20261028-1048\n数量：12，单价：39.50，合计：474.00','账号标记：O0I1-lL8B\n日期：2026-10-28，时间：08:35','Contact: hello@example.com\nURL: https://example.com/docs?id=42'],
  'columns':['第一部分\n截图保存到本地。\n识别结果自动复制。\n用户可以继续编辑。\f第二部分\n文字支持中英文。\n取消时保留剪贴板。\n操作完成后会提示。','Capture options\nSelect a screen region.\nKeep the text readable.\nSave the original image.\fOCR options\nChoose both languages.\nReview the output text.\nCopy it to a document.','项目进度\n设计工作已经完成。\n开发任务正在进行。\n测试报告即将提交。\f下一步计划\n检查软件兼容性。\n修复已经发现的问题。\n准备新的安装说明。'],
  'degraded':['轻微模糊的文字仍然需要核对。\n准确率取决于原始图片质量。','压缩图片可能损失细节。\nNumbers: 1234567890','缩小后的页面文字不够清晰。\n请尽量使用原始分辨率。'],
 },
 'holdout':{
  'normal':['明天上午九点讨论新方案。\n请提前阅读材料并整理问题。','任务完成后可以关闭窗口。\n重新启动不会删除已保存图片。','本地识别不需要上传屏幕内容。\n重要数字和姓名请再次核对。'],
  'small':['识别语言：简体中文\n处理状态：等待输入','显示比例与屏幕分辨率\n会影响小字号的识别效果','打开设置并选择目标文件夹\n保存成功后显示通知'],
  'dark':['夜间模式可以减轻屏幕亮度。\n请框选完整的句子再开始识别。','日志信息：文件写入成功\n已经完成全部检查','当前页面使用深色主题。\n浅色字形应当保持完整。'],
  'contrast':['浅灰色字幕包含重要说明。\n请检查标点是否被正确识别。','通知消息：软件更新已经完成。\n下次登录后自动启动。','绿色标签：设备运行正常\n剩余空间足够保存截图'],
  'english':['Please review the revised document tomorrow.\nEvery change should have a clear explanation.','Screenshot recognition stays on this computer.\nPress Escape to cancel the selection.','A reliable tool preserves the original data.\nSmall characters need careful preprocessing.'],
  'mixed':['Linux 桌面使用 X11 会话。\n快捷键 F3 截图，F4 识字。','文件 Report_2026.pdf 已保存。\n请使用 Ctrl+C 和 Ctrl+V 复制粘贴。','状态 Status: Finished\n中文识别与 English OCR 可以同时使用。'],
  'numeric':['发票号码：81730462\n数量：25，单价：18.80，金额：470.00','设备代码：B8S5-Z2O0\n温度：23.6，湿度：48%，序号：0017','Email: support@example.org\nURL: https://example.org/help?q=linux'],
  'columns':['阅读顺序\n首先阅读左边内容。\n然后继续阅读右栏。\n每段保持原来的顺序。\f操作提示\n按下快捷键开始框选。\n松开鼠标自动识别。\n识别完毕后粘贴文字。','Project review\nVerify the installation.\nTest common workflows.\nDocument known issues.\fNext release\nImprove language support.\nReduce recognition errors.\nPublish clear instructions.','第一组任务\n整理目录中的文件。\n删除已经失效的缓存。\n保留必要的运行组件。\f第二组任务\n测试常用的快捷键。\n核对识别后的文字。\n记录实际测试结果。'],
  'degraded':['有些形近字可能被错误识别。\n请核对文字中的关键内容。','图像经过压缩后可能产生噪声。\nInvoice: 58491726','小字和模糊图片无法保证准确。\n原图越清楚，识别越可靠。'],
 }}


def cases(split):
    for group,examples in TEXTS[split].items():
        for i,text in enumerate(examples):
            sizes={'normal':[20,28,40],'small':[12,14,16],'dark':[16,22,30],
                   'contrast':[18,22,26],'english':[14,20,30],'mixed':[16,22,32],
                   'numeric':[16,20,26],'columns':[18,18,20],'degraded':[18,20,16]}
            size=sizes[group][i]
            font=LATIN if group=='english' or (group=='columns' and i==1) else SANS
            # Alternate Chinese serif typeface only in the held-out set.
            if split=='holdout' and i==1 and font==SANS and group not in ('small','numeric'):font=SERIF
            yield dict(id=f'{split}-{group}-{i+1}',split=split,group=group,text=text,size=size,font=font,variant=i)


def render(case):
    font=ImageFont.truetype(case['font'],case['size'],index=2 if case['font'].endswith('.ttc') else 0)
    group,i=case['group'],case['variant'];bg,fg='white','#161616'
    if group=='dark':bg,fg=('#20242b','#eceff4')
    if group=='contrast':bg,fg=[('#f5f5f5','#a0a0a0'),('#165ba8','#ffffff'),('#e4f2e8','#237748')][i]
    blocks=case['text'].split('\f');line_height=round(case['size']*1.55)
    widths=[max(round(font.getlength(line)) for line in block.splitlines()) for block in blocks]
    margin=10 if group=='small' else 18;gutter=90
    height=max(len(block.splitlines()) for block in blocks)*line_height+margin*2
    image=Image.new('RGB',(sum(widths)+gutter*(len(blocks)-1)+2*margin,height),bg)
    draw=ImageDraw.Draw(image);x=margin
    for block,width in zip(blocks,widths):
        for row,line in enumerate(block.splitlines()):draw.text((x,margin+row*line_height),line,font=font,fill=fg,anchor='lt')
        x+=width+gutter
    if group=='degraded':
        if i==0:image=image.filter(ImageFilter.GaussianBlur(.65))
        elif i==1:
            stream=io.BytesIO();image.save(stream,'JPEG',quality=35);stream.seek(0);image=Image.open(stream).convert('RGB')
        else:image=image.resize((round(image.width*.72),round(image.height*.72)),Image.Resampling.BILINEAR)
    return image
