# Reference Studio

**参考图 → Florence2 提示词 → IP-Adapter 图像生成。**

A local web tool that captions a reference image with Florence2, then generates a new image from both the caption and the same reference using IP-Adapter PLUS + Stable Diffusion 1.5 in ComfyUI.

[English guide](README.en.md) · [真实测试记录](examples/test-report.json) · [安装的模型清单](models.json)

| 参考图 | 生成结果 |
| --- | --- |
| ![Reference](examples/reference.png) | ![Generated](examples/generated.png) |

## 功能

- 上传图片后，一键完成识图、提示词组合、参考图引导出图。
- 支持“只生成提示词”，编辑后再出图。补充创作方向会放在自动描述前。
- 调整参考强度、种子、步数、尺寸、负向提示词和 SD 1.5 checkpoint。
- 展示原始描述、阶段状态，下载 PNG 和包含参数/API 工作流的 JSON。
- 网页刷新后可恢复当前任务状态；服务重启后历史状态不保留，输出文件保留。
- 配套 ComfyUI 画布工作流与 API 工作流，可脱离网页使用。
- 模型在你配置的 ComfyUI 中运行；默认只连接本机，不需要云端 API key。

## 前提

需要已经安装的 **ComfyUI**、可运行 SD 1.5 的计算设备，以及 Python 3.10+。本项目是独立 HTTP 客户端，不修改 ComfyUI 核心，不打包模型权重。

真实推理测试环境：Apple M5、16 GB 统一内存、macOS、Python 3.12.15、PyTorch 2.15.0、ComfyUI 0.45.0。Windows / Linux / NVIDIA 的真实推理尚未验证；CI 仅测试客户端逻辑。

## 1. 安装 ComfyUI 节点

在 **ComfyUI 的 Python 环境**中执行，已安装时不要重复克隆：

```bash
cd /path/to/ComfyUI/custom_nodes
git clone https://github.com/kijai/ComfyUI-Florence2.git
git clone https://github.com/cubiq/ComfyUI_IPAdapter_plus.git
python -m pip install -r ComfyUI-Florence2/requirements.txt
```

本次验证的版本如下。新版接口可能变化；复现时可在对应仓库执行 `git checkout <commit>`。

| 组件 | 已测试 commit |
| --- | --- |
| ComfyUI | `74eb0c4b8a1a894e7210326882a8d9a016e37ccb` |
| ComfyUI-Florence2 | `9ece3de914214c5f581d725167bc9d0eeb0d1120` |
| ComfyUI_IPAdapter_plus | `a0f451a5113cf9becb0847b92884cb10cbdec0ef` |

ComfyUI 及节点分别从上游安装并保留各自许可证。本项目不复制它们的实现。

## 2. 安装配套模型

