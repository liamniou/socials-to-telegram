FROM python:3.15

WORKDIR /app

COPY ./app/requirements.txt ./

RUN pip install -r requirements.txt

COPY ./app ./

ENTRYPOINT ["python"]

CMD ["main.py"]
