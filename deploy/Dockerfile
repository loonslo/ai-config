FROM python:3.14-slim
WORKDIR /app
COPY server/requirements.txt /app/requirements.txt
COPY server/requirements.lock.txt /app/requirements.lock.txt
RUN pip install --no-cache-dir -r requirements.lock.txt
COPY server /app/server
RUN useradd --uid 10001 --create-home app && mkdir /data && chown app:app /data
USER app
EXPOSE 8000
CMD ["uvicorn", "server.app:production_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
