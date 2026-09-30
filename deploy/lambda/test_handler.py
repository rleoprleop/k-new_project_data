"""Offline tests only: no AWS credentials, network calls, psql, or SQL execution."""

import ast
import logging
import re
import subprocess
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import handler


TODAY = date(2026, 9, 30)
FIRST = date(2025, 10, 24)
MOCK_PASSWORD = "mock-password-for-unit-tests-not-a-real-secret"
MOCK_KEY = "mock-pseudonymization-key-for-unit-tests-only"


def setUpModule():
    # Several tests intentionally provoke FAILED events; keep the test report clear.
    handler.LOGGER.disabled = True


def tearDownModule():
    handler.LOGGER.disabled = False


def incremental(first="2025-10-24", last="2025-10-24"):
    return handler._validate_event({"action": "incremental", "from_date": first, "to_date": last}, TODAY)


class CsvPathTests(unittest.TestCase):
    """Offline regression checks for the SQL/PowerShell CSV path contract."""

    root = Path(__file__).resolve().parents[2]

    def loader(self, name):
        return (self.root / "db" / "load" / name).read_text(encoding="utf-8")

    def copy_filenames(self, text):
        lines = [line for line in text.splitlines() if line.startswith(r"\copy ")]
        filenames = []
        for line in lines:
            match = re.search(r" from '([a-z_]+\.csv)' with ", line)
            self.assertIsNotNone(match, "COPY must use a fixed client-side CSV filename")
            self.assertNotIn("from :", line)
            self.assertIn("format csv,header true,encoding 'UTF8'", line)
            filenames.append(match.group(1))
        return filenames

    def test_master_copy_uses_the_13_expected_fixed_filenames(self):
        text = self.loader("005_load_master_staging.psql")
        self.assertEqual(tuple(self.copy_filenames(text)), handler.MASTER_FILES)
        self.assertLess(text.index(r"\cd :input_csv_directory"), text.index("\n\\copy "))

    def test_incremental_copy_reads_manifest_and_combined_csv(self):
        text = self.loader("020_load_incremental_content_usage.psql")
        self.assertEqual(self.copy_filenames(text), ["source_manifest.csv", "content_usage.csv"])
        self.assertLess(text.index(r"\cd :input_csv_directory"), text.index("\n\\copy "))

    def test_full_load_inherits_the_master_input_directory(self):
        text = self.loader("010_load_full_staging.psql")
        self.assertEqual(self.copy_filenames(text), ["content_usage.csv"])
        self.assertLess(text.index(r"\ir 005_load_master_staging.psql"), text.index("\n\\copy "))

    def test_runners_pass_the_matching_absolute_csv_directory(self):
        scripts = self.root / "pipeline" / "scripts"
        for name in ("initialize_incremental_pipeline.ps1", "run_pipeline.ps1"):
            with self.subTest(script=name):
                text = (scripts / name).read_text(encoding="utf-8")
                self.assertIn('$RawDirectory = [IO.Path]::GetFullPath($RawDirectory)', text)
                self.assertIn("'-v', \"input_csv_directory=$RawDirectory\"", text)
                self.assertIn('"${name}_csv=$($fileState[$name].Path)"', text)
        text = (scripts / "run_incremental_pipeline.ps1").read_text(encoding="utf-8")
        self.assertIn("'-v', \"input_csv_directory=$temporaryRoot\"", text)
        self.assertIn("Join-Path $TemporaryRoot 'content_usage.csv'", text)
        self.assertIn("Join-Path $TemporaryRoot 'source_manifest.csv'", text)
        self.assertIn('"content_usage_csv=$($input.CombinedPath)"', text)
        self.assertIn('"source_manifest_csv=$($input.ManifestPath)"', text)

    def test_audit_keeps_original_absolute_source_path_variables(self):
        master = self.loader("005_load_master_staging.psql")
        for filename in handler.MASTER_FILES:
            stem = Path(filename).stem
            with self.subTest(source=stem):
                self.assertIn(":'" + stem + "_csv'", master)
                self.assertIn(":'" + stem + "_sha256'", master)
        self.assertIn(":'content_usage_csv'", self.loader("010_load_full_staging.psql"))
        self.assertIn("'content_usage',source_path,event_date,object_version,sha256,row_count",
                      self.loader("020_load_incremental_content_usage.psql"))

    def test_sql_includes_remain_relative_to_the_sql_file_not_csv_directory(self):
        files = list((self.root / "db" / "load").glob("*.psql"))
        files += list((self.root / "pipeline" / "sql").glob("*.psql"))
        for path in files:
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.startswith(r"\ir "):
                    with self.subTest(sql=path.name, include=line):
                        self.assertTrue((path.parent / line[4:].strip()).resolve().is_file())


