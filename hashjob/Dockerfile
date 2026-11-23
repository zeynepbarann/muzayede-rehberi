FROM python:3.12-slim
RUN pip install --no-cache-dir pillow==11.3.0
ENV PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8
WORKDIR /app
COPY hash_job.py .
CMD ["python", "hash_job.py"]
