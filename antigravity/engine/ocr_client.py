import json
import re
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

import requests

from .ocr_presets import build_optional_payload, DEFAULT_OCR_PRESET, DEFAULT_OCR_MODEL


DEFAULT_OCR_JOB_URL = "https://paddleocr.aistudio-app.com/api/v2/ocr/jobs"


class AsyncOCRClient:
    def __init__(
        self,
        job_url: str,
        token: str,
        model: str = DEFAULT_OCR_MODEL,
        preset: str = DEFAULT_OCR_PRESET,
        custom_params: Optional[Dict] = None,
        user_presets: Optional[List[Dict]] = None,
        poll_interval: int = 5,
        timeout: int = 60,
        log_callback: Optional[Callable[[str], None]] = None,
    ):
        self.job_url = job_url.rstrip("/")
        self.token = token
        self.model = model or DEFAULT_OCR_MODEL
        self.preset = preset or DEFAULT_OCR_PRESET
        self.custom_params = custom_params or {}
        self.user_presets = user_presets or []
        self.poll_interval = poll_interval
        self.timeout = timeout
        self.log_callback = log_callback

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"bearer {self.token}"}

    def _log(self, message: str) -> None:
        if self.log_callback:
            self.log_callback(message)

    def _build_payload(self) -> str:
        payload = build_optional_payload(
            self.preset,
            user_presets=self.user_presets,
            custom_params=self.custom_params,
        )
        return json.dumps(payload, ensure_ascii=False)

    def process_file(self, file_path: Path) -> List[Dict]:
        job_id = self.submit_file(file_path)
        jsonl_url = self.wait_for_result(job_id)
        return self.fetch_results(jsonl_url)

    def submit_file(self, file_path: Path) -> str:
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        data = {
            "model": self.model,
            "optionalPayload": self._build_payload(),
        }
        with file_path.open("rb") as fh:
            response = requests.post(
                self.job_url,
                headers=self._headers(),
                data=data,
                files={"file": fh},
                timeout=self.timeout,
            )

        if response.status_code != 200:
            raise RuntimeError(f"OCR job submit failed: HTTP {response.status_code} {response.text[:200]}")

        payload = response.json()
        try:
            job_id = payload["data"]["jobId"]
        except KeyError as exc:
            raise RuntimeError(f"OCR job response missing jobId: {payload}") from exc

        self._log(f"Job submitted: {job_id}")
        return job_id

    def wait_for_result(self, job_id: str) -> str:
        while True:
            response = requests.get(f"{self.job_url}/{job_id}", headers=self._headers(), timeout=self.timeout)
            if response.status_code != 200:
                raise RuntimeError(f"OCR job poll failed: HTTP {response.status_code} {response.text[:200]}")

            payload = response.json()
            data = payload.get("data", {})
            state = data.get("state")
            if state == "pending":
                self._log("Job pending")
            elif state == "running":
                progress = data.get("extractProgress") or {}
                total = progress.get("totalPages")
                extracted = progress.get("extractedPages")
                if total is not None and extracted is not None:
                    self._log(f"Job running: {extracted}/{total} pages")
                else:
                    self._log("Job running")
            elif state == "done":
                result_url = data.get("resultUrl") or {}
                json_url = result_url.get("jsonUrl")
                if not json_url:
                    raise RuntimeError(f"OCR job completed without jsonUrl: {payload}")
                progress = data.get("extractProgress") or {}
                extracted = progress.get("extractedPages")
                if extracted is not None:
                    self._log(f"Job done: {extracted} pages extracted")
                else:
                    self._log("Job done")
                return json_url
            elif state == "failed":
                error_msg = data.get("errorMsg", "unknown error")
                raise RuntimeError(f"OCR job failed: {error_msg}")
            else:
                self._log(f"Job state: {state}")

            time.sleep(self.poll_interval)

    def fetch_results(self, jsonl_url: str) -> List[Dict]:
        response = requests.get(jsonl_url, timeout=self.timeout)
        response.raise_for_status()

        results: List[Dict] = []
        for line in response.text.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            result = item.get("result")
            if result:
                results.append(result)
        return results


def save_layout_results(
    results: List[Dict],
    output_base: Path,
    download_images: bool = False,
    save_json: bool = False,
    save_layout: bool = True,
    image_meta: Optional[Dict] = None,
    timeout: int = 60,
) -> int:
    """保存 md + 精简 layout.json（坐标溯源）。

    layout 文件：``{output_base.name}_{page_num}.layout.json``
    """
    from .ocr_layout import extract_layout_pages, save_layout_json

    output_base.parent.mkdir(parents=True, exist_ok=True)
    page_num = 0

    for result in results:
        for res in result.get("layoutParsingResults", []):
            markdown = res.get("markdown", {})
            md_path = output_base.with_name(f"{output_base.name}_{page_num}.md")
            md_path.write_text(_strip_image_references(markdown.get("text", "")), encoding="utf-8")

            if download_images:
                for img_path, img_url in markdown.get("images", {}).items():
                    image_path = output_base.parent / img_path
                    image_path.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        image_path.write_bytes(requests.get(img_url, timeout=timeout).content)
                    except Exception:
                        pass

                for img_name, img_url in res.get("outputImages", {}).items():
                    try:
                        response = requests.get(img_url, timeout=timeout)
                        if response.status_code == 200:
                            image_path = output_base.parent / f"{img_name}_{page_num}.jpg"
                            image_path.parent.mkdir(parents=True, exist_ok=True)
                            image_path.write_bytes(response.content)
                    except Exception:
                        pass

            page_num += 1

    if save_layout:
        try:
            pages = extract_layout_pages(
                results,
                page_key=output_base.name,
                image_meta=image_meta or {},
            )
            for layout in pages:
                idx = layout.get("page_index", 0)
                layout_path = output_base.with_name(f"{output_base.name}_{idx}.layout.json")
                save_layout_json(layout, layout_path)
        except Exception:
            # layout 失败不阻断 OCR 主流程
            pass

    if save_json:
        json_path = output_base.with_name(f"{output_base.name}_result.json")
        json_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return page_num


def extract_markdown_text(results: List[Dict]) -> Optional[str]:
    texts: List[str] = []
    for result in results:
        for res in result.get("layoutParsingResults", []):
            text = _strip_image_references(res.get("markdown", {}).get("text", ""))
            if text:
                texts.append(text)
    return "\n".join(texts) if texts else None


def _strip_image_references(text: str) -> str:
    text = re.sub(r"<div[^>]*>\s*<img\b[^>]*>\s*</div>", "", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<img\b[^>]*>", "", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"!\[[^\]]*]\([^)]*\)", "", text)
    return text.strip()