class AgeBenefitSchemaTests(unittest.TestCase):
    """Offline schema/quality contracts; these do not execute PostgreSQL."""

    root = Path(__file__).resolve().parents[2]
    migration = "070_allow_open_ended_age_benefits.sql"

    def sql(self, path):
        return (self.root / path).read_text(encoding="utf-8")

    def test_staging_allows_null_upper_bound_but_requires_lower_bound(self):
        text = self.sql("db/load/001_create_staging.sql")
        table = re.search(r"create temp table stg_age_benefits \((.*?)\) on commit drop;",
                          text, re.DOTALL).group(1)
        self.assertRegex(table, r"min_age numeric\(5,1\) not null")
        self.assertRegex(table, r"max_age numeric\(5,1\),")

    def test_migration_only_relaxes_both_dw_upper_bounds_atomically(self):
        text = self.sql("db/schema/" + self.migration)
        statements = re.sub(r"--[^\n]*", "", text).split(";")
        statements = [" ".join(statement.split()) for statement in statements if statement.strip()]
        self.assertEqual(statements, [
            "begin",
            "alter table dw_operations.age_benefits alter column max_age drop not null",
            "alter table dw_personalization.age_benefits alter column max_age drop not null",
            "commit",
        ])

    def test_every_entrypoint_applies_migration_before_loading(self):
        for name in ("010_run_pipeline.psql", "015_initialize_incremental_pipeline.psql",
                     "020_run_incremental_pipeline.psql"):
            with self.subTest(entrypoint=name):
                text = self.sql("pipeline/sql/" + name)
                include = r"\ir ../../db/schema/" + self.migration
                self.assertEqual(text.count(include), 1)
                self.assertLess(text.index(r"\ir ../../db/schema/060_ai_views_roles.sql"),
                                text.index(include))
                self.assertLess(text.index(include), text.index("select pg_advisory_lock("))
                self.assertLess(text.index(include), text.index("select audit.start_pipeline_run("))

    def test_quality_accepts_absent_upper_bound_and_checks_null_preservation(self):
        staging = self.sql("db/quality/010_staging_full.sql")
        self.assertIn("'staging_age_benefit_range'", staging)
        self.assertIn("where max_age is not null and max_age<min_age", staging)
        for domain in ("operations", "personalization"):
            with self.subTest(domain=domain):
                text = self.sql(f"db/quality/{domain}/dw/010_quality.sql")
                self.assertIn(f"'{domain}_dw_age_benefit_bounds_preserved'", text)
                self.assertIn(f"from dw_{domain}.age_benefits d", text)
                self.assertIn("full join stg_age_benefits s using(age_benefit_id)", text)
                self.assertIn("d.age_benefit_id is null or s.age_benefit_id is null", text)
                self.assertIn("d.min_age is distinct from s.min_age", text)
                self.assertIn("d.max_age is distinct from s.max_age", text)

    def test_generator_keeps_open_ended_senior_benefit(self):
        # Inspect literal master definitions without importing/running the generator.
        tree = ast.parse(self.sql("generator/src/kt_synthetic_data_generator.py"))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                        and node.name == "create_age_benefit_master")
        rows = next(ast.literal_eval(node.value) for node in function.body
                    if isinstance(node, ast.Assign)
                    and any(isinstance(target, ast.Name) and target.id == "rows"
                            for target in node.targets))
        senior = next(row for row in rows if row[0] == "AB40")
        self.assertEqual(senior[2], 75)
        self.assertIsNone(senior[3])


