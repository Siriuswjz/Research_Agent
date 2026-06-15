"""高质量 PDF → Markdown，优先用 marker，没装则 fallback 到 PyMuPDF"""
import os
from tools.pdf_tool import parse_pdf

_marker_converter = None


def _get_marker():
    """懒加载 marker，第一次调用才载模型"""
    global _marker_converter
    if _marker_converter is not None:
        return _marker_converter
    try:
        from marker.converters.pdf import PdfConverter
        from marker.models import create_model_dict
        _marker_converter = PdfConverter(artifact_dict=create_model_dict())
        return _marker_converter
    except ImportError:
        return None


def parse_pdf_high_quality(pdf_path: str, fallback_max_chars: int = 30000) -> str:
    """
    解析 PDF 为 markdown / text。
    优先 marker（公式 LaTeX、表格 markdown、双栏正确），失败 fallback PyMuPDF。
    """
    converter = _get_marker()
    if converter is not None:
        print("   📖 使用 marker 解析（高质量，慢）...")
        try:
            from marker.output import text_from_rendered
            rendered = converter(pdf_path)
            text, _, _ = text_from_rendered(rendered)
            return text
        except Exception as e:
            print(f"   ⚠️  marker 失败 ({e})，fallback PyMuPDF")

    print("   📖 使用 PyMuPDF 解析（快速）...")
    with open(pdf_path, "rb") as f:
        return parse_pdf(f.read(), fallback_max_chars)


def is_marker_available() -> bool:
    try:
        import marker  # noqa: F401
        return True
    except ImportError:
        return False
