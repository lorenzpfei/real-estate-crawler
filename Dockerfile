FROM python:3.12-alpine

WORKDIR /app

# Build-Dependencies für native Packages (h2/hpack)
RUN apk add --no-cache --virtual .build-deps gcc musl-dev \
    && pip install --no-cache-dir --upgrade pip

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && apk del .build-deps

COPY src/ src/

VOLUME ["/app/data"]

CMD ["python", "-m", "src.main"]
