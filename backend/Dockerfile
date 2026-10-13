FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY content ./content
COPY alembic.ini .
COPY migrations ./migrations
COPY start.sh ./start.sh

EXPOSE 8000

CMD ["sh", "start.sh"]
