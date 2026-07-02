# epub_charImg_converter.py
# 依赖安装：pip install -i https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple beautifulsoup4 lxml Pillow fontTools

import os
import re
import sys
import json
import shutil
import zipfile
import bisect
import tempfile
from pathlib import Path
from bs4 import BeautifulSoup, Comment, Doctype, Declaration
from PIL import Image, ImageDraw, ImageFont
from fontTools.ttLib import TTFont

# ============================================================
# 默认配置（config.json 缺失时使用）
# ============================================================
SCRIPT_DIR = Path(__file__).parent

DEFAULT_CONFIG = {
    "font_size": 256,
    "image_size": [256, 256],
    "font_files": [
        "WenJinMincho-OTF/WenJinMinchoP0-Regular.otf",
        "WenJinMincho-OTF/WenJinMinchoP2-Regular.otf",
        "WenJinMincho-OTF/WenJinMinchoP3-Regular.otf"
    ],
    "figures_dir": "figures",
    "l3_ranges": [
        {"name": "扩展B",    "ranges": [["0x20000", "0x2A6D6"]]},
        {"name": "扩展B补充","ranges": [["0x2A6D7", "0x2A6DF"]]},
        {"name": "扩展C",    "ranges": [["0x2A700", "0x2B734"]]},
        {"name": "扩展C补充","ranges": [["0x2B735", "0x2B73A"]]},
        {"name": "扩展D",    "ranges": [["0x2B740", "0x2B81D"]]},
        {"name": "扩展E",    "ranges": [["0x2B820", "0x2CEA1"]]},
        {"name": "扩展F",    "ranges": [["0x2CEB0", "0x2EBE0"]]},
        {"name": "扩展G",    "ranges": [["0x30000", "0x3134A"]]},
        {"name": "扩展H",    "ranges": [["0x31350", "0x323AF"]]},
        {"name": "扩展I",    "ranges": [["0x2EBF0", "0x2EE5D"]]},
        {"name": "扩展J",    "ranges": [["0x323B0", "0x33479"]]}
    ]
}


# ============================================================
# 配置加载
# ============================================================

def _parse_range_value(v):
    """将范围端点转为整数，支持十六进制字符串（"0x..."）或整数"""
    if isinstance(v, str):
        return int(v, 16)
    return int(v)


def load_config():
    """从 config.json 加载配置，缺失字段使用默认值"""
    config_path = SCRIPT_DIR / "config.json"
    config = dict(DEFAULT_CONFIG)

    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)
            config.update(user_cfg)
        except Exception as e:
            print(f"[警告] 读取 config.json 失败，使用默认配置: {e}")
    else:
        print("[提示] 未找到 config.json，使用内置默认配置")

    # 字体路径转为绝对路径
    config["font_files"] = [
        str(SCRIPT_DIR / p) for p in config["font_files"]
    ]
    # figures_dir 转为绝对路径
    config["figures_dir"] = str(SCRIPT_DIR / config["figures_dir"])

    return config


# ============================================================
# L3 字符判断（bisect 二分查找）
# ============================================================

def build_l3_checker(l3_ranges):
    """根据配置构建 L3 字符判断函数（使用 bisect 提升性能）"""
    # 将所有区间展平并排序，构建有序的起止点列表
    intervals = []
    for block in l3_ranges:
        for start, end in block["ranges"]:
            intervals.append((_parse_range_value(start), _parse_range_value(end)))
    intervals.sort()
    starts = [s for s, _ in intervals]
    ends   = [e for _, e in intervals]

    def is_l3_character(char):
        cp = ord(char)
        # 找到最后一个 start <= cp 的区间
        idx = bisect.bisect_right(starts, cp) - 1
        if idx >= 0 and cp <= ends[idx]:
            return True
        return False

    return is_l3_character


# ============================================================
# 字体查找（带模块级缓存）
# ============================================================

