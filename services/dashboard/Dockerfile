FROM python:3.12-slim
WORKDIR /app
COPY services/dashboard/requirements.txt services/dashboard/requirements.txt
RUN pip install --no-cache-dir -r services/dashboard/requirements.txt
COPY services/dashboard/ services/dashboard/
EXPOSE 8501
CMD ["streamlit", "run", "services/dashboard/app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true", "--browser.gatherUsageStats=false"]