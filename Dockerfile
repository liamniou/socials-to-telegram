FROM python:3.12

WORKDIR /app

COPY ./app/req.txt ./

RUN pip install -r req.txt

COPY ./app ./

ENTRYPOINT ["python"]

CMD ["main.py"]
