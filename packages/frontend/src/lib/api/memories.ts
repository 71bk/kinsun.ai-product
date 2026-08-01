import type { ConfirmedMemory, ListMemoriesResponse } from '@elderly-care/shared';
import { apiFetch, type ApiConfig } from './client';

/** GET /v1/elders/{elderId}/memories — candidates awaiting review + already-confirmed memories (D02.3, D04.1). */
export function listMemories(config: ApiConfig, elderId: string): Promise<ListMemoriesResponse> {
  return apiFetch(config, `/v1/elders/${elderId}/memories`);
}

/** PUT /v1/memories/{memoryId}/confirm (D02.3) */
export function confirmMemory(config: ApiConfig, elderId: string, memoryId: string, confirmerId: string): Promise<ConfirmedMemory> {
  return apiFetch(config, `/v1/memories/${memoryId}/confirm`, {
    method: 'PUT',
    body: JSON.stringify({ elderId, confirmerId }),
  });
}

/** PUT /v1/memories/{memoryId}/reject (D02.2) */
export function rejectMemory(config: ApiConfig, elderId: string, memoryId: string, rejecterId: string): Promise<void> {
  return apiFetch(config, `/v1/memories/${memoryId}/reject`, {
    method: 'PUT',
    body: JSON.stringify({ elderId, rejecterId }),
  });
}

/** DELETE /v1/memories/{memoryId}?elderId=... (D04.1) */
export function deleteMemory(config: ApiConfig, elderId: string, memoryId: string): Promise<void> {
  return apiFetch(config, `/v1/memories/${memoryId}?elderId=${encodeURIComponent(elderId)}`, { method: 'DELETE' });
}
