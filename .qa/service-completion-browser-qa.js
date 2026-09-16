async (page, { base = 'http://localhost:3107', folder = '.qa/' } = {}) => {
  const evidence = [];
  for (const [locale, width, height] of [
    ['zh-Hant', 768, 1024], ['zh-Hant', 1440, 900],
    ['zh-Hant', 375, 812], ['zh-Hant', 390, 844], ['zh-Hant', 430, 932],
    ['en', 390, 844], ['en', 768, 1024],
  ]) {
    await page.unrouteAll({ behavior: 'wait' });
    await page.setViewportSize({ width, height });
    await page.context().addCookies([{ name: 'kinsun_ui_locale', value: locale, url: base }]);
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
      allowed_data_scopes: ['assignment:read', 'service_record:read', 'service_record:write', 'assignment:complete'],
    };
    const envelope = data => ({ data, meta: { correlation_id: 'synthetic-completion', schema_version: '1.0', timestamp: new Date().toISOString() } });
    await page.route('**/backend/auth/session', route => route.fulfill({ json: { credential_present: true } }));
    await page.route('**/backend/core/**', async route => {
      const request = route.request();
      const path = request.url().split('?')[0];
      if (path.endsWith('/home-care/assignments')) return route.fulfill({ json: envelope({ items: completed ? [] : [visit] }) });
      if (path.endsWith('/service-record/complete')) {
        calls.push({ path, body: request.postDataJSON(), key: request.headers()['idempotency-key'] });
        completed = true;
        return route.fulfill({ status: 201, json: envelope({ service_record_id: '00000000-0000-4000-8000-000000000001', assignment_id: visit.assignment_id, assignment_version: 3, status: 'COMPLETED' }) });
      }
      return route.fulfill({ status: 404, json: { error: { code: 'not_found', message: 'Resource not found' } } });
    });
    await page.goto(`${base}/staff/assignments?qa=combined-final-${locale}-${width}`);
    await page.getByRole('button', { name: locale === 'en' ? 'Open service record' : '開啟服務紀錄', exact: true }).click();
    await page.locator('textarea').fill(locale === 'en'
      ? 'Synthetic visit: completed the planned activity and documented the handover. This is test data.'
      : '合成測試紀錄：已完成本次安排的生活活動，並記錄交接事項。此內容僅供畫面測試。');
    await page.getByRole('checkbox').check();
    await page.evaluate(() => window.scrollTo(0, 0));
    const form = `service-completion-form-${locale}-${width}.png`;
    await page.screenshot({ path: folder + form, fullPage: true });
    const geometry = await page.evaluate(() => ({ inner: innerWidth, client: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth, checkboxLabelHeight: document.querySelector('input[type=checkbox]').closest('label').getBoundingClientRect().height }));
    if (geometry.scroll > geometry.client) throw new Error(`Form overflow ${locale}/${width}`);
    await page.getByRole('button', { name: locale === 'en' ? 'Review and submit' : '檢查並提交', exact: true }).click();
    const dialog = page.locator('dialog[open]');
    await dialog.waitFor();
    if (calls.length) throw new Error('Command sent before confirmation');
    const confirm = `service-completion-confirm-${locale}-${width}.png`;
    await page.screenshot({ path: folder + confirm });
    const box = await dialog.boundingBox();
    const dialogFits = box.x >= 0 && box.x + box.width <= geometry.inner + 1 && box.y >= 0 && box.y + box.height <= height + 1;
    if (!dialogFits) throw new Error(`Dialog outside viewport ${locale}/${width}`);
    await dialog.getByRole('button', { name: locale === 'en' ? 'Confirm submission and complete visit' : '確認提交並完成服務', exact: true }).click();
    await page.getByText(locale === 'en' ? 'Service record submitted and visit completed.' : '服務紀錄已提交，本次服務已完成。', { exact: true }).waitFor();
    await page.getByText(locale === 'en' ? 'No assignments that day' : '當日沒有派案', { exact: true }).waitFor();
    if (await page.locator('textarea').count() || await page.getByRole('article').count()) throw new Error('Completed visit content retained');
    if (calls.length !== 1) throw new Error('Duplicate combined command');
    const result = `service-completion-success-${locale}-${width}.png`;
    await page.screenshot({ path: folder + result });
    evidence.push({ locale, width, height, geometry, dialogFits, postCount: calls.length, fields: Object.keys(calls[0].body), form, confirm, result });
  }
  return evidence;
}
