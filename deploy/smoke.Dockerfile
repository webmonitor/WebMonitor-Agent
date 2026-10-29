# Trusted acceptance controller: the product image plus the Docker CLI.
# It mounts /var/run/docker.sock, which is equivalent to host administrator access.
FROM docker:28-cli AS dockercli

FROM backend

USER root
COPY --from=dockercli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=dockercli /usr/local/libexec/docker/cli-plugins/docker-compose \
    /usr/local/libexec/docker/cli-plugins/docker-compose
USER 10001:10001
ENTRYPOINT ["python"]
CMD ["scripts/smoke_mvp.py", "--base-url", "http://localhost:8080"]
