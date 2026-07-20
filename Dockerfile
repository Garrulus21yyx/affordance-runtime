FROM mcr.microsoft.com/playwright/python:v1.61.0-noble@sha256:a9731514f24121d1dcd25d58d0a38146646d290a5998fd80d3e533e7b5e21c69

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/home/pwuser

WORKDIR /workspace
COPY pyproject.toml README.md LICENSE ./
COPY src/affordance_runtime/__init__.py src/affordance_runtime/__init__.py
RUN python -m pip install --no-cache-dir -e '.[dev,web,parent,visual]'
COPY . .
RUN mkdir -p /evidence && \
    chown -R pwuser:pwuser /workspace /home/pwuser /evidence

USER pwuser
CMD ["python", "-m", "pytest", "-q"]
