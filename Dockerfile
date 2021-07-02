# buster produces 500MB image
# FROM python:3-buster
# alpine required a few tweaks but produces 50MB image
FROM python:3-alpine
LABEL org.opencontainers.image.source https://github.com/jamiew/validator-exporter
ENV PYTHONUNBUFFERED=1
EXPOSE 9825

#RUN apt update && apt install -y vim
COPY requirements.txt /opt/app/
RUN pip3 install -r /opt/app/requirements.txt

# copying the py later than the reqs so we don't need to rebuild as often
COPY *py /opt/app/
CMD /opt/app/validator-exporter.py
