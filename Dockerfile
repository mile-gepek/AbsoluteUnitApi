FROM python:3.13

WORKDIR /app

RUN apt-get update && apt-get install -y build-essential && \
    apt-get clean

COPY . /app

RUN pip install .

CMD ["python", "-m", "absolute_unit"]
