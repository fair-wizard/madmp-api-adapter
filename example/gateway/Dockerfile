# Option B: the adapter mounted in an engine-gateway image, next to other
# gateway apps.
FROM datastewardshipwizard/engine-gateway:1.0.1

RUN apk add --no-cache git

COPY requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

COPY config.yaml /app/config.yaml
COPY madmp /app/madmp
ENV MADMP_API_CONFIG_PATH=/app/madmp/config.yaml

CMD ["uvicorn", "engine_gateway:create_app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers"]
