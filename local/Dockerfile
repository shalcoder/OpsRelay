FROM python:3.12-slim
WORKDIR /app
COPY api/requirements.txt .
RUN pip install --no-cache-dir boto3
COPY api ./api
COPY frontend ./frontend
COPY data ./data
CMD ["python","api/local_server.py"]
