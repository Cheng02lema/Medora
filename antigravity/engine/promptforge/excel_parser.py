from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional
from zipfile import ZipFile


NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_PKG = "http://schemas.openxmlformats.org/package/2006/relationships"


@dataclass
class SheetMeta:
    name: str
    target: str


class ExcelReader:
    """Lightweight XLSX reader implemented with stdlib only."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if not self.path.exists():
            raise FileNotFoundError(self.path)

    def list_sheets(self) -> List[str]:
        return [sheet.name for sheet in self._load_workbook()[0]]

    def read(self, sheet: Optional[str] = None) -> List[List[str]]:
        sheets, shared_strings = self._load_workbook()
        sheet_meta = self._resolve_sheet(sheets, sheet)
        with ZipFile(self.path) as archive:
            xml_bytes = archive.read(f"xl/{sheet_meta.target}")
        return self._parse_sheet(xml_bytes, shared_strings)

    def _load_workbook(self) -> tuple[List[SheetMeta], List[str]]:
        with ZipFile(self.path) as archive:
            workbook_root = ET.fromstring(archive.read("xl/workbook.xml"))
            rel_root = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            shared_strings = []
            try:
                shared_strings = self._load_shared_strings(archive)
            except KeyError:
                pass

        ns_main = {"m": NS_MAIN, "r": NS_REL}
        sheets: List[SheetMeta] = []
        rel_map: Dict[str, str] = {}

        for rel in rel_root.findall("{%s}Relationship" % NS_PKG):
            rel_map[rel.attrib["Id"]] = rel.attrib["Target"]

        for sheet in workbook_root.find("m:sheets", ns_main):
            rel_id = sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
            target = rel_map.get(rel_id)
            if not target:
                continue
            sheets.append(SheetMeta(name=sheet.attrib.get("name", "Sheet1"), target=target))

        if not sheets:
            raise ValueError("No sheets found in workbook")

        return sheets, shared_strings

    def _load_shared_strings(self, archive: ZipFile) -> List[str]:
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
        entries = []
        for si in root.findall("{%s}si" % NS_MAIN):
            text_chunks = []
            for t in si.iter("{%s}t" % NS_MAIN):
                text_chunks.append(t.text or "")
            entries.append("".join(text_chunks))
        return entries

    def _resolve_sheet(self, sheets: List[SheetMeta], selector: Optional[str]) -> SheetMeta:
        if selector is None:
            return sheets[0]
        if selector.isdigit():
            index = int(selector)
            if index < 0 or index >= len(sheets):
                raise IndexError(f"Sheet index {index} out of range")
            return sheets[index]
        for sheet in sheets:
            if sheet.name == selector:
                return sheet
        raise ValueError(f"Sheet {selector} not found; available: {[s.name for s in sheets]}")

    def _parse_sheet(self, xml_bytes: bytes, shared_strings: List[str]) -> List[List[str]]:
        root = ET.fromstring(xml_bytes)
        sheet_data = root.find("{%s}sheetData" % NS_MAIN)
        rows: List[List[str]] = []
        if sheet_data is None:
            return rows
        for row in sheet_data.findall("{%s}row" % NS_MAIN):
            cells = {}
            for cell in row.findall("{%s}c" % NS_MAIN):
                ref = cell.attrib.get("r", "")
                column = self._column_index(ref)
                value = self._cell_value(cell, shared_strings)
                cells[column] = value
            if not cells:
                continue
            max_index = max(cells.keys())
            row_values = [""] * (max_index + 1)
            for idx, value in cells.items():
                row_values[idx] = value
            rows.append(self._trim_row(row_values))
        return rows

    def _cell_value(self, cell: ET.Element, shared_strings: List[str]) -> str:
        cell_type = cell.attrib.get("t")
        if cell_type == "s":
            idx = int(cell.findtext("{%s}v" % NS_MAIN, default="0"))
            return shared_strings[idx] if idx < len(shared_strings) else ""
        if cell_type == "inlineStr":
            return "".join(t.text or "" for t in cell.findall(".{%s}t" % NS_MAIN))
        return cell.findtext("{%s}v" % NS_MAIN, default="")

    def _column_index(self, cell_ref: str) -> int:
        match = re.match(r"([A-Z]+)", cell_ref)
        label = match.group(1) if match else "A"
        index = 0
        for char in label:
            index = index * 26 + (ord(char) - ord("A") + 1)
        return index - 1

    def _trim_row(self, row: List[str]) -> List[str]:
        trimmed = list(row)
        while trimmed and (trimmed[-1] is None or str(trimmed[-1]).strip() == ""):
            trimmed.pop()
        return trimmed
