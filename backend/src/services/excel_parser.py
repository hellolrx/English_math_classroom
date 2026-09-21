from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Any

from openpyxl import load_workbook


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
    options: dict[str, str]
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


def parse_question_excel(content: bytes) -> list[ParsedQuestion]:
    if not content:
        raise ExcelImportError(["Excel 文件为空"])
    try:
        workbook = load_workbook(filename=BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:  # openpyxl exposes several parser-specific exceptions
        raise ExcelImportError(["无法读取 Excel 文件，请确认文件格式为 .xlsx"]) from exc

    sheet = workbook.active
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
        options = {
            key: _text(values[columns[f"option_{key.lower()}"]] if columns[f"option_{key.lower()}"] < len(values) else None)
            for key in ("A", "B", "C", "D")
        }
        raw_answer = _text(values[columns["correct_answer"]] if columns["correct_answer"] < len(values) else None)
        correct_answer = _correct_key(raw_answer)
        explanation = None
        if "explanation" in columns and columns["explanation"] < len(values):
            explanation = _text(values[columns["explanation"]]) or None

        row_errors: list[str] = []
        if not question_text:
            row_errors.append("题目不能为空")
        for key, option_text in options.items():
            if not option_text:
                row_errors.append(f"选项{key}不能为空")
        if correct_answer is None:
            row_errors.append("正确答案必须是 A、B、C、D 或 1、2、3、4")
        if row_errors:
            errors.append(f"第 {row_number} 行：{'；'.join(row_errors)}")
            continue
        parsed.append(ParsedQuestion(row_number, question_text, options, correct_answer, explanation))

    if not parsed and not errors:
        errors.append("Excel 文件没有可导入的题目")
    if errors:
        raise ExcelImportError(errors)
    return parsed