class PremiumFamilyAgeTests(unittest.TestCase):
    """Offline checks for decimal integer notation at the CSV/staging boundary."""

    root = Path(__file__).resolve().parents[2]
    age_columns = ("enrollment_min_age", "enrollment_max_age", "benefit_end_age")
    columns = (
        "source_batch_id", "premium_family_rule_id", "discount_id", "benefit_type",
        "eligible_component_role", "requires_internet", "minimum_high_line_count",
        "maximum_mobile_line_count", "minimum_plan_fee", "required_network_type",
        "guardian_minimum_plan_fee", "guardian_required_network_type",
        "enrollment_min_age", "enrollment_max_age", "benefit_end_age",
        "requires_legal_guardian", "discount_rate", "discount_amount",
        "effective_start_date", "effective_end_date",
    )

    def sql(self, path):
        return (self.root / path).read_text(encoding="utf-8")

    def test_only_staging_age_columns_accept_unrounded_numeric_values(self):
        text = self.sql("db/load/001_create_staging.sql")
        table = re.search(r"create temp table stg_premium_family_discount_rules \((.*?)\) on commit drop;",
                          text, re.DOTALL).group(1)
        for column in self.age_columns:
            with self.subTest(column=column):
                self.assertRegex(table, rf"\b{column} numeric,")
        for column in ("minimum_high_line_count", "maximum_mobile_line_count"):
            self.assertRegex(table, rf"\b{column} integer,")
        for name in ("020_dw_operations.sql", "030_dw_personalization.sql"):
            text = self.sql("db/schema/" + name)
            for column in self.age_columns:
                with self.subTest(schema=name, column=column):
                    self.assertRegex(text, rf"\b{column} integer,")

    def test_quality_checks_all_three_ages_before_any_integer_cast(self):
        text = self.sql("db/quality/010_staging_full.sql")
        rule = re.search(r"'staging_premium_family_age_integer',\$\$(.*?)\$\$",
                         text, re.DOTALL).group(1)
        self.assertIn("from stg_premium_family_discount_rules r", rule)
        for column in self.age_columns:
            self.assertIn(f"(r.{column})", rule)
        self.assertIn("where age_value is not null", rule)
        self.assertIn("age_value not between -2147483648 and 2147483647", rule)
        self.assertIn("age_value<>trunc(age_value)", rule)
        self.assertNotIn("::integer", rule)

    def test_both_dw_inserts_cast_only_validated_ages_and_keep_other_fields(self):
        text = self.sql("db/transform/common/010_load_master.sql")
        for domain in ("operations", "personalization"):
            with self.subTest(domain=domain):
                statement = re.search(
                    rf"insert into dw_{domain}\.premium_family_discount_rules \((.*?)\)\s*"
                    r"select (.*?) from stg_premium_family_discount_rules r;",
                    text, re.DOTALL,
                )
                self.assertIsNotNone(statement)
                targets = tuple(column.strip() for column in statement.group(1).split(","))
                expressions = tuple(expression.strip() for expression in statement.group(2).split(","))
                self.assertEqual(targets, self.columns)
                expected = (":'batch_id'::uuid",) + tuple(
                    "r." + column + ("::integer" if column in self.age_columns else "")
                    for column in self.columns[1:]
                )
                self.assertEqual(expressions, expected)

    def test_master_entrypoints_check_staging_before_dw_conversion(self):
        for name in ("010_run_pipeline.psql", "015_initialize_incremental_pipeline.psql"):
            with self.subTest(entrypoint=name):
                text = self.sql("pipeline/sql/" + name)
                self.assertLess(text.index(r"\ir ../../db/quality/010_staging_full.sql"),
                                text.index(r"\ir ../../db/transform/common/010_load_master.sql"))


