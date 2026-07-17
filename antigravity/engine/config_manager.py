import copy
import json
import logging
from pathlib import Path
from typing import Any, Dict

from . import secrets

logger = logging.getLogger(__name__)


DEFAULT_CONFIG_DIR = Path.home() / ".config" / "clarinora"
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "settings.json"
DEFAULT_OCR_JOB_URL = "https://paddleocr.aistudio-app.com/api/v2/ocr/jobs"
DEFAULT_OCR_MODEL = "PaddleOCR-VL-1.5"

ENGINE_ROOT = Path(__file__).resolve().parent
PROMPT_PROJECT_DIR = ENGINE_ROOT / "resources" / "prompt_engineering"
PROMPT_FALLBACK_DIR = DEFAULT_CONFIG_DIR / "prompt_engineering"
PROMPT_ROOT = PROMPT_PROJECT_DIR if PROMPT_PROJECT_DIR.exists() else PROMPT_FALLBACK_DIR

CONFIG_VERSION = 3

# 敏感字段：配置里保存的是 keyring 引用（存于 <section>.<ref_key>），
# 运行时通过 get_secret() 解析出明文。旧配置里的明文 <plain_key> 会在
# 首次加载时迁移进 keyring。
SECRET_FIELDS = {
    "ocr_api": {"plain_key": "token", "ref_key": "token_ref", "secret_name": "ocr_token"},
    "prompt_llm": {"plain_key": "api_key", "ref_key": "api_key_ref", "secret_name": "prompt_llm_key"},
    "extract_llm": {"plain_key": "api_key", "ref_key": "api_key_ref", "secret_name": "extract_llm_key"},
    "agent_llm": {"plain_key": "api_key", "ref_key": "api_key_ref", "secret_name": "agent_llm_key"},
}

DEFAULT_VALUES = {
    "ui": {
        "theme": "dark",
        "language": "zh_CN",
        "font_scale": 1.0,
    },
    "pipeline": {
        "extraction_template": "",
    },
    "execution": {
        # 批量/流水线同时处理的病人数；1=串行（默认）
        "max_parallel_patients": 1,
    },
    "ocr_api": {
        "url": DEFAULT_OCR_JOB_URL,
        "token_ref": "",
        "model": DEFAULT_OCR_MODEL,
        "preset": "paper_photo",
        "custom_params": {},
        "user_presets": [],  # [{key,label,description,params}]
    },
    "prompt_llm": {
        "provider": "",
        "api_key_ref": "",
        "base_url": "",
        "model": "gpt-4o-mini",
        "temperature": 0.1,
        "max_tokens": 2000,
    },
    "extract_llm": {
        "provider": "",
        "api_key_ref": "",
        "base_url": "",
        "model": "gpt-4o-mini",
        "temperature": 0.1,
        "max_tokens": 2000,
    },
    "agent_llm": {
        "provider": "",
        "api_key_ref": "",
        "base_url": "",
        "model": "gpt-4o-mini",
        "temperature": 0.2,
        "max_tokens": 2000,
    },
    "prompt": {
        "excel_template": str(PROMPT_ROOT / "Igg4模版.xlsx"),
        "auto_rules": str(PROMPT_ROOT / "config" / "auto_rules.yaml"),
        "blueprint": str(PROMPT_ROOT / "config" / "prompt_blueprint.yaml"),
        "template": str(PROMPT_ROOT / "promptforge" / "templates" / "prompt.md.jinja"),
        "output": str(PROMPT_ROOT / "generated" / "IgG4_auto.md"),
    },
}


