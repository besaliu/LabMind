FROM python:3.11-slim
WORKDIR /opt
COPY . /opt/vix
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/opt
WORKDIR /opt/vix
RUN pip install --no-cache-dir -r requirements.txt
CMD ["python", "temp_controller.py", "--port", "8101"]
