"""S3/Secrets Manager adapter for the existing PowerShell/psql pipeline.

Importing this module never creates AWS clients or connects to a database.
Only explicit invocation events can run the pipeline. Raw subprocess output,
connection credentials, HMAC keys, and source CSV rows are never logged.
"""

import json
import logging
import os
import re
import shutil
import signal
import subprocess
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo


LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)
PROJECT_ROOT = Path(os.environ.get("LAMBDA_TASK_ROOT", Path(__file__).resolve().parents[2]))
PIPELINE_NAME = "content_usage_daily"
CONNECTION_OPTIONS = "sslmode=verify-full connect_timeout=10"
MASTER_FILES = (
    "users.csv", "families.csv", "bundle_discount_compositions.csv", "plans.csv",
    "age_benefits.csv", "plan_age_benefits.csv", "additional_services.csv",
    "plan_benefits.csv", "discounts.csv", "internet_bundle_discount_rules.csv",
    "premium_family_discount_rules.csv", "user_discounts.csv", "user_services.csv",
)
ACTIONS = {"health", "check", "initialize", "incremental", "correction"}
PART_NAME = re.compile(r"part-[A-Za-z0-9_-]+\.csv\Z")
VERSION_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")


class PipelineError(RuntimeError):
    """An intentionally sanitized error safe to include in Lambda logs."""


def _today():
    return datetime.now(ZoneInfo("Asia/Seoul")).date()


def _parse_date(value, field):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise PipelineError(f"{field} must use YYYY-MM-DD.")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise PipelineError(f"{field} is not a valid calendar date.") from None


def _validate_event(event, today):
    if not isinstance(event, dict):
        raise PipelineError("The event must be a JSON object.")
    action = event.get("action")
    if not isinstance(action, str) or action not in ACTIONS:
        raise PipelineError("Use health, check, initialize, incremental, or correction; S3 events are not supported.")
    plan = {"action": action}
    if action in {"health", "check"}:
        return plan
    if action == "initialize":
        if event.get("confirm_initialize") is not True:
            raise PipelineError("initialize requires confirm_initialize=true and an empty pipeline database.")
        reference = _parse_date(event.get("reference_date", today.isoformat()), "reference_date")
        if reference > today:
            raise PipelineError("reference_date must not be in the future.")
        return {**plan, "reference_date": reference}
    if action == "incremental":
        first = _parse_date(event.get("from_date"), "from_date")
        last = _parse_date(event.get("to_date"), "to_date")
        if not 1 <= (last - first).days + 1 <= 7:
            raise PipelineError("incremental must contain 1 to 7 consecutive dates.")
        if last >= today:
            raise PipelineError("Only dates through yesterday in Asia/Seoul may be loaded.")
        return {**plan, "from_date": first, "to_date": last}
    correction = _parse_date(event.get("correction_date"), "correction_date")
    version = event.get("correction_version")
    if not isinstance(version, str) or not VERSION_NAME.fullmatch(version):
        raise PipelineError("correction_version must be a safe run_id name of 1 to 128 characters.")
    if correction >= today:
        raise PipelineError("A correction date must be on or before yesterday in Asia/Seoul.")
    return {**plan, "from_date": correction, "to_date": correction, "version": version}


def _text(value, label):
    if not isinstance(value, str) or not value.strip() or any(c in value for c in "\x00\r\n"):
        raise PipelineError(f"Missing or invalid {label}.")
    return value


def _prefix(value, label):
    value = _text(value, label).strip("/")
    if not value or "\\" in value or any(p in {"", ".", ".."} for p in value.split("/")):
        raise PipelineError(f"Invalid {label}.")
    return value


def _config():
    return {
        "bucket": _text(os.environ.get("S3_BUCKET"), "S3_BUCKET"),
        "master_prefix": _prefix(os.environ.get("MASTER_PREFIX", "kt-nd/master"), "MASTER_PREFIX"),
        "content_prefix": _prefix(os.environ.get("CONTENT_USAGE_PREFIX", "kt-nd/raw/content_usage"), "CONTENT_USAGE_PREFIX"),
        "rds_secret": _text(os.environ.get("RDS_SECRET_ID", "kt-nd/rds/admin"), "RDS_SECRET_ID"),
        "key_secret": _text(os.environ.get("PSEUDONYMIZATION_SECRET_ID", "kt-nd/pipeline/pseudonymization"), "PSEUDONYMIZATION_SECRET_ID"),
        "database": _text(os.environ.get("DATABASE_NAME"), "DATABASE_NAME"),
        "ca_path": _text(os.environ.get("RDS_CA_PATH", "/opt/certs/global-bundle.pem"), "RDS_CA_PATH"),
        "first_date": _parse_date(os.environ.get("CONTENT_USAGE_START_DATE", "2025-10-24"), "CONTENT_USAGE_START_DATE"),
    }