def _deep_merge(base: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    """将 incoming 深度合并进 base（就地修改 base 并返回）。"""
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


class ConfigManager:
    """集中管理应用配置并持久化到 JSON 文件。敏感字段经 keyring 存储。"""

    def __init__(self, filepath: Path = DEFAULT_CONFIG_FILE):
        self.filepath = filepath
        self.data: Dict[str, Any] = {}
        self.cloud_file = DEFAULT_CONFIG_DIR / "cloud_settings.json"
        self.load()

    def load(self) -> None:
        """读取配置，如果不存在则创建默认文件。"""
        try:
            if self.filepath.exists():
                with open(self.filepath, "r", encoding="utf-8") as fh:
                    self.data = json.load(fh)
            else:
                self.data = copy.deepcopy(DEFAULT_VALUES)
                self.save()
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("配置文件读取失败（%s），已回退到默认配置：%s", self.filepath, exc)
            self.data = copy.deepcopy(DEFAULT_VALUES)
        finally:
            # 用默认值补齐缺失的 section/字段（深合并，保留用户已有值）
            merged = copy.deepcopy(DEFAULT_VALUES)
            _deep_merge(merged, self.data)
            self.data = merged
            self._migrate_secrets()
            self._migrate()

    def _migrate_secrets(self) -> None:
        """把历史明文密钥迁移进 keyring，只在配置里留引用。"""
        changed = False
        for section, spec in SECRET_FIELDS.items():
            conf = self.data.get(section)
            if not isinstance(conf, dict):
                continue
            plain = conf.pop(spec["plain_key"], None)
            if plain and not secrets.is_ref(conf.get(spec["ref_key"], "")):
                ref = secrets.set_secret(spec["secret_name"], plain)
                conf[spec["ref_key"]] = ref
                changed = True
                logger.info("已迁移 %s.%s 至安全存储", section, spec["plain_key"])
            elif plain is not None:
                # 已有 ref，丢弃残留明文
                changed = True
        if changed:
            self.save()

    def save(self) -> None:
        """保存配置到磁盘。"""
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        self.data["_version"] = CONFIG_VERSION
        with open(self.filepath, "w", encoding="utf-8") as fh:
            json.dump(self.data, fh, ensure_ascii=False, indent=2)
        self.sync_to_cloud()

    def get(self, section: str, key: str, default: Any = None) -> Any:
        return self.data.get(section, {}).get(key, default)

    def get_secret(self, section: str) -> str:
        """解析某 section 的敏感字段为明文（未配置返回空串）。"""
        spec = SECRET_FIELDS.get(section)
        if not spec:
            return ""
        ref = self.data.get(section, {}).get(spec["ref_key"], "")
        return secrets.resolve(ref)

    def set_secret(self, section: str, value: str) -> None:
        """把明文密钥写入 keyring，并在配置里保存引用。"""
        spec = SECRET_FIELDS.get(section)
        if not spec:
            raise KeyError(f"未知的敏感字段 section: {section}")
        ref = secrets.set_secret(spec["secret_name"], value or "")
        self.update_section(section, {spec["ref_key"]: ref})

    def update_section(self, section: str, values: Dict[str, Any]) -> None:
        if section not in self.data:
            self.data[section] = {}
        self.data[section].update(values)
        self.save()

    def as_dict(self) -> Dict[str, Any]:
        return self.data

    def _migrate(self):
        version = int(self.data.get("_version", 1))
        if version < 2:
            self.data["ui"].setdefault("language", "zh_CN")
        # v3：密钥字段迁移由 _migrate_secrets 处理
        self.data["_version"] = CONFIG_VERSION

    def sync_to_cloud(self):
        """简易云同步（本地共享文件，可由云盘自动同步）。不含明文密钥。"""
        try:
            self.cloud_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cloud_file, "w", encoding="utf-8") as fh:
                json.dump(self.data, fh, ensure_ascii=False, indent=2)
        except OSError as exc:
            logger.warning("云同步写入失败：%s", exc)

    def sync_from_cloud(self):
        if not self.cloud_file.exists():
            return
        try:
            with open(self.cloud_file, "r", encoding="utf-8") as fh:
                remote = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("云同步读取失败：%s", exc)
            return
        _deep_merge(self.data, remote)
        self._migrate()
        self.save()
