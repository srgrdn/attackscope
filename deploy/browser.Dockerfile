FROM mcr.microsoft.com/playwright/python:v1.64.1-noble@sha256:330d401ae23c905896a0c26c66c36fc971b621519e7b11b435a8328d7bf6e031
COPY tests/requirements-browser.lock /tmp/requirements-browser.lock
RUN pip install --no-cache-dir --require-hashes -r /tmp/requirements-browser.lock
WORKDIR /tests
USER pwuser
ENTRYPOINT ["python"]
