.PHONY: dev-up dev-down dev-status dev-infra-up dev-infra-down dev-infra-status dev-app-up dev-app-down dev-app-status dev-redis-up dev-redis-down dev-redis-status test-unit test-unit-fast test-unit-runtime test-live test-orchestration-benchmark-integration

dev-up: dev-infra-up dev-app-up

dev-down: dev-app-down dev-infra-down

dev-status: dev-infra-status dev-app-status

dev-infra-up:
	bash scripts/dev/up-infra.sh

dev-infra-down:
	bash scripts/dev/down-infra.sh

dev-infra-status:
	bash scripts/dev/status-infra.sh

dev-app-up:
	bash scripts/dev/up-redis-stack.sh

dev-app-down:
	bash scripts/dev/down-redis-stack.sh

dev-app-status:
	bash scripts/dev/status-redis-stack.sh

dev-redis-up:
	bash scripts/dev/up-infra.sh

dev-redis-down:
	bash scripts/dev/down-infra.sh

dev-redis-status:
	bash scripts/dev/status-infra.sh

test-unit-fast:
	PYTHONPATH=src pytest -q tests/unit -m fast

test-unit-runtime:
	PYTHONPATH=src pytest -q tests/unit -m runtime

test-unit:
	PYTHONPATH=src pytest -q tests/unit --durations=60 --durations-min=0.2

test-live:
	PYTHONPATH=src pytest --collect-only -q tests -m live

test-orchestration-benchmark-integration:
	bash scripts/dev/up-infra.sh
	bash -lc 'source scripts/dev/infra-env.sh && CRXZIPPLE_USE_EXTERNAL_TEST_INFRA=1 CRXZIPPLE_RUN_ORCHESTRATION_BENCHMARK_INTEGRATION=1 PYTHONPATH=src pytest -q tests/integration/test_orchestration_runtime_benchmark_postgres_redis.py -m "integration and benchmark"'
