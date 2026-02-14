.PHONY: test test-backend test-frontend

test: test-backend test-frontend

test-backend:
	$(MAKE) -C backend test

test-frontend:
	cd frontend && npm run test
