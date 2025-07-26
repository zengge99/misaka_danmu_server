import yaml
from pathlib import Path
from typing import Any, Dict, Tuple

from pydantic import BaseModel
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, EnvSettingsSource

# 1. 为配置的不同部分创建 Pydantic 模型，提供类型提示和默认值
class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8000

class DatabaseConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 3306
    user: str = "root"
    password: str = "password"
    name: str = "danmaku_db"

class JWTConfig(BaseModel):
    secret_key: str = "a_very_secret_key_that_should_be_changed"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440 # 1 day

# 2. 创建一个自定义的配置源，用于从 YAML 文件加载设置
class YamlConfigSettingsSource(PydanticBaseSettingsSource):
    def __init__(self, settings_cls: type[BaseSettings]):
        super().__init__(settings_cls)
        # 在项目根目录的 config/ 文件夹下查找 config.yml
        self.yaml_file = Path(__file__).parent.parent / "config" / "config.yml"

    def get_field_value(self, field, field_name):
        return None, None, False

    def __call__(self) -> Dict[str, Any]:
        if not self.yaml_file.is_file():
            return {}
        with open(self.yaml_file, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}


# 3. 定义主设置类，它将聚合所有配置
class Settings(BaseSettings):
    server: ServerConfig = ServerConfig()
    database: DatabaseConfig = DatabaseConfig()
    jwt: JWTConfig = JWTConfig()

    class Config:
        # 为环境变量设置前缀，避免与系统变量冲突
        # 例如，在容器中设置环境变量 DANMUAPI_SERVER__PORT=8080
        env_prefix = "DANMUAPI_"
        case_sensitive = False
        env_nested_delimiter = '__'

    @classmethod
    def settings_customise_sources(
        cls, settings_cls: type[BaseSettings], **kwargs
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        # 定义加载源的优先级:
        # 1. 环境变量 (最高)
        # 2. YAML 文件
        # 3. Pydantic 模型中的默认值 (最低)
        return (
            EnvSettingsSource(settings_cls, **kwargs),
            YamlConfigSettingsSource(settings_cls),
        )


settings = Settings()
