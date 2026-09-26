# Extraction timeout and retry policy (RF-207)

The extraction service uses a 30-second timeout for each provider attempt and
makes at most three attempts. Before a second or third attempt, it waits 0.25
or 0.5 seconds. Tests can supply a shorter `RetryPolicy` without making live
model calls. The final call record reports the number of attempts.

Retryable provider failures are SDK timeouts, connection errors, HTTP 408/409,
rate limits (429), and HTTP 5xx. All other HTTP 4xx and other SDK failures are
permanent. The application also treats a provider call that exceeds its own
30-second limit as a timeout. A completed but incomplete provider response is
permanent with the same request settings.

Refusals, empty output, malformed JSON, and invalid extraction data stop after
one attempt. The extraction service does not silently ask the model to repair
invalid content. Its `ExtractionError` retains a safe reason, final attempt
count, and provider failure kind (`timeout`, `transient`, or `permanent`) when
the failure came from the provider.

The OpenAI adapter disables the SDK's internal retries for each call. That
keeps the application's attempt limit observable and prevents retries from
being multiplied by SDK defaults. No model call is made by ordinary tests.
