document.addEventListener('submit', function (event) {
  if (event.target.dataset.confirm && !window.confirm(event.target.dataset.confirm)) {
    event.preventDefault();
    return;
  }
  const form = event.target.closest('form[data-progress]');
  if (!form) return;
  if (form.dataset.submitting) {
    event.preventDefault();
    return;
  }
  form.dataset.submitting = 'true';
  const panel = document.getElementById('ai-progress');
  if (!panel) return;
  const heading = panel.querySelector('h2');
  const message = panel.querySelector('p');
  if (heading && form.dataset.progressTitle) heading.textContent = form.dataset.progressTitle;
  if (message && form.dataset.progressMessage) message.textContent = form.dataset.progressMessage;
  panel.classList.add('visible');
  document.body.classList.add('busy');
  const button = form.querySelector('button[type="submit"],button:not([type])');
  if (button) button.disabled = true;
});

window.addEventListener('pageshow', () => {
  document.getElementById('ai-progress')?.classList.remove('visible');
  document.querySelectorAll('form[data-submitting]').forEach(form => {
    delete form.dataset.submitting;
    const button = form.querySelector('button[type="submit"],button:not([type])');
    if (button) button.disabled = false;
  });
});

const upload = document.querySelector('form.upload');
if (upload) {
  const category = upload.querySelector('[name="category"]');
  const file = upload.querySelector('[name="file"]');
  const updateFormats = () => {
    if (category.value === 'map') file.accept = '.png,.jpg,.jpeg,.gif,.webp';
    else if (category.value === 'transcript') file.accept = '.txt,text/plain';
    else if (category.value === 'draft') file.accept = '.docx';
    else if (category.value === 'assignment' || upload.dataset.sessionKind === 'reading' || upload.dataset.sessionKind === 'essay') file.accept = '.pdf,application/pdf';
    else file.accept = '.pdf,.pptx,.docx,.txt,.md,.csv';
  };
  category.addEventListener('change', updateFormats);
  updateFormats();
}

const timer = document.querySelector('[data-exam-timer]');
if (timer) {
  const started = Date.parse(timer.dataset.startedAt);
  const updateTimer = () => {
    const elapsed = Math.max(0, Math.floor((Date.now() - started) / 1000));
    const minutes = String(Math.floor(elapsed / 60)).padStart(2, '0');
    const seconds = String(elapsed % 60).padStart(2, '0');
    timer.textContent = `Tiempo: ${minutes}:${seconds}`;
  };
  updateTimer();
  window.setInterval(updateTimer, 1000);
}
