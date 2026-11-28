FROM python:3.12-slim
WORKDIR /app
COPY services/agent/requirements.txt services/agent/requirements.txt
RUN pip install --no-cache-dir -r services/agent/requirements.txt
COPY services/__init__.py services/__init__.py
COPY services/agent/ services/agent/
EXPOSE 8001
CMD ["uvicorn", "services.agent.main:app", "--host", "0.0.0.0", "--port", "8001"]