def _aws_client(service):
    # Lazy import keeps offline unit tests and the health event independent of AWS.
    import boto3
    from botocore.config import Config

    return boto3.client(service, config=Config(
        connect_timeout=5, read_timeout=30,
        retries={"mode": "standard", "total_max_attempts": 3},
    ))


def _secret_json(client, secret_id):
    response = client.get_secret_value(SecretId=secret_id)
    try:
        secret = json.loads(response["SecretString"])
    except (KeyError, TypeError, ValueError):
        raise PipelineError("A configured secret must contain a JSON SecretString.") from None
    if not isinstance(secret, dict):
        raise PipelineError("A configured secret must contain a JSON object.")
    return secret


def _database_environment(config, secrets_client, context):
    credentials = _secret_json(secrets_client, config["rds_secret"])
    key_secret = _secret_json(secrets_client, config["key_secret"])
    key = _text(key_secret.get("pseudonymization_key"), "pseudonymization_key secret field")
    if len(key) < 32 or key == "kt-nd-synthetic-analysis-v1":
        raise PipelineError("Use a stable non-default pseudonymization key of at least 32 characters.")
    port = str(credentials.get("port", 5432))
    if not port.isdecimal() or not 1 <= int(port) <= 65535:
        raise PipelineError("The RDS secret has an invalid port.")
    env = os.environ.copy()
    env.update({
        "PGHOST": _text(credentials.get("host"), "RDS secret host"),
        "PGPORT": port,
        "PGUSER": _text(credentials.get("username"), "RDS secret username"),
        "PGPASSWORD": _text(credentials.get("password"), "RDS secret password"),
        "PGDATABASE": config["database"],
        "PGSSLMODE": "verify-full",
        "PGSSLROOTCERT": config["ca_path"],
        "PGAPPNAME": "kt-nd-lambda",
        "PGOPTIONS": f"-c lock_timeout=30000 -c statement_timeout={_budget(context) * 1000}",
        "KT_ND_ANALYSIS_PSEUDONYMIZATION_KEY": key,
        "TMPDIR": "/tmp",
    })
    return env


def _budget(context, limit=880):
    seconds = context.get_remaining_time_in_millis() // 1000 - 20 if context else limit
    if seconds < 10:
        raise PipelineError("Insufficient invocation time remains to start another operation.")
    return min(seconds, limit)


def _stop_process(process):
    # Terminate pwsh and its psql child so a timeout does not leave an orphaned batch.
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
        process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
        process.communicate()
    except ProcessLookupError:
        process.communicate()


def _database_diagnostic(returncode, stderr):
    """Return a fixed hint only; never return any substring of private stderr."""
    # psql: 2 means a lost/failed connection, 3 means an ON_ERROR_STOP SQL error.
    # Do not classify SQL messages (which can contain source data) as connection errors.
    if returncode != 2:
        return "DB_QUERY_FAILED" if returncode == 3 else "DB_CLIENT_FAILED"
    rules = (
        ("DB_PASSWORD_MISSING", r"no password supplied"),
        ("DB_AUTH_FAILED", r"password authentication failed|authentication failed for user"),
        ("DB_ROLE_NOT_FOUND", r'role "[^"\n]*" does not exist'),
        ("DB_DATABASE_NOT_FOUND", r'database "[^"\n]*" does not exist'),
        ("DB_ACCESS_DENIED", r"no pg_hba\.conf entry|pg_hba\.conf rejects connection|permission denied for database"),
        ("DB_DNS_FAILED", r"could not translate host name|could not resolve host name"),
        ("DB_TLS_CA_FILE_ERROR", r"root certificate file .*does not exist|could not (?:read|load|open) root certificate file"),
        ("DB_TLS_HOSTNAME_MISMATCH", r"server certificate .*does not match host name"),
        ("DB_TLS_VERIFY_FAILED", r"certificate verify failed|certificate verification failed"),
        ("DB_CONNECTION_REFUSED", r"connection refused"),
        ("DB_CONNECT_TIMEOUT", r"timeout expired|connection timed out"),
        ("DB_NETWORK_UNREACHABLE", r"network is unreachable|no route to host"),
        ("DB_CONNECTION_CLOSED", r"server closed the connection unexpectedly|connection reset by peer"),
        ("DB_TLS_FAILED", r"ssl error:|ssl syscall error:|server does not support ssl|could not establish ssl connection"),
    )
    for code, pattern in rules:
        if re.search(pattern, stderr or "", re.IGNORECASE):
            return code
    return "DB_CONNECTION_FAILED_UNKNOWN"


