# test_mwe.py
# 针对三个 MWE EPUB 的单元测试
# 运行方式：python -m pytest MWE/test_mwe.py -v
#           或直接：python MWE/test_mwe.py

import os
import re
import sys
import shutil
import zipfile
import unittest
import tempfile
from pathlib import Path

# 将脚本根目录加入 sys.path，以便导入主模块
SCRIPT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

import epub_charImg_converter as conv

MWE_DIR     = Path(__file__).parent
FIGURES_DIR = SCRIPT_DIR / "figures"


# ============================================================
# 工具函数
# ============================================================

def run_and_get_output(epub_src: Path, process_func, config: dict) -> Path:
    """
    对 epub_src 的副本执行 process_func，返回输出 EPUB 的路径。
    副本放在系统临时目录，测试结束后由调用方清理。
    """
    tmp = Path(tempfile.mkdtemp())
    epub_copy = tmp / epub_src.name
    shutil.copy2(epub_src, epub_copy)
    process_func(str(epub_copy), config)
    suffix_map = {
        conv.process_epub_char2img: "char2img",
        conv.process_epub_img2char: "img2char",
        conv.process_epub_remap:    "remap",
    }
    suffix = suffix_map[process_func]
    output = epub_copy.with_name(f"{epub_copy.stem}_{suffix}.epub")
    return output, tmp


def read_html_from_epub(epub_path: Path, html_rel: str = "OEBPS/Text/test.xhtml") -> str:
    with zipfile.ZipFile(epub_path) as zf:
        return zf.read(html_rel).decode("utf-8")


def read_opf_from_epub(epub_path: Path, opf_rel: str = "OEBPS/content.opf") -> str:
    with zipfile.ZipFile(epub_path) as zf:
        return zf.read(opf_rel).decode("utf-8")


def list_epub_files(epub_path: Path) -> list:
    with zipfile.ZipFile(epub_path) as zf:
        return zf.namelist()


def make_config(extra: dict = None) -> dict:
    cfg = conv.load_config()
    if extra:
        cfg.update(extra)
    return cfg


# ============================================================
# 测试：-char2img 模式
# ============================================================

