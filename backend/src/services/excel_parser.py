from __future__ import annotations

from dataclasses import dataclass
import base64
import re
import zipfile
from pathlib import PurePosixPath
from xml.etree import ElementTree
from io import BytesIO
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter


MAX_QUESTION_COUNT = 500
# Images are stored as Base64 data URLs in the existing text columns. Keep the
# encoded value below 1 MiB so a single upload cannot create an unexpectedly
# large database row. The raw target is lower because Base64 adds ~33%.
MAX_IMAGE_DATA_URL_BYTES = 1024 * 1024
MAX_IMAGE_RAW_BYTES = 700 * 1024

HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "question_text": ("题目", "题目内容", "question", "question_text"),
    "correct_answer": ("正确答案", "正確答案", "答案", "correct_answer", "answer"),
    "question_type": ("题型", "題型", "question_type"),
    "source_year": ("年份", "来源年份", "來源年份", "source_year", "year"),
}


@dataclass(frozen=True)
class ParsedQuestion:
    row_number: int
    question_text: str
    question_image_url: str | None
    question_type: str
    correct_answer: str | None
    source_year: str | None


class ExcelImportError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("Excel 文件存在错误，请修正后重新上传")


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalise_header(value: Any) -> str:
    return "".join(_text(value).lower().split())


def _find_columns(header_row: tuple[Any, ...]) -> dict[str, int]:
    normalized = {_normalise_header(value): index for index, value in enumerate(header_row)}
    columns: dict[str, int] = {}
    missing: list[str] = []
    for field, aliases in HEADER_ALIASES.items():
        for alias in aliases:
            index = normalized.get(_normalise_header(alias))
            if index is not None:
                columns[field] = index
                break
        if field != "source_year" and field not in columns:
            missing.append(aliases[0])
    if missing:
        raise ExcelImportError([f"缺少必要欄位：{', '.join(missing)}"])
    return columns


def _correct_key(value: str) -> str | None:
    aliases = {"1": "A", "2": "B", "3": "C", "4": "D", "Ａ": "A", "Ｂ": "B", "Ｃ": "C", "Ｄ": "D"}
    answer = value.strip().upper()
    return aliases.get(answer, answer if answer in {"A", "B", "C", "D"} else None)


_DISPIMG_RE = re.compile(r'DISPIMG\(\s*["\']([^"\']+)["\']', re.IGNORECASE)


def _data_url(filename: str, content: bytes) -> str:
    suffix = PurePosixPath(filename).suffix.lower()
    media_type = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }.get(suffix, "application/octet-stream")
    encoded = base64.b64encode(content).decode("ascii")
    data_url = f"data:{media_type};base64,{encoded}"
    if len(content) <= MAX_IMAGE_RAW_BYTES and len(data_url.encode("ascii")) <= MAX_IMAGE_DATA_URL_BYTES:
        return data_url

    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError as exc:
        raise ExcelImportError(["图片文件过大，无法压缩；请使用较小的图片后重新上传"]) from exc

    try:
        with Image.open(BytesIO(content)) as image:
            image.load()
            has_alpha = image.mode in {"RGBA", "LA"} or "transparency" in image.info
            if has_alpha:
                converted = image.convert("RGBA")
            else:
                converted = image.convert("RGB")

            # First bound dimensions so very large camera photos do not consume
            # excessive CPU/memory during repeated quality attempts.
            converted.thumbnail((1800, 1800), Image.Resampling.LANCZOS)
            candidates: list[bytes] = []
            for quality in (85, 75, 65, 55, 45, 35):
                output = BytesIO()
                # JPEG is substantially smaller for photos and line drawings.
                # Transparent images are composited onto white before encoding.
                candidate_image = converted
                if has_alpha:
                    background = Image.new("RGB", converted.size, "white")
                    background.paste(converted, mask=converted.getchannel("A"))
                    candidate_image = background
                candidate_image.save(output, format="JPEG", quality=quality, optimize=True, progressive=True)
                candidates.append(output.getvalue())
                encoded_candidate = base64.b64encode(candidates[-1]).decode("ascii")
                candidate_url = f"data:image/jpeg;base64,{encoded_candidate}"
                if len(candidates[-1]) <= MAX_IMAGE_RAW_BYTES and len(candidate_url.encode("ascii")) <= MAX_IMAGE_DATA_URL_BYTES:
                    return candidate_url

                # For unusually detailed images, reduce dimensions between passes.
                if quality == 35 and min(converted.size) > 480:
                    converted = converted.resize(
                        (max(1, int(converted.width * 0.8)), max(1, int(converted.height * 0.8))),
                        Image.Resampling.LANCZOS,
                    )
            if candidates:
                smallest = min(candidates, key=len)
                encoded_smallest = base64.b64encode(smallest).decode("ascii")
                smallest_url = f"data:image/jpeg;base64,{encoded_smallest}"
                if len(smallest_url.encode("ascii")) <= MAX_IMAGE_DATA_URL_BYTES:
                    return smallest_url
    except (OSError, UnidentifiedImageError) as exc:
        raise ExcelImportError(["无法读取或压缩 Excel 中的图片，请更换图片后重新上传"]) from exc

    raise ExcelImportError(["图片压缩后仍超过 1MB，请裁剪图片或使用更小的图片后重新上传"])


