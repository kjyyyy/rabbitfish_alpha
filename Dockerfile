# Alpha Lab container.
#
# Two stages so the runtime image carries no compiler and no build caches.
# Everything is installed into a virtualenv in the builder and copied across,
# which keeps the final image ~400MB and makes the dependency layer cacheable
# independently of the source tree.
#
# Build:   docker build -t alphalab:0.15.0 .
# Run:     docker run --rm -v "$PWD/runs:/app/runs" -v "$PWD/data:/app/data" alphalab:0.15.0 journal
# Serve:   docker run --rm -p 8000:8000 alphalab:0.15.0 serve      (once the API lands - task 9)
#
# The base image is pinned to a patch version. For a reproducible build, pin by
# digest instead:  FROM python:3.11.9-slim-bookworm@sha256:<digest> AS builder
# (get it with: docker buildx imagetools inspect python:3.11.9-slim-bookworm)

# ---------------------------------------------------------------- builder ----
FROM python:3.11.9-slim-bookworm AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

# build-essential + cmake are needed to compile lightgbm/scipy wheels if a
# binary wheel is not available for the platform (notably linux/arm64).
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential cmake git \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build

# Dependency layer: copy only what the metadata needs, plus a stub package so
# `pip install -e .` resolves. Editing src/ does NOT invalidate this layer.
COPY pyproject.toml README.md ./
RUN mkdir -p src/alphalab && touch src/alphalab/__init__.py
# constraints.txt pins the full transitive tree (see `make lock`). Without it
# the build still works, it is just not bit-reproducible.
COPY constraints.tx[t] ./
RUN pip install -U pip setuptools wheel \
    && if [ -f constraints.txt ]; then \
         pip install -e ".[qlib,llm,postgres]" -c constraints.txt ; \
       else \
         pip install -e ".[qlib,llm,postgres]" ; \
       fi

# Source layer: cheap to rebuild.
COPY src/ ./src/
RUN pip install --no-deps -e .

# ---------------------------------------------------------------- runtime ----
FROM python:3.11.9-slim-bookworm AS runtime

LABEL org.opencontainers.image.title="alphalab" \
      org.opencontainers.image.description="LLM-assisted formulaic alpha research with deterministic gates" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.source="https://github.com/YOUR-USER/alpha-lab"

# libgomp1 is LightGBM's OpenMP runtime - the one non-obvious runtime dep.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 tini \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MPLBACKEND=Agg \
    ALPHALAB_CONFIG=configs/cn_csi300.yaml

# Non-root from here on. uid/gid are fixed so bind-mounted runs/ and data/
# keep predictable ownership on the host.
RUN groupadd -g 10001 alphalab && \
    useradd -u 10001 -g 10001 -m -s /usr/sbin/nologin alphalab

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --chown=alphalab:alphalab src/ ./src/
COPY --chown=alphalab:alphalab configs/ ./configs/
COPY --chown=alphalab:alphalab migrations/ ./migrations/
COPY --chown=alphalab:alphalab alembic.ini pyproject.toml README.md docker/entrypoint.sh ./
RUN chmod +x entrypoint.sh && install -d -o alphalab -g alphalab /app/runs /app/data

USER alphalab
VOLUME ["/app/runs", "/app/data"]
EXPOSE 8000

# Liveness for the API service. For CLI containers it is harmless: it fails
# until `serve` is running, which is why compose overrides it per service.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3).status==200 else 1)"

# tini reaps zombies so a long discovery run can be stopped cleanly.
ENTRYPOINT ["/usr/bin/tini", "--", "/app/entrypoint.sh"]
CMD ["--help"]
