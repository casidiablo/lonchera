FROM python:3.12.4-slim

WORKDIR /app

COPY requirements.txt /app
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

ENV PYTHONUNBUFFERED 1

CMD ["python", "main.py"]
