"""
OpenNEM Settings Schema

Everything that can be changed is set here and can be overwritten with ENV settings
"""
from datetime import UTC
from datetime import timezone as pytimezone
from pathlib import Path

from pydantic import BaseSettings
from pydantic.class_validators import validator

SUPPORTED_LOG_LEVEL_NAMES = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class SettingsException(Exception):
    pass


class OpennemSettings(BaseSettings):
    env: str = "local"

    log_level: str = "DEBUG"

    timezone: pytimezone | str = UTC

    # Set maintenance mode - workers won't run and API will return a MaintenanceMode response
    maintenance_mode: bool = False

    # @NOTE pydantic settings assignment type mismatch from mypy
    # https://github.com/samuelcolvin/pydantic/issues/1490
    db_url: str = "postgresql://user:pass@127.0.0.1:15444/opennem"  # type: ignore

    # if we're doing a dry run
    dry_run: bool = False

    cache_url: str = "redis://127.0.0.1"

    sentry_url: str | None = None

    prometheus_url: str | None = None

    # This is the module where crawlers are found
    crawlers_module: str = "opennem.crawlers"

    google_places_api_key: str | None = None

    requests_cache_path: str = ".requests"

    # Slack notifications
    slack_notifications: bool = True
    slack_hook_url: str | None = None

    # web hook for data channel
    slack_data_webhook: str | None = None

    # APVI
    apvi_token: str | None = None

    export_local: bool = False

    s3_bucket_path: str = "s3://data.opennem.org.au/"
    backup_bucket_path: str = "backups.opennem.org.au"
    photos_bucket_path: str = "s3://photos.opennem.org.au/"

    # opennem output settings
    interval_default: str = "15m"
    period_default: str = "7d"
    precision_default: int = 4

    # show database debug
    db_debug: bool = False

    # cache scada values for
    cache_scada_values_ttl_sec: int = 60 * 5

    # asgi server settings
    server_host: str = "0.0.0.0"
    server_port: int = 8000
    server_reload: bool = False
    server_ssl: bool = False

    # timeout on http requests
    # see opennem.utils.http
    http_timeout: int = 20

    # number of retries by default
    http_retries: int = 5

    # cache http requests locally
    http_cache_local: bool = False
    http_verify_ssl: bool = True
    https_proxy_url: str | None = None  # @note don't let it confict with env HTTP_PROXY

    _static_folder_path: str = "opennem/static/"

    # output schema options
    # output values for region, network etc. in lower case
    schema_output_lowercase_strings: bool = True
    # prepend the country code in the id
    schema_output_id_country: bool = False

    # workers
    workers_run: bool = True
    workers_db_run: bool = True

    # templates folder relative to opennem module root
    templates_dir: str = "templates"

    # monitoring
    monitoring_alert_sms: str | None = None
    monitoring_alert_slack_user: list[str] | None = None

    # api key cookie settings
    api_app_auth_name: str = "onau"
    api_user_auth_name: str = "onuu"
    api_app_auth_key_length: int = 24
    api_auth_cookie_domain: str = "opennem.org.au"

    # willy weather client
    willyweather_api_key: str | None = None

    # cloudflare
    cloudflare_account_id: str | None = None
    cloudflare_api_key: str | None = None

    tmp_file_prefix: str | None = "opennem_"

    slack_admin_alert: list[str] | None = ["nik"]

    # alert threshold level in minutes for interval delay monitoring
    monitor_interval_alert_threshold: int | None = 10

    # feature flags
    run_crawlers: bool = True  # do we enable the crawlers
    flows_and_emissions_v2: bool = False  # use the aggregate tables rather than the views
    flows_and_emissions_v3: bool = False  #
    opennem_power_flows: bool = False  # in the power outputs, use the aggregate flows
    opennem_flows_v3: bool = False  # use aggregate in opennem.aggregates.network_flows_v3 per-interval
    redirect_api_static: bool = True  # redirect api endpoints to statics where applicable
    per_interval_aggregate_processing: bool = False  # process per interval aggregates

    # send daily fueltech summary
    send_daily_fueltech_summary: bool = True

    # profiler options
    profiler_level: str = "NOISY"

    # feedback
    feedback_send_to_github: bool = False
    feedback_send_to_slack: bool = True
    feedback_slack_hook_url: str | None = None
    feedback_tag_users: list[str] = ["U047H1T2JJK", "nik"]

    # api messages
    api_messages: list[str] = [
        "OpenNEM API will be moving behind a login soon. Please see the discssion at https://github.com/opennem/opennem/discussions/243"
    ]

    # pylint: disable=no-self-argument
    @validator("log_level")
    def validate_log_level(cls, log_value: str) -> str | None:
        _log_value = log_value.upper().strip()

        if _log_value not in SUPPORTED_LOG_LEVEL_NAMES:
            raise SettingsException(f"Invalid log level: {_log_value}")

        return _log_value

    @property
    def static_folder_path(self) -> str:
        static_path: Path = Path(self._static_folder_path)

        if not static_path.is_dir():
            raise SettingsException(f"{static_path} is not a folder")

        return str(static_path.resolve())

    @property
    def debug(self) -> bool:
        return self.env in ("local", "development", "staging")

    @property
    def is_prod(self) -> bool:
        if self.db_url and "opennem03" in self.db_url:
            return True

        return self.env in ("production", "prod")

    @property
    def is_dev(self) -> bool:
        return self.env in ("local", "development", "staging")

    class Config:
        fields = {
            "env": {"env": "ENV"},
            "log_level": {"env": "LOG_LEVEL"},
            "_static_folder_path": {"env": "STATIC_PATH"},
            "db_url": {"env": "DATABASE_HOST_URL"},
            "cache_url": {"env": "REDIS_HOST_URL"},
            "slack_hook_url": {"env": "MONITORING_SLACK_HOOK"},
            "s3_bucket_path": {"env": "S3_DATA_BUCKET_PATH"},
            "server_port": {"env": "PORT"},
            "server_host": {"env": "HOST"},
            "cache_scada_values_ttl_sec": {"env": "CACHE_SCADA_TTL"},
        }
