FROM node:22-bookworm-slim AS web
WORKDIR /src/web
COPY web/package.json web/package-lock.json ./
# IPv4 first: flaky IPv6 made npm silently drop optional native deps, then `next build`
# tried to download SWC itself and died. Fail here instead if a Linux binary is missing.
ENV NODE_OPTIONS=--dns-result-order=ipv4first
RUN npm ci --no-audit --no-fund --fetch-retries=5 \
    && node -e "for (const p of ['@next/swc-linux-x64-gnu','lightningcss-linux-x64-gnu','@tailwindcss/oxide-linux-x64-gnu']) require.resolve(p + '/package.json')"
COPY web/ ./
RUN rm -f .env*.local
ARG NEXT_PUBLIC_VCF_SESSIONS=1
ENV VCF_STANDALONE=1 NEXT_PUBLIC_VCF_SESSIONS=$NEXT_PUBLIC_VCF_SESSIONS NEXT_TELEMETRY_DISABLED=1
RUN node node_modules/next/dist/bin/next build

FROM python:3.12-slim-bookworm
WORKDIR /app
COPY --from=web /usr/local/bin/node /usr/local/bin/node
COPY model/worker/pyproject.toml model/worker/
COPY model/worker/c4 model/worker/c4
COPY model/worker/service model/worker/service
COPY model/worker/configs model/worker/configs
RUN pip install --no-cache-dir -e "./model/worker[service]"
RUN python -c "import urllib.request,tarfile,io; d=urllib.request.urlopen('https://github.com/ip7z/7zip/releases/download/24.09/7z2409-linux-x64.tar.xz').read(); tarfile.open(fileobj=io.BytesIO(d),mode='r:xz').extract('7zz','/usr/local/bin')" \
    && chmod +x /usr/local/bin/7zz && ln -s /usr/local/bin/7zz /usr/local/bin/7z
COPY --from=web /src/web/.next/standalone /app/web
COPY --from=web /src/web/.next/static /app/web/.next/static
COPY --from=web /src/web/public /app/web/public
COPY deploy/azure/start.sh /opt/vcf/start.sh
ENV WORKSPACE=/data/workspace WORKER_URL=http://127.0.0.1:8001 VCF_PORT=8001 \
    PORT=3000 HOSTNAME=0.0.0.0 C4_PROFILE=azure-lite VCF_SESSIONS=1 \
    PYTHONIOENCODING=utf-8 SEVENZIP_PATH=/usr/local/bin/7zz NEXT_TELEMETRY_DISABLED=1
EXPOSE 3000
CMD ["bash", "/opt/vcf/start.sh"]