class TestChar2Img(unittest.TestCase):
    """test_char2img.epub：含 𫖯(U+2B5AF) 和 𪮤(U+2ABA4) 两个 L3 字符"""

    EPUB_SRC   = MWE_DIR / "test_char2img.epub"
    L3_CHARS   = [("\U0002b5af", "U02B5AF"), ("\U0002aba4", "U02ABA4")]  # (字符, 预期文件名前缀)

    @classmethod
    def setUpClass(cls):
        config = make_config()
        cls.output, cls.tmp = run_and_get_output(cls.EPUB_SRC, conv.process_epub_char2img, config)
        cls.html = read_html_from_epub(cls.output)
        cls.opf  = read_opf_from_epub(cls.output)
        cls.files = list_epub_files(cls.output)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_output_file_exists(self):
        """输出文件应存在"""
        self.assertTrue(self.output.exists(), f"输出文件不存在: {self.output}")

    def test_l3_chars_removed_from_text(self):
        """原始 L3 字符不应再以文本节点形式出现（允许存在于 alt 属性中）"""
        # 将所有 alt="..." 属性值替换为空，再检查字符是否仍以文本形式存在
        html_no_alt = re.sub(r'alt="[^"]*"', 'alt=""', self.html)
        for char, _ in self.L3_CHARS:
            with self.subTest(char=repr(char)):
                self.assertNotIn(char, html_no_alt,
                    f"L3 字符 {repr(char)} 仍以文本节点形式存在于输出 HTML 中")

    def test_img_tags_inserted(self):
        """每个 L3 字符应被替换为对应的 <img> 标签"""
        for char, code in self.L3_CHARS:
            expected_src = f"{code}.png"
            with self.subTest(char=repr(char), src=expected_src):
                self.assertIn(expected_src, self.html,
                    f"未找到 {expected_src} 对应的 <img> 标签")

    def test_img_alt_equals_original_char(self):
        """<img> 标签的 alt 属性应等于原始 L3 字符"""
        alts = re.findall(r'alt="([^"]*)"', self.html)
        for char, _ in self.L3_CHARS:
            with self.subTest(char=repr(char)):
                self.assertIn(char, alts,
                    f"<img alt> 中未找到原始字符 {repr(char)}")

    def test_png_files_added_to_epub(self):
        """生成的 PNG 图片应被打包进 EPUB"""
        for _, code in self.L3_CHARS:
            expected = f"OEBPS/Images/{code}.png"
            with self.subTest(file=expected):
                self.assertIn(expected, self.files,
                    f"EPUB 中未找到 {expected}")

    def test_png_files_in_opf_manifest(self):
        """生成的 PNG 图片应出现在 OPF manifest 中"""
        for _, code in self.L3_CHARS:
            expected_href = f"Images/{code}.png"
            with self.subTest(href=expected_href):
                self.assertIn(expected_href, self.opf,
                    f"OPF manifest 中未找到 {expected_href}")

    def test_xml_declaration_preserved(self):
        """输出 XHTML 应保留 XML 声明"""
        self.assertTrue(self.html.startswith("<?xml"),
            "输出 HTML 缺少 XML 声明")

    def test_doctype_preserved(self):
        """输出 XHTML 应保留 DOCTYPE"""
        self.assertIn("<!DOCTYPE", self.html,
            "输出 HTML 缺少 DOCTYPE")

    def test_title_not_affected(self):
        """<title> 元素内容不应被替换"""
        self.assertIn("<title>test_char2img</title>", self.html,
            "<title> 内容被意外修改")

    def test_non_l3_text_preserved(self):
        """非 L3 文本（如 CIP）应完整保留"""
        self.assertIn("图书在", self.html)
        self.assertIn("版编目", self.html)
        self.assertIn("CIP", self.html)


# ============================================================
# 测试：-img2char 模式
# ============================================================

class TestImg2Char(unittest.TestCase):
    """
    test_img2char.epub：含 3 个 <img alt="L3字" src="Images/U??????.png">
      - 𣾧 (U+023FA7) × 1
      - 𠇑 (U+0201D1) × 2
    """

    EPUB_SRC = MWE_DIR / "test_img2char.epub"
    EXPECTED = [
        ("\U00023fa7", "U023FA7.png", 1),  # (字符, src文件名, 出现次数)
        ("\U000201d1", "U0201D1.png", 2),
    ]

    @classmethod
    def setUpClass(cls):
        config = make_config()
        cls.output, cls.tmp = run_and_get_output(cls.EPUB_SRC, conv.process_epub_img2char, config)
        cls.html  = read_html_from_epub(cls.output)
        cls.opf   = read_opf_from_epub(cls.output)
        cls.files = list_epub_files(cls.output)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_output_file_exists(self):
        self.assertTrue(self.output.exists())

    def test_l3_chars_restored(self):
        """L3 字符应以文本形式出现在输出 HTML 中"""
        for char, _, count in self.EXPECTED:
            with self.subTest(char=repr(char)):
                actual = self.html.count(char)
                self.assertEqual(actual, count,
                    f"{repr(char)} 应出现 {count} 次，实际 {actual} 次")

    def test_img_tags_removed(self):
        """原有的 L3 <img> 标签应被移除"""
        for _, src, _ in self.EXPECTED:
            with self.subTest(src=src):
                self.assertNotIn(src, self.html,
                    f"img src={src} 仍残留在输出 HTML 中")

    def test_png_files_removed_from_opf(self):
        """OPF manifest 中的 L3 PNG 条目应被移除"""
        for _, src, _ in self.EXPECTED:
            href = f"Images/{src}"
            with self.subTest(href=href):
                self.assertNotIn(href, self.opf,
                    f"OPF manifest 中仍残留 {href}")

    def test_xml_declaration_preserved(self):
        self.assertTrue(self.html.startswith("<?xml"))

    def test_doctype_preserved(self):
        self.assertIn("<!DOCTYPE", self.html)

    def test_surrounding_text_preserved(self):
        """还原后周围文本应完整"""
        self.assertIn("本章第一段文字基本一样", self.html)
        self.assertIn("自今及古", self.html)


