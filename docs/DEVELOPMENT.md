# 开发文档

[返回产品介绍](../README.md)

本文介绍文枢的源码运行、测试与桌面应用打包方式。Windows 应用下载及使用说明见 [README](../README.md#安装与使用)。

## 环境要求

- Python 3.10 或更高版本。
- Node.js：仅用于正文布局测试。
- TeX Live 或 TinyTeX：仅用于 LaTeX 项目编译，编译器需加入 PATH。

## 从源码运行

下载源码包，或克隆仓库后创建虚拟环境：

```sh
git clone https://github.com/feedy-hub/wenshu.git
cd wenshu
python -m venv .venv
```

### Windows

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe launch.py
```

### macOS / Linux

```sh
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python launch.py
```

浏览器打开 <http://127.0.0.1:18761/>。可先使用内置示例；`samples/` 提供双栏 PDF、公式及 LaTeX 项目样本。

## 测试

在已安装项目依赖的 Python 环境中运行：

```sh
python -m unittest discover -s tests -v
node tests/test_artifact_layout.cjs
node tests/test_reference_layout.cjs
```

未激活虚拟环境时，请使用 `.venv` 中对应的 Python 可执行文件替代 `python`。

## 项目结构

| 目录 / 模块 | 职责 |
| :--- | :--- |
| `static/` | 阅读界面、批注、上下文设置和源文件编辑交互 |
| `app.py` | 本地 HTTP 服务、数据存储与 API 请求 |
| `parser.py` · `math_layout.py` | PDF 阅读顺序、图表和公式处理 |
| `writing.py` · `source_mapping.py` | 文本定位、修改差异与源文件匹配 |
| `latex_project.py` | 项目副本、编译、历史版本与修改写入 |
| `context_manager.py` · `batch_rewrite.py` | 论文上下文与批量改写任务 |
| `samples/` · `tests/` | 演示材料与回归测试 |

## 桌面应用打包

Windows 使用 `packaging/build_windows.ps1`，macOS 需在 Mac 上运行 `packaging/build_macos.sh`。应用尚未签名，macOS 构建暂未经过运行验证。

打包资源不包含本机 `.data/` 目录。[版本下载页](https://github.com/feedy-hub/wenshu/releases/latest) 提供 Windows 应用和源码包。
