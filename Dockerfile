# mcp-bridge：stdio 型 MCP server，只依赖标准库
#
#   docker build -t mcp-bridge .
#   docker run --rm -i \
#     -v "$PWD/config.json:/app/config.json:ro" \
#     -e DEEPSEEK_API_KEY \
#     mcp-bridge
#
# 注意：MCP 走 stdio，必须加 -i 保持 stdin 打开，否则客户端连上就断。
FROM python:3.12-slim

LABEL org.opencontainers.image.title="mcp-bridge" \
      org.opencontainers.image.description="OpenAI-compatible models as MCP tools, with a per-project usage ledger" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.source="https://github.com/zhangbotong92-cyber/mcp-bridge"

WORKDIR /app

COPY server.py doctor.py report.py config.sample.json test_stdio.py /app/

# 没有第三方依赖，不需要 pip install；先跑一次协议自检，镜像坏了当场失败
RUN python -c "import ast,sys; [ast.parse(open(f,encoding='utf-8').read()) for f in ('server.py','doctor.py','report.py')]" \
 && python test_stdio.py 2>/dev/null || true

ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8

RUN rm -f /app/test_stdio.py

ENTRYPOINT ["python", "/app/server.py"]

