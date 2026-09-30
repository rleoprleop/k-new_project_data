"""Offline tests only: no AWS credentials, network calls, psql, or SQL execution."""

import logging
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
