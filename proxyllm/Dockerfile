FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi uvicorn httpx

COPY proxyllm/server.py .

EXPOSE 9099

CMD ["python", "server.py"]
