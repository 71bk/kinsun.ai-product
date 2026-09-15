async (page, { base = 'http://localhost:3107', folder = '.qa/' } = {}) => {
  const evidence = [];
  await page.setViewportSize({ width: 390, height: 844 });
  await page.context().addCookies([{ name: 'kinsun_ui_locale', value: 'en', url: base }]);
  for (const state of ['retry', 'conflict', 'denied', 'lostReceipt', 'noScope', 'keyboard']) {
    await page.unrouteAll({ behavior: 'wait' });
    await page.emulateMedia({ reducedMotion: state === 'keyboard' ? 'reduce' : 'no-preference' });
    const calls = [];
    let completed = false;
    const visit = {
      assignment_id: '00000000-0000-4000-8000-000000000002',
      elder_id: '00000000-0000-4000-8000-000000000003',
      provider_tenant_id: '00000000-0000-4000-8000-000000000004',
      care_unit_id: '00000000-0000-4000-8000-000000000005',
      home_care_worker_id: '00000000-0000-4000-8000-000000000006',
      scheduled_start: new Date(Date.now() - 3600000).toISOString(),
      scheduled_end: new Date(Date.now() + 3600000).toISOString(),
      expires_at: new Date(Date.now() + 3600000).toISOString(),
      status: 'IN_PROGRESS', version: 2,
      allowed_data_scopes: ['assignment:read', 'service_record:read', 'service_record:write', ...(state === 'noScope' ? [] : ['assignment:complete'])],
    };
    const envelope = data => ({ data, meta: { correlation_id: 'synthetic-completion-states', schema_version: '1.0', timestamp: new Date().toISOString() } });
    await page.route('**/backend/auth/session', route => route.fulfill({ json: { credential_present: true } }));
    await page.route('**/backend/core/**', async route => {
      const request = route.request();
      const path = request.url().split('?')[0];
      if (path.endsWith('/home-care/assignments')) return route.fulfill({ json: envelope({ items: completed ? [] : [visit] }) });
      if (path.endsWith('/service-record/complete')) {
        calls.push({ body: request.postDataJSON(), key: request.headers()['idempotency-key'] });
        if (state === 'conflict') return route.fulfill({ status: 409, json: { error: { code: 'conflict', message: 'Conflict' } } });
        if (state === 'denied') return route.fulfill({ status: 403, json: { error: { code: 'forbidden', message: 'Forbidden' } } });
        if (calls.length === 1 && ['retry', 'lostReceipt'].includes(state)) {
          completed = state === 'lostReceipt';
          return route.abort('failed');
        }
        if (completed) return route.fulfill({ status: 404, json: { error: { code: 'not_found', message: 'Resource not found' } } });
        completed = true;
        return route.fulfill({ status: 201, json: envelope({ service_record_id: '00000000-0000-4000-8000-000000000001', assignment_id: visit.assignment_id, assignment_version: 3, status: 'COMPLETED' }) });
      }
      return route.fulfill({ status: 404, json: { error: { code: 'not_found', message: 'Resource not found' } } });
    });
    await page.goto(`${base}/staff/assignments?qa=completion-state-${state}`);
    await page.getByRole('button', { name: 'Open service record', exact: true }).click();
    await page.locator('textarea').fill('Synthetic service note for failure-state verification.');
    if (state === 'noScope') {
      if (await page.getByRole('checkbox').count()) throw new Error('Completion offered without scope');
    } else {
      await page.getByRole('checkbox').check();
      await page.getByRole('button', { name: 'Review and submit', exact: true }).click();
      const dialog = page.locator('dialog[open]');
      await dialog.waitFor();
      if (state === 'keyboard') {
        const firstFocus = await page.evaluate(() => document.activeElement.textContent);
        if (firstFocus !== 'Cancel') throw new Error('Cancel not initially focused');
        await page.keyboard.press('Tab');
        if (await page.evaluate(() => document.activeElement.textContent) !== 'Confirm submission and complete visit') throw new Error('Confirm not keyboard reachable');
        await page.keyboard.press('Escape');
        if (await page.evaluate(() => document.activeElement.textContent) !== 'Review and submit') throw new Error('Focus not restored');
        if (!await page.evaluate(() => matchMedia('(prefers-reduced-motion: reduce)').matches)) throw new Error('Reduced motion not set');
      } else {
        await dialog.getByRole('button', { name: 'Confirm submission and complete visit', exact: true }).click();
        if (['retry', 'lostReceipt'].includes(state)) {
          await page.getByRole('button', { name: 'Retry the same submission', exact: true }).waitFor();
          if (!await page.locator('textarea').isDisabled() || !await page.getByRole('checkbox').isDisabled()) throw new Error('Uncertain submission not frozen');
          if (!await page.getByRole('button', { name: 'Complete service', exact: true }).isDisabled() || !await page.getByRole('button', { name: 'Close record (unsent text is not saved)', exact: true }).isDisabled()) throw new Error('Conflicting parent command enabled');
          await page.evaluate(() => window.scrollTo(0, 0));
          await page.screenshot({ path: `${folder}service-completion-${state}-pending-en-390.png`, fullPage: true });
          await page.getByRole('button', { name: 'Retry the same submission', exact: true }).click();
          await page.waitForFunction(() => document.querySelectorAll('textarea').length === 0);
          if (calls.length !== 2 || JSON.stringify(calls[0]) !== JSON.stringify(calls[1])) throw new Error('Retry changed key or payload');
        } else await page.waitForFunction(() => document.querySelectorAll('textarea').length === 0);
        if (state === 'retry') await page.getByText('Service record submitted and visit completed.', { exact: true }).waitFor();
        else if (await page.getByText('Service record submitted and visit completed.', { exact: true }).count()) throw new Error('False success');
        if (['denied', 'lostReceipt'].includes(state) && await page.getByRole('article').count()) throw new Error('Denied assignment retained');
      }
    }
    if (['noScope', 'keyboard'].includes(state) && calls.length) throw new Error('Unexpected POST');
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: `${folder}service-completion-state-${state}-en-390.png`, fullPage: true });
    const geometry = await page.evaluate(() => ({ client: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }));
    if (geometry.scroll > geometry.client) throw new Error('State overflows');
    evidence.push({ state, posts: calls.length, geometry, textareas: await page.locator('textarea').count(), articles: await page.getByRole('article').count() });
  }
  return evidence;
}
