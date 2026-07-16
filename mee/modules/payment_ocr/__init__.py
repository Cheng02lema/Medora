from pathlib import Path
from typing import Optional

from ..ocr_client import AsyncOCRClient, DEFAULT_OCR_MODEL, extract_markdown_text, save_layout_results


def process_payment_images(
    input_dir: str,
    output_dir: str,
    api_url: str,
    token: str,
    model: str = DEFAULT_OCR_MODEL,
    preset: str = "original",
    pattern: str = "-缴费情况.jpg",
    log_callback=None,
) -> int:
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    matches = [
        file
        for file in input_path.rglob("*")
        if file.is_file() and file.name.lower().endswith(pattern.lower())
    ]

    def log(msg: str):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)

    client = AsyncOCRClient(api_url, token, model=model or DEFAULT_OCR_MODEL, preset=preset, log_callback=log)

    for file_path in matches:
        log(f"处理缴费文件：{file_path.name}")
        results = client.process_file(file_path)
        if not results:
            continue
        markdown_text = extract_markdown_text(results)
        if not markdown_text:
            continue
        rel = file_path.relative_to(input_path)
        out_file = output_path / rel.parent / (file_path.stem + ".md")
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(markdown_text, encoding="utf-8")
        log(f"已输出 {out_file}")
    return len(matches)
