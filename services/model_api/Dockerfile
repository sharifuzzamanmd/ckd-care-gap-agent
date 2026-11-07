FROM python:3.12-slim
WORKDIR /app
COPY services/model_api/requirements.txt services/model_api/requirements.txt
RUN pip install --no-cache-dir -r services/model_api/requirements.txt
COPY services/__init__.py services/__init__.py
COPY services/model_api/ services/model_api/
COPY models/ models/
EXPOSE 8000
CMD ["uvicorn", "services.model_api.main:app", "--host", "0.0.0.0", "--port", "8000"]