def _cell_image_formulas(content: bytes) -> dict[str, str]:
    """Read WPS/Excel DISPIMG cell formulas without losing the embedded media."""
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            names = set(archive.namelist())
            if "xl/cellimages.xml" not in names or "xl/_rels/cellimages.xml.rels" not in names:
                return {}
            rel_root = ElementTree.fromstring(archive.read("xl/_rels/cellimages.xml.rels"))
            rels = {
                rel.attrib.get("Id"): rel.attrib.get("Target", "")
                for rel in rel_root
            }
            image_root = ElementTree.fromstring(archive.read("xl/cellimages.xml"))
            image_urls: dict[str, str] = {}
            for cell_image in image_root.iter():
                if cell_image.tag.rsplit("}", 1)[-1] != "cellImage":
                    continue
                c_nv = next((node for node in cell_image.iter() if node.tag.rsplit("}", 1)[-1] == "cNvPr"), None)
                if c_nv is None:
                    continue
                image_id = c_nv.attrib.get("name")
                if not image_id:
                    continue
                blip = next((node for node in cell_image.iter() if node.tag.rsplit("}", 1)[-1] == "blip"), None)
                rel_id = blip.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed") if blip is not None else None
                target = rels.get(rel_id or "")
                if not target:
                    continue
                media_name = str(PurePosixPath("xl") / PurePosixPath(target.lstrip("/")))
                if media_name not in names:
                    media_name = str(PurePosixPath("xl") / PurePosixPath("media") / PurePosixPath(target).name)
                if media_name in names:
                    image_urls[image_id] = _data_url(media_name, archive.read(media_name))

            sheet_xml = "xl/worksheets/sheet1.xml"
            if sheet_xml not in names:
                return {}
            root = ElementTree.fromstring(archive.read(sheet_xml))
            result: dict[str, str] = {}
            for cell in root.iter():
                if cell.tag.rsplit("}", 1)[-1] != "c":
                    continue
                coordinate = cell.attrib.get("r")
                if not coordinate:
                    continue
                formula = next((node.text or "" for node in cell if node.tag.rsplit("}", 1)[-1] == "f"), "")
                match = _DISPIMG_RE.search(formula)
                if match and match.group(1) in image_urls:
                    result[coordinate] = image_urls[match.group(1)]
            return result
    except (OSError, ElementTree.ParseError, zipfile.BadZipFile):
        return {}


def _cell_key(row_number: int, column_index: int) -> str:
    return f"{get_column_letter(column_index + 1)}{row_number}"


def parse_question_excel(content: bytes) -> list[ParsedQuestion]:
    if not content:
        raise ExcelImportError(["Excel 文件为空"])
    try:
        workbook = load_workbook(filename=BytesIO(content), read_only=False, data_only=False)
    except Exception as exc:  # openpyxl exposes several parser-specific exceptions
        raise ExcelImportError(["无法读取 Excel 文件，请确认文件格式为 .xlsx"]) from exc

    sheet = workbook.active
    formula_images = _cell_image_formulas(content)
    anchored_images: dict[str, str] = {}
    for image in getattr(sheet, "_images", []):
        anchor = getattr(image, "anchor", None)
        origin = getattr(anchor, "_from", None)
        if origin is None:
            continue
        try:
            anchored_images[_cell_key(origin.row + 1, origin.col)] = _data_url(
                getattr(image, "path", "image.png"), image._data()
            )
        except Exception:
            continue
    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        raise ExcelImportError(["Excel 文件没有内容"])
    columns = _find_columns(tuple(rows[0]))
    parsed: list[ParsedQuestion] = []
    errors: list[str] = []

    for row_number, row in enumerate(rows[1:], start=2):
        values = tuple(row)
        if not any(_text(value) for value in values):
            continue
        if len(parsed) >= MAX_QUESTION_COUNT:
            errors.append(f"第 {row_number} 行之后题目超过上限 {MAX_QUESTION_COUNT} 题")
            break

        question_text = _text(values[columns["question_text"]] if columns["question_text"] < len(values) else None)
        question_cell = _cell_key(row_number, columns["question_text"])
        question_image_url = formula_images.get(question_cell) or anchored_images.get(question_cell)
        if question_image_url and _DISPIMG_RE.search(question_text):
            question_text = ""
        raw_type = _text(values[columns["question_type"]] if columns["question_type"] < len(values) else None)
        type_aliases = {
            "选择题": "single_choice", "選擇題": "single_choice", "single_choice": "single_choice",
            "非选择题": "text_input", "非選擇題": "text_input", "text_input": "text_input",
        }
        question_type = type_aliases.get(raw_type.strip().lower())
        raw_answer = _text(values[columns["correct_answer"]] if columns["correct_answer"] < len(values) else None)
        correct_answer = _correct_key(raw_answer)
        source_year = _text(values[columns["source_year"]] if "source_year" in columns and columns["source_year"] < len(values) else None) or None

        row_errors: list[str] = []
        if not question_image_url:
            row_errors.append("题目必须包含题目截图（请将图片嵌入题目单元格）")
        if question_type is None:
            row_errors.append("题型必须填写“选择题”或“非选择题”")
        elif question_type == "single_choice" and correct_answer is None:
            row_errors.append("正确答案必须是 A、B、C、D 或 1、2、3、4")
        elif question_type == "text_input" and raw_answer:
            row_errors.append("非选择题不设置标准答案，请将正确答案留空")
        if row_errors:
            errors.append(f"第 {row_number} 行：{'；'.join(row_errors)}")
            continue
        parsed.append(ParsedQuestion(row_number, question_text, question_image_url, question_type, correct_answer, source_year))

    if not parsed and not errors:
        errors.append("Excel 文件没有可导入的题目")
    if errors:
        raise ExcelImportError(errors)
    return parsed