# ============================================================
# 测试：-remap 模式
# ============================================================

class TestRemap(unittest.TestCase):
    """
    test_remap.epub：含 6 个 <img src="../Images/10CFigure-0000-000N.jpg">
    figures/test_remap/ 映射：
      0001/0002/0003/0004.jpg → 𩅦 (U+29166)
      0007/0008/0009.jpg      → 斅 (U+6585)
    HTML 中实际引用：0001/0002/0003（3个）+ 0007/0008/0009（3个）= 6个
    0004.jpg 在 figures 中存在但 HTML 中无引用，不应影响输出
    """

    EPUB_SRC = MWE_DIR / "test_remap.epub"
    CHAR_A   = "\U00029166"  # 𩅦，对应 0001/0002/0003
    CHAR_B   = "\u6585"      # 斅，对应 0007/0008/0009
    IMGS_A   = ["10CFigure-0000-0001.jpg", "10CFigure-0000-0002.jpg", "10CFigure-0000-0003.jpg"]
    IMGS_B   = ["10CFigure-0000-0007.jpg", "10CFigure-0000-0008.jpg", "10CFigure-0000-0009.jpg"]

    @classmethod
    def setUpClass(cls):
        config = make_config({"figures_dir": str(FIGURES_DIR)})
        cls.output, cls.tmp = run_and_get_output(cls.EPUB_SRC, conv.process_epub_remap, config)
        cls.html = read_html_from_epub(cls.output)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_output_file_exists(self):
        self.assertTrue(self.output.exists())

    def test_char_a_restored_correct_count(self):
        """𩅦 应出现 3 次（对应 0001/0002/0003）"""
        count = self.html.count(self.CHAR_A)
        self.assertEqual(count, 3,
            f"𩅦 应出现 3 次，实际 {count} 次")

    def test_char_b_restored_correct_count(self):
        """斅 应出现 3 次（对应 0007/0008/0009）"""
        count = self.html.count(self.CHAR_B)
        self.assertEqual(count, 3,
            f"斅 应出现 3 次，实际 {count} 次")

    def test_img_tags_a_removed(self):
        """0001/0002/0003 的 <img> 应被替换"""
        for src in self.IMGS_A:
            with self.subTest(src=src):
                self.assertNotIn(src, self.html,
                    f"{src} 的 <img> 标签仍残留")

    def test_img_tags_b_removed(self):
        """0007/0008/0009 的 <img> 应被替换"""
        for src in self.IMGS_B:
            with self.subTest(src=src):
                self.assertNotIn(src, self.html,
                    f"{src} 的 <img> 标签仍残留")

    def test_unmapped_image_not_affected(self):
        """0004.jpg 在 HTML 中本无引用，输出中也不应出现该文件名"""
        self.assertNotIn("10CFigure-0000-0004.jpg", self.html)

    def test_surrounding_text_preserved(self):
        """替换后周围文本应完整保留"""
        self.assertIn("吴主重病", self.html)
        self.assertIn("王濬虽然奉诏募兵", self.html)

    def test_xml_declaration_preserved(self):
        self.assertTrue(self.html.startswith("<?xml"))

    def test_doctype_preserved(self):
        self.assertIn("<!DOCTYPE", self.html)

    def test_figures_book_dir_used(self):
        """figures/test_remap/ 目录应存在（模式A）"""
        book_dir = FIGURES_DIR / "test_remap"
        self.assertTrue(book_dir.is_dir(),
            f"figures 书名子目录不存在: {book_dir}")


# ============================================================
# 入口
# ============================================================

if __name__ == "__main__":
    unittest.main(verbosity=2)
