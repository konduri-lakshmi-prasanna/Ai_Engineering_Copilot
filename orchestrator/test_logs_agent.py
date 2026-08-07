from agents.logs_agent import logs_agent

sample_log = """
2026-08-06 10:00:01 INFO Starting deployment
2026-08-06 10:00:05 ERROR Database connection failed
2026-08-06 10:00:06 Traceback (most recent call last):
2026-08-06 10:00:06 NullPointerException: Database URL is null
2026-08-06 10:00:10 INFO Retrying connection
"""

if __name__ == "__main__":
    result = logs_agent(sample_log)
    print(result)