FROM modelscope-registry.cn-beijing.cr.aliyuncs.com/modelscope-repo/python:3.10

WORKDIR /home/user/app

RUN mkdir -p data storage logs

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=7860 \
    PYTHONUNBUFFERED=1 \
    PUBLIC_BASE_URL=https://gxchang-ai-workstation.ms.show
EXPOSE 7860

CMD ["python", "server.py"]