_font_cmap_cache  = {}  # {font_path: set(code_points)}
_pil_font_cache   = {}  # {(font_path, font_size): ImageFont}


def find_font_for_char(char, font_files):
    """在字体列表中查找支持该字符的字体，带缓存"""
    cp = ord(char)
    for font_path in font_files:
        if not os.path.exists(font_path):
            continue
        if font_path not in _font_cmap_cache:
            try:
                font = TTFont(font_path)
                cmap_set = set()
                for table in font["cmap"].tables:
                    cmap_set.update(table.cmap.keys())
                _font_cmap_cache[font_path] = cmap_set
            except Exception as e:
                print(f"[警告] 加载字体 {font_path} 失败: {e}")
                _font_cmap_cache[font_path] = set()
        if cp in _font_cmap_cache[font_path]:
            return font_path
    return None


def get_pil_font(font_path, font_size):
    """获取 PIL 字体对象，带缓存避免重复加载"""
    key = (font_path, font_size)
    if key not in _pil_font_cache:
        _pil_font_cache[key] = ImageFont.truetype(font_path, font_size)
    return _pil_font_cache[key]


# ============================================================
# 字符渲染为 PNG
# ============================================================

def render_char_image(char, font_path, output_path, font_size, image_size):
    """将字符渲染为透明背景 PNG"""
    try:
        font = get_pil_font(font_path, font_size)
        img  = Image.new("RGBA", tuple(image_size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        bbox   = draw.textbbox((0, 0), char, font=font)
        char_w = bbox[2] - bbox[0]
        char_h = bbox[3] - bbox[1]
        x = (image_size[0] - char_w) // 2 - bbox[0]
        y = (image_size[1] - char_h) // 2 - bbox[1]
        draw.text((x, y), char, font=font, fill=(0, 0, 0, 255))
        img.save(output_path)
        return True
    except Exception as e:
        print(f"[警告] 渲染字符 {char} 失败: {e}")
        return False


# ============================================================
# 公共 EPUB 工具
# ============================================================

def epub_extract(epub_path, temp_dir):
    """解压 EPUB 到临时目录"""
    with zipfile.ZipFile(epub_path, "r") as zf:
        zf.extractall(temp_dir)


def epub_repack(temp_dir, output_path):
    """将临时目录重新打包为 EPUB（mimetype 不压缩且第一个，其余文件排序）"""
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        mimetype = Path(temp_dir) / "mimetype"
        if mimetype.exists():
            zf.write(mimetype, "mimetype", compress_type=zipfile.ZIP_STORED)
        for root, dirs, files in os.walk(temp_dir):
            dirs.sort()
            for file in sorted(files):
                fp  = Path(root) / file
                rel = fp.relative_to(temp_dir)
                if str(rel) == "mimetype":
                    continue
                zf.write(fp, rel)


def find_opf_path(temp_dir):
    """
    优先解析 META-INF/container.xml 定位 OPF；
    回退到按文件名（content.opf / package.opf）查找。
    """
    container_xml = Path(temp_dir) / "META-INF" / "container.xml"
    if container_xml.exists():
        try:
            with open(container_xml, "r", encoding="utf-8") as f:
                soup = BeautifulSoup(f, "lxml-xml")
            rootfile = soup.find("rootfile")
            if rootfile and rootfile.get("full-path"):
                return str(Path(temp_dir) / rootfile["full-path"])
        except Exception as e:
            print(f"[警告] 解析 container.xml 失败，尝试回退: {e}")

    # 回退：按文件名搜索
    for root, _, files in os.walk(temp_dir):
        for file in files:
            if file.lower() in ("content.opf", "package.opf"):
                return os.path.join(root, file)
    return None


def find_html_files(temp_dir):
    """遍历临时目录，返回 HTML/XHTML 文件列表"""
    html_files = []
    for root, _, files in os.walk(temp_dir):
        for file in sorted(files):
            if file.lower().endswith((".xhtml", ".html", ".htm")):
                html_files.append(os.path.join(root, file))
    return html_files


def make_output_path(epub_path, suffix):
    """生成输出 EPUB 路径，如 foo_char2img.epub"""
    p = Path(epub_path)
    return str(p.with_name(f"{p.stem}_{suffix}.epub"))


def make_temp_dir(epub_path):
    """
    创建唯一临时目录：若同名旧目录存在则先清空，
    再在 epub_temp/ 下用 tempfile 创建带前缀的唯一子目录。
    """
    base = SCRIPT_DIR / "epub_temp"
    base.mkdir(parents=True, exist_ok=True)
    prefix = Path(epub_path).stem + "_"
    return tempfile.mkdtemp(prefix=prefix, dir=str(base))


# ============================================================
# XHTML 解析 / 序列化工具
# ============================================================

_XML_DECL_RE  = re.compile(r"^(<\?xml[^?]*\?>\s*)")
_DOCTYPE_RE   = re.compile(r"(<!DOCTYPE[^>]*>\s*)")


def split_prolog(content):
    """
    从文件内容中分离 XML 声明和 DOCTYPE，
    返回 (xml_decl, doctype, body_start_index)。
    """
    xml_decl = doctype = ""
    body_start = 0

    m = _XML_DECL_RE.match(content)
    if m:
        xml_decl   = m.group(0)
        body_start = m.end()

    m2 = _DOCTYPE_RE.search(content, body_start)
    if m2:
        doctype    = m2.group(0)
        body_start = max(body_start, m2.end())

    return xml_decl, doctype, body_start


def parse_xhtml(content, body_start):
    """使用 lxml-xml 解析 XHTML 片段（严格 XML 规则）"""
    return BeautifulSoup(content[body_start:], "lxml-xml")


def serialize_xhtml(xml_decl, doctype, soup):
    """序列化回 XHTML，保留原始声明头"""
    # lxml-xml 的 str(soup) 会自带 <?xml ...?> 声明，需去掉再拼接原始声明
    body = str(soup)
    # 去除 BS4/lxml 自动插入的 XML 声明（若有）
    body = _XML_DECL_RE.sub("", body)
    return xml_decl + doctype + body


# ============================================================
# 模式 -char2img：L3文字 → 图片
# ============================================================

def _process_html_char2img(html_path, images_dir, images_href_base,
                            handled_chars, is_l3, font_files, font_size, image_size):
    """处理单个 HTML 文件：将 L3 文字替换为 <img> 标签"""
    with open(html_path, "r", encoding="utf-8") as f:
        content = f.read()

    xml_decl, doctype, body_start = split_prolog(content)
    soup = parse_xhtml(content, body_start)

    # 计算从当前 HTML 到 Images 目录的相对路径
    html_dir = Path(html_path).parent
    try:
        rel_prefix = os.path.relpath(images_dir, html_dir).replace("\\", "/")
    except ValueError:
        rel_prefix = images_href_base  # 跨盘符时回退

    replacements = 0
    for text_node in soup.find_all(string=True):
        if isinstance(text_node, (Comment, Doctype, Declaration)):
            continue
        parent = text_node.parent
        if parent is None:
            continue
        if parent.name in ("title", "script", "style"):
            continue

        new_content  = []
        current_text = []

        for char in text_node:
            if is_l3(char):
                if current_text:
                    new_content.append("".join(current_text))
                    current_text = []

                char_code    = f"U{ord(char):06X}"
                img_filename = f"{char_code}.png"
                img_path     = os.path.join(images_dir, img_filename)
                rel_img_path = f"{rel_prefix}/{img_filename}"

                if char not in handled_chars:
                    font_path = find_font_for_char(char, font_files)
                    if font_path:
                        os.makedirs(images_dir, exist_ok=True)
                        if render_char_image(char, font_path, img_path, font_size, image_size):
                            handled_chars[char] = rel_img_path

                if char in handled_chars:
                    img_tag = soup.new_tag("img")
                    img_tag["alt"]   = char
                    img_tag["style"] = ("width: 1em; vertical-align: middle; "
                                        "margin-left: 0.1em; margin-right: 0.1em;")
                    img_tag["src"]   = handled_chars[char]
                    new_content.append(img_tag)
                    replacements += 1
            else:
                current_text.append(char)

        if current_text:
            new_content.append("".join(current_text))

        if new_content:
            text_node.replace_with(*new_content)

    if replacements > 0:
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(serialize_xhtml(xml_decl, doctype, soup))

    return replacements


def _update_opf_add(opf_path, handled_chars, manifest_added, images_href_base):
    """向 content.opf manifest 添加图片条目"""
    with open(opf_path, "r", encoding="utf-8") as f:
        raw = f.read()
    soup = BeautifulSoup(raw, "lxml-xml")
    manifest = soup.find("manifest")
    if not manifest:
        return
    for char, rel_path in handled_chars.items():
        img_filename = os.path.basename(rel_path)
        href = f"{images_href_base}/{img_filename}"
        if href in manifest_added:
            continue
        item = soup.new_tag("item")
        item["id"]         = img_filename.replace(".", "_")
        item["href"]       = href
        item["media-type"] = "image/png"
        manifest.append(item)
        manifest_added.add(href)
    with open(opf_path, "w", encoding="utf-8") as f:
        f.write(str(soup))


def process_epub_char2img(epub_path, config):
    """模式 -char2img：处理单个 EPUB"""
    is_l3      = build_l3_checker(config["l3_ranges"])
    font_files = config["font_files"]
    font_size  = config["font_size"]
    image_size = config["image_size"]

    temp_dir = make_temp_dir(epub_path)
    print(f"  临时目录: {temp_dir}")

    try:
        epub_extract(epub_path, temp_dir)

        opf_path = find_opf_path(temp_dir)
        if not opf_path:
            raise FileNotFoundError("未找到 OPF 文件（content.opf / package.opf）")

        # Images 目录与 OPF 同级（EPUB 规范常见结构）
        opf_dir    = Path(opf_path).parent
        images_dir = str(opf_dir / "Images")
        # OPF manifest 中的 href 相对于 OPF 文件所在目录
        images_href_base = "Images"

        html_files = find_html_files(temp_dir)

        handled_chars  = {}
        manifest_added = set()
        total = 0

        for hf in html_files:
            n = _process_html_char2img(
                hf, images_dir, images_href_base,
                handled_chars, is_l3, font_files, font_size, image_size
            )
            total += n
            if n > 0:
                print(f"    {Path(hf).name}: 替换 {n} 处")

        print(f"  共替换 {total} 处 L3 字符")
        _update_opf_add(opf_path, handled_chars, manifest_added, images_href_base)

        output = make_output_path(epub_path, "char2img")
        epub_repack(temp_dir, output)
        print(f"  输出: {output}")
        return True

    except Exception as e:
        print(f"  [错误] {e}")
        return False
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ============================================================
# 模式 -img2char：图片 → L3文字（逆向）
# ============================================================

_L3_IMG_SRC_RE = re.compile(r"U[0-9A-Fa-f]{6}\.png$")


def _process_html_img2char(html_path, is_l3):
    """将 <img alt="L3汉字"> 替换回 L3 文字文本，返回替换数"""
    with open(html_path, "r", encoding="utf-8") as f:
        content = f.read()

    xml_decl, doctype, body_start = split_prolog(content)
    soup = parse_xhtml(content, body_start)

    replacements = 0
    for img in soup.find_all("img"):
        alt = img.get("alt", "")
        src = img.get("src", "")
        # 严格匹配：alt 恰好为单个 L3 字符，且 src 符合 U??????.png 格式
        if (len(alt) == 1
                and is_l3(alt)
                and _L3_IMG_SRC_RE.search(src)):
            img.replace_with(alt)
            replacements += 1

    if replacements > 0:
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(serialize_xhtml(xml_decl, doctype, soup))

    return replacements


def _update_opf_remove(opf_path):
    """从 manifest 中移除由 -char2img 添加的图片条目（href 以 Images/U 开头的 .png）"""
    with open(opf_path, "r", encoding="utf-8") as f:
        raw = f.read()
    soup = BeautifulSoup(raw, "lxml-xml")
    manifest = soup.find("manifest")
    if not manifest:
        return
    removed = 0
    for item in manifest.find_all("item"):
        href = item.get("href", "")
        if re.match(r"Images/U[0-9A-Fa-f]+\.png$", href):
            item.decompose()
            removed += 1
    if removed:
        with open(opf_path, "w", encoding="utf-8") as f:
            f.write(str(soup))
        print(f"  已从 manifest 移除 {removed} 条图片记录")


def process_epub_img2char(epub_path, config):
    """模式 -img2char：处理单个 EPUB"""
    is_l3 = build_l3_checker(config["l3_ranges"])

    temp_dir = make_temp_dir(epub_path)
    print(f"  临时目录: {temp_dir}")

    try:
        epub_extract(epub_path, temp_dir)

        opf_path = find_opf_path(temp_dir)
        if not opf_path:
            raise FileNotFoundError("未找到 OPF 文件（content.opf / package.opf）")

        html_files = find_html_files(temp_dir)
        total = 0
        for hf in html_files:
            n = _process_html_img2char(hf, is_l3)
            total += n
            if n > 0:
                print(f"    {Path(hf).name}: 还原 {n} 处")

        print(f"  共还原 {total} 处 L3 字符")
        _update_opf_remove(opf_path)

        output = make_output_path(epub_path, "img2char")
        epub_repack(temp_dir, output)
        print(f"  输出: {output}")
        return True

    except Exception as e:
        print(f"  [错误] {e}")
        return False
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ============================================================
# 模式 -remap：图片字 → 纯文本（figures 目录映射）
# ============================================================

def build_image_map(figures_dir, epub_stem=None):
    """
    扫描 figures/ 目录，构建 {图片文件名: 汉字} 映射。

    目录结构支持两种模式（优先级从高到低）：

    模式A（按书名隔离，推荐多本使用）：
        figures/<EPUB文件名（不含扩展名）>/<汉字>/<图片文件>

    模式B（通用映射，向后兼容）：
        figures/<汉字>/<图片文件>

    当 epub_stem 对应的子目录存在时，优先使用模式A；
    否则回退到模式B（扫描 figures/ 根目录下的汉字子目录）。
    """
    figures_path = Path(figures_dir)
    if not figures_path.exists():
        raise FileNotFoundError(f"figures 目录不存在: {figures_dir}")

    # 判断是否存在以 epub_stem 命名的子目录
    book_dir = figures_path / epub_stem if epub_stem else None
    if book_dir and book_dir.is_dir():
        scan_root = book_dir
        print(f"  figures 模式A：使用书名子目录 [{epub_stem}]")
    else:
        scan_root = figures_path
        if epub_stem:
            print(f"  figures 模式B：未找到书名子目录 [{epub_stem}]，使用通用映射")

    image_map = {}
    char_dirs = [d for d in scan_root.iterdir() if d.is_dir()]
    if not char_dirs:
        print("  [警告] figures 目录下未找到任何汉字子文件夹")
    for char_dir in char_dirs:
        for img_file in char_dir.iterdir():
            if img_file.is_file():
                image_map[img_file.name] = char_dir.name
    print(f"  图片映射: 共 {len(image_map)} 张")
    return image_map


def _process_html_remap(html_path, image_map):
    """将 <img src="..."> 按 figures 映射替换为汉字文本"""
    with open(html_path, "r", encoding="utf-8") as f:
        content = f.read()

    xml_decl, doctype, body_start = split_prolog(content)
    soup = parse_xhtml(content, body_start)

    replacements = 0
    for img in soup.find_all("img"):
        src      = img.get("src", "")
        img_name = Path(src).name
        if img_name in image_map:
            img.replace_with(image_map[img_name])
            replacements += 1

    if replacements > 0:
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(serialize_xhtml(xml_decl, doctype, soup))

    return replacements


def process_epub_remap(epub_path, config, image_map=None):
    """模式 -remap：处理单个 EPUB。
    image_map 若为 None，则根据 EPUB 文件名自动从 figures/ 构建（优先书名子目录）。
    """
    if image_map is None:
        epub_stem = Path(epub_path).stem
        image_map = build_image_map(config["figures_dir"], epub_stem=epub_stem)

    temp_dir = make_temp_dir(epub_path)
    print(f"  临时目录: {temp_dir}")

    try:
        epub_extract(epub_path, temp_dir)

        html_files = find_html_files(temp_dir)
        total = 0
        for hf in html_files:
            n = _process_html_remap(hf, image_map)
            total += n
            if n > 0:
                print(f"    {Path(hf).name}: 替换 {n} 处")

        print(f"  共替换 {total} 处图片字")

        output = make_output_path(epub_path, "remap")
        epub_repack(temp_dir, output)
        print(f"  输出: {output}")
        return True

    except Exception as e:
        print(f"  [错误] {e}")
        return False
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ============================================================
# 批量处理分发
# ============================================================

def run_on_path(path, process_func, config):
    """对单个文件或目录下所有 EPUB 执行 process_func"""
    path = Path(path)

    if path.is_file() and path.suffix.lower() == ".epub":
        print(f"\n处理: {path}")
        process_func(str(path), config)
    elif path.is_dir():
        epub_list = sorted(path.rglob("*.epub"))
        if not epub_list:
            print("  未找到任何 EPUB 文件")
            return
        ok = err = 0
        for ep in epub_list:
            print(f"\n处理: {ep}")
            if process_func(str(ep), config):
                ok += 1
            else:
                err += 1
        print(f"\n完成：成功 {ok}，失败 {err}")
    else:
        print(f"[错误] 路径不是 EPUB 文件或文件夹: {path}")


# ============================================================
# 入口
# ============================================================

MODES = {
    "-char2img": ("L3文字 → 图片",         process_epub_char2img),
    "-img2char": ("图片 → L3文字（逆向）",  process_epub_img2char),
    "-remap":    ("图片字 → 纯文本",        process_epub_remap),
}

BANNER = """
╔══════════════════════════════════════════════╗
║       EPUB L3 字符 / 字图转换工具            ║
╠══════════════════════════════════════════════╣
║  -char2img   L3文字 → 图片                   ║
║  -img2char   图片 → L3文字（逆向）           ║
║  -remap      图片字 → 纯文本（figures映射）  ║
╚══════════════════════════════════════════════╝
"""

def main():
    print(BANNER)

    if len(sys.argv) < 2 or sys.argv[1] not in MODES:
        print("用法: python epub_charImg_converter.py -<模式> [EPUB文件或文件夹路径]")
        print("模式:", " / ".join(MODES.keys()))
        sys.exit(1)

    mode_key = sys.argv[1]
    mode_name, process_func = MODES[mode_key]
    print(f"当前模式: {mode_key}  ({mode_name})")

    config = load_config()

    # 支持命令行直接传入路径，也支持交互输入
    if len(sys.argv) >= 3:
        path_input = sys.argv[2].strip().strip('"').strip("'")
    else:
        path_input = input("\n请输入 EPUB 文件或文件夹路径（可直接拖入）: ").strip().strip('"').strip("'")

    if not path_input:
        print("[错误] 路径为空")
        sys.exit(1)

    run_on_path(path_input, process_func, config)
    input("\n按 Enter 键退出...")


if __name__ == "__main__":
    main()
