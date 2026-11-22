FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates tzdata && rm -rf /var/lib/apt/lists/*
# the scan stamps rows with local time, and the site shows Turkish auction times
ENV TZ=Europe/Istanbul PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8
WORKDIR /app
COPY cloud_job.py .
CMD ["python", "cloud_job.py"]
