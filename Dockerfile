# syntax=docker/dockerfile:1
# Build from git root with following command:
# docker build -t cmless:latest .
FROM python:3.12-rc-bullseye

# root installs

RUN addgroup --system app && adduser --system --group app
USER app
WORKDIR /app
# Mark /app github safe, important to build python package with git
# tracked files 
RUN git config --global --add safe.directory /app

# Dev tools
RUN pip install build twine ipython

# CSI code
ENV TZ="Europe/Brussels"
ENV PATH=/home/app/.local/bin/:$PATH
ENV FLASK_APP=tests:create_app
ENV FLASK_RUN_HOST=0.0.0.0

COPY --chown=app:app . .
RUN pip install .[fullstack,dev]

EXPOSE 5000
CMD ["flask", "run"]
