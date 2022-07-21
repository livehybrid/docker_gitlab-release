FROM amd64/alpine:3.9.4
LABEL maintainer="Will Searle <will@livehybrid.com>"
ENV GITCHK_VERSION=0.8.0
RUN apk add --no-cache curl git python3
RUN python3 -m pip install pyyaml requests
RUN wget https://github.com/git-chglog/git-chglog/releases/download/${GITCHK_VERSION}/git-chglog_linux_amd64 -O /usr/local/bin/git-chglog && chmod +x /usr/local/bin/git-chglog

COPY opt /opt
WORKDIR /src
ENTRYPOINT ["python3", "/opt/gitlab-api/main.py"]

