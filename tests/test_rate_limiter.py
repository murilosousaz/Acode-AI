from src.infrastructure.adapters.rate_limiter import SlidingWindowRateLimiter


def test_blocks_after_limit_and_reports_retry_after():
    rl = SlidingWindowRateLimiter(requests_limit=2, window_seconds=60)
    assert rl.check("a").allowed and rl.check("a").allowed
    res = rl.check("a")
    assert not res.allowed and 0 < res.retry_after <= 60
    assert rl.check("b").allowed  # chaves independentes


def test_sweep_removes_idle_keys():
    rl = SlidingWindowRateLimiter(requests_limit=1, window_seconds=0)
    rl.check("a")
    rl._sweep(rl._hits["a"][0] + 1)
    assert "a" not in rl._hits