class EventTests(unittest.TestCase):
    def test_initialization_requires_explicit_boolean_confirmation(self):
        for confirmation in (None, False, "true", 1):
            with self.subTest(confirmation=confirmation), self.assertRaises(handler.PipelineError):
                handler._validate_event({"action": "initialize", "confirm_initialize": confirmation}, TODAY)
        result = handler._validate_event({"action": "initialize", "confirm_initialize": True}, TODAY)
        self.assertEqual(result["reference_date"], TODAY)

    def test_maximum_seven_days(self):
        self.assertEqual(incremental(last="2025-10-30")["to_date"], date(2025, 10, 30))
        for first, last in (("2025-10-24", "2025-10-31"), ("2025-10-25", "2025-10-24")):
            with self.subTest(first=first, last=last), self.assertRaises(handler.PipelineError):
                incremental(first, last)

    def test_today_and_future_dates_are_blocked(self):
        for day in ("2026-09-30", "2026-10-01"):
            with self.subTest(day=day), self.assertRaises(handler.PipelineError):
                incremental(day, day)
        incremental("2026-09-29", "2026-09-29")

    def test_invalid_dates_and_sql_injection_are_blocked(self):
        for day in ("2026-02-30", "2026-9-29", "2026-09-29';drop table x;--", None):
            with self.subTest(day=day), self.assertRaises(handler.PipelineError):
                incremental(day, day)

    def test_unsupported_and_s3_events_are_blocked(self):
        for event in ({"Records": []}, {"action": "migrate"}, {"action": "full_snapshot"}, [], None):
            with self.subTest(event=event), self.assertRaises(handler.PipelineError):
                handler._validate_event(event, TODAY)

    def test_correction_version_cannot_escape_partition(self):
        event = {"action": "correction", "correction_date": "2025-10-24"}
        for version in ("../escape", "..", "/absolute", "a/b", "a\\b", "", None):
            with self.subTest(version=version), self.assertRaises(handler.PipelineError):
                handler._validate_event({**event, "correction_version": version}, TODAY)
        self.assertEqual(handler._validate_event({**event, "correction_version": "fix-001"}, TODAY)["version"], "fix-001")

    def test_watermark_and_first_source_date_are_enforced(self):
        self.assertTrue(handler._check_range(incremental(), None, FIRST))
        with self.assertRaises(handler.PipelineError):
            handler._check_range(incremental("2025-10-25", "2025-10-25"), None, FIRST)
        with self.assertRaises(handler.PipelineError):
            handler._check_range(incremental("2025-10-26", "2025-10-26"), FIRST, FIRST)
        self.assertTrue(handler._check_range(incremental("2025-10-25", "2025-10-25"), FIRST, FIRST))
        self.assertFalse(handler._check_range(incremental(), FIRST, FIRST))
        with self.assertRaises(handler.PipelineError):
            handler._check_range(incremental("2025-10-23", "2025-10-23"), FIRST, FIRST)

    def test_correction_requires_loaded_date(self):
        plan = handler._validate_event({"action": "correction", "correction_date": "2025-10-24", "correction_version": "fix-001"}, TODAY)
        with self.assertRaises(handler.PipelineError):
            handler._check_range(plan, None, FIRST)
        self.assertTrue(handler._check_range(plan, FIRST, FIRST))