def _command(arguments, env, context, label, input_text=None, limit=880, diagnose_database=False):
    timeout = _budget(context, limit)
    process = subprocess.Popen(
        arguments, env=env, cwd=PROJECT_ROOT,
        stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace",
        start_new_session=os.name == "posix",
    )
    try:
        stdout, stderr = process.communicate(input=input_text, timeout=timeout)
    except subprocess.TimeoutExpired:
        _stop_process(process)
        diagnostic = " diagnostic=DB_COMMAND_TIMEOUT;" if diagnose_database else ""
        raise PipelineError(f"{label} timed out;{diagnostic} the subprocess group was terminated.") from None
    if process.returncode:
        # Do not include stdout, stderr, arguments, or environment in exceptions.
        diagnostic = f" diagnostic={_database_diagnostic(process.returncode, stderr)};" if diagnose_database else ""
        raise PipelineError(f"{label} failed with exit code {process.returncode};{diagnostic} raw output is withheld to protect credentials and source data.")
    return stdout.strip()


def _query(sql, env, context):
    read_env = env.copy()
    # Stable English client messages allow fixed-code diagnostics without raw logs.
    read_env["LC_ALL"] = "C"
    read_env["PGOPTIONS"] = "-c default_transaction_read_only=on -c statement_timeout=30000 -c lock_timeout=10000"
    return _command(
        ["psql", "-X", "-A", "-t", "--no-password", "-v", "ON_ERROR_STOP=1", "-d", CONNECTION_OPTIONS],
        read_env, context, "Database verification", input_text=sql + "\n", limit=40, diagnose_database=True,
    )


def _has_pipeline_data(env, context):
    # Catalog-generated identifiers avoid referencing tables that do not yet exist.
    # \gexec runs SELECT EXISTS only; no DDL or DML is performed here.
    result = _query(r"""
select format('select exists(select 1 from %I.%I limit 1);', n.nspname, c.relname)
from pg_class c join pg_namespace n on n.oid=c.relnamespace
where n.nspname in ('dw_operations','dw_personalization','dm_operations','dm_personalization')
  and c.relkind in ('r','p')
order by n.nspname,c.relname
\gexec
""", env, context)
    return "t" in result.splitlines()


def _watermark(env, context, require_initialized=True):
    exists = _query("select to_regclass('audit.ingestion_watermark') is not null;", env, context)
    if exists != "t":
        if require_initialized:
            raise PipelineError("Run initialize on an empty pipeline database first.")
        return None
    value = _query(
        "select to_char(last_successful_event_date,'YYYY-MM-DD') from audit.ingestion_watermark where pipeline_name='content_usage_daily';",
        env, context,
    )
    return _parse_date(value, "database watermark") if value else None


def _check_range(plan, watermark, first_date):
    if plan["from_date"] < first_date:
        raise PipelineError("The requested range precedes CONTENT_USAGE_START_DATE.")
    if plan["action"] == "correction":
        if watermark is None or plan["to_date"] > watermark:
            raise PipelineError("correction must target an already successfully loaded date.")
        return True
    if watermark is not None and plan["to_date"] <= watermark:
        return False  # Already covered; changed historical CSVs need a correction event.
    expected = watermark + timedelta(days=1) if watermark else first_date
    if plan["from_date"] != expected:
        raise PipelineError(f"The next incremental from_date must be {expected.isoformat()}.")
    return True


def _master_objects(s3, config):
    objects = []
    for name in MASTER_FILES:
        key = config["master_prefix"] + "/" + name
        metadata = s3.head_object(Bucket=config["bucket"], Key=key)
        objects.append({"key": key, "path": name, "size": metadata["ContentLength"]})
    return objects


