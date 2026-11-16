from gemm_queue.api.settings import ApiSettings


class SweeperSettings(ApiSettings):
    # A queued run untouched for this long is treated as lost. The chaos tests
    # shorten both, so recovery takes seconds instead of minutes.
    sweeper_stuck_after_s: int = 600
    sweeper_interval_s: int = 60


settings = SweeperSettings()