| 模型 | 放置位置（相对 ComfyUI） |
| --- | --- |
| [SD 1.5 FP16](https://huggingface.co/Comfy-Org/stable-diffusion-1.5) | `models/checkpoints/v1-5-pruned-emaonly-fp16.safetensors` |
| [IP-Adapter PLUS SD15](https://huggingface.co/h94/IP-Adapter) | `models/ipadapter/ip-adapter-plus_sd15.safetensors` |
| [CLIP Vision H](https://huggingface.co/Comfy-Org/Wan-2.1/tree/main/split_files/clip_vision) | `models/clip_vision/CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors` |
| [Florence-2-base](https://huggingface.co/microsoft/Florence-2-base) | `models/LLM/Florence-2-base/`（权重、config、tokenizer、preprocessor 等） |

仓库提供下载脚本，下载约 4 GB，按清单校验 SHA-256。先安装下一步的客户端依赖，再运行：

```bash
python scripts/download_models.py --comfy-dir /path/to/ComfyUI
```

脚本只下载所列模型，不安装节点；已有文件通过哈希验证后会跳过。下载中断后重新执行会重新下载未完成的单个文件。模型许可证以对应模型卡为准，MIT 许可证不适用于第三方模型权重。

重启 ComfyUI。Apple Silicon 建议按本次测试配置启动：

```bash
cd /path/to/ComfyUI
python main.py --listen 127.0.0.1 --port 8188 --fp32-vae
```

## 3. 启动工具

```bash
git clone https://github.com/lsy1250732908-eng/reference-image-studio.git
cd reference-image-studio
python -m venv .venv
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

打开 **http://127.0.0.1:7860**。如 ComfyUI 端口不同：

```bash
python app.py --comfy-url http://127.0.0.1:8189 --port 7861
```

网页默认只监听本机，没有账号系统，不适合作为公开网络服务。若指定远程 ComfyUI，上传图片和提示词会发给该服务器。

## 使用

1. 上传 PNG、JPG 或 WebP。上限 15 MB / 2500 万像素；自动纠正 EXIF 方向、转 RGB，并缩小至最长边 2048。
2. 可填写英文创作方向，例如 `watercolor illustration, soft natural light`。
3. 点击“一键识图并生成”，等待两个阶段完成。
4. 或先点击“只生成提示词”，编辑描述，再点击“使用当前提示词出图”。这个模式使用文本框的完整内容，不会再次追加创作方向。
5. 下载图像与参数。结果也保存在本项目 `outputs/`，ComfyUI 中另有一份生成图片。

默认：512×512、20 步、CFG 7、Euler、种子 42、参考强度 0.6。每次一个任务，等待上一个完成后再提交。首轮加载模型较慢，16 GB 设备建议保持 512×512。

**能力边界：** Florence2 生成画面描述，不还原原图提示词，也不负责自动理解和重写编辑指令。补充方向与原描述可能冲突，例如“红衣”与“蓝衣”；需要在提示词框手动删除冲突描述。IP-Adapter 不保证人物身份、构图或某项文字修改精准一致。想让文字影响更大，尝试降低参考强度。

## ComfyUI 工作流

- `workflows/reference-studio.json`：拖入 ComfyUI 画布，选择参考图后运行。原始 Florence2 caption 直接接入正向提示词；需要更灵活的文字编辑时使用网页。
- `workflows/reference-studio-api.json`：给 ComfyUI `/prompt` 接口使用的 API 格式，不是画布文件。

网页分两次提交任务，使描述能够先显示和编辑；画布工作流把两部分连成一次执行。两者都把同一参考图送入 Florence2 和 IP-Adapter。

## 验证

```bash
python -m unittest discover -s tests -v
# 启动 ComfyUI 和 app.py 后执行真实模型测试：
python scripts/smoke_test.py examples/reference.png --output outputs/smoke
```

单元测试覆盖引用图连接、提示词传递、参数验证、上传规范化、错误传播、超时与任务互斥。真实测试通过 HTTP 上传、运行两个模型、下载并校验 512×512 非空图像，同时验证生成提示词确实包含 Florence2 描述。它不保证每张输入图都获得符合审美或编辑要求的结果。

本次完整流程用时 **365.27 秒**（512×512，20 步，种子 73，参考强度 0.55）。

实际测试详情见 [examples/test-report.json](examples/test-report.json)。展示参考图是本机先前由 SD 1.5 生成的虚构人物插画，不是个人照片。

## 常见问题

- **连接失败**：确认 ComfyUI 已启动，端口和 `--comfy-url` 一致。
- **缺少节点/模型**：按错误提示安装并重启 ComfyUI。请选择 SD 1.5 系列 checkpoint，当前不支持 SDXL、Flux 或 FaceID。
- **内存不足**：关闭其他占内存应用，使用 512×512；Florence2 默认 FP32，并在描述完成后卸载。
- **任务失败**：界面显示 ComfyUI 返回的错误；同时检查 ComfyUI 终端。
- **超时**：客户端最多等待 30 分钟，超时不会取消 ComfyUI 队列。到 ComfyUI 检查任务，避免重复提交。关闭本网页也不会取消已经提交的任务。

## 许可与致谢

客户端原创代码：MIT。依赖的 ComfyUI、Florence2 节点、IP-Adapter 节点和模型权重遵循各自上游许可证；请查阅上游仓库和模型卡。

- [ComfyUI](https://github.com/Comfy-Org/ComfyUI) / [HTTP API 文档](https://docs.comfy.org/development/comfyui-server/comms_routes)
- [Microsoft Florence2](https://huggingface.co/microsoft/Florence-2-base) / [kijai ComfyUI-Florence2](https://github.com/kijai/ComfyUI-Florence2)
- [Tencent IP-Adapter](https://github.com/tencent-ailab/IP-Adapter) / [cubiq ComfyUI_IPAdapter_plus](https://github.com/cubiq/ComfyUI_IPAdapter_plus)