def _partition_objects(s3, config, plan):
    objects = []
    current = plan["from_date"]
    while current <= plan["to_date"]:
        folder = "event_date=" + current.isoformat()
        if plan["action"] == "correction":
            folder += "/run_id=" + plan["version"]
        prefix = config["content_prefix"] + "/" + folder + "/"
        count = 0
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=config["bucket"], Prefix=prefix):
            for item in page.get("Contents", []):
                name = item["Key"][len(prefix):]
                if not PART_NAME.fullmatch(name):
                    continue  # No nested versions, arbitrary paths, or non-CSV objects.
                count += 1
                if count > 1000:
                    raise PipelineError("A partition contains more than 1000 part CSVs.")
                objects.append({"key": item["Key"], "path": folder + "/" + name, "size": item["Size"]})
        if count == 0:
            raise PipelineError(f"No direct part CSVs exist for requested date {current.isoformat()} and version.")
        current += timedelta(days=1)
    return sorted(objects, key=lambda item: item["path"])


def _download(s3, config, objects, directory, context):
    size = sum(item["size"] for item in objects)
    if any(item["size"] <= 0 for item in objects):
        raise PipelineError("An input CSV object is empty.")
    # Allow raw downloads, PowerShell's combined CSV, and scratch space.
    if size * 3 + 64 * 1024 * 1024 > shutil.disk_usage(directory).free:
        raise PipelineError("Insufficient /tmp storage; reduce the date range or increase ephemeral storage.")
    for item in objects:
        _budget(context)
        target = directory / item["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        s3.download_file(config["bucket"], item["key"], str(target))
        if target.stat().st_size != item["size"]:
            raise PipelineError("An input object changed size while downloading; retry with stable S3 inputs.")


def _pipeline(plan, directory, env, context):
    arguments = ["pwsh", "-NoLogo", "-NoProfile", "-NonInteractive", "-File"]
    scripts = PROJECT_ROOT / "pipeline" / "scripts"
    if plan["action"] == "initialize":
        arguments += [str(scripts / "initialize_incremental_pipeline.ps1"),
                      "-ConnectionString", CONNECTION_OPTIONS, "-RawDirectory", str(directory),
                      "-ReferenceDate", plan["reference_date"].isoformat()]
    else:
        processing_date = plan["to_date"] + timedelta(days=1) if plan["action"] == "incremental" else _today()
        arguments += [str(scripts / "run_incremental_pipeline.ps1"),
                      "-ConnectionString", CONNECTION_OPTIONS, "-ContentRoot", str(directory),
                      "-ProcessingDate", processing_date.isoformat(), "-MaxDatesPerBatch", "7"]
        if plan["action"] == "correction":
            arguments += ["-CorrectionDate", plan["from_date"].isoformat(), "-CorrectionVersion", plan["version"]]
    # Credentials and the HMAC key travel only in the child's environment.
    _command(arguments, env, context, "PowerShell pipeline")


def _verify_run(plan, env, context):
    run_type = {"initialize": "DATASET_INITIALIZATION", "incremental": "INCREMENTAL", "correction": "CORRECTION"}[plan["action"]]
    dates = ""
    if plan["action"] != "initialize":
        dates = f" and event_date_from='{plan['from_date'].isoformat()}'::date and event_date_to='{plan['to_date'].isoformat()}'::date"
    batch = _query(
        f"select batch_id::text from audit.pipeline_run where pipeline_name='content_usage_daily' and run_type='{run_type}' and status='SUCCEEDED'{dates} order by started_at desc limit 1;",
        env, context,
    )
    try:
        batch = str(UUID(batch))
    except ValueError:
        raise PipelineError("No matching SUCCEEDED audit batch was found after pipeline execution.") from None
    quality = _query(
        f"select exists(select 1 from audit.data_quality_result where batch_id='{batch}'::uuid) and not exists(select 1 from audit.data_quality_result where batch_id='{batch}'::uuid and failed_row_count>0);",
        env, context,
    )
    if quality != "t":
        raise PipelineError("Audit quality verification did not pass.")
    if plan["action"] == "incremental" and _watermark(env, context) != plan["to_date"]:
        raise PipelineError("The database watermark did not reach the requested to_date.")
    return batch


def _health(context):
    for filename in ("initialize_incremental_pipeline.ps1", "run_incremental_pipeline.ps1"):
        if not (PROJECT_ROOT / "pipeline" / "scripts" / filename).is_file():
            raise PipelineError("A required PowerShell script is missing from the image.")
    if not Path(os.environ.get("RDS_CA_PATH", "/opt/certs/global-bundle.pem")).is_file():
        raise PipelineError("The RDS public CA bundle is missing from the image.")
    env = os.environ.copy()
    psql = _command(["psql", "--version"], env, context, "psql health check", limit=30)
    if not re.search(r"\b18\.", psql):
        raise PipelineError("The image must provide a PostgreSQL 18 psql client.")
    powershell = _command(
        ["pwsh", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command",
         r'$ErrorActionPreference="Stop"; [System.TimeZoneInfo]::FindSystemTimeZoneById("Asia/Seoul") | Out-Null; '
         r'$scriptRoot=Join-Path (Get-Location) "pipeline/scripts"; '
         r'foreach ($relative in @("..\sql\015_initialize_incremental_pipeline.psql","..\sql\020_run_incremental_pipeline.psql")) { '
         r'$entry=[IO.Path]::GetFullPath((Join-Path $scriptRoot $relative)); '
         r'if (-not (Test-Path -LiteralPath $entry -PathType Leaf)) { throw "SQL entrypoint path resolution failed" } }; '
         r'$PSVersionTable.PSVersion.ToString()'],
        env, context, "PowerShell health check", limit=30,
    )
    return {"status": "SUCCEEDED", "action": "health", "psql": psql,
            "powershell": powershell, "database_accessed": False, "aws_apis_accessed": False}


def lambda_handler(event, context):
    stage = "validate_event"
    action = "unknown"
    try:
        # health works without configuration, time zone data, or AWS credentials.
        if isinstance(event, dict) and event.get("action") == "health":
            action = "health"
            return _health(context)
        plan = _validate_event(event, _today())
        action = plan["action"]
        stage = "load_configuration"
        config = _config()
        if not Path(config["ca_path"]).is_file():
            raise PipelineError("The RDS public CA bundle is missing from the image.")
        stage = "retrieve_secrets"
        env = _database_environment(config, _aws_client("secretsmanager"), context)
        s3 = _aws_client("s3")
        stage = "database_preflight"
        if action == "check":
            connected = _query("select 1;", env, context) == "1"
            if not connected:
                raise PipelineError("The RDS connection check did not pass.")
            watermark = _watermark(env, context, require_initialized=False)
            stage = "s3_preflight"
            objects = _master_objects(s3, config)
            return {"status": "SUCCEEDED", "action": action, "database_connected": True,
                    "master_files_found": len(objects), "watermark": watermark.isoformat() if watermark else None,
                    "database_modified": False}
        if action == "initialize":
            if _has_pipeline_data(env, context):
                raise PipelineError("initialize is blocked because pipeline tables contain data; do not use it for master updates or schema migrations.")
        else:
            watermark = _watermark(env, context)
            if not _check_range(plan, watermark, config["first_date"]):
                return {"status": "ALREADY_PROCESSED", "action": action,
                        "watermark": watermark.isoformat(), "database_modified": False}
        stage = "list_source_objects"
        objects = _master_objects(s3, config) if action == "initialize" else _partition_objects(s3, config, plan)
        with tempfile.TemporaryDirectory(prefix="kt-nd-lambda-", dir="/tmp") as temporary:
            directory = Path(temporary)
            stage = "download_source_objects"
            _download(s3, config, objects, directory, context)
            LOGGER.info(json.dumps({"stage": "pipeline_start", "action": action, "input_files": len(objects)}))
            stage = "run_pipeline"
            _pipeline(plan, directory, env, context)
            stage = "verify_audit"
            batch = _verify_run(plan, env, context)
        result = {"status": "SUCCEEDED", "action": action, "batch_id": batch, "input_files": len(objects)}
        if action != "initialize":
            result.update(from_date=plan["from_date"].isoformat(), to_date=plan["to_date"].isoformat())
        LOGGER.info(json.dumps(result))
        return result
    except PipelineError:
        LOGGER.error(json.dumps({"status": "FAILED", "action": action, "stage": stage}))
        raise
    except Exception as error:
        LOGGER.error(json.dumps({"status": "FAILED", "action": action, "stage": stage, "error_type": type(error).__name__}))
        raise PipelineError(f"Failed at {stage} ({type(error).__name__}); raw exception details are withheld to protect secrets and data.") from None
