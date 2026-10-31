# 批量提取视频文案 v6

把一批视频/音频丢进去，用 Whisper 逐个转写成文本，可选加标点、繁转简，最后统一导出 txt / srt / json，并把整批结果汇总成一张 Excel。

Windows 桌面程序，Python + tkinter 写的，**开箱即用的 exe 在 [Releases](../../releases)** 里（免安装，解压即用）。

## 功能

- 批量选择视频/音频文件或整个文件夹，按队列顺序处理
- Whisper 模型可选：tiny / base / small / medium / large-v3-turbo（默认 large-v3-turbo）
- 自动调用 ffmpeg 抽音频并转 16 kHz 单声道 wav
- 可选 funasr ct-punc 标点模型，给纯文本补句读
- 可选繁转简（opencc）
- 导出 txt / srt / json，可按「跳过已存在」断点续跑
- 处理进度、逐文件日志、失败不中断整批
- 整批结果汇总成 Excel（文件名 + 文案）
- 缺失的模型会自动下载，支持断点续传和多镜像回退

## 直接使用（exe）

到 [Releases](../../releases) 下载 `whisper-batch-transcript-v6.0.0-win64.zip`，解压后双击 `批量提取视频文案工具v6.exe`。

解压后的目录必须完整保留：

```
批量提取视频文案工具v6/
├── 批量提取视频文案工具v6.exe
├── _internal/          ← 运行时依赖，删了就打不开
├── ffmpeg.exe
├── ffprobe.exe
└── models/
    └── ct-punc/        ← 标点模型，已随包提供（283 MB）
```

包里**已经带了标点模型 `ct-punc`**（278 MB 的 `model.pt`），开箱就能补句读，不用联网下载。

Whisper 语音模型（默认 large-v3-turbo，1.6 GB）没有打进包——太大，而且多数人只用得到其中一档。第一次转写时程序会自动下到 `models\`，支持断点续传和多镜像；已有模型就直接放进 `models\`。

> 日志写在 `%USERPROFILE%\whisper_v6.log`，出问题时先看这里。

## 源码运行

```bash
pip install -r requirements.txt
python 批量提取视频文案工具v6.py
```

`requirements.txt` 里只有核心依赖，**torch 请按自己的 CUDA/CPU 环境单独装**：

```bash
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
```

## 打包成 exe

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```

产物在 `dist\批量提取视频文案工具v6\`。用的是 **onedir**，不是单文件——这套依赖（torch + transformers + funasr）单文件打包会到 1 GB 以上，每次启动都要先解压到 `%TEMP%`，冷启动几十秒，不划算。

构建产物约 1.29 GB / 7600+ 个文件。

## 项目结构

```
批量提取视频文案工具v6.py   启动入口（只做 freeze_support + 调 main）
whisper_tool/
├── gui/          主窗口、日志面板、任务控制器
├── core/         转写、ffmpeg、模型管理、标点、导出、汇总
├── config.py     配置读写
├── deps.py       依赖探测
├── downloader.py 带重试/续传的模型下载
└── paths.py      路径解析（源码 / 冻结环境 / 模型目录）
packaging/
├── v6.spec        PyInstaller 配置
├── rthook_gui.py  运行时补丁（见下）
└── build.ps1     一键打包
```

## 打包时踩过的两个坑

都写在 `packaging/rthook_gui.py` 里了，改打包配置时别把它删掉。

**1. 转写时控制台一闪一闪**

`whisper/audio.py` 解码音频用的是裸的 `subprocess.run(["ffmpeg", ...])`，没带 `CREATE_NO_WINDOW`。GUI 程序自身没有控制台，Windows 就会给这个子进程新开一个控制台窗口——每个视频闪一次。

修法：运行时钩子在启动时把 `subprocess.Popen` 的默认行为改成隐藏窗口，所有库（whisper、funasr、modelscope）的子进程一并生效。

**2. 打包后标点模型加载失败**

日志报 `ct-punc 加载失败: could not get source code`。原因是 funasr 的 `register.py` 用 `inspect.getsourcelines()` 取类定义位置做注册元信息，而 PyInstaller 打出来的包里没有源码，这一步直接抛 `OSError`，整个标点链路被禁用。

修法：钩子里给 `inspect.getsourcelines` 加兜底，拿不到源码时返回占位行号。

## 说明

- 转写质量取决于选用的模型和音源质量，large-v3-turbo 在 CPU 上大约 30–90 秒/分钟音频
- `models/` 目录不纳入版本库，模型按需下载或自行放置
- 仅用于合法的语音转写用途
