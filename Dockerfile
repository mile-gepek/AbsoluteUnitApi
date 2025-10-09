FROM python

WORKDIR /app

RUN apt-get update && apt-get install -y build-essential && \
    apt-get clean

COPY . /app

RUN pip install -r pint disnake result python-dotenv rich

CMD ["python", "-m", "absolute_unit"]
