FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV MUJOCO_STUDIO_HOST=0.0.0.0 MUJOCO_STUDIO_DATA=/data MUJOCO_STUDIO_NO_BROWSER=1 MUJOCO_STUDIO_SINGLE_USER=0 MUJOCO_STUDIO_DESKTOP=0
# The effective port comes from ports.json / docker_ports.py at runtime.
VOLUME ["/data"]
CMD ["python", "run.py"]
