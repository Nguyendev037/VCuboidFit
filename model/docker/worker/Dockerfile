# Image model: worker FastAPI (Tầng 0, CPU). KHÔNG có web, KHÔNG có dữ liệu Tầng 1 nướng sẵn.
#   docker build -f model/docker/worker/Dockerfile -t vcf-worker:0.1 .        (từ gốc repo)
#   docker run -d --name vcf-worker -e VCF_PORT=8001 -p 8001:8001 -v vcf-ws:/data/workspace vcf-worker:0.1
# Không apt (Docker local không ra cổng 80 — xem known-gotchas); mọi gói qua HTTPS/pip.

FROM python:3.12-slim-bookworm
WORKDIR /app
COPY model/worker/pyproject.toml model/worker/
COPY model/worker/c4 model/worker/c4
COPY model/worker/service model/worker/service
COPY model/worker/configs model/worker/configs
# editable: c4/config.py tìm configs/ cạnh package (parent.parent)
RUN pip install --no-cache-dir -e "./model/worker[service]"
COPY model/docker/worker/start.sh /opt/vcf/
ENV WORKSPACE=/data/workspace PYTHONIOENCODING=utf-8 VCF_PORT=8001
VOLUME /data/workspace
EXPOSE 8001
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import os,urllib.request as u; u.urlopen('http://127.0.0.1:%s/health' % os.environ['VCF_PORT'], timeout=4)"
CMD ["sh", "/opt/vcf/start.sh"]