class AdapterTests(unittest.TestCase):
    def test_secrets_are_environment_only_and_use_verified_tls(self):
        client = MagicMock()
        client.get_secret_value.side_effect = [
            {"SecretString": '{"host":"example.invalid","port":5432,"username":"mock-user","password":"' + MOCK_PASSWORD + '"}'},
            {"SecretString": '{"pseudonymization_key":"' + MOCK_KEY + '"}'},
        ]
        config = {"rds_secret": "mock/rds", "key_secret": "mock/key", "database": "mock_database", "ca_path": "/mock/ca.pem"}
        env = handler._database_environment(config, client, None)
        self.assertEqual(env["PGPASSWORD"], MOCK_PASSWORD)
        self.assertEqual(env["KT_ND_ANALYSIS_PSEUDONYMIZATION_KEY"], MOCK_KEY)
        self.assertEqual(env["PGSSLMODE"], "verify-full")
        self.assertEqual(env["PGSSLROOTCERT"], "/mock/ca.pem")
        self.assertNotIn(MOCK_PASSWORD, handler.CONNECTION_OPTIONS)

    def test_default_and_weak_hmac_keys_are_rejected(self):
        for key in ("short", "kt-nd-synthetic-analysis-v1"):
            client = MagicMock()
            client.get_secret_value.side_effect = [
                {"SecretString": "{}"}, {"SecretString": '{"pseudonymization_key":"' + key + '"}'},
            ]
            with self.subTest(key=key), self.assertRaises(handler.PipelineError):
                handler._database_environment({"rds_secret": "mock/rds", "key_secret": "mock/key"}, client, None)

    def test_pipeline_arguments_do_not_contain_secrets(self):
        with patch.object(handler, "_command") as command:
            handler._pipeline(incremental(), Path("/tmp/mock-input"), {"PGPASSWORD": MOCK_PASSWORD}, None)
        arguments = command.call_args.args[0]
        self.assertNotIn(MOCK_PASSWORD, " ".join(arguments))
        self.assertNotIn(MOCK_KEY, " ".join(arguments))
        self.assertEqual(arguments[arguments.index("-ProcessingDate") + 1], "2025-10-25")
        self.assertNotIn("-AllowSyntheticDefaultKey", arguments)

    def test_queries_force_read_only_and_no_password_prompt(self):
        with patch.object(handler, "_command", return_value="t") as command:
            handler._has_pipeline_data({}, None)
        arguments, env = command.call_args.args[:2]
        self.assertIn("--no-password", arguments)
        self.assertIn("default_transaction_read_only=on", env["PGOPTIONS"])
        self.assertEqual(env["LC_ALL"], "C")
        self.assertTrue(command.call_args.kwargs["diagnose_database"])
        self.assertIn("\\gexec", command.call_args.kwargs["input_text"])

    def test_partition_listing_ignores_nested_versions_and_path_traversal(self):
        s3 = MagicMock()
        prefix = "kt-nd/raw/content_usage/event_date=2025-10-24/"
        s3.get_paginator.return_value.paginate.return_value = [{"Contents": [
            {"Key": prefix + "part-000.csv", "Size": 100},
            {"Key": prefix + "run_id=old/part-000.csv", "Size": 100},
            {"Key": prefix + "../part-000.csv", "Size": 100},
            {"Key": prefix + ".gitkeep", "Size": 0},
        ]}]
        config = {"bucket": "mock-bucket", "content_prefix": "kt-nd/raw/content_usage"}
        objects = handler._partition_objects(s3, config, incremental())
        self.assertEqual([item["path"] for item in objects], ["event_date=2025-10-24/part-000.csv"])

    def test_missing_partition_fails_before_pipeline(self):
        s3 = MagicMock()
        s3.get_paginator.return_value.paginate.return_value = [{}]
        with self.assertRaises(handler.PipelineError):
            handler._partition_objects(s3, {"bucket": "mock", "content_prefix": "raw"}, incremental())

    def test_correction_only_lists_requested_version(self):
        s3 = MagicMock()
        prefix = "raw/event_date=2025-10-24/run_id=fix-001/"
        s3.get_paginator.return_value.paginate.return_value = [{"Contents": [{"Key": prefix + "part-000.csv", "Size": 100}]}]
        plan = handler._validate_event({"action": "correction", "correction_date": "2025-10-24", "correction_version": "fix-001"}, TODAY)
        objects = handler._partition_objects(s3, {"bucket": "mock", "content_prefix": "raw"}, plan)
        self.assertEqual(objects[0]["path"], "event_date=2025-10-24/run_id=fix-001/part-000.csv")

    def test_storage_is_checked_before_download(self):
        s3 = MagicMock()
        with patch.object(handler.shutil, "disk_usage") as usage:
            usage.return_value.free = 1
            with self.assertRaises(handler.PipelineError):
                handler._download(s3, {"bucket": "mock"}, [{"size": 100}], Path("/tmp/mock"), None)
        s3.download_file.assert_not_called()

    def test_failed_command_does_not_expose_raw_output(self):
        process = MagicMock(returncode=1)
        process.communicate.return_value = (MOCK_PASSWORD, MOCK_KEY)
        with patch.object(handler.subprocess, "Popen", return_value=process):
            with self.assertRaises(handler.PipelineError) as error:
                handler._command(["mock-command"], {}, None, "Mock command")
        self.assertNotIn(MOCK_PASSWORD, str(error.exception))
        self.assertNotIn(MOCK_KEY, str(error.exception))
        self.assertNotIn("diagnostic=", str(error.exception))

    def test_database_connection_diagnostics_are_fixed_codes(self):
        samples = (
            ('fe_sendauth: no password supplied', "DB_PASSWORD_MISSING"),
            ('FATAL: password authentication failed for user "mock-user"', "DB_AUTH_FAILED"),
            ('FATAL: role "mock-user" does not exist', "DB_ROLE_NOT_FOUND"),
            ('FATAL: database "mock_database" does not exist', "DB_DATABASE_NOT_FOUND"),
            ('FATAL: no pg_hba.conf entry for host "192.0.2.1", user "mock-user", database "mock_database", SSL encryption', "DB_ACCESS_DENIED"),
            ('could not translate host name "example.invalid" to address: Name or service not known', "DB_DNS_FAILED"),
            ('root certificate file "/mock/ca.pem" does not exist', "DB_TLS_CA_FILE_ERROR"),
            ('could not read root certificate file "/mock/ca.pem": Permission denied', "DB_TLS_CA_FILE_ERROR"),
            ('server certificate for "example.invalid" does not match host name "other.invalid"', "DB_TLS_HOSTNAME_MISMATCH"),
            ('SSL error: certificate verify failed', "DB_TLS_VERIFY_FAILED"),
            ('connection to server at "example.invalid" (192.0.2.1), port 5432 failed: Connection refused', "DB_CONNECTION_REFUSED"),
            ('connection to server at "example.invalid" (192.0.2.1), port 5432 failed: timeout expired', "DB_CONNECT_TIMEOUT"),
            ('Connection timed out', "DB_CONNECT_TIMEOUT"),
            ('Network is unreachable', "DB_NETWORK_UNREACHABLE"),
            ('No route to host', "DB_NETWORK_UNREACHABLE"),
            ('server closed the connection unexpectedly', "DB_CONNECTION_CLOSED"),
            ('SSL error: unexpected eof while reading', "DB_TLS_FAILED"),
            ('server does not support SSL, but SSL was required', "DB_TLS_FAILED"),
            ('FATAL: unrecognized configuration parameter "mock_parameter"', "DB_CONNECTION_FAILED_UNKNOWN"),
            ('알 수 없는 연결 오류', "DB_CONNECTION_FAILED_UNKNOWN"),
            ('', "DB_CONNECTION_FAILED_UNKNOWN"),
        )
        for stderr, expected in samples:
            with self.subTest(expected=expected, stderr=stderr):
                self.assertEqual(handler._database_diagnostic(2, stderr), expected)

    def test_non_connection_errors_are_not_classified_from_sql_data(self):
        for returncode, expected in ((1, "DB_CLIENT_FAILED"), (3, "DB_QUERY_FAILED"), (-6, "DB_CLIENT_FAILED")):
            with self.subTest(returncode=returncode):
                self.assertEqual(handler._database_diagnostic(returncode, "password authentication failed"), expected)

    def test_query_failure_exposes_only_diagnostic_not_private_output(self):
        env = {"PGHOST": "example.invalid", "PGUSER": "mock-user", "PGDATABASE": "mock_database",
               "PGPASSWORD": MOCK_PASSWORD, "KT_ND_ANALYSIS_PSEUDONYMIZATION_KEY": MOCK_KEY,
               "LC_ALL": "ko_KR.UTF-8"}
        private_output = " | ".join(env.values()) + " mock-private-csv-row"
        for returncode, stderr, diagnostic in (
                (2, 'FATAL: password authentication failed for user "mock-user"', "DB_AUTH_FAILED"),
                (2, "unrecognized private error", "DB_CONNECTION_FAILED_UNKNOWN"),
                (3, "password authentication failed", "DB_QUERY_FAILED")):
            process = MagicMock(returncode=returncode)
            process.communicate.return_value = (private_output, stderr + "\n" + private_output)
            with self.subTest(diagnostic=diagnostic), patch.object(handler.subprocess, "Popen", return_value=process) as popen:
                with self.assertRaises(handler.PipelineError) as error:
                    handler._query("select 1;", env, None)
            message = str(error.exception)
            self.assertIn("diagnostic=" + diagnostic + ";", message)
            for private_value in (*env.values(), "mock-private-csv-row", stderr):
                self.assertNotIn(private_value, message)
            child_env = popen.call_args.kwargs["env"]
            self.assertEqual(child_env["LC_ALL"], "C")
            self.assertIn("default_transaction_read_only=on", child_env["PGOPTIONS"])
            self.assertEqual(env["LC_ALL"], "ko_KR.UTF-8")

    def test_successful_query_does_not_log_stderr(self):
        process = MagicMock(returncode=0)
        process.communicate.return_value = ("1\n", MOCK_PASSWORD + MOCK_KEY)
        with patch.object(handler.subprocess, "Popen", return_value=process), \
                patch.object(handler.LOGGER, "error") as error_log, patch.object(handler.LOGGER, "info") as info_log:
            self.assertEqual(handler._query("select 1;", {}, None), "1")
        error_log.assert_not_called()
        info_log.assert_not_called()

    def test_query_timeout_has_fixed_diagnostic_and_stops_process_group(self):
        process = MagicMock()
        process.communicate.side_effect = subprocess.TimeoutExpired("mock", 1, output=MOCK_PASSWORD, stderr=MOCK_KEY)
        with patch.object(handler.subprocess, "Popen", return_value=process), patch.object(handler, "_stop_process") as stop:
            with self.assertRaises(handler.PipelineError) as error:
                handler._query("select 1;", {}, None)
        stop.assert_called_once_with(process)
        self.assertIn("diagnostic=DB_COMMAND_TIMEOUT;", str(error.exception))
        self.assertNotIn(MOCK_PASSWORD, str(error.exception))
        self.assertNotIn(MOCK_KEY, str(error.exception))

    def test_timeout_stops_process_group(self):
        process = MagicMock()
        process.communicate.side_effect = subprocess.TimeoutExpired("mock", 1)
        with patch.object(handler.subprocess, "Popen", return_value=process), patch.object(handler, "_stop_process") as stop:
            with self.assertRaises(handler.PipelineError):
                handler._command(["mock-command"], {}, None, "Mock command")
        stop.assert_called_once_with(process)

    def test_expired_budget_does_not_start_process(self):
        context = MagicMock()
        context.get_remaining_time_in_millis.return_value = 1000
        with patch.object(handler.subprocess, "Popen") as process, self.assertRaises(handler.PipelineError):
            handler._command(["mock-command"], {}, context, "Mock command")
        process.assert_not_called()

    def test_audit_verification_requires_successful_batch_and_quality(self):
        batch = "00000000-0000-0000-0000-000000000001"
        plan = incremental()
        with patch.object(handler, "_query", side_effect=[batch, "t"]), \
                patch.object(handler, "_watermark", return_value=FIRST):
            self.assertEqual(handler._verify_run(plan, {}, None), batch)
        for responses in ([""], [batch, "f"]):
            with self.subTest(responses=responses), patch.object(handler, "_query", side_effect=responses), \
                    self.assertRaises(handler.PipelineError):
                handler._verify_run(plan, {}, None)

    def test_audit_verification_requires_requested_watermark(self):
        with patch.object(handler, "_query", side_effect=["00000000-0000-0000-0000-000000000001", "t"]), \
                patch.object(handler, "_watermark", return_value=None), \
                self.assertRaises(handler.PipelineError):
            handler._verify_run(incremental(), {}, None)

    def test_health_never_creates_aws_clients(self):
        with patch.object(handler.Path, "is_file", return_value=True), \
                patch.object(handler, "_command", side_effect=["psql (PostgreSQL) 18.6", "7.6.6"]), \
                patch.object(handler, "_aws_client") as client:
            result = handler.lambda_handler({"action": "health"}, None)
        client.assert_not_called()
        self.assertEqual(result["status"], "SUCCEEDED")
        self.assertFalse(result["database_accessed"])

    def test_health_rejects_wrong_client_major_version(self):
        with patch.object(handler.Path, "is_file", return_value=True), \
                patch.object(handler, "_command", return_value="psql (PostgreSQL) 15.19"), \
                self.assertRaises(handler.PipelineError):
            handler.lambda_handler({"action": "health"}, None)


