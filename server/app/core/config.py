from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import BaseModel
from pathlib import Path


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    app_name: str = "OpenClaw Community"
    debug: bool = True

    # 数据库
    db_path: str = str(Path(__file__).parent.parent.parent / "data" / "openclaw.db")
    lancedb_path: str = str(Path(__file__).parent.parent.parent / "data" / "lancedb")

    # === 供应商配置（{NAME}_AUTH_TOKEN + {NAME}_BASE_URL）===
    openrouter_auth_token: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    openai_auth_token: str = ""
    openai_base_url: str = "https://api.openai.com/v1"

    anthropic_auth_token: str = ""
    anthropic_base_url: str = "https://api.anthropic.com/v1"

    siliconflow_auth_token: str = ""
    siliconflow_base_url: str = "https://api.siliconflow.cn/v1"

    # Agent 默认配置
    default_speak_interval: int = 60  # 默认发言间隔（秒）
    max_agents: int = 20


settings = Settings()


# --- 多供应商模型注册表 ---

class ModelProvider(BaseModel):
    """单个供应商配置"""
    name: str       # 供应商标识（对应 .env 中的前缀）
    model_id: str   # 该供应商下的模型 ID

    def get_auth_token(self) -> str:
        return getattr(settings, f"{self.name}_auth_token", "")

    def get_base_url(self) -> str:
        return getattr(settings, f"{self.name}_base_url", "")

    def is_available(self) -> bool:
        return bool(self.get_auth_token())


class ModelEntry(BaseModel):
    """一个模型可以有多个供应商，按优先级排列"""
    display_name: str
    providers: list[ModelProvider]

    def get_active_provider(self) -> ModelProvider | None:
        """返回第一个有 token 的供应商"""
        for p in self.providers:
            if p.is_available():
                return p
        return None


# 模型注册表：key 是前端/数据库中存储的模型标识
MODEL_REGISTRY: dict[str, ModelEntry] = {
    "arcee/trinity-large-preview": ModelEntry(
        display_name="Arcee Trinity Large Preview (free)",
        providers=[
            ModelProvider(name="openrouter", model_id="arcee-ai/trinity-large-preview:free"),
        ],
    ),
    "stepfun/step-3.5-flash": ModelEntry(
        display_name="StepFun Step 3.5 Flash (free)",
        providers=[
            ModelProvider(name="openrouter", model_id="stepfun/step-3.5-flash:free"),
        ],
    ),
    # 唤醒选人用的小模型
    "wakeup-model": ModelEntry(
        display_name="Wakeup Selector (小模型)",
        providers=[
            ModelProvider(name="openrouter", model_id="stepfun/step-3.5-flash:free"),
        ],
    ),
}


def resolve_model(model_key: str) -> tuple[str, str, str] | None:
    """
    解析模型标识，返回 (base_url, auth_token, model_id)。
    找不到或没有可用供应商返回 None。
    """
    entry = MODEL_REGISTRY.get(model_key)
    if not entry:
        return None
    provider = entry.get_active_provider()
    if not provider:
        return None
    return provider.get_base_url(), provider.get_auth_token(), provider.model_id


def list_available_models() -> list[dict]:
    """返回所有有可用供应商的模型列表（给前端下拉框用）"""
    result = []
    for key, entry in MODEL_REGISTRY.items():
        if key == "wakeup-model":
            continue  # 内部模型不暴露给前端
        provider = entry.get_active_provider()
        result.append({
            "id": key,
            "name": entry.display_name,
            "available": provider is not None,
            "provider": provider.name if provider else None,
        })
    return result
