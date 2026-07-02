# EPUB L3 字符 / 字图转换工具

本工具面向以下两类需求：

**需求一：EPUB 阅读器不支持 L3 汉字显示**
EPUB 中包含 GB 18030-2022 三级汉字（Unicode 扩展B～J区，码点 U+20000 以上），在部分阅读器中显示为方块或乱码。使用 `-char2img` 模式，可将这些字符逐一渲染为 PNG 图片并嵌入 EPUB，确保在任意设备上正常显示；使用 `-img2char` 模式可将其还原为原始文字。

**需求二：EPUB 中的图片字需要替换为可检索的文字**
EPUB 中部分汉字以图片形式呈现（`<img src="...">`），无法被搜索或复制。使用 `-remap` 模式，按预先准备的图片→汉字映射表（`figures/` 目录），将这些图片批量替换为对应的 Unicode 文字。

---

## 功能模式

| 命令参数 | 功能 | 输出文件 |
|---------|------|---------|
| `-char2img` | 将 EPUB 中的 L3 汉字渲染为 PNG 图片，原地替换为 `<img>` 标签 | `*_char2img.epub` |
| `-img2char` | 将 `-char2img` 生成的 `<img alt="L3汉字">` 还原为原始 L3 文字 | `*_img2char.epub` |
| `-remap` | 按 `figures/` 目录中的图片映射，将 EPUB 中的图片替换为对应汉字文本 | `*_remap.epub` |

---

## 使用方式

```
python epub_charImg_converter.py -char2img
python epub_charImg_converter.py -img2char
python epub_charImg_converter.py -remap
```

运行后按提示输入 EPUB 文件路径或文件夹路径（可直接拖入），支持：
- 单个 `.epub` 文件
- 文件夹（递归处理其中所有 `.epub` 文件）

---

## 环境要求

- Python **3.8+**（推荐 3.10 及以上）

## 依赖安装

```
pip install -i https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple beautifulsoup4 lxml Pillow fontTools
```

---

## 字体文件（`-char2img` 模式必需）

使用**文津宋体**渲染 L3 汉字图片，字体文件已随本脚本一同提供：

```
WenJinMincho-OTF/
├── WenJinMinchoP0-Regular.otf
├── WenJinMinchoP2-Regular.otf
└── WenJinMinchoP3-Regular.otf
```

如需更新字体，可从以下地址下载替换：https://github.com/takushun-wu/WenJinMincho/releases/

---

## `figures/` 目录结构（`-remap` 模式必需）

`figures/` 支持两种目录结构，脚本按优先级自动选择：

### 模式A：按书名隔离（推荐，多本处理时避免同名图片冲突）

在 `figures/` 下创建与 **EPUB 文件名（不含扩展名）** 完全一致的子目录，每本书的图片映射相互独立：

```
figures/
├── 书名A/                ← 与 EPUB 文件名（不含 .epub）完全一致
│   ├── 𠀀/
│   │   ├── abc.jpg       ← 图片文件名需与 EPUB 中 <img src> 文件名一致
│   │   └── def.jpg
│   └── 𠀁/
│       └── xyz.png
├── 书名B/
│   ├── 𠀀/
│   │   └── abc.jpg       ← 与书名A中同名，但属于不同书，不会冲突
│   └── ...
└── ...
```

### 模式B：通用映射（向后兼容，单本或所有书共用同一套映射时使用）

直接在 `figures/` 根目录下放置汉字子目录：

```
figures/
├── 𠀀/          ← 子目录名为对应的汉字字符
│   ├── abc.jpg  ← 图片文件名需与 EPUB 中 <img src> 文件名一致
│   └── def.jpg
├── 𠀁/
│   └── xyz.png
└── ...
```

### 选择逻辑

脚本处理每本 EPUB 时，自动判断：
1. 若 `figures/<EPUB文件名>/` 子目录存在 → 使用**模式A**（书名隔离）
2. 否则 → 回退到**模式B**（通用映射）

映射规则：`<img src="...abc.jpg">` → 替换为对应汉字（如 `𠀀`）

---

## `config.json` 配置说明

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `font_size` | 整数 | `256` | 渲染字号（像素） |
| `image_size` | 数组 | `[256, 256]` | 输出图片尺寸（宽×高，像素） |
| `font_files` | 字符串数组 | 见下 | 字体文件路径（相对脚本目录），按顺序查找 |
| `figures_dir` | 字符串 | `"figures"` | `-remap` 模式的图片映射目录（相对脚本目录） |
| `l3_ranges` | 对象数组 | 完整L3范围 | L3 汉字 Unicode 码点范围，通常无需修改 |

`config.json` 缺失或字段缺失时，自动使用内置默认值，不影响运行。

---

## 注意事项

- `-char2img` 模式会跳过 `<title>` 元素中的 L3 汉字（不转为图片）
- `-img2char` 模式仅还原 `alt` 属性为 L3 汉字的 `<img>` 标签，不影响其他图片
- 输出文件与源文件同目录，不覆盖源文件

---

## 单元测试

`MWE/` 目录提供三个最小工作示例（MWE），对应三种模式各一个，测试脚本 `MWE/test_mwe.py` 验证各模式的核心行为是否符合预期。

### 运行测试

```
pip install pytest
python -m pytest MWE/test_mwe.py -v
```

### MWE 文件说明

| 文件 | 对应模式 | 内容 |
|------|---------|------|
| `MWE/test_char2img.epub` | `-char2img` | 含 2 个 L3 汉字（𫖯、𪮤）的段落 |
| `MWE/test_img2char.epub` | `-img2char` | 含 3 个 L3 字图（`<img alt="L3字" src="U??????.png">`）的段落 |
| `MWE/test_remap.epub` | `-remap` | 含 6 个图片字（`<img src="10CFigure-*.jpg">`）的段落，映射表位于 `figures/test_remap/` |

### 测试覆盖项

**`-char2img` 模式（10 项）**
- L3 字符不再以文本节点出现（仍保留在 `alt` 属性中）
- 每个 L3 字符对应的 `<img>` 标签已插入，`alt` 保留原字
- PNG 图片已打包进 EPUB 并注册到 OPF manifest
- `<title>` 内容未被替换；非 L3 文本完整保留
- XML 声明和 DOCTYPE 完整保留

**`-img2char` 模式（7 项）**
- L3 字符以正确数量还原为文本（`𣾧`×1、`𠇑`×2）
- 原有 L3 `<img>` 标签已移除
- OPF manifest 中对应 PNG 条目已清除
- 周围文本完整；XML 声明和 DOCTYPE 完整保留

**`-remap` 模式（10 项）**
- `𩅦` 出现 3 次（对应 0001/0002/0003.jpg）；`斅` 出现 3 次（对应 0007/0008/0009.jpg）
- 6 个 `<img>` 标签全部替换；`figures/` 中存在但 HTML 未引用的图片不影响输出
- 自动使用 `figures/test_remap/` 书名子目录（模式A）
- 周围文本完整；XML 声明和 DOCTYPE 完整保留