class InvocationTests(unittest.TestCase):
    def setUp(self):
        self.patches = [
            patch.object(handler, "_today", return_value=TODAY),
            patch.object(handler, "_config", return_value={"ca_path": "/mock/ca.pem", "first_date": FIRST}),
            patch.object(handler.Path, "is_file", return_value=True),
            patch.object(handler, "_aws_client"),
            patch.object(handler, "_database_environment", return_value={}),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def test_initialize_cannot_clear_existing_data(self):
        with patch.object(handler, "_has_pipeline_data", return_value=True), patch.object(handler, "_pipeline") as pipeline:
            with self.assertRaises(handler.PipelineError):
                handler.lambda_handler({"action": "initialize", "confirm_initialize": True}, None)
        pipeline.assert_not_called()

    def test_already_processed_range_skips_download_and_pipeline(self):
        with patch.object(handler, "_watermark", return_value=FIRST), \
                patch.object(handler, "_partition_objects") as objects, \
                patch.object(handler, "_pipeline") as pipeline:
            result = handler.lambda_handler({"action": "incremental", "from_date": "2025-10-24", "to_date": "2025-10-24"}, None)
        self.assertEqual(result["status"], "ALREADY_PROCESSED")
        objects.assert_not_called()
        pipeline.assert_not_called()

    def test_incremental_flow_verifies_audit_after_pipeline(self):
        with patch.object(handler, "_watermark", return_value=None), \
                patch.object(handler, "_partition_objects", return_value=[{"size": 100}]), \
                patch.object(handler.tempfile, "TemporaryDirectory") as temporary, \
                patch.object(handler, "_download") as download, \
                patch.object(handler, "_pipeline") as pipeline, \
                patch.object(handler, "_verify_run", return_value="00000000-0000-0000-0000-000000000001") as verify:
            temporary.return_value.__enter__.return_value = "/tmp/mock-job"
            result = handler.lambda_handler({"action": "incremental", "from_date": "2025-10-24", "to_date": "2025-10-24"}, None)
        download.assert_called_once()
        pipeline.assert_called_once()
        verify.assert_called_once()
        self.assertEqual(result["status"], "SUCCEEDED")

    def test_sdk_errors_are_sanitized(self):
        with patch.object(handler, "_aws_client", side_effect=RuntimeError(MOCK_PASSWORD)), self.assertRaises(handler.PipelineError) as error:
            handler.lambda_handler({"action": "check"}, None)
        self.assertNotIn(MOCK_PASSWORD, str(error.exception))

    def test_failed_database_check_stops_before_s3_and_preserves_redaction(self):
        process = MagicMock(returncode=2)
        process.communicate.return_value = (MOCK_PASSWORD, 'FATAL: database "mock_database" does not exist\n' + MOCK_KEY)
        with patch.object(handler.subprocess, "Popen", return_value=process), \
                patch.object(handler, "_master_objects") as objects, patch.object(handler, "_pipeline") as pipeline, \
                patch.object(handler.LOGGER, "error") as log:
            with self.assertRaises(handler.PipelineError) as error:
                handler.lambda_handler({"action": "check"}, None)
        objects.assert_not_called()
        pipeline.assert_not_called()
        self.assertIn("diagnostic=DB_DATABASE_NOT_FOUND;", str(error.exception))
        for private_value in (MOCK_PASSWORD, MOCK_KEY, "mock_database"):
            self.assertNotIn(private_value, str(error.exception))
            self.assertNotIn(private_value, str(log.call_args))
        self.assertIn('"stage": "database_preflight"', log.call_args.args[0])

    def test_check_does_not_download_or_run_pipeline(self):
        with patch.object(handler, "_query", return_value="1"), \
                patch.object(handler, "_watermark", return_value=None), \
                patch.object(handler, "_master_objects", return_value=[{}] * 13), \
                patch.object(handler, "_download") as download, \
                patch.object(handler, "_pipeline") as pipeline:
            result = handler.lambda_handler({"action": "check"}, None)
        self.assertEqual(result["master_files_found"], 13)
        self.assertFalse(result["database_modified"])
        download.assert_not_called()
        pipeline.assert_not_called()


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)
    unittest.main()
