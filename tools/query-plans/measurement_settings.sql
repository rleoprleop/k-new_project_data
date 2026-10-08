-- Shared memory setting for every query-plan measurement entrypoint.
-- Include AFTER BEGIN. Change this value here to update all measurements.
-- COMMIT/ROLLBACK restores the original session value.
set local work_mem = '64MB';
