export interface RetryPolicy {
  maxAttempts: number;
  intervalSeconds: number;
  backoffRate: number;
  retryableErrors: string[];
}

export type FallbackAction =
  | { type: 'default_response'; message: string }
  | { type: 'skip_node' }
  | { type: 'notify_and_terminate'; notificationTarget: string };

export interface WorkflowNodeConfig {
  nodeId: string;
  lambdaArn: string;
  inputSchema: unknown;
  outputSchema: unknown;
  timeoutSeconds: number;
  retryPolicy: RetryPolicy;
  fallbackAction: FallbackAction;
}

export interface DegradedResponse {
  type: 'prerecorded_audio' | 'static_text' | 'text_only';
  content: string;
  audioUrl?: string;
  retryAfterSeconds: number;
}

export interface ErrorLog {
  traceId: string;
  timestamp: string;
  component: 'asr' | 'llm' | 'tts' | 'context' | 'event_extractor' | 'memory' | string;
  errorType: 'timeout' | 'service_error' | 'validation_error' | 'permission_denied' | string;
  errorCode: string;
  message: string;
  elderId: string;
  retryAttempt: number;
  resolved: boolean;
  fallbackAction: string;
}
