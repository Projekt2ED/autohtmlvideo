# autohtmlvideo

`autohtmlvideo` 是一个面向 `9:16` AI 资讯短视频的本地流水线，固定提供三条命令：

- `collect`: 抓取 5 个固定源，过滤近 36 小时内的热点，聚合成候选池
- `review`: 启动本地审核页，人工选中 1 条热点进入生成
- `build <story_id>`: 生成 `video.mp4`、`cover.png`、`subtitles.srt`、`title.txt`、`description.txt`、`sources.json`

## 环境

- Windows
- Python 3.12+
- 已安装 Playwright 浏览器
- 可访问外网

## 安装

```powershell
pip install -e .
playwright install chromium
```

## 使用

```powershell
autohtmlvideo collect
autohtmlvideo review
autohtmlvideo build <story_id>
```

也可以直接：

```powershell
python -m autohtmlvideo collect
python -m autohtmlvideo review
python -m autohtmlvideo build <story_id>
```

## 输出目录

所有运行产物默认写入 `workspace/`：

- `workspace/raw/`: 原始抓取结果
- `workspace/candidates/`: 候选池和 `latest.json`
- `workspace/approved/`: 审核通过的条目
- `workspace/builds/`: 每次构建的成片包

## 实现说明

- 官方源优先用 RSS/HTML 解析，微软源通过 Playwright 浏览器抓取
- 语音默认优先使用 `edge-tts`，失败后降级到 Windows `System.Speech`
- 视频正文、场景动画、字幕展示都由 HTML 模板驱动，最终用 Playwright 录制，再用 ffmpeg 合成 MP4
- `sources.json` 会保留原始出处，方便复核或导入剪映继续精修

