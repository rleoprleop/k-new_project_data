# Build from the repository root with --platform linux/amd64 --provenance=false.
FROM public.ecr.aws/lambda/python:3.12

ARG POWERSHELL_VERSION=7.6.6
ARG POWERSHELL_SHA256=ddbc4a2d113bbd46d283cfedcbcd117a70caefd7673f41f2b4e0000badf103bc
ARG AMAZON_LINUX_RELEASE=2023.12.20260831

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Lambda only permits application writes under /tmp.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POWERSHELL_TELEMETRY_OPTOUT=1 \
    POWERSHELL_UPDATECHECK=Off \
    XDG_CACHE_HOME=/tmp/kt-nd/cache \
    XDG_CONFIG_HOME=/tmp/kt-nd/config \
    XDG_DATA_HOME=/tmp/kt-nd/data \
    PSModuleAnalysisCachePath=/tmp/powershell-module-analysis-cache \
    RDS_CA_PATH=/opt/certs/global-bundle.pem

# Install the psql client, archive tools, time zones, and PowerShell dependencies.
# The PowerShell archive below is for x86_64, not arm64.
RUN test "$(uname -m)" = "x86_64" \
    && dnf --releasever=${AMAZON_LINUX_RELEASE} install -y \
        ca-certificates \
        glibc \
        gzip \
        krb5-libs \
        libgcc \
        libicu \
        libstdc++ \
        postgresql18 \
        tar \
        tzdata \
        zlib \
    && dnf clean all

# Use Microsoft's self-contained archive; no separate .NET SDK is needed.
RUN mkdir -p /opt/microsoft/powershell/7 \
    && curl --fail --show-error --silent --location --retry 3 \
        "https://github.com/PowerShell/PowerShell/releases/download/v${POWERSHELL_VERSION}/powershell-${POWERSHELL_VERSION}-linux-x64.tar.gz" \
        --output /tmp/powershell.tar.gz \
    && printf '%s  %s\n' "${POWERSHELL_SHA256}" /tmp/powershell.tar.gz \
        | sha256sum --check - \
    && tar --extract --gzip --file /tmp/powershell.tar.gz \
        --directory /opt/microsoft/powershell/7 \
    && chmod -R a+rX /opt/microsoft/powershell/7 \
    && chmod a+x /opt/microsoft/powershell/7/pwsh \
    && ln -s /opt/microsoft/powershell/7/pwsh /usr/local/bin/pwsh \
    && rm -f /tmp/powershell.tar.gz

# This is AWS's public CA bundle, not a private key or database credential.
RUN mkdir -p /opt/certs \
    && curl --fail --show-error --silent --location --retry 3 \
        https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem \
        --output /opt/certs/global-bundle.pem \
    && test -s /opt/certs/global-bundle.pem \
    && chmod a+r /opt/certs/global-bundle.pem

# Check dependencies without contacting AWS APIs or a database.
# Boto3 is provided by the AWS Lambda Python base image; no AWS CLI is required.
RUN psql --version \
    && pwsh -NoLogo -NoProfile -NonInteractive -Command \
        '$ErrorActionPreference = "Stop"; $PSVersionTable.PSVersion.ToString(); [System.TimeZoneInfo]::FindSystemTimeZoneById("Asia/Seoul").Id' \
    && python -c "import boto3; print('AWS SDK import OK')"

WORKDIR ${LAMBDA_TASK_ROOT}

# Preserve relative paths used by the existing PowerShell scripts and psql \ir.
# Never COPY the complete repository or generator data into this image.
COPY db/ ${LAMBDA_TASK_ROOT}/db/
COPY pipeline/ ${LAMBDA_TASK_ROOT}/pipeline/
COPY deploy/lambda/handler.py ${LAMBDA_TASK_ROOT}/handler.py

RUN chmod -R a+rX db pipeline handler.py \
    && test -f pipeline/scripts/initialize_incremental_pipeline.ps1 \
    && test -f pipeline/scripts/run_incremental_pipeline.ps1 \
    && python -c "import ast, pathlib; ast.parse(pathlib.Path('handler.py').read_text(encoding='utf-8'))"

# Lambda calls lambda_handler in the deployed handler.py module.
CMD ["handler.lambda_handler"]
