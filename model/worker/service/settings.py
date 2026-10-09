"""Cài đặt dịch vụ, lấy từ biến môi trường; test truyền Settings trực tiếp."""
import os
from dataclasses import dataclass, field
from pathlib import Path


def _env_workspace() -> Path:
    return Path(os.environ.get("WORKSPACE", "../workspace"))


@dataclass
class Settings:
    workspace: Path = field(default_factory=_env_workspace)
    sevenzip: str = field(default_factory=lambda: os.environ.get("SEVENZIP_PATH", "7z"))
    profile: str = field(default_factory=lambda: os.environ.get("C4_PROFILE", "local-4060"))
    remote_token: str = field(default_factory=lambda: os.environ.get("VCF_REMOTE_TOKEN", ""))
    remote_lease_sec: int = field(
        default_factory=lambda: int(os.environ.get("VCF_REMOTE_LEASE_SEC", "5400")))
    remote_max_result_mb: int = field(
        default_factory=lambda: int(os.environ.get("VCF_REMOTE_MAX_RESULT_MB", "200")))
    # Thí nghiệm có trọng số seed (t1/ckpt/seed_latest.pth): Colab dùng lại, bỏ bước train.
    # Trống = tự dò thư mục mới nhất trong <workspace>/experiments; "none" = tắt.
    t1_exp: str = field(default_factory=lambda: os.environ.get("VCF_T1_EXP", "").strip())

    def __post_init__(self):
        self.workspace = Path(self.workspace)

    @property
    def uploads(self) -> Path:
        return self.workspace / "uploads"

    @property
    def datasets(self) -> Path:
        return self.workspace / "datasets"

    @property
    def jobs(self) -> Path:
        return self.workspace / "jobs"

    @property
    def remote(self) -> Path:
        return self.workspace / "remote"
