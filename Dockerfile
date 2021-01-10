FROM python:3

WORKDIR /root
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

WORKDIR /usr/src/app
COPY src/ ./

CMD ["flask", "run", "--host=0.0.0.0", "--port=80"]