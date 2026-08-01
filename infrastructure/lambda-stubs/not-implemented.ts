/**
 * Placeholder integration target for routes whose real Lambda hasn't been
 * wired into the CDK stack yet. Once packages/backend/src/handlers/* exists
 * for a route, pass it into Api's props (restHandlers / wsConnectFn / etc.)
 * instead of leaving it on this stub.
 */
export const handler = async () => ({
  statusCode: 501,
  body: JSON.stringify({ code: 'NOT_IMPLEMENTED', message: 'This route is not wired to a handler yet.' }),
});
