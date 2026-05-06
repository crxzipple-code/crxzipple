.PHONY: dev-up dev-down dev-status dev-infra-up dev-infra-down dev-infra-status dev-app-up dev-app-down dev-app-status dev-redis-up dev-redis-down dev-redis-status

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
