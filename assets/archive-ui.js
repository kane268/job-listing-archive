(() => {
  const captureForm = document.getElementById('capture-form');
  if (captureForm) {
    captureForm.addEventListener('submit', event => {
      event.preventDefault();
      const input = document.getElementById('source-url');
      const url = (input?.value || '').trim();
      const repoUrl = captureForm.dataset.repoUrl || '';
      if (!url || !repoUrl) return;
      const params = new URLSearchParams({ title: 'Capture: ' + url, labels: 'capture', body: '' });
      window.open(repoUrl + '/issues/new?' + params.toString(), '_blank', 'noopener,noreferrer');
      captureForm.reset();
    });
  }

  const filterInput = document.getElementById('listing-filter-input');
  if (filterInput) {
    const cards = Array.from(document.querySelectorAll('.listing-card'));
    const applyFilter = () => {
      const query = filterInput.value.trim().toLowerCase();
      for (const card of cards) {
        const haystack = (card.dataset.search || card.textContent || '').toLowerCase();
        card.hidden = query !== '' && !haystack.includes(query);
      }
    };
    filterInput.addEventListener('input', applyFilter);
    applyFilter();
  }
})();
