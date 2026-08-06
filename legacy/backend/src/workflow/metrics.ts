import { CloudWatchClient, PutMetricDataCommand, type StandardUnit } from '@aws-sdk/client-cloudwatch';
import type { ErrorLog } from '@elderly-care/shared';

const NAMESPACE = 'ElderlyCare/Workflow';

let cachedClient: CloudWatchClient | null = null;
function getClient(): CloudWatchClient {
  if (!cachedClient) cachedClient = new CloudWatchClient({});
  return cachedClient;
}

export interface StageMetric {
  component: string;
  latencyMs: number;
  success: boolean;
}

/**
 * Writes per-stage latency + success/error-rate metrics to CloudWatch
 * (J04.1). Best-effort: a metrics-pipeline failure (missing region/creds in
 * a given environment, CloudWatch throttling, ...) must never fail the
 * actual voice interaction it's measuring, so failures here are logged and
 * swallowed rather than propagated.
 */
export async function recordStageMetric(metric: StageMetric): Promise<void> {
  const unit: StandardUnit = 'Milliseconds';
  try {
    await getClient().send(
      new PutMetricDataCommand({
        Namespace: NAMESPACE,
        MetricData: [
          {
            MetricName: 'StageLatency',
            Dimensions: [{ Name: 'Component', Value: metric.component }],
            Unit: unit,
            Value: metric.latencyMs,
          },
          {
            MetricName: metric.success ? 'StageSuccess' : 'StageError',
            Dimensions: [{ Name: 'Component', Value: metric.component }],
            Unit: 'Count',
            Value: 1,
          },
        ],
      }),
    );
  } catch (err) {
    console.error('[metrics] failed to publish stage metric', err instanceof Error ? err.message : err);
  }
}

/**
 * Structured JSON log line — CloudWatch Logs Insights can filter/aggregate
 * on `traceId` across every stage of one interaction (J04.2). X-Ray
 * correlates via the ambient _X_AMZN_TRACE_ID env var Lambda sets, not
 * anything we pass explicitly here.
 */
export function logError(entry: ErrorLog): void {
  console.error(JSON.stringify(entry));
}
