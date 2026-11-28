FROM python:3.12-slim
WORKDIR /srv
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
RUN useradd -m appuser && chown -R appuser /srv
USER appuser
EXPOSE 8000
# Put a TLS-terminating proxy (Caddy, nginx, a cloud load balancer) in front; the app speaks plain HTTP.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
