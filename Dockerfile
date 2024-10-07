FROM python:3.12-slim

ADD requirements.txt ./requirements.txt
ADD privatekey.json ./privatekey.json

RUN pip install -r requirements.txt

ADD . /app/

WORKDIR /app

CMD ["gunicorn", "--timeout", "50", "--bind", "0.0.0.0:8080", "hydroengine_service.main:app"]
