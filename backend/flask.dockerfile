FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY . .
EXPOSE 4000

CMD ["flask", "run", "--host=192.168.1.100", "--port=4000"]