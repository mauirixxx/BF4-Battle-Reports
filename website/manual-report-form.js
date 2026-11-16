'use strict';
(() => {
  const form = document.getElementById('manual-report-form');
  if (!form) return;
  const input = document.getElementById('manual-report-url');
  const button = form.querySelector('button[type="submit"]');
  const feedback = document.getElementById('manual-report-feedback');
  let csrf = null;
  const endpoint = 'manual-report-gateway.php';
  async function token() {
    const response = await fetch(endpoint, {credentials:'same-origin',cache:'no-store'});
    if (!response.ok) throw new Error('Submission service unavailable');
    const body = await response.json();
    if (!body.csrf) throw new Error('Unable to initialize submission');
    csrf = body.csrf;
  }
  token().catch(() => { feedback.textContent = 'Report submission is temporarily unavailable.'; button.disabled = true; });
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!csrf || !input.value.trim()) return;
    button.disabled = true;
    feedback.textContent = 'Checking report…';
    try {
      const response = await fetch(endpoint, {
        method:'POST',credentials:'same-origin',
        headers:{'Content-Type':'application/json','X-BF4BR-CSRF':csrf},
        body:JSON.stringify({url:input.value.trim()})
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.error || body.detail || 'Unable to submit report');
      const messages = {
        already_complete:'This report is already archived and fully enriched.',
        enrichment_prioritized:'Report already archived. Remaining player details prioritized!',
        generic_prioritized:'Report queued for priority collection!'
      };
      feedback.textContent = messages[body.status] || 'Request received.';
    } catch (error) {
      feedback.textContent = error.message || 'Submission failed. Please retry later.';
    } finally { button.disabled = !csrf; }
  });
})();
