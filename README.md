# 文枢 Wenshu

本地运行的双语论文阅读与修订工作台。支持 PDF 和 LaTeX 项目，在同一界面完成中英对照阅读、选句批注、定向改写、差异审阅和源稿副本编辑。

## 最新更新

- 暖灰米色工作台、陶土色强调和深色文字，统一放大界面字号。
- 左侧章节导航、中间论文正文、右侧批注与改写建议；支持专注阅读和原 PDF 对照。
- 调整导入入口，使用原生文件选择控件，避免转发点击导致文件选择窗口无法打开。
- 支持 PDF、单个 `.tex`、项目 ZIP 和完整项目文件夹。

## Windows 使用

从 Releases 下载 Windows 压缩包，解压后双击 `文枢.exe`，浏览器会打开 <http://127.0.0.1:18761/>。程序在可执行文件旁建立 `.data` 文件夹，保存论文、译文、批注和源稿副本。重复启动会复用正在运行的服务。

首次打开可点击“先用示例体验”。导入论文后，点击英文句子或整段添加批注。未关联 LaTeX 源稿的 PDF 可以阅读、批注和导出改写建议；编辑及自动写回需要关联的源稿项目。

## 源码运行

需要 Python 3.10 或更新版本。

```sh
python -m venv .venv
# Windows
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python launch.py
# macOS / Linux
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python launch.py
```

LaTeX 编译需要另外安装 TeX Live 或 TinyTeX，并将所用编译器加入 PATH。只阅读 PDF、批注及使用 AI 服务不需要安装 LaTeX。内置示例位于 `samples/`。

## AI 服务

点击“AI 服务设置”，填写兼容 OpenAI Chat Completions 的 API 地址、模型名及密钥。地址和模型保存在本机；密钥仅保存在当前进程内存中，重启后需重新输入。翻译和改写会将相应正文及所选上下文发送到配置的服务。

改写先生成建议与差异预览，审阅确认后才能写入源稿副本。自动写回仅接受当前源稿版本中能够唯一定位的文本；复杂宏、公式或重复文字可能需要人工处理。

## 开发与打包

```sh
python -m unittest discover -s tests -v
node tests/test_artifact_layout.cjs
node tests/test_reference_layout.cjs
```

Windows：运行 `packaging/build_windows.ps1`。macOS：在 Mac 上运行 `packaging/build_macos.sh`。桌面包不会包含本机 `.data`。

主要模块：`app.py` 提供本地服务；`parser.py`、`math_layout.py` 处理 PDF 排版；`writing.py`、`source_mapping.py` 和 `latex_project.py` 负责批注、差异与源稿定位；`context_manager.py` 和 `batch_rewrite.py` 管理上下文及批量改写；`static/` 为前端。

## 当前限制

扫描 PDF 暂无 OCR。复杂图表和数学版式请用“核对原 PDF”确认。旧版本 PDF 上的批注不会自动迁移到重新编译后的版本。macOS 打包脚本需在对应平台运行，应用未签名。

KaTeX 随前端资源提供，其许可证见 `static/vendor/katex/LICENSE`。其他依赖按各自许可证分发。
