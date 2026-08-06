FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY . .
EXPOSE 4000

CMD ["flask", "run", "--host=10.0.0.125", "--port=4000"]