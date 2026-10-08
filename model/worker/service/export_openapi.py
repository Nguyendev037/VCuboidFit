"""python -m service.export_openapi > openapi.json — hợp đồng API cho `openapi-typescript`."""
import json
import sys
import tempfile

from service.main import create_app
from service.settings import Settings


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:  # app chỉ để đọc schema: không chạm workspace thật
        spec = create_app(Settings(workspace=tmp)).openapi()
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdout.write(json.dumps(spec, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
