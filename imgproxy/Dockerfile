FROM python:3.12-slim
RUN pip install --no-cache-dir pillow==11.3.0
WORKDIR /app
COPY main.py .
ENV PYTHONUNBUFFERED=1
CMD ["python", "main.py"]
