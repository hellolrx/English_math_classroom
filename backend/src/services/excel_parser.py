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

HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "question_text": ("题目", "题目内容", "question", "question_text"),
    "option_a": ("选项A", "選項A", "A", "option_a"),
    "option_b": ("选项B", "選項B", "B", "option_b"),
    "option_c": ("选项C", "選項C", "C", "option_c"),
    "option_d": ("选项D", "選項D", "D", "option_d"),
    "correct_answer": ("正确答案", "正確答案", "答案", "correct_answer", "answer"),
    "explanation": ("解析", "解釋", "explanation"),
}


@dataclass(frozen=True)
class ParsedQuestion:
    row_number: int
    question_text: str
    question_image_url: str | None
    options: dict[str, str]
    option_image_urls: dict[str, str | None]
    correct_answer: str
    explanation: str | None


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
        if field != "explanation" and field not in columns:
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
    return f"data:{media_type};base64,{base64.b64encode(content).decode('ascii')}"


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
        options = {
            key: _text(values[columns[f"option_{key.lower()}"]] if columns[f"option_{key.lower()}"] < len(values) else None)
            for key in ("A", "B", "C", "D")
        }
        option_image_urls = {
            key: formula_images.get(_cell_key(row_number, columns[f"option_{key.lower()}"]))
            or anchored_images.get(_cell_key(row_number, columns[f"option_{key.lower()}"]))
            for key in ("A", "B", "C", "D")
        }
        for key in ("A", "B", "C", "D"):
            if option_image_urls[key] and _DISPIMG_RE.search(options[key]):
                options[key] = ""
        raw_answer = _text(values[columns["correct_answer"]] if columns["correct_answer"] < len(values) else None)
        correct_answer = _correct_key(raw_answer)
        explanation = None
        if "explanation" in columns and columns["explanation"] < len(values):
            explanation = _text(values[columns["explanation"]]) or None

        row_errors: list[str] = []
        if not question_text and not question_image_url:
            row_errors.append("题目不能为空（可填写文字或插入图片）")
        for key, option_text in options.items():
            if not option_text and not option_image_urls[key]:
                row_errors.append(f"选项{key}不能为空（可填写文字或插入图片）")
        if correct_answer is None:
            row_errors.append("正确答案必须是 A、B、C、D 或 1、2、3、4")
        if row_errors:
            errors.append(f"第 {row_number} 行：{'；'.join(row_errors)}")
            continue
        parsed.append(ParsedQuestion(row_number, question_text, question_image_url, options, option_image_urls, correct_answer, explanation))

    if not parsed and not errors:
        errors.append("Excel 文件没有可导入的题目")
    if errors:
        raise ExcelImportError(errors)
    return parsed
